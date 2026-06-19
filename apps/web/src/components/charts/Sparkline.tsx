interface Props {
  values: number[];
  color: string;
}

// Mini sparkline used in watchlist cards. Ported from `buildSpark` (W=96,H=30).
export default function Sparkline({ values, color }: Props) {
  const W = 96;
  const H = 30;
  const pad = 2;
  const mn = Math.min(...values);
  const mx = Math.max(...values);
  const rng = mx - mn || 1;
  const xs = (i: number) => pad + (i / (values.length - 1)) * (W - 2 * pad);
  const ys = (v: number) => H - pad - ((v - mn) / rng) * (H - 2 * pad);
  const line = values.map((v, i) => `${xs(i).toFixed(1)},${ys(v).toFixed(1)}`).join(" ");

  return (
    <svg viewBox={`0 0 ${W} ${H}`} width={W} height={H} preserveAspectRatio="none" style={{ display: "block" }}>
      <polyline points={line} fill="none" stroke={color} strokeWidth={1.6} strokeLinejoin="round" strokeLinecap="round" />
      <circle cx={xs(values.length - 1)} cy={ys(values[values.length - 1])} r={2.4} fill={color} />
    </svg>
  );
}
