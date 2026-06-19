import { palette, fonts } from "../theme";
import PageHeader from "../components/PageHeader";
import Heatmap from "../components/charts/Heatmap";
import type { SentimentStat } from "../types";

const stats: SentimentStat[] = [
  { label: "Net Sentiment", value: "+0.18", color: palette.pos, note: "aggregate across all topics" },
  { label: "Most Positive", value: "Science", color: palette.pos, note: "+0.58 avg · fusion, health" },
  { label: "Most Negative", value: "Finance", color: palette.neg, note: "-0.44 avg · CRE, credit" },
];

export default function Sentiment() {
  return (
    <div>
      <PageHeader title="Sentiment Analysis" subtitle="Topic × time heatmap · 16-hour rolling window" />

      <div style={{ background: "#11151c", border: "1px solid #1c2330", borderRadius: 10, padding: "18px 20px", marginBottom: 12 }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 14 }}>
          <div style={{ fontFamily: fonts.grotesk, fontWeight: 600, fontSize: 14 }}>Sentiment Heatmap</div>
          <div style={{ display: "flex", alignItems: "center", gap: 10, fontFamily: fonts.mono, fontSize: 10, color: "#8a94a6" }}>
            <span style={{ color: "#FF5C5C" }}>■</span> negative
            <span style={{ color: "#8B95A5" }}>■</span> neutral
            <span style={{ color: "#3DD68C" }}>■</span> positive
          </div>
        </div>
        <Heatmap />
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 12 }}>
        {stats.map((s) => (
          <div key={s.label} style={{ background: "#11151c", border: "1px solid #1c2330", borderRadius: 10, padding: "15px 17px" }}>
            <div style={{ fontFamily: fonts.mono, fontSize: 10, color: "#8a94a6", letterSpacing: "0.1em", textTransform: "uppercase" }}>
              {s.label}
            </div>
            <div style={{ fontFamily: fonts.grotesk, fontWeight: 600, fontSize: 24, marginTop: 8, color: s.color }}>
              {s.value}
            </div>
            <div style={{ fontFamily: fonts.mono, fontSize: 10.5, color: "#5b6675", marginTop: 4 }}>{s.note}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
