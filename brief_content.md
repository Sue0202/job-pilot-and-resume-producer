# JobPilot: AI Resume Tailoring and Application Tracker
### BAX423 Big Data — Final Project Brief (Draft)

---

## 1. Problem Statement

Job seekers applying to operations and program-management roles must re-tailor their
resume for every posting: matching the right title angle, surfacing the most relevant
experience, and mirroring the language of each job description (JD). Doing this by hand
is slow, inconsistent, and error-prone, and it is easy to overstate or fabricate
experience under time pressure.

JobPilot addresses this with a lightweight, deterministic pipeline that ingests
structured job postings, matches each JD against a verified candidate profile, and
generates a tailored, truthful resume that always follows the candidate's real resume
structure — plus a simple tracker for managing applications.

---

## 2. Architecture

```
data/raw/job_raw.json (~1.3 GB)                 candidate_master_profile.md
        │  (offline, one-time, streamed)                    │
        ▼                                                   │
preprocess_jobs.py ──► data/processed/external_jobs_sample.csv
   (extract, clean,            │
    classify, filter,          ▼
    dedupe)            matching.py  ──►  ranked recommendations
                       (TF-IDF + keyword        │
                        coverage + feedback     ▼
                        bias)            resume_generator.py ──► docx_export.py
                              ▲                  (rule-based)       (styled DOCX)
                              │                        │                 │
                    database.py (SQLite:               ▼                 ▼
            resume_versions, applications,      TXT / DOCX download + top jobs CSV
                    job_feedback)
                              │
                    app.py (Streamlit UI, 5 pages)
```

Architecture: raw JSON external dataset → preprocessing → processed CSV →
ranking / recommendation app → resume generation → SQLite persistence.

- **Preprocessing:** `preprocess_jobs.py` (stdlib streaming JSON, no whole-file load).
- **Frontend / orchestration:** `app.py` (Streamlit, 5 pages).
- **Matching & ranking:** `matching.py` (keyword bank, role-family rules, TF-IDF,
  multi-job ranking, feedback bias).
- **Generation:** `resume_generator.py` (structured candidate material, rule-based).
- **Export:** `docx_export.py` (python-docx).
- **Persistence:** `database.py` (sqlite3: resume_versions, applications, job_feedback).
- **Data:** processed job CSVs (from `data/raw/job_raw.json`), `candidate_master_profile.md`.

---

## 3. BAX423 Big Data Techniques Used

- **Structured data ingestion:** a ~1.3 GB MongoDB-style JSON array is streamed
  line-by-line (one record per line) with the standard-library `json` module, plus
  structured CSV ingestion for processed jobs and for application records
  (`sample_applications.csv` or user-uploaded CSV) with required-column validation.
- **Data preprocessing pipeline:** `preprocess_jobs.py` extracts nested fields, strips
  HTML, normalizes whitespace, classifies role families, filters to relevant jobs,
  deduplicates by job_id/url, and emits compact processed CSVs for cheap app loads.
- **TF-IDF / vector similarity retrieval:** scikit-learn `TfidfVectorizer` + cosine
  similarity scores the candidate against many JDs at once and ranks them.
- **Multi-stage ranking:** TF-IDF similarity + controlled-keyword coverage combine into
  a base score, refined by feedback bias and surfaced as ranked recommendations.
- **Feedback-based adaptive ranking:** saved job feedback lightly boosts/penalizes role
  families and keywords on subsequent ranking runs (explainable, no ML training).
- **Rule-based NLP / keyword extraction:** regex cleaning, a controlled keyword bank,
  matched vs. missing keyword extraction, and role-family scoring rules.
- **Data pipeline:** end-to-end flow from raw JSON → preprocessing → processed CSV →
  ranking → generation → export → persistence, plus a second ingestion path for batch
  application records (CSV upload → validation → bulk SQLite insert).
