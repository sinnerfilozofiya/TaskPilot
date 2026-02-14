"""Summarize activity for a repo in a time range. Supports GET (blocking) and POST start + GET status (job with progress)."""
import asyncio
import uuid
from pathlib import Path

from datetime import datetime, timedelta, timezone
from typing import Any, Literal, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.config import config
from app.services.github_client import GitHubClient
from app.services.summarizer import summarize_activity
from app.services.repo_clone import ensure_repo_cloned
from app.services.git_context import get_git_log_for_range
from app.services.summary_cache import cache_key, get as cache_get, set_ as cache_set
from app.services.summary_db import get_saved_summary as db_get_saved, save_summary as db_save_summary

router = APIRouter()

RangeKind = Literal["day", "week", "month"]

# In-memory job store; for multi-worker use a shared store (e.g. Redis)
_summarize_jobs: dict[str, dict[str, Any]] = {}
_jobs_lock = asyncio.Lock()
# Max chars of Cursor CLI log to keep per job (keep tail so UI stays responsive)
CURSOR_LOG_MAX_CHARS = 80_000


def _range_to_dates(range_kind: RangeKind) -> tuple[datetime, datetime]:
    now = datetime.now(timezone.utc)
    if range_kind == "day":
        since = now - timedelta(days=1)
    elif range_kind == "week":
        since = now - timedelta(weeks=1)
    else:
        since = now - timedelta(days=30)
    return since, now


async def _run_summarize_job(
    job_id: str, owner: str, repo: str, range_kind: RangeKind, token: str,
    user_id: Optional[int] = None,
) -> None:
    full_name = f"{owner}/{repo}"
    since, until = _range_to_dates(range_kind)
    cache_dir = Path(config.REPOS_CACHE_DIR)
    if not cache_dir.is_absolute():
        cache_dir = cache_dir.resolve()

    async def update(status: str, message: Optional[str] = None, result: Optional[dict] = None, error: Optional[str] = None) -> None:
        async with _jobs_lock:
            _summarize_jobs[job_id].update({
                "status": status,
                "message": message or _summarize_jobs[job_id].get("message"),
                "result": result if result is not None else _summarize_jobs[job_id].get("result"),
                "error": error,
            })

    repo_path = None
    try:
        activity = await (GitHubClient(token).get_activity(full_name, since, until))
    except Exception as e:
        await update("error", error=str(e))
        return

    try:
        if config.LLM_PROVIDER.lower() == "cursor":
            key = cache_key(
                full_name,
                range_kind,
                activity["since"],
                activity["until"],
                activity,
            )
            cached = cache_get(key)
            if cached:
                payload = {
                    "repo": full_name,
                    "range": range_kind,
                    "since": cached["since"],
                    "until": cached["until"],
                    "summary": cached["summary"],
                    "summary_tasks": cached["summary_tasks"],
                    "activity": cached["activity"],
                }
                if user_id is not None:
                    try:
                        db_save_summary(user_id, full_name, range_kind, payload)
                    except Exception:
                        pass
                await update("done", message="Done (cached).", result=payload)
                return
            await update("cloning", "Cloning repository...")
            try:
                repo_path = await ensure_repo_cloned(full_name, token, cache_dir)
            except Exception as e:
                await update("error", error=str(e))
                return
            await update("git_log", "Fetching git history...")
            git_log_text = await get_git_log_for_range(
                repo_path, since, until,
                max_chars=getattr(config, "GIT_LOG_MAX_CHARS", 50000),
            )
            await update("cursor", "Analyzing with Cursor...")

            async def append_cursor_log(chunk: str) -> None:
                async with _jobs_lock:
                    job = _summarize_jobs.get(job_id)
                    if job is None:
                        return
                    current = job.get("cursor_log", "") + chunk
                    if len(current) > CURSOR_LOG_MAX_CHARS:
                        current = "... (truncated)\n" + current[-CURSOR_LOG_MAX_CHARS:]
                    job["cursor_log"] = current

            result = await summarize_activity(
                activity,
                range_kind,
                repo_path=repo_path,
                git_log_text=git_log_text,
                cursor_log_callback=append_cursor_log,
            )
            payload = {
                "repo": full_name,
                "range": range_kind,
                "since": activity["since"],
                "until": activity["until"],
                "summary": result["summary"],
                "summary_tasks": result["tasks"],
                "activity": activity,
            }
            cache_set(key, payload)
        else:
            await update("cursor", "Analyzing...")
            result = await summarize_activity(activity, range_kind)

        payload = {
            "repo": full_name,
            "range": range_kind,
            "since": activity["since"],
            "until": activity["until"],
            "summary": result["summary"],
            "summary_tasks": result["tasks"],
            "activity": activity,
        }
        if user_id is not None:
            try:
                db_save_summary(user_id, full_name, range_kind, payload)
            except Exception:
                pass
        await update("done", message="Done.", result=payload)
    except Exception as e:
        await update("error", error=str(e))


