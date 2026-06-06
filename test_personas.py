"""Official test personas for evaluating JobPilot's recommendation quality.

IMPORTANT: These personas are used ONLY to evaluate ranking / filtering behavior.
They do NOT replace the project owner's (Yeyi Su) verified resume material, and the
real resume generator is never used to fabricate persona resumes. An optional,
clearly-labeled generic "persona demo resume" is available for demonstration only.
"""

# Companies treated as simple, well-known sponsor-friendly employers (Kenji check).
SPONSOR_COMPANIES = [
    "google", "microsoft", "amazon", "meta", "apple", "nvidia", "openai",
    "adobe", "salesforce", "ibm", "oracle", "intel", "tiktok", "uber",
]

SENIOR_TITLE_TERMS = ["senior", "staff", "principal", "lead", "sr.", "sr ", "director", "head of"]
JUNIOR_TITLE_TERMS = ["junior", "jr.", "jr ", "intern", "trainee"]
CONTRACT_TERMS = ["contract", "contractor", "temp", "temporary", "unpaid", "part-time"]
EXPERIENCE_TERMS = ["3+ years", "5+ years", "7+ years", "3-5 years", "5-7 years"]


PERSONAS = {
    "aisha": {
        "persona_name": "Aisha — ML Engineer career pivoter",
        "background": "Career pivoter moving into machine learning engineering from an adjacent field.",
        "skills": ["machine learning", "python", "pytorch", "scikit-learn", "data analysis"],
        "target_roles": ["ML Engineer", "Applied Scientist", "Data Scientist"],
        "preferences": ["Entry/mid-level ML roles", "Hands-on modeling work"],
        "dealbreakers": ["Senior/Staff/Principal/Lead titles", "Defense/military work"],
        "pass_criteria": (
            "Top 10 avoids senior titles, is ML-related by keywords, and has no "
            "defense/military keywords."
        ),
        "profile_text": (
            "Machine learning engineer candidate pivoting into ML. Skilled in Python, "
            "PyTorch, scikit-learn, applied machine learning, model training, data "
            "analysis, and experimentation. Seeking entry to mid-level ML engineer, "
            "applied scientist, or data scientist roles."
        ),
    },
    "marcus": {
        "persona_name": "Marcus — New grad broad analytics search",
        "background": "New graduate running a broad analytics job search.",
        "skills": ["sql", "python", "data analysis", "dashboards", "statistics"],
        "target_roles": ["Data Analyst", "BI Analyst", "Junior Data Scientist", "Analytics Engineer"],
        "preferences": ["Entry-level analytics", "Full-time paid roles"],
        "dealbreakers": ["3+/5+ years required", "Senior/Staff/Principal", "Contract-only/unpaid"],
        "pass_criteria": (
            "Top 10 avoids senior/experienced titles and contract/unpaid roles, and "
            "leans toward analytics roles."
        ),
        "profile_text": (
            "New graduate seeking entry-level analytics roles such as data analyst, "
            "business intelligence analyst, junior data scientist, or analytics "
            "engineer. Skilled in SQL, Python, data analysis, dashboards, reporting, "
            "and statistics."
        ),
    },
    "priya": {
        "persona_name": "Priya — Experienced ML/AI infrastructure",
        "background": "Experienced engineer focused on ML/AI platform and infrastructure.",
        "skills": ["mlops", "kafka", "spark", "kubernetes", "aws", "ml platform", "infrastructure"],
        "target_roles": ["ML Platform Engineer", "MLOps Engineer", "ML Infrastructure Engineer"],
        "preferences": ["NYC or remote", "Senior platform/infrastructure roles"],
        "dealbreakers": ["Junior roles"],
        "pass_criteria": (
            "Top 10 avoids junior roles and leans toward ML platform / MLOps / "
            "infrastructure; prefers NYC or remote."
        ),
        "profile_text": (
            "Experienced ML/AI infrastructure engineer. Skilled in MLOps, ML platform "
            "engineering, Kafka, Spark, Kubernetes, AWS, distributed systems, and "
            "infrastructure. Seeking senior ML platform, MLOps, or ML infrastructure "
            "roles in NYC or remote."
        ),
    },
    "kenji": {
        "persona_name": "Kenji — International visa-constrained AI/ML search",
        "background": "International candidate needing visa sponsorship for AI/ML roles.",
        "skills": ["machine learning", "deep learning", "python", "research", "ai engineering"],
        "target_roles": ["Research Scientist", "ML Engineer", "Applied Scientist", "AI Engineer"],
        "preferences": ["Sponsor-friendly large employers", "Full-time roles"],
        "dealbreakers": ["Contract/temp roles"],
        "pass_criteria": (
            "Top 10 avoids contract/temp roles, leans toward AI/ML research/engineering, "
            "and prefers known sponsor-friendly companies."
        ),
        "profile_text": (
            "International AI/ML candidate seeking visa sponsorship. Skilled in machine "
            "learning, deep learning, Python, research, and AI engineering. Targeting "
            "research scientist, ML engineer, applied scientist, or AI engineer roles "
            "at large sponsor-friendly companies."
        ),
    },
}

