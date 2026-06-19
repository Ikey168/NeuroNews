import { useState, type CSSProperties } from "react";
import { ACCENT, palette, accentSoft, accentBorder, fonts } from "../theme";
import { sentColor } from "../lib/sentiment";
import { useArticles, useClusters, useTrending } from "../lib/queries";
import type { Kpi, ViewKey } from "../types";
import TrendChart from "../components/charts/TrendChart";
import Hover from "../components/Hover";

const kpis: Kpi[] = [
  { label: "Articles 24h", value: "3,847", delta: "+12.4%", deltaLabel: "vs prev", color: ACCENT, positive: true },
  { label: "Avg Sentiment", value: "+0.18", delta: "+0.06", deltaLabel: "shift", color: palette.pos, positive: true },
  { label: "Active Clusters", value: "18", delta: "+4", deltaLabel: "new", color: palette.teal, positive: true },
  { label: "Entities Tracked", value: "12,409", delta: "+318", deltaLabel: "24h", color: palette.blue, positive: true },
  { label: "Avg Latency", value: "1.2s", delta: "-0.3s", deltaLabel: "ingest", color: palette.amber, positive: true },
];

const card: CSSProperties = {
  background: "#11151c",
  border: "1px solid #1c2330",
  borderRadius: 10,
  padding: "16px 18px",
};

const sectionTitle: CSSProperties = { fontFamily: fonts.grotesk, fontWeight: 600, fontSize: 14 };
const linkBtn: CSSProperties = {
  fontFamily: fonts.mono,
  fontSize: 10.5,
  color: ACCENT,
  background: "none",
  border: "none",
  cursor: "pointer",
};

interface Props {
  setView: (v: ViewKey) => void;
}

