const API = (import.meta.env.VITE_API_URL || "").replace(/\/$/, "") + "/api";

const opts: RequestInit = {
  credentials: "include",
  headers: { "Content-Type": "application/json" },
};

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
  await checkOk(r);
  return r.json();
}
