"""Builds API response models from DB rows (read side). No HTTP concerns."""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import schemas as S
from ..config import CRITERIA
from ..models import Demand, ImportRun, Project, Result
from . import discovery
from .metrics import STATUS_FAIL, STATUS_PASS, classify_change, delta_curve


class NotFound(Exception):
    pass


def criteria_out() -> S.Criteria:
    c = CRITERIA
    return S.Criteria(
        metric=c.metric, unit=c.unit, limit=c.limit, range_min=c.f_min, range_max=c.f_max,
        marginal_fraction=c.marginal_fraction, change_tolerance=c.change_tolerance,
        description=(f"A revision passes when its maximum magnitude for {c.f_min:g} ≤ f ≤ {c.f_max:g} Hz (inclusive) "
                     f"is at or below {c.limit:g} {c.unit}. Frequencies above {c.f_max:g} Hz are plotted but not assessed. "
                     "This is a data-review criterion, not a complete engineering safety assessment."),
    )


def explain(r: Result) -> str:
    rng = f"{r.range_min:g}–{r.range_max:g} Hz"
    if r.status == "not_assessable":
        return f"No samples within {rng}; the {r.limit_value:g} {r.unit} criterion cannot be evaluated."
    p = f"{r.peak_magnitude:g} {r.unit} at {r.peak_frequency:g} Hz"
    if r.status == STATUS_FAIL:
        return f"FAIL: peak {p} (within {rng}) exceeds the {r.limit_value:g} {r.unit} limit by {-r.margin:.2f} {r.unit}."
    if r.status == "incomplete":
        return f"INCONCLUSIVE: peak {p} is within the limit, but data ends at {r.freq_max:g} Hz, short of {r.range_max:g} Hz."
    extra = " (marginal)" if r.marginal else ""
    return f"PASS{extra}: peak {p} (within {rng}) is {r.margin:.2f} {r.unit} below the {r.limit_value:g} {r.unit} limit."


def summary(r: Result) -> S.ResultSummary:
    return S.ResultSummary(
        id=r.id, project=r.project.name, revision=r.revision.name, status=r.status, marginal=r.marginal,
        metric=CRITERIA.metric, unit=r.unit, limit=r.limit_value, range_min=r.range_min, range_max=r.range_max,
        peak_magnitude=r.peak_magnitude, peak_frequency=r.peak_frequency, margin=r.margin,
        samples_in_range=r.samples_in_range, sample_count=r.sample_count, freq_min=r.freq_min, freq_max=r.freq_max,
        overall_peak_magnitude=r.overall_peak_magnitude, overall_peak_frequency=r.overall_peak_frequency,
        explanation=explain(r), warnings=[S.WarningOut(**w) for w in (r.warnings or [])],
        sync_state=r.sync_state, sync_message=r.sync_message, source_path=r.source_path, file_hash=r.file_hash,
        data_version=r.data_version, imported_at=r.imported_at, updated_at=r.updated_at,
    )


def samples(r: Result) -> list[S.Sample]:
    return [S.Sample(frequency=s.frequency, magnitude=s.magnitude, in_range=r.range_min <= s.frequency <= r.range_max) for s in r.samples]


def get_project(db: Session, name: str) -> Project:
    p = db.scalar(select(Project).where(Project.name == name))
    if p is None:
        raise NotFound(f"Unknown project '{name}'")
    return p


def project_results(db: Session, project: Project) -> list[Result]:
    return sorted(project.results, key=lambda r: discovery.natural_key(r.revision.name))


def get_result(db: Session, project: str, revision: str) -> Result:
    p = get_project(db, project)
    for r in p.results:
        if r.revision.name == revision:
            return r
    raise NotFound(f"Project '{project}' has no result for revision '{revision}'")


def change(metric: str, unit: str, a: float | None, b: float | None, tol: float | None = None) -> S.Change:
    d = None if a is None or b is None else b - a
    pct = None if d is None or not a else d / a * 100
    cls = classify_change(d, tol) if tol is not None else None
    return S.Change(metric=metric, unit=unit, base=a, target=b, delta=d, delta_pct=pct, classification=cls)


def overall_trend(results: list[Result]) -> tuple[str, str]:
    """Compare first vs latest peak. Returns (code, sentence)."""
    if len(results) < 2:
        return "single", "Only one revision available; no trend yet."
    a, b = results[0], results[-1]
    ch = change("peak", a.unit, a.peak_magnitude, b.peak_magnitude, CRITERIA.change_tolerance)
    cls = ch.classification
    if cls == "unknown":
        return "unknown", "Trend cannot be computed (a revision has no in-range samples)."
    verb = {"improved": "improved", "degraded": "degraded", "unchanged": "is unchanged"}[cls]
    if cls == "unchanged":
        text = f"Peak {verb} from {a.revision.name} to {b.revision.name} ({a.peak_magnitude:g} {a.unit})."
    else:
        text = (f"Peak {verb} from {a.peak_magnitude:g} to {b.peak_magnitude:g} {a.unit} "
                f"({ch.delta:+.2f} {a.unit}, {ch.delta_pct:+.1f}%) between {a.revision.name} and {b.revision.name}.")
    if len(results) > 2:  # surface a reversal hidden by the first-vs-latest summary
        p = results[-2]
        last = change("peak", a.unit, p.peak_magnitude, b.peak_magnitude, CRITERIA.change_tolerance)
        if last.classification not in (cls, "unknown"):
            text += (f" However, the latest step {p.revision.name} → {b.revision.name} {last.classification} "
                     f"({last.delta:+.2f} {a.unit}).")
    return cls, text


