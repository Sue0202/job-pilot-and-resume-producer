"""Tests for Evidence Library editable vocabulary.

Run: python test_evidence_vocabulary.py
Uses a temp DB — real jobpilot.db is not touched.
"""

import tempfile
from pathlib import Path

import database as db

db.DB_PATH = Path(tempfile.mkdtemp()) / "test_evidence_vocab.db"
db.init_db()

import evidence_vocabulary as evocab  # noqa: E402
import jd_analyzer  # noqa: E402
import app  # noqa: E402

_results = []


def check(name, cond):
    _results.append((name, bool(cond)))
    print(f"{'PASS' if cond else 'FAIL'}: {name}")


def test_custom_category_persists():
    cat = evocab.ensure_category("Internal Tool Product Ownership")
    check("category resolved", cat == "Internal Tool Product Ownership")
    rows = db.get_user_vocabulary(evocab.VOCAB_CATEGORY)
    check("category in db", any(r["value"] == "Internal Tool Product Ownership" for r in rows))
    check("category in all_categories", "Internal Tool Product Ownership" in evocab.all_categories())


def test_custom_capability_tag_persists():
    tags = evocab.ensure_capability_tags(["Requirements Intake", "External Partner Enablement"])
    check("tags returned", "Requirements Intake" in tags)
    rows = db.get_user_vocabulary(evocab.VOCAB_CAPABILITY_TAG)
    check("tag in db", any(r["value"] == "Requirements Intake" for r in rows))
    check("tag in all_capability_tags", "Requirements Intake" in evocab.all_capability_tags())


def test_custom_skill_becomes_suggestion():
    evocab.register_skills_from_text("Snowflake, CustomInternalTool")
    suggestions = evocab.skill_suggestions()
    check("custom skill suggested", any("CustomInternalTool" in s or "custominternaltool" in s.lower() for s in suggestions))
    rows = db.get_user_vocabulary(evocab.VOCAB_SKILL_TOOL)
    check("skill in vocabulary table", any("CustomInternalTool" in r["value"] for r in rows))


def test_duplicate_normalization():
    id1 = db.add_user_vocabulary(evocab.VOCAB_CATEGORY, "Access Governance", "access governance")
    id2 = db.add_user_vocabulary(evocab.VOCAB_CATEGORY, "access governance", "access governance")
    check("duplicate norm_key same id", id1 == id2)
    c1 = evocab.ensure_category("Access Governance")
    c2 = evocab.ensure_category(" access governance ")
    check("whitespace variant same display", c1 == c2)
    rows = db.get_user_vocabulary(evocab.VOCAB_CATEGORY)
    keys = [r["norm_key"] for r in rows if r["norm_key"] == "access governance"]
    check("only one access governance row", len(keys) <= 1)


def test_existing_evidence_readable():
    eid = db.save_evidence_item({
        "title": "Legacy item",
        "category": "Platform Operations",
        "capability_tags": "Internal Tools, Incident / Escalation",
        "skills": "Jira, SQL",
        "status": "Verified",
        "proof_strength": "Supporting",
    })
    item = db.get_evidence_item(eid)
    check("legacy item readable", item is not None)
    check("legacy category preserved", item["category"] == "Platform Operations")
    check("legacy proof strength preserved", item["proof_strength"] == "Supporting")
    check("legacy tags preserved", "Internal Tools" in item["capability_tags"])


def test_default_options_available():
    check("default category Launch / Release", "Launch / Release" in evocab.all_categories())
    check("default tag Program Management", "Program Management" in evocab.all_capability_tags())
    check("default skill Jira", "Jira" in evocab.skill_suggestions())
    check("status options controlled", evocab.EVIDENCE_STATUSES == ["Draft", "Verified", "Archived"])


def test_custom_values_do_not_change_scoring():
    profile = app.load_profile_text()
    jd = "Product Operations Manager. Workday, launch operations, cross-functional."
    before = jd_analyzer.analyze_fit(jd, profile)
    evocab.ensure_category("Financial Operations")
    evocab.ensure_capability_tags(["Risk Controls", "Compliance Workflow Design"])
    evocab.register_skills_from_text("NetSuite, Workday")
    db.save_evidence_item({
        "title": "Vocab only",
        "category": "Financial Operations",
        "capability_tags": "Risk Controls",
        "skills": "NetSuite",
        "status": "Draft",
    })
    after = jd_analyzer.analyze_fit(jd, profile)
    check("base score unchanged", before["base_score"] == after["base_score"])
    check("component scores unchanged", before["component_scores"] == after["component_scores"])
    check("profile unchanged", profile == app.load_profile_text())


def test_cannot_delete_vocabulary_in_use():
    cat = evocab.ensure_category("Risk Controls Operations")
    eid = db.save_evidence_item({
        "title": "Uses custom cat",
        "category": cat,
        "status": "Draft",
    })
    row = next(r for r in db.get_user_vocabulary(evocab.VOCAB_CATEGORY) if r["norm_key"] == "risk controls operations")
    ok, msg = evocab.delete_custom_vocabulary(row["id"])
    check("delete blocked when in use", not ok)
    check("warning mentions use", "in use" in msg.lower())
    check("evidence still exists", db.get_evidence_item(eid) is not None)


def test_can_delete_unused_vocabulary():
    vid = db.add_user_vocabulary(evocab.VOCAB_CAPABILITY_TAG, "Unused Tag", "unused tag")
    ok, msg = evocab.delete_custom_vocabulary(vid)
    check("unused delete succeeds", ok)
    check("removed from db", db.get_user_vocabulary_by_id(vid) is None)


def test_system_default_not_deletable():
    fake_id = db.add_user_vocabulary(evocab.VOCAB_CATEGORY, "Platform Operations", "platform operations")
    ok, _ = evocab.delete_custom_vocabulary(fake_id)
    check("system default category delete blocked", not ok)
    check("system defaults flagged", evocab.is_system_default(evocab.VOCAB_CATEGORY, "Analytics"))


def test_user_vocabulary_table_exists():
    conn = db._connect()
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='user_vocabulary'")
    row = cur.fetchone()
    conn.close()
    check("user_vocabulary table exists", row is not None)


if __name__ == "__main__":
    test_user_vocabulary_table_exists()
    test_custom_category_persists()
    test_custom_capability_tag_persists()
    test_custom_skill_becomes_suggestion()
    test_duplicate_normalization()
    test_existing_evidence_readable()
    test_default_options_available()
    test_custom_values_do_not_change_scoring()
    test_cannot_delete_vocabulary_in_use()
    test_can_delete_unused_vocabulary()
    test_system_default_not_deletable()
    passed = sum(1 for _, ok in _results if ok)
    failed = [n for n, ok in _results if not ok]
    print(f"\n{passed}/{len(_results)} passed")
    if failed:
        print("FAILED:", ", ".join(failed))
        raise SystemExit(1)
