// React Query hooks. Each hook attempts the live backend and transparently
// falls back to the design dataset when the API is unreachable, so the UI is
// always pixel-perfect and runnable. `source` reports which path was taken.

import { useQuery } from "@tanstack/react-query";
import { api } from "./api";
import {
  adaptArticles,
  adaptClusters,
  adaptTrending,
  adaptInfluencers,
  adaptTopicSentiment,
  adaptEntityGraph,
  adaptHeatmap,
  adaptDocuments,
  adaptFrameDistribution,
} from "./adapters";
import {
  mockArticles,
  mockClusters,
  mockDocuments,
  mockTrending,
  mockTickerText,
  mockTopicSentiment,
  mockHeatmap,
  mockClaims,
  mockStance,
  mockPositions,
  mockConflicts,
  mockFrameDistribution,
  mockControversyGraph,
} from "../data/mock";
import type { RawClaim, RawStanceSummary, RawActorPosition } from "./api";
import { palette, ACCENT } from "../theme";
import type {
  Article,
  Cluster,
  KnowledgeDocument,
  TrendingTopic,
  TopEntity,
  TopicSentiment,
  LiveGraph,
  Heatmap,
  ClaimResult,
  StanceSummary,
  ActorPosition,
  ConflictPair,
  FrameDistribution,
  SourceType,
  ControversyGraph,
} from "../types";

export type Source = "live" | "demo";
export interface Result<T> {
  data: T;
  source: Source;
  isLoading: boolean;
}

export type BackendStatus = "checking" | "online" | "offline";

const STALE = 60_000;

// Lightweight liveness probe against the backend's /health endpoint. Drives
// the global connection indicator in the top bar and is polled periodically so
// the UI reflects the backend coming up or going down without a reload.
export function useBackendStatus(): BackendStatus {
  const q = useQuery({
    queryKey: ["health"],
    queryFn: async () => {
      const h = await api.health();
      return h?.status ?? "ok";
    },
    staleTime: 15_000,
    refetchInterval: 30_000,
    retry: false,
  });
  if (q.isLoading) return "checking";
  return q.isSuccess ? "online" : "offline";
}

function useWithFallback<T>(key: string, fn: () => Promise<T>, fallback: T): Result<T> {
  const q = useQuery({
    queryKey: [key],
    queryFn: async (): Promise<{ data: T; source: Source }> => {
      try {
        const data = await fn();
        // Treat an empty payload as "no live data" and prefer the demo set.
        if (Array.isArray(data) && data.length === 0) {
          return { data: fallback, source: "demo" };
        }
        return { data, source: "live" };
      } catch {
        return { data: fallback, source: "demo" };
      }
    },
    staleTime: STALE,
    retry: false,
  });
  return {
    data: q.data?.data ?? fallback,
    source: q.data?.source ?? "demo",
    isLoading: q.isLoading,
  };
}

export function useArticles(): Result<Article[]> {
  return useWithFallback("articles", async () => adaptArticles(await api.articles()), mockArticles);
}

export function useClusters(): Result<Cluster[]> {
  return useWithFallback("clusters", async () => adaptClusters(await api.eventClusters()), mockClusters);
}

export function useTrending(): Result<TrendingTopic[]> {
  return useWithFallback(
    "trending",
    async () => adaptTrending(await api.trendingTopics()),
    mockTrending,
  );
}

const mockTopEntities: TopEntity[] = [
  { name: "Federal Reserve", color: ACCENT, links: 42 },
  { name: "Nvidia", color: ACCENT, links: 38 },
  { name: "European Union", color: ACCENT, links: 31 },
  { name: "Microsoft", color: ACCENT, links: 27 },
  { name: "AI", color: palette.amber, links: 24 },
];

export function useTopEntities(): Result<TopEntity[]> {
  return useWithFallback(
    "topEntities",
    async () => adaptInfluencers(await api.topInfluencers({ limit: 5 })),
    mockTopEntities,
  );
}