def projects_list(db: Session) -> list[S.ProjectOut]:
    open_counts = dict(db.execute(select(Demand.project_id, func.count()).where(Demand.status != "Resolved").group_by(Demand.project_id)).all())
    out = []
    for p in db.scalars(select(Project).order_by(Project.name)).all():
        rs = project_results(db, p)
        latest = rs[-1] if rs else None
        out.append(S.ProjectOut(
            name=p.name, image_url=f"/api/projects/{p.name}/image" if p.image_path else None,
            revisions=[S.RevisionRef(name=r.revision.name, status=r.status, marginal=r.marginal, peak_magnitude=r.peak_magnitude,
                                     peak_frequency=r.peak_frequency, sync_state=r.sync_state) for r in rs],
            latest_revision=latest.revision.name if latest else None, latest_status=latest.status if latest else None,
            trend=overall_trend(rs)[0] if rs else "single", open_demands=open_counts.get(p.id, 0),
        ))
    return out


def revision_result(db: Session, project: str, revision: str) -> S.RevisionResult:
    r = get_result(db, project, revision)
    return S.RevisionResult(summary=summary(r), samples=samples(r))


def compare(db: Session, project: str, base: str, target: str) -> S.Comparison:
    a, b = get_result(db, project, base), get_result(db, project, target)
    u, tol = a.unit, CRITERIA.change_tolerance
    changes = [
        change("Peak magnitude (in range)", u, a.peak_magnitude, b.peak_magnitude, tol),
        change("Peak frequency", "Hz", a.peak_frequency, b.peak_frequency),
        change("Margin to limit", u, a.margin, b.margin),
        change("Overall peak magnitude (0–max Hz)", u, a.overall_peak_magnitude, b.overall_peak_magnitude, tol),
    ]
    fa, ma = [s.frequency for s in a.samples], [s.magnitude for s in a.samples]
    fb, mb = [s.frequency for s in b.samples], [s.magnitude for s in b.samples]
    dc = delta_curve(fa, ma, fb, mb)
    inr = [d for d in dc if a.range_min <= d["frequency"] <= a.range_max]
    largest = max(inr, key=lambda d: abs(d["delta"])) if inr else None

    sc = f"{a.status} → {b.status}" if a.status != b.status else f"{a.status} (no change)"
    overall = changes[0].classification or "unknown"
    pk = changes[0]
    if pk.delta is None:
        verdict = "Cannot compare peaks: one revision has no samples in the assessment range."
    else:
        verdict = (f"{b.revision.name} vs {a.revision.name}: in-range peak {overall} "
                   f"({a.peak_magnitude:g} → {b.peak_magnitude:g} {u}, {pk.delta:+.2f} {u}); "
                   f"assessment {a.status.upper()} → {b.status.upper()}." if a.status != b.status else
                   f"{b.revision.name} vs {a.revision.name}: in-range peak {overall} "
                   f"({a.peak_magnitude:g} → {b.peak_magnitude:g} {u}, {pk.delta:+.2f} {u}); assessment stays {a.status.upper()}.")
    notes = []
    if a.limit_value != b.limit_value or (a.range_min, a.range_max) != (b.range_min, b.range_max):
        notes.append("The two results were assessed against different criteria; metrics are not directly comparable.")
    if fa != fb:
        notes.append(f"Frequency grids differ ({a.sample_count} vs {b.sample_count} samples), so the delta curve uses linear interpolation; "
                     "treat it as approximate near sharp resonances.")
    if pk.delta is not None and abs(pk.delta) <= tol:
        notes.append("Peak change is within the noise floor of the 0.1 mm CSV resolution.")
    return S.Comparison(
        project=project, base=summary(a), target=summary(b), changes=changes, status_change=sc, overall=overall, verdict=verdict,
        base_samples=samples(a), target_samples=samples(b), delta_curve=[S.DeltaPoint(**d) for d in dc],
        delta_curve_note="Δ = target − base, linearly interpolated onto the union of both frequency grids over their overlap.",
        largest_in_range_change=S.DeltaPoint(**largest) if largest else None, notes=notes,
    )


def history(db: Session, project: str) -> S.History:
    p = get_project(db, project)
    rs = project_results(db, p)
    demands_by_rev: dict[int, list[int]] = {}
    for d in db.scalars(select(Demand).where(Demand.project_id == p.id)).all():
        for r in rs:
            demands_by_rev.setdefault(r.id, []).append(d.id)
    tol = CRITERIA.change_tolerance
    steps = []
    for i, r in enumerate(rs):
        prev = rs[i - 1] if i else None
        steps.append(S.HistoryStep(
            summary=summary(r),
            vs_previous=change("Peak magnitude (in range)", r.unit, prev.peak_magnitude, r.peak_magnitude, tol) if prev else None,
            vs_first=change("Peak magnitude (in range)", r.unit, rs[0].peak_magnitude, r.peak_magnitude, tol) if i > 1 else None,
            demand_ids=demands_by_rev.get(r.id, []),
        ))
    code, text = overall_trend(rs) if rs else ("single", "No revisions.")
    return S.History(project=project, steps=steps, trend=code, trend_text=text)


def import_run_out(run: ImportRun) -> S.ImportRunOut:
    return S.ImportRunOut(
        id=run.id, trigger=run.trigger, started_at=run.started_at, finished_at=run.finished_at, input_dir=run.input_dir,
        files_found=run.files_found, created=run.created, updated=run.updated, unchanged=run.unchanged, failed=run.failed,
        missing=run.missing, issues=[S.IssueOut(path=i.path, severity=i.severity, message=i.message) for i in run.issues],
    )
