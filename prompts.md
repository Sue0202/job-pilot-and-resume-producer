# JobPilot — Prompts & Logic Documentation

This file documents the prompts and the rule-based logic that drive JobPilot. The
MVP uses **no external AI APIs**; "prompts" here describe the deterministic logic
and the original Cursor initialization prompt.

---

## 1. Cursor Initialization Prompt (summary)

The project was initialized in Cursor with a prompt to build a stable, deployable
Streamlit MVP named **JobPilot: AI Resume Tailoring and Application Tracker**, with
the following constraints:

- Tech stack: Python, Streamlit, pandas, scikit-learn, sqlite3, python-docx.
- Build these files: `app.py`, `database.py`, `matching.py`, `resume_generator.py`,
  `docx_export.py`, `sample_jobs.csv`, `candidate_master_profile.md`,
  `requirements.txt`, `README.md`, `prompts.md`, `brief_content.md`.
- Core flow: view/edit candidate profile → load jobs from CSV → select a job →
  match JD vs. candidate → generate tailored resume → export DOCX/TXT → save to
  SQLite → track applications → support feedback-driven regeneration.
- Out of scope: LinkedIn scraping, resume.io, auto-apply, scheduler, accounts/OAuth,
  PDF template editing, external AI APIs, LangChain, vector DBs, agents.
- The candidate profile must be based on real resume material, never generic.

---

## 2. Matching Logic (matching.py)

Goal: score how well a job description (JD) fits the candidate and pick the right
target title.

Steps:

1. **Build JD text** — concatenate `job_title`, `company`, `description`,
   `responsibilities`, `qualifications`; lowercase and clean with regex.
2. **Controlled keyword bank** — a fixed list of operations/analytics terms (e.g.
   product operations, incident response, release management, SQL, EDA, monitoring).
3. **Matched vs. missing keywords** —
   - `jd_terms` = bank terms present in the JD.
   - `matched_keywords` = jd_terms also present in candidate material.
   - `missing_keywords` = jd_terms NOT present in candidate material (gaps to note).
4. **Role-family scoring** — four families (Product Ops / Program, Workflow /
   Support, Platform Ops, Technical Production / Live Service), each with a term
   list. The family with the highest count wins and maps to a target title +
   profile angle.
5. **TF-IDF cosine similarity** —
   - Overall JD vs. candidate similarity feeds the match score.
   - JD vs. each candidate fact (contexts + bullets) ranks the top relevant facts.
6. **Match score** = `100 * (0.5 * cosine + 0.5 * keyword_coverage)`.

Output `match_result` includes: `match_score`, `matched_keywords`,
`missing_keywords`, `selected_title_option`, `selected_profile_angle`,
`selected_expertise_keywords`, `selected_experience_groups`, `top_relevant_facts`,
and `role_family_scores`.

---

## 3. Resume Generation Logic (resume_generator.py)

Goal: assemble a truthful, tailored resume that always follows the candidate's real
structure.

Logic:

- The candidate's real material (header, four profile versions A–D, four experience
  groups with verified bullet banks, and education) lives as structured constants —
  the single source of truth. Nothing is fabricated.
- The **target title / profile angle** comes from the match result's selected role
  family.
- For each of the four experience groups (miHoYo, ByteDance, Ubisoft, Shenzhen
  Yousidun), bullets are ranked by:
  - keyword overlap with matched JD keywords + feedback + job title, and
  - a bonus if the bullet's tagged role family matches the selected family.
  The top 2–4 bullets per group are selected; every group always yields at least 2.
- **Context sentences** adapt per family (e.g. miHoYo uses a platform-leaning vs.
  product-leaning context; Ubisoft uses an analytics vs. general framing).
- **Education** always appears; coursework switches to an analytics-leaning list when
  the JD is analytics-heavy.
- Output sections are exactly: PROFILE, AREAS OF EXPERTISE, PROFESSIONAL EXPERIENCE,
  EDUCATION.

---

## 4. Feedback / Refinement Logic

Goal: let the user nudge the generated resume without an AI API.

Logic:

- The user enters free-text feedback such as "make it more platform operations
  focused" or "add more support escalation".
