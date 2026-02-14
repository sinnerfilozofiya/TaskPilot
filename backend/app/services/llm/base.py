"""Abstract LLM interface for summarization."""
from abc import ABC, abstractmethod


class LLMProvider(ABC):
    @abstractmethod
    async def summarize(self, activity_text: str, repo_name: str, range_label: str) -> str:
        """Return a short narrative summary of the activity."""
        pass

    async def summarize_tasks(self, activity_text: str, repo_name: str, range_label: str) -> str:
        """Return raw LLM output for structured tasks (JSON array of {title, description})."""
        return await self.summarize(activity_text, repo_name, range_label)
