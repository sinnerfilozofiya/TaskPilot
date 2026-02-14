"""List repos for the authenticated user (optional multi-contributor filter)."""
import httpx
from fastapi import APIRouter, HTTPException, Request

from app.services.github_client import GitHubClient

router = APIRouter()


@router.get("")
async def list_repos(
    request: Request,
    multi_contributor: bool = False,
):
    """List repositories the user can access. If multi_contributor=true, only repos with 2+ contributors."""
    token = request.session.get("github_token")
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    client = GitHubClient(token)
    try:
        repos = await client.get_user_repos(only_multi_contributor=multi_contributor)
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))
    return {
        "repos": [
            {
                "full_name": r["full_name"],
                "name": r["name"],
                "private": r.get("private", False),
                "description": r.get("description"),
                "updated_at": r.get("updated_at"),
            }
            for r in repos
        ],
    }
