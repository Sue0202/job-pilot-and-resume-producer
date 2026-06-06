# JobPilot: AI Resume Tailoring and Application Tracker

JobPilot is a Streamlit MVP that helps a job seeker tailor a resume to a specific
job description and track applications. It matches sample job postings against a
candidate master profile, generates a tailored resume using a rule-based engine,
exports the result to DOCX or TXT, and persists generated versions and manual
application records in SQLite.

Built for the BAX423 Big Data final project.

## MVP Features

- **Candidate Profile** — view, edit, save, or upload a Candidate Master Profile
  (resume material library) in markdown.
- **Job Matching & Recommendations** — load a (preprocessed) external job dataset,
  filter by keyword / location / role family, and get **ranked job recommendations**
  scored against the candidate profile. Choose a **ranking method**:
  - **TF-IDF baseline** — TF-IDF cosine + keyword coverage (always available).
  - **Dense embedding retrieval** — lightweight dense-vector retrieval using
    `sentence-transformers/all-MiniLM-L6-v2` (optional; see note below).
  - **Hybrid ranking** — `0.50*dense + 0.30*tfidf + 0.20*keyword_coverage + feedback_bias`.

  Each recommendation shows an **explain** breakdown (dense score, TF-IDF score,
  keyword coverage, feedback adjustment, matched/missing keywords, role family).
  A built-in **benchmark** compares the three methods (top-10 overlap, average
  keyword coverage, runtime). Download the top jobs as CSV, then select one to tailor
  a resume to.
- **Feedback learning** — rate a job (Interested, Not Interested, Too Senior, Wrong
  Location, Good Match); saved feedback lightly boosts/penalizes role families and
  keywords on the next ranking run.
- **Batch Analytics** — aggregate insights over the processed dataset: jobs by role
  family, top locations/companies, top keyword/skill demand, source and employment-type
  distributions, and a missing-data audit (salary / job_url / location). Download the
  summary as CSV.
- **Test Personas** — evaluate recommendation quality for the four official personas
  (Aisha, Marcus, Priya, Kenji) with rule-based pass/fail checks and a downloadable
  evaluation CSV. Personas are used for **ranking evaluation only** and never reuse the
  project owner's real resume material.
- **Tailored Resume Generation** — rule-based resume builder that always follows the
  candidate's real resume structure (PROFILE, AREAS OF EXPERTISE, PROFESSIONAL
  EXPERIENCE, EDUCATION).
