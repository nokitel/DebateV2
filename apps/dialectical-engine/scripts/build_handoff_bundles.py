#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import shutil
import stat
import tarfile
import tempfile
import textwrap
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = Path("/private/tmp")
DEFAULT_WORKER_NAME = "adesso-mbp"
DEFAULT_PUBLIC_URL = "https://debate.<your-domain>"
AUDIT_PATH = Path("/private/tmp/dialectical-completion-audit.md")


def write(path: Path, text: str, mode: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text).lstrip(), encoding="utf-8")
    if mode is not None:
        path.chmod(mode)


def tar_directory(source: Path, destination: Path) -> None:
    if destination.exists():
        destination.unlink()
    with tarfile.open(destination, "w:gz") as archive:
        archive.add(source, arcname=source.name)


def worker_env_example(public_url: str, worker_name: str) -> str:
    return f"""
    USER_TOKEN=<coordinator-user-token>
    COORDINATOR_URL={public_url}
    NEW_COORDINATOR_URL=https://debate.<your-domain>
    WORKER_NAME={worker_name}
    WORKER_A_NAME=mac-mini
    WORKER_B_NAME={worker_name}
    MODE=two-worker
    ACCEPTANCE_REPORT_DIR=/private/tmp
    ALLOW_QUICK_TUNNEL_REGISTRATION=0
    ALLOW_QUICK_TUNNEL_ACCEPTANCE=0
    REQUIRE_DIFFERENT_REGEN_MODEL=1
    ALLOW_DISABLE_DIFFERENT_REGEN_MODEL_FOR_REHEARSAL=0
    SKIP_STRICT_REPORT_VALIDATION=0
    ALLOW_SKIP_STRICT_REPORT_VALIDATION_FOR_REHEARSAL=0
    WORKER_REQUIRED_CAPABILITIES=codex-gpt-5.5,gemini-2.5-flash
    ALLOWED_MODELS=codex-gpt-5.5,gemini-2.5-flash
    GEMINI_API_KEY=<google-ai-studio-api-key-for-gemini-2.5-flash>
    XAI_API_KEY=<optional-xai-api-key>
    ENGINE_DIR=/path/to/dialectical-engine
    """


def user_token_prompt(extra_exit_cleanup: str = "") -> str:
    extra_cleanup = f"; {extra_exit_cleanup}" if extra_exit_cleanup else ""
    return """
    if [ -z "${USER_TOKEN:-}" ]; then
        if [ ! -t 0 ]; then
            echo "set USER_TOKEN to the coordinator user bearer token" >&2
            exit 2
        fi
        printf "Coordinator user token: " >&2
        saved_stty=$(stty -g)
        trap 'stty "$saved_stty"__TOKEN_PROMPT_EXTRA_CLEANUP__' INT TERM HUP 0
        stty -echo
        if IFS= read -r USER_TOKEN; then
            stty "$saved_stty"
            trap - INT TERM HUP 0
            printf "\\n" >&2
        else
            stty "$saved_stty"
            trap - INT TERM HUP 0
            printf "\\n" >&2
            exit 2
        fi
    fi
    : "${USER_TOKEN:?coordinator user token cannot be empty}"
    """.replace("__TOKEN_PROMPT_EXTRA_CLEANUP__", extra_cleanup)


def optional_user_token_for_install() -> str:
    return """
    USER_TOKEN="${USER_TOKEN:-}"
    if [ -z "$USER_TOKEN" ]; then
        echo "No USER_TOKEN set; make install-worker will reuse an existing matching worker registration, or prompt if a new registration is required." >&2
    fi
    """


def worker_register_script(public_url: str, worker_name: str) -> str:
    return f"""
    #!/bin/sh
    set -eu

    : "${{ENGINE_DIR:?set ENGINE_DIR to the dialectical-engine checkout on this Mac}}"

    SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
    COORDINATOR_URL="${{COORDINATOR_URL:-{public_url}}}"
    ALLOW_QUICK_TUNNEL_REGISTRATION="${{ALLOW_QUICK_TUNNEL_REGISTRATION:-0}}"
    WORKER_REQUIRE_NAMED_HTTPS=1
    WORKER_NAME="${{WORKER_NAME:-{worker_name}}}"
    WORKER_VISIBLE_TIMEOUT="${{WORKER_VISIBLE_TIMEOUT:-120}}"
    ALLOWED_MODELS="${{ALLOWED_MODELS:-codex-gpt-5.5}}"
    PUBLIC_ENDPOINT_PYTHON="${{PUBLIC_ENDPOINT_PYTHON:-python3}}"
    PUBLIC_ENDPOINT_SCRIPT="${{PUBLIC_ENDPOINT_SCRIPT:-$SCRIPT_DIR/verify_public_endpoint.py}}"
    if [ ! -r "$PUBLIC_ENDPOINT_SCRIPT" ]; then
        PUBLIC_ENDPOINT_SCRIPT="$ENGINE_DIR/scripts/verify_public_endpoint.py"
    fi

    case "$COORDINATOR_URL" in
        https:*) ;;
        *)
            echo "Worker B registration requires an HTTPS named Cloudflare coordinator URL" >&2
            exit 2
            ;;
    esac
    case "$COORDINATOR_URL" in
        *"://"*) ;;
        *)
            echo "Worker B registration requires an HTTPS named Cloudflare coordinator URL" >&2
            exit 2
            ;;
    esac
    case "$COORDINATOR_URL" in
        *"<"*|*">"*)
            echo "Worker B registration requires a real named Cloudflare hostname, not a placeholder" >&2
            exit 2
            ;;
        *localhost*|*127.*|*0.0.0.0*|*"::1"*)
            echo "Worker B registration requires a public named Cloudflare hostname, not a local URL" >&2
            exit 2
            ;;
        *trycloudflare.com*)
            if [ "$ALLOW_QUICK_TUNNEL_REGISTRATION" != "1" ] && [ "$ALLOW_QUICK_TUNNEL_REGISTRATION" != "true" ] && [ "$ALLOW_QUICK_TUNNEL_REGISTRATION" != "yes" ]; then
                echo "Worker B registration requires a named Cloudflare hostname; set ALLOW_QUICK_TUNNEL_REGISTRATION=1 only for a provisional quick-tunnel registration" >&2
                exit 2
            fi
            WORKER_REQUIRE_NAMED_HTTPS=0
            ;;
    esac

    SEEN_ALLOWED_MODELS=,
    NEEDS_GEMINI_API_KEY=0
    NEEDS_XAI_API_KEY=0
    old_ifs="$IFS"
    IFS=,
    for capability in $ALLOWED_MODELS; do
        capability="$(printf '%s' "$capability" | sed 's/^[[:space:]]*//; s/[[:space:]]*$//')"
        case "$capability" in
            "")
                echo "Worker B registration requires non-empty model IDs in ALLOWED_MODELS" >&2
                exit 2
                ;;
            *"<"*|*">"*|*placeholder*)
                echo "Worker B registration requires real model IDs in ALLOWED_MODELS, not placeholders" >&2
                exit 2
                ;;
            mock-local|mock-*|*mock-*)
                echo "Worker B registration requires real model IDs in ALLOWED_MODELS, not mock model IDs" >&2
                exit 2
                ;;
            *)
                case "$SEEN_ALLOWED_MODELS" in
                    *",$capability,"*)
                        echo "Worker B registration requires distinct model IDs in ALLOWED_MODELS, not duplicate model IDs" >&2
                        exit 2
                        ;;
                esac
                case "$capability" in
                    gemini-2.5-flash) NEEDS_GEMINI_API_KEY=1 ;;
                    grok-4) NEEDS_XAI_API_KEY=1 ;;
                esac
                SEEN_ALLOWED_MODELS="${{SEEN_ALLOWED_MODELS}}$capability,"
                ;;
        esac
    done
    IFS="$old_ifs"

    export ALLOWED_MODELS
    export DIALECTICAL_ALLOWED_MODELS="$ALLOWED_MODELS"
    GEMINI_API_KEY_FOR_INSTALL=""
    case "${{GEMINI_API_KEY:-}}" in
        ""|*"<"*|*">"*) unset GEMINI_API_KEY ;;
        *)
            GEMINI_API_KEY_FOR_INSTALL="$GEMINI_API_KEY"
            unset GEMINI_API_KEY
            ;;
    esac
    XAI_API_KEY_FOR_INSTALL=""
    case "${{XAI_API_KEY:-}}" in
        ""|*"<"*|*">"*) unset XAI_API_KEY ;;
        *)
            XAI_API_KEY_FOR_INSTALL="$XAI_API_KEY"
            unset XAI_API_KEY
            ;;
    esac
    if [ "$NEEDS_GEMINI_API_KEY" = "1" ] && [ -z "$GEMINI_API_KEY_FOR_INSTALL" ]; then
        echo "Worker B registration requires GEMINI_API_KEY when ALLOWED_MODELS includes gemini-2.5-flash" >&2
        exit 2
    fi
    if [ "$NEEDS_XAI_API_KEY" = "1" ] && [ -z "$XAI_API_KEY_FOR_INSTALL" ]; then
        echo "Worker B registration requires XAI_API_KEY when ALLOWED_MODELS includes grok-4" >&2
        exit 2
    fi

    cd "$ENGINE_DIR"
    if [ "$WORKER_REQUIRE_NAMED_HTTPS" = "1" ]; then
        "$PUBLIC_ENDPOINT_PYTHON" "$PUBLIC_ENDPOINT_SCRIPT" --base-url "$COORDINATOR_URL" --require-named-https
    else
        "$PUBLIC_ENDPOINT_PYTHON" "$PUBLIC_ENDPOINT_SCRIPT" --base-url "$COORDINATOR_URL"
    fi
    make bootstrap
    {optional_user_token_for_install()}
    DIALECTICAL_USER_TOKEN="$USER_TOKEN" GEMINI_API_KEY="$GEMINI_API_KEY_FOR_INSTALL" XAI_API_KEY="$XAI_API_KEY_FOR_INSTALL" make install-worker COORDINATOR_URL="$COORDINATOR_URL" WORKER_NAME="$WORKER_NAME" ALLOWED_MODELS="$ALLOWED_MODELS" WORKER_REQUIRE_NAMED_HTTPS="$WORKER_REQUIRE_NAMED_HTTPS"
    make deploy-preflight DEPLOY_ROLE=worker PREFLIGHT_FLAGS="--require-registered-worker --require-installed-services --require-worker-api-keys-for-models $ALLOWED_MODELS"
    if [ "$ALLOWED_MODELS" ]; then
        make verify-worker-visible COORDINATOR_URL="$COORDINATOR_URL" WORKER_NAME="$WORKER_NAME" WORKER_VISIBLE_TIMEOUT="$WORKER_VISIBLE_TIMEOUT" WORKER_REQUIRED_CAPABILITIES="$ALLOWED_MODELS" WORKER_REJECT_NON_PRODUCTION_CAPABILITIES=1
    else
    make verify-worker-visible COORDINATOR_URL="$COORDINATOR_URL" WORKER_NAME="$WORKER_NAME" WORKER_VISIBLE_TIMEOUT="$WORKER_VISIBLE_TIMEOUT" WORKER_REJECT_NON_PRODUCTION_CAPABILITIES=1
    fi
    """


def worker_real_models_script(public_url: str, worker_name: str) -> str:
    return f"""
    #!/bin/sh
    set -eu

    : "${{ENGINE_DIR:?set ENGINE_DIR to the dialectical-engine checkout on this Mac}}"

    SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
    COORDINATOR_URL="${{COORDINATOR_URL:-{public_url}}}"
    WORKER_NAME="${{WORKER_NAME:-{worker_name}}}"
    WORKER_VISIBLE_TIMEOUT="${{WORKER_VISIBLE_TIMEOUT:-180}}"
    WORKER_REQUIRE_NAMED_HTTPS=1
    ALLOWED_MODELS="${{ALLOWED_MODELS:-${{REAL_MODEL_CAPABILITIES:-codex-gpt-5.5,gemini-2.5-flash}}}}"
    PUBLIC_ENDPOINT_PYTHON="${{PUBLIC_ENDPOINT_PYTHON:-python3}}"
    PUBLIC_ENDPOINT_SCRIPT="${{PUBLIC_ENDPOINT_SCRIPT:-$SCRIPT_DIR/verify_public_endpoint.py}}"
    if [ ! -r "$PUBLIC_ENDPOINT_SCRIPT" ]; then
        PUBLIC_ENDPOINT_SCRIPT="$ENGINE_DIR/scripts/verify_public_endpoint.py"
    fi

    case "$COORDINATOR_URL" in
        https:*) ;;
        *)
            echo "Worker B real-model setup requires an HTTPS named Cloudflare coordinator URL" >&2
            exit 2
            ;;
    esac
    case "$COORDINATOR_URL" in
        *"://"*) ;;
        *)
            echo "Worker B real-model setup requires an HTTPS named Cloudflare coordinator URL" >&2
            exit 2
            ;;
    esac
    case "$COORDINATOR_URL" in
        *"<"*|*">"*)
            echo "Worker B real-model setup requires a real named Cloudflare hostname, not a placeholder" >&2
            exit 2
            ;;
        *localhost*|*127.*|*0.0.0.0*|*"::1"*)
            echo "Worker B real-model setup requires a public named Cloudflare hostname, not a local URL" >&2
            exit 2
            ;;
        *trycloudflare.com*)
            echo "Worker B real-model setup requires a named Cloudflare hostname, not a trycloudflare.com quick tunnel" >&2
            exit 2
            ;;
    esac

    REQUIRED_CAPABILITY_COUNT=0
    SEEN_REQUIRED_CAPABILITIES=,
    NEEDS_GEMINI_API_KEY=0
    NEEDS_XAI_API_KEY=0
    old_ifs="$IFS"
    IFS=,
    for capability in $ALLOWED_MODELS; do
        capability="$(printf '%s' "$capability" | sed 's/^[[:space:]]*//; s/[[:space:]]*$//')"
        case "$capability" in
            "")
                echo "Worker B real-model setup requires non-empty model IDs in ALLOWED_MODELS" >&2
                exit 2
                ;;
            *"<"*|*">"*|*placeholder*)
                echo "Worker B real-model setup requires real model IDs in ALLOWED_MODELS, not placeholders" >&2
                exit 2
                ;;
            mock-local|mock-*|*mock-*)
                echo "Worker B real-model setup requires real model IDs in ALLOWED_MODELS, not mock model IDs" >&2
                exit 2
                ;;
            *)
                case "$SEEN_REQUIRED_CAPABILITIES" in
                    *",$capability,"*)
                        echo "Worker B real-model setup requires distinct model IDs in ALLOWED_MODELS, not duplicate model IDs" >&2
                        exit 2
                        ;;
                esac
                case "$capability" in
                    gemini-2.5-flash) NEEDS_GEMINI_API_KEY=1 ;;
                    grok-4) NEEDS_XAI_API_KEY=1 ;;
                esac
                SEEN_REQUIRED_CAPABILITIES="${{SEEN_REQUIRED_CAPABILITIES}}$capability,"
                REQUIRED_CAPABILITY_COUNT=$((REQUIRED_CAPABILITY_COUNT + 1))
                ;;
        esac
    done
    IFS="$old_ifs"
    if [ "$REQUIRED_CAPABILITY_COUNT" -lt 2 ]; then
        echo "Worker B real-model setup requires ALLOWED_MODELS to list at least two distinct real model IDs" >&2
        exit 2
    fi

    GEMINI_API_KEY_FOR_INSTALL=""
    case "${{GEMINI_API_KEY:-}}" in
        ""|*"<"*|*">"*) unset GEMINI_API_KEY ;;
        *)
            GEMINI_API_KEY_FOR_INSTALL="$GEMINI_API_KEY"
            unset GEMINI_API_KEY
            ;;
    esac
    XAI_API_KEY_FOR_INSTALL=""
    case "${{XAI_API_KEY:-}}" in
        ""|*"<"*|*">"*) unset XAI_API_KEY ;;
        *)
            XAI_API_KEY_FOR_INSTALL="$XAI_API_KEY"
            unset XAI_API_KEY
            ;;
    esac
    if [ "$NEEDS_GEMINI_API_KEY" = "1" ] && [ -z "$GEMINI_API_KEY_FOR_INSTALL" ]; then
        echo "Worker B real-model setup requires GEMINI_API_KEY when ALLOWED_MODELS includes gemini-2.5-flash" >&2
        exit 2
    fi
    if [ "$NEEDS_XAI_API_KEY" = "1" ] && [ -z "$XAI_API_KEY_FOR_INSTALL" ]; then
        echo "Worker B real-model setup requires XAI_API_KEY when ALLOWED_MODELS includes grok-4" >&2
        exit 2
    fi

    export ALLOWED_MODELS
    export DIALECTICAL_ALLOWED_MODELS="$ALLOWED_MODELS"

    cd "$ENGINE_DIR"
    "$PUBLIC_ENDPOINT_PYTHON" "$PUBLIC_ENDPOINT_SCRIPT" --base-url "$COORDINATOR_URL" --require-named-https
    make bootstrap
    {optional_user_token_for_install()}
    DIALECTICAL_USER_TOKEN="$USER_TOKEN" GEMINI_API_KEY="$GEMINI_API_KEY_FOR_INSTALL" XAI_API_KEY="$XAI_API_KEY_FOR_INSTALL" make install-worker COORDINATOR_URL="$COORDINATOR_URL" WORKER_NAME="$WORKER_NAME" ALLOWED_MODELS="$ALLOWED_MODELS" WORKER_REQUIRE_NAMED_HTTPS="$WORKER_REQUIRE_NAMED_HTTPS"
    make deploy-preflight DEPLOY_ROLE=worker PREFLIGHT_FLAGS="--require-registered-worker --require-installed-services --require-worker-api-keys-for-models $ALLOWED_MODELS"
    make verify-worker-visible COORDINATOR_URL="$COORDINATOR_URL" WORKER_NAME="$WORKER_NAME" WORKER_VISIBLE_TIMEOUT="$WORKER_VISIBLE_TIMEOUT" WORKER_REQUIRED_CAPABILITIES="$ALLOWED_MODELS" WORKER_REJECT_NON_PRODUCTION_CAPABILITIES=1
    echo "Worker B advertises required real-model capabilities: $ALLOWED_MODELS"
    """


