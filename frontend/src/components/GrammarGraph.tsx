"use client";

// Hand-rolled force-directed graph, canvas-rendered, zero new dependencies —
// ARCHITECTURE.md "V2 Slice" §V2.4 / ADR-13. Layout is a Fruchterman-Reingold-style
// repulsion/spring relaxation computed ONCE in a useEffect (not a live per-frame physics
// sim — 205 nodes settle into a static layout you then pan/zoom). Draw loop reads from refs
// so hover/pan/zoom don't need React re-renders per frame.

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import type { GrammarRelationEdge, GrammarRelationType, GrammarWithProgressOut } from "@/lib/types";
import { RELATION_ORDER, RELATION_TYPE_COLORS, RELATION_TYPE_LABELS } from "@/lib/grammar";

interface GrammarGraphProps {
  items: GrammarWithProgressOut[];
  edges: GrammarRelationEdge[];
}

interface LayoutNode {
  id: string;
  label: string;
  x: number;
  y: number;
  degree: number;
}

interface LayoutEdge {
  a: string;
  b: string;
  type: GrammarRelationType;
  directional: boolean;
}

const CANVAS_W = 960;
const CANVAS_H = 640;
const ITERATIONS = 260;
const HUB_LABEL_MIN_DEGREE = 6;
// Isolated (degree-0) nodes have no spring force pulling them back toward the graph — only
// mutual repulsion, which the boundary clamp below turns into a pile-up flush against the
// canvas edges (a "picture frame" of dots). Curated relations (V4) intentionally don't cover
// every item, so a large chunk of nodes are genuinely isolated now — give them their own grid
// strip instead of feeding them into the physics sim at all.
const ISOLATED_STRIP_HEIGHT = 90;

function computeLayout(
  nodeIds: string[],
  edges: LayoutEdge[],
  bounds: { w: number; h: number } = { w: CANVAS_W, h: CANVAS_H },
): Map<string, { x: number; y: number }> {
  const { w: CANVAS_W, h: CANVAS_H } = bounds;
  const n = nodeIds.length || 1;
  const area = CANVAS_W * CANVAS_H;
  const k = Math.sqrt(area / n);

  const pos = new Map<string, { x: number; y: number; dx: number; dy: number }>();
  nodeIds.forEach((id, i) => {
    const angle = (i / n) * Math.PI * 2;
    const radius = Math.min(CANVAS_W, CANVAS_H) * 0.35 * Math.sqrt(Math.random());
    pos.set(id, {
      x: CANVAS_W / 2 + Math.cos(angle) * radius,
      y: CANVAS_H / 2 + Math.sin(angle) * radius,
      dx: 0,
      dy: 0,
    });
  });

  let temperature = CANVAS_W / 10;
  const cooling = temperature / ITERATIONS;

  for (let iter = 0; iter < ITERATIONS; iter++) {
    for (const p of pos.values()) {
      p.dx = 0;
      p.dy = 0;
    }
    for (let i = 0; i < nodeIds.length; i++) {
      const idA = nodeIds[i];
      if (idA === undefined) continue;
      const a = pos.get(idA)!;
      for (let j = i + 1; j < nodeIds.length; j++) {
        const idB = nodeIds[j];
        if (idB === undefined) continue;
        const b = pos.get(idB)!;
        let dx = a.x - b.x;
        let dy = a.y - b.y;
        const dist = Math.sqrt(dx * dx + dy * dy) || 0.01;
        const force = (k * k) / dist;
        dx = (dx / dist) * force;
        dy = (dy / dist) * force;
        a.dx += dx;
        a.dy += dy;
        b.dx -= dx;
        b.dy -= dy;
      }
    }
    for (const e of edges) {
      const a = pos.get(e.a);
      const b = pos.get(e.b);
      if (!a || !b) continue;
      let dx = a.x - b.x;
      let dy = a.y - b.y;
      const dist = Math.sqrt(dx * dx + dy * dy) || 0.01;
      const force = (dist * dist) / k;
      dx = (dx / dist) * force;
      dy = (dy / dist) * force;
      a.dx -= dx;
      a.dy -= dy;
      b.dx += dx;
      b.dy += dy;
    }
    // Pure repulsion + springs (classic Fruchterman-Reingold) has no notion of "center" — a
    // weakly-connected pair (degree 1 each) feels only its own small spring but full global
    // repulsion from all 400+ other nodes, so it drifts outward with nothing to stop it until
    // the boundary clamp below snaps it flush against the edge (the "picture frame" bug). A
    // small constant pull toward the canvas center (d3-force's forceCenter equivalent) fixes
    // this without meaningfully distorting well-connected clusters, where spring forces dominate.
    const cx = CANVAS_W / 2;
    const cy = CANVAS_H / 2;
    // Coefficient scaled by node count: with O(n) other nodes each contributing k²/dist of
    // outward push, a fixed-strength centering pull gets drowned out as n grows. Scaling it by
    // n keeps the pull competitive with the summed repulsion regardless of graph size.
    const centerPull = 0.006 * n;
    for (const p of pos.values()) {
      p.dx += (cx - p.x) * centerPull;
      p.dy += (cy - p.y) * centerPull;
    }
    for (const p of pos.values()) {
      const dist = Math.sqrt(p.dx * p.dx + p.dy * p.dy) || 0.01;
      const limited = Math.min(dist, temperature);
      p.x += (p.dx / dist) * limited;
      p.y += (p.dy / dist) * limited;
      p.x = Math.min(CANVAS_W - 20, Math.max(20, p.x));
      p.y = Math.min(CANVAS_H - 20, Math.max(20, p.y));
    }
    temperature = Math.max(temperature - cooling, 0.5);
  }

  const result = new Map<string, { x: number; y: number }>();
  for (const [id, p] of pos) result.set(id, { x: p.x, y: p.y });
  return result;
}

