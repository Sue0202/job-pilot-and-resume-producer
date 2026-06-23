"""Tests for experience translation engine (Phase 8).

Run: python test_translation.py
Uses temp DB; never touches real jobpilot.db or candidate_master_profile.md.
"""

import tempfile
from pathlib import Path

import database as db

db.DB_PATH = Path(tempfile.mkdtemp()) / "test_translation.db"
db.init_db()

import app  # noqa: E402
import experience_translation as xt  # noqa: E402
import jd_analyzer  # noqa: E402

PROFILE = app.load_profile_text()
_results = []


def check(name, cond):
    _results.append((name, bool(cond)))
    print(f"{'PASS' if cond else 'FAIL'}: {name}")


def test_business_ops_jd_surfaces_transferable_not_missing():
    jd = """
    Product Operations Manager — Business Systems & Workflow
    Responsibilities: Own cross-functional launch readiness, stakeholder management,
    workflow optimization, internal tools improvement, and operational incident escalation.
    Requirements: SQL, process documentation, program delivery experience.
    """
    result = jd_analyzer.analyze_fit(jd, PROFILE)
    analysis = xt.analyze_translation(PROFILE, jd, result)
    cards = analysis["translation_cards"]
    narrative = analysis["fit_narrative"]
    check("transferable translation cards generated", len(cards) >= 2)
    check("primary challenge is positioning not evidence_retrieval",
          narrative["primary_challenge"] in ("positioning", "true_gap"))
    check("fit narrative mentions positioning or enterprise",
          "positioning" in narrative["summary_text"].lower()
          or "enterprise" in narrative["summary_text"].lower())
    check("has direct or adjacent evidence", bool(result.get("direct_evidence") or result.get("adjacent_evidence")))


def test_tool_gap_distinguishes_adjacent_vs_none():
    jd_tableau = """
    Business Operations Analyst. Requirements: Tableau dashboards, SQL, stakeholder reporting.
    Responsibilities: Build dashboards and translate operational data for leadership.
    """
    result_t = jd_analyzer.analyze_fit(jd_tableau, PROFILE)
    gaps_t = xt.classify_gaps(jd_tableau, PROFILE, result_t)
    tableau_gaps = [g for g in gaps_t["preferred_tool_gaps"] if "tableau" in g.get("tool", "").lower()]
    check("Tableau gap detected", len(tableau_gaps) >= 1)
    if tableau_gaps:
        check("Tableau has adjacent workflow (SQL/EDA)", tableau_gaps[0].get("has_adjacent_workflow") is True)
        check("Tableau note says syntax gap", "syntax gap" in tableau_gaps[0].get("note", "").lower()
              or "adjacent" in tableau_gaps[0].get("note", "").lower())

    jd_salesforce = """
    CRM Operations. Requirements: Salesforce administration, workflow automation.
    Must have 3+ years Salesforce experience.
    """
    result_s = jd_analyzer.analyze_fit(jd_salesforce, PROFILE)
    gaps_s = xt.classify_gaps(jd_salesforce, PROFILE, result_s)
    sf_gaps = [g for g in gaps_s["preferred_tool_gaps"] if "salesforce" in g.get("tool", "").lower()]
    if sf_gaps:
        check("Salesforce gap does not claim direct evidence",
              "do not claim" in sf_gaps[0].get("note", "").lower())


def test_hard_requirement_shows_blocker():
    jd = """
    Senior ML Engineer. Train deep learning models from scratch using PyTorch.
    US citizenship required. Active security clearance required.
    """
    result = jd_analyzer.analyze_fit(jd, PROFILE)
    gaps = xt.classify_gaps(jd, PROFILE, result)
    eligibility = gaps.get("eligibility_constraints") or []
    check("citizenship or clearance flagged", any(
        "citizen" in e.lower() or "clearance" in e.lower() for e in eligibility
    ) or bool(result.get("red_flags")))
    action = xt.recommend_primary_action(result, xt.build_fit_narrative(result, [], gaps), gaps)
    check("hard blocker suggests caution or save", action[1] in ("save", "strengthen"))


def test_temp_evidence_separate_from_library():
    before = len(db.get_evidence_items())
    jd_analyzer.analyze_fit(
        "Need workflow tools.", PROFILE + "\nTemporary recall only",
        added_evidence_quality="Concrete experience example",
    )
    after = len(db.get_evidence_items())
    check("temp evidence not in library", before == after)


def test_resume_uses_approved_mapping_not_fabrication():
    cards = xt.build_translation_cards(PROFILE, """
    Program manager for cross-functional launch readiness and stakeholder management.
    """, jd_analyzer.analyze_fit("""
    Program manager for cross-functional launch readiness and stakeholder management.
    """, PROFILE))
    check("launch mapping present", any(c["mapping_id"] == "launch_coordination" for c in cards))
    material = PROFILE + xt.approved_mappings_to_material(cards)
    check("approved material includes phrasing", "cross-functional launch readiness" in material.lower())
    check("material cites original context not fabrication",
          "maps from" in material.lower() or "R&D" in material or "engineering" in material.lower())
    # Must not claim Salesforce if not in profile.
    check("no Salesforce claim in mapping material", "salesforce" not in material.lower())


def test_profile_isolated_from_persona():
    persona = "Background\tSenior Software Engineer, 7 years in fintech.\nDealbreakers\tUS only"
    check("persona detected", app.looks_like_test_persona(persona))
    check("real profile is Yeyi Su", app._active_profile_name(PROFILE).upper() == "YEYI SU")
    raised = False
    try:
        app.save_profile_text(persona)
    except app.ProfileSafetyError:
        raised = True
    check("persona save blocked", raised)


def test_translation_card_structure():
    jd = "Own launch readiness, incident escalation, and workflow design across stakeholders."
    result = jd_analyzer.analyze_fit(jd, PROFILE)
    cards = xt.build_translation_cards(PROFILE, jd, result)
    if cards:
        c = cards[0]
        for key in ("original_context", "target_role_interpretation", "resume_ready_phrasing",
                    "jd_relevance", "match_label", "why_valid"):
            check(f"card has {key}", key in c and bool(c[key]))


def main():
    test_business_ops_jd_surfaces_transferable_not_missing()
    test_tool_gap_distinguishes_adjacent_vs_none()
    test_hard_requirement_shows_blocker()
    test_temp_evidence_separate_from_library()
    test_resume_uses_approved_mapping_not_fabrication()
    test_profile_isolated_from_persona()
    test_translation_card_structure()
    passed = sum(1 for _, ok in _results if ok)
    print(f"\n{passed}/{len(_results)} checks passed")
    if passed != len(_results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
