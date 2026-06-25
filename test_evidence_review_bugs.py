"""Regression tests for Evidence Library review/edit bugs (tags + resume bullet).

Run: python test_evidence_review_bugs.py
"""

import tempfile
from pathlib import Path

import database as db

db.DB_PATH = Path(tempfile.mkdtemp()) / "test_evidence_review_bugs.db"
db.init_db()

import evidence_verbal as ev  # noqa: E402
import evidence_vocabulary as evocab  # noqa: E402

import evidence_edit_state as ees  # noqa: E402

_results = []


def check(name, cond):
    _results.append((name, bool(cond)))
    print(f"{'PASS' if cond else 'FAIL'}: {name}")


def _seed_item(tags="Workflow Design"):
    return db.save_evidence_item({
        "title": "Permission Governance and Access Lifecycle Design",
        "company": "Internal Platform",
        "role_context": "Product Operations",
        "factual_context": (
            "Designed role-based access controls for an internal operations platform. "
            "Owned access request intake, approval paths, elevated-access review, "
            "onboarding provisioning, permission-change monitoring, and exception handling."
        ),
        "impact_outcome": "Improved auditability of permission changes.",
        "capability_tags": tags,
        "tags": tags,
        "status": "Verified",
    })


def test_merge_single_custom_tag():
    merged = evocab.merge_capability_tags(["Workflow Design"], "Onboarding")
    check("single custom tag merged", "Onboarding" in merged)
    check("existing tag kept", "Workflow Design" in merged)


def test_merge_multiple_comma_tags():
    merged = evocab.merge_capability_tags([], "Onboarding, Access Governance, Launch Readiness")
    check("multiple tags parsed", len(merged) == 3)
    check("onboarding present", "Onboarding" in merged)


def test_merge_deduplicates_case_variants():
    merged = evocab.merge_capability_tags(["onboarding"], "Onboarding, ONBOARDING")
    check("case variants deduped", len(merged) == 1)
    check("preserved display casing", merged[0] == "onboarding" or merged[0] == "Onboarding")


def test_custom_tag_persists_on_item():
    eid = _seed_item()
    tags = evocab.merge_capability_tags(["Workflow Design"], "Onboarding")
    db.update_evidence_item(eid, {"capability_tags": ", ".join(tags), "tags": ", ".join(tags)})
    item = db.get_evidence_item(eid)
    check("onboarding on item after save", "Onboarding" in (item.get("capability_tags") or ""))


def test_custom_tag_in_reusable_vocabulary():
    evocab.merge_capability_tags([], "Onboarding")
    all_tags = evocab.all_capability_tags()
    check("onboarding in vocabulary list", "Onboarding" in all_tags)


def test_existing_tags_remain_after_adding_new():
    merged = evocab.merge_capability_tags(["Workflow Design", "Launch Readiness"], "Onboarding")
    check("all three tags present", len(merged) == 3)
    check("workflow kept", "Workflow Design" in merged)


def test_generate_resume_bullet_non_empty_for_access_governance():
    facts = (
        "Designed role-based access controls for an internal operations platform. "
        "Owned access request intake, approval paths, elevated-access review, "
        "onboarding provisioning, permission-change monitoring, and exception handling."
    )
    text, err = ev.generate_resume_bullet(
        facts, "Improved auditability.", "Internal Platform", "Product Operations",
        "Jira", ["Access Governance"], "Product Operations",
    )
    check("no error", err is None)
    check("non-empty bullet", bool(text and text.strip()))
    check("role-based or access-governance phrasing", "role-based" in text.lower() or "access-governance" in text.lower())
    check("no invented workday", "workday" not in text.lower())
    check("concise bullet", 25 <= len(text.split()) <= 45)


def test_generate_resume_bullet_error_when_no_facts():
    text, err = ev.generate_resume_bullet("", "", role_family="Product Operations")
    check("empty facts returns error", err is not None)
    check("empty facts returns no text", not text)


def test_generate_does_not_persist_without_save():
    eid = _seed_item()
    before = db.count_verbal_outputs(eid, ev.OUTPUT_RESUME_BULLET)
    facts = db.get_evidence_item(eid)["factual_context"]
    text, err = ev.generate_resume_bullet(facts, role_family="Product Operations")
    check("generation works", err is None and text)
    after = db.count_verbal_outputs(eid, ev.OUTPUT_RESUME_BULLET)
    check("generate alone does not insert row", before == after)


def test_upsert_persists_verbal_output():
    eid = _seed_item()
    facts = db.get_evidence_item(eid)["factual_context"]
    text, _ = ev.generate_resume_bullet(facts, role_family="Product Operations")
    db.upsert_verbal_output(eid, ev.OUTPUT_RESUME_BULLET, text, role_family="Product Operations")
    saved = db.get_verbal_output_for_role(eid, ev.OUTPUT_RESUME_BULLET, "Product Operations")
    check("upsert saved text", saved and saved.get("generated_text") == text)


