# 8. Live site guide: what is what

The same app runs in two places:

- **Online:** https://rudder-fde-qiyin.netlify.app (Netlify + Render). Share a link, open it from any computer.
- **On your Mac:** `./run.sh` → http://127.0.0.1:8000 (control center) and http://127.0.0.1:8001 (CRM).

Same code in both. Every push to GitHub (branch `claude/affectionate-euler-cvrdsm`) redeploys the online version.

## The addresses

| Address | What it is | Served by |
|---|---|---|
| https://rudder-fde-qiyin.netlify.app/ | **Control center**: Demo, Call my phone, Results, Troubleshoot, and the **Learn** tab (video + Learn page) | Netlify page; its buttons call the backend |
| `/learn` | **Learn page**: interview prep (AI Rudder, CALL-E, the role), the project in depth (diagrams, code tour, terminal, these docs) and what to say (script, STAR, Q&A, flashcards) | Netlify |
| `/crm/` | **Mock CRM**: the 8 fictional customers, follow-up tasks, outage buttons | Render, through Netlify |
| `/docs` | Interactive API reference (Swagger). Every button is one of these endpoints | Render, through Netlify |
| `/api/status` | Health check: JSON with CALL-E mode, CRM state, webhook | Render, through Netlify |
| `/rudder/ai-rudder-explainer.mp4` | The 7-minute explainer video file | Netlify CDN |
| `/rudder/video/player.html` | The same video as an interactive animation you can scrub | Netlify |
| `/rudder/` | Old address of the study guide. Redirects to `/learn` | Netlify |
| https://calle-rudder-api.onrender.com | **The backend itself.** You rarely open it: Netlify forwards to it. Useful to check `/api/status` directly | Render |

## Why two services (Netlify and Render)

```
 Browser ──▶ Netlify ── pages, video (CDN) ────────────────▶ served directly
                    └── /api/*, /calls/*, /crm/*, /docs ───▶ Render: FastAPI backend
                                                              orchestrator + mock CRM (/crm)
 CALL-E (live calls) ── webhook ──▶ Render directly (RENDER_EXTERNAL_URL/calle/webhook)
 Simulated calls ── webhook ──▶ loopback inside the Render process
```

| | Netlify | Render |
|---|---|---|
| Job | Hosts the static pages and the 36 MB video on a CDN; **proxies** every API path to Render | Runs the Python backend: campaign, guards, CALL-E gateway, webhook, rules, outbox, mock CRM, SQLite |
| Why it's needed | Fast, free, redeploys on push, one public address for everything | Netlify **can't run Python**, a database or background timers (the simulated webhooks) |
| Config | `netlify.toml`, `scripts/netlify_build.sh`, env var `BACKEND_URL` | `render.yaml`, `app/combined.py`, env vars `LIVE_PASSCODE`, optional `CALLE_API_KEY` |

Because Netlify proxies the API, the browser only ever talks to `rudder-fde-qiyin.netlify.app`. There's no CORS setup, and
the UI code is identical locally and online. Locally the CRM is a separate service on :8001; online it is mounted at `/crm`
inside the same Render process, and the orchestrator still talks to it over real HTTP (loopback).

## Live site or your Mac?

| Use the live site when… | Use your Mac when… |
|---|---|
| You want to share a link or present from another computer | It's the interview demo: no cold start, private data, no passcode |
| You don't want to install anything | You want to change code, run tests, or show the terminal (`git log`, `pytest`) |

## Before presenting on the live site

1. **Wake it up 2–3 minutes early.** The free Render instance sleeps after ~15 minutes idle and takes up to a minute to start.
   While it wakes, the control center shows a yellow "Can't reach the server yet" banner and retries by itself.
2. **Demo tab → Reset everything.** Everyone who opens the link shares the same CRM and calls, and Render restarts reset them.
3. **Real calls are locked.** "Call my phone" asks once per browser session for the **live-call passcode**: Render dashboard →
   `calle-rudder-api` → **Environment** → `LIVE_PASSCODE`. This stops visitors from spending your CALL-E credits.
4. Optional: put your CALL-E key in Render's `CALLE_API_KEY`. A key typed into the page lives in memory and is lost when the
   instance sleeps.

## What to change where

| You want to… | Do this |
|---|---|
| Change code, docs, the Learn page or the video | Edit, run `./setup.sh` (tests), push to GitHub. Netlify and Render both redeploy (about 1–5 min) |
| Point Netlify at a different backend | Netlify → Site configuration → Environment variables → `BACKEND_URL`, then Deploys → Trigger deploy |
| Change the live-call passcode | Render → service → Environment → `LIVE_PASSCODE` → Save (Render restarts the service) |
| Read backend logs | Render → service → **Logs** |
| See why a page deploy failed | Netlify → **Deploys** → the failed deploy → log |

## Troubleshooting

| You see | Why | Fix |
|---|---|---|
| Yellow "Can't reach the server yet" banner | Render is asleep or restarting | Wait up to a minute; the page retries by itself |
| `/api/status` returns 404 "Not Found" | Netlify forwards to a Render service that doesn't exist (wrong `BACKEND_URL`) | Check the Render URL; update `BACKEND_URL`; redeploy Netlify |
| A 401 asking for a passcode | Real calls are locked on the public site | Enter `LIVE_PASSCODE` from Render |
| The CRM page loads but buttons do nothing | It was opened at `/crm` (no slash), so its relative links point at the site root. The page now redirects itself to `/crm/`; an old cached copy may not | Open `/crm/` with the slash, or reload |
| Results stuck in `submitted` on a live call | No webhook arrived yet | Results → the call → "Sync from CALL-E"; the live tab also polls |
| Data looks strange | Someone else used the shared demo, or Render restarted | Demo tab → Reset everything |
