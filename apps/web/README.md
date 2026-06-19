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
uvicorn src.api.app:app --reload --port 8000
```

For production builds, point the app at an absolute backend origin:

```bash
VITE_API_BASE_URL=https://api.neuronews.example npm run build
npm run preview
```

## Views & backend wiring

Each view fetches from the backend and **falls back to the design dataset** if
the endpoint is unreachable or returns no rows, so the UI always renders. The
data source (`live` / `demo`) is tracked per query in `src/lib/queries.ts`.

| View            | Backend endpoint(s)                                  |
| --------------- | ---------------------------------------------------- |
| Overview        | aggregates feed / clusters / trending                |
| News Feed       | `GET /api/v1/news/articles`                          |
| Entity Graph    | `GET /api/influence/top-influencers`                 |
| Sentiment       | static heatmap (no live endpoint yet)                |
| Event Clusters  | `GET /api/v1/events/clusters`                        |
| Trending        | `GET /topics/trending`                               |
| Breaking ticker | `GET /api/v1/breaking_news`                          |
| Workspaces      | client research data (no backend endpoint)           |
| Watchlists      | client research data (no backend endpoint)           |
| Story Timeline  | client research data (no backend endpoint)           |

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
