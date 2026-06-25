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
    # v3: structured Evidence Library. Temporary re-analysis notes are NEVER written
    # here automatically; only an explicit "Save to Evidence Library" creates a row.
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS evidence_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            company TEXT,
            role_context TEXT,
            time_period TEXT,
            category TEXT,
            skills TEXT,
            action TEXT,
            outcome TEXT,
            raw_notes TEXT,
            bullet_draft TEXT,
            status TEXT,
            tags TEXT,
            source_job_analysis_id INTEGER,
            created_at TEXT,
            updated_at TEXT
        )
        """
    )
    # v3: transparent resume/recommendation preference feedback (bounded, explainable).
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS preference_feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scope TEXT,
            role_family TEXT,
            preference TEXT,
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
    # v3: richer application tracker columns (non-destructive).
    _ensure_columns(cur, "applications", {
        "source": "TEXT",
        "location": "TEXT",
        "recommendation": "TEXT",
        "resume_version_id": "INTEGER",
        "analyzed_date": "TEXT",
        "applied_date": "TEXT",
        "next_action_date": "TEXT",
        "updated_at": "TEXT",
    })
    # v3: resume version provenance (which job/angle/evidence produced it).
    _ensure_columns(cur, "resume_versions", {
        "jd_snapshot": "TEXT",
        "selected_angle": "TEXT",
        "decision_at_generation": "TEXT",
        "score_at_generation": "REAL",
        "evidence_used_json": "TEXT",
        "job_analysis_id": "INTEGER",
    })
    # v3.1: evidence translation / positioning fields (non-destructive).
    _ensure_columns(cur, "evidence_items", {
        "original_industry_context": "TEXT",
        "capability_tags": "TEXT",
        "target_role_translations": "TEXT",
        "proof_strength": "TEXT",
    })
    # v3.4: factual source vs generated verbal outputs (additive).
    _ensure_columns(cur, "evidence_items", {
        "factual_context": "TEXT",
        "impact_outcome": "TEXT",
    })
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS evidence_verbal_outputs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            evidence_item_id INTEGER NOT NULL,
            role_family TEXT,
            job_analysis_id INTEGER,
            output_type TEXT NOT NULL,
            generated_text TEXT,
            user_approved INTEGER DEFAULT 0,
            user_feedback TEXT,
            created_at TEXT,
            updated_at TEXT
        )
        """
    )
    # v3.5: canonical/preferred verbal metadata (additive).
    _ensure_columns(cur, "evidence_verbal_outputs", {
        "role_family_normalized": "TEXT",
        "is_preferred": "INTEGER",
        "source": "TEXT",
        "feedback_tags": "TEXT",
        "feedback_note": "TEXT",
    })
    # v3.2: resume review + translation feedback (behavior-driven, not score weights).
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS translation_feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            resume_version_id INTEGER,
            analysis_id INTEGER,
            evidence_item_id INTEGER,
            role_family TEXT,
            source_text TEXT,
            generated_text TEXT,
            final_text TEXT,
            action_type TEXT,
            feedback_tags TEXT,
            notes TEXT,
            bullet_index INTEGER,
            created_at TEXT
        )
        """
    )
    _ensure_columns(cur, "resume_versions", {
        "review_usefulness": "TEXT",
        "review_tags": "TEXT",
        "review_notes": "TEXT",
        "bullet_state_json": "TEXT",
    })
    # v3.3: user-controlled evidence vocabulary (categories, tags, skill suggestions).
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS user_vocabulary (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            vocab_type TEXT NOT NULL,
            value TEXT NOT NULL,
            norm_key TEXT NOT NULL,
            created_at TEXT,
            updated_at TEXT,
            UNIQUE(vocab_type, norm_key)
        )
        """
    )
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
    _backfill_verbal_role_family_normalized(cur)
    conn.commit()
    conn.close()


