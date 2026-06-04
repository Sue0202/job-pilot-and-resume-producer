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
  scored against the candidate profile (TF-IDF + keyword coverage + feedback bias).
  Download the top jobs as CSV, then select one to inspect and tailor a resume to.
- **Feedback learning** — rate a job (Interested, Not Interested, Too Senior, Wrong
  Location, Good Match); saved feedback lightly boosts/penalizes role families and
  keywords on the next ranking run.
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

## External Dataset & Preprocessing

The app is driven by a large external job dataset provided as a MongoDB-style JSON
array at `data/raw/job_raw.json` (~1.3 GB). **This raw file is never loaded by the
Streamlit app at runtime**, and `data/raw/` is git-ignored so it is never committed.

`preprocess_jobs.py` reads the raw JSON **once** (streaming it line-by-line with the
standard-library `json` module, so the whole file is never held in memory — no extra
dependencies such as `ijson` are required), extracts and normalizes useful fields,
strips HTML, filters to relevant job families, removes duplicates, and writes two
smaller CSVs the app loads cheaply:

- `data/processed/external_jobs_sample.csv` — up to ~3,000 relevant jobs
- `data/processed/external_jobs_demo_200.csv` — up to 200 rows for fast testing

Run preprocessing once (re-run only if the raw file changes):

```bash
python3 preprocess_jobs.py
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
| `matching.py` | Matching + ranking: keyword bank, role-family rules, TF-IDF, feedback bias. |
| `resume_generator.py` | Canonical candidate material + rule-based resume builder. |
| `docx_export.py` | Styled DOCX generation with python-docx. |
| `data/raw/job_raw.json` | Large external raw dataset (git-ignored, local only). |
| `data/processed/external_jobs_sample.csv` | Processed job dataset used by the app. |
| `data/processed/external_jobs_demo_200.csv` | Small processed dataset for fast testing. |
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
