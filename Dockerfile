FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    FLOW_WORKSPACE_ROOT=/app \
    SOFTOS_GATEWAY_HOST=0.0.0.0 \
    SOFTOS_GATEWAY_PORT=8010 \
    SOFTOS_GATEWAY_FLOW_BIN=python3 \
    SOFTOS_GATEWAY_FLOW_ENTRYPOINT=./flow

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends bash curl gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY . /app

RUN chmod +x /app/flow /app/scripts/gateway_central_start.sh /app/scripts/gateway_central_smoke.sh \
    && python -m pip install --upgrade pip \
    && pip install fastapi uvicorn httpx python-multipart pyyaml psycopg2-binary

EXPOSE 8010

CMD ["bash", "scripts/gateway_central_start.sh"]
