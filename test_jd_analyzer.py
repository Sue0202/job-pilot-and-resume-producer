"""Tests for the Analyze Job fit-scoring and calibration logic.

Run with either:
    python test_jd_analyzer.py
    pytest test_jd_analyzer.py
"""

import hashlib
import tempfile
from pathlib import Path

import jd_analyzer as jd

PROFILE_PATH = Path(__file__).parent / "candidate_master_profile.md"
PROFILE = PROFILE_PATH.read_text(encoding="utf-8")

STRONG_PRODUCT_OPS_JD = """Product Operations Manager
Responsibilities: own cross-functional workflows, SOPs, launch readiness and release
cadence for our creator platform. Partner with stakeholders across product and
engineering. Drive support escalation and incident response process improvements. Build
dashboards and reporting for operations. Run program management for creator and
community operations.
Qualifications: 3+ years product operations or program management. SQL and dashboard
reporting required. Experience with creator/community operations, platform operations,
stakeholder management and cross-functional coordination. Visa sponsorship available.
"""

BORDERLINE_JD = """Operations Coordinator
Responsibilities: help coordinate workflows and support the team. Assist with reporting.
Qualifications: 2 years experience. Communication skills. Excel.
"""

ML_CLEARANCE_JD = """Senior Machine Learning Engineer
Requirements: 7+ years building and training deep learning models in PyTorch and
TensorFlow. Must be a US citizen with active security clearance. Production code at scale.
"""

# JD requiring tools NOT in the candidate's verified skill set (tableau, looker), so
# appended evidence can measurably change skill coverage.
TOOL_GAP_JD = """Analytics Operations Analyst
Responsibilities: build reporting and dashboards for product operations workflows.
Qualifications: SQL, Tableau, and Looker required. Stakeholder management.
"""


def test_strong_product_ops_scores_high():
    r = jd.analyze_fit(STRONG_PRODUCT_OPS_JD, PROFILE)
    assert r["base_score"] >= 8.5, r["base_score"]
    assert r["decision"] == "High Priority"
    assert r["priority"] == "High"
    assert len(r["direct_evidence"]) >= 2, r["direct_evidence"]


def test_borderline_scores_mid_band():
    r = jd.analyze_fit(BORDERLINE_JD, PROFILE)
    assert 6.5 <= r["base_score"] <= 8.4, r["base_score"]


def test_senior_ml_clearance_skips_with_red_flags():
    r = jd.analyze_fit(ML_CLEARANCE_JD, PROFILE)
    assert r["base_score"] < 5.5, r["base_score"]
    assert r["decision"] == "Skip"
    flags = set(r["red_flags"])
    assert "Security clearance required" in flags
    assert "US citizenship required" in flags
    assert "Deep ML model training" in flags


def test_added_evidence_changes_reanalysis_score():
    base = jd.analyze_fit(TOOL_GAP_JD, PROFILE)
    combined = PROFILE + "\n\n## Additional evidence (temporary)\n" \
        "Built Tableau and Looker dashboards for operational reporting."
    after = jd.analyze_fit(TOOL_GAP_JD, combined)
    assert after["base_score"] != base["base_score"], (base["base_score"], after["base_score"])
    assert after["component_scores"]["skill_fit"] > base["component_scores"]["skill_fit"]


def test_calibration_creates_calibrated_without_changing_base():
    # apply_calibration must clamp and not mutate the base.
    base_score = 7.2
    calibrated = jd.apply_calibration(base_score, 0.6)
    assert calibrated == 7.8
    assert jd.apply_calibration(9.8, 1.0) == 10.0  # clamp high
    assert jd.apply_calibration(0.2, -1.0) == 0.0  # clamp low
    assert base_score == 7.2  # base untouched

    # DB round-trip on a temp database: saving feedback must not change base_score.
    import database as db
    original = db.DB_PATH
    tmp = Path(tempfile.mkdtemp()) / "test.db"
    db.DB_PATH = tmp
    try:
        db.init_db()
        aid = db.save_job_analysis({"company": "C", "job_title": "J",
                                    "base_score": base_score, "overall_score": base_score,
                                    "selected_role_family": "Product Operations"})
        db.save_score_feedback(aid, "Too low", "Missed transferable experience", "",
                               base_score=base_score, adjustment_magnitude=0.6,
                               calibrated_score=calibrated, role_family="Product Operations")
        row = db.get_job_analysis(aid)
        assert row["base_score"] == base_score
        fb = db.get_score_feedback(aid)
        assert fb and fb[0]["calibrated_score"] == calibrated
        assert db.get_calibration_adjustment("Product Operations") == 0.3  # clamped to +/-0.3
    finally:
        db.DB_PATH = original


