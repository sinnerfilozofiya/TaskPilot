# TaskPilot

**TaskPilot** is a GitHub activity summarizer: you connect your GitHub account (or organization), choose a time range, and get a structured list of tasks plus a clear view of commits and pull requests across **all branches**, with merge status. An AI (Ollama or Hugging Face) turns the raw activity into human-readable task titles and descriptions that you can confirm (Done? / Working?) in the UI.

This document describes what the project does, how the codebase works, where the data comes from, how summarization and “scraping” work, and how to run it—so project managers and other reviewers can see what’s there and what might be improved.

---

## What has been done

- **GitHub connection** – OAuth (org or personal). List repos with optional “multi-contributor only” filter.
- **Time range** – User picks last 24 hours, 7 days, or 30 days.
- **Activity across all branches** – Commits and PRs are fetched for the **default branch and up to 25 other branches** in the selected range. Each commit is labeled with **branch** and **merged** (whether its SHA appears on the default branch).
- **Structured summarization** – Activity is sent to an LLM with strict prompt rules. The model returns a **JSON array of tasks** (title + description). The backend parses this (including when wrapped in markdown or with trailing commas), normalizes it, and optionally fixes common typos.
- **UI** – Dashboard (repo list), repo view (time range, “Summarize with AI”), **task table** (Task | Summary | Done? | Working?), and **activity table** (commits with SHA, branch, merged, message, author, date; plus PRs).
- **LLM options** – One abstract provider interface with two backends: **Ollama** (local) and **Hugging Face** (router API). Same prompts for both; switch via env.

---

## Features (current scope)

| Feature | Description |
|--------|-------------|
| GitHub OAuth | Login with GitHub; session stores token; scopes: `repo`, `read:user`, `read:org`. |
| Repo list | All repos the user can access; optional filter: only repos with 2+ contributors. |
| All-branches activity | Commits from default + other branches (up to 25) in the chosen range; each commit has `branch` and `merged`. |
| Pull requests | PRs updated in the range (state: all); shown with number, title, state, user. |
| AI task list | LLM turns activity into 5–12 tasks (title + description); output must be JSON only. |
| Task table | Rows: task title, summary text, checkboxes for “Done?” and “Working?” (state in memory only). |
| Activity table | Commits in a table: SHA, Branch, Merged (Yes/No), Message, Author, Date. |

---

## Architecture (high level)

```
┌─────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   Browser   │────▶│  Backend (API)    │────▶│  GitHub REST API │
│  (Vite+React)│     │  (FastAPI)        │     │  (commits, PRs,  │
└─────────────┘     └────────┬───────────┘     │   branches, repo) │
        │                    │                 └─────────────────┘
        │                    │
        │                    ▼
        │             ┌──────────────────┐     ┌─────────────────┐
        │             │  Summarizer       │────▶│  Ollama or       │
        │             │  (activity→text, │     │  Hugging Face    │
        │             │   parse response) │     │  (LLM)           │
        │             └──────────────────┘     └─────────────────┘
        │
        └──────────── Session cookie (OAuth token)
```

- **Frontend** – SPA: Home (login), Dashboard (repos), Repo view (range picker, Summarize button, task table, activity table). Calls backend with credentials so the session cookie is sent.
- **Backend** – FastAPI: auth (OAuth + session), repos list, activity fetch, summarize (fetch activity → build text → call LLM → parse JSON → return tasks + activity).
- **Data source** – **Only the GitHub REST API.** There is no web scraping of GitHub HTML pages.

---

## How we get the data (no web scraping)

All data comes from **GitHub’s REST API** (`https://api.github.com`), using the user’s OAuth token. We do **not** scrape web pages.

### Endpoints used

| Purpose | Endpoint | What we use |
|--------|----------|-------------|
| Repos | `GET /user/repos` | List repos (optional filter by contributor count). |
| Repo metadata | `GET /repos/{owner}/{repo}` | `default_branch` (e.g. `main`). |
| Branches | `GET /repos/{owner}/{repo}/branches` | Branch names (up to 25). |
| Commits | `GET /repos/{owner}/{repo}/commits` | Query params: `sha=<branch>`, `since`, `until` (ISO), `per_page=100`. |
| Pull requests | `GET /repos/{owner}/{repo}/pulls` | `state=all`, then filter by `updated_at` in range. |
| Contributors | `GET /repos/{owner}/{repo}/contributors` | Only to count contributors for the filter. |

