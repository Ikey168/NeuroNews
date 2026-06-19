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
} from "./adapters";
import {
  mockArticles,
  mockClusters,
  mockTrending,
  mockTickerText,
  mockTopicSentiment,
} from "../data/mock";
import { palette, ACCENT } from "../theme";
import type {
  Article,
  Cluster,
  TrendingTopic,
  TopEntity,
  TopicSentiment,
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

export function useClusters(): Result<Omit<Cluster, "headlines">[]> {
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

export function useTopicSentiment(): Result<TopicSentiment[]> {
  return useWithFallback(
    "topicSentiment",
    async () => adaptTopicSentiment(await api.sentimentTopics({ days: 7 })),
    mockTopicSentiment,
  );
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
