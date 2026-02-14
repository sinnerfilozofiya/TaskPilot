"""Clone or update a GitHub repo to a local cache for Cursor CLI to run in."""
import asyncio
import re
from pathlib import Path
from urllib.parse import quote_plus

# One lock per repo to avoid concurrent clone/fetch on same repo
_repo_locks: dict[str, asyncio.Lock] = {}
_lock_mutex = asyncio.Lock()

# Sanitize repo name for use as directory name (owner_repo)
_REPO_DIR_PATTERN = re.compile(r"^[a-zA-Z0-9_.-]+$")


def _safe_dir_name(full_name: str) -> str:
    """Return a safe directory name from owner/repo."""
    if _REPO_DIR_PATTERN.match(full_name.replace("/", "_")):
        return full_name.replace("/", "_")
    return quote_plus(full_name).replace("/", "_").replace("+", "_")


def _clone_url(full_name: str, token: str) -> str:
    """Build HTTPS clone URL with token for private repos."""
    return f"https://x-access-token:{token}@github.com/{full_name}.git"


async def _get_repo_lock(full_name: str) -> asyncio.Lock:
    async with _lock_mutex:
        if full_name not in _repo_locks:
            _repo_locks[full_name] = asyncio.Lock()
        return _repo_locks[full_name]


async def ensure_repo_cloned(
    full_name: str,
    token: str,
    cache_dir: Path,
) -> Path:
    """
    Ensure the repo is cloned (or updated) at cache_dir / safe_name.
    Returns the repo root Path. Uses asyncio subprocess for git.
    One operation per repo at a time (lock per full_name).
    """
    async with await _get_repo_lock(full_name):
        return await _ensure_repo_cloned_impl(full_name, token, cache_dir)


async def _ensure_repo_cloned_impl(
    full_name: str,
    token: str,
    cache_dir: Path,
) -> Path:
    cache_dir = Path(cache_dir).resolve()
    cache_dir.mkdir(parents=True, exist_ok=True)
    dir_name = _safe_dir_name(full_name)
    repo_path = cache_dir / dir_name

    if not repo_path.exists():
        pass  # will clone below
    elif (repo_path / ".git").exists():
        # Update existing clone (fetch all branches)
        proc = await asyncio.create_subprocess_exec(
            "git",
            "fetch",
            "origin",
            "--prune",
            cwd=str(repo_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.wait()
        # Non-zero is ok (e.g. no network); we still have a clone
        return repo_path

    # Clone (full history for git log across branches)
    url = _clone_url(full_name, token)
    proc = await asyncio.create_subprocess_exec(
        "git",
        "clone",
        "--no-single-branch",
        url,
        str(repo_path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        err = (stderr or b"").decode().strip() or (stdout or b"").decode().strip()
        raise RuntimeError(f"git clone failed: {err}")
    return repo_path
