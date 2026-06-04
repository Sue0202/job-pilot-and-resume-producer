"""JobPilot: AI Resume Tailoring and Application Tracker.

A Streamlit MVP that matches sample job postings against a candidate master
profile, generates a tailored resume (rule-based), exports DOCX/TXT, and tracks
generated versions and manual applications in SQLite.

Run locally:
    pip install -r requirements.txt
    streamlit run app.py
"""

from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

import database as db
import docx_export
import matching
import resume_generator as rg

BASE_DIR = Path(__file__).parent
PROFILE_PATH = BASE_DIR / "candidate_master_profile.md"
README_PATH = BASE_DIR / "README.md"

# Job dataset fallback order: processed full sample -> demo -> built-in sample.
PROCESSED_SAMPLE_PATH = BASE_DIR / "data" / "processed" / "external_jobs_sample.csv"
PROCESSED_DEMO_PATH = BASE_DIR / "data" / "processed" / "external_jobs_demo_200.csv"
SAMPLE_JOBS_PATH = BASE_DIR / "sample_jobs.csv"

DATASET_CANDIDATES = [
    (PROCESSED_SAMPLE_PATH, "External jobs — processed sample"),
    (PROCESSED_DEMO_PATH, "External jobs — demo (200)"),
    (SAMPLE_JOBS_PATH, "Built-in sample jobs"),
]

DEFAULT_PROFILE_TEXT = (
    "# Candidate Master Profile\n\n"
    "This is a placeholder profile. Replace it with your real resume material.\n"
)

JOB_COLUMNS = [
    "job_id",
    "company",
    "job_title",
    "location",
    "job_url",
    "description",
    "responsibilities",
    "qualifications",
]

# Application tracker status options and CSV schema (shared across the page).
STATUS_OPTIONS = ["Saved", "Applied", "Interview", "OA", "Rejected", "Closed", "Offer"]
APPLICATION_COLUMNS = [
    "company",
    "job_title",
    "job_url",
    "status",
    "application_date",
    "notes",
]


# ---------------------------------------------------------------------------
# Safe file loaders (create defaults if a file is missing)
# ---------------------------------------------------------------------------

def load_profile_text():
    if not PROFILE_PATH.exists():
        PROFILE_PATH.write_text(DEFAULT_PROFILE_TEXT, encoding="utf-8")
    return PROFILE_PATH.read_text(encoding="utf-8")


def save_profile_text(text):
    PROFILE_PATH.write_text(text, encoding="utf-8")


@st.cache_data
def _read_jobs_csv(path_str, mtime):
    return pd.read_csv(path_str, dtype=str).fillna("")


def _normalize_jobs(df):
    """Ensure all expected columns exist and role_family is populated."""
    for col in JOB_COLUMNS + ["salary", "source", "source_country", "date_posted",
                              "employment_type", "category", "role_family"]:
        if col not in df.columns:
            df[col] = ""
    df = df.fillna("")
    needs_family = (df["role_family"].astype(str).str.strip() == "")
    if needs_family.any():
        df.loc[needs_family, "role_family"] = df.loc[needs_family].apply(
            lambda r: matching.classify_role_family(r.get("job_title", ""), r.get("description", "")),
            axis=1,
        )
    return df


def load_jobs():
    """Return (DataFrame, dataset_label) using the fallback order."""
    for path, label in DATASET_CANDIDATES:
        if path.exists():
            df = _read_jobs_csv(str(path), path.stat().st_mtime)
            return _normalize_jobs(df.copy()), label
    return pd.DataFrame(columns=JOB_COLUMNS), "No dataset found"


def load_readme():
    if README_PATH.exists():
        return README_PATH.read_text(encoding="utf-8")
    return "# JobPilot\n\nREADME.md not found. See project documentation."


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

def page_candidate_profile():
    st.header("Candidate Profile")
    st.caption("View, edit, or upload your Candidate Master Profile / Resume Material Library.")

    uploaded = st.file_uploader("Upload a markdown file to replace the profile", type=["md", "txt"])
    if uploaded is not None:
        content = uploaded.read().decode("utf-8", errors="replace")
        save_profile_text(content)
        st.success("Profile replaced from uploaded file.")

    current_text = load_profile_text()
    edited = st.text_area("Candidate Master Profile (markdown)", value=current_text, height=500)
    if st.button("Save Profile"):
        save_profile_text(edited)
        st.success("Profile saved to candidate_master_profile.md")


