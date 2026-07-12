"""Regression tests for transient verbal draft session-state isolation.

Run: python test_verbal_draft_state.py
"""

import tempfile
from pathlib import Path

import database as db

db.DB_PATH = Path(tempfile.mkdtemp()) / "test_verbal_draft_state.db"
db.init_db()

import evidence_verbal as ev  # noqa: E402
import role_family_vocab as rfv  # noqa: E402
import verbal_draft_state as vds  # noqa: E402

_results = []

ID2_ACCESS_DRAFT = (
    "Designed and operated access-governance workflows for an internal operations platform, "
    "establishing access-request intake, approval paths, permission-change monitoring."
)
ID3_REQUIREMENTS_DRAFT = (
    "Owned requirements intake and prioritization for an internal tool platform, "
    "translating operator feedback into scoped delivery plans."
)
ID5_PLATFORM_FACTS = (
    "Led SDK and platform integration governance at ByteDance. Built phased integration "
    "checklists, acceptance conditions, dependency management, partner coordination, "
    "compliance escalation paths, and end-to-end validation across release milestones."
)

ACCESS_GOVERNANCE_TERMS = (
    "access-governance",
    "access-request",
    "permission-change",
    "role-based access",
    "new-hire provisioning",
    "permission govern",
)


def check(name, cond):
    _results.append((name, bool(cond)))
    print(f"{'PASS' if cond else 'FAIL'}: {name}")


def _po_norm():
    return rfv.normalize_role_family_key("Product Operations")


def _analytics_norm():
    return rfv.normalize_role_family_key("Analytics")


def _seed_evidence(title, company, facts, *, eid_hint=None):
    return db.save_evidence_item({
        "title": title,
        "company": company,
        "role_context": "Product Operations",
        "factual_context": facts,
        "impact_outcome": "Measurable improvement.",
        "capability_tags": "Workflow Design",
        "tags": "Workflow Design",
        "status": "Verified",
    })


def _simulate_ui(state, evidence_id, role_family, output_type=ev.OUTPUT_RESUME_BULLET):
    """Mimic app.py: evidence select + prepare_verbal_draft_ui."""
    vds.on_evidence_selection_changed(state, evidence_id)
    return vds.prepare_verbal_draft_ui(state, evidence_id, role_family, output_type)


def _contains_access_governance_terms(text):
    low = (text or "").lower()
    return any(term in low for term in ACCESS_GOVERNANCE_TERMS)


def test_draft_keys_include_evidence_role_and_output():
    data = vds.verbal_draft_key(5, _po_norm(), ev.OUTPUT_RESUME_BULLET)
    widget = vds.verbal_draft_widget_key(5, _po_norm(), ev.OUTPUT_RESUME_BULLET)
    check("data key contains evidence id", data.startswith("verbal_draft_5_"))
    check("widget key contains evidence id", widget.startswith("verbal_draft_w_5_"))
    check("data and widget keys differ", data != widget)


def test_reproduction_id3_to_id5_no_id2_or_id3_leak():
    """Exact user sequence: ID 3 PO draft -> switch ID 5 PO -> no ID-2/ID-3 text."""
    state = {}
    po = _po_norm()

    # Seed ID 2 access-governance draft in session (simulates earlier session use).
    vds.set_verbal_draft(state, 2, po, ev.OUTPUT_RESUME_BULLET, ID2_ACCESS_DRAFT)

    # Step 1-3: ID 3 + Product Operations + generate draft.
    vds.on_evidence_selection_changed(state, 3)
    _, widget_3, _, _ = _simulate_ui(state, 3, "Product Operations")
    vds.set_verbal_draft(state, 3, po, ev.OUTPUT_RESUME_BULLET, ID3_REQUIREMENTS_DRAFT)
    check("ID 3 draft stored", state[vds.verbal_draft_key(3, po, ev.OUTPUT_RESUME_BULLET)] == ID3_REQUIREMENTS_DRAFT)

    # Step 4-5: switch to ID 5 + Product Operations.
    _, widget_5, _, _ = _simulate_ui(state, 5, "Product Operations")
    shown = state.get(widget_5, "")

    check("ID 2 data draft not shown on ID 5 widget", ID2_ACCESS_DRAFT not in shown)
    check("ID 3 data draft not shown on ID 5 widget", ID3_REQUIREMENTS_DRAFT not in shown)
    check("ID 5 widget draft empty on switch", shown == "")
    check("ID 5 widget does not show ID 2 access text", ID2_ACCESS_DRAFT not in shown)
    check("ID 5 widget does not show ID 3 requirements text", ID3_REQUIREMENTS_DRAFT not in shown)
    check("ID 5 widget has no access-governance terms", not _contains_access_governance_terms(shown))


