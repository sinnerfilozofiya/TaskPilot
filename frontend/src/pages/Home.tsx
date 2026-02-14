import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { getMe } from "../api";

export default function Home() {
  const [loading, setLoading] = useState(true);
  const [user, setUser] = useState<Awaited<ReturnType<typeof getMe>> | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    getMe()
      .then((u) => {
        setUser(u);
        if (u.logged_in) navigate("/dashboard", { replace: true });
      })
      .finally(() => setLoading(false));
  }, [navigate]);

  if (loading) return <div className="page">Loading…</div>;

  return (
    <div className="page home">
      <h1>TaskPilot</h1>
      <p>Summarize GitHub repo activity by connecting your account and choosing a time range.</p>
      <a href={`${(import.meta.env.VITE_API_URL || "").replace(/\/$/, "")}/api/auth/login`} className="btn btn-primary">
        Connect with GitHub
      </a>
    </div>
  );
}
