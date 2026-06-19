import { useState } from "react";
import { ACCENT, palette, accentSoft, accentBorder, fonts } from "../theme";
import { sentColor, fmt } from "../lib/sentiment";
import { mockStories, mockTimeline } from "../data/mock";
import PageHeader from "../components/PageHeader";
import Hover from "../components/Hover";
import type { TimelineEvent } from "../types";

function kindColor(kind: TimelineEvent["kind"]): string {
  if (kind === "Milestone") return ACCENT;
  if (kind === "Origin") return palette.blue;
  if (kind === "Reaction") return palette.violet;
  return palette.teal;
}

export default function Timeline() {
  const [activeStory, setActiveStory] = useState("s1");
  const events = mockTimeline[activeStory] ?? [];
  const activeLabel = mockStories.find((s) => s.id === activeStory)?.label ?? "";

  return (
    <div>
      <PageHeader
        title="Story Timeline"
        subtitle={
          <>
            How <span style={{ color: "#9aa4b2" }}>{activeLabel}</span> developed over time
          </>
        }
      />
      <div style={{ display: "flex", gap: 7, marginBottom: 22, flexWrap: "wrap" }}>
        {mockStories.map((s) => {
          const active = activeStory === s.id;
          return (
            <Hover
              key={s.id}
              as="button"
              onClick={() => setActiveStory(s.id)}
              style={{
                fontFamily: fonts.mono,
                fontSize: 11,
                padding: "6px 13px",
                borderRadius: 7,
                cursor: "pointer",
                ...(active
                  ? { background: accentSoft(ACCENT), color: ACCENT, border: `1px solid ${accentBorder(ACCENT)}` }
                  : { background: "#11151c", color: "#8a94a6", border: "1px solid #232a36" }),
              }}
              hoverStyle={active ? {} : { borderColor: "#3a4554" }}
            >
              {s.label}
            </Hover>
          );
        })}
      </div>

      <div style={{ position: "relative", paddingLeft: 6 }}>
        {events.map((e, i) => {
          const kc = kindColor(e.kind);
          const showLine = i !== events.length - 1;
          return (
            <div key={i} style={{ display: "grid", gridTemplateColumns: "74px 28px 1fr", gap: 0, alignItems: "stretch" }}>
              <div style={{ textAlign: "right", padding: "2px 14px 0 0", fontFamily: fonts.mono, fontSize: 11, color: "#8a94a6" }}>
                {e.date}
              </div>
              <div style={{ position: "relative", display: "flex", flexDirection: "column", alignItems: "center" }}>
                <span style={{ width: 13, height: 13, flex: "none", borderRadius: "50%", background: "#0e131a", border: `2px solid ${kc}`, zIndex: 1, marginTop: 3 }} />
                {showLine ? <span style={{ flex: 1, width: 2, background: "#1c2330" }} /> : null}
              </div>
              <div style={{ padding: "0 0 18px 6px" }}>
                <div style={{ background: "#11151c", border: "1px solid #1c2330", borderRadius: 10, padding: "14px 16px", borderLeft: `3px solid ${kc}` }}>
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 7 }}>
                    <span style={{ fontFamily: fonts.mono, fontSize: 9, color: kc, letterSpacing: "0.08em", textTransform: "uppercase" }}>
                      {e.kind}
                    </span>
                    <span style={{ fontFamily: fonts.mono, fontSize: 11, color: sentColor(e.sent) }}>{fmt(e.sent)}</span>
                  </div>
                  <div style={{ fontSize: 14, fontWeight: 500, lineHeight: 1.38 }}>{e.title}</div>
                  <div style={{ fontFamily: fonts.mono, fontSize: 10, color: "#5b6675", marginTop: 7 }}>{e.source}</div>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
