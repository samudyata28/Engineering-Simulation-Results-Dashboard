from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class WarningOut(BaseModel):
    code: str
    severity: str
    message: str


class ResultSummary(BaseModel):
    id: int
    project: str
    revision: str
    status: str = Field(description="pass | fail | incomplete | not_assessable")
    marginal: bool
    metric: str
    unit: str
    limit: float
    range_min: float
    range_max: float
    peak_magnitude: float | None
    peak_frequency: float | None
    margin: float | None = Field(description="limit - peak; negative when failing")
    samples_in_range: int
    sample_count: int
    freq_min: float
    freq_max: float
    overall_peak_magnitude: float
    overall_peak_frequency: float
    explanation: str
    warnings: list[WarningOut]
    sync_state: str
    sync_message: str | None
    source_path: str
    file_hash: str
    data_version: int
    imported_at: datetime
    updated_at: datetime


class Sample(BaseModel):
    frequency: float
    magnitude: float
    in_range: bool


class RevisionResult(BaseModel):
    summary: ResultSummary
    samples: list[Sample]


class Criteria(BaseModel):
    metric: str
    unit: str
    limit: float
    range_min: float
    range_max: float
    marginal_fraction: float
    change_tolerance: float
    description: str


class RevisionRef(BaseModel):
    name: str
    status: str
    marginal: bool
    peak_magnitude: float | None
    peak_frequency: float | None
    sync_state: str


class ProjectOut(BaseModel):
    name: str
    image_url: str | None
    revisions: list[RevisionRef]
    latest_revision: str | None
    latest_status: str | None
    trend: str
    open_demands: int


class Change(BaseModel):
    metric: str
    unit: str
    base: float | None
    target: float | None
    delta: float | None
    delta_pct: float | None
    classification: str | None = None  # improved | degraded | unchanged | unknown


class DeltaPoint(BaseModel):
    frequency: float
    base: float
    target: float
    delta: float


class Comparison(BaseModel):
    project: str
    base: ResultSummary
    target: ResultSummary
    changes: list[Change]
    status_change: str
    overall: str
    verdict: str
    base_samples: list[Sample]
    target_samples: list[Sample]
    delta_curve: list[DeltaPoint]
    delta_curve_note: str
    largest_in_range_change: DeltaPoint | None
    notes: list[str]


class HistoryStep(BaseModel):
    summary: ResultSummary
    vs_previous: Change | None
    vs_first: Change | None
    demand_ids: list[int]


class History(BaseModel):
    project: str
    steps: list[HistoryStep]
    trend: str
    trend_text: str


class IssueOut(BaseModel):
    path: str
    severity: str
    message: str


class ImportRunOut(BaseModel):
    id: int
    trigger: str
    started_at: datetime
    finished_at: datetime | None
    input_dir: str
    files_found: int
    created: int
    updated: int
    unchanged: int
    failed: int
    missing: int
    issues: list[IssueOut]


class LinkedResult(BaseModel):
    revision: str
    is_origin: bool
    status: str
    marginal: bool
    peak_magnitude: float | None
    peak_frequency: float | None
    margin: float | None
    limit: float
    unit: str
    delta_vs_origin: float | None
    change_vs_origin: str | None
    sync_state: str


class DemandEventOut(BaseModel):
    at: datetime
    kind: str
    detail: str


class DemandOrigin(BaseModel):
    manual: bool
    revision: str | None
    metric: str | None
    value: float | None
    frequency: float | None
    limit: float | None
    unit: str | None
    range_min: float | None
    range_max: float | None
    current_value: float | None = Field(description="What the origin revision's result says now (differs only if the CSV was re-imported with new data)")
    drifted: bool


class DemandOut(BaseModel):
    id: int
    project: str
    component: str
    description: str
    status: str
    created_at: datetime
    updated_at: datetime
    origin: DemandOrigin
    linked_results: list[LinkedResult]
    latest: LinkedResult | None
    needs_review: bool = Field(description="Latest result passes but demand is not Resolved: an engineer must decide")
    regressed: bool = Field(description="Demand is Resolved but the latest result fails again")
    events: list[DemandEventOut]


class DemandCreate(BaseModel):
    project: str
    description: str = Field(min_length=3, max_length=4000)
    origin_revision: str | None = Field(default=None, description="Create from this revision's failed finding; omit for a manual demand")


class DemandUpdate(BaseModel):
    description: str | None = Field(default=None, min_length=3, max_length=4000)
    status: str | None = Field(default=None, pattern="^(Open|In Progress|Resolved)$")
