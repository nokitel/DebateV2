from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]


def worker_row(
    name: str,
    *,
    status: str = "online",
    capabilities: list[object] | None = None,
    worker_id: str = "11111111-1111-4111-8111-111111111111",
    current_job_id: object | None = None,
    last_seen: object = "2026-05-24T08:00:00+00:00",
) -> dict[str, object]:
    return {
        "id": worker_id,
        "name": name,
        "status": status,
        "capabilities": capabilities if capabilities is not None else ["codex-gpt-5.5"],
        "current_job_id": current_job_id,
        "last_seen": last_seen,
    }


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_worker_visibility_detail_requires_named_online_worker_with_capabilities() -> None:
    module = load_module(ROOT / "scripts" / "verify_worker_visible.py", "dialectical_verify_worker_visible")

    detail = module.worker_visibility_detail(
        {
            "workers": [
                worker_row("mac-mini", worker_id="11111111-1111-4111-8111-111111111111"),
                worker_row(
                    "adesso-mbp",
                    worker_id="22222222-2222-4222-8222-222222222222",
                    capabilities=["codex-gpt-5.5", "mock-local"],
                ),
            ]
        },
        "adesso-mbp",
    )

    assert detail == "adesso-mbp:online (2 capabilities)"


def test_fetch_status_sends_browser_like_user_agent(monkeypatch: pytest.MonkeyPatch) -> None:
    module = load_module(ROOT / "scripts" / "verify_worker_visible.py", "dialectical_verify_worker_fetch")
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self) -> bytes:
            return json.dumps({"workers": []}).encode("utf-8")

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["headers"] = dict(request.header_items())
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(module.urllib.request, "urlopen", fake_urlopen)

    assert module.fetch_status("https://dezbatere.ro/", 7) == {"workers": []}
    assert captured["url"] == "https://dezbatere.ro/api/backends/status"
    assert captured["headers"]["Accept"] == "application/json"
    assert captured["headers"]["User-agent"] == module.STATUS_USER_AGENT
    assert captured["timeout"] == 7


def test_worker_status_detail_accepts_offline_worker_without_capabilities() -> None:
    module = load_module(ROOT / "scripts" / "verify_worker_visible.py", "dialectical_verify_worker_status")

    detail = module.worker_status_detail(
        {
            "workers": [
                worker_row(
                    "adesso-mbp",
                    status="offline",
                    capabilities=[],
                    worker_id="22222222-2222-4222-8222-222222222222",
                )
            ]
        },
        "adesso-mbp",
        "offline",
    )

    assert detail == "adesso-mbp:offline (0 capabilities)"


def test_worker_status_detail_requires_specific_capabilities() -> None:
    module = load_module(ROOT / "scripts" / "verify_worker_visible.py", "dialectical_verify_worker_required_caps")

    detail = module.worker_status_detail(
        {
            "workers": [
                worker_row(
                    "adesso-mbp",
                    worker_id="22222222-2222-4222-8222-222222222222",
                    capabilities=["codex-gpt-5.5", "grok-4"],
                )
            ]
        },
        "adesso-mbp",
        "online",
        require_capabilities=True,
        required_capabilities=["codex-gpt-5.5"],
    )

    assert detail == "adesso-mbp:online (2 capabilities; required codex-gpt-5.5)"

    with pytest.raises(module.VisibilityError, match="missing required capabilities: gemini-2.5-flash"):
        module.worker_status_detail(
            {
                "workers": [
                    worker_row(
                        "adesso-mbp",
                        worker_id="22222222-2222-4222-8222-222222222222",
                        capabilities=["codex-gpt-5.5"],
                    )
                ]
            },
            "adesso-mbp",
            "online",
            require_capabilities=True,
            required_capabilities=["gemini-2.5-flash"],
        )


def test_worker_status_detail_rejects_non_production_capabilities_when_requested() -> None:
    module = load_module(
        ROOT / "scripts" / "verify_worker_visible.py",
        "dialectical_verify_worker_reject_non_production_caps",
    )

    with pytest.raises(module.VisibilityError, match="has mock capability: mock-local"):
        module.worker_status_detail(
            {
                "workers": [
                    worker_row(
                        "adesso-mbp",
                        worker_id="22222222-2222-4222-8222-222222222222",
                        capabilities=["codex-gpt-5.5", "mock-local"],
                    )
                ]
            },
            "adesso-mbp",
            "online",
            require_capabilities=True,
            required_capabilities=["codex-gpt-5.5"],
            reject_non_production_capabilities=True,
        )

    with pytest.raises(module.VisibilityError, match="has placeholder capability: <model-id>"):
        module.worker_status_detail(
            {
                "workers": [
                    worker_row(
                        "adesso-mbp",
                        worker_id="22222222-2222-4222-8222-222222222222",
                        capabilities=["codex-gpt-5.5", "<model-id>"],
                    )
                ]
            },
            "adesso-mbp",
            "online",
            reject_non_production_capabilities=True,
        )


def test_parse_required_capabilities_accepts_csv_and_repeated_flags() -> None:
    module = load_module(ROOT / "scripts" / "verify_worker_visible.py", "dialectical_verify_worker_parse_caps")

    assert module.parse_required_capabilities(["codex-gpt-5.5, grok-4", "codex-gpt-5.5", ""]) == [
        "codex-gpt-5.5",
        "grok-4",
    ]