def _backfill_verbal_role_family_normalized(cur):
    """Populate role_family_normalized for legacy verbal output rows."""
    cur.execute(
        "SELECT id, role_family, role_family_normalized FROM evidence_verbal_outputs"
    )
    import re

    def _norm(v):
        s = re.sub(r"\s+", " ", (v or "").strip())
        s = s.replace("–", "-").replace("—", "-")
        return s.lower()

    for row in cur.fetchall():
        if (row["role_family_normalized"] or "").strip():
            continue
        rf = (row["role_family"] or "").strip()
        if rf:
            cur.execute(
                "UPDATE evidence_verbal_outputs SET role_family_normalized = ? WHERE id = ?",
                (_norm(rf), row["id"]),
            )


def _ensure_columns(cur, table, columns):
    """Add missing optional columns to an existing table (non-destructive)."""
    cur.execute(f"PRAGMA table_info({table})")
    existing = {row["name"] for row in cur.fetchall()}
    for name, col_type in columns.items():
        if name not in existing:
            cur.execute(f"ALTER TABLE {table} ADD COLUMN {name} {col_type}")


def add_or_update_application_from_analysis(
    company, job_title, job_url, status, analysis_score=None, role_family="", notes="",
    source="", location="", recommendation="",
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
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    today = datetime.now().strftime("%Y-%m-%d")
    if row:
        cur.execute(
            """
            UPDATE applications
            SET job_url = ?, status = ?, analysis_score = ?, role_family = ?, notes = ?,
                source = ?, location = ?, recommendation = ?, analyzed_date = ?, updated_at = ?
            WHERE id = ?
            """,
            (str(job_url), str(status), score_val, str(role_family), str(notes),
             str(source), str(location), str(recommendation), today, now, row["id"]),
        )
        conn.commit()
        rid = row["id"]
        conn.close()
        return rid, False
    cur.execute(
        """
        INSERT INTO applications (
            created_at, company, job_title, job_url, status,
            application_date, notes, analysis_score, role_family,
            source, location, recommendation, analyzed_date, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            now,
            str(company),
            str(job_title),
            str(job_url),
            str(status),
            "",
            str(notes),
            score_val,
            str(role_family),
            str(source),
            str(location),
            str(recommendation),
            today,
            now,
        ),
    )
    conn.commit()
    rid = cur.lastrowid
    conn.close()
    return rid, True


def update_application_fields(application_id, fields):
    """Update arbitrary safe columns of an application. Returns rows affected."""
    init_db()
    allowed = {
        "company", "job_title", "job_url", "status", "application_date", "notes",
        "analysis_score", "role_family", "source", "location", "recommendation",
        "resume_version_id", "analyzed_date", "applied_date", "next_action_date",
    }
    sets = {k: v for k, v in fields.items() if k in allowed}
    if not sets:
        return 0
    conn = _connect()
    cur = conn.cursor()
    sets["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    assignments = ", ".join(f"{k} = ?" for k in sets)
    cur.execute(
        f"UPDATE applications SET {assignments} WHERE id = ?",
        list(sets.values()) + [int(application_id)],
    )
    n = cur.rowcount
    conn.commit()
    conn.close()
    return n


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
    jd_snapshot="",
    selected_angle="",
    decision_at_generation="",
    score_at_generation=None,
    evidence_used_json="",
    job_analysis_id=None,
    review_usefulness="",
    review_tags="",
    review_notes="",
    bullet_state_json="",
):
    """Persist a generated resume version. Returns the new row id.

    Each call creates a NEW row (feedback never overwrites an earlier version).
    Optional provenance fields record the job/angle/evidence used.
    """
    init_db()
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO resume_versions (
            created_at, company, job_title, job_id, target_title,
            match_score, matched_keywords, missing_keywords,
            feedback_text, resume_text,
            jd_snapshot, selected_angle, decision_at_generation,
            score_at_generation, evidence_used_json, job_analysis_id,
            review_usefulness, review_tags, review_notes, bullet_state_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            jd_snapshot,
            selected_angle,
            decision_at_generation,
            float(score_at_generation) if score_at_generation is not None else None,
            evidence_used_json,
            job_analysis_id,
            review_usefulness or "",
            review_tags or "",
            review_notes or "",
            bullet_state_json or "",
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


# ---------------------------------------------------------------------------
# Evidence Library (v3)
# ---------------------------------------------------------------------------

EVIDENCE_FIELDS = [
    "title", "company", "role_context", "time_period", "category", "skills",
    "action", "outcome", "raw_notes", "bullet_draft", "status", "tags",
    "source_job_analysis_id", "original_industry_context", "capability_tags",
    "target_role_translations", "proof_strength", "factual_context", "impact_outcome",
]


def save_evidence_item(item):
    """Insert a new evidence item. Returns the new row id.

    Only called from an explicit 'Save to Evidence Library' action.
    """
    init_db()
    conn = _connect()
    cur = conn.cursor()
    now = datetime.utcnow().isoformat(timespec="seconds")
    # Normalize: ensure status is explicit; sync legacy action/outcome from factual fields.
    record = dict(item)
    if record.get("factual_context") and not record.get("action"):
        record["action"] = (record["factual_context"] or "")[:2000]
    if record.get("impact_outcome") and not record.get("outcome"):
        record["outcome"] = record["impact_outcome"]
    status = (record.get("status") or "Draft").strip()
    if status not in ("Draft", "Verified", "Archived"):
        status = "Draft"
    record["status"] = status
    cols = EVIDENCE_FIELDS + ["created_at", "updated_at"]
    vals = [record.get(f, "") or "" for f in EVIDENCE_FIELDS] + [now, now]
    placeholders = ", ".join(["?"] * len(cols))
    cur.execute(
        f"INSERT INTO evidence_items ({', '.join(cols)}) VALUES ({placeholders})",
        vals,
    )
    new_id = cur.lastrowid
    conn.commit()
    conn.close()
    return new_id


def get_evidence_items(status=None):
    """Return evidence items, newest first; optionally filtered by status."""
    init_db()
    conn = _connect()
    cur = conn.cursor()
    if status:
        cur.execute("SELECT * FROM evidence_items WHERE status = ? ORDER BY id DESC", (status,))
    else:
        cur.execute("SELECT * FROM evidence_items ORDER BY id DESC")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def get_evidence_item(item_id):
    init_db()
    conn = _connect()
    cur = conn.cursor()
    cur.execute("SELECT * FROM evidence_items WHERE id = ?", (int(item_id),))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def update_evidence_item(item_id, fields):
    """Update selected fields of an evidence item. Returns rows affected."""
    init_db()
    allowed = set(EVIDENCE_FIELDS)
    sets = {k: v for k, v in fields.items() if k in allowed}
    if not sets:
        return 0
    conn = _connect()
    cur = conn.cursor()
    sets["updated_at"] = datetime.utcnow().isoformat(timespec="seconds")
    assignments = ", ".join(f"{k} = ?" for k in sets)
    cur.execute(
        f"UPDATE evidence_items SET {assignments} WHERE id = ?",
        list(sets.values()) + [int(item_id)],
    )
    n = cur.rowcount
    conn.commit()
    conn.close()
    return n


def get_verified_evidence():
    """Verified evidence items only — the pool eligible for resume generation."""
    return get_evidence_items(status="Verified")


def backfill_evidence_factual_fields():
    """Safe additive backfill: populate factual_context from legacy fields when empty."""
    init_db()
    items = get_evidence_items()
    for item in items:
        updates = {}
        if not (item.get("factual_context") or "").strip():
            parts = [
                item.get("action"),
                item.get("original_industry_context"),
                item.get("raw_notes"),
            ]
            combined = "\n\n".join(p.strip() for p in parts if p and str(p).strip())
            if combined:
                updates["factual_context"] = combined
        if not (item.get("impact_outcome") or "").strip() and (item.get("outcome") or "").strip():
            updates["impact_outcome"] = item["outcome"]
        if updates:
            update_evidence_item(item["id"], updates)


# ---------------------------------------------------------------------------
# Evidence verbal outputs (v3.4+) — generated wording separate from source facts
# ---------------------------------------------------------------------------

VERBAL_OUTPUT_ALLOWED = {
    "generated_text", "user_approved", "user_feedback", "role_family",
    "role_family_normalized", "is_preferred", "source", "feedback_tags", "feedback_note",
}


def insert_verbal_output(
    evidence_item_id,
    output_type,
    generated_text,
    role_family="",
    role_family_normalized="",
    job_analysis_id=None,
    user_approved=False,
    is_preferred=False,
    source="generated",
    user_feedback="",
    feedback_tags="",
    feedback_note="",
):
    init_db()
    conn = _connect()
    cur = conn.cursor()
    now = datetime.utcnow().isoformat(timespec="seconds")
    cur.execute(
        """
        INSERT INTO evidence_verbal_outputs (
            evidence_item_id, role_family, role_family_normalized, job_analysis_id,
            output_type, generated_text, user_approved, is_preferred, source,
            user_feedback, feedback_tags, feedback_note, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            int(evidence_item_id),
            role_family or "",
            role_family_normalized or "",
            job_analysis_id,
            output_type,
            generated_text or "",
            1 if user_approved else 0,
            1 if is_preferred else 0,
            source or "generated",
            user_feedback or "",
            feedback_tags or "",
            feedback_note or "",
            now,
            now,
        ),
    )
    new_id = cur.lastrowid
    conn.commit()
    conn.close()
    return new_id


def save_verbal_output(
    evidence_item_id,
    output_type,
    generated_text,
    role_family="",
    job_analysis_id=None,
    user_approved=False,
    user_feedback="",
    role_family_normalized="",
    is_preferred=False,
    source="generated",
    feedback_tags="",
    feedback_note="",
):
    """Insert a new verbal output row (legacy-compatible wrapper)."""
    return insert_verbal_output(
        evidence_item_id, output_type, generated_text,
        role_family=role_family,
        role_family_normalized=role_family_normalized,
        job_analysis_id=job_analysis_id,
        user_approved=user_approved,
        is_preferred=is_preferred,
        source=source,
        user_feedback=user_feedback,
        feedback_tags=feedback_tags,
        feedback_note=feedback_note,
    )


def get_verbal_outputs(evidence_item_id, output_type=None):
    init_db()
    conn = _connect()
    cur = conn.cursor()
    if output_type:
        cur.execute(
            """
            SELECT * FROM evidence_verbal_outputs
            WHERE evidence_item_id = ? AND output_type = ?
            ORDER BY id DESC
            """,
            (int(evidence_item_id), output_type),
        )
    else:
        cur.execute(
            """
            SELECT * FROM evidence_verbal_outputs
            WHERE evidence_item_id = ?
            ORDER BY id DESC
            """,
            (int(evidence_item_id),),
        )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def update_verbal_output(output_id, fields):
    init_db()
    allowed = VERBAL_OUTPUT_ALLOWED
    sets = {k: v for k, v in fields.items() if k in allowed}
    if not sets:
        return 0
    conn = _connect()
    cur = conn.cursor()
    sets["updated_at"] = datetime.utcnow().isoformat(timespec="seconds")
    if "user_approved" in sets:
        sets["user_approved"] = 1 if sets["user_approved"] else 0
    if "is_preferred" in sets:
        sets["is_preferred"] = 1 if sets["is_preferred"] else 0
    assignments = ", ".join(f"{k} = ?" for k in sets)
    cur.execute(
        f"UPDATE evidence_verbal_outputs SET {assignments} WHERE id = ?",
        list(sets.values()) + [int(output_id)],
    )
    n = cur.rowcount
    conn.commit()
    conn.close()
    return n


def delete_verbal_output(output_id):
    init_db()
    conn = _connect()
    cur = conn.cursor()
    cur.execute("DELETE FROM evidence_verbal_outputs WHERE id = ?", (int(output_id),))
    conn.commit()
    conn.close()


def _resolve_role_family_normalized(role_family, role_family_normalized=None):
    if (role_family_normalized or "").strip():
        return role_family_normalized.strip()
    if (role_family or "").strip():
        import role_family_vocab as rfv
        return rfv.normalize_role_family_key(role_family)
    return ""


def get_verbal_outputs_for_role(evidence_item_id, role_family, role_family_normalized=None):
    """All verbal outputs for evidence + role family (normalized match)."""
    init_db()
    conn = _connect()
    cur = conn.cursor()
    rf_norm = _resolve_role_family_normalized(role_family, role_family_normalized)
    cur.execute(
        """
        SELECT * FROM evidence_verbal_outputs
        WHERE evidence_item_id = ? AND role_family_normalized = ?
        ORDER BY is_preferred DESC, user_approved DESC, id DESC
        """,
        (int(evidence_item_id), rf_norm),
    )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def get_verbal_output_for_role(evidence_item_id, output_type, role_family, role_family_normalized=None):
    """Most recent verbal output for evidence + type + role family (normalized)."""
    init_db()
    conn = _connect()
    cur = conn.cursor()
    rf_norm = _resolve_role_family_normalized(role_family, role_family_normalized)
    cur.execute(
        """
        SELECT * FROM evidence_verbal_outputs
        WHERE evidence_item_id = ? AND output_type = ? AND role_family_normalized = ?
        ORDER BY is_preferred DESC, user_approved DESC, id DESC LIMIT 1
        """,
        (int(evidence_item_id), output_type, rf_norm),
    )
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def get_preferred_verbal_output(evidence_item_id, output_type, role_family_normalized):
    """Preferred or approved wording for resume retrieval."""
    init_db()
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT * FROM evidence_verbal_outputs
        WHERE evidence_item_id = ? AND output_type = ? AND role_family_normalized = ?
          AND (is_preferred = 1 OR user_approved = 1)
        ORDER BY is_preferred DESC, user_approved DESC, id DESC LIMIT 1
        """,
        (int(evidence_item_id), output_type, role_family_normalized),
    )
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def get_verbal_outputs_by_slot(evidence_item_id, output_type, role_family_normalized):
    init_db()
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT * FROM evidence_verbal_outputs
        WHERE evidence_item_id = ? AND output_type = ? AND role_family_normalized = ?
        ORDER BY id DESC
        """,
        (int(evidence_item_id), output_type, role_family_normalized),
    )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def canonical_seed_decision(evidence_item_id, output_type, role_family_normalized, generated_text):
    """Return ('insert'|'skip_idempotent'|'skip_protected', reason)."""
    rows = get_verbal_outputs_by_slot(evidence_item_id, output_type, role_family_normalized)
    for row in rows:
        src = (row.get("source") or "").strip()
        if src == "canonical_seed" and (row.get("generated_text") or "").strip() == generated_text.strip():
            return "skip_idempotent", "already seeded"
        if row.get("user_approved") or row.get("is_preferred") or src == "user_saved":
            return "skip_protected", "user-approved or preferred wording exists"
        if src == "canonical_seed":
            return "skip_idempotent", "canonical seed already present"
        return "skip_protected", "existing verbal output present"
    return "insert", ""


