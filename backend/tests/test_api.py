def test_projects_and_revisions(synced):
    ps = synced.get("/api/projects").json()
    assert [p["name"] for p in ps] == ["Bracket", "Housing", "Lens"]
    b = ps[0]
    assert [r["name"] for r in b["revisions"]] == ["rev1", "rev2", "rev3"]
    assert b["latest_status"] == "pass" and b["image_url"]
    assert synced.get(b["image_url"]).headers["content-type"] == "image/png"


def test_criteria_endpoint(synced):
    c = synced.get("/api/criteria").json()
    assert (c["limit"], c["range_min"], c["range_max"], c["unit"]) == (15.0, 0.0, 50.0, "mm")


def test_revision_result(synced):
    d = synced.get("/api/projects/Bracket/revisions/rev1").json()
    s = d["summary"]
    assert s["status"] == "fail" and s["peak_magnitude"] == 19.9 and s["peak_frequency"] == 37.6
    assert "exceeds" in s["explanation"] and round(s["margin"], 2) == -4.9
    assert len(d["samples"]) == 15
    assert all(x["in_range"] == (x["frequency"] <= 50) for x in d["samples"])


def test_404s(synced):
    assert synced.get("/api/projects/Nope/revisions").status_code == 404
    assert synced.get("/api/projects/Bracket/revisions/rev99").status_code == 404
    assert synced.get("/api/projects/Bracket/compare?base=rev1&target=rev99").status_code == 404


def test_compare(synced):
    c = synced.get("/api/projects/Bracket/compare?base=rev1&target=rev2").json()
    assert c["overall"] == "degraded" and c["status_change"] == "fail (no change)"
    pk = c["changes"][0]
    assert round(pk["delta"], 2) == 2.1 and pk["classification"] == "degraded"
    assert any("grids differ" in n for n in c["notes"])
    c = synced.get("/api/projects/Bracket/compare?base=rev1&target=rev3").json()
    assert c["overall"] == "improved" and c["status_change"] == "fail → pass"
    assert c["largest_in_range_change"] is not None and c["delta_curve"]


def test_history_trace(synced):
    h = synced.get("/api/projects/Lens/history").json()
    assert [s["summary"]["revision"] for s in h["steps"]] == ["rev1", "rev2", "rev3"]
    assert h["steps"][0]["vs_previous"] is None
    assert h["steps"][2]["vs_previous"]["classification"] == "degraded"  # 16.1 -> 17.5
    assert h["trend"] == "improved"  # 18.0 -> 17.5 overall, though rev3 regressed vs rev2
    assert "latest step rev2 → rev3 degraded" in h["trend_text"]  # the reversal is not hidden


def test_import_endpoint_idempotent(synced):
    r = synced.post("/api/import").json()
    assert (r["created"], r["updated"], r["unchanged"]) == (0, 0, 9)
    assert synced.get("/api/import/latest").json()["id"] == r["id"]


# ------------------------------------------------------------------ demands
def test_seed_then_demand_history_across_revisions(synced):
    for p in ("Bracket", "Housing", "Lens"):
        r = synced.post("/api/demands", json={"project": p, "description": f"Fix {p}", "origin_revision": "rev1"})
        assert r.status_code == 201, r.text
    ds = synced.get("/api/demands").json()
    assert len(ds) == 3
    b = next(d for d in ds if d["project"] == "Bracket")
    assert b["origin"]["revision"] == "rev1" and b["origin"]["value"] == 19.9 and b["origin"]["frequency"] == 37.6
    assert b["origin"]["limit"] == 15 and not b["origin"]["manual"]
    assert [l["revision"] for l in b["linked_results"]] == ["rev1", "rev2", "rev3"]
    assert [l["status"] for l in b["linked_results"]] == ["fail", "fail", "pass"]
    assert b["latest"]["revision"] == "rev3" and b["latest"]["status"] == "pass"
    assert b["status"] == "Open" and b["needs_review"] is True  # passing does NOT auto-resolve
    l = next(d for d in ds if d["project"] == "Lens")
    assert l["needs_review"] is False and l["latest"]["status"] == "fail"