def test_main_reports_worker_status_success(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    module = load_module(ROOT / "scripts" / "verify_worker_visible.py", "dialectical_verify_worker_main_success")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "verify_worker_visible.py",
            "--base-url",
            "https://debate.example.com",
            "--worker-name",
            "adesso-mbp",
        ],
    )
    monkeypatch.setattr(module, "wait_for_worker_status", lambda *args: "adesso-mbp:online (1 capabilities)")

    assert module.main() == 0
    captured = capsys.readouterr()
    assert captured.out == "Worker status verified: adesso-mbp:online (1 capabilities)\n"
    assert captured.err == ""


def test_main_reports_visibility_error_without_traceback(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = load_module(ROOT / "scripts" / "verify_worker_visible.py", "dialectical_verify_worker_main_failure")

    def raise_visibility_error(*args: object) -> str:
        raise module.VisibilityError("adesso-mbp missing from /api/backends/status")

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "verify_worker_visible.py",
            "--base-url",
            "https://debate.example.com",
            "--worker-name",
            "adesso-mbp",
        ],
    )
    monkeypatch.setattr(module, "wait_for_worker_status", raise_visibility_error)

    assert module.main() == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "worker visibility check failed: adesso-mbp missing from /api/backends/status" in captured.err
    assert "Traceback" not in captured.err


@pytest.mark.parametrize(
    ("payload", "match"),
    [
        ({"workers": [{"name": "mac-mini", "status": "online", "capabilities": ["codex-gpt-5.5"]}]}, "missing"),
        (
            {
                "workers": [
                    worker_row(
                        "adesso-mbp",
                        status="offline",
                        worker_id="22222222-2222-4222-8222-222222222222",
                    )
                ]
            },
            "not online",
        ),
        (
            {
                "workers": [
                    worker_row(
                        "adesso-mbp",
                        capabilities=[],
                        worker_id="22222222-2222-4222-8222-222222222222",
                    )
                ]
            },
            "no advertised capabilities",
        ),
        ({}, "workers list"),
    ],
)
def test_worker_visibility_detail_rejects_non_visible_worker(payload: dict[str, object], match: str) -> None:
    module = load_module(ROOT / "scripts" / "verify_worker_visible.py", "dialectical_verify_worker_visible_reject")

    with pytest.raises(module.VisibilityError, match=match):
        module.worker_visibility_detail(payload, "adesso-mbp")


@pytest.mark.parametrize(
    ("row_update", "match"),
    [
        ({"id": "not-a-uuid"}, "id is not a UUID"),
        ({"current_job_id": "not-a-uuid"}, "current_job_id is not a UUID"),
        ({"last_seen": "2026-05-24T08:00:00"}, "last_seen missing timezone"),
        ({"capabilities": ["codex-gpt-5.5", "codex-gpt-5.5"]}, "duplicate capability"),
        ({"capabilities": ["codex-gpt-5.5", ""]}, "capability 2 is blank"),
    ],
)
def test_worker_status_detail_rejects_malformed_target_row(
    row_update: dict[str, object],
    match: str,
) -> None:
    module = load_module(ROOT / "scripts" / "verify_worker_visible.py", "dialectical_verify_worker_shape")
    row = worker_row("adesso-mbp", worker_id="22222222-2222-4222-8222-222222222222")
    row.update(row_update)

    with pytest.raises(module.VisibilityError, match=match):
        module.worker_visibility_detail({"workers": [row]}, "adesso-mbp")


def test_worker_status_detail_rejects_duplicate_worker_names() -> None:
    module = load_module(ROOT / "scripts" / "verify_worker_visible.py", "dialectical_verify_worker_duplicate")

    with pytest.raises(module.VisibilityError, match="duplicate worker names: adesso-mbp"):
        module.worker_visibility_detail(
            {
                "workers": [
                    worker_row("adesso-mbp", worker_id="22222222-2222-4222-8222-222222222222"),
                    worker_row("adesso-mbp", worker_id="33333333-3333-4333-8333-333333333333"),
                ]
            },
            "adesso-mbp",
        )


