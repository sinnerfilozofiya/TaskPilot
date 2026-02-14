"""SQLite persistence for user summaries so they survive reload."""
import json
import os
import sqlite3
from pathlib import Path
from typing import Any, Dict, Optional

from app.config import config


def _db_path() -> Path:
    raw = getattr(config, "SUMMARY_DB_PATH", None) or os.getenv("SUMMARY_DB_PATH", "")
    if raw:
        p = Path(raw)
    else:
        project_root = Path(__file__).resolve().parents[2]
        p = project_root / "taskpilot_summaries.db"
    return p.resolve()


def _get_conn() -> sqlite3.Connection:
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS saved_summaries (
            user_id INTEGER NOT NULL,
            repo TEXT NOT NULL,
            range_kind TEXT NOT NULL,
            summary TEXT NOT NULL,
            summary_tasks_json TEXT NOT NULL,
            activity_json TEXT NOT NULL,
            since TEXT NOT NULL,
            until TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (user_id, repo, range_kind)
        )
        """
    )
    conn.commit()
    return conn


def save_summary(
    user_id: int,
    repo: str,
    range_kind: str,
    payload: Dict[str, Any],
) -> None:
    """Store or overwrite the latest summary for this user + repo + range."""
    from datetime import datetime, timezone
    summary = payload.get("summary") or ""
    summary_tasks = payload.get("summary_tasks") or []
    activity = payload.get("activity") or {}
    since = payload.get("since") or ""
    until = payload.get("until") or ""
    updated_at = datetime.now(timezone.utc).isoformat()
    conn = _get_conn()
    try:
        conn.execute(
            """
            INSERT OR REPLACE INTO saved_summaries
            (user_id, repo, range_kind, summary, summary_tasks_json, activity_json, since, until, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                repo,
                range_kind,
                summary,
                json.dumps(summary_tasks),
                json.dumps(activity),
                since,
                until,
                updated_at,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def get_saved_summary(
    user_id: int,
    repo: str,
    range_kind: str,
) -> Optional[Dict[str, Any]]:
    """Return the saved summary for this user + repo + range, or None."""
    conn = _get_conn()
    try:
        row = conn.execute(
            """
            SELECT summary, summary_tasks_json, activity_json, since, until
            FROM saved_summaries
            WHERE user_id = ? AND repo = ? AND range_kind = ?
            """,
            (user_id, repo, range_kind),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return None
    summary, summary_tasks_json, activity_json, since, until = row
    try:
        summary_tasks = json.loads(summary_tasks_json) if summary_tasks_json else []
        activity = json.loads(activity_json) if activity_json else {}
    except (TypeError, ValueError):
        return None
    return {
        "repo": repo,
        "range": range_kind,
        "since": since or "",
        "until": until or "",
        "summary": summary or "",
        "summary_tasks": summary_tasks,
        "activity": activity,
    }
