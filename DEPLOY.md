# Server deployment (one URL)

Set **one variable** to your server’s public URL; callback and frontend URLs are derived from it.

---

## 1. Set your URL in `.env`

Use your server’s full URL **with no trailing slash**:

```env
APP_URL=https://taskpilot.yourdomain.com
```

Or with a port if you’re not using a reverse proxy:

```env
APP_URL=https://taskpilot.yourdomain.com:8443
```

Also set (as before):

- `GITHUB_CLIENT_ID` and `GITHUB_CLIENT_SECRET`
- `SECRET_KEY` (e.g. `openssl rand -hex 32`)

The app will use:

- **Callback URL:** `{APP_URL}/api/auth/callback`
- **Frontend URL:** `{APP_URL}` (CORS and post-login redirect)

No need to set `GITHUB_CALLBACK_URL` or `FRONTEND_URL` when `APP_URL` is set.

---

## 2. Add the callback URL in GitHub

1. Open **GitHub** → **Settings** (your profile) → **Developer settings** → **OAuth Apps**.
2. Create a new OAuth App (or edit the one you use for TaskPilot).
3. Set **Homepage URL** to your app URL:
   - `https://taskpilot.yourdomain.com`
4. Set **Authorization callback URL** to exactly:
   - `https://taskpilot.yourdomain.com/api/auth/callback`
   - (Same as `APP_URL` + `/api/auth/callback` — no trailing slash.)
5. Save. Copy the **Client ID** and **Client secret** into your `.env` as `GITHUB_CLIENT_ID` and `GITHUB_CLIENT_SECRET`.

![GitHub OAuth App](https://docs.github.com/assets/cb-34573/mw-1440/images/help/settings/oauth-applications-create.webp)

**Summary:**

| In GitHub OAuth App | Value |
|---------------------|--------|
| **Homepage URL** | Your `APP_URL` (e.g. `https://taskpilot.yourdomain.com`) |
| **Authorization callback URL** | `{APP_URL}/api/auth/callback` (e.g. `https://taskpilot.yourdomain.com/api/auth/callback`) |

---

## 3. Run the app

- **Docker:** `docker compose up -d`. Ensure your reverse proxy (if any) forwards to port 8000 and uses the same host as `APP_URL`.
- **Local:** Leave `APP_URL` empty in `.env` for default localhost URLs.
