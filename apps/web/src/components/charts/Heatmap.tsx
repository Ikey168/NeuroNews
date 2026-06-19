import { fonts } from "../../theme";
import { mockHeatmap } from "../../data/mock";

// Sentiment heatmap (topics × 16 hourly columns). Ported from `buildHeatmap`.
function cellColor(v: number): string {
  if (v > 0.05) {
    const t = Math.min(v / 0.7, 1);
    return `rgba(61,214,140,${0.18 + 0.7 * t})`;
  }
  if (v < -0.05) {
    const t = Math.min(-v / 0.7, 1);
    return `rgba(255,92,92,${0.18 + 0.7 * t})`;
  }
  return "rgba(139,149,165,0.16)";
}

export default function Heatmap() {
  const { topics, cols, seed } = mockHeatmap;
  const nowHour = new Date().getUTCHours();
  const hours = Array.from({ length: cols }, (_, i) => ((nowHour - (cols - 1 - i)) % 24 + 24) % 24);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
      {topics.map((t, ri) => (
        <div key={ri} style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <div style={{ width: 78, flex: "none", fontSize: 11.5, color: "#9aa4b2", fontFamily: fonts.sans }}>
            {t}
          </div>
          <div style={{ flex: 1, display: "grid", gridTemplateColumns: `repeat(${cols},1fr)`, gap: 4 }}>
            {seed[ri].map((v, ci) => (
              <div
                key={ci}
                title={`${t} · ${v.toFixed(2)}`}
                style={{ height: 26, borderRadius: 3, background: cellColor(v) }}
              />
            ))}
          </div>
        </div>
      ))}
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginTop: 2 }}>
        <div style={{ width: 78, flex: "none" }} />
        <div style={{ flex: 1, display: "grid", gridTemplateColumns: `repeat(${cols},1fr)`, gap: 4 }}>
          {hours.map((h, i) => (
            <div key={i} style={{ textAlign: "center", fontFamily: fonts.mono, fontSize: 9, color: "#4b5563" }}>
              {i % 2 === 0 ? String(h).padStart(2, "0") : ""}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
