"""SQLite persistence layer for JobPilot.

Stores generated resume versions and manual application tracking records.
The database file (jobpilot.db) is created automatically on first use.
"""

import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent / "jobpilot.db"


def _connect():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create tables if they do not already exist."""
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS resume_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT,
            company TEXT,
            job_title TEXT,
            job_id TEXT,
            target_title TEXT,
            match_score REAL,
            matched_keywords TEXT,
            missing_keywords TEXT,
            feedback_text TEXT,
            resume_text TEXT
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT,
            company TEXT,
            job_title TEXT,
            job_url TEXT,
            status TEXT,
            application_date TEXT,
            notes TEXT
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS job_feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT,
            job_id TEXT,
            company TEXT,
            job_title TEXT,
            role_family TEXT,
            feedback TEXT,
            notes TEXT
        )
        """
    )
    # v2: one-JD intake + fit diagnosis records.
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS job_analyses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company TEXT,
            job_title TEXT,
            apply_link TEXT,
            source TEXT,
            jd_text TEXT,
            notes TEXT,
            overall_score REAL,
            decision TEXT,
            selected_role_family TEXT,
            suggested_resume_angle TEXT,
            component_scores_json TEXT,
            matched_evidence_json TEXT,
            missing_evidence_json TEXT,
            evidence_gap_questions_json TEXT,
            red_flags_json TEXT,
            recommended_positioning TEXT,
            scoring_explanation TEXT,
            added_evidence TEXT,
            created_at TEXT,
            updated_at TEXT
        )
        """
    )
    # v2: feedback on the fit score (does not auto-overwrite the score).
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS score_feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_analysis_id INTEGER,
            feedback_label TEXT,
            reason TEXT,
            notes TEXT,
            created_at TEXT
        )
        """
    )
    # v2: add safe optional columns to applications for analysis handoff.
    _ensure_columns(cur, "applications", {
        "analysis_score": "REAL",
        "role_family": "TEXT",
    })
    # v2.1: calibration + diagnosis detail columns (non-destructive).
    _ensure_columns(cur, "job_analyses", {
        "base_score": "REAL",
        "calibrated_score": "REAL",
        "priority": "TEXT",
        "confidence": "TEXT",
        "sponsorship_feasibility": "REAL",
        "temporary_added_evidence": "TEXT",
        "evidence_reanalysis_score": "REAL",
    })
    _ensure_columns(cur, "score_feedback", {
        "base_score": "REAL",
        "adjustment_magnitude": "REAL",
        "calibrated_score": "REAL",
        "role_family": "TEXT",
    })
    conn.commit()
    conn.close()


def _ensure_columns(cur, table, columns):
    """Add missing optional columns to an existing table (non-destructive)."""
    cur.execute(f"PRAGMA table_info({table})")
    existing = {row["name"] for row in cur.fetchall()}
    for name, col_type in columns.items():
        if name not in existing:
            cur.execute(f"ALTER TABLE {table} ADD COLUMN {name} {col_type}")


