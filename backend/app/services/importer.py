"""CSV -> database synchronisation.

Idempotent: each file is identified by (revision folder, project name) and a
SHA-256 of its bytes. Same hash => skipped. Different hash => the Result row is
updated in place (its id, and therefore demand links, are preserved) and the
samples are replaced inside one transaction. Bad files never partially import.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..config import CRITERIA, Criteria, Settings
from ..models import ImportIssue, ImportRun, Project, Result, Revision, Sample, utcnow
from . import discovery
from .metrics import Assessment, assess
from .parsing import CsvValidationError, parse_curve_csv


@dataclass
class SyncReport:
    run_id: int
    created: int
    updated: int
    unchanged: int
    failed: int
    missing: int
    recomputed: int


def _apply_assessment(r: Result, a: Assessment, c: Criteria, extra_warnings: list[dict]) -> None:
    r.criteria_key = c.key()
    r.limit_value, r.range_min, r.range_max, r.unit = c.limit, c.f_min, c.f_max, c.unit
    r.samples_in_range = a.samples_in_range
    r.peak_magnitude, r.peak_frequency, r.margin = a.peak_magnitude, a.peak_frequency, a.margin
    r.status, r.marginal = a.status, a.marginal
    r.overall_peak_magnitude, r.overall_peak_frequency = a.overall_peak_magnitude, a.overall_peak_frequency
    r.warnings = extra_warnings + [w.as_dict() for w in a.warnings]


def _get_or_create(db: Session, model, name: str):
    obj = db.scalar(select(model).where(model.name == name))
    if obj is None:
        obj = model(name=name)
        db.add(obj)
        db.flush()
    return obj


def sync(db: Session, settings: Settings, trigger: str = "api", criteria: Criteria = CRITERIA) -> SyncReport:
    run = ImportRun(trigger=trigger, input_dir=str(settings.input_dir))
    db.add(run)
    db.flush()

    files, problems = discovery.discover(settings.input_dir)
    run.files_found = len(files)
    for p in problems:
        db.add(ImportIssue(run_id=run.id, path=p.path, severity=p.severity, message=p.message))
        if p.severity == "error":
            run.failed += 1

    seen: set[tuple[str, str]] = set()
    for f in files:
        seen.add((f.revision, f.project))
        # Each file gets its own savepoint: one bad file must not poison the batch.
        sp = db.begin_nested()
        try:
            raw = f.path.read_bytes()
            digest = hashlib.sha256(raw).hexdigest()
            st = f.path.stat()

            project = db.scalar(select(Project).where(Project.name == f.project))
            revision = db.scalar(select(Revision).where(Revision.name == f.revision))
            existing = None
            if project and revision:
                existing = db.scalar(select(Result).where(Result.project_id == project.id, Result.revision_id == revision.id))

            if existing and existing.file_hash == digest:
                if existing.sync_state != "ok":
                    existing.sync_state, existing.sync_message = "ok", None
                existing.source_path = f.rel_path
                existing.file_mtime = st.st_mtime
                sp.commit()
                run.unchanged += 1
                continue

            curve = parse_curve_csv(raw)  # may raise CsvValidationError
            a = assess(curve.frequencies, curve.magnitudes, criteria)
            file_warnings = [{"code": "FILE", "severity": "info", "message": w} for w in curve.warnings]

            project = project or _get_or_create(db, Project, f.project)
            revision = revision or _get_or_create(db, Revision, f.revision)
            if existing is None:
                r = Result(project_id=project.id, revision_id=revision.id, source_path=f.rel_path, file_hash=digest,
                           file_size=len(raw), file_mtime=st.st_mtime, sample_count=len(curve.frequencies),
                           freq_min=curve.frequencies[0], freq_max=curve.frequencies[-1],
                           overall_peak_magnitude=0, overall_peak_frequency=0, criteria_key="", limit_value=0,
                           range_min=0, range_max=0, unit="", samples_in_range=0, status="", warnings=[])
                db.add(r)
                run.created += 1
            else:
                r = existing
                db.execute(delete(Sample).where(Sample.result_id == r.id))
                r.data_version += 1
                run.updated += 1
            r.source_path, r.file_hash, r.file_size, r.file_mtime = f.rel_path, digest, len(raw), st.st_mtime
            r.sample_count = len(curve.frequencies)
            r.freq_min, r.freq_max = curve.frequencies[0], curve.frequencies[-1]
            r.updated_at = utcnow()
            r.sync_state, r.sync_message = "ok", None
            _apply_assessment(r, a, criteria, file_warnings)
            db.flush()
            db.bulk_insert_mappings(Sample, [
                {"result_id": r.id, "frequency": x, "magnitude": y} for x, y in zip(curve.frequencies, curve.magnitudes)
            ])
            if project.image_path is None:
                project.image_path = discovery.find_project_image(settings.input_dir, f.project)
            sp.commit()
        except (CsvValidationError, OSError) as e:
            sp.rollback()
            msg = "; ".join(e.problems) if isinstance(e, CsvValidationError) else f"Could not read file: {e}"
            run.failed += 1
            db.add(ImportIssue(run_id=run.id, path=f.rel_path, severity="error", message=msg))
            # Keep the last good data, but never let it look current.
            prev = db.scalar(select(Result).join(Project).join(Revision).where(Project.name == f.project, Revision.name == f.revision))
            if prev is not None:
                prev.sync_state = "stale_error"
                prev.sync_message = f"Latest file on disk was rejected ({msg}). Showing the last successfully imported data."
        except Exception as e:  # defensive: never abort the whole sync
            sp.rollback()
            run.failed += 1
            db.add(ImportIssue(run_id=run.id, path=f.rel_path, severity="error", message=f"Unexpected error: {e!r}"))

    # files that vanished from disk
    for r in db.scalars(select(Result)).all():
        key = (r.revision.name, r.project.name)
        if key not in seen:
            if r.sync_state != "source_missing":
                r.sync_state = "source_missing"
                r.sync_message = f"Source file {r.source_path} no longer exists in the input directory."
            run.missing += 1
            db.add(ImportIssue(run_id=run.id, path=r.source_path, severity="warning", message="Previously imported file is missing from disk; stored data kept."))

    recomputed = recompute_stale_criteria(db, criteria)
    for p in db.scalars(select(Project).where(Project.image_path.is_(None))).all():
        p.image_path = discovery.find_project_image(settings.input_dir, p.name)

    run.finished_at = utcnow()
    db.commit()
    return SyncReport(run.id, run.created, run.updated, run.unchanged, run.failed, run.missing, recomputed)


def recompute_stale_criteria(db: Session, criteria: Criteria = CRITERIA) -> int:
    """If the configured criterion changed, recompute summaries from stored samples."""
    n = 0
    for r in db.scalars(select(Result).where(Result.criteria_key != criteria.key())).all():
        fs = [s.frequency for s in r.samples]
        ms = [s.magnitude for s in r.samples]
        file_w = [w for w in (r.warnings or []) if w.get("code") == "FILE"]
        _apply_assessment(r, assess(fs, ms, criteria), criteria, file_w)
        n += 1
    return n
