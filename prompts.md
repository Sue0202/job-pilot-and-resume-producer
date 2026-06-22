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

## 9. Weakness Improvement Prompt

**Purpose:** This prompt added dense-vector retrieval fallback, stream-style ingestion
documentation, batch analytics, and persona evaluation while preserving the project
owner's verified resume generator.

**Prompt (condensed):**
> Improve grading weaknesses without breaking the working MVP. (1) Add true dense
> embeddings / ANN-style retrieval using `sentence-transformers/all-MiniLM-L6-v2`,
> keeping TF-IDF as a graceful fallback; add `build_embedding_index`, `rank_jobs_dense`,
> a ranking-method selector (TF-IDF / Dense / Hybrid), a hybrid score
> (`0.50*dense + 0.30*tfidf + 0.20*coverage + feedback_bias`), a per-job explain view,
> and an `evaluate_ranking_methods` benchmark. (2) Better justify streaming: process the
> raw JSON incrementally in batches, log progress every 5,000 records, deduplicate with
> running sets, and add `simulate_streaming_ingestion`; document it as stream-style batch
> ingestion (not real-time). (3) Add a Batch Analytics page (`compute_batch_analytics`).
> (4) Add four official test personas for ranking evaluation only, never reusing the
> real resume material.

**How AI was used:**
- Implemented the optional dense backend with a lazy singleton model loader and
  try/except guards so the app falls back to TF-IDF (with a UI warning) whenever
  `sentence-transformers` is missing or the model cannot be downloaded.
- Cached embeddings via `st.cache_resource` and capped dense indexing to the ~3K app
  dataset for interactive responsiveness.
- Added per-component (dense / TF-IDF / coverage / feedback) scores to each result for
  the explain view, plus a benchmark expander.
- Refactored `rank_jobs` with an `include_candidate_facts` flag so persona ranking uses
  only the persona profile text and never injects the owner's verified facts.

---

## 10. Post-submission JobPilot v2: JD Intake and Fit Diagnosis

**Purpose:** Upgrade the class project into a personal job-search copilot by adding a
one-JD intake + conservative fit-diagnosis workflow, without rewriting the app or
removing any existing class-project feature.

**Prompt (condensed):**
> Add a new top sidebar page **Analyze Job** for one-JD intake (company, title, apply
> link, source, JD text, notes) and fit diagnosis. Create `jd_analyzer.py` with rule-based
> `parse_jd` (responsibilities, qualifications, required/preferred skills, tools, seniority
> signals, role keywords, sponsorship signals, risk flags) and `analyze_fit` returning an
> overall 0–10 score, a decision (High Priority / Apply with Tailoring / Maybe / Skip),
> component scores with fixed weights (role 20, experience 25, skill 15, seniority 15,
> transferability 10, sponsorship 5, evidence 10), matched/missing evidence, evidence-gap
> questions, red flags, recommended positioning, and a scoring explanation. Keep scoring
> conservative — do not overrate roles needing hard tech skills, clearance, CPA,
> quota-carrying sales, or many years of direct domain experience. When score < 6.5, show
> evidence-gap questions plus a temporary "added evidence" re-analyze loop that never
> overwrites the master profile. Add a score-feedback section (saved, not auto-applied),
> a Save-to-Tracker handoff, and a Generate-Tailored-Resume handoff that reuses the
> verified resume generator. Add `job_analyses` and `score_feedback` SQLite tables without
> touching existing tables.

**How AI was used:**
- Built `jd_analyzer.py` as a self-contained, testable module (regex + keyword banks),
  with hard-requirement detection that caps the overall score toward Skip (sponsorship
  blockers cap hardest).
- Added two new SQLite tables and an `applications` upsert with safe optional columns
  (`analysis_score`, `role_family`) so the tracker handoff never breaks the existing schema.
- Reused the existing rule-based resume generator for the handoff so persona/verified
  material constraints are preserved (no fabrication, master profile never overwritten).

---

## 11. JobPilot v2.1: Score Calibration and Split Feedback Loop

**Purpose:** Make the Analyze Job fit scoring stricter and more truthful, and turn
feedback into a useful, explainable calibration loop separated from added-evidence
re-analysis.

