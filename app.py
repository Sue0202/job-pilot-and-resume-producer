"""JobPilot: AI Resume Tailoring and Application Tracker.

A Streamlit MVP that matches sample job postings against a candidate master
profile, generates a tailored resume (rule-based), exports DOCX/TXT, and tracks
generated versions and manual applications in SQLite.

Run locally:
    pip install -r requirements.txt
    streamlit run app.py
"""

import json
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

import analytics
import database as db
import docx_export
import experience_translation as xt
import jd_analyzer
import matching
import resume_generator as rg
import test_personas

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
# Expanded for the real job-search workflow; old values remain compatible.
STATUS_OPTIONS = [
    "Saved", "Analyzed", "Need Evidence", "Ready to Apply", "Applied",
    "Recruiter Screen", "Interview", "Offer", "Rejected", "Closed",
]
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

class ProfileSafetyError(Exception):
    """Raised when something tries to write a test-persona profile to the master file."""


def looks_like_test_persona(text):
    """Heuristic guard: detect the tab-separated test-persona format.

    Test personas use lines like 'Background\\t...', 'Target Roles\\t...',
    'Dealbreakers\\t...'. The real master profile is markdown with a
    'Name: ...' header and PROFESSIONAL EXPERIENCE / EDUCATION sections.
    """
    low = (text or "").lower()
    persona_markers = ("background\t", "target roles\t", "dealbreakers\t")
    if any(m in low for m in persona_markers):
        return True
    if "senior software engineer, 7 years in fintech" in low:
        return True
    return False


def _active_profile_name(text=None):
    """Parse the active candidate name from the master profile, for display/guarding."""
    if text is None:
        text = load_profile_text()
    for line in text.splitlines():
        s = line.strip().lstrip("-").strip()
        if s.lower().startswith("name:"):
            return s.split(":", 1)[1].strip()
    return "Unknown"


def load_profile_text():
    if not PROFILE_PATH.exists():
        PROFILE_PATH.write_text(DEFAULT_PROFILE_TEXT, encoding="utf-8")
    return PROFILE_PATH.read_text(encoding="utf-8")


def save_profile_text(text):
    """Persist the master profile. Refuses test-persona content as a safety guard.

    This is only ever called from explicit Candidate Profile actions (edit/upload);
    no test/demo/analysis flow calls it. The guard is a second line of defense so a
    persona/sample can never silently become the master profile.
    """
    if looks_like_test_persona(text):
        raise ProfileSafetyError(
            "Refused to save: the content looks like a test-persona / sample profile, "
            "not the candidate master profile."
        )
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


# Dense embeddings are expensive; build once per dataset and cache the index as a
# resource. Returns None if the dense backend is unavailable (graceful fallback).
@st.cache_resource(show_spinner="Building dense embeddings (first time only)...")
def _get_dense_index(dataset_label, n_rows):
    jobs, _ = load_jobs()
    # Cap dense indexing to the interactive 3K dataset size for responsiveness.
    return matching.build_embedding_index(jobs, max_rows=3000)


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

SOURCE_OPTIONS = ["LinkedIn", "Company website", "Referral", "Handshake", "Indeed", "Other"]

SCORE_FEEDBACK_REASONS = [
    "Missed transferable experience",
    "Overestimated my experience",
    "Missed a hard requirement",
    "Weighted tools too heavily",
    "Weighted industry/domain too heavily",
    "Ignored sponsorship risk",
    "Other",
]

DECISION_STYLE = {
    "High Priority": ("#0b8043", "🟢"),
    "Apply with Tailoring": ("#1a73e8", "🔵"),
    "Apply Selectively": ("#1a73e8", "🔵"),
    "Maybe - Needs More Evidence": ("#f29900", "🟠"),
    "Skip": ("#d93025", "🔴"),
}


def _render_decision(decision):
    color, icon = DECISION_STYLE.get(decision, ("#5f6368", "⚪"))
    st.markdown(
        f"<div style='font-size:1.3rem;font-weight:700;color:{color};'>"
        f"{icon} {decision}</div>",
        unsafe_allow_html=True,
    )


# Plain-language explanation of each decision (shown on the summary card).
DECISION_BLURB = {
    "High Priority": "Strong evidence supports an application.",
    "Apply with Tailoring": "Good transferable fit, but tailor your positioning.",
    "Apply Selectively": (
        "Transferable systems-delivery experience is strong, but enterprise-domain gaps "
        "remain — apply only if the role values adaptable operators."
    ),
    "Maybe - Needs More Evidence": "Consider applying only if you can add credible evidence.",
    "Skip": "Material requirements or constraints are not currently supported.",
}

# ---------------------------------------------------------------------------
# Navigation + theme (workflow-oriented information architecture)
# ---------------------------------------------------------------------------

# Product-oriented sidebar. The active navigation focuses on the personal
# job-search workflow; course-project tools are preserved behind an "Advanced"
# expander (not removed, not required at runtime).
NAV_GROUPS = [
    ("Workspace", [
        ("Home", "🏠"),
        ("Analyze Job", "🎯"),
        ("Applications", "📋"),
        ("Resume Library", "📄"),
        ("Evidence Library", "🗂️"),
    ]),
    ("Settings", [
        ("Candidate Profile", "👤"),
    ]),
]

# Preserved but hidden from the primary workflow navigation.
ADVANCED_PAGES = [
    ("Job Matching", "🔎"),
    ("Insights", "📊"),
    ("Test Personas", "🧪"),
    ("Project README", "📘"),
]

_THEME_CSS = """
<style>
/* Constrain content width for readability on wide desktops. */
.block-container { max-width: 1180px; padding-top: 2.2rem; padding-bottom: 3rem; }
/* Tighter, clearer type hierarchy. */
h1 { font-weight: 700; letter-spacing: -0.01em; }
h2 { font-weight: 650; margin-top: 0.4rem; }
h3 { font-weight: 600; }
/* Sidebar nav buttons read as a list, not chunky controls. */
section[data-testid="stSidebar"] .stButton > button {
    text-align: left;
    justify-content: flex-start;
    font-weight: 500;
    border: 1px solid transparent;
    padding: 0.35rem 0.6rem;
}
section[data-testid="stSidebar"] .stButton > button:hover {
    border-color: #d7dce3;
    background: #eef2f7;
}
/* Subtle separation for bordered containers used as cards. */
div[data-testid="stVerticalBlockBorderWrapper"] {
    border-radius: 10px;
}
</style>
"""


def _inject_theme():
    st.markdown(_THEME_CSS, unsafe_allow_html=True)


def _go(page):
    """Navigate to a page and rerun."""
    st.session_state["nav_page"] = page
    st.rerun()


def _sidebar_nav():
    """Render grouped, workflow-oriented navigation. Returns the selected page."""
    current = st.session_state.setdefault("nav_page", "Home")
    st.sidebar.markdown("### JobPilot")
    st.sidebar.caption("Job Search Decision Support & Resume Tailoring")
    st.sidebar.divider()
    for group_title, pages in NAV_GROUPS:
        st.sidebar.caption(group_title.upper())
        for label, icon in pages:
            active = (label == current)
            if st.sidebar.button(
                f"{icon}  {label}",
                key=f"nav_{label}",
                width="stretch",
                type="primary" if active else "secondary",
            ):
                _go(label)
    # Course-project tools preserved but out of the primary workflow.
    with st.sidebar.expander("Advanced (course project)", expanded=False):
        for label, icon in ADVANCED_PAGES:
            active = (label == current)
            if st.button(
                f"{icon}  {label}",
                key=f"nav_{label}",
                width="stretch",
                type="primary" if active else "secondary",
            ):
                _go(label)
    return st.session_state["nav_page"]


def _decision_summary_card(result, fit_narrative=None):
    """High-visibility decision summary used at the top of Analyze Job results.

    Pure presentation: reads precomputed fields. Optional fit_narrative supplies
    display-calibrated base fit / decision for enterprise-systems roles.
    """
    fn = fit_narrative or {}
    base_score = fn.get("calibrated_base_fit") if fn.get("calibrated_base_fit") is not None else result["base_score"]
    role_family = result["selected_role_family"]
    rf_adjustment = db.get_calibration_adjustment(role_family)
    adjusted_score = jd_analyzer.apply_calibration(base_score, rf_adjustment)

    if fn.get("display_decision"):
        decision = fn["display_decision"]
        priority = fn.get("display_priority") or jd_analyzer.priority_for(base_score)
    else:
        decision = jd_analyzer.decision_for(adjusted_score)
        priority = jd_analyzer.priority_for(adjusted_score)

    color, icon = DECISION_STYLE.get(decision, ("#5f6368", "⚪"))

    with st.container(border=True):
        top = st.columns([1, 1, 2])
        with top[0]:
            label = "Calibrated Fit" if fn.get("calibrated_base_fit") is not None else "Base Fit Score"
            st.metric(label, f"{base_score} / 10")
        with top[1]:
            if rf_adjustment and not fn.get("display_decision"):
                st.metric("Adjusted Score", f"{adjusted_score} / 10", delta=f"{rf_adjustment:+}")
            elif fn.get("material_gap_risk"):
                st.metric("Material Gap Risk", fn["material_gap_risk"])
            else:
                st.metric("Confidence", result.get("confidence", "").replace(" confidence", ""))
        with top[2]:
            st.markdown(
                f"<div style='font-size:1.25rem;font-weight:700;color:{color};'>"
                f"{icon} {decision} &middot; {priority} Priority</div>",
                unsafe_allow_html=True,
            )
            st.write(DECISION_BLURB.get(decision, ""))
            st.caption(
                f"Confidence: {result.get('confidence', 'n/a')} · Role family: "
                f"{role_family} · Suggested angle: **{result['suggested_resume_angle']}**"
            )
        st.caption(result["scoring_explanation"])
        if fn.get("calibrated_base_fit") is not None and fn.get("calibrated_base_fit") != result["base_score"]:
            st.caption(
                f"Display calibration for enterprise domain gaps: raw base "
                f"{result['base_score']} → calibrated {fn['calibrated_base_fit']} "
                f"(component weights unchanged)."
            )
        elif rf_adjustment and not fn.get("display_decision"):
            st.caption(
                f"Calibration adjustment from prior feedback for this role family: "
                f"{rf_adjustment:+} (base {base_score} → adjusted {adjusted_score})."
            )
    return decision, priority, adjusted_score, rf_adjustment


# ---------------------------------------------------------------------------
# Pipeline status mapping (shared by Home + Applications)
# ---------------------------------------------------------------------------

# Existing stored statuses are preserved; these helpers only group them for display.
PIPELINE_BUCKETS = [
    ("Saved / To Apply", ["Saved", "Saved / To Apply", "Analyzed", "Need Evidence"]),
    ("Ready to Apply", ["Ready to Apply"]),
    ("Applied", ["Applied"]),
    ("Interview", ["Recruiter Screen", "Interview", "OA"]),
    ("Offer", ["Offer"]),
    ("Closed / Rejected", ["Rejected", "Closed"]),
]


def _pipeline_counts(apps):
    counts = {name: 0 for name, _ in PIPELINE_BUCKETS}
    for a in apps:
        status = (a.get("status") or "").strip()
        for name, members in PIPELINE_BUCKETS:
            if status in members:
                counts[name] += 1
                break
    return counts


