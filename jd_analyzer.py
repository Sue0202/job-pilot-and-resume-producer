"""Rule-based job-description (JD) parser and fit-scoring engine for JobPilot.

This powers the "Analyze Job" workflow: a single JD is parsed into structured
signals (responsibilities, qualifications, skills, tools, seniority, role family,
sponsorship signals, risk flags), then scored against the project owner's verified
candidate profile.

Design principles:
  - No external API required. Everything is regex + keyword banks.
  - Conservative and truthful: roles requiring hard technical skills, security
    clearance, quota-carrying sales, CPA, or no-sponsorship are NOT overrated and
    are capped toward "Skip".
  - Never fabricates candidate experience. Evidence matching only credits
    verified candidate strengths that actually appear in the JD.
"""

import re

# Optional: pull verified candidate facts for richer evidence matching. The module
# still works standalone (e.g. in tests) if the import is unavailable.
try:
    import resume_generator as rg
except Exception:  # pragma: no cover - defensive
    rg = None


# ---------------------------------------------------------------------------
# Keyword banks
# ---------------------------------------------------------------------------

# Role families relevant to the candidate, with detection keywords.
ROLE_FAMILY_KEYWORDS = {
    "Product Operations": [
        "product operations", "product ops", "product operations manager",
        "product coordinator", "product specialist",
    ],
    "Platform Operations": [
        "platform operations", "platform ops", "platform program",
        "platform manager", "sdk", "platform integration",
    ],
    "Program Management": [
        "program manager", "program management", "technical program manager",
        "tpm", "project manager", "program coordinator", "program lead",
    ],
    "Business Operations": [
        "business operations", "business ops", "bizops", "operations manager",
        "strategy and operations", "strategy & operations", "revenue operations",
    ],
    "Business Systems / Internal Tools / Enterprise Operations Systems": [
        "business systems", "business system", "people systems", "people system",
        "hris", "workday", "netsuite", "employee lifecycle", "employee life cycle",
        "enterprise integration", "enterprise integrations", "erp", "internal tools",
        "internal tool", "business process", "business-process", "systems implementation",
        "3pl", "servicenow", "sap", "business systems analyst", "systems analyst",
        "enterprise systems", "people operations systems",
    ],
    "Workflow / CX Operations": [
        "workflow", "cx operations", "customer experience operations",
        "process improvement", "operations analyst", "operational excellence",
    ],
    "Customer Support Operations": [
        "customer support", "support operations", "technical support",
        "support specialist", "help desk", "customer success", "support engineer",
    ],
    "Trust & Safety Operations": [
        "trust and safety", "trust & safety", "content moderation",
        "policy operations", "risk operations", "fraud operations", "abuse",
    ],
    "Creator / Content Operations": [
        "creator operations", "content operations", "community operations",
        "ugc", "creator program", "content management", "community manager",
    ],
    "Technical Production / Live Operations": [
        "technical producer", "live operations", "live ops", "release manager",
        "game operations", "production coordinator", "release management",
    ],
    "Product Analytics / Marketing Analytics": [
        "product analytics", "marketing analytics", "data analyst",
        "business analyst", "bi analyst", "analytics", "reporting", "dashboard",
    ],
    "AI Workflow / Automation Operations": [
        "ai operations", "workflow automation", "ai workflow", "automation operations",
        "llm operations", "ai program", "prompt operations", "ai enablement",
    ],
}

# Map each role family to the candidate's verified resume angle (resume_generator
# profile angle + display title).
FAMILY_TO_ANGLE = {
    "Product Operations": "A",
    "Program Management": "A",
    "Business Operations": "A",
    "Business Systems / Internal Tools / Enterprise Operations Systems": "A",
    "Creator / Content Operations": "A",
    "Product Analytics / Marketing Analytics": "A",
    "AI Workflow / Automation Operations": "A",
    "Platform Operations": "C",
    "Workflow / CX Operations": "B",
    "Customer Support Operations": "B",
    "Trust & Safety Operations": "B",
    "Technical Production / Live Operations": "D",
}

ANGLE_TITLES = {
    "A": "Product Operations & Program Management",
    "B": "Workflow Strategist, Customer Support",
    "C": "Product Operations Manager | Platform Operations",
    "D": "Technical Production & Live Service Operations",
}

# Business-systems / enterprise-tooling signals. When present (and the JD is not
# explicitly customer-support focused) the suggested angle should lean toward a
# business-systems / internal-tools positioning rather than Customer Support.
BUSINESS_SYSTEMS_SIGNALS = [
    "business systems", "business system", "enterprise", "integration", "integrations",
    "internal tool", "internal tools", "workflow automation", "process improvement",
    "salesforce", "workday", "netsuite", "it systems", "systems implementation",
    "systems analyst", "business systems analyst", "erp", "crm", "sap", "servicenow",
    "cross-functional systems", "tooling", "systems administration", "system integration",
]

# Explicit customer-support / CX-support focus. Only then do we keep a support angle.
SUPPORT_FOCUS_CUES = [
    "customer support", "support operations", "help desk", "customer success",
    "technical support", "support ticket", "csat", "customer service", "support team",
    "service desk", "contact center", "call center",
]


