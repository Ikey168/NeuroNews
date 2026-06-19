import { ACCENT, palette, fonts } from "../../theme";
import type { GraphNode } from "../../types";

interface Props {
  accent?: string;
}

// Static force-style entity relationship graph. Ported from `buildGraph`.
export default function EntityGraph({ accent = ACCENT }: Props) {
  const W = 760;
  const H = 480;
  const nodes: GraphNode[] = [
    { id: "fed", label: "Federal Reserve", x: 0.3, y: 0.3, r: 26, type: "org", color: accent },
    { id: "powell", label: "J. Powell", x: 0.16, y: 0.52, r: 15, type: "person", color: palette.blue },
    { id: "pce", label: "PCE", x: 0.44, y: 0.16, r: 13, type: "topic", color: palette.amber },
    { id: "nvda", label: "Nvidia", x: 0.66, y: 0.28, r: 24, type: "org", color: accent },
    { id: "huang", label: "J. Huang", x: 0.82, y: 0.16, r: 14, type: "person", color: palette.blue },
    { id: "ai", label: "AI", x: 0.6, y: 0.5, r: 20, type: "topic", color: palette.amber },
    { id: "eu", label: "European Union", x: 0.4, y: 0.7, r: 21, type: "org", color: accent },
    { id: "msft", label: "Microsoft", x: 0.6, y: 0.78, r: 18, type: "org", color: accent },
    { id: "opec", label: "OPEC", x: 0.84, y: 0.62, r: 17, type: "org", color: accent },
    { id: "oil", label: "Crude Oil", x: 0.84, y: 0.84, r: 15, type: "topic", color: palette.amber },
    { id: "eu2", label: "Brussels", x: 0.2, y: 0.8, r: 12, type: "place", color: palette.violet },
    { id: "cloud", label: "Cloud", x: 0.5, y: 0.92, r: 13, type: "topic", color: palette.amber },
  ];
  const edges: [string, string][] = [
    ["fed", "powell"], ["fed", "pce"], ["fed", "ai"], ["nvda", "huang"], ["nvda", "ai"], ["ai", "msft"],
    ["eu", "msft"], ["eu", "eu2"], ["msft", "cloud"], ["eu", "cloud"], ["opec", "oil"], ["nvda", "fed"], ["ai", "eu"],
  ];
  const N: Record<string, GraphNode> = {};
  nodes.forEach((n) => (N[n.id] = n));
  const px = (n: GraphNode) => n.x * W;
  const py = (n: GraphNode) => n.y * H;

  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" height={480} style={{ display: "block" }}>
      <g>
        {edges.map((e, i) => (
          <line
            key={i}
            x1={px(N[e[0]])}
            y1={py(N[e[0]])}
            x2={px(N[e[1]])}
            y2={py(N[e[1]])}
            stroke="#2a3340"
            strokeWidth={1.2}
          />
        ))}
      </g>
      <g>
        {nodes.map((n, i) => (
          <g key={i}>
            <circle cx={px(n)} cy={py(n)} r={n.r + 5} fill={n.color} opacity={0.1} />
            <circle cx={px(n)} cy={py(n)} r={n.r} fill="#0e131a" stroke={n.color} strokeWidth={2} />
            <circle cx={px(n)} cy={py(n)} r={Math.max(3, n.r * 0.28)} fill={n.color} />
            <text
              x={px(n)}
              y={py(n) + n.r + 13}
              textAnchor="middle"
              fill="#c7cdd6"
              fontSize={11}
              fontFamily={fonts.sans}
              fontWeight={500}
            >
              {n.label}
            </text>
          </g>
        ))}
      </g>
    </svg>
  );
}