**Prompt (condensed):**
> Make scoring more conservative with stricter bands (≥ 8.5 High Priority, 7.0–8.4 Apply
> with Tailoring, 5.5–6.9 Maybe, < 5.5 Skip) plus a Priority and Confidence label. Resume
> Evidence Strength must not default near 10 — cap at 6.5 (adjacent only), 8.0 (single
> indirect transferable), 9.0+ only with multiple direct examples covering core
> responsibilities, with credit for outcomes/metrics. Add hard penalties for no
> sponsorship, US-citizen/clearance, over-seniority, deep SWE/ML without evidence, and
> quota/licensed roles. Rename "Sponsorship Market Risk" to "Sponsorship Feasibility"
> (higher = better). Split feedback into (A) Score Calibration Feedback that stores a
> calibrated score (base ± magnitude) without overwriting the base, and (B) Add Evidence
> and Re-analyze with a before/after comparison. Apply a small, visible role-family
> calibration (max ±0.3) to new JDs in a family with prior feedback. Add tests.

**How AI was used:**
- Reworked `jd_analyzer.py` evidence scoring to distinguish **direct vs. adjacent**
  evidence and measure **core-responsibility coverage**, with explicit caps and
  hard-penalty caps; added `priority_for`, `decision_for`, and `apply_calibration` helpers
  and a one-line score explanation.
- Extended `database.py` (`job_analyses`, `score_feedback`) with calibration columns via
  safe `ALTER TABLE`, and added `get_calibration_adjustment(role_family)` (clamped ±0.3).
- Split the Analyze Job UI into four clearly separated sections (Calibration Feedback,
  Add Evidence & Re-analyze, Save to Tracker, Generate Resume) and relabeled the headline
  to Base Fit Score / Priority / Confidence.
- Added `test_jd_analyzer.py` covering the high-fit, borderline, ML/clearance, added-
  evidence, calibration, and profile-unchanged cases.

**Follow-up — clearer Added Evidence re-analysis results:**
> The re-analysis showed "Newly matched evidence: 0" even when added skills (Salesforce,
> Tableau) correctly raised Skill Fit. Split the output into (A) new JD requirements
> covered by the added evidence and (B) new verified evidence items matched; add an
> evidence-quality label (Skill claim only / Concrete / Outcome-backed) with rules so a
> skill claim only improves Skill Fit but not Experience Fit or Resume Evidence Strength;
> and add a "Why changed" explanation. Scoring, calibration, tracker, and resume behavior
> unchanged. Implemented as UI helpers (`_classify_evidence_quality`,
> `_newly_covered_skills`) in `app.py` without touching the scoring model.

**Follow-up — better angle + 4-level evidence quality:**
> Two fixes (no scoring-weight changes): (1) for business-systems / enterprise-tooling JDs
> (Salesforce, Workday, NetSuite, integrations, internal tools, process improvement),
> suggest a Business Systems / Internal Tools angle instead of defaulting to Customer
> Support unless the JD is explicitly support/CX. (2) Expand temporary evidence quality to
> four levels (Skill claim only / Basic / Concrete / Outcome-backed) with scaled effects —
> skill/basic raise Skill Fit only, concrete adds a small Experience Fit bump, outcome-backed
> adds more, and Resume Evidence Strength is never auto-raised. Implemented `_suggested_angle`
> and `classify_evidence_quality` in `jd_analyzer.py` plus an optional `added_evidence_quality`
> Experience-Fit bonus used only during re-analysis; updated the "Why changed" explanation and
> added unit tests for all four categories and the angle behavior.

**Base vs. calibrated vs. re-analysis (key distinction):**
- **Base Fit Score** = the model's conservative rule-based score for the JD as written.
- **Calibrated Score** = Base ± a user adjustment from Score Calibration Feedback; saved
  separately, base never changes. Aggregated per role family it becomes a small (±0.3)
  visible adjustment on future JDs in that family.
- **Added-Evidence Re-analysis** = a fresh full re-score after temporarily appending
  user-supplied evidence (never written to the master profile), shown as before/after.

---

## Appendix — Build Iterations (summary)

1. **Round 1:** initial MVP (sections 1–2 above, plus matching and DOCX/TXT export).
2. **Round 2:** persistence/versioning fix and Application Tracker batch upload
   (sections 3–4).
3. **Round 3:** external dataset preprocessing, ranked recommendations, and
   feedback-based ranking (sections 5–7).
4. **Docs:** README/brief drafting kept current throughout (section 8).
5. **Round 4 (weakness improvement):** dense/hybrid ranking with TF-IDF fallback,
   stream-style ingestion documentation, batch analytics, and persona evaluation
   (section 9).
6. **v2 (personal copilot):** Analyze Job one-JD intake + conservative fit diagnosis,
   evidence-gap loop, score feedback, and tracker/resume handoffs (section 10).
7. **v2.1 (calibration):** stricter score bands, priority/confidence, conservative
   evidence-strength caps, hard penalties, Sponsorship Feasibility, and a split
   calibration / added-evidence feedback loop with tests (section 11).
