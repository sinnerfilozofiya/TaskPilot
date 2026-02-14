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

# Install deps (no venv in container)
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Backend code
COPY backend/ ./

# Frontend static (from stage 1)
COPY --from=frontend /app/frontend/dist ./static

# Create data dir for volumes (cache, DB)
RUN mkdir -p /data

ENV PYTHONUNBUFFERED=1
EXPOSE 8000

# Run from /app so `app` package and static are found
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
