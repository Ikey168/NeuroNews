---
name: run-streamlit
description: Run, launch, start, or screenshot the NeuroNews Streamlit app (apps/streamlit — Home dashboard + "Ask the News" Q&A page). LEGACY/deprecated — the primary UI is now the apps/web React frontend (use run-web). Use this only when specifically working on the Streamlit code.
---

# Run the NeuroNews Streamlit app

> **Legacy.** The Streamlit app is effectively deprecated — the primary
> NeuroNews UI is now the React frontend in `apps/web` (skill: `run-web`). Reach
> for this skill only when you're specifically touching the Streamlit code; for
> "show me the NeuroNews dashboard," use `run-web` instead.

`apps/streamlit` is a multi-page Streamlit app: a static **Home** dashboard and
an **Ask the News** Q&A/debug page (`pages/02_Ask_the_News.py`) that wraps the
RAG pipeline. Home renders standalone in ~2s with no backend. Ask the News pulls
in the full ML/RAG stack on import (transformers, torch, mlflow) and **does not
render in this container** — that stack isn't installed (see Gotchas).

The agent path is the driver at
`.claude/skills/run-streamlit/driver.mjs`: it drives a running Streamlit server
with headless Chromium (Playwright), screenshots Home, attempts Ask the News
with a bounded timeout, and reports console errors.

**Paths below are relative to `apps/streamlit/`.** `cd` there first.

## Prerequisites

- **Python 3** with Streamlit (already installed):

```bash
python3 -c "import streamlit; print(streamlit.__version__)"
```

- **A Chromium binary + Playwright** for the driver (same setup as `run-web`).
  The driver resolves Playwright from the global n8n install and points
  `launch()` at the Chromium under `~/.cache/ms-playwright/`. Overrides:
  `PLAYWRIGHT_PATH` (dir with the `playwright` package), `CHROMIUM_PATH`
  (explicit chrome binary). Verify Chromium is present:

```bash
ls ~/.cache/ms-playwright/chromium-*/chrome-linux64/chrome
```

## Run (agent path) — the driver

Streamlit must be started separately (spawning a long-running server from inside
the driver is unreliable under restrictive sandboxes).

**1. Start Streamlit** (background; headless mode skips the email prompt and
auto-open):

```bash
cd apps/streamlit
streamlit run Home.py --server.port 8502 --server.headless true
```

Confirm it's up (expect `200`):

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8502/
```

**2. Drive it** (from `apps/streamlit`):

```bash
node .claude/skills/run-streamlit/driver.mjs --url http://localhost:8502
```

Expected output — Home captured, Ask the News skipped (no ML stack), exit `0`:

```
Using Chromium: /home/.../chromium-1228/chrome-linux64/chrome
Navigating to http://localhost:8502
✓ home      -> .../screenshots/home.png
! "Ask the News" did not render within 20000ms — expected without the ML stack ...
Screens captured: 1
No console errors.
```

Screenshots land in `.claude/skills/run-streamlit/screenshots/`. **Open
`home.png` and look** — it shows the "NeuroNews Dashboard" with the sidebar nav
("Home" / "Ask the News"), "Available Tools" and "Navigation" sections.

If you DO have the ML stack installed, give Ask the News a longer window:

```bash
ASK_TIMEOUT_MS=120000 node .claude/skills/run-streamlit/driver.mjs --url http://localhost:8502
```

## Run (human path)

```bash
cd apps/streamlit
streamlit run Home.py    # opens http://localhost:8501, Ctrl-C to stop
```

Useless headless — no browser to view it in. Use the driver.

## Gotchas

- **The "Ask the News" page wedges on import here.** It does
  `from services.rag.answer import RAGAnswerService`, which imports
  `transformers`; transformers lazily imports a model module that needs
  `torchvision`, which isn't installed. The page's `except ImportError` is
  *supposed* to catch this and show a demo form, but the heavy transformers
  import chain never returns within 90s — the page's "Running…" status widget
  spins forever and no heading paints. The driver bounds the wait and moves on;
  Home is the reliable screenshot. The server log shows the smoking gun:
  `ModuleNotFoundError: No module named 'torchvision'` deep in a transformers
  stack trace.
- **Home itself is mostly static** (`st.title` + `st.markdown`) — it needs no
  backend, no DB, no keys, and renders in ~2s. That's why it's the deliverable.
- **`mlflow` is also missing** — the first page load logs
  `RAG dependencies unavailable: No module named 'mlflow'`. Benign for Home.
- **Streamlit keeps a websocket open**, so Playwright's `networkidle` never
  fully settles by itself. The driver waits on Streamlit's `stStatusWidget`
  detaching (the "Running" indicator) plus a short settle instead.
- **`--server.headless true` matters.** Without it Streamlit prints a "Welcome"
  email prompt and tries to open a browser, which is noise in a container.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Driver: `Could not load Playwright` | Set `PLAYWRIGHT_PATH` to a `node_modules` dir containing `playwright` (e.g. `/usr/local/lib/node_modules/n8n/node_modules`). |
| Driver: `Executable doesn't exist at .../chromium_headless_shell-...` | The driver auto-discovers the cached Chromium; if it still fails set `CHROMIUM_PATH` (`ls ~/.cache/ms-playwright/chromium-*/chrome-linux64/chrome`). |
| `curl http://localhost:8502/` not 200 | Streamlit not up yet (it's slow to boot) or port taken. Wait a few seconds; pick another `--server.port`. |
| Ask the News never renders | Expected without `torch`/`torchvision`/`transformers`/`mlflow`. Install the full RAG stack (`requirements*.txt`) and re-run with a large `ASK_TIMEOUT_MS`. |