def test_worker_b_handoff_scripts_verify_public_worker_visibility() -> None:
    module = load_module(ROOT / "scripts" / "build_handoff_bundles.py", "dialectical_build_handoff_bundles")

    register_script = module.worker_register_script("https://current.example.com", "adesso-mbp")
    real_models_script = module.worker_real_models_script("https://current.example.com", "adesso-mbp")
    switch_script = module.worker_switch_url_script()
    production_acceptance_script = module.production_acceptance_script("https://current.example.com", "adesso-mbp")

    assert 'ALLOWED_MODELS="${ALLOWED_MODELS:-codex-gpt-5.5}"' in register_script
    assert 'ALLOW_QUICK_TUNNEL_REGISTRATION="${ALLOW_QUICK_TUNNEL_REGISTRATION:-0}"' in register_script
    assert "WORKER_REQUIRE_NAMED_HTTPS=1" in register_script
    assert "Worker B registration requires an HTTPS named Cloudflare coordinator URL" in register_script
    assert "Worker B registration requires a real named Cloudflare hostname, not a placeholder" in register_script
    assert "Worker B registration requires a public named Cloudflare hostname, not a local URL" in register_script
    assert "Worker B registration requires a named Cloudflare hostname" in register_script
    assert "Worker B registration requires non-empty model IDs in ALLOWED_MODELS" in register_script
    assert "Worker B registration requires real model IDs in ALLOWED_MODELS, not placeholders" in register_script
    assert "Worker B registration requires real model IDs in ALLOWED_MODELS, not mock model IDs" in register_script
    assert "Worker B registration requires distinct model IDs in ALLOWED_MODELS, not duplicate model IDs" in register_script
    assert "Worker B registration requires GEMINI_API_KEY when ALLOWED_MODELS includes gemini-2.5-flash" in register_script
    assert "Worker B registration requires XAI_API_KEY when ALLOWED_MODELS includes grok-4" in register_script
    assert register_script.index("Worker B registration requires a named Cloudflare hostname") < register_script.index(
        "No USER_TOKEN set; make install-worker will reuse an existing matching worker registration"
    )
    assert register_script.index("Worker B registration requires GEMINI_API_KEY") < register_script.index(
        "No USER_TOKEN set; make install-worker will reuse an existing matching worker registration"
    )
    assert "Coordinator user token:" not in register_script
    assert 'USER_TOKEN="${USER_TOKEN:-}"' in register_script
    assert "No USER_TOKEN set; make install-worker will reuse an existing matching worker registration" in register_script
    assert 'export DIALECTICAL_USER_TOKEN="$USER_TOKEN"' not in register_script
    assert "GEMINI_API_KEY_FOR_INSTALL=" in register_script
    assert "XAI_API_KEY_FOR_INSTALL=" in register_script
    assert "export GEMINI_API_KEY" not in register_script
    assert "export XAI_API_KEY" not in register_script
    assert (
        'DIALECTICAL_USER_TOKEN="$USER_TOKEN" GEMINI_API_KEY="$GEMINI_API_KEY_FOR_INSTALL" XAI_API_KEY="$XAI_API_KEY_FOR_INSTALL" make install-worker COORDINATOR_URL="$COORDINATOR_URL" WORKER_NAME="$WORKER_NAME" ALLOWED_MODELS="$ALLOWED_MODELS" WORKER_REQUIRE_NAMED_HTTPS="$WORKER_REQUIRE_NAMED_HTTPS"'
        in register_script
    )
    assert register_script.index("No USER_TOKEN set; make install-worker will reuse") < register_script.index(
        'DIALECTICAL_USER_TOKEN="$USER_TOKEN" GEMINI_API_KEY="$GEMINI_API_KEY_FOR_INSTALL"'
    )
    assert 'export DIALECTICAL_ALLOWED_MODELS="$ALLOWED_MODELS"' in register_script
    assert 'ALLOWED_MODELS="$ALLOWED_MODELS"' in register_script
    assert (
        'make deploy-preflight DEPLOY_ROLE=worker PREFLIGHT_FLAGS="--require-registered-worker --require-installed-services --require-worker-api-keys-for-models $ALLOWED_MODELS"'
        in register_script
    )
    assert register_script.index("make install-worker") < register_script.index("make deploy-preflight DEPLOY_ROLE=worker")
    assert register_script.index("make deploy-preflight DEPLOY_ROLE=worker") < register_script.index(
        "make verify-worker-visible"
    )
    assert 'WORKER_REQUIRED_CAPABILITIES="$ALLOWED_MODELS"' in register_script
    assert "WORKER_REJECT_NON_PRODUCTION_CAPABILITIES=1" in register_script
    assert 'WORKER_REQUIRE_NAMED_HTTPS="$WORKER_REQUIRE_NAMED_HTTPS"' in register_script
    assert 'make verify-worker-visible COORDINATOR_URL="$COORDINATOR_URL" WORKER_NAME="$WORKER_NAME"' in register_script
    assert 'WORKER_VISIBLE_TIMEOUT="${WORKER_VISIBLE_TIMEOUT:-120}"' in register_script
    assert 'ALLOWED_MODELS="${ALLOWED_MODELS:-${REAL_MODEL_CAPABILITIES:-codex-gpt-5.5,gemini-2.5-flash}}"' in real_models_script
    assert "Worker B real-model setup requires an HTTPS named Cloudflare coordinator URL" in real_models_script
    assert "Worker B real-model setup requires a real named Cloudflare hostname, not a placeholder" in real_models_script
    assert "Worker B real-model setup requires a public named Cloudflare hostname, not a local URL" in real_models_script
    assert "Worker B real-model setup requires a named Cloudflare hostname, not a trycloudflare.com quick tunnel" in real_models_script
    assert "Worker B real-model setup requires non-empty model IDs in ALLOWED_MODELS" in real_models_script
    assert "Worker B real-model setup requires real model IDs in ALLOWED_MODELS, not placeholders" in real_models_script
    assert "Worker B real-model setup requires real model IDs in ALLOWED_MODELS, not mock model IDs" in real_models_script
    assert "Worker B real-model setup requires distinct model IDs in ALLOWED_MODELS, not duplicate model IDs" in real_models_script
    assert "Worker B real-model setup requires ALLOWED_MODELS to list at least two distinct real model IDs" in real_models_script
    assert "Worker B real-model setup requires GEMINI_API_KEY when ALLOWED_MODELS includes gemini-2.5-flash" in real_models_script
    assert "Worker B real-model setup requires XAI_API_KEY when ALLOWED_MODELS includes grok-4" in real_models_script
    assert real_models_script.index("Worker B real-model setup requires a named Cloudflare hostname") < real_models_script.index(
        "No USER_TOKEN set; make install-worker will reuse an existing matching worker registration"
    )
    assert real_models_script.index("Worker B real-model setup requires ALLOWED_MODELS") < real_models_script.index(
        "No USER_TOKEN set; make install-worker will reuse an existing matching worker registration"
    )
    assert "Coordinator user token:" not in real_models_script
    assert 'USER_TOKEN="${USER_TOKEN:-}"' in real_models_script
    assert "No USER_TOKEN set; make install-worker will reuse an existing matching worker registration" in real_models_script
    assert 'export DIALECTICAL_USER_TOKEN="$USER_TOKEN"' not in real_models_script
    assert "GEMINI_API_KEY_FOR_INSTALL=" in real_models_script
    assert "XAI_API_KEY_FOR_INSTALL=" in real_models_script
    assert "export GEMINI_API_KEY" not in real_models_script
    assert "export XAI_API_KEY" not in real_models_script
    assert 'export DIALECTICAL_ALLOWED_MODELS="$ALLOWED_MODELS"' in real_models_script
    assert (
        'DIALECTICAL_USER_TOKEN="$USER_TOKEN" GEMINI_API_KEY="$GEMINI_API_KEY_FOR_INSTALL" XAI_API_KEY="$XAI_API_KEY_FOR_INSTALL" make install-worker COORDINATOR_URL="$COORDINATOR_URL" WORKER_NAME="$WORKER_NAME" ALLOWED_MODELS="$ALLOWED_MODELS" WORKER_REQUIRE_NAMED_HTTPS="$WORKER_REQUIRE_NAMED_HTTPS"'
        in real_models_script
    )
    assert (
        'make deploy-preflight DEPLOY_ROLE=worker PREFLIGHT_FLAGS="--require-registered-worker --require-installed-services --require-worker-api-keys-for-models $ALLOWED_MODELS"'
        in real_models_script
    )
    assert real_models_script.index("make install-worker") < real_models_script.index(
        "make deploy-preflight DEPLOY_ROLE=worker"
    )
    assert real_models_script.index("make deploy-preflight DEPLOY_ROLE=worker") < real_models_script.index(
        "make verify-worker-visible"
    )
    assert 'make verify-worker-visible COORDINATOR_URL="$COORDINATOR_URL" WORKER_NAME="$WORKER_NAME"' in real_models_script
    assert 'WORKER_REQUIRED_CAPABILITIES="$ALLOWED_MODELS"' in real_models_script
    assert "WORKER_REJECT_NON_PRODUCTION_CAPABILITIES=1" in real_models_script
    assert "Worker B URL switch requires an HTTPS named Cloudflare coordinator URL" in switch_script
    assert "Worker B URL switch requires a real named Cloudflare hostname, not a placeholder" in switch_script
    assert "Worker B URL switch requires a public named Cloudflare hostname, not a local URL" in switch_script
    assert "Worker B URL switch requires a named Cloudflare hostname, not a trycloudflare.com quick tunnel" in switch_script
    assert "https://*" not in switch_script
    assert 'make update-worker-config COORDINATOR_URL="$NEW_COORDINATOR_URL"' in switch_script
    assert "WORKER_REQUIRE_NAMED_HTTPS=1" in switch_script
    assert 'launchctl load "$HOME/Library/LaunchAgents/com.dialectical.worker.plist"' in switch_script
    assert (
        'make deploy-preflight DEPLOY_ROLE=worker PREFLIGHT_FLAGS="--require-registered-worker --require-installed-services"'
        in switch_script
    )
    assert (
        'make deploy-preflight DEPLOY_ROLE=worker PREFLIGHT_FLAGS="--require-registered-worker --require-installed-services --require-worker-api-keys-for-models $VERIFY_REQUIRED_CAPABILITIES"'
        in switch_script
    )
    assert switch_script.index('make update-worker-config COORDINATOR_URL="$NEW_COORDINATOR_URL"') < switch_script.index(
        'launchctl load "$HOME/Library/LaunchAgents/com.dialectical.worker.plist"'
    )
    assert switch_script.index('launchctl load "$HOME/Library/LaunchAgents/com.dialectical.worker.plist"') < switch_script.index(
        "make deploy-preflight DEPLOY_ROLE=worker"
    )
    assert switch_script.index("make deploy-preflight DEPLOY_ROLE=worker") < switch_script.index(
        "make verify-worker-visible"
    )
    assert switch_script.index(
        'make deploy-preflight DEPLOY_ROLE=worker PREFLIGHT_FLAGS="--require-registered-worker --require-installed-services --require-worker-api-keys-for-models $VERIFY_REQUIRED_CAPABILITIES"'
    ) < switch_script.index('WORKER_REQUIRED_CAPABILITIES="$VERIFY_REQUIRED_CAPABILITIES"')
    assert 'make verify-worker-visible COORDINATOR_URL="$NEW_COORDINATOR_URL" WORKER_NAME="$WORKER_NAME"' in switch_script
    assert 'WORKER_REQUIRED_CAPABILITIES="$VERIFY_REQUIRED_CAPABILITIES"' in switch_script
    assert "WORKER_REJECT_NON_PRODUCTION_CAPABILITIES=1" in switch_script
    assert 'WORKER_STATUS_TIMEOUT="${WORKER_STATUS_TIMEOUT:-180}"' in production_acceptance_script
    assert (
        'WORKER_REQUIRED_CAPABILITIES="${WORKER_REQUIRED_CAPABILITIES:-${ALLOWED_MODELS:-codex-gpt-5.5,gemini-2.5-flash}}"'
        in production_acceptance_script
    )
    assert (
        'ALLOW_DISABLE_DIFFERENT_REGEN_MODEL_FOR_REHEARSAL="${ALLOW_DISABLE_DIFFERENT_REGEN_MODEL_FOR_REHEARSAL:-0}"'
        in production_acceptance_script
    )
    assert "production acceptance requires different-model regeneration proof" in production_acceptance_script
    assert 'STRICT_REPORT_VALIDATOR="${STRICT_REPORT_VALIDATOR:-$ENGINE_DIR/scripts/status_report.py}"' in production_acceptance_script
    assert 'SKIP_STRICT_REPORT_VALIDATION="${SKIP_STRICT_REPORT_VALIDATION:-0}"' in production_acceptance_script
    assert (
        'ALLOW_SKIP_STRICT_REPORT_VALIDATION_FOR_REHEARSAL="${ALLOW_SKIP_STRICT_REPORT_VALIDATION_FOR_REHEARSAL:-0}"'
        in production_acceptance_script
    )
    assert "production acceptance requires strict report validation" in production_acceptance_script
    assert "NONSTANDARD_REPORT_REHEARSAL=0" in production_acceptance_script
    assert "NONSTANDARD_REPORT_REHEARSAL=1" in production_acceptance_script
    assert "production acceptance nonstandard report directory is rehearsal-only" in production_acceptance_script
    assert "REQUIRED_CAPABILITY_COUNT=0" in production_acceptance_script
    assert "SEEN_REQUIRED_CAPABILITIES=," in production_acceptance_script
    assert (
        "final different-model production acceptance requires non-empty model IDs in WORKER_REQUIRED_CAPABILITIES"
        in production_acceptance_script
    )
    assert "not placeholders" in production_acceptance_script
    assert "not mock model IDs" in production_acceptance_script
    assert "not duplicate model IDs" in production_acceptance_script
    assert "final different-model production acceptance requires WORKER_REQUIRED_CAPABILITIES" in production_acceptance_script
    assert "ACCEPTANCE_REQUIRE_NAMED_HTTPS=1" in production_acceptance_script
    assert 'ACCEPTANCE_REQUIRE_NAMED_HTTPS="$ACCEPTANCE_REQUIRE_NAMED_HTTPS"' in production_acceptance_script
    assert production_acceptance_script.index("production acceptance requires a named Cloudflare hostname") < production_acceptance_script.index(
        "Coordinator user token:"
    )
    assert production_acceptance_script.index("final different-model production acceptance requires WORKER_REQUIRED_CAPABILITIES") < production_acceptance_script.index(
        "Coordinator user token:"
    )
    assert production_acceptance_script.index(
        "production acceptance requires different-model regeneration proof"
    ) < production_acceptance_script.index("Coordinator user token:")
    assert production_acceptance_script.index(
        "production acceptance nonstandard report directory is rehearsal-only"
    ) < production_acceptance_script.index("Coordinator user token:")
    assert "production acceptance requires an HTTPS named Cloudflare coordinator URL" in production_acceptance_script
    assert "production acceptance requires a real named Cloudflare hostname, not a placeholder" in production_acceptance_script
    assert "production acceptance requires a public named Cloudflare hostname, not a local URL" in production_acceptance_script
    assert "https://*" not in production_acceptance_script
    assert "https://localhost" not in production_acceptance_script
    assert 'make verify-worker-visible COORDINATOR_URL="$COORDINATOR_URL" WORKER_NAME="$WORKER_A_NAME"' in production_acceptance_script
    assert 'make verify-worker-visible COORDINATOR_URL="$COORDINATOR_URL" WORKER_NAME="$WORKER_B_NAME"' in production_acceptance_script
    assert 'WORKER_REQUIRED_CAPABILITIES="$WORKER_REQUIRED_CAPABILITIES"' in production_acceptance_script
    assert "WORKER_REJECT_NON_PRODUCTION_CAPABILITIES=1" in production_acceptance_script
    assert 'export USER_TOKEN' not in production_acceptance_script
    assert 'USER_TOKEN="$USER_TOKEN" make acceptance \\' in production_acceptance_script
    assert 'allowed_worker_statuses = set(("online", "offline", "degraded"))' in production_acceptance_script
    assert 'status is not a string' in production_acceptance_script
    assert 'invalid status: " + status' in production_acceptance_script
    assert 'current_job_id is not a string' in production_acceptance_script
    assert 'current_job_id is blank' in production_acceptance_script
    assert '"id": raw_worker_id.strip() if isinstance(raw_worker_id, str) else ""' in production_acceptance_script
    assert (
        '"current_job_id": current_job_id.strip() if isinstance(current_job_id, str) else current_job_id'
        in production_acceptance_script
    )
    assert '"last_seen": raw_last_seen.strip() if isinstance(raw_last_seen, str) else ""' in production_acceptance_script
    assert "def validate_worker_id_consistency(online_rows, offline_rows):" in production_acceptance_script
    assert "id mismatch between row sets:" in production_acceptance_script
    assert "worker row id reused by multiple workers:" in production_acceptance_script
    assert "validate_worker_id_consistency(online_rows, offline_rows)" in production_acceptance_script
    assert "def result_detail_values(result_name):" in production_acceptance_script
    assert "def result_evidence_values(result_name, evidence_kind):" in production_acceptance_script
    assert "def validate_result_values(label, structured_values, result_name, evidence_kind):" in production_acceptance_script
    assert "result detail mismatch: structured" in production_acceptance_script
    assert "result evidence mismatch: structured" in production_acceptance_script
    assert (
        'validate_result_values("online worker rows", set(online_rows), "workers-online", "worker-row")'
        in production_acceptance_script
    )
    assert (
        'validate_result_values("generated workers", generated_workers, "generated-workers", "string")'
        in production_acceptance_script
    )
    assert (
        'validate_result_values("regenerated model ids", regenerated_models, "regenerated-models", "string")'
        in production_acceptance_script
    )
    assert "def worker_row_field_value(row, field):" in production_acceptance_script
    assert "def worker_status_payload_names(evidence, field):" in production_acceptance_script
    assert "def validate_worker_status_payload(online_rows, offline_rows):" in production_acceptance_script
    assert "worker status payload evidence online names mismatch: structured" in production_acceptance_script
    assert "worker status payload evidence row mismatch for " in production_acceptance_script
    assert "worker status payload result detail does not match worker_count" in production_acceptance_script
    assert "validate_worker_status_payload(online_rows, offline_rows)" in production_acceptance_script
    assert production_acceptance_script.index('USER_TOKEN="$USER_TOKEN" make acceptance \\') > production_acceptance_script.index(
        "Coordinator user token:"
    )
    assert 'rm -rf "$tmpdir"' not in production_acceptance_script
    assert 'rm -f "$ACCEPTANCE_REPORT"' in production_acceptance_script
    assert production_acceptance_script.index('rm -f "$ACCEPTANCE_REPORT"') > production_acceptance_script.index(
        "Coordinator user token:"
    )
    assert production_acceptance_script.index('rm -f "$ACCEPTANCE_REPORT"') < production_acceptance_script.index(
        "make acceptance \\"
    )
    assert (
        'validate_acceptance_report "$ACCEPTANCE_REPORT" "$MODE" "current report" "$ACCEPTANCE_REQUIRE_NAMED_HTTPS" "$REQUIRE_DIFFERENT_REGEN_MODEL"'
        in production_acceptance_script
    )
    assert (
        'validate_strict_acceptance_report "$PRIOR_ACCEPTANCE_REPORT" "$PRIOR_ACCEPTANCE_MODE" "prior report"'
        in production_acceptance_script
    )
    assert (
        'validate_strict_acceptance_report "$ACCEPTANCE_REPORT" "$MODE" "current report"'
        in production_acceptance_script
    )
    assert production_acceptance_script.index(
        "production acceptance requires strict report validation"
    ) < production_acceptance_script.index("--validate-production-acceptance-report")
    assert "--validate-production-acceptance-report" in production_acceptance_script
    assert "--validate-production-phase" in production_acceptance_script
    assert "--validate-production-public-url" in production_acceptance_script
    assert production_acceptance_script.index(
        'validate_acceptance_report "$ACCEPTANCE_REPORT" "$MODE" "current report"'
    ) > production_acceptance_script.index("make acceptance \\")
    assert production_acceptance_script.index(
        'validate_acceptance_report "$ACCEPTANCE_REPORT" "$MODE" "current report"'
    ) < production_acceptance_script.index("Wrote acceptance report:")
    assert production_acceptance_script.index(
        'validate_strict_acceptance_report "$ACCEPTANCE_REPORT" "$MODE" "current report"'
    ) > production_acceptance_script.index(
        'validate_acceptance_report "$ACCEPTANCE_REPORT" "$MODE" "current report"'
    )
    assert production_acceptance_script.index(
        'validate_strict_acceptance_report "$ACCEPTANCE_REPORT" "$MODE" "current report"'
    ) < production_acceptance_script.index("Wrote acceptance report:")
    assert "make verify-worker-status COORDINATOR_URL=\"$COORDINATOR_URL\" WORKER_NAME=\"$WORKER_B_NAME\" WORKER_EXPECTED_STATUS=offline" in production_acceptance_script
    assert "WORKER_REQUIRE_CAPABILITIES=1" in production_acceptance_script
    assert 'REQUIRE_DIFFERENT_REGEN_MODEL="${REQUIRE_DIFFERENT_REGEN_MODEL:-1}"' in production_acceptance_script
    assert "SKIP_WEB_CHECKS=0" in production_acceptance_script
    assert "SKIP_SSE_CHECK=0" in production_acceptance_script