def test_profile_file_unchanged_after_reanalysis():
    before = hashlib.sha256(PROFILE_PATH.read_bytes()).hexdigest()
    combined = PROFILE + "\n\n## Additional evidence (temporary)\nExtra ops evidence."
    jd.analyze_fit(TOOL_GAP_JD, combined)  # re-analysis must never write the profile file
    after = hashlib.sha256(PROFILE_PATH.read_bytes()).hexdigest()
    assert before == after


def test_evidence_quality_four_categories():
    cases = {
        "I used Figma a lot": "Skill claim only",
        "At miHoYo, used Figma to prototype an internal operations tool":
            "Basic experience example",
        "At miHoYo, designed Figma prototypes for an internal release-operations tool "
        "used by QA and publishing teams": "Concrete experience example",
        "At miHoYo, designed Figma prototypes for an internal release-operations tool "
        "used by QA and publishing teams, reducing manual handoff steps by 30%":
            "Outcome-backed experience example",
        "Salesforce, Tableau, Looker": "Skill claim only",
    }
    for text, expected in cases.items():
        assert jd.classify_evidence_quality(text) == expected, (text, jd.classify_evidence_quality(text))


def test_skill_claim_only_does_not_raise_experience_fit():
    # A pure skill claim must not increase Experience Fit or Resume Evidence Strength.
    base = jd.analyze_fit(TOOL_GAP_JD, PROFILE)
    same = jd.analyze_fit(TOOL_GAP_JD, PROFILE, added_evidence_quality="Skill claim only")
    assert same["component_scores"]["experience_fit"] == base["component_scores"]["experience_fit"]
    assert same["component_scores"]["resume_evidence_strength"] == \
        base["component_scores"]["resume_evidence_strength"]


def test_outcome_backed_raises_experience_fit_more_than_concrete():
    base = jd.analyze_fit(TOOL_GAP_JD, PROFILE)
    concrete = jd.analyze_fit(TOOL_GAP_JD, PROFILE,
                              added_evidence_quality="Concrete experience example")
    outcome = jd.analyze_fit(TOOL_GAP_JD, PROFILE,
                             added_evidence_quality="Outcome-backed experience example")
    be = base["component_scores"]["experience_fit"]
    ce = concrete["component_scores"]["experience_fit"]
    oe = outcome["component_scores"]["experience_fit"]
    assert ce > be, (be, ce)
    assert oe > ce, (ce, oe)
    # Resume Evidence Strength is never auto-raised by temporary evidence.
    assert outcome["component_scores"]["resume_evidence_strength"] == \
        base["component_scores"]["resume_evidence_strength"]


def test_business_systems_angle_not_customer_support():
    biz = ("Business Systems Analyst. Responsibilities: support process improvement and "
           "internal tools, configure Salesforce and Workday integrations across "
           "cross-functional teams. Qualifications: workflow automation, stakeholder "
           "management, reporting.")
    r = jd.analyze_fit(biz, PROFILE)
    assert "Customer Support" not in r["suggested_resume_angle"], r["suggested_resume_angle"]
    assert r["suggested_resume_angle"] in (
        "Internal Tools & Process Improvement",
        "Product Operations & Business Systems",
        "Business Systems / Operations Analyst",
    )


def test_explicit_support_jd_keeps_support_angle():
    support = ("Customer Support Operations Specialist. Responsibilities: manage customer "
               "support tickets, help desk, customer success workflows and escalations.")
    r = jd.analyze_fit(support, PROFILE)
    assert "Customer Support" in r["suggested_resume_angle"], r["suggested_resume_angle"]


def _run():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    for t in tests:
        t()
        print(f"PASS: {t.__name__}")
        passed += 1
    print(f"\n{passed}/{len(tests)} tests passed")


if __name__ == "__main__":
    _run()
