"""Pre-compute git log for a time range in a repo (for Cursor prompt)."""
import asyncio
from datetime import datetime
from pathlib import Path


def _format_iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


async def get_git_log_for_range(
    repo_path: Path,
    since: datetime,
    until: datetime,
    max_chars: int = 50000,
    timeout_sec: float = 60.0,
) -> str:
    """
    Run git log -p --all --since=... --until=... in repo_path; return stdout, truncated to last max_chars.
    Returns empty string on failure or timeout.
    """
    since_s = _format_iso(since)
    until_s = _format_iso(until)
    proc = await asyncio.create_subprocess_exec(
        "git",
        "log",
        "-p",
        "--all",
        f"--since={since_s}",
        f"--until={until_s}",
        cwd=str(repo_path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout_sec)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return ""
    if proc.returncode != 0:
        return ""
    raw = (stdout or b"").decode("utf-8", errors="replace")
    if len(raw) <= max_chars:
        return raw
    truncated = raw[-max_chars:]
    return f"[Output truncated; showing last {max_chars} characters.]\n{truncated}"