- **SQLite persistence:** three tables (`resume_versions`, `applications`,
  `job_feedback`). Every generated resume version is persisted (with company, job
  title, target title, match score, feedback text, and full resume text) and is
  retrievable on the Generated Versions page. Application records support single and
  bulk inserts, status updates, summary metrics, and status filtering. Job feedback is
  stored and fed back into ranking.
- **DOCX generation:** programmatic, styled document creation with python-docx.
- **Deployed Streamlit app:** runnable locally and deployable on Streamlit Community
  Cloud.

---

## 4. Application Workflow

0. **Preprocess (one-time, offline)** — `python3 preprocess_jobs.py` turns the raw
   JSON dataset into compact processed CSVs.
1. **Candidate Profile** — user views/edits/uploads the master profile.
2. **Recommend** — user loads the processed dataset, filters by keyword / location /
   role family, and gets ranked job recommendations against the candidate profile.
3. **Review** — ranked table shows rank, score, role family, company, title, location,
   source, and matched/missing keywords; the top jobs can be downloaded as CSV.
4. **Select & Feedback** — user picks a job, inspects the JD, and can rate it; feedback
   adjusts future ranking.
5. **Generate** — a tailored resume is produced following the fixed structure.
6. **Refine** — user enters feedback and regenerates a new version.
7. **Export** — download DOCX or TXT.
8. **Persist** — save the version to SQLite (it then appears on Generated Versions).
9. **Track** — log applications manually or via batch CSV upload, monitor summary
   metrics, filter by status, and update status/notes in the tracker.

---

## 5. Test Results with Sample Jobs

Using the 10 sample postings, the matcher routes each JD to a sensible title angle:

| Sample Job | Expected Title Angle |
| --- | --- |
| Product Operations Intern | Product Operations & Program Management |
| Platform Operations Manager | Product Operations Manager \| Platform Operations |
| Customer Support Workflow Strategist | Workflow Strategist, Customer Support |
| Trust & Safety Operations Analyst | Workflow Strategist, Customer Support |
| Technical Producer | Technical Production & Live Service Operations |
| Release Manager | Technical Production & Live Service Operations |
| Business Operations Intern | Product Operations & Program Management |
| Creator Operations Program Manager | Product Operations & Program Management |
| Marketing Analytics Intern | Product Operations & Program Management (analytics coursework) |
| Live Operations Producer | Technical Production & Live Service Operations |

For each, the generated resume includes the four experience groups with bullets
selected by keyword overlap and role-family fit, and the match score reflects keyword
coverage and TF-IDF similarity. DOCX and TXT exports were verified to download.

> Note: replace this section with exact observed scores after a final test run.

---

## 6. Limitations

- Matching is keyword/TF-IDF based, not semantic; nuanced JDs may need manual title
  override via feedback.
- Resume generation uses structured candidate constants as the source of truth;
  free-text edits to `candidate_master_profile.md` adjust matching keywords but do not
  re-parse new bullets into generation.
- No external AI API, so phrasing is fixed to the verified bullet bank.
- On Streamlit Community Cloud the filesystem is ephemeral, so SQLite data resets on
  redeploy.
- The external dataset is an **offline historical snapshot**, not a live feed of
  currently-open jobs; recommendations reflect the snapshot, not real-time availability.
- Preprocessing stops once the relevant-row target (~3,000) is reached, so the
  processed sample is a bounded subset of the full raw dataset rather than an
  exhaustive extraction.

---

## 7. Future Work

- Optional LLM-assisted rephrasing (with strict no-fabrication guardrails).
- PDF export and user-provided DOCX template support.
- Semantic matching with embeddings / a vector store.
- Parsing edited markdown profiles directly into the generation engine.
- Persistent cloud database for multi-session tracking.

---

## 8. Links

- **Deployment URL:** _<add Streamlit Community Cloud URL here>_
- **GitHub URL:** _<add GitHub repository URL here>_
