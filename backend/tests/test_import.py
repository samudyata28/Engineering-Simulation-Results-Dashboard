from sqlalchemy import func, select

from app.models import ImportIssue, Result, Sample
from app.services import importer
from tests.conftest import HEADER, write_csv


def counts(db):
    return db.scalar(select(func.count()).select_from(Result)), db.scalar(select(func.count()).select_from(Sample))


def test_initial_import_of_supplied_data(db, settings):
    rep = importer.sync(db, settings)
    assert (rep.created, rep.failed, rep.unchanged) == (9, 0, 0)
    assert counts(db) == (9, 9 * 15)
    r = {(x.project.name, x.revision.name): x for x in db.scalars(select(Result))}
    assert r[("Bracket", "rev1")].status == "fail" and r[("Bracket", "rev1")].peak_magnitude == 19.9
    assert r[("Bracket", "rev1")].peak_frequency == 37.6
    assert r[("Housing", "rev2")].status == "pass" and r[("Housing", "rev2")].marginal
    assert r[("Lens", "rev3")].status == "fail" and r[("Lens", "rev3")].peak_magnitude == 17.5
    assert r[("Bracket", "rev3")].status == "pass"
    assert r[("Bracket", "rev1")].project.image_path == "Bracket.png"


def test_repeat_import_is_idempotent(db, settings):
    importer.sync(db, settings)
    before = counts(db)
    rep = importer.sync(db, settings)
    assert (rep.created, rep.updated, rep.unchanged) == (0, 0, 9)
    assert counts(db) == before


def test_changed_file_updates_in_place(db, settings):
    importer.sync(db, settings)
    old = db.scalar(select(Result).join(Result.project).where(Result.revision.has(name="rev2"), Result.project.has(name="Lens")))
    rid = old.id
    write_csv(settings.input_dir / "rev2" / "Lens.csv", [(5, 0.5), (37.8, 12.0), (50, 1), (200, 0.1)])
    rep = importer.sync(db, settings)
    assert (rep.updated, rep.unchanged, rep.created) == (1, 8, 0)
    db.expire_all()
    new = db.get(Result, rid)
    assert new.id == rid and new.status == "pass" and new.peak_magnitude == 12.0 and new.data_version == 2
    assert db.scalar(select(func.count()).select_from(Sample).where(Sample.result_id == rid)) == 4  # no duplicates


def test_new_revision_folder_detected(db, settings):
    importer.sync(db, settings)
    write_csv(settings.input_dir / "rev10" / "Lens.csv", [(5, 1), (40, 9), (60, 1)])
    write_csv(settings.input_dir / "rev10" / "NewPart.csv", [(5, 1), (40, 9), (60, 1)])
    rep = importer.sync(db, settings)
    assert rep.created == 2
    from app.services import views
    p = views.projects_list(db)
    lens = next(x for x in p if x.name == "Lens")
    assert [r.name for r in lens.revisions] == ["rev1", "rev2", "rev3", "rev10"]  # natural sort, not lexical
    assert any(x.name == "NewPart" for x in p)


def test_malformed_file_reported_and_others_imported(db, settings):
    (settings.input_dir / "rev4").mkdir()
    (settings.input_dir / "rev4" / "Bracket.csv").write_text(HEADER + "5,oops\n")
    write_csv(settings.input_dir / "rev4" / "Housing.csv", [(5, 1), (40, 5), (60, 1)])
    rep = importer.sync(db, settings)
    assert rep.failed == 1 and rep.created == 10
    issue = db.scalar(select(ImportIssue).where(ImportIssue.severity == "error"))
    assert issue.path == "rev4/Bracket.csv" and "non-numeric" in issue.message
    assert db.scalar(select(Result).join(Result.revision).where(Result.project.has(name="Bracket"), Result.revision.has(name="rev4"))) is None


def test_file_becoming_invalid_keeps_last_good_data_but_flags_it(db, settings):
    importer.sync(db, settings)
    (settings.input_dir / "rev1" / "Bracket.csv").write_text("garbage")
    rep = importer.sync(db, settings)
    assert rep.failed == 1
    r = db.scalar(select(Result).where(Result.project.has(name="Bracket"), Result.revision.has(name="rev1")))
    assert r.sync_state == "stale_error" and r.peak_magnitude == 19.9
    # fixing the file clears the flag
    write_csv(settings.input_dir / "rev1" / "Bracket.csv", [(5, 2.1), (37.6, 19.9), (60, 1)])
    importer.sync(db, settings)
    db.expire_all()
    assert db.get(Result, r.id).sync_state == "ok"


def test_removed_file_flagged_not_deleted(db, settings):
    importer.sync(db, settings)
    (settings.input_dir / "rev3" / "Lens.csv").unlink()
    rep = importer.sync(db, settings)
    assert rep.missing == 1
    r = db.scalar(select(Result).where(Project_name("Lens"), Result.revision.has(name="rev3")))
    assert r.sync_state == "source_missing" and r.sample_count > 0


def Project_name(n):
    return Result.project.has(name=n)


def test_stray_csv_and_empty_folder_reported(db, settings):
    write_csv(settings.input_dir / "stray.csv", [(1, 1)])
    (settings.input_dir / "rev9").mkdir()
    importer.sync(db, settings)
    msgs = " | ".join(i.message for i in db.scalars(select(ImportIssue)))
    assert "not inside a revision folder" in msgs and "no CSV" in msgs


def test_missing_input_dir(db, settings, tmp_path):
    from dataclasses import replace
    rep = importer.sync(db, replace(settings, input_dir=tmp_path / "nope"))
    assert rep.failed == 1


def test_criteria_change_recomputes_from_stored_samples(db, settings):
    from app.config import Criteria
    importer.sync(db, settings)
    n = importer.recompute_stale_criteria(db, Criteria(limit=14.0))
    assert n == 9
    r = db.scalar(select(Result).where(Project_name("Bracket"), Result.revision.has(name="rev3")))
    assert r.status == "pass" and r.limit_value == 14.0  # 13.8 <= 14
    h = db.scalar(select(Result).where(Project_name("Housing"), Result.revision.has(name="rev2")))
    assert h.status == "fail"  # 14.9 > 14