- **Feedback / Refinement** — enter feedback (e.g. "make it more platform operations
  focused") and regenerate a new version.
- **Exports** — download as styled DOCX (python-docx) or plain TXT.
- **Generated Versions** — every generated resume is persisted in SQLite and listed
  with id, timestamp, company, job title, target title, match score, and feedback used.
  Select any version by id to view and re-download its full text.
- **Application Tracker** — manual single-record add **and** batch CSV upload, with
  executive summary metrics (Total, Saved, Applied, Interview, Rejected/Closed), a
  status filter, and inline status/notes updates. A `sample_applications.csv` and a
  downloadable CSV template are provided.

## Tech Stack

- Python
- Streamlit
- pandas
- scikit-learn (TF-IDF + cosine similarity)
- sqlite3 (standard library)
- python-docx
- sentence-transformers (**optional** — enables dense / hybrid ranking)

### Ranking methods & the optional dense backend

`sentence-transformers` is listed in `requirements.txt` but is **optional**. If it is
not installed, or the model cannot be downloaded (e.g. offline), the app **automatically
falls back to the TF-IDF baseline** and shows a warning instead of crashing. The dense
index is built once and cached (`st.cache_resource`) and is capped to the ~3K app
dataset for interactive responsiveness. This is intentionally a lightweight dense-vector
retrieval suitable for MVP scale; FAISS/Annoy-based approximate nearest neighbor (ANN)
indexing is noted as future work.

## External Dataset & Preprocessing

The app is driven by a large external job dataset provided as a MongoDB-style JSON
array at `data/raw/job_raw.json` (~1.3 GB). **This raw file is never loaded by the
Streamlit app at runtime**, and `data/raw/` is git-ignored so it is never committed.

`preprocess_jobs.py` reads the raw JSON **once** using **stream-style batch ingestion**:
it streams the file line-by-line with the standard-library `json` module (the whole file
is never held in memory — no extra dependencies such as `ijson` are required), processes
records incrementally, deduplicates with running `job_id`/`job_url` sets, prints progress
every 5,000 records, extracts and normalizes useful fields, strips HTML, classifies role
families, filters to relevant job families, and writes the CSVs the app loads cheaply:

- `data/processed/external_jobs_sample.csv` — up to ~3,000 **relevance-filtered** jobs;
  this is the dataset the app loads by default for fast demo responsiveness.
- `data/processed/external_jobs_demo_200.csv` — up to 200 rows for fast testing.
- `data/processed/external_jobs_20k_sample.csv` — up to **20,000** structured job
  postings (deduped, cleaned, role-family classified, but **not** relevance-filtered).
  This is the larger structured sample kept as submission evidence of scalable
  ingestion; the app does **not** load it (to keep the demo responsive).

Run preprocessing once (re-run only if the raw file changes):

```bash
python3 preprocess_jobs.py
```

There is also an explicit **stream-style batch ingestion** entry point that processes
the snapshot in fixed-size batches and logs per-batch counts (raw / valid / duplicates /
written). This simulates a streaming-style pipeline suitable for MVP constraints; it is
**not** real-time production streaming, and real-time API ingestion is future work:

```bash
python3 preprocess_jobs.py stream
```

The processed CSVs **are** committed (only `data/raw/` is ignored).

### Dataset fallback order

At startup the Job Matching page loads the first dataset that exists:

1. `data/processed/external_jobs_sample.csv`
2. `data/processed/external_jobs_demo_200.csv`
3. `sample_jobs.csv` (built-in 10-row demo)

The page shows which dataset is currently loaded.

## How to Run Locally

```bash
pip install -r requirements.txt
python3 preprocess_jobs.py     # one-time: build processed job CSVs from data/raw/
streamlit run app.py
```

The SQLite database (`jobpilot.db`) is created automatically on first run. If the
processed CSVs are missing, the app falls back to `sample_jobs.csv` and still runs.

## Deployment

This app can be deployed for free on **Streamlit Community Cloud**:

1. Push this folder to a public GitHub repository.
2. On Streamlit Community Cloud, create a new app pointing to `app.py`.
3. Streamlit installs `requirements.txt` automatically.

Note: Streamlit Community Cloud has an ephemeral filesystem, so `jobpilot.db` and
profile edits reset on redeploy. This is acceptable for an MVP demo.

## Files

| File | Purpose |
| --- | --- |
| `app.py` | Streamlit UI and page routing. |
| `preprocess_jobs.py` | One-time pipeline: raw JSON → cleaned/filtered processed CSVs. |
| `database.py` | SQLite layer (resume versions + applications + job feedback). |
| `matching.py` | Matching + ranking: keyword bank, role-family rules, TF-IDF, dense embeddings, hybrid ranking, benchmark, feedback bias. |
| `analytics.py` | Batch analytics helper (`compute_batch_analytics`) over the processed dataset. |
| `test_personas.py` | Four official test personas + rule-based pass/fail evaluation (ranking only). |
| `resume_generator.py` | Canonical candidate material + rule-based resume builder. |
| `docx_export.py` | Styled DOCX generation with python-docx. |
| `data/raw/job_raw.json` | Large external raw dataset (git-ignored, local only). |
| `data/processed/external_jobs_sample.csv` | Relevance-filtered (~3K) job dataset the app loads by default. |
| `data/processed/external_jobs_demo_200.csv` | Small processed dataset for fast testing. |
| `data/processed/external_jobs_20k_sample.csv` | Larger 20K structured sample for submission (not loaded by the app). |
| `sample_jobs.csv` | Built-in fallback job postings dataset (10 roles). |
| `sample_applications.csv` | Sample application records for batch upload (5 rows). |
| `candidate_master_profile.md` | Editable candidate resume material library. |
| `requirements.txt` | Python dependencies. |
| `prompts.md` | Prompt and logic documentation. |
| `brief_content.md` | Draft of the final project brief. |
| `jobpilot.db` | SQLite database (auto-created). |

## Scope Notes

This MVP intentionally excludes: real LinkedIn scraping, resume.io integration,
auto-apply, schedulers, accounts/OAuth, PDF template editing, and external AI APIs.
Resume generation is fully rule-based and deterministic.
