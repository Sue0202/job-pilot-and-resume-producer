"""Batch analytics over the processed job dataset (pandas only).

Computes aggregate insights for the Batch Analytics page: role-family and source
distributions, top locations/companies, keyword demand, employment types, a
missing-data audit, and an optional salary summary.
"""

import re

import pandas as pd

import matching


def _safe_series(df, col):
    if col not in df.columns:
        return pd.Series(dtype=str)
    return df[col].fillna("").astype(str)


def _missing_pct(df, col):
    if col not in df.columns or len(df) == 0:
        return 100.0 if len(df) else 0.0
    s = df[col].fillna("").astype(str).str.strip()
    return round(100.0 * (s == "").mean(), 1)


def _keyword_frequencies(df, top=20):
    """Count, per controlled keyword, how many descriptions contain it."""
    desc = _safe_series(df, "description").str.lower()
    counts = {}
    for kw in matching.KEYWORD_BANK:
        counts[kw] = int(desc.str.contains(re.escape(kw), regex=True).sum())
    series = pd.Series(counts).sort_values(ascending=False)
    series = series[series > 0]
    return series.head(top)


def _salary_summary(df):
    """Return basic stats only if salary data exists and is numeric-parseable."""
    if "salary" not in df.columns:
        return None
    raw = df["salary"].fillna("").astype(str)
    nums = pd.to_numeric(raw.str.replace(r"[^0-9.]", "", regex=True), errors="coerce")
    nums = nums.dropna()
    nums = nums[nums > 0]
    if len(nums) == 0:
        return None
    return {
        "count_with_salary": int(len(nums)),
        "min": float(nums.min()),
        "median": float(nums.median()),
        "max": float(nums.max()),
    }


def compute_batch_analytics(jobs_df, top=20):
    """Return a dict of aggregate analytics for the given jobs DataFrame."""
    df = jobs_df.fillna("") if jobs_df is not None else pd.DataFrame()
    total = len(df)

    def _vc(col, n):
        s = _safe_series(df, col).str.strip()
        s = s[s != ""]
        return s.value_counts().head(n)

    return {
        "total_jobs": total,
        "by_role_family": _vc("role_family", 50),
        "top_locations": _vc("location", top),
        "top_companies": _vc("company", top),
        "keyword_frequencies": _keyword_frequencies(df, top),
        "source_distribution": _vc("source", top),
        "employment_type_distribution": _vc("employment_type", top),
        "missing": {
            "salary_pct": _missing_pct(df, "salary"),
            "job_url_pct": _missing_pct(df, "job_url"),
            "location_pct": _missing_pct(df, "location"),
        },
        "salary_summary": _salary_summary(df),
    }


def analytics_to_csv(analytics):
    """Flatten the analytics dict into a long-format summary DataFrame for export."""
    rows = []
    rows.append({"section": "summary", "key": "total_jobs", "value": analytics["total_jobs"]})

    for section_key in [
        "by_role_family",
        "top_locations",
        "top_companies",
        "keyword_frequencies",
        "source_distribution",
        "employment_type_distribution",
    ]:
        series = analytics.get(section_key)
        if series is not None:
            for key, value in series.items():
                rows.append({"section": section_key, "key": key, "value": int(value)})

    for key, value in analytics.get("missing", {}).items():
        rows.append({"section": "missing_data_pct", "key": key, "value": value})

    salary = analytics.get("salary_summary")
    if salary:
        for key, value in salary.items():
            rows.append({"section": "salary_summary", "key": key, "value": value})

    return pd.DataFrame(rows, columns=["section", "key", "value"])
