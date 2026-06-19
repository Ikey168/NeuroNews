import { palette, fonts } from "../theme";
import { sentColor, sentLabel } from "../lib/sentiment";
import { useArticles, useClusters } from "../lib/queries";
import PageHeader from "../components/PageHeader";

export default function Clusters() {
  const { data: clustersRaw } = useClusters();
  const { data: articles } = useArticles();

  const clusters = clustersRaw.map((c, i) => ({
    ...c,
    headlines: articles.length
      ? [articles[i % articles.length].title, articles[(i + 3) % articles.length].title]
      : [],
  }));

  return (
    <div>
      <PageHeader
        title="Event Clusters"
        subtitle={`${clusters.length} active clusters · grouped by semantic similarity`}
      />
      <div style={{ display: "grid", gridTemplateColumns: "repeat(2,1fr)", gap: 12 }}>
        {clusters.map((c, i) => {
          const sc = sentColor(c.sent);
          const velColor = c.vel[0] === "▲" ? palette.pos : palette.neg;
          return (
            <div
              key={i}
              style={{
                background: "#11151c",
                border: "1px solid #1c2330",
                borderRadius: 10,
                padding: "17px 19px",
                borderLeft: `3px solid ${sc}`,
              }}
            >
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 9 }}>
                <span style={{ fontFamily: fonts.mono, fontSize: 9.5, color: sc, letterSpacing: "0.08em" }}>
                  {sentLabel(c.sent)}
                </span>
                <span style={{ fontFamily: fonts.mono, fontSize: 10, color: velColor }}>{c.vel}</span>
              </div>
              <h3 style={{ fontFamily: fonts.grotesk, fontWeight: 600, fontSize: 15.5, margin: "0 0 8px", lineHeight: 1.32 }}>
                {c.title}
              </h3>
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 8,
                  fontFamily: fonts.mono,
                  fontSize: 10.5,
                  color: "#5b6675",
                  marginBottom: 11,
                }}
              >
                <span>{c.count} articles</span>
                <span>·</span>
                <span>{c.sources} sources</span>
                <span>·</span>
                <span>{c.time}</span>
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 6, borderTop: "1px solid #1c2330", paddingTop: 11 }}>
                {c.headlines.map((h, hi) => (
                  <div key={hi} style={{ display: "flex", gap: 8, alignItems: "flex-start" }}>
                    <span style={{ color: "#3a4554", fontSize: 11, marginTop: 1 }}>›</span>
                    <span style={{ flex: 1, fontSize: 12, color: "#9aa4b2", lineHeight: 1.4 }}>{h}</span>
                  </div>
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
