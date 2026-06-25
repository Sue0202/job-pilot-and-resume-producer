"""Evidence Library controlled vocabularies: defaults + user-created + normalization.

Custom labels are for organization and retrieval only — they do not affect fit scores.
"""

import re

import database as db

VOCAB_CATEGORY = "category"
VOCAB_CAPABILITY_TAG = "capability_tag"
VOCAB_SKILL_TOOL = "skill_tool"

# System defaults (not stored in DB; not editable/deletable via Manage vocabulary).
DEFAULT_CATEGORIES = [
    "Launch / Release",
    "Program Management",
    "Analytics",
    "Support Operations",
    "Platform Operations",
    "Creator Operations",
    "Stakeholder Management",
    "Process Improvement",
    "Access Governance",
    "Business Systems Operations",
    "Enterprise Integration",
    "Financial Operations",
    "Commercial Evaluation",
    "Technical Product Operations",
    "Other",
]

DEFAULT_CAPABILITY_TAGS = [
    "Product Operations",
    "Program Management",
    "Platform Operations",
    "Live Operations / Technical Production",
    "Workflow / Business Operations",
    "Analytics",
    "Launch / Release",
    "Stakeholder Management",
    "Internal Tools",
    "Incident / Escalation",
    "Workflow Design",
    "Access Governance",
    "Role-Based Controls",
    "Approval Workflows",
    "Employee Lifecycle Support",
    "Requirements Discovery",
    "Stakeholder Alignment",
    "Process Standardization",
    "Launch Readiness",
    "Technical Integration",
    "Risk Management",
    "Incident Response",
    "Compliance Coordination",
    "Vendor / Partner Enablement",
    "Financial Approval Process",
    "Commercial Evaluation",
    "User Enablement",
    "Documentation Governance",
    "Support Operations",
    "Creator Operations",
]

DEFAULT_SKILL_SUGGESTIONS = [
    "Jira", "Confluence", "Figma", "Visio", "SQL", "Python", "Snowflake",
    "Databricks", "Salesforce", "Workday", "NetSuite", "SDK", "API", "Excel",
    "Tableau", "Lucidchart",
]

PROOF_STRENGTH_OPTIONS = [
    "Direct",
    "Transferable",
    "Adjacent",
    "Supporting",  # legacy records
    "Draft / Needs verification",
]

EVIDENCE_STATUSES = ["Draft", "Verified", "Archived"]

SELECTOR_HELP = (
    "Choose an existing option or create one for future reuse. "
    "Custom labels improve organization and retrieval; they do not automatically raise fit scores."
)


def normalize_key(value):
    """Lowercase, trim, collapse whitespace — used for deduplication."""
    return re.sub(r"\s+", " ", (value or "").strip().lower())


def _default_lookup(vocab_type):
    if vocab_type == VOCAB_CATEGORY:
        return {normalize_key(v): v for v in DEFAULT_CATEGORIES}
    if vocab_type == VOCAB_CAPABILITY_TAG:
        return {normalize_key(v): v for v in DEFAULT_CAPABILITY_TAGS}
    return {}


def is_system_default(vocab_type, value):
    return normalize_key(value) in _default_lookup(vocab_type)


def _sorted_unique(values):
    seen = set()
    out = []
    for v in values:
        k = normalize_key(v)
        if k and k not in seen:
            seen.add(k)
            out.append(v)
    return sorted(out, key=lambda x: x.lower())


def all_categories(include_custom=True, extra=None):
    """System defaults + user-created categories."""
    defaults = list(DEFAULT_CATEGORIES)
    custom = []
    if include_custom:
        custom = [r["value"] for r in db.get_user_vocabulary(VOCAB_CATEGORY)]
    merged = defaults + custom + (extra or [])
    return _sorted_unique(merged)


def all_capability_tags(include_custom=True, extra=None):
    """System defaults + user-created tags + any extra values (e.g. from current item)."""
    defaults = list(DEFAULT_CAPABILITY_TAGS)
    custom = []
    if include_custom:
        custom = [r["value"] for r in db.get_user_vocabulary(VOCAB_CAPABILITY_TAG)]
    merged = defaults + custom + (extra or [])
    return _sorted_unique(merged)