### How commits are collected (all branches)

1. **Default branch** – We call `GET /repos/{owner}/{repo}` to get `default_branch`.
2. **Branch list** – We call `GET /repos/{owner}/{repo}/branches?per_page=25` to get branch names.
3. **Commits on default** – We call `GET /repos/.../commits?sha=<default_branch>&since=&until=` and collect all returned commit SHAs into a set `main_shas`. These are treated as “merged” (they appear on the default branch in this range).
4. **Commits per branch** – For each branch (default first, then the rest), we call `GET /repos/.../commits?sha=<branch>&since=&until=`. For each commit we store:
   - `sha`, `message`, `author`, `date` (from commit payload),
   - `branch` = branch we requested,
   - `merged` = `True` if this commit’s SHA is in `main_shas`, else `False`.
5. **Deduplication** – We deduplicate by SHA so each commit appears once (with the first branch we saw it on). Processing the default branch first keeps labels consistent.

So: we are **not** scraping the site; we are **only** using GitHub’s official API to list branches and to list commits per branch in the given time window, then deriving “merged” from whether the commit appears in the default-branch commit list.

---

## How summarization works (and what “scraping” means here)

“Scraping” in this project does **not** mean scraping GitHub HTML. It means **extracting structured data from the LLM’s response** (which can be plain JSON, JSON inside markdown code fences, or with trailing commas).

### Inputs to the summarizer

1. **Activity payload** – From `get_activity()`: repo name, since/until, list of commits (each with message, author, date, branch, merged), list of PRs (number, title, state, user, updated_at, merged_at).
2. **Activity as text** – The summarizer converts this into a single text blob (`_activity_to_text` in `backend/app/services/summarizer.py`):
   - A line per commit: `[author] branch=X [merged|open] message (date)`.
   - Then a line per PR: `#num title [state] by user`.
   - Up to 50 commits and 30 PRs to keep the prompt size reasonable.

### Prompt and LLM call

- **Prompt** – Built in `backend/app/services/llm/prompts.py`. It includes:
  - Rules: plain language, consistent terms, short actionable titles (8–10 words), 1–2 sentence descriptions, 5–12 tasks, **output only a JSON array** (no markdown, no extra text).
  - An example: `[{"title": "...", "description": "..."}, ...]`.
  - The repo name, time range label, and the activity text.
- **LLM** – Either Ollama (`POST /api/generate` with prompt) or Hugging Face (`POST https://router.huggingface.co/v1/responses` with `instructions` + `input`). The model is asked to return **only** a JSON array of `{ "title", "description" }`.

### Extracting the task list (“scraping” the LLM response)

The LLM often returns JSON wrapped in markdown (e.g. ` ```json ... ``` `) or with trailing commas. We **parse** this in `_parse_tasks_from_response()` in `backend/app/services/summarizer.py`:

