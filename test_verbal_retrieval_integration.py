"""Integration tests for role-family-aware verbal retrieval in Analyze Job / resume assembly.

Run: python test_verbal_retrieval_integration.py
Uses temp DB — real jobpilot.db is not modified.
"""

import tempfile
from pathlib import Path

import database as db

db.DB_PATH = Path(tempfile.mkdtemp()) / "test_verbal_retrieval.db"
db.init_db()

import app  # noqa: E402
import evidence_verbal as ev  # noqa: E402
import experience_translation as xt  # noqa: E402
import jd_analyzer  # noqa: E402
import role_family_vocab as rfv  # noqa: E402
import verbal_retrieval as vr  # noqa: E402

PROFILE_PATH = app.PROFILE_PATH
_results = []

PO_BULLET = (
    "Designed and operated a role-based access-governance workflow for an internal "
    "operations platform, establishing approval paths, elevated-access controls, "
    "new-hire provisioning, permission-change monitoring, and exception handling to "
    "replace fragmented access processes with a traceable lifecycle."
)
TPM_BULLET = (
    "Owned the operating design for internal permission-governance workflows, coordinating "
    "role-based controls, approval paths, access-lifecycle changes, exception processes, "
    "and traceability requirements across internal users and tool stakeholders."
)
BS_BULLET = (
    "Designed access-lifecycle workflows for an internal operations platform, covering "
    "role tiers, accountable-owner approvals, elevated-access controls, onboarding "
    "provisioning, transfer and offboarding changes, and auditable exception handling."
)
FACTS = (
    "Designed role-based access controls for an internal operations platform. "
    "Owned access request intake, approval paths, elevated-access review, "
    "onboarding provisioning, permission-change monitoring, and exception handling."
)


def check(name, cond):
    _results.append((name, bool(cond)))
    print(f"{'PASS' if cond else 'FAIL'}: {name}")


def _perm_item(**kw):
    base = {
        "title": "Permission Governance and Access Lifecycle Design",
        "company": "miHoYo",
        "role_context": "Live Service Operations / Internal Tools Product Ownership",
        "time_period": "2021–2024",
        "factual_context": FACTS,
        "impact_outcome": "Improved auditability of permission changes.",
        "capability_tags": "Access Governance, Workflow Design",
        "tags": "Access Governance, Workflow Design",
        "status": "Verified",
    }
    base.update(kw)
    return base


def _seed_permission_governance_verbal(eid):
    for rf, text, src, pref in [
        ("Product Operations", PO_BULLET, "canonical_seed", True),
        ("Business Systems", BS_BULLET, "canonical_seed", True),
        ("Technical Program Management", TPM_BULLET, "user_saved", True),
    ]:
        norm = rfv.normalize_role_family_key(rfv.ensure_role_family(rf))
        db.insert_verbal_output(
            eid, ev.OUTPUT_RESUME_BULLET, text,
            role_family=rf, role_family_normalized=norm,
            user_approved=True, is_preferred=pref, source=src,
        )


def test_exact_preferred_beats_canonical():
    eid = db.save_evidence_item(_perm_item())
    po_norm = rfv.normalize_role_family_key("Product Operations")
    db.insert_verbal_output(
        eid, ev.OUTPUT_RESUME_BULLET, PO_BULLET,
        role_family="Product Operations", role_family_normalized=po_norm,
        user_approved=True, is_preferred=True, source="canonical_seed",
    )
    db.insert_verbal_output(
        eid, ev.OUTPUT_RESUME_BULLET, "User preferred PO bullet wins.",
        role_family="Product Operations", role_family_normalized=po_norm,
        user_approved=True, is_preferred=True, source="user_saved",
    )
    item = db.get_evidence_item(eid)
    r = vr.retrieve_verbal(item, ev.OUTPUT_RESUME_BULLET, "Product Operations")
    check("user preferred wins", "User preferred PO bullet wins" in r["selected_verbal_text"])
    check("exact match", r["relationship_type"] == vr.RELATIONSHIP_EXACT)


