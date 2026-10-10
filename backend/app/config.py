"""Runtime configuration and the engineering review criterion.

The criterion lives in one place so that it is never duplicated between the
metric code, the API and the UI (the UI reads it from ``GET /api/criteria``).
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Criteria:
    """Displacement review rule: max magnitude within [f_min, f_max] <= limit."""

    metric: str = "Peak displacement magnitude"
    unit: str = "mm"
    limit: float = 15.0
    f_min: float = 0.0
    f_max: float = 50.0  # inclusive
    # Passing by less than this fraction of the limit is flagged as "marginal":
    # the CSVs are sparsely sampled so the true peak may sit between samples.
    marginal_fraction: float = 0.10
    # Changes in peak smaller than this are reported as "unchanged" (the CSV
    # resolution is 0.1 mm, so half a resolution step is the noise floor).
    change_tolerance: float = 0.05

    def key(self) -> str:
        return f"{self.limit}|{self.f_min}|{self.f_max}|{self.unit}"


CRITERIA = Criteria()


@dataclass(frozen=True)
class Settings:
    input_dir: Path
    database_url: str
    sync_on_startup: bool
    frontend_dist: Path


def get_settings() -> Settings:
    return Settings(
        input_dir=Path(os.environ.get("SIM_INPUT_DIR", REPO_ROOT / "Inputs")).resolve(),
        database_url=os.environ.get(
            "SIM_DATABASE_URL", f"sqlite:///{REPO_ROOT / 'backend' / 'data' / 'dashboard.db'}"
        ),
        sync_on_startup=os.environ.get("SIM_SYNC_ON_STARTUP", "1") != "0",
        frontend_dist=Path(os.environ.get("SIM_FRONTEND_DIST", REPO_ROOT / "frontend" / "dist")),
    )
