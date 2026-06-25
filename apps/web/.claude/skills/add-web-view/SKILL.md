---
name: add-web-view
description: Scaffold a new view/page in the NeuroNews web frontend (apps/web). Use when adding a sidebar tab, a new dashboard screen, or wiring a backend endpoint into a new React view. Covers the exact touch-points (ViewKey, Sidebar nav, view component, App switch, api/adapter/query/mock) so the view compiles and renders.
---

# Add a view to the NeuroNews web frontend

`apps/web` renders one component per sidebar tab. A view is registered in a few
fixed places; miss one and it either won't compile (the `ViewKey` union is
exhaustive) or won't appear. This skill is the checklist — verified by
scaffolding a throwaway view, screenshotting it, and reverting.

**Paths below are relative to `apps/web/`.** Every view follows the same shape:
a component in `src/views/` that calls a `useX()` hook from `src/lib/queries.ts`
and renders `<PageHeader>` + `<SourceBadge>`.

## The 4 required touch-points (structural)

A view needs these four edits to compile and show up. (Data wiring is separate,
below — a demo-only view can reuse an existing hook or static data.)

1. **`src/types.ts`** — add the slug to the `ViewKey` union (around line 154):

   ```ts
   export type ViewKey =
     | "dashboard"
     | ...
     | "timeline"
     | "pulse";        // <- new
   ```

2. **`src/views/Pulse.tsx`** — the component. Minimal shape that renders and
   shows the live/demo badge:

   ```tsx
   import { fonts } from "../theme";
   import { useTrending } from "../lib/queries";
   import PageHeader from "../components/PageHeader";
   import SourceBadge from "../components/SourceBadge";

   export default function Pulse() {
     const { data: trending, source, isLoading } = useTrending();
     return (
       <div>
         <PageHeader
           title="Pulse"
           subtitle="Some subtitle"
           right={<SourceBadge source={source} isLoading={isLoading} />}
         />
         <div style={{ fontFamily: fonts.mono, fontSize: 13, color: "#c7cdd6" }}>
           {trending.length} trending topics loaded.
         </div>
       </div>
     );
   }
   ```

3. **`src/components/Sidebar.tsx`** — add a `NavDef` to `intelligenceNav` (top
   group) or `researchNav` (bottom group). `glyph` is a single unicode mark;
   `badge` is optional:

   ```ts
   { key: "pulse", label: "Pulse", glyph: "◇" },
   ```

4. **`src/App.tsx`** — import the component and add it to the view switch:

   ```tsx
   import Pulse from "./views/Pulse";
   // ...inside <main>:
   {view === "pulse" && <Pulse />}
   ```

## Data wiring (if the view needs a backend endpoint)

Demo-only views reuse an existing hook (as above) or static data. To pull from
the backend, follow the existing pattern across four files — read a working
example end-to-end first: `useArticles` is wired through all four
(`api.articles` → `adaptArticles` → `useArticles` → `mockArticles`).

1. **`src/lib/api.ts`** — add a typed call under the `api` object and a `Raw…`
   interface for the backend's response shape:

   ```ts
   myThing: (params?: { days?: number }) =>
     request<RawMyThing[]>("/api/v1/my_thing", params),
   ```

2. **`src/lib/adapters.ts`** — map the `Raw…` shape to the view-model type from
   `src/types.ts` (adapters read defensively; backend fields are often a subset
   of what the design shows).

3. **`src/lib/queries.ts`** — add the hook via `useWithFallback`, which returns
   `{ data, source, isLoading }` and swaps to the mock on error **or empty
   payload**:

   ```ts
   export function useMyThing(): Result<MyThing[]> {
     return useWithFallback("myThing", async () => adaptMyThing(await api.myThing()), mockMyThing);
   }
   ```

4. **`src/data/mock.ts`** (or an inline `const` in `queries.ts`, like
   `mockTopEntities`) — the design dataset the view falls back to so it always
   renders without a backend.

## Verify

```bash
cd apps/web
npm run typecheck     # catches a missing ViewKey arm / bad import — must be exit 0
```

Then screenshot the new tab with the run-web driver. It clicks every sidebar
label, so add your view's **label** to the `VIEWS` array in
`.claude/skills/run-web/driver.mjs` (`["Pulse", "pulse"]`) to include it, or
just run the driver and confirm no console errors:

```bash
npm run dev    # in one shell; note the port (5173+)
node .claude/skills/run-web/driver.mjs --url http://localhost:5173 --view pulse
```

Open `.claude/skills/run-web/screenshots/pulse.png` and confirm the view
renders with its `PageHeader` and a `LIVE`/`DEMO` badge.

## Gotchas

- **`ViewKey` is exhaustive — `tsc` is your safety net.** Add the slug to the
  union (step 1) *and* an arm in `App.tsx` (step 4). Forgetting the union arm is
  a type error; forgetting the `App.tsx` arm compiles but the tab does nothing.
- **The sidebar button's accessible name includes the glyph + badge**, so it's
  not matchable by `getByRole('button', { name })`. The run-web driver clicks
  the **label text** inside `<aside>` — keep labels unique.
- **`useWithFallback` treats an empty array as "demo".** If your live endpoint
  legitimately returns `[]`, the badge will read `DEMO` and the mock shows — by
  design, so the UI is never blank. Account for it when testing live wiring.
- **No CSS framework** — styling is inline-style objects with tokens from
  `src/theme.ts` (`fonts`, `palette`, `ACCENT`). Copy an existing view's style
  blocks (e.g. `views/Trending.tsx`) rather than inventing classes.
