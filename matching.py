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
import time

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

import resume_generator as rg

# ---------------------------------------------------------------------------
# Optional dense-embedding backend (sentence-transformers).
# Everything degrades gracefully to TF-IDF if the package or model is missing.
# ---------------------------------------------------------------------------

DENSE_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
_DENSE_MODEL = None
_DENSE_DISABLED = False  # set True after a failed load so we don't retry every call

DENSE_TEXT_COLUMNS = [
    "job_title",
    "company",
    "location",
    "description",
    "responsibilities",
    "qualifications",
    "role_family",
]


def _get_model():
    """Lazily load the sentence-transformers model. Returns None if unavailable."""
    global _DENSE_MODEL, _DENSE_DISABLED
    if _DENSE_MODEL is not None:
        return _DENSE_MODEL
    if _DENSE_DISABLED:
        return None
    try:
        from sentence_transformers import SentenceTransformer

        _DENSE_MODEL = SentenceTransformer(DENSE_MODEL_NAME)
        return _DENSE_MODEL
    except Exception:
        # Package not installed, offline, or model download failed.
        _DENSE_DISABLED = True
        return None


def dense_backend_available():
    """True if the dense embedding model can be loaded."""
    return _get_model() is not None


def embed_texts(texts):
    """Encode a list of texts into L2-normalized vectors, or None on failure."""
    model = _get_model()
    if model is None:
        return None
    try:
        return model.encode(
            list(texts),
            normalize_embeddings=True,
            show_progress_bar=False,
        )
    except Exception:
        return None


def _combined_job_text(row):
    return " ".join(str(row.get(c, "")) for c in DENSE_TEXT_COLUMNS)


def _combined_candidate_text(candidate_profile, include_candidate_facts=True):
    text = candidate_profile or ""
    if include_candidate_facts:
        text = text + " " + " ".join(rg.get_all_facts())
    return text


def build_embedding_index(jobs_df, text_col="combined_text", max_rows=None):
    """Build a dense embedding index for a jobs DataFrame.

    Returns {"by_id": {job_id: vector}} (vectors L2-normalized) or None if the
    dense backend is unavailable. `text_col` is accepted for API clarity; the
    combined text is derived from the standard job columns.
    """
    if jobs_df is None or len(jobs_df) == 0:
        return None
    df = jobs_df.head(max_rows) if max_rows else jobs_df
    rows = df.to_dict("records")
    texts = [_combined_job_text(r) for r in rows]
    vectors = embed_texts(texts)
    if vectors is None:
        return None
    by_id = {}
    for r, vec in zip(rows, vectors):
        by_id[str(r.get("job_id", ""))] = np.asarray(vec, dtype=float)
    return {"by_id": by_id}

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


def _tfidf_sims(candidate_text, jd_texts):
    """Cosine similarity of candidate vs each JD via a single TF-IDF fit."""
    try:
        vec = TfidfVectorizer(stop_words="english")
        matrix = vec.fit_transform([candidate_text] + jd_texts)
        return cosine_similarity(matrix[0:1], matrix[1:]).flatten()
    except ValueError:
        return np.zeros(len(jd_texts))


def _dense_sims(candidate_profile, rows, dense_index=None, include_candidate_facts=True):
    """Dense cosine similarity of candidate vs each row. Returns array or None.

    Uses a precomputed `dense_index` ({"by_id": {job_id: vec}}) when available,
    falling back to encoding individual rows. Returns None if the dense backend
    is unavailable.
    """
    cand = embed_texts([_combined_candidate_text(candidate_profile, include_candidate_facts)])
    if cand is None:
        return None
    cand_vec = np.asarray(cand[0], dtype=float)

    by_id = (dense_index or {}).get("by_id") if dense_index else None
    if by_id is None:
        built = build_embedding_index(_rows_to_df(rows))
        if built is None:
            return None
        by_id = built["by_id"]

    sims = []
    missing_rows = []
    for row in rows:
        vec = by_id.get(str(row.get("job_id", "")))
        if vec is None:
            missing_rows.append(row)
            sims.append(None)
        else:
            sims.append(float(np.dot(cand_vec, vec)))

    # Encode any rows not present in the index (e.g., fallback dataset).
    if missing_rows:
        extra = embed_texts([_combined_job_text(r) for r in missing_rows])
        if extra is not None:
            it = iter(extra)
            for idx, row in enumerate(rows):
                if sims[idx] is None:
                    sims[idx] = float(np.dot(cand_vec, np.asarray(next(it), dtype=float)))
    sims = [0.0 if s is None else max(0.0, s) for s in sims]
    return np.array(sims)


def _rows_to_df(rows):
    import pandas as pd

    return pd.DataFrame(list(rows))