def upsert_verbal_output(
    evidence_item_id,
    output_type,
    generated_text,
    role_family="",
    job_analysis_id=None,
    user_approved=False,
    user_feedback="",
    role_family_normalized="",
    is_preferred=False,
    source="user_saved",
    feedback_tags="",
    feedback_note="",
):
    """Insert or update user-saved verbal output for evidence + type + role family."""
    if not role_family_normalized and role_family:
        import role_family_vocab as rfv
        rf_norm = rfv.normalize_role_family_key(role_family)
    else:
        rf_norm = role_family_normalized or ""
    existing = get_verbal_output_for_role(
        evidence_item_id, output_type, role_family, role_family_normalized=rf_norm,
    )
    if existing and (existing.get("source") or "") != "generated":
        update_verbal_output(existing["id"], {
            "generated_text": generated_text,
            "user_approved": user_approved,
            "user_feedback": user_feedback,
            "is_preferred": is_preferred,
            "source": source,
            "feedback_tags": feedback_tags,
            "feedback_note": feedback_note,
            "role_family": role_family,
            "role_family_normalized": rf_norm,
        })
        return existing["id"]
    return insert_verbal_output(
        evidence_item_id, output_type, generated_text,
        role_family=role_family,
        role_family_normalized=rf_norm,
        job_analysis_id=job_analysis_id,
        user_approved=user_approved,
        is_preferred=is_preferred,
        source=source,
        user_feedback=user_feedback,
        feedback_tags=feedback_tags,
        feedback_note=feedback_note,
    )