def production_acceptance_script(public_url: str, worker_name: str) -> str:
    return f"""
    #!/bin/sh
    set -eu

    : "${{ENGINE_DIR:?set ENGINE_DIR to the dialectical-engine checkout on this Mac}}"

    COORDINATOR_URL="${{COORDINATOR_URL:-{public_url}}}"
    ALLOW_QUICK_TUNNEL_ACCEPTANCE="${{ALLOW_QUICK_TUNNEL_ACCEPTANCE:-0}}"
    ACCEPTANCE_REQUIRE_NAMED_HTTPS=1
    MODE="${{MODE:-two-worker}}"
    WORKER_A_NAME="${{WORKER_A_NAME:-mac-mini}}"
    WORKER_B_NAME="${{WORKER_B_NAME:-{worker_name}}}"
    ACCEPTANCE_REPORT_DIR="${{ACCEPTANCE_REPORT_DIR:-/private/tmp}}"
    ALLOW_NONSTANDARD_ACCEPTANCE_REPORT_DIR="${{ALLOW_NONSTANDARD_ACCEPTANCE_REPORT_DIR:-0}}"
    REQUIRE_DIFFERENT_REGEN_MODEL="${{REQUIRE_DIFFERENT_REGEN_MODEL:-1}}"
    ALLOW_DISABLE_DIFFERENT_REGEN_MODEL_FOR_REHEARSAL="${{ALLOW_DISABLE_DIFFERENT_REGEN_MODEL_FOR_REHEARSAL:-0}}"
    WORKER_STATUS_TIMEOUT="${{WORKER_STATUS_TIMEOUT:-180}}"
    WORKER_REQUIRED_CAPABILITIES="${{WORKER_REQUIRED_CAPABILITIES:-${{ALLOWED_MODELS:-codex-gpt-5.5,gemini-2.5-flash}}}}"
    export WORKER_REQUIRED_CAPABILITIES
    ACCEPTANCE_REPORT="${{ACCEPTANCE_REPORT:-$ACCEPTANCE_REPORT_DIR/dialectical-acceptance-$MODE.json}}"
    TWO_WORKER_ACCEPTANCE_REPORT="${{TWO_WORKER_ACCEPTANCE_REPORT:-$ACCEPTANCE_REPORT_DIR/dialectical-acceptance-two-worker.json}}"
    FAILOVER_ACCEPTANCE_REPORT="${{FAILOVER_ACCEPTANCE_REPORT:-$ACCEPTANCE_REPORT_DIR/dialectical-acceptance-failover-one-worker.json}}"
    REJOIN_ACCEPTANCE_REPORT="${{REJOIN_ACCEPTANCE_REPORT:-$ACCEPTANCE_REPORT_DIR/dialectical-acceptance-rejoin-two-worker.json}}"
    REPORT_PYTHON="${{REPORT_PYTHON:-python3}}"
    STRICT_REPORT_VALIDATOR="${{STRICT_REPORT_VALIDATOR:-$ENGINE_DIR/scripts/status_report.py}}"
    SKIP_STRICT_REPORT_VALIDATION="${{SKIP_STRICT_REPORT_VALIDATION:-0}}"
    ALLOW_SKIP_STRICT_REPORT_VALIDATION_FOR_REHEARSAL="${{ALLOW_SKIP_STRICT_REPORT_VALIDATION_FOR_REHEARSAL:-0}}"
    REHEARSAL_ACCEPTANCE=0
    NONSTANDARD_REPORT_REHEARSAL=0

    case "$COORDINATOR_URL" in
        https:*) ;;
        *)
            echo "production acceptance requires an HTTPS named Cloudflare coordinator URL" >&2
            exit 2
            ;;
    esac
    case "$COORDINATOR_URL" in
        *"://"*) ;;
        *)
            echo "production acceptance requires an HTTPS named Cloudflare coordinator URL" >&2
            exit 2
            ;;
    esac
    case "$COORDINATOR_URL" in
        *"<"*|*">"*)
            echo "production acceptance requires a real named Cloudflare hostname, not a placeholder" >&2
            exit 2
            ;;
        *localhost*|*127.*|*0.0.0.0*|*"::1"*)
            echo "production acceptance requires a public named Cloudflare hostname, not a local URL" >&2
            exit 2
            ;;
    esac
    case "$COORDINATOR_URL" in
        *trycloudflare.com*)
            if [ "$ALLOW_QUICK_TUNNEL_ACCEPTANCE" != "1" ] && [ "$ALLOW_QUICK_TUNNEL_ACCEPTANCE" != "true" ] && [ "$ALLOW_QUICK_TUNNEL_ACCEPTANCE" != "yes" ]; then
                echo "production acceptance requires a named Cloudflare hostname; set ALLOW_QUICK_TUNNEL_ACCEPTANCE=1 only for a provisional quick-tunnel smoke run" >&2
                exit 2
            fi
            ACCEPTANCE_REQUIRE_NAMED_HTTPS=0
            REHEARSAL_ACCEPTANCE=1
            ;;
    esac

    REQUIRED_CAPABILITY_COUNT=0
    SEEN_REQUIRED_CAPABILITIES=,
    old_ifs="$IFS"
    IFS=,
    for capability in $WORKER_REQUIRED_CAPABILITIES; do
        capability="$(printf '%s' "$capability" | sed 's/^[[:space:]]*//; s/[[:space:]]*$//')"
        case "$capability" in
            "")
                echo "final different-model production acceptance requires non-empty model IDs in WORKER_REQUIRED_CAPABILITIES" >&2
                exit 2
                ;;
            *"<"*|*">"*|*placeholder*)
                echo "final different-model production acceptance requires real model IDs in WORKER_REQUIRED_CAPABILITIES, not placeholders" >&2
                exit 2
                ;;
            mock-local|mock-*|*mock-*)
                echo "final different-model production acceptance requires real model IDs in WORKER_REQUIRED_CAPABILITIES, not mock model IDs" >&2
                exit 2
                ;;
            *)
                case "$SEEN_REQUIRED_CAPABILITIES" in
                    *",$capability,"*)
                        echo "final different-model production acceptance requires distinct model IDs in WORKER_REQUIRED_CAPABILITIES, not duplicate model IDs" >&2
                        exit 2
                        ;;
                esac
                SEEN_REQUIRED_CAPABILITIES="${{SEEN_REQUIRED_CAPABILITIES}}$capability,"
                REQUIRED_CAPABILITY_COUNT=$((REQUIRED_CAPABILITY_COUNT + 1))
                ;;
        esac
    done
    IFS="$old_ifs"
    case "$REQUIRE_DIFFERENT_REGEN_MODEL" in
        1|true|yes)
            if [ "$REQUIRED_CAPABILITY_COUNT" -lt 2 ]; then
                echo "final different-model production acceptance requires WORKER_REQUIRED_CAPABILITIES to list at least two real model IDs; set REQUIRE_DIFFERENT_REGEN_MODEL=0 with ALLOW_DISABLE_DIFFERENT_REGEN_MODEL_FOR_REHEARSAL=1 only for a rehearsal run" >&2
                exit 2
            fi
            ;;
        0|false|no)
            REHEARSAL_ACCEPTANCE=1
            if [ "$ALLOW_DISABLE_DIFFERENT_REGEN_MODEL_FOR_REHEARSAL" != "1" ] && [ "$ALLOW_DISABLE_DIFFERENT_REGEN_MODEL_FOR_REHEARSAL" != "true" ] && [ "$ALLOW_DISABLE_DIFFERENT_REGEN_MODEL_FOR_REHEARSAL" != "yes" ]; then
                echo "production acceptance requires different-model regeneration proof; set ALLOW_DISABLE_DIFFERENT_REGEN_MODEL_FOR_REHEARSAL=1 only for a rehearsal run" >&2
                exit 2
            fi
            ;;
    esac

    if [ "$REHEARSAL_ACCEPTANCE" = "1" ]; then
        case "$SKIP_STRICT_REPORT_VALIDATION" in
            1|true|yes) ;;
            *)
                echo "production acceptance rehearsal requires strict report validation skip; set SKIP_STRICT_REPORT_VALIDATION=1 with ALLOW_SKIP_STRICT_REPORT_VALIDATION_FOR_REHEARSAL=1 only for a rehearsal run" >&2
                exit 2
                ;;
        esac
        if [ "$ALLOW_SKIP_STRICT_REPORT_VALIDATION_FOR_REHEARSAL" != "1" ] && [ "$ALLOW_SKIP_STRICT_REPORT_VALIDATION_FOR_REHEARSAL" != "true" ] && [ "$ALLOW_SKIP_STRICT_REPORT_VALIDATION_FOR_REHEARSAL" != "yes" ]; then
            echo "production acceptance rehearsal requires strict report validation skip; set ALLOW_SKIP_STRICT_REPORT_VALIDATION_FOR_REHEARSAL=1 only for a rehearsal run" >&2
            exit 2
        fi
    fi

    case "$MODE" in
        two-worker|rejoin-two-worker)
            EXPECTED_WORKERS="${{EXPECTED_WORKERS:-2}}"
            EXPECTED_WORKER_NAMES="${{EXPECTED_WORKER_NAMES:-$WORKER_A_NAME,$WORKER_B_NAME}}"
            EXPECTED_OFFLINE_WORKER_NAMES="${{EXPECTED_OFFLINE_WORKER_NAMES:-}}"
            REQUIRE_WORKERS_IN_TREE="${{REQUIRE_WORKERS_IN_TREE:-1}}"
            ;;
        failover-one-worker)
            EXPECTED_WORKERS="${{EXPECTED_WORKERS:-1}}"
            EXPECTED_WORKER_NAMES="${{EXPECTED_WORKER_NAMES:-$WORKER_A_NAME}}"
            EXPECTED_OFFLINE_WORKER_NAMES="${{EXPECTED_OFFLINE_WORKER_NAMES:-$WORKER_B_NAME}}"
            REQUIRE_WORKERS_IN_TREE="${{REQUIRE_WORKERS_IN_TREE:-0}}"
            ;;
        *)
            echo "MODE must be two-worker, failover-one-worker, or rejoin-two-worker" >&2
            exit 2
            ;;
    esac

    validate_report_path() {{
        actual="$1"
        expected="$2"
        label="$3"
        expected_double_slash="${{expected%/*}}//${{expected##*/}}"
        if [ "$actual" = "$expected" ] || [ "$actual" = "$expected_double_slash" ]; then
            return
        fi
        if [ "$ALLOW_NONSTANDARD_ACCEPTANCE_REPORT_DIR" = "1" ] || [ "$ALLOW_NONSTANDARD_ACCEPTANCE_REPORT_DIR" = "true" ] || [ "$ALLOW_NONSTANDARD_ACCEPTANCE_REPORT_DIR" = "yes" ]; then
            NONSTANDARD_REPORT_REHEARSAL=1
            return
        fi
        echo "production acceptance writes final reports to /private/tmp where strict status reads them; $label must be $expected, got $actual; set ALLOW_NONSTANDARD_ACCEPTANCE_REPORT_DIR=1 only for a rehearsal run" >&2
        exit 2
    }}

    validate_report_path "$ACCEPTANCE_REPORT" "/private/tmp/dialectical-acceptance-$MODE.json" "current report path"
    validate_report_path "$TWO_WORKER_ACCEPTANCE_REPORT" "/private/tmp/dialectical-acceptance-two-worker.json" "two-worker report path"
    validate_report_path "$FAILOVER_ACCEPTANCE_REPORT" "/private/tmp/dialectical-acceptance-failover-one-worker.json" "failover report path"
    validate_report_path "$REJOIN_ACCEPTANCE_REPORT" "/private/tmp/dialectical-acceptance-rejoin-two-worker.json" "rejoin report path"

    if [ "$NONSTANDARD_REPORT_REHEARSAL" = "1" ]; then
        case "$SKIP_STRICT_REPORT_VALIDATION" in
            1|true|yes) ;;
            *)
                echo "production acceptance nonstandard report directory is rehearsal-only; set SKIP_STRICT_REPORT_VALIDATION=1 with ALLOW_SKIP_STRICT_REPORT_VALIDATION_FOR_REHEARSAL=1 before prompting for the user token" >&2
                exit 2
                ;;
        esac
        if [ "$ALLOW_SKIP_STRICT_REPORT_VALIDATION_FOR_REHEARSAL" != "1" ] && [ "$ALLOW_SKIP_STRICT_REPORT_VALIDATION_FOR_REHEARSAL" != "true" ] && [ "$ALLOW_SKIP_STRICT_REPORT_VALIDATION_FOR_REHEARSAL" != "yes" ]; then
            echo "production acceptance nonstandard report directory is rehearsal-only; set ALLOW_SKIP_STRICT_REPORT_VALIDATION_FOR_REHEARSAL=1 before prompting for the user token" >&2
            exit 2
        fi
    fi

    validate_acceptance_report() {{
        report_path="$1"
        expected_phase="$2"
        report_label="$3"
        expected_named_https="$4"
        expected_different_regen_model="$5"
        if ! command -v "$REPORT_PYTHON" >/dev/null 2>&1 && [ ! -x "$REPORT_PYTHON" ]; then
            echo "production acceptance report validation requires python: $REPORT_PYTHON" >&2
            exit 2
        fi
        "$REPORT_PYTHON" - "$report_path" "$expected_phase" "$COORDINATOR_URL" "$WORKER_A_NAME" "$WORKER_B_NAME" "$report_label" "$expected_named_https" "$expected_different_regen_model" <<'PY'
import json
import sys
from datetime import datetime
from uuid import UUID

path = sys.argv[1]
expected_phase = sys.argv[2]
coordinator_url = sys.argv[3].rstrip("/")
worker_a = sys.argv[4]
worker_b = sys.argv[5]
report_label = sys.argv[6]
expected_named_https = sys.argv[7].lower() in ("1", "true", "yes")
expected_different_regen_model = sys.argv[8].lower() in ("1", "true", "yes")
issues = []

try:
    with open(path, encoding="utf-8") as handle:
        payload = json.load(handle)
except Exception as exc:
    print(
        "production acceptance "
        + report_label
        + " invalid: "
        + path
        + ": unreadable ("
        + type(exc).__name__
        + ")",
        file=sys.stderr,
    )
    raise SystemExit(2)

if not isinstance(payload, dict):
    issues.append("report root is not an object")

def list_values(field):
    value = payload.get(field) if isinstance(payload, dict) else None
    if not isinstance(value, list):
        issues.append(field + " missing")
        return []
    normalized = []
    seen = set()
    for index, item in enumerate(value, start=1):
        if not isinstance(item, str):
            issues.append(field + "[" + str(index) + "] is not a string")
            continue
        item = item.strip()
        if not item:
            issues.append(field + "[" + str(index) + "] is blank")
            continue
        if item in seen:
            issues.append(field + " duplicates " + item)
            continue
        seen.add(item)
        normalized.append(item)
    return sorted(normalized)

def require_list_values(field):
    values = list_values(field)
    if not values:
        issues.append(field + " missing values")
    return values

def string_value(field):
    value = payload.get(field) if isinstance(payload, dict) else None
    if not isinstance(value, str) or not value.strip():
        issues.append(field + " missing")
        return ""
    return value.strip()

def datetime_value(field):
    value = string_value(field)
    if not value:
        return None
    parse_value = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(parse_value)
    except ValueError:
        issues.append(field + " not ISO formatted")
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        issues.append(field + " missing timezone")
    elif parsed > datetime.now(parsed.tzinfo):
        issues.append(field + " is in the future")
    return parsed

def uuid_value(field):
    value = string_value(field)
    if not value:
        return ""
    try:
        UUID(value)
    except ValueError:
        issues.append(field + " is not a UUID")
    return value

def positive_int_value(field):
    value = payload.get(field) if isinstance(payload, dict) else None
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        issues.append(field + " must be a positive integer")
        return None
    return value

def validate_top_level_fields(allowed_fields):
    if not isinstance(payload, dict):
        return
    unexpected_fields = sorted(str(field) for field in payload if field not in allowed_fields)
    if unexpected_fields:
        issues.append("unexpected top-level fields: " + ", ".join(unexpected_fields))

def validate_result_rows(required_names):
    results = payload.get("results") if isinstance(payload, dict) else None
    if not isinstance(results, list):
        issues.append("results missing")
        return
    seen = set()
    for index, result in enumerate(results, start=1):
        if not isinstance(result, dict):
            issues.append("results[" + str(index) + "] is not an object")
            continue
        raw_name = result.get("name")
        if not isinstance(raw_name, str) or not raw_name.strip():
            issues.append("results[" + str(index) + "] missing name")
            continue
        name = raw_name.strip()
        unexpected_fields = sorted(str(field) for field in result if field not in allowed_result_fields)
        if unexpected_fields:
            issues.append("result " + name + " unexpected fields: " + ", ".join(unexpected_fields))
        if name in seen:
            issues.append("duplicate result name: " + name)
        seen.add(name)
        if not isinstance(result.get("detail"), str):
            issues.append("result " + name + " detail is not a string")
        if name in required_names and result.get("evidence") is None:
            issues.append("result " + name + " evidence missing")
    missing_result_names = sorted(required_names - seen)
    if missing_result_names:
        issues.append("missing result names: " + ", ".join(missing_result_names))
    unexpected_result_names = sorted(seen - required_names)
    if unexpected_result_names:
        issues.append("unexpected result names: " + ", ".join(unexpected_result_names))

def worker_row_values(field):
    values = payload.get(field) if isinstance(payload, dict) else None
    if not isinstance(values, list):
        issues.append(field + " missing")
        return {{}}
    rows = {{}}
    allowed_worker_statuses = set(("online", "offline", "degraded"))
    for index, row in enumerate(values, start=1):
        row_label = field + "[" + str(index) + "]"
        if not isinstance(row, dict):
            issues.append(row_label + " is not an object")
            continue
        raw_name = row.get("name")
        if not isinstance(raw_name, str):
            issues.append(row_label + " name is not a string")
            continue
        name = raw_name.strip()
        if not name:
            issues.append(row_label + " missing name")
            continue
        named_label = field + "." + name
        unexpected_fields = sorted(str(row_field) for row_field in row if row_field not in allowed_worker_fields)
        if unexpected_fields:
            issues.append(named_label + " unexpected fields: " + ", ".join(unexpected_fields))
        if name in rows:
            issues.append(field + " duplicates " + name)

        raw_worker_id = row.get("id")
        if not isinstance(raw_worker_id, str) or not raw_worker_id.strip():
            issues.append(named_label + " missing id")
        else:
            try:
                UUID(raw_worker_id.strip())
            except ValueError:
                issues.append(named_label + " id is not a UUID")

        raw_status = row.get("status")
        status = raw_status.strip() if isinstance(raw_status, str) else ""
        if not isinstance(raw_status, str):
            issues.append(named_label + " status is not a string")
        elif not status:
            issues.append(named_label + " missing status")
        elif status not in allowed_worker_statuses:
            issues.append(named_label + " invalid status: " + status)

        capabilities = row.get("capabilities")
        normalized_capabilities = set()
        if not isinstance(capabilities, list):
            issues.append(named_label + " missing capabilities")
        else:
            for capability_index, capability in enumerate(capabilities, start=1):
                if not isinstance(capability, str):
                    issues.append(named_label + " capabilities[" + str(capability_index) + "] is not a string")
                    continue
                capability = capability.strip()
                if not capability:
                    issues.append(named_label + " capabilities[" + str(capability_index) + "] is blank")
                    continue
                if capability in normalized_capabilities:
                    issues.append(named_label + " duplicate capability: " + capability)
                normalized_capabilities.add(capability)

        current_job_id = row.get("current_job_id")
        if "current_job_id" not in row:
            issues.append(named_label + " missing current_job_id")
        elif current_job_id is not None:
            if not isinstance(current_job_id, str):
                issues.append(named_label + " current_job_id is not a string")
            elif not current_job_id.strip():
                issues.append(named_label + " current_job_id is blank")
            else:
                try:
                    UUID(current_job_id.strip())
                except ValueError:
                    issues.append(named_label + " current_job_id is not a UUID")

        raw_last_seen = row.get("last_seen")
        if not isinstance(raw_last_seen, str) or not raw_last_seen.strip():
            issues.append(named_label + " last_seen missing")
        else:
            parse_value = raw_last_seen.strip()
            parse_value = parse_value[:-1] + "+00:00" if parse_value.endswith("Z") else parse_value
            try:
                parsed = datetime.fromisoformat(parse_value)
            except ValueError:
                issues.append(named_label + " last_seen not ISO formatted")
            else:
                if parsed.tzinfo is None or parsed.utcoffset() is None:
                    issues.append(named_label + " last_seen missing timezone")

        rows[name] = {{
            "id": raw_worker_id.strip() if isinstance(raw_worker_id, str) else "",
            "status": status,
            "capabilities": normalized_capabilities,
            "current_job_id": current_job_id.strip() if isinstance(current_job_id, str) else current_job_id,
            "last_seen": raw_last_seen.strip() if isinstance(raw_last_seen, str) else "",
        }}
    return rows

def validate_worker_id_consistency(online_rows, offline_rows):
    worker_ids_by_name = {{}}
    names_by_worker_id = {{}}
    for row_set in (online_rows, offline_rows):
        for name, row in row_set.items():
            worker_id = row.get("id")
            if not worker_id:
                continue
            previous_worker_id = worker_ids_by_name.get(name)
            if previous_worker_id and previous_worker_id != worker_id:
                issues.append(
                    "worker rows " + name + " id mismatch between row sets: "
                    + previous_worker_id + ", " + worker_id
                )
            worker_ids_by_name[name] = worker_id
            names_by_worker_id.setdefault(worker_id, set()).add(name)
    for worker_id, names in sorted(names_by_worker_id.items()):
        if len(names) > 1:
            issues.append(
                "worker row id reused by multiple workers: "
                + worker_id + " (" + ", ".join(sorted(names)) + ")"
            )

def validate_worker_rows(observed_models):
    online_rows = worker_row_values("online_workers")
    offline_rows = worker_row_values("offline_workers")
    validate_worker_id_consistency(online_rows, offline_rows)
    expected_worker_set = set(expected_names)
    expected_offline_set = set(expected_offline)

    missing_online = sorted(expected_worker_set - set(online_rows))
    if missing_online:
        issues.append("online worker rows missing expected names: " + ", ".join(missing_online))
    unexpected_online = sorted(set(online_rows) - expected_worker_set)
    if unexpected_online:
        issues.append("online worker rows include unexpected names: " + ", ".join(unexpected_online))

    missing_offline = sorted(expected_offline_set - set(offline_rows))
    if missing_offline:
        issues.append("offline worker rows missing expected names: " + ", ".join(missing_offline))
    unexpected_offline = sorted(set(offline_rows) - expected_offline_set)
    if unexpected_offline:
        issues.append("offline worker rows include unexpected names: " + ", ".join(unexpected_offline))

    for name, row in sorted(online_rows.items()):
        if name in expected_worker_set and row.get("status") != "online":
            issues.append("online worker rows not online: " + name)
        capabilities = row.get("capabilities")
        if name in expected_worker_set and not capabilities:
            issues.append("online worker rows missing capabilities: " + name)
        if expected_different_regen_model and name in expected_worker_set and capabilities:
            missing_capabilities = sorted(observed_models - capabilities)
            if missing_capabilities:
                issues.append(
                    "online worker row " + name + " missing observed model capabilities: "
                    + ", ".join(missing_capabilities)
                )
    validate_result_values("online worker rows", set(online_rows), "workers-online", "worker-row")

    for name, row in sorted(offline_rows.items()):
        if name in expected_offline_set and row.get("status") != "offline":
            issues.append("offline worker rows not offline: " + name)
        capabilities = row.get("capabilities")
        if name in expected_offline_set and not capabilities:
            issues.append("offline worker rows missing capabilities: " + name)
        if expected_different_regen_model and name in expected_offline_set and capabilities:
            missing_capabilities = sorted(observed_models - capabilities)
            if missing_capabilities:
                issues.append(
                    "offline worker row " + name + " missing observed model capabilities: "
                    + ", ".join(missing_capabilities)
                )
    if expected_offline_set or offline_rows:
        validate_result_values("offline worker rows", set(offline_rows), "workers-offline", "worker-row")
    validate_worker_status_payload(online_rows, offline_rows)

def result_row(result_name):
    results = payload.get("results") if isinstance(payload, dict) else None
    if not isinstance(results, list):
        return {{}}
    for result in results:
        if not isinstance(result, dict):
            continue
        raw_name = result.get("name")
        if isinstance(raw_name, str) and raw_name.strip() == result_name:
            return result
    return {{}}

def format_values(values):
    return ", ".join(sorted(values)) or "none"

def result_detail_values(result_name):
    row = result_row(result_name)
    detail = row.get("detail") if isinstance(row, dict) else None
    if not isinstance(detail, str) or not detail.strip():
        issues.append(result_name + " result detail missing")
        return set()
    values = set()
    for raw_item in detail.split(","):
        item = raw_item.strip()
        if not item or item == "none":
            continue
        if item in values:
            issues.append(result_name + " result detail duplicates " + item)
        values.add(item)
    return values

def result_evidence_values(result_name, evidence_kind):
    row = result_row(result_name)
    evidence = row.get("evidence") if isinstance(row, dict) else None
    if not isinstance(evidence, list):
        issues.append(result_name + " result evidence missing")
        return set()
    values = set()
    for index, item in enumerate(evidence, start=1):
        if evidence_kind == "worker-row":
            if not isinstance(item, dict):
                issues.append(result_name + " result evidence[" + str(index) + "] is not an object")
                continue
            raw_value = item.get("name")
            if not isinstance(raw_value, str):
                issues.append(result_name + " result evidence[" + str(index) + "] name is not a string")
                continue
        else:
            if not isinstance(item, str):
                issues.append(result_name + " result evidence[" + str(index) + "] is not a string")
                continue
            raw_value = item
        value = raw_value.strip()
        if not value:
            issues.append(result_name + " result evidence[" + str(index) + "] is blank")
            continue
        if value in values:
            issues.append(result_name + " result evidence duplicates " + value)
        values.add(value)
    return values

def validate_result_values(label, structured_values, result_name, evidence_kind):
    detail_values = result_detail_values(result_name)
    if detail_values != structured_values:
        issues.append(
            label + " result detail mismatch: structured "
            + format_values(structured_values) + "; detail " + format_values(detail_values)
        )
    evidence_values = result_evidence_values(result_name, evidence_kind)
    if evidence_values != structured_values:
        issues.append(
            label + " result evidence mismatch: structured "
            + format_values(structured_values) + "; evidence " + format_values(evidence_values)
        )

def worker_row_field_value(row, field):
    if field == "capabilities":
        capabilities = row.get("capabilities")
        if isinstance(capabilities, set):
            return tuple(sorted(capabilities))
        if isinstance(capabilities, list):
            return tuple(sorted(item.strip() for item in capabilities if isinstance(item, str) and item.strip()))
        return ()
    return row.get(field)

def worker_status_payload_names(evidence, field):
    values = evidence.get(field)
    if not isinstance(values, list):
        issues.append("worker status payload evidence " + field + " missing")
        return set()
    names = set()
    for index, value in enumerate(values, start=1):
        if not isinstance(value, str):
            issues.append("worker status payload evidence " + field + "[" + str(index) + "] is not a string")
            continue
        value = value.strip()
        if not value:
            issues.append("worker status payload evidence " + field + "[" + str(index) + "] is blank")
            continue
        if value in names:
            issues.append("worker status payload evidence " + field + " duplicates " + value)
        names.add(value)
    return names

def validate_worker_status_payload(online_rows, offline_rows):
    result = result_row("worker-status-payload")
    detail = result.get("detail") if isinstance(result, dict) else None
    evidence = result.get("evidence") if isinstance(result, dict) else None
    if not isinstance(evidence, dict):
        issues.append("worker status payload evidence missing")
        return
    allowed_fields = set((
        "busy_count",
        "capabilities",
        "capability_count",
        "degraded_count",
        "degraded_worker_names",
        "offline_count",
        "offline_worker_names",
        "online_count",
        "online_worker_names",
        "worker_count",
        "workers",
    ))
    unexpected_fields = sorted(str(field) for field in evidence if field not in allowed_fields)
    if unexpected_fields:
        issues.append("worker status payload evidence unexpected fields: " + ", ".join(unexpected_fields))

    worker_rows = evidence.get("workers")
    if not isinstance(worker_rows, list):
        issues.append("worker status payload evidence workers missing")
        return
    rows = {{}}
    for index, worker in enumerate(worker_rows, start=1):
        if not isinstance(worker, dict):
            issues.append("worker status payload evidence workers[" + str(index) + "] is not an object")
            continue
        raw_name = worker.get("name")
        if not isinstance(raw_name, str):
            issues.append("worker status payload evidence workers[" + str(index) + "] name is not a string")
            continue
        name = raw_name.strip()
        if not name:
            issues.append("worker status payload evidence workers[" + str(index) + "] missing name")
            continue
        if name in rows:
            issues.append("worker status payload evidence duplicate worker: " + name)
        rows[name] = worker

    expected_online = set(online_rows)
    expected_offline = set(offline_rows)
    online_names = set(name for name, row in rows.items() if row.get("status") == "online")
    offline_names = set(name for name, row in rows.items() if row.get("status") == "offline")
    degraded_names = set(name for name, row in rows.items() if row.get("status") == "degraded")
    if online_names != expected_online:
        issues.append(
            "worker status payload evidence online names mismatch: structured "
            + format_values(expected_online) + "; evidence " + format_values(online_names)
        )
    if offline_names != expected_offline:
        issues.append(
            "worker status payload evidence offline names mismatch: structured "
            + format_values(expected_offline) + "; evidence " + format_values(offline_names)
        )
    if degraded_names:
        issues.append("worker status payload evidence degraded workers present: " + format_values(degraded_names))

    for label, structured_rows in (("online", online_rows), ("offline", offline_rows)):
        for name, structured_row in sorted(structured_rows.items()):
            match = rows.get(name)
            if not isinstance(match, dict):
                issues.append("worker status payload evidence missing " + label + " worker: " + name)
                continue
            for field in ("id", "status", "capabilities", "current_job_id", "last_seen"):
                if worker_row_field_value(structured_row, field) != worker_row_field_value(match, field):
                    issues.append("worker status payload evidence row mismatch for " + name + ": " + field)

    expected_count_values = {{
        "worker_count": len(rows),
        "online_count": len(online_names),
        "offline_count": len(offline_names),
        "degraded_count": len(degraded_names),
        "busy_count": sum(1 for row in rows.values() if row.get("current_job_id")),
    }}
    for field, expected_value in sorted(expected_count_values.items()):
        value = evidence.get(field)
        if not isinstance(value, int) or isinstance(value, bool):
            issues.append("worker status payload evidence " + field + " missing")
        elif value != expected_value:
            issues.append(
                "worker status payload evidence " + field + "=" + str(value)
                + ", want " + str(expected_value)
            )

    capability_values = set()
    for worker in rows.values():
        capability_values.update(worker_row_field_value(worker, "capabilities"))
    if evidence.get("capability_count") != len(capability_values):
        issues.append(
            "worker status payload evidence capability_count="
            + str(evidence.get("capability_count")) + ", want " + str(len(capability_values))
        )
    if worker_status_payload_names(evidence, "online_worker_names") != online_names:
        issues.append("worker status payload evidence online_worker_names mismatch")
    if worker_status_payload_names(evidence, "offline_worker_names") != offline_names:
        issues.append("worker status payload evidence offline_worker_names mismatch")
    if worker_status_payload_names(evidence, "degraded_worker_names") != degraded_names:
        issues.append("worker status payload evidence degraded_worker_names mismatch")
    if isinstance(detail, str):
        if str(expected_count_values["worker_count"]) + " workers" not in detail:
            issues.append("worker status payload result detail does not match worker_count")
        if str(len(capability_values)) + " capabilities" not in detail:
            issues.append("worker status payload result detail does not match capability_count")
        if str(expected_count_values["busy_count"]) + " busy" not in detail:
            issues.append("worker status payload result detail does not match busy_count")

def switch_model_values(label, switch):
    values = {{}}
    for field in ("old_model", "new_model"):
        raw_value = switch.get(field) if isinstance(switch, dict) else None
        if not isinstance(raw_value, str) or not raw_value.strip():
            issues.append("regeneration model switch " + label + " " + field + " missing")
            values[field] = ""
            continue
        values[field] = raw_value.strip()
    unexpected_fields = sorted(str(field) for field in switch if field not in ("old_model", "new_model"))
    if unexpected_fields:
        issues.append("regeneration model switch " + label + " unexpected fields: " + ", ".join(unexpected_fields))
    return values.get("old_model", ""), values.get("new_model", "")

def validate_regeneration_model_switch(observed_models):
    if not expected_different_regen_model:
        return
    switch = payload.get("regeneration_model_switch") if isinstance(payload, dict) else None
    switch_detail = ""
    if not isinstance(switch, dict):
        issues.append("regeneration model switch evidence missing")
    else:
        old_model, new_model = switch_model_values("structured", switch)
        switch_detail = old_model + " -> " + new_model if old_model or new_model else ""
        switch_result = result_row("regeneration-model-switch")
        result_detail = switch_result.get("detail") if isinstance(switch_result, dict) else None
        if isinstance(result_detail, str) and result_detail.strip() and result_detail.strip() != switch_detail:
            issues.append("regeneration model switch result detail mismatch")
        result_evidence = switch_result.get("evidence") if isinstance(switch_result, dict) else None
        if not isinstance(result_evidence, dict):
            issues.append("regeneration model switch result evidence missing")
        else:
            evidence_old_model, evidence_new_model = switch_model_values("result evidence", result_evidence)
            evidence_detail = (
                evidence_old_model + " -> " + evidence_new_model
                if evidence_old_model or evidence_new_model
                else ""
            )
            if evidence_detail != switch_detail:
                issues.append("regeneration model switch result evidence mismatch")
    if " -> " not in switch_detail:
        issues.append("regeneration model switch detail missing")
        return
    old_model, new_model = (part.strip() for part in switch_detail.split(" -> ", 1))
    if not old_model or not new_model:
        issues.append("regeneration model switch detail incomplete")
    elif old_model == new_model:
        issues.append("regeneration model switch used same model: " + old_model)
    else:
        missing_switch_models = sorted(set((old_model, new_model)) - observed_models)
        if missing_switch_models:
            issues.append(
                "regeneration model switch references unobserved model ids: "
                + ", ".join(missing_switch_models)
            )

def validate_structured_report_values():
    expected_worker_set = set(expected_names)
    expected_offline_set = set(expected_offline)
    allowed_worker_set = expected_worker_set | expected_offline_set
    observed_workers = set(list_values("observed_worker_names"))
    generated_workers = set(list_values("generated_worker_names"))
    regenerated_workers = set(list_values("regenerated_worker_names"))
    observed_models = set(require_list_values("observed_model_ids"))
    generated_models = set(require_list_values("generated_model_ids"))
    regenerated_models = set(require_list_values("regenerated_model_ids"))

    missing_observed_workers = sorted(allowed_worker_set - observed_workers)
    if missing_observed_workers:
        issues.append("observed worker names missing expected values: " + ", ".join(missing_observed_workers))
    unexpected_observed_workers = sorted(observed_workers - allowed_worker_set)
    if unexpected_observed_workers:
        issues.append("observed worker names include unexpected values: " + ", ".join(unexpected_observed_workers))

    missing_generated_workers = sorted(expected_worker_set - generated_workers)
    if missing_generated_workers:
        issues.append("generated workers missing expected names: " + ", ".join(missing_generated_workers))
    unexpected_generated_workers = sorted(generated_workers - expected_worker_set)
    if unexpected_generated_workers:
        issues.append("generated workers include unexpected names: " + ", ".join(unexpected_generated_workers))

    missing_regenerated_workers = sorted(expected_worker_set - regenerated_workers)
    if missing_regenerated_workers:
        issues.append("regenerated workers missing expected names: " + ", ".join(missing_regenerated_workers))
    unexpected_regenerated_workers = sorted(regenerated_workers - expected_worker_set)
    if unexpected_regenerated_workers:
        issues.append("regenerated workers include unexpected names: " + ", ".join(unexpected_regenerated_workers))
    validate_result_values("generated workers", generated_workers, "generated-workers", "string")
    validate_result_values("regenerated workers", regenerated_workers, "regenerated-workers", "string")

    model_evidence = generated_models | regenerated_models
    missing_observed_models = sorted(model_evidence - observed_models)
    if missing_observed_models:
        issues.append("observed model ids missing generated values: " + ", ".join(missing_observed_models))
    extra_observed_models = sorted(observed_models - model_evidence)
    if extra_observed_models:
        issues.append("observed model ids include ungenerated values: " + ", ".join(extra_observed_models))
    validate_result_values("generated model ids", generated_models, "generated-models", "string")
    validate_result_values("regenerated model ids", regenerated_models, "regenerated-models", "string")
    if expected_different_regen_model and len(observed_models) < 2:
        issues.append("different-model proof observed only " + str(len(observed_models)) + " model id(s)")
    return observed_models

expected_workers = None
expected_names = []
expected_offline = []
expected_tree = None
if expected_phase == "two-worker":
    expected_workers = 2
    expected_names = [worker_a, worker_b]
    expected_tree = True
elif expected_phase == "failover-one-worker":
    expected_workers = 1
    expected_names = [worker_a]
    expected_offline = [worker_b]
    expected_tree = False
elif expected_phase == "rejoin-two-worker":
    expected_workers = 2
    expected_names = [worker_a, worker_b]
    expected_tree = True
else:
    issues.append("unknown phase " + expected_phase)

allowed_top_level_fields = set((
    "base_url",
    "branching",
    "completed_at",
    "debate_id",
    "depth",
    "error",
    "expected_offline_worker_names",
    "expected_worker_names",
    "expected_workers",
    "generated_model_ids",
    "generated_worker_names",
    "observed_model_ids",
    "observed_worker_names",
    "offline_workers",
    "online_workers",
    "phase",
    "regenerated_model_ids",
    "regenerated_worker_names",
    "regeneration_model_switch",
    "require_different_regen_model",
    "require_expected_workers_in_tree",
    "require_named_https",
    "results",
    "skip_sse_check",
    "skip_web_checks",
    "started_at",
    "status",
    "topic",
    "web_base_url",
))

allowed_result_fields = set((
    "detail",
    "evidence",
    "name",
))

allowed_worker_fields = set((
    "capabilities",
    "current_job_id",
    "id",
    "last_seen",
    "name",
    "status",
))

required_result_names = {{
    "auth-boundaries",
    "create-debate",
    "generated-models",
    "generated-node-metadata",
    "generated-workers",
    "markdown-export",
    "persistence",
    "public-list",
    "regenerate-history",
    "regenerate-request",
    "regenerate-sse-stream",
    "regenerate-synthesis",
    "regenerated-models",
    "regenerated-node-metadata",
    "regenerated-workers",
    "regeneration-model-switch",
    "role-overrides",
    "settings-roundtrip",
    "sse-stream",
    "synthesis",
    "tree-skeleton",
    "tree-skeleton-timing",
    "web-auth-gates",
    "web-auth-surfaces",
    "web-auth-token-flow",
    "web-debate-actions",
    "web-debate-detail",
    "web-home",
    "web-streaming-client",
    "worker-status-payload",
    "workers-online",
    "write-auth-boundaries",
}}
if expected_offline:
    required_result_names.add("workers-offline")

if isinstance(payload, dict):
    validate_top_level_fields(allowed_top_level_fields)
    if payload.get("status") != "passed":
        issues.append("status is not passed")
    if payload.get("error") not in (None, ""):
        issues.append("error is present")
    if payload.get("phase") != expected_phase:
        issues.append("phase metadata mismatch")
    base_url = payload.get("base_url")
    if not isinstance(base_url, str) or not base_url.strip():
        issues.append("base_url missing")
    elif base_url.rstrip("/") != coordinator_url:
        issues.append("base_url does not match coordinator URL")
    web_base_url = payload.get("web_base_url")
    if not isinstance(web_base_url, str) or not web_base_url.strip():
        issues.append("web_base_url missing")
    elif web_base_url.rstrip("/") != coordinator_url:
        issues.append("web_base_url does not match coordinator URL")
    actual_expected_workers = positive_int_value("expected_workers")
    if actual_expected_workers != expected_workers:
        issues.append("expected_workers mismatch")
    if list_values("expected_worker_names") != sorted(expected_names):
        issues.append("expected_worker_names mismatch")
    if list_values("expected_offline_worker_names") != sorted(expected_offline):
        issues.append("expected_offline_worker_names mismatch")
    if payload.get("require_expected_workers_in_tree") is not expected_tree:
        issues.append("worker-tree requirement mismatch")
    if payload.get("require_different_regen_model") is not expected_different_regen_model:
        issues.append("different-model requirement mismatch")
    if payload.get("require_named_https") is not expected_named_https:
        issues.append("named-HTTPS requirement mismatch")
    if payload.get("skip_web_checks") is not False:
        issues.append("skipped web checks")
    if payload.get("skip_sse_check") is not False:
        issues.append("skipped SSE checks")
    started_at = datetime_value("started_at")
    completed_at = datetime_value("completed_at")
    if started_at is not None and completed_at is not None and completed_at <= started_at:
        issues.append("completed_at must be after started_at")
    uuid_value("debate_id")
    string_value("topic")
    positive_int_value("depth")
    positive_int_value("branching")
    validate_result_rows(required_result_names)
    observed_model_values = validate_structured_report_values()
    validate_worker_rows(observed_model_values)
    validate_regeneration_model_switch(observed_model_values)

if issues:
    print(
        "production acceptance " + report_label + " invalid: " + path + ": " + "; ".join(issues),
        file=sys.stderr,
    )
    raise SystemExit(2)
PY
    }}

    validate_strict_acceptance_report() {{
        report_path="$1"
        expected_phase="$2"
        report_label="$3"
        case "$SKIP_STRICT_REPORT_VALIDATION" in
            1|true|yes)
                if [ "$ALLOW_SKIP_STRICT_REPORT_VALIDATION_FOR_REHEARSAL" != "1" ] && [ "$ALLOW_SKIP_STRICT_REPORT_VALIDATION_FOR_REHEARSAL" != "true" ] && [ "$ALLOW_SKIP_STRICT_REPORT_VALIDATION_FOR_REHEARSAL" != "yes" ]; then
                    echo "production acceptance requires strict report validation; set ALLOW_SKIP_STRICT_REPORT_VALIDATION_FOR_REHEARSAL=1 only for a rehearsal run" >&2
                    exit 2
                fi
                return 0
                ;;
        esac
        if [ ! -r "$STRICT_REPORT_VALIDATOR" ]; then
            echo "production acceptance strict report validation requires status_report.py: $STRICT_REPORT_VALIDATOR" >&2
            exit 2
        fi
        if ! "$REPORT_PYTHON" "$STRICT_REPORT_VALIDATOR" \\
            --validate-production-acceptance-report "$report_path" \\
            --validate-production-phase "$expected_phase" \\
            --validate-production-public-url "$COORDINATOR_URL"; then
            echo "production acceptance $report_label failed strict report validation" >&2
            exit 2
        fi
    }}

    validate_report_chronology() {{
        prior_report="$1"
        current_report="$2"
        prior_phase="$3"
        current_phase="$4"
        if [ -z "$prior_report" ]; then
            return 0
        fi
        "$REPORT_PYTHON" - "$prior_report" "$current_report" "$prior_phase" "$current_phase" <<'PY'
import json
import sys
from datetime import datetime

prior_report = sys.argv[1]
current_report = sys.argv[2]
prior_phase = sys.argv[3]
current_phase = sys.argv[4]

def load_payload(path, label):
    try:
        with open(path, encoding="utf-8") as handle:
            payload = json.load(handle)
    except Exception as exc:
        print(
            "production acceptance phase chronology invalid: "
            + label
            + " report unreadable ("
            + type(exc).__name__
            + "): "
            + path,
            file=sys.stderr,
        )
        raise SystemExit(2)
    if not isinstance(payload, dict):
        print(
            "production acceptance phase chronology invalid: "
            + label
            + " report root is not an object: "
            + path,
            file=sys.stderr,
        )
        raise SystemExit(2)
    return payload

def timestamp(payload, label, field):
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        print(
            "production acceptance phase chronology invalid: "
            + label
            + " "
            + field
            + " missing",
            file=sys.stderr,
        )
        raise SystemExit(2)
    parse_value = value.strip()
    if parse_value.endswith("Z"):
        parse_value = parse_value[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(parse_value)
    except ValueError:
        print(
            "production acceptance phase chronology invalid: "
            + label
            + " "
            + field
            + " not ISO formatted",
            file=sys.stderr,
        )
        raise SystemExit(2)
    if parsed.tzinfo is None or parsed.tzinfo.utcoffset(parsed) is None:
        print(
            "production acceptance phase chronology invalid: "
            + label
            + " "
            + field
            + " missing timezone",
            file=sys.stderr,
        )
        raise SystemExit(2)
    return parsed

prior_payload = load_payload(prior_report, prior_phase)
current_payload = load_payload(current_report, current_phase)
prior_completed = timestamp(prior_payload, prior_phase, "completed_at")
current_started = timestamp(current_payload, current_phase, "started_at")
if current_started <= prior_completed:
    print(
        "production acceptance phase chronology invalid: "
        + current_phase
        + " started before or at "
        + prior_phase
        + " completion ("
        + current_started.isoformat()
        + " <= "
        + prior_completed.isoformat()
        + ")",
        file=sys.stderr,
    )
    raise SystemExit(2)
PY
    }}

    PRIOR_ACCEPTANCE_REPORT=""
    PRIOR_ACCEPTANCE_MODE=""
    case "$MODE" in
        failover-one-worker)
            PRIOR_ACCEPTANCE_MODE=two-worker
            PRIOR_ACCEPTANCE_REPORT="$TWO_WORKER_ACCEPTANCE_REPORT"
            ;;
        rejoin-two-worker)
            PRIOR_ACCEPTANCE_MODE=failover-one-worker
            PRIOR_ACCEPTANCE_REPORT="$FAILOVER_ACCEPTANCE_REPORT"
            ;;
    esac
    if [ "$PRIOR_ACCEPTANCE_REPORT" ] && [ ! -s "$PRIOR_ACCEPTANCE_REPORT" ]; then
        echo "production acceptance mode $MODE requires an existing $PRIOR_ACCEPTANCE_MODE report at $PRIOR_ACCEPTANCE_REPORT" >&2
        exit 2
    fi
    if [ "$PRIOR_ACCEPTANCE_REPORT" ]; then
        validate_acceptance_report "$PRIOR_ACCEPTANCE_REPORT" "$PRIOR_ACCEPTANCE_MODE" "prior report" "$ACCEPTANCE_REQUIRE_NAMED_HTTPS" "$REQUIRE_DIFFERENT_REGEN_MODEL"
        validate_strict_acceptance_report "$PRIOR_ACCEPTANCE_REPORT" "$PRIOR_ACCEPTANCE_MODE" "prior report"
    fi

    cd "$ENGINE_DIR"
    if [ "$WORKER_REQUIRED_CAPABILITIES" ]; then
        make verify-worker-visible COORDINATOR_URL="$COORDINATOR_URL" WORKER_NAME="$WORKER_A_NAME" WORKER_VISIBLE_TIMEOUT="$WORKER_STATUS_TIMEOUT" WORKER_REQUIRED_CAPABILITIES="$WORKER_REQUIRED_CAPABILITIES" WORKER_REJECT_NON_PRODUCTION_CAPABILITIES=1
    else
        make verify-worker-visible COORDINATOR_URL="$COORDINATOR_URL" WORKER_NAME="$WORKER_A_NAME" WORKER_VISIBLE_TIMEOUT="$WORKER_STATUS_TIMEOUT" WORKER_REJECT_NON_PRODUCTION_CAPABILITIES=1
    fi
    case "$MODE" in
        two-worker|rejoin-two-worker)
            if [ "$WORKER_REQUIRED_CAPABILITIES" ]; then
                make verify-worker-visible COORDINATOR_URL="$COORDINATOR_URL" WORKER_NAME="$WORKER_B_NAME" WORKER_VISIBLE_TIMEOUT="$WORKER_STATUS_TIMEOUT" WORKER_REQUIRED_CAPABILITIES="$WORKER_REQUIRED_CAPABILITIES" WORKER_REJECT_NON_PRODUCTION_CAPABILITIES=1
            else
                make verify-worker-visible COORDINATOR_URL="$COORDINATOR_URL" WORKER_NAME="$WORKER_B_NAME" WORKER_VISIBLE_TIMEOUT="$WORKER_STATUS_TIMEOUT" WORKER_REJECT_NON_PRODUCTION_CAPABILITIES=1
            fi
            ;;
        failover-one-worker)
            if [ "$WORKER_REQUIRED_CAPABILITIES" ]; then
                make verify-worker-status COORDINATOR_URL="$COORDINATOR_URL" WORKER_NAME="$WORKER_B_NAME" WORKER_EXPECTED_STATUS=offline WORKER_VISIBLE_TIMEOUT="$WORKER_STATUS_TIMEOUT" WORKER_REQUIRE_CAPABILITIES=1 WORKER_REQUIRED_CAPABILITIES="$WORKER_REQUIRED_CAPABILITIES" WORKER_REJECT_NON_PRODUCTION_CAPABILITIES=1
            else
                make verify-worker-status COORDINATOR_URL="$COORDINATOR_URL" WORKER_NAME="$WORKER_B_NAME" WORKER_EXPECTED_STATUS=offline WORKER_VISIBLE_TIMEOUT="$WORKER_STATUS_TIMEOUT" WORKER_REJECT_NON_PRODUCTION_CAPABILITIES=1
            fi
            ;;
    esac
    {user_token_prompt()}
    rm -f "$ACCEPTANCE_REPORT"

    USER_TOKEN="$USER_TOKEN" make acceptance \\
        COORDINATOR_URL="$COORDINATOR_URL" \\
        ACCEPTANCE_PHASE="$MODE" \\
        EXPECTED_WORKERS="$EXPECTED_WORKERS" \\
        EXPECTED_WORKER_NAMES="$EXPECTED_WORKER_NAMES" \\
        EXPECTED_OFFLINE_WORKER_NAMES="$EXPECTED_OFFLINE_WORKER_NAMES" \\
        REQUIRE_WORKERS_IN_TREE="$REQUIRE_WORKERS_IN_TREE" \\
        REQUIRE_DIFFERENT_REGEN_MODEL="$REQUIRE_DIFFERENT_REGEN_MODEL" \\
        ACCEPTANCE_REQUIRE_NAMED_HTTPS="$ACCEPTANCE_REQUIRE_NAMED_HTTPS" \\
        SKIP_WEB_CHECKS=0 \\
        SKIP_SSE_CHECK=0 \\
        ACCEPTANCE_REPORT="$ACCEPTANCE_REPORT"

    validate_acceptance_report "$ACCEPTANCE_REPORT" "$MODE" "current report" "$ACCEPTANCE_REQUIRE_NAMED_HTTPS" "$REQUIRE_DIFFERENT_REGEN_MODEL"
    validate_strict_acceptance_report "$ACCEPTANCE_REPORT" "$MODE" "current report"
    validate_report_chronology "$PRIOR_ACCEPTANCE_REPORT" "$ACCEPTANCE_REPORT" "$PRIOR_ACCEPTANCE_MODE" "$MODE"
    echo "Wrote acceptance report: $ACCEPTANCE_REPORT"
    """


