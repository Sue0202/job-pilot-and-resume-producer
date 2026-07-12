"""Deterministic experience translation engine for JobPilot.

Maps verified gaming / live-operations / platform-operations experience into
target-industry language for Product Ops, Program Management, Platform Ops,
Workflow / Business Ops, Live Operations, and analytics-adjacent roles.

No external LLM calls. All mappings are explainable rule-based translations
grounded in the candidate's verified profile and evidence library.
"""

import re

try:
    import jd_analyzer
except Exception:  # pragma: no cover
    jd_analyzer = None

# ---------------------------------------------------------------------------
# Gaming / live-ops language → target-role language
# ---------------------------------------------------------------------------

TRANSLATION_MAPPINGS = [
    {
        "id": "launch_coordination",
        "profile_signals": [
            "launch", "release", "cadence", "6-week", "version", "go-live",
            "readiness", "major-version",
        ],
        "jd_signals": [
            "launch", "release", "go-live", "readiness", "program delivery",
            "cross-functional", "stakeholder", "execution",
        ],
        "original_context": (
            "Coordinated game-version launches across R&D, QA, platform, operations, "
            "and compliance."
        ),
        "target_role_interpretation": "Cross-functional launch readiness and program delivery",
        "resume_ready_phrasing": (
            "Coordinated cross-functional launch readiness across engineering, QA, platform, "
            "operations, and compliance stakeholders, translating delivery risks into "
            "execution plans and operating controls."
        ),
        "jd_themes": [
            "stakeholder management", "workflow optimization", "execution under ambiguity",
            "launch readiness",
        ],
        "match_label": "Transferable operating-context match",
        "proof_strength": "Transferable",
        "capability_tags": ["Program Management", "Live Operations", "Launch / Release"],
        "why_valid": (
            "Launch coordination across R&D, QA, platform, and compliance maps directly to "
            "cross-functional program delivery in non-gaming roles."
        ),
    },
    {
        "id": "p0_incident_response",
        "profile_signals": [
            "p0", "incident", "escalation", "outage", "production incident",
            "support escalation", "live issue",
        ],
        "jd_signals": [
            "incident", "escalation", "operational", "risk", "mitigation",
            "support", "issue triage", "on-call",
        ],
        "original_context": (
            "Managed P0 production incidents and support escalation for a large-scale "
            "live product."
        ),
        "target_role_interpretation": (
            "Operational incident management / escalation management / risk mitigation"
        ),
        "resume_ready_phrasing": (
            "Managed high-impact operational incidents and escalation workflows for a "
            "large-scale user-facing product, converting production issues into process "
            "improvements, platform requirements, and long-term operating playbooks."
        ),
        "jd_themes": [
            "incident management", "escalation management", "operational risk",
            "support operations",
        ],
        "match_label": "Transferable operating-context match",
        "proof_strength": "Transferable",
        "capability_tags": ["Incident / Escalation", "Support Operations", "Platform Operations"],
        "why_valid": (
            "Live-service P0 response and support escalation are directly transferable to "
            "operational incident and escalation management in SaaS / platform contexts."
        ),
    },
    {
        "id": "internal_tools_workflow",
        "profile_signals": [
            "internal tool", "permission", "approval", "workflow", "batch operation",
            "automated alert", "risk control", "platform-driven",
        ],
        "jd_signals": [
            "internal tool", "workflow", "business system", "process", "automation",
            "operating model", "tooling", "enablement",
        ],
        "original_context": (
            "Built platform-driven risk controls, permission models, approval checkpoints, "
            "and workflow mechanisms from live incident reviews."
        ),
        "target_role_interpretation": (
            "Internal tools optimization / workflow design / business systems operations"
        ),
        "resume_ready_phrasing": (
            "Built internal workflow and control mechanisms — including permission models, "
            "approval checkpoints, and automated alerting — by translating operational "
            "incident patterns into platform requirements and scalable process design."
        ),
        "jd_themes": [
            "workflow design", "internal tools", "process improvement", "operating controls",
        ],
        "match_label": "Adjacent / positioning opportunity",
        "proof_strength": "Transferable",
        "capability_tags": ["Internal Tools", "Platform Operations", "Workflow / Business Operations"],
        "why_valid": (
            "Platform permission models and workflow mechanisms are adjacent to business "
            "systems and internal-tool improvement roles — the underlying capability is "
            "workflow design, not a specific SaaS product name."
        ),
    },
    {
        "id": "sdk_platform_onboarding",
        "profile_signals": [
            "sdk", "integration", "server deployment", "store submission", "compliance review",
            "go-live", "platform task", "technical integration",
        ],
        "jd_signals": [
            "platform integration", "operational enablement", "systems implementation",
            "onboarding", "deployment", "integration", "technical rollout",
        ],
        "original_context": (
            "Operationalized external products into a publishing platform via SDK integration, "
            "server deployment, store submission, and compliance review."
        ),
        "target_role_interpretation": (
            "Platform integration / operational enablement / systems implementation"
        ),
        "resume_ready_phrasing": (
            "Operationalized external products into an internal publishing platform, "
            "coordinating SDK integration, server deployment, store submission, and "
            "compliance review into go-live standards and technical integration plans."
        ),
        "jd_themes": [
            "platform operations", "technical integration", "compliance readiness",
            "cross-functional delivery",
        ],
        "match_label": "Transferable operating-context match",
        "proof_strength": "Transferable",
        "capability_tags": ["Platform Operations", "Launch / Release"],
        "why_valid": (
            "SDK integration and platform onboarding workflows translate to platform "
            "enablement and systems implementation in enterprise software contexts."
        ),
    },
    {
        "id": "user_feedback_escalation",
        "profile_signals": [
            "user feedback", "support feedback", "support ticket", "player feedback",
            "customer support", "escalation workflow", "pain point",
        ],
        "jd_signals": [
            "voice of customer", "customer feedback", "support escalation", "issue triage",
            "user research", "customer experience", "feedback loop",
        ],
        "original_context": (
            "Translated user pain points and support feedback into product and engineering "
            "requirements through escalation workflows."
        ),
        "target_role_interpretation": (
            "Voice-of-customer operations / support escalation management / issue triage"
        ),
        "resume_ready_phrasing": (
            "Translated user pain points and support feedback into product and engineering "
            "requirements through beta testing, playtesting review, and customer support "
            "escalation workflows."
        ),
        "jd_themes": [
            "voice of customer", "support operations", "feedback-to-product loop",
            "stakeholder management",
        ],
        "match_label": "Transferable operating-context match",
        "proof_strength": "Transferable",
        "capability_tags": ["Support Operations", "Product Operations", "Stakeholder Management"],
        "why_valid": (
            "User feedback escalation in live products maps to voice-of-customer and "
            "support-operations roles outside gaming."
        ),
    },
    {
        "id": "analytics_practicum",
        "profile_signals": [
            "sql", "eda", "regression", "competitive research", "seasonality",
            "marketing mix", "mmm", "data cleaning", "visualization",
        ],
        "jd_signals": [
            "analytics", "data analysis", "reporting", "insights", "stakeholder",
            "business intelligence", "metrics", "kpi", "dashboard",
        ],
        "original_context": (
            "Supported Rainbow Six Siege marketing mix modeling and publishing analytics "
            "with SQL, EDA, competitive research, and stakeholder-facing deliverables."
        ),
        "target_role_interpretation": (
            "Business analytics support / data-informed decision support / stakeholder reporting"
        ),
        "resume_ready_phrasing": (
            "Built SQL/Python-assisted workflows to clean and standardize marketing and "
            "regional datasets, producing EDA, visual summaries, and analytical notes that "
            "translated market signals into stakeholder-facing insights for publishing "
            "decision-making."
        ),
        "jd_themes": [
            "data analysis", "stakeholder reporting", "business analytics",
            "decision support",
        ],
        "match_label": "Direct capability match",
        "proof_strength": "Direct",
        "capability_tags": ["Analytics", "Stakeholder Management"],
        "why_valid": (
            "SQL/EDA workstream support and stakeholder-facing analytics deliverables are "
            "direct evidence for analytics-adjacent and business-ops roles."
        ),
    },
    {
        "id": "global_publishing",
        "profile_signals": [
            "japan", "overseas", "global", "localization", "regional", "market",
            "international", "multi-region", "publishing",
        ],
        "jd_signals": [
            "global launch", "regional", "localization", "cross-market", "international",
            "market readiness", "regional operations",
        ],
        "original_context": (
            "Served as launch operations bridge for Japan-market licensed mobile game "
            "publishing, coordinating localization, compliance, and regional go-live."
        ),
        "target_role_interpretation": (
            "Global launch operations / regional operational readiness / cross-market program coordination"
        ),
        "resume_ready_phrasing": (
            "Built end-to-end launch operating plans for an international market, translating "
            "local regulatory and user requirements into platform tasks, SDK feature requests, "
            "and go-live standards across legal, security, and publishing stakeholders."
        ),
        "jd_themes": [
            "global operations", "regional readiness", "cross-market coordination",
            "compliance",
        ],
        "match_label": "Transferable operating-context match",
        "proof_strength": "Transferable",
        "capability_tags": ["Launch / Release", "Program Management", "Platform Operations"],
        "why_valid": (
            "Multi-region publishing and localization coordination translate to global "
            "launch and regional operational readiness roles."
        ),
    },
    {
        "id": "sop_runbooks",
        "profile_signals": [
            "sop", "runbook", "operating standard", "playbook", "process standard",
            "operating model", "workflow design",
        ],
        "jd_signals": [
            "operating model", "process documentation", "workflow governance", "sop",
            "standard operating", "runbook", "process improvement", "scalable workflow",
        ],
        "original_context": (
            "Built major-version release and support operating standards for a 6-week live "
            "cadence, aligning launch calendars, severity, and escalation paths."
        ),
        "target_role_interpretation": (
            "Operating model design / process documentation / scalable workflow governance"
        ),
        "resume_ready_phrasing": (
            "Designed scalable operating standards for a recurring release cadence, aligning "
            "launch calendars, issue severity, fix priority, customer response, and "
            "escalation paths across cross-functional teams."
        ),
        "jd_themes": [
            "process documentation", "workflow governance", "operating model",
            "cross-functional alignment",
        ],
        "match_label": "Direct capability match",
        "proof_strength": "Direct",
        "capability_tags": ["Workflow / Business Operations", "Program Management"],
        "why_valid": (
            "SOP and operating-standard design for live cadences is direct evidence for "
            "workflow and business-operations roles."
        ),
    },
    {
        "id": "cross_functional_program",
        "profile_signals": [
            "cross-functional", "r&d", "qa", "publishing", "marketing", "milestone",
            "stakeholder", "program",
        ],
        "jd_signals": [
            "program management", "cross-functional", "stakeholder", "milestone",
            "delivery", "coordination", "execution",
        ],
        "original_context": (
            "Drove cross-functional execution between R&D, QA, operations, publishing, "
            "marketing, platform, infrastructure, and compliance stakeholders."
        ),
        "target_role_interpretation": "Program delivery and cross-functional stakeholder management",
        "resume_ready_phrasing": (
            "Drove cross-functional execution across engineering, QA, operations, publishing, "
            "marketing, platform, and compliance stakeholders to support launch readiness, "
            "release execution, and stable live operations."
        ),
        "jd_themes": [
            "program management", "stakeholder management", "cross-functional delivery",
        ],
        "match_label": "Direct capability match",
        "proof_strength": "Direct",
        "capability_tags": ["Program Management", "Stakeholder Management", "Product Operations"],
        "why_valid": (
            "Cross-functional delivery across R&D, QA, publishing, and compliance is "
            "direct program-management evidence."
        ),
    },
]

