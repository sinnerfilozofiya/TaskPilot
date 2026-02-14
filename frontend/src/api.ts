const API = (import.meta.env.VITE_API_URL || "").replace(/\/$/, "") + "/api";

export type User = {
  logged_in: boolean;
  login?: string;
  avatar_url?: string;
  name?: string;
};

export async function getMe(): Promise<User> {
  const r = await fetch(`${API}/auth/me`, { credentials: "include" });
  return r.json();
}

export async function logout(): Promise<void> {
  await fetch(`${API}/auth/logout`, { method: "POST", credentials: "include" });
}

export type Repo = {
  full_name: string;
  name: string;
  private: boolean;
  description: string | null;
  updated_at: string;
};

async function checkOk(r: Response): Promise<void> {
  if (!r.ok) {
    const e = new Error(await r.text()) as Error & { status?: number };
    e.status = r.status;
    throw e;
  }
}

export async function getRepos(multiContributor = false): Promise<{ repos: Repo[] }> {
  const r = await fetch(
    `${API}/repos?multi_contributor=${multiContributor}`,
    { credentials: "include" }
  );
  await checkOk(r);
  return r.json();
}

export type Commit = {
  sha: string;
  message: string;
  author: string;
  date: string;
  branch?: string;
  merged?: boolean;
};

export type PullRequest = {
  number: number;
  title: string;
  state: string;
  user: string;
  updated_at: string;
  merged_at: string | null;
};

export type Activity = {
  repo: string;
  since: string;
  until: string;
  default_branch?: string;
  branches?: string[];
  commits: Commit[];
  pull_requests: PullRequest[];
};

export type RangeKind = "day" | "week" | "month";

export async function getActivity(
  owner: string,
  repo: string,
  range: RangeKind
): Promise<Activity> {
  const r = await fetch(
    `${API}/activity/${owner}/${repo}?range=${range}`,
    { credentials: "include" }
  );
  await checkOk(r);
  return r.json();
}

export type SummaryTask = {
  title: string;
  description: string;
};

export type SummaryResponse = {
  repo: string;
  range: RangeKind;
  since: string;
  until: string;
  summary: string;
  summary_tasks?: SummaryTask[];
  activity: Activity;
};

export async function getSummary(
  owner: string,
  repo: string,
  range: RangeKind
): Promise<SummaryResponse> {
  const r = await fetch(
    `${API}/summarize/${owner}/${repo}?range=${range}`,
    { credentials: "include" }
  );
  if (!r.ok) {
    const e = new Error(await r.text()) as Error & { status?: number };
    e.status = r.status;
    try {
      const body = JSON.parse(e.message);
      if (typeof body.detail === "string") e.message = body.detail;
    } catch {
      // keep raw message
    }
    throw e;
  }
  return r.json();
}

export async function postSummarizeStart(
  owner: string,
  repo: string,
  range: RangeKind
): Promise<{ job_id: string }> {
  const r = await fetch(`${API}/summarize/start`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ owner, repo, range }),
  });
  await checkOk(r);
  return r.json();
}

export type SummarizeStatusResponse = {
  status: string;
  message?: string;
  result?: SummaryResponse;
  error?: string;
  /** Live Cursor CLI output while status is "cursor" */
  cursor_log?: string;
};

export async function getSummarizeStatus(jobId: string): Promise<SummarizeStatusResponse> {
  const r = await fetch(`${API}/summarize/status/${jobId}`, { credentials: "include" });
  await checkOk(r);
  return r.json();
}

/** Load persisted summary for this repo + range (survives reload). Returns null if none saved. */
export async function getSavedSummary(
  owner: string,
  repo: string,
  range: RangeKind
): Promise<SummaryResponse | null> {
  const r = await fetch(
    `${API}/summarize/saved?owner=${encodeURIComponent(owner)}&repo=${encodeURIComponent(repo)}&range=${range}`,
    { credentials: "include" }
  );
  if (r.status === 404) return null;
  await checkOk(r);
  return r.json();
}

export type CursorStatus = {
  provider_is_cursor: boolean;
};

export async function getCursorStatus(): Promise<CursorStatus> {
  const r = await fetch(`${API}/cursor/status`, { credentials: "include" });
  await checkOk(r);
  return r.json();
}

export type CursorVerifyResult = {
  ok: boolean;
  message?: string;
  output_length?: number;
  error?: string;
};

export async function getCursorVerify(): Promise<CursorVerifyResult> {
  const r = await fetch(`${API}/cursor/verify`, { credentials: "include" });
  await checkOk(r);
  return r.json();
}
