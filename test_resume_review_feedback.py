"""Tests for resume review / translation feedback layer.

Run: python test_resume_review_feedback.py
Uses a temp DB — real jobpilot.db and candidate_master_profile.md are not touched.
"""

import tempfile
from pathlib import Path

import database as db

db.DB_PATH = Path(tempfile.mkdtemp()) / "test_resume_review.db"
db.init_db()

import app  # noqa: E402
import jd_analyzer  # noqa: E402
import resume_generator as rg  # noqa: E402
import resume_review as rr  # noqa: E402

_results = []


def check(name, cond):
    _results.append((name, bool(cond)))
    print(f"{'PASS' if cond else 'FAIL'}: {name}")


def _sample_resume_data():
    job_row = {
        "job_id": "rv1",
        "company": "Acme",
        "job_title": "Product Operations Manager",
        "description": "Launch operations, cross-functional coordination",
        "responsibilities": "",
        "qualifications": "",
    }
    profile = app.load_profile_text()
    result = __import__("matching").match_job_to_candidate(profile, job_row)
    return rg.generate_resume(profile, job_row, result, "")


def test_resume_level_feedback_persistence():
    vid = db.save_resume_version(
        "Acme", "Product Ops", "rv1", "Product Operations", 7.0,
        "launch", "workday", "", "resume text",
        review_usefulness="Needs edits",
        review_tags="Too generic, Wrong role angle",
        review_notes="Tweak platform angle",
    )
    db.save_resume_review_feedback(
        vid, "Needs edits",
        feedback_tags=["Too generic"],
        notes="Tweak platform angle",
        role_family="Product Operations",
    )
    rows = db.get_translation_feedback(resume_version_id=vid, action_type="resume_review")
    check("resume review row saved", len(rows) >= 1)
    check("usefulness stored", rows[0]["source_text"] == "Needs edits")
    versions = db.get_resume_versions()
    v = next(x for x in versions if x["id"] == vid)
    check("review_usefulness on resume_versions", v["review_usefulness"] == "Needs edits")
    check("review_tags on resume_versions", "Too generic" in v["review_tags"])


def test_edited_bullet_stores_original_and_final():
    data = _sample_resume_data()
    bullets = rr.parse_bullets(data)
    check("bullets parsed", len(bullets) >= 1)
    b = bullets[0]
    original = b["generated_text"]
    final = original + " (edited for clarity)"
    b["final_text"] = final
    b["action"] = rr.BULLET_ACTION_EDITED
    vid = db.save_resume_version(
        "Acme", "PO", "rv1", "Product Operations", 7.0,
        "", "", "", rr.rebuild_full_resume_text(data, bullets),
        bullet_state_json=rr.bullets_to_state_json(bullets),
    )
    fid = db.save_translation_feedback(
        resume_version_id=vid,
        role_family="Product Operations",
        source_text=original,
        generated_text=original,
        final_text=final,
        action_type=rr.BULLET_ACTION_EDITED,
        bullet_index=0,
    )
    row = db.get_translation_feedback(resume_version_id=vid, action_type="edited")[0]
    check("edited feedback id matches", row["id"] == fid)
    check("original generated_text preserved", row["generated_text"] == original)
    check("final_text stored", row["final_text"] == final)


def test_excluded_bullet_not_in_rebuilt_resume():
    data = _sample_resume_data()
    bullets = rr.parse_bullets(data)
    check("has bullets to exclude", len(bullets) >= 2)
    excluded_text = bullets[0]["generated_text"]
    bullets[0]["excluded"] = True
    bullets[0]["action"] = rr.BULLET_ACTION_EXCLUDED
    rebuilt = rr.rebuild_full_resume_text(data, bullets)
    check("excluded bullet absent", excluded_text not in rebuilt)
    check("other bullets remain", any(
        (b.get("final_text") or b.get("generated_text")) in rebuilt
        for b in bullets[1:] if not b.get("excluded")
    ))


def test_use_for_resume_only_no_evidence_record():
    before = len(db.get_evidence_items())
    data = _sample_resume_data()
    bullets = rr.parse_bullets(data)
    bullets.append({
        "id": "recall_0",
        "index": len(bullets),
        "block_header": ["Recalled context (this resume only)"],
        "section": "Recalled context",
        "generated_text": "Coordinated vendor integration for live ops.",
        "final_text": "Coordinated vendor integration for live ops.",
        "action": rr.BULLET_ACTION_KEEP,
        "excluded": False,
        "recalled": True,
    })
    text = rr.rebuild_full_resume_text(data, bullets)
    after = len(db.get_evidence_items())
    check("use-for-resume-only adds no evidence row", before == after)
    check("recalled bullet in resume text", "vendor integration" in text)