def test_verbal_output_does_not_overwrite_factual():
    eid = _seed_item()
    before = db.get_evidence_item(eid)["factual_context"]
    text, _ = ev.generate_resume_bullet(before, role_family="Product Operations")
    db.upsert_verbal_output(eid, ev.OUTPUT_RESUME_BULLET, text, role_family="Product Operations")
    after = db.get_evidence_item(eid)["factual_context"]
    check("factual unchanged", before == after)


def test_save_defers_tag_widget_update_until_rerun():
    """Save must queue tag reload — never assign etags_<id> after widget render."""
    state = {"etags_2": ["Workflow Design"], "etagsnew_2": "Onboarding"}
    tags = evocab.merge_capability_tags(["Workflow Design"], "Onboarding")
    before = list(state["etags_2"])
    ees.request_evidence_edit_reload(state, 2, saved_tags=tags, clear_tags_input=True)
    check("etags not mutated on save", state["etags_2"] == before)
    check("pending tags queued", state[ees._pending_tags_key(2)] == tags)
    check("reload flag set", state[ees._reload_flag_key(2)] is True)
    ees.apply_evidence_edit_reload(state, 2)
    check("tags applied before widget render", state["etags_2"] == tags)
    check("add-tags input cleared", state["etagsnew_2"] == "")


def test_apply_reload_clears_stale_widget_keys():
    state = {
        f"edit_factual_2": "stale",
        f"estatus_2": "Draft",
        f"etags_2": ["Old Tag"],
    }
    state[ees._reload_flag_key(2)] = True
    ees.apply_evidence_edit_reload(state, 2)
    check("stale factual key removed", f"edit_factual_2" not in state)
    check("stale status key removed", f"estatus_2" not in state)


def test_archive_and_verify_persist_status():
    eid1 = db.save_evidence_item({
        "title": "Duplicate incomplete",
        "company": "miHoYo",
        "status": "Draft",
    })
    eid2 = db.save_evidence_item({
        "title": "Complete item",
        "company": "miHoYo",
        "role_context": "Live Service Operations / Internal Tools Product Ownership",
        "time_period": "2021–2024",
        "capability_tags": "Workflow Design, Access Governance",
        "tags": "Workflow Design, Access Governance",
        "status": "Draft",
    })
    db.update_evidence_item(eid1, {"status": "Archived"})
    db.update_evidence_item(eid2, {"status": "Verified"})
    item1 = db.get_evidence_item(eid1)
    item2 = db.get_evidence_item(eid2)
    check("id1 archived", item1["status"] == "Archived")
    check("id2 verified", item2["status"] == "Verified")
    check("id2 tags preserved", "Access Governance" in (item2.get("capability_tags") or ""))


def test_save_with_tags_persists_to_db():
    eid = _seed_item(tags="Workflow Design")
    tags = evocab.merge_capability_tags(["Workflow Design"], "Onboarding, Access Governance")
    db.update_evidence_item(eid, {
        "capability_tags": ", ".join(tags),
        "tags": ", ".join(tags),
        "status": "Verified",
    })
    item = db.get_evidence_item(eid)
    check("all tags in db", all(t in (item.get("capability_tags") or "") for t in tags))
    check("verified status in db", item["status"] == "Verified")


def test_verbal_outputs_unaffected_by_status_change():
    eid = _seed_item()
    db.insert_verbal_output(
        eid, ev.OUTPUT_RESUME_BULLET,
        "Canonical preferred bullet text.",
        role_family="Product Operations",
        role_family_normalized="product operations",
        user_approved=True,
        is_preferred=True,
        source="canonical_seed",
    )
    db.update_evidence_item(eid, {"status": "Verified"})
    outs = db.get_verbal_outputs(eid)
    check("verbal output count unchanged", len(outs) == 1)
    check("verbal text preserved", "Canonical preferred" in outs[0]["generated_text"])


if __name__ == "__main__":
    test_merge_single_custom_tag()
    test_merge_multiple_comma_tags()
    test_merge_deduplicates_case_variants()
    test_custom_tag_persists_on_item()
    test_custom_tag_in_reusable_vocabulary()
    test_existing_tags_remain_after_adding_new()
    test_generate_resume_bullet_non_empty_for_access_governance()
    test_generate_resume_bullet_error_when_no_facts()
    test_generate_does_not_persist_without_save()
    test_upsert_persists_verbal_output()
    test_verbal_output_does_not_overwrite_factual()
    test_save_defers_tag_widget_update_until_rerun()
    test_apply_reload_clears_stale_widget_keys()
    test_archive_and_verify_persist_status()
    test_save_with_tags_persists_to_db()
    test_verbal_outputs_unaffected_by_status_change()
    passed = sum(1 for _, ok in _results if ok)
    failed = [n for n, ok in _results if not ok]
    print(f"\n{passed}/{len(_results)} passed")
    if failed:
        print("FAILED:", ", ".join(failed))
        raise SystemExit(1)