def test_cannot_create_from_passing_result_and_no_duplicates(synced):
    r = synced.post("/api/demands", json={"project": "Bracket", "description": "nope", "origin_revision": "rev3"})
    assert r.status_code == 422
    ok = synced.post("/api/demands", json={"project": "Lens", "description": "first", "origin_revision": "rev1"})
    dup = synced.post("/api/demands", json={"project": "Lens", "description": "again", "origin_revision": "rev1"})
    assert dup.status_code == 409 and dup.json()["detail"]["existing_id"] == ok.json()["id"]


def test_manual_demand_and_validation(synced):
    r = synced.post("/api/demands", json={"project": "Housing", "description": "Check mounting stiffness"})
    assert r.status_code == 201 and r.json()["origin"]["manual"] is True
    assert len(r.json()["linked_results"]) == 3
    assert synced.post("/api/demands", json={"project": "Nope", "description": "xxx"}).status_code == 404
    assert synced.post("/api/demands", json={"project": "Lens", "description": "x"}).status_code == 422


def test_update_and_filters(synced):
    a = synced.post("/api/demands", json={"project": "Lens", "description": "Stiffen lens barrel", "origin_revision": "rev1"}).json()
    synced.post("/api/demands", json={"project": "Bracket", "description": "Add ribs", "origin_revision": "rev1"})
    u = synced.patch(f"/api/demands/{a['id']}", json={"status": "In Progress", "description": "Stiffen the lens barrel (v2)"}).json()
    assert u["status"] == "In Progress" and u["description"].endswith("(v2)")
    assert [e["kind"] for e in u["events"]] == ["created", "description", "status"]
    assert synced.patch(f"/api/demands/{a['id']}", json={"status": "Done"}).status_code == 422
    assert synced.patch("/api/demands/999", json={"status": "Open"}).status_code == 404
    assert [d["project"] for d in synced.get("/api/demands?status=In Progress").json()] == ["Lens"]
    assert [d["project"] for d in synced.get("/api/demands?project=Bracket").json()] == ["Bracket"]
    assert [d["project"] for d in synced.get("/api/demands?latest_status=fail").json()] == ["Lens"]
    assert len(synced.get("/api/demands?q=ribs").json()) == 1


def test_origin_snapshot_survives_reimport_and_new_revisions(synced, settings):
    from tests.conftest import write_csv
    d = synced.post("/api/demands", json={"project": "Lens", "description": "Lens issue", "origin_revision": "rev1"}).json()
    write_csv(settings.input_dir / "rev4" / "Lens.csv", [(5, 0.5), (37.8, 9.0), (60, 1)])  # newer revision passes
    write_csv(settings.input_dir / "rev1" / "Lens.csv", [(5, 0.5), (37.8, 18.5), (60, 1)])  # origin data re-imported
    synced.post("/api/import")
    got = synced.get(f"/api/demands/{d['id']}").json()
    assert got["origin"]["value"] == 18.0 and got["origin"]["current_value"] == 18.5 and got["origin"]["drifted"]
    assert got["latest"]["revision"] == "rev4" and got["latest"]["status"] == "pass"
    assert got["status"] == "Open" and got["needs_review"]  # never auto-resolved
    assert len(synced.get("/api/demands").json()) == 1  # no replacement demand created
    synced.patch(f"/api/demands/{d['id']}", json={"status": "Resolved"})
    assert not synced.get(f"/api/demands/{d['id']}").json()["needs_review"]


def test_seed_cli_idempotent(db, settings):
    from app.services import demands, importer
    importer.sync(db, settings)
    assert len(demands.seed_rev1_demands(db)) == 3
    assert len(demands.seed_rev1_demands(db)) == 0