# Per-persona positive keyword sets used for the "ML/analytics-related" check.
POSITIVE_KEYWORDS = {
    "aisha": ["machine learning", "ml engineer", "applied scientist", "data scientist",
              "python", "pytorch", "scikit-learn"],
    "marcus": ["data analyst", "bi analyst", "business intelligence", "junior data scientist",
               "analytics engineer", "analytics", "sql"],
    "priya": ["ml platform", "mlops", "kafka", "spark", "kubernetes", "aws", "infrastructure"],
    "kenji": ["research scientist", "ml engineer", "applied scientist", "ai engineer",
              "machine learning"],
}

DEFENSE_TERMS = ["defense", "military", "weapon", "army", "navy", "air force", "missile"]


def _contains_any(text, terms):
    text = (text or "").lower()
    return [t for t in terms if t.strip() and t in text]


def _check(name, passed, detail):
    return {"check": name, "result": "Pass" if passed else "Fail", "detail": detail}


def evaluate_persona(persona_key, top_jobs):
    """Rule-based pass/fail checks over the top recommended jobs (list of dicts
    with at least 'job_title', 'company', 'location', 'description').

    Returns a list of check dicts. If there are too few jobs to judge, a single
    limitation row is returned.
    """
    checks = []
    if not top_jobs:
        return [_check("data availability", False, "No recommended jobs to evaluate.")]

    titles = [(j.get("job_title", "") or "").lower() for j in top_jobs]
    descs = [(j.get("description", "") or "").lower() for j in top_jobs]
    companies = [(j.get("company", "") or "").lower() for j in top_jobs]
    locations = [(j.get("location", "") or "").lower() for j in top_jobs]
    blob = [t + " " + d for t, d in zip(titles, descs)]

    positives = POSITIVE_KEYWORDS.get(persona_key, [])
    n_positive = sum(1 for b in blob if _contains_any(b, positives))

    if persona_key == "aisha":
        bad = [t for t in titles if _contains_any(t, SENIOR_TITLE_TERMS)]
        checks.append(_check("No senior/staff/principal/lead titles", not bad,
                             f"{len(bad)} senior-titled jobs in top {len(top_jobs)}"))
        checks.append(_check("ML-related (>=3 of top 10)", n_positive >= 3,
                             f"{n_positive} ML-related jobs by keywords"))
        defense = [b for b in blob if _contains_any(b, DEFENSE_TERMS)]
        checks.append(_check("No defense/military", not defense,
                             f"{len(defense)} defense/military jobs"))

    elif persona_key == "marcus":
        snr = [t for t in titles if _contains_any(t, SENIOR_TITLE_TERMS)]
        checks.append(_check("No senior titles", not snr,
                             f"{len(snr)} senior-titled jobs"))
        exp = [b for b in blob if _contains_any(b, EXPERIENCE_TERMS)]
        checks.append(_check("No 3+/5+ years required", not exp,
                             f"{len(exp)} jobs requiring multi-year experience"))
        contract = [b for b in blob if _contains_any(b, ["contract", "unpaid", "temporary"])]
        checks.append(_check("No contract-only/unpaid", not contract,
                             f"{len(contract)} contract/unpaid jobs"))
        checks.append(_check("Analytics-leaning (>=3 of top 10)", n_positive >= 3,
                             f"{n_positive} analytics-related jobs"))

    elif persona_key == "priya":
        jr = [t for t in titles if _contains_any(t, JUNIOR_TITLE_TERMS)]
        checks.append(_check("No junior roles", not jr, f"{len(jr)} junior-titled jobs"))
        checks.append(_check("Platform/MLOps/infra-leaning (>=3)", n_positive >= 3,
                             f"{n_positive} platform/infra-related jobs"))
        loc_ok = sum(1 for loc in locations if "remote" in loc or "ny" in loc or "new york" in loc)
        checks.append(_check("Prefer NYC or remote (>=1)", loc_ok >= 1,
                             f"{loc_ok} NYC/remote jobs (location data may be limited)"))

    elif persona_key == "kenji":
        contract = [b for b in blob if _contains_any(b, CONTRACT_TERMS)]
        checks.append(_check("No contract/temp", not contract,
                             f"{len(contract)} contract/temp jobs"))
        checks.append(_check("AI/ML-leaning (>=3 of top 10)", n_positive >= 3,
                             f"{n_positive} AI/ML-related jobs"))
        sponsor = sum(1 for c in companies if _contains_any(c, SPONSOR_COMPANIES))
        checks.append(_check("Prefer sponsor-friendly companies (>=1)", sponsor >= 1,
                             f"{sponsor} jobs at known sponsor-friendly companies"))

    return checks


def build_persona_demo_resume(persona_key):
    """Optional, clearly-labeled GENERIC demo resume for a persona.

    This is NOT the project owner's resume and uses NO real candidate material.
    """
    p = PERSONAS[persona_key]
    lines = [
        "PERSONA DEMO RESUME (synthetic — not the project owner's resume)",
        "",
        p["persona_name"],
        "",
        "PROFILE",
        p["profile_text"],
        "",
        "SKILLS",
        " | ".join(p["skills"]),
        "",
        "TARGET ROLES",
        ", ".join(p["target_roles"]),
        "",
        "NOTE: Generated for recommendation-evaluation demonstration only.",
    ]
    return "\n".join(lines)
