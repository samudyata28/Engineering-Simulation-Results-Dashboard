"""Demand (engineering follow-up) logic."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import schemas as S
from ..config import CRITERIA
from ..models import Demand, DemandEvent, Project, Result, utcnow
from . import views
from .metrics import STATUS_FAIL, STATUS_PASS, classify_change

STATUSES = ("Open", "In Progress", "Resolved")


class DemandError(Exception):
    def __init__(self, message: str, status_code: int = 422, existing_id: int | None = None):
        super().__init__(message)
        self.message, self.status_code, self.existing_id = message, status_code, existing_id


def create_demand(db: Session, project_name: str, description: str, origin_revision: str | None = None) -> Demand:
    project = views.get_project(db, project_name)
    d = Demand(project_id=project.id, description=description.strip(), status="Open")
    if origin_revision:
        r = views.get_result(db, project_name, origin_revision)
        if r.status != STATUS_FAIL:
            raise DemandError(
                f"{project_name} {origin_revision} is '{r.status}', not a failed finding. "
                "Create a manual demand (omit origin_revision) if follow-up is still needed.")
        dup = db.scalar(select(Demand).where(Demand.origin_result_id == r.id, Demand.status != "Resolved"))
        if dup:
            raise DemandError(f"An unresolved demand (#{dup.id}) already exists for this finding.", 409, dup.id)
        d.origin_result_id = r.id
        d.origin_revision = r.revision.name
        d.origin_metric = f"{CRITERIA.metric} within {r.range_min:g}–{r.range_max:g} Hz"
        d.origin_value, d.origin_frequency = r.peak_magnitude, r.peak_frequency
        d.origin_limit, d.origin_unit = r.limit_value, r.unit
        d.origin_range_min, d.origin_range_max = r.range_min, r.range_max
    db.add(d)
    db.flush()
    where = f"from {origin_revision} finding" if origin_revision else "manually"
    db.add(DemandEvent(demand_id=d.id, kind="created", detail=f"Created {where}"))
    db.commit()
    return d


def update_demand(db: Session, demand_id: int, description: str | None, status: str | None) -> Demand:
    d = db.get(Demand, demand_id)
    if d is None:
        raise views.NotFound(f"Demand {demand_id} not found")
    if description is not None and description.strip() != d.description:
        db.add(DemandEvent(demand_id=d.id, kind="description", detail="Description edited"))
        d.description = description.strip()
    if status is not None and status != d.status:
        db.add(DemandEvent(demand_id=d.id, kind="status", detail=f"{d.status} → {status}"))
        d.status = status
    d.updated_at = utcnow()
    db.commit()
    return d


def _linked(r: Result, d: Demand) -> S.LinkedResult:
    delta = None if d.origin_value is None or r.peak_magnitude is None else r.peak_magnitude - d.origin_value
    return S.LinkedResult(
        revision=r.revision.name, is_origin=r.id == d.origin_result_id, status=r.status, marginal=r.marginal,
        peak_magnitude=r.peak_magnitude, peak_frequency=r.peak_frequency, margin=r.margin, limit=r.limit_value,
        unit=r.unit, delta_vs_origin=delta,
        change_vs_origin=None if delta is None else classify_change(delta, CRITERIA.change_tolerance),
        sync_state=r.sync_state,
    )


def to_out(d: Demand, db: Session) -> S.DemandOut:
    results = views.project_results(db, d.project)
    linked = [_linked(r, d) for r in results]
    latest = linked[-1] if linked else None
    origin_now = d.origin_result.peak_magnitude if d.origin_result else None
    drifted = d.origin_value is not None and origin_now is not None and abs(origin_now - d.origin_value) > 1e-9
    return S.DemandOut(
        id=d.id, project=d.project.name, component=d.project.name, description=d.description, status=d.status,
        created_at=d.created_at, updated_at=d.updated_at,
        origin=S.DemandOrigin(
            manual=d.origin_result_id is None and d.origin_revision is None, revision=d.origin_revision,
            metric=d.origin_metric, value=d.origin_value, frequency=d.origin_frequency, limit=d.origin_limit,
            unit=d.origin_unit, range_min=d.origin_range_min, range_max=d.origin_range_max,
            current_value=origin_now, drifted=drifted),
        linked_results=linked, latest=latest,
        # a later pass never auto-resolves: it only raises this flag for a human
        needs_review=bool(latest and latest.status == STATUS_PASS and d.status != "Resolved"),
        regressed=bool(latest and latest.status == STATUS_FAIL and d.status == "Resolved"),
        events=[S.DemandEventOut(at=e.at, kind=e.kind, detail=e.detail) for e in d.events],
    )


def list_demands(db: Session, status: str | None = None, project: str | None = None, revision: str | None = None,
                 latest_status: str | None = None, q: str | None = None) -> list[S.DemandOut]:
    stmt = select(Demand).join(Project).order_by(Demand.id)
    if status:
        stmt = stmt.where(Demand.status == status)
    if project:
        stmt = stmt.where(Project.name == project)
    if revision:
        stmt = stmt.where(Demand.origin_revision == revision)
    out = [to_out(d, db) for d in db.scalars(stmt).all()]
    if latest_status:
        out = [o for o in out if o.latest and o.latest.status == latest_status]
    if q:
        ql = q.lower()
        out = [o for o in out if ql in o.description.lower() or ql in o.project.lower()]
    return out


def seed_rev1_demands(db: Session, revision: str | None = None) -> list[Demand]:
    """One demand per component from its *first* revision's failed finding. Idempotent."""
    created = []
    for p in db.scalars(select(Project).order_by(Project.name)).all():
        rs = views.project_results(db, p)
        if not rs:
            continue
        first = rs[0] if revision is None else next((r for r in rs if r.revision.name == revision), None)
        if first is None or first.status != STATUS_FAIL:
            continue
        if db.scalar(select(Demand).where(Demand.origin_result_id == first.id)):
            continue
        txt = (f"Investigate and reduce the {p.name} resonance: {first.revision.name} peaks at {first.peak_magnitude:g} {first.unit} "
               f"near {first.peak_frequency:g} Hz, above the {first.limit_value:g} {first.unit} limit "
               f"({first.range_min:g}–{first.range_max:g} Hz).")
        created.append(create_demand(db, p.name, txt, first.revision.name))
    return created