# Tools the JD may ask for where adjacent workflow exists but not direct tool evidence.
TOOL_ADJACENCY = {
    "salesforce": {
        "adjacent_signals": ["crm", "workflow", "support", "ticket", "customer", "process"],
        "adjacent_evidence": [
            "support escalation", "customer support", "workflow", "operating standard",
        ],
        "note": (
            "No direct Salesforce evidence, but adjacent customer-support and workflow "
            "operations experience exists. Position as transferable process/systems work — "
            "do not claim direct Salesforce proficiency."
        ),
    },
    "figma": {
        "adjacent_signals": ["design", "ux", "wireframe", "prototype", "product requirement"],
        "adjacent_evidence": ["product requirement", "user feedback", "beta testing", "workflow"],
        "note": (
            "No direct Figma evidence, but experience translating user feedback into product "
            "requirements is adjacent. Do not claim Figma proficiency."
        ),
    },
    "tableau": {
        "adjacent_signals": ["dashboard", "visualization", "reporting", "analytics", "bi"],
        "adjacent_evidence": ["sql", "eda", "visualization", "data", "analytics", "reporting"],
        "note": (
            "Tool syntax gap: no verified Tableau usage, but SQL/EDA/visualization and "
            "stakeholder reporting workflows are adjacent."
        ),
    },
    "looker": {
        "adjacent_signals": ["dashboard", "bi", "reporting", "analytics", "metric", "kpi"],
        "adjacent_evidence": ["sql", "eda", "visualization", "data", "analytics", "reporting"],
        "note": (
            "Tool syntax gap: no verified Looker usage, but SQL/EDA and stakeholder "
            "reporting workflows are adjacent."
        ),
    },
    "jira": {
        "adjacent_signals": ["project", "ticket", "agile", "sprint", "backlog", "issue tracking"],
        "adjacent_evidence": ["milestone", "cross-functional", "issue severity", "workflow"],
        "note": (
            "No direct Jira evidence, but milestone tracking and cross-functional issue "
            "management workflows are adjacent."
        ),
    },
    "asana": {
        "adjacent_signals": ["project management", "task", "milestone", "coordination"],
        "adjacent_evidence": ["milestone", "cross-functional", "program", "coordination"],
        "note": (
            "No direct Asana evidence, but program coordination and milestone ownership "
            "workflows are adjacent."
        ),
    },
}

