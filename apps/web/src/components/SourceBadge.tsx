import { palette, fonts } from "../theme";
import type { Source } from "../lib/queries";

// Small pill that tells the operator whether the panel is rendering data
// pulled live from the backend or the bundled demo dataset (used as a
// fallback when the API is unreachable or returns nothing).
interface Props {
  source: Source;
  isLoading?: boolean;
}

export default function SourceBadge({ source, isLoading }: Props) {
  const live = source === "live";
  const color = isLoading ? palette.amber : live ? palette.pos : palette.faint;
  const label = isLoading ? "SYNC" : live ? "LIVE" : "DEMO";

  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 6,
        fontFamily: fonts.mono,
        fontSize: 9.5,
        letterSpacing: "0.12em",
        color,
        border: `1px solid ${color}44`,
        background: `${color}14`,
        borderRadius: 5,
        padding: "3px 8px",
      }}
      title={
        isLoading
          ? "Fetching from backend…"
          : live
            ? "Live data from the NeuroNews API"
            : "Backend unreachable or empty — showing demo dataset"
      }
    >
      <span
        style={{
          width: 6,
          height: 6,
          borderRadius: "50%",
          background: color,
          boxShadow: live && !isLoading ? `0 0 6px ${color}` : "none",
          animation: isLoading ? "pulse 1s ease-in-out infinite" : undefined,
        }}
      />
      {label}
    </span>
  );
}
