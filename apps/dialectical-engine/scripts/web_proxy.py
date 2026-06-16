from __future__ import annotations

import argparse
import atexit
import http.client
import os
import signal
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit


HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
}
DEFAULT_COORDINATOR_PREFIXES = ("/api/", "/healthz", "/openapi.json", "/docs", "/redoc")
CLIENT_DISCONNECT_ERRORS = (BrokenPipeError, ConnectionResetError)
DEFAULT_NEXT_READY_TIMEOUT_SECONDS = 360


class WebProxy:
    def __init__(
        self,
        root: Path,
        pnpm: str,
        next_host: str,
        next_port: int,
        coordinator_host: str,
        coordinator_port: int,
        public_host: str,
        public_port: int,
        path_env: str | None = None,
        next_mode: str = "start",
        next_dist_dir: str | None = None,
        next_ready_timeout: float = DEFAULT_NEXT_READY_TIMEOUT_SECONDS,
    ) -> None:
        self.root = root
        self.web_dir = root / "web"
        self.pnpm = pnpm
        self.next_mode = next_mode
        self.next_host = next_host
        self.next_port = next_port
        self.coordinator_host = coordinator_host
        self.coordinator_port = coordinator_port
        self.public_host = public_host
        self.public_port = public_port
        self.path_env = path_env
        self.next_ready_timeout = next_ready_timeout
        self.next_dist_dir = next_dist_dir
        self.next_process: subprocess.Popen[bytes] | None = None

    def start_next(self) -> None:
        self.next_process = subprocess.Popen(self.next_command(), cwd=self.root, env=self.next_env())

    def next_env(self) -> dict[str, str]:
        env = os.environ.copy()
        if self.path_env:
            env["PATH"] = self.path_env
        env["DIALECTICAL_COORDINATOR_URL"] = f"http://{self.coordinator_host}:{self.coordinator_port}"
        configured_dist_dir = self.next_dist_dir or env.get("DIALECTICAL_NEXT_DIST_DIR")
        if configured_dist_dir:
            env["NEXT_DIST_DIR"] = configured_dist_dir
        elif self.next_mode == "dev":
            env["NEXT_DIST_DIR"] = ".next-dev"
        return env

    def next_command(self) -> list[str]:
        return [
            self.pnpm,
            "--dir",
            str(self.web_dir),
            "exec",
            "next",
            self.next_mode,
            "-H",
            self.next_host,
            "-p",
            str(self.next_port),
        ]

    def stop_next(self) -> None:
        proc = self.next_process
        if proc is None or proc.poll() is not None:
            return
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)

    def wait_for_next(self) -> None:
        deadline = time.monotonic() + self.next_ready_timeout
        while time.monotonic() < deadline:
            proc = self.next_process
            if proc is not None and proc.poll() is not None:
                raise RuntimeError(f"next start exited with code {proc.returncode}")
            try:
                conn = http.client.HTTPConnection(self.next_host, self.next_port, timeout=1)
                conn.request("HEAD", "/")
                conn.getresponse().read()
                conn.close()
                return
            except OSError:
                time.sleep(0.25)
        raise RuntimeError(f"next start did not become ready on port {self.next_port}")

    def monitor_next(self) -> None:
        proc = self.next_process
        if proc is None:
            return
        code = proc.wait()
        sys.stderr.write(f"next start exited with code {code}\n")
        sys.stderr.flush()
        os.kill(os.getpid(), signal.SIGTERM)

    def handler_class(self) -> type[BaseHTTPRequestHandler]:
        proxy = self

        class ProxyHandler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def do_GET(self) -> None:
                self.proxy()

            def do_HEAD(self) -> None:
                self.proxy()

            def do_POST(self) -> None:
                self.proxy()

            def do_PUT(self) -> None:
                self.proxy()

            def do_PATCH(self) -> None:
                self.proxy()

            def do_DELETE(self) -> None:
                self.proxy()

            def log_message(self, fmt: str, *args: object) -> None:
                sys.stdout.write(
                    "%s - - [%s] %s\n" % (self.address_string(), self.log_date_time_string(), fmt % args)
                )
                sys.stdout.flush()

            def proxy(self) -> None:
                target_host, target_port = (
                    (proxy.coordinator_host, proxy.coordinator_port)
                    if self.path.startswith(DEFAULT_COORDINATOR_PREFIXES)
                    else (proxy.next_host, proxy.next_port)
                )
                parsed = urlsplit(self.path)
                path = parsed.path or "/"
                if parsed.query:
                    path = f"{path}?{parsed.query}"

                body = None
                if self.command not in {"GET", "HEAD"}:
                    length = int(self.headers.get("Content-Length", "0") or "0")
                    body = self.rfile.read(length) if length else None

                headers = {
                    key: value
                    for key, value in self.headers.items()
                    if key.lower() not in HOP_BY_HOP_HEADERS and key.lower() != "host"
                }
                headers["Host"] = f"{target_host}:{target_port}"

                conn = http.client.HTTPConnection(target_host, target_port, timeout=60)
                try:
                    conn.request(self.command, path, body=body, headers=headers)
                    response = conn.getresponse()
                    self.send_response(response.status, response.reason)
                    for key, value in response.getheaders():
                        if key.lower() not in HOP_BY_HOP_HEADERS:
                            self.send_header(key, value)
                    if not response.getheader("Content-Length"):
                        self.close_connection = True
                    self.end_headers()
                    if self.command != "HEAD":
                        self.stream_response(response)
                except CLIENT_DISCONNECT_ERRORS:
                    self.close_connection = True
                except Exception as exc:  # noqa: BLE001 - keep proxy alive and surface failure.
                    message = f"Upstream proxy error: {exc}\n".encode()
                    try:
                        self.send_response(502, "Bad Gateway")
                        self.send_header("Content-Type", "text/plain; charset=utf-8")
                        self.send_header("Content-Length", str(len(message)))
                        self.end_headers()
                        self.wfile.write(message)
                    except CLIENT_DISCONNECT_ERRORS:
                        self.close_connection = True
                finally:
                    conn.close()

            def stream_response(self, response: http.client.HTTPResponse) -> None:
                content_type = response.getheader("Content-Type", "")
                if "text/event-stream" in content_type:
                    while True:
                        chunk = response.readline()
                        if not chunk:
                            return
                        try:
                            self.wfile.write(chunk)
                            self.wfile.flush()
                        except CLIENT_DISCONNECT_ERRORS:
                            self.close_connection = True
                            return
                else:
                    while True:
                        chunk = response.read(64 * 1024)
                        if not chunk:
                            return
                        try:
                            self.wfile.write(chunk)
                        except CLIENT_DISCONNECT_ERRORS:
                            self.close_connection = True
                            return

        return ProxyHandler

    def serve_forever(self) -> None:
        self.start_next()
        self.wait_for_next()

        monitor = threading.Thread(target=self.monitor_next, daemon=True)
        monitor.start()

        server = ThreadingHTTPServer((self.public_host, self.public_port), self.handler_class())
        sys.stdout.write(
            f"Proxy ready on {self.public_host}:{self.public_port}; "
            f"Next upstream {self.next_port}; API upstream {self.coordinator_port}\n"
        )
        sys.stdout.flush()
        server.serve_forever()


