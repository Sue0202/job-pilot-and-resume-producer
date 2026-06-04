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
    conn.commit()
    conn.close()


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


if __name__ == "__main__":
    init_db()
    print(f"Initialized database at {DB_PATH}")
