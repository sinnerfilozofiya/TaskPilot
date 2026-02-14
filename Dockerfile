# Multi-stage: build frontend, then run backend + serve static
# ---------------------------
# Stage 1: Frontend (Vite + React)
# ---------------------------
FROM node:20-alpine AS frontend
WORKDIR /app/frontend

COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci

COPY frontend/ ./
# Same-origin API in production (backend serves frontend)
ENV VITE_API_URL=
RUN npm run build

# ---------------------------
# Stage 2: Backend (Python + static)
# ---------------------------
FROM python:3.11-slim AS backend

WORKDIR /app

# Git + CA certs required for clone and git log (Summarize with AI)
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps (no venv in container)
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Install Cursor CLI (for "Summarize with AI" with LLM_PROVIDER=cursor). Official: https://cursor.com/docs/cli/installation
RUN apt-get update && apt-get install -y --no-install-recommends curl && \
  mkdir -p /root/.local/bin /root/.cursor/bin && \
  export PATH="/root/.local/bin:/root/.cursor/bin:$PATH" && \
  (curl -fsSL "https://cursor.com/install" | bash) && \
  apt-get remove -y curl 2>/dev/null; apt-get autoremove -y; rm -rf /var/lib/apt/lists/*
ENV PATH="/root/.local/bin:/root/.cursor/bin:${PATH}"

# Backend code
COPY backend/ ./

# Frontend static (from stage 1)
COPY --from=frontend /app/frontend/dist ./static

# Create data dir for volumes (cache, DB)
RUN mkdir -p /data

ENV PYTHONUNBUFFERED=1
EXPOSE 8000

# Run from /app so `app` package and static are found
# --proxy-headers / --forwarded-allow-ips: trust X-Forwarded-* when behind nginx (HTTPS, login redirects)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