def skill_suggestions(limit=40):
    """Prior tool names from vocabulary store + evidence records + defaults."""
    from_db = [r["value"] for r in db.get_user_vocabulary(VOCAB_SKILL_TOOL)]
    from_evidence = []
    for item in db.get_evidence_items():
        raw = item.get("skills") or ""
        from_evidence.extend(t.strip() for t in raw.split(",") if t.strip())
    combined = DEFAULT_SKILL_SUGGESTIONS + from_db + from_evidence
    seen = set()
    out = []
    for s in combined:
        k = normalize_key(s)
        if k and k not in seen:
            seen.add(k)
            out.append(s if s in from_db or s in DEFAULT_SKILL_SUGGESTIONS else _title_preserve(s))
        if len(out) >= limit:
            break
    return out


def _title_preserve(value):
    """Preserve user casing when possible; title-case only if all lower."""
    v = (value or "").strip()
    if not v:
        return v
    if v == v.lower():
        return v[0].upper() + v[1:]
    return v


def ensure_vocabulary(vocab_type, raw_value, save_custom=True):
    """Resolve display value; optionally persist new custom vocabulary."""
    v = (raw_value or "").strip()
    if not v:
        return ""
    key = normalize_key(v)
    defaults = _default_lookup(vocab_type)
    if key in defaults:
        return defaults[key]
    existing = db.get_user_vocabulary_by_key(vocab_type, key)
    if existing:
        return existing["value"]
    display = _title_preserve(v)
    if save_custom and not is_system_default(vocab_type, display):
        db.add_user_vocabulary(vocab_type, display, key)
    return display


def ensure_category(value):
    return ensure_vocabulary(VOCAB_CATEGORY, value)


def ensure_capability_tags(values, save_custom=True):
    """Normalize a list of tag strings; register new custom tags."""
    out = []
    seen = set()
    for raw in values:
        t = (raw or "").strip()
        if not t:
            continue
        resolved = ensure_vocabulary(VOCAB_CAPABILITY_TAG, t, save_custom=save_custom)
        key = normalize_key(resolved)
        if resolved and key not in seen:
            seen.add(key)
            out.append(resolved)
    return out


def merge_capability_tags(selected, pending_text="", save_custom=True):
    """Merge multiselect tags with comma-separated pending values; dedupe case-insensitively."""
    combined = list(selected or [])
    combined.extend(parse_comma_tags(pending_text))
    return ensure_capability_tags(combined, save_custom=save_custom)


def register_skills_from_text(skills_text):
    """Parse comma-separated skills and add new names as suggestions (not verified mastery)."""
    tokens = [t.strip() for t in (skills_text or "").split(",") if t.strip()]
    for token in tokens:
        ensure_vocabulary(VOCAB_SKILL_TOOL, token, save_custom=True)


def parse_comma_tags(text):
    return [t.strip() for t in (text or "").split(",") if t.strip()]


def previous_field_values(field_name, limit=30):
    """Distinct prior values for company, role_context, time_period from evidence."""
    seen = set()
    out = []
    for item in db.get_evidence_items():
        val = (item.get(field_name) or "").strip()
        k = normalize_key(val)
        if k and k not in seen:
            seen.add(k)
            out.append(val)
        if len(out) >= limit:
            break
    return sorted(out, key=lambda x: x.lower())


def count_vocabulary_usage(vocab_type, display_value):
    """How many evidence items reference this vocabulary value."""
    key = normalize_key(display_value)
    count = 0
    for item in db.get_evidence_items():
        if vocab_type == VOCAB_CATEGORY:
            if normalize_key(item.get("category") or "") == key:
                count += 1
        elif vocab_type == VOCAB_CAPABILITY_TAG:
            blob = (item.get("capability_tags") or "") + "," + (item.get("tags") or "")
            tags = [normalize_key(t) for t in blob.split(",") if t.strip()]
            if key in tags:
                count += 1
        elif vocab_type == VOCAB_SKILL_TOOL:
            skills = [normalize_key(t) for t in (item.get("skills") or "").split(",") if t.strip()]
            if key in skills:
                count += 1
    return count