# Domain / systems gaps — distinct from tool syntax (Workday, NetSuite, HRIS, etc.).
DOMAIN_SYSTEM_PATTERNS = [
    {
        "label": "Workday / HRIS / People systems",
        "jd_signals": ["workday", "hris", "people systems", "people system", "people operations systems"],
        "profile_signals": ["workday", "hris", "people systems", "workday implementation"],
        "note": (
            "No verified Workday or HRIS implementation experience. Internal workflow and "
            "platform work is transferable, but direct people-systems domain exposure is a gap."
        ),
    },
    {
        "label": "NetSuite / ERP finance systems",
        "jd_signals": ["netsuite", "erp finance", "finance erp", "financial systems"],
        "profile_signals": ["netsuite", "erp", "financial systems", "finance system"],
        "note": (
            "No verified NetSuite or ERP finance systems experience. Platform integration "
            "work is adjacent but not a substitute for finance-system domain knowledge."
        ),
    },
    {
        "label": "Employee lifecycle domain",
        "jd_signals": ["employee lifecycle", "employee life cycle", "onboarding to offboarding",
                       "lifecycle tooling", "hr lifecycle"],
        "profile_signals": ["employee lifecycle", "onboarding to offboarding", "hr lifecycle"],
        "note": (
            "No verified employee lifecycle / HR domain ownership. Cross-functional delivery "
            "experience is transferable but does not replace people-ops domain depth."
        ),
    },
    {
        "label": "Enterprise HR/finance business systems",
        "jd_signals": ["finance and hr", "hr and finance", "hr/finance", "people-systems domain"],
        "profile_signals": ["hr/finance", "finance and hr", "people-systems"],
        "note": "Enterprise HR/finance systems domain knowledge not verified in profile.",
    },
    {
        "label": "Enterprise business systems integration",
        "jd_signals": ["enterprise integration", "enterprise integrations", "enterprise business systems",
                       "business systems integration"],
        "profile_signals": ["enterprise integration", "enterprise business systems"],
        "note": (
            "SDK/platform integration experience is adjacent, but direct enterprise "
            "business-systems (HR/finance/ERP) integration exposure is not verified."
        ),
    },
    {
        "label": "3PL / logistics systems",
        "jd_signals": ["3pl", "third-party logistics", "logistics systems", "supply chain systems"],
        "profile_signals": ["3pl", "logistics systems", "supply chain"],
        "note": "No verified 3PL or logistics-systems experience.",
    },
]

