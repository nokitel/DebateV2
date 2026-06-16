#!/bin/sh
set -eu

DOMAIN="${DOMAIN:-dezbatere.ro}"
WWW_DOMAIN="${WWW_DOMAIN:-www.$DOMAIN}"
TUNNEL_NAME="${TUNNEL_NAME:-dialectical}"
SERVICE_URL="${SERVICE_URL:-http://127.0.0.1:3000}"
STATUS_URL="${STATUS_URL:-$SERVICE_URL/api/backends/status}"
CLOUDFLARED="${CLOUDFLARED:-cloudflared}"
CLOUDFLARED_DIR="${CLOUDFLARED_DIR:-$HOME/.cloudflared}"
CONFIG_PATH="${CONFIG_PATH:-$CLOUDFLARED_DIR/config.yml}"
LAUNCH_AGENT="${LAUNCH_AGENT:-$HOME/Library/LaunchAgents/com.dialectical.cloudflared.plist}"
INSTALL_SERVICE="${INSTALL_SERVICE:-0}"
STOP_QUICK_TUNNEL="${STOP_QUICK_TUNNEL:-0}"
SKIP_DNS_PREFLIGHT="${SKIP_DNS_PREFLIGHT:-0}"
SKIP_SERVICE_PREFLIGHT="${SKIP_SERVICE_PREFLIGHT:-0}"

need() {
    if ! command -v "$1" >/dev/null 2>&1; then
        echo "missing required command: $1" >&2
        exit 2
    fi
}

need "$CLOUDFLARED"
need python3
need dig
need curl

is_cloudflare_delegation() {
    ns="$1"
    [ -n "$ns" ] || return 1
    printf '%s\n' "$ns" | awk '
        NF {
            total += 1
            lower = tolower($0)
            if (lower ~ /\.ns\.cloudflare\.com\.$/) cloudflare += 1
        }
        END { exit !(total > 0 && cloudflare == total) }
    '
}

tunnel_id_from_json() {
    TUNNEL_JSON="$1" python3 - "$TUNNEL_NAME" <<'PY'
import json
import os
import sys

name = sys.argv[1]
data = json.loads(os.environ.get("TUNNEL_JSON") or "[]") or []
if not isinstance(data, list):
    data = []


def is_active(item):
    deleted_at = str(item.get("deleted_at") or "")
    return not deleted_at or deleted_at.startswith("0001-01-01")


for item in data:
    if item.get("name") == name and is_active(item):
        print(item.get("id") or "")
        break
else:
    print("")
PY
}

mkdir -p "$CLOUDFLARED_DIR"

if [ "$SKIP_SERVICE_PREFLIGHT" != "1" ] && [ "$SKIP_SERVICE_PREFLIGHT" != "true" ] && [ "$SKIP_SERVICE_PREFLIGHT" != "yes" ]; then
    if ! curl -fsS "$STATUS_URL" >/dev/null; then
        echo "Local web app is not ready for tunnel setup." >&2
        echo "Failed status URL: $STATUS_URL" >&2
        echo "Run this first:" >&2
        echo "  make local-status" >&2
        echo "Set SKIP_SERVICE_PREFLIGHT=1 only if you intentionally want to write tunnel config before the app is reachable." >&2
        exit 2
    fi
fi

if [ "$SKIP_DNS_PREFLIGHT" != "1" ] && [ "$SKIP_DNS_PREFLIGHT" != "true" ] && [ "$SKIP_DNS_PREFLIGHT" != "yes" ]; then
    registry_ns="$(dig @primary.rotld.ro "$DOMAIN" NS 2>/dev/null | awk 'toupper($4)=="NS" {print $5}' | sort -u || true)"
    if ! is_cloudflare_delegation "$registry_ns"; then
        echo "$DOMAIN is not delegated to Cloudflare yet." >&2
        echo "Current registry nameservers:" >&2
        if [ -n "$registry_ns" ]; then
            printf '%s\n' "$registry_ns" >&2
        else
            echo "  <none found>" >&2
        fi
        if printf '%s\n' "$registry_ns" | grep -qi '\.romarg\.com\.$'; then
            echo "Add $DOMAIN to Cloudflare, then replace all Romarg nameservers with only the assigned Cloudflare nameservers." >&2
            echo "See Cloudfare_TODO.md and Romarg_TODO.md." >&2
        else
            echo "Check the nameservers entered at Romarg; every nameserver must end with .ns.cloudflare.com." >&2
        fi
        echo "Set SKIP_DNS_PREFLIGHT=1 only if you intentionally want to create the tunnel before DNS delegation changes." >&2
        exit 2
    fi
