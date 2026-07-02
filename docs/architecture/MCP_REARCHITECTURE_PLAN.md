# Rearchitecting Noesis around MCP

**Status:** Proposal (design review requested)
**Date:** 2026-07-02
**Scope:** capability layer, generative-UI planner, panel data plane
**Related:** `docs/genui.md`, `docs/architecture/KNOWLEDGE_ENGINE_PIVOT_PLAN.md`

## Summary

Noesis maintains two parallel capability surfaces: ~30 FastAPI REST routes
consumed by the generative canvas, and 12 FastMCP stdio servers
(`tools/*_mcp/`) consumed by development agents. Every subsystem —
argument mining, pipeline, knowledge graph, feeds, domain packs, lineage,
contracts, monitoring — is wrapped twice, and the generative-UI panel
catalog is hand-mirrored in three more places (`src/genui/catalog.py`,
`apps/web/src/genui/spec.ts`, `contracts/schemas/jsonschema/ui-spec-v1.json`).

This proposal makes MCP the **capability and control plane**: panels,
planner inputs, and domain-pack state derive from MCP tool discovery
instead of hand-maintained registries. The REST layer remains the
high-volume **data plane** initially; the browser never speaks MCP
directly. Migration is staged so every stage ships value independently
and stage N never blocks on stage N+1.

## Current state

| Concern | Today | Problem |
|---|---|---|
| Capabilities | REST routes in `src/api/routes/*` **and** MCP tools in `tools/*_mcp/` | Every feature implemented and documented twice; surfaces drift |
| Panel catalog | Hand-written in `catalog.py`, mirrored in `spec.ts` + contract enum | Triple mirror; the genui review found real drift defects and the sync is test-enforced by hand |
| Domain packs | Registry + `config/domain_packs.json` + `ui_flags` dict | A pack is *conceptually* a capability bundle — exactly what an MCP server is |
| Data availability | Bespoke DuckDB probe in `src/genui/adaptivity.py` | Duplicate of what `am_stats` / `get_stats`-style MCP tools already report |
| LLM planner | One-shot JSON completion over a static catalog dump | Plans blind; cannot inspect data before composing a layout |
| Dev agents | `.mcp.json` wires 12 servers (read-only, token-thin by design) | Right for debugging; payloads too thin for UI data |

## Target architecture

```
                       ┌────────────────────────────────────────────┐
 browser (apps/web)    │ FastAPI backend = MCP HOST                 │   MCP servers (FastMCP)
 ───────────────────►  │                                            │  ┌──────────────────────┐
  REST (unchanged):    │  genui planner ──── MCP client sessions ───┼─►│ neuronews-arguments  │
  /api/v1/ui/generate  │   · catalog ⇐ tool discovery               │  │ neuronews-pipeline   │
  /api/v1/ui/panels    │   · availability ⇐ stats tools             │  │ neuronews-kg         │
  /api/v1/ui/data*     │   · LLM planning ⇐ bounded tool-use loop   │  │ neuronews-blog-feeds │
  (*stage 3)           │   · packs ⇐ server presence                │  │ … (12 servers)       │
                       └────────────────────────────────────────────┘  └──────────────────────┘
```

Component mapping:

| genui concept | MCP concept |
|---|---|
| Panel type | Tool annotated with a renderer hint (`panel:*` tag + `outputSchema`) |
| Panel catalog | Aggregated `tools/list` across connected servers |
| Domain pack enabled | Server connected (pack config ⇒ which servers to spawn) |
| `ui_flags` | Server presence + per-tool availability |
| Data availability | Stats tools (`am_stats`, `get_stats`, …) instead of raw DuckDB probing |
| LLM planner context | Live tool discovery + tool calls, not a static catalog dump |

## Decisions

1. **The browser never speaks MCP.** The backend is the single MCP host;
   the frontend keeps its typed REST client, demo fallback, and the
   `ui-spec-v1` contract unchanged. (Rationale: transport simplicity, the
   existing WAF/JWT/RBAC middleware stays authoritative, and the offline
   client planner keeps working.)
2. **Transport:** in-process/stdio FastMCP sessions supervised by the
   backend for the 12 local servers; Streamable HTTP only if/when a server
   moves off-box. No per-request process spawning — sessions are pooled
   and health-checked.
3. **`ui-spec-v1` stays the wire format.** MCP changes where the catalog
   and data come from, not what the frontend renders. Tools that feed
   panels must declare `outputSchema`; the generic renderers key off it.
4. **REST remains the hot data path until Stage 3 proves otherwise.**
   Panel fetches are high-fanout (a canvas issues 5–10 parallel queries);
   we do not put a tool-call hop in that path until the proxy shows
   acceptable latency.
5. **DuckDB single-writer discipline is unchanged.** MCP servers stay
   read-only against the warehouse (as today); RW "trigger" tools keep
   going through the API process which owns the write lock.

## Staged migration