def worker_switch_url_script() -> str:
    return """
    #!/bin/sh
    set -eu

    : "${NEW_COORDINATOR_URL:?set NEW_COORDINATOR_URL to the named Cloudflare coordinator URL}"
    : "${ENGINE_DIR:?set ENGINE_DIR to the dialectical-engine checkout on this Mac}"

    SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
    CONFIG_PATH="${CONFIG_PATH:-$HOME/.dialectical-worker/config.toml}"
    WORKER_NAME="${WORKER_NAME:-adesso-mbp}"
    WORKER_VISIBLE_TIMEOUT="${WORKER_VISIBLE_TIMEOUT:-120}"
    VERIFY_REQUIRED_CAPABILITIES=""
    PUBLIC_ENDPOINT_PYTHON="${PUBLIC_ENDPOINT_PYTHON:-python3}"
    PUBLIC_ENDPOINT_SCRIPT="${PUBLIC_ENDPOINT_SCRIPT:-$SCRIPT_DIR/verify_public_endpoint.py}"
    if [ ! -r "$PUBLIC_ENDPOINT_SCRIPT" ]; then
        PUBLIC_ENDPOINT_SCRIPT="$ENGINE_DIR/scripts/verify_public_endpoint.py"
    fi

    case "$NEW_COORDINATOR_URL" in
        https:*) ;;
        *)
            echo "Worker B URL switch requires an HTTPS named Cloudflare coordinator URL" >&2
            exit 2
            ;;
    esac
    case "$NEW_COORDINATOR_URL" in
        *"://"*) ;;
        *)
            echo "Worker B URL switch requires an HTTPS named Cloudflare coordinator URL" >&2
            exit 2
            ;;
    esac
    case "$NEW_COORDINATOR_URL" in
        *"<"*|*">"*)
            echo "Worker B URL switch requires a real named Cloudflare hostname, not a placeholder" >&2
            exit 2
            ;;
        *localhost*|*127.*|*0.0.0.0*|*"::1"*)
            echo "Worker B URL switch requires a public named Cloudflare hostname, not a local URL" >&2
            exit 2
            ;;
        *trycloudflare.com*)
            echo "Worker B URL switch requires a named Cloudflare hostname, not a trycloudflare.com quick tunnel" >&2
            exit 2
            ;;
    esac

    cd "$ENGINE_DIR"
    "$PUBLIC_ENDPOINT_PYTHON" "$PUBLIC_ENDPOINT_SCRIPT" --base-url "$NEW_COORDINATOR_URL" --require-named-https
    if [ "${ALLOWED_MODELS+x}" ]; then
        VERIFY_REQUIRED_CAPABILITIES="$ALLOWED_MODELS"
        make update-worker-config COORDINATOR_URL="$NEW_COORDINATOR_URL" WORKER_CONFIG="$CONFIG_PATH" ALLOWED_MODELS="$ALLOWED_MODELS" WORKER_REQUIRE_NAMED_HTTPS=1
    else
        make update-worker-config COORDINATOR_URL="$NEW_COORDINATOR_URL" WORKER_CONFIG="$CONFIG_PATH" WORKER_REQUIRE_NAMED_HTTPS=1
    fi

    launchctl unload "$HOME/Library/LaunchAgents/com.dialectical.worker.plist" 2>/dev/null || true
    launchctl load "$HOME/Library/LaunchAgents/com.dialectical.worker.plist"
    if [ "$VERIFY_REQUIRED_CAPABILITIES" ]; then
        make deploy-preflight DEPLOY_ROLE=worker PREFLIGHT_FLAGS="--require-registered-worker --require-installed-services --require-worker-api-keys-for-models $VERIFY_REQUIRED_CAPABILITIES"
        make verify-worker-visible COORDINATOR_URL="$NEW_COORDINATOR_URL" WORKER_NAME="$WORKER_NAME" WORKER_VISIBLE_TIMEOUT="$WORKER_VISIBLE_TIMEOUT" WORKER_REQUIRED_CAPABILITIES="$VERIFY_REQUIRED_CAPABILITIES" WORKER_REJECT_NON_PRODUCTION_CAPABILITIES=1
    else
        make deploy-preflight DEPLOY_ROLE=worker PREFLIGHT_FLAGS="--require-registered-worker --require-installed-services"
        make verify-worker-visible COORDINATOR_URL="$NEW_COORDINATOR_URL" WORKER_NAME="$WORKER_NAME" WORKER_VISIBLE_TIMEOUT="$WORKER_VISIBLE_TIMEOUT" WORKER_REJECT_NON_PRODUCTION_CAPABILITIES=1
    fi
    """


