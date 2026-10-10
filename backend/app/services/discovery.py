"""Find revision folders / project CSVs on disk. Nothing here knows about the DB."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DiscoveredFile:
    revision: str
    project: str
    path: Path
    rel_path: str


@dataclass(frozen=True)
class DiscoveryProblem:
    path: str
    message: str
    severity: str = "warning"  # warning | error


def natural_key(name: str) -> list:
    """'rev2' < 'rev10'."""
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", name)]


def discover(root: Path) -> tuple[list[DiscoveredFile], list[DiscoveryProblem]]:
    files: list[DiscoveredFile] = []
    problems: list[DiscoveryProblem] = []
    if not root.is_dir():
        return files, [DiscoveryProblem(str(root), "Input directory does not exist or is not a directory", "error")]
    for entry in sorted(root.iterdir(), key=lambda p: natural_key(p.name)):
        if entry.name.startswith("."):
            continue
        if entry.is_file():
            if entry.suffix.lower() == ".csv":
                problems.append(DiscoveryProblem(entry.name, "CSV is not inside a revision folder (expected <revision>/<Project>.csv); ignored"))
            continue
        if not entry.is_dir():
            continue
        csvs = [p for p in sorted(entry.iterdir()) if p.is_file() and p.suffix.lower() == ".csv" and not p.name.startswith(".")]
        if not csvs:
            problems.append(DiscoveryProblem(entry.name, "Revision folder contains no CSV files"))
        for p in csvs:
            files.append(DiscoveredFile(entry.name, p.stem, p, f"{entry.name}/{p.name}"))
    return files, problems


def find_project_image(root: Path, project: str) -> str | None:
    for ext in (".png", ".jpg", ".jpeg", ".webp"):
        cand = root / f"{project}{ext}"
        if cand.is_file():
            return cand.name
    return None
