// The generative canvas — the app's only surface. Starts empty: nothing is
// generated until an intent is submitted through the bottom composer (or a
// sidebar preset). With an intent, the planned layout fills the space above
// the composer.

import { RotateCcw } from "lucide-react";
import SpecRenderer from "./SpecRenderer";
import Composer from "./Composer";
import { usePackStatus } from "../lib/queries";
import { useUiSpec } from "./useUiSpec";
import { useAdaptiveSignals, hasSignals } from "./signals";
import { PANEL_DEFS } from "./spec";
import type { CanvasDef } from "./canvases";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";

const PLANNER_BADGE: Record<string, { label: string; className: string; hint: string }> = {
  llm: {
    label: "LLM PLAN",
    className: "border-violet-400/30 bg-violet-400/10 text-violet-400",
    hint: "Layout composed by the configured LLM planner",
  },
  heuristic: {
    label: "RULE PLAN",
    className: "border-teal-400/30 bg-teal-400/10 text-teal-400",
    hint: "Layout composed by the backend heuristic planner",
  },
  client: {
    label: "LOCAL PLAN",
    className: "border-amber-400/30 bg-amber-400/10 text-amber-400",
    hint: "Backend unreachable — layout composed in the browser",
  },
};

// Example intents on the empty canvas — the only "navigation" left. The
// news-specific ones follow the domain pack, mirroring how the planner
// gates news panels via ui_flags.
const CORE_SUGGESTIONS = [
  "Daily briefing",
  "Compare outlet framing on climate policy",
  "Who disagrees about AI regulation?",
  "Fact-check claims about the economy",
  "Library documents",
  "Entity network connections",
];

const NEWS_SUGGESTIONS = [
  "Sentiment trend for technology this month",
  "Breaking event clusters",
  "Watchlist alerts",
];

function EmptyState({ onIntent }: { onIntent: (intent: string) => void }) {
  const { newsPack } = usePackStatus();
  const suggestions = newsPack ? [...CORE_SUGGESTIONS, ...NEWS_SUGGESTIONS] : CORE_SUGGESTIONS;
  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-6 px-6 text-center">
      <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-primary shadow-[0_0_28px_-4px_hsl(var(--primary)/0.6)]">
        <span className="font-grotesk text-2xl font-bold text-primary-foreground">N</span>
      </div>
      <div className="space-y-2">
        <h1 className="font-grotesk text-2xl font-semibold tracking-tight">
          What should Noesis show you?
        </h1>
        <p className="mx-auto max-w-md text-sm leading-relaxed text-muted-foreground">
          There are no pages here. Describe what you want to see and a canvas is
          planned for it — panels sized to fit, driven by live data where it
          exists.
        </p>
      </div>
      <div className="flex max-w-xl flex-wrap items-center justify-center gap-2">
        {suggestions.map((s) => (
          <Button
            key={s}
            variant="outline"
            size="sm"
            className="rounded-full font-mono text-[11px] text-muted-foreground hover:text-foreground"
            onClick={() => onIntent(s)}
          >
            {s}
          </Button>
        ))}
      </div>
    </div>
  );
}

interface Props {
  canvas: CanvasDef;
  onIntent: (intent: string) => void;
}

export default function Canvas({ canvas, onIntent }: Props) {
  const adaptive = useAdaptiveSignals();
  const hasIntent = canvas.intent.trim().length > 0;
  const { spec, source, isLoading } = useUiSpec(canvas.intent, adaptive.signals, hasIntent);

  const planner = PLANNER_BADGE[spec.generated_by] ?? PLANNER_BADGE.heuristic;

  return (
    <div className="flex h-full min-h-0 flex-col">
      {hasIntent ? (
        <div className="min-h-0 flex-1 overflow-y-auto px-6 pb-4 pt-5">
          {/* Provenance strip */}
          <div className="mb-4 flex flex-wrap items-center gap-2.5">
            <Badge variant="outline" className={planner.className} title={planner.hint}>
              {planner.label}
            </Badge>
            <Badge variant={isLoading ? "sync" : source === "live" ? "live" : "demo"}>
              {isLoading ? "SYNC" : source === "live" ? "LIVE" : "DEMO"}
            </Badge>
            <span className="font-grotesk text-sm font-semibold">{spec.title}</span>
            {spec.subtitle ? (
              <span className="font-mono text-[10.5px] text-muted-foreground">{spec.subtitle}</span>
            ) : null}
            <span className="flex-1" />
            {adaptive.signals.dismissed.length > 0 ? (
              <span className="font-mono text-[10.5px] text-muted-foreground">
                muted:{" "}
                {adaptive.signals.dismissed.map((t, i) => (
                  <button
                    key={t}
                    onClick={() => adaptive.restore(t)}
                    title={`Restore ${PANEL_DEFS[t]?.title ?? t}`}
                    className="cursor-pointer line-through hover:text-foreground hover:no-underline"
                  >
                    {(i > 0 ? ", " : "") + t}
                  </button>
                ))}
              </span>
            ) : null}
            {hasSignals(adaptive.signals) ? (
              <Button
                variant="outline"
                size="sm"
                className="h-6 rounded-md px-2 font-mono text-[10px] text-muted-foreground"
                onClick={adaptive.reset}
                title="Forget pins, mutes and interaction weights"
              >
                <RotateCcw className="!size-3" /> RESET
              </Button>
            ) : null}
          </div>

          <SpecRenderer spec={spec} adaptive={adaptive} />
        </div>
      ) : (
        <EmptyState onIntent={onIntent} />
      )}

      <div className="shrink-0 px-6 pb-5 pt-2">
        <Composer key={canvas.id} initial={canvas.intent} onSubmit={onIntent} autoFocus={!hasIntent} />
      </div>
    </div>
  );
}
