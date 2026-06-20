import { palette, fonts } from "../theme";
import { sentColor, fmt } from "../lib/sentiment";
import { useTopicSentiment, useSentimentHeatmap } from "../lib/queries";
import PageHeader from "../components/PageHeader";
import SourceBadge from "../components/SourceBadge";
import Heatmap from "../components/charts/Heatmap";
import type { SentimentStat, TopicSentiment } from "../types";

function deriveStats(topics: TopicSentiment[]): SentimentStat[] {
  if (!topics.length) return [];
  const totalArticles = topics.reduce((s, t) => s + t.articles, 0) || 1;
  const net = topics.reduce((s, t) => s + t.avgScore * t.articles, 0) / totalArticles;
  const sorted = [...topics].sort((a, b) => b.avgScore - a.avgScore);
  const top = sorted[0];
  const bottom = sorted[sorted.length - 1];
  return [
    { label: "Net Sentiment", value: fmt(net), color: sentColor(net), note: `weighted across ${topics.length} topics` },
    { label: "Most Positive", value: top.topic, color: palette.pos, note: `${fmt(top.avgScore)} avg · ${top.articles} articles` },
    { label: "Most Negative", value: bottom.topic, color: palette.neg, note: `${fmt(bottom.avgScore)} avg · ${bottom.articles} articles` },
  ];
}

const card = {
  background: "#11151c",
  border: "1px solid #1c2330",
  borderRadius: 10,
} as const;

export default function Sentiment() {
  const { data: topics, source, isLoading } = useTopicSentiment();
  const { data: heatmap, source: heatmapSource, isLoading: heatmapLoading } = useSentimentHeatmap();
  const stats = deriveStats(topics);
  const maxA = Math.max(1, ...topics.map((t) => t.articles));

  return (
    <div>
      <PageHeader
        title="Sentiment Analysis"
        subtitle="Per-topic sentiment · last 7 days"
        right={<SourceBadge source={source} isLoading={isLoading} />}
      />

      {/* Stat cards — derived live from /news_sentiment/topics */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 12, marginBottom: 12 }}>
        {stats.map((s) => (
          <div key={s.label} style={{ ...card, padding: "15px 17px" }}>
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

      {/* Live topic breakdown */}
      <div style={{ ...card, padding: "18px 20px", marginBottom: 12 }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 14 }}>
          <div style={{ fontFamily: fonts.grotesk, fontWeight: 600, fontSize: 14 }}>Topic Sentiment</div>
          <div style={{ fontFamily: fonts.mono, fontSize: 10, color: "#8a94a6" }}>avg score · article volume</div>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 11 }}>
          {topics.slice(0, 10).map((t) => {
            const c = sentColor(t.avgScore);
            // Center a diverging bar at 50%: positive grows right, negative left.
            const pct = Math.min(Math.abs(t.avgScore), 1) * 50;
            return (
              <div key={t.topic} style={{ display: "flex", alignItems: "center", gap: 12 }}>
                <span style={{ width: 110, flex: "none", fontSize: 12.5, fontWeight: 500, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                  {t.topic}
                </span>
                <div style={{ flex: 1, position: "relative", height: 8, background: "#0e131a", borderRadius: 3 }}>
                  <div style={{ position: "absolute", left: "50%", top: 0, bottom: 0, width: 1, background: "#2a3340" }} />
                  <div
                    style={{
                      position: "absolute",
                      top: 0,
                      bottom: 0,
                      borderRadius: 3,
                      background: c,
                      ...(t.avgScore >= 0
                        ? { left: "50%", width: `${pct}%` }
                        : { right: "50%", width: `${pct}%` }),
                    }}
                  />
                </div>
                <span style={{ fontFamily: fonts.mono, fontSize: 11.5, color: c, width: 48, textAlign: "right" }}>
                  {fmt(t.avgScore)}
                </span>
                <span style={{ fontFamily: fonts.mono, fontSize: 10.5, color: "#5b6675", width: 52, textAlign: "right" }}>
                  {Math.round((t.articles / maxA) * 100)}%
                </span>
              </div>
            );
          })}
        </div>
      </div>

      {/* Category × day sentiment heatmap — live average sentiment per bucket */}
      <div style={{ ...card, padding: "18px 20px" }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 14 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <div style={{ fontFamily: fonts.grotesk, fontWeight: 600, fontSize: 14 }}>Sentiment Heatmap</div>
            <SourceBadge source={heatmapSource} isLoading={heatmapLoading} />
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 10, fontFamily: fonts.mono, fontSize: 10, color: "#8a94a6" }}>
            <span style={{ color: "#FF5C5C" }}>■</span> negative
            <span style={{ color: "#8B95A5" }}>■</span> neutral
            <span style={{ color: "#3DD68C" }}>■</span> positive
          </div>
        </div>
        <Heatmap data={heatmap} />
      </div>
    </div>
  );
}