def default_launchd_path() -> str:
    return f"{Path.home()}/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Dialectical web UI behind a same-origin API proxy")
    parser.add_argument("--root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--pnpm", default=os.getenv("PNPM", "pnpm"))
    parser.add_argument("--next-host", default="127.0.0.1")
    parser.add_argument("--next-port", type=int, default=3001)
    parser.add_argument("--coordinator-host", default="127.0.0.1")
    parser.add_argument("--coordinator-port", type=int, default=8000)
    parser.add_argument("--public-host", default="0.0.0.0")
    parser.add_argument("--public-port", type=int, default=3000)
    parser.add_argument("--path", default=os.getenv("PATH", default_launchd_path()))
    parser.add_argument("--next-mode", choices=["start", "dev"], default="start")
    parser.add_argument("--next-dist-dir", default=os.getenv("DIALECTICAL_NEXT_DIST_DIR"))
    parser.add_argument(
        "--next-ready-timeout",
        type=float,
        default=float(os.getenv("DIALECTICAL_NEXT_READY_TIMEOUT", DEFAULT_NEXT_READY_TIMEOUT_SECONDS)),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    proxy = WebProxy(
        root=Path(args.root),
        pnpm=args.pnpm,
        next_host=args.next_host,
        next_port=args.next_port,
        coordinator_host=args.coordinator_host,
        coordinator_port=args.coordinator_port,
        public_host=args.public_host,
        public_port=args.public_port,
        path_env=args.path,
        next_mode=args.next_mode,
        next_dist_dir=args.next_dist_dir,
        next_ready_timeout=args.next_ready_timeout,
    )

    def handle_signal(signum: int, _frame: object) -> None:
        proxy.stop_next()
        raise SystemExit(128 + signum)

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)
    atexit.register(proxy.stop_next)
    proxy.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
