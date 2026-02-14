"""Application configuration from environment."""
import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root (TaskPilot/) or backend/
for base in [Path(__file__).resolve().parents[2], Path(__file__).resolve().parents[1]]:
    env_path = base / ".env"
    if env_path.exists():
        load_dotenv(env_path)
        break


def _base_url() -> str:
    """Single base URL for the app (e.g. https://taskpilot.example.com). No trailing slash."""
    raw = os.getenv("APP_URL", "").strip().rstrip("/")
    if raw:
        return raw
    return ""

def _callback_url() -> str:
    if _base_url():
        return f"{_base_url()}/api/auth/callback"
    return os.getenv("GITHUB_CALLBACK_URL", "http://localhost:8000/api/auth/callback")

def _frontend_url() -> str:
    if _base_url():
        return _base_url()
    return os.getenv("FRONTEND_URL", "http://localhost:5173")


class Config:
    # GitHub OAuth (set APP_URL in production and callback/frontend are derived automatically)
    GITHUB_CLIENT_ID: str = os.getenv("GITHUB_CLIENT_ID", "")
    GITHUB_CLIENT_SECRET: str = os.getenv("GITHUB_CLIENT_SECRET", "")
    GITHUB_CALLBACK_URL: str = _callback_url()
    FRONTEND_URL: str = _frontend_url()

    # Session
    SECRET_KEY: str = os.getenv("SECRET_KEY", "change-me-in-production")

    # LLM
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "ollama")  # ollama | huggingface | cursor
    OLLAMA_HOST: str = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "llama3.2")
    OLLAMA_TEMPERATURE: str = os.getenv("OLLAMA_TEMPERATURE", "")  # e.g. 0.4 for consistency
    HF_TOKEN: str = os.getenv("HF_TOKEN", "")
    HF_MODEL: str = os.getenv("HF_MODEL", "mistralai/Mistral-7B-Instruct-v0.2")

    # Cursor CLI (when LLM_PROVIDER=cursor)
    _REPOS_CACHE_DIR_RAW: str = os.getenv("REPOS_CACHE_DIR", ".repos_cache")
    CURSOR_API_KEY: str = os.getenv("CURSOR_API_KEY", "")  # optional server fallback
    CURSOR_CLI_TIMEOUT: int = int(os.getenv("CURSOR_CLI_TIMEOUT", "300"))  # seconds
    GIT_LOG_MAX_CHARS: int = int(os.getenv("GIT_LOG_MAX_CHARS", "50000"))  # truncate pre-computed git log

    @property
    def REPOS_CACHE_DIR(self) -> str:
        """Resolve repo cache dir: if relative, under project root so it's consistent regardless of cwd."""
        p = Path(self._REPOS_CACHE_DIR_RAW)
        if not p.is_absolute():
            # Project root = parent of backend (TaskPilot/)
            project_root = Path(__file__).resolve().parents[2]
            p = (project_root / self._REPOS_CACHE_DIR_RAW).resolve()
        return str(p)


config = Config()
