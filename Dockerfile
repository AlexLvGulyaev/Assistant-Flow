FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ARG INSTALL_RAGAS=false

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
COPY requirements-ragas.txt .

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt \
    && if [ "$INSTALL_RAGAS" = "true" ]; then pip install --no-cache-dir -r requirements-ragas.txt; fi

COPY . .

CMD ["python", "run_telegram_bot.py"]