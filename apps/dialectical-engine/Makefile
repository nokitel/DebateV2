SHELL := /bin/bash

.PHONY: dev dev-smoke test acceptance configure-local-single-machine configure-local-personal-models configure-gemini-google-auth refresh-local-models setup-status interactive-manual-setup source-snapshot local-status local-next-steps manual-setup-checklist hosting-status prepare-romarg-nameservers final-single-machine-check lmstudio-worker lmstudio-worker-once install-lmstudio-worker stop-lmstudio-worker probe-lmstudio-job probe-lmstudio-worker-job probe-model-auth local-cluster-check local-single-machine-check local-single-machine-acceptance wait-dezbatere-dns resume-dezbatere-hosting deploy-preflight status install-status-helper handoff-bundles final-production-check production-readiness production-acceptance-sequence install-services setup-named-tunnel setup-dezbatere-tunnel install-tunnel stop-quick-tunnel install-worker register-worker update-worker-config verify-worker-status verify-worker-visible configure-subscription-loop-routing start-subscription-loops start-claude-subscription-loop start-gemini-subscription-loop stop-subscription-loops subscription-loop-status bootstrap web-install web-build restart-web rebuild-web-service

PYTHON ?= $(shell for py in "$(CURDIR)/.venv/bin/python" "$(CURDIR)/.venv313/bin/python" "$(CURDIR)/.venv312/bin/python" python3.13 python3.12 python3; do if [ -x "$$py" ]; then resolved="$$py"; elif command -v "$$py" >/dev/null 2>&1; then resolved="$$(command -v "$$py")"; else continue; fi; if "$$resolved" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)' >/dev/null 2>&1; then printf '%s\n' "$$resolved"; exit; fi; done; if [ -x "$(CURDIR)/.venv/bin/python" ]; then printf '%s\n' "$(CURDIR)/.venv/bin/python"; elif command -v python3 >/dev/null 2>&1; then command -v python3; fi)
PNPM ?= $(shell command -v pnpm)
PYTHON_DYLD_LIBRARY_PATH ?= $(shell if [ -d /opt/homebrew/opt/expat/lib ]; then printf '%s\n' /opt/homebrew/opt/expat/lib; fi)
PYTHON_ENV ?= $(if $(PYTHON_DYLD_LIBRARY_PATH),DYLD_LIBRARY_PATH="$(PYTHON_DYLD_LIBRARY_PATH)",)
TEST_PYCACHE_PREFIX ?= /private/tmp/dialectical-test-pycache
LOCAL_CHECK_PYTHON ?= $(PYTHON)
DEZBATERE_DOMAIN ?= dezbatere.ro
WAIT_DEZBATERE_DNS_TIMEOUT ?= 1800
WAIT_DEZBATERE_DNS_INTERVAL ?= 60
MODEL_AUTH_REPORT ?= /private/tmp/dialectical-model-auth-check.json
HOSTING_STATUS_REPORT ?= /private/tmp/dialectical-hosting-status.json
SOURCE_SNAPSHOT ?= /private/tmp/dialectical-engine-source.tgz
SOURCE_SNAPSHOT_REPORT ?= /private/tmp/dialectical-engine-source-snapshot.json
CLOUDFLARE_NAMESERVERS ?=
ROMARG_NAMESERVER_CARD ?= Romarg_Nameservers_To_Set.md
FINAL_SINGLE_MACHINE_REPORT ?= /private/tmp/dialectical-final-single-machine-check.json
FINAL_SINGLE_MACHINE_FLAGS ?=
RESTART_WORKER ?= 1
COORDINATOR_URL ?= http://localhost:8000
WEB_URL ?=
WORKER_NAME ?= $(shell hostname)
WORKER_CONFIG ?= ~/.dialectical-worker/config.toml
ALLOWED_MODELS ?=
WORKER_VISIBLE_TIMEOUT ?= 90
WORKER_EXPECTED_STATUS ?= online
WORKER_REQUIRE_CAPABILITIES ?= 0
WORKER_REQUIRED_CAPABILITIES ?=
WORKER_REJECT_NON_PRODUCTION_CAPABILITIES ?= 0
WORKER_REQUIRE_NAMED_HTTPS ?= 0
SUBSCRIPTION_LOOP_URL ?= https://dezbatere.ro
SUBSCRIPTION_LOOP_INTERVAL_SECONDS ?= 60
CLAUDE_LOOP_SESSION ?= dialectical-claude-loop
GEMINI_LOOP_SESSION ?= dialectical-gemini-loop
CLAUDE_LOOP_WORKER_NAME ?= claude-max-loop
GEMINI_LOOP_WORKER_NAME ?= gemini-google-loop
CLAUDE_LOOP_CONFIG ?= ~/.dialectical-worker/claude-subscription-loop.toml
GEMINI_LOOP_CONFIG ?= ~/.dialectical-worker/gemini-subscription-loop.toml
CLAUDE_LOOP_CLI_MODEL ?= claude-sonnet-4-6
GEMINI_LOOP_CLI_MODEL ?= gemini-2.5-flash
GEMINI_LOOP_MODEL ?= gemini-2.5-flash-google-loop
WORKER_ALLOWED_MODELS_ARG = $(if $(filter command line environment override,$(origin ALLOWED_MODELS)),--allowed-models "$(ALLOWED_MODELS)",)
WORKER_REQUIRE_CAPABILITIES_ARG = $(if $(filter 1 true yes,$(WORKER_REQUIRE_CAPABILITIES)),--require-capabilities,)
WORKER_REQUIRED_CAPABILITIES_ARG = $(if $(strip $(WORKER_REQUIRED_CAPABILITIES)),--required-capabilities "$(WORKER_REQUIRED_CAPABILITIES)",)
WORKER_REJECT_NON_PRODUCTION_CAPABILITIES_ARG = $(if $(filter 1 true yes,$(WORKER_REJECT_NON_PRODUCTION_CAPABILITIES)),--reject-non-production-capabilities,)
WORKER_REQUIRE_NAMED_HTTPS_ARG = $(if $(filter 1 true yes,$(WORKER_REQUIRE_NAMED_HTTPS)),--require-named-https,)
TUNNEL_NAME ?= dialectical
TUNNEL_HOSTNAME ?= debate.<your-domain>
CLOUDFLARED_CREDENTIALS ?= auto
STOP_QUICK_TUNNEL_AFTER_VERIFY ?= 1
SETUP_NAMED_TUNNEL_FLAGS ?=
USER_TOKEN ?=
export USER_TOKEN
EXPECTED_WORKERS ?= 1
EXPECTED_WORKER_NAMES ?=
EXPECTED_OFFLINE_WORKER_NAMES ?=
ACCEPTANCE_PHASE ?=
REQUIRE_WORKERS_IN_TREE ?= 0
REQUIRE_DIFFERENT_REGEN_MODEL ?= 0
SKIP_WEB_CHECKS ?= 0
SKIP_SSE_CHECK ?= 0
ACCEPTANCE_REQUIRE_NAMED_HTTPS ?= 0
ACCEPTANCE_REPORT ?=
ACCEPTANCE_REQUIRE_NAMED_HTTPS_ARG = $(if $(filter 1 true yes,$(ACCEPTANCE_REQUIRE_NAMED_HTTPS)),--require-named-https,)
ACCEPTANCE_PHASE_ARG = $(if $(strip $(ACCEPTANCE_PHASE)),--phase "$(ACCEPTANCE_PHASE)",)
DEPLOY_ROLE ?= both
PREFLIGHT_FLAGS ?=
STATUS_FLAGS ?=
BUNDLE_OUTPUT_DIR ?= /private/tmp
HANDOFF_ARCHIVE ?= $(BUNDLE_OUTPUT_DIR)/dialectical-v2-handoff-$(shell date +%F).tgz
PUBLIC_URL ?= https://debate.<your-domain>
WORKER_B_NAME ?= adesso-mbp
LAUNCHD_PATH ?= $(HOME)/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin

dev:
	$(PYTHON_ENV) "$(PYTHON)" scripts/dev.py

dev-smoke:
	$(PYTHON_ENV) "$(PYTHON)" scripts/dev_smoke_check.py

test:
	cd coordinator && PYTHONPYCACHEPREFIX="$(TEST_PYCACHE_PREFIX)" PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 $(PYTHON_ENV) "$(PYTHON)" -m pytest -p pytest_cov.plugin -p pytest_asyncio.plugin tests --cov=app/services --cov-report=term-missing --cov-fail-under=70
	cd worker && PYTHONPYCACHEPREFIX="$(TEST_PYCACHE_PREFIX)" PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 $(PYTHON_ENV) "$(PYTHON)" -m pytest -p pytest_cov.plugin -p pytest_asyncio.plugin tests --cov=app/adapters --cov-report=term-missing --cov-fail-under=70
	$(PYTHON_ENV) "$(PYTHON)" scripts/write_test_report.py

acceptance:
	@set -eu; \
	token="$${USER_TOKEN:-}"; \
	if [ -z "$$token" ]; then \
		if [ ! -t 0 ]; then \
			echo "USER_TOKEN is required for acceptance checks that create and regenerate debates" >&2; \
			exit 2; \
		fi; \
		printf "Coordinator user token: " >&2; \
		saved_stty="$$(stty -g)"; \
		trap 'stty "$$saved_stty"' INT TERM HUP EXIT; \
		stty -echo; \
		if IFS= read -r token; then \
			stty "$$saved_stty"; \
			trap - INT TERM HUP EXIT; \
			printf "\n" >&2; \
		else \
			stty "$$saved_stty"; \
			trap - INT TERM HUP EXIT; \
			printf "\n" >&2; \
			exit 2; \
		fi; \
	fi; \
	if [ -z "$$token" ]; then \
		echo "USER_TOKEN cannot be empty" >&2; \
		exit 2; \
	fi; \
	USER_TOKEN="$$token" $(PYTHON_ENV) "$(PYTHON)" scripts/acceptance_check.py --base-url "$(COORDINATOR_URL)" $(if $(WEB_URL),--web-base-url "$(WEB_URL)",) $(ACCEPTANCE_PHASE_ARG) --expected-workers "$(EXPECTED_WORKERS)" --expected-worker-names "$(EXPECTED_WORKER_NAMES)" $(if $(EXPECTED_OFFLINE_WORKER_NAMES),--expected-offline-worker-names "$(EXPECTED_OFFLINE_WORKER_NAMES)",) $(if $(filter 1 true yes,$(REQUIRE_WORKERS_IN_TREE)),--require-expected-workers-in-tree,) $(if $(filter 1 true yes,$(REQUIRE_DIFFERENT_REGEN_MODEL)),--require-different-regen-model,) $(ACCEPTANCE_REQUIRE_NAMED_HTTPS_ARG) $(if $(filter 1 true yes,$(SKIP_WEB_CHECKS)),--skip-web-checks,) $(if $(filter 1 true yes,$(SKIP_SSE_CHECK)),--skip-sse-check,) $(if $(ACCEPTANCE_REPORT),--report-path "$(ACCEPTANCE_REPORT)",)