def test_save_draft_and_verified_evidence_status():
    draft_id = db.save_evidence_item({
        "title": "Recall example",
        "action": "Led rollout",
        "raw_notes": "Led rollout",
        "bullet_draft": "Led rollout of ticketing integration.",
        "status": "Draft",
    })
    verified_id = db.save_evidence_item({
        "title": "Recall verified",
        "action": "Owned SLA",
        "raw_notes": "Owned SLA",
        "bullet_draft": "Owned SLA reporting for live ops.",
        "status": "Verified",
    })
    draft = db.get_evidence_item(draft_id)
    verified = db.get_evidence_item(verified_id)
    check("draft status is Draft", draft["status"] == "Draft")
    check("verified status is Verified", verified["status"] == "Verified")
    check("draft not in verified pool", draft_id not in [v["id"] for v in db.get_verified_evidence()])
    check("verified in verified pool", verified_id in [v["id"] for v in db.get_verified_evidence()])


def test_preferred_wording_retrieval_by_role_family():
    db.save_translation_feedback(
        role_family="Product Operations",
        generated_text="Original phrasing",
        final_text="Owned cross-functional launch readiness workflows.",
        action_type=rr.BULLET_ACTION_PREFERRED,
    )
    db.save_translation_feedback(
        role_family="Program Management",
        generated_text="Other family",
        final_text="Different wording.",
        action_type=rr.BULLET_ACTION_PREFERRED,
    )
    preferred = db.get_preferred_wording("Product Operations")
    check("preferred wording retrieved", len(preferred) >= 1)
    check("correct role family", preferred[0]["role_family"] == "Product Operations")
    check("final text available", "launch readiness" in (preferred[0]["final_text"] or ""))
    snippet = rr.style_guidance_snippet(preferred, ["Too generic"])
    check("style guidance snippet built", "Preferred phrasing" in snippet)


def test_feedback_does_not_alter_score_or_profile():
    profile_before = app.load_profile_text()
    jd = "Product Operations Manager. Workday, launch operations, cross-functional."
    result_before = jd_analyzer.analyze_fit(jd, profile_before)
    db.save_translation_feedback(
        role_family="Product Operations",
        generated_text="Overclaimed bullet",
        action_type=rr.BULLET_ACTION_PREFERRED,
        feedback_tags="Overclaims experience",
    )
    db.save_resume_review_feedback(
        1, "Not usable", feedback_tags=["Overclaims experience"],
        role_family="Product Operations",
    )
    result_after = jd_analyzer.analyze_fit(jd, profile_before)
    profile_after = app.load_profile_text()
    check("base score unchanged by feedback", result_before["base_score"] == result_after["base_score"])
    check("component scores unchanged", result_before["component_scores"] == result_after["component_scores"])
    check("profile text unchanged", profile_before == profile_after)
    check("profile still YEYI SU", app._active_profile_name(profile_after).upper() == "YEYI SU")


def test_classify_recalled_context():
    existing_id = db.save_evidence_item({
        "title": "Dashboard work",
        "action": "Built Tableau dashboards for release readiness at miHoYo",
        "raw_notes": "Built Tableau dashboards for release readiness at miHoYo",
        "status": "Verified",
    })
    kind, eid = rr.classify_recalled_context(
        "Built Tableau dashboards for release readiness at miHoYo with QA",
        db.get_evidence_items(),
    )
    check("existing evidence detected", kind == "existing_evidence")
    check("existing id returned", eid == existing_id)
    kind2, _ = rr.classify_recalled_context(
        "Completely unique experience about vendor contract renewals",
        db.get_evidence_items(),
    )
    check("new context classified", kind2 == "new")


def test_bullet_state_json_roundtrip():
    data = _sample_resume_data()
    bullets = rr.parse_bullets(data)
    raw = rr.bullets_to_state_json(bullets)
    restored = rr.bullets_from_state_json(raw)
    check("json roundtrip count", len(restored) == len(bullets))
    check("json roundtrip text", restored[0]["generated_text"] == bullets[0]["generated_text"])


def test_init_db_creates_translation_feedback_table():
    db.init_db()
    conn = db._connect()
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='translation_feedback'")
    row = cur.fetchone()
    conn.close()
    check("translation_feedback table exists", row is not None)


if __name__ == "__main__":
    test_init_db_creates_translation_feedback_table()
    test_resume_level_feedback_persistence()
    test_edited_bullet_stores_original_and_final()
    test_excluded_bullet_not_in_rebuilt_resume()
    test_use_for_resume_only_no_evidence_record()
    test_save_draft_and_verified_evidence_status()
    test_preferred_wording_retrieval_by_role_family()
    test_feedback_does_not_alter_score_or_profile()
    test_classify_recalled_context()
    test_bullet_state_json_roundtrip()
    passed = sum(1 for _, ok in _results if ok)
    failed = [n for n, ok in _results if not ok]
    print(f"\n{passed}/{len(_results)} passed")
    if failed:
        print("FAILED:", ", ".join(failed))
        raise SystemExit(1)
