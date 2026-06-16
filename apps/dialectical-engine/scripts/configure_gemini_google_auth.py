#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


DEFAULT_SETTINGS = Path("~/.gemini/settings.json").expanduser()
GOOGLE_OAUTH_AUTH_TYPE = "oauth-personal"


def set_nested(payload: dict[str, Any], dotted_key: str, value: Any) -> None:
    current = payload
    parts = dotted_key.split(".")
    for part in parts[:-1]:
        child = current.get(part)
        if not isinstance(child, dict):
            child = {}
            current[part] = child
        current = child
    current[parts[-1]] = value


def load_settings(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Set Gemini CLI to use Google-account OAuth for non-interactive local testing."
    )
    parser.add_argument("--settings", type=Path, default=DEFAULT_SETTINGS)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    settings_path = args.settings.expanduser()
    settings = load_settings(settings_path)
    before = json.dumps(settings, indent=2, sort_keys=True)

    # The Gemini CLI has used both locations across versions. Writing both keeps
    # this harmless preference compatible without adding API keys or tokens.
    settings["selectedAuthType"] = GOOGLE_OAUTH_AUTH_TYPE
    set_nested(settings, "security.auth.selectedType", GOOGLE_OAUTH_AUTH_TYPE)

    after = json.dumps(settings, indent=2, sort_keys=True) + "\n"
    if args.dry_run:
        print(after, end="")
        return 0

    settings_path.parent.mkdir(parents=True, exist_ok=True)
    if settings_path.exists() and before != after.rstrip():
        backup = settings_path.with_suffix(settings_path.suffix + ".bak")
        backup.write_text(settings_path.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"Backed up existing settings to {backup}")
    settings_path.write_text(after, encoding="utf-8")
    print(f"Set Gemini CLI auth method to {GOOGLE_OAUTH_AUTH_TYPE} in {settings_path}")
    print("Next: run `gemini` once interactively and choose Login with Google if prompted.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