def _applied_this_week(apps):
    """Count applications marked Applied with an applied/updated date in the last 7 days."""
    cutoff = pd.Timestamp.now() - pd.Timedelta(days=7)
    n = 0
    for a in apps:
        if (a.get("status") or "") != "Applied":
            continue
        raw = a.get("applied_date") or a.get("application_date") or a.get("updated_at") or a.get("created_at")
        ts = pd.to_datetime(raw, errors="coerce")
        if pd.notna(ts) and ts >= cutoff:
            n += 1
    return n


def _analysis_to_record(inputs, result):
    """Flatten an analyze_fit result + inputs into a DB-ready dict."""
    return {
        "company": inputs.get("company", ""),
        "job_title": inputs.get("job_title", ""),
        "apply_link": inputs.get("apply_link", ""),
        "source": inputs.get("source", ""),
        "jd_text": inputs.get("jd_text", ""),
        "notes": inputs.get("notes", ""),
        "overall_score": result.get("overall_score", 0.0),
        "decision": result.get("decision", ""),
        "selected_role_family": result.get("selected_role_family", ""),
        "suggested_resume_angle": result.get("suggested_resume_angle", ""),
        "component_scores_json": json.dumps(result.get("component_scores", {})),
        "matched_evidence_json": json.dumps(result.get("matched_evidence", [])),
        "missing_evidence_json": json.dumps(result.get("missing_evidence", [])),
        "evidence_gap_questions_json": json.dumps(result.get("evidence_gap_questions", [])),
        "red_flags_json": json.dumps(result.get("red_flags", [])),
        "recommended_positioning": result.get("recommended_positioning", ""),
        "scoring_explanation": result.get("scoring_explanation", ""),
        "added_evidence": inputs.get("added_evidence", ""),
        "base_score": result.get("base_score", result.get("overall_score", 0.0)),
        "calibrated_score": result.get("calibrated_score"),
        "priority": result.get("priority", ""),
        "confidence": result.get("confidence", ""),
        "sponsorship_feasibility": result.get("sponsorship_feasibility"),
        "temporary_added_evidence": inputs.get("added_evidence", ""),
        "evidence_reanalysis_score": result.get("evidence_reanalysis_score"),
    }


def _analyze_job_from_match(profile_text, job_row, role_family=""):
    """Run Analyze Job on a dataset job and jump to the Analyze Job page."""
    jd_text = "\n".join(
        x for x in [
            job_row.get("description", ""),
            job_row.get("responsibilities", ""),
            job_row.get("qualifications", ""),
        ] if x
    )
    inputs = {
        "company": job_row.get("company", ""),
        "job_title": job_row.get("job_title", ""),
        "apply_link": job_row.get("job_url", ""),
        "source": "Other",
        "jd_text": jd_text,
        "notes": f"From Job Matching ({role_family}).",
        "added_evidence": "",
    }
    st.session_state["analyze_inputs"] = inputs
    st.session_state["analyze_result"] = jd_analyzer.analyze_fit(jd_text, profile_text)
    for k in ("analyze_analysis_id", "analyze_show_resume", "analyze_reanalysis",
              "analyze_calibrated", "analyze_focus_evidence"):
        st.session_state.pop(k, None)
    _go("Analyze Job")


def _persist_current_analysis():
    """Save the current analysis to job_analyses once; cache id in session."""
    if st.session_state.get("analyze_analysis_id"):
        return st.session_state["analyze_analysis_id"]
    inputs = st.session_state.get("analyze_inputs", {})
    result = st.session_state.get("analyze_result")
    if not result:
        return None
    record = _analysis_to_record(inputs, result)
    analysis_id = db.save_job_analysis(record)
    st.session_state["analyze_analysis_id"] = analysis_id
    return analysis_id


def _activity_rows(rows, cols, limit=5):
    """Build a compact DataFrame from db rows for recent-activity tables."""
    out = []
    for r in rows[:limit]:
        out.append({label: r.get(key, "") for key, label in cols})
    return pd.DataFrame(out)


def page_home():
    st.title("Job Search Workspace")
    st.caption(
        "Evaluate jobs, tailor credible resumes, and keep your application pipeline "
        "organized."
    )
    st.write(
        "JobPilot evaluates fit conservatively, distinguishes **direct** evidence from "
        "**transferable** evidence, never fabricates experience, and helps you decide "
        "whether to apply **before** generating a resume — while preserving your version "
        "and application history."
    )

    analyses = db.get_job_analyses()
    apps = db.get_applications()
    versions = db.get_resume_versions()
    evidence = db.get_evidence_items()

    # ---- Primary + secondary action cards --------------------------------
    st.subheader("Start here")
    a1, a2 = st.columns([2, 1])
    with a1:
        with st.container(border=True):
            st.markdown("#### 🎯 Analyze a New Job")
            st.write(
                "Paste a job description to get a conservative fit assessment, evidence "
                "gaps, and a recommended next step."
            )
            if st.button("Analyze a New Job", type="primary", width="stretch"):
                _go("Analyze Job")
    with a2:
        with st.container(border=True):
            st.markdown("#### Quick actions")
            if st.button("Review Applications", width="stretch"):
                _go("Applications")
            if st.button("Add Evidence", width="stretch"):
                _go("Evidence Library")
            if st.button("Open Resume Library", width="stretch"):
                _go("Resume Library")

    # ---- Pipeline summary metrics ----------------------------------------
    st.subheader("Pipeline")
    counts = _pipeline_counts(apps)
    applied_week = _applied_this_week(apps)
    draft_evidence = sum(1 for e in evidence if (e.get("status") or "") == "Draft")
    m = st.columns(6)
    m[0].metric("Saved / To analyze", counts["Saved / To Apply"])
    m[1].metric("Ready to Apply", counts.get("Ready to Apply", 0))
    m[2].metric("Applied this week", applied_week)
    m[3].metric("Active interviews", counts["Interview"])
    m[4].metric("Resume versions", len(versions))
    m[5].metric("Evidence to review", draft_evidence)

    if not apps and not analyses and not versions and not evidence:
        st.info(
            "Your workspace is empty. A good first step: open **Analyze Job**, paste a "
            "job description, and review the fit assessment before tailoring a resume."
        )
        with st.container(border=True):
            st.markdown("**Suggested workflow**")
            st.markdown(
                "1. **Analyze a job** to check fit and surface evidence gaps.\n"
                "2. **Add evidence** for any gaps and verify your strongest examples.\n"
                "3. **Save promising roles** to build your pipeline.\n"
                "4. **Generate a tailored version** only after you've reviewed fit and gaps."
            )
        return

    # ---- Recent activity --------------------------------------------------
    st.subheader("Recent activity")
    r1, r2 = st.columns(2)
    with r1:
        st.markdown("**Recent job analyses**")
        if analyses:
            df = _activity_rows(
                analyses,
                [("company", "Company"), ("job_title", "Title"),
                 ("base_score", "Score"), ("decision", "Decision")],
            )
            st.dataframe(df, width="stretch", hide_index=True)
        else:
            st.caption("No analyses yet — start by analyzing a job description.")
    with r2:
        st.markdown("**Recent applications**")
        if apps:
            df = _activity_rows(
                apps,
                [("company", "Company"), ("job_title", "Title"),
                 ("status", "Status"), ("application_date", "Date")],
            )
            st.dataframe(df, width="stretch", hide_index=True)
        else:
            st.caption("No applications yet — save promising roles to build your pipeline.")

    r3, r4 = st.columns(2)
    with r3:
        st.markdown("**Recent resume versions**")
        if versions:
            df = _activity_rows(
                versions,
                [("company", "Company"), ("job_title", "Title"),
                 ("selected_angle", "Angle"), ("match_score", "Score"),
                 ("created_at", "Created")],
            )
            st.dataframe(df, width="stretch", hide_index=True)
        else:
            st.caption("No resume versions yet — generate one after reviewing fit and gaps.")
    with r4:
        st.markdown("**Evidence waiting for review**")
        drafts = [e for e in evidence if (e.get("status") or "") == "Draft"]
        if drafts:
            df = _activity_rows(
                drafts,
                [("title", "Title"), ("company", "Company"), ("category", "Category")],
            )
            st.dataframe(df, width="stretch", hide_index=True)
        else:
            st.caption("No draft evidence to review.")


def page_analyze_job():
    st.header("Analyze Job")
    st.caption(
        "Paste one job description, see how your verified experience maps, then translate "
        "and tailor — or save to your tracker. Your master profile is never overwritten."
    )

    profile_text = load_profile_text()

    # ---- Stage 1: Job Input ----------------------------------------------
    st.subheader("1. Job Input")
    with st.form("analyze_job_form"):
        c1, c2 = st.columns(2)
        with c1:
            company = st.text_input("Company", key="aj_company")
            apply_link = st.text_input("Application URL", key="aj_link")
            location = st.text_input("Location", key="aj_location")
        with c2:
            job_title = st.text_input("Job title", key="aj_title")
            source = st.selectbox("Source (optional)", SOURCE_OPTIONS, key="aj_source")
            angle_choice = st.selectbox("Target-role angle", TARGET_ANGLE_OPTIONS, key="aj_angle")
        custom_angle = st.text_input(
            "Custom angle (used only if 'Custom angle' is selected)", key="aj_custom_angle"
        )
        jd_text = st.text_area("Job description", height=240, key="aj_jd")
        notes = st.text_input("Notes (optional)", key="aj_notes")
        analyze_clicked = st.form_submit_button("Analyze Fit", type="primary")

    if analyze_clicked:
        if not jd_text.strip():
            st.warning("Please paste a job description first.")
        else:
            chosen_angle = ""
            if angle_choice == "Custom angle":
                chosen_angle = custom_angle.strip()
            elif angle_choice != "Auto (recommended)":
                chosen_angle = angle_choice
            inputs = {
                "company": company, "job_title": job_title, "apply_link": apply_link,
                "location": location, "source": source, "jd_text": jd_text,
                "notes": notes, "added_evidence": "", "angle_override": chosen_angle,
            }
            result = jd_analyzer.analyze_fit(jd_text, profile_text)
            # Optional UI-level angle override (does not change scoring).
            if chosen_angle:
                result["auto_resume_angle"] = result.get("suggested_resume_angle", "")
                result["suggested_resume_angle"] = chosen_angle
            st.session_state["analyze_inputs"] = inputs
            st.session_state["analyze_result"] = result
            # Reset persisted-analysis + handoff state for the new analysis.
            st.session_state.pop("analyze_analysis_id", None)
            st.session_state.pop("analyze_show_resume", None)
            st.session_state.pop("analyze_reanalysis", None)
            st.session_state.pop("analyze_calibrated", None)

    result = st.session_state.get("analyze_result")
    inputs = st.session_state.get("analyze_inputs", {})
    if not result:
        st.info("Fill in the job description and click **Analyze Fit**.")
        return

    _render_analysis_results(profile_text, inputs, result)


TARGET_ANGLE_OPTIONS = [
    "Auto (recommended)",
    "Product Operations",
    "Program Management",
    "Platform Operations",
    "Live Operations / Technical Production",
    "Workflow / Business Operations",
    "Analytics-adjacent",
    "Custom angle",
]

