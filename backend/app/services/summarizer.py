"""Build activity text and call LLM to produce structured task list."""
import json
import re
from typing import Any, Dict, List

from app.config import config
from app.services.llm.base import LLMProvider
from app.services.llm.ollama_provider import OllamaProvider
from app.services.llm.huggingface_provider import HuggingFaceProvider


def _get_provider() -> LLMProvider:
    if config.LLM_PROVIDER.lower() == "huggingface":
        return HuggingFaceProvider()
    return OllamaProvider()


def _activity_to_text(activity: dict) -> str:
    lines = []
    repo = activity.get("repo", "")
    commits = activity.get("commits", [])
    prs = activity.get("pull_requests", [])

    lines.append(f"Commits ({len(commits)}), across all branches:")
    for c in commits[:50]:
        author = c.get("author", "?")
        msg = (c.get("message") or "").strip()
        date = c.get("date", "")
        branch = c.get("branch", "?")
        merged = c.get("merged", False)
        status = "merged" if merged else "open"
        lines.append(f"  - [{author}] branch={branch} [{status}] {msg} ({date})")
    if len(commits) > 50:
        lines.append(f"  ... and {len(commits) - 50} more")

    lines.append("")
    lines.append(f"Pull requests ({len(prs)}):")
    for pr in prs[:30]:
        num = pr.get("number", "?")
        title = pr.get("title", "")
        state = pr.get("state", "")
        user = pr.get("user", "?")
        lines.append(f"  - #{num} {title} [{state}] by {user}")
    if len(prs) > 30:
        lines.append(f"  ... and {len(prs) - 30} more")

    return "\n".join(lines)


def _range_label(range_kind: str) -> str:
    if range_kind == "day":
        return "Last 24 hours"
    if range_kind == "week":
        return "Last 7 days"
    return "Last 30 days"


def _parse_tasks_from_response(raw: str) -> List[Dict[str, str]]:
    """Extract JSON array of {title, description} from LLM response. Strips markdown and scrapes only the array."""
    raw = (raw or "").strip()
    if not raw:
        return []

    def scrape_array(s: str) -> str:
        """Strip markdown code fences and return the first JSON array slice [ ... ]."""
        s = s.strip()
        code = re.search(r"```(?:json)?\s*([\s\S]*?)```", s)
        if code:
            s = code.group(1).strip()
        start = s.find("[")
        if start == -1:
            return ""
        depth = 0
        for i in range(start, len(s)):
            if s[i] == "[":
                depth += 1
            elif s[i] == "]":
                depth -= 1
                if depth == 0:
                    return s[start : i + 1]
        return ""

    def fix_json(s: str) -> str:
        """Remove trailing commas so Python json.loads accepts the array."""
        s = re.sub(r",\s*]", "]", s)
        s = re.sub(r",\s*}", "}", s)
        return s

    def parse_array(block: str) -> List[Dict[str, str]]:
        for attempt in (block, fix_json(block)):
            try:
                data = json.loads(attempt)
            except (json.JSONDecodeError, TypeError):
                continue
            if not isinstance(data, list):
                continue
            out = []
            for item in data:
                if not isinstance(item, dict):
                    continue
                title = item.get("title") or item.get("name") or ""
                desc = item.get("description") or item.get("detail") or item.get("text") or ""
                title = str(title).strip() if title else ""
                desc = str(desc).strip() if desc else ""
                if title or desc:
                    out.append({"title": title or "Task", "description": desc})
            if out:
                return out
        return []

    # Try scraped array first (handles markdown and surrounding text)
    block = scrape_array(raw)
    if block:
        tasks = parse_array(block)
        if tasks:
            return tasks
    # Try raw as JSON array (with trailing-comma fix)
    tasks = parse_array(raw)
    if tasks:
        return tasks
    if raw.startswith("["):
        tasks = parse_array(fix_json(raw))
        if tasks:
            return tasks
    # Fallback: raw looks like plain text (no JSON structure)
    if raw and len(raw) < 500 and "{" not in raw and "[" not in raw:
        return [{"title": "Summary", "description": raw}]
    # Last resort: we got content but parse failed - show sanitized summary so UI is not empty
    if raw and ("title" in raw or "description" in raw or "[" in raw):
        sanitized = re.sub(r"```(?:json)?\s*", "", raw)
        sanitized = re.sub(r"```", "", sanitized).strip()
        if len(sanitized) > 2000:
            sanitized = sanitized[:2000] + "..."
        if sanitized:
            return [{"title": "Summary", "description": sanitized}]
    return []


# Common typos in LLM output to fix before showing in UI
_TYPO_REPLACEMENTS = (
    ("Healt ", "Health "),
    ("healt ", "health "),
    ("Healtcheck", "Health check"),
    ("healtcheck", "health check"),
)


def _normalize_tasks(tasks: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """Trim whitespace, normalize newlines, and apply typo fixes to task title/description."""
    out = []
    for t in tasks:
        title = (t.get("title") or "").strip()
        desc = (t.get("description") or "").strip()
        # Normalize newlines to single space or keep paragraph breaks
        desc = " ".join(desc.split())
        for wrong, right in _TYPO_REPLACEMENTS:
            title = title.replace(wrong, right)
            desc = desc.replace(wrong, right)
        out.append({"title": title or "Task", "description": desc})
    return out


async def summarize_activity(activity: dict, range_kind: str = "week") -> Dict[str, Any]:
    """Produce structured list of tasks (title + description) using configured LLM."""
    text = _activity_to_text(activity)
    repo_name = activity.get("repo", "unknown")
    label = _range_label(range_kind)
    provider = _get_provider()
    raw = await provider.summarize_tasks(text, repo_name, label)
    tasks = _parse_tasks_from_response(raw)
    tasks = _normalize_tasks(tasks)
    summary = tasks[0]["description"] if tasks else ""
    return {"summary": summary, "tasks": tasks}
