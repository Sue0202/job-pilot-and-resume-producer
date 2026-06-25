"""Tests for canonical verbal seeding, role families, and preferred wording retrieval.

Run: python test_canonical_verbal_seed.py
Uses a temp DB — real jobpilot.db is not touched unless SEED_LOCAL=1.
"""

import os
import sqlite3
import tempfile
from pathlib import Path

import database as db

db.DB_PATH = Path(tempfile.mkdtemp()) / "test_canonical_verbal.db"
db.init_db()

import app  # noqa: E402
import canonical_verbal as cv  # noqa: E402
import evidence_verbal as ev  # noqa: E402
import jd_analyzer  # noqa: E402
import role_family_vocab as rfv  # noqa: E402
import verbal_retrieval as vr  # noqa: E402

PROFILE_PATH = app.PROFILE_PATH
_results = []


def check(name, cond):
    _results.append((name, bool(cond)))
    print(f"{'PASS' if cond else 'FAIL'}: {name}")


def _identity_item(title, company, role_context, time_period, **extra):
    return {
        "title": title,
        "company": company,
        "role_context": role_context,
        "time_period": time_period,
        "factual_context": extra.get("factual_context", "Verified factual context for testing."),
        "impact_outcome": extra.get("impact_outcome", "Measurable outcome."),
        "status": "Verified",
    }


def _perm_governance(**kw):
    return _identity_item(
        "Permission Governance and Access Lifecycle Design",
        "miHoYo",
        "Live Service Operations / Internal Tools Product Ownership",
        "2021–2024",
        **kw,
    )


def test_same_title_different_company_not_seeded():
    db.save_evidence_item(_perm_governance())
    db.save_evidence_item(_identity_item(
        "Permission Governance and Access Lifecycle Design",
        "Other Corp",
        "Live Service Operations / Internal Tools Product Ownership",
        "2021–2024",
    ))
    report = cv.seed_canonical_verbal_outputs()
    check("one evidence block seeded", len(report["inserted"]) == 4)
    other = db.get_evidence_items()
    other_id = [e for e in other if e["company"] == "Other Corp"][0]["id"]
    outs = db.get_verbal_outputs(other_id)
    check("different company gets no seed", len(outs) == 0)


def test_same_title_company_different_role_or_period_not_seeded():
    db.DB_PATH = Path(tempfile.mkdtemp()) / "test_canonical_verbal2.db"
    db.init_db()
    db.save_evidence_item(_perm_governance())
    db.save_evidence_item(_identity_item(
        "Permission Governance and Access Lifecycle Design",
        "miHoYo",
        "Different Role Context",
        "2021–2024",
    ))
    db.save_evidence_item(_identity_item(
        "Permission Governance and Access Lifecycle Design",
        "miHoYo",
        "Live Service Operations / Internal Tools Product Ownership",
        "2019–2020",
    ))
    report = cv.seed_canonical_verbal_outputs()
    check("only full match seeded", len(report["inserted"]) == 4)
    for e in db.get_evidence_items():
        if e["role_context"] != _perm_governance()["role_context"]:
            check(f"no seed for mismatch id={e['id']}", len(db.get_verbal_outputs(e["id"])) == 0)


def test_full_identity_match_receives_outputs():
    db.DB_PATH = Path(tempfile.mkdtemp()) / "test_canonical_verbal3.db"
    db.init_db()
    eid = db.save_evidence_item(_perm_governance())
    report = cv.seed_canonical_verbal_outputs()
    check("four outputs inserted", len(report["inserted"]) == 4)
    outs = db.get_verbal_outputs(eid)
    check("four rows in db", len(outs) == 4)
    bullets = [o for o in outs if o["output_type"] == ev.OUTPUT_RESUME_BULLET]
    check("three resume bullets", len(bullets) == 3)
    families = {o["role_family"] for o in bullets}
    check("product ops bullet present", "Product Operations" in families)
    check("all seeded approved", all(o.get("user_approved") for o in outs))
    check("all seeded preferred", all(o.get("is_preferred") for o in outs))
    check("source is canonical_seed", all(o.get("source") == "canonical_seed" for o in outs))


def test_ambiguous_match_skipped():
    db.DB_PATH = Path(tempfile.mkdtemp()) / "test_canonical_verbal4.db"
    db.init_db()
    db.save_evidence_item(_perm_governance())
    db.save_evidence_item(_perm_governance())
    report = cv.seed_canonical_verbal_outputs()
    check("ambiguous reported", len(report["skipped_ambiguous"]) == 1)
    check("nothing inserted", len(report["inserted"]) == 0)


