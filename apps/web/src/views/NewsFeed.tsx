import { useState } from "react";
import { ACCENT, accentSoft, accentBorder, fonts } from "../theme";
import { sentColor, sentLabel, fmt } from "../lib/sentiment";
import { useArticles } from "../lib/queries";
import PageHeader from "../components/PageHeader";
import SourceBadge from "../components/SourceBadge";
import Hover from "../components/Hover";

const filters = ["All", "Economy", "Technology", "Policy", "Energy", "Health"];

export default function NewsFeed() {
  const [filter, setFilter] = useState("All");
  const { data: articles, source, isLoading } = useArticles();
  const feed = filter === "All" ? articles : articles.filter((a) => a.category === filter);

  return (
    <div>
      <PageHeader
        title="News Feed"
        subtitle={`${articles.length} articles · 142 sources · auto-classified`}
        right={<SourceBadge source={source} isLoading={isLoading} />}
      />
      <div style={{ display: "flex", gap: 7, marginBottom: 16, flexWrap: "wrap" }}>
        {filters.map((f) => {
          const active = filter === f;
          return (
            <Hover
              key={f}
              as="button"
              onClick={() => setFilter(f)}
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
              {f}
            </Hover>
          );
        })}
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        {feed.map((a, i) => (
          <Hover
            key={i}
            as="article"
            style={{
              background: "#11151c",
              border: "1px solid #1c2330",
              borderRadius: 10,
              padding: "16px 18px",
              display: "flex",
              gap: 16,
            }}
            hoverStyle={{ borderColor: "#2a3340" }}
          >
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 9, marginBottom: 8 }}>
                <span
                  style={{
                    fontFamily: fonts.mono,
                    fontSize: 9.5,
                    fontWeight: 600,
                    color: ACCENT,
                    letterSpacing: "0.08em",
                    textTransform: "uppercase",
                  }}
                >
                  {a.category}
                </span>
                <span style={{ fontFamily: fonts.mono, fontSize: 10, color: "#5b6675" }}>
                  {a.source} · {a.time}
                </span>
              </div>
              <h3 style={{ fontFamily: fonts.grotesk, fontWeight: 600, fontSize: 16, margin: "0 0 6px", lineHeight: 1.3 }}>
                {a.title}
              </h3>
              {a.summary ? (
                <p style={{ fontSize: 13, color: "#9aa4b2", margin: "0 0 11px", lineHeight: 1.5 }}>{a.summary}</p>
              ) : null}
              <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
                {a.entities.map((e) => (
                  <span
                    key={e}
                    style={{
                      fontFamily: fonts.mono,
                      fontSize: 10,
                      color: "#9aa4b2",
                      background: "#161d28",
                      border: "1px solid #232a36",
                      borderRadius: 5,
                      padding: "2px 7px",
                    }}
                  >
                    {e}
                  </span>
                ))}
              </div>
            </div>
            <div style={{ flex: "none", width: 84, display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 4 }}>
              <div style={{ fontFamily: fonts.mono, fontSize: 18, fontWeight: 600, color: sentColor(a.sent) }}>
                {fmt(a.sent)}
              </div>
              <div style={{ fontFamily: fonts.mono, fontSize: 9, color: "#5b6675", letterSpacing: "0.08em" }}>
                {sentLabel(a.sent)}
              </div>
            </div>
          </Hover>
        ))}
      </div>
    </div>
  );
}
