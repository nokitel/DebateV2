from __future__ import annotations

import os
import tempfile

TEST_HOME = tempfile.mkdtemp(prefix="dialectical-test-")
os.environ["DIALECTICAL_HOME"] = TEST_HOME
os.environ["DIALECTICAL_DATABASE_URL"] = f"sqlite:///{TEST_HOME}/test.sqlite3"
os.environ["DIALECTICAL_USER_TOKEN"] = "user_test_token"

import pytest

from app.core.auth import ensure_user_token
from app.core.db import Base, SessionLocal, engine, init_db


@pytest.fixture()
def db():
    init_db()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as session:
        ensure_user_token(session, "user_test_token")
        yield session

