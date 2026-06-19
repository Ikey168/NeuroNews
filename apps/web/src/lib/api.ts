// Thin typed client over the NeuroNews FastAPI backend.
//
// In development, requests use relative paths and are proxied to the backend
// by Vite (see vite.config.ts). In other environments set VITE_API_BASE_URL
// to the absolute backend origin (e.g. https://api.neuronews.example).

const BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "");
const DEFAULT_TIMEOUT_MS = 8000;

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status?: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, params?: Record<string, string | number | undefined>): Promise<T> {
  const url = new URL(BASE_URL + path, BASE_URL || window.location.origin);
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined) url.searchParams.set(k, String(v));
    }
  }

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), DEFAULT_TIMEOUT_MS);
  try {
    const res = await fetch(url.toString(), {
      headers: { Accept: "application/json" },
      signal: controller.signal,
    });
    if (!res.ok) {
      throw new ApiError(`Request failed: ${path}`, res.status);
    }
    return (await res.json()) as T;
  } catch (err) {
    if (err instanceof ApiError) throw err;
    throw new ApiError(err instanceof Error ? err.message : `Request error: ${path}`);
  } finally {
    clearTimeout(timer);
  }
}

// ---------- raw backend response shapes ----------

export interface RawArticle {
  id: string;
  title: string;
  url: string;
  publish_date: string | null;
  source: string;
  category: string;
  sentiment: { score: number | null; label: string | null };
}

export interface RawEventCluster {
  cluster_id: string;
  cluster_name: string;
  event_type: string;
  category: string;
  cluster_size: number;
  trending_score: number;
  impact_score: number;
  velocity_score: number;
  first_article_date: string;
  last_article_date: string;
  primary_sources: string[];
  key_entities: string[];
  status: string;
}

export interface RawBreakingNews {
  cluster_id: string;
  cluster_name: string;
  category: string;
  trending_score: number;
  sample_headlines: string | null;
}

export interface RawTrendingTopic {
  topic?: string;
  topic_name?: string;
  article_count: number;
  avg_probability?: number;
  avg_sentiment?: number;
  growth_rate?: number;
}

export interface RawTrendingResponse {
  trending_topics: RawTrendingTopic[];
}

export interface RawSentimentSummary {
  // shape varies; the adapter reads defensively
  [key: string]: unknown;
}

export interface RawKgStats {
  [key: string]: unknown;
}

export interface RawInfluencer {
  entity?: string;
  name?: string;
  entity_type?: string;
  type?: string;
  influence_score?: number;
  connections?: number;
  degree?: number;
}

// ---------- endpoint calls ----------

export const api = {
  articles: (params?: { category?: string; source?: string }) =>
    request<RawArticle[]>("/api/v1/news/articles", params),

  eventClusters: (params?: { limit?: number }) =>
    request<RawEventCluster[]>("/api/v1/events/clusters", params),

  breakingNews: (params?: { limit?: number; hours_back?: number }) =>
    request<RawBreakingNews[]>("/api/v1/breaking_news", params),

  trendingTopics: (params?: { days?: number }) =>
    request<RawTrendingResponse>("/topics/trending", params),

  sentimentSummary: () => request<RawSentimentSummary>("/news_sentiment/summary"),

  sentimentTopics: () => request<RawSentimentSummary>("/news_sentiment/topics"),

  knowledgeGraphStats: () => request<RawKgStats>("/api/v1/knowledge_graph_stats"),

  topInfluencers: (params?: { limit?: number }) =>
    request<RawInfluencer[]>("/api/influence/top-influencers", params),
};