# Technical skills required by JD but not verified — separate from domain gaps.
TECHNICAL_SKILL_REQUIREMENTS = {
    "javascript": {
        "profile_signals": ["javascript", "js ", " front-end", "frontend", "react", "node"],
        "note": "JavaScript proficiency not verified — Python exposure exists but is not equivalent.",
    },
    "html": {
        "profile_signals": ["html", "css", "front-end", "frontend", "web development"],
        "note": "HTML / front-end markup not verified in profile.",
    },
}

BUSINESS_SYSTEMS_JD_SIGNALS = [
    "business systems", "business system", "people systems", "people system", "workday",
    "netsuite", "employee lifecycle", "enterprise integration", "hris", "internal tool",
    "internal tools", "business-process", "business process", "3pl", "enterprise systems",
]

BS_ROLE_FAMILY = "Business Systems / Internal Tools / Enterprise Operations Systems"

import role_family_resolver as rfrs
# User-facing capability labels (Part 3 — never imply direct enterprise-system ownership).
CAPABILITY_FIT_METRIC_LABEL = "Direct Capability Fit"
POSITIONING_CAPTION = (
    "Strong positioning potential can improve how transferable experience is communicated, "
    "but it does not replace direct enterprise-domain experience."
)
CAPABILITY_DIRECT = "Direct capability match"
CAPABILITY_TRANSFERABLE = "Transferable operating-context match"
CAPABILITY_ADJACENT = "Adjacent / positioning opportunity"
CAPABILITY_GAP = "True gap / cannot claim directly"

CAPABILITY_SORT_ORDER = {
    CAPABILITY_DIRECT: 0,
    CAPABILITY_TRANSFERABLE: 1,
    CAPABILITY_ADJACENT: 2,
    CAPABILITY_GAP: 3,
}

ENTERPRISE_DOMAIN_PROFILE_SIGNALS = [
    "workday", "netsuite", "hris", "employee lifecycle", "erp implementation",
    "people systems implementation", "people-systems domain",
]


def resolve_role_family(jd_text, result, job_title=""):
    """Retrieval role family — does not change jd_analyzer scoring role family."""
    jd_low = _norm(jd_text)
    if _has_any(jd_low, BUSINESS_SYSTEMS_JD_SIGNALS):
        return BS_ROLE_FAMILY
    return rfrs.resolve_retrieval_role_family(
        jd_text,
        job_title=job_title,
        scoring_role_family=result.get("selected_role_family", ""),
    )


def is_business_systems_jd(jd_text):
    return _has_any(jd_text, BUSINESS_SYSTEMS_JD_SIGNALS)


RECALL_PROMPTS = [
    "Have you worked on an internal tool, workflow, process redesign, or operational system that is not yet in your library?",
    "Do you have an example of gathering requirements from stakeholders and translating them into process or tooling changes?",
    "Have you used a similar tool or method in another context (e.g., a different dashboard, ticketing, or project-tracking system)?",
    "Do you have a launch, escalation, reporting, or cross-functional delivery example relevant to this JD?",
    "Is there a regional, compliance, or partnership workflow you coordinated that is not yet recorded?",
]

FILTER_TAGS = [
    "Product Operations", "Program Management", "Platform Operations",
    "Live Operations / Technical Production", "Workflow / Business Operations",
    "Analytics", "Launch / Release", "Stakeholder Management", "Internal Tools",
    "Incident / Escalation",
]

PROOF_STRENGTHS = ["Direct", "Transferable", "Supporting"]


def _norm(text):
    return re.sub(r"\s+", " ", (text or "").lower())


def _has_any(text, terms):
    low = _norm(text)
    return any(t in low for t in terms)


def _profile_has_signals(profile_text, signals):
    return _has_any(profile_text, signals)


def _jd_has_signals(jd_text, signals):
    return _has_any(jd_text, signals)


def _relevant_jd_themes(jd_text, themes):
    low = _norm(jd_text)
    return [t for t in themes if any(word in low for word in t.split())]


