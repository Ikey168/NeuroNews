-- Migration: 0005_document_model.sql
-- Description: Generalized document ingest model (M0 keystone of the knowledge-engine pivot)
-- Author: NeuroNews Team
-- Date: 2026-06-21
--
-- Introduces the generalized `document_ingest` landing table that supersedes the
-- news-specific article-ingest record, plus a separate `document_enrichments`
-- table (sentiment, topics, ... are now one analyzer among many, not intrinsic
-- to a document) and a backward-compatible view that reproduces the
-- article-ingest contract shape so the legacy news pipeline stays green.
--
-- This is purely additive. It does NOT touch the existing `documents` table from
-- 0002_schema_chunks.sql (the RAG chunk store), nor the dbt `articles` source.

-- Generalized raw document captured from any source (document-ingest-v1).
CREATE TABLE IF NOT EXISTS document_ingest (
    document_id    TEXT PRIMARY KEY,
    source_type    TEXT NOT NULL CHECK (
        source_type IN ('news', 'blog', 'book', 'paper', 'transcript', 'web', 'note')
    ),
    source_id      TEXT,
    url            TEXT,
    title          TEXT,
    content        TEXT,
    content_ref    TEXT,
    language       VARCHAR(8) NOT NULL,
    authors        JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at     TIMESTAMP WITH TIME ZONE,                  -- generalizes published_at; nullable
    ingested_at    TIMESTAMP WITH TIME ZONE NOT NULL,
    metadata       JSONB NOT NULL DEFAULT '{}'::jsonb,        -- source-type-specific bag
    row_created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_document_ingest_source_type ON document_ingest (source_type);
CREATE INDEX IF NOT EXISTS idx_document_ingest_ingested_at ON document_ingest (ingested_at);
CREATE INDEX IF NOT EXISTS idx_document_ingest_created_at ON document_ingest (created_at);
CREATE INDEX IF NOT EXISTS idx_document_ingest_metadata ON document_ingest USING GIN (metadata);

-- Enrichment layer: downstream analyzer outputs, kept separate from the core record.
-- One row per (document, enrichment_type), e.g. ('sentiment', {"score": 0.75}),
-- ('topics', ["technology", "ai"]).
CREATE TABLE IF NOT EXISTS document_enrichments (
    document_id     TEXT NOT NULL REFERENCES document_ingest (document_id) ON DELETE CASCADE,
    enrichment_type TEXT NOT NULL,
    value           JSONB NOT NULL,
    model           TEXT,
    created_at      TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (document_id, enrichment_type)
);

-- Backward-compatible view reproducing the article-ingest-v1 record shape from the
-- generalized store (news documents only). Sentiment/topics are re-joined from the
-- enrichment layer so existing consumers of the article shape keep working.
CREATE OR REPLACE VIEW v_article_ingest AS
SELECT
    d.document_id                                   AS article_id,
    d.source_id,
    d.url,
    d.title,
    d.content                                       AS body,
    d.language,
    d.metadata ->> 'country'                        AS country,
    d.created_at                                    AS published_at,
    d.ingested_at,
    (se.value ->> 'score')::double precision        AS sentiment_score,
    COALESCE(te.value, '[]'::jsonb)                 AS topics
FROM document_ingest d
LEFT JOIN document_enrichments se
    ON se.document_id = d.document_id AND se.enrichment_type = 'sentiment'
LEFT JOIN document_enrichments te
    ON te.document_id = d.document_id AND te.enrichment_type = 'topics'
WHERE d.source_type = 'news';

COMMENT ON TABLE document_ingest IS 'Generalized raw document landing table (document-ingest-v1); supersedes the news-only article-ingest record.';
COMMENT ON TABLE document_enrichments IS 'Downstream analyzer outputs (sentiment, topics, ...) kept separate from the core document record.';
COMMENT ON VIEW v_article_ingest IS 'Backward-compatible article-ingest-v1 shape over the generalized document store (news only).';
