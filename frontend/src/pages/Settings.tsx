import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { getMe, getCursorStatus, getCursorVerify, type CursorStatus } from "../api";

export default function Settings() {
  const [cursorStatus, setCursorStatus] = useState<CursorStatus | null>(null);
  const [verifyResult, setVerifyResult] = useState<{ ok: boolean; message?: string; error?: string } | null>(null);
  const [verifying, setVerifying] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    getMe().then((u) => {
      if (!u.logged_in) {
        navigate("/", { replace: true });
        return;
      }
      getCursorStatus().then(setCursorStatus).catch(() => setCursorStatus(null));
    });
  }, [navigate]);

  return (
    <div className="page settings">
      <header className="header">
        <button type="button" className="btn" onClick={() => navigate("/dashboard")}>
          Back to dashboard
        </button>
        <h1>Settings</h1>
      </header>

      {cursorStatus?.provider_is_cursor && (
        <section className="settings-section">
          <h2>Summarize with Cursor</h2>
          <p className="settings-desc">
            When the server is set to use Cursor CLI, &ldquo;Summarize with AI&rdquo; runs Cursor on the <strong>server machine</strong>.
            Cursor does not use an API key—it uses <strong>browser login</strong>. On the computer where the backend runs, ensure:
          </p>
          <ul className="settings-list">
            <li>Cursor CLI is installed and on PATH</li>
            <li>You are logged in (e.g. open the Cursor app or run <code>cursor</code> in a terminal and sign in via the browser)</li>
          </ul>
          <p className="settings-desc">
            Once the server is logged in to Cursor, summarization will use that session. No key is entered in TaskPilot.
          </p>
          <p className="settings-desc">
            <strong>Docker / headless:</strong> If the backend runs in a container (no browser), set <code>CURSOR_API_KEY</code> in the server environment. Create a key at Cursor dashboard → Integrations → User API Keys.
          </p>
          <div className="cursor-verify">
            <button
              type="button"
              className="btn btn-primary"
              onClick={() => {
                setVerifying(true);
                setVerifyResult(null);
                getCursorVerify()
                  .then((r) => setVerifyResult({ ok: r.ok, message: r.message, error: r.error }))
                  .catch((e: Error) => setVerifyResult({ ok: false, error: e.message }))
                  .finally(() => setVerifying(false));
              }}
              disabled={verifying}
            >
              {verifying ? "Testing…" : "Test Cursor connection"}
            </button>
            {verifyResult && (
              <>
                <div className={verifyResult.ok ? "message-ok" : "message-err"} style={{ marginTop: "0.75rem" }}>
                  {verifyResult.ok ? verifyResult.message : verifyResult.error}
                </div>
                {!verifyResult.ok && verifyResult.error?.includes("SecItemCopyMatching") && (
                  <p className="settings-desc" style={{ marginTop: "0.5rem", fontSize: "0.85rem" }}>
                    On macOS, the CLI may hit a keychain error when run from the server. Set <code>CURSOR_API_KEY</code> in your backend <code>.env</code> (key from Cursor dashboard → Integrations → User API Keys) so the CLI uses the key instead.
                  </p>
                )}
              </>
            )}
          </div>
        </section>
      )}
    </div>
  );
}