def count_verbal_outputs(evidence_item_id, output_type=None):
    init_db()
    conn = _connect()
    cur = conn.cursor()
    if output_type:
        cur.execute(
            "SELECT COUNT(*) AS n FROM evidence_verbal_outputs WHERE evidence_item_id = ? AND output_type = ?",
            (int(evidence_item_id), output_type),
        )
    else:
        cur.execute(
            "SELECT COUNT(*) AS n FROM evidence_verbal_outputs WHERE evidence_item_id = ?",
            (int(evidence_item_id),),
        )
    row = cur.fetchone()
    conn.close()
    return int(row["n"]) if row else 0


# ---------------------------------------------------------------------------
# User vocabulary (v3.3) — custom categories, tags, skill suggestions
# ---------------------------------------------------------------------------

def add_user_vocabulary(vocab_type, value, norm_key):
    """Insert a custom vocabulary item. Returns id (existing if norm_key duplicate)."""
    init_db()
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        "SELECT id FROM user_vocabulary WHERE vocab_type = ? AND norm_key = ?",
        (vocab_type, norm_key),
    )
    row = cur.fetchone()
    if row:
        conn.close()
        return row["id"]
    now = datetime.utcnow().isoformat(timespec="seconds")
    cur.execute(
        """
        INSERT INTO user_vocabulary (vocab_type, value, norm_key, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (vocab_type, value, norm_key, now, now),
    )
    new_id = cur.lastrowid
    conn.commit()
    conn.close()
    return new_id


def get_user_vocabulary(vocab_type=None):
    init_db()
    conn = _connect()
    cur = conn.cursor()
    if vocab_type:
        cur.execute(
            "SELECT * FROM user_vocabulary WHERE vocab_type = ? ORDER BY value COLLATE NOCASE",
            (vocab_type,),
        )
    else:
        cur.execute("SELECT * FROM user_vocabulary ORDER BY vocab_type, value COLLATE NOCASE")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def get_user_vocabulary_by_id(vocab_id):
    init_db()
    conn = _connect()
    cur = conn.cursor()
    cur.execute("SELECT * FROM user_vocabulary WHERE id = ?", (int(vocab_id),))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def get_user_vocabulary_by_key(vocab_type, norm_key):
    init_db()
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM user_vocabulary WHERE vocab_type = ? AND norm_key = ?",
        (vocab_type, norm_key),
    )
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def update_user_vocabulary(vocab_id, value, norm_key):
    init_db()
    conn = _connect()
    cur = conn.cursor()
    now = datetime.utcnow().isoformat(timespec="seconds")
    cur.execute(
        "UPDATE user_vocabulary SET value = ?, norm_key = ?, updated_at = ? WHERE id = ?",
        (value, norm_key, now, int(vocab_id)),
    )
    conn.commit()
    conn.close()


def delete_user_vocabulary(vocab_id):
    init_db()
    conn = _connect()
    cur = conn.cursor()
    cur.execute("DELETE FROM user_vocabulary WHERE id = ?", (int(vocab_id),))
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Preference feedback (v3) — transparent, bounded personalization
# ---------------------------------------------------------------------------

def save_preference_feedback(scope, preference, role_family="", notes=""):
    """Record a resume/recommendation preference. Returns the new row id."""
    init_db()
    conn = _connect()
    cur = conn.cursor()
    now = datetime.utcnow().isoformat(timespec="seconds")
    cur.execute(
        """
        INSERT INTO preference_feedback (scope, role_family, preference, notes, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (scope, str(role_family or ""), preference, notes, now),
    )
    new_id = cur.lastrowid
    conn.commit()
    conn.close()
    return new_id


def get_preference_feedback(scope=None):
    init_db()
    conn = _connect()
    cur = conn.cursor()
    if scope:
        cur.execute("SELECT * FROM preference_feedback WHERE scope = ? ORDER BY id DESC", (scope,))
    else:
        cur.execute("SELECT * FROM preference_feedback ORDER BY id DESC")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


# ---------------------------------------------------------------------------
# Translation feedback (v3.2) — bullet actions + preferred wording
# ---------------------------------------------------------------------------

def save_translation_feedback(
    resume_version_id=None,
    analysis_id=None,
    evidence_item_id=None,
    role_family="",
    source_text="",
    generated_text="",
    final_text=None,
    action_type="keep",
    feedback_tags=None,
    notes="",
    bullet_index=None,
):
    """Persist a bullet-level or resume-level translation feedback row."""
    init_db()
    conn = _connect()
    cur = conn.cursor()
    now = datetime.utcnow().isoformat(timespec="seconds")
    tags = feedback_tags
    if isinstance(tags, (list, tuple)):
        tags = ", ".join(str(t) for t in tags if t)
    cur.execute(
        """
        INSERT INTO translation_feedback (
            resume_version_id, analysis_id, evidence_item_id, role_family,
            source_text, generated_text, final_text, action_type,
            feedback_tags, notes, bullet_index, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            resume_version_id,
            analysis_id,
            evidence_item_id,
            str(role_family or ""),
            source_text or "",
            generated_text or "",
            final_text,
            action_type,
            tags or "",
            notes or "",
            bullet_index,
            now,
        ),
    )
    new_id = cur.lastrowid
    conn.commit()
    conn.close()
    return new_id


def get_translation_feedback(
    resume_version_id=None,
    role_family=None,
    action_type=None,
    limit=50,
):
    """Return translation feedback rows, newest first."""
    init_db()
    conn = _connect()
    cur = conn.cursor()
    clauses = []
    params = []
    if resume_version_id is not None:
        clauses.append("resume_version_id = ?")
        params.append(int(resume_version_id))
    if role_family:
        clauses.append("role_family = ?")
        params.append(role_family)
    if action_type:
        clauses.append("action_type = ?")
        params.append(action_type)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    cur.execute(
        f"SELECT * FROM translation_feedback {where} ORDER BY id DESC LIMIT ?",
        params + [int(limit)],
    )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def get_preferred_wording(role_family, limit=10):
    """Retrieve approved/preferred phrasing for style guidance (not model training)."""
    preferred = get_translation_feedback(role_family=role_family, action_type="preferred", limit=limit)
    edited = get_translation_feedback(role_family=role_family, action_type="edited", limit=limit)
    seen = set()
    out = []
    for row in preferred + edited:
        text = row.get("final_text") or row.get("generated_text") or ""
        if text and text not in seen:
            seen.add(text)
            out.append(row)
        if len(out) >= limit:
            break
    return out


def get_avoid_feedback_tags(role_family):
    """Tags from resume-level reviews to avoid in future wording."""
    init_db()
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT feedback_tags FROM translation_feedback
        WHERE role_family = ? AND action_type = 'resume_review'
        ORDER BY id DESC LIMIT 20
        """,
        (role_family,),
    )
    avoid = {"Overclaims experience", "Too generic"}
    for row in cur.fetchall():
        for tag in (row["feedback_tags"] or "").split(","):
            t = tag.strip()
            if t in ("Overclaims experience", "Too generic", "Poor wording / not how I would say it"):
                avoid.add(t)
    conn.close()
    return sorted(avoid)


def save_resume_review_feedback(
    resume_version_id,
    usefulness,
    feedback_tags=None,
    notes="",
    analysis_id=None,
    role_family="",
):
    """Persist resume-level review (usefulness + optional tags)."""
    return save_translation_feedback(
        resume_version_id=resume_version_id,
        analysis_id=analysis_id,
        role_family=role_family,
        action_type="resume_review",
        feedback_tags=feedback_tags,
        notes=notes,
        source_text=usefulness,
    )


if __name__ == "__main__":
    init_db()
    print(f"Initialized database at {DB_PATH}")
