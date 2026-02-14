#!/usr/bin/env python3
"""Test summarizer parsing and optionally call the real API. Run from repo root with .env set."""
import json
import os
import sys

# Add backend to path so we can import app
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Load .env from project root
from pathlib import Path
try:
    from dotenv import load_dotenv
    root = Path(__file__).resolve().parents[2]
    load_dotenv(root / ".env")
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
except ImportError:
    pass

from app.services.summarizer import _parse_tasks_from_response, summarize_activity


def test_parser():
    """Test with a sample HF-style response (markdown JSON block)."""
    sample = '''```json
[
  {"title": "Add health check to Docker", "description": "Docker health check was fixed."},
  {"title": "Contact form", "description": "New contact form with email."}
]
```'''
    tasks = _parse_tasks_from_response(sample)
    assert len(tasks) == 2, f"Expected 2 tasks, got {len(tasks)}: {tasks}"
    assert tasks[0]["title"] == "Add health check to Docker"
    print("Parser test (markdown block): OK")

    # Trailing comma
    sample2 = '[{"title": "A", "description": "B"},]'
    tasks2 = _parse_tasks_from_response(sample2)
    assert len(tasks2) >= 1, f"Expected at least 1 task with trailing comma, got {tasks2}"
    print("Parser test (trailing comma): OK")


def test_live():
    """Call real summarize_activity (uses HF/Ollama from env)."""
    from app.services.summarizer import _activity_to_text, _range_label
    import asyncio

    activity = {
        "repo": "test/repo",
        "since": "2025-02-01T00:00:00Z",
        "until": "2025-02-14T00:00:00Z",
        "commits": [
            {"sha": "abc123", "message": "Fix Docker health check", "author": "dev", "date": "2025-02-10"},
            {"sha": "def456", "message": "Add contact form", "author": "dev", "date": "2025-02-11"},
        ],
        "pull_requests": [],
    }
    result = asyncio.run(summarize_activity(activity, "week"))
    tasks = result.get("tasks") or []
    summary = result.get("summary") or ""
    print(f"Tasks: {len(tasks)}, summary length: {len(summary)}")
    if tasks:
        print("First task:", json.dumps(tasks[0], indent=2))


if __name__ == "__main__":
    test_parser()
    if os.getenv("HF_TOKEN") or os.getenv("OLLAMA_HOST"):
        print("\nRunning live summarize (may take a few seconds)...")
        test_live()
    else:
        print("\nSkipping live test (set HF_TOKEN or use Ollama).")