def test_handoff_final_helpers_reject_url_mismatch_with_named_config() -> None:
    module = load_module(ROOT / "scripts" / "build_handoff_bundles.py", "dialectical_build_handoff_bundles_url_match")

    final_check_script = module.final_production_check_script("https://current.example.com")
    worker_a_script = module.worker_a_real_models_script("https://current.example.com")
    readiness_script = module.production_readiness_script("https://current.example.com")
    sequence_script = module.production_acceptance_sequence_script("https://current.example.com")

    assert (
        "final production check requires COORDINATOR_URL to match installed named Cloudflare tunnel config"
        in final_check_script
    )
    assert (
        "final production check requires PUBLIC_URL to match installed named Cloudflare tunnel config"
        in final_check_script
    )
    assert (
        "production readiness requires COORDINATOR_URL to match installed named Cloudflare tunnel config"
        in readiness_script
    )
    assert (
        "production acceptance sequence requires COORDINATOR_URL to match installed named Cloudflare tunnel config before prompting for the user token"
        in sequence_script
    )
    assert (
        "Worker A real-model setup requires PUBLIC_COORDINATOR_URL to match installed named Cloudflare tunnel config"
        in worker_a_script
    )
    assert (
        'WORKER_REQUIRED_CAPABILITIES="${WORKER_REQUIRED_CAPABILITIES:-${ALLOWED_MODELS:-codex-gpt-5.5,gemini-2.5-flash}}"'
        in sequence_script
    )
    assert (
        'ALLOW_DISABLE_DIFFERENT_REGEN_MODEL_FOR_REHEARSAL="${ALLOW_DISABLE_DIFFERENT_REGEN_MODEL_FOR_REHEARSAL:-0}"'
        in sequence_script
    )
    assert (
        "production acceptance sequence requires different-model regeneration proof before prompting for the user token"
        in sequence_script
    )
    assert "final production check requires non-empty model IDs in WORKER_REQUIRED_CAPABILITIES" in final_check_script
    assert (
        "final production check requires WORKER_REQUIRED_CAPABILITIES to list at least two distinct real model IDs"
        in final_check_script
    )
    assert (
        'ALLOW_SKIP_PRODUCTION_REPORTS_FOR_REHEARSAL="${ALLOW_SKIP_PRODUCTION_REPORTS_FOR_REHEARSAL:-0}"'
        in final_check_script
    )
    assert "NONSTANDARD_REPORT_REHEARSAL=0" in final_check_script
    assert "NONSTANDARD_REPORT_REHEARSAL=1" in final_check_script
    assert (
        "final production check nonstandard report directory is rehearsal-only; set "
        "REQUIRE_PRODUCTION_ACCEPTANCE_REPORTS=0 with ALLOW_SKIP_PRODUCTION_REPORTS_FOR_REHEARSAL=1 "
        "before refreshing proof"
        in final_check_script
    )
    assert (
        "final production check nonstandard report directory is rehearsal-only; set "
        "ALLOW_SKIP_PRODUCTION_REPORTS_FOR_REHEARSAL=1 before refreshing proof"
        in final_check_script
    )
    assert 'ALLOW_SKIP_LOCAL_PROOF_FOR_REHEARSAL="${ALLOW_SKIP_LOCAL_PROOF_FOR_REHEARSAL:-0}"' in final_check_script
    assert "final production check requires production acceptance reports before refreshing proof" in final_check_script
    assert "final production check requires local proof refresh" in final_check_script
    assert "make test" in final_check_script
    assert "Worker A real-model setup requires non-empty model IDs in ALLOWED_MODELS" in worker_a_script
    assert "production readiness requires non-empty model IDs in WORKER_REQUIRED_CAPABILITIES" in readiness_script
    assert "production readiness requires deploy preflight" in readiness_script
    assert "production readiness requires endpoint status" in readiness_script
    assert (
        "production acceptance sequence requires non-empty model IDs in WORKER_REQUIRED_CAPABILITIES"
        in sequence_script
    )
    assert (
        "export ALLOW_DISABLE_DIFFERENT_REGEN_MODEL_FOR_REHEARSAL"
        in sequence_script
    )
    assert (
        "production acceptance sequence requires production_readiness.sh before prompting for the user token"
        in sequence_script
    )
    assert 'RUN_PREFLIGHT="${RUN_PREFLIGHT:-1}"' in sequence_script
    assert 'RUN_ENDPOINT_STATUS="${RUN_ENDPOINT_STATUS:-1}"' in sequence_script
    assert (
        "production acceptance sequence requires production_readiness.sh deploy preflight before prompting for the user token"
        in sequence_script
    )
    assert (
        "production acceptance sequence requires production_readiness.sh endpoint status before prompting for the user token"
        in sequence_script
    )
    assert (
        "production acceptance sequence nonstandard report directory is rehearsal-only; set SKIP_STRICT_REPORT_VALIDATION=1"
        in sequence_script
    )
    assert (
        "production acceptance sequence nonstandard report directory is rehearsal-only; set FINAL_CHECK_AFTER_ACCEPTANCE=0"
        in sequence_script
    )
    assert (
        "production acceptance sequence requires final_production_check.sh after rejoin acceptance"
        in sequence_script
    )
    assert "export WORKER_REQUIRED_CAPABILITIES" in readiness_script
    assert final_check_script.index("COORDINATOR_URL=") < final_check_script.index(
        "final production check requires COORDINATOR_URL to match installed named Cloudflare tunnel config"
    )
    assert final_check_script.index("PUBLIC_URL=") < final_check_script.index(
        "final production check requires PUBLIC_URL to match installed named Cloudflare tunnel config"
    )
    assert final_check_script.index(
        "final production check requires WORKER_REQUIRED_CAPABILITIES to list at least two distinct real model IDs"
    ) < final_check_script.index("final production check requires production acceptance report before refreshing proof")
    assert final_check_script.index(
        "final production check requires production acceptance reports before refreshing proof"
    ) < final_check_script.index("final production check requires production acceptance report before refreshing proof")
    assert final_check_script.index("NONSTANDARD_REPORT_REHEARSAL=1") < final_check_script.index(
        "final production check nonstandard report directory is rehearsal-only; set REQUIRE_PRODUCTION_ACCEPTANCE_REPORTS=0"
    )
    assert final_check_script.index(
        "final production check nonstandard report directory is rehearsal-only; set REQUIRE_PRODUCTION_ACCEPTANCE_REPORTS=0"
    ) < final_check_script.index(
        "final production check nonstandard report directory is rehearsal-only; set ALLOW_SKIP_PRODUCTION_REPORTS_FOR_REHEARSAL=1"
    )
    assert final_check_script.index(
        "final production check nonstandard report directory is rehearsal-only; set ALLOW_SKIP_PRODUCTION_REPORTS_FOR_REHEARSAL=1"
    ) < final_check_script.index("final production check requires production acceptance report before refreshing proof")
    assert final_check_script.index("final production check requires local proof refresh") < final_check_script.index(
        "make dev-smoke"
    )
    assert final_check_script.index("make deploy-preflight DEPLOY_ROLE=both") < final_check_script.index("make test")
    assert final_check_script.index("make test") < final_check_script.index("make dev-smoke")
    assert readiness_script.index(
        "production readiness requires COORDINATOR_URL to match installed named Cloudflare tunnel config"
    ) < readiness_script.index("make deploy-preflight")
    assert readiness_script.index("production readiness requires deploy preflight") < readiness_script.index(
        "make deploy-preflight"
    )
    assert readiness_script.index("production readiness requires endpoint status") < readiness_script.index(
        "make status STATUS_FLAGS=--check-endpoints"
    )
    assert worker_a_script.index(
        "Worker A real-model setup requires PUBLIC_COORDINATOR_URL to match installed named Cloudflare tunnel config"
    ) < worker_a_script.index("No USER_TOKEN set; make install-worker will reuse an existing matching worker registration")
    assert "Coordinator user token:" not in worker_a_script
    assert 'USER_TOKEN="${USER_TOKEN:-}"' in worker_a_script
    assert "No USER_TOKEN set; make install-worker will reuse an existing matching worker registration" in worker_a_script
    assert sequence_script.index(
        "production acceptance sequence requires COORDINATOR_URL to match installed named Cloudflare tunnel config before prompting for the user token"
    ) < sequence_script.index("Coordinator user token:")
    assert sequence_script.index(
        "production acceptance sequence requires production_readiness.sh before prompting for the user token"
    ) < sequence_script.index("Coordinator user token:")
    assert sequence_script.index(
        "production acceptance sequence requires production_readiness.sh deploy preflight before prompting for the user token"
    ) < sequence_script.index("Coordinator user token:")
    assert sequence_script.index(
        "production acceptance sequence requires production_readiness.sh endpoint status before prompting for the user token"
    ) < sequence_script.index("Coordinator user token:")
    assert sequence_script.index(
        "production acceptance sequence requires different-model regeneration proof before prompting for the user token"
    ) < sequence_script.index("Coordinator user token:")
    assert sequence_script.index(
        "production acceptance sequence nonstandard report directory is rehearsal-only; set SKIP_STRICT_REPORT_VALIDATION=1"
    ) < sequence_script.index("Coordinator user token:")
    assert sequence_script.index(
        "production acceptance sequence nonstandard report directory is rehearsal-only; set FINAL_CHECK_AFTER_ACCEPTANCE=0"
    ) < sequence_script.index("Coordinator user token:")
    assert (
        "production acceptance sequence final-check skip is rehearsal-only before prompting for the user token"
        in sequence_script
    )
    assert sequence_script.index(
        "production acceptance sequence final-check skip is rehearsal-only before prompting for the user token"
    ) < sequence_script.index("Coordinator user token:")
    assert (
        "production acceptance sequence requires executable final_production_check.sh before prompting for the user token"
        in sequence_script
    )
    assert (
        "production acceptance sequence requires valid final_production_check.sh before prompting for the user token"
        in sequence_script
    )
    assert sequence_script.index(
        "production acceptance sequence requires executable final_production_check.sh before prompting for the user token"
    ) < sequence_script.index("Coordinator user token:")
    assert sequence_script.index(
        "production acceptance sequence requires valid final_production_check.sh before prompting for the user token"
    ) < sequence_script.index("Coordinator user token:")
    assert sequence_script.index("export RUN_PREFLIGHT") < sequence_script.index(
        '"$SCRIPT_DIR/production_readiness.sh"'
    )
    assert sequence_script.index("export RUN_ENDPOINT_STATUS") < sequence_script.index(
        '"$SCRIPT_DIR/production_readiness.sh"'
    )
    assert sequence_script.index('MODE=rejoin-two-worker "$ACCEPTANCE_HELPER"') < sequence_script.index(
        "production acceptance sequence requires final_production_check.sh after rejoin acceptance"
    )
    assert sequence_script.index(
        "production acceptance sequence requires final_production_check.sh after rejoin acceptance"
    ) < sequence_script.rindex('"$FINAL_CHECK_HELPER"')


def test_named_tunnel_handoff_documents_install_guard() -> None:
    module = load_module(ROOT / "scripts" / "build_handoff_bundles.py", "dialectical_build_handoff_bundles_tunnel")

    readme = module.named_tunnel_readme()

    assert "This file must already exist before you run" in readme
    assert "validates the tunnel name" in readme
    assert "validates the credentials path, verifies" in readme
    assert "contains `AccountTag`, UUID-shaped `TunnelID`, and `TunnelSecret`" in readme
    assert "rejects `trycloudflare.com` quick tunnel hostnames" in readme
    assert "`cloudflared` on `PATH` before writing" in readme
    assert "`--stop-quick-after-verified`" in readme
    assert "`STOP_QUICK_TUNNEL_AFTER_VERIFY=0`" in readme
    assert "exits before changing" in readme