1. **Strip markdown** – Regex to find ` ```json ... ``` ` or ` ``` ... ``` ` and take the inner content.
2. **Find the array** – Locate the first `[` and the matching `]` (bracket counting) so we ignore any text before/after.
3. **Fix JSON** – Remove trailing commas (e.g. `,]` → `]`, `,}` → `}`) so `json.loads` accepts it.
4. **Parse** – `json.loads` the string; iterate items; for each object take `title` (or `name`) and `description` (or `detail`/`text`); normalize to `{"title": str, "description": str}`.
5. **Fallbacks** – If the result looks like plain text (short, no brackets), return one task “Summary” with that text. If parsing fails but the response contains “title”/“description”/“[”, return one “Summary” task with sanitized content (strip backticks, truncate) so the UI is never empty when the API returned something.

Then we run **post-processing**:

- **Normalize** – Trim whitespace, collapse newlines in descriptions.
- **Typo list** – Simple string replacements (e.g. “Healt ” → “Health ”) in titles and descriptions.

So “scraping” here = **parsing and normalizing the LLM’s text response into a list of `{ title, description }`**, not scraping GitHub.

### Hugging Face response shape

The Hugging Face router API returns a JSON body with an `output` array. Each element can have a `content` array (not a single `text` string). We **extract** the model’s text in `_extract_text()` in `backend/app/services/llm/huggingface_provider.py`:

- If `output` is a list, we iterate items and for each item’s `content` (if a list) we take `c.get("text") or c.get("content")` from each part and concatenate. That gives the raw LLM output string (the JSON array of tasks), which we then parse as above.

---

## What we look at to create the summarization

| Input | Source | Used for |
|-------|--------|----------|
| Repo name | Activity payload | Shown in prompt so the LLM knows the project. |
| Time range label | “Last 24 hours” / “Last 7 days” / “Last 30 days” | In prompt. |
| Commits (up to 50) | GitHub API, all branches | Author, branch, merged/open, message, date → one line per commit in the activity text. |
| Pull requests (up to 30) | GitHub API | Number, title, state, user → one line per PR in the activity text. |

The LLM sees only this **text summary** of the activity (no raw JSON from GitHub in the prompt). It is instructed to output a **JSON array of tasks** with short titles and 1–2 sentence descriptions. We then parse that array and show it in the UI with Done? / Working? checkboxes.

---

## Codebase layout

### Backend (`backend/`)

| Path | Role |
|------|------|
| `app/main.py` | FastAPI app, CORS, session middleware, router includes. |
| `app/config.py` | Env-based config (GitHub, session, LLM provider, Ollama/HF settings). |
| `app/api/auth.py` | GitHub OAuth: login redirect, callback (exchange code, store token in session), me, logout. |
| `app/api/repos.py` | List repos (optional multi-contributor filter). |
| `app/api/activity.py` | Get activity for a repo in a range (day/week/month); calls `GitHubClient.get_activity`. |
| `app/api/summarize.py` | Get activity, then `summarize_activity()`; return summary + `summary_tasks` + activity. |
| `app/services/github_client.py` | GitHub API: repos, default branch, branches, commits per branch, PRs; builds activity with branch + merged. |
| `app/services/summarizer.py` | `_activity_to_text`, `_parse_tasks_from_response`, `_normalize_tasks`, `summarize_activity()` (calls LLM, parses, normalizes). |
| `app/services/llm/base.py` | Abstract `LLMProvider` (summarize, summarize_tasks). |
| `app/services/llm/prompts.py` | Shared task prompt: `TASKS_INSTRUCTIONS`, `TASKS_INPUT_TEMPLATE`, `get_tasks_prompt()`. |
| `app/services/llm/ollama_provider.py` | Ollama: POST to `/api/generate` with prompt; optional temperature. |
| `app/services/llm/huggingface_provider.py` | Hugging Face router: POST to `/v1/responses`; `_extract_text()` handles `output[].content[]`. |
| `scripts/test_summarize.py` | Parser tests and optional live call to summarizer (for debugging). |

### Frontend (`frontend/src/`)

| Path | Role |
|------|------|
| `main.tsx` | React root, BrowserRouter. |
| `App.tsx` | Routes: Home, Dashboard, Repo view. |
| `api.ts` | API client (getMe, logout, getRepos, getActivity, getSummary); types (Commit with branch/merged, Activity, SummaryTask, etc.). |
| `pages/Home.tsx` | Landing; “Connect with GitHub” link to backend OAuth. |
| `pages/Dashboard.tsx` | Repo list (optional multi-contributor checkbox); navigate to repo. |
| `pages/RepoView.tsx` | Time range select, “Summarize with AI”, task table (Task | Summary | Done? | Working?), activity table (commits + PRs), branches meta. |
| `index.css` | Global and component styles (tables, task cards, activity, buttons). |

---

## Data flow (end to end)

1. User opens app → may log in via GitHub OAuth (redirect to GitHub, callback to backend, token stored in session).
2. User sees Dashboard → backend `GET /api/repos` (with optional `multi_contributor=true`) → list of repos.
3. User selects a repo → frontend loads activity: `GET /api/activity/{owner}/{repo}?range=week` → backend fetches default branch, branches, commits per branch (with since/until), PRs; dedupes commits; returns commits (with branch, merged), PRs, default_branch, branches.
4. User clicks “Summarize with AI” → `GET /api/summarize/{owner}/{repo}?range=week` → backend again gets activity (same as above), builds activity text, calls LLM (Ollama or Hugging Face) with task prompt, gets back a string (JSON array), parses it (`_parse_tasks_from_response`), normalizes, returns `summary_tasks` + `summary` + `activity`.
5. Frontend shows the task table (title, description, Done?, Working?) and the activity table (commits with branch and merged, then PRs).

---

## Setup and run

### 1. GitHub OAuth App

- Create an OAuth App at [GitHub Developer Settings](https://github.com/settings/developers).
- **Authorization callback URL:** `http://localhost:8000/api/auth/callback` (for local dev).
- **Scopes:** `repo`, `read:user`, `read:org`.
- Copy Client ID and Client Secret.

### 2. Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate   # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
```

Create a `.env` in the **project root** (TaskPilot/) with at least:

- `GITHUB_CLIENT_ID`
- `GITHUB_CLIENT_SECRET`
- `SECRET_KEY` (random string for session signing)
- `LLM_PROVIDER` = `ollama` or `huggingface`
- For Ollama: run Ollama and e.g. `ollama run llama3.2`; optional `OLLAMA_TEMPERATURE=0.4`.
- For Hugging Face: `HF_TOKEN`; optional `HF_MODEL`.

Then:

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 3. Frontend

```bash
cd frontend
npm install
cp .env.example .env
# For dev, set VITE_API_URL=http://localhost:8000
npm run dev
```

Open http://localhost:5173, connect with GitHub, pick a repo and time range, and use “Summarize with AI”.

---

## Environment reference

| Variable | Description |
|----------|-------------|
| `GITHUB_CLIENT_ID` | GitHub OAuth App client ID |
| `GITHUB_CLIENT_SECRET` | GitHub OAuth App client secret |
| `GITHUB_CALLBACK_URL` | Callback URL (default: `http://localhost:8000/api/auth/callback`) |
| `FRONTEND_URL` | Frontend origin for post-login redirect (default: `http://localhost:5173`) |
| `SECRET_KEY` | Session signing secret |
| `LLM_PROVIDER` | `ollama` or `huggingface` |
| `OLLAMA_HOST` | Ollama URL (default: `http://localhost:11434`) |
| `OLLAMA_MODEL` | Model name (default: `llama3.2`) |
| `OLLAMA_TEMPERATURE` | Optional; e.g. `0.4` for more consistent output |
| `HF_TOKEN` | Hugging Face API token |
| `HF_MODEL` | Hugging Face model (default: `mistralai/Mistral-7B-Instruct-v0.2`) |

Frontend (optional, for dev):

| Variable | Description |
|----------|-------------|
| `VITE_API_URL` | Backend URL (e.g. `http://localhost:8000`) for API and auth cookies |

---

## API summary

| Method + path | Description |
|---------------|-------------|
| `GET /api/auth/login` | Redirect to GitHub OAuth |
| `GET /api/auth/callback` | OAuth callback; stores token in session; redirects to frontend |
| `GET /api/auth/me` | Current user or `{ "logged_in": false }` |
| `POST /api/auth/logout` | Clear session |
| `GET /api/repos?multi_contributor=false` | List repos (optional filter: 2+ contributors) |
| `GET /api/activity/{owner}/{repo}?range=day\|week\|month` | Commits (all branches, with branch + merged) and PRs in range |
| `GET /api/summarize/{owner}/{repo}?range=day\|week\|month` | Same activity + AI-generated `summary_tasks` (and legacy `summary`) |

---

## What might be missing / improvement ideas

This section is for project managers and reviewers (human or AI) to extend.

- **Persistence** – Done? / Working? are only in React state; no DB or backend save. Could add a small store (e.g. SQLite) or API to save/load confirmations per repo + range.
- **Caching** – Activity and summaries are recomputed every time. Caching by (repo, range) with TTL could reduce GitHub and LLM calls.
- **Rate limits** – Many branches × commits can hit GitHub rate limits; consider limiting branches or adding backoff/retry and user-facing messaging.
- **Issues** – Only commits and PRs are in the activity; GitHub Issues are not. Could add `GET /repos/.../issues` and include them in the activity text.
- **Larger repos** – 50 commits / 30 PRs cap might drop important context; could make caps configurable or paginate.
- **Access control** – Any logged-in user can list and summarize any repo they have access to; there is no extra permission or audit model.
- **Tests** – `scripts/test_summarize.py` exercises the parser and optional live summarizer; there are no automated unit/integration tests in CI.
- **Error handling** – Some GitHub/LLM errors could be surfaced more clearly in the UI (e.g. “branch X failed to load”).
- **Export** – No export of the task list or activity (e.g. CSV, PDF, or markdown) for sharing with stakeholders.

If you are a reviewer (PM or AI), you can use this README and the codebase to suggest concrete next steps or priorities for the above (or new) items.
