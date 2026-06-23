"""Regression tests for Verkada Business Systems PM JD.

Run: python test_verkada_regression.py
Ensures enterprise people-systems roles are not overstated.
"""

import tempfile
from pathlib import Path

import database as db

db.DB_PATH = Path(tempfile.mkdtemp()) / "test_verkada.db"
db.init_db()

import app  # noqa: E402
import experience_translation as xt  # noqa: E402
import jd_analyzer  # noqa: E402

PROFILE = app.load_profile_text()

# Exact regression JD from product spec.
VERKADA_JD = (
    "Business Systems - Product Manager at Verkada, involving People systems, "
    "data pipelines, enterprise integrations, Workday, NetSuite, Salesforce, "
    "3PL systems, employee lifecycle, Python, JavaScript, HTML, Figma/Lucidchart, "
    "and internal business-process design."
)

VERKADA_JD_FULL = VERKADA_JD + """

Responsibilities:
- Own People systems, HRIS workflows, and employee lifecycle tooling
- Design internal business-process improvements and enterprise integrations
- Partner with Finance and HR on Workday and NetSuite implementations
- Build data pipelines connecting 3PL systems, Salesforce, and internal tools
- Use Python, JavaScript, and HTML for lightweight tooling; Figma/Lucidchart for process design

Requirements:
- Experience with Workday, NetSuite, Salesforce, and enterprise business systems
- Employee lifecycle and people-systems domain knowledge
- JavaScript, HTML, Python
- Cross-functional delivery across engineering and business stakeholders
"""

_results = []


def check(name, cond):
    _results.append((name, bool(cond)))
    print(f"{'PASS' if cond else 'FAIL'}: {name}")


def _analyze(jd):
    result = jd_analyzer.analyze_fit(jd, PROFILE)
    analysis = xt.analyze_translation(PROFILE, jd, result)
    return result, analysis


def test_verkada_exact_jd():
    result, analysis = _analyze(VERKADA_JD)
    narrative = analysis["fit_narrative"]
    gaps = analysis["gap_analysis"]
    family = analysis["resolved_role_family"]

    check("role family is Business Systems (exact JD)", family == xt.BS_ROLE_FAMILY)
    check("role family is NOT Workflow / CX Operations",
          family != "Workflow / CX Operations")
    check("Direct Evidence Fit <= 8.0", narrative["direct_evidence_fit"] <= 8.0)
    check("Direct Evidence Fit < 7.0 (enterprise calibrated)", narrative["direct_evidence_fit"] < 7.0)
    check("Material Gap Risk Significant or Major",
          narrative.get("material_gap_risk") in ("Significant", "Major"))
    check("Resume Competitiveness <= 7.3", narrative["resume_competitiveness"] <= 7.3)
    check("calibrated base <= 7.0", narrative.get("calibrated_base_fit", 99) <= 7.0)
    check("Transferability Fit stays strong", narrative["transferability_fit"] >= 5.0)
    check("Positioning stays strong", 5.0 <= narrative["verbal_positioning_potential"] <= 8.0)

    domain_labels = " ".join(g["domain"] for g in gaps.get("domain_system_gaps", [])).lower()
    check("Workday/HRIS gap flagged", "workday" in domain_labels or "hris" in domain_labels or "people" in domain_labels)
    check("NetSuite gap flagged", "netsuite" in domain_labels)
    check("Employee lifecycle gap flagged", "lifecycle" in domain_labels)

    tech_skills = [g["skill"] for g in gaps.get("technical_skill_gaps", [])]
    check("JavaScript gap flagged", "javascript" in tech_skills)
    check("HTML gap flagged", "html" in tech_skills)

    tool_names = [g["tool"] for g in gaps.get("preferred_tool_gaps", [])]
    check("Figma is tool syntax gap", "figma" in tool_names)
    check("Salesforce is tool syntax gap", "salesforce" in tool_names)
    sf = next((g for g in gaps.get("preferred_tool_gaps", []) if g["tool"] == "salesforce"), None)
    if sf:
        check("Salesforce has adjacent workflow", sf.get("has_adjacent_workflow") is True)

    check("decision is Apply with Tailoring (not Skip)",
          jd_analyzer.decision_for(result["base_score"]) in (
              "Apply with Tailoring", "High Priority", "Maybe - Needs More Evidence"
          ))
    check("summary mentions people-systems gap",
          "people-systems" in narrative["summary_text"].lower()
          or "enterprise" in narrative["summary_text"].lower())


def test_verkada_full_jd():
    result, analysis = _analyze(VERKADA_JD_FULL)
    narrative = analysis["fit_narrative"]
    family = analysis["resolved_role_family"]

    check("full JD: Business Systems role family", family == xt.BS_ROLE_FAMILY)
    check("full JD: NOT Workflow / CX Operations", family != "Workflow / CX Operations")
    check("full JD: Direct Evidence Fit < 7.0", narrative["direct_evidence_fit"] < 7.0)
    check("full JD: Material Gap Risk Significant or Major",
          narrative.get("material_gap_risk") in ("Significant", "Major"))
    check("full JD: Resume Competitiveness <= 7.3", narrative["resume_competitiveness"] <= 7.3)
    check("full JD: calibrated base <= 7.0", narrative.get("calibrated_base_fit", 99) <= 7.0)
    check("full JD: Apply with Tailoring or Apply Selectively",
          (narrative.get("display_decision") or result["decision"]) in (
              "Apply with Tailoring", "Apply Selectively"))
    check("full JD: expected summary text",
          "enterprise" in narrative["summary_text"].lower()
          and ("selectively" in narrative["summary_text"].lower()
               or "people-systems" in narrative["summary_text"].lower()
               or "systems-delivery" in narrative["summary_text"].lower()))


def main():
    test_verkada_exact_jd()
    test_verkada_full_jd()
    passed = sum(1 for _, ok in _results if ok)
    print(f"\n{passed}/{len(_results)} checks passed")
    if passed != len(_results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
