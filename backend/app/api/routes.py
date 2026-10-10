from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import schemas as S
from ..models import ImportRun
from ..services import demands as demand_svc
from ..services import importer, views

router = APIRouter(prefix="/api")


def get_db(request: Request):
    with request.app.state.session_factory() as db:
        yield db


def _nf(e: views.NotFound):
    return HTTPException(404, str(e))


@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/criteria", response_model=S.Criteria, tags=["review"])
def criteria():
    return views.criteria_out()


@router.get("/projects", response_model=list[S.ProjectOut], tags=["discovery"])
def list_projects(db: Session = Depends(get_db)):
    return views.projects_list(db)


@router.get("/projects/{project}/revisions", response_model=list[S.ResultSummary], tags=["discovery"])
def list_revisions(project: str, db: Session = Depends(get_db)):
    try:
        return [views.summary(r) for r in views.project_results(db, views.get_project(db, project))]
    except views.NotFound as e:
        raise _nf(e)


@router.get("/projects/{project}/revisions/{revision}", response_model=S.RevisionResult, tags=["results"])
def revision_result(project: str, revision: str, db: Session = Depends(get_db)):
    try:
        return views.revision_result(db, project, revision)
    except views.NotFound as e:
        raise _nf(e)


@router.get("/projects/{project}/compare", response_model=S.Comparison, tags=["results"])
def compare(project: str, base: str, target: str, db: Session = Depends(get_db)):
    try:
        return views.compare(db, project, base, target)
    except views.NotFound as e:
        raise _nf(e)


@router.get("/projects/{project}/history", response_model=S.History, tags=["results"])
def history(project: str, db: Session = Depends(get_db)):
    try:
        return views.history(db, project)
    except views.NotFound as e:
        raise _nf(e)


@router.get("/projects/{project}/image", tags=["discovery"])
def project_image(project: str, request: Request, db: Session = Depends(get_db)):
    try:
        p = views.get_project(db, project)
    except views.NotFound as e:
        raise _nf(e)
    root = request.app.state.settings.input_dir
    path = (root / p.image_path).resolve() if p.image_path else None
    if not path or root not in path.parents or not path.is_file():
        raise HTTPException(404, "No image for this project")
    return FileResponse(path)


# ---- import -----------------------------------------------------------------
@router.post("/import", response_model=S.ImportRunOut, tags=["import"])
def trigger_import(request: Request, db: Session = Depends(get_db)):
    """Re-scan the input directory. Safe to call repeatedly (idempotent)."""
    rep = importer.sync(db, request.app.state.settings, trigger="api")
    return views.import_run_out(db.get(ImportRun, rep.run_id))


@router.get("/import/latest", response_model=S.ImportRunOut | None, tags=["import"])
def latest_import(db: Session = Depends(get_db)):
    run = db.scalar(select(ImportRun).order_by(ImportRun.id.desc()).limit(1))
    return views.import_run_out(run) if run else None


# ---- demands ----------------------------------------------------------------
@router.get("/demands", response_model=list[S.DemandOut], tags=["demands"])
def list_demands(status: str | None = Query(None, pattern="^(Open|In Progress|Resolved)$"), project: str | None = None,
                 origin_revision: str | None = None, latest_status: str | None = None, q: str | None = None,
                 db: Session = Depends(get_db)):
    return demand_svc.list_demands(db, status, project, origin_revision, latest_status, q)


@router.get("/demands/{demand_id}", response_model=S.DemandOut, tags=["demands"])
def get_demand(demand_id: int, db: Session = Depends(get_db)):
    from ..models import Demand
    d = db.get(Demand, demand_id)
    if d is None:
        raise HTTPException(404, f"Demand {demand_id} not found")
    return demand_svc.to_out(d, db)


@router.post("/demands", response_model=S.DemandOut, status_code=201, tags=["demands"])
def create_demand(body: S.DemandCreate, db: Session = Depends(get_db)):
    try:
        d = demand_svc.create_demand(db, body.project, body.description, body.origin_revision)
    except views.NotFound as e:
        raise _nf(e)
    except demand_svc.DemandError as e:
        raise HTTPException(e.status_code, {"message": e.message, "existing_id": e.existing_id})
    return demand_svc.to_out(d, db)


@router.patch("/demands/{demand_id}", response_model=S.DemandOut, tags=["demands"])
def update_demand(demand_id: int, body: S.DemandUpdate, db: Session = Depends(get_db)):
    try:
        d = demand_svc.update_demand(db, demand_id, body.description, body.status)
    except views.NotFound as e:
        raise _nf(e)
    return demand_svc.to_out(d, db)