def worker_readme(public_url: str, worker_name: str) -> str:
    return f"""
    # Dialectical Worker B Onboarding

    This bundle registers the adesso MacBook as Worker B against:

    `{public_url}`

    It does not contain tokens. Run it on the adesso MacBook from a terminal
    that can access the `dialectical-engine` checkout.

    ## Usage

    ```sh
    cd /path/to/dialectical-worker-b-onboarding
    ENGINE_DIR='/path/to/dialectical-engine' \\
    ./register_worker_b.sh
    ```

    The install step reads the coordinator user token from `DIALECTICAL_USER_TOKEN`
    or `USER_TOKEN`, or prompts only when a new worker registration is needed.
    Reruns with a matching saved worker config reuse the stored worker token
    without prompting.

    Optional environment variables:

    - `COORDINATOR_URL`: coordinator URL. Defaults to `{public_url}`.
      Registration requires an HTTPS named Cloudflare hostname by default and
      rejects placeholder, local, and `trycloudflare.com` quick-tunnel URLs.
      Set `ALLOW_QUICK_TUNNEL_REGISTRATION=1` only for an explicit provisional
      quick-tunnel registration before the final named hostname exists.
    - `WORKER_NAME`: defaults to `{worker_name}`.
    - `ALLOWED_MODELS`: comma-separated model IDs the worker may advertise.
      Defaults to `codex-gpt-5.5` until Claude/Gemini unattended auth is
      configured. Pass `ALLOWED_MODELS=` to clear the pin and advertise all
      detected healthy adapters.
    - `GEMINI_API_KEY`: optional Google AI Studio API key. When set,
      `gemini-2.5-flash` is available through the Gemini API path, which takes
      precedence over Gemini CLI detection for the same model.
    - `XAI_API_KEY`: optional xAI API key for the Grok API fallback.

    The bundle includes the token-free endpoint verifier used by these helper
    scripts. The script first verifies the coordinator's token-free
    `/api/backends/status` endpoint, then runs `make bootstrap`, registers the worker with
    `make install-worker`, installs the worker launchd service, and then runs
    worker deployment preflight. It also verifies the public coordinator's
    `/api/backends/status` endpoint sees `{worker_name}` online with advertised
    capabilities before finishing. When `ALLOWED_MODELS` is non-empty, the
    visibility check also requires those exact capabilities to be advertised.
    If a real `GEMINI_API_KEY` or `XAI_API_KEY` is present while the script
    runs, `make install-worker` copies it into the installed worker launchd
    service. Placeholder values from `worker-b.env.example` are ignored. Rerun
    registration after changing these API keys so launchd receives the updated
    environment; when the existing worker config already matches this worker
    name and coordinator URL, `make install-worker` reuses the saved worker
    identity instead of requiring a new user-token registration. If
    `ALLOWED_MODELS` is omitted during that rerun, the saved allowlist is
    preserved; pass `ALLOWED_MODELS=` only when you intentionally want to
    clear the pin and advertise all detected healthy adapters.
    If capability detection finds no healthy adapter matching the allowlist,
    registration stops before saving worker config or updating the coordinator.

    ## Final Real-Model Capability Setup

    Before final production acceptance, both workers must advertise at least
    two distinct real, non-mock models. On Worker B, run the helper after the
    named hostname is live and the API key for the second model is available:

    ```sh
    COORDINATOR_URL='https://debate.<your-domain>' \\
    ENGINE_DIR='/path/to/dialectical-engine' \\
    GEMINI_API_KEY='<google-ai-studio-api-key>' \\
    ALLOWED_MODELS=codex-gpt-5.5,gemini-2.5-flash \\
    ./configure_worker_b_real_models.sh
    ```

    The helper rejects placeholder, local, quick-tunnel, mock, duplicate, and
    single-model configurations before invoking `make install-worker`. The
    helper first verifies the coordinator's token-free `/api/backends/status`
    endpoint. The installer reuses the saved worker token when this worker is already
    registered against the same coordinator, or prompts only if a new
    registration is needed. It then reruns `make install-worker` so launchd
    receives the API key, runs worker preflight, and verifies `{worker_name}` is
    visible through the public coordinator with all required capabilities.

    Configure Worker A on the Mac mini with the same final allowlist before
    running production acceptance. If Worker A is already registered against
    the local coordinator, rerunning `make install-worker` with the API key
    present preserves the existing worker token, heartbeats the final
    capabilities, preserves the saved allowlist unless `ALLOWED_MODELS` is
    explicitly set, and refreshes the launchd environment:

    ```sh
    GEMINI_API_KEY='<google-ai-studio-api-key>' \\
    make install-worker COORDINATOR_URL=http://localhost:8000 \\
        WORKER_NAME=mac-mini \\
        ALLOWED_MODELS=codex-gpt-5.5,gemini-2.5-flash
    make verify-worker-visible COORDINATOR_URL='https://debate.<your-domain>' \\
        WORKER_NAME=mac-mini \\
        WORKER_REQUIRED_CAPABILITIES=codex-gpt-5.5,gemini-2.5-flash \\
        WORKER_REJECT_NON_PRODUCTION_CAPABILITIES=1
    ```

    If this URL is a `trycloudflare.com` quick tunnel, switch Worker B to the
    named Cloudflare hostname after the named tunnel is verified:

    ```sh
    NEW_COORDINATOR_URL='https://debate.<your-domain>' \\
    ENGINE_DIR='/path/to/dialectical-engine' \\
    ./switch_worker_b_url.sh
    ```

    This verifies the new coordinator's token-free `/api/backends/status`
    endpoint before changing Worker B config, preserves the registered worker
    token, and does not require the user token again. Set
    `ALLOWED_MODELS=codex-gpt-5.5` in the same command if you
    also need to keep the Worker B model allowlist pinned and capability-checked
    during the switch.
    The switch helper rejects placeholder values, non-HTTPS URLs, and
    `trycloudflare.com` quick-tunnel URLs; it is only for moving Worker B to
    the stable named Cloudflare hostname.
    Omit `ALLOWED_MODELS` to preserve the current allowlist; pass
    `ALLOWED_MODELS=` to clear it and advertise all detected healthy adapters.
    Set `WORKER_NAME` if Worker B was registered with a non-default name.

    ## Production Acceptance

    After Worker B is online and the named hostname is stable, run:

    ```sh
    COORDINATOR_URL='https://debate.<your-domain>' \\
    ENGINE_DIR='/path/to/dialectical-engine' \\
    MODE=two-worker \\
    ./production_acceptance.sh
    ```

    For final production proof, run all three phases from the Mac mini so the
    reports land where strict status reads them. If you run a phase from
    another machine, copy the JSON report to the same `/private/tmp` path on
    the Mac mini before running the next phase or final strict status.

    To prove physical failover, sleep or power off the adesso MacBook, wait at
    least 90 seconds, then run the failover mode from the Mac mini or from a
    machine whose report will be copied back to the Mac mini. This mode waits
    for the Worker B row to be present, `offline`, and still advertising the
    required capabilities in `/api/backends/status` before it starts the
    acceptance run:

    ```sh
    COORDINATOR_URL='https://debate.<your-domain>' \\
    ENGINE_DIR='/path/to/dialectical-engine' \\
    MODE=failover-one-worker \\
    ./production_acceptance.sh
    ```

    Wake Worker B and run the first command again with
    `MODE=rejoin-two-worker`. The two-worker modes wait for both workers to be
    `online` with advertised capabilities before they start acceptance.
    The helper requires the two-worker report before failover mode starts and
    the failover report before rejoin mode starts, so the three production
    reports are captured in order. It also parses that prior report and
    rejects stale evidence unless the report passed, has the expected phase
    metadata, matches the current coordinator URL, kept web/SSE proof enabled,
    and matches the current run's named-HTTPS and different-model proof
    requirements. In a rehearsal sequence, prior reports must use the same
    quick-tunnel and one-model flags as the current phase. After each
    acceptance run, the helper validates the report it just wrote before
    printing success.
    Skipping the strict report validator requires pairing
    `SKIP_STRICT_REPORT_VALIDATION=1` with
    `ALLOW_SKIP_STRICT_REPORT_VALIDATION_FOR_REHEARSAL=1` and is only for
    rehearsal runs. Any quick-tunnel, one-model, or nonstandard report-directory
    rehearsal must set those strict-validation rehearsal flags before the
    helper prompts for the user token, because the final strict validator only
    accepts named-HTTPS, different-model production reports written where
    strict status reads them.
    The helper rejects placeholder, non-HTTPS, and local coordinator URLs. It
    also rejects `trycloudflare.com` quick-tunnel URLs by default and passes
    `ACCEPTANCE_REQUIRE_NAMED_HTTPS=1` into `make acceptance` because final
    production proof must be tied to a stable named hostname. Set
    `ALLOW_QUICK_TUNNEL_ACCEPTANCE=1` only for a provisional quick-tunnel smoke
    run; `make status STATUS_FLAGS=--strict-production` will still reject
    quick-tunnel production reports.
    The standalone helper and consolidated Mac mini final sequence default
    `WORKER_REQUIRED_CAPABILITIES` to `codex-gpt-5.5,gemini-2.5-flash` for final
    different-model proof. Final different-model production acceptance requires
    `WORKER_REQUIRED_CAPABILITIES` to list at least two distinct, real,
    non-placeholder, non-mock model IDs before the helper prompts for the user
    token; override it only if the final real-model pair changes.
    The shipped `worker-b.env.example` uses that final two-model pair, so
    replace the `GEMINI_API_KEY` placeholder before sourcing it for final
    Worker B setup or acceptance. A one-model run is rehearsal-only and must
    explicitly set `REQUIRE_DIFFERENT_REGEN_MODEL=0` with
    `ALLOW_DISABLE_DIFFERENT_REGEN_MODEL_FOR_REHEARSAL=1`, plus
    `SKIP_STRICT_REPORT_VALIDATION=1` with
    `ALLOW_SKIP_STRICT_REPORT_VALIDATION_FOR_REHEARSAL=1`.

    Each acceptance run verifies the authenticated settings API, including
    per-model monthly spend/cap fields and a temporary per-model cap
    round-trip that restores the original cap map.
    It also verifies public/auth-gated web routes, token prompts, auth token
    storage/validation/header source contracts, and post-unlock `/new`,
    `/settings`, and `/admin/workers` source surfaces from the checkout. Debate
    detail action controls are checked for unlock, regenerate, generation
    history, archived-generation display, API wiring, refresh, and auth
    rejection handling. Browser SSE streaming is checked for EventSource
    subscription, node/synthesis token rendering, reconnect, completion
    refreshes, and model/worker metadata color markers. Reports also capture
    worker status rows with timezone-aware `last_seen`, timezone-aware
    public-list/create/synthesis/history timestamps, observed worker names,
    observed model IDs, result detail/evidence, and the exact regeneration
    model switch tied to archived/active generation history so the final gate
    can reject mock/local or contradictory evidence.

    `REQUIRE_DIFFERENT_REGEN_MODEL=1` is the default because final production
    proof requires a real model switch. Setting it to `0` also requires
    `ALLOW_DISABLE_DIFFERENT_REGEN_MODEL_FOR_REHEARSAL=1` and is only for a
    rehearsal run while a second real model is still being configured.
    Set `WORKER_STATUS_TIMEOUT` to override the default 180 second worker
    online/offline wait.

    Each run writes a JSON report to
    `/private/tmp/dialectical-acceptance-$MODE.json` unless
    `ACCEPTANCE_REPORT` or `ACCEPTANCE_REPORT_DIR` is set.
    Final strict status reads these production acceptance reports from
    `/private/tmp` on the Mac mini. Nonstandard report directories require
    `ALLOW_NONSTANDARD_ACCEPTANCE_REPORT_DIR=1`,
    `SKIP_STRICT_REPORT_VALIDATION=1`, and
    `ALLOW_SKIP_STRICT_REPORT_VALIDATION_FOR_REHEARSAL=1`, and are rehearsal-only.
    """


