from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def load_web_proxy_module():
    spec = importlib.util.spec_from_file_location("dialectical_web_proxy", ROOT / "scripts" / "web_proxy.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DisconnectingWriter:
    def write(self, _chunk: bytes) -> None:
        raise BrokenPipeError("client disconnected")

    def flush(self) -> None:
        return


class FakeSseResponse:
    def __init__(self) -> None:
        self._sent = False

    def getheader(self, name: str, default: str = "") -> str:
        return "text/event-stream" if name.lower() == "content-type" else default

    def readline(self) -> bytes:
        if self._sent:
            return b""
        self._sent = True
        return b"data: hello\n\n"


class FakeBodyResponse:
    def __init__(self) -> None:
        self._sent = False

    def getheader(self, name: str, default: str = "") -> str:
        return "application/json" if name.lower() == "content-type" else default

    def read(self, _size: int) -> bytes:
        if self._sent:
            return b""
        self._sent = True
        return b'{"ok": true}'


def proxy_handler():
    module = load_web_proxy_module()
    proxy = module.WebProxy(
        root=ROOT,
        pnpm="pnpm",
        next_host="127.0.0.1",
        next_port=3001,
        coordinator_host="127.0.0.1",
        coordinator_port=8000,
        public_host="127.0.0.1",
        public_port=3000,
    )
    handler_cls = proxy.handler_class()
    handler = handler_cls.__new__(handler_cls)
    handler.wfile = DisconnectingWriter()
    handler.close_connection = False
    return handler


def test_web_proxy_uses_next_start_by_default() -> None:
    module = load_web_proxy_module()
    proxy = module.WebProxy(
        root=ROOT,
        pnpm="pnpm",
        next_host="127.0.0.1",
        next_port=3001,
        coordinator_host="127.0.0.1",
        coordinator_port=8000,
        public_host="127.0.0.1",
        public_port=3000,
    )

    assert proxy.next_command() == [
        "pnpm",
        "--dir",
        str(ROOT / "web"),
        "exec",
        "next",
        "start",
        "-H",
        "127.0.0.1",
        "-p",
        "3001",
    ]


def test_web_proxy_can_run_next_dev_behind_public_proxy() -> None:
    module = load_web_proxy_module()
    proxy = module.WebProxy(
        root=ROOT,
        pnpm="pnpm",
        next_host="127.0.0.1",
        next_port=3001,
        coordinator_host="127.0.0.1",
        coordinator_port=8000,
        public_host="127.0.0.1",
        public_port=3000,
        next_mode="dev",
    )

    assert proxy.next_command() == [
        "pnpm",
        "--dir",
        str(ROOT / "web"),
        "exec",
        "next",
        "dev",
        "-H",
        "127.0.0.1",
        "-p",
        "3001",
    ]


def test_web_proxy_uses_separate_dist_dir_for_next_dev() -> None:
    module = load_web_proxy_module()
    proxy = module.WebProxy(
        root=ROOT,
        pnpm="pnpm",
        next_host="127.0.0.1",
        next_port=3001,
        coordinator_host="127.0.0.1",
        coordinator_port=8000,
        public_host="127.0.0.1",
        public_port=3000,
        next_mode="dev",
    )

    assert proxy.next_env()["NEXT_DIST_DIR"] == ".next-dev"


def test_web_proxy_allows_custom_next_dev_dist_dir() -> None:
    module = load_web_proxy_module()
    proxy = module.WebProxy(
        root=ROOT,
        pnpm="pnpm",
        next_host="127.0.0.1",
        next_port=3001,
        coordinator_host="127.0.0.1",
        coordinator_port=8000,
        public_host="127.0.0.1",
        public_port=3000,
        next_mode="dev",
        next_dist_dir=".next-dev-smoke",
    )

    assert proxy.next_env()["NEXT_DIST_DIR"] == ".next-dev-smoke"


def test_web_proxy_forwards_custom_next_dist_dir_to_start_mode() -> None:
    module = load_web_proxy_module()
    proxy = module.WebProxy(
        root=ROOT,
        pnpm="pnpm",
        next_host="127.0.0.1",
        next_port=3001,
        coordinator_host="127.0.0.1",
        coordinator_port=8000,
        public_host="127.0.0.1",
        public_port=3000,
        next_mode="start",
        next_dist_dir=".next-dev-smoke",
    )

    assert proxy.next_env()["NEXT_DIST_DIR"] == ".next-dev-smoke"


def test_web_proxy_passes_coordinator_url_to_next_server() -> None:
    module = load_web_proxy_module()
    proxy = module.WebProxy(
        root=ROOT,
        pnpm="pnpm",
        next_host="127.0.0.1",
        next_port=3001,
        coordinator_host="127.0.0.1",
        coordinator_port=8765,
        public_host="127.0.0.1",
        public_port=3000,
        path_env="/tmp/bin",
    )

    env = proxy.next_env()

    assert env["DIALECTICAL_COORDINATOR_URL"] == "http://127.0.0.1:8765"
    assert env["PATH"] == "/tmp/bin"


def test_web_proxy_uses_longer_default_next_ready_timeout() -> None:
    module = load_web_proxy_module()
    proxy = module.WebProxy(
        root=ROOT,
        pnpm="pnpm",
        next_host="127.0.0.1",
        next_port=3001,
        coordinator_host="127.0.0.1",
        coordinator_port=8000,
        public_host="127.0.0.1",
        public_port=3000,
    )

    assert module.DEFAULT_NEXT_READY_TIMEOUT_SECONDS == 360
    assert proxy.next_ready_timeout == 360


def test_web_proxy_stream_response_treats_sse_disconnect_as_closed_connection() -> None:
    handler = proxy_handler()

    handler.stream_response(FakeSseResponse())

    assert handler.close_connection is True


def test_web_proxy_stream_response_treats_body_disconnect_as_closed_connection() -> None:
    handler = proxy_handler()

    handler.stream_response(FakeBodyResponse())

    assert handler.close_connection is True