def _suggested_angle(role_family, text_low):
    """Pick a resume angle title. Prefers business-systems positioning for
    enterprise-tooling JDs and avoids defaulting to Customer Support unless the JD
    is explicitly support/CX focused."""
    business = any(sig in text_low for sig in BUSINESS_SYSTEMS_SIGNALS)
    support_focus = (
        role_family == "Customer Support Operations"
        or any(c in text_low for c in SUPPORT_FOCUS_CUES)
    )

    if business and not support_focus:
        if role_family == "Product Analytics / Marketing Analytics":
            return "Business Systems / Operations Analyst"
        if role_family in ("Workflow / CX Operations", "AI Workflow / Automation Operations"):
            return "Internal Tools & Process Improvement"
        return "Product Operations & Business Systems"

    angle = FAMILY_TO_ANGLE.get(role_family, "A")
    if angle == "B" and not support_focus:
        # Do not default to a Customer Support angle for non-support roles.
        if role_family == "Workflow / CX Operations":
            return "Internal Tools & Process Improvement"
        return ANGLE_TITLES["A"]
    return ANGLE_TITLES.get(angle, ANGLE_TITLES["A"])

# Tools / platforms commonly named in JDs.
TOOL_BANK = [
    "sql", "python", "javascript", "html", "r", "excel", "google sheets", "tableau", "power bi",
    "looker", "sigma", "snowflake", "bigquery", "airflow", "dbt", "jira",
    "asana", "confluence", "notion", "figma", "lucidchart", "salesforce", "workday", "netsuite",
    "zendesk", "intercom", "hubspot", "git", "spark", "kafka", "kubernetes", "aws",
    "gcp", "azure", "powerpoint", "pytorch", "tensorflow",
]

# Broader skill bank (includes soft/process skills).
SKILL_BANK = TOOL_BANK + [
    "data analysis", "data visualization", "a/b testing", "experimentation",
    "statistics", "machine learning", "deep learning", "etl", "api",
    "stakeholder management", "cross-functional", "project management",
    "process improvement", "workflow design", "sop", "incident response",
    "escalation", "root cause analysis", "compliance", "localization",
    "program management", "roadmap", "kpi", "reporting", "forecasting",
]

# Verified candidate skills/strengths (used for conservative skill_fit). Only
# things the candidate genuinely has from the master profile.
CANDIDATE_SKILLS = {
    "sql", "python", "excel", "data analysis", "data visualization", "eda",
    "a/b testing", "experimentation", "statistics", "reporting", "kpi",
    "stakeholder management", "cross-functional", "project management",
    "program management", "process improvement", "workflow design", "sop",
    "incident response", "escalation", "root cause analysis", "compliance",
    "localization", "roadmap", "powerpoint", "google sheets",
}

# Hard skills the candidate does NOT have (used to flag and avoid overrating).
CANDIDATE_SKILL_GAPS = {
    "machine learning", "deep learning", "pytorch", "tensorflow", "spark",
    "kafka", "kubernetes", "dbt", "airflow",
}

# Enterprise domain / tool-syntax skills surfaced in the translation gap layer.
# Excluded from skill_fit denominator so Workday/NetSuite/JS/HTML do not
# double-penalize the base score alongside domain gap flags.
SKILL_FIT_GAP_LAYER_SKILLS = {
    "workday", "netsuite", "servicenow", "sap",
    "javascript", "html", "figma", "lucidchart", "salesforce",
}

# Verified candidate evidence library. Each item declares:
#   keywords  : JD terms that imply this evidence is relevant
#   text      : human-readable evidence statement (verified, no fabrication)
#   families  : role families this is DIRECT evidence for (else it is "adjacent")
#   has_metric: whether the verified evidence carries a concrete outcome/metric
EVIDENCE_LIBRARY = [
    {
        "keywords": ["sql", "dashboard", "reporting", "analytics", "eda", "data",
                     "visualization", "metric", "forecasting"],
        "text": "SQL/EDA and analytics deliverables (Ubisoft Rainbow Six Siege MMM practicum)",
        "families": {"Product Analytics / Marketing Analytics", "Business Operations"},
        "has_metric": False,
    },
    {
        "keywords": ["support", "escalation", "incident", "ticket", "customer", "p0", "outage"],
        "text": "Support escalation & P0 incident response for a large live product (miHoYo)",
        "families": {"Customer Support Operations", "Workflow / CX Operations",
                     "Trust & Safety Operations"},
        "has_metric": False,
    },
    {
        "keywords": ["workflow", "sop", "process", "operations", "operating", "playbook", "standard"],
        "text": "Workflow/SOP design and live operating standards (miHoYo live operations)",
        "families": {"Platform Operations", "Workflow / CX Operations", "Product Operations"},
        "has_metric": False,
    },
    {
        "keywords": ["launch", "release", "go-live", "cadence", "readiness", "deployment"],
        "text": "Launch readiness & 6-week release operating standards (miHoYo, ByteDance)",
        "families": {"Technical Production / Live Operations", "Program Management",
                     "Product Operations"},
        "has_metric": True,
    },
    {
        "keywords": ["program", "cross-functional", "stakeholder", "roadmap", "milestone", "coordination"],
        "text": "Cross-functional program execution across R&D/QA/publishing (miHoYo, ByteDance)",
        "families": {"Program Management", "Product Operations", "Business Operations"},
        "has_metric": False,
    },
    {
        "keywords": ["creator", "content", "ugc", "community", "partnership", "moderator"],
        "text": "Creator/UGC & community operations (miHoYo partnerships, Yousidun community)",
        "families": {"Creator / Content Operations", "Customer Support Operations"},
        "has_metric": False,
    },
    {
        "keywords": ["platform", "sdk", "integration", "permission", "approval", "risk", "controls"],
        "text": "Platform operations: SDK integration, permissions, risk controls (ByteDance, miHoYo)",
        "families": {"Platform Operations", "Trust & Safety Operations"},
        "has_metric": False,
    },
    {
        "keywords": ["trust", "safety", "compliance", "policy", "abuse", "moderation", "fraud"],
        "text": "Trust & safety / compliance and anti-abuse workflows (ByteDance, miHoYo)",
        "families": {"Trust & Safety Operations", "Platform Operations"},
        "has_metric": False,
    },
    {
        "keywords": ["localization", "global", "international", "overseas", "market"],
        "text": "Global/overseas product launch operations (ByteDance Japan publishing)",
        "families": {"Program Management", "Product Operations",
                     "Technical Production / Live Operations"},
        "has_metric": False,
    },
    {
        "keywords": ["retention", "a/b", "ab test", "experiment", "growth", "engagement"],
        "text": "A/B testing & retention analysis with growth teams (supported 10%+ Day-1 "
                "retention improvement, ByteDance)",
        "families": {"Product Analytics / Marketing Analytics", "Product Operations"},
        "has_metric": True,
    },
]