def build_worker_bundle(output_dir: Path, public_url: str, worker_name: str) -> Path:
    with tempfile.TemporaryDirectory(prefix="dialectical-worker-b-bundle-") as tmp:
        root = Path(tmp) / "dialectical-worker-b-onboarding"
        write(root / "README.md", worker_readme(public_url, worker_name))
        write(root / "worker-b.env.example", worker_env_example(public_url, worker_name))
        write(
            root / "register_worker_b.sh",
            worker_register_script(public_url, worker_name),
            stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR | stat.S_IRGRP | stat.S_IROTH,
        )
        write(
            root / "production_acceptance.sh",
            production_acceptance_script(public_url, worker_name),
            stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR | stat.S_IRGRP | stat.S_IROTH,
        )
        write(
            root / "configure_worker_b_real_models.sh",
            worker_real_models_script(public_url, worker_name),
            stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR | stat.S_IRGRP | stat.S_IROTH,
        )
        write(
            root / "switch_worker_b_url.sh",
            worker_switch_url_script(),
            stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR | stat.S_IRGRP | stat.S_IROTH,
        )
        verifier = ROOT / "scripts" / "verify_public_endpoint.py"
        shutil.copy2(verifier, root / "verify_public_endpoint.py")
        (root / "verify_public_endpoint.py").chmod(
            stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR | stat.S_IRGRP | stat.S_IROTH
        )
        destination = output_dir / "dialectical-worker-b-onboarding.tgz"
        tar_directory(root, destination)
        return destination


def named_tunnel_readme() -> str:
    return """
    # Dialectical Named Cloudflare Tunnel Template

    This template replaces the temporary `trycloudflare.com` quick tunnel with
    a stable named tunnel and hostname.

    Fill these values before use:

    - `<tunnel-name>`: Cloudflare tunnel name, usually `dialectical`.
    - `<public-hostname>`: hostname such as `debate.example.com`.
    - `<credentials-file>`: optional path to the tunnel credentials JSON created
      by `cloudflared tunnel create`. This file must already exist before you run
      `make install-tunnel`, unless `~/.cloudflared` contains exactly one tunnel
      credentials JSON for the installer to auto-detect.

    `make install-tunnel` validates the tunnel name, validates that the
    hostname is a DNS name, and rejects `trycloudflare.com` quick tunnel hostnames.
    It also validates the credentials path, verifies that the credentials JSON
    contains `AccountTag`, UUID-shaped `TunnelID`, and `TunnelSecret`, and requires
    `cloudflared` on `PATH` before writing
    `~/.cloudflared/config.yml`, routing DNS, or loading launchd. If the
    credentials path is still a placeholder, the hostname is invalid, the file
    is missing or malformed, or `cloudflared` is unavailable, it exits before changing
    the installed tunnel config. After the named tunnel is verified, use
    `make stop-quick-tunnel` to unload the temporary quick-tunnel launchd
    service.

    ## Preferred Setup

    From the `dialectical-engine` checkout on the Mac mini:

    ```sh
    make setup-named-tunnel TUNNEL_NAME=dialectical TUNNEL_HOSTNAME=<public-hostname>
    ```

    Use `make setup-named-tunnel` for the login, create, install, preflight,
    endpoint-check, and quick-tunnel retirement sequence. The setup target runs
    `cloudflared tunnel login` if needed, runs
    `cloudflared tunnel create` when credentials do not exist, installs the
    named tunnel, then runs deploy preflight, endpoint status, and
    `make handoff-bundles PUBLIC_URL=https://<public-hostname>` so Worker B and
    final handoff files immediately carry the named URL. By default the Makefile
    target passes `--stop-quick-after-verified`, so it unloads the temporary
    quick-tunnel service only after endpoint status has verified the named
    hostname. Set `STOP_QUICK_TUNNEL_AFTER_VERIFY=0` only when you intentionally
    need to keep the provisional quick tunnel alive. If more than one
    credentials JSON exists in `~/.cloudflared`, pass
    `CLOUDFLARED_CREDENTIALS=<credentials-file>`. Pass
    `SETUP_NAMED_TUNNEL_FLAGS=--skip-handoff` only when you intentionally want
    to skip refreshing the handoff archives. If `--skip-status` or
    `--skip-preflight` is used, the helper refuses to refresh handoff bundles
    unless `--allow-unverified-handoff` is also set, and it refuses to stop the
    quick tunnel because the named endpoint and launchd preflight have not both
    been verified.

    Verify:

    ```sh
    curl -fsS https://<public-hostname>/api/backends/status
    curl -fsS https://<public-hostname>/openapi.json
    ```

    If you opted out of automatic quick-tunnel retirement, stop it after the
    named tunnel is verified:

    ```sh
    make stop-quick-tunnel
    ```

    On the adesso MacBook, switch Worker B from the quick tunnel URL to the
    named hostname with the Worker B bundle helper:

    ```sh
    cd /path/to/dialectical-worker-b-onboarding
    NEW_COORDINATOR_URL=https://<public-hostname> \\
    ENGINE_DIR=/path/to/dialectical-engine \\
    ./switch_worker_b_url.sh
    ```

    Then use `production_acceptance.sh` from the Worker B bundle to verify the
    two-worker, one-worker failover, and rejoin phases in that order; the
    helper requires the prior phase report before failover and rejoin modes.
    Regenerate handoff bundles with the named public URL, then run
    `make status STATUS_FLAGS=--strict-production` as the final gate.
    """


def build_named_tunnel_bundle(output_dir: Path) -> Path:
    with tempfile.TemporaryDirectory(prefix="dialectical-named-tunnel-bundle-") as tmp:
        root = Path(tmp) / "dialectical-cloudflare-named-tunnel-template"
        write(root / "README.md", named_tunnel_readme())
        shutil.copyfile(ROOT / "deploy" / "cloudflared.config.yml", root / "cloudflared.config.yml")
        shutil.copyfile(ROOT / "deploy" / "launchd" / "cloudflared.plist", root / "com.dialectical.cloudflared.plist.template")
        destination = output_dir / "dialectical-cloudflare-named-tunnel-template.tgz"
        tar_directory(root, destination)
        return destination


def final_production_check_script(public_url: str) -> str:
    return f"""
    #!/bin/sh
    set -eu

    : "${{ENGINE_DIR:?set ENGINE_DIR to the dialectical-engine checkout on the Mac mini}}"

    SCRIPT_DIR="$(CDPATH= cd "$(dirname "$0")" && pwd)"
    CLOUDFLARED_CONFIG="${{CLOUDFLARED_CONFIG:-$HOME/.cloudflared/config.yml}}"
    CONFIG_PUBLIC_URL=""
    if [ -r "$CLOUDFLARED_CONFIG" ]; then
        CONFIG_HOSTNAME="$(awk '
            /^[[:space:]]*-[[:space:]]*hostname:[[:space:]]*/ {{
                value=$0
                sub(/^[[:space:]]*-[[:space:]]*hostname:[[:space:]]*/, "", value)
                sub(/[[:space:]]*#.*/, "", value)
                gsub(/"/, "", value)
                gsub(/^[[:space:]]+|[[:space:]]+$/, "", value)
                if (value != "" && value !~ /[<>]/ && value !~ /trycloudflare[.]com$/ && value !~ /^localhost$/ && value !~ /^127[.]/ && value !~ /^0[.]0[.]0[.]0$/ && value !~ /:/) {{
                    print value
                    exit
                }}
            }}
        ' "$CLOUDFLARED_CONFIG")"
        if [ "$CONFIG_HOSTNAME" ]; then
            CONFIG_PUBLIC_URL="https://$CONFIG_HOSTNAME"
        fi
    fi
    if [ -z "$CONFIG_PUBLIC_URL" ]; then
        echo "final production check requires an installed named Cloudflare tunnel config before refreshing proof" >&2
        echo "run: make setup-named-tunnel TUNNEL_NAME=dialectical TUNNEL_HOSTNAME=<public-hostname>" >&2
        exit 2
    fi

    COORDINATOR_URL="${{COORDINATOR_URL:-${{CONFIG_PUBLIC_URL:-{public_url}}}}}"
    PUBLIC_URL="${{PUBLIC_URL:-$COORDINATOR_URL}}"
    if [ "$CONFIG_PUBLIC_URL" ]; then
        if [ "$COORDINATOR_URL" != "$CONFIG_PUBLIC_URL" ]; then
            echo "final production check requires COORDINATOR_URL to match installed named Cloudflare tunnel config: $CONFIG_PUBLIC_URL" >&2
            exit 2
        fi
        if [ "$PUBLIC_URL" != "$CONFIG_PUBLIC_URL" ]; then
            echo "final production check requires PUBLIC_URL to match installed named Cloudflare tunnel config: $CONFIG_PUBLIC_URL" >&2
            exit 2
        fi
    fi
    WORKER_REQUIRED_CAPABILITIES="${{WORKER_REQUIRED_CAPABILITIES:-${{ALLOWED_MODELS:-codex-gpt-5.5,gemini-2.5-flash}}}}"
    export WORKER_REQUIRED_CAPABILITIES
    PREFLIGHT_FLAGS="${{PREFLIGHT_FLAGS:---require-installed-services --require-registered-worker --require-worker-api-keys-for-models $WORKER_REQUIRED_CAPABILITIES}}"
    REFRESH_LOCAL_PROOF="${{REFRESH_LOCAL_PROOF:-1}}"
    ALLOW_SKIP_LOCAL_PROOF_FOR_REHEARSAL="${{ALLOW_SKIP_LOCAL_PROOF_FOR_REHEARSAL:-0}}"
    REQUIRE_PRODUCTION_ACCEPTANCE_REPORTS="${{REQUIRE_PRODUCTION_ACCEPTANCE_REPORTS:-1}}"
    ALLOW_SKIP_PRODUCTION_REPORTS_FOR_REHEARSAL="${{ALLOW_SKIP_PRODUCTION_REPORTS_FOR_REHEARSAL:-0}}"
    ACCEPTANCE_REPORT_DIR="${{ACCEPTANCE_REPORT_DIR:-/private/tmp}}"
    ALLOW_NONSTANDARD_ACCEPTANCE_REPORT_DIR="${{ALLOW_NONSTANDARD_ACCEPTANCE_REPORT_DIR:-0}}"
    NONSTANDARD_REPORT_REHEARSAL=0
    REPORT_PYTHON="${{REPORT_PYTHON:-python3}}"
    STATUS_REPORT="${{STATUS_REPORT:-$SCRIPT_DIR/runtime-status-report.py}}"

    REQUIRED_CAPABILITY_COUNT=0
    SEEN_REQUIRED_CAPABILITIES=,
    old_ifs="$IFS"
    IFS=,
    for capability in $WORKER_REQUIRED_CAPABILITIES; do
        capability="$(printf '%s' "$capability" | sed 's/^[[:space:]]*//; s/[[:space:]]*$//')"
        case "$capability" in
            "")
                echo "final production check requires non-empty model IDs in WORKER_REQUIRED_CAPABILITIES" >&2
                exit 2
                ;;
            *"<"*|*">"*|*placeholder*)
                echo "final production check requires real model IDs in WORKER_REQUIRED_CAPABILITIES, not placeholders" >&2
                exit 2
                ;;
            mock-local|mock-*|*mock-*)
                echo "final production check requires real model IDs in WORKER_REQUIRED_CAPABILITIES, not mock model IDs" >&2
                exit 2
                ;;
            *)
                case "$SEEN_REQUIRED_CAPABILITIES" in
                    *",$capability,"*)
                        echo "final production check requires distinct model IDs in WORKER_REQUIRED_CAPABILITIES, not duplicate model IDs" >&2
                        exit 2
                        ;;
                esac
                SEEN_REQUIRED_CAPABILITIES="${{SEEN_REQUIRED_CAPABILITIES}}$capability,"
                REQUIRED_CAPABILITY_COUNT=$((REQUIRED_CAPABILITY_COUNT + 1))
                ;;
        esac
    done
    IFS="$old_ifs"
    if [ "$REQUIRED_CAPABILITY_COUNT" -lt 2 ]; then
        echo "final production check requires WORKER_REQUIRED_CAPABILITIES to list at least two distinct real model IDs" >&2
        exit 2
    fi

    case "$ACCEPTANCE_REPORT_DIR" in
        /private/tmp|/private/tmp/) ;;
        *)
            if [ "$ALLOW_NONSTANDARD_ACCEPTANCE_REPORT_DIR" != "1" ] && [ "$ALLOW_NONSTANDARD_ACCEPTANCE_REPORT_DIR" != "true" ] && [ "$ALLOW_NONSTANDARD_ACCEPTANCE_REPORT_DIR" != "yes" ]; then
                echo "final production check reads production acceptance reports from /private/tmp where strict status reads them; set ALLOW_NONSTANDARD_ACCEPTANCE_REPORT_DIR=1 only for a rehearsal run" >&2
                exit 2
            fi
            NONSTANDARD_REPORT_REHEARSAL=1
            ;;
    esac

    if [ "$NONSTANDARD_REPORT_REHEARSAL" = "1" ]; then
        case "$REQUIRE_PRODUCTION_ACCEPTANCE_REPORTS" in
            0|false|no) ;;
            *)
                echo "final production check nonstandard report directory is rehearsal-only; set REQUIRE_PRODUCTION_ACCEPTANCE_REPORTS=0 with ALLOW_SKIP_PRODUCTION_REPORTS_FOR_REHEARSAL=1 before refreshing proof" >&2
                exit 2
                ;;
        esac
        if [ "$ALLOW_SKIP_PRODUCTION_REPORTS_FOR_REHEARSAL" != "1" ] && [ "$ALLOW_SKIP_PRODUCTION_REPORTS_FOR_REHEARSAL" != "true" ] && [ "$ALLOW_SKIP_PRODUCTION_REPORTS_FOR_REHEARSAL" != "yes" ]; then
            echo "final production check nonstandard report directory is rehearsal-only; set ALLOW_SKIP_PRODUCTION_REPORTS_FOR_REHEARSAL=1 before refreshing proof" >&2
            exit 2
        fi
    fi

    cd "$ENGINE_DIR"

    case "$REQUIRE_PRODUCTION_ACCEPTANCE_REPORTS" in
        0|false|no)
            if [ "$ALLOW_SKIP_PRODUCTION_REPORTS_FOR_REHEARSAL" != "1" ] && [ "$ALLOW_SKIP_PRODUCTION_REPORTS_FOR_REHEARSAL" != "true" ] && [ "$ALLOW_SKIP_PRODUCTION_REPORTS_FOR_REHEARSAL" != "yes" ]; then
                echo "final production check requires production acceptance reports before refreshing proof; set ALLOW_SKIP_PRODUCTION_REPORTS_FOR_REHEARSAL=1 only for a rehearsal run" >&2
                exit 2
            fi
            ;;
        *)
            if ! command -v "$REPORT_PYTHON" >/dev/null 2>&1 && [ ! -x "$REPORT_PYTHON" ]; then
                echo "final production check requires python for report validation: $REPORT_PYTHON" >&2
                exit 2
            fi
            if [ ! -r "$STATUS_REPORT" ]; then
                echo "final production check requires status_report.py for report validation: $STATUS_REPORT" >&2
                exit 2
            fi
            REPORT_VALIDATION_FAILED=0
            for report_name in two-worker failover-one-worker rejoin-two-worker; do
                report_path="$ACCEPTANCE_REPORT_DIR/dialectical-acceptance-$report_name.json"
                if [ ! -s "$report_path" ]; then
                    echo "final production check requires production acceptance report before refreshing proof: $report_path" >&2
                    REPORT_VALIDATION_FAILED=1
                    continue
                fi
                if ! "$REPORT_PYTHON" "$STATUS_REPORT" \
                    --validate-production-acceptance-report "$report_path" \
                    --validate-production-phase "$report_name" \
                    --validate-production-public-url "$PUBLIC_URL"; then
                    echo "final production check requires current production acceptance report before refreshing proof: $report_path" >&2
                    REPORT_VALIDATION_FAILED=1
                fi
            done
            if [ "$REPORT_VALIDATION_FAILED" != "0" ]; then
                echo "final production check requires all production acceptance reports before refreshing proof" >&2
                echo "run: ENGINE_DIR=$ENGINE_DIR ./production_acceptance_sequence.sh" >&2
                exit 2
            fi
            ;;
    esac

    make install-status-helper
    make deploy-preflight DEPLOY_ROLE=both PREFLIGHT_FLAGS="$PREFLIGHT_FLAGS"
    make test
    case "$REFRESH_LOCAL_PROOF" in
        0|false|no)
            if [ "$ALLOW_SKIP_LOCAL_PROOF_FOR_REHEARSAL" != "1" ] && [ "$ALLOW_SKIP_LOCAL_PROOF_FOR_REHEARSAL" != "true" ] && [ "$ALLOW_SKIP_LOCAL_PROOF_FOR_REHEARSAL" != "yes" ]; then
                echo "final production check requires local proof refresh; set ALLOW_SKIP_LOCAL_PROOF_FOR_REHEARSAL=1 only for a rehearsal run" >&2
                exit 2
            fi
            ;;
        *)
            make dev-smoke
            make local-cluster-check
            ;;
    esac
    make handoff-bundles PUBLIC_URL="$PUBLIC_URL"
    make status STATUS_FLAGS=--check-endpoints
    make status STATUS_FLAGS=--strict-production
    """


