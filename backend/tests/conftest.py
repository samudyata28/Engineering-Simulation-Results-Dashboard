from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import REPO_ROOT, Settings
from app.db import init_db, make_engine, make_session_factory
from app.main import create_app

HEADER = "Frequency [Hz],Magnitude [mm]\n"


def write_csv(path: Path, rows, header: str = HEADER):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(header + "".join(f"{f},{m}\n" for f, m in rows))


@pytest.fixture
def inputs(tmp_path) -> Path:
    """A private copy of the real supplied data."""
    dst = tmp_path / "Inputs"
    shutil.copytree(REPO_ROOT / "Inputs", dst)
    return dst


def make_settings(tmp_path, inputs, sync=False) -> Settings:
    return Settings(input_dir=inputs, database_url=f"sqlite:///{tmp_path / 'test.db'}", sync_on_startup=sync,
                    frontend_dist=tmp_path / "no-dist")


@pytest.fixture
def settings(tmp_path, inputs):
    return make_settings(tmp_path, inputs)


@pytest.fixture
def db(settings):
    engine = make_engine(settings.database_url)
    init_db(engine)
    with make_session_factory(engine)() as s:
        yield s


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as c:
        yield c


@pytest.fixture
def synced(client):
    r = client.post("/api/import")
    assert r.status_code == 200
    return client