# Core responsibility themes used to measure how directly evidence covers a JD.
RESPONSIBILITY_THEMES = {
    "analytics/reporting": ["sql", "dashboard", "reporting", "analytics", "data", "metric", "kpi"],
    "program/cross-functional": ["program", "cross-functional", "stakeholder", "roadmap", "milestone"],
    "support/cx": ["support", "customer", "escalation", "incident", "ticket"],
    "platform/workflow": ["platform", "sdk", "integration", "workflow", "automation", "sop"],
    "launch/release": ["launch", "release", "go-live", "readiness", "cadence"],
    "creator/community": ["creator", "content", "ugc", "community", "moderation"],
    "trust/safety/compliance": ["trust", "safety", "compliance", "policy", "abuse", "fraud"],
}

# Seniority signal patterns -> normalized label.
SENIORITY_PATTERNS = {
    "intern": [r"\bintern\b", r"\binternship\b"],
    "new grad": [r"new\s*grad", r"new\s*graduate", r"entry[- ]level"],
    "associate": [r"\bassociate\b"],
    "junior": [r"\bjunior\b", r"\bjr\.?\b"],
    "senior": [
        r"\bsenior director\b",
        r"\bsenior manager\b",
        r"\bsenior program\b",
        r"\bsenior product\b",
        r"\bsenior operations\b",
        r"\bsenior engineer\b",
        r"\bsenior machine learning engineer\b",
        r"\bsenior analyst\b",
        r"\bsenior lead\b",
        r"\bsenior level\b",
        r"\bsenior role\b",
        r"\bsenior(?:ity)?(?: level)?(?: position)?(?: role)? required\b",
        r"\bsr\.?\s+(?:director|manager|engineer|pm|program)\b",
        r"\bsenior\b(?!\s+leadership\b)",
    ],
    "staff": [
        r"\bstaff engineer\b",
        r"\bstaff software engineer\b",
        r"\bstaff program manager\b",
        r"\bstaff product manager\b",
        r"\bstaff tpm\b",
        r"\bstaff level\b",
        r"\bstaff role\b",
        r"\bstaff position\b",
        r"\bprincipal/staff\b",
        r"\bstaff/principal\b",
    ],
    "principal": [r"\bprincipal\b(?!\s*/\s*staff)"],
    "lead": [r"\blead\b"],
    "manager": [r"\bmanager\b"],
    "director": [r"\bdirector\b", r"\bhead of\b", r"\bvp\b", r"\bvice president\b"],
}

# Phrases that mention senior/staff words without requiring that seniority level.
SENIORITY_FALSE_POSITIVE_SCRUBS = [
    r"chief[- ]of[- ]staff[- ]adjacent",
    r"chief[- ]of[- ]staff",
    r"cos[- ]adjacent",
    r"reporting to (?:the )?chief of staff",
    r"for senior leadership",
    r"with senior leadership",
    r"to senior leadership",
    r"senior leadership team",
    r"executive[- ]level decision support",
    r"executive decision support",
]

# Hard cap applies at or above this explicit years requirement (candidate ~6 yrs ops).
SENIORITY_YEARS_HARD_CAP_THRESHOLD = 8

# Hard-risk patterns. dealbreaker=True caps the overall score toward Skip.
RISK_PATTERNS = [
    ("US citizenship required",
     [r"u\.?s\.? citizen", r"must be a citizen", r"citizenship required", r"us citizenship"],
     True),
    ("Security clearance required",
     [r"security clearance", r"secret clearance", r"top secret", r"ts/sci", r"active clearance"],
     True),
    ("No visa sponsorship",
     [r"no (?:visa )?sponsorship", r"(?:visa )?sponsorship (?:is )?not available",
      r"not (?:provide|offer|offering|able to provide) (?:visa )?sponsorship",
      r"without sponsorship", r"unable to sponsor", r"not able to sponsor",
      r"cannot sponsor", r"do(?:es)? not (?:provide|offer) (?:visa )?sponsorship",
      r"authorized to work .{0,40}without sponsorship"],
     True),
    ("Local candidates only",
     [r"local candidates only", r"must be local", r"locals only"],
     False),
    ("Native English required",
     [r"native english", r"native[- ]level english", r"native speaker"],
     False),
    ("CPA required",
     [r"cpa required", r"cpa license", r"certified public accountant"],
     True),
    ("Quota-carrying sales role",
     [r"quota[- ]carrying", r"sales quota", r"carry a quota", r"revenue quota",
      r"cold calling", r"sales target"],
     True),
    ("Heavy production software engineering",
     [r"production[- ]level code", r"production code", r"scalable backend",
      r"data structures and algorithms", r"design patterns",
      r"build and ship software", r"software development life ?cycle"],
     True),
    ("Deep ML model training",
     [r"train (?:deep learning|ml|machine learning) models", r"model training",
      r"from scratch", r"deep learning", r"\bpytorch\b", r"\btensorflow\b",
      r"model architecture"],
     True),
]