def build_translation_cards(profile_text, jd_text, result, evidence_items=None):
    """Return positioning cards for verified experience that maps to this JD."""
    import verbal_retrieval as vr

    evidence_items = vr.filter_tailoring_evidence(evidence_items or [])
    role_family = result.get("selected_role_family", "")
    cards = []
    seen_ids = set()

    for mapping in TRANSLATION_MAPPINGS:
        if not _profile_has_signals(profile_text, mapping["profile_signals"]):
            continue
        if not _jd_has_signals(jd_text, mapping["jd_signals"]):
            continue
        if mapping["id"] in seen_ids:
            continue
        seen_ids.add(mapping["id"])

        jd_themes = _relevant_jd_themes(jd_text, mapping["jd_themes"]) or mapping["jd_themes"][:3]
        label = mapping["match_label"]
        cards.append({
            "mapping_id": mapping["id"],
            "original_context": mapping["original_context"],
            "target_role_interpretation": mapping["target_role_interpretation"],
            "resume_ready_phrasing": mapping["resume_ready_phrasing"],
            "jd_relevance": "Supports: " + ", ".join(jd_themes),
            "match_label": label,
            "capability_label": label,
            "proof_strength": mapping["proof_strength"],
            "capability_tags": mapping["capability_tags"],
            "why_valid": mapping["why_valid"],
            "selected": True,
            "source": "profile",
        })

    seen_evidence_ids = set()
    for item in evidence_items:
        eid = item.get("id")
        if eid in seen_evidence_ids:
            continue
        seen_evidence_ids.add(eid)

        pair = vr.retrieve_evidence_pair(item, role_family=role_family, jd_snippet=jd_text)
        bullet = pair["resume_bullet"]
        translation = pair["target_translation"]
        bullet["source_badge"] = vr.source_badge_label(bullet)

        facts = (
            (item.get("factual_context") or item.get("action") or "").strip()
        )
        tags = [t.strip() for t in (item.get("capability_tags") or item.get("tags") or "").split(",") if t.strip()]
        strength = item.get("proof_strength") or "Transferable"
        cap_label = CAPABILITY_DIRECT if strength == "Direct" else CAPABILITY_TRANSFERABLE

        trans_text = (translation.get("selected_verbal_text") or "").strip()
        cards.append({
            "mapping_id": f"evidence_{eid}",
            "evidence_id": eid,
            "evidence_title": item.get("title") or "",
            "original_context": facts[:240] + ("…" if len(facts) > 240 else ""),
            "target_role_interpretation": trans_text or "No saved target-role translation for this role family.",
            "resume_ready_phrasing": bullet.get("selected_verbal_text") or "",
            "jd_relevance": "Verified Evidence Library",
            "match_label": cap_label,
            "match_classification": cap_label,
            "capability_label": cap_label,
            "proof_strength": strength,
            "capability_tags": tags,
            "why_valid": "Verified evidence library item with role-family verbal retrieval.",
            "selected": True,
            "source": "evidence_library",
            "retrieval_role_family": bullet.get("selected_role_family") or role_family,
            "role_family_used": bullet.get("matched_role_family") or role_family,
            "wording_source": bullet.get("wording_source"),
            "relationship_type": bullet.get("relationship_type"),
            "source_badge": bullet.get("source_badge"),
            "verbal_retrieval": pair,
        })

    cards.sort(key=lambda c: CAPABILITY_SORT_ORDER.get(c.get("capability_label", c["match_label"]), 4))
    return cards


def gap_risk_category(gap_severity_score):
    """Categorical material-gap risk (Option B — user-facing)."""
    s = float(gap_severity_score or 0)
    if s <= 3.0:
        return "Low"
    if s <= 6.0:
        return "Moderate"
    if s <= 8.0:
        return "Significant"
    return "Major"


def _has_verified_enterprise_domain(profile_text):
    return _profile_has_signals(profile_text, ENTERPRISE_DOMAIN_PROFILE_SIGNALS)


def needs_enterprise_display_calibration(gap_analysis, fit_narrative, profile_text):
    """True when material enterprise domain/system gaps warrant conservative display."""
    domain_n = len(gap_analysis.get("domain_system_gaps") or [])
    tech_n = len(gap_analysis.get("technical_skill_gaps") or [])
    direct_fit = fit_narrative.get("direct_evidence_fit", 10)
    return (
        domain_n >= 2
        and direct_fit < 7.0
        and tech_n >= 2
        and not _has_verified_enterprise_domain(profile_text)
    )


