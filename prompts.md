# JobPilot — AI Prompts Documentation

This file documents the key AI (Cursor) prompts used to build **JobPilot: AI Resume
Tailoring and Application Tracker** for the BAX423 final project, and how AI was used
in each step.

Notes:
- The running app uses **no external AI APIs and no API keys**. AI (Cursor) was used at
  *build time* to generate and refine code; the app's resume generation, matching, and
  ranking are deterministic and rule-based.
- Prompts below are condensed to the essential instructions. Raw data, secrets, and
  chat history are intentionally excluded.

---

## 1. Initial MVP App Generation

**Prompt (condensed):**
> Build a stable, deployable Streamlit MVP named *JobPilot: AI Resume Tailoring and
> Application Tracker*. Tech stack: Python, Streamlit, pandas, scikit-learn, sqlite3,
> python-docx. Create `app.py`, `database.py`, `matching.py`, `resume_generator.py`,
> `docx_export.py`, `sample_jobs.csv`, `candidate_master_profile.md`,
> `requirements.txt`, `README.md`, `prompts.md`, `brief_content.md`. Core flow:
> view/edit candidate profile → load jobs from CSV → select a job → match JD vs.
> candidate → generate a tailored resume → export DOCX/TXT → save versions to SQLite →
> track applications → support feedback-driven regeneration. Out of scope: LinkedIn
> scraping, resume.io, auto-apply, scheduler, accounts/OAuth, external AI APIs, vector
> DBs, agents. Candidate profile must use real resume material, never generic.

**How AI was used:** scaffolded the full multi-file project, a 5-page Streamlit
sidebar app, and the matching/generation/export/persistence modules from one spec.

---

## 2. Resume Generation Logic

