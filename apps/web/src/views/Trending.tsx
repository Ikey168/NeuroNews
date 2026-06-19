import { ACCENT, palette, fonts } from "../theme";
import { sentColor, fmt } from "../lib/sentiment";
import { useTrending } from "../lib/queries";
import PageHeader from "../components/PageHeader";
import SourceBadge from "../components/SourceBadge";
import Hover from "../components/Hover";

const GRID = "50px 1fr 130px 110px 90px";

export default function Trending() {
  const { data: trending, source, isLoading } = useTrending();
  const maxM = Math.max(1, ...trending.map((t) => t.mentions));

  const rows = trending.map((t, i) => ({
    rank: i + 1,
    topic: t.topic,
    mentions: t.mentions.toLocaleString(),
    barWidth: Math.round((t.mentions / maxM) * 100) + "%",
    change: (t.change >= 0 ? "+" : "") + t.change + "%",
    changeColor: t.change >= 0 ? palette.pos : palette.neg,
    sentScore: fmt(t.sent),
    sentColor: sentColor(t.sent),
    rankColor: i < 3 ? ACCENT : "#c7cdd6",
  }));

  return (
    <div>
      <PageHeader
        title="Trending Topics"
        subtitle="Ranked by mention velocity · 24h"
        right={<SourceBadge source={source} isLoading={isLoading} />}
      />
      <div style={{ background: "#11151c", border: "1px solid #1c2330", borderRadius: 10, overflow: "hidden" }}>
        <div
          style={{
            display: "grid",
            gridTemplateColumns: GRID,
            gap: 14,
            padding: "11px 20px",
            borderBottom: "1px solid #1c2330",
            fontFamily: fonts.mono,
            fontSize: 10,
            color: "#5b6675",
            letterSpacing: "0.1em",
          }}
        >
          <span>RANK</span>
          <span>TOPIC</span>
          <span>MENTIONS</span>
          <span>VELOCITY</span>
          <span style={{ textAlign: "right" }}>SENTIMENT</span>
        </div>
        {rows.map((t) => (
          <Hover
            key={t.rank}
            style={{
              display: "grid",
              gridTemplateColumns: GRID,
              gap: 14,
              padding: "13px 20px",
              borderBottom: "1px solid #161d28",
              alignItems: "center",
            }}
            hoverStyle={{ background: "#0e131a" }}
          >
            <span style={{ fontFamily: fonts.grotesk, fontWeight: 600, fontSize: 15, color: t.rankColor }}>{t.rank}</span>
            <span style={{ fontSize: 13.5, fontWeight: 500 }}>{t.topic}</span>
            <span style={{ fontFamily: fonts.mono, fontSize: 12, color: "#c7cdd6" }}>{t.mentions}</span>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <div style={{ flex: 1, height: 4, background: "#1c2330", borderRadius: 2, overflow: "hidden" }}>
                <div style={{ height: "100%", width: t.barWidth, background: ACCENT }} />
              </div>
              <span style={{ fontFamily: fonts.mono, fontSize: 10.5, color: t.changeColor, width: 38, textAlign: "right" }}>
                {t.change}
              </span>
            </div>
            <span style={{ fontFamily: fonts.mono, fontSize: 12, color: t.sentColor, textAlign: "right" }}>{t.sentScore}</span>
          </Hover>
        ))}
      </div>
    </div>
  );
}
