"""Retrieve preferred/canonical verbal wording for resume assembly (not ML training)."""

import database as db
import evidence_verbal as ev
import role_family_vocab as rfv


def preferred_resume_bullet(evidence_item, role_family=""):
    """Return preferred/approved resume bullet for evidence + role family, or None."""
    eid = evidence_item["id"]
    if role_family:
        rf_norm = rfv.normalize_role_family_key(rfv.ensure_role_family(role_family, save_custom=False))
        row = db.get_preferred_verbal_output(eid, ev.OUTPUT_RESUME_BULLET, rf_norm)
        if row and (row.get("generated_text") or "").strip():
            return row["generated_text"].strip()
    for row in db.get_verbal_outputs(eid, ev.OUTPUT_RESUME_BULLET):
        if row.get("is_preferred") or row.get("user_approved"):
            text = (row.get("generated_text") or "").strip()
            if text:
                return text
    return None