def _render_match_result(result):
    col1, col2 = st.columns(2)
    with col1:
        st.metric("Match Score", f"{result['match_score']}")
        st.write("**Selected Target Title**")
        st.write(result["selected_title_option"])
    with col2:
        st.write("**Selected Expertise**")
        st.write(" | ".join(result["selected_expertise_keywords"]))

    col3, col4 = st.columns(2)
    with col3:
        st.write("**Matched Keywords**")
        st.write(", ".join(result["matched_keywords"]) if result["matched_keywords"] else "_None_")
    with col4:
        st.write("**Missing Keywords**")
        st.write(", ".join(result["missing_keywords"]) if result["missing_keywords"] else "_None_")

    st.write("**Top Relevant Facts**")
    for fact in result["top_relevant_facts"]:
        st.markdown(f"- {fact}")


FEEDBACK_OPTIONS = [
    "Interested",
    "Not Interested",
    "Too Senior",
    "Wrong Location",
    "Good Match",
]

# How many filtered jobs to actually rank (keeps ranking fast on large datasets).
RANK_CAP = 1500


def _render_resume_section(profile_text, job_row):
    """Match the selected job, then generate / download / save a tailored resume.

    Resume state is keyed by job_id so switching jobs does not show stale output.
    """
    job_id = str(job_row.get("job_id", ""))

    # Full match result for resume generation (cached per job in session).
    mr_key = f"match_result_{job_id}"
    if mr_key not in st.session_state:
        st.session_state[mr_key] = matching.match_job_to_candidate(profile_text, job_row)
    result = st.session_state[mr_key]

    _render_match_result(result)

    st.markdown("**Tailored Resume**")
    feedback_text = st.text_area(
        "Feedback / refinement (optional)",
        value="",
        placeholder="e.g. make it more platform operations focused, or add more support escalation",
        key=f"resume_feedback_input_{job_id}",
    )

    colg1, colg2 = st.columns(2)
    with colg1:
        gen_clicked = st.button("Generate Resume", key=f"gen_{job_id}")
    with colg2:
        regen_clicked = st.button("Regenerate with Feedback", key=f"regen_{job_id}")

    data_key = f"resume_data_{job_id}"
    fb_key = f"resume_feedback_{job_id}"
    if gen_clicked or regen_clicked:
        fb = feedback_text if regen_clicked else ""
        st.session_state[data_key] = rg.generate_resume(profile_text, job_row, result, fb)
        st.session_state[fb_key] = fb

    resume_data = st.session_state.get(data_key)
    if not resume_data:
        st.info("Click **Generate Resume** to build a tailored resume from this match.")
        return

    st.text_area(
        "Generated Resume",
        value=resume_data["full_resume_text"],
        height=500,
        key=f"resume_text_{job_id}",
    )

    cold1, cold2, cold3 = st.columns(3)
    with cold1:
        st.download_button(
            "Download TXT",
            data=resume_data["full_resume_text"].encode("utf-8"),
            file_name=f"resume_{job_id}.txt",
            mime="text/plain",
            key=f"txt_{job_id}",
        )
    with cold2:
        try:
            docx_bytes = docx_export.create_resume_docx(resume_data)
            st.download_button(
                "Download DOCX",
                data=docx_bytes,
                file_name=f"resume_{job_id}.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                key=f"docx_{job_id}",
            )
        except Exception as exc:  # pragma: no cover - defensive
            st.error(f"DOCX export failed: {exc}")
    with cold3:
        if st.button("Save Generated Version", type="primary", key=f"save_{job_id}"):
            new_id = db.save_resume_version(
                company=job_row.get("company", ""),
                job_title=job_row.get("job_title", ""),
                job_id=job_row.get("job_id", ""),
                target_title=resume_data.get("target_title", ""),
                match_score=result.get("match_score", 0.0),
                matched_keywords=", ".join(result.get("matched_keywords", []) or []),
                missing_keywords=", ".join(result.get("missing_keywords", []) or []),
                feedback_text=st.session_state.get(fb_key, ""),
                resume_text=resume_data.get("full_resume_text", ""),
            )
            st.success(f"Saved generated version to SQLite (version id {new_id}).")


