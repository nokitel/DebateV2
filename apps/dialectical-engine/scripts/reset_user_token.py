from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "coordinator"))

from app.core.auth import USER_TOKEN_SETTING, hash_token
from app.core.config import ensure_home, load_settings, new_secret_token
from app.core.db import SessionLocal, init_db
from app.core.write_lock import commit_write
from app.models.entities import Setting


def reset_user_token(token: str | None = None) -> str:
    settings = load_settings()
    ensure_home(settings)
    init_db()
    token = token or new_secret_token("user")
    with SessionLocal() as db:
        setting = db.get(Setting, USER_TOKEN_SETTING)
        if setting:
            setting.value = {"hash": hash_token(token)}
        else:
            db.add(Setting(key=USER_TOKEN_SETTING, value={"hash": hash_token(token)}))
        commit_write(db)
    return token


def main() -> int:
    parser = argparse.ArgumentParser(description="Rotate the Dialectical Engine user bearer token")
    parser.add_argument("--token", help="Optional explicit token. Omit to generate a new secure token.")
    args = parser.parse_args()
    token = reset_user_token(args.token)
    print("Dialectical Engine user token:", token)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
