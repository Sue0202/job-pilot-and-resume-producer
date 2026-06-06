"""Offline preprocessing for the large external job dataset.

Reads the raw MongoDB-style JSON array (data/raw/job_raw.json) ONCE, extracts and
normalizes useful fields, filters to relevant job families, removes duplicates, and
writes two smaller CSVs the Streamlit app can load cheaply:

    data/processed/external_jobs_sample.csv     (up to TARGET_ROWS relevant jobs)
    data/processed/external_jobs_demo_200.csv   (up to 200 rows for fast testing)
    data/processed/external_jobs_20k_sample.csv (up to 20,000 structured jobs, not
                                                 relevance-filtered — submission sample)

The raw file is ~1.3 GB. It is a JSON array with one complete record per physical
line, so we stream it line-by-line with the standard library `json` module — the
whole file is never loaded into memory and no extra dependencies are required.

Usage:
    python3 preprocess_jobs.py

Optional environment variables:
    JOBPILOT_MAX_SCAN   stop after scanning this many raw records (for quick tests)
    JOBPILOT_TARGET     max number of relevant rows to keep (default 3000)
"""

import csv
import json
import os
import re
import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent
RAW_PATH = BASE_DIR / "data" / "raw" / "job_raw.json"
PROCESSED_DIR = BASE_DIR / "data" / "processed"
SAMPLE_PATH = PROCESSED_DIR / "external_jobs_sample.csv"
DEMO_PATH = PROCESSED_DIR / "external_jobs_demo_200.csv"
LARGE_PATH = PROCESSED_DIR / "external_jobs_20k_sample.csv"

TARGET_ROWS = int(os.environ.get("JOBPILOT_TARGET", "3000"))
DEMO_ROWS = 200
# Larger, general (not relevance-filtered) structured sample for submission evidence.
GENERAL_TARGET = int(os.environ.get("JOBPILOT_GENERAL_TARGET", "20000"))
MAX_SCAN = int(os.environ.get("JOBPILOT_MAX_SCAN", "0")) or None  # None = unlimited
PROGRESS_EVERY = 5000
DESCRIPTION_MAX_CHARS = 2000

CSV_COLUMNS = [
    "job_id",
    "company",
    "job_title",
    "location",
    "job_url",
    "description",
    "responsibilities",
    "qualifications",
    "salary",
    "source",
    "source_country",
    "date_posted",
    "employment_type",
    "category",
    "role_family",
]

# Relevant keyword groups. A job is kept if its title+description matches at least
# one keyword from any group. The group with the strongest (title-weighted) match
# becomes the role_family.
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

_HTML_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


# ---------------------------------------------------------------------------
# Safe helpers
# ---------------------------------------------------------------------------

def get(d, *keys, default=""):
    """Safely walk nested dicts; return default on any missing/None step."""
    cur = d
    for k in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(k)
        if cur is None:
            return default
    return cur if cur is not None else default


def strip_html(text):
    if not isinstance(text, str):
        return ""
    return _HTML_TAG_RE.sub(" ", text)


def normalize_ws(text):
    if not isinstance(text, str):
        return ""
    return _WS_RE.sub(" ", text).strip()


def join_list(value, sep=" | "):
    """Join a list, dropping None/empty values. Pass through strings."""
    if isinstance(value, list):
        parts = [str(v).strip() for v in value if v not in (None, "", [])]
        return sep.join(parts)
    if value in (None, ""):
        return ""
    return str(value)


# ---------------------------------------------------------------------------
# Field extraction
# ---------------------------------------------------------------------------