def apply_display_calibration(result, fit_narrative, gap_analysis, profile_text):
    """Conservative display-layer calibration for enterprise systems roles.

    Does not change jd_analyzer WEIGHTS or stored base_score in the DB — only the
    numbers and recommendation copy shown on Analyze Job results.
    """
    narrative = dict(fit_narrative)
    severity = narrative.get("true_capability_gap_severity", 0)
    narrative["material_gap_risk"] = gap_risk_category(severity)

    if not needs_enterprise_display_calibration(gap_analysis, narrative, profile_text):
        narrative["calibrated_base_fit"] = result.get("base_score")
        narrative["display_decision"] = None
        narrative["display_priority"] = None
        narrative["capability_fit_metric_label"] = CAPABILITY_FIT_METRIC_LABEL
        narrative["has_literal_direct_evidence"] = bool(result.get("direct_evidence"))
        narrative["direct_capability_fit"] = narrative.get("direct_evidence_fit")
        narrative["show_positioning_cap_note"] = False
        return narrative

    raw_base = float(result.get("base_score", 0))
    domain_n = len(gap_analysis.get("domain_system_gaps") or [])
    tech_n = len(gap_analysis.get("technical_skill_gaps") or [])

    # Single conservative adjustment — gaps already counted in material_gap_risk.
    adjustment = min(1.0, 0.12 * domain_n + 0.08 * tech_n)
    calibrated_base = round(max(6.5, min(7.0, raw_base - adjustment)), 1)

    narrative["direct_evidence_fit"] = round(
        min(narrative.get("direct_evidence_fit", 10), 6.5), 1
    )
    narrative["direct_capability_fit"] = narrative["direct_evidence_fit"]
    narrative["resume_competitiveness"] = round(
        min(narrative.get("resume_competitiveness", 10), 7.3), 1
    )
    if domain_n >= 3:
        narrative["resume_competitiveness"] = round(
            min(narrative["resume_competitiveness"], 7.0), 1
        )

    # Major domain gaps: positioning can help narrative but cannot imply domain ownership.
    if narrative["material_gap_risk"] == "Major":
        narrative["verbal_positioning_potential"] = round(
            min(narrative.get("verbal_positioning_potential", 10), 7.8), 1
        )

    narrative["capability_fit_metric_label"] = CAPABILITY_FIT_METRIC_LABEL
    narrative["has_literal_direct_evidence"] = bool(result.get("direct_evidence"))
    narrative["direct_capability_fit"] = narrative.get("direct_evidence_fit")
    narrative["show_positioning_cap_note"] = narrative["material_gap_risk"] == "Major"
    narrative["calibrated_base_fit"] = calibrated_base
    if calibrated_base >= 7.0:
        narrative["display_decision"] = "Apply with Tailoring"
        narrative["display_priority"] = "Medium"
    elif calibrated_base >= 6.5:
        narrative["display_decision"] = "Apply Selectively"
        narrative["display_priority"] = "Medium-Low"
    else:
        narrative["display_decision"] = (
            jd_analyzer.decision_for(calibrated_base) if jd_analyzer else "Maybe - Needs More Evidence"
        )
        narrative["display_priority"] = (
            jd_analyzer.priority_for(calibrated_base) if jd_analyzer else "Low"
        )

    narrative["summary_text"] = (
        "Strong transferable operating and systems-delivery experience, but material "
        "enterprise-domain and tool gaps remain. Apply selectively if the role values "
        "adaptable operators; tailor toward workflow design, internal tools, stakeholder "
        "alignment, and process improvement."
    )
    return narrative


def classify_gaps(jd_text, profile_text, result):
    """Split gaps into true capability/eligibility gaps vs tool/positioning gaps."""
    parsed = result.get("parsed") or {}
    jd_low = _norm(jd_text)
    prof_low = _norm(profile_text)
    candidate_skills = getattr(jd_analyzer, "CANDIDATE_SKILLS", set()) if jd_analyzer else set()

    required_hard = []
    preferred_tool = []
    potentially_learnable = []
    eligibility = []
    seniority_mismatch = []
    domain_system_gaps = []
    technical_skill_gaps = []

    # Red flags → eligibility / hard gaps.
    for rf in result.get("red_flags") or []:
        eligibility.append(rf)

    # Domain / systems gaps (Workday, NetSuite, employee lifecycle, etc.).
    seen_domain = set()
    for pattern in DOMAIN_SYSTEM_PATTERNS:
        if not _has_any(jd_low, pattern["jd_signals"]):
            continue
        if _profile_has_signals(profile_text, pattern["profile_signals"]):
            continue
        if pattern["label"] in seen_domain:
            continue
        seen_domain.add(pattern["label"])
        domain_system_gaps.append({
            "domain": pattern["label"],
            "note": pattern["note"],
            "gap_type": "domain_system_gap",
        })

    # Technical skill gaps (JavaScript, HTML, etc.).
    seen_tech = set()
    for skill, meta in TECHNICAL_SKILL_REQUIREMENTS.items():
        if skill not in jd_low:
            continue
        if skill in candidate_skills or _profile_has_signals(profile_text, meta["profile_signals"]):
            continue
        if skill in seen_tech:
            continue
        seen_tech.add(skill)
        technical_skill_gaps.append({
            "skill": skill,
            "note": meta["note"],
            "gap_type": "technical_skill_gap",
        })

    # Required skills missing from profile.
    for skill in parsed.get("required_skills") or []:
        s_low = skill.lower()
        if s_low in candidate_skills or s_low in prof_low:
            continue
        # Domain tools handled above — avoid duplicating in preferred_tool.
        if s_low in ("workday", "netsuite"):
            continue
        if s_low in TECHNICAL_SKILL_REQUIREMENTS:
            continue
        if s_low in TOOL_ADJACENCY:
            adj = TOOL_ADJACENCY[s_low]
            has_adjacent = _profile_has_signals(profile_text, adj["adjacent_evidence"])
            preferred_tool.append({
                "tool": skill,
                "gap_type": "tool_syntax_gap" if has_adjacent else "no_comparable_workflow",
                "note": adj["note"],
                "has_adjacent_workflow": has_adjacent,
            })
        elif any(s_low in _norm(k) for k in getattr(jd_analyzer, "CANDIDATE_SKILL_GAPS", set())):
            required_hard.append(f"Required capability gap: {skill}")
        else:
            potentially_learnable.append(f"Potentially learnable: {skill}")

    # Preferred skills.
    for skill in parsed.get("preferred_skills") or []:
        s_low = skill.lower()
        if s_low in candidate_skills or s_low in prof_low:
            continue
        if s_low in ("workday", "netsuite"):
            continue
        if s_low in TECHNICAL_SKILL_REQUIREMENTS:
            continue
        if s_low in TOOL_ADJACENCY:
            adj = TOOL_ADJACENCY[s_low]
            has_adjacent = _profile_has_signals(profile_text, adj["adjacent_evidence"])
            preferred_tool.append({
                "tool": skill,
                "gap_type": "tool_syntax_gap" if has_adjacent else "no_comparable_workflow",
                "note": adj["note"],
                "has_adjacent_workflow": has_adjacent,
            })

    # Seniority check (conservative) — only explicit Director/Staff/Principal or 8+ years.
    seniority = parsed.get("seniority_signals") or []
    if jd_analyzer and jd_analyzer.has_explicit_senior_level_requirement(seniority):
        seniority_mismatch.append(
            "Seniority signal: role may expect Director/Staff/Principal level — verify scope fit."
        )
    if any(s in seniority for s in ("intern", "new grad", "junior")):
        seniority_mismatch.append(
            "Seniority signal: role appears entry-level — may underutilize your experience."
        )

    # Sponsorship.
    if result.get("sponsorship_feasibility", 10) < 5:
        eligibility.append("Sponsorship / work authorization may be a constraint for this role.")

    return {
        "required_hard_gaps": required_hard,
        "preferred_tool_gaps": preferred_tool,
        "potentially_learnable_gaps": potentially_learnable,
        "eligibility_constraints": eligibility,
        "seniority_mismatch": seniority_mismatch,
        "domain_system_gaps": domain_system_gaps,
        "technical_skill_gaps": technical_skill_gaps,
    }