const mockEntityGraph: LiveGraph = {
  nodes: [
    { id: "fed", label: "Federal Reserve", type: "org", color: ACCENT, count: 9, degree: 4 },
    { id: "powell", label: "Jerome Powell", type: "person", color: palette.blue, count: 5, degree: 2 },
    { id: "nvda", label: "Nvidia", type: "org", color: ACCENT, count: 8, degree: 3 },
    { id: "huang", label: "Jensen Huang", type: "person", color: palette.blue, count: 4, degree: 1 },
    { id: "ai", label: "AI", type: "topic", color: palette.amber, count: 11, degree: 4 },
    { id: "eu", label: "European Union", type: "org", color: ACCENT, count: 7, degree: 3 },
    { id: "msft", label: "Microsoft", type: "org", color: ACCENT, count: 6, degree: 2 },
    { id: "opec", label: "OPEC", type: "org", color: ACCENT, count: 5, degree: 1 },
    { id: "oil", label: "Crude Oil", type: "topic", color: palette.amber, count: 5, degree: 1 },
    { id: "ukraine", label: "Ukraine", type: "place", color: palette.violet, count: 6, degree: 2 },
  ],
  edges: [
    ["fed", "powell", 5], ["fed", "ai", 3], ["nvda", "huang", 4], ["nvda", "ai", 6],
    ["ai", "msft", 3], ["eu", "msft", 2], ["eu", "ukraine", 4], ["opec", "oil", 5],
    ["nvda", "fed", 2], ["ai", "eu", 2],
  ],
  nodeCount: 10,
  edgeCount: 10,
};

export function useEntityGraph(): Result<LiveGraph> {
  return useWithFallback(
    "entityGraph",
    async () => {
      const g = adaptEntityGraph(await api.entityGraph({ days: 7, max_nodes: 16 }));
      if (!g.nodes.length) throw new Error("empty");
      return g;
    },
    mockEntityGraph,
  );
}

export function useTopicSentiment(): Result<TopicSentiment[]> {
  return useWithFallback(
    "topicSentiment",
    async () => adaptTopicSentiment(await api.sentimentTopics({ days: 7 })),
    mockTopicSentiment,
  );
}

const mockSentimentHeatmap: Heatmap = {
  topics: ["Economy", "Technology", "Energy", "Policy", "Health", "Markets"],
  cols: mockHeatmap.cols,
  labels: Array.from({ length: mockHeatmap.cols }, (_, i) =>
    i % 2 === 0 ? String(i) : "",
  ),
  seed: mockHeatmap.seed,
};

export function useSentimentHeatmap(): Result<Heatmap> {
  return useWithFallback(
    "sentimentHeatmap",
    async () => {
      const hm = adaptHeatmap(await api.sentimentHeatmap({ days: 14 }));
      if (!hm.topics.length) throw new Error("empty");
      return hm;
    },
    mockSentimentHeatmap,
  );
}

export function useDocuments(sourceType?: string): Result<KnowledgeDocument[]> {
  return useWithFallback(
    `documents-${sourceType ?? "all"}`,
    async () => {
      const raw = await api.documents(sourceType ? { source_type: sourceType } : undefined);
      return adaptDocuments(raw);
    },
    sourceType
      ? mockDocuments.filter((d) => d.source_type === sourceType)
      : mockDocuments,
  );
}

export function usePackStatus(): { newsPack: boolean; isLoading: boolean } {
  const q = useQuery({
    queryKey: ["packStatus"],
    queryFn: async () => {
      const root = await api.packStatus();
      return { newsPack: root.domain_packs?.news ?? true };
    },
    staleTime: 60_000,
    retry: false,
  });
  // Default to news-pack enabled so views render while checking or when offline.
  return { newsPack: q.data?.newsPack ?? true, isLoading: q.isLoading };
}

