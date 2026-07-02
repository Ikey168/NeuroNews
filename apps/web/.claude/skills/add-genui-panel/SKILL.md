---
name: add-genui-panel
description: Add a new panel type to the Noesis generative canvas (apps/web + src/genui). Use when the canvas should be able to render a new kind of content — a new chart, list, or metric — that the planner can select for matching intents. Covers the backend catalog, the ui-spec-v1 contract, the frontend mirror/registry, and the tests that keep the three in sync.
---

# Add a panel type to the Noesis generative canvas

The UI has no fixed views: every screen is a `ui-spec-v1` layout planned from
an intent and rendered from a panel registry. Adding a capability to the
canvas means adding a **panel type** in three synchronized places — backend
catalog, JSON-schema contract, frontend mirror — plus a renderer. Miss one
and either the backend emits panels the frontend stubs out, or validation
rejects the planner's own output.

**Paths are relative to the repo root.**

## The 6 touch-points

1. **`src/genui/catalog.py`** — add a `PanelDef` to `PANEL_CATALOG`:

   ```python
   PanelDef(
       type="my_panel",                    # renderer key, snake_case
       title="My panel",
       description="One line for the LLM planner and /api/v1/ui/panels.",
       endpoint="/api/v1/my_thing",        # or None for client-side data
       facets=("overview",),               # which intents select it
       tables=("my_table",),               # warehouse tables it needs (availability gate)
       ui_flag=None,                       # domain-pack flag gate, if any
       default_span=6,                     # 12-column grid units
       topic_param="topic",                # param names, if the endpoint takes them
       source_type_param="source_type",
       days_param="days", max_days=30,     # match the endpoint's Query(le=...)
   )
   ```

   Catalog order matters: within a facet, earlier panels get higher priority.

2. **`contracts/schemas/jsonschema/ui-spec-v1.json`** — add the type to the
   panel `type` enum (and any new facet to the facets enum).

3. **`apps/web/src/genui/spec.ts`** — add the type to the `PanelType` union
   and a mirrored entry to `PANEL_CATALOG` (used by the offline client
   planner and pinned-panel rendering).

4. **`apps/web/src/genui/registry.tsx`** — write the renderer and register it:

   ```tsx
   function MyPanel(props: PanelProps) {
     const { data, source, isLoading } = useMyThing();   // hook from lib/queries.ts
     return (
       <GenPanel {...props} source={source} isLoading={isLoading}>
         {data.length === 0 ? <Empty text="No data yet" /> : /* rows */}
       </GenPanel>
     );
   }
   // ...and in REGISTRY: my_panel: MyPanel,
   ```

   Read panel params defensively (`props.panel.params?.topic` may be any
   scalar — see `topicMatch`/`daysParam` helpers). Hooks must be called
   unconditionally (hooks rules); reuse or extend `lib/queries.ts` hooks,
   which give you the live/demo fallback and `SourceBadge` provenance.

5. **Planner keywords (only if the panel needs a new facet)** — add the facet
   to `FACETS` in `catalog.py`, keywords to `FACET_KEYWORDS` in BOTH
   `src/genui/planner.py` and `apps/web/src/genui/planner.ts` (keep them
   word-for-word identical — a drift means live and offline plans diverge),
   and the contract facets enum.

6. **Tests** — extend `tests/unit/genui/` (planner selects the panel for a
   matching intent; catalog dict shape) and, if you added params, assert they
   land on the panel. Run:

   ```bash
   python3 -m pytest tests/unit/genui tests/unit/api/routes/test_genui_routes_smoke.py -q
   cd apps/web && npm run typecheck
   ```

## Verify

```bash
python3 - <<'PY'
from src.genui import plan, validate_spec
spec = plan("an intent that should select your panel")
print([p.type for p in spec.panels])
assert validate_spec(spec.to_dict()) == []
PY
```

Then screenshot with the run-web driver (add a preset to
`src/components/Sidebar.tsx` if the panel deserves a sidebar entry, and its
label to the driver's `VIEWS`):

```bash
node .claude/skills/run-web/driver.mjs --url http://localhost:5173 --view briefing
```

## Gotchas

- **Three catalogs, one truth.** `catalog.py`, the contract enum, and
  `spec.ts` must agree on the type string. The contract test
  (`tests/unit/genui/test_genui_spec.py`) and `validate_spec` catch backend
  drift; a missing frontend registry entry renders a "not installed" stub
  rather than crashing — visible in screenshots.
- **`tables` drives adaptivity.** If the warehouse table is empty the panel
  is silently dropped from generated layouts (by design). Leave `tables=()`
  for panels fed by non-warehouse or client-side data.
- **`max_days` must match the endpoint's `Query(le=...)`** or generated
  layouts will 422 against their own endpoint and the panel falls to demo.
- **Params reach the renderer as untrusted scalars** (the LLM planner can
  emit anything that validates). Type-check before use.