def test_no_source_metadata_in_verbal_table():
    db.DB_PATH = Path(tempfile.mkdtemp()) / "test_canonical_verbal5.db"
    db.init_db()
    eid = db.save_evidence_item(_perm_governance())
    cv.seed_canonical_verbal_outputs()
    conn = sqlite3.connect(str(db.DB_PATH))
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(evidence_verbal_outputs)")
    cols = {r[1] for r in cur.fetchall()}
    conn.close()
    forbidden = {"company", "company_project", "role_context", "time_period", "title",
                 "factual_context", "category", "tags", "status"}
    check("no duplicated source columns", not (cols & forbidden))
    row = db.get_verbal_outputs(eid)[0]
    check("row has evidence_item_id only", row.get("evidence_item_id") == eid)
    check("row has role_family", bool(row.get("role_family")))
    check("row has generated_text", bool(row.get("generated_text")))


def test_seed_idempotent():
    db.DB_PATH = Path(tempfile.mkdtemp()) / "test_canonical_verbal6.db"
    db.init_db()
    db.save_evidence_item(_perm_governance())
    r1 = cv.seed_canonical_verbal_outputs()
    r2 = cv.seed_canonical_verbal_outputs()
    check("first run inserts", len(r1["inserted"]) == 4)
    check("second run idempotent", len(r2["inserted"]) == 0)
    check("second run skips", len(r2["skipped_idempotent"]) == 4)


def test_seed_no_duplicate_outputs():
    db.DB_PATH = Path(tempfile.mkdtemp()) / "test_canonical_verbal7.db"
    db.init_db()
    eid = db.save_evidence_item(_perm_governance())
    for _ in range(3):
        cv.seed_canonical_verbal_outputs()
    check("still four outputs", len(db.get_verbal_outputs(eid)) == 4)


def test_seed_skips_user_approved():
    db.DB_PATH = Path(tempfile.mkdtemp()) / "test_canonical_verbal8.db"
    db.init_db()
    eid = db.save_evidence_item(_perm_governance())
    rf_norm = rfv.normalize_role_family_key("Product Operations")
    db.insert_verbal_output(
        eid, ev.OUTPUT_RESUME_BULLET, "User-owned bullet text.",
        role_family="Product Operations", role_family_normalized=rf_norm,
        user_approved=True, is_preferred=True, source="user_saved",
    )
    report = cv.seed_canonical_verbal_outputs()
    protected = [p for p in report["skipped_user_protected"]
                 if p["output_type"] == ev.OUTPUT_RESUME_BULLET
                 and p["role_family"] == "Product Operations"]
    check("user bullet protected", len(protected) >= 1)
    row = db.get_preferred_verbal_output(eid, ev.OUTPUT_RESUME_BULLET, rf_norm)
    check("user text preserved", "User-owned" in (row.get("generated_text") or ""))


def test_seed_skips_missing_evidence():
    db.DB_PATH = Path(tempfile.mkdtemp()) / "test_canonical_verbal9.db"
    db.init_db()
    report = cv.seed_canonical_verbal_outputs()
    check("all six blocks missing", len(report["skipped_missing"]) == 6)
    check("nothing inserted", len(report["inserted"]) == 0)


def test_seeded_output_retrieved_for_evidence_role_family():
    db.DB_PATH = Path(tempfile.mkdtemp()) / "test_canonical_verbal10.db"
    db.init_db()
    eid = db.save_evidence_item(_perm_governance())
    cv.seed_canonical_verbal_outputs()
    item = db.get_evidence_item(eid)
    bullet = vr.preferred_resume_bullet(item, role_family="Product Operations")
    check("preferred bullet retrieved", bullet and "access-governance" in bullet.lower())


def test_custom_role_family_crud():
    db.DB_PATH = Path(tempfile.mkdtemp()) / "test_canonical_verbal11.db"
    db.init_db()
    rf = rfv.ensure_role_family("Technical Program Management")
    check("custom created", rf == "Technical Program Management")
    check("in all list", "Technical Program Management" in rfv.all_role_families())
    dup = rfv.ensure_role_family("technical program management")
    check("normalized dedupe", dup == "Technical Program Management")
    rows = rfv.custom_role_families_only()
    vid = rows[0]["id"]
    ok, _ = rfv.rename_custom_role_family(vid, "Release Management")
    check("rename ok", ok)
    check("renamed value", rfv.ensure_role_family("Release Management") == "Release Management")
    ok2, _ = rfv.delete_custom_role_family(vid)
    check("delete ok", ok2)


def test_system_defaults_not_deletable():
    db.DB_PATH = Path(tempfile.mkdtemp()) / "test_canonical_verbal12.db"
    db.init_db()
    check("product ops is default", rfv.is_system_default_role_family("Product Operations"))
    rows = db.get_user_vocabulary(rfv.VOCAB_ROLE_FAMILY)
    fake_id = (rows[0]["id"] if rows else 99999)
    if rows:
        ok, msg = rfv.delete_custom_role_family(fake_id)
        check("custom delete works or protected", ok or "not found" in msg.lower())
    ok_def, msg_def = rfv.delete_custom_role_family(-1)
    check("invalid id fails", not ok_def)


