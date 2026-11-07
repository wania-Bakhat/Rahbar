FROM python:3.12.10-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    TESSDATA_PREFIX=/usr/share/tesseract-ocr/5/tessdata

RUN apt-get update && apt-get install -y --no-install-recommends \
      poppler-utils tesseract-ocr ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid 10001 rahbar \
    && useradd --system --uid 10001 --gid rahbar --home-dir /nonexistent rahbar

WORKDIR /app
COPY indexer/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY --chown=10001:10001 indexer/pipeline ./pipeline
COPY --chown=10001:10001 corpus/fetch.py corpus/sources.yaml ./corpus/
RUN mkdir -p /app/corpus/raw && chown -R 10001:10001 /app/corpus

USER 10001:10001
CMD ["python", "-m", "pipeline.run"]
