// The generative canvas — the app's only surface. Renders the layout the
// planner generates for this canvas's intent; typing a new intent opens a
// new canvas (App remounts this component per canvas via key={canvas.id}).

import { useState, type CSSProperties } from "react";
import { ACCENT, palette, accentSoft, accentBorder, fonts } from "../theme";
import PageHeader from "../components/PageHeader";
import SourceBadge from "../components/SourceBadge";
import Hover from "../components/Hover";
import SpecRenderer from "./SpecRenderer";
import { useUiSpec } from "./useUiSpec";
import { useAdaptiveSignals, hasSignals } from "./signals";
import { PANEL_DEFS } from "./spec";
import type { CanvasDef } from "./canvases";

const PLANNER_LABELS: Record<string, { label: string; color: string; hint: string }> = {
  llm: { label: "LLM PLAN", color: palette.violet, hint: "Layout composed by the configured LLM planner" },
  heuristic: { label: "RULE PLAN", color: palette.teal, hint: "Layout composed by the backend heuristic planner" },
  client: { label: "LOCAL PLAN", color: palette.amber, hint: "Backend unreachable — layout composed in the browser" },
};

const inputStyle: CSSProperties = {
  flex: 1,
  minWidth: 0,
  background: "#10151d",
  border: "1px solid #232a36",
  borderRadius: 8,
  padding: "10px 14px",
  color: "#e6eaf0",
  fontFamily: fonts.sans,
  fontSize: 13.5,
  outline: "none",
};

interface Props {
  canvas: CanvasDef;
  onIntent: (intent: string) => void;
}

export default function Canvas({ canvas, onIntent }: Props) {
  const [draft, setDraft] = useState(canvas.intent);
  const adaptive = useAdaptiveSignals();
  const { spec, source, isLoading } = useUiSpec(canvas.intent, adaptive.signals);

  const planner = PLANNER_LABELS[spec.generated_by] ?? PLANNER_LABELS.heuristic;

  return (
    <div>
      <PageHeader
        title={canvas.label}
        subtitle="Generative canvas — describe what you want to see and the layout assembles itself"
        right={<SourceBadge source={source} isLoading={isLoading} />}
      />

      {/* Intent bar */}
      <div style={{ display: "flex", gap: 10, marginBottom: 14 }}>
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") onIntent(draft);
          }}
          placeholder="e.g. compare outlet framing on climate policy · who disagrees about AI regulation? · fact-check claims about vaccines"
          maxLength={500}
          style={inputStyle}
        />
        <Hover
          as="button"
          onClick={() => onIntent(draft)}
          style={{
            fontFamily: fonts.mono,
            fontSize: 11.5,
            letterSpacing: "0.08em",
            padding: "0 18px",
            borderRadius: 8,
            cursor: "pointer",
            background: accentSoft(ACCENT),
            color: ACCENT,
            border: `1px solid ${accentBorder(ACCENT)}`,
          }}
          hoverStyle={{ background: `${ACCENT}2e` }}
        >
          GENERATE
        </Hover>
      </div>

      {/* Plan provenance strip */}
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 14, flexWrap: "wrap" }}>
        <span
          title={planner.hint}
          style={{
            fontFamily: fonts.mono,
            fontSize: 9.5,
            letterSpacing: "0.12em",
            color: planner.color,
            border: `1px solid ${planner.color}44`,
            background: `${planner.color}14`,
            borderRadius: 5,
            padding: "3px 8px",
          }}
        >
          {planner.label}
        </span>
        <span style={{ fontFamily: fonts.grotesk, fontWeight: 600, fontSize: 14 }}>{spec.title}</span>
        {spec.subtitle ? (
          <span style={{ fontFamily: fonts.mono, fontSize: 10.5, color: "#5b6675" }}>{spec.subtitle}</span>
        ) : null}
        <span style={{ flex: 1 }} />
        {adaptive.signals.dismissed.length > 0 ? (
          <span style={{ fontFamily: fonts.mono, fontSize: 10.5, color: "#5b6675" }}>
            muted:{" "}
            {adaptive.signals.dismissed.map((t, i) => (
              <Hover
                key={t}
                as="button"
                onClick={() => adaptive.restore(t)}
                style={{
                  fontFamily: fonts.mono,
                  fontSize: 10.5,
                  color: "#8a94a6",
                  background: "none",
                  border: "none",
                  cursor: "pointer",
                  padding: 0,
                  textDecoration: "line-through",
                }}
                hoverStyle={{ color: "#e6eaf0", textDecoration: "none" }}
                title={`Restore ${PANEL_DEFS[t]?.title ?? t}`}
              >
                {(i > 0 ? ", " : "") + t}
              </Hover>
            ))}
          </span>
        ) : null}
        {hasSignals(adaptive.signals) ? (
          <Hover
            as="button"
            onClick={adaptive.reset}
            style={{
              fontFamily: fonts.mono,
              fontSize: 10.5,
              color: "#5b6675",
              background: "none",
              border: "1px solid #232a36",
              borderRadius: 6,
              padding: "3px 9px",
              cursor: "pointer",
            }}
            hoverStyle={{ color: "#e6eaf0", background: "#161d28" }}
            title="Forget pins, mutes and interaction weights"
          >
            RESET ADAPTIVITY
          </Hover>
        ) : null}
      </div>

      <SpecRenderer spec={spec} adaptive={adaptive} />
    </div>
  );
}
