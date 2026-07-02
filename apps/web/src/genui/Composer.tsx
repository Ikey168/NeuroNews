// The prompt composer — the app's primary control, anchored at the bottom
// of every canvas like a chat input. Submitting an intent opens (or
// activates) a canvas planned for it.

import { useState } from "react";
import { ArrowUp } from "lucide-react";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";

interface Props {
  initial?: string;
  onSubmit: (intent: string) => void;
  autoFocus?: boolean;
}

export default function Composer({ initial = "", onSubmit, autoFocus }: Props) {
  const [draft, setDraft] = useState(initial);
  const submit = () => {
    if (draft.trim()) onSubmit(draft);
  };

  return (
    <div className="mx-auto w-full max-w-2xl">
      <div className="flex items-center gap-2 rounded-xl border border-input bg-card p-1.5 pl-4 shadow-lg transition-colors focus-within:border-primary/50">
        <Input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") submit();
          }}
          placeholder="Describe the view you need…"
          maxLength={500}
          autoFocus={autoFocus}
          className="h-9 border-0 bg-transparent px-0 text-[13.5px] shadow-none focus-visible:ring-0"
        />
        <Button
          size="icon"
          className="h-8 w-8 shrink-0 rounded-lg"
          onClick={submit}
          disabled={!draft.trim()}
          title="Generate a canvas for this intent"
        >
          <ArrowUp />
        </Button>
      </div>
      <p className="mt-2 text-center font-mono text-[10px] tracking-wide text-muted-foreground/60">
        panels assemble to fit your request · adapting to live data, packs and your pins
      </p>
    </div>
  );
}
