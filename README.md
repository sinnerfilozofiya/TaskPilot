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
- **LLM options** – One abstract provider interface with three backends: **Ollama** (local), **Hugging Face** (router API), and **Cursor CLI**. Same task table and activity table; switch via env. When using Cursor, the backend clones the repo and runs the Cursor CLI in that directory; **Cursor uses browser login** (no API key). The server machine must have Cursor CLI installed and logged in via the browser.

---

## Features (current scope)

| Feature | Description |
|--------|-------------|
| GitHub OAuth | Login with GitHub; session stores token; scopes: `repo`, `read:user`, `read:org`. |
| Repo list | All repos the user can access; optional filter: only repos with 2+ contributors. |
| All-branches activity | Commits from default + other branches (up to 25) in the chosen range; each commit has `branch` and `merged`. |
| Pull requests | PRs updated in the range (state: all); shown with number, title, state, user. |
| AI task list | LLM turns activity into 5–12 tasks (title + description); output must be JSON only. With Cursor, the agent analyzes the cloned repo and git history in the time range. |
| Cursor CLI | When provider is Cursor, summarization runs Cursor on the server; Cursor uses browser login (no API key in the app). |
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
        │             │  Summarizer       │────▶│  Ollama,         │
        │             │  (activity→text   │     │  Hugging Face,   │
        │             │   or Cursor CLI   │     │  or Cursor CLI  │
        │             │   in repo clone)  │     │  (in repo dir)  │
        │             └──────────────────┘     └─────────────────┘
        │
        └──────────── Session cookie (OAuth token)
