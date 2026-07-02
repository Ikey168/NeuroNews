import type { CSSProperties } from "react";
import { ACCENT, accentSoft, accentGlow, fonts } from "../theme";
import { usePackStatus } from "../lib/queries";
import Hover from "./Hover";
import { BRIEFING, type CanvasDef } from "../genui/canvases";

// The sidebar is a canvas manager, not a view switch: every entry either
// activates an open canvas or generates a new one from a preset intent.
// Presets route through the same planner as free-typed intents.

interface PresetDef {
  label: string;
  intent: string;
  glyph: string;
}

const corePresets: PresetDef[] = [
  { label: "Library", intent: "library documents", glyph: "≣" },
  { label: "Entity network", intent: "entity network connections", glyph: "⬡" },
  { label: "Claims & facts", intent: "fact-check claims and evidence", glyph: "◫" },
  { label: "Stance & conflicts", intent: "stance conflicts and disagreements", glyph: "◮" },
  { label: "Outlets & framing", intent: "compare outlet framing and transparency", glyph: "◭" },
  { label: "Key actors", intent: "who are the key actors and stakeholders", glyph: "◉" },
];

const newsPresets: PresetDef[] = [
  { label: "Sentiment", intent: "sentiment overview this week", glyph: "◑" },
  { label: "Event clusters", intent: "breaking event clusters", glyph: "⊞" },
  { label: "Trending", intent: "trending topics this week", glyph: "↗" },
  { label: "Watchlists", intent: "watchlist alerts", glyph: "☆" },
  { label: "Story timeline", intent: "story timeline developments", glyph: "⤳" },
];

interface Props {
  canvases: CanvasDef[];
  activeId: string;
  onSelect: (id: string) => void;
  onOpen: (intent: string, label?: string) => void;
  onRemove: (id: string) => void;
  ingestRate: string;
}

