"""Generate JD-specific verbal outputs from factual evidence — never overwrites source."""

import re

OUTPUT_RESUME_BULLET = "resume_bullet"
OUTPUT_TARGET_TRANSLATION = "target_translation"
OUTPUT_PREFERRED_PHRASING = "preferred_phrasing"

ROLE_FAMILIES = [
    "Product Operations",
    "Program Management",
    "Business Operations",
    "Business Systems / Internal Tools / Enterprise Operations Systems",
    "Platform Operations",
    "Workflow / CX Operations",
    "Customer Support Operations",
    "Technical Production / Live Operations",
    "Product Analytics / Marketing Analytics",
    "Creator / Content Operations",
]

_FORBIDDEN_INVENTED = [
    "workday", "hris", "netsuite", "salesforce", "okta", "servicenow", "erp",
    "iam vendor", "iam platform", "identity and access management platform",
    "enterprise saas configuration", "engineering implementation",
    "hris administration", "workday implementation",
]

_GENERIC_FILLER = [
    "supporting product operations delivery needs",
    "supporting program management delivery needs",
    "supporting platform operations delivery needs",
    "supporting business systems operations delivery needs",
    "cross-functional delivery, workflow coordination, and stakeholder alignment",
    "cross-functional delivery",
    "workflow coordination, and stakeholder alignment",
    "stakeholder alignment in an enterprise context",
    "aligned to ",
    "framed for ",
    "capability themes including",
    "driving cross-functional alignment",
    "improving stakeholder coordination",
]

_MECHANISM_RULES = [
    (("approval path", "accountable-owner approval", "approval"), "approval paths"),
    (("elevated", "secondary confirmation"), "elevated-access controls"),
    (("provis", "new hire", "new hires"), "new-hire provisioning"),
    (("monitor", "follow-up", "permission change", "permission-change"), "permission-change monitoring"),
    (("exception", "special-access"), "exception handling"),
    (("role tier", "role-based", "role based"), "role-based tiering"),
    (("offboarding", "access removal"), "access removal"),
    (("documentation", "usage standard", "onboarding documentation"), "internal enablement standards"),
    (("access request", "request initiation"), "access-request intake"),
    (("alert",), "change alerts"),
]

_CAPABILITY_RULES = [
    (("access govern", "permission govern", "role-based access"), "internal access governance"),
    (("approval",), "approval workflow design"),
    (("lifecycle", "provisioning", "onboarding", "offboarding"), "access lifecycle controls"),
    (("documentation", "usage standard", "enablement"), "internal-user enablement"),
    (("monitor", "audit", "traceable", "alert"), "operational process auditability"),
    (("exception", "elevated", "special-access"), "elevated-access and exception handling"),
    (("workflow design", "workflow"), "internal workflow design"),
]


def _norm(text):
    return re.sub(r"\s+", " ", (text or "").strip())


def _low(text):
    return _norm(text).lower().replace("-", " ")


def _words(text):
    return len(_norm(text).split())


def _sentences(text):
    t = _norm(text)
    if not t:
        return []
    parts = re.split(r"(?<=[.!?])\s+", t)
    return [p.strip() for p in parts if p.strip()]


def _token_set(text):
    return set(re.findall(r"[a-z0-9]+", _low(text)))


