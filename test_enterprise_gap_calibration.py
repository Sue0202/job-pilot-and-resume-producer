"""Enterprise gap display calibration regression tests.

Run: python test_enterprise_gap_calibration.py
"""

import tempfile
from pathlib import Path

import database as db

db.DB_PATH = Path(tempfile.mkdtemp()) / "test_enterprise_cal.db"
db.init_db()

import app  # noqa: E402
import experience_translation as xt  # noqa: E402
import jd_analyzer  # noqa: E402

PROFILE = app.load_profile_text()

VERKADA_JD = (
    "Business Systems - Product Manager at Verkada, involving People systems, "
    "data pipelines, enterprise integrations, Workday, NetSuite, Salesforce, "
    "3PL systems, employee lifecycle, Python, JavaScript, HTML, Figma/Lucidchart, "
    "and internal business-process design."
)

STRONG_PRODUCT_OPS_JD = """
Product Operations Manager — Live Digital Product
Responsibilities: Own product operations, cross-functional program execution, launch readiness,
workflow design, stakeholder management, SQL reporting, and process improvement.
Requirements: 5+ years product operations, program management, cross-functional delivery,
SQL, stakeholder management, process improvement, launch readiness.
"""

CLEARANCE_JD = """
Senior ML Engineer. US citizenship required. Active security clearance required.
Train deep learning models from scratch using PyTorch.
"""

_results = []


def check(name, cond):
    _results.append((name, bool(cond)))
    print(f"{'PASS' if cond else 'FAIL'}: {name}")


def _analyze(jd):
    result = jd_analyzer.analyze_fit(jd, PROFILE)
    analysis = xt.analyze_translation(PROFILE, jd, result)
    return result, analysis


def test_verkada_enterprise_calibration():
    result, analysis = _analyze(VERKADA_JD)
    n = analysis["fit_narrative"]
    gaps = analysis["gap_analysis"]
    cards = analysis["translation_cards"]

    check("domain gaps detected", len(gaps.get("domain_system_gaps", [])) >= 2)
    check("technical gaps detected", len(gaps.get("technical_skill_gaps", [])) >= 2)
    check("Direct Evidence Fit < 7", n["direct_evidence_fit"] < 7.0)
    check("Transferability stays strong", n["transferability_fit"] >= 5.0)
    check("Positioning stays strong", 5.0 <= n["verbal_positioning_potential"] <= 8.0)
    check("Resume Competitiveness <= 7.3", n["resume_competitiveness"] <= 7.3)
    check("calibrated base <= 7.0", n.get("calibrated_base_fit", 99) <= 7.0)
    check("calibrated base >= 6.5", n.get("calibrated_base_fit", 0) >= 6.5)
    check("Material Gap Risk is Significant or Major",
          n.get("material_gap_risk") in ("Significant", "Major"))
    check("not Workflow / CX Operations",
          analysis["resolved_role_family"] != "Workflow / CX Operations")
    check("recommendation not Skip",
          n.get("display_decision") or result["decision"] != "Skip")
    check("Apply with Tailoring or Apply Selectively",
          (n.get("display_decision") or result["decision"]) in (
              "Apply with Tailoring", "Apply Selectively", "Maybe - Needs More Evidence"
          ))
    check("no misleading Direct match · Direct labels",
          not any(
              "Direct match" in (c.get("capability_label") or c.get("match_label", ""))
              and "Direct" == c.get("proof_strength")
              for c in cards
          ))
    check("uses capability-oriented labels",
          any("capability" in (c.get("capability_label") or "").lower()
              or "operating-context" in (c.get("capability_label") or "").lower()
              for c in cards))
    check("summary mentions enterprise gaps",
          "enterprise" in n["summary_text"].lower())


def test_strong_product_ops_not_over_suppressed():
    result, analysis = _analyze(STRONG_PRODUCT_OPS_JD)
    n = analysis["fit_narrative"]
    check("strong product ops can reach High Priority or Apply with Tailoring",
          result["decision"] in ("High Priority", "Apply with Tailoring"))
    check("no enterprise calibration on strong product ops",
          n.get("display_decision") is None or n.get("calibrated_base_fit") == result["base_score"]
          or not xt.needs_enterprise_display_calibration(
              analysis["gap_analysis"], n, PROFILE))
    check("resume competitiveness not artificially capped below 6",
          n["resume_competitiveness"] >= 6.0)


def test_clearance_blocker_unchanged():
    result, analysis = _analyze(CLEARANCE_JD)
    gaps = analysis["gap_analysis"]
    check("clearance or citizenship flagged",
          any("clearance" in e.lower() or "citizen" in e.lower()
              for e in gaps.get("eligibility_constraints", []))
          or bool(result.get("red_flags")))


def test_capability_fit_label_consistency():
    result, analysis = _analyze(VERKADA_JD)
    n = analysis["fit_narrative"]
    check("metric label is Direct Capability Fit, not Direct Evidence Fit",
          n.get("capability_fit_metric_label") == xt.CAPABILITY_FIT_METRIC_LABEL)
    check("metric label is not Direct Evidence Fit",
          n.get("capability_fit_metric_label") != "Direct Evidence Fit")
    check("no literal direct evidence but capability score may be nonzero",
          not n.get("has_literal_direct_evidence") and n.get("direct_capability_fit", 0) > 0)
    check("capability score preserved internally", n.get("direct_evidence_fit") == n.get("direct_capability_fit"))


def test_positioning_cap_with_major_gap():
    result, analysis = _analyze(VERKADA_JD)
    n = analysis["fit_narrative"]
    check("Material Gap Risk is Major", n.get("material_gap_risk") == "Major")
    check("Positioning Potential not 10.0 with Major gap", n["verbal_positioning_potential"] < 10.0)
    check("Positioning Potential capped at 8.0", n["verbal_positioning_potential"] <= 8.0)
    check("Positioning Potential in 7.5-8.0 range for Major enterprise case",
          7.5 <= n["verbal_positioning_potential"] <= 8.0)
    check("positioning cap note flag set", n.get("show_positioning_cap_note") is True)


def test_verkada_recommendation_unchanged():
    result, analysis = _analyze(VERKADA_JD)
    n = analysis["fit_narrative"]
    check("Apply Selectively", n.get("display_decision") == "Apply Selectively")
    check("Medium-Low Priority", n.get("display_priority") == "Medium-Low")
    check("Material Gap Risk Major", n.get("material_gap_risk") == "Major")


def main():
    test_verkada_enterprise_calibration()
    test_capability_fit_label_consistency()
    test_positioning_cap_with_major_gap()
    test_verkada_recommendation_unchanged()
    test_strong_product_ops_not_over_suppressed()
    test_clearance_blocker_unchanged()
    passed = sum(1 for _, ok in _results if ok)
    print(f"\n{passed}/{len(_results)} checks passed")
    if passed != len(_results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
