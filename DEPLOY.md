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

## 3. Reverse proxy (Nginx)

Use **`nginx.conf.example`** in the repo as a template:

1. Copy it to your server, e.g. `/etc/nginx/sites-available/taskpilot`.
2. Replace `YOUR_DOMAIN` with your host (e.g. `taskpilot.yourdomain.com`).
3. Get TLS certs (e.g. `certbot --nginx -d taskpilot.yourdomain.com`) and set the `ssl_certificate` / `ssl_certificate_key` paths in the `server { listen 443 ... }` block.
4. Enable the site and reload Nginx:
   ```bash
   sudo ln -s /etc/nginx/sites-available/taskpilot /etc/nginx/sites-enabled/
   sudo nginx -t && sudo systemctl reload nginx
   ```
5. Ensure the app is listening on `127.0.0.1:8000` (e.g. `docker compose up -d` with port `8000:8000`).

---

## 4. Run the app

- **Docker:** `docker compose up -d`. The proxy forwards to port 8000; use the same host in `APP_URL`.
- **Local:** Leave `APP_URL` empty in `.env` for default localhost URLs.

---

## 5. Docker image requirements

The image **includes git and CA certificates** so that "Summarize with AI" can clone repos and run `git log`. Rebuild if you had an older image:

```bash
docker compose build --no-cache
docker compose up -d
```

If you still see `[Errno 2] No such file or directory` when summarizing, ensure you rebuilt after this change (the previous image had no git).

---

## 6. Using Cursor in Docker

The default image does **not** include the Cursor CLI. To use “Summarize with AI” with Cursor in Docker:

1. **Set in `.env`:**
   ```env
   LLM_PROVIDER=cursor
   CURSOR_API_KEY=your_key_from_cursor_dashboard
   ```
   Create the key at **Cursor → Settings → Integrations → User API Keys**.

2. **Build the image with Cursor CLI installed:**
   ```bash
   INSTALL_CURSOR_CLI=1 docker compose build --no-cache
   docker compose up -d
   ```
   Or add to your `.env`: `INSTALL_CURSOR_CLI=1`, then run `docker compose build` and `docker compose up -d`.

3. **Optional:** Use Ollama or Hugging Face in Docker instead (no CLI): set `LLM_PROVIDER=ollama` or `LLM_PROVIDER=huggingface` and the matching env vars; no image rebuild needed.

---

## 7. Login / session behind nginx

The container runs uvicorn with `--proxy-headers` and `--forwarded-allow-ips '*'` so that when traffic comes through nginx (or another reverse proxy), the app trusts `X-Forwarded-Proto` and `X-Forwarded-For`. That keeps redirects and session cookies correct over HTTPS. Ensure your nginx (or proxy) passes:

- `Host`
- `X-Real-IP`
- `X-Forwarded-For`
- `X-Forwarded-Proto`

(as in `nginx.conf.example`).