SPONSORSHIP_POSITIVE = [
    r"visa sponsorship", r"will sponsor", r"sponsorship available",
    r"sponsorship is available", r"provide sponsorship", r"offer sponsorship",
    r"open to sponsorship",
]

# Section header cues used to split the JD.
SECTION_CUES = {
    "responsibilities": [
        "responsibilities", "what you'll do", "what you will do", "the role",
        "duties", "day to day", "day-to-day", "your impact", "you will",
    ],
    "qualifications": [
        "qualifications", "requirements", "what you'll need", "what we're looking for",
        "what you will need", "minimum qualifications", "basic qualifications",
        "who you are", "required", "must have",
    ],
    "preferred": [
        "preferred", "nice to have", "nice-to-have", "bonus", "plus",
        "preferred qualifications", "preferred skills", "a plus",
    ],
}


# ---------------------------------------------------------------------------
# Text helpers
# ---------------------------------------------------------------------------

def _clean_text(text):
    text = (text or "")
    text = re.sub(r"<[^>]+>", " ", text)          # strip any HTML tags
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _lower(text):
    return (text or "").lower()


def _find_terms(text_lower, terms):
    """Return the subset of `terms` present in text_lower (substring match)."""
    return [t for t in terms if t in text_lower]


def _split_sections(jd_text):
    """Best-effort split of the JD into responsibilities / qualifications /
    preferred regions using header cues on their own lines."""
    lines = [ln.strip() for ln in (jd_text or "").splitlines()]
    sections = {"responsibilities": [], "qualifications": [], "preferred": [], "_other": []}
    current = "_other"
    for ln in lines:
        low = ln.lower().strip(" :*-•#")
        matched_header = None
        if low and len(low) <= 60:
            for sec, cues in SECTION_CUES.items():
                if any(low == c or low.startswith(c) for c in cues):
                    matched_header = sec
                    break
        if matched_header:
            current = matched_header
            continue
        if ln:
            sections[current].append(ln)
    return {k: "\n".join(v) for k, v in sections.items()}


def _scrub_seniority_false_positives(text_lower):
    """Remove stakeholder/context phrases that are not seniority requirements."""
    scrubbed = text_lower
    for pattern in SENIORITY_FALSE_POSITIVE_SCRUBS:
        scrubbed = re.sub(pattern, " ", scrubbed, flags=re.I)
    return re.sub(r"\s+", " ", scrubbed)


def _max_years_required(text_lower):
    years = [int(m) for m in re.findall(r"(\d{1,2})\s*\+?\s*(?:years|yrs)", text_lower)]
    return max(years) if years else 0


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def _detect_seniority(text_lower):
    scrubbed = _scrub_seniority_false_positives(text_lower)
    found = []
    for label, patterns in SENIORITY_PATTERNS.items():
        if any(re.search(p, scrubbed) for p in patterns):
            found.append(label)
    yrs = _max_years_required(scrubbed)
    if yrs:
        found.append(f"{yrs}+ years")
    return found


def has_explicit_senior_level_requirement(seniority_signals):
    """True when JD explicitly requires Director/Staff/Principal-level or 8+ years."""
    labels = set(seniority_signals or [])
    if labels & {"director", "principal", "staff"}:
        return True
    yrs = _years_required(seniority_signals)
    return yrs >= SENIORITY_YEARS_HARD_CAP_THRESHOLD


def _seniority_overreach_cap(seniority_signals):
    """Whether to apply the conservative seniority/years hard cap."""
    return has_explicit_senior_level_requirement(seniority_signals)


def _detect_risk_flags(text_lower):
    flags = []
    for label, patterns, dealbreaker in RISK_PATTERNS:
        if any(re.search(p, text_lower) for p in patterns):
            flags.append({"flag": label, "dealbreaker": dealbreaker})
    return flags


def _detect_sponsorship(text_lower):
    signals = []
    negatives = []
    for label, patterns, _ in RISK_PATTERNS:
        if label in ("No visa sponsorship", "US citizenship required", "Security clearance required"):
            if any(re.search(p, text_lower) for p in patterns):
                negatives.append(label)
    # Only treat sponsorship as available if there is no negative signal, to avoid
    # matching phrases like "no visa sponsorship available".
    if not negatives and any(re.search(p, text_lower) for p in SPONSORSHIP_POSITIVE):
        signals.append({"signal": "Visa sponsorship appears available", "positive": True})
    for label in negatives:
        signals.append({"signal": label, "positive": False})
    return signals


def _score_role_families(text_lower):
    scores = {}
    matched = {}
    for family, kws in ROLE_FAMILY_KEYWORDS.items():
        hits = _find_terms(text_lower, kws)
        if hits:
            scores[family] = len(hits)
            matched[family] = hits
    return scores, matched


def parse_jd(jd_text):
    """Parse a raw JD into structured signals. Returns a dict."""
    cleaned = _clean_text(jd_text)
    low = _lower(cleaned)
    sections = _split_sections(jd_text)

    responsibilities = sections.get("responsibilities", "")
    qualifications = "\n".join(
        s for s in [sections.get("qualifications", ""), sections.get("_other", "")] if s
    ).strip()
    preferred_region = _lower(sections.get("preferred", ""))
    # Required region = everything except the preferred region.
    required_region = low
    if preferred_region:
        required_region = low.replace(preferred_region, " ")

    preferred_skills = _find_terms(preferred_region, SKILL_BANK)
    required_skills = [s for s in _find_terms(required_region, SKILL_BANK) if s not in preferred_skills]
    tools = _find_terms(low, TOOL_BANK)

    role_scores, role_matched = _score_role_families(low)
    role_keywords = sorted({kw for hits in role_matched.values() for kw in hits})

    return {
        "cleaned_text": cleaned,
        "responsibilities": responsibilities,
        "qualifications": qualifications,
        "required_skills": required_skills,
        "preferred_skills": preferred_skills,
        "tools": tools,
        "seniority_signals": _detect_seniority(low),
        "role_keywords": role_keywords,
        "role_family_scores": role_scores,
        "sponsorship_signals": _detect_sponsorship(low),
        "risk_flags": _detect_risk_flags(low),
    }


# ---------------------------------------------------------------------------
# Fit scoring
# ---------------------------------------------------------------------------

def _candidate_tokens(candidate_profile_text):
    text = _lower(candidate_profile_text)
    if rg is not None:
        try:
            text += " " + " ".join(rg.get_all_facts()).lower()
        except Exception:
            pass
    return text


# Tie-break order reflecting where the candidate is strongest (earlier = stronger).
FAMILY_PRIORITY = [
    "Business Systems / Internal Tools / Enterprise Operations Systems",
    "Product Operations",
    "Program Management",
    "Platform Operations",
    "Product Analytics / Marketing Analytics",
    "Business Operations",
    "Workflow / CX Operations",
    "Customer Support Operations",
    "Creator / Content Operations",
    "Technical Production / Live Operations",
    "Trust & Safety Operations",
    "AI Workflow / Automation Operations",
]


def _select_role_family(role_scores, matched_items):
    """Pick the JD's role family. Ties are broken toward the family where the
    candidate has the most direct verified evidence, then by candidate strength.

    Business-systems JDs prefer the dedicated enterprise-systems family over the
    generic Workflow / CX Operations bucket when both match."""
    if not role_scores:
        return "Other / Unclear", 3.0

    bs_family = "Business Systems / Internal Tools / Enterprise Operations Systems"
    wf_family = "Workflow / CX Operations"
    bs_score = role_scores.get(bs_family, 0)
    wf_score = role_scores.get(wf_family, 0)

    # Enterprise people-systems / ERP JDs should not collapse into CX Operations.
    if bs_score > 0 and (bs_score >= wf_score or wf_score <= 1):
        family = bs_family
        top = bs_score
    else:
        top = max(role_scores.values())
        tied = [f for f, s in role_scores.items() if s == top]

        def direct_count(f):
            return sum(1 for m in matched_items if f in m["families"])

        def prio(f):
            return FAMILY_PRIORITY.index(f) if f in FAMILY_PRIORITY else len(FAMILY_PRIORITY)

        family = max(tied, key=lambda f: (direct_count(f), -prio(f)))

    score = min(10.0, 5.5 + 1.5 * top)
    return family, round(score, 1)


def _score_seniority_fit(seniority_signals):
    """Candidate (~6 yrs ops) fits associate / IC / manager-track ops roles best;
    staff/principal/director are a poor fit. Higher = better fit."""
    labels = set(seniority_signals)
    if {"director"} & labels:
        return 2.0
    if {"principal", "staff"} & labels:
        return 3.0
    score = 7.5  # neutral default (no explicit seniority)
    if {"intern", "new grad", "associate", "junior"} & labels:
        score = 8.5
    if "manager" in labels:
        score = 8.0
    if "lead" in labels:
        score = 6.0
    if "senior" in labels:
        score = 6.0
    yrs = _years_required(seniority_signals)
    if yrs >= 8:
        score = min(score, 3.5)
    elif yrs >= 5:
        score = min(score, 5.5)
    return round(score, 1)


def _score_skill_fit(required_skills, preferred_skills, candidate_text=""):
    req = [
        s for s in required_skills
        if s in SKILL_BANK and s not in SKILL_FIT_GAP_LAYER_SKILLS
    ]
    if not req:
        base = 5.5  # thin JD: be modest, not generous
    else:
        covered = sum(
            1 for s in req
            if s in CANDIDATE_SKILLS or (candidate_text and s in candidate_text)
        )
        base = 10.0 * (covered / len(req))
        # Dampen over-confidence on thin JDs (few required skills detected).
        if len(req) < 3:
            base *= (0.7 + 0.1 * len(req))  # 1 skill -> *0.8, 2 -> *0.9
    # Penalize required hard-skill gaps the candidate lacks.
    gaps = [s for s in required_skills if s in CANDIDATE_SKILL_GAPS]
    base -= 1.5 * len(gaps)
    return round(max(0.0, min(10.0, base)), 1)


def _match_evidence(text_lower):
    """Return matched evidence dicts (full library entries that match the JD)."""
    return [item for item in EVIDENCE_LIBRARY if any(k in text_lower for k in item["keywords"])]


def _evidence_profile(parsed, role_family):
    """Classify matched evidence as direct vs adjacent for the selected family and
    measure coverage of the JD's core responsibility themes by DIRECT evidence."""
    text_low = parsed["cleaned_text"].lower()
    matched = _match_evidence(text_low)

    if role_family == "Other / Unclear":
        direct, adjacent = [], matched
    else:
        direct = [m for m in matched if role_family in m["families"]]
        adjacent = [m for m in matched if role_family not in m["families"]]

    has_metric = any(m["has_metric"] for m in direct)

    # Coverage = JD core themes that a DIRECT evidence item addresses.
    themes_present = [
        t for t, kws in RESPONSIBILITY_THEMES.items() if any(k in text_low for k in kws)
    ]
    covered = 0
    for t in themes_present:
        theme_kws = set(RESPONSIBILITY_THEMES[t])
        if any(theme_kws & set(m["keywords"]) for m in direct):
            covered += 1
    coverage = (covered / len(themes_present)) if themes_present else 0.0

    return {
        "matched": matched,
        "matched_texts": [m["text"] for m in matched],
        "direct": direct,
        "adjacent": adjacent,
        "has_metric": has_metric,
        "coverage": coverage,
        "themes_present": themes_present,
        "themes_covered": covered,
    }


def _score_evidence_strength(profile):
    """Conservative evidence strength.

    Caps:
      - <= 6.5 when there is only adjacent (no direct) evidence
      - <= 8.0 when there is a single / indirect transferable direct example
      - 9.0+ only with multiple direct examples covering core responsibilities
    """
    direct = len(profile["direct"])
    adjacent = len(profile["adjacent"])
    has_metric = profile["has_metric"]
    coverage = profile["coverage"]

    themes_covered = profile["themes_covered"]
    if direct == 0:
        # Only adjacent evidence -> hard cap 6.5.
        score = min(6.5, 3.0 + 1.0 * adjacent)
    elif direct == 1:
        # Single / indirect transferable example -> hard cap 8.0.
        score = 5.0 + 1.0 + 0.5 * min(adjacent, 2) + (0.5 if has_metric else 0.0)
        score = min(8.0, score)
    else:  # >= 2 direct examples
        score = 6.5 + 0.6 * min(themes_covered, 4) + (0.5 if has_metric else 0.0) \
            + 0.2 * min(adjacent, 2)
        # 9.0+ only when multiple direct examples cover several core responsibilities.
        if themes_covered < 3:
            score = min(8.0, score)
        else:
            score = min(10.0, score)
    return round(max(0.0, min(10.0, score)), 1)


def _score_experience_fit(role_family, seniority_signals, risk_flags, profile):
    """Conservative: strong only when the role is in the candidate's wheelhouse AND
    there are DIRECT verified examples. Hard-tech/sales roles stay low."""
    if role_family == "Other / Unclear":
        base = 4.0
    else:
        base = 5.0 + min(3.5, 0.9 * len(profile["direct"])) + 0.3 * min(len(profile["adjacent"]), 2)
    yrs = _years_required(seniority_signals)
    if yrs >= 7:
        base -= 2.5
    elif yrs >= 5:
        base -= 1.0
    hard = {"Heavy production software engineering", "Deep ML model training",
            "Quota-carrying sales role", "CPA required"}
    if any(f["flag"] in hard for f in risk_flags):
        base = min(base, 3.0)
    return round(max(0.0, min(10.0, base)), 1)


def _score_industry_transferability(role_family, risk_flags, profile):
    if role_family == "Other / Unclear":
        return 5.0
    base = 7.0
    # Demonstrated direct transferable evidence raises transferability.
    if len(profile["direct"]) >= 2:
        base = 8.5
    if any(f["flag"] in {"CPA required"} for f in risk_flags):
        base = 3.0
    return round(base, 1)


def _score_sponsorship_feasibility(sponsorship_signals, risk_flags):
    """Sponsorship Feasibility (higher = better / more feasible for the candidate,
    who needs visa sponsorship)."""
    neg = [s for s in sponsorship_signals if not s.get("positive")]
    pos = [s for s in sponsorship_signals if s.get("positive")]
    if neg:
        return 1.0
    if any(f["flag"] in {"US citizenship required", "Security clearance required"}
           for f in risk_flags):
        return 1.0
    if pos:
        return 10.0
    return 6.0


def _years_required(seniority_signals):
    yrs = 0
    for s in seniority_signals:
        m = re.match(r"(\d+)\+ years", s)
        if m:
            yrs = max(yrs, int(m.group(1)))
    return yrs


WEIGHTS = {
    "role_fit": 0.20,
    "experience_fit": 0.25,
    "skill_fit": 0.15,
    "seniority_fit": 0.15,
    "industry_transferability": 0.10,
    "sponsorship_feasibility": 0.05,
    "resume_evidence_strength": 0.10,
}


def decision_for(score):
    """Decision band (recalibrated, stricter)."""
    if score >= 8.5:
        return "High Priority"
    if score >= 7.0:
        return "Apply with Tailoring"
    if score >= 5.5:
        return "Maybe - Needs More Evidence"
    return "Skip"


def priority_for(score):
    if score >= 8.5:
        return "High"
    if score >= 7.0:
        return "Medium"
    if score >= 5.5:
        return "Low"
    return "Skip"


# Backwards-compatible alias.
_decision_for = decision_for


def apply_calibration(base_score, adjustment):
    """Return base_score + adjustment, clamped to [0, 10]."""
    return round(max(0.0, min(10.0, float(base_score) + float(adjustment))), 1)