export default function Sidebar({ canvases, activeId, onSelect, onOpen, onRemove, ingestRate }: Props) {
  const { newsPack } = usePackStatus();

  const navBtn = (active: boolean): CSSProperties => ({
    display: "flex",
    alignItems: "center",
    gap: 11,
    width: "100%",
    padding: "9px 10px",
    border: "none",
    borderRadius: 7,
    cursor: "pointer",
    fontFamily: fonts.sans,
    fontSize: 13,
    fontWeight: 500,
    transition: "background .12s",
    background: active ? accentSoft(ACCENT) : "transparent",
    color: active ? ACCENT : "#9aa4b2",
  });

  const sectionLabel: CSSProperties = {
    fontFamily: fonts.mono,
    fontSize: 9.5,
    color: "#4b5563",
    letterSpacing: "0.16em",
    padding: "8px 10px 6px",
  };

  return (
    <aside
      style={{
        width: 236,
        flex: "none",
        background: "#0c1016",
        borderRight: "1px solid #1c2330",
        display: "flex",
        flexDirection: "column",
      }}
    >
      {/* Brand */}
      <div
        style={{
          padding: "20px 18px 18px",
          borderBottom: "1px solid #1c2330",
          display: "flex",
          alignItems: "center",
          gap: 11,
        }}
      >
        <div
          style={{
            width: 34,
            height: 34,
            flex: "none",
            borderRadius: 8,
            background: ACCENT,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            boxShadow: `0 0 18px -2px ${accentGlow(ACCENT)}`,
          }}
        >
          <span style={{ fontFamily: fonts.grotesk, fontWeight: 700, fontSize: 19, color: "#0a0d12" }}>N</span>
        </div>
        <div style={{ lineHeight: 1.1 }}>
          <div style={{ fontFamily: fonts.grotesk, fontWeight: 700, fontSize: 16, letterSpacing: "-0.01em" }}>
            Noesis
          </div>
          <div style={{ fontFamily: fonts.mono, fontSize: 9.5, color: "#5b6675", letterSpacing: "0.16em", marginTop: 2 }}>
            GENERATIVE CANVAS
          </div>
        </div>
      </div>

      <nav
        style={{
          flex: 1,
          padding: "12px 10px",
          display: "flex",
          flexDirection: "column",
          gap: 2,
          overflowY: "auto",
        }}
      >
        <div style={sectionLabel}>CANVASES</div>
        {canvases.map((c) => (
          <Hover
            key={c.id}
            as="button"
            onClick={() => onSelect(c.id)}
            style={navBtn(c.id === activeId)}
            hoverStyle={c.id === activeId ? {} : { background: "#161d28", color: "#e6eaf0" }}
            title={c.intent || "Adaptive overview briefing"}
          >
            <span style={{ width: 18, flex: "none", textAlign: "center", fontSize: 13 }}>
              {c.id === BRIEFING.id ? "✦" : "◈"}
            </span>
            <span
              style={{
                flex: 1,
                textAlign: "left",
                whiteSpace: "nowrap",
                overflow: "hidden",
                textOverflow: "ellipsis",
              }}
            >
              {c.label}
            </span>
            {c.id !== BRIEFING.id ? (
              <span
                onClick={(e) => {
                  e.stopPropagation();
                  onRemove(c.id);
                }}
                title="Close canvas"
                style={{ fontFamily: fonts.mono, fontSize: 11, color: "#4b5563", padding: "0 2px" }}
              >
                ✕
              </span>
            ) : null}
          </Hover>
        ))}

        <div style={{ ...sectionLabel, padding: "18px 10px 6px" }}>GENERATE</div>
        {corePresets.map((p) => (
          <Hover
            key={p.label}
            as="button"
            onClick={() => onOpen(p.intent, p.label)}
            style={navBtn(false)}
            hoverStyle={{ background: "#161d28", color: "#e6eaf0" }}
            title={`Generate: “${p.intent}”`}
          >
            <span style={{ width: 18, flex: "none", textAlign: "center", fontSize: 13 }}>{p.glyph}</span>
            <span style={{ flex: 1, textAlign: "left" }}>{p.label}</span>
          </Hover>
        ))}

        {newsPack ? (
          <>
            <div
              style={{
                ...sectionLabel,
                padding: "18px 10px 6px",
                display: "flex",
                alignItems: "center",
                gap: 6,
              }}
            >
              NEWS PACK
              <span
                style={{
                  fontFamily: fonts.mono,
                  fontSize: 8.5,
                  color: "#3DD68C",
                  background: "#3DD68C18",
                  border: "1px solid #3DD68C44",
                  borderRadius: 4,
                  padding: "1px 5px",
                  letterSpacing: "0.08em",
                }}
              >
                ON
              </span>
            </div>
            {newsPresets.map((p) => (
              <Hover
                key={p.label}
                as="button"
                onClick={() => onOpen(p.intent, p.label)}
                style={navBtn(false)}
                hoverStyle={{ background: "#161d28", color: "#e6eaf0" }}
                title={`Generate: “${p.intent}”`}
              >
                <span style={{ width: 18, flex: "none", textAlign: "center", fontSize: 13 }}>{p.glyph}</span>
                <span style={{ flex: 1, textAlign: "left" }}>{p.label}</span>
              </Hover>
            ))}
          </>
        ) : null}
      </nav>

      {/* Footer */}
      <div
        style={{
          padding: "14px 16px",
          borderTop: "1px solid #1c2330",
          display: "flex",
          flexDirection: "column",
          gap: 9,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span
            style={{ width: 7, height: 7, borderRadius: "50%", background: "#3DD68C", animation: "blink 2s infinite" }}
          />
          <span style={{ fontFamily: fonts.mono, fontSize: 10.5, color: "#8a94a6" }}>PIPELINE LIVE</span>
        </div>
        <div
          style={{
            fontFamily: fonts.mono,
            fontSize: 10.5,
            color: "#5b6675",
            display: "flex",
            justifyContent: "space-between",
          }}
        >
          <span>142 sources</span>
          <span>{ingestRate}/min</span>
        </div>
      </div>
    </aside>
  );
}
