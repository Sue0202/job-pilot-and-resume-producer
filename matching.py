"""Job-to-candidate matching for JobPilot.

Combines a controlled keyword bank, simple role-family scoring rules, and
TF-IDF cosine similarity to:
  - score how well a JD fits the candidate,
  - pick the best target title / profile angle,
  - surface matched vs. missing keywords,
  - select the most relevant candidate facts.

Kept intentionally simple and stable for the MVP.
"""

import re

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

import resume_generator as rg

# Controlled keyword bank (multi-word phrases supported).
KEYWORD_BANK = [
    "product operations",
    "program management",
    "business operations",
    "creator operations",
    "content operations",
    "platform operations",
    "workflow design",
    "sop",
    "launch readiness",
    "incident response",
    "support escalation",
    "customer support",
    "trust and safety",
    "cx operations",
    "technical producer",
    "release manager",
    "release management",
    "live operations",
    "game operations",
    "technical production",
    "sql",
    "eda",
    "analytics",
    "data visualization",
    "stakeholder management",
    "cross-functional",
    "user feedback",
    "product requirements",
    "risk management",
    "rca",
    "compliance",
    "sdk",
    "store submission",
    "monitoring",
    "alerting",
]

# Role-family scoring terms.
ROLE_FAMILY_TERMS = {
    "product_program": [
        "product operations",
        "program manager",
        "program management",
        "business operations",
        "creator",
        "content",
        "user feedback",
        "workflow",
        "sop",
        "cross-functional",
    ],
    "workflow_support": [
        "customer support",
        "support escalation",
        "incident response",
        "trust and safety",
        "cx",
        "rca",
        "support workflow",
        "workflow strategist",
    ],
    "platform_ops": [
        "platform operations",
        "platform program",
        "operations manager",
        "risk controls",
        "risk management",
        "approval",
        "permissions",
        "monitoring",
        "alerting",
        "sdk",
        "platform requirements",
    ],
    "technical_production": [
        "technical producer",
        "release manager",
        "release producer",
        "release management",
        "live ops",
        "live operations",
        "game ops",
        "game operations",
        "release cadence",
        "launch readiness",
        "hotfix",
        "release execution",
        "technical production",
        "producer",
    ],
}

FAMILY_TO_ANGLE = {
    "product_program": "A",
    "workflow_support": "B",
    "platform_ops": "C",
    "technical_production": "D",
}

# Keyword groups used to classify a job into a display role_family (matches the
# labels produced by preprocess_jobs.py). Used as a fallback when a job dataset
# does not already include a role_family column.
ROLE_FAMILY_GROUPS = {
    "Product Operations / Program": [
        "product operations", "product ops", "program manager", "program management",
        "business operations", "business ops", "creator operations",
        "content operations", "product coordinator", "product specialist",
    ],
    "Platform Operations": [
        "platform operations", "platform program", "platform manager",
        "platform support", "platform workflow", "sdk", "integration",
        "monitoring", "alerting", "compliance", "risk control", "operations manager",
    ],
    "Workflow / Support Operations": [
        "customer support", "support operations", "support escalation",
        "customer experience", "cx operations", "trust and safety",
        "incident response", "rca", "workflow", "help center", "support analyst",
    ],
    "Technical Production / Live Operations": [
        "technical producer", "release manager", "release producer",
        "live operations", "live ops", "game operations", "game producer",
        "production coordinator", "launch readiness", "release management",
        "release execution",
    ],
    "Analytics / Business Operations": [
        "marketing analytics", "business analytics", "operations analyst",
        "data analyst", "sql", "reporting", "dashboard", "data visualization",
        "eda", "metric", "performance analysis",
    ],
}


def classify_role_family(job_title, description):
    """Classify a job into a display role_family (title-weighted), or 'Other'."""
    title = (job_title or "").lower()
    desc = (description or "").lower()
    best_family, best_score = "Other", 0
    for family, keywords in ROLE_FAMILY_GROUPS.items():
        score = 0
        for kw in keywords:
            if kw in title:
                score += 3
            elif kw in desc:
                score += 1
        if score > best_score:
            best_score, best_family = score, family
    return best_family

FAMILY_TO_TITLE = {fam: rg.ROLE_FAMILIES[fam]["title"] for fam in rg.ROLE_FAMILIES}


