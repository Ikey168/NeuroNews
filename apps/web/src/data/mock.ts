// Data carried over verbatim from the design handoff. Used as a graceful
// fallback when a backend endpoint is unreachable, and as the source of truth
// for the research views (Workspaces / Watchlists / Timeline) that have no
// corresponding backend endpoint yet.

import type {
  Article,
  Cluster,
  TrendingTopic,
  Workspace,
  WorkspaceDetail,
  WatchItem,
  Story,
  TimelineEvent,
} from "../types";

export const mockArticles: Article[] = [
  { title: "Federal Reserve signals pause on rate hikes amid cooling inflation data", source: "Reuters", time: "2m", category: "Economy", sent: 0.34, summary: "Policymakers indicated a willingness to hold rates steady as core PCE eased for a third consecutive month, lifting risk assets.", entities: ["Federal Reserve", "Jerome Powell", "PCE"] },
  { title: "Nvidia unveils next-gen Blackwell Ultra accelerators at developer summit", source: "Bloomberg", time: "8m", category: "Technology", sent: 0.61, summary: "The chipmaker claims a 4x throughput gain for large-model inference, deepening its lead in the AI hardware race.", entities: ["Nvidia", "Jensen Huang", "AI"] },
  { title: "EU regulators open antitrust probe into cloud licensing practices", source: "FT", time: "14m", category: "Policy", sent: -0.42, summary: "Brussels is examining whether bundling terms unfairly disadvantage rival cloud providers across the bloc.", entities: ["European Union", "Microsoft", "Antitrust"] },
  { title: "Oil slips below $74 as OPEC+ weighs output adjustments", source: "CNBC", time: "21m", category: "Energy", sent: -0.18, summary: "Crude retreated on demand concerns ahead of the cartel’s ministerial meeting later this week.", entities: ["OPEC", "Saudi Arabia", "Crude Oil"] },
  { title: "Breakthrough fusion experiment sustains net energy gain for record duration", source: "Nature", time: "33m", category: "Science", sent: 0.72, summary: "Researchers report a stable burning plasma lasting several seconds, a milestone for commercial viability.", entities: ["Fusion", "LLNL", "Plasma"] },
  { title: "Major bank flags rising commercial real-estate delinquencies", source: "WSJ", time: "47m", category: "Finance", sent: -0.55, summary: "Quarterly filings show provisions for office-loan losses climbing as refinancing pressure mounts.", entities: ["JPMorgan", "CRE", "Credit"] },
  { title: "Pacific trade bloc finalizes digital-economy framework", source: "Nikkei", time: "1h", category: "Trade", sent: 0.28, summary: "Member states agreed on cross-border data flow rules and aligned standards for digital services.", entities: ["CPTPP", "Japan", "Trade"] },
  { title: "Pharma giant’s Alzheimer’s drug clears late-stage trial endpoint", source: "STAT", time: "1h", category: "Health", sent: 0.49, summary: "The therapy slowed cognitive decline by 27% versus placebo, sending shares sharply higher in pre-market.", entities: ["Eli Lilly", "FDA", "Alzheimer’s"] },
];

export const mockClusters: Omit<Cluster, "headlines">[] = [
  { title: "Global central banks converge on rate-pause signaling", count: 47, sources: 23, time: "12m", sent: 0.31, vel: "▲ 340%/h" },
  { title: "AI chip supply chain tightens ahead of Q3 demand surge", count: 38, sources: 19, time: "24m", sent: 0.18, vel: "▲ 210%/h" },
  { title: "Cloud antitrust scrutiny widens across EU and US", count: 31, sources: 17, time: "38m", sent: -0.39, vel: "▲ 155%/h" },
  { title: "Energy markets react to OPEC+ output uncertainty", count: 29, sources: 21, time: "51m", sent: -0.22, vel: "▼ 40%/h" },
  { title: "Fusion milestone reignites clean-energy investment thesis", count: 22, sources: 14, time: "1h", sent: 0.66, vel: "▲ 480%/h" },
  { title: "Commercial real-estate stress spreads to regional lenders", count: 26, sources: 16, time: "1h", sent: -0.51, vel: "▲ 90%/h" },
];

export const mockTrending: TrendingTopic[] = [
  { topic: "Rate Pause", mentions: 4820, change: 340, sent: 0.31 },
  { topic: "Blackwell Ultra", mentions: 3910, change: 210, sent: 0.58 },
  { topic: "Fusion Energy", mentions: 2740, change: 480, sent: 0.66 },
  { topic: "Cloud Antitrust", mentions: 2310, change: 155, sent: -0.39 },
  { topic: "CRE Delinquency", mentions: 1980, change: 90, sent: -0.51 },
  { topic: "OPEC+ Output", mentions: 1720, change: -40, sent: -0.22 },
  { topic: "Alzheimer’s Trial", mentions: 1540, change: 120, sent: 0.49 },
  { topic: "Digital Trade Pact", mentions: 1180, change: 64, sent: 0.28 },
  { topic: "PCE Inflation", mentions: 980, change: 35, sent: 0.12 },
  { topic: "Regional Banks", mentions: 870, change: 72, sent: -0.44 },
];

