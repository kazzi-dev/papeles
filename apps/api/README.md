# Papeles API

FastAPI backend for [Papeles](https://github.com/kazzi-dev/papeles): it searches official
Philippine agency sources and has an LLM answer from them with citations.

- `POST /ask` with `{"question": "...", "lang": "en" | "tl" | "ceb"}`
- `GET /health`
- Interactive docs at `/docs`

Deployed to Render as a Docker service (`render.yaml` at the repo root). See
[docs/DEPLOY.md](../../docs/DEPLOY.md).
