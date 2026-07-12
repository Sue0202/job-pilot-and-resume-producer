"""Explicit JD role-family resolution for verbal-output retrieval only.

Does not affect jd_analyzer scoring, calibration, or fit formulas.
"""

import re

import role_family_vocab as rfv

PRODUCT_OPERATIONS = "Product Operations"
PRODUCT_OPERATIONS_COMPOSITE = "Product Operations & Program Management"
PROGRAM_MANAGEMENT = "Program Management"
PROGRAM_IMPLEMENTATION = "Program / Implementation"
TECHNICAL_PROGRAM_MANAGEMENT = "Technical Program Management"
BUSINESS_SYSTEMS = "Business Systems"

PRODUCT_OPERATIONS_SIGNALS = [
    "product operations",
    "product operating cadence",
    "operating cadence",
    "business review",
    "wbr",
    "mbr",
    "qbo",
    "executive decision support",
    "action tracking",
    "decision hygiene",
    "decision log",
    "business rhythm",
    "scorecard",
    "chief of staff",
    "product organization",
    "product org",
    "business metrics",
    "financial metrics",
    "product operations program manager",
]

TPM_TITLE_SIGNALS = [
    "technical program manager",
    "technical program management",
    "engineering program manager",
    "engineering program management",
]

TPM_TECHNICAL_SIGNALS = [
    "hardware/software integration",
    "hardware software integration",
    "systems engineering",
    "technical roadmap",
    "architecture",
    "interface dependencies",
    "interface dependency",
    "validation",
    "v&v",
    "platform engineering",
    "platform engineering delivery",
    "embedded systems",
    "robotics",
]

GENERIC_PROGRAM_SIGNALS = [
    "program manager",
    "program management",
    "cross-functional planning",
    "program delivery",
    "implementation plan",
    "milestone",
    "dependency tracking",
]

RETRIEVAL_ALIASES = {
    "product operations & program management": PRODUCT_OPERATIONS,
    "product operations and program management": PRODUCT_OPERATIONS,
    "business systems / internal tools / enterprise operations systems": BUSINESS_SYSTEMS,
}


def _norm(text):
    return re.sub(r"\s+", " ", (text or "").lower())


def _count_signals(text, signals):
    return sum(1 for s in signals if s in text)


def _explicit_tpm_title(text):
    return _count_signals(text, TPM_TITLE_SIGNALS) > 0


def _tpm_technical_score(text):
    return _count_signals(text, TPM_TECHNICAL_SIGNALS)


def is_technical_program_management_jd(jd_text, job_title=""):
    """True only for explicit TPM titles or multiple strong technical-program signals."""
    text = _norm(f"{job_title} {jd_text}")
    if _explicit_tpm_title(text):
        return True
    return _tpm_technical_score(text) >= 2


def is_product_operations_jd(jd_text, job_title=""):
    text = _norm(f"{job_title} {jd_text}")
    po_score = _count_signals(text, PRODUCT_OPERATIONS_SIGNALS)
    if "product operations" in text:
        return True
    if po_score >= 2:
        return True
    if po_score >= 1 and _count_signals(text, GENERIC_PROGRAM_SIGNALS) >= 1:
        return True
    return False


def resolve_retrieval_role_family(jd_text, job_title="", scoring_role_family=""):
    """Return primary role family used for verbal-output retrieval."""
    text = _norm(f"{job_title} {jd_text}")
    scoring = (scoring_role_family or "").strip()

    if is_technical_program_management_jd(jd_text, job_title):
        return TECHNICAL_PROGRAM_MANAGEMENT

    if is_product_operations_jd(jd_text, job_title):
        return PRODUCT_OPERATIONS

    if scoring == PRODUCT_OPERATIONS:
        return PRODUCT_OPERATIONS

    if scoring == PROGRAM_MANAGEMENT:
        return PROGRAM_MANAGEMENT

    if scoring:
        aliased = RETRIEVAL_ALIASES.get(rfv.normalize_role_family_key(scoring))
        if aliased:
            return aliased
        return rfv.ensure_role_family(scoring, save_custom=False)

    return ""


def retrieval_role_family(selected_role_family):
    """Map display/scoring labels to canonical retrieval families."""
    selected = rfv.ensure_role_family(selected_role_family or "", save_custom=False)
    if not selected:
        return ""
    norm = rfv.normalize_role_family_key(selected)
    if norm in RETRIEVAL_ALIASES:
        return RETRIEVAL_ALIASES[norm]
    return selected


def strict_relationship_type(resolved_role_family, matched_role_family):
    """Exact only when normalized retrieval families are identical."""
    resolved_norm = rfv.normalize_role_family_key(
        retrieval_role_family(resolved_role_family)
    )
    matched_norm = rfv.normalize_role_family_key(matched_role_family or "")
    if resolved_norm and matched_norm and resolved_norm == matched_norm:
        return "exact"
    return "related"


def distinct_from_program_management(role_family):
    """True when role family is not generic Program Management or TPM."""
    norm = rfv.normalize_role_family_key(role_family or "")
    return norm not in {
        rfv.normalize_role_family_key(PROGRAM_MANAGEMENT),
        rfv.normalize_role_family_key(TECHNICAL_PROGRAM_MANAGEMENT),
    }