local-cluster-check:
	pnpm --dir web build
	$(PYTHON_ENV) "$(PYTHON)" scripts/local_cluster_check.py

local-single-machine-check:
	DYLD_LIBRARY_PATH="$(PYTHON_DYLD_LIBRARY_PATH)" "$(LOCAL_CHECK_PYTHON)" scripts/local_single_machine_check.py

local-single-machine-acceptance:
	DYLD_LIBRARY_PATH="$(PYTHON_DYLD_LIBRARY_PATH)" "$(LOCAL_CHECK_PYTHON)" scripts/local_single_machine_acceptance.py

local-status: local-single-machine-acceptance local-next-steps

setup-status:
	$(MAKE) local-single-machine-check
	$(MAKE) probe-model-auth
	$(MAKE) hosting-status
	$(MAKE) manual-setup-checklist
	$(MAKE) local-status

interactive-manual-setup:
	./scripts/interactive_manual_setup.sh

source-snapshot:
	DYLD_LIBRARY_PATH="$(PYTHON_DYLD_LIBRARY_PATH)" "$(LOCAL_CHECK_PYTHON)" scripts/export_source_snapshot.py --output "$(SOURCE_SNAPSHOT)" --report-path "$(SOURCE_SNAPSHOT_REPORT)"

local-next-steps:
	DYLD_LIBRARY_PATH="$(PYTHON_DYLD_LIBRARY_PATH)" "$(LOCAL_CHECK_PYTHON)" scripts/local_next_steps.py --auth-report "$(MODEL_AUTH_REPORT)"