def test_exact_canonical_beats_related():
    eid = db.save_evidence_item(_perm_item())
    po_norm = rfv.normalize_role_family_key("Product Operations")
    bs_norm = rfv.normalize_role_family_key("Business Systems")
    db.insert_verbal_output(
        eid, ev.OUTPUT_RESUME_BULLET, PO_BULLET,
        role_family="Product Operations", role_family_normalized=po_norm,
        user_approved=True, is_preferred=True, source="canonical_seed",
    )
    db.insert_verbal_output(
        eid, ev.OUTPUT_RESUME_BULLET, BS_BULLET,
        role_family="Business Systems", role_family_normalized=bs_norm,
        user_approved=True, is_preferred=True, source="canonical_seed",
    )
    item = db.get_evidence_item(eid)
    r = vr.retrieve_verbal(item, ev.OUTPUT_RESUME_BULLET, "Product Operations")
    check("PO canonical not BS", "access-governance workflow for an internal operations platform" in r["selected_verbal_text"])
    check("exact not related", r["relationship_type"] == vr.RELATIONSHIP_EXACT)


def test_related_preferred_beats_generation():
    eid = db.save_evidence_item(_perm_item())
    bs_norm = rfv.normalize_role_family_key("Business Systems")
    db.insert_verbal_output(
        eid, ev.OUTPUT_RESUME_BULLET, BS_BULLET,
        role_family="Business Systems", role_family_normalized=bs_norm,
        user_approved=True, is_preferred=True, source="canonical_seed",
    )
    item = db.get_evidence_item(eid)
    r = vr.retrieve_verbal(item, ev.OUTPUT_RESUME_BULLET, "Product Operations")
    check("related BS used", "access-lifecycle workflows" in r["selected_verbal_text"])
    check("related match", r["relationship_type"] == vr.RELATIONSHIP_RELATED)


def test_unknown_custom_no_unsafe_guess():
    eid = db.save_evidence_item(_perm_item())
    _seed_permission_governance_verbal(eid)
    item = db.get_evidence_item(eid)
    r = vr.retrieve_verbal(item, ev.OUTPUT_RESUME_BULLET, "Marketing Analytics")
    check("unknown uses generated or factual not TPM", TPM_BULLET not in r["selected_verbal_text"]
          or r["relationship_type"] in (vr.RELATIONSHIP_FALLBACK_GENERATED, vr.RELATIONSHIP_FALLBACK_FACTUAL))


def test_archived_excluded():
    archived = db.save_evidence_item(_perm_item(status="Archived"))
    verified = db.save_evidence_item(_perm_item(title="Verified only item"))
    items = db.get_evidence_items()
    eligible = vr.filter_tailoring_evidence(items)
    ids = {e["id"] for e in eligible}
    check("archived out", archived not in ids)
    check("verified in", verified in ids)


def test_incomplete_excluded():
    incomplete = db.save_evidence_item({
        "title": "Title only item",
        "factual_context": "Title only item",
        "status": "Verified",
    })
    items = db.get_evidence_items()
    eligible = vr.filter_tailoring_evidence(items)
    check("title-only out", incomplete not in {e["id"] for e in eligible})


def test_dedupe_by_id():
    item = _perm_item()
    eid = db.save_evidence_item(item)
    dupes = [{"id": eid, **item}, {"id": eid, **item}]
    eligible = vr.filter_tailoring_evidence(dupes)
    check("one entry", len(eligible) == 1)


def test_analyze_job_uses_verbal_not_full_factual():
    eid = db.save_evidence_item(_perm_item())
    _seed_permission_governance_verbal(eid)
    item = db.get_evidence_item(eid)
    profile = app.load_profile_text()
    jd = "Product Operations Manager. Internal tools, access governance, launch operations."
    result = jd_analyzer.analyze_fit(jd, profile)
    result["selected_role_family"] = "Product Operations"
    cards = xt.build_translation_cards(profile, jd, result, [item])
    ev_cards = [c for c in cards if c.get("source") == "evidence_library"]
    check("one evidence card", len(ev_cards) == 1)
    phrasing = ev_cards[0]["resume_ready_phrasing"]
    check("uses PO bullet not full facts", PO_BULLET[:60] in phrasing)
    check("not raw factual dump", phrasing != FACTS)
    check("badge present", ev_cards[0].get("source_badge"))


def test_resume_assembly_matches_analyze_job():
    eid = db.save_evidence_item(_perm_item())
    _seed_permission_governance_verbal(eid)
    item = db.get_evidence_item(eid)
    profile = app.load_profile_text()
    jd = "Product Operations Manager."
    result = {"selected_role_family": "Product Operations"}
    cards = xt.build_translation_cards(profile, jd, result, [item])
    card_phrasing = [c for c in cards if c.get("source") == "evidence_library"][0]["resume_ready_phrasing"]
    material = app._evidence_to_material([item], role_family="Product Operations", jd_snippet=jd)
    check("same PO bullet in resume material", PO_BULLET[:60] in material)
    check("matches card phrasing", card_phrasing[:60] in material)