```

- **Frontend** – SPA: Home (login), Dashboard (repos), Repo view (range picker, Summarize button, task table, activity table), Settings (Cursor instructions when provider is Cursor). Calls backend with credentials so the session cookie is sent.
- **Backend** – FastAPI: auth (OAuth + session), Cursor link/status (session-stored API key), repos list, activity fetch, summarize (fetch activity → when Cursor: clone repo, run Cursor CLI in repo dir; else build text → call LLM → parse JSON → return tasks + activity).
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

**When `LLM_PROVIDER=cursor`:** The summarizer does *not* send activity text to an HTTP LLM. Instead, the API ensures the repo is cloned (or updated) to a local cache using the user’s GitHub token, then runs **Cursor CLI** (`cursor agent -p "..."`) in that directory with a prompt that tells the agent to analyze git changes in the time range (e.g. `git log -p --since=... --until=...`) and the codebase and to output **only** a JSON array of tasks. Cursor uses **browser login** (no API key). On the server machine, install **Cursor CLI** and log in (e.g. run Cursor or `cursor` and sign in via the browser). The server must have Cursor CLI on PATH. Repos are stored under `REPOS_CACHE_DIR` (default `.repos_cache`); add this directory to `.gitignore`.

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
| `app/api/summarize.py` | Get activity; when Cursor: ensure repo cloned, pass `repo_path` and Cursor key; else call LLM with activity text; return summary + `summary_tasks` + activity. |
| `app/api/cursor_auth.py` | `GET /api/cursor/status` (returns whether provider is Cursor; no API key—Cursor uses browser login on the server). |
| `app/services/github_client.py` | GitHub API: repos, default branch, branches, commits per branch, PRs; builds activity with branch + merged. |
| `app/services/repo_clone.py` | `ensure_repo_cloned(full_name, token, cache_dir)`; clone or fetch via GitHub token; per-repo lock. |
| `app/services/summarizer.py` | `_activity_to_text`, `_parse_tasks_from_response`, `_normalize_tasks`, `summarize_activity()` (Cursor: repo_path + CLI; else LLM, parse, normalize). |
| `app/services/llm/base.py` | Abstract `LLMProvider` (summarize, summarize_tasks). |
| `app/services/llm/prompts.py` | Shared task prompt: `TASKS_INSTRUCTIONS`, `TASKS_INPUT_TEMPLATE`, `get_tasks_prompt()`. |
| `app/services/llm/ollama_provider.py` | Ollama: POST to `/api/generate` with prompt; optional temperature. |
| `app/services/llm/huggingface_provider.py` | Hugging Face router: POST to `/v1/responses`; `_extract_text()` handles `output[].content[]`. |
| `app/services/llm/cursor_cli_provider.py` | Cursor CLI: run `cursor agent -p "..."` in repo dir with `CURSOR_API_KEY`; `summarize_tasks_from_repo(repo_path, since, until, range_label, cursor_api_key)`. |
| `scripts/test_summarize.py` | Parser tests and optional live call to summarizer (for debugging). |

### Frontend (`frontend/src/`)

| Path | Role |
|------|------|
| `main.tsx` | React root, BrowserRouter. |
| `App.tsx` | Routes: Home, Dashboard, Repo view, Settings. |
| `api.ts` | API client (getMe, logout, getRepos, getActivity, getSummary, getCursorStatus); types (Commit, Activity, SummaryTask, CursorStatus, etc.). |
| `pages/Home.tsx` | Landing; “Connect with GitHub” link to backend OAuth. |
| `pages/Dashboard.tsx` | Repo list (optional multi-contributor checkbox); Settings link; navigate to repo. |
| `pages/RepoView.tsx` | Time range select, “Summarize with AI”, task table (Task | Summary | Done? | Working?), activity table (commits + PRs), branches meta; when provider is Cursor, info banner linking to Settings (browser login on server). |
| `pages/Settings.tsx` | When provider is Cursor, shows instructions: Cursor uses browser login on the server (no API key). |
| `index.css` | Global and component styles (tables, task cards, activity, buttons). |

---

## Data flow (end to end)

1. User opens app → may log in via GitHub OAuth (redirect to GitHub, callback to backend, token stored in session).
2. User sees Dashboard → backend `GET /api/repos` (with optional `multi_contributor=true`) → list of repos.
3. User selects a repo → frontend loads activity: `GET /api/activity/{owner}/{repo}?range=week` → backend fetches default branch, branches, commits per branch (with since/until), PRs; dedupes commits; returns commits (with branch, merged), PRs, default_branch, branches.
4. User clicks “Summarize with AI” → `GET /api/summarize/{owner}/{repo}?range=week` → backend again gets activity. If **Cursor**: ensures repo is cloned/updated, runs Cursor CLI in repo dir (uses browser login on the server; no API key), parses stdout (JSON array). If **Ollama/Hugging Face**: builds activity text, calls LLM with task prompt. In all cases: parse (`_parse_tasks_from_response`), normalize, return `summary_tasks` + `summary` + `activity`.
5. Frontend shows the task table (title, description, Done?, Working?) and the activity table (commits with branch and merged, then PRs).

---

## Using Cursor CLI in TaskPilot

When `LLM_PROVIDER=cursor`, the backend **simulates the server as the “computer”** and talks to Cursor via the **terminal**: it runs the Cursor CLI as a subprocess in the cloned repo directory. So from Cursor’s point of view, it’s as if someone had opened a terminal on that machine, `cd`’d into the repo, and run the agent there.

### How it works

1. **Clone** – On “Summarize”, the backend ensures the repo is cloned (or updated) under `REPOS_CACHE_DIR` using the user’s GitHub token.
2. **Run CLI** – It runs: `cursor agent -p "<prompt>"` with that directory as the working directory (`cwd`). The prompt tells the agent to analyze git changes in the time range and the codebase and to output only a JSON array of tasks.
3. **Capture** – Stdout is captured and parsed with the same task parser as for Ollama/Hugging Face.

So the “terminal” is our subprocess; the “computer” is the machine (or container) where the backend runs. No API key is required in the TaskPilot UI.

### Authentication: two options

Cursor CLI supports [browser login and API keys](https://cursor.com/docs/cli/reference/authentication). TaskPilot supports both so you can run **with or without Docker**.

| Scenario | What to do |
|----------|------------|
| **Same machine (no Docker)** | On the machine that runs the backend, authenticate once so the CLI has credentials. Either: (1) Run `cursor agent login` in a terminal (opens browser; credentials stored locally), or (2) Use the Cursor app and sign in. Then our code runs `cursor agent -p "..."` and the CLI uses that stored login. No key in the app. |
| **Docker / headless** | There is no browser. Use an **API key**: create one in the [Cursor dashboard](https://cursor.com/dashboard) under **Integrations → User API Keys**. Set `CURSOR_API_KEY=your_key` in the container environment (e.g. in `docker run -e CURSOR_API_KEY=...` or in your compose/env). The backend passes it through to the CLI subprocess. |

So: **without Docker**, use browser login on the server (or optionally `CURSOR_API_KEY`); **with Docker**, set `CURSOR_API_KEY` in the environment. Our code does not store or ask for the key in the UI; it only uses the key if the server already has it (e.g. from env).

### Summary

- **Terminal** = subprocess running `cursor agent -p "..."` with `cwd` = cloned repo.
- **Computer** = the host (or container) where the backend runs; Cursor CLI must be installed and on `PATH` there.
- **Auth** = browser login on that host, or `CURSOR_API_KEY` in the environment for headless/Docker.

### Testing the connection

- **From the app:** In **Settings**, when the provider is Cursor, use **Test Cursor connection** to run a minimal CLI command from the backend. It shows success or the exact error (e.g. CLI not found, timeout, or auth/keychain errors).
- **From the shell:** From the `backend/` directory with your venv active and `.env` set, run: `python scripts/test_cursor_cli.py`. This uses the same code path as the API.

### Troubleshooting (macOS keychain)

If you see **"SecItemCopyMatching failed -50"** or similar when the backend runs the CLI, the subprocess is hitting macOS Keychain. Set **`CURSOR_API_KEY`** in your `.env` (create a key at Cursor dashboard → Integrations → User API Keys) so the CLI uses the API key instead of the keychain.

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
- `LLM_PROVIDER` = `ollama`, `huggingface`, or `cursor`
- For Ollama: run Ollama and e.g. `ollama run llama3.2`; optional `OLLAMA_TEMPERATURE=0.4`.
- For Hugging Face: `HF_TOKEN`; optional `HF_MODEL`.
- For Cursor: install [Cursor CLI](https://cursor.com/docs/cli) on the server and ensure it is on PATH. Auth: log in on that machine with `cursor agent login` (browser), or for Docker set `CURSOR_API_KEY` (create key at [Cursor dashboard](https://cursor.com/dashboard) → Integrations → User API Keys). See [Using Cursor CLI in TaskPilot](#using-cursor-cli-in-taskpilot).

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
| `LLM_PROVIDER` | `ollama`, `huggingface`, or `cursor` |
| `OLLAMA_HOST` | Ollama URL (default: `http://localhost:11434`) |
| `OLLAMA_MODEL` | Model name (default: `llama3.2`) |
| `OLLAMA_TEMPERATURE` | Optional; e.g. `0.4` for more consistent output |
| `HF_TOKEN` | Hugging Face API token |
| `HF_MODEL` | Hugging Face model (default: `mistralai/Mistral-7B-Instruct-v0.2`) |
| `REPOS_CACHE_DIR` | Directory for cloned repos when using Cursor (default: `.repos_cache`) |
| `CURSOR_API_KEY` | For headless/Docker: create at Cursor dashboard → Integrations → User API Keys; set in server/container env. If unset, Cursor CLI uses browser login on the server. |
| `CURSOR_CLI_TIMEOUT` | Timeout in seconds for Cursor CLI (default: 300) |