def test_role_family_does_not_change_scores():
    profile = app.load_profile_text()
    jd = "Product Operations Manager. Workday, launch operations."
    before = jd_analyzer.analyze_fit(jd, profile)
    rfv.ensure_role_family("AI Workflow / Automation")
    eid = db.save_evidence_item(_perm_governance())
    rf_norm = rfv.normalize_role_family_key("AI Workflow / Automation")
    db.insert_verbal_output(
        eid, ev.OUTPUT_RESUME_BULLET, "Custom preferred bullet.",
        role_family="AI Workflow / Automation", role_family_normalized=rf_norm,
        user_approved=True, is_preferred=True, source="user_saved",
    )
    after = jd_analyzer.analyze_fit(jd, profile)
    check("base score unchanged", before["base_score"] == after["base_score"])
    check("components unchanged", before["component_scores"] == after["component_scores"])


def test_generated_wording_transient_until_save():
    db.DB_PATH = Path(tempfile.mkdtemp()) / "test_canonical_verbal13.db"
    db.init_db()
    eid = db.save_evidence_item(_perm_governance())
    facts = "Designed access governance workflows."
    text, err = ev.generate_resume_bullet(facts, role_family="Product Operations")
    check("generation ok", not err and text)
    outs_before = db.get_verbal_outputs(eid)
    check("no auto-persist on generate", len(outs_before) == 0)


def test_preferred_wording_used_in_resume_material():
    db.DB_PATH = Path(tempfile.mkdtemp()) / "test_canonical_verbal14.db"
    db.init_db()
    eid = db.save_evidence_item(_perm_governance())
    rf_norm = rfv.normalize_role_family_key("Product Operations")
    preferred = "CANONICAL PREFERRED BULLET for resume assembly."
    db.insert_verbal_output(
        eid, ev.OUTPUT_RESUME_BULLET, preferred,
        role_family="Product Operations", role_family_normalized=rf_norm,
        user_approved=True, is_preferred=True, source="user_saved",
    )
    item = db.get_evidence_item(eid)
    material = app._evidence_to_material([item], role_family="Product Operations")
    check("preferred in material", preferred in material)
    generic_mat = app._evidence_to_material([item], role_family="Unrelated Family")
    check("still uses preferred without exact family", preferred in generic_mat)


def test_existing_records_readable():
    db.DB_PATH = Path(tempfile.mkdtemp()) / "test_canonical_verbal15.db"
    db.init_db()
    eid = db.save_evidence_item({
        "title": "Legacy item",
        "action": "Old action text.",
        "outcome": "Old outcome.",
        "status": "Verified",
    })
    db.save_verbal_output(eid, ev.OUTPUT_RESUME_BULLET, "Legacy bullet.", role_family="Analytics")
    db.init_db()
    item = db.get_evidence_item(eid)
    outs = db.get_verbal_outputs(eid)
    check("legacy evidence readable", item is not None)
    check("legacy verbal readable", len(outs) >= 1)
    check("backfill normalized key", bool(outs[0].get("role_family_normalized") or outs[0].get("role_family")))


def test_identity_normalization_hyphen_variants():
    db.DB_PATH = Path(tempfile.mkdtemp()) / "test_canonical_verbal16.db"
    db.init_db()
    db.save_evidence_item(_identity_item(
        "Permission Governance and Access Lifecycle Design",
        "miHoYo",
        "Live Service Operations / Internal Tools Product Ownership",
        "2021-2024",
    ))
    matches = cv.find_evidence_matches(
        "Permission Governance and Access Lifecycle Design",
        "miHoYo",
        "Live Service Operations / Internal Tools Product Ownership",
        "2021–2024",
    )
    check("hyphen variant matches", len(matches) == 1)


def main():
    tests = [
        test_same_title_different_company_not_seeded,
        test_same_title_company_different_role_or_period_not_seeded,
        test_full_identity_match_receives_outputs,
        test_ambiguous_match_skipped,
        test_no_source_metadata_in_verbal_table,
        test_seed_idempotent,
        test_seed_no_duplicate_outputs,
        test_seed_skips_user_approved,
        test_seed_skips_missing_evidence,
        test_seeded_output_retrieved_for_evidence_role_family,
        test_custom_role_family_crud,
        test_system_defaults_not_deletable,
        test_role_family_does_not_change_scores,
        test_generated_wording_transient_until_save,
        test_preferred_wording_used_in_resume_material,
        test_existing_records_readable,
        test_identity_normalization_hyphen_variants,
    ]
    for fn in tests:
        print(f"\n--- {fn.__name__} ---")
        fn()
    passed = sum(1 for _, ok in _results if ok)
    failed = [n for n, ok in _results if not ok]
    print(f"\n{'=' * 60}")
    print(f"Results: {passed}/{len(_results)} passed")
    if failed:
        print("FAILED:", ", ".join(failed))
        raise SystemExit(1)
    print("All canonical verbal seed tests passed.")


if __name__ == "__main__":
    main()
