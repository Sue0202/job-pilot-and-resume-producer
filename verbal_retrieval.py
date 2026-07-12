"""Role-family-aware verbal output retrieval for Analyze Job and resume assembly.

Preference-memory / retrieval only — not model training. Does not modify stored wording.
"""

import evidence_verbal as ev
import role_family_relations as rfr
import role_family_resolver as rfrs
import role_family_vocab as rfv
import database as db

RELATIONSHIP_EXACT = "exact"
RELATIONSHIP_RELATED = "related"
RELATIONSHIP_FALLBACK_GENERATED = "fallback_generated"
RELATIONSHIP_FALLBACK_FACTUAL = "fallback_factual"

SOURCE_USER_SAVED = "user_saved"
SOURCE_CANONICAL = "canonical_seed"
SOURCE_GENERATED = "generated"
SOURCE_FACTUAL = "factual"

MIN_FACTUAL_LEN = 30


def is_eligible_for_tailoring(item):
    """Verified evidence with meaningful factual context — excludes archived/title-only."""
    if (item.get("status") or "") != "Verified":
        return False
    facts = _factual_text(item)
    title = (item.get("title") or "").strip()
    if not facts or len(facts) < MIN_FACTUAL_LEN:
        return False
    if title and facts == title:
        return False
    if title and facts.startswith(title) and len(facts) <= len(title) + 10:
        return False
    return True


def filter_tailoring_evidence(items):
    """Verified, meaningful evidence items deduped by id."""
    seen = set()
    out = []
    for item in items or []:
        eid = item.get("id")
        if eid in seen:
            continue
        if not is_eligible_for_tailoring(item):
            continue
        seen.add(eid)
        out.append(item)
    return out


def source_badge_label(retrieval):
    """Human-readable badge for Analyze Job cards."""
    rel = retrieval.get("relationship_type")
    src = retrieval.get("wording_source")
    if rel == RELATIONSHIP_FALLBACK_GENERATED:
        return "Generated fallback"
    if rel == RELATIONSHIP_FALLBACK_FACTUAL:
        return "Factual fallback"
    if src == SOURCE_USER_SAVED and retrieval.get("is_preferred"):
        return "Preferred wording used"
    if src == SOURCE_CANONICAL:
        return "Canonical wording used"
    if src == SOURCE_USER_SAVED:
        return "Approved wording used"
    return "Generated fallback"


def preferred_resume_bullet(evidence_item, role_family=""):
    """Legacy helper — returns resume bullet text only."""
    result = retrieve_verbal(
        evidence_item, ev.OUTPUT_RESUME_BULLET, role_family=role_family,
    )
    text = (result.get("selected_verbal_text") or "").strip()
    return text or None


def retrieve_verbal(
    evidence_item,
    output_type,
    role_family="",
    jd_snippet="",
):
    """Retrieve best verbal output for evidence + role family + output type."""
    eid = evidence_item["id"]
    selected_rf = rfr.retrieval_role_family(role_family or "")
    selected_norm = rfv.normalize_role_family_key(selected_rf)

    best = None
    best_key = None

    for rf in rfr.search_role_families(selected_rf):
        rf_norm = rfv.normalize_role_family_key(rf)
        rel_rank = 0 if rf_norm == selected_norm else 1
        for row in db.get_verbal_outputs_by_slot(eid, output_type, rf_norm):
            tier = _wording_tier(row)
            if tier >= 99:
                continue
            key = (rel_rank, tier, -int(row.get("is_preferred") or 0), -row["id"])
            if best_key is None or key < best_key:
                best_key = key
                best = (row, rf)

    if best:
        row, matched_rf = best
        text = (row.get("generated_text") or "").strip()
        if text:
            rel_type = rfrs.strict_relationship_type(selected_rf, matched_rf)
            result = _result(
                evidence_item,
                selected_rf,
                matched_rf,
                rel_type,
                row.get("source") or SOURCE_USER_SAVED,
                output_type,
                text,
                is_preferred=bool(row.get("is_preferred")),
            )
            result["source_badge"] = source_badge_label(result)
            return result

    if output_type == ev.OUTPUT_RESUME_BULLET:
        text, err = ev.generate_resume_bullet(
            _factual_text(evidence_item),
            _impact_text(evidence_item),
            evidence_item.get("company", ""),
            evidence_item.get("role_context", ""),
            evidence_item.get("skills", ""),
            _capability_tags(evidence_item),
            role_family=selected_rf,
        )
        if text and not err:
            result = _result(
                evidence_item,
                selected_rf,
                selected_rf or "",
                RELATIONSHIP_FALLBACK_GENERATED,
                SOURCE_GENERATED,
                output_type,
                text.strip(),
            )
            result["source_badge"] = source_badge_label(result)
            return result

    if output_type == ev.OUTPUT_TARGET_TRANSLATION:
        text, err = ev.generate_target_translation(
            _factual_text(evidence_item),
            selected_rf,
            jd_snippet,
            impact_outcome=_impact_text(evidence_item),
            capability_tags=_capability_tags(evidence_item),
        )
        if text and not err:
            result = _result(
                evidence_item,
                selected_rf,
                selected_rf or "",
                RELATIONSHIP_FALLBACK_GENERATED,
                SOURCE_GENERATED,
                output_type,
                text.strip(),
            )
            result["source_badge"] = source_badge_label(result)
            return result

    facts = _factual_text(evidence_item)
    result = _result(
        evidence_item,
        selected_rf,
        selected_rf or "",
        RELATIONSHIP_FALLBACK_FACTUAL,
        SOURCE_FACTUAL,
        output_type,
        facts,
    )
    result["source_badge"] = source_badge_label(result)
    return result


