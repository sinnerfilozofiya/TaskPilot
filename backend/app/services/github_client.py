"""GitHub API client: repos, commits, PRs for a given time range."""
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

GITHUB_API = "https://api.github.com"


class GitHubClient:
    def __init__(self, token: str):
        self._token = token
        self._headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github.v3+json",
        }

    async def get_user_repos(
        self, only_multi_contributor: bool = False
    ) -> list[dict[str, Any]]:
        """List repos the user has access to (owned + orgs). Optionally filter to multi-contributor."""
        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"{GITHUB_API}/user/repos",
                headers=self._headers,
                params={"sort": "updated", "per_page": 100, "affiliation": "owner,collaborator,organization_member"},
            )
            if r.status_code == 403 and "rate limit" in (r.text or "").lower():
                raise httpx.HTTPStatusError(
                    "GitHub API rate limit exceeded. Try again later.",
                    request=r.request,
                    response=r,
                )
            if r.status_code != 200:
                raise httpx.HTTPStatusError(
                    f"GitHub API error: {r.status_code}", request=r.request, response=r
                )
            repos = r.json()
        if not only_multi_contributor:
            return repos
        out = []
        for repo in repos:
            full_name = repo["full_name"]
            try:
                n = await self.get_contributor_count(full_name)
                if n > 1:
                    out.append(repo)
            except Exception:
                continue
        return out

    async def get_contributor_count(self, full_name: str) -> int:
        """Number of contributors (first page is 30; we only need >1)."""
        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"{GITHUB_API}/repos/{full_name}/contributors",
                headers=self._headers,
                params={"per_page": 2},
            )
            if r.status_code != 200:
                return 0
            return len(r.json())

    async def get_default_branch(self, full_name: str) -> str:
        """Default branch name (e.g. main)."""
        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"{GITHUB_API}/repos/{full_name}",
                headers=self._headers,
            )
            if r.status_code != 200:
                return "main"
            return (r.json().get("default_branch") or "main")

    async def get_branches(self, full_name: str, limit: int = 25) -> list[str]:
        """List branch names (up to limit)."""
        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"{GITHUB_API}/repos/{full_name}/branches",
                headers=self._headers,
                params={"per_page": limit},
            )
            if r.status_code != 200:
                return []
            return [b.get("name") for b in (r.json() or []) if b.get("name")]

    async def get_commits(
        self,
        full_name: str,
        since: datetime,
        until: datetime,
        sha: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """Commits in the repo (or on branch sha) between since and until."""
        params = {
            "since": since.isoformat(),
            "until": until.isoformat(),
            "per_page": 100,
        }
        if sha:
            params["sha"] = sha
        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"{GITHUB_API}/repos/{full_name}/commits",
                headers=self._headers,
                params=params,
            )
            if r.status_code != 200:
                raise httpx.HTTPStatusError(
                    f"GitHub API error: {r.status_code}", request=r.request, response=r
                )
            return r.json()

    async def get_pull_requests(
        self, full_name: str, since: datetime, until: datetime
    ) -> list[dict[str, Any]]:
        """PRs updated in the window (state=all)."""
        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"{GITHUB_API}/repos/{full_name}/pulls",
                headers=self._headers,
                params={"state": "all", "sort": "updated", "direction": "desc", "per_page": 100},
            )
            if r.status_code != 200:
                raise httpx.HTTPStatusError(
                    f"GitHub API error: {r.status_code}", request=r.request, response=r
                )
            all_prs = r.json()
        # Filter by updated_at in range
        out = []
        for pr in all_prs:
            raw = pr.get("updated_at") or pr.get("created_at")
            if not raw:
                continue
            updated = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if since <= updated <= until:
                out.append(pr)
        return out

    def _commit_row(self, c: dict[str, Any], branch: str, merged: bool) -> dict[str, Any]:
        commit = c.get("commit") or {}
        author = commit.get("author") or {}
        return {
            "sha": (c.get("sha") or "")[:7],
            "message": (commit.get("message") or "").split("\n")[0],
            "author": author.get("name") or (c.get("author") or {}).get("login") or "?",
            "date": author.get("date") or "",
            "branch": branch,
            "merged": merged,
        }

    async def get_activity(
        self, full_name: str, since: datetime, until: datetime
    ) -> dict[str, Any]:
        """Aggregated activity: commits from all branches (with branch + merged), and PRs."""
        default_branch = await self.get_default_branch(full_name)
        branches = await self.get_branches(full_name)
        if not branches:
            branches = [default_branch]

        # Commits on default branch in range -> used to know which SHAs are "merged"
        default_commits = await self.get_commits(full_name, since, until, sha=default_branch)
        main_shas = {c.get("sha") for c in default_commits if c.get("sha")}

        # Process default branch first so its commits get merged=True and branch=default; then other branches
        rest = [b for b in branches if b != default_branch]
        ordered_branches = [default_branch] + rest
        seen_shas = set()
        commit_list = []
        for branch in ordered_branches:
            try:
                commits = await self.get_commits(full_name, since, until, sha=branch)
            except Exception:
                continue
            for c in commits:
                sha = c.get("sha")
                if not sha or sha in seen_shas:
                    continue
                seen_shas.add(sha)
                merged = sha in main_shas
                commit_list.append(self._commit_row(c, branch, merged))
        # Sort by date descending
        commit_list.sort(key=lambda x: x.get("date") or "", reverse=True)

        prs = await self.get_pull_requests(full_name, since, until)
        return {
            "repo": full_name,
            "since": since.isoformat(),
            "until": until.isoformat(),
            "default_branch": default_branch,
            "branches": branches,
            "commits": commit_list,
            "pull_requests": [
                {
                    "number": pr.get("number"),
                    "title": pr.get("title"),
                    "state": pr.get("state"),
                    "user": (pr.get("user") or {}).get("login"),
                    "updated_at": pr.get("updated_at"),
                    "merged_at": pr.get("merged_at"),
                }
                for pr in prs
            ],
        }