manual-setup-checklist:
	DYLD_LIBRARY_PATH="$(PYTHON_DYLD_LIBRARY_PATH)" "$(LOCAL_CHECK_PYTHON)" scripts/manual_setup_checklist.py --auth-report "$(MODEL_AUTH_REPORT)" --hosting-report "$(HOSTING_STATUS_REPORT)"

hosting-status:
	DYLD_LIBRARY_PATH="$(PYTHON_DYLD_LIBRARY_PATH)" "$(LOCAL_CHECK_PYTHON)" scripts/hosting_status.py --domain "$(DEZBATERE_DOMAIN)" --report-path "$(HOSTING_STATUS_REPORT)"

prepare-romarg-nameservers:
	DYLD_LIBRARY_PATH="$(PYTHON_DYLD_LIBRARY_PATH)" "$(LOCAL_CHECK_PYTHON)" scripts/prepare_romarg_nameservers.py $(if $(strip $(CLOUDFLARE_NAMESERVERS)),--nameservers "$(CLOUDFLARE_NAMESERVERS)",) --output "$(ROMARG_NAMESERVER_CARD)"

final-single-machine-check: setup-status
	DYLD_LIBRARY_PATH="$(PYTHON_DYLD_LIBRARY_PATH)" "$(LOCAL_CHECK_PYTHON)" scripts/final_single_machine_check.py --report-path "$(FINAL_SINGLE_MACHINE_REPORT)" $(FINAL_SINGLE_MACHINE_FLAGS)

wait-dezbatere-dns:
	DYLD_LIBRARY_PATH="$(PYTHON_DYLD_LIBRARY_PATH)" "$(LOCAL_CHECK_PYTHON)" scripts/wait_dezbatere_delegation.py --domain "$(DEZBATERE_DOMAIN)" --timeout-seconds "$(WAIT_DEZBATERE_DNS_TIMEOUT)" --interval-seconds "$(WAIT_DEZBATERE_DNS_INTERVAL)"

resume-dezbatere-hosting:
	./scripts/resume_dezbatere_hosting.sh

configure-local-single-machine:
	DYLD_LIBRARY_PATH="$(PYTHON_DYLD_LIBRARY_PATH)" "$(LOCAL_CHECK_PYTHON)" scripts/configure_local_single_machine.py

configure-local-personal-models:
	DYLD_LIBRARY_PATH="$(PYTHON_DYLD_LIBRARY_PATH)" "$(LOCAL_CHECK_PYTHON)" scripts/configure_local_personal_models.py $(if $(filter 1 true yes,$(RESTART_WORKER)),--restart-worker,)

refresh-local-models: configure-local-personal-models local-status

configure-gemini-google-auth:
	DYLD_LIBRARY_PATH="$(PYTHON_DYLD_LIBRARY_PATH)" "$(LOCAL_CHECK_PYTHON)" scripts/configure_gemini_google_auth.py

lmstudio-worker:
	DYLD_LIBRARY_PATH="$(PYTHON_DYLD_LIBRARY_PATH)" "$(LOCAL_CHECK_PYTHON)" scripts/lmstudio_worker.py

lmstudio-worker-once:
	DYLD_LIBRARY_PATH="$(PYTHON_DYLD_LIBRARY_PATH)" "$(LOCAL_CHECK_PYTHON)" scripts/lmstudio_worker.py --once

install-lmstudio-worker:
	mkdir -p "$$HOME/Library/LaunchAgents"
	sed -e "s#__ROOT__#$(CURDIR)#g" -e "s#__PYTHON__#$(LOCAL_CHECK_PYTHON)#g" -e "s#__PATH__#$(LAUNCHD_PATH)#g" -e "s#__PYTHON_DYLD_LIBRARY_PATH__#$(PYTHON_DYLD_LIBRARY_PATH)#g" deploy/launchd/lmstudio-worker.plist > "$$HOME/Library/LaunchAgents/com.dialectical.lmstudio-worker.plist"
	launchctl unload "$$HOME/Library/LaunchAgents/com.dialectical.lmstudio-worker.plist" 2>/dev/null || true
	launchctl load "$$HOME/Library/LaunchAgents/com.dialectical.lmstudio-worker.plist"

