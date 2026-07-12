"""Resume review, bullet parsing, and translation preference helpers.

Behavior-driven feedback — no per-bullet rating forms. Preferences are used only
as retrieval/style guidance for future resume generation, not model training.
"""

import json
import re

RESUME_USEFULNESS_OPTIONS = ["Ready to use", "Needs edits", "Not usable"]

REVIEW_FEEDBACK_TAGS = [
    "Too generic",
    "Wrong role angle",
    "Understates my ownership",
    "Overclaims experience",
    "Missing a key capability",
    "Poor wording / not how I would say it",
]

BULLET_ACTION_KEEP = "keep"
BULLET_ACTION_EDITED = "edited"
BULLET_ACTION_EXCLUDED = "excluded"
BULLET_ACTION_PREFERRED = "preferred"


def parse_bullets(resume_data):
    """Extract resume bullets from generated resume_data dict, preserving block headers."""
    exp = resume_data.get("professional_experience") or ""
    bullets = []
    idx = 0
    for block in re.split(r"\n\s*\n", exp.strip()):
        if not block.strip():
            continue
        header_lines = []
        for line in block.splitlines():
            s = line.strip()
            if s.startswith("•"):
                text = s.lstrip("•").strip()
                bullets.append({
                    "id": f"b{idx}",
                    "index": idx,
                    "block_header": list(header_lines),
                    "section": (header_lines[0] if header_lines else "Experience")[:80],
                    "generated_text": text,
                    "final_text": text,
                    "action": BULLET_ACTION_KEEP,
                    "excluded": False,
                    "evidence_item_id": None,
                })
                idx += 1
            else:
                header_lines.append(line)
    return bullets


def active_bullets(bullet_states):
    """Return bullets that are not excluded."""
    return [
        b for b in bullet_states
        if not b.get("excluded") and b.get("action") != BULLET_ACTION_EXCLUDED
    ]


def rebuild_experience_text(bullet_states):
    """Rebuild professional experience block from bullet states."""
    active = active_bullets(bullet_states)
    if not active:
        return ""
    parts = []
    last_header = None
    for b in active:
        header = tuple(b.get("block_header") or [])
        if header != last_header:
            if parts:
                parts.append("")
            parts.extend(b.get("block_header") or [])
            last_header = header
        text = (b.get("final_text") or b.get("generated_text") or "").strip()
        if text:
            parts.append(f"• {text}")
    return "\n".join(parts)


def rebuild_full_resume_text(resume_data, bullet_states):
    """Rebuild full resume text replacing the experience section."""
    exp = rebuild_experience_text(bullet_states)
    parts = [
        resume_data.get("header_name", ""),
        resume_data.get("target_title", ""),
        " | ".join(
            p.strip()
            for p in (
                resume_data.get("header_location", ""),
                resume_data.get("header_email", ""),
                resume_data.get("header_phone", ""),
            )
            if p and p.strip()
        ),
        "",
        "PROFILE",
        resume_data.get("profile", ""),
        "",
        "AREAS OF EXPERTISE",
        f"• {resume_data.get('areas_of_expertise', '')}",
        "",
        "PROFESSIONAL EXPERIENCE",
        exp,
        "",
        "EDUCATION",
        resume_data.get("education", ""),
    ]
    return "\n".join(parts)


def classify_recalled_context(raw_text, evidence_items):
    """Classify recalled context: existing_evidence, recalled_temp, or new."""
    low = (raw_text or "").lower().strip()
    if not low:
        return "empty", None
    for item in evidence_items or []:
        blob = " ".join(
            str(item.get(k, "") or "")
            for k in ("action", "title", "bullet_draft", "raw_notes", "company", "factual_context")
        ).lower()
        if len(low) >= 15 and low[: min(40, len(low))] in blob:
            return "existing_evidence", item.get("id")
    return "new", None


def propose_bullet(raw_context, role_family=""):
    """Conservative draft bullet from user-provided factual context only."""
    text = (raw_context or "").strip()
    if not text:
        return ""
    # Trim; capitalize first letter; do not invent metrics or tools.
    line = text[0].upper() + text[1:] if len(text) > 1 else text.upper()
    line = re.sub(r"\s+", " ", line)
    if not line.endswith("."):
        line += "."
    return line


def style_guidance_snippet(preferred_rows, avoid_tags=None):
    """Build a feedback_text appendix from saved preferences (style guidance only)."""
    parts = []
    if preferred_rows:
        examples = [r.get("final_text") or r.get("generated_text") for r in preferred_rows[:3]]
        examples = [e for e in examples if e]
        if examples:
            parts.append("Preferred phrasing examples: " + " | ".join(examples))
    if avoid_tags:
        parts.append("Avoid wording patterns: " + ", ".join(avoid_tags))
    return "; ".join(parts)


def bullets_to_state_json(bullet_states):
    return json.dumps(bullet_states, ensure_ascii=False)


def bullets_from_state_json(raw):
    if not raw:
        return []
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []
