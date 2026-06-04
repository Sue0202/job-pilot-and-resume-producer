"""Rule-based tailored resume generator for JobPilot.

Holds the canonical, verified candidate material (header, profile versions,
experience groups, bullet banks, education) and assembles a tailored resume
based on the match result and optional user feedback.

No external AI APIs are used. Generation is deterministic and rule-based, and
never fabricates experience, tools, metrics, titles, employers, or dates.
"""

import re

# ---------------------------------------------------------------------------
# Canonical candidate material (single source of truth for generation)
# ---------------------------------------------------------------------------

HEADER = {
    "name": "YEYI SU",
    "location": "San Francisco, California, United States",
    "email": "yyisu0202@gmail.com",
    "phone": "6283064627",
}

# Role family -> profile angle + target title
ROLE_FAMILIES = {
    "product_program": {
        "angle": "A",
        "title": "Product Operations & Program Management",
    },
    "workflow_support": {
        "angle": "B",
        "title": "Workflow Strategist, Customer Support",
    },
    "platform_ops": {
        "angle": "C",
        "title": "Product Operations Manager | Platform Operations",
    },
    "technical_production": {
        "angle": "D",
        "title": "Technical Production & Live Service Operations",
    },
}

PROFILES = {
    "A": {
        "title": "Product Operations & Program Management",
        "profile": (
            "MSBA candidate with a background in product operations, creator-facing "
            "programs, and large-scale digital products. Experienced in turning user "
            "feedback, operational signals, and data insights into product requirements, "
            "workflow improvements, SOPs, and cross-functional execution plans. Available "
            "for a 2026 internship starting June 2026."
        ),
        "expertise": [
            "Product Operations",
            "Program Management",
            "Workflow Design",
            "SOP Development",
            "SQL & EDA",
            "User Feedback Analysis",
            "Cross-functional Execution",
            "Launch Readiness",
        ],
    },
    "B": {
        "title": "Workflow Strategist, Customer Support",
        "profile": (
            "Product operations and workflow strategy professional with 6+ years in live "
            "digital products, launch readiness, support escalation, incident response, and "
            "platform-driven process improvement. Completing MSBA at UC Davis in July 2026, "
            "with SQL/EDA experience turning operational signals into actionable workflows "
            "and product requirements."
        ),
        "expertise": [
            "Product Operations",
            "Workflow Design",
            "Support Escalation",
            "Incident Response",
            "RCA",
            "SOP Development",
            "SQL",
            "EDA",
            "Data Visualization",
            "Platform Requirements",
        ],
    },
    "C": {
        "title": "Product Operations Manager | Platform Operations",
        "profile": (
            "Product operations professional with 6+ years in live digital products, "
            "platform operations, launch readiness, workflow design, and incident response. "
            "Completing MSBA at UC Davis in July 2026, with SQL/EDA experience translating "
            "operational, user, and business signals into scalable workflows and product "
            "requirements."
        ),
        "expertise": [
            "Product Operations",
            "Platform Operations",
            "Launch Readiness",
            "Workflow Design",
            "SOP Development",
            "Risk Management",
            "RCA",
            "Incident Response",
            "SQL",
            "EDA",
            "Data Visualization",
            "Cross-functional Execution",
        ],
    },
    "D": {
        "title": "Technical Production & Live Service Operations",
        "profile": (
            "Live service operations and technical production professional with experience "
            "in launch readiness, release execution, platform workflows, incident response, "
            "operational risk controls, and cross-functional delivery for large-scale "
            "digital products."
        ),
        "expertise": [
            "Technical Production",
            "Release Management",
            "Live Operations",
            "Launch Readiness",
            "Incident Response",
            "Risk Management",
            "Cross-functional Execution",
            "Platform Workflows",
        ],
    },
}

# Experience groups. Each bullet carries the role families it best supports.
EXPERIENCE = {
    "mihoyo": {
        "role_title": "Technical Production & Product Operations, miHoYo",
        "dates": "Jul 2021 to Jul 2024",
        "location": "Shanghai, China",
        "contexts": {
            "default": (
                "Honkai: Star Rail, a globally published, multi-platform live digital "
                "product across iOS, Android, PC, PlayStation, and cloud platforms with "
                "tens of millions of MAU (20M downloads within 24 hours of launch; "
                "100M+ downloads within its first year)."
            ),
            "product": (
                "Owned live product operations from launch through post-launch iteration, "
                "supporting high-volume user-facing workflows, incident response, release "
                "readiness, and long-term operating standards."
            ),
            "platform": (
                "Owned R&D-side live operations from 0-to-1 launch through post-launch "
                "stability, focusing on workflow design, platform capability building, "
                "incident response, and user-facing operational risk for a high-scale "
                "live product."
            ),
        },
        "bullets": [
            {
                "text": "Built platform-driven risk controls by turning live incident reviews into product requirements and workflow mechanisms, including batch operations, permission models, approval checkpoints, and automated alerting.",
                "families": ["platform_ops"],
            },
            {
                "text": "Managed high-impact live operations and P0-level incident response for a large-scale user-facing product, converting production incidents and policy-risk cases into process improvements, platform requirements, and long-term operating playbooks.",
                "families": ["platform_ops", "workflow_support", "technical_production"],
            },
            {
                "text": "Translated user pain points and support feedback into product and engineering requirements through beta testing, internal playtesting, post-launch issue review, and customer support escalation workflows.",
                "families": ["product_program", "workflow_support"],
            },
            {
                "text": "Drove cross-functional execution between R&D, QA, operations, publishing, marketing, platform, infrastructure, and compliance stakeholders to support launch readiness, release execution, and stable live operations from v1.0 to v2.2.",
                "families": ["product_program", "technical_production", "platform_ops"],
            },
            {
                "text": "Built major-version release and support operating standards for a 6-week live cadence, aligning launch calendars, issue severity, fix priority, customer response, compensation logic, and escalation paths across teams.",
                "families": ["technical_production", "workflow_support"],
            },
            {
                "text": "Supported external partnership and creator-facing initiatives by coordinating confidentiality and compliance workflows, breaking down R&D requirements, defining milestones, and tracking execution for marketing campaigns, creator/UGC programs, exhibitions, and Apple/Google platform collaborations.",
                "families": ["product_program"],
            },
        ],
    },
    "bytedance": {
        "role_title": "Overseas Product Launch & Game Operations, ByteDance",
        "dates": "Jan 2020 to Jun 2021",
        "location": "Shenzhen, China",
        "contexts": {
            "default": (
                "Japan-market licensed mobile game publishing, including Eden's Door, "
                "ByteDance's first Japan-published mobile game. Served as the China-based "
                "launch operations bridge between external developers and ByteDance's "
                "internal platform, legal, security, growth, and operations teams."
            ),
        },
        "bullets": [
            {
                "text": "Built end-to-end launch operating plans by translating publishing goals into milestone ownership, SDK integration, server deployment, store submission, compliance review, update maintenance, and quality management workflows.",
                "families": ["product_program", "technical_production", "platform_ops"],
            },
            {
                "text": "Served as the China-based launch operations bridge between external game developers and ByteDance's internal platform, coordinating legal, security, SDK, server deployment, store submission, and publishing planning workflows.",
                "families": ["product_program", "platform_ops"],
            },
            {
                "text": "Operationalized external products into ByteDance's publishing platform, turning developer-side constraints and Japan-market requirements into internal platform tasks, SDK feature requests, technical integration plans, and go-live standards.",
                "families": ["platform_ops", "technical_production"],
            },
            {
                "text": "Partnered with User Growth, data analysis, and user research teams on closed beta and customer engagement tests, using creative A/B testing, user feedback, and retention analysis to identify product improvements and support 10%+ Day-1 retention improvement during test iterations.",
                "families": ["product_program"],
            },
            {
                "text": "Defined Japan-specific product and SDK requirements based on local user behavior and regulatory needs, including transfer-code flows, account recovery, login adjustments, review prompts, and underage payment restrictions.",
                "families": ["platform_ops", "product_program"],
            },
            {
                "text": "Coordinated legal, security, and platform reviews before launch, converting compliance and operational risk requirements into product modifications, monitoring rules, alerting strategies, and anti-abuse workflows.",
                "families": ["platform_ops", "workflow_support"],
            },
        ],
    },
    "ubisoft": {
        "role_title": "Business Analytics Practicum, Ubisoft",
        "dates": "Sep 2025 to Jun 2026",
        "location": "San Francisco, CA / Remote",
        "contexts": {
            "default": (
                "Supported Ubisoft's Rainbow Six Siege marketing mix modeling (MMM) and "
                "publishing analytics workstream through data collection, EDA, competitive "
                "research, deliverable tracking, and stakeholder review across a student "
                "consulting team."
            ),
            "analytics": (
                "Supported Ubisoft's Rainbow Six Siege MMM and publishing analytics "
                "workstream by using SQL, EDA, visualization, and external data collection "
                "to identify regional trends, competitor signals, and performance patterns "
                "for stakeholder decision-making."
            ),
        },
        "bullets": [
            {
                "text": "Built SQL/Python-assisted workflows to clean and standardize global social media, marketing, and regional datasets, resolving messy historical fields, region mappings, weekly aggregation issues, and metric definition gaps.",
                "families": ["product_program", "platform_ops"],
            },
            {
                "text": "Conducted seasonality, regional performance, and competitor analysis to identify recurring demand patterns across holidays, major launches, esports events, social channels, and FPS market activity.",
                "families": ["product_program"],
            },
            {
                "text": "Created external competitor datasets through web scraping and secondary research to monitor FPS release cycles, pre-order availability, and competitor launch timing.",
                "families": ["product_program", "technical_production"],
            },
            {
                "text": "Produced EDA, regression checks, visual summaries, and analytical notes that translated data limitations, market signals, and competitive risks into stakeholder-facing insights, while maintaining PMO cadence for task intake, documentation, deliverable tracking, and presentations.",
                "families": ["product_program", "platform_ops", "technical_production", "workflow_support"],
            },
        ],
    },
    "yousidun": {
        "role_title": "Community & Live Operations, Shenzhen Yousidun",
        "dates": "Jul 2018 to Dec 2019",
        "location": "Shenzhen, China",
        "contexts": {
            "default": (
                "Clash of Empires, a U.S.-focused mobile strategy game. Managed frontline "
                "user/player-facing live operations, connecting player feedback, support "
                "issues, community sentiment, and product improvement needs."
            ),
        },
        "bullets": [
            {
                "text": "Managed player-facing live operations for a U.S.-market mobile strategy game, covering community management, localization, customer support workflows, player sentiment tracking, and live issue escalation.",
                "families": ["workflow_support", "product_program"],
            },
            {
                "text": "Built feedback-to-product loops across Facebook communities, support tickets, and moderator reports, identifying recurring player pain points and translating them into version improvement recommendations.",
                "families": ["product_program"],
            },
            {
                "text": "Managed support escalation for live issues, bugs, account problems, and player complaints, helping prioritize high-impact cases and maintain consistent multilingual support workflows.",
                "families": ["workflow_support"],
            },
            {
                "text": "Designed data-informed in-game campaigns based on activity, retention, and virtual economy trends to maintain engagement and support long-term ecosystem balance.",
                "families": ["product_program", "technical_production"],
            },
        ],
    },
}

GROUP_ORDER = ["mihoyo", "bytedance", "ubisoft", "yousidun"]

EDUCATION_PRIMARY = {
    "school": "University of California, Davis, San Francisco, CA",
    "degree": "Master of Science in Business Analytics",
    "dates": "Aug 2025 to Jul 2026",
    "fellowship": "MSBA Fellowship: $27,000",
    "coursework_analytics": "SQL, Data Management, Business Analytics, Statistics, Marketing Analytics, Machine Learning",
    "coursework_product": "Business Analytics, Statistics, SQL, Data Management, Big Data Concepts, LLM Applications",
}

EDUCATION_SECONDARY = {
    "school": "Sichuan International Studies University, Chongqing, China",
    "degree": "Bachelor of Arts in International Economics and Trade",
    "dates": "Sep 2014 to Jun 2018",
}

# Feedback keyword -> role family nudge
FEEDBACK_FAMILY_HINTS = {
    "platform": "platform_ops",
    "support": "workflow_support",
    "incident": "workflow_support",
    "technical": "technical_production",
    "release": "technical_production",
    "production": "technical_production",
    "analytics": "product_program",
    "program": "product_program",
    "product": "product_program",
}


def _tokens(text):
    return set(re.findall(r"[a-z0-9]+", (text or "").lower()))


def _select_family(match_result, feedback_text):
    """Pick the role family / profile angle, lightly nudged by feedback."""
    scores = dict(match_result.get("role_family_scores") or {})
    for fam in ROLE_FAMILIES:
        scores.setdefault(fam, 0)

    feedback_tokens = _tokens(feedback_text)
    for word, fam in FEEDBACK_FAMILY_HINTS.items():
        if word in feedback_tokens:
            scores[fam] = scores.get(fam, 0) + 1.5

    # Fall back to match_result's selection if everything ties at zero.
    best = max(scores, key=lambda f: (scores[f], f == _angle_to_family(match_result.get("selected_profile_angle"))))
    if all(v == 0 for v in scores.values()):
        best = _angle_to_family(match_result.get("selected_profile_angle")) or "product_program"
    return best


def _angle_to_family(angle):
    for fam, meta in ROLE_FAMILIES.items():
        if meta["angle"] == angle:
            return fam
    return None


def _pick_context(group_key, family):
    contexts = EXPERIENCE[group_key]["contexts"]
    if group_key == "mihoyo":
        if family in ("platform_ops", "technical_production"):
            return contexts["default"] + " " + contexts["platform"]
        return contexts["default"] + " " + contexts["product"]
    if group_key == "ubisoft":
        if family == "product_program":
            return contexts["default"]
        # analytics-leaning families still use a stakeholder-safe framing
        return contexts.get("analytics", contexts["default"])
    return contexts["default"]


def _feedback_families(feedback_text):
    tokens = _tokens(feedback_text)
    return {fam for word, fam in FEEDBACK_FAMILY_HINTS.items() if word in tokens}


def _select_bullets(group_key, family, feedback_families, keyword_tokens, max_bullets=3):
    """Rank bullets by keyword overlap + family fit; always return >=2.

    Feedback families add an extra bonus so refinement visibly re-weights the
    selected bullets even when the overall target title stays the same.
    """
    bullets = EXPERIENCE[group_key]["bullets"]
    scored = []
    for idx, b in enumerate(bullets):
        overlap = len(_tokens(b["text"]) & keyword_tokens)
        family_bonus = 3 if family in b["families"] else 0
        feedback_bonus = 2 * len(feedback_families & set(b["families"]))
        score = overlap * 2 + family_bonus + feedback_bonus
        scored.append((score, -idx, b["text"]))
    scored.sort(reverse=True)
    chosen = [t[2] for t in scored[:max_bullets]]
    if len(chosen) < 2:
        chosen = [b["text"] for b in bullets[:2]]
    return chosen


def _build_education(keyword_tokens):
    analytics_signal = {"sql", "eda", "analytics", "statistics", "visualization", "marketing", "data"}
    use_analytics = len(keyword_tokens & analytics_signal) >= 2
    coursework = (
        EDUCATION_PRIMARY["coursework_analytics"]
        if use_analytics
        else EDUCATION_PRIMARY["coursework_product"]
    )
    lines = [
        EDUCATION_PRIMARY["school"],
        EDUCATION_PRIMARY["degree"],
        EDUCATION_PRIMARY["dates"],
        EDUCATION_PRIMARY["fellowship"],
        f"Relevant coursework: {coursework}",
        "",
        EDUCATION_SECONDARY["school"],
        EDUCATION_SECONDARY["degree"],
        EDUCATION_SECONDARY["dates"],
    ]
    return "\n".join(lines)


def generate_resume(candidate_profile, job_row, match_result, feedback_text=""):
    """Assemble a tailored resume. Returns a structured dict + full text."""
    family = _select_family(match_result, feedback_text)
    angle = ROLE_FAMILIES[family]["angle"]
    profile_meta = PROFILES[angle]
    target_title = profile_meta["title"]

    # Keyword pool used to rank bullets: matched JD keywords + feedback words.
    keyword_tokens = set()
    for kw in match_result.get("matched_keywords", []):
        keyword_tokens |= _tokens(kw)
    keyword_tokens |= _tokens(feedback_text)
    keyword_tokens |= _tokens(job_row.get("job_title", ""))

    feedback_families = _feedback_families(feedback_text)

    # Build professional experience section.
    experience_blocks = []
    for group_key in GROUP_ORDER:
        g = EXPERIENCE[group_key]
        context = _pick_context(group_key, family)
        bullets = _select_bullets(group_key, family, feedback_families, keyword_tokens)
        block_lines = [
            g["role_title"],
            f"{g['dates']} | {g['location']}",
            context,
        ]
        for b in bullets:
            block_lines.append(f"• {b}")
        experience_blocks.append("\n".join(block_lines))
    professional_experience = "\n\n".join(experience_blocks)

    areas_of_expertise = " | ".join(profile_meta["expertise"])
    education = _build_education(keyword_tokens)

    contact_line = f"{HEADER['location']} | {HEADER['email']} | {HEADER['phone']}"

    full_text_parts = [
        HEADER["name"],
        target_title,
        contact_line,
        "",
        "PROFILE",
        profile_meta["profile"],
        "",
        "AREAS OF EXPERTISE",
        f"• {areas_of_expertise}",
        "",
        "PROFESSIONAL EXPERIENCE",
        professional_experience,
        "",
        "EDUCATION",
        education,
    ]
    full_resume_text = "\n".join(full_text_parts)

    return {
        "header_name": HEADER["name"],
        "header_location": HEADER["location"],
        "header_email": HEADER["email"],
        "header_phone": HEADER["phone"],
        "target_title": target_title,
        "profile": profile_meta["profile"],
        "areas_of_expertise": areas_of_expertise,
        "professional_experience": professional_experience,
        "education": education,
        "full_resume_text": full_resume_text,
    }


def get_all_facts():
    """Flat list of all candidate facts (contexts + bullets) for TF-IDF use."""
    facts = []
    for group_key in GROUP_ORDER:
        g = EXPERIENCE[group_key]
        for ctx in g["contexts"].values():
            facts.append(ctx)
        for b in g["bullets"]:
            facts.append(b["text"])
    return facts
