from __future__ import annotations

import base64
import hashlib
import hmac
import os
from dataclasses import dataclass
from typing import Annotated, Optional

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import new_secret_token
from app.core.db import get_db
from app.core.write_lock import commit_write
from app.models.entities import Setting, Worker

try:
    import bcrypt
except ImportError:  # pragma: no cover - dependency is declared, fallback keeps tests importable.
    bcrypt = None


USER_TOKEN_SETTING = "user_token_hash"


@dataclass
class AuthContext:
    token: str


def hash_token(token: str) -> str:
    if bcrypt is not None:
        return "bcrypt$" + bcrypt.hashpw(token.encode(), bcrypt.gensalt(rounds=12)).decode()
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", token.encode(), salt, 260_000)
    return "pbkdf2_sha256$" + base64.b64encode(salt).decode() + "$" + base64.b64encode(digest).decode()


def verify_token(token: str, token_hash: str) -> bool:
    if token_hash.startswith("bcrypt$") and bcrypt is not None:
        return bool(bcrypt.checkpw(token.encode(), token_hash.removeprefix("bcrypt$").encode()))
    if token_hash.startswith("pbkdf2_sha256$"):
        _, salt_b64, digest_b64 = token_hash.split("$", 2)
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(digest_b64)
        actual = hashlib.pbkdf2_hmac("sha256", token.encode(), salt, 260_000)
        return hmac.compare_digest(actual, expected)
    return False


def bearer_token(authorization: Annotated[Optional[str], Header()] = None) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer token required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return authorization.removeprefix("Bearer ").strip()


def require_user_token(
    token: Annotated[str, Depends(bearer_token)],
    db: Annotated[Session, Depends(get_db)],
) -> AuthContext:
    setting = db.get(Setting, USER_TOKEN_SETTING)
    if not setting or not verify_token(token, str(setting.value["hash"])):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid user token")
    return AuthContext(token=token)


def require_worker(
    worker_id: str,
    token: Annotated[str, Depends(bearer_token)],
    db: Annotated[Session, Depends(get_db)],
) -> Worker:
    worker = db.get(Worker, worker_id)
    if not worker or not verify_token(token, worker.token_hash):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid worker token")
    return worker


def require_worker_header(
    x_worker_id: Annotated[Optional[str], Header(alias="X-Worker-ID")] = None,
    token: Annotated[str, Depends(bearer_token)] = "",
    db: Annotated[Session, Depends(get_db)] = None,  # type: ignore[assignment]
) -> Worker:
    if not x_worker_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="X-Worker-ID header required")
    worker = db.get(Worker, x_worker_id)
    if not worker or not verify_token(token, worker.token_hash):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid worker token")
    return worker


def ensure_user_token(db: Session, explicit_token: str | None = None) -> str | None:
    existing = db.get(Setting, USER_TOKEN_SETTING)
    if existing:
        return None
    token = explicit_token or new_secret_token("user")
    db.add(Setting(key=USER_TOKEN_SETTING, value={"hash": hash_token(token)}))
    commit_write(db)
    return token