CALIBRATION_MAGNITUDES = {"Slightly: 0.3": 0.3, "Moderately: 0.6": 0.6, "Significantly: 1.0": 1.0}

EVIDENCE_TYPES = [
    "Launch", "Program Management", "Analytics", "Support Operations",
    "Platform Operations", "Creator Operations", "Other",
]

# Human-readable note on what each evidence-quality level can affect.
EVIDENCE_QUALITY_EFFECT = {
    "Skill claim only":
        "increases Skill Fit only (no Experience Fit or Resume Evidence Strength change).",
    "Basic experience example":
        "modestly supports Skill Fit; Experience Fit and Resume Evidence Strength are not "
        "increased (no scope or outcome given).",
    "Concrete experience example":
        "supports Skill Fit and allows a small Experience Fit increase; it is still not "
        "treated as verified master-profile evidence.",
    "Outcome-backed experience example":
        "supports Skill Fit and increases Experience Fit more meaningfully; it is still "
        "not auto-saved to your master profile.",
}


def _newly_covered_skills(result, profile_text, added_text):
    """JD required/preferred skills newly covered only because of the added text."""
    parsed = result.get("parsed", {})
    required = list(parsed.get("required_skills", [])) + list(parsed.get("preferred_skills", []))
    added_low = (added_text or "").lower()
    prof_low = (profile_text or "").lower()
    out = []
    for s in required:
        already = s in jd_analyzer.CANDIDATE_SKILLS or s in prof_low
        if (s in added_low) and not already and s not in out:
            out.append(s)
    return out


def _component_table(component_scores):
    weights = jd_analyzer.WEIGHTS
    label_overrides = {"sponsorship_feasibility": "Sponsorship Feasibility"}
    return pd.DataFrame(
        [
            {
                "component": label_overrides.get(k, k.replace("_", " ").title()),
                "score (0-10)": v,
                "weight": f"{int(weights.get(k, 0) * 100)}%",
            }
            for k, v in component_scores.items()
        ]
    )


def _render_fit_narrative(narrative):
    """Display fit dimensions (presentation only — does not change scoring)."""
    with st.container(border=True):
        st.markdown("**How your experience maps to this role**")
        st.caption(narrative.get("summary_text", ""))
        m = st.columns(5)
        cap_label = narrative.get("capability_fit_metric_label", xt.CAPABILITY_FIT_METRIC_LABEL)
        cap_val = narrative.get("direct_capability_fit", narrative.get("direct_evidence_fit", 0))
        m[0].metric(cap_label, f"{cap_val}")
        m[1].metric("Transferability Fit", f"{narrative.get('transferability_fit', 0)}")
        m[2].metric("Positioning Potential", f"{narrative.get('verbal_positioning_potential', 0)}")
        risk = narrative.get("material_gap_risk", "—")
        m[3].metric("Material Gap Risk", risk)
        m[4].metric("Resume Competitiveness", f"{narrative.get('resume_competitiveness', 0)}")
        if not narrative.get("has_literal_direct_evidence") and cap_val:
            st.caption(
                f"{cap_label} reflects verified functional capabilities (workflow, systems delivery, "
                "stakeholder alignment) — not direct experience with this employer's specific "
                "enterprise systems or domain."
            )
        if risk and risk != "—":
            st.caption(
                "Material Gap Risk reflects domain, systems, and technical gaps — "
                "Low / Moderate / Significant / Major. Higher means more material gaps."
            )
        if narrative.get("show_positioning_cap_note"):
            st.caption(xt.POSITIONING_CAPTION)


def _render_what_you_have(result, profile_text, fit_narrative=None):
    """Section A: domain evidence + transferable evidence + usable skills."""
    fn = fit_narrative or {}
    st.subheader("A. What You Already Have")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Direct domain evidence**")
        st.caption(
            "Specific industry or system ownership (e.g., Workday, HRIS, ERP) — "
            "not implied by capability scores above."
        )
        if result.get("direct_evidence"):
            for e in result["direct_evidence"]:
                st.markdown(f"- {e}")
        else:
            st.caption(
                "No verified direct domain-specific evidence for this role's systems or industry. "
                "See transferable evidence below and positioning cards in Section B."
            )
        st.markdown("**Transferable evidence**")
        st.caption("Relevant experience that may need translation.")
        if result.get("adjacent_evidence"):
            for e in result["adjacent_evidence"]:
                st.markdown(f"- {e}")
        elif fn.get("direct_capability_fit", 0) > 0:
            st.caption(
                "Functional capabilities are present in your profile — surfaced via "
                f"{fn.get('capability_fit_metric_label', 'Direct Capability Fit')} and Section B."
            )
        else:
            st.caption("No adjacent evidence flagged.")
    with col2:
        st.markdown("**Existing skills & tools usable for this role**")
        parsed = result.get("parsed") or {}
        prof_low = (profile_text or "").lower()
        usable = []
        for s in (parsed.get("required_skills") or []) + (parsed.get("preferred_skills") or []):
            if s.lower() in jd_analyzer.CANDIDATE_SKILLS or s.lower() in prof_low:
                usable.append(s)
        if usable:
            st.write(", ".join(sorted(set(usable))[:12]))
        else:
            st.caption("No JD-listed tools/skills directly verified — check positioning section.")


def _render_positioning_section(cards):
    """Section B: translation cards for transferable experience."""
    st.subheader("B. What Needs Better Positioning")
    st.caption(
        "These are **positioning opportunities**, not missing experience. Your underlying "
        "work is relevant — the goal is target-industry language."
    )
    st.caption(
        "Capability match does not imply direct experience with the employer's specific "
        "systems or industry domain."
    )
    if not cards:
        st.info("No positioning translations identified for this JD with your current profile.")
        return cards
    for i, card in enumerate(cards):
        with st.container(border=True):
            cap = card.get("capability_label") or card.get("match_label", "")
            st.markdown(f"**{cap}**")
            st.markdown(f"*Original context:* {card['original_context']}")
            st.markdown(f"*Target-role interpretation:* {card['target_role_interpretation']}")
            st.markdown(f"*Resume-ready phrasing:* {card['resume_ready_phrasing']}")
            st.caption(f"**JD relevance:** {card['jd_relevance']}")
            st.caption(f"Why valid: {card.get('why_valid', '')}")
            card["selected"] = st.checkbox(
                "Include in tailoring plan",
                value=card.get("selected", True),
                key=f"pos_card_{card['mapping_id']}_{i}",
            )
    return cards


def _render_true_gaps(gap_analysis):
    """Section C: genuine gaps — not wording gaps."""
    st.subheader("C. True Gaps / Caution Flags")
    st.caption(
        "Hard requirements, domain/system gaps, and eligibility constraints — "
        "not simple wording differences."
    )
    has_any = False
    if gap_analysis.get("domain_system_gaps"):
        has_any = True
        st.markdown("**Domain / systems gaps**")
        for g in gap_analysis["domain_system_gaps"]:
            st.markdown(f"- :orange[{g['domain']}]")
            st.caption(g.get("note", ""))
    if gap_analysis.get("technical_skill_gaps"):
        has_any = True
        st.markdown("**Technical skill gaps**")
        for g in gap_analysis["technical_skill_gaps"]:
            st.markdown(f"- :orange[{g['skill']}]")
            st.caption(g.get("note", ""))
    if gap_analysis.get("required_hard_gaps"):
        has_any = True
        st.markdown("**Required hard gaps**")
        for g in gap_analysis["required_hard_gaps"]:
            st.markdown(f"- :red[{g}]")
    if gap_analysis.get("eligibility_constraints"):
        has_any = True
        st.markdown("**Eligibility / sponsorship / location constraints**")
        for g in gap_analysis["eligibility_constraints"]:
            st.markdown(f"- :red[{g}]")
    if gap_analysis.get("seniority_mismatch"):
        has_any = True
        st.markdown("**Seniority mismatch**")
        for g in gap_analysis["seniority_mismatch"]:
            st.markdown(f"- {g}")
    if gap_analysis.get("preferred_tool_gaps"):
        has_any = True
        st.markdown("**Preferred tool gaps**")
        for g in gap_analysis["preferred_tool_gaps"]:
            if g.get("has_adjacent_workflow"):
                st.markdown(f"- :orange[{g['tool']}] — tool syntax gap; adjacent workflow exists")
                st.caption(g.get("note", ""))
            else:
                st.markdown(f"- :red[{g['tool']}] — no evidence of comparable workflow")
                st.caption(g.get("note", ""))
    if gap_analysis.get("potentially_learnable_gaps"):
        has_any = True
        st.markdown("**Potentially learnable gaps**")
        for g in gap_analysis["potentially_learnable_gaps"]:
            st.markdown(f"- {g}")
    if not has_any:
        st.caption("No material true gaps detected — focus on positioning and translation.")


def _render_strengthen_your_case(profile_text, inputs, result, base_score, translation_analysis):
    """Section: Strengthen Your Case — translate / recall / add (lowest priority)."""
    st.subheader("Strengthen Your Case")
    cards = translation_analysis.get("translation_cards") or []
    recall_prompts = translation_analysis.get("recall_prompts") or xt.RECALL_PROMPTS

    tab1, tab2, tab3 = st.tabs([
        "1. Translate Existing Experience",
        "2. Recall an Unlisted Example",
        "3. Add New Evidence",
    ])

    with tab1:
        st.caption(
            "Default action: translate verified experience into target-industry language. "
            "Select which mappings to include in your tailoring plan."
        )
        if cards:
            for i, card in enumerate(cards):
                with st.container(border=True):
                    st.markdown(f"**{card['resume_ready_phrasing']}**")
                    st.caption(
                        f"{card.get('capability_label') or card['match_label']} · {card['jd_relevance']}"
                    )
                    card["selected"] = st.checkbox(
                        "Include in tailoring plan",
                        value=card.get("selected", True),
                        key=f"str_card_{card['mapping_id']}_{i}",
                    )
            if st.button("Apply selections to tailoring plan", type="primary", key="apply_tailoring"):
                st.session_state["analyze_translation_cards"] = cards
                st.session_state["analyze_show_resume"] = True
                st.success("Tailoring plan updated — scroll to resume generation.")
        else:
            st.info(
                "No automatic translations for this JD yet. Try **Recall an Unlisted Example** "
                "if you have relevant experience not captured in your profile."
            )

    with tab2:
        st.caption(
            "Guided recall — help yourself remember a real example that is not yet in your "
            "profile or Evidence Library."
        )
        for prompt in recall_prompts:
            st.markdown(f"- {prompt}")
        with st.form("recall_example_form"):
            recall_text = st.text_area(
                "Describe a real example you recall (temporary for this analysis)",
                height=120,
            )
            recall_title = st.text_input("Short title (optional)")
            if st.form_submit_button("Use for this analysis only"):
                if recall_text.strip():
                    st.session_state["analyze_temp_recall"] = {
                        "text": recall_text.strip(),
                        "title": recall_title.strip(),
                    }
                    st.success("Saved as temporary evidence for this job only.")
                else:
                    st.warning("Enter a real example first.")
        temp = st.session_state.get("analyze_temp_recall")
        if temp:
            st.caption(f"Temporary recall loaded: {temp.get('title') or temp['text'][:80]}…")
            if st.button("Re-analyze with recalled example"):
                combined = profile_text + f"\n\n## Recalled evidence (temporary)\n{temp['text']}"
                quality = jd_analyzer.classify_evidence_quality(temp["text"])
                new_result = jd_analyzer.analyze_fit(
                    inputs.get("jd_text", ""), combined, added_evidence_quality=quality,
                )
                st.session_state["analyze_reanalysis"] = {
                    "added": temp["text"], "ev_type": "Recalled example",
                    "result": new_result, "quality": quality,
                    "title": temp.get("title", ""), "company": "",
                    "action": temp["text"], "outcome": "", "gap_type": "Recall",
                }
                st.rerun()

    with tab3:
        st.warning(
            "Only add real experience you have not recorded yet. Do not create new experience "
            "to fit the JD."
        )
        _render_evidence_reanalysis(profile_text, inputs, result, base_score)