def rename_custom_vocabulary(vocab_id, new_value):
    """Rename a user-created vocabulary item and update evidence references."""
    row = db.get_user_vocabulary_by_id(vocab_id)
    if not row:
        return False, "Item not found."
    if is_system_default(row["vocab_type"], row["value"]):
        return False, "System defaults cannot be edited."
    new_value = (new_value or "").strip()
    if not new_value:
        return False, "New name cannot be empty."
    new_key = normalize_key(new_value)
    if is_system_default(row["vocab_type"], new_value):
        return False, "That name matches a system default."
    clash = db.get_user_vocabulary_by_key(row["vocab_type"], new_key)
    if clash and clash["id"] != vocab_id:
        return False, "Another vocabulary item already uses that name."
    old_value = row["value"]
    display = _title_preserve(new_value)
    db.update_user_vocabulary(vocab_id, display, new_key)
    _replace_in_evidence(row["vocab_type"], old_value, display)
    return True, f"Renamed to '{display}'."


def delete_custom_vocabulary(vocab_id):
    """Delete custom vocabulary if unused."""
    row = db.get_user_vocabulary_by_id(vocab_id)
    if not row:
        return False, "Item not found."
    if is_system_default(row["vocab_type"], row["value"]):
        return False, "System defaults cannot be deleted."
    used = count_vocabulary_usage(row["vocab_type"], row["value"])
    if used:
        return False, f"In use by {used} evidence item(s). Rename or reassign first."
    db.delete_user_vocabulary(vocab_id)
    return True, "Deleted."


def merge_custom_vocabulary(from_id, to_id):
    """Merge one custom tag/category/skill into another and delete source."""
    src = db.get_user_vocabulary_by_id(from_id)
    dst = db.get_user_vocabulary_by_id(to_id)
    if not src or not dst:
        return False, "Both items must exist."
    if src["vocab_type"] != dst["vocab_type"]:
        return False, "Can only merge items of the same type."
    if is_system_default(src["vocab_type"], src["value"]):
        return False, "Cannot merge from a system default."
    _replace_in_evidence(src["vocab_type"], src["value"], dst["value"])
    db.delete_user_vocabulary(from_id)
    return True, f"Merged into '{dst['value']}'."


def _replace_in_evidence(vocab_type, old_value, new_value):
    old_key = normalize_key(old_value)
    new_display = new_value
    for item in db.get_evidence_items():
        updates = {}
        if vocab_type == VOCAB_CATEGORY:
            if normalize_key(item.get("category") or "") == old_key:
                updates["category"] = new_display
        elif vocab_type == VOCAB_CAPABILITY_TAG:
            tags = [t.strip() for t in (item.get("capability_tags") or item.get("tags") or "").split(",") if t.strip()]
            if any(normalize_key(t) == old_key for t in tags):
                new_tags = []
                for t in tags:
                    new_tags.append(new_display if normalize_key(t) == old_key else t)
                new_tags = _dedupe_tags(new_tags)
                joined = ", ".join(new_tags)
                updates["capability_tags"] = joined
                updates["tags"] = joined
        elif vocab_type == VOCAB_SKILL_TOOL:
            skills = [t.strip() for t in (item.get("skills") or "").split(",") if t.strip()]
            if any(normalize_key(t) == old_key for t in skills):
                new_skills = []
                for t in skills:
                    new_skills.append(new_display if normalize_key(t) == old_key else t)
                new_skills = _dedupe_tags(new_skills)
                updates["skills"] = ", ".join(new_skills)
        if updates:
            db.update_evidence_item(item["id"], updates)


def _dedupe_tags(tags):
    seen = set()
    out = []
    for t in tags:
        k = normalize_key(t)
        if k and k not in seen:
            seen.add(k)
            out.append(t)
    return out


def custom_vocabulary_only(vocab_type):
    """User-created entries (excludes system defaults even if duplicated in DB)."""
    rows = db.get_user_vocabulary(vocab_type)
    return [r for r in rows if not is_system_default(vocab_type, r["value"])]
