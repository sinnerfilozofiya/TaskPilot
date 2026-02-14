"""GitHub OAuth: login and callback, session with access token."""
from typing import Optional
from urllib.parse import urlencode

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import RedirectResponse
import httpx

from app.config import config

router = APIRouter()

GITHUB_AUTH_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_USER_URL = "https://api.github.com/user"


@router.get("/login")
def login(request: Request):
    """Redirect to GitHub OAuth consent."""
    if not config.GITHUB_CLIENT_ID:
        raise HTTPException(
            status_code=503,
            detail="GitHub OAuth not configured (GITHUB_CLIENT_ID missing)",
        )
    state = request.session.get("oauth_state") or _random_state()
    request.session["oauth_state"] = state
    params = {
        "client_id": config.GITHUB_CLIENT_ID,
        "redirect_uri": config.GITHUB_CALLBACK_URL,
        "scope": "repo read:user read:org",
        "state": state,
    }
    return RedirectResponse(url=f"{GITHUB_AUTH_URL}?{urlencode(params)}")


@router.get("/callback")
async def callback(request: Request, code: Optional[str] = None, state: Optional[str] = None):
    """Exchange code for token and store in session."""
    if not code:
        raise HTTPException(status_code=400, detail="Missing code")
    saved_state = request.session.get("oauth_state")
    if state != saved_state:
        raise HTTPException(status_code=400, detail="Invalid state")
    request.session.pop("oauth_state", None)

    async with httpx.AsyncClient() as client:
        r = await client.post(
            GITHUB_TOKEN_URL,
            headers={"Accept": "application/json"},
            data={
                "client_id": config.GITHUB_CLIENT_ID,
                "client_secret": config.GITHUB_CLIENT_SECRET,
                "code": code,
                "redirect_uri": config.GITHUB_CALLBACK_URL,
            },
        )
    if r.status_code != 200:
        raise HTTPException(status_code=502, detail="GitHub token exchange failed")
    data = r.json()
    if "access_token" not in data:
        raise HTTPException(status_code=502, detail=data.get("error_description", "No token"))
    token = data["access_token"]
    request.session["github_token"] = token
    # Fetch user id for persisted data (e.g. saved summaries)
    async with httpx.AsyncClient() as client:
        ru = await client.get(
            GITHUB_USER_URL,
            headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github.v3+json"},
        )
    if ru.status_code == 200:
        request.session["github_user_id"] = ru.json().get("id")
    return RedirectResponse(url=f"{config.FRONTEND_URL}/dashboard")


@router.get("/me")
async def me(request: Request):
    """Return current user if logged in."""
    token = request.session.get("github_token")
    if not token:
        return {"logged_in": False}
    async with httpx.AsyncClient() as client:
        r = await client.get(
            GITHUB_USER_URL,
            headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github.v3+json"},
        )
    if r.status_code != 200:
        request.session.pop("github_token", None)
        request.session.pop("github_user_id", None)
        return {"logged_in": False}
    user = r.json()
    request.session["github_user_id"] = user.get("id")
    return {
        "logged_in": True,
        "login": user.get("login"),
        "avatar_url": user.get("avatar_url"),
        "name": user.get("name"),
    }


@router.post("/logout")
def logout(request: Request):
    """Clear session."""
    request.session.clear()
    return {"ok": True}


def _random_state() -> str:
    import secrets
    return secrets.token_urlsafe(24)