def worker_a_real_models_script(public_url: str) -> str:
    return f"""
    #!/bin/sh
    set -eu

    : "${{ENGINE_DIR:?set ENGINE_DIR to the dialectical-engine checkout on the Mac mini}}"

    WORKER_NAME="${{WORKER_NAME:-mac-mini}}"
    LOCAL_COORDINATOR_URL="${{LOCAL_COORDINATOR_URL:-http://localhost:8000}}"
    WORKER_VISIBLE_TIMEOUT="${{WORKER_VISIBLE_TIMEOUT:-180}}"
    ALLOWED_MODELS="${{ALLOWED_MODELS:-${{REAL_MODEL_CAPABILITIES:-codex-gpt-5.5,gemini-2.5-flash}}}}"
    RUN_BOOTSTRAP="${{RUN_BOOTSTRAP:-0}}"
    CLOUDFLARED_CONFIG="${{CLOUDFLARED_CONFIG:-$HOME/.cloudflared/config.yml}}"
    RUN_NAMED_TUNNEL_PREFLIGHT="${{RUN_NAMED_TUNNEL_PREFLIGHT:-1}}"
    ALLOW_SKIP_NAMED_TUNNEL_PREFLIGHT_FOR_REHEARSAL="${{ALLOW_SKIP_NAMED_TUNNEL_PREFLIGHT_FOR_REHEARSAL:-0}}"
    NAMED_TUNNEL_PREFLIGHT_FLAGS="${{NAMED_TUNNEL_PREFLIGHT_FLAGS:---require-installed-services}}"

    CONFIG_PUBLIC_URL=""
    if [ -r "$CLOUDFLARED_CONFIG" ]; then
        CONFIG_HOSTNAME="$(awk '
            /^[[:space:]]*-[[:space:]]*hostname:[[:space:]]*/ {{
                value=$0
                sub(/^[[:space:]]*-[[:space:]]*hostname:[[:space:]]*/, "", value)
                sub(/[[:space:]]*#.*/, "", value)
                gsub(/"/, "", value)
                gsub(/^[[:space:]]+|[[:space:]]+$/, "", value)
                if (value != "" && value !~ /[<>]/ && value !~ /trycloudflare[.]com$/ && value !~ /^localhost$/ && value !~ /^127[.]/ && value !~ /^0[.]0[.]0[.]0$/ && value !~ /:/) {{
                    print value
                    exit
                }}
            }}
        ' "$CLOUDFLARED_CONFIG")"
        if [ "$CONFIG_HOSTNAME" ]; then
            CONFIG_PUBLIC_URL="https://$CONFIG_HOSTNAME"
        fi
    fi
    if [ -z "$CONFIG_PUBLIC_URL" ]; then
        echo "Worker A real-model setup requires an installed named Cloudflare tunnel config before changing Worker A" >&2
        echo "run: make setup-named-tunnel TUNNEL_NAME=dialectical TUNNEL_HOSTNAME=<public-hostname>" >&2
        exit 2
    fi
    PUBLIC_COORDINATOR_URL="${{PUBLIC_COORDINATOR_URL:-${{CONFIG_PUBLIC_URL:-{public_url}}}}}"
    if [ "$CONFIG_PUBLIC_URL" ] && [ "$PUBLIC_COORDINATOR_URL" != "$CONFIG_PUBLIC_URL" ]; then
        echo "Worker A real-model setup requires PUBLIC_COORDINATOR_URL to match installed named Cloudflare tunnel config: $CONFIG_PUBLIC_URL" >&2
        exit 2
    fi

    case "$LOCAL_COORDINATOR_URL" in
        http://localhost:*|http://127.*|http://0.0.0.0:*) ;;
        *)
            echo "Worker A real-model setup requires LOCAL_COORDINATOR_URL to be the local Mac mini coordinator origin" >&2
            exit 2
            ;;
    esac
    case "$PUBLIC_COORDINATOR_URL" in
        https:*) ;;
        *)
            echo "Worker A real-model setup requires an HTTPS named Cloudflare public coordinator URL" >&2
            exit 2
            ;;
    esac
    case "$PUBLIC_COORDINATOR_URL" in
        *"://"*) ;;
        *)
            echo "Worker A real-model setup requires an HTTPS named Cloudflare public coordinator URL" >&2
            exit 2
            ;;
    esac
    case "$PUBLIC_COORDINATOR_URL" in
        *"<"*|*">"*)
            echo "Worker A real-model setup requires a real named Cloudflare hostname, not a placeholder" >&2
            exit 2
            ;;
        *localhost*|*127.*|*0.0.0.0*|*"::1"*)
            echo "Worker A real-model setup requires a public named Cloudflare hostname, not a local URL" >&2
            exit 2
            ;;
        *trycloudflare.com*)
            echo "Worker A real-model setup requires a named Cloudflare hostname, not a trycloudflare.com quick tunnel" >&2
            exit 2
            ;;
    esac

    REQUIRED_CAPABILITY_COUNT=0
    SEEN_REQUIRED_CAPABILITIES=,
    NEEDS_GEMINI_API_KEY=0
    NEEDS_XAI_API_KEY=0
    old_ifs="$IFS"
    IFS=,
    for capability in $ALLOWED_MODELS; do
        capability="$(printf '%s' "$capability" | sed 's/^[[:space:]]*//; s/[[:space:]]*$//')"
        case "$capability" in
            "")
                echo "Worker A real-model setup requires non-empty model IDs in ALLOWED_MODELS" >&2
                exit 2
                ;;
            *"<"*|*">"*|*placeholder*)
                echo "Worker A real-model setup requires real model IDs in ALLOWED_MODELS, not placeholders" >&2
                exit 2
                ;;
            mock-local|mock-*|*mock-*)
                echo "Worker A real-model setup requires real model IDs in ALLOWED_MODELS, not mock model IDs" >&2
                exit 2
                ;;
            *)
                case "$SEEN_REQUIRED_CAPABILITIES" in
                    *",$capability,"*)
                        echo "Worker A real-model setup requires distinct model IDs in ALLOWED_MODELS, not duplicate model IDs" >&2
                        exit 2
                        ;;
                esac
                case "$capability" in
                    gemini-2.5-flash) NEEDS_GEMINI_API_KEY=1 ;;
                    grok-4) NEEDS_XAI_API_KEY=1 ;;
                esac
                SEEN_REQUIRED_CAPABILITIES="${{SEEN_REQUIRED_CAPABILITIES}}$capability,"
                REQUIRED_CAPABILITY_COUNT=$((REQUIRED_CAPABILITY_COUNT + 1))
                ;;
        esac
    done
    IFS="$old_ifs"
    if [ "$REQUIRED_CAPABILITY_COUNT" -lt 2 ]; then
        echo "Worker A real-model setup requires ALLOWED_MODELS to list at least two distinct real model IDs" >&2
        exit 2
    fi

    GEMINI_API_KEY_FOR_INSTALL=""
    case "${{GEMINI_API_KEY:-}}" in
        ""|*"<"*|*">"*) unset GEMINI_API_KEY ;;
        *)
            GEMINI_API_KEY_FOR_INSTALL="$GEMINI_API_KEY"
            unset GEMINI_API_KEY
            ;;
    esac
    XAI_API_KEY_FOR_INSTALL=""
    case "${{XAI_API_KEY:-}}" in
        ""|*"<"*|*">"*) unset XAI_API_KEY ;;
        *)
            XAI_API_KEY_FOR_INSTALL="$XAI_API_KEY"
            unset XAI_API_KEY
            ;;
    esac
    if [ "$NEEDS_GEMINI_API_KEY" = "1" ] && [ -z "$GEMINI_API_KEY_FOR_INSTALL" ]; then
        echo "Worker A real-model setup requires GEMINI_API_KEY when ALLOWED_MODELS includes gemini-2.5-flash" >&2
        exit 2
    fi
    if [ "$NEEDS_XAI_API_KEY" = "1" ] && [ -z "$XAI_API_KEY_FOR_INSTALL" ]; then
        echo "Worker A real-model setup requires XAI_API_KEY when ALLOWED_MODELS includes grok-4" >&2
        exit 2
    fi

    export ALLOWED_MODELS
    export DIALECTICAL_ALLOWED_MODELS="$ALLOWED_MODELS"

    cd "$ENGINE_DIR"
    case "$RUN_BOOTSTRAP" in
        1|true|yes)
            make bootstrap
            ;;
    esac
    case "$RUN_NAMED_TUNNEL_PREFLIGHT" in
        0|false|no)
            if [ "$ALLOW_SKIP_NAMED_TUNNEL_PREFLIGHT_FOR_REHEARSAL" != "1" ] && [ "$ALLOW_SKIP_NAMED_TUNNEL_PREFLIGHT_FOR_REHEARSAL" != "true" ] && [ "$ALLOW_SKIP_NAMED_TUNNEL_PREFLIGHT_FOR_REHEARSAL" != "yes" ]; then
                echo "Worker A real-model setup requires named tunnel deploy preflight before changing Worker A; set ALLOW_SKIP_NAMED_TUNNEL_PREFLIGHT_FOR_REHEARSAL=1 only for a rehearsal run" >&2
                exit 2
            fi
            ;;
        *)
            make deploy-preflight DEPLOY_ROLE=mac-mini PREFLIGHT_FLAGS="$NAMED_TUNNEL_PREFLIGHT_FLAGS"
            ;;
    esac
    {optional_user_token_for_install()}
    DIALECTICAL_USER_TOKEN="$USER_TOKEN" GEMINI_API_KEY="$GEMINI_API_KEY_FOR_INSTALL" XAI_API_KEY="$XAI_API_KEY_FOR_INSTALL" make install-worker COORDINATOR_URL="$LOCAL_COORDINATOR_URL" WORKER_NAME="$WORKER_NAME" ALLOWED_MODELS="$ALLOWED_MODELS"
    make deploy-preflight DEPLOY_ROLE=worker PREFLIGHT_FLAGS="--require-registered-worker --require-installed-services --require-worker-api-keys-for-models $ALLOWED_MODELS"
    make verify-worker-visible COORDINATOR_URL="$PUBLIC_COORDINATOR_URL" WORKER_NAME="$WORKER_NAME" WORKER_VISIBLE_TIMEOUT="$WORKER_VISIBLE_TIMEOUT" WORKER_REQUIRED_CAPABILITIES="$ALLOWED_MODELS" WORKER_REJECT_NON_PRODUCTION_CAPABILITIES=1
    echo "Worker A advertises required real-model capabilities through $PUBLIC_COORDINATOR_URL: $ALLOWED_MODELS"
    """


def production_readiness_script(public_url: str) -> str:
    return f"""
    #!/bin/sh
    set -eu

    : "${{ENGINE_DIR:?set ENGINE_DIR to the dialectical-engine checkout on the Mac mini}}"

    WORKER_A_NAME="${{WORKER_A_NAME:-mac-mini}}"
    WORKER_B_NAME="${{WORKER_B_NAME:-adesso-mbp}}"
    WORKER_VISIBLE_TIMEOUT="${{WORKER_VISIBLE_TIMEOUT:-180}}"
    WORKER_REQUIRED_CAPABILITIES="${{WORKER_REQUIRED_CAPABILITIES:-${{ALLOWED_MODELS:-codex-gpt-5.5,gemini-2.5-flash}}}}"
    export WORKER_REQUIRED_CAPABILITIES
    RUN_PREFLIGHT="${{RUN_PREFLIGHT:-1}}"
    ALLOW_SKIP_PREFLIGHT_FOR_REHEARSAL="${{ALLOW_SKIP_PREFLIGHT_FOR_REHEARSAL:-0}}"
    PREFLIGHT_FLAGS="${{PREFLIGHT_FLAGS:---require-installed-services --require-registered-worker --require-worker-api-keys-for-models $WORKER_REQUIRED_CAPABILITIES}}"
    RUN_ENDPOINT_STATUS="${{RUN_ENDPOINT_STATUS:-1}}"
    ALLOW_SKIP_ENDPOINT_STATUS_FOR_REHEARSAL="${{ALLOW_SKIP_ENDPOINT_STATUS_FOR_REHEARSAL:-0}}"
    REQUIRE_QUICK_TUNNEL_STOPPED="${{REQUIRE_QUICK_TUNNEL_STOPPED:-1}}"
    CLOUDFLARED_CONFIG="${{CLOUDFLARED_CONFIG:-$HOME/.cloudflared/config.yml}}"

    CONFIG_PUBLIC_URL=""
    if [ -r "$CLOUDFLARED_CONFIG" ]; then
        CONFIG_HOSTNAME="$(awk '
            /^[[:space:]]*-[[:space:]]*hostname:[[:space:]]*/ {{
                value=$0
                sub(/^[[:space:]]*-[[:space:]]*hostname:[[:space:]]*/, "", value)
                sub(/[[:space:]]*#.*/, "", value)
                gsub(/"/, "", value)
                gsub(/^[[:space:]]+|[[:space:]]+$/, "", value)
                if (value != "" && value !~ /[<>]/ && value !~ /trycloudflare[.]com$/ && value !~ /^localhost$/ && value !~ /^127[.]/ && value !~ /^0[.]0[.]0[.]0$/ && value !~ /:/) {{
                    print value
                    exit
                }}
            }}
        ' "$CLOUDFLARED_CONFIG")"
        if [ "$CONFIG_HOSTNAME" ]; then
            CONFIG_PUBLIC_URL="https://$CONFIG_HOSTNAME"
        fi
    fi
    if [ -z "$CONFIG_PUBLIC_URL" ]; then
        echo "production readiness requires an installed named Cloudflare tunnel config" >&2
        echo "run: make setup-named-tunnel TUNNEL_NAME=dialectical TUNNEL_HOSTNAME=<public-hostname>" >&2
        exit 2
    fi

    COORDINATOR_URL="${{COORDINATOR_URL:-${{CONFIG_PUBLIC_URL:-{public_url}}}}}"
    if [ "$CONFIG_PUBLIC_URL" ] && [ "$COORDINATOR_URL" != "$CONFIG_PUBLIC_URL" ]; then
        echo "production readiness requires COORDINATOR_URL to match installed named Cloudflare tunnel config: $CONFIG_PUBLIC_URL" >&2
        exit 2
    fi

    case "$COORDINATOR_URL" in
        https:*) ;;
        *)
            echo "production readiness requires an HTTPS named Cloudflare coordinator URL" >&2
            exit 2
            ;;
    esac
    case "$COORDINATOR_URL" in
        *"://"*) ;;
        *)
            echo "production readiness requires an HTTPS named Cloudflare coordinator URL" >&2
            exit 2
            ;;
    esac
    case "$COORDINATOR_URL" in
        *"<"*|*">"*)
            echo "production readiness requires a real named Cloudflare hostname, not a placeholder" >&2
            exit 2
            ;;
        *localhost*|*127.*|*0.0.0.0*|*"::1"*)
            echo "production readiness requires a public named Cloudflare hostname, not a local URL" >&2
            exit 2
            ;;
        *trycloudflare.com*)
            echo "production readiness requires a named Cloudflare hostname, not a trycloudflare.com quick tunnel" >&2
            exit 2
            ;;
    esac

    REQUIRED_CAPABILITY_COUNT=0
    SEEN_REQUIRED_CAPABILITIES=,
    old_ifs="$IFS"
    IFS=,
    for capability in $WORKER_REQUIRED_CAPABILITIES; do
        capability="$(printf '%s' "$capability" | sed 's/^[[:space:]]*//; s/[[:space:]]*$//')"
        case "$capability" in
            "")
                echo "production readiness requires non-empty model IDs in WORKER_REQUIRED_CAPABILITIES" >&2
                exit 2
                ;;
            *"<"*|*">"*|*placeholder*)
                echo "production readiness requires real model IDs in WORKER_REQUIRED_CAPABILITIES, not placeholders" >&2
                exit 2
                ;;
            mock-local|mock-*|*mock-*)
                echo "production readiness requires real model IDs in WORKER_REQUIRED_CAPABILITIES, not mock model IDs" >&2
                exit 2
                ;;
            *)
                case "$SEEN_REQUIRED_CAPABILITIES" in
                    *",$capability,"*)
                        echo "production readiness requires distinct model IDs in WORKER_REQUIRED_CAPABILITIES, not duplicate model IDs" >&2
                        exit 2
                        ;;
                esac
                SEEN_REQUIRED_CAPABILITIES="${{SEEN_REQUIRED_CAPABILITIES}}$capability,"
                REQUIRED_CAPABILITY_COUNT=$((REQUIRED_CAPABILITY_COUNT + 1))
                ;;
        esac
    done
    IFS="$old_ifs"
    if [ "$REQUIRED_CAPABILITY_COUNT" -lt 2 ]; then
        echo "production readiness requires WORKER_REQUIRED_CAPABILITIES to list at least two distinct real model IDs" >&2
        exit 2
    fi

    case "$REQUIRE_QUICK_TUNNEL_STOPPED" in
        1|true|yes)
            if command -v launchctl >/dev/null 2>&1 && launchctl list com.dialectical.cloudflared-quick >/dev/null 2>&1; then
                echo "production readiness requires the temporary quick tunnel service to be stopped" >&2
                echo "run: make stop-quick-tunnel" >&2
                exit 2
            fi
            ;;
    esac

    cd "$ENGINE_DIR"
    case "$RUN_PREFLIGHT" in
        0|false|no)
            if [ "$ALLOW_SKIP_PREFLIGHT_FOR_REHEARSAL" != "1" ] && [ "$ALLOW_SKIP_PREFLIGHT_FOR_REHEARSAL" != "true" ] && [ "$ALLOW_SKIP_PREFLIGHT_FOR_REHEARSAL" != "yes" ]; then
                echo "production readiness requires deploy preflight; set ALLOW_SKIP_PREFLIGHT_FOR_REHEARSAL=1 only for a rehearsal run" >&2
                exit 2
            fi
            ;;
        *)
            make deploy-preflight DEPLOY_ROLE=both PREFLIGHT_FLAGS="$PREFLIGHT_FLAGS"
            ;;
    esac
    case "$RUN_ENDPOINT_STATUS" in
        0|false|no)
            if [ "$ALLOW_SKIP_ENDPOINT_STATUS_FOR_REHEARSAL" != "1" ] && [ "$ALLOW_SKIP_ENDPOINT_STATUS_FOR_REHEARSAL" != "true" ] && [ "$ALLOW_SKIP_ENDPOINT_STATUS_FOR_REHEARSAL" != "yes" ]; then
                echo "production readiness requires endpoint status; set ALLOW_SKIP_ENDPOINT_STATUS_FOR_REHEARSAL=1 only for a rehearsal run" >&2
                exit 2
            fi
            ;;
        *)
            make status STATUS_FLAGS=--check-endpoints
            ;;
    esac
    make verify-worker-visible COORDINATOR_URL="$COORDINATOR_URL" WORKER_NAME="$WORKER_A_NAME" WORKER_VISIBLE_TIMEOUT="$WORKER_VISIBLE_TIMEOUT" WORKER_REQUIRED_CAPABILITIES="$WORKER_REQUIRED_CAPABILITIES" WORKER_REJECT_NON_PRODUCTION_CAPABILITIES=1
    make verify-worker-visible COORDINATOR_URL="$COORDINATOR_URL" WORKER_NAME="$WORKER_B_NAME" WORKER_VISIBLE_TIMEOUT="$WORKER_VISIBLE_TIMEOUT" WORKER_REQUIRED_CAPABILITIES="$WORKER_REQUIRED_CAPABILITIES" WORKER_REJECT_NON_PRODUCTION_CAPABILITIES=1
    echo "Production readiness passed for $WORKER_A_NAME and $WORKER_B_NAME at $COORDINATOR_URL with capabilities: $WORKER_REQUIRED_CAPABILITIES"
    """


