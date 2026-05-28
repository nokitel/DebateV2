#!/bin/sh
set -eu

DOMAIN="${DOMAIN:-dezbatere.ro}"
CLOUDFLARED="${CLOUDFLARED:-cloudflared}"
CLOUDFLARED_DIR="${CLOUDFLARED_DIR:-$HOME/.cloudflared}"
SERVICE_URL="${SERVICE_URL:-http://127.0.0.1:3000}"
STATUS_URL="${STATUS_URL:-$SERVICE_URL/api/backends/status}"

need() {
    if ! command -v "$1" >/dev/null 2>&1; then
        echo "missing required command: $1" >&2
        exit 2
    fi
}

need dig
need curl
need "$CLOUDFLARED"

if ! curl -fsS "$STATUS_URL" >/dev/null; then
    echo "Local web app is not ready for tunnel setup." >&2
    echo "Failed status URL: $STATUS_URL" >&2
    echo "Next:" >&2
    echo "  make local-status" >&2
    echo "Then rerun:" >&2
    echo "  make resume-dezbatere-hosting" >&2
    exit 2
fi

registry_ns="$(dig @primary.rotld.ro "$DOMAIN" NS 2>/dev/null | awk 'toupper($4)=="NS" {print $5}' | sort -u || true)"

if ! printf '%s\n' "$registry_ns" | grep -qi '\.ns\.cloudflare\.com\.$'; then
    echo "$DOMAIN is not delegated to Cloudflare yet." >&2
    echo "Current ROTLD nameservers:" >&2
    if [ -n "$registry_ns" ]; then
        printf '%s\n' "$registry_ns" >&2
    else
        echo "  <none found>" >&2
    fi
    echo "Next:" >&2
    echo "  1. Add $DOMAIN to Cloudflare and copy the assigned nameservers." >&2
    echo "  2. Replace the nameservers in Romarg." >&2
    echo "  3. Run: make wait-dezbatere-dns" >&2
    exit 2
fi

if [ ! -r "$CLOUDFLARED_DIR/cert.pem" ]; then
    echo "Cloudflare login is not complete on this Mac." >&2
    echo "Missing: $CLOUDFLARED_DIR/cert.pem" >&2
    echo "Next:" >&2
    echo "  cloudflared tunnel login" >&2
    echo "Then rerun:" >&2
    echo "  make resume-dezbatere-hosting" >&2
    exit 2
fi

./scripts/setup_dezbatere_tunnel.sh

echo "Hosting resume completed."
echo "If the manual HTTPS checks pass, install the named tunnel service with:"
echo "  INSTALL_SERVICE=1 STOP_QUICK_TUNNEL=1 make resume-dezbatere-hosting"