def _overlap_ratio(a, b):
    ta, tb = _token_set(a), _token_set(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / min(len(ta), len(tb))


def _strip_unsupported_claims(text, source_blob):
    src = _low(source_blob)
    out = text
    for term in _FORBIDDEN_INVENTED:
        if term not in src and term in _low(out):
            if len(term) <= 4:
                out = re.sub(rf"\b{re.escape(term)}\b", "", out, flags=re.IGNORECASE)
            else:
                out = re.sub(re.escape(term), "", out, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", out).strip(" ,;—-")


def _remove_generic_filler(text):
    out = _norm(text)
    low = out.lower()
    for phrase in _GENERIC_FILLER:
        if phrase in low:
            idx = low.find(phrase)
            out = out[:idx].rstrip(" ,;—-")
            low = out.lower()
    return out.strip(" ,;—-")


def _extract_mechanisms(facts_low):
    found = []
    seen = set()
    for needles, label in _MECHANISM_RULES:
        if any(n in facts_low for n in needles):
            key = _low(label)
            if key not in seen:
                seen.add(key)
                found.append(label)
    return found


def _extract_capabilities(facts_low, impact_low=""):
    blob = facts_low + " " + impact_low
    found = []
    seen = set()
    for needles, label in _CAPABILITY_RULES:
        if any(n in blob for n in needles):
            key = _low(label)
            if key not in seen:
                seen.add(key)
                found.append(label)
    return found


def _compress_outcome(impact, mechanisms, facts_low):
    imp = _norm(impact)
    if not imp:
        return ""
    imp = re.sub(r"^(outcome:\s*)", "", imp, flags=re.IGNORECASE)
    imp_low = _low(imp)

    if "fragmented" in imp_low and "lifecycle" in imp_low:
        return "replace fragmented access processes with a traceable lifecycle"

    mech_tokens = set()
    for m in mechanisms:
        mech_tokens |= _token_set(m)

    if _overlap_ratio(imp, " ".join(mechanisms)) > 0.45:
        if "audit" in imp_low:
            return "improve auditability of permission changes"
        if "structured" in imp_low or "fragmented" in imp_low:
            return "replace fragmented access processes with a traceable lifecycle"
        words = imp.split()
        return " ".join(words[:8]).rstrip(",") if len(words) > 8 else imp

    short = imp.rstrip(".")
    if _words(short) > 10:
        short = " ".join(short.split()[:10])
    return short[0].lower() + short[1:] if short else ""


def _access_opener(facts_low):
    if any(k in facts_low for k in ("permission govern", "access govern", "role based", "role-based")):
        platform = "internal operations platform"
        if "tool platform" in facts_low or "operations tool" in facts_low:
            platform = "internal operations tool platform"
        return f"Designed and operated a role-based access-governance workflow for an {platform}"
    return ""


def _is_access_governance_evidence(facts_low):
    """True only for permission/access lifecycle evidence — not platform integration governance."""
    strong_signals = (
        "access govern", "permission govern", "role-based access", "role based access",
        "access request", "access lifecycle", "elevated access", "permission change",
        "permission-change", "access control", "access-request",
    )
    if any(k in facts_low for k in strong_signals):
        return True
    if "provisioning" in facts_low and any(
        k in facts_low for k in ("access", "permission", "onboarding", "hire", "new-hire", "new hire")
    ):
        return True
    if "permission" in facts_low and "govern" in facts_low:
        return True
    return False


def _build_access_bullet(facts, impact):
    facts_low = _low(facts)
    mechanisms = _extract_mechanisms(facts_low)
    if not mechanisms:
        mechanisms = ["access-request intake", "approval paths", "permission-change monitoring"][:3]

    opener = _access_opener(facts_low) or "Designed and operated access-governance workflows for an internal operations platform"
    outcome = _compress_outcome(impact, mechanisms, facts_low)

    def assemble(mechs, out):
        body = f"{opener}, establishing {', '.join(mechs)}"
        if out and _overlap_ratio(out, body) < 0.55:
            body += f" to {out}"
        body = body.rstrip(" ,;") + "."
        return _remove_generic_filler(_strip_unsupported_claims(body, facts + " " + impact))

    bullet = assemble(mechanisms[:5], outcome)
    while _words(bullet) > 45 and len(mechanisms) > 3:
        mechanisms = mechanisms[:-1]
        bullet = assemble(mechanisms, outcome)
    if outcome and _words(bullet) > 45:
        bullet = assemble(mechanisms[:4], _compress_outcome("", mechanisms, facts_low) or outcome.split()[0:6])
    while _words(bullet) > 45 and mechanisms:
        mechanisms = mechanisms[:-1]
        bullet = assemble(mechanisms, outcome if _words(outcome) <= 8 else "")
    return bullet


def _build_general_bullet(facts, impact, source_blob):
    sents = _sentences(facts)
    opener = sents[0].rstrip(".") if sents else facts
    if _words(opener) > 18:
        opener = " ".join(opener.split()[:18])

    mechanisms = []
    for s in sents[1:]:
        s = s.rstrip(".")
        if _words(s) <= 12 and _overlap_ratio(s, opener) < 0.6:
            mechanisms.append(s[0].lower() + s[1:] if s else s)
        if len(mechanisms) >= 3:
            break

    outcome = _compress_outcome(impact, mechanisms, _low(facts))
    bullet = opener
    if mechanisms:
        bullet += ", including " + ", ".join(mechanisms[:3])
    if outcome and _overlap_ratio(outcome, bullet) < 0.5:
        bullet += f" to {outcome}"
    bullet = bullet.rstrip(" ,;") + "."
    bullet = _remove_generic_filler(_strip_unsupported_claims(bullet, source_blob))

    while _words(bullet) > 45:
        if mechanisms:
            mechanisms = mechanisms[:-1]
            bullet = opener + (", including " + ", ".join(mechanisms) if mechanisms else "")
            if outcome:
                bullet += f" to {outcome}"
            bullet = bullet.rstrip(" ,;") + "."
        else:
            bullet = " ".join(bullet.split()[:45]).rstrip(",;.") + "."
            break
    return bullet


def _has_repeated_phrase(text, min_words=2):
    """Detect if a multi-word phrase appears twice (major repetition)."""
    words = _norm(text).lower().split()
    for size in range(4, min_words - 1, -1):
        for i in range(len(words) - size + 1):
            phrase = " ".join(words[i:i + size])
            if text.lower().count(phrase) > 1:
                return True
    return False


def generate_resume_bullet(
    factual_context,
    impact_outcome="",
    company="",
    role_context="",
    skills="",
    capability_tags=None,
    role_family="",
):
    """Conservative resume bullet from source facts. Returns (text, error_message)."""
    facts = _norm(factual_context)
    if not facts:
        return "", "Add factual evidence before generating a resume bullet."

    impact = _norm(impact_outcome)
    source_blob = " ".join(filter(None, [facts, impact, company, role_context, skills]))
    facts_low = _low(facts)

    if _is_access_governance_evidence(facts_low):
        bullet = _build_access_bullet(facts, impact)
    else:
        bullet = _build_general_bullet(facts, impact, source_blob)

    bullet = _remove_generic_filler(bullet)
    if not bullet.strip():
        return "", "Could not generate a resume bullet from the available facts."
    return bullet, None


def _role_family_translation_frame(role_family, capabilities):
    family = (role_family or "").strip()
    cap_str = ", ".join(capabilities[:4]) if capabilities else "internal operational workflow design"

    if "Business Systems" in family:
        return (
            f"For {family}, this evidence represents {cap_str} for internal enterprise-adjacent "
            f"operations—describing capability transfer from platform/live-ops context, not direct ERP, HRIS, or IAM vendor administration."
        )
    if family == "Product Operations":
        return (
            f"For Product Operations, this evidence demonstrates {cap_str} on an internal platform—"
            f"positioning workflow ownership and lifecycle controls outside gaming, without claiming employer-specific enterprise SaaS ownership."
        )
    if family == "Program Management":
        return (
            f"For Program Management, this evidence highlights {cap_str}—"
            f"transferable program delivery through defined workflows and controls, not domain-specific system implementation."
        )
    if family == "Platform Operations":
        return (
            f"For Platform Operations, this evidence maps to {cap_str}—"
            f"internal platform reliability and operational workflow design rather than external product feature development."
        )
    return (
        f"For {family or 'target roles'}, this evidence maps to {cap_str}—"
        f"capability-based positioning from verified internal operating experience."
    )


def generate_target_translation(
    factual_context,
    role_family="",
    jd_snippet="",
    impact_outcome="",
    capability_tags=None,
):
    """Frame factual evidence for a target role family. Returns (text, error_message)."""
    facts = _norm(factual_context)
    if not facts:
        return "", "Add factual evidence before generating a translation."

    impact = _norm(impact_outcome or "")
    facts_low = _low(facts)
    impact_low = _low(impact)
    capabilities = _extract_capabilities(facts_low, impact_low)
    if capability_tags:
        for tag in capability_tags:
            t = _norm(tag)
            if t and t not in capabilities and _low(t) not in {_low(c) for c in capabilities}:
                capabilities.append(t)

    framing = _role_family_translation_frame(role_family, capabilities)
    framing = _remove_generic_filler(framing)
    framing = _strip_unsupported_claims(framing, facts + " " + impact)

    if jd_snippet:
        jd_low = jd_snippet.lower()
        honest = [t for t in ("workflow", "integration", "launch", "stakeholder", "access", "approval")
                  if t in jd_low and t in facts_low]
        if honest:
            framing = framing.rstrip(".") + f" JD-relevant themes supported by facts: {', '.join(honest[:3])}."

    return framing, None


def verbal_output_label(output_type):
    return {
        OUTPUT_RESUME_BULLET: "Resume bullet draft",
        OUTPUT_TARGET_TRANSLATION: "Target-role translation",
        OUTPUT_PREFERRED_PHRASING: "Preferred approved wording",
    }.get(output_type, output_type)


# Example used in tests / manual verification
PERMISSION_GOV_EXAMPLE = {
    "factual_context": (
        "Designed and managed permission-governance workflows for an internal operations tool platform. "
        "Defined role tiers, access-request initiation, accountable-owner approval paths, secondary confirmation "
        "for elevated permissions, and alerts for key permission changes. "
        "Owned workflow design for exception requests and special-access handling. "
        "Supported automated access provisioning for new hires, plus monitoring and follow-up for permission "
        "changes related to team transfers and offboarding. "
        "Maintained onboarding documentation and usage standards for role-specific tool functions."
    ),
    "impact_outcome": (
        "Replaced fragmented permission handling with a more structured lifecycle covering request initiation, "
        "approval, elevated-access controls, provisioning, change monitoring, exception handling, and access removal."
    ),
}
