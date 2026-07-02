// The sidebar is a canvas manager, not a view switch: every entry either
// activates an open canvas or generates a new one from a suggested intent.
// Suggestions route through the same planner as composer-typed intents.

import { Plus, Sparkles, X } from "lucide-react";
import { usePackStatus } from "../lib/queries";
import { HOME, type CanvasDef } from "../genui/canvases";
import { Button } from "./ui/button";
import { cn } from "../lib/utils";

interface PresetDef {
  label: string;
  intent: string;
  glyph: string;
}

const corePresets: PresetDef[] = [
  { label: "Library", intent: "library documents", glyph: "≣" },
  { label: "Entity network", intent: "entity network connections", glyph: "⬡" },
  { label: "Claims & facts", intent: "fact-check claims and evidence", glyph: "◫" },
  { label: "Stance & conflicts", intent: "stance conflicts and disagreements", glyph: "◮" },
  { label: "Outlets & framing", intent: "compare outlet framing and transparency", glyph: "◭" },
  { label: "Key actors", intent: "who are the key actors and stakeholders", glyph: "◉" },
];

const newsPresets: PresetDef[] = [
  { label: "Sentiment", intent: "sentiment overview this week", glyph: "◑" },
  { label: "Event clusters", intent: "breaking event clusters", glyph: "⊞" },
  { label: "Trending", intent: "trending topics this week", glyph: "↗" },
  { label: "Watchlists", intent: "watchlist alerts", glyph: "☆" },
  { label: "Story timeline", intent: "story timeline developments", glyph: "⤳" },
];

interface Props {
  canvases: CanvasDef[];
  activeId: string;
  onSelect: (id: string) => void;
  onOpen: (intent: string, label?: string) => void;
  onRemove: (id: string) => void;
  ingestRate: string;
}

const sectionLabel = "px-2.5 pb-1.5 pt-2 font-mono text-[9.5px] tracking-[0.16em] text-muted-foreground/60";

function NavButton({
  active,
  onClick,
  glyph,
  icon,
  label,
  title,
  trailing,
}: {
  active?: boolean;
  onClick: () => void;
  glyph?: string;
  icon?: React.ReactNode;
  label: string;
  title?: string;
  trailing?: React.ReactNode;
}) {
  return (
    <Button
      variant="ghost"
      onClick={onClick}
      title={title}
      className={cn(
        "h-auto w-full justify-start gap-2.5 px-2.5 py-2 text-[13px] font-medium text-muted-foreground",
        active && "bg-primary/10 text-primary hover:bg-primary/10 hover:text-primary",
      )}
    >
      <span className="w-[18px] shrink-0 text-center text-[13px]">{icon ?? glyph}</span>
      <span className="min-w-0 flex-1 truncate text-left">{label}</span>
      {trailing}
    </Button>
  );
}

export default function Sidebar({ canvases, activeId, onSelect, onOpen, onRemove, ingestRate }: Props) {
  const { newsPack } = usePackStatus();

  return (
    <aside className="flex w-60 shrink-0 flex-col border-r bg-[#0c1016]">
      {/* Brand */}
      <div className="flex items-center gap-3 border-b px-4 py-4">
        <div className="flex h-[34px] w-[34px] shrink-0 items-center justify-center rounded-lg bg-primary shadow-[0_0_18px_-2px_hsl(var(--primary)/0.5)]">
          <span className="font-grotesk text-[19px] font-bold text-primary-foreground">N</span>
        </div>
        <div className="leading-tight">
          <div className="font-grotesk text-base font-bold tracking-tight">Noesis</div>
          <div className="mt-0.5 font-mono text-[9.5px] tracking-[0.16em] text-muted-foreground/60">
            GENERATIVE CANVAS
          </div>
        </div>
      </div>

      <nav className="flex min-h-0 flex-1 flex-col gap-0.5 overflow-y-auto p-2.5">
        <div className={sectionLabel}>CANVASES</div>
        {canvases.map((c) => (
          <NavButton
            key={c.id}
            active={c.id === activeId}
            onClick={() => onSelect(c.id)}
            icon={c.id === HOME.id ? <Plus className="size-3.5" /> : <Sparkles className="size-3.5" />}
            label={c.label}
            title={c.intent || "Empty canvas — describe what you want to see"}
            trailing={
              c.id !== HOME.id ? (
                <span
                  role="button"
                  title="Close canvas"
                  className="rounded p-0.5 text-muted-foreground/50 hover:bg-secondary hover:text-foreground"
                  onClick={(e) => {
                    e.stopPropagation();
                    onRemove(c.id);
                  }}
                >
                  <X className="size-3" />
                </span>
              ) : undefined
            }
          />
        ))}

        <div className={cn(sectionLabel, "pt-4")}>SUGGESTIONS</div>
        {corePresets.map((p) => (
          <NavButton
            key={p.label}
            onClick={() => onOpen(p.intent, p.label)}
            glyph={p.glyph}
            label={p.label}
            title={`Generate: “${p.intent}”`}
          />
        ))}

        {newsPack ? (
          <>
            <div className={cn(sectionLabel, "flex items-center gap-1.5 pt-4")}>
              NEWS PACK
              <span className="rounded border border-emerald-400/30 bg-emerald-400/10 px-1 py-px font-mono text-[8.5px] tracking-wider text-emerald-400">
                ON
              </span>
            </div>
            {newsPresets.map((p) => (
              <NavButton
                key={p.label}
                onClick={() => onOpen(p.intent, p.label)}
                glyph={p.glyph}
                label={p.label}
                title={`Generate: “${p.intent}”`}
              />
            ))}
          </>
        ) : null}
      </nav>

      {/* Footer */}
      <div className="flex flex-col gap-2 border-t px-4 py-3.5">
        <div className="flex items-center gap-2">
          <span className="h-[7px] w-[7px] rounded-full bg-emerald-400" style={{ animation: "blink 2s infinite" }} />
          <span className="font-mono text-[10.5px] text-muted-foreground">PIPELINE LIVE</span>
        </div>
        <div className="flex justify-between font-mono text-[10.5px] text-muted-foreground/60">
          <span>142 sources</span>
          <span>{ingestRate}/min</span>
        </div>
      </div>
    </aside>
  );
}