def page_job_matching():
    st.header("Job Matching & Recommendations")

    jobs, dataset_label = load_jobs()
    st.caption(f"Loaded dataset: **{dataset_label}** — {len(jobs)} jobs")
    if jobs.empty:
        st.warning(
            "No job dataset found. Run `python3 preprocess_jobs.py` to build the "
            "processed dataset, or add `sample_jobs.csv`."
        )
        return

    profile_text = load_profile_text()

    # ---- 1. Filters -------------------------------------------------------
    st.subheader("1. Filter Jobs")
    c1, c2, c3 = st.columns(3)
    with c1:
        keyword = st.text_input("Keyword search", placeholder="e.g. operations, support")
    with c2:
        location = st.text_input("Location contains", placeholder="e.g. San Francisco")
    with c3:
        families = sorted([f for f in jobs["role_family"].unique() if str(f).strip()])
        selected_families = st.multiselect("Role family", families)

    filtered = jobs
    if keyword:
        mask = filtered["job_title"].str.contains(keyword, case=False, na=False, regex=False) | \
            filtered["description"].str.contains(keyword, case=False, na=False, regex=False)
        filtered = filtered[mask]
    if location:
        filtered = filtered[
            filtered["location"].str.contains(location, case=False, na=False, regex=False)
        ]
    if selected_families:
        filtered = filtered[filtered["role_family"].isin(selected_families)]

    st.caption(f"{len(filtered)} jobs match the current filters (ranking up to {RANK_CAP}).")
    top_n = st.slider("Number of recommendations to show", 5, 50, 25)

    if st.button("Recommend Jobs", type="primary"):
        feedback_rows = db.get_job_feedback()
        ranked = matching.rank_jobs(
            profile_text,
            filtered.head(RANK_CAP).to_dict("records"),
            feedback_rows=feedback_rows,
            top_n=top_n,
        )
        st.session_state["ranked_jobs"] = ranked

    ranked = st.session_state.get("ranked_jobs")
    if not ranked:
        st.info("Set filters and click **Recommend Jobs** to see ranked recommendations.")
        return

    # ---- 2. Recommendations table ----------------------------------------
    st.divider()
    st.subheader("2. Top Recommended Jobs")
    table = pd.DataFrame(
        [
            {
                "rank": r["rank"],
                "match_score": r["match_score"],
                "role_family": r["role_family"],
                "company": r["job_row"].get("company", ""),
                "job_title": r["job_row"].get("job_title", ""),
                "location": r["job_row"].get("location", ""),
                "source": r["job_row"].get("source", ""),
                "matched_keywords": ", ".join(r["matched_keywords"]),
                "missing_keywords": ", ".join(r["missing_keywords"]),
            }
            for r in ranked
        ]
    )
    st.dataframe(table, width="stretch", hide_index=True)
    st.download_button(
        "Download Top Jobs as CSV",
        data=table.to_csv(index=False).encode("utf-8"),
        file_name="top_recommended_jobs.csv",
        mime="text/csv",
    )

    # ---- 3. Select one recommended job -----------------------------------
    st.divider()
    st.subheader("3. Select a Recommended Job")
    ranks = [r["rank"] for r in ranked]
    sel_rank = st.selectbox(
        "Select by rank",
        ranks,
        format_func=lambda x: (
            f"#{x} — {ranked[x - 1]['job_row'].get('job_title', '')} "
            f"@ {ranked[x - 1]['job_row'].get('company', '')} "
            f"(score {ranked[x - 1]['match_score']})"
        ),
    )
    selected = ranked[sel_rank - 1]
    job_row = selected["job_row"]

    st.markdown(f"**{job_row.get('job_title', '')} @ {job_row.get('company', '')}**")
    meta = f"Role family: {selected['role_family']}  |  Location: {job_row.get('location', '')}"
    if job_row.get("source"):
        meta += f"  |  Source: {job_row.get('source')}"
    st.markdown(meta)
    if job_row.get("job_url"):
        st.markdown(f"[Job link]({job_row.get('job_url')})")
    st.markdown(f"**Description:** {job_row.get('description', '')}")
    if job_row.get("responsibilities"):
        st.markdown(f"**Responsibilities:** {job_row.get('responsibilities')}")
    if job_row.get("qualifications"):
        st.markdown(f"**Qualifications:** {job_row.get('qualifications')}")

    # ---- 4. Feedback learning --------------------------------------------
    st.divider()
    st.subheader("4. Job Feedback (improves ranking)")
    with st.form(f"job_feedback_{job_row.get('job_id', '')}"):
        fb_choice = st.radio("Your feedback on this job", FEEDBACK_OPTIONS, horizontal=True)
        fb_notes = st.text_input("Notes (optional)")
        if st.form_submit_button("Save Feedback"):
            db.save_job_feedback(
                job_id=job_row.get("job_id", ""),
                company=job_row.get("company", ""),
                job_title=job_row.get("job_title", ""),
                role_family=selected["role_family"],
                feedback=fb_choice,
                notes=fb_notes,
            )
            st.success("Feedback saved. Click **Recommend Jobs** again to apply it to ranking.")

    # ---- 5. Tailored resume ----------------------------------------------
    st.divider()
    st.subheader("5. Generate Tailored Resume")
    _render_resume_section(profile_text, job_row)


