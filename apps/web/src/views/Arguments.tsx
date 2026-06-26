import { useState, useEffect, useRef, useCallback } from "react";
import { fonts, palette, colors, ACCENT, accentSoft, accentBorder } from "../theme";
import { useArgumentClaims, useArgumentStance, useArgumentFrames, useArgumentPositions, useArgumentControversy, useArgumentControversyGraph, useArgumentStanceSources, useArgumentStanceDrift } from "../lib/queries";
import { mockFramesBySourceType } from "../data/mock";
import PageHeader from "../components/PageHeader";
import SourceBadge from "../components/SourceBadge";
import Sparkline from "../components/charts/Sparkline";
import type { ArgumentTab, SourceType, StanceSummary, ControversyNode, ControversyEdge, SourceStance, StanceDriftEvent } from "../types";

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
  { key: "sources",     label: "Sources",     glyph: "◎" },
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
  mixed:      palette.amber,
  unverified: palette.dim,
};

const VERDICT_LABELS: Record<string, string> = {
  verified:   "✓ TRUE",
  disputed:   "✗ FALSE",
  mixed:      "⚠ MIXED",
  unverified: "? UNVERIFIED",
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
          const verdictLabel = verdict ? (VERDICT_LABELS[verdict] ?? verdict.toUpperCase()) : "—";
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

                  {c.factcheck_url ? (
                    <a
                      href={c.factcheck_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      title={c.factcheck_publisher ?? undefined}
                      style={{
                        fontFamily: fonts.mono, fontSize: 9.5, letterSpacing: "0.08em",
                        color: verdictColor, background: `${verdictColor}18`,
                        border: `1px solid ${verdictColor}40`, borderRadius: 5, padding: "2px 7px",
                        textDecoration: "none",
                      }}
                    >
                      {verdictLabel}
                    </a>
                  ) : (
                    <span style={{
                      fontFamily: fonts.mono, fontSize: 9.5, letterSpacing: "0.08em",
                      color: verdictColor, background: `${verdictColor}18`,
                      border: `1px solid ${verdictColor}40`, borderRadius: 5, padding: "2px 7px",
                    }}>
                      {verdictLabel}
                    </span>
                  )}

                  {c.factcheck_publisher && (
                    <span style={{ fontFamily: fonts.mono, fontSize: 9, color: palette.faint, letterSpacing: "0.06em" }}>
                      {c.factcheck_publisher}
                    </span>
                  )}

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
  const { data: positions, source, isLoading } = useArgumentPositions(
    sourceType !== "all" ? { source_type: sourceType } : undefined,
  );
  const allTopics = Array.from(new Set(positions.map((p) => p.topic)));
  const [selectedTopic, setSelectedTopic] = useState<string | null>(null);
  const topic = selectedTopic !== null && allTopics.includes(selectedTopic)
    ? selectedTopic
    : (allTopics[0] ?? "");
  const filtered = positions.filter(
    (p) => p.topic === topic && (sourceType === "all" || p.source_type === sourceType),
  );

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
        <span style={{ fontFamily: fonts.grotesk, fontWeight: 600, fontSize: 14 }}>Actor Policy Positions</span>
        <SourceBadge source={source} isLoading={isLoading} />
      </div>

      {/* Topic selector */}
      <div style={{ display: "flex", gap: 6, marginBottom: 16, flexWrap: "wrap" }}>
        {allTopics.map((t) => (
          <button
            key={t}
            onClick={() => setSelectedTopic(t)}
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

const ST_COLORS: Record<string, string> = {
  news: palette.blue, blog: palette.teal, paper: palette.violet,
  transcript: palette.amber, book: palette.pos, note: palette.dim,
};

interface SimNode extends ControversyNode {
  x: number; y: number; vx: number; vy: number;
}

function useForceSimulation(
  nodes: ControversyNode[],
  edges: ControversyEdge[],
  width: number,
  height: number,
) {
  const simRef = useRef<SimNode[]>([]);
  const rafRef = useRef<number>(0);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    cancelAnimationFrame(rafRef.current);
    simRef.current = nodes.map((n, i) => ({
      ...n,
      x: width / 2 + Math.cos((i / nodes.length) * Math.PI * 2) * 160,
      y: height / 2 + Math.sin((i / nodes.length) * Math.PI * 2) * 120,
      vx: 0, vy: 0,
    }));
    let iter = 0;

    function step() {
      const sim = simRef.current;
      const alpha = Math.max(0.01, 0.8 * Math.pow(0.975, iter));
      const cx = width / 2, cy = height / 2;
      const R = 18;

      for (let i = 0; i < sim.length; i++) {
        sim[i].vx += (cx - sim[i].x) * 0.012 * alpha;
        sim[i].vy += (cy - sim[i].y) * 0.012 * alpha;
        for (let j = i + 1; j < sim.length; j++) {
          const dx = sim[i].x - sim[j].x;
          const dy = sim[i].y - sim[j].y;
          const dist = Math.sqrt(dx * dx + dy * dy) || 1;
          const force = (alpha * 3200) / (dist * dist);
          const fx = (dx / dist) * force;
          const fy = (dy / dist) * force;
          sim[i].vx += fx; sim[i].vy += fy;
          sim[j].vx -= fx; sim[j].vy -= fy;
        }
      }

      for (const e of edges) {
        const a = sim.find((n) => n.id === e.source);
        const b = sim.find((n) => n.id === e.target);
        if (!a || !b) continue;
        const dx = b.x - a.x, dy = b.y - a.y;
        const dist = Math.sqrt(dx * dx + dy * dy) || 1;
        const restLen = 120;
        const force = ((dist - restLen) / dist) * alpha * 0.35 * e.severity;
        const fx = dx * force, fy = dy * force;
        a.vx += fx; a.vy += fy;
        b.vx -= fx; b.vy -= fy;
      }

      for (const n of sim) {
        n.vx *= 0.72; n.vy *= 0.72;
        n.x = Math.max(R, Math.min(width - R, n.x + n.vx));
        n.y = Math.max(R, Math.min(height - R, n.y + n.vy));
      }

      iter++;
      setTick((t) => t + 1);
      if (iter < 220) rafRef.current = requestAnimationFrame(step);
    }

    rafRef.current = requestAnimationFrame(step);
    return () => cancelAnimationFrame(rafRef.current);
  }, [nodes, edges, width, height]);

  return { sim: simRef.current, tick };
}

function ConflictGraph({
  nodes,
  edges,
  selectedId,
  onSelect,
}: {
  nodes: ControversyNode[];
  edges: ControversyEdge[];
  selectedId: string | null;
  onSelect: (id: string | null) => void;
}) {
  const W = 740, H = 420;
  const { sim } = useForceSimulation(nodes, edges, W, H);

  const posMap = new Map(sim.map((n) => [n.id, { x: n.x, y: n.y }]));

  return (
    <svg
      width="100%"
      viewBox={`0 0 ${W} ${H}`}
      style={{ display: "block", background: colors.cardInner, borderRadius: 8 }}
      onClick={() => onSelect(null)}
    >
      <defs>
        <marker id="arr" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto">
          <path d="M0,0 L6,3 L0,6 Z" fill={`${palette.neg}88`} />
        </marker>
      </defs>

      {/* Edges */}
      {edges.map((e, i) => {
        const a = posMap.get(e.source);
        const b = posMap.get(e.target);
        if (!a || !b) return null;
        const w = 1 + e.severity * 3.5;
        const opacity = selectedId
          ? e.source === selectedId || e.target === selectedId ? 0.85 : 0.12
          : 0.45;
        return (
          <line key={i}
            x1={a.x} y1={a.y} x2={b.x} y2={b.y}
            stroke={palette.neg}
            strokeWidth={w}
            strokeOpacity={opacity}
            markerEnd="url(#arr)"
          />
        );
      })}

      {/* Nodes */}
      {sim.map((n) => {
        const color = ST_COLORS[n.source_type] ?? palette.dim;
        const isSelected = n.id === selectedId;
        const dimmed = selectedId !== null && !isSelected &&
          !edges.some((e) => e.source === selectedId && e.target === n.id || e.target === selectedId && e.source === n.id);
        return (
          <g key={n.id} transform={`translate(${n.x},${n.y})`}
            style={{ cursor: "pointer" }}
            onClick={(ev) => { ev.stopPropagation(); onSelect(isSelected ? null : n.id); }}
          >
            <circle r={isSelected ? 20 : 14}
              fill={`${color}22`}
              stroke={isSelected ? color : `${color}88`}
              strokeWidth={isSelected ? 2.5 : 1.5}
              opacity={dimmed ? 0.2 : 1}
            />
            <text
              textAnchor="middle" dominantBaseline="middle"
              fontSize={9} fill={color}
              opacity={dimmed ? 0.2 : 1}
              style={{ pointerEvents: "none", userSelect: "none", fontFamily: fonts.mono }}
            >
              {n.label.length > 10 ? n.label.slice(0, 9) + "…" : n.label}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

function NodeDetail({
  node,
  edges,
  nodes,
  onClose,
}: {
  node: ControversyNode;
  edges: ControversyEdge[];
  nodes: ControversyNode[];
  onClose: () => void;
}) {
  const color = ST_COLORS[node.source_type] ?? palette.dim;
  const linked = edges
    .filter((e) => e.source === node.id || e.target === node.id)
    .map((e) => {
      const peerId = e.source === node.id ? e.target : e.source;
      const peer = nodes.find((n) => n.id === peerId);
      return peer ? { peer, edge: e } : null;
    })
    .filter(Boolean) as { peer: ControversyNode; edge: ControversyEdge }[];

  return (
    <div style={{ ...card, padding: "16px 18px", borderLeft: `3px solid ${color}` }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
        <div>
          <span style={{ fontWeight: 600, fontSize: 13 }}>{node.source}</span>
          <SourceTypePill type={node.source_type} />
          <span style={{ fontFamily: fonts.mono, fontSize: 10, color: palette.faint, marginLeft: 8 }}>
            {node.date ?? "—"} · {node.topic}
          </span>
        </div>
        <button onClick={onClose} style={{ background: "none", border: "none", color: palette.dim, cursor: "pointer", fontSize: 16, lineHeight: 1 }}>
          ✕
        </button>
      </div>
      <div style={{ marginTop: 10, fontSize: 13, lineHeight: 1.6, color: colors.text }}>
        "{node.claim_text}"
      </div>
      <div style={{ marginTop: 8 }}>
        <div style={{ ...mono10, marginBottom: 6 }}>confidence</div>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <div style={{ flex: 1, height: 4, background: colors.cardInner, borderRadius: 2 }}>
            <div style={{ width: `${node.confidence * 100}%`, height: "100%", borderRadius: 2, background: color }} />
          </div>
          <span style={{ fontFamily: fonts.mono, fontSize: 10, color }}>{Math.round(node.confidence * 100)}%</span>
        </div>
      </div>
      {linked.length > 0 && (
        <div style={{ marginTop: 14 }}>
          <div style={{ ...mono10, marginBottom: 8 }}>conflicting with ({linked.length})</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            {linked.map(({ peer, edge }) => {
              const pcolor = ST_COLORS[peer.source_type] ?? palette.dim;
              const sev = Math.round(edge.severity * 100);
              return (
                <div key={peer.id} style={{ background: colors.cardInner, borderRadius: 6, padding: "8px 12px", display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 10 }}>
                  <div style={{ flex: 1 }}>
                    <span style={{ fontFamily: fonts.mono, fontSize: 10, color: pcolor, marginRight: 6 }}>{peer.source}</span>
                    <span style={{ fontSize: 11.5, color: colors.textMuted }}>"{peer.claim_text.slice(0, 90)}{peer.claim_text.length > 90 ? "…" : ""}"</span>
                  </div>
                  <span style={{ fontFamily: fonts.mono, fontSize: 9, color: sev >= 75 ? palette.neg : palette.amber, background: `${sev >= 75 ? palette.neg : palette.amber}18`, border: `1px solid ${sev >= 75 ? palette.neg : palette.amber}40`, borderRadius: 4, padding: "2px 6px", flexShrink: 0 }}>
                    {sev}% sev
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

function ControversyPanel({ sourceType }: { sourceType: string }) {
  const [topic, setTopicFilter] = useState<string | null>(null);
  const [dateRange, setDateRange] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const { data: conflicts, source: listSource, isLoading: listLoading } = useArgumentControversy(
    sourceType !== "all" ? { source_type: sourceType } : undefined,
  );
  const params: { topic?: string; source_type?: string; date_range?: string } = {};
  if (sourceType !== "all") params.source_type = sourceType;
  if (topic) params.topic = topic;
  if (dateRange) params.date_range = dateRange;
  const { data: graph, source: graphSource, isLoading: graphLoading } = useArgumentControversyGraph(
    Object.keys(params).length ? params : undefined,
  );

  const allTopics = Array.from(new Set([
    ...graph.nodes.map((n) => n.topic),
    ...conflicts.map((c) => c.topic),
  ])).sort();

  const filteredNodes = topic ? graph.nodes.filter((n) => n.topic === topic) : graph.nodes;
  const filteredNodeIds = new Set(filteredNodes.map((n) => n.id));
  const filteredEdges = graph.edges.filter((e) => filteredNodeIds.has(e.source) && filteredNodeIds.has(e.target));

  const selectedNode = selectedId ? filteredNodes.find((n) => n.id === selectedId) ?? null : null;

  const onSelect = useCallback((id: string | null) => {
    setSelectedId(id);
  }, []);

  const DATE_RANGES = [
    { key: null, label: "All time" },
    { key: "7d",  label: "7 days" },
    { key: "30d", label: "30 days" },
    { key: "90d", label: "90 days" },
  ];

  return (
    <div>
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
        <span style={{ fontFamily: fonts.grotesk, fontWeight: 600, fontSize: 14 }}>Conflict Graph</span>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <SourceBadge source={graphSource} isLoading={graphLoading} />
        </div>
      </div>

      {/* Filters row */}
      <div style={{ display: "flex", gap: 16, marginBottom: 14, flexWrap: "wrap", alignItems: "center" }}>
        {/* Topic picker */}
        <div style={{ display: "flex", gap: 5, flexWrap: "wrap", alignItems: "center" }}>
          <span style={{ ...mono10, marginRight: 4 }}>Topic</span>
          {[{ key: null, label: "All" }, ...allTopics.map((t) => ({ key: t, label: t }))].map(({ key, label }) => (
            <button key={label} onClick={() => { setTopicFilter(key); setSelectedId(null); }}
              style={{
                fontFamily: fonts.mono, fontSize: 10, padding: "3px 9px", borderRadius: 5, cursor: "pointer",
                border: topic === key ? `1px solid ${accentBorder(ACCENT)}` : `1px solid ${colors.border2}`,
                background: topic === key ? accentSoft(ACCENT) : "transparent",
                color: topic === key ? ACCENT : palette.dim,
              }}
            >{label}</button>
          ))}
        </div>
        {/* Date range */}
        <div style={{ display: "flex", gap: 5, alignItems: "center" }}>
          <span style={{ ...mono10, marginRight: 4 }}>Period</span>
          {DATE_RANGES.map(({ key, label }) => (
            <button key={label} onClick={() => setDateRange(key)}
              style={{
                fontFamily: fonts.mono, fontSize: 10, padding: "3px 9px", borderRadius: 5, cursor: "pointer",
                border: dateRange === key ? `1px solid ${accentBorder(ACCENT)}` : `1px solid ${colors.border2}`,
                background: dateRange === key ? accentSoft(ACCENT) : "transparent",
                color: dateRange === key ? ACCENT : palette.dim,
              }}
            >{label}</button>
          ))}
        </div>
      </div>

      {/* Legend */}
      <div style={{ display: "flex", gap: 14, marginBottom: 12, flexWrap: "wrap" }}>
        {Object.entries(ST_COLORS).map(([type, color]) => (
          <span key={type} style={{ display: "flex", alignItems: "center", gap: 4, fontFamily: fonts.mono, fontSize: 9.5, color }}>
            <span style={{ width: 8, height: 8, borderRadius: "50%", background: color, display: "inline-block" }} />
            {type}
          </span>
        ))}
        <span style={{ fontFamily: fonts.mono, fontSize: 9.5, color: palette.faint, marginLeft: 8 }}>
          edge thickness = conflict severity · click node for details
        </span>
      </div>

      {/* Graph */}
      <div style={{ ...card, padding: 12, marginBottom: 14 }}>
        {filteredNodes.length === 0 ? (
          <div style={{ height: 200, display: "flex", alignItems: "center", justifyContent: "center", fontFamily: fonts.mono, fontSize: 12, color: palette.faint }}>
            No conflict data for selected filters.
          </div>
        ) : (
          <ConflictGraph nodes={filteredNodes} edges={filteredEdges} selectedId={selectedId} onSelect={onSelect} />
        )}
      </div>

      {/* Node detail panel */}
      {selectedNode && (
        <div style={{ marginBottom: 14 }}>
          <NodeDetail node={selectedNode} edges={filteredEdges} nodes={filteredNodes} onClose={() => setSelectedId(null)} />
        </div>
      )}

      {/* Conflict list (collapsed summary) */}
      <div style={{ marginTop: 4 }}>
        <div style={{ ...mono10, marginBottom: 8 }}>Top conflicts by intensity</div>
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          {[...conflicts].sort((a, b) => b.intensity - a.intensity).slice(0, 5).map((c) => {
            const intPct = Math.round(c.intensity * 100);
            const color = c.intensity > 0.75 ? palette.neg : c.intensity > 0.5 ? palette.amber : palette.neu;
            return (
              <div key={`${c.actor_a}-${c.actor_b}`} style={{ ...card, padding: "10px 14px", display: "flex", alignItems: "center", gap: 10 }}>
                <span style={{ fontWeight: 600, fontSize: 12, flex: 1, textAlign: "right", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{c.actor_a}</span>
                <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 3, flexShrink: 0, minWidth: 70 }}>
                  <div style={{ width: 70, height: 4, background: colors.cardInner, borderRadius: 2 }}>
                    <div style={{ width: `${intPct}%`, height: "100%", borderRadius: 2, background: color }} />
                  </div>
                  <span style={{ fontFamily: fonts.mono, fontSize: 9, color, letterSpacing: "0.08em" }}>{intPct}%</span>
                </div>
                <span style={{ fontWeight: 600, fontSize: 12, flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{c.actor_b}</span>
              </div>
            );
          })}
        </div>
      </div>

      {/* List source badge */}
      <div style={{ marginTop: 10, display: "flex", justifyContent: "flex-end" }}>
        <SourceBadge source={listSource} isLoading={listLoading} />
      </div>
    </div>
  );
}

// ─── Sources panel (#99) ──────────────────────────────────────────────────────

const ST_COLORS_SHARED: Record<string, string> = {
  news: palette.blue, blog: palette.teal, paper: palette.violet,
  transcript: palette.amber, book: palette.pos, note: palette.dim,
};

function StanceBar({ s }: { s: SourceStance }) {
  const { supportive, critical, neutral, ambiguous, total } = s;
  if (total === 0) return null;
  const pct = (n: number) => Math.round((n / total) * 100);
  return (
    <div>
      <div style={{ display: "flex", height: 7, borderRadius: 4, overflow: "hidden", gap: 1 }}>
        {supportive > 0 && <div style={{ flex: supportive, background: STANCE_COLORS.supportive }} title={`Supportive ${pct(supportive)}%`} />}
        {critical   > 0 && <div style={{ flex: critical,   background: STANCE_COLORS.critical   }} title={`Critical ${pct(critical)}%`} />}
        {neutral    > 0 && <div style={{ flex: neutral,    background: STANCE_COLORS.neutral    }} title={`Neutral ${pct(neutral)}%`} />}
        {ambiguous  > 0 && <div style={{ flex: ambiguous,  background: STANCE_COLORS.ambiguous  }} title={`Ambiguous ${pct(ambiguous)}%`} />}
      </div>
      <div style={{ display: "flex", gap: 10, marginTop: 4 }}>
        {([["supportive", supportive], ["critical", critical], ["neutral", neutral], ["ambiguous", ambiguous]] as [string, number][])
          .filter(([, n]) => n > 0)
          .map(([key, n]) => (
            <span key={key} style={{ fontFamily: fonts.mono, fontSize: 10, color: STANCE_COLORS[key as keyof typeof STANCE_COLORS] }}>
              {pct(n)}% {key.slice(0, 3).toUpperCase()}
            </span>
          ))}
      </div>
    </div>
  );
}

// ─── Drift timeline ───────────────────────────────────────────────────────────

function DriftTimeline({ source, sourceType }: { source: string; sourceType: string }) {
  const params = {
    source,
    ...(sourceType !== "all" ? { source_type: sourceType } : {}),
  };
  const { data: events, source: dataSource } = useArgumentStanceDrift(params);

  const filtered = events.filter((e: StanceDriftEvent) => e.source === source);

  function windowLabel(pair: string | null): string {
    if (!pair) return "—";
    const [a, b] = pair.split(":");
    return `${a} → ${b}`;
  }

  return (
    <div style={{ marginTop: 14, paddingTop: 14, borderTop: `1px solid ${colors.border}` }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
        <span style={{ ...mono10 }}>Drift timeline</span>
        <span style={{
          fontFamily: fonts.mono, fontSize: 9, letterSpacing: "0.07em",
          color: dataSource === "live" ? palette.pos : palette.dim,
          background: `${dataSource === "live" ? palette.pos : palette.dim}18`,
          border: `1px solid ${dataSource === "live" ? palette.pos : palette.dim}40`,
          borderRadius: 4, padding: "1px 6px", textTransform: "uppercase",
        }}>{dataSource}</span>
      </div>

      {filtered.length === 0 ? (
        <div style={{ fontFamily: fonts.mono, fontSize: 11, color: palette.dim, padding: "8px 0" }}>
          No drift events detected for this source.
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          {filtered.map((e: StanceDriftEvent, i: number) => {
            const fromColor = STANCE_COLORS[e.from_stance];
            const toColor   = STANCE_COLORS[e.to_stance];
            const delta = e.confidence_delta != null ? `Δ${(e.confidence_delta * 100).toFixed(0)}%` : null;
            return (
              <div key={i} style={{
                display: "flex", alignItems: "center", gap: 10,
                padding: "7px 10px", borderRadius: 7,
                background: colors.cardInner, border: `1px solid ${colors.border2}`,
              }}>
                <span style={{ fontFamily: fonts.mono, fontSize: 10, color: palette.dim, width: 170, flexShrink: 0 }}>
                  {windowLabel(e.window_pair)}
                </span>
                <span style={{ fontFamily: fonts.mono, fontSize: 10, fontWeight: 600, color: fromColor }}>{e.from_stance}</span>
                <span style={{ color: palette.dim, fontSize: 12 }}>→</span>
                <span style={{ fontFamily: fonts.mono, fontSize: 10, fontWeight: 600, color: toColor }}>{e.to_stance}</span>
                {e.topic && (
                  <span style={{ fontFamily: fonts.mono, fontSize: 9, color: palette.dim, marginLeft: "auto", flexShrink: 0 }}>{e.topic}</span>
                )}
                {delta && (
                  <span style={{
                    fontFamily: fonts.mono, fontSize: 9, color: palette.amber,
                    background: `${palette.amber}18`, border: `1px solid ${palette.amber}40`,
                    borderRadius: 4, padding: "1px 5px", flexShrink: 0,
                  }}>{delta}</span>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ─── Sources panel ────────────────────────────────────────────────────────────

function SourcesPanel({ sourceType }: { sourceType: string }) {
  const [selectedTopic, setSelectedTopic] = useState<string>("all");
  const [expandedSource, setExpandedSource] = useState<string | null>(null);
  const params = sourceType !== "all" ? { source_type: sourceType } : undefined;
  const { data: stances, source, isLoading } = useArgumentStanceSources(params);

  const topics = Array.from(new Set(stances.map((s) => s.topic))).sort();
  const filtered = selectedTopic === "all" ? stances : stances.filter((s) => s.topic === selectedTopic);

  // Aggregate per source across all selected topics
  const bySource: Record<string, { source_type: string; rows: SourceStance[]; sup: number; crit: number; neu: number; amb: number; total: number }> = {};
  for (const s of filtered) {
    if (!bySource[s.source]) {
      bySource[s.source] = { source_type: s.source_type, rows: [], sup: 0, crit: 0, neu: 0, amb: 0, total: 0 };
    }
    const b = bySource[s.source];
    b.rows.push(s);
    b.sup += s.supportive; b.crit += s.critical; b.neu += s.neutral; b.amb += s.ambiguous; b.total += s.total;
  }
  const sorted = Object.entries(bySource).sort(([, a], [, b]) => b.total - a.total);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <span style={{ fontFamily: fonts.grotesk, fontWeight: 600, fontSize: 14 }}>Stance by Source</span>
        <SourceBadge source={source} isLoading={isLoading} />
      </div>

      {/* Topic filter pills */}
      <div style={{ display: "flex", gap: 5, flexWrap: "wrap" }}>
        {["all", ...topics].map((t) => {
          const active = selectedTopic === t;
          return (
            <button key={t} onClick={() => setSelectedTopic(t)} style={{
              fontFamily: fonts.mono, fontSize: 10, padding: "3px 9px", borderRadius: 5,
              border: active ? `1px solid ${accentBorder(ACCENT)}` : `1px solid ${colors.border2}`,
              background: active ? accentSoft(ACCENT) : "transparent",
              color: active ? ACCENT : palette.dim, cursor: "pointer", letterSpacing: "0.05em",
            }}>
              {t === "all" ? "All Topics" : t}
            </button>
          );
        })}
      </div>

      {/* Legend */}
      <div style={{ display: "flex", gap: 14 }}>
        {(["supportive", "critical", "neutral", "ambiguous"] as const).map((k) => (
          <div key={k} style={{ display: "flex", alignItems: "center", gap: 5 }}>
            <div style={{ width: 8, height: 8, borderRadius: 2, background: STANCE_COLORS[k] }} />
            <span style={{ fontFamily: fonts.mono, fontSize: 10, color: palette.dim, textTransform: "uppercase", letterSpacing: "0.07em" }}>{k}</span>
          </div>
        ))}
      </div>

      {/* Source cards */}
      {sorted.length === 0 ? (
        <div style={{ padding: 28, textAlign: "center", color: palette.dim, fontFamily: fonts.mono, fontSize: 12 }}>
          No stance data available. Run stance aggregation to populate.
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {sorted.map(([src, { source_type, sup, crit, neu, amb, total }]) => {
            const color = ST_COLORS_SHARED[source_type] ?? palette.dim;
            const isExpanded = expandedSource === src;
            const row: SourceStance = {
              source: src, source_type: source_type as SourceType,
              topic: selectedTopic === "all" ? "all" : selectedTopic,
              supportive: sup, critical: crit, neutral: neu, ambiguous: amb,
              total, confidence: null, document_count: total,
              window_start: null, window_end: null,
            };
            return (
              <div key={src} style={{ ...card, padding: "10px 14px" }}>
                <div
                  style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8, cursor: "pointer" }}
                  onClick={() => setExpandedSource(isExpanded ? null : src)}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <div style={{ width: 6, height: 6, borderRadius: "50%", background: color, flexShrink: 0 }} />
                    <span style={{ fontFamily: fonts.mono, fontSize: 12, color: colors.text }}>{src}</span>
                    <span style={{
                      fontFamily: fonts.mono, fontSize: 9, letterSpacing: "0.08em",
                      color, background: `${color}18`, border: `1px solid ${color}40`,
                      borderRadius: 4, padding: "1px 5px", flexShrink: 0, textTransform: "uppercase",
                    }}>{source_type}</span>
                  </div>
                  <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                    <span style={{ fontFamily: fonts.mono, fontSize: 10, color: palette.dim }}>{total} docs</span>
                    <span style={{ fontFamily: fonts.mono, fontSize: 10, color: palette.dim }}>{isExpanded ? "▲" : "▼"}</span>
                  </div>
                </div>
                <StanceBar s={row} />
                {isExpanded && <DriftTimeline source={src} sourceType={sourceType} />}
              </div>
            );
          })}
        </div>
      )}
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
        subtitle="Claims · stance · sources · drift · frames · positions · controversy — across all content types"
        right={
          <FilterPills value={sourceType} onChange={setSourceType} />
        }
      />

      <TabBar active={tab} onChange={setTab} />

      {tab === "claims"      && <ClaimsPanel      sourceType={sourceType} />}
      {tab === "stance"      && <StancePanel       sourceType={sourceType} />}
      {tab === "sources"     && <SourcesPanel      sourceType={sourceType} />}
      {tab === "frames"      && <FramesPanel       sourceType={sourceType} />}
      {tab === "positions"   && <PositionsPanel    sourceType={sourceType} />}
      {tab === "controversy" && <ControversyPanel  sourceType={sourceType} />}
    </div>
  );
}