def _render_analysis_results(profile_text, inputs, result):
    base_score = result["base_score"]
    jd_text = inputs.get("jd_text", "")
    evidence_items = db.get_evidence_items()
    translation_analysis = xt.analyze_translation(
        profile_text, jd_text, result, evidence_items,
        target_angle=inputs.get("angle_override") or result.get("suggested_resume_angle", ""),
    )
    # Apply resolved role family / angle for business-systems JDs (display only).
    result = dict(result)
    resolved = translation_analysis.get("resolved_role_family")
    if resolved:
        result["selected_role_family"] = resolved
    if resolved == xt.BS_ROLE_FAMILY:
        result["suggested_resume_angle"] = "Product Operations & Business Systems"
    role_family = result["selected_role_family"]
    st.session_state.setdefault("analyze_translation_cards", translation_analysis["translation_cards"])

    # ---- Stage 2: Decision Summary ---------------------------------------
    st.subheader("2. Decision Summary")
    decision, priority, adjusted_score, rf_adjustment = _decision_summary_card(
        result, fit_narrative=translation_analysis["fit_narrative"],
    )
    _render_fit_narrative(translation_analysis["fit_narrative"])

    # ---- Stage 3: Evidence mapping (A / B / C) -----------------------------
    st.subheader("3. How Your Experience Maps")
    _render_what_you_have(result, profile_text, fit_narrative=translation_analysis["fit_narrative"])
    cards = _render_positioning_section(st.session_state["analyze_translation_cards"])
    st.session_state["analyze_translation_cards"] = cards
    _render_true_gaps(translation_analysis["gap_analysis"])

    with st.expander("Component scores & recommended positioning"):
        st.dataframe(
            _component_table(result["component_scores"]), width="stretch", hide_index=True
        )
        st.markdown("**Recommended resume positioning**")
        st.markdown(result["recommended_positioning"])

    # ---- Stage 4: Recommended Action -------------------------------------
    st.subheader("4. Recommended Action")
    primary_label, primary_target, primary_hint = translation_analysis["primary_action"]
    st.caption(primary_hint)

    ac1, ac2, ac3 = st.columns([2, 1, 1])
    with ac1:
        if st.button(f"▶ {primary_label}", type="primary", width="stretch", key="aj_primary_action"):
            if primary_target == "resume":
                st.session_state["analyze_show_resume"] = True
            elif primary_target == "strengthen":
                st.session_state["analyze_focus_strengthen"] = True
            else:
                _save_job_to_tracker(inputs, result, decision, priority, base_score, role_family)
    with ac2:
        if st.button("Save Job to Tracker", width="stretch", key="aj_save_secondary"):
            _save_job_to_tracker(inputs, result, decision, priority, base_score, role_family)
    with ac3:
        if st.button("Generate Resume", width="stretch", key="aj_gen_secondary"):
            st.session_state["analyze_show_resume"] = True

    # ---- Resume generation (verified material only) ----------------------
    if st.session_state.get("analyze_show_resume"):
        with st.container(border=True):
            angle = result["suggested_resume_angle"]
            cards_for_plan = st.session_state.get("analyze_translation_cards") or []
            plan = xt.build_tailoring_plan(result, cards_for_plan, angle=angle, jd_text=jd_text)
            st.markdown("**Tailoring Plan**")
            st.caption(f"Positioning angle: **{plan['positioning_angle']}**")
            if plan["top_evidence"]:
                st.markdown("**Top evidence selected:**")
                for c in plan["top_evidence"]:
                    st.markdown(f"- {c['resume_ready_phrasing'][:120]}…")
            if plan["jd_themes"]:
                st.caption("JD themes to emphasize: " + ", ".join(plan["jd_themes"]))
            if plan["jd_language_to_mirror"]:
                st.caption("JD language to mirror: " + ", ".join(plan["jd_language_to_mirror"]))
            if plan["true_gaps_not_overstated"]:
                st.caption("Will not overstate: " + "; ".join(plan["true_gaps_not_overstated"][:4]))
            job_row = {
                "job_id": "analyze_" + (inputs.get("company", "") + "_" + inputs.get("job_title", "")).replace(" ", "_")[:40],
                "company": inputs.get("company", ""),
                "job_title": inputs.get("job_title", ""),
                "location": inputs.get("location", ""),
                "job_url": inputs.get("apply_link", ""),
                "description": inputs.get("jd_text", ""),
                "responsibilities": result["parsed"].get("responsibilities", ""),
                "qualifications": result["parsed"].get("qualifications", ""),
            }
            _render_resume_section(
                profile_text, job_row, angle=angle, decision=decision,
                score=base_score, job_analysis_id=_persist_current_analysis(),
                translation_cards=cards_for_plan,
                tailoring_plan=plan,
            )

    # ---- Strengthen Your Case + calibration ------------------------------
    st.subheader("Refine & Calibrate")
    expand_strengthen = st.session_state.pop("analyze_focus_strengthen", False)

    with st.expander("Strengthen Your Case", expanded=expand_strengthen):
        _render_strengthen_your_case(
            profile_text, inputs, result, base_score, translation_analysis,
        )

    with st.expander("Score Calibration Feedback"):
        st.caption(
            "Records your opinion and a calibrated score. The base score is never overwritten."
        )
        with st.form("score_feedback_form"):
            fb_label = st.radio(
                "Do you agree with this score?",
                ["About right", "Too low", "Too high"], horizontal=True,
            )
            cc1, cc2 = st.columns(2)
            with cc1:
                mag_label = st.selectbox("How much should the score change?", list(CALIBRATION_MAGNITUDES))
            with cc2:
                fb_reason = st.selectbox("Reason", SCORE_FEEDBACK_REASONS)
            fb_notes = st.text_input("Notes (optional)")
            if st.form_submit_button("Save Score Feedback"):
                magnitude = CALIBRATION_MAGNITUDES[mag_label]
                sign = {"About right": 0, "Too low": 1, "Too high": -1}[fb_label]
                signed_adjustment = sign * magnitude
                calibrated = jd_analyzer.apply_calibration(base_score, signed_adjustment)
                analysis_id = _persist_current_analysis()
                db.save_score_feedback(
                    job_analysis_id=analysis_id,
                    feedback_label=fb_label,
                    reason=fb_reason,
                    notes=fb_notes,
                    base_score=base_score,
                    adjustment_magnitude=signed_adjustment,
                    calibrated_score=calibrated,
                    role_family=role_family,
                )
                st.session_state["analyze_calibrated"] = (base_score, calibrated)
                st.success(
                    f"Saved. Base Score {base_score} -> Calibrated Score {calibrated} "
                    f"(adjustment {signed_adjustment:+}). Base score unchanged."
                )
        if st.session_state.get("analyze_calibrated"):
            b, c = st.session_state["analyze_calibrated"]
            st.caption(f"Most recent calibration — Base: {b} | Calibrated: {c}")


def _save_job_to_tracker(inputs, result, decision, priority, base_score, role_family):
    analysis_id = _persist_current_analysis()
    note = (
        f"Fit base {base_score}/10 ({decision}, {priority}). "
        f"{inputs.get('notes', '')}".strip()
    )
    rid, created = db.add_or_update_application_from_analysis(
        company=inputs.get("company", ""),
        job_title=inputs.get("job_title", ""),
        job_url=inputs.get("apply_link", ""),
        status="Saved / To Apply",
        analysis_score=base_score,
        role_family=role_family,
        notes=note,
    )
    verb = "Added" if created else "Updated"
    st.success(f"{verb} in Applications (id {rid}). Analysis saved (id {analysis_id}).")


GAP_PROOF_TYPES = [
    "Tool exposure", "Direct responsibility", "Stakeholder-management example",
    "Process improvement", "Data analysis", "Launch / release ownership",
    "Outcome / metric",
]


