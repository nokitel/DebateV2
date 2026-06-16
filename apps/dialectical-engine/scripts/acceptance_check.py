from __future__ import annotations

import argparse
import json
import os
import re
import sys
import threading
import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID

import httpx


ROOT = Path(__file__).resolve().parents[1]
DNS_HOSTNAME_RE = re.compile(
    r"(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+"
    r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?",
    re.IGNORECASE,
)
WEB_AUTH_GATE_PATHS = ("/new", "/settings", "/admin/workers")
WEB_AUTH_GATE_MARKERS = ("Bearer Token", "User token", "Unlock")
WEB_AUTH_SURFACES: dict[str, tuple[Path, tuple[str, ...]]] = {
    "/new": (
        ROOT / "web" / "app" / "new" / "page.tsx",
        (
            "<AuthGate>",
            "NewDebateForm",
            "createDebate(",
            "New Debate",
            'htmlFor="topic"',
            "Role overrides JSON",
            "router.push(`/debate/${debate.id}`)",
        ),
    ),
    "/settings": (
        ROOT / "web" / "app" / "settings" / "page.tsx",
        (
            "<AuthGate>",
            "SettingsForm",
            '"/api/settings"',
            "Enabled models",
            "Backend spend",
            "Role routing JSON",
            "model_monthly_caps_usd",
            "Save",
        ),
    ),
    "/admin/workers": (
        ROOT / "web" / "app" / "admin" / "workers" / "page.tsx",
        (
            "<AuthGate>",
            "WorkersView",
            "backendStatus()",
            "Workers",
            "Current Job",
            "current_job_id",
            "Capabilities",
            "Worker B",
        ),
    ),
}
WEB_AUTH_TOKEN_FLOW: dict[str, tuple[Path, tuple[str, ...]]] = {
    "AuthGate": (
        ROOT / "web" / "components" / "AuthGate.tsx",
        (
            "getStoredToken()",
            "validateUserToken(stored)",
            "clearStoredToken()",
            "setStoredToken(value)",
            "setToken(value)",
            "Token was rejected by the coordinator.",
            "type=\"password\"",
            "children(token)",
        ),
    ),
    "api-client": (
        ROOT / "web" / "lib" / "api.ts",
        (
            "window.localStorage.getItem(\"dialectical:userToken\")",
            "window.localStorage.setItem(\"dialectical:userToken\", token)",
            "window.localStorage.removeItem(\"dialectical:userToken\")",
            "headers.set(\"Authorization\", `Bearer ${token}`)",
            "apiFetch<Record<string, unknown>>(\"/api/settings\", {}, token)",
        ),
    ),
}
WEB_DEBATE_ACTION_SURFACES: dict[str, tuple[Path, tuple[str, ...]]] = {
    "debate-page": (
        ROOT / "web" / "app" / "debate" / "[id]" / "DebatePageClient.tsx",
        (
            "getStoredToken()",
            "validateUserToken(stored)",
            "validateUserToken(value)",
            "setStoredToken(value)",
            "setActionToken(value)",
            "clearStoredToken()",
            "rejectActionToken",
            "Unlock Actions",
            "Lock Actions",
            "token={actionToken}",
            "onQueued={refresh}",
            "onAuthRejected={rejectActionToken}",
        ),
    ),
    "debate-tree": (
        ROOT / "web" / "components" / "DebateTree.tsx",
        (
            "regenerateNode(id, token)",
            "nodeGenerations(node.id, token)",
            "onQueued()",
            "onAuthRejected()",
            "looksAuthRelated(message)",
            "Regenerate",
            "History",
            "historyPanel",
            "Active",
            "Archived",
        ),
    ),
    "api-client": (
        ROOT / "web" / "lib" / "api.ts",
        (
            "regenerateNode(nodeId: string, token: string",
            "`/api/nodes/${nodeId}/regenerate`",
            "nodeGenerations(nodeId: string, token: string)",
            "`/api/nodes/${nodeId}/generations`",
        ),
    ),
}
WEB_STREAMING_CLIENT_SURFACES: dict[str, tuple[Path, tuple[str, ...]]] = {
    "debate-page": (
        ROOT / "web" / "app" / "debate" / "[id]" / "DebatePageClient.tsx",
        (
            "new EventSource(`${API_BASE}/api/debates/${id}/events`)",
            'events.addEventListener("tree_ready", () => refresh())',
            'events.addEventListener("node_started"',
            "beginNodeStream(current.tree",
            'events.addEventListener("node_token"',
            "appendToken(current.tree, nodeId, delta)",
            'events.addEventListener("node_complete", () => refresh())',
            'events.addEventListener("node_failed"',
            'events.addEventListener("synthesis_started"',
            'events.addEventListener("synthesis_token"',
            'events.addEventListener("synthesis_complete"',
            'events.addEventListener("debate_complete"',
            'events.addEventListener("error"',
            "events.onerror = () =>",
            "scheduleReconnect()",
            "partialJsonField(synthesisDraft?.raw || \"\", \"strongest_pro\")",
            "partialJsonField(synthesisDraft?.raw || \"\", \"strongest_con\")",
            "partialJsonField(synthesisDraft?.raw || \"\", \"verdict\")",
            'streamState.status === "live"',
            'streamState.status === "reconnecting"',
            'synthesisStreaming ? "cursor" : undefined',
        ),
    ),
    "debate-tree": (
        ROOT / "web" / "components" / "DebateTree.tsx",
        (
            'node.status === "generating" || node.status === "pending" ? "argument cursor" : "argument"',
            "data-model-id={generation?.model_id}",
            "data-worker-name={workerName}",
            "data-model-color={activeModelColor}",
            '"--model-color"',
            '"--node-model-color"',
        ),
    ),
}


@dataclass
class CheckResult:
    name: str
    detail: str
    evidence: Any | None = None


class AcceptanceError(RuntimeError):
    pass


@dataclass
class SseRecorder:
    base_url: str
    debate_id: str
    replay_history: bool = True
    events: list[str] = field(default_factory=list)
    tree_ready_payloads: list[dict[str, Any]] = field(default_factory=list)
    node_started_payloads: list[dict[str, Any]] = field(default_factory=list)
    node_complete_payloads: list[dict[str, Any]] = field(default_factory=list)
    synthesis_started_payloads: list[dict[str, Any]] = field(default_factory=list)
    synthesis_complete_payloads: list[dict[str, Any]] = field(default_factory=list)
    debate_complete_payloads: list[dict[str, Any]] = field(default_factory=list)
    node_token_count: int = 0
    synthesis_token_count: int = 0
    error: str | None = None
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)
    _stop: threading.Event = field(default_factory=threading.Event, init=False, repr=False)
    _thread: threading.Thread | None = field(default=None, init=False, repr=False)

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name=f"sse-{self.debate_id}", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3)

    def snapshot(
        self,
    ) -> tuple[
        list[str],
        list[dict[str, Any]],
        list[dict[str, Any]],
        list[dict[str, Any]],
        list[dict[str, Any]],
        list[dict[str, Any]],
        list[dict[str, Any]],
        int,
        int,
        str | None,
    ]:
        with self._lock:
            return (
                list(self.events),
                list(self.tree_ready_payloads),
                list(self.node_started_payloads),
                list(self.node_complete_payloads),
                list(self.synthesis_started_payloads),
                list(self.synthesis_complete_payloads),
                list(self.debate_complete_payloads),
                self.node_token_count,
                self.synthesis_token_count,
                self.error,
            )

    def _record(self, event: str, data: str) -> None:
        payload: dict[str, Any] | None = None
        if data:
            try:
                decoded = json.loads(data)
            except json.JSONDecodeError:
                decoded = None
            if isinstance(decoded, dict):
                payload = decoded
        with self._lock:
            self.events.append(event)
            if event == "node_token":
                self.node_token_count += 1
            elif event == "tree_ready" and payload is not None:
                self.tree_ready_payloads.append(payload)
            elif event == "node_started" and payload is not None:
                self.node_started_payloads.append(payload)
            elif event == "node_complete" and payload is not None:
                self.node_complete_payloads.append(payload)
            elif event == "synthesis_started" and payload is not None:
                self.synthesis_started_payloads.append(payload)
            elif event == "synthesis_complete" and payload is not None:
                self.synthesis_complete_payloads.append(payload)
            elif event == "debate_complete" and payload is not None:
                self.debate_complete_payloads.append(payload)
            elif event == "synthesis_token":
                self.synthesis_token_count += 1

    def _run(self) -> None:
        current_event = "message"
        current_data: list[str] = []
        try:
            timeout = httpx.Timeout(None, connect=10, read=20)
            with httpx.Client(base_url=self.base_url, timeout=timeout, follow_redirects=True) as client:
                with client.stream(
                    "GET",
                    f"/api/debates/{self.debate_id}/events",
                    params={"replay_history": str(self.replay_history).lower()},
                    headers={"Accept": "text/event-stream"},
                ) as response:
                    response.raise_for_status()
                    for line in response.iter_lines():
                        if self._stop.is_set():
                            return
                        if not line:
                            self._record(current_event, "\n".join(current_data))
                            current_event = "message"
                            current_data = []
                        elif line.startswith("event:"):
                            current_event = line.split(":", 1)[1].strip()
                        elif line.startswith("data:"):
                            current_data.append(line.split(":", 1)[1].lstrip())
        except Exception as exc:
            if not self._stop.is_set():
                with self._lock:
                    self.error = str(exc)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AcceptanceError(message)


