import { palette } from "../theme";

// Sentiment helpers, mirrored from the design's `sentColor` / `sentLabel` / `fmt`.
export function sentColor(v: number): string {
  return v > 0.15 ? palette.pos : v < -0.15 ? palette.neg : palette.neu;
}

export function sentLabel(v: number): "POSITIVE" | "NEGATIVE" | "NEUTRAL" {
  return v > 0.15 ? "POSITIVE" : v < -0.15 ? "NEGATIVE" : "NEUTRAL";
}

export function fmt(v: number): string {
  return (v >= 0 ? "+" : "") + v.toFixed(2);
}
