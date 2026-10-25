FROM python:3.12-slim

# Hugging Face Spaces runs containers as user 1000; using it everywhere keeps one image.
RUN useradd -m -u 1000 user
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    EMBEDDING_CACHE_DIR=/app/models \
    HF_HUB_DISABLE_SYMLINKS_WARNING=1

COPY pyproject.toml ./
COPY app ./app
RUN pip install --no-cache-dir .

COPY data ./data
RUN mkdir -p /app/models && chown -R user:user /app
USER user

# With BAKE_DATA=true (the default), the official sources are downloaded, embedded and stored in
# a SQLite file inside the image, and the embedding model is downloaded too, so the server starts
# with everything ready and needs no database service. docker-compose sets it to false and uses
# Postgres instead.
ARG BAKE_DATA=true
ENV DATABASE_URL=sqlite:////app/data/papeles.db
RUN if [ "$BAKE_DATA" = "true" ]; then python -m app.ingest; fi

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
