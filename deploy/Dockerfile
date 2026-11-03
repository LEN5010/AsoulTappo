# Build from the repo root (the image bundles the downloadable asset packs):
#   docker build -f deploy/Dockerfile -t asoultappo-server .
FROM python:3.12-slim
WORKDIR /srv
ENV PYTHONUNBUFFERED=1 \
    ASOULTAPPO_DB=/srv/data/asoultappo.db \
    ASOULTAPPO_PACKS=/srv/assets-packs
COPY server/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY server/app ./app
COPY assets-packs ./assets-packs
RUN useradd -m app && mkdir -p /srv/data && chown -R app /srv/data
USER app
VOLUME /srv/data
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
