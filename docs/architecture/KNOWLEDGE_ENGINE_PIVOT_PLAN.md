# Pivot Plan: From News Analytics to a General Knowledge Extraction Engine

**Status:** Proposed
**Owner:** TBD
**Date:** 2026-06-21
**Decisions locked in:**

- First new source type built end-to-end: **Academic papers** (arXiv / PubMed / PDF).
- Existing news features are **kept as an optional "domain pack"**, not deleted.
- Migration is **incremental and additive** — the existing news pipeline stays green throughout.

---

## 1. Vision

NeuroNews becomes a **knowledge extraction engine for arbitrary text media** — news sites,
blogs, books, papers, transcripts, and uploaded documents. The product output shifts from
"news dashboards" to a **queryable, cited, cross-source knowledge base**: entities, relations,
and claims extracted from any document, retrievable via RAG and explorable as a knowledge graph.

News analytics (sentiment, fake-news, events, influence networks) is preserved as one
**pluggable domain pack** that runs only for `source_type = news`.

---

## 2. What already transfers (no change required)

These components are already domain-agnostic and form the core of the new engine:

| Capability | Location | Role in new engine |
| --- | --- | --- |
| RAG (chunk/retrieve/rerank/diversify/answer) | `services/rag/` | Core Q&A over any corpus |
| Vector search | Qdrant + pgvector, `services/vector_service.py` | Core semantic retrieval |
| Embeddings | `src/nlp/article_embedder.py`, `services/embeddings/` | Core indexing |
| Entity **and relation** extraction | `src/knowledge_graph/enhanced_entity_extractor.py` (`extract_entities_from_article`, `extract_relationships`) | Core KG construction |
| Knowledge graph build/query/search | `src/knowledge_graph/{graph_builder,graph_query_engine,graph_search_service,semantic_analyzer}.py` | Core knowledge base |
| NER / keywords / topics / summarization / multilingual | `src/nlp/` | Generic enrichers |
| Orchestration / MLOps / contracts / FinOps | `airflow/`, `src/ml/mlops/`, `contracts/`, `deploy/kubernetes/finops/` | Reusable as-is |

**Implication:** the pivot is mostly a *data-model generalization* plus *new ingestion connectors*,
not a rewrite of the analytical core.

---

## 3. Keystone: `Article` → `Document`

All news-specificity traces back to the ingest contract
(`contracts/schemas/jsonschema/article-ingest-v1.json`), which assumes a published news article:
`url`, `source_id` (publisher), `published_at`, and `country` are effectively required and
`sentiment_score`/`topics` are inlined.

### 3.1 New core contract: `document-ingest-v1`

Introduce `contracts/schemas/jsonschema/document-ingest-v1.json` (and matching Avro
`contracts/schemas/avro/document-ingest-v1.avsc`) alongside the existing article contract.

Core fields:

```jsonc
{
  "document_id": "string (required)",
  "source_type": "enum: news | blog | book | paper | transcript | web | note (required)",
  "title": "string|null",
  "content": "string|null",            // inline body, OR
  "content_ref": "string|null",        // pointer to object storage for large docs (books/PDFs)
  "language": "string (ISO 639-1)",
  "ingested_at": "date-time (required)",
  "created_at": "date-time|null",      // generalizes published_at; optional
  "authors": ["string"],               // optional
  "source_id": "string|null",          // publisher/repository; optional
  "url": "string|null",                // optional (books/uploads have none)
  "metadata": { }                      // type-specific bag (see below)
}
```

`metadata` examples by `source_type`:

- **paper**: `doi`, `arxiv_id`, `pubmed_id`, `journal`, `venue`, `references[]`, `sections[]`, `cited_by_count`
- **book**: `isbn`, `publisher`, `edition`, `toc[]`, `chapter`, `page_range`
- **transcript**: `media_url`, `duration_s`, `speakers[]`, `timestamps[]`
- **news**: `country`, `section`, `byline` (the old fields move here)

### 3.2 Enrichments move out of the core record

