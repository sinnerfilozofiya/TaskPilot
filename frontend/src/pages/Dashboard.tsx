import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { getMe, getRepos, logout, type Repo, type User } from "../api";

export default function Dashboard() {
  const [user, setUser] = useState<User | null>(null);
  const [repos, setRepos] = useState<Repo[]>([]);
  const [loading, setLoading] = useState(true);
  const [multiContributor, setMultiContributor] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    getMe().then((u) => {
      if (!u.logged_in) {
        navigate("/", { replace: true });
        return;
      }
      setUser(u);
      getRepos(false)
        .then((d) => setRepos(d.repos))
        .catch((e: Error & { status?: number }) => {
          if (e.status === 401) navigate("/", { replace: true });
          else setRepos([]);
        })
        .finally(() => setLoading(false));
    });
  }, [navigate]);

  useEffect(() => {
    if (!user?.logged_in) return;
    setLoading(true);
    getRepos(multiContributor)
      .then((d) => setRepos(d.repos))
      .catch((e: Error & { status?: number }) => {
        if (e.status === 401) navigate("/", { replace: true });
        else setRepos([]);
      })
      .finally(() => setLoading(false));
  }, [multiContributor, user?.logged_in]);

  const handleLogout = () => {
    logout().then(() => {
      setUser(null);
      navigate("/", { replace: true });
    });
  };

  if (!user?.logged_in) return null;

  const goToRepo = (fullName: string) => {
    const [owner, repo] = fullName.split("/");
    navigate(`/repo/${owner}/${repo}`);
  };

  return (
    <div className="page dashboard">
      <header className="header">
        <div>
          <h1>TaskPilot</h1>
          {user.avatar_url && (
            <img src={user.avatar_url} alt="" className="avatar" width={32} height={32} />
          )}
          <span>{user.login ?? user.name}</span>
        </div>
        <button type="button" className="btn" onClick={() => navigate("/settings")}>
          Settings
        </button>
        <button type="button" className="btn" onClick={handleLogout}>
          Log out
        </button>
      </header>

      <section>
        <label>
          <input
            type="checkbox"
            checked={multiContributor}
            onChange={(e) => setMultiContributor(e.target.checked)}
          />
          Only repos with multiple contributors
        </label>
      </section>

      <section>
        <h2>Repositories</h2>
        {loading ? (
          <p>Loading repos…</p>
        ) : (
          <ul className="repo-list">
            {repos.map((r) => (
              <li key={r.full_name}>
                <button
                  type="button"
                  className="repo-item"
                  onClick={() => goToRepo(r.full_name)}
                >
                  <strong>{r.full_name}</strong>
                  {r.description && <span className="desc">{r.description}</span>}
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