Frontend (optional, for dev):

| Variable | Description |
|----------|-------------|
| `VITE_API_URL` | Backend URL (e.g. `http://localhost:8000`) for API and auth cookies |

---

## Docker and server deployment

TaskPilot can run as a single container: the image builds the frontend and serves it from the backend. No separate frontend server or CORS setup is needed in production.

### Build and run (docker Compose)

1. Copy env and set required variables:

   ```bash
   cp .env.example .env
   # Edit .env: GITHUB_CLIENT_ID, GITHUB_CLIENT_SECRET, SECRET_KEY
   # For production: GITHUB_CALLBACK_URL and FRONTEND_URL (see below)
   ```

2. Build and start:

   ```bash
   docker compose up -d
   ```

3. Open **http://localhost:8000** (frontend and API on one port).

Data (repo cache, summary cache, SQLite DB) is stored in a named volume `taskpilot_data` and persisted across restarts.

### Production (public server)

- **One URL** – Set **`APP_URL`** to your public URL (e.g. `https://taskpilot.yourdomain.com`). Callback and frontend URLs are derived automatically. See **[DEPLOY.md](DEPLOY.md)** for how to add this URL to GitHub OAuth and full deployment steps.
- **Env in production** – In `.env` or the host: `APP_URL`, `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET`, and `SECRET_KEY` (e.g. `openssl rand -hex 32`).
- **HTTPS** – Put the container behind a reverse proxy (nginx, Caddy, Traefik) that terminates TLS and forwards to `localhost:8000`.
- **Cursor in Docker** – The image does **not** include the Cursor CLI. To use Cursor in Docker you must either:
  - Set **`CURSOR_API_KEY`** (create at Cursor dashboard → Integrations → User API Keys) so the backend can call Cursor’s API without a local CLI, or
  - Build a custom image that installs the Cursor CLI and ensure it can authenticate (e.g. via `CURSOR_API_KEY`).
- **Ollama / Hugging Face** – Set `LLM_PROVIDER=ollama` or `huggingface` and the corresponding env vars; for Ollama you’d typically run Ollama in another container and set `OLLAMA_HOST` to that service.

### Docker reference

| Item | Description |
|------|-------------|
| `Dockerfile` | Multi-stage: builds frontend (Node), then backend (Python) + copies static into `/app/static`. |
| `docker-compose.yml` | Single service `app`, port 8000, volume `taskpilot_data` at `/data` for caches and DB. |
| `.dockerignore` | Excludes `.git`, `.env`, venv, `node_modules`, local caches. |

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
| `GET /api/summarize/{owner}/{repo}?range=day\|week\|month` | Same activity + AI-generated `summary_tasks` (and legacy `summary`); when Cursor: requires Cursor key in session, clones repo, runs Cursor CLI |
| `GET /api/cursor/status` | `{ "provider_is_cursor": boolean }` — whether summarization uses Cursor CLI (no API key; Cursor uses browser login on the server) |

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