def require_timezone_aware_iso_timestamp(value: object, label: str) -> str:
    require(isinstance(value, str) and value.strip(), f"{label} missing")
    raw_value = value.strip()
    parse_value = raw_value[:-1] + "+00:00" if raw_value.endswith("Z") else raw_value
    try:
        parsed = datetime.fromisoformat(parse_value)
    except ValueError as exc:
        raise AcceptanceError(f"{label} is not ISO formatted: {raw_value}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise AcceptanceError(f"{label} missing timezone")
    return raw_value


def require_uuid_value(value: object, label: str) -> str:
    require(isinstance(value, str) and value.strip(), f"{label} missing")
    raw_value = value.strip()
    try:
        UUID(raw_value)
    except ValueError as exc:
        raise AcceptanceError(f"{label} is not a UUID") from exc
    return raw_value


def named_https_url_issue(value: str) -> str | None:
    cleaned = value.strip().rstrip("/")
    if not cleaned:
        return "empty URL"
    if "<" in cleaned or ">" in cleaned or "debate.<your-domain>" in cleaned:
        return "placeholder URL"
    parsed = urlsplit(cleaned)
    if parsed.scheme != "https" or not parsed.netloc:
        return "must be an HTTPS URL"
    if parsed.username or parsed.password:
        return "must not include credentials"
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        return "must be the coordinator origin without a path, query, or fragment"
    hostname = (parsed.hostname or "").strip().rstrip(".").lower()
    if hostname in {"localhost", "local"} or hostname.startswith("127.") or hostname == "0.0.0.0" or hostname == "::1":
        return "must use a public DNS hostname, not a local URL"
    if hostname == "trycloudflare.com" or hostname.endswith(".trycloudflare.com"):
        return "must be a stable named Cloudflare hostname, not a trycloudflare.com quick tunnel"
    if not DNS_HOSTNAME_RE.fullmatch(hostname):
        return "must use a DNS hostname such as debate.example.com"
    return None


def require_named_https_url(value: str, label: str) -> None:
    if issue := named_https_url_issue(value):
        raise AcceptanceError(f"{label} must be a named HTTPS origin: {issue}")


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def fetch_json(client: httpx.Client, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
    response = client.request(method, path, **kwargs)
    if response.status_code >= 400:
        raise AcceptanceError(f"{method} {path} failed with {response.status_code}: {response.text[:500]}")
    return response.json()


def require_rejected(response: httpx.Response, label: str, statuses: set[int] | None = None) -> None:
    expected = statuses or {401, 403}
    require(response.status_code in expected, f"{label} was not rejected: {response.status_code}")


def rejection_evidence(
    response: httpx.Response,
    label: str,
    method: str,
    path: str,
    statuses: set[int] | None = None,
) -> dict[str, Any]:
    expected = statuses or {401, 403}
    require_rejected(response, label, expected)
    return {
        "label": label,
        "method": method,
        "path": path,
        "status_code": response.status_code,
        "expected_statuses": sorted(expected),
        "rejected": True,
    }


def auth_boundaries_detail(evidence: dict[str, Any]) -> str:
    return "public read open; write/settings blocked without valid token"


def public_list_detail(evidence: dict[str, Any]) -> str:
    return f"{evidence['debate_count']} debates visible without auth"


def public_list_evidence(payload: dict[str, Any]) -> dict[str, Any]:
    items = payload.get("items")
    require(isinstance(items, list), "Public debates list did not return an items array")
    limit = payload.get("limit")
    offset = payload.get("offset")
    require(isinstance(limit, int) and not isinstance(limit, bool) and limit > 0, "Public debates list missing limit")
    require(isinstance(offset, int) and not isinstance(offset, bool) and offset >= 0, "Public debates list missing offset")
    rows = []
    for item in items:
        require(isinstance(item, dict), "Public debates list item is not an object")
        debate_id = item.get("id")
        topic = item.get("topic")
        status = item.get("status")
        created_at = item.get("created_at")
        completed_at = item.get("completed_at")
        models = item.get("models")
        require(isinstance(debate_id, str) and debate_id.strip(), "Public debates list item missing id")
        require(isinstance(topic, str) and topic.strip(), f"Public debate {debate_id} missing topic")
        require(isinstance(status, str) and status.strip(), f"Public debate {debate_id} missing status")
        require(status != "archived", f"Public debate {debate_id} was archived")
        created_at = require_timezone_aware_iso_timestamp(created_at, f"Public debate {debate_id} created_at")
        if completed_at is not None:
            completed_at = require_timezone_aware_iso_timestamp(
                completed_at,
                f"Public debate {debate_id} completed_at",
            )
        require(isinstance(models, list), f"Public debate {debate_id} missing models list")
        rows.append(
            {
                "id": debate_id,
                "topic": topic,
                "status": status,
                "created_at": created_at,
                "completed_at": completed_at,
                "models": sorted({str(model).strip() for model in models if str(model).strip()}),
            }
        )
    return {
        "method": "GET",
        "path": "/api/debates",
        "status_code": 200,
        "accepted": True,
        "debate_count": len(rows),
        "limit": limit,
        "offset": offset,
        "items": rows,
    }


def require_public_list_current_debate(
    evidence: dict[str, Any],
    debate_id: str,
    topic: str,
    model_ids: Iterable[str],
) -> None:
    rows = evidence.get("items")
    require(isinstance(rows, list), "Public debates list evidence did not include items")
    current = next((row for row in rows if isinstance(row, dict) and row.get("id") == debate_id), None)
    require(current is not None, f"Public debates list missing current debate {debate_id}")
    require(current.get("topic") == topic, "Public debates list current debate topic mismatch")
    require(current.get("status") == "complete", "Public debates list current debate is not complete")
    models = current.get("models")
    require(isinstance(models, list), "Public debates list current debate missing models")
    present_models = {str(model).strip() for model in models if str(model).strip()}
    missing_models = sorted({str(model).strip() for model in model_ids if str(model).strip()} - present_models)
    require(
        not missing_models,
        "Public debates list current debate missing model badges: " + ", ".join(missing_models),
    )


def auth_boundaries_evidence(
    public_debate_count: int,
    unauth_create: httpx.Response,
    unauth_settings: httpx.Response,
    wrong_token_settings: httpx.Response,
) -> dict[str, Any]:
    checks = [
        {
            "label": "public-list",
            "method": "GET",
            "path": "/api/debates",
            "status_code": 200,
            "accepted": True,
            "debate_count": public_debate_count,
        },
        rejection_evidence(unauth_create, "unauthenticated create", "POST", "/api/debates"),
        rejection_evidence(unauth_settings, "unauthenticated settings", "GET", "/api/settings"),
        rejection_evidence(wrong_token_settings, "invalid-token settings", "GET", "/api/settings", {403}),
    ]
    return {
        "public_read_open": True,
        "write_blocked_without_token": True,
        "settings_blocked_without_token": True,
        "invalid_token_blocked": True,
        "checks": checks,
    }


def write_auth_boundaries_detail(evidence: dict[str, Any]) -> str:
    return "history, regenerate, and archive reject missing or invalid user tokens"


def write_auth_boundaries_evidence(client: httpx.Client, debate_id: str, node_id: str) -> dict[str, Any]:
    generations_path = f"/api/nodes/{node_id}/generations"
    regenerate_path = f"/api/nodes/{node_id}/regenerate"
    archive_path = f"/api/debates/{debate_id}"
    checks = [
        rejection_evidence(
            client.get(generations_path),
            "unauthenticated generation history",
            "GET",
            generations_path,
        ),
        rejection_evidence(
            client.get(generations_path, headers=auth_headers("invalid-token")),
            "invalid-token generation history",
            "GET",
            generations_path,
            {403},
        ),
        rejection_evidence(
            client.post(regenerate_path, json={}),
            "unauthenticated regenerate",
            "POST",
            regenerate_path,
        ),
        rejection_evidence(
            client.post(regenerate_path, headers=auth_headers("invalid-token"), json={}),
            "invalid-token regenerate",
            "POST",
            regenerate_path,
            {403},
        ),
        rejection_evidence(client.delete(archive_path), "unauthenticated archive", "DELETE", archive_path),
        rejection_evidence(
            client.delete(archive_path, headers=auth_headers("invalid-token")),
            "invalid-token archive",
            "DELETE",
            archive_path,
            {403},
        ),
    ]
    return {
        "debate_id": debate_id,
        "node_id": node_id,
        "history_blocked": True,
        "regenerate_blocked": True,
        "archive_blocked": True,
        "invalid_token_blocked": True,
        "checks": checks,
    }


def require_write_auth_boundaries(client: httpx.Client, debate_id: str, node_id: str) -> str:
    return write_auth_boundaries_detail(write_auth_boundaries_evidence(client, debate_id, node_id))


def check_web_page(client: httpx.Client, path: str, markers: list[str]) -> None:
    response = client.get(path, headers={"Accept": "text/html"})
    if response.status_code >= 400:
        raise AcceptanceError(f"GET {path} web page failed with {response.status_code}: {response.text[:500]}")
    content_type = response.headers.get("content-type", "")
    require("text/html" in content_type, f"GET {path} did not return HTML: {content_type}")
    require(
        any(marker in response.text for marker in markers),
        f"GET {path} HTML did not contain any expected marker: {markers}",
    )


def check_web_page_all(client: httpx.Client, path: str, markers: list[str]) -> None:
    response = client.get(path, headers={"Accept": "text/html"})
    if response.status_code >= 400:
        raise AcceptanceError(f"GET {path} web page failed with {response.status_code}: {response.text[:500]}")
    content_type = response.headers.get("content-type", "")
    require("text/html" in content_type, f"GET {path} did not return HTML: {content_type}")
    missing = [marker for marker in markers if marker not in response.text]
    require(not missing, f"GET {path} HTML was missing expected markers: {missing}")


def web_home_detail(evidence: dict[str, Any]) -> str:
    detail = f"{evidence['base_url']}/ returned HTML"
    debate_id = str(evidence.get("current_debate_id") or "").strip()
    if debate_id:
        detail += f" with /debate/{debate_id}"
    topic = str(evidence.get("current_topic") or "").strip()
    if topic:
        detail += f" for {topic}"
    return detail


def web_home_evidence(
    client: httpx.Client,
    base_url: str,
    current_debate_id: str = "",
    current_topic: str = "",
    current_status: str = "",
    current_model_ids: Iterable[str] = (),
) -> dict[str, Any]:
    markers = ["Debates", "Public archive"]
    debate_id = current_debate_id.strip()
    topic = current_topic.strip()
    status = current_status.strip()
    model_ids = sorted({model_id.strip() for model_id in current_model_ids if model_id.strip()})
    response = client.get("/", headers={"Accept": "text/html"})
    if response.status_code >= 400:
        raise AcceptanceError(f"GET / web page failed with {response.status_code}: {response.text[:500]}")
    content_type = response.headers.get("content-type", "")
    require("text/html" in content_type, f"GET / did not return HTML: {content_type}")
    missing = [marker for marker in markers if marker not in response.text]
    require(not missing, f"GET / HTML was missing expected markers: {missing}")
    debate_link = f"/debate/{debate_id}" if debate_id else ""
    if debate_id:
        require(debate_link in response.text, f"GET / HTML missing current debate link: {debate_link}")
    if topic:
        require(topic in response.text, "GET / HTML missing current debate topic")
    if status:
        require(status in response.text, f"GET / HTML missing current debate status: {status}")
    missing_models = [model_id for model_id in model_ids if model_id not in response.text]
    require(not missing_models, f"GET / HTML missing current debate model badges: {missing_models}")
    return {
        "method": "GET",
        "path": "/",
        "status_code": response.status_code,
        "content_type": content_type,
        "byte_count": len(response.text),
        "base_url": base_url.rstrip("/"),
        "required_markers": markers,
        "markers_present": {marker: marker in response.text for marker in markers},
        "debates_heading": "Debates" in response.text,
        "public_archive_copy": "Public archive" in response.text,
        "new_debate_link": "/new" in response.text,
        "debate_link_count": response.text.count("/debate/"),
        "current_debate_id": debate_id,
        "current_debate_link": bool(debate_link and debate_link in response.text),
        "current_topic": topic,
        "current_topic_present": bool(topic and topic in response.text),
        "current_status": status,
        "current_status_present": bool(status and status in response.text),
        "current_model_ids": model_ids,
        "current_model_markers_present": {model_id: model_id in response.text for model_id in model_ids},
    }


def web_auth_gates_evidence(client: httpx.Client) -> dict[str, Any]:
    routes = []
    for path in WEB_AUTH_GATE_PATHS:
        response = client.get(path, headers={"Accept": "text/html"})
        if response.status_code >= 400:
            raise AcceptanceError(f"GET {path} web page failed with {response.status_code}: {response.text[:500]}")
        content_type = response.headers.get("content-type", "")
        require("text/html" in content_type, f"GET {path} did not return HTML: {content_type}")
        missing = [marker for marker in WEB_AUTH_GATE_MARKERS if marker not in response.text]
        require(not missing, f"GET {path} HTML was missing expected auth-gate markers: {missing}")
        routes.append(
            {
                "path": path,
                "byte_count": len(response.text),
                "content_type": content_type,
                "bearer_token_prompt": "Bearer Token" in response.text,
                "user_token_prompt": "User token" in response.text,
                "unlock_button": "Unlock" in response.text,
            }
        )
    return {
        "route_count": len(routes),
        "routes": routes,
        "required_markers": list(WEB_AUTH_GATE_MARKERS),
    }


def source_marker_evidence(surfaces: dict[str, tuple[Path, tuple[str, ...]]], label: str) -> dict[str, Any]:
    rows = []
    for name, (source_path, markers) in surfaces.items():
        try:
            source = source_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise AcceptanceError(f"{name} {label} source is unreadable: {source_path} ({exc})") from exc
        missing = [marker for marker in markers if marker not in source]
        require(not missing, f"{name} {label} source missing markers: {missing}")
        try:
            relative_path = str(source_path.relative_to(ROOT))
        except ValueError:
            relative_path = str(source_path)
        rows.append(
            {
                "label": name,
                "path": relative_path,
                "marker_count": len(markers),
                "markers_present": True,
                "required_markers": list(markers),
            }
        )
    return {
        "surface_count": len(rows),
        "marker_count": sum(int(row["marker_count"]) for row in rows),
        "surfaces": rows,
    }


def require_web_auth_surfaces() -> str:
    source_marker_evidence(WEB_AUTH_SURFACES, "post-unlock")
    return "post-unlock source markers present for " + ", ".join(WEB_AUTH_SURFACES)


def require_web_auth_token_flow() -> str:
    source_marker_evidence(WEB_AUTH_TOKEN_FLOW, "auth token-flow")
    return "token validation, storage, bearer header, rejection clearing, and child render source markers present"


def require_web_debate_actions() -> str:
    source_marker_evidence(WEB_DEBATE_ACTION_SURFACES, "debate-action")
    return "unlock, regenerate, history, archived-generation, API, refresh, and auth-rejection source markers present"


def require_web_streaming_client() -> str:
    source_marker_evidence(WEB_STREAMING_CLIENT_SURFACES, "streaming-client")
    return "SSE subscription, node/synthesis token rendering, reconnect, metadata color, and refresh source markers present"


def web_debate_detail_evidence(
    response: httpx.Response,
    path: str,
    topic: str,
    worker_names: set[str],
    model_ids: set[str],
) -> dict[str, Any]:
    text = response.text
    debate_id = path.rstrip("/").split("/")[-1]
    export_href = f"/api/debates/{debate_id}/export.md"
    return {
        "byte_count": len(text),
        "content_type": response.headers.get("content-type", ""),
        "path": path,
        "debate_id": debate_id,
        "topic": topic,
        "topic_present": topic in text,
        "export_button": "Export Markdown" in text,
        "export_href": export_href,
        "same_origin_export_link": f'href="{export_href}"' in text,
        "localhost_export_link": f"http://localhost:8000/api/debates/{debate_id}/export.md" in text,
        "auth_gate_controls": "User token" in text and "Unlock Actions" in text,
        "synthesis_markers": all(marker in text for marker in ("Strongest Pro", "Strongest Con", "Verdict")),
        "worker_markers_present": all(worker_name in text for worker_name in worker_names),
        "model_markers_present": all(model_id in text for model_id in model_ids),
        "model_color_markers": all(
            marker in text
            for marker in ("data-model-id=", "data-worker-name=", "data-model-color=", "--model-color:", "--node-model-color:")
        ),
        "worker_names": sorted(worker_names),
        "model_ids": sorted(model_ids),
        "worker_count": len(worker_names),
        "model_count": len(model_ids),
    }


def web_debate_detail_result(
    client: httpx.Client,
    path: str,
    topic: str,
    worker_names: set[str],
    model_ids: set[str],
) -> tuple[str, dict[str, Any]]:
    response = client.get(path, headers={"Accept": "text/html"})
    if response.status_code >= 400:
        raise AcceptanceError(f"GET {path} web page failed with {response.status_code}: {response.text[:500]}")
    content_type = response.headers.get("content-type", "")
    require("text/html" in content_type, f"GET {path} did not return HTML: {content_type}")
    debate_id = path.rstrip("/").split("/")[-1]
    export_href = f"/api/debates/{debate_id}/export.md"
    required = [
        topic,
        "Export Markdown",
        f'href="{export_href}"',
        "User token",
        "Unlock Actions",
        "Strongest Pro",
        "Strongest Con",
        "Verdict",
    ]
    required.extend(sorted(worker_names))
    required.extend(sorted(model_ids))
    required.extend(["data-model-id=", "data-worker-name=", "data-model-color=", "--model-color:", "--node-model-color:"])
    missing = [marker for marker in required if marker not in response.text]
    require(not missing, f"GET {path} HTML was missing expected debate detail markers: {missing}")
    forbidden = [f"http://localhost:8000/api/debates/{debate_id}/export.md"]
    present_forbidden = [marker for marker in forbidden if marker in response.text]
    require(not present_forbidden, f"GET {path} HTML contained forbidden debate detail markers: {present_forbidden}")
    return (
        f"{len(worker_names)} workers; {len(model_ids)} models",
        web_debate_detail_evidence(response, path, topic, worker_names, model_ids),
    )


def check_web_debate_detail(
    client: httpx.Client,
    path: str,
    topic: str,
    worker_names: set[str],
    model_ids: set[str],
) -> str:
    summary, _ = web_debate_detail_result(client, path, topic, worker_names, model_ids)
    return summary


def flatten_nodes(node: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not node:
        return []
    rows = [node]
    for child in node.get("children", []):
        rows.extend(flatten_nodes(child))
    return rows


def first_argument_node(debate: dict[str, Any]) -> dict[str, Any]:
    for node in flatten_nodes(debate.get("tree")):
        if node.get("node_type") in {"PRO", "CON"}:
            return node
    raise AcceptanceError("No argument node found for regeneration check")


def wait_for_debate(client: httpx.Client, debate_id: str, predicate, timeout: int, label: str) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    last: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        last = fetch_json(client, "GET", f"/api/debates/{debate_id}")
        if predicate(last):
            return last
        time.sleep(1)
    status = last.get("status") if last else "unknown"
    raise AcceptanceError(f"Timed out waiting for {label}; last debate status was {status}")


def worker_names_from_tree(debate: dict[str, Any]) -> set[str]:
    names: set[str] = set()
    for node in flatten_nodes(debate.get("tree")):
        generation = node.get("active_generation") or {}
        worker_name = generation.get("worker_name")
        if worker_name:
            names.add(worker_name)
    return names


def generated_node_metadata_detail(evidence: dict[str, Any]) -> str:
    return (
        f"{evidence['argument_node_count']} argument nodes; "
        f"{evidence['model_count']} models; "
        f"{evidence['worker_count']} workers"
    )


def generated_node_metadata_evidence(debate: dict[str, Any]) -> dict[str, Any]:
    nodes = [node for node in flatten_nodes(debate.get("tree")) if node.get("node_type") in {"PRO", "CON"}]
    require(nodes, "No generated argument nodes found")
    models: set[str] = set()
    workers: set[str] = set()
    node_rows: list[dict[str, Any]] = []
    for node in nodes:
        node_id = str(node.get("id") or "unknown")
        require(node.get("status") == "complete", f"Argument node {node_id} is not complete: {node.get('status')}")
        generation = node.get("active_generation")
        require(isinstance(generation, dict), f"Argument node {node_id} is missing active_generation")
        require(
            node.get("active_generation_id") == generation.get("id"),
            f"Argument node {node_id} active_generation_id does not match active_generation.id",
        )
        model_id = generation.get("model_id")
        worker_id = generation.get("worker_id")
        worker_name = generation.get("worker_name")
        role = generation.get("role")
        argument = generation.get("argument")
        require(isinstance(model_id, str) and model_id, f"Argument node {node_id} missing model_id")
        require(isinstance(worker_id, str) and worker_id, f"Argument node {node_id} missing worker_id")
        require(isinstance(worker_name, str) and worker_name, f"Argument node {node_id} missing worker_name")
        require(isinstance(role, str) and role, f"Argument node {node_id} missing role")
        require(isinstance(argument, str) and argument, f"Argument node {node_id} missing argument")
        models.add(model_id)
        workers.add(worker_name)
        node_rows.append(
            {
                "id": node_id,
                "node_type": node.get("node_type"),
                "status": node.get("status"),
                "active_generation_id": node.get("active_generation_id"),
                "generation_id": generation.get("id"),
                "model_id": model_id,
                "worker_id": worker_id,
                "worker_name": worker_name,
                "role": role,
                "argument_present": True,
                "argument_length": len(argument),
            }
        )
    return {
        "argument_node_count": len(nodes),
        "model_count": len(models),
        "worker_count": len(workers),
        "model_ids": sorted(models),
        "worker_names": sorted(workers),
        "nodes": sorted(node_rows, key=lambda row: str(row["id"])),
    }


def require_generated_node_metadata(debate: dict[str, Any]) -> str:
    return generated_node_metadata_detail(generated_node_metadata_evidence(debate))


def require_synthesis_evidence(synthesis: object, label: str) -> dict[str, str]:
    require(isinstance(synthesis, dict), f"{label} missing synthesis payload")
    evidence: dict[str, str] = {}
    for field in (
        "id",
        "debate_id",
        "strongest_pro",
        "strongest_con",
        "verdict",
        "model_id",
        "worker_id",
        "worker_name",
        "created_at",
    ):
        value = synthesis.get(field)
        require(isinstance(value, str) and value.strip(), f"{label} synthesis missing {field}")
        evidence[field] = value.strip()
    require_timezone_aware_iso_timestamp(evidence["created_at"], f"{label} synthesis created_at")
    return evidence


def canonical_utc_timestamp(value: object, label: str) -> str:
    raw_value = require_timezone_aware_iso_timestamp(value, label)
    parse_value = raw_value[:-1] + "+00:00" if raw_value.endswith("Z") else raw_value
    parsed = datetime.fromisoformat(parse_value)
    parsed = parsed.astimezone(timezone.utc)
    return parsed.isoformat()


def worker_status_payload_detail(evidence: dict[str, Any]) -> str:
    return (
        f"{evidence['worker_count']} workers; "
        f"{evidence['capability_count']} capabilities; "
        f"{evidence['busy_count']} busy"
    )


def worker_capability_values(capabilities: object, label: str) -> list[str]:
    require(isinstance(capabilities, list), f"{label} missing capabilities list")
    normalized: list[str] = []
    seen: set[str] = set()
    for index, capability in enumerate(capabilities, start=1):
        require(isinstance(capability, str), f"{label} capability {index} is not a string")
        value = capability.strip()
        require(value, f"{label} capability {index} is blank")
        require(value not in seen, f"{label} duplicate capability: {value}")
        seen.add(value)
        normalized.append(value)
    return sorted(normalized)


def worker_status_row_evidence(worker: dict[str, Any]) -> dict[str, Any]:
    worker_name = worker.get("name")
    require(isinstance(worker_name, str) and worker_name.strip(), "Worker status row missing name")
    name = worker_name.strip()
    status = worker.get("status")
    allowed_statuses = {"online", "offline", "degraded"}
    require(status in allowed_statuses, f"Worker {name} has invalid status {status!r}")
    require("current_job_id" in worker, f"Worker {name} missing current_job_id")
    current_job_id = worker.get("current_job_id")
    if current_job_id is not None:
        current_job_id = require_uuid_value(current_job_id, f"Worker {name} current_job_id")
    return {
        "id": require_uuid_value(worker.get("id"), f"Worker {name} id"),
        "name": name,
        "status": status,
        "capabilities": worker_capability_values(worker.get("capabilities"), f"Worker {name}"),
        "current_job_id": current_job_id,
        "last_seen": canonical_utc_timestamp(worker.get("last_seen"), f"Worker {name} last_seen"),
    }


def worker_status_payload_evidence(workers: object, online: list[dict[str, Any]]) -> dict[str, Any]:
    require(isinstance(workers, list), "Worker status payload did not include a workers list")
    unique_capabilities: set[str] = set()
    busy_workers = 0
    rows: list[dict[str, Any]] = []
    for worker in workers:
        require(isinstance(worker, dict), "Worker status row is not an object")
        row = worker_status_row_evidence(worker)
        if row["current_job_id"]:
            busy_workers += 1
        unique_capabilities.update(row["capabilities"])
        rows.append(row)

    for worker in online:
        require(worker.get("capabilities"), f"Online worker {worker.get('name')} has no capabilities")

    rows.sort(key=lambda row: str(row["name"]))
    online_names = sorted(str(row["name"]) for row in rows if row["status"] == "online")
    offline_names = sorted(str(row["name"]) for row in rows if row["status"] == "offline")
    degraded_names = sorted(str(row["name"]) for row in rows if row["status"] == "degraded")
    return {
        "worker_count": len(rows),
        "online_count": len(online_names),
        "offline_count": len(offline_names),
        "degraded_count": len(degraded_names),
        "busy_count": busy_workers,
        "capability_count": len(unique_capabilities),
        "capabilities": sorted(unique_capabilities),
        "online_worker_names": online_names,
        "offline_worker_names": offline_names,
        "degraded_worker_names": degraded_names,
        "workers": rows,
    }


def require_worker_status_payload(workers: object, online: list[dict[str, Any]]) -> str:
    return worker_status_payload_detail(worker_status_payload_evidence(workers, online))


def require_offline_worker_names(workers: list[dict[str, Any]], expected_names: set[str]) -> str:
    if not expected_names:
        return "no offline workers required"
    rows_by_name = {str(worker.get("name")): worker for worker in workers if isinstance(worker.get("name"), str)}
    missing = expected_names - set(rows_by_name)
    require(not missing, f"Expected offline workers missing from /api/backends/status: {sorted(missing)}")
    wrong_status = {
        name: rows_by_name[name].get("status")
        for name in expected_names
        if rows_by_name[name].get("status") != "offline"
    }
    require(
        not wrong_status,
        "Expected workers to be offline: "
        + ", ".join(f"{name} is {status!r}" for name, status in sorted(wrong_status.items())),
    )
    return ", ".join(sorted(expected_names))


def model_ids_from_tree(debate: dict[str, Any]) -> set[str]:
    models: set[str] = set()
    for node in flatten_nodes(debate.get("tree")):
        generation = node.get("active_generation") or {}
        model_id = generation.get("model_id")
        if model_id:
            models.add(model_id)
    synthesis = debate.get("synthesis") or {}
    synthesis_model = synthesis.get("model_id")
    if synthesis_model:
        models.add(synthesis_model)
    return models


def active_generation_ids_from_tree(debate: dict[str, Any]) -> set[str]:
    generation_ids: set[str] = set()
    missing_node_ids: list[str] = []
    for node in flatten_nodes(debate.get("tree")):
        generation = node.get("active_generation") or {}
        generation_id = node.get("active_generation_id") or generation.get("id")
        if generation_id:
            generation_ids.add(str(generation_id))
        else:
            missing_node_ids.append(str(node.get("id") or "unknown"))
    require(
        not missing_node_ids,
        "Revisited debate missing active generation ids for nodes: " + ", ".join(missing_node_ids),
    )
    return generation_ids


def require_markdown_generation_history(markdown: str, history_items: list[dict[str, Any]]) -> str:
    require("## Generation History" in markdown, "Markdown export missing generation history section")
    require(history_items, "Generation history check did not receive any history items")
    archived_count = 0
    for item in history_items:
        generation_id = str(item.get("id") or "")
        require(generation_id, "Generation history item missing id")
        required_values = {
            "id": generation_id,
            "model_id": item.get("model_id"),
            "worker_name": item.get("worker_name"),
            "argument": item.get("argument"),
        }
        for field, value in required_values.items():
            require(isinstance(value, str) and value, f"Generation history {generation_id} missing {field}")
            require(value in markdown, f"Markdown export missing generation history {field}: {value}")
        if item.get("is_active") is False:
            archived_count += 1
    require(archived_count > 0, "Markdown export history check did not include an archived generation")
    require("**Archived**" in markdown, "Markdown export missing archived generation marker")
    require("**Active**" in markdown, "Markdown export missing active generation marker")
    return f"{len(history_items)} generations; {archived_count} archived"


def generation_history_evidence(
    node_id: str,
    history_items: list[dict[str, Any]],
    archived_generation: dict[str, Any],
    active_generation: dict[str, Any],
) -> dict[str, Any]:
    def compact_generation(item: dict[str, Any]) -> dict[str, Any]:
        argument = str(item.get("argument") or "")
        return {
            "id": item.get("id"),
            "model_id": item.get("model_id"),
            "worker_id": item.get("worker_id"),
            "worker_name": item.get("worker_name"),
            "role": item.get("role"),
            "is_active": item.get("is_active"),
            "created_at": item.get("created_at"),
            "argument_present": bool(argument.strip()),
            "argument_length": len(argument),
            "latency_ms": item.get("latency_ms"),
            "tokens_in": item.get("tokens_in"),
            "tokens_out": item.get("tokens_out"),
        }

    active_ids = sorted(str(item.get("id")) for item in history_items if item.get("is_active") is True)
    archived_ids = sorted(str(item.get("id")) for item in history_items if item.get("is_active") is False)
    return {
        "node_id": node_id,
        "generation_count": len(history_items),
        "active_count": len(active_ids),
        "archived_count": len(archived_ids),
        "active_generation_id": active_generation.get("id"),
        "archived_generation_id": archived_generation.get("id"),
        "active_generation": compact_generation(active_generation),
        "archived_generation": compact_generation(archived_generation),
    }


def regenerate_request_detail(evidence: dict[str, Any]) -> str:
    return f"job {evidence['job_id']} for node {evidence['node_id']}"


def regenerate_request_evidence(
    response: dict[str, Any],
    debate_id: str,
    node_id: str,
    previous_generation_id: str | None,
    previous_synthesis_id: str | None,
) -> dict[str, Any]:
    job_id = response.get("job_id")
    status = response.get("status")
    require(isinstance(job_id, str) and job_id.strip(), "Regenerate did not return a job id")
    require(status == "queued", f"Regenerate response status was not queued: {status!r}")
    require(isinstance(node_id, str) and node_id.strip(), "Regenerate request target node id missing")
    require(isinstance(debate_id, str) and debate_id.strip(), "Regenerate request debate id missing")
    require(
        isinstance(previous_generation_id, str) and previous_generation_id.strip(),
        "Regenerate request previous generation id missing",
    )
    require(
        isinstance(previous_synthesis_id, str) and previous_synthesis_id.strip(),
        "Regenerate request previous synthesis id missing",
    )
    return {
        "debate_id": debate_id,
        "node_id": node_id,
        "job_id": job_id.strip(),
        "status": status,
        "previous_generation_id": previous_generation_id.strip(),
        "previous_synthesis_id": previous_synthesis_id.strip(),
        "accepted": True,
    }


def markdown_export_evidence(
    response: httpx.Response,
    topic: str,
    debate_id: str,
    worker_names: set[str],
    model_ids: set[str],
    history_items: list[dict[str, Any]],
) -> dict[str, Any]:
    text = response.text
    content_disposition = response.headers.get("content-disposition", "")
    content_type = response.headers.get("content-type", "")
    history_generation_ids = sorted(str(item.get("id") or "") for item in history_items if item.get("id"))
    active_generation_ids = sorted(
        str(item.get("id") or "") for item in history_items if item.get("id") and item.get("is_active") is True
    )
    archived_generation_ids = sorted(
        str(item.get("id") or "") for item in history_items if item.get("id") and item.get("is_active") is False
    )
    return {
        "debate_id": debate_id,
        "topic": topic,
        "byte_count": len(text),
        "content_disposition": content_disposition,
        "content_type": content_type,
        "attachment": "attachment" in content_disposition.lower(),
        "filename": f"debate-{debate_id}.md" in content_disposition,
        "filename_debate_id": f"debate-{debate_id}.md" in content_disposition,
        "topic_present": topic in text,
        "synthesis_section": "## Synthesis" in text,
        "tree_section": "## Tree" in text,
        "generation_history_section": "## Generation History" in text,
        "worker_metadata": "**Workers:**" in text,
        "model_metadata": "**Models:**" in text,
        "worker_names": sorted(worker_names),
        "model_ids": sorted(model_ids),
        "history_generation_ids": history_generation_ids,
        "active_generation_ids": active_generation_ids,
        "archived_generation_ids": archived_generation_ids,
        "history_generation_count": len(history_items),
        "archived_history_count": sum(1 for item in history_items if item.get("is_active") is False),
    }


def require_node_started_payloads(payloads: list[dict[str, Any]], label: str) -> None:
    require(payloads, f"{label} did not capture node_started payloads")
    for index, payload in enumerate(payloads, start=1):
        for key in ("node_id", "model_id", "worker_id", "role"):
            value = payload.get(key)
            require(isinstance(value, str) and value, f"{label} node_started #{index} missing {key}: {payload}")


def require_tree_ready_payloads(payloads: list[dict[str, Any]], label: str) -> None:
    require(payloads, f"{label} did not capture tree_ready payloads")
    for index, payload in enumerate(payloads, start=1):
        tree = payload.get("tree")
        require(isinstance(tree, dict), f"{label} tree_ready #{index} missing tree object: {payload}")
        root_tree = tree.get("tree") if isinstance(tree.get("tree"), dict) else tree
        node_id = root_tree.get("id")
        require(isinstance(node_id, str) and node_id, f"{label} tree_ready #{index} tree missing id: {payload}")
        children = root_tree.get("children")
        require(isinstance(children, list), f"{label} tree_ready #{index} tree missing children list: {payload}")


def require_synthesis_started_payloads(payloads: list[dict[str, Any]], label: str) -> None:
    require(payloads, f"{label} did not capture synthesis_started payloads")
    for index, payload in enumerate(payloads, start=1):
        for key in ("debate_id", "model_id", "worker_id"):
            value = payload.get(key)
            require(isinstance(value, str) and value, f"{label} synthesis_started #{index} missing {key}: {payload}")


def require_synthesis_complete_payloads(payloads: list[dict[str, Any]], label: str) -> None:
    require(payloads, f"{label} did not capture synthesis_complete payloads")
    for index, payload in enumerate(payloads, start=1):
        synthesis = payload.get("synthesis")
        require(isinstance(synthesis, dict), f"{label} synthesis_complete #{index} missing synthesis object: {payload}")
        for key in ("strongest_pro", "strongest_con", "verdict"):
            value = synthesis.get(key)
            require(
                isinstance(value, str) and value.strip(),
                f"{label} synthesis_complete #{index} synthesis missing {key}: {payload}",
            )


def require_debate_complete_payloads(payloads: list[dict[str, Any]], label: str, debate_id: str) -> None:
    require(payloads, f"{label} did not capture debate_complete payloads")
    for index, payload in enumerate(payloads, start=1):
        value = payload.get("debate_id")
        require(isinstance(value, str) and value, f"{label} debate_complete #{index} missing debate_id: {payload}")
        require(value == debate_id, f"{label} debate_complete #{index} debate_id mismatch: {value}, want {debate_id}")


def require_node_complete_payloads(payloads: list[dict[str, Any]], label: str) -> None:
    require(payloads, f"{label} did not capture node_complete payloads")
    for index, payload in enumerate(payloads, start=1):
        for key in ("node_id", "generation_id"):
            value = payload.get(key)
            require(isinstance(value, str) and value, f"{label} node_complete #{index} missing {key}: {payload}")


SSE_REQUIRED_EVENTS = (
    "connected",
    "node_started",
    "node_complete",
    "synthesis_started",
    "synthesis_complete",
    "debate_complete",
)


def event_indexes(events: list[str], event_type: str) -> list[int]:
    return [index for index, event in enumerate(events) if event == event_type]


def require_sse_event_order(events: list[str], label: str) -> None:
    indexes = {event_type: event_indexes(events, event_type) for event_type in set(events)}

    def require_before(first_event: str, second_event: str) -> None:
        first = indexes.get(first_event) or []
        second = indexes.get(second_event) or []
        if first and second:
            require(
                first[0] < second[0],
                f"{label} emitted {second_event} before {first_event}: {events}",
            )

    def require_all_before(first_event: str, second_event: str) -> None:
        first = indexes.get(first_event) or []
        second = indexes.get(second_event) or []
        if first and second:
            require(
                first[-1] < second[0],
                f"{label} emitted {second_event} before all {first_event} events completed: {events}",
            )

    require_before("connected", "node_started")
    require_before("connected", "tree_ready")
    require_before("node_started", "node_token")
    require_before("node_started", "node_complete")
    require_before("tree_ready", "synthesis_started")
    require_all_before("node_started", "synthesis_started")
    require_all_before("node_token", "synthesis_started")
    require_all_before("node_complete", "synthesis_started")
    require_before("synthesis_started", "synthesis_token")
    require_before("synthesis_started", "synthesis_complete")
    require_all_before("synthesis_token", "synthesis_complete")
    require_before("synthesis_complete", "debate_complete")


def sse_stream_detail(evidence: dict[str, Any]) -> str:
    return (
        f"{evidence['event_count']} events, "
        f"{evidence['node_token_count']} node tokens, "
        f"{evidence['synthesis_token_count']} synthesis tokens"
    )


def sse_stream_evidence(recorder: SseRecorder, *, require_tree_ready: bool = False) -> dict[str, Any]:
    recorder.stop()
    (
        events,
        tree_ready_payloads,
        node_started_payloads,
        node_complete_payloads,
        synthesis_started_payloads,
        synthesis_complete_payloads,
        debate_complete_payloads,
        node_tokens,
        synthesis_tokens,
        error,
    ) = recorder.snapshot()
    require(error is None, f"SSE stream failed: {error}")
    seen = set(events)
    require("connected" in seen, "SSE stream did not emit the connected event")
    if require_tree_ready:
        require("tree_ready" in seen, f"SSE stream missed tree_ready; saw {events}")
        require_tree_ready_payloads(tree_ready_payloads, "SSE stream")
    require("node_started" in seen, f"SSE stream missed node_started; saw {events}")
    require_node_started_payloads(node_started_payloads, "SSE stream")
    require(node_tokens > 0, f"SSE stream did not emit node_token events; saw {events}")
    require("node_complete" in seen, f"SSE stream missed node_complete; saw {events}")
    require_node_complete_payloads(node_complete_payloads, "SSE stream")
    require("synthesis_started" in seen, f"SSE stream missed synthesis_started; saw {events}")
    require_synthesis_started_payloads(synthesis_started_payloads, "SSE stream")
    require(synthesis_tokens > 0, f"SSE stream did not emit synthesis_token events; saw {events}")
    require("synthesis_complete" in seen, f"SSE stream missed synthesis_complete; saw {events}")
    require_synthesis_complete_payloads(synthesis_complete_payloads, "SSE stream")
    require("debate_complete" in seen, f"SSE stream missed debate_complete; saw {events}")
    require_debate_complete_payloads(debate_complete_payloads, "SSE stream", recorder.debate_id)
    require_sse_event_order(events, "SSE stream")
    event_type_counts: dict[str, int] = {}
    for event in events:
        event_type_counts[event] = event_type_counts.get(event, 0) + 1
    required_events = list(SSE_REQUIRED_EVENTS) + ["node_token", "synthesis_token"]
    if require_tree_ready:
        required_events.append("tree_ready")
    return {
        "event_count": len(events),
        "event_sequence": events,
        "replay_history": bool(getattr(recorder, "replay_history", False)),
        "node_token_count": node_tokens,
        "synthesis_token_count": synthesis_tokens,
        "event_type_counts": dict(sorted(event_type_counts.items())),
        "required_events": required_events,
        "required_events_present": {event: event in seen or event_type_counts.get(event, 0) > 0 for event in required_events},
        "tree_ready_required": require_tree_ready,
        "tree_ready_count": len(tree_ready_payloads),
        "tree_ready_payloads": tree_ready_payloads,
        "node_started_count": len(node_started_payloads),
        "node_complete_count": len(node_complete_payloads),
        "synthesis_started_count": len(synthesis_started_payloads),
        "synthesis_complete_count": len(synthesis_complete_payloads),
        "debate_complete_count": len(debate_complete_payloads),
        "node_started_payloads": node_started_payloads,
        "node_complete_payloads": node_complete_payloads,
        "synthesis_started_payloads": synthesis_started_payloads,
        "synthesis_complete_payloads": synthesis_complete_payloads,
        "debate_complete_payloads": debate_complete_payloads,
    }


def require_sse_stream(recorder: SseRecorder) -> str:
    return sse_stream_detail(sse_stream_evidence(recorder))


def require_non_negative_number(value: Any, label: str) -> float:
    require(not isinstance(value, bool), f"{label} must be a non-negative number")
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise AcceptanceError(f"{label} must be a non-negative number") from None
    require(number == number and number not in {float("inf"), float("-inf")} and number >= 0, f"{label} must be non-negative")
    return number


def require_numeric_model_map(value: Any, label: str) -> dict[str, float]:
    require(isinstance(value, dict), f"Settings response missing {label} object")
    result: dict[str, float] = {}
    for model_id, raw_number in value.items():
        require(isinstance(model_id, str) and model_id.strip(), f"{label} contains a blank model id")
        result[model_id.strip()] = require_non_negative_number(raw_number, f"{label}.{model_id}")
    return result


def require_model_pricing_map(value: Any) -> dict[str, dict[str, float]]:
    require(isinstance(value, dict), "Settings response missing model pricing object")
    pricing: dict[str, dict[str, float]] = {}
    for model_id, raw_pricing in value.items():
        require(isinstance(model_id, str) and model_id.strip(), "model pricing contains a blank model id")
        require(isinstance(raw_pricing, dict), f"model pricing for {model_id} must be an object")
        require("input" in raw_pricing and "output" in raw_pricing, f"model pricing for {model_id} missing input/output rates")
        pricing[model_id.strip()] = {
            "input": require_non_negative_number(raw_pricing["input"], f"model_pricing.{model_id}.input"),
            "output": require_non_negative_number(raw_pricing["output"], f"model_pricing.{model_id}.output"),
        }
    return pricing


def settings_round_trip_detail(evidence: dict[str, Any]) -> str:
    return (
        f"{evidence['configured_model_count']} configured models; "
        f"model cap restored for {evidence['cap_model']}; "
        f"Grok cap ${float(evidence['original_grok_cap_usd']):.2f}"
    )


def settings_round_trip_evidence(client: httpx.Client, token: str) -> dict[str, Any]:
    headers = auth_headers(token)
    original = fetch_json(client, "GET", "/api/settings", headers=headers)
    routing = original.get("routing")
    configured_models = original.get("configured_models")
    enabled_models = original.get("enabled_models")
    grok_pricing = original.get("grok_pricing_usd_per_million_tokens")
    require(isinstance(routing, dict), "Settings response missing routing object")
    require(isinstance(configured_models, list), "Settings response missing configured_models list")
    require(isinstance(enabled_models, list), "Settings response missing enabled_models list")
    require(configured_models, "Settings response has no configured models")
    require(isinstance(grok_pricing, dict), "Settings response missing Grok pricing")
    require("input" in grok_pricing and "output" in grok_pricing, "Grok pricing missing input/output rates")
    require("grok_monthly_cap_usd" in original, "Settings response missing Grok monthly cap")
    require("grok_monthly_spend_usd" in original, "Settings response missing Grok monthly spend")
    require_non_negative_number(original["grok_monthly_cap_usd"], "grok_monthly_cap_usd")
    require_non_negative_number(original["grok_monthly_spend_usd"], "grok_monthly_spend_usd")
    original_model_caps = require_numeric_model_map(
        original.get("model_monthly_caps_usd"),
        "model_monthly_caps_usd",
    )
    original_model_spend = require_numeric_model_map(
        original.get("model_monthly_spend_usd"),
        "model_monthly_spend_usd",
    )
    require_model_pricing_map(original.get("model_pricing_usd_per_million_tokens"))
    configured_model_set = {str(model).strip() for model in configured_models if str(model).strip()}
    require(configured_model_set, "Settings response has no usable configured models")
    unknown_cap_models = sorted(model for model in original_model_caps if model not in configured_model_set)
    require(not unknown_cap_models, f"Settings returned caps for models outside routing: {', '.join(unknown_cap_models)}")
    missing_spend_models = sorted(model for model in configured_model_set if model not in original_model_spend)
    require(not missing_spend_models, f"Settings response missing spend for configured models: {', '.join(missing_spend_models)}")

    original_enabled = list(enabled_models)
    original_cap = float(original["grok_monthly_cap_usd"])
    ordered_configured_models = sorted(configured_model_set)
    cap_model = next((model for model in ordered_configured_models if model != "grok-4"), ordered_configured_models[0])
    original_model_cap = original_model_caps.get(cap_model, 0.0)
    temporary_enabled = [cap_model]
    temporary_cap = round(original_cap + 0.01, 2)
    if temporary_cap == original_cap:
        temporary_cap = original_cap + 1
    temporary_model_cap = temporary_cap if cap_model == "grok-4" else round(original_model_cap + 1.0, 2)
    if temporary_model_cap == original_model_cap:
        temporary_model_cap = original_model_cap + 1
    temporary_model_caps = dict(original_model_caps)
    temporary_model_caps[cap_model] = temporary_model_cap

    try:
        updated = fetch_json(
            client,
            "PUT",
            "/api/settings",
            headers=headers,
            json={
                "enabled_models": temporary_enabled,
                "grok_monthly_cap_usd": temporary_cap,
                "model_monthly_caps_usd": temporary_model_caps,
            },
        )
        require(
            updated.get("enabled_models") == temporary_enabled,
            f"Settings did not persist enabled_models: {updated.get('enabled_models')}",
        )
        require(
            abs(float(updated.get("grok_monthly_cap_usd")) - temporary_cap) < 0.000001,
            f"Settings did not persist Grok cap: {updated.get('grok_monthly_cap_usd')}",
        )
        updated_model_caps = require_numeric_model_map(
            updated.get("model_monthly_caps_usd"),
            "updated model_monthly_caps_usd",
        )
        require(
            abs(updated_model_caps.get(cap_model, -1) - temporary_model_cap) < 0.000001,
            f"Settings did not persist cap for {cap_model}: {updated_model_caps.get(cap_model)}",
        )
    finally:
        fetch_json(
            client,
            "PUT",
            "/api/settings",
            headers=headers,
            json={
                "enabled_models": original_enabled,
                "grok_monthly_cap_usd": original_cap,
                "model_monthly_caps_usd": original_model_caps,
            },
        )

    restored = fetch_json(client, "GET", "/api/settings", headers=headers)
    require(restored.get("enabled_models") == original_enabled, "Settings enabled_models were not restored")
    require(
        abs(float(restored.get("grok_monthly_cap_usd")) - original_cap) < 0.000001,
        "Settings Grok monthly cap was not restored",
    )
    restored_model_caps = require_numeric_model_map(
        restored.get("model_monthly_caps_usd"),
        "restored model_monthly_caps_usd",
    )
    require(restored_model_caps == original_model_caps, "Settings model monthly caps were not restored")
    restored_grok_cap = float(restored.get("grok_monthly_cap_usd"))
    return {
        "configured_model_count": len(configured_model_set),
        "configured_models": ordered_configured_models,
        "cap_model": cap_model,
        "original_enabled_models": original_enabled,
        "temporary_enabled_models": temporary_enabled,
        "restored_enabled_models": restored.get("enabled_models"),
        "enabled_models_restored": restored.get("enabled_models") == original_enabled,
        "original_grok_cap_usd": original_cap,
        "temporary_grok_cap_usd": temporary_cap,
        "restored_grok_cap_usd": restored_grok_cap,
        "grok_cap_restored": abs(restored_grok_cap - original_cap) < 0.000001,
        "original_model_cap_usd": original_model_cap,
        "temporary_model_cap_usd": temporary_model_cap,
        "restored_model_cap_usd": restored_model_caps.get(cap_model, 0.0),
        "model_cap_restored": restored_model_caps == original_model_caps,
        "model_monthly_caps_models": sorted(original_model_caps),
        "model_monthly_spend_models": sorted(original_model_spend),
        "model_pricing_models": sorted(require_model_pricing_map(restored.get("model_pricing_usd_per_million_tokens"))),
        "grok_pricing_input": require_non_negative_number(grok_pricing["input"], "grok_pricing.input"),
        "grok_pricing_output": require_non_negative_number(grok_pricing["output"], "grok_pricing.output"),
    }


def require_settings_round_trip(client: httpx.Client, token: str) -> str:
    return settings_round_trip_detail(settings_round_trip_evidence(client, token))


def role_model_order(settings: dict[str, Any], role: str) -> list[str]:
    routing = settings.get("routing")
    if not isinstance(routing, dict):
        return []
    role_config = routing.get(role)
    if not isinstance(role_config, dict):
        return []
    if isinstance(role_config.get("pool"), list):
        return [str(model) for model in role_config["pool"] if str(model).strip()]
    ordered: list[str] = []
    primary = role_config.get("primary")
    if primary:
        ordered.append(str(primary))
    fallback = role_config.get("fallback")
    if isinstance(fallback, list):
        ordered.extend(str(model) for model in fallback if str(model).strip())
    return ordered


def choose_decomposer_override_model(settings: dict[str, Any], online_workers: list[dict[str, Any]]) -> str:
    capabilities = {
        str(capability).strip()
        for worker in online_workers
        for capability in (worker.get("capabilities") or [])
        if str(capability).strip()
    }
    require(capabilities, "Online workers did not advertise any capabilities for role override check")

    enabled_models = settings.get("enabled_models")
    enabled = {str(model).strip() for model in enabled_models if str(model).strip()} if isinstance(enabled_models, list) else set()
    allowed = capabilities & enabled if enabled else capabilities
    require(allowed, "No enabled online worker capability is available for role override check")

    for model in role_model_order(settings, "decomposer"):
        if model in allowed:
            return model
    return sorted(allowed)[0]


def create_debate_evidence(
    created: dict[str, Any],
    topic: str,
    depth: int,
    branching: int,
    decomposer_override_model: str,
) -> dict[str, Any]:
    debate_id = created.get("id")
    require(isinstance(debate_id, str) and debate_id.strip(), "Created debate response missing id")
    require(created.get("topic") == topic, "Created debate response topic mismatch")
    status = created.get("status")
    require(isinstance(status, str) and status.strip(), "Created debate response missing status")
    require(status not in {"failed", "archived"}, f"Created debate had invalid status for acceptance: {status!r}")
    config = created.get("config")
    require(isinstance(config, dict), "Created debate response missing config")
    require(config.get("max_depth") == depth, f"Created debate max_depth mismatch: {config.get('max_depth')!r}")
    require(config.get("branching") == branching, f"Created debate branching mismatch: {config.get('branching')!r}")
    role_overrides = config.get("role_overrides")
    require(isinstance(role_overrides, dict), "Created debate config missing role_overrides")
    decomposer = role_overrides.get("decomposer")
    require(isinstance(decomposer, dict), "Created debate config missing decomposer override")
    require(
        decomposer.get("primary") == decomposer_override_model,
        "Created debate decomposer override model mismatch",
    )
    created_at = require_timezone_aware_iso_timestamp(
        created.get("created_at"),
        "Created debate response created_at",
    )
    return {
        "debate_id": debate_id,
        "topic": created.get("topic"),
        "status": status,
        "requested_depth": depth,
        "requested_branching": branching,
        "config_max_depth": config.get("max_depth"),
        "config_branching": config.get("branching"),
        "decomposer_override_model": decomposer_override_model,
        "created_at": created_at,
        "root_node_id": created.get("root_node_id"),
    }


def tree_skeleton_detail(evidence: dict[str, Any]) -> str:
    return f"{evidence['node_count']} nodes"


def tree_skeleton_evidence(debate: dict[str, Any], debate_id: str, expected_branching: int) -> dict[str, Any]:
    require(debate.get("id") == debate_id, "Tree skeleton debate id mismatch")
    node_count = debate.get("node_count")
    require(isinstance(node_count, int) and not isinstance(node_count, bool) and node_count > 0, "Tree skeleton node_count missing")
    root = debate.get("tree")
    require(isinstance(root, dict), "Tree skeleton missing root node")
    root_id = root.get("id")
    require(isinstance(root_id, str) and root_id, "Tree skeleton root node missing id")
    children = root.get("children")
    require(isinstance(children, list) and children, "Tree skeleton root has no children")
    require(len(children) >= expected_branching, f"Tree skeleton has {len(children)} children, expected at least {expected_branching}")
    child_rows = []
    for child in children:
        require(isinstance(child, dict), "Tree skeleton child row is not an object")
        child_id = child.get("id")
        node_type = child.get("node_type")
        depth = child.get("depth")
        position = child.get("position")
        status = child.get("status")
        require(isinstance(child_id, str) and child_id, "Tree skeleton child missing id")
        require(node_type in {"PRO", "CON"}, f"Tree skeleton child {child_id} has invalid node_type {node_type!r}")
        require(isinstance(depth, int) and depth >= 1, f"Tree skeleton child {child_id} missing depth")
        require(isinstance(position, int) and position >= 0, f"Tree skeleton child {child_id} missing position")
        require(isinstance(status, str) and status, f"Tree skeleton child {child_id} missing status")
        child_rows.append(
            {
                "id": child_id,
                "node_type": node_type,
                "depth": depth,
                "position": position,
                "status": status,
                "claim_present": bool(str(child.get("claim") or "").strip()),
            }
        )
    return {
        "debate_id": debate_id,
        "node_count": node_count,
        "root_node_id": root_id,
        "root_status": root.get("status"),
        "child_count": len(child_rows),
        "expected_branching": expected_branching,
        "child_node_types": sorted({str(row["node_type"]) for row in child_rows}),
        "children": sorted(child_rows, key=lambda row: (int(row["position"]), str(row["id"]))),
    }


def role_override_detail(evidence: dict[str, Any]) -> str:
    return f"decomposer primary {evidence['expected_model']}; persisted and used by root job"


def role_override_evidence(debate: dict[str, Any], expected_model: str) -> dict[str, Any]:
    config = debate.get("config")
    require(isinstance(config, dict), "Debate detail missing config")
    role_overrides = config.get("role_overrides")
    require(isinstance(role_overrides, dict), "Debate config missing role_overrides")
    decomposer = role_overrides.get("decomposer")
    require(isinstance(decomposer, dict), "Debate config missing decomposer role override")
    persisted_primary = decomposer.get("primary")
    require(
        persisted_primary == expected_model,
        f"Debate decomposer override was not persisted: {persisted_primary!r}",
    )
    root = debate.get("tree")
    require(isinstance(root, dict), "Debate detail missing root node")
    generation = root.get("active_generation")
    require(isinstance(generation, dict), "Root node missing active generation")
    root_model = generation.get("model_id")
    require(
        root_model == expected_model,
        f"Root decomposition did not use override model: {root_model!r}",
    )
    return {
        "expected_model": expected_model,
        "persisted_primary": persisted_primary,
        "persisted_fallback": decomposer.get("fallback") if isinstance(decomposer.get("fallback"), list) else [],
        "root_node_id": root.get("id"),
        "root_generation_id": generation.get("id"),
        "root_generation_model_id": root_model,
        "persisted": True,
        "root_job_used_override": True,
    }


def require_decomposer_role_override(debate: dict[str, Any], expected_model: str) -> str:
    return role_override_detail(role_override_evidence(debate, expected_model))


def tree_skeleton_timing_detail(evidence: dict[str, Any]) -> str:
    return f"{evidence['elapsed_seconds']:.2f}s <= {evidence['timeout_seconds']}s"


def tree_skeleton_timing_evidence(elapsed_seconds: float, timeout_seconds: float) -> dict[str, Any]:
    require(elapsed_seconds >= 0, "Tree skeleton timing elapsed seconds was negative")
    require(elapsed_seconds <= timeout_seconds, f"Tree skeleton took {elapsed_seconds:.2f}s, timeout was {timeout_seconds}s")
    return {
        "elapsed_seconds": elapsed_seconds,
        "timeout_seconds": timeout_seconds,
        "within_timeout": True,
    }


def persistence_detail(evidence: dict[str, Any]) -> str:
    return f"revisited {evidence['debate_id']}; exact detail match"


def persistence_evidence(revisited: dict[str, Any], expected: dict[str, Any], debate_id: str) -> dict[str, Any]:
    require(revisited.get("id") == debate_id, "Revisited debate id mismatch")
    require(
        stable_json(revisited) == stable_json(expected),
        "Revisited debate detail payload changed unexpectedly",
    )
    active_generation_ids = active_generation_ids_from_tree(revisited)
    return {
        "debate_id": debate_id,
        "topic": revisited.get("topic"),
        "status": revisited.get("status"),
        "node_count": revisited.get("node_count"),
        "synthesis_id": revisited.get("synthesis_id"),
        "root_node_id": revisited.get("root_node_id"),
        "model_ids": sorted(model_ids_from_tree(revisited)),
        "worker_names": sorted(worker_names_from_tree(revisited)),
        "active_generation_ids": sorted(active_generation_ids),
        "active_generation_count": len(active_generation_ids),
        "exact_payload_match": True,
        "stable_json_length": len(stable_json(revisited)),
    }


def result_dicts(results: list[CheckResult]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for result in results:
        row: dict[str, Any] = {"name": result.name, "detail": result.detail}
        if result.evidence is not None:
            row["evidence"] = result.evidence
        rows.append(row)
    return rows


def result_evidence(results: list[CheckResult], name: str) -> Any | None:
    for result in results:
        if result.name == name:
            return result.evidence
    return None


def evidence_names(results: list[CheckResult], name: str) -> list[str]:
    evidence = result_evidence(results, name)
    if not isinstance(evidence, list):
        return []
    names: set[str] = set()
    for item in evidence:
        if isinstance(item, str) and item.strip():
            names.add(item.strip())
        elif isinstance(item, dict) and isinstance(item.get("name"), str) and item["name"].strip():
            names.add(item["name"].strip())
    return sorted(names)


def evidence_model_ids(results: list[CheckResult], name: str) -> list[str]:
    evidence = result_evidence(results, name)
    if not isinstance(evidence, list):
        return []
    return sorted({str(item).strip() for item in evidence if str(item).strip()})


def evidence_worker_rows(results: list[CheckResult], name: str) -> list[dict[str, Any]]:
    evidence = result_evidence(results, name)
    if not isinstance(evidence, list):
        return []
    rows = [item for item in evidence if isinstance(item, dict)]
    return sorted(rows, key=lambda item: str(item.get("name") or ""))


def worker_status_evidence(workers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for worker in workers:
        rows.append(worker_status_row_evidence(worker))
    return sorted(rows, key=lambda item: item["name"])


def comma_detail_values(results: list[CheckResult], names: set[str]) -> list[str]:
    values: set[str] = set()
    for result in results:
        if result.name not in names:
            continue
        for raw_value in result.detail.split(","):
            value = raw_value.strip()
            if value and value != "none":
                values.add(value)
    return sorted(values)


def stable_json(payload: object) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def write_report(
    path: str | None,
    args: argparse.Namespace,
    status: str,
    results: list[CheckResult],
    started_at: str,
    error: str | None = None,
) -> None:
    if not path:
        return
    report_path = Path(path).expanduser()
    report_path.parent.mkdir(parents=True, exist_ok=True)
    online_worker_rows = evidence_worker_rows(results, "workers-online")
    offline_worker_rows = evidence_worker_rows(results, "workers-offline")
    generated_worker_names = evidence_names(results, "generated-workers")
    regenerated_worker_names = evidence_names(results, "regenerated-workers")
    generated_model_ids = evidence_model_ids(results, "generated-models")
    regenerated_model_ids = evidence_model_ids(results, "regenerated-models")
    regeneration_model_switch = result_evidence(results, "regeneration-model-switch")
    observed_worker_names = sorted(
        set(evidence_names(results, "workers-online"))
        | set(evidence_names(results, "workers-offline"))
        | set(generated_worker_names)
        | set(regenerated_worker_names)
    )
    if not observed_worker_names:
        observed_worker_names = comma_detail_values(
            results,
            {"workers-online", "workers-offline", "generated-workers", "regenerated-workers"},
        )
    observed_model_ids = sorted(set(generated_model_ids) | set(regenerated_model_ids))
    if not observed_model_ids:
        observed_model_ids = comma_detail_values(results, {"generated-models", "regenerated-models"})
    payload = {
        "status": status,
        "started_at": started_at,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "phase": str(getattr(args, "phase", "") or "").strip() or None,
        "base_url": args.base_url.rstrip("/"),
        "web_base_url": (args.web_base_url or args.base_url).rstrip("/"),
        "expected_workers": args.expected_workers,
        "expected_worker_names": [name.strip() for name in args.expected_worker_names.split(",") if name.strip()],
        "expected_offline_worker_names": [
            name.strip() for name in args.expected_offline_worker_names.split(",") if name.strip()
        ],
        "require_expected_workers_in_tree": bool(args.require_expected_workers_in_tree),
        "require_different_regen_model": bool(args.require_different_regen_model),
        "require_named_https": bool(getattr(args, "require_named_https", False)),
        "skip_web_checks": bool(args.skip_web_checks),
        "skip_sse_check": bool(args.skip_sse_check),
        "topic": args.topic,
        "depth": args.depth,
        "branching": args.branching,
        "debate_id": next((result.detail for result in results if result.name == "create-debate"), None),
        "online_workers": online_worker_rows,
        "offline_workers": offline_worker_rows,
        "generated_worker_names": generated_worker_names,
        "regenerated_worker_names": regenerated_worker_names,
        "generated_model_ids": generated_model_ids,
        "regenerated_model_ids": regenerated_model_ids,
        "regeneration_model_switch": regeneration_model_switch if isinstance(regeneration_model_switch, dict) else None,
        "observed_worker_names": observed_worker_names,
        "observed_model_ids": observed_model_ids,
        "results": result_dicts(results),
        "error": error,
    }
    report_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def run(args: argparse.Namespace) -> list[CheckResult]:
    if not args.user_token:
        raise AcceptanceError("USER_TOKEN is required for acceptance checks that create and regenerate debates")

    base_url = args.base_url.rstrip("/")
    web_base_url = (args.web_base_url or args.base_url).rstrip("/")
    if args.require_named_https:
        require_named_https_url(base_url, "base URL")
        require_named_https_url(web_base_url, "web base URL")
    expected_names = {name.strip() for name in args.expected_worker_names.split(",") if name.strip()}
    expected_offline_names = {name.strip() for name in args.expected_offline_worker_names.split(",") if name.strip()}
    results: list[CheckResult] = []

    with httpx.Client(base_url=base_url, timeout=httpx.Timeout(20, connect=10), follow_redirects=True) as client:
        debates = fetch_json(client, "GET", "/api/debates")
        initial_public_evidence = public_list_evidence(debates)

        if not args.skip_web_checks:
            with httpx.Client(
                base_url=web_base_url,
                timeout=httpx.Timeout(20, connect=10),
                follow_redirects=True,
            ) as web_client:
                results.append(
                    CheckResult(
                        "web-auth-gates",
                        "/new, /settings, and /admin/workers prompt for token",
                        web_auth_gates_evidence(web_client),
                    )
                )
                token_flow_detail = require_web_auth_token_flow()
                results.append(
                    CheckResult(
                        "web-auth-token-flow",
                        token_flow_detail,
                        source_marker_evidence(WEB_AUTH_TOKEN_FLOW, "auth token-flow"),
                    )
                )
                auth_surfaces_detail = require_web_auth_surfaces()
                results.append(
                    CheckResult(
                        "web-auth-surfaces",
                        auth_surfaces_detail,
                        source_marker_evidence(WEB_AUTH_SURFACES, "post-unlock"),
                    )
                )
                debate_actions_detail = require_web_debate_actions()
                results.append(
                    CheckResult(
                        "web-debate-actions",
                        debate_actions_detail,
                        source_marker_evidence(WEB_DEBATE_ACTION_SURFACES, "debate-action"),
                    )
                )
                streaming_client_detail = require_web_streaming_client()
                results.append(
                    CheckResult(
                        "web-streaming-client",
                        streaming_client_detail,
                        source_marker_evidence(WEB_STREAMING_CLIENT_SURFACES, "streaming-client"),
                    )
                )

        unauth_create = client.post("/api/debates", json={"topic": args.topic})
        require(
            unauth_create.status_code in {401, 403},
            f"Unauthenticated create was not rejected: {unauth_create.status_code}",
        )
        unauth_settings = client.get("/api/settings")
        require(
            unauth_settings.status_code in {401, 403},
            f"Unauthenticated settings read was not rejected: {unauth_settings.status_code}",
        )
        wrong_token_settings = client.get("/api/settings", headers=auth_headers("invalid-token"))
        require(
            wrong_token_settings.status_code == 403,
            f"Invalid settings token was not rejected with 403: {wrong_token_settings.status_code}",
        )
        auth_evidence = auth_boundaries_evidence(
            initial_public_evidence["debate_count"],
            unauth_create,
            unauth_settings,
            wrong_token_settings,
        )
        results.append(CheckResult("auth-boundaries", auth_boundaries_detail(auth_evidence), auth_evidence))
        settings_evidence = settings_round_trip_evidence(client, args.user_token)
        results.append(CheckResult("settings-roundtrip", settings_round_trip_detail(settings_evidence), settings_evidence))
        settings = fetch_json(client, "GET", "/api/settings", headers=auth_headers(args.user_token))

        status = fetch_json(client, "GET", "/api/backends/status")
        workers = status.get("workers", [])
        online = [worker for worker in workers if worker.get("status") == "online"]
        worker_status_payload = worker_status_payload_evidence(workers, online)
        results.append(
            CheckResult(
                "worker-status-payload",
                worker_status_payload_detail(worker_status_payload),
                worker_status_payload,
            )
        )
        require(
            len(online) == args.expected_workers,
            f"Expected exactly {args.expected_workers} online workers, saw {len(online)}",
        )
        if expected_names:
            online_names = {worker.get("name") for worker in online}
            missing = expected_names - online_names
            require(not missing, f"Expected worker names missing from /api/backends/status: {sorted(missing)}")
        results.append(
            CheckResult(
                "workers-online",
                ", ".join(worker["name"] for worker in online),
                worker_status_evidence(online),
            )
        )
        if expected_offline_names:
            offline_detail = require_offline_worker_names(workers, expected_offline_names)
            workers_by_name = {
                str(worker.get("name")): worker
                for worker in workers
                if isinstance(worker, dict) and isinstance(worker.get("name"), str)
            }
            offline_rows = [workers_by_name[name] for name in sorted(expected_offline_names)]
            results.append(CheckResult("workers-offline", offline_detail, worker_status_evidence(offline_rows)))

        decomposer_override_model = choose_decomposer_override_model(settings, online)
        created = fetch_json(
            client,
            "POST",
            "/api/debates",
            headers=auth_headers(args.user_token),
            json={
                "topic": args.topic,
                "config": {
                    "max_depth": args.depth,
                    "branching": args.branching,
                    "role_overrides": {
                        "decomposer": {
                            "primary": decomposer_override_model,
                            "fallback": [],
                        }
                    },
                },
            },
        )
        created_at = time.monotonic()
        debate_id = created["id"]
        results.append(
            CheckResult(
                "create-debate",
                debate_id,
                create_debate_evidence(
                    created,
                    args.topic,
                    args.depth,
                    args.branching,
                    decomposer_override_model,
                ),
            )
        )
        sse_recorder = None
        if not args.skip_sse_check:
            sse_recorder = SseRecorder(base_url, debate_id)
            sse_recorder.start()

        skeleton = wait_for_debate(
            client,
            debate_id,
            lambda debate: bool((debate.get("tree") or {}).get("children")),
            args.skeleton_timeout,
            "tree skeleton",
        )
        skeleton_elapsed = time.monotonic() - created_at
        skeleton_evidence = tree_skeleton_evidence(skeleton, debate_id, args.branching)
        results.append(CheckResult("tree-skeleton", tree_skeleton_detail(skeleton_evidence), skeleton_evidence))
        role_evidence = role_override_evidence(skeleton, decomposer_override_model)
        results.append(CheckResult("role-overrides", role_override_detail(role_evidence), role_evidence))
        timing_evidence = tree_skeleton_timing_evidence(skeleton_elapsed, args.skeleton_timeout)
        results.append(
            CheckResult(
                "tree-skeleton-timing",
                tree_skeleton_timing_detail(timing_evidence),
                timing_evidence,
            )
        )

        complete = wait_for_debate(
            client,
            debate_id,
            lambda debate: debate.get("status") == "complete" and bool(debate.get("synthesis")),
            args.completion_timeout,
            "debate completion",
        )
        synthesis_evidence = require_synthesis_evidence(complete.get("synthesis"), "Initial")
        results.append(CheckResult("synthesis", synthesis_evidence["verdict"][:120], synthesis_evidence))
        if sse_recorder:
            sse_evidence = sse_stream_evidence(sse_recorder, require_tree_ready=True)
            sse_recorder.stop()
            results.append(CheckResult("sse-stream", sse_stream_detail(sse_evidence), sse_evidence))

        generated_worker_names = worker_names_from_tree(complete)
        generated_model_ids = model_ids_from_tree(complete)
        generated_node_evidence = generated_node_metadata_evidence(complete)
        results.append(
            CheckResult(
                "generated-node-metadata",
                generated_node_metadata_detail(generated_node_evidence),
                generated_node_evidence,
            )
        )
        results.append(
            CheckResult(
                "generated-models",
                ", ".join(sorted(generated_model_ids)) or "none",
                sorted(generated_model_ids),
            )
        )
        if expected_names and args.require_expected_workers_in_tree:
            missing = expected_names - generated_worker_names
            require(not missing, f"Expected workers did not all generate nodes: {sorted(missing)}")
        results.append(
            CheckResult(
                "generated-workers",
                ", ".join(sorted(generated_worker_names)) or "none",
                sorted(generated_worker_names),
            )
        )

        target_node = first_argument_node(complete)
        write_auth_evidence = write_auth_boundaries_evidence(client, debate_id, target_node["id"])
        results.append(
            CheckResult(
                "write-auth-boundaries",
                write_auth_boundaries_detail(write_auth_evidence),
                write_auth_evidence,
            )
        )
        before_generation = target_node.get("active_generation_id")
        before_synthesis = complete.get("synthesis_id")
        regeneration_sse_recorder = None
        if not args.skip_sse_check:
            regeneration_sse_recorder = SseRecorder(base_url, debate_id, replay_history=False)
            regeneration_sse_recorder.start()
        regen = fetch_json(
            client,
            "POST",
            f"/api/nodes/{target_node['id']}/regenerate",
            headers=auth_headers(args.user_token),
            json={},
        )
        request_evidence = regenerate_request_evidence(
            regen,
            debate_id,
            target_node["id"],
            before_generation,
            before_synthesis,
        )
        results.append(
            CheckResult(
                "regenerate-request",
                regenerate_request_detail(request_evidence),
                request_evidence,
            )
        )
        regenerated = wait_for_debate(
            client,
            debate_id,
            lambda debate: next(
                (
                    node
                    for node in flatten_nodes(debate.get("tree"))
                    if node.get("id") == target_node["id"] and node.get("active_generation_id") != before_generation
                ),
                None,
            ),
            args.regeneration_timeout,
            "node regeneration",
        )
        regenerated_node = next(node for node in flatten_nodes(regenerated.get("tree")) if node.get("id") == target_node["id"])
        history = fetch_json(
            client,
            "GET",
            f"/api/nodes/{target_node['id']}/generations",
            headers=auth_headers(args.user_token),
        )
        history_items = history.get("items", [])
        require(len(history_items) >= 2, "Generation history did not preserve the previous generation")
        require(history.get("node_id") == target_node["id"], "Generation history returned the wrong node id")
        before_history = next((item for item in history_items if item.get("id") == before_generation), None)
        after_generation = regenerated_node.get("active_generation_id")
        after_history = next((item for item in history_items if item.get("id") == after_generation), None)
        require(before_history is not None, "Generation history is missing the previous active generation")
        require(after_history is not None, "Generation history is missing the regenerated active generation")
        require(before_history.get("is_active") is False, "Previous generation was not archived in history")
        require(after_history.get("is_active") is True, "Regenerated generation is not active in history")
        active_count = sum(1 for item in history_items if item.get("is_active") is True)
        require(active_count == 1, f"Expected exactly one active generation, saw {active_count}")
        for item in history_items:
            generation_id = item.get("id", "unknown")
            require(isinstance(item.get("model_id"), str) and item["model_id"], f"History {generation_id} missing model_id")
            require(isinstance(item.get("role"), str) and item["role"], f"History {generation_id} missing role")
            require(isinstance(item.get("argument"), str) and item["argument"], f"History {generation_id} missing argument")
            require(isinstance(item.get("worker_id"), str) and item["worker_id"], f"History {generation_id} missing worker_id")
            require(isinstance(item.get("worker_name"), str) and item["worker_name"], f"History {generation_id} missing worker_name")
            require_timezone_aware_iso_timestamp(item.get("created_at"), f"History {generation_id} created_at")
            require(isinstance(item.get("latency_ms"), int), f"History {generation_id} missing latency_ms")
            require(item.get("tokens_in") is None or isinstance(item.get("tokens_in"), int), f"History {generation_id} has invalid tokens_in")
            require(item.get("tokens_out") is None or isinstance(item.get("tokens_out"), int), f"History {generation_id} has invalid tokens_out")
        old_model = (target_node.get("active_generation") or {}).get("model_id")
        new_model = (regenerated_node.get("active_generation") or {}).get("model_id")
        require(isinstance(old_model, str) and old_model, "Previous active generation missing model_id")
        require(isinstance(new_model, str) and new_model, "Regenerated active generation missing model_id")
        if args.require_different_regen_model:
            require(old_model != new_model, f"Regenerated node used the same model: {old_model}")
        results.append(
            CheckResult(
                "regenerate-history",
                f"{len(history_items)} generations; archived previous; active current",
                generation_history_evidence(target_node["id"], history_items, before_history, after_history),
            )
        )
        results.append(
            CheckResult(
                "regeneration-model-switch",
                f"{old_model} -> {new_model}",
                {"old_model": old_model, "new_model": new_model},
            )
        )

        regenerated = wait_for_debate(
            client,
            debate_id,
            lambda debate: debate.get("status") == "complete"
            and bool(debate.get("synthesis"))
            and debate.get("synthesis_id") != before_synthesis,
            args.regeneration_timeout,
            "post-regeneration synthesis",
        )
        regenerated_synthesis_evidence = require_synthesis_evidence(regenerated.get("synthesis"), "Regenerated")
        results.append(
            CheckResult(
                "regenerate-synthesis",
                str(regenerated.get("synthesis_id")),
                regenerated_synthesis_evidence,
            )
        )
        if regeneration_sse_recorder:
            regenerate_sse_evidence = sse_stream_evidence(regeneration_sse_recorder)
            regeneration_sse_recorder.stop()
            results.append(
                CheckResult(
                    "regenerate-sse-stream",
                    sse_stream_detail(regenerate_sse_evidence),
                    regenerate_sse_evidence,
                )
            )
        generated_worker_names = worker_names_from_tree(regenerated)
        generated_model_ids = model_ids_from_tree(regenerated)
        regenerated_node_evidence = generated_node_metadata_evidence(regenerated)
        results.append(
            CheckResult(
                "regenerated-node-metadata",
                generated_node_metadata_detail(regenerated_node_evidence),
                regenerated_node_evidence,
            )
        )
        results.append(
            CheckResult(
                "regenerated-workers",
                ", ".join(sorted(generated_worker_names)) or "none",
                sorted(generated_worker_names),
            )
        )
        results.append(
            CheckResult(
                "regenerated-models",
                ", ".join(sorted(generated_model_ids)) or "none",
                sorted(generated_model_ids),
            )
        )

        public_debates = fetch_json(client, "GET", "/api/debates")
        public_evidence = public_list_evidence(public_debates)
        require_public_list_current_debate(public_evidence, debate_id, args.topic, generated_model_ids)
        results.append(CheckResult("public-list", public_list_detail(public_evidence), public_evidence))

        if not args.skip_web_checks:
            with httpx.Client(
                base_url=web_base_url,
                timeout=httpx.Timeout(20, connect=10),
                follow_redirects=True,
            ) as web_client:
                home_evidence = web_home_evidence(
                    web_client,
                    web_base_url,
                    debate_id,
                    args.topic,
                    "complete",
                    generated_model_ids,
                )
                results.append(CheckResult("web-home", web_home_detail(home_evidence), home_evidence))
                detail_summary, detail_evidence = web_debate_detail_result(
                    web_client,
                    f"/debate/{debate_id}",
                    args.topic,
                    generated_worker_names,
                    generated_model_ids,
                )
            results.append(
                CheckResult(
                    "web-debate-detail",
                    f"{web_base_url}/debate/{debate_id} returned server-rendered detail with {detail_summary}",
                    detail_evidence,
                )
            )

        export_response = client.get(f"/api/debates/{debate_id}/export.md")
        require(export_response.status_code == 200, f"Export failed with {export_response.status_code}")
        content_disposition = export_response.headers.get("content-disposition", "")
        content_type = export_response.headers.get("content-type", "")
        require("attachment" in content_disposition.lower(), "Markdown export is not served as an attachment")
        require(f"debate-{debate_id}.md" in content_disposition, "Markdown export filename is missing debate id")
        require("text/plain" in content_type or "text/markdown" in content_type, f"Unexpected export content type: {content_type}")
        require(args.topic in export_response.text, "Markdown export missing debate topic")
        require("## Synthesis" in export_response.text, "Markdown export missing synthesis section")
        require("## Tree" in export_response.text, "Markdown export missing tree section")
        require("**Workers:**" in export_response.text, "Markdown export missing worker metadata")
        require("**Models:**" in export_response.text, "Markdown export missing model metadata")
        for worker_name in generated_worker_names:
            require(worker_name in export_response.text, f"Markdown export missing generated worker {worker_name}")
        for model_id in generated_model_ids:
            require(model_id in export_response.text, f"Markdown export missing generated model {model_id}")
        history_summary = require_markdown_generation_history(export_response.text, history_items)
        results.append(
            CheckResult(
                "markdown-export",
                f"{len(export_response.text)} bytes; attachment; {history_summary}",
                markdown_export_evidence(
                    export_response,
                    args.topic,
                    debate_id,
                    generated_worker_names,
                    generated_model_ids,
                    history_items,
                ),
            )
        )

        revisited = fetch_json(client, "GET", f"/api/debates/{debate_id}")
        persistence = persistence_evidence(revisited, regenerated, debate_id)
        results.append(CheckResult("persistence", persistence_detail(persistence), persistence))

    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Dialectical Engine deployment acceptance checks")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--web-base-url")
    parser.add_argument("--user-token", default=os.getenv("DIALECTICAL_USER_TOKEN") or os.getenv("USER_TOKEN"))
    parser.add_argument("--phase", default=os.getenv("ACCEPTANCE_PHASE", ""))
    parser.add_argument("--expected-workers", type=int, default=1)
    parser.add_argument("--expected-worker-names", default="")
    parser.add_argument("--expected-offline-worker-names", default="")
    parser.add_argument("--require-expected-workers-in-tree", action="store_true")
    parser.add_argument("--require-different-regen-model", action="store_true")
    parser.add_argument("--require-named-https", action="store_true")
    parser.add_argument("--topic", default="Should the EU ban gas cars by 2035?")
    parser.add_argument("--depth", type=int, default=1)
    parser.add_argument("--branching", type=int, default=2)
    parser.add_argument("--skeleton-timeout", type=int, default=30)
    parser.add_argument("--completion-timeout", type=int, default=180)
    parser.add_argument("--regeneration-timeout", type=int, default=120)
    parser.add_argument("--skip-web-checks", action="store_true")
    parser.add_argument("--skip-sse-check", action="store_true")
    parser.add_argument("--report-path")
    args = parser.parse_args()

    started_at = datetime.now(timezone.utc).isoformat()
    results: list[CheckResult] = []
    try:
        results = run(args)
    except Exception as exc:
        write_report(args.report_path, args, "failed", results, started_at, str(exc))
        print(f"ACCEPTANCE FAILED: {exc}", file=sys.stderr)
        return 1

    write_report(args.report_path, args, "passed", results, started_at)
    for result in results:
        print(f"PASS {result.name}: {result.detail}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
