"""Focused tests for the v3 personal-copilot refactor.

Run directly:  python test_workflow.py
Uses a temp DB so the real jobpilot.db is never touched.
"""

import inspect
import json
import tempfile
from pathlib import Path

import database as db

# Point DB at a throwaway file BEFORE any write.
db.DB_PATH = Path(tempfile.mkdtemp()) / "test_workflow.db"
db.init_db()

import app  # noqa: E402  (import after DB_PATH set; app uses db lazily)
import resume_generator as rg  # noqa: E402

_results = []


def check(name, cond):
    _results.append((name, bool(cond)))
    print(f"{'PASS' if cond else 'FAIL'}: {name}")


def test_profile_cannot_be_replaced_by_persona():
    persona = (
        "Background\tSenior Software Engineer, 7 years in fintech.\n"
        "Target Roles\tML Platform Engineer\nDealbreakers\tUS only"
    )
    raised = False
    try:
        app.save_profile_text(persona)
    except app.ProfileSafetyError:
        raised = True
    check("persona text rejected by save guard", raised)
    check("looks_like_test_persona detects persona", app.looks_like_test_persona(persona))
    real = app.load_profile_text()
    check("active profile is YEYI SU", app._active_profile_name(real).upper() == "YEYI SU")
    check("real profile not flagged as persona", not app.looks_like_test_persona(real))


def test_temporary_evidence_not_autosaved():
    before = len(db.get_evidence_items())
    import jd_analyzer
    profile = app.load_profile_text()
    q = jd_analyzer.classify_evidence_quality("At miHoYo I used Tableau and SQL for dashboards.")
    jd_analyzer.analyze_fit("Need Tableau and SQL dashboards.", profile + "\nTableau SQL",
                            added_evidence_quality=q)
    after = len(db.get_evidence_items())
    check("re-analysis does not auto-save evidence", before == after)


def test_verified_evidence_used_in_resume():
    eid = db.save_evidence_item({
        "title": "Launch ops dashboard", "company": "miHoYo",
        "action": "Built a release-readiness dashboard", "outcome": "cut handoff steps",
        "bullet_draft": "Built a release-readiness dashboard used by QA and publishing",
        "status": "Verified",
    })
    verified = db.get_verified_evidence()
    check("verified evidence retrievable", any(v["id"] == eid for v in verified))
    material = app._evidence_to_material(verified)
    check("evidence material contains the bullet", "release-readiness dashboard" in material)
    # Resume generation accepts the augmented material without error.
    job_row = {"job_id": "t1", "company": "Acme", "job_title": "Product Ops",
               "description": "Own launch operations and dashboards", "responsibilities": "",
               "qualifications": ""}
    result = __import__("matching").match_job_to_candidate(app.load_profile_text(), job_row)
    data = rg.generate_resume(app.load_profile_text() + material, job_row, result, "")
    check("resume generated with evidence material", bool(data.get("full_resume_text")))
    # Draft evidence is NOT eligible.
    db.save_evidence_item({"title": "draft only", "action": "x", "status": "Draft"})
    check("draft evidence excluded from verified pool",
          all(v["status"] == "Verified" for v in db.get_verified_evidence()))


def test_resume_versions_stored_separately():
    base = len(db.get_resume_versions())
    db.save_resume_version("Acme", "Product Ops", "j1", "Product Operations", 7.0,
                           "", "", "v1 feedback", "RESUME ONE")
    db.save_resume_version("Acme", "Product Ops", "j1", "Product Operations", 7.0,
                           "", "", "v2 feedback", "RESUME TWO")
    versions = db.get_resume_versions()
    check("two distinct versions stored", len(versions) == base + 2)
    texts = {v["resume_text"] for v in versions}
    check("versions not overwritten", {"RESUME ONE", "RESUME TWO"} <= texts)


def test_application_status_updates():
    rid, created = db.add_or_update_application_from_analysis(
        "Acme", "Product Ops Manager", "https://x", "Saved", analysis_score=7.2,
        role_family="Product Operations", notes="n", source="LinkedIn", location="SF")
    check("application created", created)
    db.update_application_fields(rid, {"status": "Applied", "applied_date": "2026-06-22"})
    app_row = next(a for a in db.get_applications() if a["id"] == rid)
    check("status updated to Applied", app_row["status"] == "Applied")
    check("applied_date persisted", app_row.get("applied_date") == "2026-06-22")
    check("source persisted", app_row.get("source") == "LinkedIn")


def test_home_does_not_load_dataset_at_startup():
    src = inspect.getsource(app.page_home)
    check("Home page does not call load_jobs", "load_jobs" not in src)
    # Default landing is Home.
    check("default nav routes to Home", "Home" in app.PAGE_DISPATCH)


def main():
    test_profile_cannot_be_replaced_by_persona()
    test_temporary_evidence_not_autosaved()
    test_verified_evidence_used_in_resume()
    test_resume_versions_stored_separately()
    test_application_status_updates()
    test_home_does_not_load_dataset_at_startup()
    passed = sum(1 for _, ok in _results if ok)
    print(f"\n{passed}/{len(_results)} checks passed")
    if passed != len(_results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