- The generator tokenizes the feedback and applies light weight bonuses to role
  families based on hint words: `platform` → Platform Ops, `support`/`incident` →
  Workflow/Support, `technical`/`release`/`production` → Technical Production,
  `analytics`/`program`/`product` → Product Ops.
- Feedback words are also added to the keyword pool used to rank bullets, so the
  regenerated version emphasizes the requested angle.
- The new version can be saved to SQLite alongside the feedback text for traceability.

---

## 5. Bug-Fix & Optimization Prompt (round 2)

A follow-up Cursor prompt was used to fix and optimize the app without redesigning
it or expanding MVP scope:

- **Fix resume version saving** — ensure generated resumes persist to the
  `resume_versions` SQLite table and appear on the Generated Versions page. Use a
  single consistent `DB_PATH = Path(__file__).parent / "jobpilot.db"`, call
  `init_db()` once at startup, keep the generated resume and match result in
  `st.session_state` so they survive reruns, capture the returned version id in the
  success message, use safe defaults for missing fields, and store keyword lists as
  comma-separated strings.
- **Improve the Application Tracker** — keep the manual add form and add a
  "Batch Upload Applications" section: a downloadable CSV template, a CSV uploader
  with required-column validation, a preview, and a "Save Uploaded Applications"
  button backed by a new `add_applications_bulk(records)` helper in `database.py`.
- **Make the tracker more presentable** — add summary metrics (Total, Saved, Applied,
  Interview, Rejected/Closed), simplified status options
  (Saved, Applied, Interview, OA, Rejected, Closed, Offer), and a status filter.
- **Add sample data** — `sample_applications.csv` with five realistic records.

Implementation note: after a write (manual add, bulk save, or update) the page sets a
one-time flash message in `st.session_state` and calls `st.rerun()`, so the metrics
and tables always reflect the latest database state immediately.

---

## 6. Dataset Preprocessing & Recommendation Pipeline Prompt (round 3)

A follow-up Cursor prompt added a large external dataset, an offline preprocessing
pipeline, and a ranked recommendation workflow:

- **Preprocess the raw dataset** — `preprocess_jobs.py` reads
  `data/raw/job_raw.json` (~1.3 GB MongoDB-style JSON array) once. Because the file
  has one JSON object per line, it is streamed with the standard-library `json`
  module (no `ijson` / no whole-file load). It extracts normalized fields
  (job_id, company, job_title, location, job_url, description, responsibilities,
  qualifications, salary, source, source_country, date_posted, employment_type,
  category, role_family), strips HTML with regex, normalizes whitespace, classifies
  each job into a role family, filters to relevant families, dedupes by job_id/url,
  drops rows missing title or description, and writes
  `data/processed/external_jobs_sample.csv` and `external_jobs_demo_200.csv`.
- **Ignore large/private files** — `.gitignore` excludes `data/raw/`, `*.db`,
  `__pycache__/`, `.DS_Store`, `*.zip`, `*.log`, `.env`; processed CSVs stay tracked.
- **Recommendation workflow** — the Job Matching page loads the processed CSV (with a
  fallback chain), lets the user filter by keyword / location / role family, and ranks
  many jobs at once with `matching.rank_jobs()` (one TF-IDF fit over candidate + all
  JDs, plus keyword coverage). It shows a ranked table (rank, score, role family,
  company, title, location, source, matched/missing keywords), a "Download Top Jobs as
  CSV" button, and per-job selection that feeds the existing resume generation,
  DOCX/TXT export, and Save Generated Version flow.

### Feedback-based adaptive ranking

- The user rates a selected job (Interested, Not Interested, Too Senior, Wrong
  Location, Good Match). Feedback is stored in a new `job_feedback` SQLite table.
- `compute_feedback_bias()` converts feedback into light, explainable adjustments:
  Good Match (+2) / Interested (+1) boost a role family and its title keywords;
  Not Interested / Too Senior (−1) penalize them; Wrong Location is treated as
  location-specific and does not bias families. The bias is added to the base score
  on the next ranking run. No ML model training is involved.