def build_fit_narrative(result, translation_cards, gap_analysis, jd_text=""):
    """Explain fit dimensions without changing underlying score weights."""
    cs = result.get("component_scores") or {}
    direct_n = len(result.get("direct_evidence") or [])
    adjacent_n = len(result.get("adjacent_evidence") or [])
    positioning_n = len(translation_cards)
    hard_gaps = len(gap_analysis.get("required_hard_gaps") or [])
    eligibility = len(gap_analysis.get("eligibility_constraints") or [])
    domain_n = len(gap_analysis.get("domain_system_gaps") or [])
    tech_n = len(gap_analysis.get("technical_skill_gaps") or [])
    tool_syntax_only = sum(
        1 for g in gap_analysis.get("preferred_tool_gaps") or []
        if g.get("has_adjacent_workflow")
    )

    direct_base = cs.get("resume_evidence_strength", 0)
    # Enterprise people-systems roles: transferable workflow evidence exists, but direct
    # enterprise-tool/domain evidence is usually absent — cap Direct Evidence Fit.
    if domain_n >= 2:
        direct_fit = round(min(7.5, direct_base + min(direct_n * 0.25, 0.75)), 1)
    elif domain_n == 1:
        direct_fit = round(min(8.0, direct_base + min(direct_n * 0.35, 1.0)), 1)
    else:
        direct_fit = round(min(10.0, direct_base + direct_n * 0.5), 1)

    transfer_fit = round(min(10.0, cs.get("industry_transferability", 0) + adjacent_n * 0.3), 1)
    verbal_potential = round(min(10.0, 5.0 + positioning_n * 0.8 + tool_syntax_only * 0.5), 1)
    gap_severity = round(min(10.0,
        hard_gaps * 2.5 + eligibility * 3.0 + domain_n * 2.0 + tech_n * 1.5
    ), 1)
    resume_comp = round(min(10.0, result.get("base_score", 0) + (verbal_potential - 5) * 0.12), 1)

    has_transferable = direct_n > 0 or adjacent_n > 0 or positioning_n > 0
    has_true_blocker = hard_gaps > 0 or eligibility > 0
    business_systems = is_business_systems_jd(jd_text) or domain_n > 0

    if has_true_blocker:
        primary = "true_gap"
        summary = (
            "This role has material eligibility or capability constraints. Review caution "
            "flags before investing significant tailoring time."
        )
    elif business_systems and has_transferable and domain_n > 0:
        primary = "positioning"
        summary = (
            "You have strong transferable internal-tool, workflow, launch, and "
            "systems-delivery experience. However, direct enterprise people-systems, "
            "finance-systems, and specific business-platform exposure remain material gaps."
        )
    elif has_transferable and tool_syntax_only > 0 and hard_gaps == 0:
        primary = "positioning"
        summary = (
            "You have transferable evidence for this role. The primary challenge is "
            "positioning your existing experience in target-industry language, not adding "
            "more experience."
        )
    elif has_transferable and positioning_n >= 2:
        primary = "positioning"
        summary = (
            "Strong underlying experience maps to this role — the primary challenge is "
            "positioning your existing experience in target-industry language, not adding "
            "more experience."
        )
    elif not has_transferable:
        primary = "evidence_retrieval"
        summary = (
            "Limited direct or transferable evidence detected. Consider whether you have a "
            "real example not yet recorded in your profile or Evidence Library."
        )
    else:
        primary = "positioning"
        summary = (
            "Partial alignment with transferable evidence. Strengthen your case through "
            "positioning and selective evidence recall before adding new material."
        )

    narrative = {
        "direct_evidence_fit": direct_fit,
        "direct_capability_fit": direct_fit,
        "capability_fit_metric_label": CAPABILITY_FIT_METRIC_LABEL,
        "has_literal_direct_evidence": direct_n > 0,
        "transferability_fit": transfer_fit,
        "verbal_positioning_potential": verbal_potential,
        "true_capability_gap_severity": gap_severity,
        "resume_competitiveness": resume_comp,
        "primary_challenge": primary,
        "summary_text": summary,
        "show_positioning_cap_note": False,
    }
    return narrative


