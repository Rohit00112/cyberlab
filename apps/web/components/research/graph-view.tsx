"use client";

import { useMemo, useRef, useState, type PointerEvent } from "react";

import type { GraphEdge, GraphNode, GraphNodeType, ResearchGraph } from "@/lib/research/types";

const VIEW_W = 920;
const VIEW_H = 560;

const NODE_STYLE: Record<GraphNodeType, { r: number; fill: string }> = {
  skill: { r: 9, fill: "#3b82f6" },
  challenge: { r: 6, fill: "#10b981" },
  category: { r: 12, fill: "#f59e0b" },
};

const RELATION_LABEL: Record<string, string> = {
  requires: "requires",
  in: "in category",
  co_solved: "co-solved",
  step: "path step",
};

function computeLayout(nodes: GraphNode[], edges: GraphEdge[]) {
  const count = nodes.length;
  const positions = new Array<{ x: number; y: number }>(count);
  for (let i = 0; i < count; i += 1) {
    positions[i] = {
      x: VIEW_W / 2 + (Math.random() - 0.5) * VIEW_W * 0.6,
      y: VIEW_H / 2 + (Math.random() - 0.5) * VIEW_H * 0.6,
    };
  }

  const index = new Map<string, number>();
  nodes.forEach((node, i) => index.set(node.id, i));

  const springs = edges
    .map((edge) => {
      const s = index.get(edge.source);
      const t = index.get(edge.target);
      return s !== undefined && t !== undefined ? { s, t } : null;
    })
    .filter((pair): pair is { s: number; t: number } => pair !== null);

  const dt = 0.08;
  for (let iter = 0; iter < 240; iter += 1) {
    for (let i = 0; i < count; i += 1) {
      for (let j = i + 1; j < count; j += 1) {
        const dx = positions[j].x - positions[i].x;
        const dy = positions[j].y - positions[i].y;
        const dist = Math.max(Math.hypot(dx, dy), 18);
        const force = (2400 / (dist * dist)) * dt;
        const fx = (dx / dist) * force;
        const fy = (dy / dist) * force;
        positions[i].x -= fx;
        positions[i].y -= fy;
        positions[j].x += fx;
        positions[j].y += fy;
      }
    }
    for (const { s, t } of springs) {
      const dx = positions[t].x - positions[s].x;
      const dy = positions[t].y - positions[s].y;
      const dist = Math.max(Math.hypot(dx, dy), 1);
      const target = 70;
      const force = (dist - target) * 0.02;
      positions[s].x += (dx / dist) * force;
      positions[s].y += (dy / dist) * force;
      positions[t].x -= (dx / dist) * force;
      positions[t].y -= (dy / dist) * force;
    }
    const cx = VIEW_W / 2;
    const cy = VIEW_H / 2;
    for (let i = 0; i < count; i += 1) {
      positions[i].x += (cx - positions[i].x) * 0.005;
      positions[i].y += (cy - positions[i].y) * 0.005;
      positions[i].x = Math.min(VIEW_W - 20, Math.max(20, positions[i].x));
      positions[i].y = Math.min(VIEW_H - 20, Math.max(20, positions[i].y));
    }
  }
  return positions;
}

