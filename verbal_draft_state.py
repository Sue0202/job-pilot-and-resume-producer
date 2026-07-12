"""Transient generated-verbal draft session-state isolation for Evidence Library.

Drafts are never persisted to the database until the user explicitly saves.
Storage and Streamlit widget keys are both scoped by:
  evidence_id + role_family_normalized + output_type
"""

import role_family_vocab as rfv

DATA_KEY_PREFIX = "verbal_draft_"
WIDGET_KEY_PREFIX = "verbal_draft_w_"
ACTIVE_EVIDENCE_KEY = "_verbal_draft_active_evidence_id"
ACTIVE_CONTEXT_KEY = "_verbal_draft_active_context"


def verbal_draft_key(evidence_id, role_family_normalized, output_type):
    """Session-state key for stored transient draft text."""
    eid = int(evidence_id)
    rf_norm = (role_family_normalized or "").strip()
    otype = (output_type or "").strip()
    return f"{DATA_KEY_PREFIX}{eid}_{rf_norm}_{otype}"


def verbal_draft_widget_key(evidence_id, role_family_normalized, output_type):
    """Streamlit text_area widget key — must match the same tuple as verbal_draft_key."""
    eid = int(evidence_id)
    rf_norm = (role_family_normalized or "").strip()
    otype = (output_type or "").strip()
    return f"{WIDGET_KEY_PREFIX}{eid}_{rf_norm}_{otype}"


def _is_data_draft_key(key):
    return key.startswith(DATA_KEY_PREFIX) and not key.startswith(WIDGET_KEY_PREFIX)


def _is_widget_draft_key(key):
    return key.startswith(WIDGET_KEY_PREFIX)


def _draft_evidence_id(key):
    """Extract evidence id from a draft data or widget key, or None."""
    if _is_widget_draft_key(key):
        rest = key[len(WIDGET_KEY_PREFIX):]
    elif _is_data_draft_key(key):
        rest = key[len(DATA_KEY_PREFIX):]
    else:
        return None
    part = rest.split("_", 1)[0]
    try:
        return int(part)
    except ValueError:
        return None


def purge_draft_widgets_for_other_evidence(state, evidence_id):
    """Remove Streamlit draft widget keys for evidence items other than the active one."""
    eid = int(evidence_id)
    for key in list(state.keys()):
        if not _is_widget_draft_key(key):
            continue
        draft_eid = _draft_evidence_id(key)
        if draft_eid is not None and draft_eid != eid:
            state.pop(key, None)


def purge_draft_widgets_except(state, keep_widget_key):
    """Remove all draft widget keys except the active tuple's widget key."""
    for key in list(state.keys()):
        if _is_widget_draft_key(key) and key != keep_widget_key:
            state.pop(key, None)


def purge_legacy_verbal_draft_keys(state):
    """Remove pre-isolation draft keys that omitted evidence_id."""
    for key in list(state.keys()):
        if _is_data_draft_key(key) and _draft_evidence_id(key) is None:
            state.pop(key, None)
        if _is_widget_draft_key(key) and _draft_evidence_id(key) is None:
            state.pop(key, None)


def purge_verbal_drafts_for_other_evidence(state, evidence_id):
    """Remove transient draft *widget* keys for other evidence ids.

    Data keys are kept per evidence tuple so drafts survive switching away and back.
    """
    purge_draft_widgets_for_other_evidence(state, evidence_id)


def on_evidence_selection_changed(state, evidence_id):
    """Call when Review/edit selected evidence id changes."""
    eid = int(evidence_id)
    prev = state.get(ACTIVE_EVIDENCE_KEY)
    if prev is not None and int(prev) != eid:
        purge_draft_widgets_for_other_evidence(state, eid)
        state.pop(ACTIVE_CONTEXT_KEY, None)
    state[ACTIVE_EVIDENCE_KEY] = eid
    purge_legacy_verbal_draft_keys(state)


def prepare_verbal_draft_ui(state, evidence_id, role_family, output_type):
    """Prepare data + widget keys before rendering draft controls.

    Returns (data_key, widget_key, rf_norm, output_type).
    """
    rf_norm = rfv.normalize_role_family_key(
        rfv.ensure_role_family(role_family or "", save_custom=False)
    )
    otype = (output_type or "").strip()
    eid = int(evidence_id)
    ctx = (eid, rf_norm, otype)
    data_key = verbal_draft_key(eid, rf_norm, otype)
    widget_key = verbal_draft_widget_key(eid, rf_norm, otype)

    if state.get(ACTIVE_CONTEXT_KEY) != ctx:
        purge_draft_widgets_except(state, widget_key)
        state.setdefault(data_key, "")
        state[widget_key] = state.get(data_key, "")
        state[ACTIVE_CONTEXT_KEY] = ctx

    return data_key, widget_key, rf_norm, otype


def set_verbal_draft(state, evidence_id, role_family_normalized, output_type, text):
    """Store generated draft text in data + widget slots for the active tuple."""
    data_key = verbal_draft_key(evidence_id, role_family_normalized, output_type)
    widget_key = verbal_draft_widget_key(evidence_id, role_family_normalized, output_type)
    value = text or ""
    state[data_key] = value
    state[widget_key] = value
    state[ACTIVE_CONTEXT_KEY] = (
        int(evidence_id),
        (role_family_normalized or "").strip(),
        (output_type or "").strip(),
    )
    return data_key, widget_key


def get_verbal_draft(state, evidence_id, role_family_normalized, output_type):
    data_key = verbal_draft_key(evidence_id, role_family_normalized, output_type)
    return state.get(data_key, "")


def get_verbal_draft_widget_value(state, evidence_id, role_family_normalized, output_type):
    widget_key = verbal_draft_widget_key(evidence_id, role_family_normalized, output_type)
    return state.get(widget_key, "")
