"""
NeuroNews Pipeline-stage runner — MCP server.

A thin developer tool that exposes each ETL pipeline boundary as a typed tool so
you can run a single stage against a fixture/source and inspect a SUMMARY or
DIFF — never the full payload. It drives the project's own pipeline code
(`src.ingestion.scrapy_integration`) and the local docker-compose stack
(DuckDB warehouse, Postgres/pgvector, S3/MinIO).

Tools:
  list_sources(category?)              -> the configured RSS connectors (DEFAULT_FEEDS)
  list_connector_types()               -> all registered document connector source types
  run_connector(source, sample=5,      -> fetch+parse one source, summary only (no write).
                query?)                   source = RSS feed name OR a source_type from
                                          list_connector_types(); query = JSON list of paths/
                                          IDs passed to that connector's discover().
  run_stage(stage, input_ref?, ...)    -> run one named stage: fetch|sentiment|store|ingest|positions
  trace_article(id)                    -> where an article exists across warehouse / vector / s3
  query_positions(actor?, topic?, ...) -> query policy_positions table for actor commitments (#110)

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


def _warehouse_rw():
    """Open the DuckDB warehouse READ-WRITE. Use only for write-stage tools."""
    import duckdb

    path = _db_path()
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"warehouse not found at {path} — start the API once to seed it, "
            f"or set NEURONEWS_DB_PATH"
        )
    try:
        return duckdb.connect(path, read_only=False)
    except Exception as exc:
        raise RuntimeError(
            f"warehouse at {path} is locked (DuckDB single-writer): {exc}"
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
def list_connector_types() -> dict:
    """List all registered document connector source types.

    Returns the source types that have a connector registered in the connector
    registry (e.g. "news", "paper", "book", "transcript"). Each type can be
    passed as the ``source`` argument to ``run_connector``.
    """
    import src.ingestion.connectors  # noqa: F401 — triggers @register_connector for all built-ins
    from src.ingestion.connectors.registry import available_source_types
    types = available_source_types()
    return {
        "count": len(types),
        "source_types": types,
        "usage": (
            "Pass a source_type as `source` to run_connector(), "
            "and supply `query` as a JSON list of paths/IDs for that connector "
            "(e.g. query='[\"/books/foo.epub\"]' for book, "
            "query='[\"2312.00752\"]' for paper arXiv IDs, "
            "query='[\"/podcasts/ep.mp3\"]' for transcript). "
            "For `news`, omit query to use the default RSS feeds."
        ),
    }


@mcp.tool
def run_connector(source: str, sample: int = 5, query: Optional[str] = None) -> dict:
    """Run a single connector: fetch + parse up to `sample` records from one
    source and return a SUMMARY only (no warehouse write).

    Two dispatch modes, selected automatically:

    1. **RSS feed** (legacy): ``source`` is a feed name from ``list_sources``
       (e.g. ``"BBC Technology"``). ``query`` is ignored.

    2. **Document connector**: ``source`` is a source type from
       ``list_connector_types`` (e.g. ``"book"``, ``"paper"``, ``"transcript"``).
       ``query`` is a JSON list of paths or IDs to pass to ``discover()``.
       Examples::

         run_connector("book",       query='["/books/foo.epub"]')
         run_connector("paper",      query='["2312.00752", "1706.03762"]')
         run_connector("transcript", query='["/pods/ep42.mp3"]')
         run_connector("news")       # uses DEFAULT_FEEDS, no query needed

    Args:
        source: RSS feed name OR a source_type from list_connector_types.
        sample: max records to harvest (1-25).
        query:  JSON list of paths/IDs for document connectors (ignored for RSS).

    Returns a summary: source type, record count, and sample titles/snippets.
    """
    sample = max(1, min(int(sample), 25))

    # --- Try document connector registry first ----------------------------- #
    import src.ingestion.connectors as _conn_pkg  # noqa: F401 — trigger registrations
    from src.ingestion.connectors.registry import available_source_types, get_connector, is_registered

    if is_registered(source):
        return _run_document_connector(source, sample, query, get_connector)

    # --- Fall back to legacy RSS path -------------------------------------- #
    si = _pipeline()
    feed = _find_feed(si, source)
    if feed is None:
        types = available_source_types()
        return {
            "error": f"unknown source {source!r}",
            "hint": (
                f"For RSS feeds call list_sources(). "
                f"For document connectors use one of: {types}"
            ),
        }

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


def _run_document_connector(
    source_type: str,
    sample: int,
    query_json: Optional[str],
    get_connector,
) -> dict:
    """Harvest up to ``sample`` Documents from a registry connector and return a summary."""
    import json as _json

    query = None
    if query_json:
        try:
            query = _json.loads(query_json)
        except _json.JSONDecodeError as exc:
            return {"error": f"query must be a JSON list: {exc}", "example": '["path/to/file"]'}

    try:
        connector = get_connector(source_type)
    except KeyError as exc:
        return {"error": str(exc)}

    docs = []
    errors = []
    for ref in list(connector.discover(query))[:sample]:
        try:
            raw = connector.fetch(ref)
            parsed = connector.parse(raw)
            docs.extend(parsed)
        except Exception as exc:
            errors.append({"locator": ref.locator, "error": str(exc)})
        if len(docs) >= sample:
            break

    docs = docs[:sample]
    sample_snippets = []
    for d in docs[:MAX_LIST]:
        snippet = {
            "document_id": d.document_id,
            "title": d.title,
            "language": d.language,
        }
        # Include a few type-specific metadata highlights.
        for key in ("section_path", "start_s", "end_s", "speaker", "arxiv_id", "doi"):
            if key in (d.metadata or {}):
                snippet[key] = d.metadata[key]
        if d.content:
            snippet["content_preview"] = d.content[:CONTENT_PREVIEW]
        sample_snippets.append(snippet)

    result: dict = {
        "source_type": source_type,
        "connector": type(connector).__name__,
        "query": query,
        "harvested": len(docs),
        "documents": sample_snippets,
    }
    if errors:
        result["errors"] = errors
    return result


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
      positions input_ref = article/document id already in the warehouse.
                Runs position extraction and writes results to policy_positions.
                Use query_positions() to read them back.

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

    if stage == "positions":
        if not input_ref:
            return {"error": "positions needs input_ref = an article/document id"}
        try:
            con_rw = _warehouse_rw()
        except Exception as exc:
            return {"error": f"warehouse unavailable: {exc}"}
        try:
            row = con_rw.execute(
                "SELECT id, title, content, publish_date, source, category "
                "FROM news_articles WHERE id = ? LIMIT 1",
                [input_ref],
            ).fetchone()
        except Exception as exc:
            con_rw.close()
            return {"error": f"document lookup failed: {exc}"}
        if not row:
            con_rw.close()
            return {"error": f"document {input_ref!r} not found in warehouse"}
        doc_id, title, content, publish_date, source, category = row
        if not content:
            con_rw.close()
            return {"error": "document has no content"}
        try:
            import time as _time
            from services.ingest.common.document_model import Document
            from src.argument_mining.positions import run_position_pipeline
            meta: dict[str, Any] = {}
            if category:
                meta["category"] = category
            created_ms: Optional[int] = None
            if publish_date is not None:
                try:
                    created_ms = int(publish_date.timestamp() * 1000)
                except Exception:
                    pass
            doc = Document(
                document_id=doc_id,
                source_type="news",
                language="en",
                ingested_at=int(_time.time() * 1000),
                source_id=source,
                title=title,
                content=content,
                created_at=created_ms,
                metadata=meta,
            )
            records = run_position_pipeline(doc, con_rw)
            con_rw.close()
        except Exception as exc:
            con_rw.close()
            return {"error": f"position extraction failed: {exc}"}
        return {
            "stage": "positions",
            "document_id": doc_id,
            "positions_extracted": len(records),
            "positions": [
                {
                    "actor": r.actor,
                    "topic": r.topic,
                    "confidence": round(r.confidence, 4),
                    "text_preview": r.position_text[:CONTENT_PREVIEW],
                }
                for r in records[:MAX_LIST]
            ],
        }

    return {
        "error": f"unknown stage {stage!r}",
        "valid_stages": ["fetch", "sentiment", "store", "ingest", "positions"],
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


@mcp.tool
def query_positions(
    actor: Optional[str] = None,
    topic: Optional[str] = None,
    source_type: Optional[str] = None,
    limit: int = 10,
) -> dict:
    """Query the ``policy_positions`` table for actor policy commitments (#110).

    Returns compact position summaries — never full content payloads.
    Use ``run_stage("positions", input_ref=<id>)`` to first populate the table
    for a specific document.

    Args:
        actor:       ILIKE filter on the actor name (e.g. "government", "Johnson").
        topic:       ILIKE filter on topic (e.g. "economy", "healthcare", "law").
        source_type: Exact filter on source type (news/blog/paper/transcript/book/note).
        limit:       Max rows to return (capped at 25).
    """
    limit = max(1, min(int(limit), MAX_LIST))
    try:
        con = _warehouse_ro()
    except Exception as exc:
        return {"error": f"warehouse unavailable: {exc}"}

    where_parts: list[str] = []
    params: list[Any] = []
    if actor:
        where_parts.append("actor ILIKE ?")
        params.append(f"%{actor}%")
    if topic:
        where_parts.append("topic ILIKE ?")
        params.append(f"%{topic}%")
    if source_type:
        where_parts.append("source_type = ?")
        params.append(source_type)
    where_clause = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""
    params.append(limit)

    try:
        rows = con.execute(
            f"""
            SELECT position_id, actor, topic, source_type, document_id,
                   position_date, confidence,
                   LEFT(position_text, {CONTENT_PREVIEW}) AS preview
            FROM policy_positions
            {where_clause}
            ORDER BY position_date DESC NULLS LAST, confidence DESC
            LIMIT ?
            """,
            params,
        ).fetchall()
        con.close()
    except Exception as exc:
        con.close()
        return {"error": f"query failed: {exc}", "hint": "table may not exist yet — run ensure_schema"}

    return {
        "filters": {k: v for k, v in {"actor": actor, "topic": topic, "source_type": source_type}.items() if v},
        "count": len(rows),
        "positions": [
            {
                "position_id": r[0],
                "actor": r[1],
                "topic": r[2],
                "source_type": r[3],
                "document_id": r[4],
                "date": r[5] or "",
                "confidence": round(float(r[6] or 0), 4),
                "text_preview": r[7],
            }
            for r in rows
        ],
    }


if __name__ == "__main__":
    mcp.run()  # stdio transport by default