def add_or_update_application_from_analysis(
    company, job_title, job_url, status, analysis_score=None, role_family="", notes=""
):
    """Upsert an application from a job analysis, keyed by (company, job_title).

    Preserves the analysis score and role family in the optional columns. Returns
    (row_id, created) where created is True for a new insert.
    """
    init_db()
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        "SELECT id FROM applications WHERE company = ? AND job_title = ? ORDER BY id DESC LIMIT 1",
        (str(company), str(job_title)),
    )
    row = cur.fetchone()
    score_val = float(analysis_score) if analysis_score is not None else None
    if row:
        cur.execute(
            """
            UPDATE applications
            SET job_url = ?, status = ?, analysis_score = ?, role_family = ?, notes = ?
            WHERE id = ?
            """,
            (str(job_url), str(status), score_val, str(role_family), str(notes), row["id"]),
        )
        conn.commit()
        rid = row["id"]
        conn.close()
        return rid, False
    cur.execute(
        """
        INSERT INTO applications (
            created_at, company, job_title, job_url, status,
            application_date, notes, analysis_score, role_family
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            str(company),
            str(job_title),
            str(job_url),
            str(status),
            "",
            str(notes),
            score_val,
            str(role_family),
        ),
    )
    conn.commit()
    rid = cur.lastrowid
    conn.close()
    return rid, True


def save_resume_version(
    company,
    job_title,
    job_id,
    target_title,
    match_score,
    matched_keywords,
    missing_keywords,
    feedback_text,
    resume_text,
):
    """Persist a generated resume version. Returns the new row id."""
    init_db()
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO resume_versions (
            created_at, company, job_title, job_id, target_title,
            match_score, matched_keywords, missing_keywords,
            feedback_text, resume_text
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            company,
            job_title,
            job_id,
            target_title,
            float(match_score) if match_score is not None else 0.0,
            matched_keywords,
            missing_keywords,
            feedback_text,
            resume_text,
        ),
    )
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return new_id


def get_resume_versions():
    """Return all saved resume versions, newest first, as a list of dicts."""
    init_db()
    conn = _connect()
    cur = conn.cursor()
    cur.execute("SELECT * FROM resume_versions ORDER BY id DESC")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def get_resume_version(version_id):
    """Return a single resume version by id, or None."""
    init_db()
    conn = _connect()
    cur = conn.cursor()
    cur.execute("SELECT * FROM resume_versions WHERE id = ?", (version_id,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def add_application(company, job_title, job_url, status, application_date, notes):
    """Add a manual application record. Returns the new row id."""
    init_db()
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO applications (
            created_at, company, job_title, job_url,
            status, application_date, notes
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            company,
            job_title,
            job_url,
            status,
            application_date,
            notes,
        ),
    )
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return new_id


def add_applications_bulk(records):
    """Insert multiple application records in one transaction.

    records: list of dicts with keys company, job_title, job_url, status,
    application_date, notes. Missing keys default to empty strings.
    Returns the number of records inserted.
    """
    init_db()
    conn = _connect()
    cur = conn.cursor()
    count = 0
    for r in records:
        cur.execute(
            """
            INSERT INTO applications (
                created_at, company, job_title, job_url,
                status, application_date, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                str(r.get("company", "")),
                str(r.get("job_title", "")),
                str(r.get("job_url", "")),
                str(r.get("status", "")),
                str(r.get("application_date", "")),
                str(r.get("notes", "")),
            ),
        )
        count += 1
    conn.commit()
    conn.close()
    return count


def get_applications():
    """Return all application records, newest first, as a list of dicts."""
    init_db()
    conn = _connect()
    cur = conn.cursor()
    cur.execute("SELECT * FROM applications ORDER BY id DESC")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def update_application(application_id, status, notes):
    """Update the status and notes of an existing application record."""
    init_db()
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        "UPDATE applications SET status = ?, notes = ? WHERE id = ?",
        (status, notes, application_id),
    )
    conn.commit()
    conn.close()


def save_job_feedback(job_id, company, job_title, role_family, feedback, notes=""):
    """Persist a single job feedback record. Returns the new row id."""
    init_db()
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO job_feedback (
            created_at, job_id, company, job_title, role_family, feedback, notes
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            str(job_id),
            str(company),
            str(job_title),
            str(role_family),
            str(feedback),
            str(notes),
        ),
    )
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return new_id


