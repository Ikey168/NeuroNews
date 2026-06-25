"""
NeuroNews Pipeline-stage runner — MCP server.

A thin developer tool that exposes each ETL pipeline boundary as a typed tool so
you can run a single stage against a fixture/source and inspect a SUMMARY or
DIFF — never the full payload. It drives the project's own pipeline code
(`src.ingestion.scrapy_integration`) and the local docker-compose stack
(DuckDB warehouse, Postgres/pgvector, S3/MinIO).

Tools:
  list_sources(category?)              -> the configured RSS connectors (DEFAULT_FEEDS)
  run_connector(source, sample=5)      -> fetch+parse one source, summary only (no write)
  run_stage(stage, input_ref?, ...)    -> run one named stage: fetch | sentiment | store | ingest
  trace_article(id)                    -> where an article exists across warehouse / vector / s3

Design constraints (learned the hard way in this repo):
  * Lazy imports inside tools. The top of this module imports only stdlib +
    fastmcp so the server starts instantly and never triggers the repo's heavy
    ML import graph (transformers/torch), which can hang on import.
  * The DuckDB warehouse is SINGLE-WRITER. We open it READ-ONLY for inspection
    so we don't fight the API server's writer lock, and report the lock cleanly
    instead of crashing. Writes (store/ingest) require apply=True and a free
    warehouse.
  * Postgres/S3 checks are best-effort with short timeouts; an unreachable
    backend yields a status string, not a hang or traceback.
"""

from __future__ import annotations

import os
import sys
import socket
from pathlib import Path
from typing import Any, Optional

from fastmcp import FastMCP

# Make the repo importable (server lives at <repo>/tools/pipeline_mcp/server.py).
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

mcp = FastMCP("neuronews-pipeline")

# Caps so we always return summaries, not payloads.
MAX_LIST = 25
CONTENT_PREVIEW = 200


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _pipeline():
    """Lazy-import the (light) ingestion pipeline module."""
    from src.ingestion import scrapy_integration as si
    return si


def _db_path() -> str:
    return os.getenv("NEURONEWS_DB_PATH", str(REPO_ROOT / "data" / "neuronews.duckdb"))


def _warehouse_ro():
    """Open the DuckDB warehouse READ-ONLY. Raises with a clear message if the
    file is missing or locked by another (writer) process."""
    import duckdb

    path = _db_path()
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"warehouse not found at {path} — start the API once to seed it, "
            f"or set NEURONEWS_DB_PATH"
        )
    try:
        return duckdb.connect(path, read_only=True)
    except Exception as exc:  # IOException when a writer holds the lock
        raise RuntimeError(
            f"warehouse at {path} is not readable (likely locked by a running "
            f"API/ingester — DuckDB is single-writer): {exc}"
        ) from exc


def _find_feed(si, source: str):
    """Resolve a source by exact or case-insensitive name; return Feed or None."""
    for f in si.DEFAULT_FEEDS:
        if f.name == source:
            return f
    low = source.strip().lower()
    for f in si.DEFAULT_FEEDS:
        if f.name.lower() == low:
            return f
    return None


def _sentiment_distribution(articles) -> dict:
    dist = {"positive": 0, "neutral": 0, "negative": 0}
    for a in articles:
        dist[a.sentiment_label] = dist.get(a.sentiment_label, 0) + 1
    return dist


