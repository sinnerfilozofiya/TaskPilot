"""Cursor CLI provider: run `cursor agent -p "..."` in repo dir to analyze git changes and output tasks JSON.
Cursor uses browser login by default (no API key); the CLI uses the auth from the machine where it runs."""
import asyncio
import os
from datetime import datetime
from pathlib import Path
from typing import Awaitable, Callable, Optional

from app.config import config
from app.services.llm.base import LLMProvider


def _format_iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _build_analysis_prompt(
    since: datetime,
    until: datetime,
    range_label: str,
    repo_name: Optional[str] = None,
    git_log_text: Optional[str] = None,
) -> str:
    since_s = _format_iso(since)
    until_s = _format_iso(until)
    repo_line = f"Repository: {repo_name}." if repo_name else "You are in the repository root."
    if git_log_text is not None and git_log_text.strip():
        return (
            repo_line + " "
            f"Time range: {since_s} to {until_s} ({range_label}). "
            "Below is the git activity in this period (commit messages and diffs). Analyze it and the codebase in this directory. "
            "Summarize: (1) what the commit messages say, (2) what actually changed in the code, (3) what has been going on across branches. "
            "Produce a short narrative summary (2-4 sentences) and 5-12 concrete tasks (what was done, what changed). "
            "Output ONLY a single JSON object with exactly two keys: \"summary\" (string, the narrative) and \"tasks\" (array of objects with \"title\" and \"description\"). "
            "No markdown, no code fences, no text outside the JSON. Example: {\"summary\": \"...\", \"tasks\": [{\"title\": \"...\", \"description\": \"...\"}, ...]}.\n\n"
            "Git log:\n" + git_log_text.strip()
        )
    return (
        repo_line + " "
        f"Time range: {since_s} to {until_s} ({range_label}). "
        "Analyze what happened in this period: run `git branch -a` to see branches, then `git log -p --all --since=\"" + since_s + "\" --until=\"" + until_s + "\"` to see commit messages and code diffs across all branches. Use the codebase as needed. "
        "Summarize: (1) what the commit messages say, (2) what actually changed in the code, (3) what has been going on across branches. "
        "Produce a short narrative summary (2-4 sentences) and 5-12 concrete tasks (what was done, what changed). "
        "Output ONLY a single JSON object with exactly two keys: \"summary\" (string, the narrative) and \"tasks\" (array of objects with \"title\" and \"description\"). "
        "No markdown, no code fences, no text outside the JSON. Example: {\"summary\": \"...\", \"tasks\": [{\"title\": \"...\", \"description\": \"...\"}, ...]}."
    )


class CursorCLIProvider(LLMProvider):
    """Run Cursor CLI in a cloned repo directory to produce task list from git + codebase."""

    async def verify_cli_available(self, timeout: float = 5.0) -> str:
        """Run `cursor --version` or `agent --version` to verify CLI is installed and on PATH.
        Returns version string (or first line of output). Raises on failure or timeout."""
        for argv in [["cursor", "--version"], ["agent", "--version"]]:
            try:
                proc = await asyncio.create_subprocess_exec(
                    argv[0],
                    *argv[1:],
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                )
            except FileNotFoundError:
                continue
            try:
                stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                raise RuntimeError("Cursor CLI version check timed out.")
            if proc.returncode == 0:
                if stdout:
                    return stdout.decode(errors="replace").strip().split("\n")[0]
                return "Cursor CLI available"
        raise FileNotFoundError(
            "Cursor CLI not found. Install it (see https://cursor.com/docs/cli) and ensure 'cursor' or 'agent' is on PATH."
        )

    async def summarize(self, activity_text: str, repo_name: str, range_label: str) -> str:
        """Not used when provider is Cursor; summarize_tasks_from_repo is used instead."""
        return ""

    async def summarize_tasks(self, activity_text: str, repo_name: str, range_label: str) -> str:
        """Not used when provider is Cursor; summarize_tasks_from_repo is used instead."""
        return ""

    async def summarize_tasks_from_repo(
        self,
        repo_path: Path,
        since: datetime,
        until: datetime,
        range_label: str,
        cursor_api_key: Optional[str] = None,
        repo_name: Optional[str] = None,
        git_log_text: Optional[str] = None,
        log_callback: Optional[Callable[[str], Awaitable[None]]] = None,
    ) -> str:
        """Run Cursor CLI in repo_path with analysis prompt; return raw stdout (JSON object or array).
        If git_log_text is provided, prompt pastes it so Cursor does not run git. Otherwise Cursor runs git itself.
        If log_callback is provided, stream stdout and stderr to it as output is produced."""
        prompt = _build_analysis_prompt(since, until, range_label, repo_name, git_log_text)
        env = dict(os.environ)
        key = (cursor_api_key or getattr(config, "CURSOR_API_KEY", "") or "").strip()
        if key:
            env["CURSOR_API_KEY"] = key
        timeout = getattr(config, "CURSOR_CLI_TIMEOUT", 300) or 300
        # --trust: non-interactive; we trust the cloned repo dir (required in Docker/headless)
        for argv in [["agent", "--trust", "-p", prompt], ["cursor", "agent", "--trust", "-p", prompt]]:
            try:
                proc = await asyncio.create_subprocess_exec(
                    argv[0],
                    *argv[1:],
                    cwd=str(repo_path),
                    env=env,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
            except FileNotFoundError:
                continue

            async def read_stream(stream: asyncio.StreamReader) -> str:
                buf: list[str] = []
                while True:
                    line = await stream.readline()
                    if not line:
                        break
                    decoded = line.decode(errors="replace")
                    if log_callback:
                        await log_callback(decoded)
                    buf.append(decoded)
                return "".join(buf)

            stdout_task = asyncio.create_task(read_stream(proc.stdout))
            stderr_task = asyncio.create_task(read_stream(proc.stderr))
            try:
                await asyncio.wait_for(proc.wait(), timeout=float(timeout))
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                await stdout_task
                await stderr_task
                raise RuntimeError(
                    f"Cursor CLI timed out after {timeout} seconds. Try a shorter time range or check the repo size."
                )
            stdout = await stdout_task
            stderr = await stderr_task

            if proc.returncode != 0:
                err = (stderr or stdout).strip()
                raise RuntimeError(f"Cursor CLI failed: {err}")
            return (stdout or "").strip()
        raise RuntimeError(
            "Cursor CLI not found. Install it (see https://cursor.com/docs/cli) and ensure 'agent' or 'cursor' is on PATH."
        )
