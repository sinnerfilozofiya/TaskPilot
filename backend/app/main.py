"""FastAPI application entry point."""
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.api import auth, repos, activity, summarize, cursor_auth
from app.config import config

app = FastAPI(
    title="TaskPilot",
    description="GitHub activity summarizer",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[config.FRONTEND_URL, "http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(SessionMiddleware, secret_key=config.SECRET_KEY)

app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(repos.router, prefix="/api/repos", tags=["repos"])
app.include_router(activity.router, prefix="/api/activity", tags=["activity"])
app.include_router(summarize.router, prefix="/api/summarize", tags=["summarize"])
app.include_router(cursor_auth.router, prefix="/api/cursor", tags=["cursor"])


@app.get("/api/health")
def health():
    return {"status": "ok"}


# Serve frontend static (Docker/production: static/ exists; dev: optional)
_static_dir = Path(__file__).resolve().parent.parent / "static"
if _static_dir.exists():
    app.mount("/", StaticFiles(directory=str(_static_dir), html=True), name="static")