def _port_open(host: str, port: int, timeout: float = 1.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


# --------------------------------------------------------------------------- #
# Tools
# --------------------------------------------------------------------------- #

@mcp.tool
def list_sources(category: Optional[str] = None) -> dict:
    """List the configured news connectors (RSS/Atom feeds in DEFAULT_FEEDS).

    Args:
        category: optional filter, e.g. "Technology", "Economy", "World".

    Returns a summary: total count, the categories present, and the feeds
    (name, url, category).
    """
    si = _pipeline()
    feeds = list(si.DEFAULT_FEEDS)
    if category:
        feeds = [f for f in feeds if f.category.lower() == category.lower()]
    return {
        "count": len(feeds),
        "categories": sorted({f.category for f in si.DEFAULT_FEEDS}),
        "sources": [{"name": f.name, "url": f.url, "category": f.category} for f in feeds],
    }


@mcp.tool
def run_connector(source: str, sample: int = 5) -> dict:
    """Run a single connector: fetch + parse up to `sample` articles from one
    source's live feed and return a SUMMARY only (no warehouse write).

    Args:
        source: a source name from list_sources (e.g. "BBC Technology").
        sample: max articles to parse (1-25).

    Returns counts, category, date range, sentiment distribution and a few
    sample titles. Network-dependent — reports a clear error if the feed can't
    be fetched.
    """
    si = _pipeline()
    feed = _find_feed(si, source)
    if feed is None:
        return {"error": f"unknown source {source!r}", "hint": "call list_sources()"}

    sample = max(1, min(int(sample), 25))
    try:
        raw = si._http_get(feed.url)
        articles = si.parse_feed(raw, feed, limit=sample)
    except Exception as exc:
        return {"error": f"fetch/parse failed for {feed.name}: {exc}", "url": feed.url}

    dates = sorted(a.publish_date for a in articles) if articles else []
    return {
        "source": feed.name,
        "category": feed.category,
        "url": feed.url,
        "fetched": len(articles),
        "date_range": (
            {"earliest": dates[0].isoformat(), "latest": dates[-1].isoformat()}
            if dates else None
        ),
        "sentiment": _sentiment_distribution(articles),
        "sample_titles": [a.title for a in articles[:MAX_LIST]],
    }


@mcp.tool
def run_stage(
    stage: str,
    input_ref: Optional[str] = None,
    sample: int = 5,
    apply: bool = False,
) -> dict:
    """Run a single pipeline stage against a fixture/source and return a
    summary or diff.

    Stages:
      fetch     input_ref = source name. Fetch+parse, return article refs
                (id, title, sentiment) — no write.
      sentiment input_ref = raw text, OR an article id present in the warehouse.
                Returns {score, label}.
      store     input_ref = source name. Fetch that source, then DIFF against
                the warehouse: which ids are new vs already present. Read-only
                by default; pass apply=true to actually insert (requires the
                warehouse to be free — DuckDB single-writer).
      ingest    input_ref = source name (or omit for all sources). Full
                fetch->store. Read-only diff unless apply=true.

    Args:
        stage: one of fetch | sentiment | store | ingest.
        input_ref: source name, text, or article id depending on the stage.
        sample: max articles per feed for fetch/store/ingest (1-25).
        apply: actually write to the warehouse (store/ingest only).
    """
    si = _pipeline()
    stage = stage.strip().lower()
    sample = max(1, min(int(sample), 25))

    if stage == "fetch":
        if not input_ref:
            return {"error": "fetch needs input_ref = a source name"}
        feed = _find_feed(si, input_ref)
        if feed is None:
            return {"error": f"unknown source {input_ref!r}", "hint": "call list_sources()"}
        try:
            raw = si._http_get(feed.url)
            articles = si.parse_feed(raw, feed, limit=sample)
        except Exception as exc:
            return {"error": f"fetch failed for {feed.name}: {exc}"}
        return {
            "stage": "fetch",
            "source": feed.name,
            "fetched": len(articles),
            "articles": [
                {"id": a.id, "title": a.title, "sentiment": a.sentiment_label}
                for a in articles[:MAX_LIST]
            ],
        }

    if stage == "sentiment":
        if not input_ref:
            return {"error": "sentiment needs input_ref = text or an article id"}
        text = input_ref
        resolved_from = "text"
        # If it looks like an id rather than a sentence, try the warehouse.
        if " " not in input_ref.strip():
            try:
                con = _warehouse_ro()
                row = con.execute(
                    "SELECT title, content FROM news_articles WHERE id = ?", [input_ref]
                ).fetchone()
                con.close()
                if row:
                    text = f"{row[0]}. {row[1] or ''}"
                    resolved_from = "article_id"
            except Exception:
                pass  # fall back to treating input_ref as literal text
        score, label = si.score_sentiment(text)
        return {
            "stage": "sentiment",
            "resolved_from": resolved_from,
            "score": score,
            "label": label,
            "scored_chars": len(text),
        }

    if stage in ("store", "ingest"):
        feeds = None
        if input_ref and input_ref.lower() != "all":
            feed = _find_feed(si, input_ref)
            if feed is None:
                return {"error": f"unknown source {input_ref!r}", "hint": "call list_sources()"}
            feeds = [feed]
        try:
            articles = si.fetch_articles(feeds, limit_per_feed=sample)
        except Exception as exc:
            return {"error": f"fetch failed: {exc}"}

        # Read-only diff against the warehouse.
        existing: set[str] = set()
        warehouse_status = "ok"
        try:
            con = _warehouse_ro()
            ids = [a.id for a in articles]
            if ids:
                placeholders = ",".join("?" for _ in ids)
                rows = con.execute(
                    f"SELECT id FROM news_articles WHERE id IN ({placeholders})", ids
                ).fetchall()
                existing = {r[0] for r in rows}
            con.close()
        except Exception as exc:
            warehouse_status = str(exc)

        new = [a for a in articles if a.id not in existing]
        result = {
            "stage": stage,
            "source": input_ref or "all",
            "fetched": len(articles),
            "would_insert": len(new),
            "already_present": len(existing),
            "warehouse": warehouse_status,
            "applied": False,
            "sample_new_titles": [a.title for a in new[:MAX_LIST]],
        }
        if apply:
            try:
                inserted = si.store_articles(articles, replace=False)
                result["applied"] = True
                result["inserted"] = inserted
            except Exception as exc:
                result["apply_error"] = (
                    f"{exc} (warehouse likely locked by a running API/ingester; "
                    f"stop it or set NEURONEWS_DB_PATH to a free file)"
                )
        return result

    return {
        "error": f"unknown stage {stage!r}",
        "valid_stages": ["fetch", "sentiment", "store", "ingest"],
    }


@mcp.tool
def trace_article(id: str) -> dict:
    """Trace an article id across the pipeline's stores: the DuckDB warehouse,
    the Postgres/pgvector store, and S3/MinIO. Returns a presence summary and a
    truncated warehouse row — never the full content.

    Args:
        id: the article id (warehouse ids are a url hash; seed ids look like
            "art-0001"). Use run_stage("fetch", ...) to discover ids.
    """
    trace: dict[str, Any] = {"id": id, "warehouse": {}, "vector_store": {}, "object_store": {}}

    # 1) DuckDB warehouse (read-only).
    try:
        con = _warehouse_ro()
        row = con.execute(
            "SELECT title, url, source, category, publish_date, sentiment_score, "
            "sentiment_label, content FROM news_articles WHERE id = ?",
            [id],
        ).fetchone()
        con.close()
        if row:
            content = row[7] or ""
            trace["warehouse"] = {
                "present": True,
                "title": row[0],
                "url": row[1],
                "source": row[2],
                "category": row[3],
                "publish_date": row[4].isoformat() if row[4] else None,
                "sentiment": {"score": row[5], "label": row[6]},
                "content_length": len(content),
                "content_preview": content[:CONTENT_PREVIEW],
            }
        else:
            trace["warehouse"] = {"present": False}
    except Exception as exc:
        trace["warehouse"] = {"status": str(exc)}

    # 2) Postgres / pgvector (best-effort, short timeout).
    pg_host = os.getenv("PGVECTOR_HOST", "localhost")
    pg_port = int(os.getenv("PGVECTOR_PORT", "5433"))
    if not _port_open(pg_host, pg_port):
        trace["vector_store"] = {"reachable": False, "endpoint": f"{pg_host}:{pg_port}"}
    else:
        try:
            import psycopg2

            dsn = os.getenv(
                "PGVECTOR_DSN",
                f"postgresql://neuronews:neuronews_vector_pass@{pg_host}:{pg_port}/neuronews_vector",
            )
            conn = psycopg2.connect(dsn, connect_timeout=2)
            cur = conn.cursor()
            # Find any table with an 'id'-like column; report presence generically.
            cur.execute(
                "SELECT table_name FROM information_schema.columns "
                "WHERE column_name IN ('id','article_id','doc_id') "
                "AND table_schema='public' LIMIT 5"
            )
            tables = [r[0] for r in cur.fetchall()]
            hits = []
            for t in tables:
                for col in ("id", "article_id", "doc_id"):
                    try:
                        cur.execute(
                            f"SELECT 1 FROM {t} WHERE {col} = %s LIMIT 1", (id,)
                        )
                        if cur.fetchone():
                            hits.append(f"{t}.{col}")
                    except Exception:
                        conn.rollback()
            cur.close()
            conn.close()
            trace["vector_store"] = {
                "reachable": True,
                "endpoint": f"{pg_host}:{pg_port}",
                "candidate_tables": tables,
                "found_in": hits,
            }
        except Exception as exc:
            trace["vector_store"] = {"reachable": True, "error": str(exc)}

    # 3) S3 / MinIO (reachability only — don't hang on a full object scan).
    s3_endpoint = os.getenv("S3_ENDPOINT_URL") or os.getenv("AWS_ENDPOINT_URL")
    if s3_endpoint:
        host = s3_endpoint.split("://", 1)[-1].split("/", 1)[0]
        h, _, p = host.partition(":")
        port = int(p) if p else (443 if s3_endpoint.startswith("https") else 80)
        trace["object_store"] = {"endpoint": s3_endpoint, "reachable": _port_open(h, port)}
    else:
        trace["object_store"] = {"status": "no S3_ENDPOINT_URL configured"}

    return trace


if __name__ == "__main__":
    mcp.run()  # stdio transport by default