def test_reproduction_id5_generate_uses_id5_facts():
    state = {}
    po = _po_norm()
    eid_5 = _seed_evidence(
        "Platform Integration Governance and End-to-End Validation Improvement",
        "ByteDance",
        ID5_PLATFORM_FACTS,
    )
    _, widget_5, _, _ = _simulate_ui(state, eid_5, "Product Operations")
    text, err = ev.generate_resume_bullet(ID5_PLATFORM_FACTS, role_family="Product Operations")
    check("ID 5 generation succeeds", err is None and text)
    vds.set_verbal_draft(state, eid_5, po, ev.OUTPUT_RESUME_BULLET, text)
    shown = state.get(widget_5, "")
    check("generated draft synced to widget", shown == text)
    check("ID 5 draft excludes access-governance terms", not _contains_access_governance_terms(shown))
    check(
        "ID 5 draft reflects platform/integration theme",
        any(k in shown.lower() for k in ("integration", "platform", "validation", "sdk", "checklist")),
    )


def test_roundtrip_id5_id3_id5_no_resurfacing():
    state = {}
    po = _po_norm()
    vds.set_verbal_draft(state, 2, po, ev.OUTPUT_RESUME_BULLET, ID2_ACCESS_DRAFT)
    vds.set_verbal_draft(state, 3, po, ev.OUTPUT_RESUME_BULLET, ID3_REQUIREMENTS_DRAFT)
    id5_draft = "ByteDance integration validation draft for ID 5."
    vds.set_verbal_draft(state, 5, po, ev.OUTPUT_RESUME_BULLET, id5_draft)

    _, w5a, _, _ = _simulate_ui(state, 5, "Product Operations")
    check("first ID 5 visit shows ID 5 draft", state[w5a] == id5_draft)

    _, w3, _, _ = _simulate_ui(state, 3, "Product Operations")
    check("ID 3 visit restores ID 3 draft", state[w3] == ID3_REQUIREMENTS_DRAFT)
    check("ID 3 visit not ID 2 text", ID2_ACCESS_DRAFT not in state[w3])

    _, w5b, _, _ = _simulate_ui(state, 5, "Product Operations")
    check("return to ID 5 restores ID 5 draft only", state[w5b] == id5_draft)
    check("return to ID 5 no ID 2 text", ID2_ACCESS_DRAFT not in state[w5b])
    check("return to ID 5 no ID 3 text", ID3_REQUIREMENTS_DRAFT not in state[w5b])


def test_role_family_po_analytics_po_no_stale_text():
    state = {}
    eid = 5
    po = _po_norm()
    analytics = _analytics_norm()
    po_draft = "Product Operations draft for evidence 5."
    analytics_draft = "Analytics draft for evidence 5."

    vds.set_verbal_draft(state, eid, po, ev.OUTPUT_RESUME_BULLET, po_draft)
    vds.set_verbal_draft(state, eid, analytics, ev.OUTPUT_RESUME_BULLET, analytics_draft)

    _, w_po, _, _ = _simulate_ui(state, eid, "Product Operations")
    check("PO widget shows PO draft", state[w_po] == po_draft)

    _, w_analytics, _, _ = _simulate_ui(state, eid, "Analytics")
    check("Analytics widget shows analytics draft", state[w_analytics] == analytics_draft)
    check("Analytics widget not PO draft", state[w_analytics] != po_draft)

    _, w_po_again, _, _ = _simulate_ui(state, eid, "Product Operations")
    check("back to PO restores PO draft", state[w_po_again] == po_draft)
    check("back to PO not analytics draft", state[w_po_again] != analytics_draft)


def test_legacy_shared_data_key_purged_and_not_used_as_widget():
    """Legacy role-family-only data key must not bleed into a new evidence widget."""
    state = {
        "verbal_draft_product operations_resume_bullet": ID2_ACCESS_DRAFT,
    }
    _, widget_5, _, _ = _simulate_ui(state, 5, "Product Operations")
    check("legacy data key removed", "verbal_draft_product operations_resume_bullet" not in state)
    check("ID 5 widget empty after legacy purge", state.get(widget_5, "") == "")
    check("legacy text not in widget", ID2_ACCESS_DRAFT not in state.get(widget_5, ""))


