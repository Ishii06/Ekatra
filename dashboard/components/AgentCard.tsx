"use client";

import { motion } from "framer-motion";
import { Plus } from "lucide-react";
import type { Agent, RoleKey } from "@/lib/types";
import { ROLE_LABELS } from "@/lib/types";
import { cn } from "@/lib/cn";
import { StatusDot, STATUS_TONE, roleShort } from "./ui";

const STATUS_TEXT: Record<Agent["status"], string> = {
  CREATED: "CREATED",
  IDLE: "IDLE",
  ACTIVE: "ACTIVE",
  COMPLETED: "COMPLETED",
  TERMINATED: "TERMINATED",
};

export function AgentCard({
  agent,
  justSpawned,
  selected,
  onSelect,
  compact,
}: {
  agent: Agent;
  justSpawned?: boolean;
  selected?: boolean;
  onSelect?: (id: string) => void;
  compact?: boolean;
}) {
  const isActive = agent.status === "ACTIVE";
  return (
    <motion.button
      type="button"
      onClick={() => onSelect?.(agent.agentId)}
      initial={justSpawned ? { opacity: 0, scale: 0.82, y: -8 } : false}
      animate={{ opacity: 1, scale: 1, y: 0 }}
      transition={{ type: "spring", stiffness: 360, damping: 26 }}
      whileHover={{ y: -2 }}
      className={cn(
        "group relative w-full overflow-hidden rounded-xl border px-3 py-2 text-left transition-colors",
        isActive
          ? "border-cyan-glow/45 bg-cyan-glow/[0.07]"
          : "border-line-soft bg-white/[0.025] hover:border-accent/40",
        justSpawned &&
          "border-accent/70 shadow-[0_0_28px_-8px_rgba(34,211,238,0.85)]",
        selected && "ring-1 ring-accent/70",
      )}
      aria-label={`${agent.agentId}, ${ROLE_LABELS[agent.role]}, ${agent.status}`}
    >
      {justSpawned && (
        <span className="scan-sweep pointer-events-none absolute inset-x-0 top-0 h-8 bg-gradient-to-b from-cyan-glow/25 to-transparent" />
      )}
      <span
        className={cn(
          "absolute inset-y-1 left-0 w-0.5 rounded-full",
          isActive
            ? "bg-cyan-glow"
            : agent.status === "COMPLETED"
              ? "bg-mint/70"
              : agent.status === "TERMINATED"
                ? "bg-rose/70"
                : "bg-line",
        )}
      />

      <div className="flex items-center justify-between gap-2 pl-1.5">
        <span className="mono text-[12px] font-semibold tracking-wide text-fg">
          {agent.agentId}
        </span>
        {agent.spawned ? (
          <span className="mono inline-flex items-center gap-1 rounded border border-accent/40 bg-accent/10 px-1.5 py-[1px] text-[8px] uppercase tracking-[0.16em] text-accent">
            <Plus className="h-2.5 w-2.5" /> Spawned
          </span>
        ) : (
          <span className="mono rounded border border-line-soft px-1.5 py-[1px] text-[8px] uppercase tracking-[0.16em] text-fg-dim">
            Baseline
          </span>
        )}
      </div>

      <div className="mt-1 pl-1.5">
        <div className="mono text-[9px] uppercase tracking-[0.16em] text-fg-dim">
          {ROLE_LABELS[agent.role]}
        </div>
        <div className="mt-1 flex items-center justify-between gap-2">
          <span
            className={cn(
              "mono inline-flex items-center gap-1.5 rounded border px-1.5 py-[1px] text-[9px] uppercase tracking-[0.12em]",
              STATUS_TONE[agent.status],
            )}
          >
            <StatusDot status={agent.status} />
            {STATUS_TEXT[agent.status]}
          </span>
          {!compact && (
            <span className="mono max-w-[84px] truncate text-[9px] text-fg-dim">
              {agent.currentTask ?? "—"}
            </span>
          )}
        </div>
      </div>
    </motion.button>
  );
}

export function RoleGroup({
  role,
  agents,
  justSpawned,
  selectedAgentId,
  onSelect,
}: {
  role: RoleKey;
  agents: Agent[];
  justSpawned: string | null;
  selectedAgentId: string | null;
  onSelect: (id: string) => void;
}) {
  const visible = agents.slice(0, 3);
  const overflow = agents.length - visible.length;
  return (
    <div className="w-[190px]">
      <div className="mb-1.5 flex items-center justify-between px-0.5">
        <span className="mono text-[9px] uppercase tracking-[0.2em] text-fg-dim">
          {roleShort(role)}
        </span>
        <span className="mono text-[9px] text-fg-dim">
          · {agents.length}
        </span>
      </div>
      <div className="space-y-1.5">
        {visible.map((a) => (
          <AgentCard
            key={a.agentId}
            agent={a}
            justSpawned={justSpawned === a.agentId}
            selected={selectedAgentId === a.agentId}
            onSelect={onSelect}
          />
        ))}
        {overflow > 0 && (
          <div className="mono rounded-lg border border-dashed border-line-soft px-3 py-1.5 text-center text-[9px] text-fg-dim">
            +{overflow} more
          </div>
        )}
      </div>
    </div>
  );
}
