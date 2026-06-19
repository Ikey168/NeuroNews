# NeuroNews Intelligence Terminal — Web Frontend

A React + Vite + TypeScript single-page app that implements the **NeuroNews
Intelligence Terminal** design (dark "terminal" UI) pixel-for-pixel, wired to
the NeuroNews FastAPI backend (`src/api`).

## Stack

- **React 18** + **TypeScript**
- **Vite** (dev server, build)
- **TanStack Query** for data fetching with transparent fallback

No CSS framework: the design is reproduced with the exact inline styles, fonts
(Space Grotesk / IBM Plex Mono / IBM Plex Sans) and color tokens from the
handoff. Tokens live in `src/theme.ts`.

## Getting started

```bash
cd apps/web
npm install
npm run dev        # http://localhost:5173
```

By default the dev server proxies API requests to the FastAPI backend at
`http://localhost:8000` (override with `VITE_API_PROXY_TARGET`). Start the
backend separately, e.g.:

```bash
pip install -r requirements.txt
NEURONEWS_DEV_MODE=true uvicorn src.api.app:app --reload --port 8000
```

`NEURONEWS_DEV_MODE=true` disables the WAF, rate limiting, API-key and RBAC
middlewares for local development. Without it the API protects itself with an
aggressive WAF and a low anonymous rate limit (10 req/min), which blocks the
dashboard's burst of requests on load. Leave it unset in production.

The backend serves real data from a **local DuckDB warehouse** (no Snowflake or
external services needed). On first request it creates and seeds
`data/neuronews.duckdb` with sample articles, so the News Feed, Overview and
Sentiment views light up `LIVE` out of the box. Point it elsewhere with
`NEURONEWS_DB_PATH`.

For production builds, point the app at an absolute backend origin:

```bash
VITE_API_BASE_URL=https://api.neuronews.example npm run build
npm run preview
```

## Live data

The app talks to the FastAPI backend on every view. To make it obvious what
you're looking at:

- The **top bar** shows a global connection pill driven by a `/health` probe:
  `CONNECTING` → `BACKEND LIVE` (green) → `DEMO MODE`. The probe re-runs every
  30s, so it flips automatically when the backend comes up or goes down.
- Each data-backed view carries a small **`LIVE` / `DEMO` / `SYNC`** badge so
  you can tell, per panel, whether the rows came from the API or the bundled
  design dataset.

To see live data: start the backend (below), then run `npm run dev`. With no
backend reachable every badge reads `DEMO`.

## Views & backend wiring

Each view fetches from the backend and **falls back to the design dataset** if
the endpoint is unreachable or returns no rows, so the UI always renders. The
data source (`live` / `demo`) is tracked per query in `src/lib/queries.ts` and
surfaced through `src/components/SourceBadge.tsx`.

| View            | Backend endpoint(s)                                  | Badge     |
| --------------- | ---------------------------------------------------- | --------- |
| Overview        | aggregates feed / clusters / trending                | live/demo |
| News Feed       | `GET /api/v1/news/articles`                          | live/demo |
| Entity Graph    | `GET /api/influence/top-influencers`                 | live/demo |
| Sentiment       | `GET /news_sentiment/topics` (stats + breakdown) — **live from local DuckDB** | live/demo |
| Sentiment       | topic×time heatmap — no hourly endpoint yet          | demo      |
| Event Clusters  | `GET /api/v1/events/clusters`                        | live/demo |
| Trending        | `GET /topics/trending`                               | live/demo |
| Breaking ticker | `GET /api/v1/breaking_news`                          | live/demo |
| Workspaces      | client research data (no backend endpoint)           | demo      |
| Watchlists      | client research data (no backend endpoint)           | demo      |
| Story Timeline  | client research data (no backend endpoint)           | demo      |

> Which endpoints serve real data today: **articles** (News Feed + Overview),
> **sentiment topics** (Sentiment), **trending** (`/topics/trending`),
> **event clusters** (`/api/v1/events/clusters`) and the **breaking-news**
> ticker (`/api/v1/breaking_news`) are all backed by the local DuckDB
> warehouse — trending/clusters/breaking are derived from the seeded
> `news_articles` table (grouped by topic, with size/recency-based scores).
> Only the Sentiment topic×time heatmap (no hourly endpoint) and the research
> views (Workspaces / Watchlists / Timeline) remain on the demo dataset.

> Note: the backend list endpoints expose a subset of the fields the design
> shows (e.g. `/news/articles` has no per-article summary/entities, and the
> cluster endpoint has no aggregate sentiment). Adapters in `src/lib/adapters.ts`
> degrade gracefully for missing fields. Wiring the research views and the
> richer per-article fields is a natural follow-up once the backend exposes them.

## Project layout

```
src/
  theme.ts              design tokens (colors, fonts, accent)
  types.ts              view-model types
  lib/
    api.ts              typed fetch client for the FastAPI backend
    adapters.ts         backend response -> view-model mapping
    queries.ts          React Query hooks + demo fallback
    sentiment.ts        sentColor / sentLabel / fmt helpers
  data/mock.ts          design dataset (fallback + research views)
  components/           Sidebar, TopBar, BreakingTicker, charts, ...
  views/                one component per terminal view
```