def production_acceptance_sequence_script(public_url: str) -> str:
    return f"""
    #!/bin/sh
    set -eu

    : "${{ENGINE_DIR:?set ENGINE_DIR to the dialectical-engine checkout on the Mac mini}}"

    SCRIPT_DIR="$(CDPATH= cd "$(dirname "$0")" && pwd)"
    WORKER_B_BUNDLE="${{WORKER_B_BUNDLE:-$SCRIPT_DIR/bundles/dialectical-worker-b-onboarding.tgz}}"
    FINAL_CHECK_HELPER="${{FINAL_CHECK_HELPER:-$SCRIPT_DIR/final_production_check.sh}}"
    ACCEPTANCE_REPORT_DIR="${{ACCEPTANCE_REPORT_DIR:-/private/tmp}}"
    WORKER_A_NAME="${{WORKER_A_NAME:-mac-mini}}"
    WORKER_B_NAME="${{WORKER_B_NAME:-adesso-mbp}}"
    FINAL_CHECK_AFTER_ACCEPTANCE="${{FINAL_CHECK_AFTER_ACCEPTANCE:-1}}"
    FAILOVER_SETTLE_SECONDS="${{FAILOVER_SETTLE_SECONDS:-90}}"
    RUN_READINESS_CHECK="${{RUN_READINESS_CHECK:-1}}"
    ALLOW_SKIP_READINESS_CHECK_FOR_REHEARSAL="${{ALLOW_SKIP_READINESS_CHECK_FOR_REHEARSAL:-0}}"
    RUN_PREFLIGHT="${{RUN_PREFLIGHT:-1}}"
    ALLOW_SKIP_PREFLIGHT_FOR_REHEARSAL="${{ALLOW_SKIP_PREFLIGHT_FOR_REHEARSAL:-0}}"
    RUN_ENDPOINT_STATUS="${{RUN_ENDPOINT_STATUS:-1}}"
    ALLOW_SKIP_ENDPOINT_STATUS_FOR_REHEARSAL="${{ALLOW_SKIP_ENDPOINT_STATUS_FOR_REHEARSAL:-0}}"
    ALLOW_SKIP_FINAL_CHECK_FOR_REHEARSAL="${{ALLOW_SKIP_FINAL_CHECK_FOR_REHEARSAL:-0}}"
    REQUIRE_DIFFERENT_REGEN_MODEL="${{REQUIRE_DIFFERENT_REGEN_MODEL:-1}}"
    ALLOW_DISABLE_DIFFERENT_REGEN_MODEL_FOR_REHEARSAL="${{ALLOW_DISABLE_DIFFERENT_REGEN_MODEL_FOR_REHEARSAL:-0}}"
    SKIP_STRICT_REPORT_VALIDATION="${{SKIP_STRICT_REPORT_VALIDATION:-0}}"
    ALLOW_SKIP_STRICT_REPORT_VALIDATION_FOR_REHEARSAL="${{ALLOW_SKIP_STRICT_REPORT_VALIDATION_FOR_REHEARSAL:-0}}"
    WORKER_REQUIRED_CAPABILITIES="${{WORKER_REQUIRED_CAPABILITIES:-${{ALLOWED_MODELS:-codex-gpt-5.5,gemini-2.5-flash}}}}"
    ALLOW_QUICK_TUNNEL_ACCEPTANCE="${{ALLOW_QUICK_TUNNEL_ACCEPTANCE:-0}}"
    ALLOW_NONSTANDARD_ACCEPTANCE_REPORT_DIR="${{ALLOW_NONSTANDARD_ACCEPTANCE_REPORT_DIR:-0}}"
    REPORT_PYTHON="${{REPORT_PYTHON:-python3}}"
    STATUS_REPORT="${{STATUS_REPORT:-$SCRIPT_DIR/runtime-status-report.py}}"
    CLOUDFLARED_CONFIG="${{CLOUDFLARED_CONFIG:-$HOME/.cloudflared/config.yml}}"
    QUICK_TUNNEL_REHEARSAL=0
    REHEARSAL_ACCEPTANCE=0
    NONSTANDARD_REPORT_REHEARSAL=0

    CONFIG_PUBLIC_URL=""
    if [ -r "$CLOUDFLARED_CONFIG" ]; then
        CONFIG_HOSTNAME="$(awk '
            /^[[:space:]]*-[[:space:]]*hostname:[[:space:]]*/ {{
                value=$0
                sub(/^[[:space:]]*-[[:space:]]*hostname:[[:space:]]*/, "", value)
                sub(/[[:space:]]*#.*/, "", value)
                gsub(/"/, "", value)
                gsub(/^[[:space:]]+|[[:space:]]+$/, "", value)
                if (value != "" && value !~ /[<>]/ && value !~ /trycloudflare[.]com$/ && value !~ /^localhost$/ && value !~ /^127[.]/ && value !~ /^0[.]0[.]0[.]0$/ && value !~ /:/) {{
                    print value
                    exit
                }}
            }}
        ' "$CLOUDFLARED_CONFIG")"
        if [ "$CONFIG_HOSTNAME" ]; then
            CONFIG_PUBLIC_URL="https://$CONFIG_HOSTNAME"
        fi
    fi

    COORDINATOR_URL="${{COORDINATOR_URL:-${{CONFIG_PUBLIC_URL:-{public_url}}}}}"
    if [ "$CONFIG_PUBLIC_URL" ] && [ "$COORDINATOR_URL" != "$CONFIG_PUBLIC_URL" ]; then
        echo "production acceptance sequence requires COORDINATOR_URL to match installed named Cloudflare tunnel config before prompting for the user token: $CONFIG_PUBLIC_URL" >&2
        exit 2
    fi

    case "$COORDINATOR_URL" in
        https:*) ;;
        *)
            echo "production acceptance sequence requires an HTTPS named Cloudflare coordinator URL before prompting for the user token" >&2
            exit 2
            ;;
    esac
    case "$COORDINATOR_URL" in
        *"://"*) ;;
        *)
            echo "production acceptance sequence requires an HTTPS named Cloudflare coordinator URL before prompting for the user token" >&2
            exit 2
            ;;
    esac
    case "$COORDINATOR_URL" in
        *"<"*|*">"*)
            echo "production acceptance sequence requires a real named Cloudflare hostname, not a placeholder" >&2
            exit 2
            ;;
        *localhost*|*127.*|*0.0.0.0*|*"::1"*)
            echo "production acceptance sequence requires a public named Cloudflare hostname, not a local URL" >&2
            exit 2
            ;;
        *trycloudflare.com*)
            if [ "$ALLOW_QUICK_TUNNEL_ACCEPTANCE" != "1" ] && [ "$ALLOW_QUICK_TUNNEL_ACCEPTANCE" != "true" ] && [ "$ALLOW_QUICK_TUNNEL_ACCEPTANCE" != "yes" ]; then
                echo "production acceptance sequence requires a named Cloudflare hostname before prompting for the user token; set ALLOW_QUICK_TUNNEL_ACCEPTANCE=1 only for a provisional quick-tunnel smoke run" >&2
                exit 2
            fi
            QUICK_TUNNEL_REHEARSAL=1
            REHEARSAL_ACCEPTANCE=1
            ;;
    esac

    if [ "$QUICK_TUNNEL_REHEARSAL" = "1" ]; then
        case "$RUN_READINESS_CHECK" in
            0|false|no) ;;
            *)
                echo "production acceptance sequence quick-tunnel smoke is rehearsal-only; set RUN_READINESS_CHECK=0 with ALLOW_SKIP_READINESS_CHECK_FOR_REHEARSAL=1 before prompting for the user token" >&2
                exit 2
                ;;
        esac
        if [ "$ALLOW_SKIP_READINESS_CHECK_FOR_REHEARSAL" != "1" ] && [ "$ALLOW_SKIP_READINESS_CHECK_FOR_REHEARSAL" != "true" ] && [ "$ALLOW_SKIP_READINESS_CHECK_FOR_REHEARSAL" != "yes" ]; then
            echo "production acceptance sequence quick-tunnel smoke is rehearsal-only; set ALLOW_SKIP_READINESS_CHECK_FOR_REHEARSAL=1 before prompting for the user token" >&2
            exit 2
        fi
        case "$FINAL_CHECK_AFTER_ACCEPTANCE" in
            0|false|no) ;;
            *)
                echo "production acceptance sequence quick-tunnel smoke is rehearsal-only; set FINAL_CHECK_AFTER_ACCEPTANCE=0 with ALLOW_SKIP_FINAL_CHECK_FOR_REHEARSAL=1 before prompting for the user token" >&2
                exit 2
                ;;
        esac
        if [ "$ALLOW_SKIP_FINAL_CHECK_FOR_REHEARSAL" != "1" ] && [ "$ALLOW_SKIP_FINAL_CHECK_FOR_REHEARSAL" != "true" ] && [ "$ALLOW_SKIP_FINAL_CHECK_FOR_REHEARSAL" != "yes" ]; then
            echo "production acceptance sequence quick-tunnel smoke is rehearsal-only; set ALLOW_SKIP_FINAL_CHECK_FOR_REHEARSAL=1 before prompting for the user token" >&2
            exit 2
        fi
    fi

    if [ ! -f "$WORKER_B_BUNDLE" ]; then
        echo "missing Worker B bundle: $WORKER_B_BUNDLE" >&2
        exit 2
    fi
    case "$ACCEPTANCE_REPORT_DIR" in
        /private/tmp|/private/tmp/) ;;
        *)
            if [ "$ALLOW_NONSTANDARD_ACCEPTANCE_REPORT_DIR" != "1" ] && [ "$ALLOW_NONSTANDARD_ACCEPTANCE_REPORT_DIR" != "true" ] && [ "$ALLOW_NONSTANDARD_ACCEPTANCE_REPORT_DIR" != "yes" ]; then
                echo "production acceptance sequence writes final reports to /private/tmp where strict status reads them; set ALLOW_NONSTANDARD_ACCEPTANCE_REPORT_DIR=1 only for a rehearsal run" >&2
                exit 2
            fi
            NONSTANDARD_REPORT_REHEARSAL=1
            REHEARSAL_ACCEPTANCE=1
            ;;
    esac

    if [ "$NONSTANDARD_REPORT_REHEARSAL" = "1" ]; then
        case "$SKIP_STRICT_REPORT_VALIDATION" in
            1|true|yes) ;;
            *)
                echo "production acceptance sequence nonstandard report directory is rehearsal-only; set SKIP_STRICT_REPORT_VALIDATION=1 with ALLOW_SKIP_STRICT_REPORT_VALIDATION_FOR_REHEARSAL=1 before prompting for the user token" >&2
                exit 2
                ;;
        esac
        if [ "$ALLOW_SKIP_STRICT_REPORT_VALIDATION_FOR_REHEARSAL" != "1" ] && [ "$ALLOW_SKIP_STRICT_REPORT_VALIDATION_FOR_REHEARSAL" != "true" ] && [ "$ALLOW_SKIP_STRICT_REPORT_VALIDATION_FOR_REHEARSAL" != "yes" ]; then
            echo "production acceptance sequence nonstandard report directory is rehearsal-only; set ALLOW_SKIP_STRICT_REPORT_VALIDATION_FOR_REHEARSAL=1 before prompting for the user token" >&2
            exit 2
        fi
        case "$FINAL_CHECK_AFTER_ACCEPTANCE" in
            0|false|no) ;;
            *)
                echo "production acceptance sequence nonstandard report directory is rehearsal-only; set FINAL_CHECK_AFTER_ACCEPTANCE=0 with ALLOW_SKIP_FINAL_CHECK_FOR_REHEARSAL=1 before prompting for the user token" >&2
                exit 2
                ;;
        esac
        if [ "$ALLOW_SKIP_FINAL_CHECK_FOR_REHEARSAL" != "1" ] && [ "$ALLOW_SKIP_FINAL_CHECK_FOR_REHEARSAL" != "true" ] && [ "$ALLOW_SKIP_FINAL_CHECK_FOR_REHEARSAL" != "yes" ]; then
            echo "production acceptance sequence nonstandard report directory is rehearsal-only; set ALLOW_SKIP_FINAL_CHECK_FOR_REHEARSAL=1 before prompting for the user token" >&2
            exit 2
        fi
    fi

    confirm_step() {{
        message="$1"
        env_name="$2"
        eval "confirmed=\\${{$env_name:-}}"
        case "$confirmed" in
            1|true|yes)
                return
                ;;
        esac
        if [ ! -t 0 ]; then
            echo "$message" >&2
            echo "set $env_name=1 after completing that physical step" >&2
            exit 2
        fi
        printf "%s Press Enter to continue: " "$message" >&2
        IFS= read -r _
    }}

    REQUIRED_CAPABILITY_COUNT=0
    SEEN_REQUIRED_CAPABILITIES=,
    old_ifs="$IFS"
    IFS=,
    for capability in $WORKER_REQUIRED_CAPABILITIES; do
        capability="$(printf '%s' "$capability" | sed 's/^[[:space:]]*//; s/[[:space:]]*$//')"
        case "$capability" in
            "")
                echo "production acceptance sequence requires non-empty model IDs in WORKER_REQUIRED_CAPABILITIES" >&2
                exit 2
                ;;
            *"<"*|*">"*|*placeholder*)
                echo "production acceptance sequence requires real model IDs in WORKER_REQUIRED_CAPABILITIES, not placeholders" >&2
                exit 2
                ;;
            mock-local|mock-*|*mock-*)
                echo "production acceptance sequence requires real model IDs in WORKER_REQUIRED_CAPABILITIES, not mock model IDs" >&2
                exit 2
                ;;
            *)
                case "$SEEN_REQUIRED_CAPABILITIES" in
                    *",$capability,"*)
                        echo "production acceptance sequence requires distinct model IDs in WORKER_REQUIRED_CAPABILITIES, not duplicate model IDs" >&2
                        exit 2
                        ;;
                esac
                SEEN_REQUIRED_CAPABILITIES="${{SEEN_REQUIRED_CAPABILITIES}}$capability,"
                REQUIRED_CAPABILITY_COUNT=$((REQUIRED_CAPABILITY_COUNT + 1))
                ;;
        esac
    done
    IFS="$old_ifs"
    case "$REQUIRE_DIFFERENT_REGEN_MODEL" in
        1|true|yes)
            if [ "$REQUIRED_CAPABILITY_COUNT" -lt 2 ]; then
                echo "production acceptance sequence requires WORKER_REQUIRED_CAPABILITIES to list at least two real model IDs before prompting for the user token" >&2
                exit 2
            fi
            ;;
        0|false|no)
            REHEARSAL_ACCEPTANCE=1
            if [ "$ALLOW_DISABLE_DIFFERENT_REGEN_MODEL_FOR_REHEARSAL" != "1" ] && [ "$ALLOW_DISABLE_DIFFERENT_REGEN_MODEL_FOR_REHEARSAL" != "true" ] && [ "$ALLOW_DISABLE_DIFFERENT_REGEN_MODEL_FOR_REHEARSAL" != "yes" ]; then
                echo "production acceptance sequence requires different-model regeneration proof before prompting for the user token; set ALLOW_DISABLE_DIFFERENT_REGEN_MODEL_FOR_REHEARSAL=1 only for a rehearsal run" >&2
                exit 2
            fi
            ;;
    esac

    case "$RUN_READINESS_CHECK" in
        0|false|no)
            REHEARSAL_ACCEPTANCE=1
            if [ "$ALLOW_SKIP_READINESS_CHECK_FOR_REHEARSAL" != "1" ] && [ "$ALLOW_SKIP_READINESS_CHECK_FOR_REHEARSAL" != "true" ] && [ "$ALLOW_SKIP_READINESS_CHECK_FOR_REHEARSAL" != "yes" ]; then
                echo "production acceptance sequence requires production_readiness.sh before prompting for the user token; set ALLOW_SKIP_READINESS_CHECK_FOR_REHEARSAL=1 only for a rehearsal run" >&2
                exit 2
            fi
            ;;
    esac

    case "$RUN_READINESS_CHECK" in
        0|false|no)
            ;;
        *)
            case "$RUN_PREFLIGHT" in
                0|false|no)
                    REHEARSAL_ACCEPTANCE=1
                    if [ "$ALLOW_SKIP_PREFLIGHT_FOR_REHEARSAL" != "1" ] && [ "$ALLOW_SKIP_PREFLIGHT_FOR_REHEARSAL" != "true" ] && [ "$ALLOW_SKIP_PREFLIGHT_FOR_REHEARSAL" != "yes" ]; then
                        echo "production acceptance sequence requires production_readiness.sh deploy preflight before prompting for the user token; set ALLOW_SKIP_PREFLIGHT_FOR_REHEARSAL=1 only for a rehearsal run" >&2
                        exit 2
                    fi
                    ;;
            esac
            case "$RUN_ENDPOINT_STATUS" in
                0|false|no)
                    REHEARSAL_ACCEPTANCE=1
                    if [ "$ALLOW_SKIP_ENDPOINT_STATUS_FOR_REHEARSAL" != "1" ] && [ "$ALLOW_SKIP_ENDPOINT_STATUS_FOR_REHEARSAL" != "true" ] && [ "$ALLOW_SKIP_ENDPOINT_STATUS_FOR_REHEARSAL" != "yes" ]; then
                        echo "production acceptance sequence requires production_readiness.sh endpoint status before prompting for the user token; set ALLOW_SKIP_ENDPOINT_STATUS_FOR_REHEARSAL=1 only for a rehearsal run" >&2
                        exit 2
                    fi
                    ;;
            esac
            ;;
    esac

    case "$FINAL_CHECK_AFTER_ACCEPTANCE" in
        0|false|no)
            REHEARSAL_ACCEPTANCE=1
            if [ "$ALLOW_SKIP_FINAL_CHECK_FOR_REHEARSAL" != "1" ] && [ "$ALLOW_SKIP_FINAL_CHECK_FOR_REHEARSAL" != "true" ] && [ "$ALLOW_SKIP_FINAL_CHECK_FOR_REHEARSAL" != "yes" ]; then
                echo "production acceptance sequence final-check skip is rehearsal-only before prompting for the user token; set ALLOW_SKIP_FINAL_CHECK_FOR_REHEARSAL=1 only for a rehearsal run" >&2
                exit 2
            fi
            ;;
    esac

    if [ "$REHEARSAL_ACCEPTANCE" = "1" ]; then
        case "$SKIP_STRICT_REPORT_VALIDATION" in
            1|true|yes) ;;
            *)
                echo "production acceptance sequence rehearsal requires strict report validation skip before prompting for the user token; set SKIP_STRICT_REPORT_VALIDATION=1 with ALLOW_SKIP_STRICT_REPORT_VALIDATION_FOR_REHEARSAL=1 only for a rehearsal run" >&2
                exit 2
                ;;
        esac
        if [ "$ALLOW_SKIP_STRICT_REPORT_VALIDATION_FOR_REHEARSAL" != "1" ] && [ "$ALLOW_SKIP_STRICT_REPORT_VALIDATION_FOR_REHEARSAL" != "true" ] && [ "$ALLOW_SKIP_STRICT_REPORT_VALIDATION_FOR_REHEARSAL" != "yes" ]; then
            echo "production acceptance sequence rehearsal requires strict report validation skip before prompting for the user token; set ALLOW_SKIP_STRICT_REPORT_VALIDATION_FOR_REHEARSAL=1 only for a rehearsal run" >&2
            exit 2
        fi
        case "$FINAL_CHECK_AFTER_ACCEPTANCE" in
            0|false|no) ;;
            *)
                echo "production acceptance sequence rehearsal requires final check skip before prompting for the user token; set FINAL_CHECK_AFTER_ACCEPTANCE=0 with ALLOW_SKIP_FINAL_CHECK_FOR_REHEARSAL=1 only for a rehearsal run" >&2
                exit 2
                ;;
        esac
        if [ "$ALLOW_SKIP_FINAL_CHECK_FOR_REHEARSAL" != "1" ] && [ "$ALLOW_SKIP_FINAL_CHECK_FOR_REHEARSAL" != "true" ] && [ "$ALLOW_SKIP_FINAL_CHECK_FOR_REHEARSAL" != "yes" ]; then
            echo "production acceptance sequence rehearsal requires final check skip before prompting for the user token; set ALLOW_SKIP_FINAL_CHECK_FOR_REHEARSAL=1 only for a rehearsal run" >&2
            exit 2
        fi
    fi

    tmpdir="$(mktemp -d)"
    trap 'rm -rf "$tmpdir"' EXIT INT TERM HUP
    tar -xzf "$WORKER_B_BUNDLE" -C "$tmpdir"
    ACCEPTANCE_HELPER="$tmpdir/dialectical-worker-b-onboarding/production_acceptance.sh"
    if [ ! -x "$ACCEPTANCE_HELPER" ]; then
        echo "missing executable production_acceptance.sh in $WORKER_B_BUNDLE" >&2
        exit 2
    fi
    if ! /bin/sh -n "$ACCEPTANCE_HELPER"; then
        echo "invalid production_acceptance.sh in $WORKER_B_BUNDLE" >&2
        exit 2
    fi
    if ! command -v "$REPORT_PYTHON" >/dev/null 2>&1 && [ ! -x "$REPORT_PYTHON" ]; then
        echo "production acceptance sequence requires python for bundle validation: $REPORT_PYTHON" >&2
        exit 2
    fi
    if [ ! -r "$STATUS_REPORT" ]; then
        echo "production acceptance sequence requires runtime-status-report.py for bundle validation: $STATUS_REPORT" >&2
        exit 2
    fi
    if ! "$REPORT_PYTHON" "$STATUS_REPORT" --validate-worker-b-bundle "$WORKER_B_BUNDLE" --validate-worker-b-bundle-public-url "$COORDINATOR_URL"; then
        echo "production acceptance sequence requires a current Worker B onboarding bundle before prompting for the user token" >&2
        exit 2
    fi
    case "$FINAL_CHECK_AFTER_ACCEPTANCE" in
        0|false|no)
            ;;
        *)
            if [ ! -x "$FINAL_CHECK_HELPER" ]; then
                echo "production acceptance sequence requires executable final_production_check.sh before prompting for the user token: $FINAL_CHECK_HELPER" >&2
                exit 2
            fi
            if ! /bin/sh -n "$FINAL_CHECK_HELPER"; then
                echo "production acceptance sequence requires valid final_production_check.sh before prompting for the user token: $FINAL_CHECK_HELPER" >&2
                exit 2
            fi
            ;;
    esac

    case "$RUN_READINESS_CHECK" in
        0|false|no)
            ;;
        *)
            export COORDINATOR_URL
            export ENGINE_DIR
            export WORKER_A_NAME
            export WORKER_B_NAME
            export WORKER_REQUIRED_CAPABILITIES
            export RUN_PREFLIGHT
            export ALLOW_SKIP_PREFLIGHT_FOR_REHEARSAL
            export RUN_ENDPOINT_STATUS
            export ALLOW_SKIP_ENDPOINT_STATUS_FOR_REHEARSAL
            "$SCRIPT_DIR/production_readiness.sh"
            ;;
    esac

    {user_token_prompt('rm -rf "$tmpdir"')}
    trap 'rm -rf "$tmpdir"' EXIT INT TERM HUP
    export COORDINATOR_URL
    export ENGINE_DIR
    export ACCEPTANCE_REPORT_DIR
    export REQUIRE_DIFFERENT_REGEN_MODEL
    export ALLOW_DISABLE_DIFFERENT_REGEN_MODEL_FOR_REHEARSAL
    export SKIP_STRICT_REPORT_VALIDATION
    export ALLOW_SKIP_STRICT_REPORT_VALIDATION_FOR_REHEARSAL
    export WORKER_REQUIRED_CAPABILITIES
    export ALLOW_QUICK_TUNNEL_ACCEPTANCE

    USER_TOKEN="$USER_TOKEN" MODE=two-worker "$ACCEPTANCE_HELPER"

    confirm_step "Sleep or power off Worker B, then wait for it to disappear from online workers." CONFIRM_WORKER_B_OFFLINE
    if [ "$FAILOVER_SETTLE_SECONDS" != "0" ]; then
        sleep "$FAILOVER_SETTLE_SECONDS"
    fi
    USER_TOKEN="$USER_TOKEN" MODE=failover-one-worker "$ACCEPTANCE_HELPER"

    confirm_step "Wake Worker B and wait until it can reconnect to the named tunnel." CONFIRM_WORKER_B_REJOINED
    USER_TOKEN="$USER_TOKEN" MODE=rejoin-two-worker "$ACCEPTANCE_HELPER"

    case "$FINAL_CHECK_AFTER_ACCEPTANCE" in
        0|false|no)
            if [ "$ALLOW_SKIP_FINAL_CHECK_FOR_REHEARSAL" != "1" ] && [ "$ALLOW_SKIP_FINAL_CHECK_FOR_REHEARSAL" != "true" ] && [ "$ALLOW_SKIP_FINAL_CHECK_FOR_REHEARSAL" != "yes" ]; then
                echo "production acceptance sequence requires final_production_check.sh after rejoin acceptance; set ALLOW_SKIP_FINAL_CHECK_FOR_REHEARSAL=1 only for a rehearsal run" >&2
                exit 2
            fi
            ;;
        *)
            "$FINAL_CHECK_HELPER"
            ;;
    esac
    """


