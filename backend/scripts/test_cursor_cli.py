#!/usr/bin/env python3
"""Test that the backend can run Cursor CLI with the current config. Run from repo root with .env set."""
import asyncio
import os
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta

# Add backend to path so we can import app
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Load .env from project root or backend
try:
    from dotenv import load_dotenv
    root = Path(__file__).resolve().parents[2]
    load_dotenv(root / ".env")
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
except ImportError:
    pass

from app.config import config
from app.services.llm.cursor_cli_provider import CursorCLIProvider


async def main():
    print("Cursor CLI test")
    print("  LLM_PROVIDER:", config.LLM_PROVIDER)
    print("  CURSOR_API_KEY set:", bool((getattr(config, "CURSOR_API_KEY", "") or "").strip()))
    print("  REPOS_CACHE_DIR:", config.REPOS_CACHE_DIR)

    if config.LLM_PROVIDER.lower() != "cursor":
        print("  -> Set LLM_PROVIDER=cursor in .env to use Cursor CLI")
        return 1

    # Use project root (TaskPilot) as the test repo - it's a git repo
    repo_root = Path(__file__).resolve().parents[2]
    if not (repo_root / ".git").exists():
        print("  -> No .git in project root; run from TaskPilot repo")
        return 1

    provider = CursorCLIProvider()
    since = datetime.now(timezone.utc) - timedelta(days=7)
    until = datetime.now(timezone.utc)
    # Minimal prompt so the agent returns quickly
    label = "Last 7 days (test)"

    print("  Running: cursor agent -p \"...\" in", repo_root)
    print("  Timeout: 90 seconds...")
    try:
        raw = await asyncio.wait_for(
            provider.summarize_tasks_from_repo(
                repo_root, since, until, label, cursor_api_key=None
            ),
            timeout=90.0,
        )
        print("  -> Cursor CLI returned (length:", len(raw), "chars)")
        if raw.strip():
            preview = raw.strip()[:500] + ("..." if len(raw) > 500 else "")
            print("  Preview:", preview)
        else:
            print("  (empty output)")
        print("  OK: Backend can interact with Cursor CLI.")
        return 0
    except FileNotFoundError as e:
        print("  ERROR: Cursor CLI not found. Install it and ensure 'cursor' is on PATH:", e)
        return 1
    except asyncio.TimeoutError:
        print("  ERROR: Cursor CLI timed out after 90s. Try a shorter range or check your network.")
        return 1
    except Exception as e:
        print("  ERROR:", type(e).__name__, str(e))
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