stop-lmstudio-worker:
	launchctl unload "$$HOME/Library/LaunchAgents/com.dialectical.lmstudio-worker.plist" 2>/dev/null || true

probe-lmstudio-job:
	DYLD_LIBRARY_PATH="$(PYTHON_DYLD_LIBRARY_PATH)" "$(LOCAL_CHECK_PYTHON)" scripts/probe_lmstudio_worker_job.py

probe-lmstudio-worker-job: probe-lmstudio-job

probe-model-auth:
	DYLD_LIBRARY_PATH="$(PYTHON_DYLD_LIBRARY_PATH)" "$(LOCAL_CHECK_PYTHON)" scripts/local_single_machine_check.py --probe-models --report-path "$(MODEL_AUTH_REPORT)"

deploy-preflight:
	$(PYTHON_ENV) "$(PYTHON)" scripts/deployment_preflight.py --role "$(DEPLOY_ROLE)" $(PREFLIGHT_FLAGS)

status:
	$(PYTHON_ENV) "$(PYTHON)" scripts/status_report.py $(STATUS_FLAGS)

install-status-helper:
	mkdir -p "$$HOME/.dialectical/bin"
	install -m 0755 scripts/status_report.py "$$HOME/.dialectical/bin/dialectical-status-report.py"

handoff-bundles:
	$(PYTHON_ENV) "$(PYTHON)" scripts/build_handoff_bundles.py --output-dir "$(BUNDLE_OUTPUT_DIR)" --public-url "$(PUBLIC_URL)" --worker-name "$(WORKER_B_NAME)"

final-production-check:
	@set -eu; \
	bundle="$(HANDOFF_ARCHIVE)"; \
	if [ ! -f "$$bundle" ]; then \
		echo "handoff bundle missing: $$bundle" >&2; \
		echo "run: make handoff-bundles PUBLIC_URL=$(PUBLIC_URL)" >&2; \
		exit 2; \
	fi; \
	tmpdir="$$(mktemp -d)"; \
	trap 'rm -rf "$$tmpdir"' EXIT INT TERM HUP; \
	tar -xzf "$$bundle" -C "$$tmpdir"; \
	script="$$tmpdir/dialectical-handoff/final_production_check.sh"; \
	if [ ! -x "$$script" ]; then \
		echo "handoff bundle missing executable final_production_check.sh: $$bundle" >&2; \
		exit 2; \
	fi; \
	ENGINE_DIR="$${ENGINE_DIR:-$(CURDIR)}" "$$script"

production-readiness:
	@set -eu; \
	bundle="$(HANDOFF_ARCHIVE)"; \
	if [ ! -f "$$bundle" ]; then \
		echo "handoff bundle missing: $$bundle" >&2; \
		echo "run: make handoff-bundles PUBLIC_URL=$(PUBLIC_URL)" >&2; \
		exit 2; \
	fi; \
	tmpdir="$$(mktemp -d)"; \
	trap 'rm -rf "$$tmpdir"' EXIT INT TERM HUP; \
	tar -xzf "$$bundle" -C "$$tmpdir"; \
	script="$$tmpdir/dialectical-handoff/production_readiness.sh"; \
	if [ ! -x "$$script" ]; then \
		echo "handoff bundle missing executable production_readiness.sh: $$bundle" >&2; \
		exit 2; \
	fi; \
	ENGINE_DIR="$${ENGINE_DIR:-$(CURDIR)}" "$$script"

production-acceptance-sequence:
	@set -eu; \
	bundle="$(HANDOFF_ARCHIVE)"; \
	if [ ! -f "$$bundle" ]; then \
		echo "handoff bundle missing: $$bundle" >&2; \
		echo "run: make handoff-bundles PUBLIC_URL=$(PUBLIC_URL)" >&2; \
		exit 2; \
	fi; \
	tmpdir="$$(mktemp -d)"; \
	trap 'rm -rf "$$tmpdir"' EXIT INT TERM HUP; \
	tar -xzf "$$bundle" -C "$$tmpdir"; \
	script="$$tmpdir/dialectical-handoff/production_acceptance_sequence.sh"; \
	if [ ! -x "$$script" ]; then \
		echo "handoff bundle missing executable production_acceptance_sequence.sh: $$bundle" >&2; \
		exit 2; \
	fi; \
	ENGINE_DIR="$${ENGINE_DIR:-$(CURDIR)}" "$$script"

