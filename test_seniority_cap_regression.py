"""Regression tests for seniority cap / mismatch false positives.

Run: python test_seniority_cap_regression.py
"""

import tempfile
from pathlib import Path

import jd_analyzer as jd

import database as db

db.DB_PATH = Path(tempfile.mkdtemp()) / "test_seniority_cap.db"

import app  # noqa: E402
import evidence_verbal as ev  # noqa: E402
import experience_translation as xt  # noqa: E402
import verbal_retrieval as vr  # noqa: E402

import role_family_vocab as rfv  # noqa: E402

PROFILE = app.load_profile_text()
_results = []

PERM_ITEM = {
    "title": "Permission Governance and Access Lifecycle Design",
    "company": "miHoYo",
    "role_context": "Live Service Operations / Internal Tools Product Ownership",
    "time_period": "2021–2024",
    "factual_context": (
        "Designed role-based access controls for an internal operations platform. "
        "Owned access request intake, approval paths, elevated-access review, "
        "onboarding provisioning, permission-change monitoring, and exception handling."
    ),
    "impact_outcome": "Improved auditability of permission changes.",
    "status": "Verified",
}


def _seed_perm_verbal():
    eid = db.save_evidence_item(PERM_ITEM)
    for rf, text, src in [
        ("Product Operations", (
            "Designed and operated a role-based access-governance workflow for an internal "
            "operations platform, establishing approval paths, elevated-access controls, "
            "new-hire provisioning, permission-change monitoring, and exception handling to "
            "replace fragmented access processes with a traceable lifecycle."
        ), "canonical_seed"),
        ("Technical Program Management", (
            "Owned the operating design for internal permission-governance workflows, coordinating "
            "role-based controls, approval paths, access-lifecycle changes, exception processes, "
            "and traceability requirements across internal users and tool stakeholders."
        ), "user_saved"),
    ]:
        norm = rfv.normalize_role_family_key(rf)
        db.insert_verbal_output(
            eid, ev.OUTPUT_RESUME_BULLET, text,
            role_family=rf, role_family_normalized=norm,
            user_approved=True, is_preferred=True, source=src,
        )
    return eid


PERM_EID = _seed_perm_verbal()

WD_JD = """
Product Operations Program Manager at WD.
3+ years of experience in program management, business operations, product operations,
or a Chief of Staff-adjacent role.
Own the product operating cadence including WBR, MBR, and QBO business reviews.
Provide executive decision support and executive-level materials for senior leadership.
Report to the Chief of Staff. Align Product, Engineering, Finance, Operations, and HR
on business and financial metrics. Chief of Staff-adjacent operating rigor.
"""

SENIOR_DIRECTOR_JD = """
Director of Product Operations.
10+ years of experience required. Staff Program Manager level scope.
Senior Director responsibilities across the product organization.
"""

HUMBLE_TPM_JD = """
Technical Program Manager at Humble Robotics.
Hardware/software integration, systems engineering, technical roadmap, validation V&V,
platform engineering delivery.
"""

PO_BULLET_PREFIX = "Designed and operated a role-based access-governance workflow"
TPM_BULLET_PREFIX = "Owned the operating design for internal permission-governance workflows"


def check(name, cond):
    _results.append((name, bool(cond)))
    print(f"{'PASS' if cond else 'FAIL'}: {name}")


def test_wd_no_seniority_cap():
    parsed = jd.parse_jd(WD_JD)
    check("no staff from chief of staff", "staff" not in parsed["seniority_signals"])
    check("years is 3+", any("3" in s for s in parsed["seniority_signals"]))
    cap, notes = jd._compute_caps(parsed, "Product Operations", {})
    check("no hard cap", cap is None)
    check("no seniority cap note", not any("seniority" in n for n in (notes or [])))


def test_wd_not_skip():
    r = jd.analyze_fit(WD_JD, PROFILE)
    check("not capped at 5", r["base_score"] != 5.0 or "seniority" not in r["scoring_explanation"])
    check("decision not skip", r["decision"] != "Skip")
    check("no seniority cap in explanation", "seniority/years far above" not in r["scoring_explanation"])


def test_wd_no_director_staff_warning():
    result = jd.analyze_fit(WD_JD, PROFILE)
    gaps = xt.classify_gaps(WD_JD, PROFILE, result)
    mismatch = gaps.get("seniority_mismatch") or []
    check("no director/staff/principal warning", not any(
        "Director/Staff/Principal" in m for m in mismatch
    ))


def test_wd_resolves_product_operations():
    result = jd.analyze_fit(WD_JD, PROFILE)
    resolved = xt.resolve_role_family(
        WD_JD, result, job_title="Product Operations Program Manager",
    )
    check("resolved product operations", resolved == "Product Operations")


def test_wd_permission_governance_po_canonical():
    perm = db.get_evidence_item(PERM_EID)
    result = jd.analyze_fit(WD_JD, PROFILE)
    resolved = xt.resolve_role_family(
        WD_JD, result, job_title="Product Operations Program Manager",
    )
    r = vr.retrieve_verbal(perm, ev.OUTPUT_RESUME_BULLET, resolved, WD_JD)
    check("PO canonical selected", PO_BULLET_PREFIX in r["selected_verbal_text"])
    check("not TPM preferred", TPM_BULLET_PREFIX not in r["selected_verbal_text"])
    check("exact PO match", r["relationship_type"] == "exact")


def test_senior_director_still_capped():
    parsed = jd.parse_jd(SENIOR_DIRECTOR_JD)
    check("director detected", "director" in parsed["seniority_signals"])
    cap, notes = jd._compute_caps(parsed, "Product Operations", {})
    check("senior role capped", cap == 5.0)
    check("seniority note present", any("seniority" in n for n in notes))


def test_senior_director_warning():
    result = jd.analyze_fit(SENIOR_DIRECTOR_JD, PROFILE)
    gaps = xt.classify_gaps(SENIOR_DIRECTOR_JD, PROFILE, result)
    mismatch = gaps.get("seniority_mismatch") or []
    check("director warning shown", any("Director/Staff/Principal" in m for m in mismatch))


def test_humble_tpm_retrieval_unchanged():
    perm = db.get_evidence_item(PERM_EID)
    result = jd.analyze_fit(HUMBLE_TPM_JD, PROFILE)
    resolved = xt.resolve_role_family(
        HUMBLE_TPM_JD, result, job_title="Technical Program Manager",
    )
    check("humble resolves tpm", resolved == "Technical Program Management")
    r = vr.retrieve_verbal(perm, ev.OUTPUT_RESUME_BULLET, resolved, HUMBLE_TPM_JD)
    check("tpm preferred exact", r["relationship_type"] == "exact")
    check("tpm bullet", TPM_BULLET_PREFIX in r["selected_verbal_text"])


def test_program_and_tpm_distinct():
    check(
        "distinct norms",
        jd._scrub_seniority_false_positives("chief of staff") != "staff"
        or "staff" not in jd.parse_jd("Chief of Staff role")["seniority_signals"],
    )


def main():
    tests = [
        test_wd_no_seniority_cap,
        test_wd_not_skip,
        test_wd_no_director_staff_warning,
        test_wd_resolves_product_operations,
        test_wd_permission_governance_po_canonical,
        test_senior_director_still_capped,
        test_senior_director_warning,
        test_humble_tpm_retrieval_unchanged,
        test_program_and_tpm_distinct,
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
    print("All seniority cap regression tests passed.")


if __name__ == "__main__":
    main()
