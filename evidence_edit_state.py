"""Safe session-state sync for Evidence Library review/edit widgets.

Streamlit forbids assigning to a widget's session_state key after that widget
has been rendered in the same script run. These helpers defer updates to the
next rerun and apply them before widgets are instantiated.
"""

EVIDENCE_EDIT_WIDGET_PREFIXES = (
    "edit_factual",
    "edit_impact",
    "ec",
    "er",
    "et",
    "es",
    "ecat",
    "ecatnew",
    "etags",
    "etagsnew",
    "enotes",
    "estatus",
)


def evidence_edit_widget_keys(evidence_id):
    return [f"{prefix}_{evidence_id}" for prefix in EVIDENCE_EDIT_WIDGET_PREFIXES]


def _reload_flag_key(evidence_id):
    return f"_evidence_edit_reload_{evidence_id}"


def _pending_tags_key(evidence_id):
    return f"_pending_etags_{evidence_id}"


def _clear_tags_input_key(evidence_id):
    return f"_clear_etagsnew_{evidence_id}"


def request_evidence_edit_reload(state, evidence_id, *, saved_tags=None, clear_tags_input=False):
    """Queue widget reset for the next rerun (call from save/archive/verify handlers)."""
    state[_reload_flag_key(evidence_id)] = True
    if saved_tags is not None:
        state[_pending_tags_key(evidence_id)] = list(saved_tags)
    if clear_tags_input:
        state[_clear_tags_input_key(evidence_id)] = True


def apply_evidence_edit_reload(state, evidence_id):
    """Apply queued widget reset before review/edit widgets render. Returns True if applied."""
    if not state.pop(_reload_flag_key(evidence_id), False):
        return False

    for key in evidence_edit_widget_keys(evidence_id):
        state.pop(key, None)

    pending_tags = state.pop(_pending_tags_key(evidence_id), None)
    if pending_tags is not None:
        state[f"etags_{evidence_id}"] = pending_tags

    if state.pop(_clear_tags_input_key(evidence_id), False):
        state[f"etagsnew_{evidence_id}"] = ""

    return True
