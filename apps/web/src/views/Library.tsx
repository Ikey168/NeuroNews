import { useState } from "react";
import { ACCENT, accentSoft, accentBorder, palette, fonts } from "../theme";
import { useDocuments } from "../lib/queries";
import PageHeader from "../components/PageHeader";
import SourceBadge from "../components/SourceBadge";
import Hover from "../components/Hover";
import type { SourceType, KnowledgeDocument } from "../types";

const SOURCE_TYPES: SourceType[] = ["news", "blog", "paper", "book", "transcript", "web", "note"];

const TYPE_COLOR: Record<SourceType, string> = {
  news: ACCENT,
  blog: palette.teal,
  paper: palette.blue,
  book: palette.violet,
  transcript: palette.pos,
  web: palette.dim,
  note: palette.amber,
};

const TYPE_GLYPH: Record<SourceType, string> = {
  news: "≣",
  blog: "✍",
  paper: "◻",
  book: "⊟",
  transcript: "♪",
  web: "⊕",
  note: "◈",
};

function relativeDate(ms: number | null): string {
  if (!ms) return "—";
  const diff = Date.now() - ms;
  const mins = Math.floor(diff / 60_000);
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

function TypePill({ type }: { type: SourceType }) {
  const color = TYPE_COLOR[type];
  const glyph = TYPE_GLYPH[type];
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 5,
        fontFamily: fonts.mono,
        fontSize: 9.5,
        fontWeight: 600,
        letterSpacing: "0.08em",
        textTransform: "uppercase",
        color,
        background: `${color}18`,
        border: `1px solid ${color}44`,
        borderRadius: 5,
        padding: "2px 7px",
      }}
    >
      {glyph} {type}
    </span>
  );
}

function DocumentCard({ doc }: { doc: KnowledgeDocument }) {
  const color = TYPE_COLOR[doc.source_type];
  const preview = doc.content ? doc.content.slice(0, 220) + (doc.content.length > 220 ? "…" : "") : null;
  const date = relativeDate(doc.created_at ?? doc.ingested_at);
  const source = doc.source_id ?? (doc.url ? new URL(doc.url).hostname.replace("www.", "") : "—");
  const authorsText = doc.authors.length > 0 ? doc.authors.slice(0, 3).join(", ") + (doc.authors.length > 3 ? " et al." : "") : null;

  return (
    <Hover
      as="article"
      style={{
        background: "#11151c",
        border: "1px solid #1c2330",
        borderLeft: `3px solid ${color}`,
        borderRadius: 10,
        padding: "14px 16px",
        display: "flex",
        flexDirection: "column",
        gap: 8,
      }}
      hoverStyle={{ borderColor: "#2a3340", borderLeftColor: color }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 9, flexWrap: "wrap" }}>
        <TypePill type={doc.source_type} />
        <span style={{ fontFamily: fonts.mono, fontSize: 10, color: "#5b6675" }}>
          {source}
          {authorsText ? ` · ${authorsText}` : ""}
          {" · "}
          {date}
        </span>
      </div>
      <h3
        style={{
          fontFamily: fonts.grotesk,
          fontWeight: 600,
          fontSize: 15,
          margin: 0,
          lineHeight: 1.35,
          color: "#e6eaf0",
        }}
      >
        {doc.title ?? "Untitled"}
      </h3>
      {preview ? (
        <p style={{ fontSize: 12.5, color: "#9aa4b2", margin: 0, lineHeight: 1.5 }}>{preview}</p>
      ) : null}
      {doc.url ? (
        <a
          href={doc.url}
          target="_blank"
          rel="noopener noreferrer"
          style={{
            fontFamily: fonts.mono,
            fontSize: 10,
            color: color,
            textDecoration: "none",
            alignSelf: "flex-start",
          }}
          onClick={(e) => e.stopPropagation()}
        >
          OPEN ↗
        </a>
      ) : null}
    </Hover>
  );
}

export default function Library() {
  const [filter, setFilter] = useState<"all" | SourceType>("all");
  const { data: docs, source, isLoading } = useDocuments(filter === "all" ? undefined : filter);

  const filterBtn = (active: boolean) => ({
    fontFamily: fonts.mono,
    fontSize: 11,
    padding: "5px 12px",
    borderRadius: 7,
    cursor: "pointer",
    ...(active
      ? { background: accentSoft(ACCENT), color: ACCENT, border: `1px solid ${accentBorder(ACCENT)}` }
      : { background: "#11151c", color: "#8a94a6", border: "1px solid #232a36" }),
  });

  return (
    <div>
      <PageHeader
        title="Library"
        subtitle={`${docs.length} documents · all source types · knowledge engine`}
        right={<SourceBadge source={source} isLoading={isLoading} />}
      />

      {/* Source-type filter strip */}
      <div style={{ display: "flex", gap: 6, marginBottom: 18, flexWrap: "wrap" }}>
        <Hover
          as="button"
          onClick={() => setFilter("all")}
          style={filterBtn(filter === "all")}
          hoverStyle={filter === "all" ? {} : { borderColor: "#3a4554" }}
        >
          All
        </Hover>
        {SOURCE_TYPES.map((t) => {
          const active = filter === t;
          const color = TYPE_COLOR[t];
          return (
            <Hover
              key={t}
              as="button"
              onClick={() => setFilter(t)}
              style={
                active
                  ? {
                      fontFamily: fonts.mono,
                      fontSize: 11,
                      padding: "5px 12px",
                      borderRadius: 7,
                      cursor: "pointer",
                      background: `${color}18`,
                      color,
                      border: `1px solid ${color}44`,
                    }
                  : filterBtn(false)
              }
              hoverStyle={active ? {} : { borderColor: "#3a4554" }}
            >
              {TYPE_GLYPH[t]} {t}
            </Hover>
          );
        })}
      </div>

      {docs.length === 0 ? (
        <div
          style={{
            textAlign: "center",
            padding: "48px 0",
            fontFamily: fonts.mono,
            fontSize: 12,
            color: "#4b5563",
          }}
        >
          No {filter === "all" ? "" : filter + " "}documents ingested yet.
          <br />
          <span style={{ color: "#5b6675", fontSize: 11, marginTop: 8, display: "block" }}>
            Use the upload connector or subscribe to an RSS feed to add documents.
          </span>
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {docs.map((doc) => (
            <DocumentCard key={doc.document_id} doc={doc} />
          ))}
        </div>
      )}
    </div>
  );
}