def extract_record(rec, fallback_index):
    j = rec.get("json") or {}
    so = j.get("schemaOrg") or {} if isinstance(j, dict) else {}

    job_id = (
        rec.get("idInSource")
        or get(rec, "_id", "$oid")
        or f"row_{fallback_index}"
    )

    company = (
        get(so, "hiringOrganization", "name")
        or get(rec, "orgCompany", "name")
        or get(rec, "orgCompany", "nameOrg")
        or ""
    )

    job_title = (
        so.get("title")
        or rec.get("name")
        or get(rec, "position", "name")
        or ""
    )

    location = get(rec, "orgAddress", "addressLine")
    if not location:
        locality = get(so, "jobLocation", "address", "addressLocality")
        region = get(so, "jobLocation", "address", "addressRegion")
        location = ", ".join([p for p in [locality, region] if p])

    job_url = so.get("url") or rec.get("url") or ""

    # Description: prefer the already-clean `text`; else strip HTML from schemaOrg
    # description or raw html.
    description = rec.get("text") or ""
    if not description:
        description = strip_html(so.get("description") or rec.get("html") or "")
    description = normalize_ws(description)[:DESCRIPTION_MAX_CHARS]

    salary = ""

    source = rec.get("source") or ""
    source_country = rec.get("sourceCC") or ""

    date_posted = so.get("datePosted") or get(rec, "dateCreated", "$date") or ""

    employment_type = (
        join_list(so.get("employmentType"))
        or get(rec, "position", "workType")
        or ""
    )

    category = join_list(get(rec, "orgTags", "CATEGORIES", default=[]))

    return {
        "job_id": str(job_id),
        "company": normalize_ws(str(company)),
        "job_title": normalize_ws(str(job_title)),
        "location": normalize_ws(str(location)),
        "job_url": str(job_url).strip(),
        "description": description,
        "responsibilities": "",  # blank for MVP (kept simple, not over-engineered)
        "qualifications": "",     # blank for MVP
        "salary": salary,
        "source": str(source).strip(),
        "source_country": str(source_country).strip(),
        "date_posted": str(date_posted).strip(),
        "employment_type": normalize_ws(str(employment_type)),
        "category": normalize_ws(str(category)),
        "role_family": "Other",
    }


def classify_and_filter(row):
    """Return role_family if the row matches a relevant group, else None."""
    title = (row.get("job_title") or "").lower()
    desc = (row.get("description") or "").lower()
    best_family = None
    best_score = 0
    for family, keywords in ROLE_FAMILY_GROUPS.items():
        score = 0
        for kw in keywords:
            if kw in title:
                score += 3
            elif kw in desc:
                score += 1
        if score > best_score:
            best_score = score
            best_family = family
    return best_family if best_score > 0 else None


# ---------------------------------------------------------------------------
# Streaming raw reader (one JSON object per line)
# ---------------------------------------------------------------------------

def iter_raw_records(path):
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line in ("[", "]"):
                continue
            if line.endswith(","):
                line = line[:-1]
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for r in rows:
            writer.writerow(r)


