import { useState } from "react";
import { fonts } from "./theme";
import type { ViewKey } from "./types";
import { useTicker } from "./lib/queries";
import Sidebar from "./components/Sidebar";
import TopBar from "./components/TopBar";
import BreakingTicker from "./components/BreakingTicker";
import Dashboard from "./views/Dashboard";
import Library from "./views/Library";
import EntityGraphView from "./views/EntityGraphView";
import DocumentReader from "./views/DocumentReader";
import Sentiment from "./views/Sentiment";
import Clusters from "./views/Clusters";
import Trending from "./views/Trending";
import Workspaces from "./views/Workspaces";
import Watchlists from "./views/Watchlists";
import Timeline from "./views/Timeline";
import Arguments from "./views/Arguments";

export default function App() {
  const [view, setView] = useState<ViewKey>("dashboard");
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
      <Sidebar view={view} setView={setView} ingestRate="64" />

      <div style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0 }}>
        <TopBar />
        <BreakingTicker text={ticker} />
        <main style={{ flex: 1, overflowY: "auto", padding: "22px 24px 40px" }}>
          {view === "dashboard" && <Dashboard setView={setView} />}
          {view === "library" && <Library />}
          {view === "knowledge" && <EntityGraphView />}
          {view === "reader" && <DocumentReader />}
          {view === "sentiment" && <Sentiment />}
          {view === "clusters" && <Clusters />}
          {view === "trending" && <Trending />}
          {view === "workspaces" && <Workspaces />}
          {view === "watchlists" && <Watchlists />}
          {view === "timeline" && <Timeline />}
          {view === "arguments" && <Arguments />}
        </main>
      </div>
    </div>
  );
}