export default function Dashboard({ setView }: Props) {
  const [range, setRange] = useState("24H");
  const { data: articles } = useArticles();
  const { data: clustersRaw } = useClusters();
  const { data: trending } = useTrending();

  const clusters = clustersRaw.slice(0, 3).map((c, i) => ({
    ...c,
    headlines: articles.length
      ? [articles[i % articles.length].title, articles[(i + 3) % articles.length].title]
      : [],
  }));

  const maxM = Math.max(1, ...trending.map((t) => t.mentions));
  const trendingTop = trending.slice(0, 5).map((t, i) => ({
    rank: i + 1,
    topic: t.topic,
    barWidth: Math.round((t.mentions / maxM) * 100) + "%",
    change: (t.change >= 0 ? "+" : "") + t.change + "%",
    changeColor: t.change >= 0 ? palette.pos : palette.neg,
  }));

  const feedTop = articles.slice(0, 4);

  return (
    <div>
      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", marginBottom: 16 }}>
        <div>
          <h1 style={{ fontFamily: fonts.grotesk, fontWeight: 600, fontSize: 21, margin: 0, letterSpacing: "-0.01em" }}>
            Intelligence Overview
          </h1>
          <p style={{ fontFamily: fonts.mono, fontSize: 11, color: "#5b6675", margin: "5px 0 0", letterSpacing: "0.04em" }}>
            Real-time signal across 142 sources · last 24h
          </p>
        </div>
        <div style={{ display: "flex", gap: 6 }}>
          {["1H", "6H", "24H", "7D"].map((r) => {
            const active = r === range;
            return (
              <span
                key={r}
                onClick={() => setRange(r)}
                style={{
                  fontFamily: fonts.mono,
                  fontSize: 10.5,
                  padding: "4px 11px",
                  borderRadius: 6,
                  cursor: "pointer",
                  ...(active
                    ? { background: accentSoft(ACCENT), color: ACCENT, border: `1px solid ${accentBorder(ACCENT)}` }
                    : { background: "#11151c", color: "#8a94a6", border: "1px solid #232a36" }),
                }}
              >
                {r}
              </span>
            );
          })}
        </div>
      </div>

      {/* KPI row */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(5,1fr)", gap: 12, marginBottom: 16 }}>
        {kpis.map((k) => (
          <div key={k.label} style={{ ...card, padding: "15px 16px", position: "relative", overflow: "hidden" }}>
            <div style={{ position: "absolute", top: 0, left: 0, width: 3, height: "100%", background: k.color }} />
            <div style={{ fontFamily: fonts.mono, fontSize: 10, color: "#8a94a6", letterSpacing: "0.1em", textTransform: "uppercase" }}>
              {k.label}
            </div>
            <div style={{ fontFamily: fonts.grotesk, fontWeight: 600, fontSize: 26, marginTop: 8, letterSpacing: "-0.01em" }}>
              {k.value}
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 5, marginTop: 6 }}>
              <span style={{ fontFamily: fonts.mono, fontSize: 11, color: k.positive ? palette.pos : palette.neg }}>{k.delta}</span>
              <span style={{ fontFamily: fonts.mono, fontSize: 10, color: "#5b6675" }}>{k.deltaLabel}</span>
            </div>
          </div>
        ))}
      </div>

      {/* Mid grid */}
      <div style={{ display: "grid", gridTemplateColumns: "1.6fr 1fr", gap: 12, marginBottom: 16 }}>
        <div style={card}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 6 }}>
            <div style={sectionTitle}>Market Sentiment Index</div>
            <div style={{ fontFamily: fonts.mono, fontSize: 11, color: "#8a94a6" }}>24h · hourly</div>
          </div>
          <TrendChart />
        </div>
        <div style={card}>
          <div style={{ ...sectionTitle, marginBottom: 12 }}>Trending Topics</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 11 }}>
            {trendingTop.map((t) => (
              <div key={t.rank} style={{ display: "flex", alignItems: "center", gap: 11 }}>
                <span style={{ fontFamily: fonts.mono, fontSize: 12, color: "#5b6675", width: 16 }}>{t.rank}</span>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 12.5, fontWeight: 500, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                    {t.topic}
                  </div>
                  <div style={{ height: 3, background: "#1c2330", borderRadius: 2, marginTop: 5, overflow: "hidden" }}>
                    <div style={{ height: "100%", width: t.barWidth, background: ACCENT }} />
                  </div>
                </div>
                <span style={{ fontFamily: fonts.mono, fontSize: 11, color: t.changeColor, width: 46, textAlign: "right" }}>
                  {t.change}
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Bottom grid */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
        <div style={card}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
            <div style={sectionTitle}>Active Event Clusters</div>
            <Hover as="button" onClick={() => setView("clusters")} style={linkBtn}>
              VIEW ALL →
            </Hover>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {clusters.map((c, i) => {
              const sc = sentColor(c.sent);
              return (
                <div key={i} style={{ border: "1px solid #1c2330", borderRadius: 8, padding: "11px 13px", background: "#0e131a" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 5 }}>
                    <span
                      style={{
                        fontFamily: fonts.mono,
                        fontSize: 9,
                        color: sc,
                        border: `1px solid ${sc}55`,
                        borderRadius: 4,
                        padding: "1px 5px",
                        letterSpacing: "0.06em",
                      }}
                    >
                      {c.sent > 0.15 ? "POSITIVE" : c.sent < -0.15 ? "NEGATIVE" : "NEUTRAL"}
                    </span>
                    <span style={{ fontFamily: fonts.mono, fontSize: 10, color: "#5b6675" }}>
                      {c.count} articles · {c.sources} sources
                    </span>
                  </div>
                  <div style={{ fontSize: 13, fontWeight: 500, lineHeight: 1.35 }}>{c.title}</div>
                </div>
              );
            })}
          </div>
        </div>

        <div style={card}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
            <div style={sectionTitle}>Latest Feed</div>
            <Hover as="button" onClick={() => setView("feed")} style={linkBtn}>
              OPEN FEED →
            </Hover>
          </div>
          <div style={{ display: "flex", flexDirection: "column" }}>
            {feedTop.map((a, i) => (
              <div key={i} style={{ display: "flex", gap: 11, padding: "9px 0", borderBottom: "1px solid #161d28" }}>
                <span style={{ width: 6, height: 6, flex: "none", borderRadius: "50%", background: sentColor(a.sent), marginTop: 6 }} />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 12.5, lineHeight: 1.35, fontWeight: 500 }}>{a.title}</div>
                  <div style={{ fontFamily: fonts.mono, fontSize: 10, color: "#5b6675", marginTop: 4 }}>
                    {a.source} · {a.time}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
