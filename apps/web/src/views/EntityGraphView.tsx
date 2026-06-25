import { useMemo } from "react";
import { ACCENT, palette, fonts } from "../theme";
import { useEntityGraph } from "../lib/queries";
import PageHeader from "../components/PageHeader";
import SourceBadge from "../components/SourceBadge";
import EntityGraph from "../components/charts/EntityGraph";
import type { LegendItem } from "../types";

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

const TYPE_LABEL: Record<string, string> = {
  org: "Organizations",
  person: "People",
  topic: "Topics",
  place: "Places",
};
const TYPE_COLOR: Record<string, string> = {
  org: ACCENT,
  person: palette.blue,
  topic: palette.amber,
  place: palette.violet,
};

export default function EntityGraphView() {
  const { data: graph, source, isLoading } = useEntityGraph();

  const legend: LegendItem[] = useMemo(() => {
    const counts: Record<string, number> = { org: 0, person: 0, topic: 0, place: 0 };
    graph.nodes.forEach((n) => {
      counts[n.type] = (counts[n.type] ?? 0) + 1;
    });
    return (["org", "person", "topic", "place"] as const).map((t) => ({
      label: TYPE_LABEL[t],
      color: TYPE_COLOR[t],
      count: String(counts[t] ?? 0),
    }));
  }, [graph]);

  const topConnected = useMemo(
    () => [...graph.nodes].sort((a, b) => b.degree - a.degree).slice(0, 6),
    [graph],
  );

  return (
    <div>
      <PageHeader
        title="Knowledge Graph"
        subtitle={`${graph.nodeCount} entities · ${graph.edgeCount} co-occurrence links · 7d window`}
        right={<SourceBadge source={source} isLoading={isLoading} />}
      />
      <div style={{ display: "grid", gridTemplateColumns: "1fr 280px", gap: 12 }}>
        <div style={{ background: "#0e131a", border: "1px solid #1c2330", borderRadius: 10, overflow: "hidden" }}>
          <EntityGraph data={graph} />
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
              {topConnected.map((e) => (
                <div key={e.id} style={{ display: "flex", alignItems: "center", gap: 10 }}>
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
                    {e.label}
                  </span>
                  <span style={{ fontFamily: fonts.mono, fontSize: 11, color: "#8a94a6" }}>{e.degree}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