def test_tpm_regression():
    eid = db.save_evidence_item(_perm_item())
    _seed_permission_governance_verbal(eid)
    item = db.get_evidence_item(eid)
    r = vr.retrieve_verbal(item, ev.OUTPUT_RESUME_BULLET, "Technical Program Management")
    check("TPM bullet selected", "permission-governance workflows" in r["selected_verbal_text"])
    check("user_saved source", r["wording_source"] == vr.SOURCE_USER_SAVED)
    check("preferred", r["is_preferred"])
    check("exact TPM", r["relationship_type"] == vr.RELATIONSHIP_EXACT)
    check("not PO bullet", PO_BULLET[:40] not in r["selected_verbal_text"])


def test_product_operations_regression():
    eid = db.save_evidence_item(_perm_item())
    _seed_permission_governance_verbal(eid)
    item = db.get_evidence_item(eid)
    r = vr.retrieve_verbal(item, ev.OUTPUT_RESUME_BULLET, "Product Operations")
    check("PO bullet", "role-based access-governance workflow" in r["selected_verbal_text"])
    check("canonical or preferred", r["wording_source"] in (vr.SOURCE_CANONICAL, vr.SOURCE_USER_SAVED))
    check("exact PO", r["relationship_type"] == vr.RELATIONSHIP_EXACT)


def test_business_systems_regression():
    eid = db.save_evidence_item(_perm_item())
    _seed_permission_governance_verbal(eid)
    item = db.get_evidence_item(eid)
    r = vr.retrieve_verbal(item, ev.OUTPUT_RESUME_BULLET, "Business Systems")
    check("BS bullet", "access-lifecycle workflows" in r["selected_verbal_text"])
    check("exact BS", r["relationship_type"] == vr.RELATIONSHIP_EXACT)


def test_no_saved_wording_generated_fallback():
    eid = db.save_evidence_item(_perm_item())
    item = db.get_evidence_item(eid)
    r = vr.retrieve_verbal(item, ev.OUTPUT_RESUME_BULLET, "Product Operations")
    check("generated fallback", r["relationship_type"] == vr.RELATIONSHIP_FALLBACK_GENERATED)
    check("generated source", r["wording_source"] == vr.SOURCE_GENERATED)
    check("badge", r["source_badge"] == "Generated fallback")


def test_scoring_unchanged():
    profile = app.load_profile_text()
    jd = "Product Operations Manager. Workday, launch operations."
    before = jd_analyzer.analyze_fit(jd, profile)
    eid = db.save_evidence_item(_perm_item())
    _seed_permission_governance_verbal(eid)
    after = jd_analyzer.analyze_fit(jd, profile)
    check("base score unchanged", before["base_score"] == after["base_score"])
    check("components unchanged", before["component_scores"] == after["component_scores"])


def test_verbal_outputs_not_overwritten():
    eid = db.save_evidence_item(_perm_item())
    _seed_permission_governance_verbal(eid)
    before = db.get_verbal_outputs(eid)
    item = db.get_evidence_item(eid)
    for rf in ("Technical Program Management", "Product Operations", "Business Systems"):
        vr.retrieve_verbal(item, ev.OUTPUT_RESUME_BULLET, rf)
        vr.build_evidence_material([item], role_family=rf)
        xt.build_translation_cards("", "jd", {"selected_role_family": rf}, [item])
    after = db.get_verbal_outputs(eid)
    check("same output count", len(before) == len(after))
    check("TPM text preserved", any(TPM_BULLET in (o.get("generated_text") or "") for o in after))


WD_JD = """
Product Operations Program Manager at WD.
Own the product operating cadence including WBR, MBR, and QBO business reviews.
Provide executive decision support, action tracking, and decision hygiene.
Align Product, Engineering, Finance, Operations, and HR on business and financial metrics.
Chief of Staff-adjacent operating rigor for the product organization.
"""

HUMBLE_TPM_JD = """
Technical Program Manager at Humble Robotics.
Hardware/software integration, systems engineering, technical roadmap, validation V&V,
platform engineering delivery across robotics product development.
"""


