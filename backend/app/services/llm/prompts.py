"""Shared prompt text for task summarization so Ollama and HuggingFace use the same rules."""

TASKS_INSTRUCTIONS = """Turn the following GitHub activity into a short list of distinct tasks or changes.

Rules:
- Use plain, human-readable language. No jargon unless the commits/PRs use it; then keep one consistent term (e.g. always "CMJ", not "C MJ" or "cmj").
- Titles: short, actionable headlines (e.g. "Add health check to Docker" or "Contact form with email"). Prefer verb-first. Max 8-10 words. Use correct spelling.
- Descriptions: 1-2 clear sentences a teammate can understand. Be specific; avoid "unknown specifics", "unresolved changes", or vague wording.
- Prefer 5-12 distinct tasks. Group small related changes into one task instead of listing every commit separately.
- Output format: You must respond with ONLY a valid JSON array. No markdown, no code fences (no backticks), no explanation before or after. Your entire response must start with [ and end with ]. Each array element must be an object with exactly two string keys: "title" and "description".

Example (output exactly in this style, no other text):
[
  {"title": "Add health check to Docker", "description": "Docker health check sleep duration was corrected and the build process was improved for reliability."},
  {"title": "Contact form with email notifications", "description": "New contact form was added to the website; submissions trigger email notifications."}
]"""

TASKS_INPUT_TEMPLATE = """Repository: {repo_name}
Time range: {range_label}

Activity:
{activity_text}

Output the JSON array:"""


def get_tasks_prompt(repo_name: str, range_label: str, activity_text: str) -> str:
    """Full prompt for Ollama (instructions + input in one block)."""
    input_part = TASKS_INPUT_TEMPLATE.format(
        repo_name=repo_name, range_label=range_label, activity_text=activity_text
    )
    return TASKS_INSTRUCTIONS + "\n\n" + input_part
