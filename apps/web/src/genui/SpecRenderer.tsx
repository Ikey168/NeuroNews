// Renders a ui-spec-v1 layout: a 12-column grid of registry panels, each
// wired to the adaptive usage signals.

import { panelComponent } from "./registry";
import type { UISpec } from "./spec";
import type { AdaptiveSignals } from "./signals";

interface Props {
  spec: UISpec;
  adaptive: AdaptiveSignals;
}

export default function SpecRenderer({ spec, adaptive }: Props) {
  const dataPanels = spec.panels.filter((p) => p.type !== "note").length;
  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(12, 1fr)", gap: 12 }}>
      {spec.panels.map((panel) => {
        const Component = panelComponent(panel.type);
        // A lone data panel stretches to the full row instead of leaving
        // half the canvas empty.
        const span = dataPanels === 1 && panel.type !== "note" ? 12 : Math.max(3, Math.min(12, panel.span || 6));
        return (
          <div key={panel.id} style={{ gridColumn: `span ${span}`, minWidth: 0 }}>
            <Component
              panel={panel}
              pinned={adaptive.isPinned(panel.type)}
              onPin={() => adaptive.togglePin(panel.type)}
              onDismiss={() => adaptive.dismiss(panel.type)}
              onTouch={() => adaptive.touch(panel.type)}
            />
          </div>
        );
      })}
    </div>
  );
}