bootstrap:
	$(PYTHON_ENV) "$(PYTHON)" -m pip install -r requirements-dev.txt
	pnpm --dir web install

web-install:
	pnpm --dir web install

web-build:
	pnpm --dir web build

restart-web:
	launchctl unload "$$HOME/Library/LaunchAgents/com.dialectical.web.plist" 2>/dev/null || true
	launchctl load "$$HOME/Library/LaunchAgents/com.dialectical.web.plist"

rebuild-web-service: web-install web-build restart-web

register-worker:
	$(PYTHON_ENV) "$(PYTHON)" scripts/register_worker.py --coordinator-url "$(COORDINATOR_URL)" --name "$(WORKER_NAME)" $(WORKER_ALLOWED_MODELS_ARG) $(WORKER_REQUIRE_NAMED_HTTPS_ARG)

install-worker:
	$(PYTHON_ENV) "$(PYTHON)" scripts/install_worker.py --coordinator-url "$(COORDINATOR_URL)" --name "$(WORKER_NAME)" --python "$(PYTHON)" $(WORKER_ALLOWED_MODELS_ARG) $(WORKER_REQUIRE_NAMED_HTTPS_ARG)

update-worker-config:
	$(PYTHON_ENV) "$(PYTHON)" scripts/update_worker_config.py --coordinator-url "$(COORDINATOR_URL)" --config "$(WORKER_CONFIG)" $(WORKER_ALLOWED_MODELS_ARG) $(WORKER_REQUIRE_NAMED_HTTPS_ARG)

verify-worker-status:
	$(PYTHON_ENV) "$(PYTHON)" scripts/verify_worker_visible.py --base-url "$(COORDINATOR_URL)" --worker-name "$(WORKER_NAME)" --expected-status "$(WORKER_EXPECTED_STATUS)" --timeout "$(WORKER_VISIBLE_TIMEOUT)" $(WORKER_REQUIRE_CAPABILITIES_ARG) $(WORKER_REQUIRED_CAPABILITIES_ARG) $(WORKER_REJECT_NON_PRODUCTION_CAPABILITIES_ARG)

verify-worker-visible:
	$(PYTHON_ENV) "$(PYTHON)" scripts/verify_worker_visible.py --base-url "$(COORDINATOR_URL)" --worker-name "$(WORKER_NAME)" --expected-status online --timeout "$(WORKER_VISIBLE_TIMEOUT)" --require-capabilities $(WORKER_REQUIRED_CAPABILITIES_ARG) $(WORKER_REJECT_NON_PRODUCTION_CAPABILITIES_ARG)

configure-subscription-loop-routing:
	$(PYTHON_ENV) "$(PYTHON)" scripts/subscription_loop.py configure-routing --coordinator-url "$(SUBSCRIPTION_LOOP_URL)" --gemini-loop-model "$(GEMINI_LOOP_MODEL)"

start-subscription-loops:
	$(PYTHON_ENV) "$(PYTHON)" scripts/subscription_loop.py start --coordinator-url "$(SUBSCRIPTION_LOOP_URL)" --interval-seconds "$(SUBSCRIPTION_LOOP_INTERVAL_SECONDS)" --claude-session "$(CLAUDE_LOOP_SESSION)" --gemini-session "$(GEMINI_LOOP_SESSION)" --claude-worker-name "$(CLAUDE_LOOP_WORKER_NAME)" --gemini-worker-name "$(GEMINI_LOOP_WORKER_NAME)" --claude-config "$(CLAUDE_LOOP_CONFIG)" --gemini-config "$(GEMINI_LOOP_CONFIG)" --claude-model "$(CLAUDE_LOOP_CLI_MODEL)" --gemini-model "$(GEMINI_LOOP_CLI_MODEL)" --gemini-loop-model "$(GEMINI_LOOP_MODEL)"