# Cues for classifying the *quality* of temporary added evidence.
_EVQ_ACTION = [
    "used", "use", "design", "built", "build", "creat", "develop", "implement",
    "prototyp", "led ", "lead", "manage", "own", "ran ", "run ", "coordinat",
    "deliver", "automat", "integrat", "configur", "launch", "drove", "drive",
    "set up", "rolled out", "support", "analyz", "analys", "report", "maintain",
]
_EVQ_CONTEXT = [
    " at ", "for the", "on the", "project", "team", "tool", "internal", "company",
    "client", "mihoyo", "bytedance", "ubisoft", "yousidun", "platform", "system",
    "department", "org ", "organization", "as a ", "as an ",
]
_EVQ_SCOPE = [
    "used by", "stakeholder", "across", "teams", "qa", "publishing", "workflow",
    "process", "deliverable", "dashboard", "pipeline", "rolled out", "handoff",
    "release", "sop", "integration", "implementation", "supporting", "end-to-end",
    "cross-functional", "users", "vendors", "partners", "global", "scope",
]
_EVQ_OUTCOME = [
    "%", "percent", "reduc", "increas", "improv", "sav", "boost", "grew", "grow",
    "cut ", "faster", "roi", "revenue", "retention", "conversion", "decreas",
    "up by", "down by", "by ",
]


def classify_evidence_quality(text):
    """Classify temporary added evidence into one of four levels.

    - Skill claim only: a tool/skill with no company/project/action context.
    - Basic experience example: company/project context + an action, but no scope/outcome.
    - Concrete experience example: action + context + scope/stakeholder/deliverable detail.
    - Outcome-backed experience example: a concrete example plus a measurable result.
    """
    low = (text or "").lower()
    if not low.strip():
        return "Skill claim only"
    has_action = any(c in low for c in _EVQ_ACTION)
    has_context = any(c in low for c in _EVQ_CONTEXT)
    has_scope = any(c in low for c in _EVQ_SCOPE)
    has_number = any(ch.isdigit() for ch in low)
    has_outcome = has_number and any(c in low for c in _EVQ_OUTCOME)

    if has_context and has_action and has_outcome:
        return "Outcome-backed experience example"
    if has_context and has_action and has_scope:
        return "Concrete experience example"
    if has_context and has_action:
        return "Basic experience example"
    return "Skill claim only"


# Small, transparent re-analysis bonus to Experience Fit by evidence quality. This does
# NOT change scoring weights and is only applied during added-evidence re-analysis.
EVIDENCE_QUALITY_EXPERIENCE_BONUS = {
    "Skill claim only": 0.0,
    "Basic experience example": 0.0,
    "Concrete experience example": 0.5,
    "Outcome-backed experience example": 1.0,
}


# Maps a missing skill/keyword theme to an evidence-gap question.
GAP_QUESTION_RULES = [
    (["stakeholder", "cross-functional", "communication", "program", "project"],
     "Do you have an example of owning stakeholder communication or cross-functional coordination for this type of workflow?"),
    (["sql", "dashboard", "reporting", "analytics", "data", "metric", "kpi"],
     "Do you have SQL / dashboard / reporting evidence you can point to for this role?"),
    (["support", "customer", "creator", "community", "trust", "safety", "moderation"],
     "Do you have creator / customer / support operations experience related to this JD?"),
    (["launch", "release", "go-live", "program", "roadmap", "milestone"],
     "Do you have a cross-functional launch or program-management example for this scope?"),
    (["platform", "sdk", "integration", "automation", "workflow"],
     "Do you have platform / workflow / automation operations evidence for this JD?"),
]


def _evidence_gap_questions(parsed, matched_evidence, candidate_text):
    """Generate targeted questions for themes present in the JD but weak in evidence."""
    jd_low = parsed["cleaned_text"].lower()
    questions = []
    matched_blob = " ".join(matched_evidence).lower()
    for keywords, question in GAP_QUESTION_RULES:
        in_jd = any(k in jd_low for k in keywords)
        have_evidence = any(k in matched_blob for k in keywords) or any(
            k in candidate_text for k in keywords
        )
        if in_jd and not have_evidence:
            questions.append(question)
    # Always offer the broad transferability question if few matches.
    if len(matched_evidence) < 3:
        questions.append(
            "Do you have any experience in this industry or a similar user-facing "
            "product workflow you can add?"
        )
    # De-duplicate, keep order.
    seen, out = set(), []
    for q in questions:
        if q not in seen:
            seen.add(q)
            out.append(q)
    return out


def _compute_caps(parsed, role_family, profile):
    """Return (cap_value or None, notes) applying conservative hard penalties."""
    flags = {f["flag"] for f in parsed["risk_flags"]}

    caps = []
    notes = []

    sponsorship_blockers = {"No visa sponsorship", "US citizenship required",
                            "Security clearance required"}
    if flags & sponsorship_blockers:
        caps.append(3.0)
        notes.append("sponsorship/clearance blocker")

    hard_domain = {"Heavy production software engineering", "Deep ML model training",
                   "Quota-carrying sales role", "CPA required"}
    if flags & hard_domain:
        # Candidate has no direct verified evidence for these domains.
        caps.append(4.0)
        notes.append("hard domain requirement without verified evidence")

    overreach = _seniority_overreach_cap(parsed["seniority_signals"])
    if overreach:
        caps.append(5.0)
        notes.append("seniority/years far above candidate experience")

    if caps:
        return min(caps), notes
    return None, notes


def _compute_confidence(parsed, role_family, profile):
    text = parsed["cleaned_text"]
    points = 0
    if len(text) >= 400:
        points += 1
    if len(text) >= 800:
        points += 1
    if parsed["required_skills"]:
        points += 1
    if role_family != "Other / Unclear":
        points += 1
    if parsed.get("responsibilities"):
        points += 1
    if len(profile["direct"]) >= 2:
        points += 1

    if points >= 5:
        label = "High confidence"
    elif points >= 3:
        label = "Medium confidence"
    else:
        label = "Low confidence"
    # Unclear role family limits how confident we can be.
    if role_family == "Other / Unclear" and label == "High confidence":
        label = "Medium confidence"
    return label


