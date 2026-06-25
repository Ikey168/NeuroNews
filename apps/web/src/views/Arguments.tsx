import { useState, useEffect } from "react";
import { fonts, palette, colors, ACCENT, accentSoft, accentBorder } from "../theme";
import { useArgumentClaims, useArgumentStance, useArgumentFrames } from "../lib/queries";
import { mockFramesBySourceType, mockPositions, mockConflicts } from "../data/mock";
import PageHeader from "../components/PageHeader";
import SourceBadge from "../components/SourceBadge";
import Sparkline from "../components/charts/Sparkline";
import type { ArgumentTab, SourceType, StanceSummary } from "../types";

// ─── Constants ────────────────────────────────────────────────────────────────

const SOURCE_TYPES: Array<{ key: string; label: string }> = [
  { key: "all",        label: "All" },
  { key: "news",       label: "News" },
  { key: "blog",       label: "Blog" },
  { key: "paper",      label: "Paper" },
  { key: "transcript", label: "Transcript" },
  { key: "book",       label: "Book" },
  { key: "note",       label: "Note" },
];

const TABS: Array<{ key: ArgumentTab; label: string; glyph: string }> = [
  { key: "claims",      label: "Claims",      glyph: "◈" },
  { key: "stance",      label: "Stance",      glyph: "◑" },
  { key: "frames",      label: "Frames",      glyph: "⬡" },
  { key: "positions",   label: "Positions",   glyph: "⤳" },
  { key: "controversy", label: "Controversy", glyph: "⊗" },
];

const FRAME_LABELS = ["economic", "security", "humanitarian", "legal", "political", "scientific", "other"];

const FRAME_COLORS: Record<string, string> = {
  economic:     palette.pos,
  security:     palette.neg,
  humanitarian: palette.amber,
  legal:        palette.teal,
  political:    palette.violet,
  scientific:   palette.blue,
  other:        palette.dim,
};

const STANCE_COLORS = {
  supportive: palette.pos,
  critical:   palette.neg,
  neutral:    palette.neu,
  ambiguous:  palette.amber,
};

const VERDICT_COLORS: Record<string, string> = {
  verified:   palette.pos,
  disputed:   palette.neg,
  unverified: palette.amber,
};

const POSITION_COLORS: Record<string, string> = { for: palette.pos, against: palette.neg, neutral: palette.neu };

// ─── Shared style tokens ─────────────────────────────────────────────────────

const card = { background: colors.card, border: `1px solid ${colors.border}`, borderRadius: 10 } as const;
const mono10 = { fontFamily: fonts.mono, fontSize: 10, color: palette.dim, letterSpacing: "0.1em", textTransform: "uppercase" as const };

// ─── URL param helpers ────────────────────────────────────────────────────────

function readParam(key: string): string | null {
  return new URLSearchParams(window.location.search).get(key);
}

function setParam(key: string, value: string) {
  const p = new URLSearchParams(window.location.search);
  p.set(key, value);
  history.pushState({}, "", `?${p}`);
}

// ─── Sub-components ───────────────────────────────────────────────────────────