def rank_jobs(
    candidate_profile,
    jobs,
    feedback_rows=None,
    top_n=25,
    method="tfidf",
    dense_index=None,
    include_candidate_facts=True,
):
    """Rank many jobs against the candidate. `jobs` is a list of dicts.

    method:
      - "tfidf"  : TF-IDF cosine + keyword coverage (baseline / fallback)
      - "dense"  : dense embedding cosine (sentence-transformers)
      - "hybrid" : 0.50*dense + 0.30*tfidf + 0.20*keyword_coverage

    Feedback bias is always added on top. If dense is requested but the backend
    is unavailable, ranking transparently falls back to TF-IDF and each result is
    tagged with method_used="tfidf (fallback)".

    Each result dict includes per-component scores (dense_score, tfidf_score,
    coverage_score on a 0–100 scale, feedback_adjustment) for the explain view.
    """
    rows = list(jobs)
    if not rows:
        return []

    candidate_text = _clean(_combined_candidate_text(candidate_profile, include_candidate_facts))
    jd_texts = [_build_jd_text(row) for row in rows]

    tfidf_sims = _tfidf_sims(candidate_text, jd_texts)

    method_used = method
    dense_sims = None
    if method in ("dense", "hybrid"):
        dense_sims = _dense_sims(
            candidate_profile, rows, dense_index, include_candidate_facts
        )
        if dense_sims is None:
            method_used = "tfidf (fallback)"
            method = "tfidf"

    family_bias, liked_tokens, disliked_tokens = compute_feedback_bias(feedback_rows)

    results = []
    for i, row in enumerate(rows):
        jd = jd_texts[i]
        jd_terms = [kw for kw in KEYWORD_BANK if kw in jd]
        matched = [kw for kw in jd_terms if kw in candidate_text]
        missing = [kw for kw in jd_terms if kw not in candidate_text]
        coverage = (len(matched) / len(jd_terms)) if jd_terms else 0.0

        tfidf_score = float(tfidf_sims[i])
        dense_score = float(dense_sims[i]) if dense_sims is not None else None

        if method == "dense":
            base = 100 * dense_score
        elif method == "hybrid":
            base = 100 * (0.50 * dense_score + 0.30 * tfidf_score + 0.20 * coverage)
        else:  # tfidf
            base = 100 * (0.5 * tfidf_score + 0.5 * coverage)

        role_family = row.get("role_family") or classify_role_family(
            row.get("job_title", ""), row.get("description", "")
        )
        title_tokens = _tokens(row.get("job_title", ""))
        bias = family_bias.get(role_family, 0)
        like_bonus = len(title_tokens & liked_tokens)
        dislike_pen = len(title_tokens & disliked_tokens)
        feedback_adjustment = bias * 3 + like_bonus * 1.0 - dislike_pen * 1.0

        score = max(0.0, min(100.0, base + feedback_adjustment))

        results.append(
            {
                "match_score": round(score, 1),
                "role_family": role_family,
                "matched_keywords": matched,
                "missing_keywords": missing,
                "tfidf_score": round(100 * tfidf_score, 1),
                "dense_score": round(100 * dense_score, 1) if dense_score is not None else None,
                "coverage_score": round(100 * coverage, 1),
                "feedback_adjustment": round(feedback_adjustment, 1),
                "method_used": method_used,
                "job_row": row,
            }
        )

    results.sort(key=lambda r: r["match_score"], reverse=True)
    results = results[:top_n]
    for rank, r in enumerate(results, start=1):
        r["rank"] = rank
    return results


def rank_jobs_dense(profile_text, jobs_df, top_n=50):
    """Convenience dense-only ranking over a jobs DataFrame (or list of dicts).

    Returns a ranked list of result dicts, or an empty list if the dense backend
    is unavailable.
    """
    rows = jobs_df.to_dict("records") if hasattr(jobs_df, "to_dict") else list(jobs_df)
    if not dense_backend_available():
        return []
    return rank_jobs(profile_text, rows, top_n=top_n, method="dense")


def evaluate_ranking_methods(candidate_profile, jobs_df, sample_rows=400, dense_index=None):
    """Benchmark TF-IDF vs dense vs hybrid ranking on a sample of jobs.

    Returns a dict with top-10 keyword coverage, runtime, and TF-IDF/dense
    top-10 overlap. Safe to call even when the dense backend is unavailable.
    """
    rows = jobs_df.to_dict("records") if hasattr(jobs_df, "to_dict") else list(jobs_df)
    if sample_rows:
        rows = rows[:sample_rows]

    out = {"dense_available": dense_backend_available(), "sample_rows": len(rows)}
    ranked_by_method = {}
    for method in ("tfidf", "dense", "hybrid"):
        t0 = time.time()
        ranked = rank_jobs(
            candidate_profile, rows, feedback_rows=None, top_n=10,
            method=method, dense_index=dense_index,
        )
        out[f"{method}_runtime_sec"] = round(time.time() - t0, 3)
        ranked_by_method[method] = ranked
        covs = []
        for r in ranked:
            total = len(r["matched_keywords"]) + len(r["missing_keywords"])
            covs.append((len(r["matched_keywords"]) / total) if total else 0.0)
        out[f"{method}_avg_keyword_coverage_top10"] = round(sum(covs) / len(covs), 3) if covs else 0.0

    tids = {r["job_row"].get("job_id") for r in ranked_by_method["tfidf"]}
    dids = {r["job_row"].get("job_id") for r in ranked_by_method["dense"]}
    out["top_10_overlap_tfidf_dense"] = len(tids & dids)
    return out