def _render_evidence_reanalysis(profile_text, inputs, result, base_score):
    st.caption(
        "Lowest-priority option: only add real experience you have not recorded yet. "
        "Do not create new experience to fit the JD."
    )
    with st.form("reanalyze_form"):
        st.caption("Enter one real experience. Be specific: action, scope, and any outcome.")
        f1, f2 = st.columns(2)
        with f1:
            ev_title = st.text_input("Short title (optional)")
            ev_company = st.text_input("Company / project (optional)")
        with f2:
            ev_type = st.selectbox("Evidence type", EVIDENCE_TYPES)
            gap_type = st.selectbox("Proof type this addresses", GAP_PROOF_TYPES)
        added = st.text_area("Action taken (what you did, scope, stakeholders)", height=110)
        ev_outcome = st.text_input("Outcome / measurable result (only if real)")
        reanalyze = st.form_submit_button("Re-analyze with Added Evidence", type="primary")
    if reanalyze:
        if not added.strip():
            st.warning("Add some evidence text first.")
        else:
            full_text = added + ((" " + ev_outcome) if ev_outcome.strip() else "")
            combined = (
                profile_text
                + f"\n\n## Additional evidence (temporary, type: {ev_type})\n"
                + full_text
            )
            quality = jd_analyzer.classify_evidence_quality(full_text)
            new_result = jd_analyzer.analyze_fit(
                inputs.get("jd_text", ""), combined, added_evidence_quality=quality
            )
            st.session_state["analyze_reanalysis"] = {
                "added": full_text, "ev_type": ev_type, "result": new_result,
                "quality": quality, "title": ev_title, "company": ev_company,
                "action": added, "outcome": ev_outcome, "gap_type": gap_type,
            }

    reanalysis = st.session_state.get("analyze_reanalysis")
    if reanalysis:
        new_result = reanalysis["result"]
        added_text = reanalysis.get("added", "")
        quality = reanalysis.get("quality") or jd_analyzer.classify_evidence_quality(added_text)
        newly_covered = _newly_covered_skills(result, profile_text, added_text)
        new_verified = [e for e in new_result["matched_evidence"]
                        if e not in result["matched_evidence"]]

        st.markdown("**Before / After**")
        bc1, bc2 = st.columns(2)
        bc1.metric("Base score before", f"{base_score}")
        bc2.metric("New score after", f"{new_result['base_score']}",
                   delta=f"{round(new_result['base_score'] - base_score, 1):+}")

        st.markdown(f"**Temporary evidence quality:** {quality}")
        st.caption("This evidence " + EVIDENCE_QUALITY_EFFECT.get(quality, ""))

        oc1, oc2 = st.columns(2)
        with oc1:
            st.markdown("**A. New JD requirements covered by added evidence**")
            if newly_covered:
                for s in newly_covered:
                    st.markdown(f"- {s}")
            else:
                st.caption("None — added text did not cover any new JD requirement.")
        with oc2:
            st.markdown("**B. New verified evidence items matched**")
            st.markdown(f"Count: **{len(new_verified)}**")
            for e in new_verified:
                st.markdown(f"- {e}")

        st.caption(
            "Temporary added evidence can improve skill coverage without becoming verified "
            "resume evidence. It does not automatically increase Experience Fit or Resume "
            "Evidence Strength unless it includes a concrete, relevant experience example."
        )

        before = result["component_scores"]
        after = new_result["component_scores"]
        delta_df = pd.DataFrame(
            [
                {
                    "component": k.replace("_", " ").title(),
                    "before": before.get(k),
                    "after": after.get(k),
                    "change": round((after.get(k, 0) - before.get(k, 0)), 1),
                }
                for k in after
            ]
        )
        st.dataframe(delta_df, width="stretch", hide_index=True)

        # ---- Why changed -------------------------------------------------
        st.markdown("**Why changed**")
        reasons = []
        if after.get("skill_fit", 0) > before.get("skill_fit", 0):
            covered_txt = ", ".join(newly_covered) if newly_covered else "JD-required skills"
            reasons.append(
                f"Skill Fit increased because temporary evidence mentions {covered_txt}, "
                "which the JD requires."
            )
        elif newly_covered:
            reasons.append(
                "Added evidence covered " + ", ".join(newly_covered) +
                ", though overall Skill Fit was already near its ceiling."
            )
        exp_delta = round(after.get("experience_fit", 0) - before.get("experience_fit", 0), 1)
        if exp_delta > 0:
            reasons.append(
                f"Experience Fit increased by {exp_delta:+} because the evidence reads as a "
                f"{quality.lower()}."
            )
        if quality in ("Skill claim only", "Basic experience example"):
            reasons.append(
                f"As a {quality.lower()}, it did not raise Experience Fit or Resume Evidence "
                "Strength — add scope (stakeholders, deliverable, workflow) or a measurable "
                "outcome to do that."
            )
        elif quality == "Concrete experience example":
            reasons.append(
                "Resume Evidence Strength was not changed: a concrete example still is not "
                "verified master-profile evidence until you save it."
            )
        elif quality == "Outcome-backed experience example":
            reasons.append(
                "Resume Evidence Strength was not auto-changed: even outcome-backed text stays "
                "temporary until you explicitly save it to the Evidence Library."
            )
        if abs(new_result["base_score"] - base_score) < 0.05 and not newly_covered and exp_delta == 0:
            reasons.append("No JD requirement was newly covered, so the score is essentially unchanged.")
        for r in reasons:
            st.markdown(f"- {r}")

        # ---- Explicit save choice (nothing is auto-saved) ----------------
        st.markdown("**Save this evidence?**")
        st.caption(
            "Temporary evidence is used only for this re-analysis unless you explicitly "
            "save it. Saved items go to the Evidence Library; only **Verified** items are "
            "eligible for resume generation. Your master profile is never changed."
        )
        ev_record = {
            "title": reanalysis.get("title") or (added_text[:60]),
            "company": reanalysis.get("company", ""),
            "role_context": reanalysis.get("gap_type", ""),
            "category": reanalysis.get("ev_type", ""),
            "action": reanalysis.get("action", added_text),
            "outcome": reanalysis.get("outcome", ""),
            "raw_notes": added_text,
            "bullet_draft": "",
            "tags": "",
            "source_job_analysis_id": st.session_state.get("analyze_analysis_id"),
        }
        sv1, sv2, sv3 = st.columns(3)
        with sv1:
            if st.button("Use only for this analysis", width="stretch"):
                st.info("Kept temporary — nothing saved.")
        with sv2:
            if st.button("Save as Draft Evidence", width="stretch"):
                nid = db.save_evidence_item({**ev_record, "status": "Draft"})
                st.success(f"Saved as Draft evidence (id {nid}). Review/verify it in Evidence Library.")
        with sv3:
            if st.button("Save as Verified Evidence", width="stretch", type="primary"):
                nid = db.save_evidence_item({**ev_record, "status": "Verified"})
                st.success(f"Saved as Verified evidence (id {nid}). It can now be used in resumes.")


def page_candidate_profile():
    st.header("Candidate Profile")
    st.caption("View, edit, or upload your Candidate Master Profile / Resume Material Library.")

    current_text = load_profile_text()
    active_name = _active_profile_name(current_text)
    with st.container(border=True):
        st.markdown(f"**Active profile:** {active_name}")
        st.caption(
            "This is the single verified master profile used for resume generation. Job "
            "analysis and temporary evidence never overwrite it, and test personas / demo "
            "profiles are fully isolated and can never be saved here."
        )
        if looks_like_test_persona(current_text):
            st.error(
                "This file currently looks like a TEST PERSONA, not your real profile. "
                "Restore your master profile before generating resumes."
            )

    uploaded = st.file_uploader("Upload a markdown file to replace the profile", type=["md", "txt"])
    if uploaded is not None:
        content = uploaded.read().decode("utf-8", errors="replace")
        try:
            save_profile_text(content)
            st.success("Profile replaced from uploaded file.")
            current_text = content
        except ProfileSafetyError as exc:
            st.error(str(exc))

    edited = st.text_area("Candidate Master Profile (markdown)", value=current_text, height=500)
    if st.button("Save Profile", type="primary"):
        try:
            save_profile_text(edited)
            st.success(f"Profile saved to candidate_master_profile.md (active: {_active_profile_name(edited)}).")
        except ProfileSafetyError as exc:
            st.error(str(exc))


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


RESUME_FEEDBACK_PRESETS = [
    "Stronger product ops angle",
    "Emphasize analytics",
    "Reduce gaming jargon",
    "More program-management framing",
    "More concise",
    "Too generic",
    "Too technical",
    "Too senior",
    "Too junior",
]


def _render_resume_section(profile_text, job_row, angle="", decision="", score=None,
                           job_analysis_id=None, translation_cards=None, tailoring_plan=None):
    """Match the selected job, then generate / download / save a tailored resume.

    Resume state is keyed by job_id so switching jobs does not show stale output.
    Verified Evidence Library items and user-approved translation mappings can be
    explicitly included; temporary/unverified evidence is never used here.
    """
    job_id = str(job_row.get("job_id", ""))
    translation_cards = translation_cards or []

    # Full match result for resume generation (cached per job in session).
    mr_key = f"match_result_{job_id}"
    if mr_key not in st.session_state:
        st.session_state[mr_key] = matching.match_job_to_candidate(profile_text, job_row)
    result = st.session_state[mr_key]

    _render_match_result(result)

    st.markdown("**Tailored Resume**")
    st.caption(
        "Generated resumes use your verified master profile, selected Verified Evidence "
        "items, and approved translation mappings. Unverified / temporary evidence is "
        "never used."
    )

    # ---- Verified evidence selection -------------------------------------
    verified = db.get_verified_evidence()
    chosen_ev = []
    if verified:
        labels = {f"#{e['id']} {e.get('title') or e.get('company') or 'evidence'}": e for e in verified}
        picked = st.multiselect(
            "Include verified evidence items", list(labels),
            default=list(labels), key=f"resume_ev_{job_id}",
        )
        chosen_ev = [labels[p] for p in picked]
    else:
        st.caption("No verified evidence items yet (Evidence Library). Using master profile only.")

    approved_cards = [c for c in translation_cards if c.get("selected")]
    if approved_cards:
        st.caption(f"{len(approved_cards)} approved translation mapping(s) will be included.")

    # ---- Structured + free-text feedback (remembered preferences) --------
    remembered = [p["preference"] for p in db.get_preference_feedback("resume")
                  if p.get("preference") in RESUME_FEEDBACK_PRESETS]
    remembered = list(dict.fromkeys(remembered))  # de-dup, keep order
    fb_presets = st.multiselect(
        "Refinement preferences (optional)", RESUME_FEEDBACK_PRESETS,
        default=[r for r in remembered if r],
        key=f"resume_fb_presets_{job_id}",
    )
    if remembered:
        st.caption("Applied remembered resume preferences: " + ", ".join(remembered))
    if fb_presets and st.button("Remember these preferences", key=f"remember_prefs_{job_id}"):
        for p in fb_presets:
            db.save_preference_feedback("resume", p, role_family=angle or "")
        st.success("Saved. These preferences will pre-apply to future resumes.")
    feedback_text = st.text_area(
        "Free-text refinement request (optional)",
        value="",
        placeholder="e.g. make it more platform operations focused, or add more support escalation",
        key=f"resume_feedback_input_{job_id}",
    )

    colg1, colg2 = st.columns(2)
    with colg1:
        gen_clicked = st.button("Generate Resume", key=f"gen_{job_id}", type="primary")
    with colg2:
        regen_clicked = st.button("Regenerate with Feedback (new version)", key=f"regen_{job_id}")

    data_key = f"resume_data_{job_id}"
    fb_key = f"resume_feedback_{job_id}"
    if gen_clicked or regen_clicked:
        # Combine verified profile + evidence + approved translations (never temp evidence).
        material = profile_text + _evidence_to_material(chosen_ev)
        material += xt.approved_mappings_to_material(approved_cards)
        fb_parts = list(fb_presets)
        if angle:
            fb_parts.append(f"angle: {angle}")
        if tailoring_plan and tailoring_plan.get("jd_language_to_mirror"):
            fb_parts.append("mirror JD terms: " + ", ".join(tailoring_plan["jd_language_to_mirror"][:4]))
        if regen_clicked and feedback_text.strip():
            fb_parts.append(feedback_text.strip())
        fb = "; ".join(fb_parts)
        st.session_state[data_key] = rg.generate_resume(material, job_row, result, fb)
        st.session_state[fb_key] = fb
        st.session_state[f"resume_ev_used_{job_id}"] = [e["id"] for e in chosen_ev]
        st.session_state[f"resume_maps_used_{job_id}"] = [
            c["mapping_id"] for c in approved_cards
        ]
        if angle:
            st.session_state[data_key]["target_title"] = angle

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
    st.caption("✓ Generated from verified material only — no fabricated experience.")

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
                jd_snapshot=(job_row.get("description", "") or "")[:2000],
                selected_angle=angle or resume_data.get("target_title", ""),
                decision_at_generation=decision,
                score_at_generation=score,
                evidence_used_json=json.dumps(st.session_state.get(f"resume_ev_used_{job_id}", [])),
                job_analysis_id=job_analysis_id,
            )
            st.success(f"Saved as a new resume version (id {new_id}). Earlier versions are kept.")


METHOD_BLURBS = {
    "TF-IDF baseline": "Keyword-based lexical similarity.",
    "Dense embedding retrieval": "Semantic similarity using embeddings.",
    "Hybrid ranking": "Combines semantic, lexical, keyword coverage, and feedback.",
}


