"""Fetch activity (commits + PRs) for a repo in a time range."""
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, HTTPException, Request

from app.services.github_client import GitHubClient

router = APIRouter()

RangeKind = Literal["day", "week", "month"]


def _range_to_dates(range_kind: RangeKind) -> tuple[datetime, datetime]:
    now = datetime.now(timezone.utc)
    if range_kind == "day":
        since = now - timedelta(days=1)
    elif range_kind == "week":
        since = now - timedelta(weeks=1)
    else:  # month
        since = now - timedelta(days=30)
    return since, now


@router.get("/{owner}/{repo}")
async def get_activity(
    request: Request,
    owner: str,
    repo: str,
    range: RangeKind = "week",
):
    """Get commits and PRs for the repo in the given time range (day, week, month)."""
    token = request.session.get("github_token")
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    full_name = f"{owner}/{repo}"
    since, until = _range_to_dates(range)
    client = GitHubClient(token)
    try:
        data = await client.get_activity(full_name, since, until)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))
    return data
