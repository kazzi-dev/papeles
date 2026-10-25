FROM python:3.12-slim

RUN useradd -m -u 1000 user
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

COPY pyproject.toml ./
COPY app ./app
RUN pip install --no-cache-dir .

COPY data ./data
RUN chown -R user:user /app
USER user

# With BAKE_DATA=true (the default), the search index committed in data/index/ is loaded into a
# SQLite file inside the image: no database service, no network calls, a few seconds. Embeddings
# are made with Gemini, so the server only calls it once per question and stays small enough for
# free hosts (512 MB). docker-compose sets BAKE_DATA=false and uses Postgres instead.
ARG BAKE_DATA=true
ENV DATABASE_URL=sqlite:////app/data/papeles.db
RUN if [ "$BAKE_DATA" = "true" ]; then python -m app.snapshot import; fi

EXPOSE 8000
# Hosts such as Render tell the app which port to use through $PORT.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
