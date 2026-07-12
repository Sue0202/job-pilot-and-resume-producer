"""Reusable role-family relationship map for verbal-output retrieval.

Used for preference-memory lookup only — does not affect fit scores or calibration.
"""

import role_family_resolver as rfrs
import role_family_vocab as rfv

ROLE_FAMILY_RELATIONS = {
    "Technical Program Management": [
        "Program / Implementation",
        "Release Management",
    ],
    "Product Operations": [
        "Internal Tools",
        "Business Operations",
        "Business Systems",
        "Program / Implementation",
    ],
    "Business Systems": [
        "Internal Tools",
        "Product Operations",
    ],
    "Program Management": [
        "Product Operations",
        "Business Operations",
        "Business Systems",
        "Internal Tools",
        "Program / Implementation",
    ],
    "Live Operations": [
        "Release Management",
        "Program / Implementation",
    ],
    "Customer / Partner Operations": [
        "Program / Implementation",
        "Business Operations",
    ],
}


def retrieval_role_family(selected_role_family):
    """Normalize display/JD role family labels for verbal-output lookup."""
    return rfrs.retrieval_role_family(selected_role_family)


def related_role_families(selected_role_family):
    """Return normalized related families for a selected role family (deduped, ordered)."""
    selected = retrieval_role_family(selected_role_family)
    if not selected:
        return []
    sel_norm = rfv.normalize_role_family_key(selected)
    related = ROLE_FAMILY_RELATIONS.get(selected, [])
    if not related:
        related = ROLE_FAMILY_RELATIONS.get(
            _default_lookup().get(sel_norm, selected), []
        )
    out = []
    seen = {sel_norm}
    for rf in related:
        display = rfv.ensure_role_family(rf, save_custom=False)
        norm = rfv.normalize_role_family_key(display)
        if norm and norm not in seen:
            seen.add(norm)
            out.append(display)
    return out


def search_role_families(selected_role_family):
    """Exact selected family first, then configured related families."""
    selected = retrieval_role_family(selected_role_family)
    if not selected:
        return []
    families = [selected]
    families.extend(related_role_families(selected))
    return families


def _default_lookup():
    return {rfv.normalize_role_family_key(v): v for v in rfv.DEFAULT_ROLE_FAMILIES}