export function GraphView({ graph }: { graph: ResearchGraph }) {
  const nodes = useMemo(() => graph.nodes, [graph]);
  const edges = useMemo(() => graph.edges, [graph]);

  const [positions, setPositions] = useState<{ x: number; y: number }[]>(() =>
    computeLayout(nodes, edges),
  );
  const [hovered, setHovered] = useState<string | null>(null);
  const [selected, setSelected] = useState<GraphNode | null>(null);
  const [dragging, setDragging] = useState<number | null>(null);
  const dragRef = useRef<{ dx: number; dy: number } | null>(null);

  const index = useMemo(() => new Map(nodes.map((n, i) => [n.id, i])), [nodes]);
  const neighbors = useMemo(() => {
    const adjacent = new Set<string>();
    if (!hovered && !selected) return adjacent;
    const focus = hovered ?? selected?.id ?? null;
    if (!focus) return adjacent;
    for (const edge of edges) {
      if (edge.source === focus) adjacent.add(edge.target);
      if (edge.target === focus) adjacent.add(edge.source);
    }
    adjacent.add(focus);
    return adjacent;
  }, [edges, hovered, selected]);

  const counts = useMemo(() => {
    const byType: Record<GraphNodeType, number> = { skill: 0, challenge: 0, category: 0 };
    for (const node of nodes) byType[node.type] += 1;
    return byType;
  }, [nodes]);

  const relationCounts = useMemo(() => {
    const byRelation: Record<string, number> = {};
    for (const edge of edges) {
      byRelation[edge.relation] = (byRelation[edge.relation] ?? 0) + 1;
    }
    return byRelation;
  }, [edges]);

  const maxWeight = useMemo(
    () => Math.max(1, ...edges.map((edge) => edge.weight)),
    [edges],
  );

  function onPointerDown(nodeIndex: number, event: PointerEvent<SVGGraphicsElement>) {
    const svg = event.currentTarget.ownerSVGElement;
    if (!svg) return;
    const point = svg.createSVGPoint();
    point.x = event.clientX;
    point.y = event.clientY;
    const ctm = svg.getScreenCTM();
    if (!ctm) return;
    const { x, y } = point.matrixTransform(ctm.inverse());
    dragRef.current = {
      dx: x - positions[nodeIndex].x,
      dy: y - positions[nodeIndex].y,
    };
    event.currentTarget.setPointerCapture(event.pointerId);
    setDragging(nodeIndex);
  }

  function onPointerMove(nodeIndex: number, event: PointerEvent<SVGGraphicsElement>) {
    if (dragging !== nodeIndex || !dragRef.current) return;
    const svg = event.currentTarget.ownerSVGElement;
    if (!svg) return;
    const point = svg.createSVGPoint();
    point.x = event.clientX;
    point.y = event.clientY;
    const ctm = svg.getScreenCTM();
    if (!ctm) return;
    const { x, y } = point.matrixTransform(ctm.inverse());
    setPositions((previous) => {
      const next = [...previous];
      next[nodeIndex] = {
        x: Math.min(VIEW_W - 16, Math.max(16, x - dragRef.current!.dx)),
        y: Math.min(VIEW_H - 16, Math.max(16, y - dragRef.current!.dy)),
      };
      return next;
    });
  }

  function onPointerUp(nodeIndex: number, event: PointerEvent<SVGGraphicsElement>) {
    if (dragging === nodeIndex) {
      event.currentTarget.releasePointerCapture(event.pointerId);
      setDragging(null);
      dragRef.current = null;
    }
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_260px]">
      <div>
        <svg
          viewBox={`0 0 ${VIEW_W} ${VIEW_H}`}
          className="w-full rounded-lg border bg-muted/30"
          role="img"
          aria-label="Knowledge graph of skills, challenges and categories"
        >
          <g>
            {edges.map((edge, i) => {
              const s = index.get(edge.source);
              const t = index.get(edge.target);
              if (s === undefined || t === undefined || positions[s] === undefined || positions[t] === undefined) {
                return null;
              }
              const focused =
                neighbors.size === 0 ||
                neighbors.has(edge.source) ||
                neighbors.has(edge.target);
              const opacity = focused
                ? 0.35 + 0.65 * (edge.weight / maxWeight)
                : 0.06;
              return (
                <line
                  key={`${edge.source}-${edge.target}-${i}`}
                  x1={positions[s].x}
                  y1={positions[s].y}
                  x2={positions[t].x}
                  y2={positions[t].y}
                  stroke="#64748b"
                  strokeWidth={Math.max(0.5, Math.min(3, 1 + edge.weight / maxWeight))}
                  strokeOpacity={opacity}
                />
              );
            })}
          </g>
          <g>
            {nodes.map((node, i) => {
              const pos = positions[i];
              if (!pos) return null;
              const focused = neighbors.size === 0 || neighbors.has(node.id);
              const style = NODE_STYLE[node.type];
              const isSelected = selected?.id === node.id;
              return (
                <g
                  key={node.id}
                  transform={`translate(${pos.x} ${pos.y})`}
                  opacity={focused ? 1 : 0.18}
                  onPointerDown={(event) => onPointerDown(i, event)}
                  onPointerMove={(event) => onPointerMove(i, event)}
                  onPointerUp={(event) => onPointerUp(i, event)}
                  onPointerEnter={() => setHovered(node.id)}
                  onPointerLeave={() => setHovered(null)}
                  onPointerCancel={() => {
                    setDragging(null);
                    dragRef.current = null;
                  }}
                  onClick={() => setSelected(node)}
                  style={{ cursor: "pointer" }}
                >
                  <circle
                    r={style.r + (isSelected ? 3 : 0)}
                    fill={style.fill}
                    stroke={isSelected ? "#020617" : "none"}
                    strokeWidth={isSelected ? 2 : 0}
                  />
                  {node.type === "category" ? (
                    <text textAnchor="middle" dy={-16} className="text-[11px] fill-slate-600">
                      {node.label}
                    </text>
                  ) : null}
                  <title>{`${node.label} (${node.type})`}</title>
                </g>
              );
            })}
          </g>
        </svg>

        <div className="mt-3 flex flex-wrap items-center gap-4 text-xs text-muted-foreground">
          {(["skill", "challenge", "category"] as GraphNodeType[]).map((type) => (
            <span key={type} className="inline-flex items-center gap-1.5">
              <span
                className="inline-block h-2.5 w-2.5 rounded-full"
                style={{ backgroundColor: NODE_STYLE[type].fill }}
              />
              {type}
            </span>
          ))}
          <span className="ml-auto">Drag nodes to explore</span>
        </div>
      </div>

      <aside className="space-y-4">
        <div className="rounded-lg border p-4">
          <h3 className="text-sm font-semibold">Nodes</h3>
          <dl className="mt-2 space-y-1 text-sm">
            <div className="flex justify-between">
              <dt className="text-muted-foreground">Skills</dt>
              <dd className="tabular-nums">{counts.skill}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-muted-foreground">Challenges</dt>
              <dd className="tabular-nums">{counts.challenge}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-muted-foreground">Categories</dt>
              <dd className="tabular-nums">{counts.category}</dd>
            </div>
          </dl>
          <h3 className="mt-4 text-sm font-semibold">Edges</h3>
          <dl className="mt-2 space-y-1 text-sm">
            {Object.entries(relationCounts).map(([relation, count]) => (
              <div key={relation} className="flex justify-between">
                <dt className="text-muted-foreground">{RELATION_LABEL[relation] ?? relation}</dt>
                <dd className="tabular-nums">{count}</dd>
              </div>
            ))}
          </dl>
        </div>

        <div className="rounded-lg border p-4">
          <h3 className="text-sm font-semibold">Selection</h3>
          {selected ? (
            <dl className="mt-2 space-y-1 text-sm">
              <div>
                <dt className="text-muted-foreground">Label</dt>
                <dd className="font-medium">{selected.label}</dd>
              </div>
              <div>
                <dt className="text-muted-foreground">Type</dt>
                <dd>{selected.type}</dd>
              </div>
              {Object.entries(selected.meta).map(([key, value]) => (
                <div key={key}>
                  <dt className="text-muted-foreground">{key.replaceAll("_", " ")}</dt>
                  <dd>{String(value)}</dd>
                </div>
              ))}
            </dl>
          ) : (
            <p className="mt-1 text-sm text-muted-foreground">
              Click a node to inspect it.
            </p>
          )}
        </div>
      </aside>
    </div>
  );
}