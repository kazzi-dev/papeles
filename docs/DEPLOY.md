# Deploying Papeles for free

| Part | Host | Cost |
| --- | --- | --- |
| API (`apps/api`) | Hugging Face Spaces, Docker | Free (CPU basic) |
| Website (`apps/web`) | Vercel | Free (Hobby) |
| AI answers | Groq free tier | Free |
| Data | Built into the API image as SQLite | Free |

The API image downloads the official sources, embeds them and stores them in a SQLite file while
it builds, so there is no database to run. Rebuilding the Space refreshes the data.

Do the API first: the website needs its URL.

## 1. API on Hugging Face Spaces

### Create the Space

1. Sign up at https://huggingface.co (free).
2. Go to https://huggingface.co/new-space.
3. Fill in:
   - **Space name:** `papeles-api`
   - **License:** MIT (or leave empty)
   - **SDK:** Docker → **Blank**
   - **Hardware:** CPU basic (free)
   - **Visibility:** Public
4. Click **Create Space**.

Your API's URL will be `https://<your-hf-name>-papeles-api.hf.space`. (Hugging Face lowercases it
and turns `_` into `-`.)

### Add your settings

In the Space, open **Settings → Variables and secrets**:

| Type | Name | Value |
| --- | --- | --- |
| Secret | `LLM_API_KEY` | your Groq key (`gsk_...`) |
| Variable | `LLM_PROVIDER` | `groq` |
| Variable | `CORS_ORIGINS` | `["https://papeles.vercel.app"]` (your Vercel URL from step 2; you can update it later) |
| Variable | `CORS_ORIGIN_REGEX` | `https://papeles(-[a-z0-9-]+)?\.vercel\.app` (lets Vercel preview links work too) |

Optional limits (defaults shown): `RATE_LIMIT_PER_MINUTE` = `5`, `RATE_LIMIT_PER_DAY` = `50` per
visitor, and `GLOBAL_RATE_LIMIT_PER_MINUTE` = `20` for everyone together, which keeps you under
Groq's free 30 requests per minute.

Never put the key in the code or in a Variable; Variables are public.

### Send the code to the Space

The GitHub Action in `.github/workflows/deploy-api.yml` pushes `apps/api` to your Space on every
push to `main` that changes it.

1. On Hugging Face, go to https://huggingface.co/settings/tokens → **Create new token** →
   type **Write** → name it `github-deploy` → create, and copy it.
2. On GitHub, open the papeles repo → **Settings → Secrets and variables → Actions**:
   - **Secrets** tab → **New repository secret**: name `HF_TOKEN`, value the token.
   - **Variables** tab → **New repository variable**: name `HF_SPACE`, value
     `<your-hf-name>/papeles-api`.
3. Go to the **Actions** tab → **Deploy API to Hugging Face** → **Run workflow**.

The Space starts building (watch the **Logs** tab on Hugging Face). The first build takes about
5 to 10 minutes because it downloads the sources and the embedding model.

### Check it

Open `https://<your-hf-name>-papeles-api.hf.space/health`. You should see `{"status":"ok"}`.
`/docs` lets you try `/ask` in the browser.

If a source shows `skip` in the build log, that site refused the download from Hugging Face's
servers; the rest still work.

## 2. Website on Vercel

1. Sign up at https://vercel.com with your GitHub account (free Hobby plan).
2. Click **Add New → Project** and import `kazzi-dev/papeles`.
3. Configure:
   - **Root Directory:** click **Edit** and choose `apps/web`.
   - **Framework Preset:** Next.js (detected automatically).
   - **Environment Variables:** add `NEXT_PUBLIC_API_URL` =
     `https://<your-hf-name>-papeles-api.hf.space` (no trailing slash).
4. Click **Deploy**.

To get a nicer address, open the project → **Settings → Domains** and change it to
`papeles.vercel.app` if it's free (or any name you like).

If you change `NEXT_PUBLIC_API_URL` later, redeploy (**Deployments → ⋯ → Redeploy**); it's built
into the site.

## 3. Connect them

1. Put your final Vercel URL in the Space's `CORS_ORIGINS` variable, for example
   `["https://papeles.vercel.app"]`. The Space restarts by itself.
2. Open your Vercel URL and ask a question.
3. Add the link to the top of the README and to your GitHub profile.

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| Website says "Failed to fetch" | The Space is asleep (the first request after a while can take up to a minute) or `NEXT_PUBLIC_API_URL` is wrong. Open the `/health` URL to wake and check it. |
| Browser console shows a CORS error | Your Vercel URL isn't in `CORS_ORIGINS` or matched by `CORS_ORIGIN_REGEX`. |
| "Too many questions right now" | The rate limit is working. Raise the limits in the Space variables if needed. |
| "The free AI quota is used up" | Groq's free tier limit was reached; it resets within a minute (or daily for the daily cap). |
| Answers have no written text, only sources | `LLM_API_KEY` is missing or wrong in the Space secrets. |
| Action fails at "Push apps/api to the Space" | Check that `HF_TOKEN` has **Write** access and `HF_SPACE` is `name/space` exactly. |
