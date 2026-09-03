# =============================================================================
# Multi-stage build (production):
#   builder — build-essential + full pip install into /opt/venv
#   runtime — slim base + ffmpeg (audio) + curl (healthchecks), только venv
# Сборочные зависимости НЕ попадают в финальный образ.
#
# Опциональные extras (build-args):
#   INSTALL_RAGAS      — offline RAGAS evaluation (admin-api в portfolio compose)
#   INSTALL_DASHBOARD  — legacy Streamlit UI (assistant-admin в docker-compose.assistant.yml)
# =============================================================================

# ------------------------------- builder -------------------------------------
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt requirements-ragas.txt requirements-dashboard.txt ./

ARG INSTALL_RAGAS=false
ARG INSTALL_DASHBOARD=false

RUN pip install --upgrade pip \
    && pip install -r requirements.txt \
    && if [ "$INSTALL_RAGAS" = "true" ]; then pip install -r requirements-ragas.txt; fi \
    && if [ "$INSTALL_DASHBOARD" = "true" ]; then pip install -r requirements-dashboard.txt; fi

# ------------------------------- runtime -------------------------------------
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app

COPY . .

CMD ["python", "run_telegram_bot.py"]