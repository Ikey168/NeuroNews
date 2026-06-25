import { useState } from "react";
import { ACCENT, palette, fonts, accentSoft, accentBorder } from "../theme";
import { useDocuments } from "../lib/queries";
import PageHeader from "../components/PageHeader";
import SourceBadge from "../components/SourceBadge";
import Hover from "../components/Hover";
import type { KnowledgeDocument, SourceType } from "../types";

const TYPE_COLOR: Record<SourceType, string> = {
  news: ACCENT,
  blog: palette.teal,
  paper: palette.blue,
  book: palette.violet,
  transcript: palette.pos,
  web: palette.dim,
  note: palette.amber,
};

// Very lightweight entity extraction — highlight words that look like proper
// nouns or match a simple heuristic. Real extraction comes from the KG API.
function highlightEntities(text: string, entities: string[]): React.ReactNode[] {
  if (!entities.length) return [text];
  const pattern = new RegExp(`(${entities.map((e) => e.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|")})`, "gi");
  const parts = text.split(pattern);
  return parts.map((p, i) =>
    entities.some((e) => e.toLowerCase() === p.toLowerCase()) ? (
      <mark
        key={i}
        style={{
          background: `${palette.amber}30`,
          color: palette.amber,
          borderRadius: 3,
          padding: "0 2px",
          fontWeight: 500,
        }}
      >
        {p}
      </mark>
    ) : (
      p
    ),
  );
}

// Simple entity extraction: title-case words of 3+ chars that aren't common.
const STOP = new Set([
  "the", "and", "for", "with", "that", "this", "from", "are", "was", "were",
  "has", "have", "had", "its", "their", "they", "into", "been", "also",
]);

function extractEntities(doc: KnowledgeDocument): string[] {
  const text = `${doc.title ?? ""} ${doc.content ?? ""}`;
  const words = text.match(/\b[A-Z][a-zA-Z]{2,}\b/g) ?? [];
  const counts: Record<string, number> = {};
  for (const w of words) {
    const k = w.toLowerCase();
    if (!STOP.has(k)) counts[w] = (counts[w] ?? 0) + 1;
  }
  return Object.entries(counts)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 12)
    .map(([e]) => e);
}

function AskDocPanel({ doc }: { doc: KnowledgeDocument }) {
  const [query, setQuery] = useState("");
  const [answer, setAnswer] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleAsk = async () => {
    if (!query.trim()) return;
    setLoading(true);
    setAnswer(null);
    // Placeholder: in production this calls the RAG endpoint with doc context.
    await new Promise((r) => setTimeout(r, 600));
    setAnswer(
      `[Demo] Based on the document "${doc.title ?? "Untitled"}", the answer to "${query}" would be retrieved via the RAG pipeline using the document's content as context.`,
    );
    setLoading(false);
  };

  return (
    <div
      style={{
        background: "#11151c",
        border: "1px solid #1c2330",
        borderRadius: 10,
        padding: "14px 16px",
        display: "flex",
        flexDirection: "column",
        gap: 10,
      }}
    >
      <div style={{ fontFamily: fonts.mono, fontSize: 10, color: "#8a94a6", letterSpacing: "0.12em" }}>
        ASK THIS DOCUMENT
      </div>
      <div style={{ display: "flex", gap: 8 }}>
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleAsk()}
          placeholder="What does this document say about…"
          style={{
            flex: 1,
            background: "#10151d",
            border: "1px solid #232a36",
            borderRadius: 7,
            padding: "8px 12px",
            color: "#e6eaf0",
            fontFamily: fonts.sans,
            fontSize: 13,
            outline: "none",
          }}
        />
        <Hover
          as="button"
          onClick={handleAsk}
          style={{
            background: accentSoft(ACCENT),
            border: `1px solid ${accentBorder(ACCENT)}`,
            color: ACCENT,
            borderRadius: 7,
            padding: "8px 16px",
            fontFamily: fonts.mono,
            fontSize: 11,
            cursor: "pointer",
          }}
          hoverStyle={{ background: `${ACCENT}30` }}
        >
          {loading ? "…" : "ASK"}
        </Hover>
      </div>
      {answer ? (
        <div
          style={{
            background: "#0e131a",
            border: "1px solid #1c2330",
            borderRadius: 7,
            padding: "11px 13px",
            fontSize: 13,
            color: "#c7cdd6",
            lineHeight: 1.55,
          }}
        >
          {answer}
        </div>
      ) : null}
    </div>
  );
}

