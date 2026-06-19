import { useState, type CSSProperties } from "react";
import { ACCENT, palette, fonts } from "../theme";
import { sentColor, fmt } from "../lib/sentiment";
import { mockWorkspaces, mockWorkspaceDetail } from "../data/mock";
import PageHeader from "../components/PageHeader";
import SourceBadge from "../components/SourceBadge";
import Hover from "../components/Hover";
import type { Workspace } from "../types";

function statusStyle(status: Workspace["status"]): CSSProperties {
  return status === "Synthesizing"
    ? { color: palette.amber, border: `1px solid ${palette.amber}55`, background: `${palette.amber}14` }
    : { color: palette.pos, border: `1px solid ${palette.pos}55`, background: `${palette.pos}14` };
}

const sectionLabel: CSSProperties = {
  fontFamily: fonts.mono,
  fontSize: 10,
  color: "#8a94a6",
  letterSpacing: "0.12em",
  marginBottom: 11,
};

export default function Workspaces() {
  const [activeId, setActiveId] = useState("p3");
  const active = mockWorkspaces.find((w) => w.id === activeId) ?? mockWorkspaces[0];
  const detail = mockWorkspaceDetail[active.id];

  const stats = [
    { label: "Sources", value: String(active.sources) },
    { label: "Notes", value: String(active.notes) },
    { label: "Sub-questions", value: String(detail.sub.length) },
    { label: "Entities", value: String(detail.entities.length) },
  ];

  const badgeSmall = (w: Workspace): CSSProperties => ({
    fontFamily: fonts.mono,
    fontSize: 9,
    letterSpacing: "0.06em",
    padding: "1px 6px",
    borderRadius: 4,
    ...statusStyle(w.status),
  });

  return (
    <div>
      <PageHeader
        title="Research Workspaces"
        subtitle="Group sources around a question · build toward a thesis"
        right={<SourceBadge source="demo" />}
      />
      <div style={{ display: "grid", gridTemplateColumns: "316px 1fr", gap: 14, alignItems: "start" }}>
        {/* Project list */}
        <div style={{ display: "flex", flexDirection: "column", gap: 9 }}>
          <Hover
            as="button"
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              gap: 7,
              width: "100%",
              padding: 11,
              border: "1px dashed #2a3340",
              borderRadius: 9,
              background: "transparent",
              color: "#8a94a6",
              cursor: "pointer",
              fontFamily: fonts.mono,
              fontSize: 11.5,
            }}
            hoverStyle={{ borderColor: "#3a4554", color: "#c7cdd6" }}
          >
            + NEW INVESTIGATION
          </Hover>
          {mockWorkspaces.map((w) => (
            <Hover
              key={w.id}
              as="button"
              onClick={() => setActiveId(w.id)}
              style={{
                textAlign: "left",
                width: "100%",
                cursor: "pointer",
                background: "#11151c",
                border: `1px solid ${activeId === w.id ? ACCENT : "#1c2330"}`,
                borderLeft: `3px solid ${w.color}`,
                borderRadius: 9,
                padding: "13px 14px",
                transition: "border-color .12s",
              }}
              hoverStyle={activeId === w.id ? {} : { borderColor: "#3a4554" }}
            >
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 7 }}>
                <span style={badgeSmall(w)}>{w.status}</span>
                <span style={{ fontFamily: fonts.mono, fontSize: 10, color: "#5b6675" }}>{w.updated}</span>
              </div>
              <div style={{ fontSize: 13, fontWeight: 500, lineHeight: 1.38, color: "#e6eaf0" }}>{w.q}</div>
              <div style={{ display: "flex", gap: 12, marginTop: 9, fontFamily: fonts.mono, fontSize: 10, color: "#5b6675" }}>
                <span>{w.sources} sources</span>
                <span>{w.notes} notes</span>
              </div>
            </Hover>
          ))}
        </div>

        {/* Active project detail */}
        <div style={{ background: "#11151c", border: "1px solid #1c2330", borderRadius: 11, padding: "20px 22px" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 8 }}>
            <span style={{ ...badgeSmall(active), fontSize: 10, padding: "3px 9px", borderRadius: 5 }}>{active.status}</span>
            <span style={{ fontFamily: fonts.mono, fontSize: 10.5, color: "#5b6675" }}>updated {active.updated} ago</span>
          </div>
          <h2 style={{ fontFamily: fonts.grotesk, fontWeight: 600, fontSize: 20, margin: "0 0 16px", lineHeight: 1.3, letterSpacing: "-0.01em" }}>
            {active.q}
          </h2>

          <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 10, marginBottom: 20 }}>
            {stats.map((s) => (
              <div key={s.label} style={{ background: "#0e131a", border: "1px solid #1c2330", borderRadius: 8, padding: "11px 13px" }}>
                <div style={{ fontFamily: fonts.grotesk, fontWeight: 600, fontSize: 20 }}>{s.value}</div>
                <div style={{ fontFamily: fonts.mono, fontSize: 9.5, color: "#5b6675", letterSpacing: "0.06em", textTransform: "uppercase", marginTop: 3 }}>
                  {s.label}
                </div>
              </div>
            ))}
          </div>

          <div style={sectionLabel}>KEY SUB-QUESTIONS</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 8, marginBottom: 20 }}>
            {detail.sub.map((q, i) => (
              <div key={i} style={{ display: "flex", gap: 10, alignItems: "flex-start", background: "#0e131a", border: "1px solid #1c2330", borderRadius: 8, padding: "10px 13px" }}>
                <span style={{ color: ACCENT, fontSize: 12, marginTop: 1 }}>?</span>
                <span style={{ flex: 1, fontSize: 13, color: "#c7cdd6", lineHeight: 1.42 }}>{q}</span>
              </div>
            ))}
          </div>

          <div style={sectionLabel}>SOURCES & NOTES</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 10, marginBottom: 20 }}>
            {detail.sources.map((s, i) => {
              const sc = sentColor(s.sent);
              return (
                <div key={i} style={{ border: "1px solid #1c2330", borderRadius: 9, padding: "13px 15px", background: "#0e131a" }}>
                  <div style={{ display: "flex", alignItems: "flex-start", gap: 11 }}>
                    <span style={{ width: 7, height: 7, flex: "none", borderRadius: "50%", background: sc, marginTop: 6 }} />
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontSize: 13, fontWeight: 500, lineHeight: 1.35 }}>{s.title}</div>
                      <div style={{ fontFamily: fonts.mono, fontSize: 10, color: "#5b6675", marginTop: 4 }}>
                        {s.source} · {s.time}
                      </div>
                    </div>
                    <span style={{ fontFamily: fonts.mono, fontSize: 12, fontWeight: 600, color: sc }}>{fmt(s.sent)}</span>
                  </div>
                  <div style={{ display: "flex", gap: 9, alignItems: "flex-start", marginTop: 10, paddingTop: 10, borderTop: "1px solid #1c2330" }}>
                    <span style={{ fontFamily: fonts.mono, fontSize: 9, color: ACCENT, letterSpacing: "0.08em", marginTop: 2 }}>NOTE</span>
                    <span style={{ flex: 1, fontSize: 12.5, color: "#9aa4b2", lineHeight: 1.45, fontStyle: "italic" }}>{s.note}</span>
                  </div>
                </div>
              );
            })}
          </div>

          <div style={sectionLabel}>TRACKED ENTITIES</div>
          <div style={{ display: "flex", gap: 7, flexWrap: "wrap" }}>
            {detail.entities.map((e) => (
              <span
                key={e}
                style={{
                  fontFamily: fonts.mono,
                  fontSize: 11,
                  color: "#c7cdd6",
                  background: "#161d28",
                  border: "1px solid #232a36",
                  borderRadius: 6,
                  padding: "4px 10px",
                }}
              >
                {e}
              </span>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
