---
title: Papeles API
emoji: 📄
colorFrom: blue
colorTo: yellow
sdk: docker
app_port: 8000
pinned: false
short_description: Answers Philippine government paperwork questions
---

# Papeles API

FastAPI backend for [Papeles](https://github.com/kazzi-dev/papeles): it searches official
Philippine agency sources and has an LLM answer from them with citations.

- `POST /ask` with `{"question": "...", "lang": "en" | "tl" | "ceb"}`
- `GET /health`
- Interactive docs at `/docs`

This folder is deployed to Hugging Face Spaces as a Docker Space; the block at the top of this
file is the Space's configuration. See [docs/DEPLOY.md](https://github.com/kazzi-dev/papeles/blob/main/docs/DEPLOY.md).