def _reason_text(decision, profile, capped, cap_notes):
    if capped:
        return f"Hard requirement(s) limit this fit ({', '.join(cap_notes)})."
    direct = len(profile["direct"])
    if decision == "High Priority":
        return "Multiple direct, verified examples align with the JD's core responsibilities."
    if decision == "Apply with Tailoring":
        return "Strong transferability, but not enough direct evidence to reach High Priority."
    if decision == "Maybe - Needs More Evidence":
        return "Partial alignment; add direct, verified evidence to strengthen this application."
    return "Low alignment with your verified profile."


def analyze_fit(jd_text, candidate_profile_text, role_profiles=None,
                added_evidence_quality=None):
    """Score JD fit against the candidate. Returns a structured dict.

    The returned `overall_score` is the BASE fit score. Calibration from prior
    feedback and per-analysis user calibration are applied/recorded separately.

    `added_evidence_quality` is used ONLY during added-evidence re-analysis to apply a
    small, transparent Experience Fit bonus for concrete / outcome-backed examples. It
    does not change scoring weights and defaults to no effect.
    """
    parsed = parse_jd(jd_text)
    text_low = parsed["cleaned_text"].lower()
    candidate_text = _candidate_tokens(candidate_profile_text)

    matched_items = _match_evidence(text_low)
    role_family, role_fit = _select_role_family(parsed["role_family_scores"], matched_items)
    profile = _evidence_profile(parsed, role_family)

    seniority_fit = _score_seniority_fit(parsed["seniority_signals"])
    skill_fit = _score_skill_fit(
        parsed["required_skills"], parsed["preferred_skills"], candidate_text
    )
    evidence_strength = _score_evidence_strength(profile)
    experience_fit = _score_experience_fit(
        role_family, parsed["seniority_signals"], parsed["risk_flags"], profile
    )
    # Re-analysis-only: concrete/outcome-backed temporary evidence may nudge Experience
    # Fit. Resume Evidence Strength is intentionally NOT raised (not verified evidence).
    exp_bonus = EVIDENCE_QUALITY_EXPERIENCE_BONUS.get(added_evidence_quality, 0.0)
    if exp_bonus:
        experience_fit = round(min(10.0, experience_fit + exp_bonus), 1)
    transferability = _score_industry_transferability(role_family, parsed["risk_flags"], profile)
    sponsorship_feasibility = _score_sponsorship_feasibility(
        parsed["sponsorship_signals"], parsed["risk_flags"]
    )

    component_scores = {
        "role_fit": role_fit,
        "experience_fit": experience_fit,
        "skill_fit": skill_fit,
        "seniority_fit": seniority_fit,
        "industry_transferability": transferability,
        "sponsorship_feasibility": sponsorship_feasibility,
        "resume_evidence_strength": evidence_strength,
    }

    overall = round(sum(component_scores[k] * WEIGHTS[k] for k in WEIGHTS), 1)

    cap, cap_notes = _compute_caps(parsed, role_family, profile)
    capped = False
    if cap is not None and overall > cap:
        overall = cap
        capped = True

    decision = decision_for(overall)
    priority = priority_for(overall)
    confidence = _compute_confidence(parsed, role_family, profile)

    suggested_resume_angle = _suggested_angle(role_family, text_low)

    matched_evidence = profile["matched_texts"]

    missing_evidence = [
        s for s in parsed["required_skills"]
        if s not in CANDIDATE_SKILLS and s not in (candidate_text or "")
    ]
    for f in parsed["risk_flags"]:
        missing_evidence.append(f"Hard requirement: {f['flag']}")

    evidence_gap_questions = _evidence_gap_questions(parsed, matched_evidence, candidate_text)
    red_flags = [f["flag"] for f in parsed["risk_flags"]]

    top_evidence = matched_evidence[0] if matched_evidence else "transferable operations experience"
    recommended_positioning = (
        f"Position as **{suggested_resume_angle}** for the {role_family} family. "
        f"Lead with {top_evidence}; mirror the JD's language for "
        f"{', '.join(parsed['role_keywords'][:5]) or 'the core responsibilities'}."
    )

    reason = _reason_text(decision, profile, capped, cap_notes)
    cap_note = f" Capped at {overall} due to: {', '.join(cap_notes)}." if capped else ""
    scoring_explanation = f"{overall} = {decision}. {reason}{cap_note}"

    return {
        "overall_score": overall,          # base score
        "base_score": overall,
        "decision": decision,
        "priority": priority,
        "confidence": confidence,
        "selected_role_family": role_family,
        "suggested_resume_angle": suggested_resume_angle,
        "component_scores": component_scores,
        "sponsorship_feasibility": sponsorship_feasibility,
        "matched_evidence": matched_evidence,
        "direct_evidence": [m["text"] for m in profile["direct"]],
        "adjacent_evidence": [m["text"] for m in profile["adjacent"]],
        "evidence_coverage": round(profile["coverage"], 2),
        "missing_evidence": missing_evidence,
        "evidence_gap_questions": evidence_gap_questions,
        "red_flags": red_flags,
        "recommended_positioning": recommended_positioning,
        "scoring_explanation": scoring_explanation,
        "parsed": parsed,
    }
