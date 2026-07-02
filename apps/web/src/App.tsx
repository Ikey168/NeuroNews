import { fonts } from "./theme";
import { useTicker } from "./lib/queries";
import { useCanvases } from "./genui/canvases";
import Sidebar from "./components/Sidebar";
import TopBar from "./components/TopBar";
import BreakingTicker from "./components/BreakingTicker";
import Canvas from "./genui/Canvas";

// The app is a single generative surface: every screen is a canvas planned
// from an intent (sidebar presets or free text) — there are no fixed views.
export default function App() {
  const manager = useCanvases();
  const { data: ticker } = useTicker();

  return (
    <div
      style={{
        display: "flex",
        height: "100vh",
        width: "100%",
        background: "#0a0d12",
        color: "#e6eaf0",
        fontFamily: fonts.sans,
        overflow: "hidden",
      }}
    >
      <Sidebar
        canvases={manager.canvases}
        activeId={manager.active.id}
        onSelect={manager.setActive}
        onOpen={manager.open}
        onRemove={manager.remove}
        ingestRate="64"
      />

      <div style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0 }}>
        <TopBar />
        <BreakingTicker text={ticker} />
        <main style={{ flex: 1, overflowY: "auto", padding: "22px 24px 40px" }}>
          <Canvas key={manager.active.id} canvas={manager.active} onIntent={manager.open} />
        </main>
      </div>
    </div>
  );
}