def finalize_fit_narrative(result, narrative, gap_analysis, profile_text):
    """Apply display calibration and gap-risk label (presentation layer only)."""
    return apply_display_calibration(result, narrative, gap_analysis, profile_text)


def recommend_primary_action(result, fit_narrative, gap_analysis):
    """Return (label, target, hint) for the primary CTA — positioning-first."""
    primary = fit_narrative.get("primary_challenge", "positioning")
    display_decision = fit_narrative.get("display_decision")
    decision = display_decision or result.get("decision", "")
    eligibility = gap_analysis.get("eligibility_constraints") or []
    hard = gap_analysis.get("required_hard_gaps") or []

    if eligibility or (hard and result.get("base_score", 0) < 5.0):
        return (
            "Review Caution Flags",
            "save",
            "Eligibility or hard capability constraints — review before investing time.",
        )
    if display_decision == "Apply Selectively":
        return (
            "Translate & Tailor Resume",
            "strengthen",
            fit_narrative.get("summary_text", "")[:220],
        )
    if decision in ("High Priority", "Apply with Tailoring") or primary == "positioning":
        hint = fit_narrative.get("summary_text", "")[:220] if fit_narrative.get("material_gap_risk") in (
            "Significant", "Major"
        ) else "Strong transferable evidence — translate existing experience and tailor a resume."
        return (
            "Translate & Tailor Resume",
            "strengthen",
            hint,
        )
    if primary == "evidence_retrieval":
        return (
            "Recall an Unlisted Example",
            "strengthen",
            "You may have relevant experience not yet recorded — recall a real example first.",
        )
    if decision == "Maybe - Needs More Evidence":
        return (
            "Strengthen Your Case",
            "strengthen",
            "Borderline fit — translate existing experience or recall a real unlisted example.",
        )
    return (
        "Save for Reference",
        "save",
        "Likely not a strong fit now — save for reference if you want.",
    )


def analyze_translation(profile_text, jd_text, result, evidence_items=None, target_angle="", job_title=""):
    """Full translation analysis for Analyze Job results."""
    evidence_items = evidence_items or []
    resolved_family = resolve_role_family(jd_text, result, job_title=job_title)
    result = dict(result)
    result["selected_role_family"] = resolved_family
    if resolved_family == BS_ROLE_FAMILY:
        result["suggested_resume_angle"] = "Product Operations & Business Systems"

    cards = build_translation_cards(profile_text, jd_text, result, evidence_items)
    gaps = classify_gaps(jd_text, profile_text, result)
    narrative = build_fit_narrative(result, cards, gaps, jd_text=jd_text)
    narrative = finalize_fit_narrative(result, narrative, gaps, profile_text)
    action = recommend_primary_action(result, narrative, gaps)
    return {
        "translation_cards": cards,
        "gap_analysis": gaps,
        "fit_narrative": narrative,
        "primary_action": action,
        "recall_prompts": RECALL_PROMPTS,
        "resolved_role_family": resolved_family,
    }


def build_tailoring_plan(result, translation_cards, angle="", jd_text=""):
    """Concise plan shown before resume generation."""
    selected = [c for c in translation_cards if c.get("selected")]
    top = selected[:5]
    jd_low = _norm(jd_text)
    themes = []
    for c in top:
        themes.extend(c.get("capability_tags") or [])
    themes = list(dict.fromkeys(themes))[:5]

    mirror = []
    for kw in (result.get("parsed") or {}).get("role_keywords") or []:
        if kw in jd_low:
            mirror.append(kw)
    mirror = mirror[:6]

    gaps = []
    ga = classify_gaps(jd_text, "", result)
    for g in ga.get("required_hard_gaps") or []:
        gaps.append(g)
    for g in ga.get("eligibility_constraints") or []:
        gaps.append(g)
    for g in ga.get("preferred_tool_gaps") or []:
        if not g.get("has_adjacent_workflow"):
            gaps.append(f"Will not overstate: {g['tool']}")

    return {
        "positioning_angle": angle or result.get("suggested_resume_angle", ""),
        "top_evidence": top,
        "jd_themes": themes,
        "jd_language_to_mirror": mirror,
        "true_gaps_not_overstated": gaps,
    }


def approved_mappings_to_material(cards):
    """Turn user-approved translation cards into resume-generation hints."""
    selected = [c for c in cards if c.get("selected")]
    if not selected:
        return ""
    lines = ["\n\n## Approved Experience Translations (target-industry framing)\n"]
    for c in selected:
        lines.append(f"- {c['resume_ready_phrasing']}")
        lines.append(f"  (Maps from: {c['original_context']})")
    return "\n".join(lines)
