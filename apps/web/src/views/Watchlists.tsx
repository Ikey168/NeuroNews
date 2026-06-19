import { ACCENT, palette, fonts } from "../theme";
import { sentColor, fmt } from "../lib/sentiment";
import { mockWatchlist } from "../data/mock";
import PageHeader from "../components/PageHeader";
import SourceBadge from "../components/SourceBadge";
import Hover from "../components/Hover";
import Sparkline from "../components/charts/Sparkline";

export default function Watchlists() {
  return (
    <div>
      <PageHeader
        title="Watchlists"
        subtitle="Entities & topics you track over time · 8h trend"
        right={
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <SourceBadge source="demo" />
            <Hover
              as="button"
              style={{
                fontFamily: fonts.mono,
                fontSize: 11,
                color: "#8a94a6",
                background: "#11151c",
                border: "1px solid #232a36",
                borderRadius: 7,
                padding: "7px 13px",
                cursor: "pointer",
              }}
              hoverStyle={{ borderColor: "#3a4554", color: "#c7cdd6" }}
            >
              + ADD TO WATCHLIST
            </Hover>
          </div>
        }
      />
      <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 12 }}>
        {mockWatchlist.map((w) => {
          const changeColor = w.change >= 0 ? palette.pos : palette.neg;
          return (
            <div key={w.name} style={{ background: "#11151c", border: "1px solid #1c2330", borderRadius: 11, padding: "16px 18px" }}>
              <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", marginBottom: 14 }}>
                <div>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <span style={{ fontFamily: fonts.grotesk, fontWeight: 600, fontSize: 15 }}>{w.name}</span>
                    {w.alert ? (
                      <span style={{ width: 6, height: 6, borderRadius: "50%", background: ACCENT, boxShadow: `0 0 7px ${ACCENT}` }} />
                    ) : null}
                  </div>
                  <span style={{ fontFamily: fonts.mono, fontSize: 9.5, color: "#5b6675", letterSpacing: "0.08em", textTransform: "uppercase" }}>
                    {w.type}
                  </span>
                </div>
                <Sparkline values={w.spark} color={changeColor} />
              </div>
              <div style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between" }}>
                <div>
                  <div style={{ fontFamily: fonts.grotesk, fontWeight: 600, fontSize: 24 }}>{w.mentions}</div>
                  <div style={{ fontFamily: fonts.mono, fontSize: 9.5, color: "#5b6675", letterSpacing: "0.06em" }}>MENTIONS 24H</div>
                </div>
                <div style={{ textAlign: "right" }}>
                  <div style={{ fontFamily: fonts.mono, fontSize: 13, color: changeColor }}>
                    {(w.change >= 0 ? "+" : "") + w.change + "%"}
                  </div>
                  <div style={{ fontFamily: fonts.mono, fontSize: 11, color: sentColor(w.sent), marginTop: 2 }}>
                    sent {fmt(w.sent)}
                  </div>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
