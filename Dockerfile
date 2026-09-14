FROM python:3.12-slim

LABEL org.opencontainers.image.title="Pronote Homework Exporter" \
      org.opencontainers.image.description="Self-hosted Pronote homework JSON API and weekly planner with persistent local completion tracking for E-ink and IoT devices." \
      org.opencontainers.image.url="https://github.com/vidax/pronote-homework-exporter" \
      org.opencontainers.image.source="https://github.com/vidax/pronote-homework-exporter" \
      org.opencontainers.image.documentation="https://github.com/vidax/pronote-homework-exporter/blob/main/INSTALL.md" \
      org.opencontainers.image.licenses="MIT"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY pyproject.toml README.md INSTALL.md LICENSE .env.example ./
COPY pronote_exporter ./pronote_exporter
RUN pip install --no-cache-dir .

VOLUME ["/data"]
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD ["python", "-c", "import os, urllib.request; port=os.environ.get('HTTP_PORT', '8080'); urllib.request.urlopen(f'http://127.0.0.1:{port}/healthz', timeout=3).read()"]

ENTRYPOINT ["pronote-homework"]
CMD ["serve"]
