# Deploying Papeles for free

| Part | Host | Cost |
| --- | --- | --- |
| API (`apps/api`) | Render, Docker web service (free plan, 512 MB) | Free |
| Website (`apps/web`) | Vercel (Hobby) | Free |
| AI answers | Groq free tier | Free |
| Search embeddings | Gemini API free tier | Free |
| Data | `apps/api/data/index/`, loaded into SQLite when the image builds | Free |

Why it fits a free host: search embeddings come from Google's Gemini API instead of a model
running on the server, and the search index is built once on a developer machine and committed,
so the API needs well under 512 MB and calls Gemini only once per question.

**Gemini free-tier limits:** 100 embeddings per minute and **1,000 per day** per Google Cloud
project. Building the index uses about 550 of them (the ingest paces itself and stops with a
clear message if the daily quota runs out). Each question on the live site uses one, so the site
handles up to roughly 1,000 questions a day; after that it says search is at its daily limit
until the quota resets.

Do the API first: the website needs its URL.

## 0. Keys you need

- **Groq** (answers): https://console.groq.com/keys
- **Gemini** (search): https://aistudio.google.com/apikey → **Create API key**. Free, no card.

Keep both private. You paste them into Render yourself; never put them in the code.

## 1. API on Render

1. Sign up at https://render.com with your GitHub account.
2. Go to https://dashboard.render.com/blueprints → **New Blueprint Instance** → connect
   `kazzi-dev/papeles`. Render reads `render.yaml` from the repo.
3. When it asks for the secret values:
   - `LLM_API_KEY`: your Groq key
   - `GEMINI_API_KEY`: your Gemini key
4. Click **Apply**. The first build takes a few minutes.
5. Your API's URL is shown on the service page, like `https://papeles-api.onrender.com`.
   Open `<that URL>/health`; you should see `{"status":"ok"}`. `/docs` lets you try `/ask`.

Render redeploys the API by itself whenever `apps/api` changes on `main`.

Free Render services sleep after 15 minutes without traffic; the next request wakes them in
about a minute.

Optional limits (Render → service → **Environment**), defaults shown:
`RATE_LIMIT_PER_MINUTE` = `5`, `RATE_LIMIT_PER_DAY` = `50` per visitor, and
`GLOBAL_RATE_LIMIT_PER_MINUTE` = `20` for everyone together.

## 2. Website on Vercel

1. Sign up at https://vercel.com with your GitHub account (free Hobby plan).
2. **Add New → Project** → import `kazzi-dev/papeles`.
3. Configure:
   - **Root Directory:** **Edit** → `apps/web`.
   - **Framework Preset:** Next.js (detected).
   - **Environment Variables:** `NEXT_PUBLIC_API_URL` = your Render URL, no trailing slash.
4. **Deploy**.

For a nicer address, open the project → **Settings → Domains** and use e.g. `papeles.vercel.app`
if it's free. If you change `NEXT_PUBLIC_API_URL` later, redeploy; it's built into the site.

## 3. Connect them

1. In Render → papeles-api → **Environment**, set `CORS_ORIGINS` to your Vercel URL, e.g.
   `["https://papeles.vercel.app"]`, and save (Render restarts the service).
2. Open your Vercel URL and ask a question.
3. Add the link to the README and your GitHub profile.

## Updating the sources

The search index is built on your machine and committed, so after changing
`apps/api/data/sources.yaml` or a file in `apps/api/data/manual/`:

```bash
cd apps/api
# .env must have EMBEDDING_PROVIDER=gemini, GEMINI_API_KEY and a DATABASE_URL
python -m app.ingest
python -m app.snapshot export
git add data/index && git commit -m "Refresh search index" && git push
```

Render rebuilds and serves the new index.

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| Website says "Failed to fetch" | The API is asleep (wait a minute and retry) or `NEXT_PUBLIC_API_URL` is wrong. Open `<API URL>/health`. |
| Browser console shows a CORS error | Your Vercel URL isn't in `CORS_ORIGINS` or matched by `CORS_ORIGIN_REGEX`. |
| "Too many questions right now" | The rate limit is working; raise the limits in Render's Environment if needed. |
| "The free AI quota is used up" | Groq's free limit was reached; it resets within a minute (or daily). |
| API returns 500 on every question | Check `GEMINI_API_KEY` in Render; search needs it. The service logs show the error. |
| "Search has reached its free daily limit" | Gemini's 1,000-per-day quota is used up; it resets daily. |
| Build fails with "different embedding settings" | The committed index was made with another embedding setup; re-run the ingest and export. |
