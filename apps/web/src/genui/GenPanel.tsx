// Chrome shared by every generated panel: title, provenance badge, and the
// pin / dismiss controls that feed the adaptive usage signals.

import type { CSSProperties, ReactNode } from "react";
import { ACCENT, fonts } from "../theme";
import type { Source } from "../lib/queries";
import SourceBadge from "../components/SourceBadge";
import Hover from "../components/Hover";
import type { PanelSpec } from "./spec";

const card: CSSProperties = {
  background: "#11151c",
  border: "1px solid #1c2330",
  borderRadius: 10,
  padding: "14px 16px",
  height: "100%",
  display: "flex",
  flexDirection: "column",
  minWidth: 0,
};

const iconBtn: CSSProperties = {
  fontFamily: fonts.mono,
  fontSize: 12,
  lineHeight: 1,
  background: "none",
  border: "none",
  cursor: "pointer",
  color: "#5b6675",
  padding: "3px 4px",
  borderRadius: 5,
};

export interface GenPanelProps {
  panel: PanelSpec;
  pinned: boolean;
  onPin: () => void;
  onDismiss: () => void;
  onTouch: () => void;
  source?: Source;
  isLoading?: boolean;
  children: ReactNode;
}

export default function GenPanel({
  panel,
  pinned,
  onPin,
  onDismiss,
  onTouch,
  source,
  isLoading,
  children,
}: GenPanelProps) {
  // The plan note is meta-content: pinning/muting/weighting it makes no sense.
  const adjustable = panel.type !== "note";
  return (
    <div style={card} onClick={adjustable ? onTouch : undefined} title={panel.rationale || undefined}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
        <div
          style={{
            fontFamily: fonts.grotesk,
            fontWeight: 600,
            fontSize: 13.5,
            flex: 1,
            minWidth: 0,
            whiteSpace: "nowrap",
            overflow: "hidden",
            textOverflow: "ellipsis",
          }}
        >
          {panel.title}
        </div>
        {source ? <SourceBadge source={source} isLoading={isLoading} /> : null}
        {adjustable ? (
          <>
        <Hover
          as="button"
          onClick={(e) => {
            e.stopPropagation();
            onPin();
          }}
          style={{ ...iconBtn, color: pinned ? ACCENT : "#5b6675" }}
          hoverStyle={{ background: "#161d28", color: pinned ? ACCENT : "#e6eaf0" }}
          title={pinned ? "Unpin — stop always including this panel" : "Pin — always include this panel"}
        >
          {pinned ? "★" : "☆"}
        </Hover>
        <Hover
          as="button"
          onClick={(e) => {
            e.stopPropagation();
            onDismiss();
          }}
          style={iconBtn}
          hoverStyle={{ background: "#161d28", color: "#e6eaf0" }}
          title="Mute — hide this panel type from future canvases"
        >
          ✕
        </Hover>
          </>
        ) : null}
      </div>
      <div style={{ flex: 1, minHeight: 0 }}>{children}</div>
    </div>
  );
}