def get_job_feedback():
    """Return all job feedback records, newest first, as a list of dicts."""
    init_db()
    conn = _connect()
    cur = conn.cursor()
    cur.execute("SELECT * FROM job_feedback ORDER BY id DESC")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def get_feedback_summary():
    """Return counts grouped by (role_family, feedback) as a list of dicts."""
    init_db()
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT role_family, feedback, COUNT(*) AS count
        FROM job_feedback
        GROUP BY role_family, feedback
        ORDER BY count DESC
        """
    )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def save_job_analysis(analysis):
    """Insert a job analysis record. `analysis` is a dict; *_json fields should
    already be JSON-encoded strings. Returns the new row id."""
    init_db()
    conn = _connect()
    cur = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    base_score = analysis.get("base_score", analysis.get("overall_score"))
    cur.execute(
        """
        INSERT INTO job_analyses (
            company, job_title, apply_link, source, jd_text, notes,
            overall_score, decision, selected_role_family, suggested_resume_angle,
            component_scores_json, matched_evidence_json, missing_evidence_json,
            evidence_gap_questions_json, red_flags_json, recommended_positioning,
            scoring_explanation, added_evidence, created_at, updated_at,
            base_score, calibrated_score, priority, confidence,
            sponsorship_feasibility, temporary_added_evidence, evidence_reanalysis_score
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                  ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            str(analysis.get("company", "")),
            str(analysis.get("job_title", "")),
            str(analysis.get("apply_link", "")),
            str(analysis.get("source", "")),
            str(analysis.get("jd_text", "")),
            str(analysis.get("notes", "")),
            float(analysis.get("overall_score") or 0.0),
            str(analysis.get("decision", "")),
            str(analysis.get("selected_role_family", "")),
            str(analysis.get("suggested_resume_angle", "")),
            str(analysis.get("component_scores_json", "")),
            str(analysis.get("matched_evidence_json", "")),
            str(analysis.get("missing_evidence_json", "")),
            str(analysis.get("evidence_gap_questions_json", "")),
            str(analysis.get("red_flags_json", "")),
            str(analysis.get("recommended_positioning", "")),
            str(analysis.get("scoring_explanation", "")),
            str(analysis.get("added_evidence", "")),
            now,
            now,
            float(base_score) if base_score is not None else 0.0,
            float(analysis["calibrated_score"]) if analysis.get("calibrated_score") is not None else None,
            str(analysis.get("priority", "")),
            str(analysis.get("confidence", "")),
            float(analysis["sponsorship_feasibility"]) if analysis.get("sponsorship_feasibility") is not None else None,
            str(analysis.get("temporary_added_evidence", "")),
            float(analysis["evidence_reanalysis_score"]) if analysis.get("evidence_reanalysis_score") is not None else None,
        ),
    )
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return new_id


def get_job_analyses():
    """Return all job analyses, newest first, as a list of dicts."""
    init_db()
    conn = _connect()
    cur = conn.cursor()
    cur.execute("SELECT * FROM job_analyses ORDER BY id DESC")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def get_job_analysis(analysis_id):
    """Return a single job analysis by id, or None."""
    init_db()
    conn = _connect()
    cur = conn.cursor()
    cur.execute("SELECT * FROM job_analyses WHERE id = ?", (analysis_id,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def save_score_feedback(job_analysis_id, feedback_label, reason, notes="",
                        base_score=None, adjustment_magnitude=0.0,
                        calibrated_score=None, role_family=""):
    """Persist calibration feedback about a fit score. Returns the new row id.

    This records the user's opinion and a calibrated score but does NOT modify the
    stored base score.
    """
    init_db()
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO score_feedback (
            job_analysis_id, feedback_label, reason, notes, created_at,
            base_score, adjustment_magnitude, calibrated_score, role_family
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            int(job_analysis_id) if job_analysis_id is not None else None,
            str(feedback_label),
            str(reason),
            str(notes),
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            float(base_score) if base_score is not None else None,
            float(adjustment_magnitude or 0.0),
            float(calibrated_score) if calibrated_score is not None else None,
            str(role_family),
        ),
    )
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return new_id


def get_calibration_adjustment(role_family, cap=0.3):
    """Transparent role-family calibration from prior feedback.

    Returns the average (calibrated_score - base_score) delta recorded for this
    role family, clamped to [-cap, +cap]. Returns 0.0 if there is no usable history.
    """
    if not role_family:
        return 0.0
    init_db()
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT base_score, calibrated_score FROM score_feedback
        WHERE role_family = ? AND base_score IS NOT NULL AND calibrated_score IS NOT NULL
        """,
        (str(role_family),),
    )
    rows = cur.fetchall()
    conn.close()
    deltas = [r["calibrated_score"] - r["base_score"] for r in rows]
    if not deltas:
        return 0.0
    avg = sum(deltas) / len(deltas)
    return round(max(-cap, min(cap, avg)), 2)


def get_score_feedback(job_analysis_id=None):
    """Return score feedback rows (optionally filtered by analysis id)."""
    init_db()
    conn = _connect()
    cur = conn.cursor()
    if job_analysis_id is None:
        cur.execute("SELECT * FROM score_feedback ORDER BY id DESC")
    else:
        cur.execute(
            "SELECT * FROM score_feedback WHERE job_analysis_id = ? ORDER BY id DESC",
            (int(job_analysis_id),),
        )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


if __name__ == "__main__":
    init_db()
    print(f"Initialized database at {DB_PATH}")