def retrieve_evidence_pair(evidence_item, role_family="", jd_snippet=""):
    """Resume bullet + target translation for one evidence item."""
    bullet = retrieve_verbal(
        evidence_item, ev.OUTPUT_RESUME_BULLET, role_family=role_family, jd_snippet=jd_snippet,
    )
    translation = retrieve_verbal(
        evidence_item, ev.OUTPUT_TARGET_TRANSLATION, role_family=role_family, jd_snippet=jd_snippet,
    )
    return {"resume_bullet": bullet, "target_translation": translation}


def build_evidence_material(items, role_family="", jd_snippet=""):
    """Resume appendix text + structured retrieval audit metadata."""
    eligible = filter_tailoring_evidence(items)
    if not eligible:
        return {"material": "", "retrievals": []}
    lines = ["\n\n## Verified Evidence Library (approved by candidate)\n"]
    retrievals = []
    for item in eligible:
        result = retrieve_verbal(
            item, ev.OUTPUT_RESUME_BULLET, role_family=role_family, jd_snippet=jd_snippet,
        )
        retrievals.append(result)
        bullet = (result.get("selected_verbal_text") or "").strip()
        if not bullet:
            continue
        context = " ".join(
            p for p in [item.get("company", ""), item.get("role_context", "")] if p
        )
        lines.append(f"- {bullet}" + (f" ({context})" if context else ""))
    material = "\n".join(lines) if len(lines) > 1 else ""
    return {"material": material, "retrievals": retrievals}


def _wording_tier(row):
    """Lower = higher priority within the same role-family slot."""
    if row.get("is_preferred"):
        if (row.get("source") or "") == SOURCE_USER_SAVED:
            return 0
        return 1
    src = (row.get("source") or "")
    if src == SOURCE_CANONICAL and row.get("user_approved"):
        return 2
    if src == SOURCE_USER_SAVED and row.get("user_approved"):
        return 3
    return 99


def _result(
    evidence_item,
    selected_role_family,
    matched_role_family,
    relationship_type,
    wording_source,
    output_type,
    text,
    is_preferred=False,
):
    return {
        "evidence_item_id": evidence_item["id"],
        "evidence_title": evidence_item.get("title") or "",
        "selected_role_family": selected_role_family or "",
        "matched_role_family": matched_role_family or "",
        "relationship_type": relationship_type,
        "wording_source": wording_source,
        "output_type": output_type,
        "selected_verbal_text": text,
        "is_preferred": is_preferred,
        "source_badge": None,
    }


def _factual_text(item):
    return (
        (item.get("factual_context") or "").strip()
        or (item.get("action") or "").strip()
        or (item.get("original_industry_context") or "").strip()
    )


def _impact_text(item):
    return (item.get("impact_outcome") or item.get("outcome") or "").strip()


def _capability_tags(item):
    blob = (item.get("capability_tags") or item.get("tags") or "")
    return [t.strip() for t in blob.split(",") if t.strip()]