`sentiment_score` and `topics` leave the ingest record and become rows in an **enrichment
layer** (one analyzer among many), keyed by `document_id`. This is what makes news analytics
"just a domain pack."

### 3.3 Backward compatibility

- Keep `article-ingest-v1` valid. Add an **adapter** that maps an `ArticleIngest` to a
  `Document` (`source_type = news`, news fields → `metadata`).
- Existing DAGs/tables continue to work via the adapter; no big-bang migration.
- DB: add a `documents` table (or generalize the existing articles table with a
  `source_type` column + JSON `metadata`). Provide a view `articles` for legacy queries.

---

## 4. Ingestion connector framework

Today ingestion is HTML/Scrapy-centric (`src/ingestion/`, `src/scraper/`). Introduce a
**connector framework** so each media type plugs in behind a common interface.

```
src/ingestion/connectors/
  base.py            # Connector protocol: discover() -> fetch() -> parse() -> Document
  registry.py        # source_type -> connector
  paper/             # FIRST (this milestone)
    arxiv.py         # arXiv API: metadata, PDF, references
    pubmed.py        # PubMed/Crossref metadata
    pdf_parser.py    # PDF -> sections, figures/captions, references (GROBID or pdfplumber)
  book/              # later: EPUB/PDF, hierarchical TOC, OCR fallback
  blog/              # later: RSS/Atom + readability (reuse scraper)
  transcript/        # later: audio/video -> Whisper -> Document
  upload/            # later: generic PDF/md/docx/text upload
```

Common interface:

```python
class Connector(Protocol):
    source_type: str
    async def discover(self, query) -> list[Ref]: ...
    async def fetch(self, ref) -> RawDoc: ...
    async def parse(self, raw) -> Document: ...   # normalized Document contract
```

---

## 5. First milestone end-to-end: Academic papers

Chosen as the proof of the pivot — cleanest metadata, highest knowledge-engine value, and it
exercises the citation graph (a genuinely new capability).

Pipeline:

1. **Discover** via arXiv/PubMed/Crossref API by query, author, or ID.
2. **Fetch** PDF + structured metadata; store PDF in object storage, reference via `content_ref`.
3. **Parse** with GROBID (preferred) or `pdfplumber`/`pymupdf` fallback into:
   - section tree (abstract, intro, methods, …)
   - figure/table captions
   - **reference list** (parsed citations with DOIs where resolvable)
4. **Chunk** section-aware + hierarchical (see §6).
5. **Extract** entities + relations (reuse `enhanced_entity_extractor`) and **claims** (§7).
6. **Build KG**: paper node, author nodes, and **`CITES` edges** between papers → a citation
   graph. Concepts/entities link papers across the corpus.
7. **Index** chunks into the vector store for RAG.
8. **Expose** via API (§8) and a new web view (§9).

New API surface for this milestone: `POST /documents/ingest` (paper by id/url),
`GET /documents/{id}`, `GET /documents/{id}/citations`, RAG `ask` already works over the new chunks.

---

## 6. Structure-aware chunking

`services/rag/chunking.py` is currently flat (sentence/paragraph/word/char). Add a
**hierarchical, structure-aware** strategy:

- New `SplitStrategy.STRUCTURED` that consumes the parsed section/chapter tree.
- Each `TextChunk` carries `path` metadata (e.g., `["§4", "4.2 Methods"]` or
  `["Part II", "Chapter 5"]`) so retrieval can cite location.
- Keep existing strategies for flat sources (news/blogs) — fully backward compatible.

This materially improves long-document RAG for papers and books.

---

## 7. Relation + claim extraction (the differentiator)

Entities and relations already exist. Add a **claim extraction** pass:

- New module `src/knowledge_graph/claim_extractor.py`: extract atomic
  subject–predicate–object claims with **provenance** (`document_id` + chunk `path`).
- Store claims as KG nodes/edges so the graph answers cross-document questions
  ("what does the literature say about X") with citations.
- Reuse RAG to surface corroborating/contradicting evidence per claim (this also powers the
  existing news fact-checking idea as a special case).

---

