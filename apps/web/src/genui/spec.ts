// ui-spec-v1 — the wire format between the backend planner (src/genui) and
// this renderer. Mirrors contracts/schemas/jsonschema/ui-spec-v1.json.

export type PanelType =
  | "note"
  | "kpi_row"
  | "articles"
  | "trending"
  | "clusters"
  | "sentiment_heatmap"
  | "topic_sentiment"
  | "entity_graph"
  | "claims"
  | "stance"
  | "frames"
  | "positions"
  | "controversy"
  | "drift"
  | "outlet_ranking"
  | "outlet_clusters"
  | "actors";

export type Facet =
  | "overview"
  | "trend"
  | "sentiment"
  | "claims"
  | "stance"
  | "actors"
  | "conflict"
  | "sources"
  | "entities"
  | "events";

export type GeneratedBy = "heuristic" | "llm" | "client";

export interface PanelParams {
  topic?: string;
  source_type?: string;
  days?: number;
  [key: string]: string | number | boolean | undefined;
}

export interface PanelSpec {
  id: string;
  type: PanelType;
  title: string;
  span: number;
  priority: number;
  rationale?: string;
  endpoint?: string | null;
  params?: PanelParams;
  body?: string;
}

export interface UISpec {
  spec_version: "ui-spec-v1";
  intent: string;
  title: string;
  subtitle?: string;
  generated_by: GeneratedBy;
  facets?: Facet[];
  topic?: string | null;
  source_type?: string | null;
  panels: PanelSpec[];
}

// Client-side mirror of the backend panel catalog (src/genui/catalog.py):
// which facets each panel serves and how it takes its filters. Used by the
// offline fallback planner and to render pinned panels the spec omitted.
export interface PanelDef {
  type: PanelType;
  title: string;
  facets: Facet[];
  defaultSpan: number;
  topicParam?: boolean;
  sourceTypeParam?: boolean;
  daysParam?: boolean;
  // Upper bound of the endpoint's days validator (mirrors catalog.py).
  maxDays?: number;
}

export const PANEL_CATALOG: PanelDef[] = [
  { type: "kpi_row", title: "Signal summary", facets: ["overview"], defaultSpan: 12 },
  { type: "articles", title: "Latest documents", facets: ["overview", "sentiment"], defaultSpan: 6 },
  { type: "trending", title: "Trending topics", facets: ["overview", "trend", "events"], defaultSpan: 6, daysParam: true, maxDays: 30 },
  { type: "clusters", title: "Event clusters", facets: ["overview", "events"], defaultSpan: 6 },
  { type: "sentiment_heatmap", title: "Sentiment heatmap", facets: ["sentiment", "trend"], defaultSpan: 6, daysParam: true, maxDays: 60 },
  { type: "topic_sentiment", title: "Sentiment by topic", facets: ["sentiment"], defaultSpan: 6, daysParam: true, maxDays: 90 },
  { type: "entity_graph", title: "Entity graph", facets: ["entities", "actors", "overview"], defaultSpan: 6, daysParam: true, maxDays: 30 },
  { type: "claims", title: "Extracted claims", facets: ["claims", "conflict"], defaultSpan: 6, topicParam: true, sourceTypeParam: true },
  { type: "stance", title: "Stance breakdown", facets: ["stance", "conflict", "sentiment"], defaultSpan: 6, topicParam: true, sourceTypeParam: true },
  { type: "frames", title: "Framing by source", facets: ["sources", "claims"], defaultSpan: 6, topicParam: true, sourceTypeParam: true },
  { type: "positions", title: "Actor positions", facets: ["actors", "stance"], defaultSpan: 6, topicParam: true, sourceTypeParam: true },
  { type: "controversy", title: "Conflicts", facets: ["conflict", "claims"], defaultSpan: 6, topicParam: true, sourceTypeParam: true },
  { type: "drift", title: "Stance drift", facets: ["trend", "stance"], defaultSpan: 6, topicParam: true, sourceTypeParam: true },
  { type: "outlet_ranking", title: "Outlet transparency ranking", facets: ["sources"], defaultSpan: 6, sourceTypeParam: true },
  { type: "outlet_clusters", title: "Outlet clusters", facets: ["sources", "entities"], defaultSpan: 6, sourceTypeParam: true },
  { type: "actors", title: "Key actors", facets: ["actors", "entities"], defaultSpan: 6, sourceTypeParam: true },
];

export const PANEL_DEFS: Partial<Record<PanelType, PanelDef>> = Object.fromEntries(
  PANEL_CATALOG.map((p) => [p.type, p]),
);