function DocPane({ doc }: { doc: KnowledgeDocument }) {
  const entities = extractEntities(doc);
  const color = TYPE_COLOR[doc.source_type];
  const paragraphs = (doc.content ?? "").split(/\n+/).filter(Boolean);

  return (
    <div style={{ display: "grid", gridTemplateColumns: "220px 1fr", gap: 12, height: "100%", minHeight: 0 }}>
      {/* Left: entity sidebar */}
      <div
        style={{
          background: "#11151c",
          border: "1px solid #1c2330",
          borderRadius: 10,
          padding: "14px 14px",
          display: "flex",
          flexDirection: "column",
          gap: 6,
          overflowY: "auto",
        }}
      >
        <div style={{ fontFamily: fonts.mono, fontSize: 10, color: "#8a94a6", letterSpacing: "0.12em", marginBottom: 6 }}>
          ENTITIES DETECTED
        </div>
        {entities.length > 0 ? (
          entities.map((e) => (
            <div
              key={e}
              style={{
                fontFamily: fonts.mono,
                fontSize: 11,
                color: "#c7cdd6",
                background: "#161d28",
                border: "1px solid #232a36",
                borderRadius: 5,
                padding: "4px 8px",
              }}
            >
              {e}
            </div>
          ))
        ) : (
          <div style={{ fontFamily: fonts.mono, fontSize: 11, color: "#4b5563" }}>No entities found</div>
        )}
      </div>

      {/* Right: document text + ask panel */}
      <div style={{ display: "flex", flexDirection: "column", gap: 12, minHeight: 0, overflowY: "auto" }}>
        <div
          style={{
            background: "#11151c",
            border: "1px solid #1c2330",
            borderLeft: `3px solid ${color}`,
            borderRadius: 10,
            padding: "18px 20px",
            flex: 1,
          }}
        >
          <h2
            style={{
              fontFamily: fonts.grotesk,
              fontWeight: 700,
              fontSize: 19,
              margin: "0 0 6px",
              lineHeight: 1.3,
              color: "#e6eaf0",
            }}
          >
            {doc.title ?? "Untitled"}
          </h2>
          {doc.authors.length > 0 ? (
            <div style={{ fontFamily: fonts.mono, fontSize: 11, color: "#5b6675", marginBottom: 14 }}>
              {doc.authors.join(", ")}
            </div>
          ) : null}
          <div style={{ fontSize: 13.5, color: "#c7cdd6", lineHeight: 1.65 }}>
            {paragraphs.map((p, i) => (
              <p key={i} style={{ margin: "0 0 12px" }}>
                {highlightEntities(p, entities)}
              </p>
            ))}
            {paragraphs.length === 0 ? (
              <span style={{ color: "#4b5563" }}>No content available for this document.</span>
            ) : null}
          </div>
        </div>
        <AskDocPanel doc={doc} />
      </div>
    </div>
  );
}

export default function DocumentReader() {
  const { data: docs, source, isLoading } = useDocuments();
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const selected = docs.find((d) => d.document_id === selectedId) ?? docs[0] ?? null;

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", gap: 0 }}>
      <PageHeader
        title="Document Reader"
        subtitle="Inline entity highlights · section extraction · ask this doc"
        right={<SourceBadge source={source} isLoading={isLoading} />}
      />

      {/* Document picker */}
      <div style={{ display: "flex", gap: 6, marginBottom: 14, flexWrap: "wrap" }}>
        {docs.map((d) => {
          const active = d.document_id === (selected?.document_id ?? null);
          const color = TYPE_COLOR[d.source_type];
          return (
            <Hover
              key={d.document_id}
              as="button"
              onClick={() => setSelectedId(d.document_id)}
              style={{
                fontFamily: fonts.mono,
                fontSize: 10.5,
                padding: "5px 11px",
                borderRadius: 6,
                cursor: "pointer",
                maxWidth: 220,
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
                ...(active
                  ? { background: `${color}20`, color, border: `1px solid ${color}55` }
                  : { background: "#11151c", color: "#8a94a6", border: "1px solid #232a36" }),
              }}
              hoverStyle={active ? {} : { borderColor: "#3a4554" }}
            >
              {d.title ?? d.document_id}
            </Hover>
          );
        })}
      </div>

      {selected ? (
        <DocPane doc={selected} />
      ) : (
        <div
          style={{
            textAlign: "center",
            padding: "48px 0",
            fontFamily: fonts.mono,
            fontSize: 12,
            color: "#4b5563",
          }}
        >
          No documents in library yet. Ingest a document to start reading.
        </div>
      )}
    </div>
  );
}