def page_generated_versions():
    st.header("Generated Versions")
    versions = db.get_resume_versions()
    if not versions:
        st.info("No saved resume versions yet. Generate and save one on the Job Matching page.")
        return

    summary = pd.DataFrame(
        [
            {
                "id": v.get("id"),
                "created_at": v.get("created_at", ""),
                "company": v.get("company", ""),
                "job_title": v.get("job_title", ""),
                "target_title": v.get("target_title", ""),
                "match_score": v.get("match_score", 0.0),
                "feedback_text": v.get("feedback_text", "") or "",
            }
            for v in versions
        ]
    )
    st.dataframe(summary, width="stretch", hide_index=True)

    ids = [v["id"] for v in versions]
    selected_id = st.selectbox("View saved version", options=ids)
    version = db.get_resume_version(selected_id)
    if version:
        st.caption(
            f"{version['company']} — {version['job_title']} | {version['target_title']} | "
            f"score {version['match_score']} | {version['created_at']}"
        )
        if version["feedback_text"]:
            st.write(f"**Feedback used:** {version['feedback_text']}")
        st.text_area("Resume Text", value=version["resume_text"], height=500)
        st.download_button(
            "Download TXT",
            data=version["resume_text"].encode("utf-8"),
            file_name=f"resume_version_{version['id']}.txt",
            mime="text/plain",
        )


def _flash(message):
    """Store a one-time success message and rerun so tables/metrics refresh."""
    st.session_state["app_flash"] = message
    st.rerun()


