import { ACCENT, palette, fonts } from "../theme";
import { useTopEntities } from "../lib/queries";
import PageHeader from "../components/PageHeader";
import SourceBadge from "../components/SourceBadge";
import EntityGraph from "../components/charts/EntityGraph";
import type { LegendItem } from "../types";

const legend: LegendItem[] = [
  { label: "Organizations", color: ACCENT, count: "5,210" },
  { label: "People", color: palette.blue, count: "3,840" },
  { label: "Topics", color: palette.amber, count: "2,610" },
  { label: "Places", color: palette.violet, count: "749" },
];

const panel = {
  background: "#11151c",
  border: "1px solid #1c2330",
  borderRadius: 10,
  padding: "14px 16px",
} as const;

const panelLabel = {
  fontFamily: fonts.mono,
  fontSize: 10,
  color: "#8a94a6",
  letterSpacing: "0.12em",
  marginBottom: 11,
} as const;

export default function EntityGraphView() {
  const { data: topEntities, source, isLoading } = useTopEntities();

  return (
    <div>
      <PageHeader
        title="Entity Relationship Graph"
        subtitle="12 entities · 13 co-occurrence links · 24h window"
        right={<SourceBadge source={source} isLoading={isLoading} />}
      />
      <div style={{ display: "grid", gridTemplateColumns: "1fr 280px", gap: 12 }}>
        <div style={{ background: "#0e131a", border: "1px solid #1c2330", borderRadius: 10, overflow: "hidden" }}>
          <EntityGraph />
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <div style={panel}>
            <div style={panelLabel}>ENTITY TYPES</div>
            <div style={{ display: "flex", flexDirection: "column", gap: 9 }}>
              {legend.map((l) => (
                <div key={l.label} style={{ display: "flex", alignItems: "center", gap: 9 }}>
                  <span style={{ width: 10, height: 10, borderRadius: "50%", background: l.color }} />
                  <span style={{ flex: 1, fontSize: 12.5 }}>{l.label}</span>
                  <span style={{ fontFamily: fonts.mono, fontSize: 11, color: "#5b6675" }}>{l.count}</span>
                </div>
              ))}
            </div>
          </div>
          <div style={panel}>
            <div style={panelLabel}>TOP CONNECTED</div>
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {topEntities.map((e) => (
                <div key={e.name} style={{ display: "flex", alignItems: "center", gap: 10 }}>
                  <span style={{ width: 8, height: 8, flex: "none", borderRadius: "50%", background: e.color }} />
                  <span
                    style={{
                      flex: 1,
                      fontSize: 12.5,
                      fontWeight: 500,
                      whiteSpace: "nowrap",
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                    }}
                  >
                    {e.name}
                  </span>
                  <span style={{ fontFamily: fonts.mono, fontSize: 11, color: "#8a94a6" }}>{e.links}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