// 24h hourly market-sentiment index used by the dashboard trend chart.
export const mockTrendSeries = [
  0.05, 0.08, 0.02, -0.04, -0.1, -0.06, 0.01, 0.07, 0.12, 0.09, 0.15, 0.21,
  0.18, 0.24, 0.19, 0.13, 0.16, 0.22, 0.28, 0.25, 0.31, 0.27, 0.33, 0.3,
];

export const mockWorkspaces: Workspace[] = [
  { id: "p1", q: "Is the AI chip supply chain a systemic risk to 2026 growth?", status: "Active", sources: 23, notes: 8, updated: "14m", color: "#FF6B6B" },
  { id: "p2", q: "How is cloud antitrust enforcement evolving across jurisdictions?", status: "Active", sources: 17, notes: 5, updated: "1h", color: "#5B9DFF" },
  { id: "p3", q: "Will the Fed rate-pause hold through Q3 2026?", status: "Synthesizing", sources: 31, notes: 12, updated: "3m", color: "#3DD68C" },
  { id: "p4", q: "CRE contagion risk to US regional banks", status: "Active", sources: 14, notes: 4, updated: "2h", color: "#FFD93D" },
];

export const mockWorkspaceDetail: Record<string, WorkspaceDetail> = {
  p1: {
    sub: ["Where are the single points of failure in advanced-node fabrication?", "How exposed are hyperscalers to a Taiwan disruption?", "Which substitutes scale within 18 months?"],
    sources: [
      { title: "Nvidia unveils next-gen Blackwell Ultra accelerators", source: "Bloomberg", time: "8m", sent: 0.61, note: "Confirms demand outpacing supply — key supporting evidence." },
      { title: "AI chip supply chain tightens ahead of Q3 demand surge", source: "Nikkei", time: "24m", sent: 0.18, note: "Names CoWoS packaging as the bottleneck." },
      { title: "TSMC raises capex guidance on advanced-node demand", source: "Reuters", time: "2h", sent: 0.34, note: "Counterpoint: capacity coming online late 2026." },
    ],
    entities: ["Nvidia", "TSMC", "CoWoS", "Taiwan", "Hyperscalers"],
  },
  p2: {
    sub: ["Are EU and US theories of harm converging?", "What remedies are regulators signalling?", "Precedent from prior cloud cases?"],
    sources: [
      { title: "EU regulators open antitrust probe into cloud licensing", source: "FT", time: "14m", sent: -0.42, note: "Primary trigger for this investigation." },
      { title: "Cloud antitrust scrutiny widens across EU and US", source: "WSJ", time: "38m", sent: -0.39, note: "Suggests coordinated cross-jurisdiction action." },
    ],
    entities: ["European Union", "Microsoft", "Antitrust", "Brussels"],
  },
  p3: {
    sub: ["Does core PCE trajectory support a hold?", "What is the labour-market read?", "How are markets pricing the path?", "Dissent risk on the committee?"],
    sources: [
      { title: "Federal Reserve signals pause on rate hikes amid cooling inflation", source: "Reuters", time: "2m", sent: 0.34, note: "Strongest direct evidence for the pause thesis." },
      { title: "Core PCE eases for third consecutive month", source: "CNBC", time: "1h", sent: 0.21, note: "Supports disinflation trend." },
      { title: "Labour market shows gradual cooling, not collapse", source: "Bloomberg", time: "3h", sent: 0.08, note: "Reduces pressure to cut — favours hold." },
      { title: "Two FOMC members flag upside inflation risk", source: "WSJ", time: "5h", sent: -0.22, note: "Dissent risk — weakens a clean hold narrative." },
    ],
    entities: ["Federal Reserve", "Jerome Powell", "PCE", "FOMC"],
  },
  p4: {
    sub: ["How concentrated is office-loan exposure regionally?", "What refinancing wall hits in 2026?", "Are provisions keeping pace?"],
    sources: [
      { title: "Major bank flags rising commercial real-estate delinquencies", source: "WSJ", time: "47m", sent: -0.55, note: "Lead evidence of stress building." },
      { title: "Regional lenders raise loss provisions on office loans", source: "FT", time: "4h", sent: -0.44, note: "Shows contagion path to smaller banks." },
    ],
    entities: ["JPMorgan", "CRE", "Regional Banks", "Credit"],
  },
};