def test_wd_resolves_product_operations_not_tpm():
    import role_family_resolver as rfrs
    scoring = {"selected_role_family": "Program Management"}
    resolved = xt.resolve_role_family(
        WD_JD, scoring, job_title="Product Operations Program Manager",
    )
    check("wd resolves product operations", resolved == rfrs.PRODUCT_OPERATIONS)
    check("wd not tpm", resolved != "Technical Program Management")


def test_generic_program_manager_not_tpm_exact():
    eid = db.save_evidence_item(_perm_item())
    _seed_permission_governance_verbal(eid)
    item = db.get_evidence_item(eid)
    jd = "Program Manager. Cross-functional program delivery and milestone tracking."
    resolved = xt.resolve_role_family(
        jd, {"selected_role_family": "Program Management"}, job_title="Program Manager",
    )
    r = vr.retrieve_verbal(item, ev.OUTPUT_RESUME_BULLET, resolved, jd)
    check("resolved generic program management", resolved == "Program Management")
    check(
        "not tpm exact",
        not (
            r.get("matched_role_family") == "Technical Program Management"
            and r.get("relationship_type") == vr.RELATIONSHIP_EXACT
        ),
    )


def test_wd_card_uses_product_operations_canonical():
    eid = db.save_evidence_item(_perm_item())
    _seed_permission_governance_verbal(eid)
    item = db.get_evidence_item(eid)
    profile = app.load_profile_text()
    scoring = jd_analyzer.analyze_fit(WD_JD, profile)
    scoring["selected_role_family"] = "Program Management"
    resolved = xt.resolve_role_family(
        WD_JD, scoring, job_title="Product Operations Program Manager",
    )
    scoring["selected_role_family"] = resolved
    cards = xt.build_translation_cards(profile, WD_JD, scoring, [item])
    evc = [c for c in cards if c.get("source") == "evidence_library"]
    check("wd evidence card present", len(evc) == 1)
    c = evc[0]
    check("wd retrieval rf is PO", c.get("retrieval_role_family") == "Product Operations")
    check("wd matched rf is PO", c.get("role_family_used") == "Product Operations")
    check("wd canonical badge", c.get("source_badge") == "Canonical wording used")
    check("wd exact match", c.get("relationship_type") == "exact")
    check("wd PO bullet", "role-based access-governance workflow" in c.get("resume_ready_phrasing", ""))
    check("wd not tpm preferred", "permission-governance workflows, coordinating" not in c.get("resume_ready_phrasing", ""))


def test_humble_tpm_regression_still_exact():
    eid = db.save_evidence_item(_perm_item())
    _seed_permission_governance_verbal(eid)
    item = db.get_evidence_item(eid)
    resolved = xt.resolve_role_family(
        HUMBLE_TPM_JD,
        {"selected_role_family": "Program Management"},
        job_title="Technical Program Manager",
    )
    check("humble resolves tpm", resolved == "Technical Program Management")
    r = vr.retrieve_verbal(item, ev.OUTPUT_RESUME_BULLET, resolved, HUMBLE_TPM_JD)
    check("humble tpm exact", r["relationship_type"] == vr.RELATIONSHIP_EXACT)
    check("humble tpm preferred", "permission-governance workflows" in r["selected_verbal_text"])


def test_program_and_tpm_distinct_normalized():
    import role_family_vocab as rfv
    pm = rfv.normalize_role_family_key("Program Management")
    tpm = rfv.normalize_role_family_key("Technical Program Management")
    pi = rfv.normalize_role_family_key("Program / Implementation")
    check("pm != tpm", pm != tpm)
    check("tpm != pi", tpm != pi)


def main():
    tests = [
        test_exact_preferred_beats_canonical,
        test_exact_canonical_beats_related,
        test_related_preferred_beats_generation,
        test_unknown_custom_no_unsafe_guess,
        test_archived_excluded,
        test_incomplete_excluded,
        test_dedupe_by_id,
        test_analyze_job_uses_verbal_not_full_factual,
        test_resume_assembly_matches_analyze_job,
        test_tpm_regression,
        test_product_operations_regression,
        test_business_systems_regression,
        test_no_saved_wording_generated_fallback,
        test_scoring_unchanged,
        test_verbal_outputs_not_overwritten,
        test_wd_resolves_product_operations_not_tpm,
        test_generic_program_manager_not_tpm_exact,
        test_wd_card_uses_product_operations_canonical,
        test_humble_tpm_regression_still_exact,
        test_program_and_tpm_distinct_normalized,
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
    print("All verbal retrieval integration tests passed.")


if __name__ == "__main__":
    main()
