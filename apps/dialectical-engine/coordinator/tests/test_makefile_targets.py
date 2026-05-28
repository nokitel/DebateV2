from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_worker_install_targets_forward_allowed_models() -> None:
    makefile = (ROOT / "Makefile").read_text()

    assert "WORKER_ALLOWED_MODELS_ARG = " in makefile
    assert "WORKER_REQUIRE_NAMED_HTTPS_ARG = " in makefile
    assert (
        'scripts/register_worker.py --coordinator-url "$(COORDINATOR_URL)" '
        '--name "$(WORKER_NAME)" $(WORKER_ALLOWED_MODELS_ARG) $(WORKER_REQUIRE_NAMED_HTTPS_ARG)'
    ) in makefile
    assert (
        'scripts/install_worker.py --coordinator-url "$(COORDINATOR_URL)" '
        '--name "$(WORKER_NAME)" --python "$(PYTHON)" $(WORKER_ALLOWED_MODELS_ARG) $(WORKER_REQUIRE_NAMED_HTTPS_ARG)'
    ) in makefile
    assert (
        'scripts/update_worker_config.py --coordinator-url "$(COORDINATOR_URL)" '
        '--config "$(WORKER_CONFIG)" $(WORKER_ALLOWED_MODELS_ARG) $(WORKER_REQUIRE_NAMED_HTTPS_ARG)'
    ) in makefile


def test_makefile_exposes_explicit_quick_tunnel_stop_target() -> None:
    makefile = (ROOT / "Makefile").read_text()

    assert "stop-quick-tunnel:" in makefile
    assert 'scripts/install_tunnel.py --stop-quick-service-only' in makefile


def test_makefile_exposes_named_tunnel_setup_target() -> None:
    makefile = (ROOT / "Makefile").read_text()

    assert "setup-named-tunnel:" in makefile
    assert 'scripts/setup_named_tunnel.py --tunnel "$(TUNNEL_NAME)"' in makefile
    assert "STOP_QUICK_TUNNEL_AFTER_VERIFY ?= 1" in makefile
    assert "--stop-quick-after-verified" in makefile
    assert "$(SETUP_NAMED_TUNNEL_FLAGS)" in makefile


def test_makefile_exposes_interactive_manual_setup_target() -> None:
    makefile = (ROOT / "Makefile").read_text()
    helper = (ROOT / "scripts" / "interactive_manual_setup.sh").read_text()

    assert "interactive-manual-setup:" in makefile
    assert "./scripts/interactive_manual_setup.sh" in makefile
    assert "Create Romarg nameserver paste card" in helper
    assert "make prepare-romarg-nameservers" in helper


def test_makefile_exposes_romarg_nameserver_card_target() -> None:
    makefile = (ROOT / "Makefile").read_text()

    assert "LOCAL_CHECK_PYTHON ?= $(PYTHON)" in makefile
    assert "CLOUDFLARE_NAMESERVERS ?=" in makefile
    assert "ROMARG_NAMESERVER_CARD ?= Romarg_Nameservers_To_Set.md" in makefile
    assert "prepare-romarg-nameservers:" in makefile
    assert 'scripts/prepare_romarg_nameservers.py $(if $(strip $(CLOUDFLARE_NAMESERVERS)),--nameservers "$(CLOUDFLARE_NAMESERVERS)",) --output "$(ROMARG_NAMESERVER_CARD)"' in makefile


def test_dezbatere_tunnel_helpers_require_full_cloudflare_delegation() -> None:
    for script_name in ("resume_dezbatere_hosting.sh", "setup_dezbatere_tunnel.sh"):
        script = (ROOT / "scripts" / script_name).read_text()

        assert "is_cloudflare_delegation()" in script
        assert "cloudflare == total" in script
        assert (
            "every nameserver must end with .ns.cloudflare.com" in script
            or "Replace all Romarg nameservers" in script
        )


def test_makefile_exposes_source_snapshot_target() -> None:
    makefile = (ROOT / "Makefile").read_text()

    assert "SOURCE_SNAPSHOT ?= /private/tmp/dialectical-engine-source.tgz" in makefile
    assert "SOURCE_SNAPSHOT_REPORT ?= /private/tmp/dialectical-engine-source-snapshot.json" in makefile
    assert "source-snapshot:" in makefile
    assert 'scripts/export_source_snapshot.py --output "$(SOURCE_SNAPSHOT)" --report-path "$(SOURCE_SNAPSHOT_REPORT)"' in makefile


def test_makefile_exposes_handoff_production_gate_targets() -> None:
    makefile = (ROOT / "Makefile").read_text()

    assert "HANDOFF_ARCHIVE ?= $(BUNDLE_OUTPUT_DIR)/dialectical-v2-handoff-$(shell date +%F).tgz" in makefile
    assert "final-production-check:" in makefile
    assert "production-readiness:" in makefile
    assert "production-acceptance-sequence:" in makefile
    assert "dialectical-handoff/final_production_check.sh" in makefile
    assert "dialectical-handoff/production_readiness.sh" in makefile
    assert "dialectical-handoff/production_acceptance_sequence.sh" in makefile
    assert 'ENGINE_DIR="$${ENGINE_DIR:-$(CURDIR)}" "$$script"' in makefile


def test_local_cluster_check_builds_web_before_running_proof() -> None:
    makefile = (ROOT / "Makefile").read_text()

    target = makefile.split("local-cluster-check:", 1)[1].split("\n\ndeploy-preflight:", 1)[0]

    assert "pnpm --dir web build" in target
    assert "scripts/local_cluster_check.py" in target
    assert target.index("pnpm --dir web build") < target.index("scripts/local_cluster_check.py")
