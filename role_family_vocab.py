"""Editable role-family vocabulary for verbal outputs (retrieval only — not scoring)."""

import re

import database as db

VOCAB_ROLE_FAMILY = "role_family"

DEFAULT_ROLE_FAMILIES = [
    "Product Operations",
    "Business Systems",
    "Internal Tools",
    "Program / Implementation",
    "Live Operations",
    "Business Operations",
    "Analytics",
    "Customer / Partner Operations",
]

FEEDBACK_TAG_OPTIONS = [
    "Stronger ownership",
    "Too generic",
    "Too technical",
    "Overclaim",
    "Better wording",
]


def normalize_role_family_key(value):
    s = re.sub(r"\s+", " ", (value or "").strip())
    s = s.replace("–", "-").replace("—", "-")
    return s.lower()


def _default_lookup():
    return {normalize_role_family_key(v): v for v in DEFAULT_ROLE_FAMILIES}


def is_system_default_role_family(value):
    return normalize_role_family_key(value) in _default_lookup()


def all_role_families(extra=None):
    defaults = list(DEFAULT_ROLE_FAMILIES)
    custom = [r["value"] for r in db.get_user_vocabulary(VOCAB_ROLE_FAMILY)]
    merged = defaults + custom + (extra or [])
    seen = set()
    out = []
    for v in merged:
        k = normalize_role_family_key(v)
        if k and k not in seen:
            seen.add(k)
            out.append(_default_lookup().get(k, v))
    return sorted(out, key=lambda x: x.lower())


def ensure_role_family(raw_value, save_custom=True):
    v = (raw_value or "").strip()
    if not v:
        return ""
    key = normalize_role_family_key(v)
    defaults = _default_lookup()
    if key in defaults:
        return defaults[key]
    existing = db.get_user_vocabulary_by_key(VOCAB_ROLE_FAMILY, key)
    if existing:
        return existing["value"]
    display = v[0].upper() + v[1:] if len(v) > 1 and v == v.lower() else v
    if save_custom and not is_system_default_role_family(display):
        db.add_user_vocabulary(VOCAB_ROLE_FAMILY, display, key)
    return display


def custom_role_families_only():
    rows = db.get_user_vocabulary(VOCAB_ROLE_FAMILY)
    return [r for r in rows if not is_system_default_role_family(r["value"])]


def count_role_family_usage(display_value):
    """How many verbal outputs reference this role family."""
    rf_norm = normalize_role_family_key(display_value)
    count = 0
    for item in db.get_evidence_items():
        for out in db.get_verbal_outputs(item["id"]):
            out_norm = (out.get("role_family_normalized") or "").strip()
            if not out_norm:
                out_norm = normalize_role_family_key(out.get("role_family"))
            if out_norm == rf_norm:
                count += 1
    return count


def rename_custom_role_family(vocab_id, new_value):
    row = db.get_user_vocabulary_by_id(vocab_id)
    if not row or row["vocab_type"] != VOCAB_ROLE_FAMILY:
        return False, "Item not found."
    if is_system_default_role_family(row["value"]):
        return False, "System defaults cannot be edited."
    new_value = (new_value or "").strip()
    if not new_value:
        return False, "New name cannot be empty."
    new_key = normalize_role_family_key(new_value)
    if is_system_default_role_family(new_value):
        return False, "That name matches a system default."
    clash = db.get_user_vocabulary_by_key(VOCAB_ROLE_FAMILY, new_key)
    if clash and clash["id"] != vocab_id:
        return False, "Another role family already uses that name."
    old_norm = normalize_role_family_key(row["value"])
    display = ensure_role_family(new_value, save_custom=False)
    db.update_user_vocabulary(vocab_id, display, new_key)
    for item in db.get_evidence_items():
        for out in db.get_verbal_outputs(item["id"]):
            out_norm = (out.get("role_family_normalized") or "").strip()
            if not out_norm:
                out_norm = normalize_role_family_key(out.get("role_family"))
            if out_norm == old_norm:
                db.update_verbal_output(out["id"], {
                    "role_family": display,
                    "role_family_normalized": new_key,
                })
    return True, f"Renamed to '{display}'."


def delete_custom_role_family(vocab_id):
    row = db.get_user_vocabulary_by_id(vocab_id)
    if not row or row["vocab_type"] != VOCAB_ROLE_FAMILY:
        return False, "Item not found."
    if is_system_default_role_family(row["value"]):
        return False, "System defaults cannot be deleted."
    used = count_role_family_usage(row["value"])
    if used:
        return False, f"In use by {used} verbal output(s). Reassign or delete those first."
    db.delete_user_vocabulary(vocab_id)
    return True, "Deleted."
