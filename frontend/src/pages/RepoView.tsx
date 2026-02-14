import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { getMe, getActivity, getSummary, type Activity, type RangeKind, type SummaryResponse, type SummaryTask } from "../api";

export type TaskStatus = {
  done: boolean;
  working: boolean;
};

export default function RepoView() {
  const { owner, repo } = useParams<{ owner: string; repo: string }>();
  const [range, setRange] = useState<RangeKind>("week");
  const [activity, setActivity] = useState<Activity | null>(null);
  const [summaryData, setSummaryData] = useState<SummaryResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [summarizing, setSummarizing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [taskStatus, setTaskStatus] = useState<Record<number, TaskStatus>>({});
  const navigate = useNavigate();

  const setDone = (index: number, value: boolean) => {
    setTaskStatus((s) => ({ ...s, [index]: { ...(s[index] ?? { done: false, working: false }), done: value } }));
  };
  const setWorking = (index: number, value: boolean) => {
    setTaskStatus((s) => ({ ...s, [index]: { ...(s[index] ?? { done: false, working: false }), working: value } }));
  };

  const fullName = owner && repo ? `${owner}/${repo}` : null;
  const tasks: SummaryTask[] = summaryData?.summary_tasks?.length
    ? summaryData.summary_tasks
    : summaryData?.summary
    ? [{ title: "Summary", description: summaryData.summary }]
    : [];

  useEffect(() => {
    getMe().then((u) => {
      if (!u.logged_in) navigate("/", { replace: true });
    });
  }, [navigate]);

  useEffect(() => {
    if (!owner || !repo) return;
    setLoading(true);
    setError(null);
    getActivity(owner, repo, range)
      .then(setActivity)
      .catch((e: Error & { status?: number }) => {
        if (e.status === 401) navigate("/", { replace: true });
        else setError(e.message);
      })
      .finally(() => setLoading(false));
  }, [owner, repo, range]);

  const handleSummarize = () => {
    if (!owner || !repo) return;
    setSummarizing(true);
    setError(null);
    setTaskStatus({});
    getSummary(owner, repo, range)
      .then((d) => {
        setSummaryData(d);
        setActivity(d.activity);
      })
      .catch((e: Error & { status?: number }) => {
        if (e.status === 401) navigate("/", { replace: true });
        else setError(e.message);
      })
      .finally(() => setSummarizing(false));
  };

  if (!fullName) return null;

  return (
    <div className="page repo-view">
      <header className="header">
        <button type="button" className="btn" onClick={() => navigate("/dashboard")}>
          Back to repos
        </button>
        <h1>{fullName}</h1>
      </header>

      <section className="range-section">
        <label>
          Time range:
          <select
            value={range}
            onChange={(e) => setRange(e.target.value as RangeKind)}
            disabled={loading}
          >
            <option value="day">Last 24 hours</option>
            <option value="week">Last 7 days</option>
            <option value="month">Last 30 days</option>
          </select>
        </label>
        <button
          type="button"
          className="btn btn-primary"
          onClick={handleSummarize}
          disabled={summarizing || loading}
        >
          {summarizing ? "Summarizing…" : "Summarize with AI"}
        </button>
      </section>

      {error && <div className="error">{error}</div>}

      {summaryData && tasks.length === 0 && (
        <section className="tasks-section">
          <h2>What’s been going on</h2>
          <p className="tasks-intro tasks-empty">No tasks could be parsed from the summary. Try summarizing again or check the activity list below.</p>
        </section>
      )}
      {tasks.length > 0 && (
        <section className="tasks-section">
          <h2>What’s been going on</h2>
          <p className="tasks-intro">Tasks and changes. Use the checkboxes to mark done and working.</p>
          <div className="tasks-table-wrap">
            <table className="tasks-table">
              <thead>
                <tr>
                  <th>Task</th>
                  <th>Summary</th>
                  <th className="tasks-th-check">Done?</th>
                  <th className="tasks-th-check">Working?</th>
                </tr>
              </thead>
              <tbody>
                {tasks.map((task, i) => (
                  <tr key={i}>
                    <td className="tasks-cell-title">{task.title}</td>
                    <td className="tasks-cell-summary">{task.description}</td>
                    <td className="tasks-cell-check">
                      <label className="tasks-check-label">
                        <input
                          type="checkbox"
                          checked={taskStatus[i]?.done ?? false}
                          onChange={(e) => setDone(i, e.target.checked)}
                        />
                        <span />
                      </label>
                    </td>
                    <td className="tasks-cell-check">
                      <label className="tasks-check-label">
                        <input
                          type="checkbox"
                          checked={taskStatus[i]?.working ?? false}
                          onChange={(e) => setWorking(i, e.target.checked)}
                        />
                        <span />
                      </label>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      <section className="activity-section">
        <h2>Activity</h2>
        {loading ? (
          <p>Loading activity…</p>
        ) : activity ? (
          <>
            {activity.branches && activity.branches.length > 0 && (
              <p className="activity-meta">
                Branches in range: {activity.branches.join(", ")}
                {activity.default_branch && (
                  <span> (default: <strong>{activity.default_branch}</strong>)</span>
                )}
              </p>
            )}
            <h3>Commits ({activity.commits.length})</h3>
            <div className="activity-table-wrap">
              <table className="activity-commits-table">
                <thead>
                  <tr>
                    <th>SHA</th>
                    <th>Branch</th>
                    <th>Merged</th>
                    <th>Message</th>
                    <th>Author</th>
                    <th>Date</th>
                  </tr>
                </thead>
                <tbody>
                  {activity.commits.slice(0, 80).map((c) => (
                    <tr key={`${c.sha}-${c.branch ?? ""}`}>
                      <td><code>{c.sha}</code></td>
                      <td>{c.branch ?? "—"}</td>
                      <td>{c.merged == null ? "—" : c.merged ? "Yes" : "No"}</td>
                      <td className="activity-msg">{c.message}</td>
                      <td>{c.author}</td>
                      <td>{c.date ? new Date(c.date).toLocaleDateString() : "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {activity.commits.length > 80 && (
              <p className="activity-more">… and {activity.commits.length - 80} more commits</p>
            )}
            <h3>Pull requests ({activity.pull_requests.length})</h3>
            <ul className="activity-list prs">
              {activity.pull_requests.map((pr) => (
                <li key={pr.number}>
                  <span className={`pr-state pr-${pr.state}`}>#{pr.number}</span> {pr.title} by{" "}
                  {pr.user} [{pr.state}]
                </li>
              ))}
            </ul>
          </>
        ) : (
          <p>Select a range and load activity, or run “Summarize with AI”.</p>
        )}
      </section>
    </div>
  );
}