fi

if [ ! -r "$CLOUDFLARED_DIR/cert.pem" ]; then
    echo "Cloudflare origin certificate missing: $CLOUDFLARED_DIR/cert.pem" >&2
    echo "Run this first, complete the browser login, and make sure dezbatere.ro is active in Cloudflare:" >&2
    echo "  $CLOUDFLARED tunnel login" >&2
    exit 2
fi

tunnel_json="$($CLOUDFLARED tunnel list --output json)"
tunnel_id="$(tunnel_id_from_json "$tunnel_json")"

if [ -z "$tunnel_id" ]; then
    echo "Creating Cloudflare tunnel: $TUNNEL_NAME"
    $CLOUDFLARED tunnel create "$TUNNEL_NAME"
    tunnel_json="$($CLOUDFLARED tunnel list --output json)"
    tunnel_id="$(tunnel_id_from_json "$tunnel_json")"
fi

if [ -z "$tunnel_id" ]; then
    echo "could not determine tunnel id for $TUNNEL_NAME" >&2
    exit 2
fi

credentials_file="$CLOUDFLARED_DIR/$tunnel_id.json"
if [ ! -r "$credentials_file" ]; then
    echo "tunnel credentials missing: $credentials_file" >&2
    exit 2
fi

echo "Routing $DOMAIN to tunnel $TUNNEL_NAME"
$CLOUDFLARED tunnel route dns "$TUNNEL_NAME" "$DOMAIN"
echo "Routing $WWW_DOMAIN to tunnel $TUNNEL_NAME"
$CLOUDFLARED tunnel route dns "$TUNNEL_NAME" "$WWW_DOMAIN"

if [ -f "$CONFIG_PATH" ]; then
    backup="$CONFIG_PATH.$(date +%Y%m%d%H%M%S).bak"
    cp "$CONFIG_PATH" "$backup"
    echo "Backed up existing config to $backup"
fi

cat >"$CONFIG_PATH" <<EOF
tunnel: $TUNNEL_NAME
credentials-file: $credentials_file

ingress:
  - hostname: $DOMAIN
    service: $SERVICE_URL
  - hostname: $WWW_DOMAIN
    service: $SERVICE_URL
  - service: http_status:404
EOF

chmod 600 "$CONFIG_PATH"
echo "Wrote $CONFIG_PATH"

mkdir -p "$(dirname "$LAUNCH_AGENT")"
cat >"$LAUNCH_AGENT" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.dialectical.cloudflared</string>
  <key>ProgramArguments</key>
  <array>
    <string>$(command -v "$CLOUDFLARED")</string>
    <string>tunnel</string>
    <string>--config</string>
    <string>$CONFIG_PATH</string>
    <string>run</string>
    <string>$TUNNEL_NAME</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>/tmp/dialectical-cloudflared.out.log</string>
  <key>StandardErrorPath</key>
  <string>/tmp/dialectical-cloudflared.err.log</string>
</dict>
</plist>
EOF

plutil -lint "$LAUNCH_AGENT"
echo "Wrote $LAUNCH_AGENT"

if [ "$INSTALL_SERVICE" = "1" ] || [ "$INSTALL_SERVICE" = "true" ] || [ "$INSTALL_SERVICE" = "yes" ]; then
    launchctl unload "$LAUNCH_AGENT" >/dev/null 2>&1 || true
    launchctl load "$LAUNCH_AGENT"
    echo "Loaded com.dialectical.cloudflared"
fi

if [ "$STOP_QUICK_TUNNEL" = "1" ] || [ "$STOP_QUICK_TUNNEL" = "true" ] || [ "$STOP_QUICK_TUNNEL" = "yes" ]; then
    quick_agent="$HOME/Library/LaunchAgents/com.dialectical.cloudflared-quick.plist"
    if [ -f "$quick_agent" ]; then
        launchctl unload "$quick_agent" >/dev/null 2>&1 || true
        echo "Unloaded com.dialectical.cloudflared-quick"
    fi
fi

echo "Next checks:"
echo "  curl -I https://$DOMAIN/"
echo "  curl https://$DOMAIN/api/backends/status"
