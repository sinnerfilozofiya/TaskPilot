"""Hugging Face Inference API provider (router.huggingface.co Responses API)."""
from typing import Optional

import httpx

from app.services.llm.base import LLMProvider
from app.services.llm.prompts import TASKS_INSTRUCTIONS, TASKS_INPUT_TEMPLATE
from app.config import config

# New HF API: https://router.huggingface.co (api-inference.huggingface.co is deprecated)
HF_ROUTER_URL = "https://router.huggingface.co/v1/responses"


class HuggingFaceProvider(LLMProvider):
    def __init__(self, token: Optional[str] = None, model: Optional[str] = None):
        self.token = token or config.HF_TOKEN
        self.model = model or config.HF_MODEL

    async def _call(self, prompt: str, instructions: str) -> str:
        async with httpx.AsyncClient(timeout=120.0) as client:
            r = await client.post(
                HF_ROUTER_URL,
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "instructions": instructions,
                    "input": prompt,
                },
            )
        if r.status_code != 200:
            raise RuntimeError(f"Hugging Face API error: {r.status_code} - {r.text}")
        data = r.json()
        text = _extract_text(data)
        if not isinstance(text, str):
            return ""
        return text.strip()

    async def summarize(self, activity_text: str, repo_name: str, range_label: str) -> str:
        if not self.token:
            raise RuntimeError("HF_TOKEN is required for Hugging Face provider")
        prompt = _build_prompt(activity_text, repo_name, range_label)
        return await self._call(prompt, "You are a concise assistant. Summarize the given GitHub activity in 2-4 short paragraphs. Focus on what was done, who contributed, and notable changes.")

    async def summarize_tasks(self, activity_text: str, repo_name: str, range_label: str) -> str:
        if not self.token:
            raise RuntimeError("HF_TOKEN is required for Hugging Face provider")
        input_text = TASKS_INPUT_TEMPLATE.format(
            repo_name=repo_name, range_label=range_label, activity_text=activity_text
        )
        return await self._call(input_text, TASKS_INSTRUCTIONS)


def _extract_text(data) -> str:
    """Extract summary text from Responses API payload (handles str, list, nested output)."""
    # API may return a list of output items: [{"type": "output_text", "text": "..."}]
    if isinstance(data, list):
        parts = []
        for item in data:
            if isinstance(item, dict) and item.get("type") == "output_text":
                t = item.get("text")
                if isinstance(t, str):
                    parts.append(t)
                elif isinstance(t, list):
                    parts.append(" ".join(x if isinstance(x, str) else str(x) for x in t))
        if parts:
            return "\n\n".join(parts).strip()
    if not isinstance(data, dict):
        return ""
    # Top-level output_text first
    raw = data.get("output_text")
    if raw is not None:
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
        if isinstance(raw, list):
            return " ".join((x if isinstance(x, str) else str(x) for x in raw)).strip()
    # Single item: {"type": "output_text", "text": "..."}
    if data.get("type") == "output_text":
        t = data.get("text")
        if isinstance(t, str):
            return t
        if isinstance(t, list):
            return " ".join(x if isinstance(x, str) else str(x) for x in t).strip()
    # output[] array: concat all text from each item (HF router uses "content" as list of parts)
    out = data.get("output")
    if isinstance(out, list):
        parts = []
        for item in out:
            if isinstance(item, dict):
                content = item.get("content") or item.get("text")
                if isinstance(content, str):
                    parts.append(content)
                elif isinstance(content, list):
                    for c in content:
                        if isinstance(c, dict):
                            parts.append(c.get("text") or c.get("content") or "")
                        elif isinstance(c, str):
                            parts.append(c)
            elif isinstance(item, str):
                parts.append(item)
        if parts:
            return "\n\n".join(p for p in parts if p).strip()
    # OpenAI-style choices
    choices = data.get("choices")
    if isinstance(choices, list) and len(choices) > 0:
        c = choices[0]
        if isinstance(c, dict):
            msg = c.get("message") or c
            content = msg.get("content") or msg.get("text")
            if isinstance(content, str):
                return content
    return ""


def _build_prompt(activity_text: str, repo_name: str, range_label: str) -> str:
    return f"""Summarize the following GitHub repository activity in 2-4 short paragraphs. Focus on what was done, who contributed, and any notable changes or PRs.

Repository: {repo_name}
Time range: {range_label}

Activity:
{activity_text}

Summary:"""