## 8. API generalization

`src/api/routes/` is article/news-centric. Plan:

- Add `document_routes.py` (ingest, get, list by `source_type`, citations, enrichments).
- Keep `article_routes.py`, `news_routes.py`, `sentiment_*`, `veracity_*`, `event_*`,
  `influence_*` registered **only when the news domain pack is enabled** (feature flag).
- RAG/search/graph routes stay; they already operate on generic chunks/KG.

---

## 9. Domain-pack architecture (news kept, not deleted)

Introduce a lightweight pack registry:

```
src/domains/
  base.py        # DomainPack: enrichers, routes, UI feature flags
  news/          # wraps fake_news_detector, news sentiment, event_clusterer,
                 #   influence_network_analyzer, news timeline UI
```

- A pack registers **enrichers** (run per matching `source_type`), **routes**, and **UI flags**.
- Config (`config/`) selects active packs. Default ships `news` enabled so nothing regresses.
- Future packs: `research` (papers), `legal`, `finance`, etc.

This satisfies "keep news as an optional pack" with minimal disruption.

---

## 10. Web app reframing (`apps/web/`)

- `NewsFeed.tsx` → generic **Library / Sources** view with a `source_type` filter.
- `EntityGraphView.tsx` extended to render the **citation graph** for papers.
- Add a **Document reader** view (section tree + inline entity/claim highlights + "ask this doc").
- News-only views (`Sentiment`, `Timeline`, `Clusters`, `Trending`, `Watchlists`) gated behind
  the news domain-pack flag.
- Rebrand/rename is the **last** step, after the engine is generalized.

---

## 11. Phased rollout

| Phase | Scope | Exit criteria |
| --- | --- | --- |
| **0. Foundations** | `document-ingest-v1` contract + Avro; `Document` model; Article→Document adapter; `documents` table + legacy `articles` view | Existing news pipeline green via adapter; contract tests pass |
| **1. Connector framework** | `connectors/base.py` + `registry.py`; refactor existing HTML ingest behind it | News ingest runs through the new framework unchanged |
| **2. Papers E2E** | arXiv/PubMed connector, PDF parsing, citation graph, structured chunking, RAG over papers | Ingest a paper by id → ask a question → get cited answer; citation graph queryable |
| **3. Knowledge layer** | claim extractor + cross-document claim graph | Claims with provenance queryable in KG |
| **4. Domain packs** | extract news modules into `src/domains/news/`; feature flags; `document_routes` | News features run only when pack enabled; generic API works pack-off |
| **5. Web reframing** | Library view, document reader, citation graph UI, gate news views | Papers usable end-to-end in the UI |
| **6. Rebrand** | naming, docs, README | Identity reflects general knowledge engine |

Phases 0–2 deliver a working general engine with papers; 3–6 deepen and polish.

---

## 12. Testing & data quality

- Contract tests for `document-ingest-v1` mirroring existing `contracts/tests/` + valid/invalid examples.
- Connector unit tests with recorded fixtures (one real arXiv paper, one PubMed record).
- Golden-set RAG eval (`evals/`) extended with paper Q&A pairs.
- Adapter round-trip test: `ArticleIngest` ⇄ `Document` lossless for news fields.

---

## 13. Open questions / risks

- **PDF parsing dependency:** GROBID (Docker service, best quality) vs. pure-Python
  (`pymupdf`/`pdfplumber`, simpler deploy). Recommend GROBID with a Python fallback.
- **Storage of large docs:** books/PDFs use `content_ref` to S3-compatible storage rather than
  inlining `content` — keep the metadata store lean.
- **Entity resolution at scale:** cross-source dedup of the same person/concept becomes more
  important than in news-only; may warrant a dedicated entity-resolution pass in Phase 3.
- **Naming:** "NeuroNews" implies news; rebrand deferred to Phase 6 to avoid churn mid-pivot.

---

## 14. Recommended immediate next step

Begin **Phase 0** (the `Document` contract + Article adapter). It is purely additive, unblocks
every later phase, and carries zero risk to the existing news pipeline.
