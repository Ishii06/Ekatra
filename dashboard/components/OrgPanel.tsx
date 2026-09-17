"use client";

import { useMemo } from "react";
import { motion } from "framer-motion";
import { Network } from "lucide-react";
import type { Agent, RoleKey } from "@/lib/types";
import { useDashboard } from "@/lib/dashboard-context";
import { cn } from "@/lib/cn";
import { Panel } from "./ui";
import { RoleGroup } from "./AgentCard";

const ANCHORS: Record<RoleKey, { x: number; y: number }> = {
  project_manager: { x: 50, y: 10 },
  architect: { x: 50, y: 28 },
  frontend: { x: 27, y: 50 },
  backend: { x: 73, y: 50 },
  qa: { x: 27, y: 78 },
  security: { x: 73, y: 78 },
};

const CONTAINER_H = 640;

function halfHeightPct(count: number): number {
  const clamped = Math.max(1, Math.min(3, count));
  return (30 + clamped * 64) / 2 / CONTAINER_H * 100;
}

interface Edge {
  from: RoleKey;
  to: RoleKey;
  exitX?: number;
  enterX?: number;
}

const EDGES: Edge[] = [
  { from: "project_manager", to: "architect" },
  { from: "architect", to: "frontend", exitX: 45, enterX: 27 },
  { from: "architect", to: "backend", exitX: 55, enterX: 73 },
  { from: "frontend", to: "qa" },
  { from: "backend", to: "security" },
];

function byRole(agents: Agent[]): Record<RoleKey, Agent[]> {
  const map: Record<RoleKey, Agent[]> = {
    project_manager: [],
    architect: [],
    frontend: [],
    backend: [],
    qa: [],
    security: [],
  };
  for (const a of agents) map[a.role].push(a);
  return map;
}

function EdgePath({
  edge,
  counts,
  active,
}: {
  edge: Edge;
  counts: Record<RoleKey, number>;
  active: boolean;
}) {
  const a = ANCHORS[edge.from];
  const b = ANCHORS[edge.to];
  const fromCount = counts[edge.from] || 1;
  const toCount = counts[edge.to] || 1;
  const y1 = a.y + halfHeightPct(fromCount);
  const y2 = b.y - halfHeightPct(toCount);
  const x1 = edge.exitX ?? a.x;
  const x2 = edge.enterX ?? b.x;

  const path =
    x1 === x2
      ? `M ${x1} ${y1} L ${x2} ${y2}`
      : `M ${x1} ${y1} C ${x1} ${(y1 + y2) / 2} ${x2} ${(y1 + y2) / 2} ${x2} ${y2}`;

  return (
    <g>
      <path
        d={path}
        fill="none"
        vectorEffect="non-scaling-stroke"
        strokeWidth={1.2}
        strokeLinecap="round"
        className={active ? "flow-line" : "flow-line-slow"}
        stroke={active ? "#38bdf8" : "rgba(148,163,184,0.16)"}
      />
      <circle cx={x2} cy={y2} r={0.7} fill={active ? "#7dd3fc" : "rgba(148,163,184,0.3)"} />
    </g>
  );
}

function Legend() {
  const items: { label: string; className: string }[] = [
    { label: "Active", className: "bg-cyan-glow" },
    { label: "Idle", className: "bg-fg-dim" },
    { label: "Completed", className: "bg-mint" },
    { label: "Spawned instance", className: "border border-accent bg-accent/20" },
    { label: "Baseline instance", className: "border border-line-soft bg-white/[0.05]" },
  ];
  return (
    <div className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-2 border-t border-line-soft pt-3">
      {items.map((it) => (
        <span key={it.label} className="flex items-center gap-1.5">
          <span className={cn("h-2 w-2 rounded-sm", it.className)} />
          <span className="mono text-[9px] uppercase tracking-[0.14em] text-fg-dim">
            {it.label}
          </span>
        </span>
      ))}
    </div>
  );
}

export function OrgPanel() {
  const { frame, selectAgent, selectedAgentId } = useDashboard();
  const justSpawnedId = frame?.justSpawned ?? null;

  const groups = useMemo(() => byRole(frame?.agents ?? []), [frame]);
  const counts = useMemo(() => {
    const c = {} as Record<RoleKey, number>;
    (Object.keys(groups) as RoleKey[]).forEach((r) => (c[r] = groups[r].length));
    return c;
  }, [groups]);

  const activeRole = (role: RoleKey) =>
    groups[role].some((a) => a.status === "ACTIVE");

  const activeCount = (frame?.agents ?? []).filter((a) => a.status === "ACTIVE").length;
  const total = frame?.agents.length ?? 0;

  return (
    <Panel
      eyebrow="Organization"
      title="Agent Organization"
      icon={<Network className="h-4 w-4" />}
      subtitle="Virtual software engineering organization. Roles may hold multiple runtime instances; the Adaptive Controller changes this composition at runtime."
      actions={
        <div className="mono text-right text-[10px] uppercase tracking-[0.16em] text-fg-dim">
          <div className="text-fg-muted">
            <span className="text-cyan-glow">{activeCount}</span> / {total} active
          </div>
          <div>{frame?.projectState ?? "—"}</div>
        </div>
      }
      bodyClassName="p-4"
    >
      {/* desktop topology */}
      <div className="relative hidden h-[640px] lg:block">
        <svg
          className="pointer-events-none absolute inset-0 h-full w-full"
          viewBox="0 0 100 100"
          preserveAspectRatio="none"
          aria-hidden
        >
          {EDGES.map((edge) => {
            const active =
              activeRole(edge.from) ||
              activeRole(edge.to) ||
              justSpawned === `${edge.to.toUpperCase()}-2`;
            return (
              <EdgePath
                key={`${edge.from}-${edge.to}`}
                edge={edge}
                counts={counts}
                active={active}
              />
            );
          })}
        </svg>

        {(Object.keys(ANCHORS) as RoleKey[]).map((role) => (
          <div
            key={role}
            className="absolute -translate-x-1/2 -translate-y-1/2"
            style={{ left: `${ANCHORS[role].x}%`, top: `${ANCHORS[role].y}%` }}
          >
            <motion.div
              animate={
                justSpawnedId && groups[role].some((a) => a.agentId === justSpawnedId)
                  ? { scale: [1, 1.04, 1] }
                  : { scale: 1 }
              }
              transition={{ duration: 0.6 }}
            >
              <RoleGroup
                role={role}
                agents={groups[role]}
                justSpawned={justSpawnedId}
                selectedAgentId={selectedAgentId}
                onSelect={selectAgent}
              />
            </motion.div>
          </div>
        ))}
      </div>

      {/* compact fallback */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:hidden">
        {(Object.keys(ANCHORS) as RoleKey[]).map((role) => (
          <RoleGroup
            key={role}
            role={role}
            agents={groups[role]}
            justSpawned={justSpawnedId}
            selectedAgentId={selectedAgentId}
            onSelect={selectAgent}
          />
        ))}
      </div>

      <Legend />
    </Panel>
  );
}