def page_job_matching():
    st.header("Job Matching")
    st.caption("Rank dataset jobs against your verified profile, then analyze or save them.")

    jobs, dataset_label = load_jobs()
    if jobs.empty:
        st.warning(
            "No job dataset found. Run `python3 preprocess_jobs.py` to build the "
            "processed dataset, or add `sample_jobs.csv`."
        )
        return

    profile_text = load_profile_text()

    # ---- 1. Filters + ranking method (compact panel) ----------------------
    with st.container(border=True):
        c1, c2, c3 = st.columns(3)
        with c1:
            keyword = st.text_input("Keyword search", placeholder="e.g. operations, support")
        with c2:
            location = st.text_input("Location contains", placeholder="e.g. San Francisco")
        with c3:
            families = sorted([f for f in jobs["role_family"].unique() if str(f).strip()])
            selected_families = st.multiselect("Role family", families)
        st.caption(f"Dataset: **{dataset_label}** — {len(jobs)} jobs")

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

    cm1, cm2 = st.columns([2, 1])
    with cm1:
        method_label = st.selectbox(
            "Ranking method",
            ["TF-IDF baseline", "Dense embedding retrieval", "Hybrid ranking"],
        )
        st.caption(METHOD_BLURBS.get(method_label, ""))
    with cm2:
        top_n = st.slider("Recommendations", 5, 50, 25)
    method = {
        "TF-IDF baseline": "tfidf",
        "Dense embedding retrieval": "dense",
        "Hybrid ranking": "hybrid",
    }[method_label]

    if st.button("Recommend Jobs", type="primary"):
        feedback_rows = db.get_job_feedback()
        dense_index = None
        if method in ("dense", "hybrid"):
            dense_index = _get_dense_index(dataset_label, len(jobs))
            if dense_index is None:
                st.warning(
                    "Dense embeddings unavailable (sentence-transformers not installed "
                    "or model download failed). Falling back to TF-IDF baseline."
                )
        ranked = matching.rank_jobs(
            profile_text,
            filtered.head(RANK_CAP).to_dict("records"),
            feedback_rows=feedback_rows,
            top_n=top_n,
            method=method,
            dense_index=dense_index,
        )
        st.session_state["ranked_jobs"] = ranked

    ranked = st.session_state.get("ranked_jobs")
    if not ranked:
        st.info("Set filters and click **Recommend Jobs** to see ranked recommendations.")
        return

    # ---- 2. Recommendations table (with explain columns) -----------------
    st.divider()
    method_used = ranked[0].get("method_used", "tfidf")
    st.subheader("2. Top Recommended Jobs")
    st.caption(f"Ranking method used: **{method_used}**")
    table = pd.DataFrame(
        [
            {
                "rank": r["rank"],
                "match_score": r["match_score"],
                "dense_score": r.get("dense_score") if r.get("dense_score") is not None else "",
                "tfidf_score": r.get("tfidf_score", ""),
                "coverage_score": r.get("coverage_score", ""),
                "feedback_adj": r.get("feedback_adjustment", 0.0),
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
    st.caption(
        "Explain: match_score blends dense (when available), TF-IDF, and keyword "
        "coverage, plus a feedback adjustment."
    )
    st.download_button(
        "Download Top Jobs as CSV",
        data=table.to_csv(index=False).encode("utf-8"),
        file_name="top_recommended_jobs.csv",
        mime="text/csv",
    )

    with st.expander("Benchmark ranking methods (TF-IDF vs Dense vs Hybrid)"):
        st.caption("Runs all three methods on a sample of the filtered jobs.")
        if st.button("Run Benchmark"):
            dense_index = _get_dense_index(dataset_label, len(jobs))
            bench = matching.evaluate_ranking_methods(
                profile_text, filtered.head(400), sample_rows=400, dense_index=dense_index
            )
            st.json(bench)
            if not bench.get("dense_available"):
                st.info("Dense backend unavailable — dense/hybrid rows reflect TF-IDF fallback.")

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

    with st.container(border=True):
        st.markdown(f"**{job_row.get('job_title', '')} @ {job_row.get('company', '')}**")
        meta = (
            f"Role family: {selected['role_family']}  |  Location: "
            f"{job_row.get('location', '')}  |  Match score: {selected['match_score']}"
        )
        if job_row.get("source"):
            meta += f"  |  Source: {job_row.get('source')}"
        st.caption(meta)
        if selected.get("matched_keywords"):
            st.markdown(f"**Matched skills:** {', '.join(selected['matched_keywords'])}")
        if selected.get("missing_keywords"):
            st.markdown(f"**Important missing skills:** {', '.join(selected['missing_keywords'])}")
        if job_row.get("job_url"):
            st.markdown(f"[Job link]({job_row.get('job_url')})")

        act1, act2 = st.columns(2)
        with act1:
            if st.button("Analyze this job", type="primary", width="stretch", key=f"mt_analyze_{sel_rank}"):
                _analyze_job_from_match(profile_text, job_row, selected["role_family"])
        with act2:
            if st.button("Save to tracker", width="stretch", key=f"mt_save_{sel_rank}"):
                rid, created = db.add_or_update_application_from_analysis(
                    company=job_row.get("company", ""),
                    job_title=job_row.get("job_title", ""),
                    job_url=job_row.get("job_url", ""),
                    status="Saved / To Apply",
                    analysis_score=selected.get("match_score", 0.0),
                    role_family=selected["role_family"],
                    notes="Saved from Job Matching.",
                )
                st.success(f"{'Added' if created else 'Updated'} in Applications (id {rid}).")

    with st.expander("Full job description"):
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
    st.header("Resume Library")
    st.caption(
        "Version history of resumes tailored from your verified material. Generated "
        "resumes use verified evidence unless you explicitly save new evidence."
    )
    versions = db.get_resume_versions()
    if not versions:
        st.info(
            "No saved resume versions yet. Tailor one from **Analyze Job** (after reviewing "
            "fit) or **Job Matching**, then click *Save Generated Version*."
        )
        return

    # ---- Summary metrics --------------------------------------------------
    def _parse_dt(s):
        try:
            return pd.to_datetime(s)
        except Exception:
            return pd.NaT

    created = pd.Series([_parse_dt(v.get("created_at", "")) for v in versions])
    now = pd.Timestamp.now()
    this_week = int((created >= (now - pd.Timedelta(days=7))).sum())
    jobs_tailored = len({(v.get("company", ""), v.get("job_title", "")) for v in versions})
    mcol = st.columns(3)
    mcol[0].metric("Total resume versions", len(versions))
    mcol[1].metric("Created this week", this_week)
    mcol[2].metric("Jobs with tailored resumes", jobs_tailored)

    # ---- Filters ----------------------------------------------------------
    with st.container(border=True):
        f1, f2, f3 = st.columns(3)
        with f1:
            companies = sorted({v.get("company", "") for v in versions if v.get("company")})
            company_filter = st.selectbox("Company", ["All"] + companies)
        with f2:
            angles = sorted({v.get("target_title", "") for v in versions if v.get("target_title")})
            angle_filter = st.selectbox("Target role / angle", ["All"] + angles)
        with f3:
            search = st.text_input("Search keyword", placeholder="company, title, or angle")

    def _match(v):
        if company_filter != "All" and v.get("company", "") != company_filter:
            return False
        if angle_filter != "All" and v.get("target_title", "") != angle_filter:
            return False
        if search:
            blob = " ".join(str(v.get(k, "")) for k in ("company", "job_title", "target_title")).lower()
            if search.lower() not in blob:
                return False
        return True

    filtered = [v for v in versions if _match(v)]
    st.caption(f"{len(filtered)} of {len(versions)} versions match the current filters.")

    summary = pd.DataFrame(
        [
            {
                "id": v.get("id"),
                "created_at": v.get("created_at", ""),
                "company": v.get("company", ""),
                "job_title": v.get("job_title", ""),
                "angle": v.get("target_title", ""),
                "fit_score": v.get("match_score", 0.0),
                "feedback_used": "Yes" if (v.get("feedback_text") or "").strip() else "—",
            }
            for v in filtered
        ]
    )
    if summary.empty:
        st.info("No versions match the current filters.")
        return
    st.dataframe(summary, width="stretch", hide_index=True)

    # ---- Selected version detail -----------------------------------------
    st.subheader("Version detail")
    ids = [v["id"] for v in filtered]
    selected_id = st.selectbox("Select a version", options=ids)
    version = db.get_resume_version(selected_id)
    if not version:
        return
    with st.container(border=True):
        st.markdown(f"**{version['company']} — {version['job_title']}**")
        st.caption(
            f"Angle: {version['target_title']} · Fit score: {version['match_score']} · "
            f"Created: {version['created_at']}"
        )
        st.caption("✓ Generated from verified candidate evidence only.")
        if version.get("matched_keywords"):
            st.markdown(f"**Matched keywords:** {version['matched_keywords']}")
        if version.get("feedback_text"):
            st.markdown(f"**Refinement notes:** {version['feedback_text']}")
        st.text_area("Resume text", value=version["resume_text"], height=460)

        d1, d2 = st.columns(2)
        with d1:
            st.download_button(
                "Download TXT",
                data=version["resume_text"].encode("utf-8"),
                file_name=f"resume_version_{version['id']}.txt",
                mime="text/plain",
            )
        with d2:
            try:
                docx_bytes = docx_export.create_docx_from_text(
                    version["resume_text"],
                    title=f"{version['company']} — {version['job_title']}",
                )
                st.download_button(
                    "Download DOCX",
                    data=docx_bytes,
                    file_name=f"resume_version_{version['id']}.docx",
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
            except Exception as exc:  # pragma: no cover - defensive
                st.caption(f"DOCX export unavailable: {exc}")


def _flash(message):
    """Store a one-time success message and rerun so tables/metrics refresh."""
    st.session_state["app_flash"] = message
    st.rerun()


# ---------------------------------------------------------------------------
# Evidence Library (v3)
# ---------------------------------------------------------------------------

EVIDENCE_CATEGORIES = [
    "Launch / Release", "Program Management", "Analytics", "Support Operations",
    "Platform Operations", "Creator Operations", "Stakeholder Management",
    "Process Improvement", "Other",
]
EVIDENCE_TAG_OPTIONS = xt.FILTER_TAGS
EVIDENCE_STATUSES = ["Draft", "Verified", "Archived"]
PROOF_STRENGTH_OPTIONS = xt.PROOF_STRENGTHS


def _evidence_to_material(items):
    """Render verified evidence items as resume-ready text appended to the profile."""
    if not items:
        return ""
    lines = ["\n\n## Verified Evidence Library (approved by candidate)\n"]
    for e in items:
        bullet = (e.get("bullet_draft") or "").strip()
        if not bullet:
            # Compose a plain, truthful line from structured fields (no fabrication).
            parts = [p for p in [e.get("action", ""), e.get("outcome", "")] if p]
            bullet = " — ".join(parts) if parts else (e.get("title", "") or "")
        context = " ".join(p for p in [e.get("company", ""), e.get("role_context", "")] if p)
        lines.append(f"- {bullet}" + (f" ({context})" if context else ""))
    return "\n".join(lines)


def page_evidence_library():
    st.header("Evidence Library")
    st.caption(
        "Your verified, reusable experience evidence. Only **Verified** items are eligible "
        "for resume generation. Temporary re-analysis notes are never saved here "
        "automatically — you must explicitly save them."
    )

    pending = st.session_state.pop("evidence_flash", None)
    if pending:
        st.success(pending)

    items = db.get_evidence_items()

    # ---- Summary ----------------------------------------------------------
    def _count(status):
        return sum(1 for e in items if (e.get("status") or "") == status)

    m = st.columns(4)
    m[0].metric("Total", len(items))
    m[1].metric("Draft (review)", _count("Draft"))
    m[2].metric("Verified", _count("Verified"))
    m[3].metric("Archived", _count("Archived"))

    # ---- Add new evidence -------------------------------------------------
    with st.expander("Add evidence item", expanded=not items):
        with st.form("add_evidence"):
            title = st.text_input("Title")
            c1, c2 = st.columns(2)
            with c1:
                company = st.text_input("Company / project")
                time_period = st.text_input("Date / time period")
                category = st.selectbox("Category", EVIDENCE_CATEGORIES)
            with c2:
                role_context = st.text_input("Role or context")
                skills = st.text_input("Skills / tools (comma-separated)")
                status = st.selectbox("Status", EVIDENCE_STATUSES, index=0)
            original_ctx = st.text_input(
                "Original industry context (e.g., gaming / live ops framing)"
            )
            target_trans = st.text_input(
                "Target-role translation (how this reads outside gaming)"
            )
            proof_strength = st.selectbox("Proof strength", PROOF_STRENGTH_OPTIONS, index=1)
            action = st.text_area("Action taken", height=80)
            outcome = st.text_input("Outcome / metric (only if real)")
            bullet_draft = st.text_area("Resume-ready bullet draft (optional)", height=70)
            cap_tags = st.multiselect("Transferable capability tags", EVIDENCE_TAG_OPTIONS)
            raw_notes = st.text_area("Raw notes (optional)", height=70)
            if st.form_submit_button("Save to Evidence Library", type="primary"):
                if not title.strip() and not action.strip():
                    st.warning("Add at least a title or an action.")
                else:
                    db.save_evidence_item({
                        "title": title, "company": company, "role_context": role_context,
                        "time_period": time_period, "category": category, "skills": skills,
                        "action": action, "outcome": outcome, "raw_notes": raw_notes,
                        "bullet_draft": bullet_draft, "status": status,
                        "tags": ", ".join(cap_tags),
                        "original_industry_context": original_ctx,
                        "target_role_translations": target_trans,
                        "capability_tags": ", ".join(cap_tags),
                        "proof_strength": proof_strength,
                    })
                    _flash_evidence("Evidence item saved.")

    if not items:
        st.info(
            "No evidence items yet. Add your strongest, verifiable experiences here, or "
            "recall an example from **Analyze Job → Strengthen Your Case**."
        )
        return

    # ---- Filters + list ---------------------------------------------------
    with st.container(border=True):
        f1, f2, f3, f4 = st.columns(4)
        with f1:
            fstatus = st.selectbox("Status", ["All"] + EVIDENCE_STATUSES)
        with f2:
            fcat = st.selectbox("Category", ["All"] + EVIDENCE_CATEGORIES)
        with f3:
            ftag = st.selectbox("Capability tag", ["All"] + EVIDENCE_TAG_OPTIONS)
        with f4:
            fsearch = st.text_input("Search", placeholder="title, company, skills, tags")

    def _match(e):
        if fstatus != "All" and (e.get("status") or "") != fstatus:
            return False
        if fcat != "All" and (e.get("category") or "") != fcat:
            return False
        if ftag != "All":
            tag_blob = (e.get("capability_tags") or "") + (e.get("tags") or "")
            if ftag.lower() not in tag_blob.lower():
                return False
        if fsearch:
            blob = " ".join(str(e.get(k, "")) for k in
                            ("title", "company", "role_context", "skills", "tags",
                             "capability_tags", "action", "target_role_translations")).lower()
            if fsearch.lower() not in blob:
                return False
        return True

    filtered = [e for e in items if _match(e)]
    st.caption(f"{len(filtered)} of {len(items)} evidence items match.")
    if filtered:
        st.dataframe(
            pd.DataFrame([
                {"id": e["id"], "status": e.get("status", ""), "proof": e.get("proof_strength", ""),
                 "title": e.get("title", ""), "company": e.get("company", ""),
                 "category": e.get("category", ""), "tags": e.get("capability_tags") or e.get("tags", "")}
                for e in filtered
            ]),
            width="stretch", hide_index=True,
        )

    # ---- Edit / review ----------------------------------------------------
    st.subheader("Review / edit item")
    ids = [e["id"] for e in items]
    sel = st.selectbox("Select evidence id", options=ids)
    item = db.get_evidence_item(sel)
    if item:
        with st.container(border=True):
            st.markdown(f"**{item.get('title', '')}** — {item.get('company', '')}")
            st.caption(
                f"Status: {item.get('status', '')} · Proof: {item.get('proof_strength', '—')} · "
                f"Category: {item.get('category', '')}"
            )
            new_original = st.text_input(
                "Original industry context",
                value=item.get("original_industry_context", "") or "",
            )
            new_target = st.text_input(
                "Target-role translation",
                value=item.get("target_role_translations", "") or "",
            )
            new_bullet = st.text_area(
                "Resume-ready bullet draft",
                value=item.get("bullet_draft", "") or "", height=80,
            )
            cur_strength = item.get("proof_strength") or "Transferable"
            new_strength = st.selectbox(
                "Proof strength", PROOF_STRENGTH_OPTIONS,
                index=PROOF_STRENGTH_OPTIONS.index(cur_strength)
                if cur_strength in PROOF_STRENGTH_OPTIONS else 1,
            )
            cur_tags = [t.strip() for t in (item.get("capability_tags") or item.get("tags") or "").split(",") if t.strip()]
            new_tags = st.multiselect("Capability tags", EVIDENCE_TAG_OPTIONS, default=cur_tags)
            cur_status = item.get("status") or "Draft"
            new_status = st.selectbox(
                "Verification status", EVIDENCE_STATUSES,
                index=EVIDENCE_STATUSES.index(cur_status) if cur_status in EVIDENCE_STATUSES else 0,
            )
            b1, b2 = st.columns(2)
            with b1:
                if st.button("Save changes", type="primary", width="stretch"):
                    db.update_evidence_item(sel, {
                        "bullet_draft": new_bullet, "status": new_status,
                        "original_industry_context": new_original,
                        "target_role_translations": new_target,
                        "proof_strength": new_strength,
                        "capability_tags": ", ".join(new_tags),
                        "tags": ", ".join(new_tags),
                    })
                    _flash_evidence("Evidence item updated.")
            with b2:
                if st.button("Archive item", width="stretch"):
                    db.update_evidence_item(sel, {"status": "Archived"})
                    _flash_evidence("Evidence item archived.")


def _flash_evidence(message):
    st.session_state["evidence_flash"] = message
    st.rerun()


def page_application_tracker():
    st.header("Applications")
    st.caption("Your job pipeline — saved roles, submissions, and outcomes.")

    # Show any one-time message left over from the previous action.
    pending = st.session_state.pop("app_flash", None)
    if pending:
        st.success(pending)

    apps = db.get_applications()

    # --- Pipeline summary --------------------------------------------------
    counts = _pipeline_counts(apps)
    m = st.columns(7)
    m[0].metric("Total", len(apps))
    m[1].metric("Saved", counts["Saved / To Apply"])
    m[2].metric("Ready to Apply", counts["Ready to Apply"])
    m[3].metric("Applied", counts["Applied"])
    m[4].metric("Interview", counts["Interview"])
    m[5].metric("Offer", counts["Offer"])
    m[6].metric("Closed / Rejected", counts["Closed / Rejected"])

    if not apps:
        st.info(
            "No applications yet. Save promising roles from **Analyze Job** or **Job "
            "Matching** to start building your pipeline."
        )
    else:
        # --- Next actions -------------------------------------------------
        action_statuses = {"Saved", "Analyzed", "Need Evidence", "Ready to Apply",
                           "Recruiter Screen", "Interview"}
        next_actions = [a for a in apps if (a.get("status") or "") in action_statuses
                        or (a.get("next_action_date") or "").strip()]
        with st.container(border=True):
            st.markdown("**Next actions**")
            if next_actions:
                na = pd.DataFrame([
                    {"id": a["id"], "company": a.get("company", ""),
                     "job_title": a.get("job_title", ""), "status": a.get("status", ""),
                     "next_action_date": a.get("next_action_date", "")}
                    for a in next_actions[:15]
                ])
                st.dataframe(na, width="stretch", hide_index=True)
            else:
                st.caption("No open actions — everything is applied, closed, or awaiting outcome.")

        # --- Time summary (weekly) ----------------------------------------
        with st.expander("Activity over time", expanded=False):
            df_all = pd.DataFrame(apps)
            saved_dt = pd.to_datetime(df_all.get("created_at"), errors="coerce")
            saved_week = (
                saved_dt.dropna().dt.to_period("W").dt.start_time.value_counts().sort_index()
            )
            if not saved_week.empty:
                st.caption("Applications saved per week")
                st.bar_chart(saved_week)
            applied = df_all[df_all.get("status").isin(["Applied"])] if "status" in df_all else pd.DataFrame()
            if not applied.empty:
                applied_dt = pd.to_datetime(applied.get("application_date"), errors="coerce")
                applied_week = (
                    applied_dt.dropna().dt.to_period("W").dt.start_time.value_counts().sort_index()
                )
                if not applied_week.empty:
                    st.caption("Applications submitted per week")
                    st.bar_chart(applied_week)
            if saved_week.empty:
                st.caption("Not enough dated activity yet to chart.")

        # --- Filters ------------------------------------------------------
        with st.container(border=True):
            all_statuses = sorted({(a.get("status") or "").strip() for a in apps if a.get("status")})
            fr1, fr2, fr3 = st.columns(3)
            with fr1:
                filter_status = st.selectbox("Status", ["All"] + all_statuses)
            with fr2:
                companies = sorted({a.get("company", "") for a in apps if a.get("company")})
                filter_company = st.selectbox("Company", ["All"] + companies)
            with fr3:
                fams = sorted({a.get("role_family", "") for a in apps if a.get("role_family")})
                filter_family = st.selectbox("Role family", ["All"] + fams)
            search = st.text_input("Search", placeholder="company, title, or notes")

        def _match(a):
            if filter_status != "All" and (a.get("status") or "") != filter_status:
                return False
            if filter_company != "All" and a.get("company", "") != filter_company:
                return False
            if filter_family != "All" and a.get("role_family", "") != filter_family:
                return False
            if search:
                blob = " ".join(str(a.get(k, "")) for k in ("company", "job_title", "notes")).lower()
                if search.lower() not in blob:
                    return False
            return True

        filtered = [a for a in apps if _match(a)]
        st.caption(f"{len(filtered)} of {len(apps)} applications match the current filters.")
        if filtered:
            df = pd.DataFrame(filtered)
            display_cols = ["id", "company", "job_title", "status", "role_family",
                            "analysis_score", "application_date", "job_url", "created_at"]
            df = df[[c for c in display_cols if c in df.columns]]
            st.dataframe(df, width="stretch", hide_index=True)

        # --- Detail panel + status update ---------------------------------
        st.subheader("Application detail")
        app_ids = [a["id"] for a in apps]
        selected = st.selectbox("Select application id", options=app_ids)
        current = next((a for a in apps if a["id"] == selected), None)
        if current:
            with st.container(border=True):
                st.markdown(f"**{current.get('company', '')} — {current.get('job_title', '')}**")
                dc1, dc2, dc3 = st.columns(3)
                dc1.metric("Status", current.get("status") or "—")
                score = current.get("analysis_score")
                dc2.metric("Fit score", f"{score}" if score not in (None, "") else "—")
                dc3.metric("Role family", current.get("role_family") or "—")
                meta_bits = []
                if current.get("source"):
                    meta_bits.append(f"Source: {current['source']}")
                if current.get("location"):
                    meta_bits.append(f"Location: {current['location']}")
                if current.get("recommendation"):
                    meta_bits.append(f"Recommendation: {current['recommendation']}")
                if meta_bits:
                    st.caption(" · ".join(meta_bits))
                if current.get("job_url"):
                    st.markdown(f"[Application link]({current.get('job_url')})")
                rv_id = current.get("resume_version_id")
                if rv_id:
                    st.caption(f"Resume version used: #{rv_id}")
                if current.get("notes"):
                    st.caption(f"Analysis summary / notes: {current.get('notes')}")
                date_bits = []
                for label, key in [("Analyzed", "analyzed_date"), ("Applied", "applied_date"),
                                   ("Updated", "updated_at")]:
                    if current.get(key):
                        date_bits.append(f"{label}: {current[key]}")
                if date_bits:
                    st.caption(" · ".join(date_bits))

                current_status = current.get("status") or STATUS_OPTIONS[0]
                status_index = (
                    STATUS_OPTIONS.index(current_status)
                    if current_status in STATUS_OPTIONS else 0
                )
                u1, u2 = st.columns(2)
                with u1:
                    new_status = st.selectbox("Update status", STATUS_OPTIONS, index=status_index)
                with u2:
                    next_action = st.text_input(
                        "Next action date (YYYY-MM-DD, optional)",
                        value=current.get("next_action_date", "") or "",
                    )
                new_notes = st.text_area("Notes", value=current.get("notes", "") or "")
                if st.button("Update Record", type="primary"):
                    fields = {"status": new_status, "notes": new_notes,
                              "next_action_date": next_action}
                    # Stamp applied_date the first time it moves to Applied.
                    if new_status == "Applied" and not (current.get("applied_date") or "").strip():
                        fields["applied_date"] = date.today().isoformat()
                    db.update_application_fields(selected, fields)
                    _flash("Record updated.")

    # --- Add / import (kept, decluttered into expanders) -------------------
    st.subheader("Add or import")
    with st.expander("Add a single application"):
        with st.form("add_application"):
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

    with st.expander("Batch upload from CSV"):
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
                    st.dataframe(upload_df[APPLICATION_COLUMNS], width="stretch", hide_index=True)
                    if st.button("Save Uploaded Applications"):
                        records = upload_df[APPLICATION_COLUMNS].to_dict("records")
                        saved = db.add_applications_bulk(records)
                        _flash(f"Saved {saved} application records.")


def page_batch_analytics():
    st.header("Insights")
    st.caption("Aggregate demand signals from the processed job dataset.")
    jobs, dataset_label = load_jobs()
    if jobs.empty:
        st.warning("No job dataset found. Run `python3 preprocess_jobs.py` first.")
        return

    stats = analytics.compute_batch_analytics(jobs)
    miss = stats["missing"]

    def _top_name(series):
        return series.index[0] if series is not None and len(series) else None

    # ---- KPI cards --------------------------------------------------------
    k = st.columns(5)
    k[0].metric("Total jobs", stats["total_jobs"])
    k[1].metric("Role families", int(len(stats["by_role_family"])))
    k[2].metric("Companies", int(len(stats["top_companies"])))
    k[3].metric("Locations", int(len(stats["top_locations"])))
    k[4].metric("Missing salary %", f"{miss['salary_pct']}%")
    st.caption(f"Dataset: **{dataset_label}**")

    # ---- Market Overview --------------------------------------------------
    st.subheader("Market Overview")
    top_family = _top_name(stats["by_role_family"])
    if top_family:
        st.caption(
            f"The current dataset is concentrated in **{top_family}** and related "
            "operations / analytics-adjacent roles."
        )
    o1, o2 = st.columns(2)
    with o1:
        st.markdown("**Jobs by role family**")
        st.bar_chart(stats["by_role_family"])
    with o2:
        st.markdown("**Source distribution**")
        st.bar_chart(stats["source_distribution"])

    # ---- Role Demand ------------------------------------------------------
    st.subheader("Role Demand")
    top_kw = _top_name(stats["keyword_frequencies"])
    if top_kw:
        st.caption(f"The most frequently requested skill/keyword in descriptions is **{top_kw}**.")
    st.markdown("**Top keyword / skill demand (in descriptions)**")
    st.bar_chart(stats["keyword_frequencies"])
    if len(stats["employment_type_distribution"]) > 0:
        with st.expander("Employment type distribution"):
            st.bar_chart(stats["employment_type_distribution"])

    # ---- Geography & Employers -------------------------------------------
    st.subheader("Geography & Employers")
    g1, g2 = st.columns(2)
    with g1:
        st.markdown("**Top locations**")
        st.bar_chart(stats["top_locations"])
    with g2:
        st.markdown("**Top companies**")
        st.bar_chart(stats["top_companies"])

    # ---- Data Quality -----------------------------------------------------
    st.subheader("Data Quality")
    if miss["salary_pct"] >= 60:
        st.caption("Salary fields are largely unavailable in this source snapshot.")
    mc1, mc2, mc3 = st.columns(3)
    mc1.metric("Missing salary %", f"{miss['salary_pct']}%")
    mc2.metric("Missing job_url %", f"{miss['job_url_pct']}%")
    mc3.metric("Missing location %", f"{miss['location_pct']}%")
    with st.expander("Salary summary (parseable values only)"):
        if stats["salary_summary"]:
            st.json(stats["salary_summary"])
        else:
            st.caption("No parseable salary data available in this dataset.")

    summary_df = analytics.analytics_to_csv(stats)
    st.download_button(
        "Download Analytics Summary as CSV",
        data=summary_df.to_csv(index=False).encode("utf-8"),
        file_name="batch_analytics_summary.csv",
        mime="text/csv",
    )


def page_test_personas():
    st.header("Test Personas")
    st.caption("Evaluation Demo — not used for the owner's real resume.")
    st.info(
        "Evaluates recommendation quality for the four official personas. These personas "
        "are for ranking evaluation only and do NOT use the project owner's real resume "
        "material."
    )

    jobs, dataset_label = load_jobs()
    if jobs.empty:
        st.warning("No job dataset found. Run `python3 preprocess_jobs.py` first.")
        return

    keys = list(test_personas.PERSONAS.keys())
    persona_key = st.selectbox(
        "Select persona",
        keys,
        format_func=lambda k: test_personas.PERSONAS[k]["persona_name"],
    )
    persona = test_personas.PERSONAS[persona_key]

    with st.expander("Persona details"):
        st.write(f"**Background:** {persona['background']}")
        st.write(f"**Skills:** {', '.join(persona['skills'])}")
        st.write(f"**Target roles:** {', '.join(persona['target_roles'])}")
        st.write(f"**Dealbreakers:** {', '.join(persona['dealbreakers'])}")
        st.write(f"**Pass criteria:** {persona['pass_criteria']}")

    if st.button("Run Ranking & Evaluate", type="primary"):
        # Rank using ONLY the persona profile text (no candidate facts injected).
        ranked = matching.rank_jobs(
            persona["profile_text"],
            jobs.head(RANK_CAP).to_dict("records"),
            feedback_rows=None,
            top_n=10,
            method="tfidf",
            include_candidate_facts=False,
        )
        st.session_state["persona_ranked"] = ranked
        st.session_state["persona_key_eval"] = persona_key

    ranked = st.session_state.get("persona_ranked")
    if not ranked or st.session_state.get("persona_key_eval") != persona_key:
        st.info("Click **Run Ranking & Evaluate** to score this persona against the jobs.")
        return

    st.subheader("Top 10 Recommended Jobs")
    top_table = pd.DataFrame(
        [
            {
                "rank": r["rank"],
                "match_score": r["match_score"],
                "role_family": r["role_family"],
                "company": r["job_row"].get("company", ""),
                "job_title": r["job_row"].get("job_title", ""),
                "location": r["job_row"].get("location", ""),
            }
            for r in ranked
        ]
    )
    st.dataframe(top_table, width="stretch", hide_index=True)

    top_jobs = [r["job_row"] for r in ranked]
    checks = test_personas.evaluate_persona(persona_key, top_jobs)
    checks_df = pd.DataFrame(checks)
    st.subheader("Pass / Fail Evaluation")
    st.dataframe(checks_df, width="stretch", hide_index=True)

    n_pass = sum(1 for c in checks if c["result"] == "Pass")
    st.caption(
        f"{n_pass}/{len(checks)} checks passed. Limitation: the dataset is a generic "
        "ops/analytics snapshot, so some persona-specific roles may be under-represented."
    )

    export_df = checks_df.copy()
    export_df.insert(0, "persona", persona["persona_name"])
    st.download_button(
        "Download Persona Evaluation CSV",
        data=export_df.to_csv(index=False).encode("utf-8"),
        file_name=f"persona_evaluation_{persona_key}.csv",
        mime="text/csv",
    )

    with st.expander("Optional: generic persona demo resume (NOT the project owner's resume)"):
        st.caption(
            "For demonstration only. This is a synthetic generic resume and never uses "
            "Yeyi Su's verified resume material."
        )
        if st.checkbox("Show persona demo resume"):
            st.text_area(
                "Persona demo resume",
                value=test_personas.build_persona_demo_resume(persona_key),
                height=300,
            )


def page_readme():
    st.header("Project README")
    st.markdown(load_readme())


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

PAGE_DISPATCH = {
    "Home": lambda: page_home(),
    "Analyze Job": lambda: page_analyze_job(),
    "Applications": lambda: page_application_tracker(),
    "Resume Library": lambda: page_generated_versions(),
    "Evidence Library": lambda: page_evidence_library(),
    "Job Matching": lambda: page_job_matching(),
    "Insights": lambda: page_batch_analytics(),
    "Candidate Profile": lambda: page_candidate_profile(),
    "Project README": lambda: page_readme(),
    "Test Personas": lambda: page_test_personas(),
}


def main():
    st.set_page_config(
        page_title="JobPilot — Job Search Decision Support",
        page_icon="🧭",
        layout="wide",
    )
    _inject_theme()
    db.init_db()

    page = _sidebar_nav()
    PAGE_DISPATCH.get(page, page_home)()


if __name__ == "__main__":
    main()
