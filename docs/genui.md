# Noesis Canvas — adaptive, generative UI

The Noesis Canvas (`apps/web` → sidebar → **Noesis Canvas**) turns a
natural-language intent — *"compare outlet framing on climate policy"*,
*"who disagrees about AI regulation?"* — into a dashboard layout at
runtime. The layout is a validated **`ui-spec-v1`** document; the frontend
renders it from a panel registry built on the app's existing hooks and
charts, so every generated panel keeps the terminal's live/demo fallback
behaviour.

## Architecture

```
intent ──► POST /api/v1/ui/generate ──► ui-spec-v1 ──► SpecRenderer
              │                                            │
              ├─ LLM planner (optional, key-gated)         ├─ panel registry
              ├─ heuristic planner (always available)      │  (17 renderers over
              └─ adaptivity:                               │   existing hooks/charts)
                  · warehouse data availability            └─ GenPanel chrome
                  · domain-pack ui_flags                       (pin / mute / badge)
                  · usage signals (pins, mutes, weights)
```

### Backend (`src/genui/`)

| Module | Role |
|---|---|
| `catalog.py` | Panel catalog: type → endpoint, warehouse tables, `ui_flag`, facets, layout defaults. Single source of truth, mirrored by the frontend registry. |
| `spec.py` | `ui-spec-v1` dataclasses + pure-Python `validate_spec` (contract: `contracts/schemas/jsonschema/ui-spec-v1.json`). |
| `planner.py` | Heuristic planner: facet scoring from keyword evidence, topic / source-type / time-window extraction, panel assembly. No model, no network. |
| `adaptivity.py` | The adaptive inputs: DuckDB table probing (`data_availability`), merged domain-pack `ui_flags`, and usage-signal re-ranking (`apply_signals`). |
| `llm.py` | Optional LLM planner (Anthropic or OpenAI). Any failure — no key, no SDK, bad JSON, invalid spec — falls back to the heuristic planner. |

Routes (`src/api/routes/genui_routes.py`, registered via the standard
feature-flag pattern in `src/api/app.py`):

- `POST /api/v1/ui/generate` — `{intent, source_type?, signals?}` → `{spec, meta}`
- `GET /api/v1/ui/context` — merged ui_flags, availability map, LLM planner status
- `GET /api/v1/ui/panels` — the panel catalog

### Frontend (`apps/web/src/genui/`)

- `spec.ts` — ui-spec-v1 types + client mirror of the catalog.
- `registry.tsx` — panel type → renderer, reusing `lib/queries.ts` hooks and
  the SVG charts; unknown types render a stub, never crash.
- `useUiSpec.ts` — asks the backend planner, falls back to `planner.ts`
  (a slim TS mirror of the heuristic rules) when unreachable.
- `signals.ts` — localStorage usage signals: pin (always include + boost),
  mute (hide type), interaction weights. Fed back into every generation.
- `GenPanel.tsx` / `SpecRenderer.tsx` — panel chrome (pin/mute/provenance
  badge) and the 12-column grid.

The provenance strip above the canvas shows which planner ran:
`LLM PLAN` / `RULE PLAN` (backend) / `LOCAL PLAN` (client fallback).

## Adaptivity guarantees

- **Data-aware**: panels whose warehouse tables are empty are dropped and
  listed in the plan note ("Hidden for now…"). Unknown availability keeps
  every panel (frontend demo fallback covers empty endpoints).
- **Pack-aware**: panels gated by a domain-pack `ui_flag` disappear when
  the pack is disabled.
- **Usage-aware**: pins always include and boost a panel type; mutes hide
  it (restorable from the muted strip); interaction weights nudge ordering.
- **Never empty**: if adaptivity removes every data panel, the canvas falls
  back to the overview set.

## LLM planner configuration (optional)

| Env var | Meaning |
|---|---|
| `NOESIS_GENUI_LLM` | `auto` (default) or `off`. |
| `NOESIS_GENUI_PROVIDER` | `anthropic` or `openai`; auto-detected from which API key is set. |
| `NOESIS_GENUI_MODEL` | Model id override. |
| `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` | Provider credentials. |

Without a key the canvas is fully functional on the heuristic planner —
the spec shape and every downstream behaviour are identical.

## Tests

```
python3 -m pytest tests/unit/genui tests/unit/api/routes/test_genui_routes_smoke.py \
    tests/unit/api/routes/test_genui_routes_coverage.py -q
```

Contract fixtures live in `contracts/examples/ui-spec-v1/{valid,invalid}/`
and are validated by both the pure-Python validator and (when installed)
`jsonschema` against `contracts/schemas/jsonschema/ui-spec-v1.json`.
