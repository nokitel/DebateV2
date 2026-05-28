from __future__ import annotations

import os


def is_placeholder_secret(value: str) -> bool:
    return "<" in value or ">" in value


def configured_api_key(name: str) -> str | None:
    value = os.getenv(name, "").strip()
    if not value or is_placeholder_secret(value):
        return None
    return value
