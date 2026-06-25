// View-model types consumed by the UI components. Backend responses are
// mapped into these shapes by the adapters in lib/adapters.ts.

export interface Article {
  title: string;
  source: string;
  time: string;
  category: string;
  sent: number;
  summary: string;
  entities: string[];
}

export interface Cluster {
  title: string;
  count: number;
  sources: number;
  time: string;
  sent: number;
  vel: string;
  headlines: string[];
}

export interface TrendingTopic {
  topic: string;
  mentions: number;
  change: number;
  sent: number;
}

export interface Kpi {
  label: string;
  value: string;
  delta: string;
  deltaLabel: string;
  color: string;
  positive: boolean;
}

export interface SentimentStat {
  label: string;
  value: string;
  color: string;
  note: string;
}

export interface TopicSentiment {
  topic: string;
  avgScore: number;
  articles: number;
}

export interface Heatmap {
  topics: string[];
  cols: number;
  labels: string[];
  seed: number[][];
}

export interface LegendItem {
  label: string;
  color: string;
  count: string;
}

export interface TopEntity {
  name: string;
  color: string;
  links: number;
}

export interface GraphNode {
  id: string;
  label: string;
  x: number;
  y: number;
  r: number;
  type: "org" | "person" | "topic" | "place";
  color: string;
}

export interface GraphData {
  nodes: GraphNode[];
  edges: [string, string][];
  nodeCount: number;
  edgeCount: number;
}

// Entity graph fetched live from the API (positions computed client-side).
export interface LiveGraphNode {
  id: string;
  label: string;
  type: string;
  color: string;
  count: number;
  degree: number;
}

export interface LiveGraph {
  nodes: LiveGraphNode[];
  edges: [string, string, number][];
  nodeCount: number;
  edgeCount: number;
}

export interface Workspace {
  id: string;
  q: string;
  status: "Active" | "Synthesizing";
  sources: number;
  notes: number;
  updated: string;
  color: string;
}

export interface WorkspaceSource {
  title: string;
  source: string;
  time: string;
  sent: number;
  note: string;
}

export interface WorkspaceDetail {
  sub: string[];
  sources: WorkspaceSource[];
  entities: string[];
}

export interface WatchItem {
  name: string;
  type: "Entity" | "Topic" | "Person";
  mentions: number;
  change: number;
  sent: number;
  spark: number[];
  alert: boolean;
}

export interface Story {
  id: string;
  label: string;
  sent: number;
}

export interface TimelineEvent {
  date: string;
  title: string;
  source: string;
  kind: "Origin" | "Development" | "Reaction" | "Milestone";
  sent: number;
}

export type ViewKey =
  | "dashboard"
  | "library"
  | "knowledge"
  | "reader"
  | "sentiment"
  | "clusters"
  | "trending"
  | "workspaces"
  | "watchlists"
  | "timeline"
  | "arguments";

export type ArgumentTab = "claims" | "stance" | "frames" | "positions" | "controversy";

export interface ClaimResult {
  document_id: string;
  source_type: SourceType;
  text: string;
  is_claim: boolean;
  confidence: number;
  factcheck_verdict: "verified" | "disputed" | "unverified" | null;
  title: string;
}

export interface StanceSummary {
  topic: string;
  supportive: number;
  critical: number;
  neutral: number;
  ambiguous: number;
  total: number;
  by_source: Partial<Record<SourceType, { supportive: number; critical: number; neutral: number; ambiguous: number }>>;
  drift: number[];
}

export interface FrameDistribution {
  distribution: Record<string, number>;
  dominant: string;
  total_documents: number;
  source_type_filter: string | null;
  source: string;
}

export interface ActorPosition {
  actor: string;
  position: string;
  stance: "for" | "against" | "neutral";
  date: string;
  source_type: SourceType;
  document_id: string;
  topic: string;
}

export interface ConflictPair {
  actor_a: string;
  actor_b: string;
  topic: string;
  intensity: number;
  source_count: number;
}

export type SourceType = "news" | "blog" | "paper" | "book" | "transcript" | "web" | "note";

export interface KnowledgeDocument {
  document_id: string;
  source_type: SourceType;
  title: string | null;
  source_id: string | null;
  url: string | null;
  content: string | null;
  created_at: number | null;
  ingested_at: number;
  authors: string[];
  metadata: Record<string, unknown>;
}