def page_application_tracker():
    st.header("Application Tracker")

    # Show any one-time message left over from the previous action.
    pending = st.session_state.pop("app_flash", None)
    if pending:
        st.success(pending)

    apps = db.get_applications()

    # --- Summary metrics ---------------------------------------------------
    def _count(status):
        return sum(1 for a in apps if (a.get("status") or "") == status)

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Total Applications", len(apps))
    m2.metric("Saved", _count("Saved"))
    m3.metric("Applied", _count("Applied"))
    m4.metric("Interview", _count("Interview"))
    m5.metric("Rejected / Closed", _count("Rejected") + _count("Closed"))

    st.divider()

    # --- Manual add form ---------------------------------------------------
    with st.form("add_application"):
        st.subheader("Add Application Record")
        company = st.text_input("Company")
        job_title = st.text_input("Job Title")
        job_url = st.text_input("Job URL")
        status = st.selectbox("Status", STATUS_OPTIONS)
        application_date = st.date_input("Application Date", value=date.today())
        notes = st.text_area("Notes")
        submitted = st.form_submit_button("Add Application")
        if submitted:
            if not company and not job_title:
                st.warning("Please enter at least a company or job title.")
            else:
                db.add_application(
                    company=company,
                    job_title=job_title,
                    job_url=job_url,
                    status=status,
                    application_date=str(application_date),
                    notes=notes,
                )
                _flash("Application record added.")

    st.divider()

    # --- Batch upload ------------------------------------------------------
    st.subheader("Batch Upload Applications")
    st.caption("Upload a CSV with columns: " + ", ".join(APPLICATION_COLUMNS))

    template_csv = pd.DataFrame(columns=APPLICATION_COLUMNS).to_csv(index=False)
    st.download_button(
        "Download CSV Template",
        data=template_csv.encode("utf-8"),
        file_name="applications_template.csv",
        mime="text/csv",
    )

    uploaded = st.file_uploader("Upload applications CSV", type=["csv"])
    if uploaded is not None:
        try:
            upload_df = pd.read_csv(uploaded, dtype=str).fillna("")
        except Exception as exc:
            st.error(f"Could not read CSV: {exc}")
            upload_df = None

        if upload_df is not None:
            missing = [c for c in APPLICATION_COLUMNS if c not in upload_df.columns]
            if missing:
                st.error(f"Missing required columns: {', '.join(missing)}")
            else:
                st.write("Preview:")
                st.dataframe(
                    upload_df[APPLICATION_COLUMNS], width="stretch", hide_index=True
                )
                if st.button("Save Uploaded Applications"):
                    records = upload_df[APPLICATION_COLUMNS].to_dict("records")
                    saved = db.add_applications_bulk(records)
                    _flash(f"Saved {saved} application records.")

    st.divider()

    # --- All applications (with status filter) -----------------------------
    st.subheader("All Applications")
    if not apps:
        st.info("No application records yet.")
        return

    filter_status = st.selectbox("Filter by status", ["All"] + STATUS_OPTIONS)
    filtered = (
        apps
        if filter_status == "All"
        else [a for a in apps if (a.get("status") or "") == filter_status]
    )

    if not filtered:
        st.info(f"No applications with status '{filter_status}'.")
    else:
        df = pd.DataFrame(filtered)
        display_cols = [
            "id",
            "company",
            "job_title",
            "status",
            "application_date",
            "job_url",
            "notes",
            "created_at",
        ]
        df = df[[c for c in display_cols if c in df.columns]]
        st.dataframe(df, width="stretch", hide_index=True)

    st.divider()

    # --- Update status / notes --------------------------------------------
    st.subheader("Update Status / Notes")
    app_ids = [a["id"] for a in apps]
    selected = st.selectbox("Select application id", options=app_ids)
    current = next((a for a in apps if a["id"] == selected), None)
    if current:
        current_status = current.get("status") or STATUS_OPTIONS[0]
        status_index = (
            STATUS_OPTIONS.index(current_status)
            if current_status in STATUS_OPTIONS
            else 0
        )
        new_status = st.selectbox("New status", STATUS_OPTIONS, index=status_index)
        new_notes = st.text_area("New notes", value=current.get("notes", "") or "")
        if st.button("Update Record"):
            db.update_application(selected, new_status, new_notes)
            _flash("Record updated.")


def page_readme():
    st.header("Project README")
    st.markdown(load_readme())


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    st.set_page_config(page_title="JobPilot", page_icon="🧭", layout="wide")
    db.init_db()

    st.sidebar.title("JobPilot")
    st.sidebar.caption("AI Resume Tailoring & Application Tracker")
    page = st.sidebar.radio(
        "Navigation",
        [
            "Candidate Profile",
            "Job Matching",
            "Generated Versions",
            "Application Tracker",
            "Project README",
        ],
    )

    if page == "Candidate Profile":
        page_candidate_profile()
    elif page == "Job Matching":
        page_job_matching()
    elif page == "Generated Versions":
        page_generated_versions()
    elif page == "Application Tracker":
        page_application_tracker()
    elif page == "Project README":
        page_readme()


if __name__ == "__main__":
    main()
