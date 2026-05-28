#!/bin/sh
set -eu

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
DOMAIN="${DOMAIN:-dezbatere.ro}"
CLOUDFLARED_DIR="${CLOUDFLARED_DIR:-$HOME/.cloudflared}"

need() {
    if ! command -v "$1" >/dev/null 2>&1; then
        echo "missing command: $1" >&2
        return 1
    fi
    return 0
}

confirm() {
    prompt="$1"
    printf "%s [y/N] " "$prompt"
    IFS= read -r answer
    case "$answer" in
        y|Y|yes|YES|Yes) return 0 ;;
        *) return 1 ;;
    esac
}

registry_nameservers() {
    if command -v dig >/dev/null 2>&1; then
        dig @primary.rotld.ro "$DOMAIN" NS 2>/dev/null | awk 'toupper($4)=="NS" {print $5}' | sort -u || true
    fi
}

if [ ! -t 0 ] || [ ! -t 1 ]; then
    cat >&2 <<EOF
This helper must run in a normal interactive Terminal.

It launches browser/account login flows for Claude, Gemini, and Cloudflare.
Run:

  cd "$ROOT"
  make interactive-manual-setup

Non-interactive checks remain available with:

  make setup-status
EOF
    exit 2
fi

cd "$ROOT"

cat <<EOF
Interactive manual setup helper for the single-Mac dezbatere.ro setup.

This does not create API keys and does not ask for paid Gemini API usage.
It only helps start the account login flows that require your browser/session.
EOF

if need claude; then
    if confirm "Run Claude Code login now?"; then
        claude auth status || true
        claude auth login || true
        claude -p --max-turns 1 "Reply with exactly: ok" || true
    fi
else
    echo "Skipping Claude login because the claude command is not installed."
fi

if need gemini; then
    if confirm "Configure Gemini for Google-account OAuth and open Gemini CLI now?"; then
        make configure-gemini-google-auth
        GOOGLE_GENAI_USE_GCA=true gemini || true
        GOOGLE_GENAI_USE_GCA=true gemini -p "Reply with exactly: ok" || true
    fi
else
    echo "Skipping Gemini login because the gemini command is not installed."
fi

if need cloudflared; then
    if [ -r "$CLOUDFLARED_DIR/cert.pem" ]; then
        echo "Cloudflare login already has $CLOUDFLARED_DIR/cert.pem."
    else
        echo "Current ROTLD nameservers for $DOMAIN:"
        ns="$(registry_nameservers)"
        if [ -n "$ns" ]; then
            printf "%s\n" "$ns"
        else
            echo "<none found>"
        fi
        echo "Run Cloudflare login only after adding $DOMAIN to your Cloudflare account."
        if confirm "Run cloudflared tunnel login now?"; then
            cloudflared tunnel login || true
        fi
    fi
else
    echo "Skipping Cloudflare login because cloudflared is not installed."
fi

if confirm "Refresh setup reports now?"; then
    make setup-status
else
    echo "Refresh later with: make setup-status"
fi