class SummarizeStartBody(BaseModel):
    owner: str
    repo: str
    range: RangeKind = "week"


@router.post("/start")
async def post_summarize_start(request: Request, body: SummarizeStartBody):
    """Start a summarize job; returns job_id. Poll GET /status/{job_id} for progress and result."""
    token = request.session.get("github_token")
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    job_id = str(uuid.uuid4())
    async with _jobs_lock:
        _summarize_jobs[job_id] = {
            "status": "cloning",
            "message": "Cloning repository...",
            "result": None,
            "error": None,
            "cursor_log": "",
        }
    user_id = request.session.get("github_user_id")
    asyncio.create_task(_run_summarize_job(
        job_id, body.owner, body.repo, body.range, token, user_id=user_id
    ))
    return {"job_id": job_id}


@router.get("/status/{job_id}")
async def get_summarize_status(job_id: str):
    """Return current job status, message, and result (if done) or error (if error)."""
    async with _jobs_lock:
        job = _summarize_jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return {
        "status": job["status"],
        "message": job.get("message"),
        "result": job.get("result"),
        "error": job.get("error"),
        "cursor_log": job.get("cursor_log", ""),
    }


@router.get("/saved")
async def get_saved(request: Request, owner: str, repo: str, range: RangeKind = "week"):
    """Return the persisted summary for this user + repo + range (if any). Survives reload."""
    user_id = request.session.get("github_user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    full_name = f"{owner}/{repo}"
    saved = db_get_saved(user_id, full_name, range)
    if saved is None:
        raise HTTPException(status_code=404, detail="No saved summary")
    return {
        "repo": saved["repo"],
        "range": saved["range"],
        "since": saved["since"],
        "until": saved["until"],
        "summary": saved["summary"],
        "summary_tasks": saved["summary_tasks"],
        "activity": saved["activity"],
    }


@router.get("/{owner}/{repo}")
async def get_summary(
    request: Request,
    owner: str,
    repo: str,
    range: RangeKind = "week",
):
    """Fetch activity for the repo in the range and return summary + raw activity (blocking)."""
    token = request.session.get("github_token")
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    full_name = f"{owner}/{repo}"
    since, until = _range_to_dates(range)
    client = GitHubClient(token)
    try:
        activity = await client.get_activity(full_name, since, until)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))

    if config.LLM_PROVIDER.lower() == "cursor":
        key = cache_key(
            full_name, range, activity["since"], activity["until"], activity
        )
        cached = cache_get(key)
        if cached:
            out = {
                "repo": full_name,
                "range": range,
                "since": cached["since"],
                "until": cached["until"],
                "summary": cached["summary"],
                "summary_tasks": cached["summary_tasks"],
                "activity": cached["activity"],
            }
            user_id = request.session.get("github_user_id")
            if user_id is not None:
                try:
                    db_save_summary(user_id, full_name, range, out)
                except Exception:
                    pass
            return out

    repo_path = None
    git_log_text = None
    if config.LLM_PROVIDER.lower() == "cursor":
        cache_dir = Path(config.REPOS_CACHE_DIR)
        if not cache_dir.is_absolute():
            cache_dir = Path(config.REPOS_CACHE_DIR).resolve()
        try:
            repo_path = await ensure_repo_cloned(full_name, token, cache_dir)
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Repo clone failed: {e}")
        git_log_text = await get_git_log_for_range(
            repo_path, since, until,
            max_chars=getattr(config, "GIT_LOG_MAX_CHARS", 50000),
        )

    try:
        result = await summarize_activity(
            activity,
            range,
            repo_path=repo_path,
            git_log_text=git_log_text,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Summarization failed: {e}")

    if config.LLM_PROVIDER.lower() == "cursor":
        key = cache_key(
            full_name, range, activity["since"], activity["until"], activity
        )
        payload = {
            "repo": full_name,
            "range": range,
            "since": activity["since"],
            "until": activity["until"],
            "summary": result["summary"],
            "summary_tasks": result["tasks"],
            "activity": activity,
        }
        cache_set(key, payload)

    out = {
        "repo": full_name,
        "range": range,
        "since": activity["since"],
        "until": activity["until"],
        "summary": result["summary"],
        "summary_tasks": result["tasks"],
        "activity": activity,
    }
    user_id = request.session.get("github_user_id")
    if user_id is not None:
        try:
            db_save_summary(user_id, full_name, range, out)
        except Exception:
            pass
    return out