function FilterPills({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  return (
    <div style={{ display: "flex", gap: 5, flexWrap: "wrap" }}>
      {SOURCE_TYPES.map(({ key, label }) => {
        const active = value === key;
        return (
          <button
            key={key}
            onClick={() => onChange(key)}
            style={{
              fontFamily: fonts.mono,
              fontSize: 10.5,
              padding: "3px 10px",
              borderRadius: 6,
              border: active ? `1px solid ${accentBorder(ACCENT)}` : `1px solid ${colors.border2}`,
              background: active ? accentSoft(ACCENT) : "transparent",
              color: active ? ACCENT : palette.dim,
              cursor: "pointer",
              letterSpacing: "0.06em",
            }}
          >
            {label}
          </button>
        );
      })}
    </div>
  );
}

function TabBar({ active, onChange }: { active: ArgumentTab; onChange: (t: ArgumentTab) => void }) {
  return (
    <div style={{ display: "flex", gap: 2, borderBottom: `1px solid ${colors.border}`, marginBottom: 16 }}>
      {TABS.map(({ key, label, glyph }) => {
        const isActive = active === key;
        return (
          <button
            key={key}
            onClick={() => onChange(key)}
            style={{
              fontFamily: fonts.sans,
              fontSize: 13,
              fontWeight: 500,
              padding: "9px 14px",
              border: "none",
              borderBottom: isActive ? `2px solid ${ACCENT}` : "2px solid transparent",
              background: "transparent",
              color: isActive ? ACCENT : palette.dim,
              cursor: "pointer",
              display: "flex",
              alignItems: "center",
              gap: 6,
              marginBottom: -1,
              transition: "color .12s",
            }}
          >
            <span style={{ fontSize: 12 }}>{glyph}</span>
            {label}
          </button>
        );
      })}
    </div>
  );
}

// ─── Claims panel ─────────────────────────────────────────────────────────────

function ClaimsPanel({ sourceType }: { sourceType: string }) {
  const { data: claims, source, isLoading } = useArgumentClaims();
  const filtered = sourceType === "all" ? claims : claims.filter((c) => c.source_type === sourceType);
  const claimsOnly = filtered.filter((c) => c.is_claim);

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
        <div>
          <span style={{ fontFamily: fonts.grotesk, fontWeight: 600, fontSize: 14 }}>Detected Claims</span>
          <span style={{ ...mono10, marginLeft: 10, fontFamily: fonts.mono, fontSize: 10 }}>{claimsOnly.length} of {filtered.length} sentences</span>
        </div>
        <SourceBadge source={source} isLoading={isLoading} />
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {filtered.map((c, i) => {
          const verdict = c.factcheck_verdict;
          const verdictColor = verdict ? VERDICT_COLORS[verdict] : palette.faint;
          return (
            <div
              key={`${c.document_id}-${i}`}
              style={{
                ...card,
                padding: "12px 16px",
                borderLeft: `3px solid ${c.is_claim ? palette.blue : colors.border2}`,
                opacity: c.is_claim ? 1 : 0.6,
              }}
            >
              <div style={{ display: "flex", alignItems: "flex-start", gap: 12 }}>
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 13, fontWeight: 500, color: colors.text, lineHeight: 1.5 }}>{c.text}</div>
                  <div style={{ marginTop: 6, fontFamily: fonts.mono, fontSize: 10.5, color: palette.faint }}>{c.title}</div>
                </div>
                <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 6, flexShrink: 0 }}>
                  <span style={{
                    fontFamily: fonts.mono, fontSize: 9.5, fontWeight: 700, letterSpacing: "0.1em",
                    color: c.is_claim ? palette.blue : palette.faint,
                    background: `${c.is_claim ? palette.blue : palette.faint}18`,
                    border: `1px solid ${c.is_claim ? palette.blue : palette.faint}40`,
                    borderRadius: 5, padding: "2px 7px",
                  }}>
                    {c.is_claim ? "CLAIM" : "NON-CLAIM"}
                  </span>

                  <span style={{
                    fontFamily: fonts.mono, fontSize: 9.5, letterSpacing: "0.08em",
                    color: verdictColor, background: `${verdictColor}18`,
                    border: `1px solid ${verdictColor}40`, borderRadius: 5, padding: "2px 7px",
                  }}>
                    {verdict ? verdict.toUpperCase() : "—"}
                  </span>

                  <SourceTypePill type={c.source_type} />
                </div>
              </div>

              {/* Confidence bar */}
              <div style={{ marginTop: 8, display: "flex", alignItems: "center", gap: 8 }}>
                <span style={{ ...mono10, width: 70 }}>Confidence</span>
                <div style={{ flex: 1, height: 4, background: colors.cardInner, borderRadius: 2 }}>
                  <div style={{ width: `${c.confidence * 100}%`, height: "100%", borderRadius: 2, background: c.is_claim ? palette.blue : palette.dim }} />
                </div>
                <span style={{ fontFamily: fonts.mono, fontSize: 10.5, color: palette.dim, width: 36, textAlign: "right" }}>
                  {Math.round(c.confidence * 100)}%
                </span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ─── Stance panel ─────────────────────────────────────────────────────────────

function StanceCounts({ s, sourceType }: { s: StanceSummary; sourceType: string }) {
  const breakdown = sourceType !== "all" ? s.by_source[sourceType as SourceType] : null;
  const counts = breakdown ?? { supportive: s.supportive, critical: s.critical, neutral: s.neutral, ambiguous: s.ambiguous };
  const total = counts.supportive + counts.critical + counts.neutral + counts.ambiguous || 1;

  return (
    <div style={{ display: "flex", height: 8, borderRadius: 3, overflow: "hidden", flex: 1, margin: "0 12px" }}>
      {(["supportive", "critical", "neutral", "ambiguous"] as const).map((key) => {
        const pct = (counts[key] / total) * 100;
        return pct > 0 ? (
          <div key={key} title={`${key}: ${Math.round(pct)}%`}
            style={{ width: `${pct}%`, background: STANCE_COLORS[key], transition: "width .3s" }} />
        ) : null;
      })}
    </div>
  );
}

function StancePanel({ sourceType }: { sourceType: string }) {
  const { data: stances, source, isLoading } = useArgumentStance();

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
        <span style={{ fontFamily: fonts.grotesk, fontWeight: 600, fontSize: 14 }}>Stance by Topic</span>
        <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
          <div style={{ display: "flex", gap: 10 }}>
            {(["supportive", "critical", "neutral", "ambiguous"] as const).map((k) => (
              <span key={k} style={{ fontFamily: fonts.mono, fontSize: 9.5, color: STANCE_COLORS[k], display: "flex", alignItems: "center", gap: 4 }}>
                <span style={{ width: 7, height: 7, borderRadius: "50%", background: STANCE_COLORS[k], display: "inline-block" }} />
                {k}
              </span>
            ))}
          </div>
          <SourceBadge source={source} isLoading={isLoading} />
        </div>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        {stances.map((s) => (
          <div key={s.topic} style={{ ...card, padding: "13px 16px" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <span style={{ width: 180, fontWeight: 500, fontSize: 13, flexShrink: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {s.topic}
              </span>
              <StanceCounts s={s} sourceType={sourceType} />
              <span style={{ fontFamily: fonts.mono, fontSize: 10.5, color: palette.faint, width: 56, textAlign: "right", flexShrink: 0 }}>
                {s.total} docs
              </span>
              <div style={{ flexShrink: 0 }}>
                <Sparkline values={s.drift} color={ACCENT} />
              </div>
            </div>

            {/* Per-stance counts */}
            <div style={{ marginTop: 8, display: "flex", gap: 16 }}>
              {(["supportive", "critical", "neutral", "ambiguous"] as const).map((k) => {
                const breakdown = sourceType !== "all" ? s.by_source[sourceType as SourceType] : null;
                const v = breakdown ? breakdown[k] : s[k];
                return (
                  <span key={k} style={{ fontFamily: fonts.mono, fontSize: 10, color: STANCE_COLORS[k] }}>
                    {v} {k}
                  </span>
                );
              })}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ─── Frames panel ─────────────────────────────────────────────────────────────

function FramesPanel({ sourceType }: { sourceType: string }) {
  const { data: frames, source, isLoading } = useArgumentFrames(sourceType === "all" ? undefined : sourceType);
  const dist = frames.distribution;
  const maxScore = Math.max(0.01, ...Object.values(dist));

  const crossTypes = ["news", "blog", "paper", "transcript", "book", "note"];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      {/* Distribution chart */}
      <div style={{ ...card, padding: "18px 20px" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
          <div>
            <span style={{ fontFamily: fonts.grotesk, fontWeight: 600, fontSize: 14 }}>Frame Distribution</span>
            <span style={{ ...mono10, marginLeft: 10 }}>
              dominant: <span style={{ color: FRAME_COLORS[frames.dominant] ?? ACCENT }}>{frames.dominant}</span>
              {frames.total_documents > 0 && ` · ${frames.total_documents} docs`}
            </span>
          </div>
          <SourceBadge source={source} isLoading={isLoading} />
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {FRAME_LABELS.sort((a, b) => (dist[b] ?? 0) - (dist[a] ?? 0)).map((frame) => {
            const score = dist[frame] ?? 0;
            const pct = (score / maxScore) * 100;
            const color = FRAME_COLORS[frame] ?? palette.dim;
            return (
              <div key={frame} style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <span style={{ fontFamily: fonts.mono, fontSize: 11, color, width: 110, flexShrink: 0, textTransform: "capitalize" }}>{frame}</span>
                <div style={{ flex: 1, height: 10, background: colors.cardInner, borderRadius: 3 }}>
                  <div style={{ width: `${pct}%`, height: "100%", borderRadius: 3, background: color, transition: "width .4s" }} />
                </div>
                <span style={{ fontFamily: fonts.mono, fontSize: 11, color, width: 40, textAlign: "right" }}>
                  {(score * 100).toFixed(0)}%
                </span>
              </div>
            );
          })}
        </div>
      </div>

      {/* Cross-format comparison table */}
      <div style={{ ...card, padding: "18px 20px", overflowX: "auto" }}>
        <div style={{ fontFamily: fonts.grotesk, fontWeight: 600, fontSize: 14, marginBottom: 14 }}>Cross-Format Comparison</div>
        <table style={{ width: "100%", borderCollapse: "collapse", fontFamily: fonts.mono, fontSize: 11 }}>
          <thead>
            <tr>
              <th style={{ textAlign: "left", padding: "4px 10px 8px 0", color: palette.dim, fontWeight: 400, fontSize: 10, letterSpacing: "0.1em" }}>FRAME</th>
              {crossTypes.map((st) => (
                <th key={st} style={{ textAlign: "right", padding: "4px 8px 8px", color: palette.dim, fontWeight: 400, fontSize: 10, letterSpacing: "0.1em", textTransform: "uppercase" }}>{st}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {FRAME_LABELS.map((frame) => {
              const color = FRAME_COLORS[frame] ?? palette.dim;
              return (
                <tr key={frame} style={{ borderTop: `1px solid ${colors.border}` }}>
                  <td style={{ padding: "7px 10px 7px 0", color, textTransform: "capitalize" }}>{frame}</td>
                  {crossTypes.map((st) => {
                    const val = mockFramesBySourceType[st]?.[frame] ?? 0;
                    const intensity = Math.round(val * 255).toString(16).padStart(2, "0");
                    return (
                      <td key={st} style={{ textAlign: "right", padding: "7px 8px", color: `${color}`, opacity: 0.4 + val * 0.6 }}>
                        <span style={{
                          display: "inline-block", padding: "2px 7px", borderRadius: 4,
                          background: `${color}${intensity}`, color: val > 0.4 ? colors.bg : color,
                        }}>
                          {(val * 100).toFixed(0)}%
                        </span>
                      </td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ─── Positions panel ─────────────────────────────────────────────────────────

function PositionsPanel({ sourceType }: { sourceType: string }) {
  const [topic, setTopic] = useState("Interest Rate Policy");
  const allTopics = Array.from(new Set(mockPositions.map((p) => p.topic)));
  const filtered = mockPositions.filter(
    (p) => p.topic === topic && (sourceType === "all" || p.source_type === sourceType),
  );

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
        <span style={{ fontFamily: fonts.grotesk, fontWeight: 600, fontSize: 14 }}>Actor Policy Positions</span>
        <span style={{ fontFamily: fonts.mono, fontSize: 9.5, color: palette.amber, background: `${palette.amber}14`, border: `1px solid ${palette.amber}40`, borderRadius: 5, padding: "3px 8px", letterSpacing: "0.1em" }}>
          DEMO
        </span>
      </div>

      {/* Topic selector */}
      <div style={{ display: "flex", gap: 6, marginBottom: 16, flexWrap: "wrap" }}>
        {allTopics.map((t) => (
          <button
            key={t}
            onClick={() => setTopic(t)}
            style={{
              fontFamily: fonts.mono, fontSize: 10.5, padding: "4px 11px", borderRadius: 6,
              border: t === topic ? `1px solid ${accentBorder(ACCENT)}` : `1px solid ${colors.border2}`,
              background: t === topic ? accentSoft(ACCENT) : "transparent",
              color: t === topic ? ACCENT : palette.dim, cursor: "pointer",
            }}
          >
            {t}
          </button>
        ))}
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 0 }}>
        {filtered.length === 0 && (
          <div style={{ fontFamily: fonts.mono, fontSize: 12, color: palette.faint, padding: "20px 0", textAlign: "center" }}>
            No positions recorded for this topic / source type.
          </div>
        )}
        {filtered.map((pos, i) => {
          const stanceColor = POSITION_COLORS[pos.stance];
          const isLast = i === filtered.length - 1;
          return (
            <div key={`${pos.actor}-${pos.date}`} style={{ display: "flex", gap: 16 }}>
              {/* Timeline spine */}
              <div style={{ display: "flex", flexDirection: "column", alignItems: "center", flexShrink: 0, width: 20 }}>
                <div style={{ width: 10, height: 10, borderRadius: "50%", background: stanceColor, border: `2px solid ${colors.bg}`, flexShrink: 0, marginTop: 12 }} />
                {!isLast && <div style={{ width: 1, flex: 1, background: colors.border, margin: "2px 0" }} />}
              </div>
              {/* Content */}
              <div style={{ ...card, padding: "12px 14px", marginBottom: 8, flex: 1 }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                  <div>
                    <span style={{ fontWeight: 600, fontSize: 13 }}>{pos.actor}</span>
                    <span style={{
                      marginLeft: 8, fontFamily: fonts.mono, fontSize: 9.5, letterSpacing: "0.08em",
                      color: stanceColor, background: `${stanceColor}18`, border: `1px solid ${stanceColor}40`,
                      borderRadius: 4, padding: "1px 6px",
                    }}>
                      {pos.stance.toUpperCase()}
                    </span>
                  </div>
                  <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                    <SourceTypePill type={pos.source_type} />
                    <span style={{ fontFamily: fonts.mono, fontSize: 10.5, color: palette.faint }}>{pos.date}</span>
                  </div>
                </div>
                <div style={{ marginTop: 6, fontSize: 12.5, color: colors.textMuted, lineHeight: 1.5 }}>{pos.position}</div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ─── Controversy panel ────────────────────────────────────────────────────────

function ControversyPanel({ sourceType: _sourceType }: { sourceType: string }) {
  const sorted = [...mockConflicts].sort((a, b) => b.intensity - a.intensity);

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
        <span style={{ fontFamily: fonts.grotesk, fontWeight: 600, fontSize: 14 }}>Conflict Map</span>
        <div style={{ display: "flex", gap: 8 }}>
          <span style={{ fontFamily: fonts.mono, fontSize: 9.5, color: palette.amber, background: `${palette.amber}14`, border: `1px solid ${palette.amber}40`, borderRadius: 5, padding: "3px 8px", letterSpacing: "0.1em" }}>
            DEMO
          </span>
          <span style={{ fontFamily: fonts.mono, fontSize: 9.5, color: palette.blue, background: `${palette.blue}14`, border: `1px solid ${palette.blue}40`, borderRadius: 5, padding: "3px 8px", letterSpacing: "0.1em" }}>
            GRAPH IN #96
          </span>
        </div>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {sorted.map((c) => {
          const intPct = Math.round(c.intensity * 100);
          const color = c.intensity > 0.75 ? palette.neg : c.intensity > 0.5 ? palette.amber : palette.neu;
          return (
            <div key={`${c.actor_a}-${c.actor_b}`} style={{ ...card, padding: "14px 18px" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                {/* Actor A */}
                <span style={{ fontWeight: 600, fontSize: 13, flex: 1, textAlign: "right" }}>{c.actor_a}</span>
                {/* Conflict indicator */}
                <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 4, flexShrink: 0, minWidth: 80 }}>
                  <span style={{ fontFamily: fonts.mono, fontSize: 9.5, color, letterSpacing: "0.1em" }}>
                    {intPct}% intensity
                  </span>
                  <div style={{ width: 80, height: 6, background: colors.cardInner, borderRadius: 3 }}>
                    <div style={{ width: `${intPct}%`, height: "100%", borderRadius: 3, background: color }} />
                  </div>
                  <span style={{ fontFamily: fonts.mono, fontSize: 9, color: palette.faint }}>{c.source_count} sources</span>
                </div>
                {/* Actor B */}
                <span style={{ fontWeight: 600, fontSize: 13, flex: 1 }}>{c.actor_b}</span>
              </div>
              <div style={{ marginTop: 8, textAlign: "center", fontFamily: fonts.mono, fontSize: 10.5, color: palette.faint }}>
                {c.topic}
              </div>
            </div>
          );
        })}
      </div>

      <div style={{ marginTop: 20, ...card, padding: "14px 18px", borderColor: `${palette.blue}44`, background: `${palette.blue}08` }}>
        <div style={{ fontFamily: fonts.mono, fontSize: 11, color: palette.blue }}>
          ◈ Interactive force-directed conflict graph with source_type colour coding on nodes ships in issue #96.
        </div>
      </div>
    </div>
  );
}

// ─── Source type pill ─────────────────────────────────────────────────────────

function SourceTypePill({ type }: { type: string }) {
  const ST_COLORS: Record<string, string> = {
    news: palette.blue, blog: palette.teal, paper: palette.violet,
    transcript: palette.amber, book: palette.pos, note: palette.dim,
  };
  const color = ST_COLORS[type] ?? palette.dim;
  return (
    <span style={{
      fontFamily: fonts.mono, fontSize: 9, letterSpacing: "0.08em",
      color, background: `${color}18`, border: `1px solid ${color}40`,
      borderRadius: 4, padding: "1px 5px", flexShrink: 0, textTransform: "uppercase" as const,
    }}>
      {type}
    </span>
  );
}

// ─── Main view ────────────────────────────────────────────────────────────────

export default function Arguments() {
  const [tab, setTabRaw] = useState<ArgumentTab>(
    (readParam("arg_tab") as ArgumentTab | null) ?? "claims",
  );
  const [sourceType, setSourceTypeRaw] = useState(readParam("source_type") ?? "all");

  function setTab(t: ArgumentTab) {
    setTabRaw(t);
    setParam("arg_tab", t);
  }

  function setSourceType(v: string) {
    setSourceTypeRaw(v);
    setParam("source_type", v);
  }

  // Sync state if user navigates with browser Back/Forward
  useEffect(() => {
    function onPop() {
      setTabRaw((readParam("arg_tab") as ArgumentTab | null) ?? "claims");
      setSourceTypeRaw(readParam("source_type") ?? "all");
    }
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  return (
    <div>
      <PageHeader
        title="Argument Mining"
        subtitle="Claims · stance · frames · positions · controversy — across all content types"
        right={
          <FilterPills value={sourceType} onChange={setSourceType} />
        }
      />

      <TabBar active={tab} onChange={setTab} />

      {tab === "claims"      && <ClaimsPanel      sourceType={sourceType} />}
      {tab === "stance"      && <StancePanel       sourceType={sourceType} />}
      {tab === "frames"      && <FramesPanel       sourceType={sourceType} />}
      {tab === "positions"   && <PositionsPanel    sourceType={sourceType} />}
      {tab === "controversy" && <ControversyPanel  sourceType={sourceType} />}
    </div>
  );
}
