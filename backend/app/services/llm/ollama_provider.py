"""Ollama LLM provider (local or server)."""
from typing import Optional

import httpx

from app.services.llm.base import LLMProvider
from app.services.llm.prompts import get_tasks_prompt
from app.config import config


class OllamaProvider(LLMProvider):
    def __init__(self, base_url: Optional[str] = None, model: Optional[str] = None):
        self.base_url = (base_url or config.OLLAMA_HOST).rstrip("/")
        self.model = model or config.OLLAMA_MODEL

    async def summarize(self, activity_text: str, repo_name: str, range_label: str) -> str:
        prompt = _build_prompt(activity_text, repo_name, range_label)
        return (await self._generate(prompt)).strip()

    async def summarize_tasks(self, activity_text: str, repo_name: str, range_label: str) -> str:
        prompt = get_tasks_prompt(repo_name, range_label, activity_text)
        return (await self._generate(prompt)).strip()

    async def _generate(self, prompt: str) -> str:
        payload = {"model": self.model, "prompt": prompt, "stream": False}
        if config.OLLAMA_TEMPERATURE:
            try:
                payload["options"] = {"temperature": float(config.OLLAMA_TEMPERATURE)}
            except (TypeError, ValueError):
                pass
        async with httpx.AsyncClient(timeout=120.0) as client:
            r = await client.post(f"{self.base_url}/api/generate", json=payload)
        if r.status_code != 200:
            raise RuntimeError(f"Ollama error: {r.status_code} - {r.text}")
        data = r.json()
        return data.get("response") or ""


def _build_prompt(activity_text: str, repo_name: str, range_label: str) -> str:
    return f"""Summarize the following GitHub repository activity in 2-4 short paragraphs. Focus on what was done, who contributed, and any notable changes or PRs.

Repository: {repo_name}
Time range: {range_label}

Activity:
{activity_text}

Summary:"""
