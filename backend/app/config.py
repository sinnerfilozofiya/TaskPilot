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


class Config:
    # GitHub OAuth
    GITHUB_CLIENT_ID: str = os.getenv("GITHUB_CLIENT_ID", "")
    GITHUB_CLIENT_SECRET: str = os.getenv("GITHUB_CLIENT_SECRET", "")
    GITHUB_CALLBACK_URL: str = os.getenv(
        "GITHUB_CALLBACK_URL", "http://localhost:8000/api/auth/callback"
    )
    FRONTEND_URL: str = os.getenv("FRONTEND_URL", "http://localhost:5173")

    # Session
    SECRET_KEY: str = os.getenv("SECRET_KEY", "change-me-in-production")

    # LLM
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "ollama")  # ollama | huggingface
    OLLAMA_HOST: str = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "llama3.2")
    OLLAMA_TEMPERATURE: str = os.getenv("OLLAMA_TEMPERATURE", "")  # e.g. 0.4 for consistency
    HF_TOKEN: str = os.getenv("HF_TOKEN", "")
    HF_MODEL: str = os.getenv("HF_MODEL", "mistralai/Mistral-7B-Instruct-v0.2")


config = Config()