def test_switch_evidence_purges_other_widgets_not_data():
    state = {}
    po = _po_norm()
    vds.set_verbal_draft(state, 2, po, ev.OUTPUT_RESUME_BULLET, ID2_ACCESS_DRAFT)
    vds.on_evidence_selection_changed(state, 5)
    _, widget_5, _, _ = vds.prepare_verbal_draft_ui(state, 5, "Product Operations", ev.OUTPUT_RESUME_BULLET)
    check("evidence 2 data retained in session", vds.verbal_draft_key(2, po, ev.OUTPUT_RESUME_BULLET) in state)
    check("evidence 2 widget purged", vds.verbal_draft_widget_key(2, po, ev.OUTPUT_RESUME_BULLET) not in state)
    check("evidence 5 widget empty", state.get(widget_5, "") == "")
    check("evidence 5 widget not ID 2 text", state.get(widget_5, "") != ID2_ACCESS_DRAFT)


def test_output_type_isolation():
    state = {}
    eid = 5
    po = _po_norm()
    vds.set_verbal_draft(state, eid, po, ev.OUTPUT_RESUME_BULLET, "Resume bullet text")
    vds.set_verbal_draft(state, eid, po, ev.OUTPUT_TARGET_TRANSLATION, "Target translation text")

    _, w_resume, _, otype = _simulate_ui(state, eid, "Product Operations", ev.OUTPUT_RESUME_BULLET)
    check("resume widget shows resume text", state[w_resume] == "Resume bullet text")

    _, w_target, _, otype2 = _simulate_ui(state, eid, "Product Operations", ev.OUTPUT_TARGET_TRANSLATION)
    check("target widget shows target text", state[w_target] == "Target translation text")
    check("target not resume", state[w_target] != state.get(w_resume, ""))
    check("output type preserved", otype2 == ev.OUTPUT_TARGET_TRANSLATION)


def test_saved_preferred_wording_retrievable_per_evidence():
    eid_a = _seed_evidence("Permission Governance", "miHoYo", "Designed permission governance controls.")
    eid_b = _seed_evidence(
        "Platform Integration Governance", "ByteDance", ID5_PLATFORM_FACTS,
    )
    po = _po_norm()
    db.upsert_verbal_output(
        eid_a, ev.OUTPUT_RESUME_BULLET,
        "Saved preferred wording for evidence A.",
        role_family="Product Operations",
        role_family_normalized=po,
        source="user_saved",
        is_preferred=True,
    )
    db.upsert_verbal_output(
        eid_b, ev.OUTPUT_RESUME_BULLET,
        "Saved preferred wording for evidence B.",
        role_family="Product Operations",
        role_family_normalized=po,
        source="user_saved",
        is_preferred=True,
    )
    saved_a = db.get_verbal_outputs_for_role(eid_a, "Product Operations", po)
    saved_b = db.get_verbal_outputs_for_role(eid_b, "Product Operations", po)
    check("A saved row present", len(saved_a) == 1)
    check("B saved row present", len(saved_b) == 1)
    check("A text correct", "evidence A" in saved_a[0]["generated_text"])
    check("B text correct", "evidence B" in saved_b[0]["generated_text"])
    check("saved rows scoped to evidence A", saved_a[0]["evidence_item_id"] == eid_a)
    check("saved rows scoped to evidence B", saved_b[0]["evidence_item_id"] == eid_b)


if __name__ == "__main__":
    test_draft_keys_include_evidence_role_and_output()
    test_reproduction_id3_to_id5_no_id2_or_id3_leak()
    test_reproduction_id5_generate_uses_id5_facts()
    test_roundtrip_id5_id3_id5_no_resurfacing()
    test_role_family_po_analytics_po_no_stale_text()
    test_legacy_shared_data_key_purged_and_not_used_as_widget()
    test_switch_evidence_purges_other_widgets_not_data()
    test_output_type_isolation()
    test_saved_preferred_wording_retrievable_per_evidence()
    passed = sum(1 for _, ok in _results if ok)
    failed = [n for n, ok in _results if not ok]
    print(f"\n{passed}/{len(_results)} passed")
    if failed:
        print("FAILED:", ", ".join(failed))
        raise SystemExit(1)
