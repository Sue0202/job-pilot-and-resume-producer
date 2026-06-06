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
                    app.py (Streamlit UI, 7 pages)
```

Architecture: raw JSON external dataset → preprocessing → processed CSV →
ranking / recommendation app → resume generation → SQLite persistence.

- **Preprocessing:** `preprocess_jobs.py` (stdlib streaming JSON, no whole-file load).
- **Frontend / orchestration:** `app.py` (Streamlit, 7 pages: Candidate Profile, Job
  Matching, Generated Versions, Application Tracker, Batch Analytics, Test Personas,
  Project README).
- **Matching & ranking:** `matching.py` (keyword bank, role-family rules, TF-IDF, optional
  dense embeddings, hybrid ranking, benchmark, multi-job ranking, feedback bias).
- **Analytics:** `analytics.py` (aggregate batch insights over the processed dataset).
- **Persona evaluation:** `test_personas.py` (four official personas, ranking-only checks).
- **Generation:** `resume_generator.py` (structured candidate material, rule-based).
- **Export:** `docx_export.py` (python-docx).
- **Persistence:** `database.py` (sqlite3: resume_versions, applications, job_feedback).
- **Data:** processed job CSVs (from `data/raw/job_raw.json`), `candidate_master_profile.md`.

---

## 3. BAX423 Big Data Techniques Used

- **Structured data ingestion:** a ~1.3 GB MongoDB-style JSON array (~100K raw records)
  is streamed line-by-line (one record per line) with the standard-library `json`
  module, plus structured CSV ingestion for processed jobs and for application records
  (`sample_applications.csv` or user-uploaded CSV) with required-column validation.
- **Data preprocessing pipeline:** `preprocess_jobs.py` extracts nested fields, strips
  HTML, normalizes whitespace, classifies role families, deduplicates by job_id/url,
  and emits processed CSVs in a single pass. It produces **two** scales: a **20K**
  general structured sample (`external_jobs_20k_sample.csv`, not relevance-filtered) and
  a **~3K** app-optimized relevant subset (`external_jobs_sample.csv`), plus a 200-row
  demo file. The deployed app loads the smaller ~3K subset for responsiveness, while the
  20K sample demonstrates that the same pipeline scales to larger ingestion volumes.
- **Stream-style batch ingestion:** the raw snapshot is processed incrementally in
  fixed-size batches (`simulate_streaming_ingestion`), with running `job_id`/`job_url`
  dedup sets, progress logging every 5,000 records, and per-batch counts (raw / valid /
  duplicates / written). This simulates a streaming-style pipeline appropriate for MVP
  constraints; it is **not** real-time production streaming (real-time API ingestion is
  future work).
- **TF-IDF / vector similarity retrieval:** scikit-learn `TfidfVectorizer` + cosine
  similarity scores the candidate against many JDs at once and ranks them.
- **Dense-vector retrieval (optional):** `sentence-transformers/all-MiniLM-L6-v2` encodes
  each job (title + company + location + description + responsibilities + qualifications +
  role_family) and the candidate profile into dense vectors; cosine similarity over the
  cached embedding matrix gives a lightweight dense / ANN-style retrieval. The app falls
  back to TF-IDF if the backend is unavailable. FAISS/Annoy ANN indexing is future work.
- **Hybrid ranking:** `final = 0.50*dense + 0.30*tfidf + 0.20*keyword_coverage + feedback_bias`,
  with a benchmark (`evaluate_ranking_methods`) comparing TF-IDF vs dense vs hybrid on
  top-10 overlap, average keyword coverage, and runtime.
- **Batch analytics:** `compute_batch_analytics` aggregates the processed dataset into
  role-family distribution, location demand, top companies, top keyword/skill demand,
  source and employment-type coverage, and a missing-data audit (salary / job_url /
  location), exportable as CSV.
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

## 5b. Test Persona Results

The official four personas are evaluated for **recommendation quality only** — they do
**not** generate the project owner's resume. Each persona's `profile_text` is ranked
against the processed jobs (candidate facts excluded), and the top 10 are scored with
rule-based pass/fail checks. The page exports a Persona Evaluation CSV.

| Persona | Checks (examples) | Result (template) | Limitation |
| --- | --- | --- | --- |
| Aisha (ML pivoter) | No senior titles; ML-related ≥3/10; no defense/military | _Pass/Fail_ | Dataset is ops/analytics-heavy, so ML roles may be sparse |
| Marcus (new grad analytics) | No senior titles; no 3+/5+ yrs; no contract/unpaid; analytics-leaning | _Pass/Fail_ | Few explicit junior analytics rows |
| Priya (ML infra) | No junior; platform/MLOps/infra-leaning ≥3/10; NYC/remote ≥1 | _Pass/Fail_ | Location data is partial |
| Kenji (visa AI/ML) | No contract/temp; AI/ML-leaning ≥3/10; sponsor-friendly company ≥1 | _Pass/Fail_ | Sponsor detection uses a small fixed company list |

> Note: replace _Pass/Fail_ with the observed results from the Test Personas page.

**Key clarification:** the resume generation component is personalized to the project
owner's verified resume material, while the official test personas are used to evaluate
recommendation quality and filtering behavior.

---

## 6. Limitations

- The four official test personas are used for **ranking/filtering evaluation only**;
  resume generation remains personalized to the project owner's verified material and is
  never used to fabricate persona resumes.
- The dense-embedding backend is **optional**: if `sentence-transformers` is not installed
  or the model cannot download, the app falls back to TF-IDF, so dense/hybrid results may
  reflect the TF-IDF baseline in constrained environments.
- Dense ranking is a lightweight in-memory cosine search over cached embeddings (capped to
  the ~3K app dataset for responsiveness), not a production ANN index (FAISS/Annoy is
  future work).
- Ingestion is **stream-style batch** processing over an offline snapshot, not real-time
  production streaming.
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
- Preprocessing stops once both targets (~3,000 relevant rows and the 20,000-row general
  sample) are reached, so the processed CSVs are bounded subsets of the full ~100K raw
  dataset rather than an exhaustive extraction. Targets are configurable via environment
  variables (`JOBPILOT_TARGET`, `JOBPILOT_GENERAL_TARGET`).

---

## 7. Future Work

- Optional LLM-assisted rephrasing (with strict no-fabrication guardrails).
- PDF export and user-provided DOCX template support.
- Production ANN vector store (FAISS / Annoy) for dense retrieval at larger scale.
- Real-time / API-based job ingestion (vs. the current offline snapshot).
- Parsing edited markdown profiles directly into the generation engine.
- Persistent cloud database for multi-session tracking.

---

## 8. Links

- **Deployment URL:** _<add Streamlit Community Cloud URL here>_
- **GitHub URL:** _<add GitHub repository URL here>_
