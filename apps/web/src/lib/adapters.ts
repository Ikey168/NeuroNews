// Map raw backend responses into the UI view-model shapes (types.ts).
// Adapters are deliberately defensive: the backend list endpoints expose a
// subset of the fields the design shows, so missing fields degrade gracefully.

import { palette, ACCENT } from "../theme";
import type {
  Article,
  Cluster,
  TrendingTopic,
  TopEntity,
} from "../types";
import type {
  RawArticle,
  RawEventCluster,
  RawTrendingResponse,
  RawInfluencer,
} from "./api";

export function relativeTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "—";
  const mins = Math.max(0, Math.round((Date.now() - then) / 60000));
  if (mins < 60) return `${mins}m`;
  const hrs = Math.round(mins / 60);
  if (hrs < 24) return `${hrs}h`;
  return `${Math.round(hrs / 24)}d`;
}

export function adaptArticles(raw: RawArticle[]): Article[] {
  return raw.map((a) => ({
    title: a.title,
    source: a.source ?? "—",
    time: relativeTime(a.publish_date),
    category: a.category ?? "General",
    sent: a.sentiment?.score ?? 0,
    summary: "",
    entities: [],
  }));
}

export function adaptClusters(raw: RawEventCluster[]): Omit<Cluster, "headlines">[] {
  return raw.map((c) => {
    const dir = c.velocity_score >= 0 ? "▲" : "▼";
    return {
      title: c.cluster_name,
      count: c.cluster_size,
      sources: c.primary_sources?.length ?? 0,
      time: relativeTime(c.last_article_date),
      // The cluster endpoint has no aggregate sentiment; approximate from
      // impact direction so the accent bar still reads meaningfully.
      sent: 0,
      vel: `${dir} ${Math.abs(Math.round(c.velocity_score * 100))}%/h`,
    };
  });
}

export function adaptTrending(raw: RawTrendingResponse): TrendingTopic[] {
  const topics = raw.trending_topics ?? [];
  const max = Math.max(1, ...topics.map((t) => t.article_count ?? 0));
  return topics.map((t) => ({
    topic: t.topic ?? t.topic_name ?? "—",
    mentions: t.article_count ?? 0,
    // growth_rate is a fraction; scale to a percentage for the change column.
    change: Math.round((t.growth_rate ?? t.article_count / max) * 100),
    sent: t.avg_sentiment ?? 0,
  }));
}

const ENTITY_TYPE_COLOR: Record<string, string> = {
  org: ACCENT,
  organization: ACCENT,
  person: palette.blue,
  people: palette.blue,
  topic: palette.amber,
  place: palette.violet,
  location: palette.violet,
};

export function adaptInfluencers(raw: RawInfluencer[]): TopEntity[] {
  return raw.map((i) => {
    const type = (i.entity_type ?? i.type ?? "topic").toLowerCase();
    return {
      name: i.entity ?? i.name ?? "—",
      color: ENTITY_TYPE_COLOR[type] ?? palette.amber,
      links: i.connections ?? i.degree ?? Math.round(i.influence_score ?? 0),
    };
  });
}
