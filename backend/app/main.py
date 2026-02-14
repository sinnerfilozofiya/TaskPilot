"""FastAPI application entry point."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from app.api import auth, repos, activity, summarize
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


@app.get("/api/health")
def health():
    return {"status": "ok"}
