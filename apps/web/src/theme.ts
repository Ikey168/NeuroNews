// Design tokens mirrored 1:1 from the "NeuroNews Terminal" design handoff.
// The design exposed `accent` as a configurable prop (default #FF6B6B).

export const ACCENT = "#FF6B6B";

export const palette = {
  pos: "#3DD68C",
  neg: "#FF5C5C",
  neu: "#8B95A5",
  teal: "#4ECDC4",
  amber: "#FFD93D",
  blue: "#5B9DFF",
  violet: "#A78BFA",
  dim: "#8a94a6",
  faint: "#5b6675",
} as const;

export const colors = {
  bg: "#0a0d12",
  sidebar: "#0c1016",
  card: "#11151c",
  cardInner: "#0e131a",
  input: "#10151d",
  text: "#e6eaf0",
  textMuted: "#c7cdd6",
  textSubtle: "#9aa4b2",
  borderSoft: "#161d28",
  border: "#1c2330",
  border2: "#232a36",
  border3: "#2a3340",
  border4: "#3a4554",
  faint2: "#4b5563",
} as const;

export const fonts = {
  grotesk: "'Space Grotesk', system-ui, sans-serif",
  mono: "'IBM Plex Mono', monospace",
  sans: "'IBM Plex Sans', system-ui, sans-serif",
} as const;

// Hex-with-alpha helpers, matching the design's `acc + '1a'` style suffixes.
export const accentSoft = (accent: string) => `${accent}1a`;
export const accentBorder = (accent: string) => `${accent}55`;
export const accentGlow = (accent: string) => `${accent}66`;
export const tint = (hex: string, suffix: string) => `${hex}${suffix}`;