def handoff_readme(public_url: str) -> str:
    return f"""
    # Dialectical Engine V2 Handoff

    This bundle collects the current audit plus generated onboarding bundles.

    ## Current Runtime

    - Local UI/API proxy: `http://127.0.0.1:3000`
    - Coordinator: `http://127.0.0.1:8000`
    - Public URL: `{public_url}`

    ## Quick Checks

    ```sh
    make status STATUS_FLAGS=--check-endpoints
    make deploy-preflight DEPLOY_ROLE=both
    ```

    After the named tunnel is installed, Worker B is onboarded, local proof is
    refreshed, and all three production acceptance reports exist, run the
    executable final wrapper from this bundle:

    ```sh
    ENGINE_DIR=/path/to/dialectical-engine ./final_production_check.sh
    ```

    The wrapper fails before refreshing local proof if any of the three
    production acceptance reports is missing from `/private/tmp` or if
    `ACCEPTANCE_REPORT_DIR` points elsewhere without
    `ALLOW_NONSTANDARD_ACCEPTANCE_REPORT_DIR=1`; nonstandard report directories
    are rehearsal-only because strict status reads `/private/tmp`, so they also
    require `REQUIRE_PRODUCTION_ACCEPTANCE_REPORTS=0` with
    `ALLOW_SKIP_PRODUCTION_REPORTS_FOR_REHEARSAL=1` before proof refresh.

    The wrapper prefers the installed named Cloudflare hostname from
    `~/.cloudflared/config.yml` when `COORDINATOR_URL` is not set, then falls
    back to the bundle URL. It installs the current status helper, runs strict
    deploy preflight, including launchd API-key checks for API-backed final
    models, exports `WORKER_REQUIRED_CAPABILITIES` so endpoint and strict
    status evaluate the same final model pair, refreshes local proof by
    default, regenerates the handoff bundles for `PUBLIC_URL`, then runs
    endpoint status and strict production status in order. It exits nonzero
    until the runtime, bundles, and production acceptance evidence are all
    final-ready.
    Set `REFRESH_LOCAL_PROOF=0` with `ALLOW_SKIP_LOCAL_PROOF_FOR_REHEARSAL=1`
    only when `make status` already shows all local proof artifacts current
    and you intentionally want to skip the local mock-cluster refresh for a
    rehearsal run.

    To generate the three production acceptance reports from the Mac mini in
    order, run:

    ```sh
    ENGINE_DIR=/path/to/dialectical-engine ./production_acceptance_sequence.sh
    ```

    The sequence helper first verifies that the coordinator URL is an HTTPS
    named Cloudflare hostname unless `ALLOW_QUICK_TUNNEL_ACCEPTANCE=1` is
    explicitly set for a provisional quick-tunnel smoke run. A quick-tunnel
    smoke run is rehearsal-only: the sequence also requires
    `RUN_READINESS_CHECK=0`,
    `ALLOW_SKIP_READINESS_CHECK_FOR_REHEARSAL=1`,
    `FINAL_CHECK_AFTER_ACCEPTANCE=0`, and
    `ALLOW_SKIP_FINAL_CHECK_FOR_REHEARSAL=1` before any user token prompt, and
    `SKIP_STRICT_REPORT_VALIDATION=1` with
    `ALLOW_SKIP_STRICT_REPORT_VALIDATION_FOR_REHEARSAL=1` so the embedded
    Worker B helper does not run final-only report validation against rehearsal
    reports. Final strict status will still reject the resulting reports.
    Any rehearsal report shape, including a one-model run with
    `REQUIRE_DIFFERENT_REGEN_MODEL=0`, must set those strict-validation skip
    flags and the final-check skip flags before the token prompt. It also
    verifies that final different-model proof has at least two distinct real model IDs
    in `WORKER_REQUIRED_CAPABILITIES` unless `REQUIRE_DIFFERENT_REGEN_MODEL=0`
    is explicitly set together with
    `ALLOW_DISABLE_DIFFERENT_REGEN_MODEL_FOR_REHEARSAL=1` for a rehearsal run.
    By default it requires
    `codex-gpt-5.5,gemini-2.5-flash`, matching the final readiness check. It then
    unpacks the embedded Worker B onboarding bundle
    and validates the full onboarding bundle, including the public URL, shell
    syntax, endpoint verifier, registration guard, real-model setup, switch
    helper, report-locality guidance, and strict acceptance helper contract,
    before running readiness or prompting once for the user token. After that it
    runs `two-worker`, pauses while you sleep or power off Worker B, runs
    `failover-one-worker`, pauses while you wake Worker B, runs
    `rejoin-two-worker`, and then runs `final_production_check.sh` unless
    `FINAL_CHECK_AFTER_ACCEPTANCE=0` and
    `ALLOW_SKIP_FINAL_CHECK_FOR_REHEARSAL=1` are both set for a rehearsal run.
    Set `FAILOVER_SETTLE_SECONDS=0` only when Worker B has already been offline
    for long enough to be reported offline by the coordinator.

    To verify final named-host and two-worker capability readiness before any
    user token prompt, run:

    ```sh
    ENGINE_DIR=/path/to/dialectical-engine ./production_readiness.sh
    ```

    The readiness helper requires the named Cloudflare config, rejects quick
    tunnel and local URLs, ensures the quick-tunnel launchd service is stopped,
    runs deploy preflight and endpoint status by default, requires launchd API
    keys for API-backed final models on the Mac mini worker, and verifies both
    `mac-mini` and `adesso-mbp` advertise the final required capabilities
    through the public coordinator. Skipping readiness deploy preflight or
    endpoint status requires pairing `RUN_PREFLIGHT=0` or
    `RUN_ENDPOINT_STATUS=0` with the matching `ALLOW_SKIP_*_FOR_REHEARSAL=1`
    flag, and is only for rehearsal runs. `production_acceptance_sequence.sh`
    exports the same coordinator URL, worker names, required capabilities, and
    readiness skip controls into this readiness check before prompting for the
    user token; any `RUN_PREFLIGHT=0`, `RUN_ENDPOINT_STATUS=0`, or
    `RUN_READINESS_CHECK=0` sequence run is rehearsal-only and also requires
    the strict-report-validation and final-check rehearsal skip flags before
    the token prompt. The sequence also requires
    `ACCEPTANCE_REPORT_DIR=/private/tmp`
    by default because final strict status reads the three production reports
    from that Mac mini directory; set `ALLOW_NONSTANDARD_ACCEPTANCE_REPORT_DIR=1`
    only for a rehearsal run whose reports will not be accepted as final proof.
    Nonstandard report-directory rehearsal runs must also set
    `SKIP_STRICT_REPORT_VALIDATION=1`,
    `ALLOW_SKIP_STRICT_REPORT_VALIDATION_FOR_REHEARSAL=1`,
    `FINAL_CHECK_AFTER_ACCEPTANCE=0` and
    `ALLOW_SKIP_FINAL_CHECK_FOR_REHEARSAL=1` before any user token prompt.

    Before running final production acceptance, configure both Worker A and
    Worker B with the same two-real-model allowlist. The embedded Worker B
    bundle includes `configure_worker_b_real_models.sh`; run it on the adesso
    MacBook with `ALLOWED_MODELS=codex-gpt-5.5,gemini-2.5-flash` and a real
    `GEMINI_API_KEY`, then run this handoff bundle's
    `configure_worker_a_real_models.sh` on the Mac mini with the same
    allowlist and API key:

    ```sh
    ENGINE_DIR=/path/to/dialectical-engine \\
    GEMINI_API_KEY='<google-ai-studio-api-key>' \\
    ALLOWED_MODELS=codex-gpt-5.5,gemini-2.5-flash \\
    ./configure_worker_a_real_models.sh
    ```

    The Worker A helper refuses to run until the named Cloudflare tunnel config
    is installed, runs Mac mini deploy preflight for the named tunnel before it
    changes Worker A, rejects placeholder/local/quick-tunnel public URLs,
    rejects mock, duplicate, and single-model allowlists, reruns
    `make install-worker` against the local Mac mini coordinator, and verifies
    the named public endpoint sees Worker A with the requested capabilities. If Worker A is
    already registered against the local coordinator, the installer reuses the
    saved worker token without prompting for the user token. The final
    acceptance sequence uses `codex-gpt-5.5,gemini-2.5-flash` by default; set
    `WORKER_REQUIRED_CAPABILITIES` only if the final real-model pair changes.

    `make status STATUS_FLAGS=--check-endpoints` exits nonzero if any checked
    local/public endpoint, export, or web route fails.
    `make status STATUS_FLAGS=--strict-production` also runs endpoint checks and
    exits nonzero until the public URL comes from the named tunnel config, the
    quick tunnel is stopped, prompt-safety source invariants pass,
    worker retry/stream resilience source invariants pass, API adapter
    source invariants pass, local proof artifacts are current, handoff bundles
    are current, and all three
    production acceptance reports are passed/current/complete with
    production-scoped worker/model evidence. It rejects stale failure metadata
    and generic or stale result details for web auth/token-flow, SSE,
    regeneration, markdown export, and persistence checks, and requires
    ordered timezone-aware timestamps, a UUID `debate_id` matching
    the create/persistence result details, structured public archive API and
    current-debate web-home evidence, structured worker-status payload
    evidence for `/api/backends/status` counts and rows, structured debate
    lifecycle evidence for create/skeleton/role-override/timing/persistence
    checks, structured auth-boundary evidence for public-read/auth-write rejection checks,
    structured settings round-trip
    evidence for per-model spend/cap persistence and restoration,
    structured web-auth gate evidence for the protected pages,
    structured web-auth token-flow evidence for
    AuthGate/API client source contracts, structured post-unlock web surface
    evidence for the protected pages, structured debate-action source evidence
    for regenerate/history controls and API calls, structured
    streaming-client source evidence for SSE rendering, reconnect, refresh,
    and model color markers, structured SSE evidence for required event types,
    token counts, event-sequence ordering, initial replay-history mode,
    regenerated live-only mode, initial `tree_ready` root/child IDs, and
    start/completion payloads, structured generated/regenerated node
    metadata evidence for active argument generations, structured
    initial/regenerated synthesis evidence with debate IDs, timestamps,
    observed worker names, and persisted regenerated synthesis ID, structured
    regenerate-request evidence for queued job and previous generation/synthesis IDs, structured
    regeneration-history evidence for archived/active generations with
    argument, latency, and token metadata, structured
    web-debate detail evidence for the public debate page, structured
    markdown-export evidence for the current debate/topic, debate-id filename,
    headers, sections, workers, models, and active/archived history generation
    IDs/counts, structured
    online/offline worker rows with IDs, capabilities, timezone-aware
    `last_seen`, and
    `current_job_id`,
    stable worker IDs across the two-worker, failover, and rejoin production
    phases,
    sequential production phase timestamps from two-worker to failover to
    rejoin,
    distinct debate IDs across the three production phases,
    structured settings evidence, structured SSE event/token evidence,
    generated/regenerated node metadata, worker names, and model ID fields,
    aggregate observed worker/model fields and recorded result detail/evidence
    that match that detailed evidence, exact expected
    online/offline/generated/regenerated worker names for each phase, named
    HTTPS URL-class proof, no placeholder/mock/local model or worker evidence,
    no unexpected worker names, no missing required
    capabilities for expected online/offline rows, no expected-offline workers
    in online/generated/regenerated evidence, and a structured real `old ->
    new` regeneration model switch that matches archived/active generation
    history.

    ## Remaining External Steps

    - Install the named Cloudflare tunnel with account credentials and hostname.
    - Run Worker B onboarding on the adesso MacBook.
    - Switch Worker B to the named hostname with `switch_worker_b_url.sh`.
    - Configure unattended Claude/Gemini auth before enabling those models, and
      rerun `make install-worker` with `GEMINI_API_KEY`/`XAI_API_KEY` present
      when API-backed adapters should run under launchd.
    - Run `production_readiness.sh` from this handoff bundle to verify the
      named endpoint, stopped quick tunnel, and both workers' real-model
      capabilities before entering the user token for acceptance.
    - Refresh local proof with `make dev-smoke` and `make local-cluster-check`
      or let `final_production_check.sh` do that default refresh. The local
      cluster proof includes two-worker, failover, rejoin, current-job,
      in-flight failover, restart persistence, and retryable `node_failed` SSE
      reports, including degraded worker visibility with `current_job_id`
      cleared after the retryable failure. Coordinator SSE streams replay a
      bounded per-debate event history before live events so acceptance and
      reconnecting clients can verify the ordered event prefix.
    - Run `production_acceptance.sh` in `two-worker`, `failover-one-worker`,
      and `rejoin-two-worker` modes from the Mac mini, or copy each JSON
      report back to `/private/tmp` on the Mac mini before the next phase and
      final strict status.
    - Confirm those acceptance reports include `settings-roundtrip` with
      structured per-model spend/cap restore evidence, `public-list`,
      `web-home`, `worker-status-payload`, `create-debate`, `tree-skeleton`,
      `role-overrides`, `tree-skeleton-timing`, `persistence`,
      `auth-boundaries`, `write-auth-boundaries`, `web-auth-token-flow`, and
      `web-auth-surfaces`, `web-debate-actions`, and
      `web-streaming-client`, no stale failure metadata, ordered
      timezone-aware timestamps, a UUID `debate_id` matching the
      create/persistence result details, plus structured public archive API and
      current-debate web-home evidence, structured worker-status payload
      evidence for `/api/backends/status` counts and rows, structured debate
      lifecycle evidence for create/skeleton/role-override/timing/persistence
      checks, structured auth-boundary evidence for public-read/auth-write rejection checks,
      structured web-auth gate evidence
      for the protected pages, structured web-auth token-flow evidence for
      AuthGate/API client source contracts, structured post-unlock web surface
      evidence for the protected pages, structured debate-action source
      evidence for regenerate/history controls and API calls, structured
      streaming-client source evidence for SSE rendering, reconnect, refresh,
      and model color markers, structured SSE evidence for required event
      types, token counts, event-sequence ordering, initial replay-history
      mode, regenerated live-only mode, initial `tree_ready` root/child IDs,
      and start/completion payloads, structured generated/regenerated
      node metadata evidence for active argument generations, structured
      initial/regenerated synthesis evidence with debate IDs, timestamps,
      observed worker names, and persisted regenerated synthesis ID, structured
      regenerate-request evidence for queued job and previous generation/synthesis IDs,
      regeneration-history evidence for archived/active generations with
      argument, latency, and token metadata,
      structured web-debate detail evidence for the public debate page,
      structured markdown-export evidence for the current debate/topic,
      debate-id filename, headers, sections, workers, models, and
      active/archived history generation IDs/counts,
      structured online/offline worker rows with IDs, capabilities,
      timezone-aware `last_seen`, and `current_job_id`, aggregate
      stable worker IDs across the two-worker, failover, and rejoin phases,
      sequential production phase timestamps from two-worker to failover to
      rejoin,
      distinct debate IDs across the three production phases,
      observed worker/model fields and
      recorded result detail/evidence that match those structured fields,
      generated/regenerated non-mock model IDs, exact expected non-local worker
      names for each phase, and a structured regeneration model switch tied to
      archived/active generation history.
    - Run `make status STATUS_FLAGS=--strict-production` as the final handoff
      gate.
    """


def build_handoff_bundle(output_dir: Path, public_url: str, worker_bundle: Path, tunnel_bundle: Path) -> Path:
    with tempfile.TemporaryDirectory(prefix="dialectical-handoff-bundle-") as tmp:
        root = Path(tmp) / "dialectical-handoff"
        write(root / "README.md", handoff_readme(public_url))
        write(
            root / "final_production_check.sh",
            final_production_check_script(public_url),
            stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR | stat.S_IRGRP | stat.S_IROTH,
        )
        write(
            root / "configure_worker_a_real_models.sh",
            worker_a_real_models_script(public_url),
            stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR | stat.S_IRGRP | stat.S_IROTH,
        )
        write(
            root / "production_readiness.sh",
            production_readiness_script(public_url),
            stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR | stat.S_IRGRP | stat.S_IROTH,
        )
        write(
            root / "production_acceptance_sequence.sh",
            production_acceptance_sequence_script(public_url),
            stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR | stat.S_IRGRP | stat.S_IROTH,
        )
        if AUDIT_PATH.exists():
            shutil.copyfile(AUDIT_PATH, root / "dialectical-completion-audit.md")
        bundles = root / "bundles"
        bundles.mkdir(parents=True)
        shutil.copyfile(worker_bundle, bundles / worker_bundle.name)
        shutil.copyfile(tunnel_bundle, bundles / tunnel_bundle.name)
        shutil.copyfile(ROOT / "scripts" / "status_report.py", root / "runtime-status-report.py")
        destination = output_dir / f"dialectical-v2-handoff-{date.today().isoformat()}.tgz"
        tar_directory(root, destination)
        return destination


def main() -> int:
    parser = argparse.ArgumentParser(description="Build credentials-free Dialectical deployment handoff bundles")
    parser.add_argument("--output-dir", type=Path, default=Path(os.getenv("BUNDLE_OUTPUT_DIR", DEFAULT_OUTPUT_DIR)))
    parser.add_argument("--public-url", default=os.getenv("PUBLIC_URL", DEFAULT_PUBLIC_URL))
    parser.add_argument("--worker-name", default=os.getenv("WORKER_B_NAME", DEFAULT_WORKER_NAME))
    args = parser.parse_args()

    output_dir = args.output_dir.expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)
    public_url = args.public_url.rstrip("/")

    worker_bundle = build_worker_bundle(output_dir, public_url, args.worker_name)
    tunnel_bundle = build_named_tunnel_bundle(output_dir)
    handoff_bundle = build_handoff_bundle(output_dir, public_url, worker_bundle, tunnel_bundle)

    for path in (worker_bundle, tunnel_bundle, handoff_bundle):
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
