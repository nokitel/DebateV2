from __future__ import annotations

from threading import RLock

from sqlalchemy.orm import Session

_write_lock = RLock()


def flush_write(db: Session) -> None:
    with _write_lock:
        db.flush()


def commit_write(db: Session) -> None:
    with _write_lock:
        db.commit()