export default function GrammarGraph({ items, edges }: GrammarGraphProps) {
  const router = useRouter();
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [ready, setReady] = useState(false);
  // "related" starts hidden: with no LLM key configured, these edges are heuristic-fallback
  // noise (weak particle/keyword overlap, see ARCHITECTURE.md ADR-12) and dominate the layout
  // to the point of unreadability if shown by default. The legend toggle still lets it back in.
  const [hiddenTypes, setHiddenTypes] = useState<Set<GrammarRelationType>>(new Set(["related"]));
  const [hoveredId, setHoveredId] = useState<string | null>(null);

  const nodesRef = useRef<LayoutNode[]>([]);
  const edgesRef = useRef<LayoutEdge[]>([]);
  const viewRef = useRef({ scale: 1, offsetX: 0, offsetY: 0 });
  const dragRef = useRef<{ dragging: boolean; lastX: number; lastY: number; moved: boolean }>({
    dragging: false,
    lastX: 0,
    lastY: 0,
    moved: false,
  });
  const hoveredRef = useRef<string | null>(null);
  const hiddenRef = useRef<Set<GrammarRelationType>>(new Set());

  useEffect(() => {
    hiddenRef.current = hiddenTypes;
  }, [hiddenTypes]);
  useEffect(() => {
    hoveredRef.current = hoveredId;
  }, [hoveredId]);

  // Build layout once from items/edges (identity-stable per page load — the graph page
  // fetches both once on mount and doesn't refetch).
  useEffect(() => {
    const layoutEdges: LayoutEdge[] = edges
      .filter((e) => items.some((i) => i.id === e.grammar_id) && items.some((i) => i.id === e.related_grammar_id))
      .map((e) => ({
        a: e.grammar_id,
        b: e.related_grammar_id,
        type: e.relation_type,
        directional: e.relation_type === "prerequisite" || e.relation_type === "advanced_version",
      }));

    const degree = new Map<string, number>();
    for (const e of layoutEdges) {
      degree.set(e.a, (degree.get(e.a) ?? 0) + 1);
      degree.set(e.b, (degree.get(e.b) ?? 0) + 1);
    }

    const connectedIds = items.filter((i) => (degree.get(i.id) ?? 0) > 0).map((i) => i.id);
    const isolatedIds = items.filter((i) => (degree.get(i.id) ?? 0) === 0).map((i) => i.id);

    // Connected nodes get the physics sim, confined to the area above the isolated strip.
    const graphAreaH = CANVAS_H - ISOLATED_STRIP_HEIGHT;
    const positions = computeLayout(connectedIds, layoutEdges, { w: CANVAS_W, h: graphAreaH });

    // Isolated nodes (no curated relation yet) get a plain grid in a reserved strip along the
    // bottom instead — no physics, no pile-up, just a tidy "browse the rest" row.
    const isolatedPositions = new Map<string, { x: number; y: number }>();
    const cols = Math.max(1, Math.floor(CANVAS_W / 14));
    isolatedIds.forEach((id, i) => {
      const col = i % cols;
      const row = Math.floor(i / cols);
      isolatedPositions.set(id, {
        x: 12 + col * 14,
        y: graphAreaH + 16 + row * 12,
      });
    });

    nodesRef.current = items.map((item) => {
      const p =
        positions.get(item.id) ?? isolatedPositions.get(item.id) ?? { x: CANVAS_W / 2, y: CANVAS_H / 2 };
      return {
        id: item.id,
        label: item.expression_clean,
        x: p.x,
        y: p.y,
        degree: degree.get(item.id) ?? 0,
      };
    });
    edgesRef.current = layoutEdges;
    setReady(true);
  }, [items, edges]);

  const draw = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const styles = getComputedStyle(document.documentElement);
    const bg = styles.getPropertyValue("--surface").trim() || "#fffdf7";
    const inkMuted = styles.getPropertyValue("--ink-muted").trim() || "#746a56";
    const ink = styles.getPropertyValue("--ink").trim() || "#221d14";
    const accent = styles.getPropertyValue("--accent").trim() || "#a8391c";
    const border = styles.getPropertyValue("--border-strong").trim() || "#c7b78f";

    const { scale, offsetX, offsetY } = viewRef.current;
    const dpr = window.devicePixelRatio || 1;
    canvas.width = CANVAS_W * dpr;
    canvas.height = CANVAS_H * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.fillStyle = bg;
    ctx.fillRect(0, 0, CANVAS_W, CANVAS_H);

    ctx.save();
    ctx.translate(offsetX, offsetY);
    ctx.scale(scale, scale);

    const stripY = CANVAS_H - ISOLATED_STRIP_HEIGHT;
    ctx.beginPath();
    ctx.moveTo(0, stripY);
    ctx.lineTo(CANVAS_W, stripY);
    ctx.strokeStyle = border;
    ctx.globalAlpha = 0.5;
    ctx.lineWidth = 1 / scale;
    ctx.stroke();
    ctx.globalAlpha = 1;
    ctx.font = `${11 / scale}px var(--font-sans), sans-serif`;
    ctx.fillStyle = inkMuted;
    ctx.fillText("Пока без связей", 8, stripY + 12 / scale);

    const nodesById = new Map(nodesRef.current.map((n) => [n.id, n]));
    const hidden = hiddenRef.current;
    const hovered = hoveredRef.current;
    const hoveredEdgeSet = new Set<string>();
    if (hovered) {
      for (const e of edgesRef.current) {
        if (e.a === hovered || e.b === hovered) hoveredEdgeSet.add(`${e.a}|${e.b}|${e.type}`);
      }
    }

    // edges
    for (const e of edgesRef.current) {
      if (hidden.has(e.type)) continue;
      const a = nodesById.get(e.a);
      const b = nodesById.get(e.b);
      if (!a || !b) continue;
      const key = `${e.a}|${e.b}|${e.type}`;
      const isDimmed = hovered !== null && !hoveredEdgeSet.has(key);
      ctx.beginPath();
      ctx.moveTo(a.x, a.y);
      ctx.lineTo(b.x, b.y);
      ctx.strokeStyle = RELATION_TYPE_COLORS[e.type];
      ctx.globalAlpha = isDimmed ? 0.08 : 0.55;
      ctx.lineWidth = 1.2 / scale;
      ctx.stroke();

      if (e.directional && !isDimmed) {
        const angle = Math.atan2(b.y - a.y, b.x - a.x);
        const arrowLen = 7 / scale;
        const tipX = b.x - Math.cos(angle) * 9;
        const tipY = b.y - Math.sin(angle) * 9;
        ctx.beginPath();
        ctx.moveTo(tipX, tipY);
        ctx.lineTo(
          tipX - arrowLen * Math.cos(angle - Math.PI / 7),
          tipY - arrowLen * Math.sin(angle - Math.PI / 7),
        );
        ctx.lineTo(
          tipX - arrowLen * Math.cos(angle + Math.PI / 7),
          tipY - arrowLen * Math.sin(angle + Math.PI / 7),
        );
        ctx.closePath();
        ctx.fillStyle = RELATION_TYPE_COLORS[e.type];
        ctx.globalAlpha = 0.8;
        ctx.fill();
      }
      ctx.globalAlpha = 1;
    }

    // nodes
    for (const n of nodesRef.current) {
      const isHovered = n.id === hovered;
      const isNeighbor = hoveredEdgeSet.size > 0 && edgesRef.current.some(
        (e) => (e.a === hovered && e.b === n.id) || (e.b === hovered && e.a === n.id),
      );
      const dimmed = hovered !== null && !isHovered && !isNeighbor;

      const radius = (isHovered ? 6 : 3.5 + Math.min(n.degree, 8) * 0.35) / Math.sqrt(scale);
      ctx.beginPath();
      ctx.arc(n.x, n.y, radius, 0, Math.PI * 2);
      ctx.fillStyle = isHovered ? accent : ink;
      ctx.globalAlpha = dimmed ? 0.2 : 0.9;
      ctx.fill();
      ctx.lineWidth = 1 / scale;
      ctx.strokeStyle = border;
      ctx.stroke();
      ctx.globalAlpha = 1;

      const showLabel = isHovered || (!hovered && n.degree >= HUB_LABEL_MIN_DEGREE);
      if (showLabel) {
        ctx.font = `${12 / scale}px var(--font-sans), sans-serif`;
        ctx.fillStyle = isHovered ? accent : inkMuted;
        ctx.globalAlpha = dimmed ? 0.2 : 1;
        ctx.fillText(n.label, n.x + radius + 4 / scale, n.y + 4 / scale);
        ctx.globalAlpha = 1;
      }
    }

    ctx.restore();
  }, []);

  // continuous draw loop — cheap at this node/edge count, keeps hover/pan/zoom responsive
  // without threading extra invalidation logic through refs.
  useEffect(() => {
    if (!ready) return;
    let raf = 0;
    const loop = () => {
      draw();
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, [ready, draw]);

  const toCanvasCoords = (clientX: number, clientY: number): { x: number; y: number } | null => {
    const canvas = canvasRef.current;
    if (!canvas) return null;
    const rect = canvas.getBoundingClientRect();
    const cx = ((clientX - rect.left) / rect.width) * CANVAS_W;
    const cy = ((clientY - rect.top) / rect.height) * CANVAS_H;
    const { scale, offsetX, offsetY } = viewRef.current;
    return { x: (cx - offsetX) / scale, y: (cy - offsetY) / scale };
  };

  const hitTest = (x: number, y: number): string | null => {
    let best: string | null = null;
    let bestDist = 14 / viewRef.current.scale;
    for (const n of nodesRef.current) {
      const d = Math.hypot(n.x - x, n.y - y);
      if (d < bestDist) {
        bestDist = d;
        best = n.id;
      }
    }
    return best;
  };

  const handleMouseDown = (e: React.MouseEvent<HTMLCanvasElement>) => {
    dragRef.current = { dragging: true, lastX: e.clientX, lastY: e.clientY, moved: false };
  };

  const handleMouseMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (dragRef.current.dragging) {
      const dx = e.clientX - dragRef.current.lastX;
      const dy = e.clientY - dragRef.current.lastY;
      if (Math.abs(dx) > 2 || Math.abs(dy) > 2) dragRef.current.moved = true;
      viewRef.current.offsetX += dx;
      viewRef.current.offsetY += dy;
      dragRef.current.lastX = e.clientX;
      dragRef.current.lastY = e.clientY;
      return;
    }
    const coords = toCanvasCoords(e.clientX, e.clientY);
    if (!coords) return;
    const hit = hitTest(coords.x, coords.y);
    setHoveredId(hit);
  };

  const handleMouseUp = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const wasDrag = dragRef.current.moved;
    dragRef.current.dragging = false;
    if (!wasDrag) {
      const coords = toCanvasCoords(e.clientX, e.clientY);
      if (coords) {
        const hit = hitTest(coords.x, coords.y);
        if (hit) router.push(`/grammar/${hit}`);
      }
    }
  };

  const handleWheel = (e: React.WheelEvent<HTMLCanvasElement>) => {
    e.preventDefault();
    const canvas = canvasRef.current;
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const mx = ((e.clientX - rect.left) / rect.width) * CANVAS_W;
    const my = ((e.clientY - rect.top) / rect.height) * CANVAS_H;
    const { scale, offsetX, offsetY } = viewRef.current;
    const factor = e.deltaY < 0 ? 1.1 : 0.9;
    const newScale = Math.min(4, Math.max(0.3, scale * factor));
    // zoom centered on cursor
    viewRef.current.offsetX = mx - ((mx - offsetX) / scale) * newScale;
    viewRef.current.offsetY = my - ((my - offsetY) / scale) * newScale;
    viewRef.current.scale = newScale;
  };

  const toggleType = (type: GrammarRelationType) => {
    setHiddenTypes((prev) => {
      const next = new Set(prev);
      if (next.has(type)) next.delete(type);
      else next.add(type);
      return next;
    });
  };

  const hoveredNode = hoveredId ? nodesRef.current.find((n) => n.id === hoveredId) : null;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap gap-2" role="group" aria-label="Легенда связей">
        {RELATION_ORDER.map((type) => {
          const active = !hiddenTypes.has(type);
          return (
            <button
              key={type}
              type="button"
              onClick={() => toggleType(type)}
              aria-pressed={active}
              className="transition-standard flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium"
              style={{
                borderColor: active ? RELATION_TYPE_COLORS[type] : "var(--border)",
                color: active ? "var(--ink)" : "var(--ink-faint)",
                opacity: active ? 1 : 0.55,
              }}
            >
              <span
                aria-hidden
                className="inline-block h-2 w-2 rounded-full"
                style={{ background: RELATION_TYPE_COLORS[type] }}
              />
              {RELATION_TYPE_LABELS[type]}
            </button>
          );
        })}
      </div>

      <div className="relative overflow-hidden rounded-xl border border-[var(--border)] bg-[var(--surface)]">
        <canvas
          ref={canvasRef}
          style={{ width: "100%", height: `${(CANVAS_H / CANVAS_W) * 100}vw`, maxHeight: 640, display: "block", cursor: hoveredId ? "pointer" : "grab" }}
          onMouseDown={handleMouseDown}
          onMouseMove={handleMouseMove}
          onMouseUp={handleMouseUp}
          onMouseLeave={() => {
            dragRef.current.dragging = false;
            setHoveredId(null);
          }}
          onWheel={handleWheel}
        />
        {hoveredNode && (
          <div className="pointer-events-none absolute left-3 top-3 rounded-lg border border-[var(--border)] bg-[var(--surface-raised)] px-3 py-2 text-xs shadow-sm">
            <p className="jp-text font-medium text-[var(--ink)]">{hoveredNode.label}</p>
            <p className="text-[var(--ink-faint)]">{hoveredNode.degree} связ{hoveredNode.degree === 1 ? "ь" : "и"}</p>
          </div>
        )}
      </div>
      <p className="text-xs text-[var(--ink-faint)]">
        Перетаскивание — панорама, колесо — масштаб, клик по узлу — открыть конструкцию.
      </p>
    </div>
  );
}
