"""Disk cache for Cursor summarize results. Keyed by repo + range + activity fingerprint."""
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

from app.config import config


def _cache_dir() -> Path:
    raw = getattr(config, "SUMMARY_CACHE_DIR", None) or os.getenv("SUMMARY_CACHE_DIR", "")
    if raw:
        p = Path(raw)
    else:
        project_root = Path(__file__).resolve().parents[2]
        p = project_root / ".summary_cache"
    p = p.resolve()
    p.mkdir(parents=True, exist_ok=True)
    return p


def _activity_fingerprint(activity: Dict[str, Any]) -> str:
    """Stable fingerprint from commit SHAs and PR identity only (no request time).
    Same repo + same commits (sha + message + date) + same PRs => same cache key."""
    commits = activity.get("commits") or []
    prs = activity.get("pull_requests") or []
    # Commit identity: full SHA (7-char), first line of message, and date
    commit_part = sorted(
        ((c.get("sha"), (c.get("message") or "").strip()[:200], c.get("date")) for c in commits)
    )
    pr_part = sorted(((p.get("number"), p.get("state"), p.get("updated_at")) for p in prs))
    canonical = {"commits": commit_part, "prs": pr_part}
    return hashlib.sha256(json.dumps(canonical, sort_keys=True).encode()).hexdigest()[:32]


def cache_key(full_name: str, range_kind: str, since: str, until: str, activity: Dict[str, Any]) -> str:
    """Key uses only: repo, range kind, range boundaries (since/until), and content fingerprint (commit SHAs + PRs)."""
    fp = _activity_fingerprint(activity)
    return f"{full_name}:{range_kind}:{since}:{until}:{fp}"


def _path_for_key(key: str) -> Path:
    name = hashlib.sha256(key.encode()).hexdigest()[:32] + ".json"
    return _cache_dir() / name


def get(key: str) -> Optional[Dict[str, Any]]:
    """Return cached result dict (summary, tasks, activity) or None."""
    path = _path_for_key(key)
    if not path.exists():
        return None
    try:
        with open(path, "r") as f:
            data = json.load(f)
        return data.get("result")
    except (json.JSONDecodeError, OSError):
        return None


def set_(key: str, result: Dict[str, Any]) -> None:
    """Store result in cache. result must have summary, tasks, activity."""
    path = _path_for_key(key)
    try:
        with open(path, "w") as f:
            json.dump({"result": result}, f)
    except OSError:
        pass