export function useTicker(): Result<string> {
  return useWithFallback(
    "ticker",
    async () => {
      const news = await api.breakingNews({ limit: 6 });
      if (!news.length) throw new Error("empty");
      const text =
        "  " +
        news
          .map((n) => n.sample_headlines?.split("|")[0]?.trim() || n.cluster_name)
          .filter(Boolean)
          .join("  ●  ");
      return `  ●${text}  `;
    },
    mockTickerText,
  );
}

// ─── Argument Mining ─────────────────────────────────────────────────────────

export function useArgumentClaims(params?: { source_type?: string; topic?: string }): Result<ClaimResult[]> {
  const key = `argumentClaims-${params?.source_type ?? "all"}-${params?.topic ?? ""}`;
  return useWithFallback(
    key,
    async (): Promise<ClaimResult[]> => {
      const res = await api.argumentClaims(params);
      return res.claims.map((r: RawClaim) => ({
        document_id: r.document_id,
        source_type: r.source_type as SourceType,
        text: r.claim_text,
        is_claim: true,
        confidence: r.confidence ?? 0,
        factcheck_verdict: null,
        title: "",
      }));
    },
    mockClaims,
  );
}

export function useArgumentStance(params?: { source_type?: string; topic?: string }): Result<StanceSummary[]> {
  const key = `argumentStance-${params?.source_type ?? "all"}-${params?.topic ?? ""}`;
  return useWithFallback(
    key,
    async (): Promise<StanceSummary[]> => {
      const res = await api.argumentStance(params);
      return res.stances.map((r: RawStanceSummary) => ({
        topic: r.topic,
        supportive: r.supportive,
        critical: r.critical,
        neutral: r.neutral,
        ambiguous: r.ambiguous,
        total: r.total,
        drift: r.drift,
        by_source: r.by_source as StanceSummary["by_source"],
      }));
    },
    mockStance,
  );
}

export function useArgumentPositions(params?: { actor?: string; topic?: string; source_type?: string }): Result<ActorPosition[]> {
  const key = `argumentPositions-${params?.source_type ?? "all"}-${params?.topic ?? ""}`;
  return useWithFallback(
    key,
    async (): Promise<ActorPosition[]> => {
      const res = await api.argumentPositions(params);
      return res.positions.map((r: RawActorPosition) => ({
        actor: r.actor,
        position: r.position,
        stance: r.stance as ActorPosition["stance"],
        date: r.date ?? "",
        source_type: r.source_type as SourceType,
        document_id: r.document_id,
        topic: r.topic,
      }));
    },
    mockPositions,
  );
}

export function useArgumentControversy(params?: { topic?: string; source_type?: string }): Result<ConflictPair[]> {
  const key = `argumentControversy-${params?.source_type ?? "all"}-${params?.topic ?? ""}`;
  return useWithFallback(
    key,
    async (): Promise<ConflictPair[]> => {
      const res = await api.argumentControversy(params);
      return res.conflicts;
    },
    mockConflicts,
  );
}

export function useArgumentControversyGraph(params?: { topic?: string; source_type?: string; date_range?: string }): Result<ControversyGraph> {
  const key = `argumentControversyGraph-${params?.source_type ?? "all"}-${params?.topic ?? ""}-${params?.date_range ?? ""}`;
  return useWithFallback(
    key,
    async (): Promise<ControversyGraph> => {
      const res = await api.argumentControversyGraph(params);
      if (!res.nodes.length) throw new Error("empty");
      return res;
    },
    mockControversyGraph,
  );
}

export function useArgumentFrames(sourceType?: string): Result<FrameDistribution> {
  return useWithFallback(
    `argumentFrames-${sourceType ?? "all"}`,
    async () => {
      const raw = await api.argumentFrames(sourceType ? { source_type: sourceType } : undefined);
      if (!raw.distribution || Object.keys(raw.distribution).length === 0) throw new Error("empty");
      return adaptFrameDistribution(raw);
    },
    sourceType && sourceType !== "all"
      ? { ...mockFrameDistribution, distribution: mockFrameDistribution.distribution, source_type_filter: sourceType }
      : mockFrameDistribution,
  );
}
