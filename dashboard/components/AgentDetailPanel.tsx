"use client";

import { AnimatePresence, motion } from "framer-motion";
import { X } from "lucide-react";
import type { AgentStatus } from "@/lib/types";
import { ROLE_LABELS } from "@/lib/types";
import { useDashboard } from "@/lib/dashboard-context";
import { cn } from "@/lib/cn";
import { fmtTime } from "@/lib/format";
import { Chip, StatusDot, STATUS_TONE } from "./ui";

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-3 border-b border-line-soft py-2 last:border-0">
      <span className="mono text-[9px] uppercase tracking-[0.16em] text-fg-dim">
        {label}
      </span>
      <span className="mono max-w-[200px] text-right text-[11px] text-fg">
        {value}
      </span>
    </div>
  );
}

function Lifecycle({ steps, current }: { steps: AgentStatus[]; current: AgentStatus }) {
  return (
    <div className="flex flex-wrap items-center gap-1">
      {steps.map((step, i) => {
        const isCurrent = i === steps.length - 1 && step === current;
        return (
          <div key={`${step}-${i}`} className="flex items-center">
            <span
              className={cn(
                "mono rounded border px-1.5 py-[2px] text-[9px] uppercase tracking-[0.1em]",
                isCurrent
                  ? STATUS_TONE[step]
                  : "border-line-soft bg-white/[0.02] text-fg-dim",
              )}
            >
              {step}
            </span>
            {i < steps.length - 1 && (
              <span className="mx-1 text-[10px] text-fg-dim">→</span>
            )}
          </div>
        );
      })}
    </div>
  );
}

export function AgentDetailPanel() {
  const { frame, selectedAgentId, selectAgent } = useDashboard();
  const agent = frame?.agents.find((a) => a.agentId === selectedAgentId) ?? null;

  const lifecycle: AgentStatus[] =
    agent?.lifecycle && agent.lifecycle.length > 0
      ? agent.lifecycle
      : agent
        ? ["CREATED"]
        : [];

  /* Hard guarantee: an agent that is currently ACTIVE must never read TERMINATED. */
  const status: AgentStatus = agent?.status ?? "IDLE";

  return (
    <AnimatePresence>
      {agent && (
        <>
          <motion.div
            key="backdrop"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={() => selectAgent(null)}
            className="fixed inset-0 z-40 bg-black/50 backdrop-blur-[2px]"
          />
          <motion.aside
            key="panel"
            initial={{ x: "100%", opacity: 0.6 }}
            animate={{ x: 0, opacity: 1 }}
            exit={{ x: "100%", opacity: 0.6 }}
            transition={{ type: "spring", stiffness: 320, damping: 34 }}
            className="glass fixed inset-y-0 right-0 z-50 flex w-full max-w-[400px] flex-col"
            role="dialog"
            aria-label={`Agent ${agent.agentId} details`}
          >
            <header className="flex items-start justify-between gap-3 border-b border-line-soft px-5 py-4">
              <div>
                <div className="mono text-[10px] uppercase tracking-[0.2em] text-accent/80">
                  Agent Detail
                </div>
                <h2 className="mono mt-1 text-xl font-semibold text-fg">
                  {agent.agentId}
                </h2>
                <div className="mt-1 flex flex-wrap items-center gap-2">
                  <span className="text-[12px] text-fg-muted">
                    {ROLE_LABELS[agent.role]}
                  </span>
                  {agent.spawned ? (
                    <Chip tone="accent">Spawned</Chip>
                  ) : (
                    <Chip tone="neutral">Baseline</Chip>
                  )}
                </div>
              </div>
              <button
                onClick={() => selectAgent(null)}
                className="flex h-8 w-8 items-center justify-center rounded-lg border border-line-soft text-fg-muted transition-colors hover:border-accent/40 hover:text-accent"
                aria-label="Close"
              >
                <X className="h-4 w-4" />
              </button>
            </header>

            <div className="scroll-thin flex-1 overflow-y-auto px-5 py-4">
              <div className="mb-4 flex items-center gap-2">
                <span
                  className={cn(
                    "mono inline-flex items-center gap-1.5 rounded-md border px-2 py-1 text-[10px] uppercase tracking-[0.14em]",
                    STATUS_TONE[status],
                  )}
                >
                  <StatusDot status={status} />
                  {status}
                </span>
              </div>

              <div className="rounded-xl border border-line-soft bg-white/[0.02] px-3 py-1">
                <Row label="Agent ID" value={agent.agentId} />
                <Row label="Role" value={ROLE_LABELS[agent.role]} />
                <Row label="Status" value={status} />
                <Row label="Current task" value={agent.currentTask ?? "—"} />
                <Row label="Tasks completed" value={agent.meta.tasksCompleted} />
                <Row label="Tasks failed" value={agent.meta.tasksFailed} />
                <Row label="Created at" value={formatCreated(agent.meta.createdAt)} />
                <Row label="Current workload" value={Math.round(agent.meta.workload)} />
                <Row label="Current risk" value={Math.round(agent.meta.risk)} />
                {typeof agent.meta.utilization === "number" && (
                  <Row
                    label="Utilization"
                    value={`${Math.round(agent.meta.utilization * 100)}%`}
                  />
                )}
              </div>

              <div className="mt-5">
                <div className="mono mb-2 text-[9px] uppercase tracking-[0.2em] text-accent/80">
                  Lifecycle
                </div>
                <Lifecycle steps={lifecycle} current={status} />
                <p className="mono mt-3 text-[9px] uppercase tracking-[0.12em] text-fg-dim">
                  CREATED → IDLE → ACTIVE → COMPLETED → IDLE → TERMINATED
                </p>
              </div>

              {agent.spawned && (
                <div className="mt-5 rounded-xl border border-accent/30 bg-accent/[0.05] p-3">
                  <div className="mono text-[9px] uppercase tracking-[0.18em] text-accent">
                    Spawned instance
                  </div>
                  <p className="mt-1 text-[11px] leading-relaxed text-fg-muted">
                    Created at runtime by the Adaptive Controller in response to
                    workload or risk conditions — not part of the initial
                    six-agent organization.
                  </p>
                </div>
              )}
            </div>
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  );
}

function formatCreated(value: string): string {
  if (!value || value === "run-start") return "run start";
  const t = fmtTime(value);
  return t === value ? value : t;
}
