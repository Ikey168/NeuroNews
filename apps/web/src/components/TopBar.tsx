import { useEffect, useState } from "react";
import { ACCENT, palette, fonts } from "../theme";
import { useBackendStatus, type BackendStatus } from "../lib/queries";

const STATUS_META: Record<BackendStatus, { color: string; label: string }> = {
  checking: { color: palette.amber, label: "CONNECTING" },
  online: { color: palette.pos, label: "BACKEND LIVE" },
  offline: { color: palette.faint, label: "DEMO MODE" },
};

function ConnectionPill() {
  const status = useBackendStatus();
  const { color, label } = STATUS_META[status];
  return (
    <div
      title={
        status === "online"
          ? "Connected to the NeuroNews API"
          : status === "checking"
            ? "Probing the backend…"
            : "Backend unreachable — views fall back to the demo dataset"
      }
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 7,
        fontFamily: fonts.mono,
        fontSize: 10,
        letterSpacing: "0.1em",
        color,
        border: `1px solid ${color}44`,
        background: `${color}14`,
        borderRadius: 6,
        padding: "5px 10px",
      }}
    >
      <span
        style={{
          width: 7,
          height: 7,
          borderRadius: "50%",
          background: color,
          boxShadow: status === "online" ? `0 0 6px ${color}` : "none",
          animation: status === "checking" ? "pulse 1s ease-in-out infinite" : undefined,
        }}
      />
      {label}
    </div>
  );
}

function useUtcClock() {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(t);
  }, []);
  return now;
}

export default function TopBar() {
  const now = useUtcClock();
  const pad2 = (x: number) => String(x).padStart(2, "0");
  const clock = `${pad2(now.getUTCHours())}:${pad2(now.getUTCMinutes())}:${pad2(now.getUTCSeconds())}`;
  const dateStr = now
    .toLocaleDateString("en-US", { month: "short", day: "2-digit", timeZone: "UTC" })
    .toUpperCase();

  return (
    <header
      style={{
        height: 54,
        flex: "none",
        borderBottom: "1px solid #1c2330",
        background: "#0c1016",
        display: "flex",
        alignItems: "center",
        padding: "0 18px",
        gap: 16,
      }}
    >
      <div
        style={{
          flex: 1,
          maxWidth: 440,
          display: "flex",
          alignItems: "center",
          gap: 10,
          background: "#10151d",
          border: "1px solid #232a36",
          borderRadius: 7,
          padding: "8px 12px",
        }}
      >
        <span style={{ color: "#5b6675", fontSize: 13 }}>⌕</span>
        <input
          placeholder="Search entities, topics, sources…"
          style={{
            flex: 1,
            background: "transparent",
            border: "none",
            outline: "none",
            color: "#e6eaf0",
            fontFamily: fonts.sans,
            fontSize: 13,
          }}
        />
        <span
          style={{
            fontFamily: fonts.mono,
            fontSize: 9.5,
            color: "#4b5563",
            border: "1px solid #2a3340",
            borderRadius: 4,
            padding: "1px 5px",
          }}
        >
          ⌘K
        </span>
      </div>
      <div style={{ flex: 1 }} />
      <div style={{ display: "flex", alignItems: "center", gap: 18 }}>
        <ConnectionPill />
        <div style={{ textAlign: "right", lineHeight: 1.15 }}>
          <div style={{ fontFamily: fonts.mono, fontSize: 14, fontWeight: 500, color: ACCENT }}>{clock}</div>
          <div style={{ fontFamily: fonts.mono, fontSize: 9, color: "#5b6675", letterSpacing: "0.1em" }}>
            UTC · {dateStr}
          </div>
        </div>
        <div
          style={{
            width: 32,
            height: 32,
            borderRadius: "50%",
            background: "#1c2330",
            border: "1px solid #2a3340",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            fontFamily: fonts.mono,
            fontSize: 11,
            color: "#8a94a6",
          }}
        >
          AK
        </div>
      </div>
    </header>
  );
}
