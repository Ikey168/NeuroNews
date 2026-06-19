import { ACCENT } from "../../theme";
import { mockTrendSeries } from "../../data/mock";

interface Props {
  values?: number[];
  accent?: string;
}

// Market Sentiment Index area+line chart. Ported from the design's
// `buildTrendChart` (W=720, H=188).
export default function TrendChart({ values = mockTrendSeries, accent = ACCENT }: Props) {
  const W = 720;
  const H = 188;
  const pad = 8;
  const n = values.length;
  const xs = (i: number) => pad + (i / (n - 1)) * (W - 2 * pad);
  const ys = (v: number) => H / 2 - v * (H / 2 - 14);
  const line = values.map((v, i) => `${xs(i).toFixed(1)},${ys(v).toFixed(1)}`).join(" ");
  const area = `${pad},${H / 2} ${line} ${(W - pad).toFixed(1)},${H / 2}`;

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      width="100%"
      height={188}
      preserveAspectRatio="none"
      style={{ display: "block" }}
    >
      <defs>
        <linearGradient id="tg" x1={0} y1={0} x2={0} y2={1}>
          <stop offset="0%" stopColor={accent} stopOpacity={0.28} />
          <stop offset="100%" stopColor={accent} stopOpacity={0} />
        </linearGradient>
      </defs>
      <line x1={pad} y1={H / 2} x2={W - pad} y2={H / 2} stroke="#232a36" strokeWidth={1} strokeDasharray="3 4" />
      <polygon points={area} fill="url(#tg)" />
      <polyline
        points={line}
        fill="none"
        stroke={accent}
        strokeWidth={2}
        strokeLinejoin="round"
        strokeLinecap="round"
      />
      <circle cx={xs(n - 1)} cy={ys(values[n - 1])} r={4} fill={accent} stroke="#0c1016" strokeWidth={2} />
    </svg>
  );
}