def _clean(text):
    text = (text or "").lower()
    text = re.sub(r"[^a-z0-9\s\-&]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _build_jd_text(job_row):
    parts = [
        job_row.get("job_title", ""),
        job_row.get("company", ""),
        job_row.get("description", ""),
        job_row.get("responsibilities", ""),
        job_row.get("qualifications", ""),
    ]
    return _clean(" ".join(str(p) for p in parts))


def _score_role_families(jd_text):
    scores = {}
    for family, terms in ROLE_FAMILY_TERMS.items():
        scores[family] = sum(1 for t in terms if t in jd_text)
    return scores


def _top_relevant_facts(jd_text, top_n=6):
    facts = rg.get_all_facts()
    cleaned_facts = [_clean(f) for f in facts]
    try:
        vec = TfidfVectorizer(stop_words="english")
        matrix = vec.fit_transform([jd_text] + cleaned_facts)
        sims = cosine_similarity(matrix[0:1], matrix[1:]).flatten()
        ranked = sorted(zip(sims, facts), key=lambda x: x[0], reverse=True)
        return [fact for sim, fact in ranked[:top_n] if sim > 0]
    except ValueError:
        return facts[:top_n]


def _overall_similarity(jd_text, candidate_text):
    try:
        vec = TfidfVectorizer(stop_words="english")
        matrix = vec.fit_transform([jd_text, candidate_text])
        return float(cosine_similarity(matrix[0:1], matrix[1:2])[0][0])
    except ValueError:
        return 0.0


def match_job_to_candidate(candidate_profile, job_row):
    """Return a match_result dict for the given job row."""
    jd_text = _build_jd_text(job_row)
    candidate_text = _clean(candidate_profile or "") + " " + _clean(" ".join(rg.get_all_facts()))

    # Keyword coverage: which bank terms appear in the JD, and of those, which
    # the candidate material already covers (matched) vs. does not (missing).
    jd_terms = [kw for kw in KEYWORD_BANK if kw in jd_text]
    matched_keywords = [kw for kw in jd_terms if kw in candidate_text]
    missing_keywords = [kw for kw in jd_terms if kw not in candidate_text]

    coverage = (len(matched_keywords) / len(jd_terms)) if jd_terms else 0.0
    cosine = _overall_similarity(jd_text, candidate_text)
    match_score = round(100 * (0.5 * cosine + 0.5 * coverage), 1)

    role_family_scores = _score_role_families(jd_text)
    if any(role_family_scores.values()):
        selected_family = max(role_family_scores, key=lambda f: (role_family_scores[f], f))
    else:
        selected_family = "product_program"

    selected_title_option = FAMILY_TO_TITLE[selected_family]
    selected_profile_angle = FAMILY_TO_ANGLE[selected_family]
    selected_expertise_keywords = rg.PROFILES[selected_profile_angle]["expertise"]

    top_relevant_facts = _top_relevant_facts(jd_text)

    return {
        "match_score": match_score,
        "matched_keywords": matched_keywords,
        "missing_keywords": missing_keywords,
        "selected_title_option": selected_title_option,
        "selected_profile_angle": selected_profile_angle,
        "selected_expertise_keywords": selected_expertise_keywords,
        "selected_experience_groups": list(rg.GROUP_ORDER),
        "top_relevant_facts": top_relevant_facts,
        "role_family_scores": role_family_scores,
        "selected_role_family": selected_family,
    }


def _tokens(text):
    return set(re.findall(r"[a-z0-9]+", (text or "").lower()))


def compute_feedback_bias(feedback_rows):
    """Turn saved job feedback into a light, explainable ranking adjustment.

    Returns (family_bias, liked_tokens, disliked_tokens):
      - family_bias: dict role_family -> signed weight
      - liked_tokens / disliked_tokens: token sets from job titles
    """
    family_bias = {}
    liked_tokens = set()
    disliked_tokens = set()
    for fb in feedback_rows or []:
        fam = fb.get("role_family") or ""
        verdict = (fb.get("feedback") or "").strip().lower()
        title_tokens = _tokens(fb.get("job_title", ""))
        if verdict == "good match":
            family_bias[fam] = family_bias.get(fam, 0) + 2
            liked_tokens |= title_tokens
        elif verdict == "interested":
            family_bias[fam] = family_bias.get(fam, 0) + 1
            liked_tokens |= title_tokens
        elif verdict in ("not interested", "too senior"):
            family_bias[fam] = family_bias.get(fam, 0) - 1
            disliked_tokens |= title_tokens
        # "wrong location" is location-specific and does not bias role families.
    return family_bias, liked_tokens, disliked_tokens


def rank_jobs(candidate_profile, jobs, feedback_rows=None, top_n=25):
    """Rank many jobs against the candidate using TF-IDF + keyword coverage,
    lightly adjusted by saved feedback. `jobs` is a list of dicts (job rows).

    Returns a list of result dicts (length <= top_n), each including rank,
    match_score, role_family, matched/missing keywords, and the full job row.
    """
    rows = list(jobs)
    if not rows:
        return []

    candidate_text = _clean(candidate_profile or "") + " " + _clean(" ".join(rg.get_all_facts()))
    jd_texts = [_build_jd_text(row) for row in rows]

    # Single TF-IDF fit over candidate + all JDs for efficient cosine scores.
    try:
        vec = TfidfVectorizer(stop_words="english")
        matrix = vec.fit_transform([candidate_text] + jd_texts)
        sims = cosine_similarity(matrix[0:1], matrix[1:]).flatten()
    except ValueError:
        sims = [0.0] * len(rows)

    family_bias, liked_tokens, disliked_tokens = compute_feedback_bias(feedback_rows)

    results = []
    for i, row in enumerate(rows):
        jd = jd_texts[i]
        jd_terms = [kw for kw in KEYWORD_BANK if kw in jd]
        matched = [kw for kw in jd_terms if kw in candidate_text]
        missing = [kw for kw in jd_terms if kw not in candidate_text]
        coverage = (len(matched) / len(jd_terms)) if jd_terms else 0.0
        base = 100 * (0.5 * float(sims[i]) + 0.5 * coverage)

        role_family = row.get("role_family") or classify_role_family(
            row.get("job_title", ""), row.get("description", "")
        )
        title_tokens = _tokens(row.get("job_title", ""))
        bias = family_bias.get(role_family, 0)
        like_bonus = len(title_tokens & liked_tokens)
        dislike_pen = len(title_tokens & disliked_tokens)

        score = base + bias * 3 + like_bonus * 1.0 - dislike_pen * 1.0
        score = max(0.0, min(100.0, score))

        results.append(
            {
                "match_score": round(score, 1),
                "role_family": role_family,
                "matched_keywords": matched,
                "missing_keywords": missing,
                "job_row": row,
            }
        )

    results.sort(key=lambda r: r["match_score"], reverse=True)
    results = results[:top_n]
    for rank, r in enumerate(results, start=1):
        r["rank"] = rank
    return results