export const mockWatchlist: WatchItem[] = [
  { name: "Nvidia", type: "Entity", mentions: 38, change: 210, sent: 0.58, spark: [8, 10, 9, 14, 18, 22, 30, 38], alert: true },
  { name: "Federal Reserve", type: "Entity", mentions: 42, change: 12, sent: 0.31, spark: [30, 34, 33, 36, 38, 40, 41, 42], alert: false },
  { name: "Cloud Antitrust", type: "Topic", mentions: 31, change: 155, sent: -0.39, spark: [6, 8, 7, 12, 18, 24, 28, 31], alert: true },
  { name: "Fusion Energy", type: "Topic", mentions: 22, change: 480, sent: 0.66, spark: [2, 3, 2, 4, 7, 12, 18, 22], alert: true },
  { name: "OPEC+", type: "Topic", mentions: 17, change: -40, sent: -0.22, spark: [28, 26, 24, 22, 21, 19, 18, 17], alert: false },
  { name: "Jerome Powell", type: "Person", mentions: 19, change: 8, sent: 0.12, spark: [14, 16, 15, 17, 18, 18, 19, 19], alert: false },
];

export const mockStories: Story[] = [
  { id: "s1", label: "AI chip supply chain", sent: 0.18 },
  { id: "s2", label: "Fed rate-pause signal", sent: 0.31 },
  { id: "s3", label: "Cloud antitrust probe", sent: -0.39 },
];

export const mockTimeline: Record<string, TimelineEvent[]> = {
  s1: [
    { date: "Jun 04", title: "Reports surface of tightening CoWoS packaging capacity", source: "Nikkei", kind: "Origin", sent: -0.1 },
    { date: "Jun 07", title: "TSMC privately warns key clients of allocation cuts", source: "Reuters", kind: "Development", sent: -0.22 },
    { date: "Jun 11", title: "Hyperscalers reportedly pre-pay to secure 2026 supply", source: "Bloomberg", kind: "Development", sent: 0.05 },
    { date: "Jun 14", title: "TSMC raises capex guidance on advanced-node demand", source: "Reuters", kind: "Reaction", sent: 0.34 },
    { date: "Jun 18", title: "Nvidia unveils Blackwell Ultra; demand seen outpacing supply", source: "Bloomberg", kind: "Milestone", sent: 0.61 },
  ],
  s2: [
    { date: "Jun 02", title: "Core PCE eases for a second month", source: "CNBC", kind: "Origin", sent: 0.12 },
    { date: "Jun 09", title: "Labour market shows gradual cooling", source: "Bloomberg", kind: "Development", sent: 0.08 },
    { date: "Jun 13", title: "Two FOMC members flag upside inflation risk", source: "WSJ", kind: "Reaction", sent: -0.22 },
    { date: "Jun 18", title: "Fed signals pause as core PCE eases third month", source: "Reuters", kind: "Milestone", sent: 0.34 },
  ],
  s3: [
    { date: "Jun 06", title: "Complaints filed over cloud licensing bundling", source: "Politico", kind: "Origin", sent: -0.2 },
    { date: "Jun 12", title: "US agencies signal interest in cloud competition", source: "WSJ", kind: "Development", sent: -0.3 },
    { date: "Jun 18", title: "EU opens formal antitrust probe into cloud licensing", source: "FT", kind: "Milestone", sent: -0.42 },
  ],
};

// Heatmap seed (topics × 16 hourly columns) from the design.
export const mockHeatmap = {
  topics: ["Economy", "Technology", "Energy", "Policy", "Health", "Markets"],
  cols: 16,
  seed: [
    [0.1, 0.2, 0.0, -0.1, 0.1, 0.3, 0.2, 0.4, 0.3, 0.1, -0.1, 0.0, 0.2, 0.3, 0.4, 0.3],
    [0.4, 0.5, 0.3, 0.6, 0.5, 0.4, 0.6, 0.7, 0.5, 0.4, 0.5, 0.6, 0.4, 0.5, 0.6, 0.5],
    [-0.2, -0.3, -0.1, -0.4, -0.2, 0.0, -0.1, -0.3, -0.2, -0.4, -0.1, 0.0, -0.2, -0.3, -0.1, -0.2],
    [0.0, -0.2, -0.4, -0.3, -0.5, -0.2, -0.1, -0.3, -0.4, -0.2, 0.0, -0.1, -0.3, -0.4, -0.2, -0.4],
    [0.2, 0.3, 0.4, 0.3, 0.5, 0.4, 0.3, 0.5, 0.4, 0.6, 0.5, 0.4, 0.3, 0.5, 0.4, 0.5],
    [0.1, -0.1, 0.0, 0.2, -0.2, 0.1, -0.3, 0.0, 0.2, -0.1, 0.3, 0.1, -0.2, 0.0, 0.1, -0.1],
  ],
};

export const mockTickerText =
  "  ●  Fed signals rate pause as core PCE eases  ●  Nvidia Blackwell Ultra claims 4x inference gain  ●  EU opens cloud antitrust probe  ●  Fusion experiment sustains net energy gain  ●  Oil slips below $74 on OPEC+ uncertainty  ●  Alzheimer’s drug clears late-stage trial  ";