def simulate_streaming_ingestion(input_path, output_path, batch_size=5000, max_records=None):
    """Stream-style batch ingestion over the large external JSON snapshot.

    Reads records incrementally (never loading the whole file), processes them in
    fixed-size batches, normalizes and deduplicates each batch, and appends valid
    rows to the output CSV as it goes. This simulates a streaming-style pipeline
    suitable for MVP constraints; it is NOT real-time production streaming.

    Returns a summary dict: raw_records, valid_records, duplicates_removed,
    rows_written.
    """
    input_path = Path(input_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    seen_ids = set()
    seen_urls = set()
    raw_records = 0
    valid_records = 0
    duplicates = 0
    rows_written = 0

    def _process_batch(batch, writer):
        nonlocal valid_records, duplicates, rows_written
        for rec in batch:
            try:
                row = extract_record(rec, raw_records)
            except Exception:
                continue
            if not row["job_title"] or not row["description"]:
                continue
            if row["job_id"] in seen_ids:
                duplicates += 1
                continue
            if row["job_url"] and row["job_url"] in seen_urls:
                duplicates += 1
                continue
            seen_ids.add(row["job_id"])
            if row["job_url"]:
                seen_urls.add(row["job_url"])
            row["role_family"] = classify_and_filter(row) or "Other"
            valid_records += 1
            writer.writerow(row)
            rows_written += 1

    print(f"Stream-style batch ingestion: {input_path} -> {output_path} (batch={batch_size})")
    with open(output_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        batch = []
        for rec in iter_raw_records(input_path):
            raw_records += 1
            if max_records and raw_records > max_records:
                raw_records -= 1
                break
            batch.append(rec)
            if len(batch) >= batch_size:
                _process_batch(batch, writer)
                batch = []
                print(
                    f"  batch flushed | raw={raw_records:,} valid={valid_records:,} "
                    f"dups={duplicates:,} written={rows_written:,}"
                )
        if batch:
            _process_batch(batch, writer)

    summary = {
        "raw_records": raw_records,
        "valid_records": valid_records,
        "duplicates_removed": duplicates,
        "rows_written": rows_written,
        "output_path": str(output_path),
    }
    print(
        f"\nStreaming summary: raw={raw_records:,} valid={valid_records:,} "
        f"duplicates={duplicates:,} written={rows_written:,} -> {output_path}"
    )
    return summary


def main():
    if not RAW_PATH.exists():
        print(f"ERROR: raw file not found at {RAW_PATH}")
        print("Place the raw dataset at data/raw/job_raw.json and re-run.")
        sys.exit(1)

    print(f"Reading raw dataset: {RAW_PATH}")
    print(
        f"Targets: relevant={TARGET_ROWS} general(20k sample)={GENERAL_TARGET}"
        + (f" | max scan: {MAX_SCAN}" if MAX_SCAN else "")
    )

    # `general` holds up to GENERAL_TARGET valid structured jobs (any role_family,
    # including 'Other'). `relevant` is the subset passing the relevance filter,
    # capped at TARGET_ROWS and used by the app. Dedupe is shared so a unique job
    # appears at most once in each file.
    general = []
    relevant = []
    seen_ids = set()
    seen_urls = set()
    scanned = 0
    skipped_missing = 0
    duplicates = 0

    for rec in iter_raw_records(RAW_PATH):
        scanned += 1
        if MAX_SCAN and scanned > MAX_SCAN:
            break
        if scanned % PROGRESS_EVERY == 0:
            print(f"  scanned {scanned:,} | general {len(general):,} | relevant {len(relevant):,}")

        try:
            row = extract_record(rec, scanned)
        except Exception:
            continue

        # Require a title and a description.
        if not row["job_title"] or not row["description"]:
            skipped_missing += 1
            continue

        # Dedupe by job_id, then by job_url.
        if row["job_id"] in seen_ids:
            duplicates += 1
            continue
        if row["job_url"] and row["job_url"] in seen_urls:
            duplicates += 1
            continue
        seen_ids.add(row["job_id"])
        if row["job_url"]:
            seen_urls.add(row["job_url"])

        # Classify role_family for everything; relevance is whether it matched a group.
        family = classify_and_filter(row)
        row["role_family"] = family or "Other"

        if len(general) < GENERAL_TARGET:
            general.append(row)
        if family and len(relevant) < TARGET_ROWS:
            relevant.append(row)

        # Stop once both targets are satisfied.
        if len(general) >= GENERAL_TARGET and len(relevant) >= TARGET_ROWS:
            print(f"  reached both targets; stopping scan.")
            break

    print(
        f"\nDone scanning. scanned={scanned:,} general={len(general):,} "
        f"relevant={len(relevant):,} skipped_missing={skipped_missing:,} "
        f"duplicates={duplicates:,}"
    )

    if not relevant:
        print("WARNING: no relevant rows found. Writing relevant headers only.")

    write_csv(SAMPLE_PATH, relevant)
    write_csv(DEMO_PATH, relevant[:DEMO_ROWS])
    write_csv(LARGE_PATH, general)

    print(f"Wrote {len(relevant):,} rows -> {SAMPLE_PATH}")
    print(f"Wrote {min(len(relevant), DEMO_ROWS):,} rows -> {DEMO_PATH}")
    print(f"Wrote {len(general):,} rows -> {LARGE_PATH}")

    def _print_dist(label, rows):
        dist = {}
        for r in rows:
            dist[r["role_family"]] = dist.get(r["role_family"], 0) + 1
        if dist:
            print(f"\nRole family distribution ({label}):")
            for fam, n in sorted(dist.items(), key=lambda x: -x[1]):
                print(f"  {fam}: {n}")

    _print_dist("relevant app dataset", relevant)
    _print_dist("20k general sample", general)


if __name__ == "__main__":
    # `python3 preprocess_jobs.py` builds the processed datasets.
    # `python3 preprocess_jobs.py stream` runs the stream-style batch ingestion demo.
    if len(sys.argv) > 1 and sys.argv[1] == "stream":
        demo_max = int(os.environ.get("JOBPILOT_STREAM_MAX", "20000"))
        simulate_streaming_ingestion(
            RAW_PATH,
            PROCESSED_DIR / "stream_ingestion_output.csv",
            batch_size=5000,
            max_records=demo_max,
        )
    else:
        main()