### Stage 0 — kill the mirror by codegen (no MCP required)
Generate `spec.ts`'s `PanelType`/`PANEL_CATALOG` and the contract enums
from `catalog.py` (extend `scripts/contracts/codegen.py` or a small
`scripts/genui/codegen.py`; CI check that generated files are current).
*Exit:* one source of truth; drift becomes a build error.
*Effort: small. Risk: minimal.*

### Stage 1 — MCP-derived catalog
Backend catalog builder opens MCP sessions at startup, lists tools, and
maps annotated tools (`panel:articles`, `panel:claims`, …) into
`PanelDef`s; unannotated tools are ignored. Static catalog remains as the
fallback when servers are down. `GET /api/v1/ui/context` reports
per-server health; `merged_ui_flags`/availability read from server
presence + stats tools with the DuckDB probe as fallback.
*Exit:* dropping a new annotated MCP server surfaces a new panel type in
`/api/v1/ui/panels` with zero code changes to genui.
*Effort: medium. Risk: server lifecycle management (supervision, startup
latency) — mitigated by lazy connect + cached discovery.*

### Stage 2 — grounded LLM planning
`plan_with_llm` becomes a bounded agentic loop (the backend as MCP host):
the model may call read-only inspection tools (≤ N calls, per-call and
total timeouts, allowlist) before emitting the final `ui-spec-v1` JSON,
which still passes `_sanitize` + `validate_spec` + usage-signal
enforcement. Heuristic planner untouched and still the no-key default.
*Exit:* with a key configured, plans demonstrably reflect actual data
(e.g. skips stance panels when `am_stats` shows zero rows) — testable by
mocking the MCP client.
*Effort: medium. Risk: latency and cost per generate — mitigated by the
call budget, caching stats results, and keeping the loop optional.*

### Stage 3 — MCP-backed panel data (evaluate before committing)
Add full-payload variants to the thin dev tools ("data mode"), plus
`POST /api/v1/ui/data {tool, args}` — an allowlisted, rate-limited proxy
the frontend uses for panels whose `PanelDef` names a tool instead of a
REST endpoint. Generic renderers (table / stat / list keyed off
`outputSchema`) display any new tool's data until a bespoke renderer is
registered.
*Exit:* a brand-new capability (server + annotation) renders end-to-end
with no frontend deploy.
*Effort: large. Risk: latency on the hot path, payload discipline, proxy
security surface — gate on a benchmark against the equivalent REST route.*

### Stage 4 (optional) — Noesis as an MCP server
Expose `noesis_generate_view(intent) -> ui-spec-v1` (+ claim/stance query
tools) over Streamable HTTP so external MCP hosts (Claude Desktop, other
agents) can drive Noesis; the spec document is the resource. Pairs with
the emerging MCP-apps/embedded-UI pattern when hosts support it.
*Effort: small once Stages 1–2 exist.*

## What deliberately does not change

- `ui-spec-v1` contract, validators, and fixtures.
- The heuristic planner and the browser's offline client planner.
- Frontend live/demo fallback semantics and the adaptive usage signals.
- WAF/JWT/RBAC middleware as the only externally reachable surface.
- The `.mcp.json` dev-tooling experience (dev agents keep using the same
  servers; they gain tools rather than losing any).

## Risks

| Risk | Mitigation |
|---|---|
| Server lifecycle complexity (12 child processes) | Pooled sessions, lazy connect, health endpoint in `/api/v1/ui/context`, static-catalog fallback |
| Latency regression on generate/data paths | Call budgets, discovery/stats caching (TTL ~60s), Stage-3 benchmark gate |
| Loose typing of tool results | Require `outputSchema` for panel-annotated tools; contract tests validate sample outputs |
| Auth story for remote MCP | Defer: local stdio only until a concrete remote need; proxy inherits existing HTTP auth |
| Scope creep into a data-plane rewrite | Stages are independently shippable; Stage 3 explicitly gated on measurement |

## Open questions

1. Tool→panel annotation format: FastMCP tags vs. a `meta.panel` block in
   tool descriptions — pick whichever survives `tools/list` serialization
   cleanly across FastMCP versions.
2. Where do bespoke renderers live long-term — keyed by tool name, or by
   a `renderer` hint the server declares?
3. Should domain-pack enable/disable move fully to "which servers are
   configured", retiring `config/domain_packs.json`, or keep the file as
   the source that *selects* servers? (Proposal: keep the file, it selects
   servers.)
4. Does Stage 3 use MCP resources (for cacheable reads) rather than tool
   calls for panel data?

## Recommendation

Adopt Stages 0–2. They remove the duplication and drift that motivate the
rearchitecture and make the LLM planner meaningfully better, at bounded
risk, without touching the hot data path. Decide Stage 3 only after the
Stage-1 session infrastructure has soaked and a latency benchmark exists;
Stage 4 is cheap opportunistic surface once 1–2 land.
