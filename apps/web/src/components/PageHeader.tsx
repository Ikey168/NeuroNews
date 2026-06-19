import type { ReactNode } from "react";
import { fonts } from "../theme";

interface Props {
  title: string;
  subtitle: ReactNode;
  right?: ReactNode;
}

export default function PageHeader({ title, subtitle, right }: Props) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "baseline",
        justifyContent: right ? "space-between" : "flex-start",
        marginBottom: 16,
      }}
    >
      <div>
        <h1 style={{ fontFamily: fonts.grotesk, fontWeight: 600, fontSize: 21, margin: 0, letterSpacing: "-0.01em" }}>
          {title}
        </h1>
        <p style={{ fontFamily: fonts.mono, fontSize: 11, color: "#5b6675", margin: "5px 0 0", letterSpacing: "0.04em" }}>
          {subtitle}
        </p>
      </div>
      {right}
    </div>
  );
}
