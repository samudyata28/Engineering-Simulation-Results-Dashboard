"""Database schema.

Project 1──* Result *──1 Revision      (a Result = one component's CSV in one revision)
Result  1──* Sample                    (raw frequency/magnitude rows)
Project 1──* Demand ──> origin Result  (demand keeps its origin; later revisions are
                                        *derived* by joining on project, never copied)
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Project(Base):
    """A simulated product component (Bracket, Housing, Lens...).

    In the supplied data one CSV name == one component == one project, so the
    two concepts are modelled by one row (see DECISIONS.md, assumption A1).
    """

    __tablename__ = "projects"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True)
    image_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    results: Mapped[list["Result"]] = relationship(back_populates="project", cascade="all, delete-orphan")


class Revision(Base):
    __tablename__ = "revisions"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True)
    results: Mapped[list["Result"]] = relationship(back_populates="revision", cascade="all, delete-orphan")


class Result(Base):
    __tablename__ = "results"
    __table_args__ = (UniqueConstraint("project_id", "revision_id", name="uq_result_project_revision"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    revision_id: Mapped[int] = mapped_column(ForeignKey("revisions.id", ondelete="CASCADE"))

    # provenance / change detection
    source_path: Mapped[str] = mapped_column(String(1000))
    file_hash: Mapped[str] = mapped_column(String(64))
    file_size: Mapped[int] = mapped_column(Integer)
    file_mtime: Mapped[float] = mapped_column(Float)
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    data_version: Mapped[int] = mapped_column(Integer, default=1)  # bumps when content changes
    sync_state: Mapped[str] = mapped_column(String(20), default="ok")  # ok | stale_error | source_missing
    sync_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # calculated summary (derived from samples + criteria; recomputed if criteria change)
    sample_count: Mapped[int] = mapped_column(Integer)
    freq_min: Mapped[float] = mapped_column(Float)
    freq_max: Mapped[float] = mapped_column(Float)
    overall_peak_magnitude: Mapped[float] = mapped_column(Float)
    overall_peak_frequency: Mapped[float] = mapped_column(Float)
    criteria_key: Mapped[str] = mapped_column(String(100))
    limit_value: Mapped[float] = mapped_column(Float)
    range_min: Mapped[float] = mapped_column(Float)
    range_max: Mapped[float] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(10))
    samples_in_range: Mapped[int] = mapped_column(Integer)
    peak_magnitude: Mapped[float | None] = mapped_column(Float, nullable=True)  # within range
    peak_frequency: Mapped[float | None] = mapped_column(Float, nullable=True)
    margin: Mapped[float | None] = mapped_column(Float, nullable=True)  # limit - peak
    status: Mapped[str] = mapped_column(String(20))  # pass | fail | incomplete | not_assessable
    marginal: Mapped[bool] = mapped_column(Boolean, default=False)
    warnings: Mapped[list] = mapped_column(JSON, default=list)

    project: Mapped[Project] = relationship(back_populates="results")
    revision: Mapped[Revision] = relationship(back_populates="results")
    samples: Mapped[list["Sample"]] = relationship(
        back_populates="result", cascade="all, delete-orphan", order_by="Sample.frequency"
    )


class Sample(Base):
    __tablename__ = "samples"
    id: Mapped[int] = mapped_column(primary_key=True)
    result_id: Mapped[int] = mapped_column(ForeignKey("results.id", ondelete="CASCADE"), index=True)
    frequency: Mapped[float] = mapped_column(Float)
    magnitude: Mapped[float] = mapped_column(Float)
    result: Mapped[Result] = relationship(back_populates="samples")


class ImportRun(Base):
    __tablename__ = "import_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    trigger: Mapped[str] = mapped_column(String(30))  # startup | api | cli
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    input_dir: Mapped[str] = mapped_column(String(1000))
    files_found: Mapped[int] = mapped_column(Integer, default=0)
    created: Mapped[int] = mapped_column(Integer, default=0)
    updated: Mapped[int] = mapped_column(Integer, default=0)
    unchanged: Mapped[int] = mapped_column(Integer, default=0)
    failed: Mapped[int] = mapped_column(Integer, default=0)
    missing: Mapped[int] = mapped_column(Integer, default=0)
    issues: Mapped[list["ImportIssue"]] = relationship(
        back_populates="run", cascade="all, delete-orphan", order_by="ImportIssue.id"
    )


class ImportIssue(Base):
    __tablename__ = "import_issues"
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("import_runs.id", ondelete="CASCADE"), index=True)
    path: Mapped[str] = mapped_column(String(1000))
    severity: Mapped[str] = mapped_column(String(10))  # error | warning
    message: Mapped[str] = mapped_column(Text)
    run: Mapped[ImportRun] = relationship(back_populates="issues")


class Demand(Base):
    __tablename__ = "demands"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    description: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="Open")  # Open | In Progress | Resolved
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    # Origin. NULL origin_result_id => created manually. The snapshot columns are
    # frozen at creation: they record *what the engineer saw*, even if the CSV is
    # later re-imported with different numbers.
    origin_result_id: Mapped[int | None] = mapped_column(
        ForeignKey("results.id", ondelete="SET NULL"), nullable=True
    )
    origin_revision: Mapped[str | None] = mapped_column(String(200), nullable=True)
    origin_metric: Mapped[str | None] = mapped_column(String(200), nullable=True)
    origin_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    origin_frequency: Mapped[float | None] = mapped_column(Float, nullable=True)
    origin_limit: Mapped[float | None] = mapped_column(Float, nullable=True)
    origin_unit: Mapped[str | None] = mapped_column(String(10), nullable=True)
    origin_range_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    origin_range_max: Mapped[float | None] = mapped_column(Float, nullable=True)

    project: Mapped[Project] = relationship()
    origin_result: Mapped[Result | None] = relationship()
    events: Mapped[list["DemandEvent"]] = relationship(
        back_populates="demand", cascade="all, delete-orphan", order_by="DemandEvent.id"
    )


class DemandEvent(Base):
    """Append-only audit log: who/what changed a demand and when."""

    __tablename__ = "demand_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    demand_id: Mapped[int] = mapped_column(ForeignKey("demands.id", ondelete="CASCADE"), index=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    kind: Mapped[str] = mapped_column(String(30))  # created | status | description
    detail: Mapped[str] = mapped_column(Text)
    demand: Mapped[Demand] = relationship(back_populates="events")
