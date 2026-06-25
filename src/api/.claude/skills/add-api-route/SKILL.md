---
name: add-api-route
description: Scaffold a new FastAPI route/endpoint in the NeuroNews backend (src/api). Use when adding a REST endpoint, a new router module, or wiring a route into src/api/app.py. Covers the route file plus the 4 feature-flag registration edits in app.py, and how to verify the route in isolation.
---

# Add a route to the NeuroNews FastAPI backend

`src/api/app.py` registers routers through a **feature-flag pattern**: each
optional router has a module-level `*_AVAILABLE` flag, a `try_import_*()` that
imports it under `try/except ImportError`, a call to that importer in
`check_all_imports()`, and an `if *_AVAILABLE:` block in
`include_optional_routers()` that does `app.include_router(...)`. Adding an
endpoint means one new route file plus those four edits.

**Paths below are relative to the repo root** (`/home/Ikey/NeuroNews`). The
companion `add-web-view` skill (in `apps/web`) wires the resulting endpoint into
the frontend.

## The route file

Create `src/api/routes/<name>_routes.py` with a module-level `router`. Mirror
`src/api/routes/topic_routes.py`:

```python
"""<name> routes."""
from typing import Any, Dict
from fastapi import APIRouter, Query

router = APIRouter(prefix="/api/v1/<name>", tags=["<name>"])

@router.get("/ping")
async def ping(name: str = Query("world")) -> Dict[str, Any]:
    return {"message": f"hello, {name}", "wired": True}
```

## The 4 edits in `src/api/app.py`

Copy the `topic_routes` wiring verbatim, renaming to your route. The four spots:

1. **Module-level flag** (with the others near the top, ~line 13):

   ```python
   MYTHING_ROUTES_AVAILABLE = False
   ```

2. **`try_import_*()` function** (next to `try_import_topic_routes`):

   ```python
   def try_import_mything_routes():
       global MYTHING_ROUTES_AVAILABLE
       try:
           from src.api.routes import mything_routes
           _imported_modules['mything_routes'] = mything_routes
           MYTHING_ROUTES_AVAILABLE = True
           return True
       except ImportError:
           MYTHING_ROUTES_AVAILABLE = False
           return False
   ```

3. **Call it in `check_all_imports()`** (alongside the other `try_import_*()`
   calls):

   ```python
   try_import_mything_routes()
   ```

4. **Include block in `include_optional_routers()`** (next to the topic block):

   ```python
   if MYTHING_ROUTES_AVAILABLE:
       mything_routes = _imported_modules.get('mything_routes')
       if mything_routes:
           app.include_router(mything_routes.router)
           routers_included += 1
   ```

For an **always-on core** route instead, register it in
`try_import_core_routes()` + `include_core_routers()` (no flag/optional block) —
follow `news_routes`/`sentiment_routes` there.

## Verify

`py_compile` catches syntax/indent slips in the big `app.py`:

```bash
cd /home/Ikey/NeuroNews
python3 -m py_compile src/api/app.py src/api/routes/<name>_routes.py
```

Then exercise the handler. **Do not import `src.api.app` or
`src.api.routes` to test a single route** — `src/api/routes/__init__.py`
eagerly imports every route module, one of which drags in the heavy ML stack
(transformers/torch) that stalls on a network fetch in this container (the full
app boot can hang 60s+). Load your route file **by path** and mount it on a
throwaway app — this runs in ~5s:

```bash
PYTHONPATH=/home/Ikey/NeuroNews python3 - <<'PY'
import importlib.util
from pathlib import Path
from fastapi import FastAPI
from fastapi.testclient import TestClient

p = Path("/home/Ikey/NeuroNews/src/api/routes/scaffold_demo_routes.py")  # your file
spec = importlib.util.spec_from_file_location("r", p)
mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
app = FastAPI(); app.include_router(mod.router)
r = TestClient(app).get("/api/v1/scaffold_demo/ping", params={"name": "NeuroNews"})
print(r.status_code, r.json())
PY
```

Verified output for the demo route used to build this skill:
`200 {'message': 'hello, NeuroNews', 'wired': True}`.

To smoke the **whole** server with your route live (when the ML imports
cooperate), use the run-api driver, which launches in dev mode on its own DB:

```bash
src/api/.claude/skills/run-api/smoke.sh
curl -s "http://localhost:8012/api/v1/<name>/ping"   # while it's up, or add to ENDPOINTS
```

## Gotchas

- **`src/api/routes/__init__.py` imports every route module eagerly.** Importing
  *any* route through the package (`from src.api.routes import x`) pulls the
  whole stack, including a module that imports transformers → a network-gated
  ML import that can hang the process for a minute or stall indefinitely. For
  unit-testing one route, load the file by path (above), not via the package.
- **`ImportError` in a route module silently disables the endpoint.** The
  `try_import_*` swallows `ImportError`, so a bad import in your route file
  means the route just never registers (no crash, no 404-with-reason — it's
  simply absent). If your endpoint 404s, check the import actually succeeded.
- **The WAF 403s new data endpoints unless `NEURONEWS_DEV_MODE=true`** — same as
  every other route (see the `run-api` skill). Test with dev mode on.
- **`routers_included += 1`** — keep this line in your include block; the app
  logs the count and it's the quick sanity signal that registration ran.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Endpoint 404s after wiring | Either the `app.py` include block / `check_all_imports()` call is missing, or your route module raised `ImportError` (silently disabling it). Load the file by path (Verify) to surface the real import error. |
| `python3 -m py_compile src/api/app.py` errors | Indentation/syntax in your edit. The four edits are plain — re-copy from the `topic_routes` blocks. |
| Full server hangs on boot (no `/health`) | The ML import stall, not your route. Verify the route in isolation by path; retry the server later or with the deps installed. |