**Prompt (condensed):**
> Generate a truthful, tailored resume that always follows the candidate's real
> structure (PROFILE, AREAS OF EXPERTISE, PROFESSIONAL EXPERIENCE, EDUCATION). Use the
> candidate's real material as structured constants — four profile angles (A–D) and
> four experience groups with verified bullet banks. Never fabricate. Pick the target
> title/profile angle from the match result's role family. Select 2–4 bullets per group
> by keyword overlap (matched JD keywords + feedback + title) plus a role-family bonus.
> Adapt context sentences per role family and switch coursework when the JD is
> analytics-heavy. Support free-text feedback (e.g. "make it more platform operations
> focused") that lightly reweights role-family selection and bullet ranking.

**How AI was used:** implemented `resume_generator.py` with a single source-of-truth
data structure and rule-based bullet selection, plus the feedback refinement logic, so
output is tailored yet non-fabricated.

---

## 3. SQLite Persistence / Versioning Fix

**Prompt (condensed):**
> Fix generated resumes not appearing on the Generated Versions page. Use one
> consistent `DB_PATH = Path(__file__).parent / "jobpilot.db"`, call `init_db()` once
> at startup, and ensure `save_resume_version()` commits. Keep the generated resume and
> match result in `st.session_state` so they survive reruns. Add a clear
> "Save Generated Version" button, show the returned version id in the success message,
> use safe defaults for missing fields, and store matched/missing keyword lists as
> comma-separated strings. Confirm versions list and load back by id.

**How AI was used:** diagnosed the rerun/session-state and persistence path, hardened
`database.py` + the Job Matching save flow, and verified round-trip saving/loading.

---

## 4. Application Tracker Batch Upload

**Prompt (condensed):**
> Keep the manual add form and add a "Batch Upload Applications" section: a downloadable
> CSV template, a CSV uploader, required-column validation
> (company, job_title, job_url, status, application_date, notes), a preview, and a
> "Save Uploaded Applications" button backed by a new `add_applications_bulk(records)`
> helper in `database.py`. Add executive summary metrics (Total, Saved, Applied,
> Interview, Rejected/Closed), simplified status options
> (Saved, Applied, Interview, OA, Rejected, Closed, Offer), and a status filter. Add
> `sample_applications.csv` with five realistic records.

**How AI was used:** extended the tracker with bulk ingestion + validation, summary
metrics, and a flash-message + `st.rerun()` pattern so tables/metrics refresh
immediately after writes.

---

## 5. External JSON Dataset Preprocessing

**Prompt (condensed):**
> The raw dataset is a ~1.3 GB MongoDB-style JSON array at `data/raw/job_raw.json`. The
> Streamlit app must NOT load it at runtime. Build `preprocess_jobs.py` that reads it
> once, extracts normalized fields (job_id, company, job_title, location, job_url,
> description, responsibilities, qualifications, salary, source, source_country,
> date_posted, employment_type, category, role_family), strips HTML with regex,
> normalizes whitespace, classifies a role family, filters to relevant families,
> dedupes by job_id/url, drops rows missing title/description, prints progress, and
> writes `data/processed/external_jobs_sample.csv` and `external_jobs_demo_200.csv`.
> Prefer stdlib; avoid heavy dependencies. Update `.gitignore` to exclude `data/raw/`,
> `*.db`, `__pycache__/`, `.DS_Store`, `*.zip`, `*.log`, `.env` (keep processed CSVs).

**How AI was used:** inspected the nested record schema, recognized the file is one
JSON object per line, and implemented a memory-safe **streaming** parser with the
standard-library `json` module (no `ijson`, no whole-file load) plus the extract →
clean → classify → filter → dedupe pipeline.

---

## 6. Ranked Job Recommendation Pipeline

**Prompt (condensed):**
> Update the app to load the processed external jobs (fallback order:
> processed sample → demo 200 → `sample_jobs.csv`) and show which dataset is loaded.
> Turn the Job Matching page into a recommendation workflow: filter by keyword /
> location / role family; rank many jobs against the candidate profile; show a ranked
> table with rank, match_score, role_family, company, job_title, location, source, and
> matched/missing keywords; add "Download Top Jobs as CSV"; let the user select one job
> to view the JD and generate a tailored resume (keep TXT/DOCX and Save Generated
> Version).

**How AI was used:** added `matching.rank_jobs()` (one TF-IDF fit over candidate + all
JDs, combined with controlled-keyword coverage), a `classify_role_family()` fallback,
and rebuilt the Job Matching page as a filter → rank → select → generate flow.

---

## 7. Feedback-Based Adaptive Ranking

**Prompt (condensed):**
> Add simple, explainable adaptive feedback to job ranking. Create a `job_feedback`
> SQLite table and `save_job_feedback()` / `get_job_feedback()` /
> `get_feedback_summary()`. On the Job Matching page, let the user rate the selected job
> (Interested, Not Interested, Too Senior, Wrong Location, Good Match) and save it.
> Ranking should use feedback lightly: boost role families/keywords from
> Interested/Good Match jobs and penalize those from Not Interested/Too Senior jobs.
> No ML training.

**How AI was used:** implemented `compute_feedback_bias()` — Good Match (+2) /
Interested (+1) boost a role family and its title keywords; Not Interested / Too Senior
(−1) penalize them; Wrong Location is treated as location-specific. The bias is added
to the base score on the next ranking run.

---

## 8. README / Brief Drafting

**Prompt (condensed):**
> Update `README.md` to explain the preprocessing step (raw JSON → processed CSV),
> that `data/raw/` is git-ignored, how to run preprocessing
> (`python3 preprocess_jobs.py`) and the app (`streamlit run app.py`), and the dataset
> fallback behavior. Update `brief_content.md` with the architecture
> (raw JSON → preprocessing → processed CSV → ranking/recommendation → resume
> generation → SQLite persistence) and the BAX423 techniques (structured data
> ingestion, preprocessing pipeline, TF-IDF/vector similarity retrieval, multi-stage
> ranking, feedback-based adaptive ranking, SQLite persistence, Streamlit deployment,
> DOCX generation), and note the limitation that the raw dataset is an offline
> historical snapshot, not live job availability.

**How AI was used:** drafted and kept the README and 4-page project brief in sync with
the code as features were added across iterations.

---

## Appendix — Build Iterations (summary)

1. **Round 1:** initial MVP (sections 1–2 above, plus matching and DOCX/TXT export).
2. **Round 2:** persistence/versioning fix and Application Tracker batch upload
   (sections 3–4).
3. **Round 3:** external dataset preprocessing, ranked recommendations, and
   feedback-based ranking (sections 5–7).
4. **Docs:** README/brief drafting kept current throughout (section 8).
