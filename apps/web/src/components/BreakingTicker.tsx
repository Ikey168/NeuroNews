import { ACCENT, fonts } from "../theme";

interface Props {
  text: string;
}

export default function BreakingTicker({ text }: Props) {
  return (
    <div
      style={{
        height: 30,
        flex: "none",
        background: "#11070a",
        borderBottom: "1px solid #2a1418",
        display: "flex",
        alignItems: "center",
        overflow: "hidden",
      }}
    >
      <div
        style={{
          flex: "none",
          background: ACCENT,
          color: "#0a0d12",
          fontFamily: fonts.mono,
          fontWeight: 600,
          fontSize: 10,
          letterSpacing: "0.14em",
          padding: "0 12px",
          height: "100%",
          display: "flex",
          alignItems: "center",
          zIndex: 2,
        }}
      >
        BREAKING
      </div>
      <div style={{ flex: 1, overflow: "hidden", whiteSpace: "nowrap" }}>
        <div
          style={{
            display: "inline-block",
            whiteSpace: "nowrap",
            animation: "ticker 48s linear infinite",
            fontFamily: fonts.mono,
            fontSize: 11.5,
            color: "#c7b4b6",
          }}
        >
          {text}
          {text}
        </div>
      </div>
    </div>
  );
}