start-claude-subscription-loop:
	$(PYTHON_ENV) "$(PYTHON)" scripts/subscription_loop.py start-claude --coordinator-url "$(SUBSCRIPTION_LOOP_URL)" --interval-seconds "$(SUBSCRIPTION_LOOP_INTERVAL_SECONDS)" --claude-session "$(CLAUDE_LOOP_SESSION)" --claude-worker-name "$(CLAUDE_LOOP_WORKER_NAME)" --claude-config "$(CLAUDE_LOOP_CONFIG)" --claude-model "$(CLAUDE_LOOP_CLI_MODEL)"

start-gemini-subscription-loop:
	$(PYTHON_ENV) "$(PYTHON)" scripts/subscription_loop.py start-gemini --coordinator-url "$(SUBSCRIPTION_LOOP_URL)" --interval-seconds "$(SUBSCRIPTION_LOOP_INTERVAL_SECONDS)" --gemini-session "$(GEMINI_LOOP_SESSION)" --gemini-worker-name "$(GEMINI_LOOP_WORKER_NAME)" --gemini-config "$(GEMINI_LOOP_CONFIG)" --gemini-model "$(GEMINI_LOOP_CLI_MODEL)" --gemini-loop-model "$(GEMINI_LOOP_MODEL)"

stop-subscription-loops:
	$(PYTHON_ENV) "$(PYTHON)" scripts/subscription_loop.py stop --claude-session "$(CLAUDE_LOOP_SESSION)" --gemini-session "$(GEMINI_LOOP_SESSION)"

subscription-loop-status:
	$(PYTHON_ENV) "$(PYTHON)" scripts/subscription_loop.py status --claude-session "$(CLAUDE_LOOP_SESSION)" --gemini-session "$(GEMINI_LOOP_SESSION)"

install-services:
	pnpm --dir web build
	mkdir -p "$$HOME/Library/LaunchAgents"
	sed -e "s#__ROOT__#$(CURDIR)#g" -e "s#__PYTHON__#$(PYTHON)#g" -e "s#__PATH__#$(LAUNCHD_PATH)#g" -e "s#__PYTHON_DYLD_LIBRARY_PATH__#$(PYTHON_DYLD_LIBRARY_PATH)#g" deploy/launchd/coordinator.plist > "$$HOME/Library/LaunchAgents/com.dialectical.coordinator.plist"
	sed -e "s#__ROOT__#$(CURDIR)#g" -e "s#__PYTHON__#$(PYTHON)#g" -e "s#__PNPM__#$(PNPM)#g" -e "s#__PATH__#$(LAUNCHD_PATH)#g" deploy/launchd/web.plist > "$$HOME/Library/LaunchAgents/com.dialectical.web.plist"
	launchctl unload "$$HOME/Library/LaunchAgents/com.dialectical.coordinator.plist" 2>/dev/null || true
	launchctl unload "$$HOME/Library/LaunchAgents/com.dialectical.web.plist" 2>/dev/null || true
	launchctl load "$$HOME/Library/LaunchAgents/com.dialectical.coordinator.plist"
	launchctl load "$$HOME/Library/LaunchAgents/com.dialectical.web.plist"
	@echo "Coordinator and web services installed. Register Worker A with: make install-worker COORDINATOR_URL=http://localhost:8000 WORKER_NAME=mac-mini"

setup-named-tunnel:
	$(PYTHON_ENV) "$(PYTHON)" scripts/setup_named_tunnel.py --tunnel "$(TUNNEL_NAME)" --hostname "$(TUNNEL_HOSTNAME)" --credentials-file "$(CLOUDFLARED_CREDENTIALS)" $(if $(filter 1 true yes,$(STOP_QUICK_TUNNEL_AFTER_VERIFY)),--stop-quick-after-verified,) $(SETUP_NAMED_TUNNEL_FLAGS)

setup-dezbatere-tunnel:
	./scripts/setup_dezbatere_tunnel.sh

install-tunnel:
	"$(PYTHON)" scripts/install_tunnel.py --tunnel "$(TUNNEL_NAME)" --hostname "$(TUNNEL_HOSTNAME)" --credentials-file "$(CLOUDFLARED_CREDENTIALS)" --route-dns --install-service

stop-quick-tunnel:
	$(PYTHON_ENV) "$(PYTHON)" scripts/install_tunnel.py --stop-quick-service-only
