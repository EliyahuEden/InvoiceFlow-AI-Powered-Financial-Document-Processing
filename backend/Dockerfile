# InvoiceFlow backend (API + worker). Build context: repository root.
FROM python:3.15-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1

# Tesseract OCR with Hebrew + English language data, and a Hebrew-capable font for
# regenerating the synthetic demo documents.
RUN apt-get update \
 && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-heb tesseract-ocr-eng fonts-dejavu-core \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /srv/backend
COPY backend/requirements.txt .
RUN pip install -r requirements.txt

COPY backend/ /srv/backend/
COPY data/ /srv/data/
COPY eval/ /srv/eval/

RUN useradd --create-home --uid 10001 app && mkdir -p /models /srv/.data && chown -R app /models /srv/.data /srv/eval
USER app

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
