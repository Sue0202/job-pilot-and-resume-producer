"""Tests for Evidence Library Quick Capture and field persistence.

Run: python test_evidence_quick_capture.py
Uses a temp DB — real jobpilot.db and candidate_master_profile.md are not touched.
"""

import tempfile
from pathlib import Path

import database as db

db.DB_PATH = Path(tempfile.mkdtemp()) / "test_evidence_quick.db"
db.init_db()

import app  # noqa: E402
import evidence_verbal as ev  # noqa: E402
import evidence_vocabulary as evocab  # noqa: E402
import jd_analyzer  # noqa: E402

PROFILE_PATH = app.PROFILE_PATH
_results = []


def check(name, cond):
    _results.append((name, bool(cond)))
    print(f"{'PASS' if cond else 'FAIL'}: {name}")


def _full_record(status="Draft"):
    cat = evocab.ensure_category("Access Governance")
    tags = evocab.ensure_capability_tags(["Workflow Design", "Launch Readiness"])
    return {
        "title": "Release readiness dashboard",
        "company": "miHoYo",
        "role_context": "Live ops / product ops",
        "time_period": "2022–2023",
        "factual_context": "Owned cross-team release readiness tracking for major version launches.",
        "impact_outcome": "Reduced handoff steps between QA and publishing.",
        "skills": "Jira, SQL, Tableau",
        "category": cat,
        "capability_tags": ", ".join(tags),
        "tags": ", ".join(tags),
        "raw_notes": "Internal notes",
        "status": status,
        "action": "Owned cross-team release readiness tracking for major version launches.",
        "outcome": "Reduced handoff steps between QA and publishing.",
    }


def test_save_as_draft_persists_draft():
    eid = db.save_evidence_item(_full_record(status="Draft"))
    item = db.get_evidence_item(eid)
    check("draft status persisted", item["status"] == "Draft")


def test_save_as_verified_persists_verified():
    eid = db.save_evidence_item(_full_record(status="Verified"))
    item = db.get_evidence_item(eid)
    check("verified status persisted", item["status"] == "Verified")


def test_factual_context_persists():
    eid = db.save_evidence_item(_full_record())
    item = db.get_evidence_item(eid)
    check("factual_context saved", "release readiness tracking" in (item.get("factual_context") or ""))
    check("factual readable via helper", "release readiness" in app._evidence_factual(item))


def test_impact_outcome_persists():
    eid = db.save_evidence_item(_full_record())
    item = db.get_evidence_item(eid)
    check("impact_outcome saved", "handoff steps" in (item.get("impact_outcome") or ""))
    check("impact readable via helper", "handoff" in app._evidence_impact(item))


def test_category_persists():
    eid = db.save_evidence_item(_full_record())
    item = db.get_evidence_item(eid)
    check("category saved", item.get("category") == "Access Governance")


def test_tags_persist():
    eid = db.save_evidence_item(_full_record())
    item = db.get_evidence_item(eid)
    tags = item.get("capability_tags") or item.get("tags") or ""
    check("workflow tag saved", "Workflow Design" in tags)
    check("launch tag saved", "Launch Readiness" in tags)


def test_custom_vocab_does_not_change_score():
    profile = app.load_profile_text()
    jd = "Product Operations Manager. Workday, launch operations."
    before = jd_analyzer.analyze_fit(jd, profile)
    evocab.ensure_category("Financial Operations")
    evocab.ensure_capability_tags(["Risk Controls"])
    db.save_evidence_item({
        "title": "Vocab test",
        "factual_context": "Coordinated vendor integration.",
        "category": "Financial Operations",
        "capability_tags": "Risk Controls",
        "tags": "Risk Controls",
        "status": "Draft",
    })
    after = jd_analyzer.analyze_fit(jd, profile)
    check("base score unchanged", before["base_score"] == after["base_score"])
    check("components unchanged", before["component_scores"] == after["component_scores"])


def test_verbal_output_does_not_overwrite_factual():
    eid = db.save_evidence_item(_full_record())
    facts_before = db.get_evidence_item(eid)["factual_context"]
    text, _ = ev.generate_resume_bullet(facts_before, role_family="Product Operations")
    db.upsert_verbal_output(
        eid, ev.OUTPUT_RESUME_BULLET, text, role_family="Product Operations",
    )
    item = db.get_evidence_item(eid)
    check("factual_context unchanged", item["factual_context"] == facts_before)
    outputs = db.get_verbal_outputs(eid)
    check("verbal outputs stored separately", len(outputs) >= 1)


def test_legacy_records_readable_after_migration():
    eid = db.save_evidence_item({
        "title": "Legacy only action",
        "action": "Built dashboards for QA and publishing teams.",
        "outcome": "Improved visibility",
        "category": "Platform Operations",
        "status": "Verified",
    })
    db.backfill_evidence_factual_fields()
    item = db.get_evidence_item(eid)
    check("legacy item readable", item is not None)
    check("backfill populated factual_context", "dashboards" in (item.get("factual_context") or ""))
    check("backfill populated impact", item.get("impact_outcome") == "Improved visibility")
    check("legacy status preserved", item["status"] == "Verified")


def test_profile_never_overwritten():
    before = PROFILE_PATH.read_text(encoding="utf-8")
    eid = db.save_evidence_item(_full_record(status="Verified"))
    db.save_verbal_output(eid, ev.OUTPUT_RESUME_BULLET, "Some bullet", role_family="Product Operations")
    evocab.ensure_category("New Category")
    after = PROFILE_PATH.read_text(encoding="utf-8")
    check("profile file unchanged", before == after)
    check("profile still Yeyi Su", app._active_profile_name(after).upper() == "YEYI SU")


def test_build_quick_capture_record_status_from_button():
    record = app._build_quick_capture_record(
        "T", "Co", "Role", "2023", "Did the work.", "Better flow.",
        "Jira", "Access Governance", "Workflow Design", "notes", "Verified",
    )
    check("quick capture verified status", record["status"] == "Verified")
    check("quick capture factual", record["factual_context"] == "Did the work.")
    check("quick capture tags", "Workflow Design" in record["capability_tags"])


def test_invalid_status_defaults_to_draft():
    eid = db.save_evidence_item({**_full_record(), "status": "InvalidStatus"})
    item = db.get_evidence_item(eid)
    check("invalid status coerced to draft", item["status"] == "Draft")


if __name__ == "__main__":
    test_save_as_draft_persists_draft()
    test_save_as_verified_persists_verified()
    test_factual_context_persists()
    test_impact_outcome_persists()
    test_category_persists()
    test_tags_persist()
    test_custom_vocab_does_not_change_score()
    test_verbal_output_does_not_overwrite_factual()
    test_legacy_records_readable_after_migration()
    test_profile_never_overwritten()
    test_build_quick_capture_record_status_from_button()
    test_invalid_status_defaults_to_draft()
    passed = sum(1 for _, ok in _results if ok)
    failed = [n for n, ok in _results if not ok]
    print(f"\n{passed}/{len(_results)} passed")
    if failed:
        print("FAILED:", ", ".join(failed))
        raise SystemExit(1)
