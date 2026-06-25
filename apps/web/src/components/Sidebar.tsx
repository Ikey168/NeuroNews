import type { CSSProperties } from "react";
import { ACCENT, accentSoft, accentGlow, fonts } from "../theme";
import type { ViewKey } from "../types";
import { usePackStatus } from "../lib/queries";
import Hover from "./Hover";

interface NavDef {
  key: ViewKey;
  label: string;
  glyph: string;
  badge?: string;
}

const coreNav: NavDef[] = [
  { key: "dashboard", label: "Overview", glyph: "◧" },
  { key: "library", label: "Library", glyph: "≣" },
  { key: "knowledge", label: "Knowledge Graph", glyph: "⬡" },
  { key: "reader", label: "Document Reader", glyph: "◈" },
];

const researchNav: NavDef[] = [
  { key: "workspaces", label: "Workspaces", glyph: "◳", badge: "4" },
];

const newsOnlyNav: NavDef[] = [
  { key: "sentiment", label: "Sentiment", glyph: "◑" },
  { key: "clusters", label: "Event Clusters", glyph: "⊞", badge: "18" },
  { key: "trending", label: "Trending", glyph: "↗" },
  { key: "watchlists", label: "Watchlists", glyph: "☆", badge: "6" },
  { key: "timeline", label: "Story Timeline", glyph: "⤳" },
];

interface Props {
  view: ViewKey;
  setView: (v: ViewKey) => void;
  ingestRate: string;
}

export default function Sidebar({ view, setView, ingestRate }: Props) {
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

  const badge: CSSProperties = {
    fontFamily: fonts.mono,
    fontSize: 10,
    background: "#1c2330",
    color: "#8a94a6",
    padding: "1px 6px",
    borderRadius: 10,
  };

  const renderNav = (items: NavDef[]) =>
    items.map((n) => (
      <Hover
        key={n.key}
        as="button"
        onClick={() => setView(n.key)}
        style={navBtn(view === n.key)}
        hoverStyle={view === n.key ? {} : { background: "#161d28", color: "#e6eaf0" }}
      >
        <span style={{ width: 18, flex: "none", textAlign: "center", fontSize: 13 }}>{n.glyph}</span>
        <span style={{ flex: 1, textAlign: "left" }}>{n.label}</span>
        {n.badge ? <span style={badge}>{n.badge}</span> : null}
      </Hover>
    ));

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
            KNOWLEDGE ENGINE
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
        <div style={sectionLabel}>LIBRARY</div>
        {renderNav(coreNav)}

        <div style={{ ...sectionLabel, padding: "18px 10px 6px" }}>RESEARCH</div>
        {renderNav(researchNav)}

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
            {renderNav(newsOnlyNav)}
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
