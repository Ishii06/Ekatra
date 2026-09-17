"use client";

import { AnimatePresence, motion } from "framer-motion";
import {
  ArrowDown,
  ArrowRight,
  ArrowUp,
  Check,
  Minus,
  Plus,
  RefreshCw,
  Shuffle,
  SlidersHorizontal,
} from "lucide-react";
import type { AdaptiveAction, AdaptiveDecision, FlowStage } from "@/lib/types";
import { FLOW_STAGES } from "@/lib/data/demo";
import { useDashboard } from "@/lib/dashboard-context";
import { cn } from "@/lib/cn";
import { Chip, Panel, levelText } from "./ui";

const STAGE_DETAIL: Record<FlowStage, string> = {
  OBSERVE: "Read system state",
  ANALYZE: "Compute workload / risk",
  DECIDE: "Select orchestration action",
  ALLOCATE: "Change agent pool",
  EXECUTE: "Run assigned tasks",
  EVALUATE: "Check outcomes",
  ADAPT: "Feed result back",
};

const ACTION_ICON: Record<AdaptiveAction, React.ReactNode> = {
  SPAWN: <Plus className="h-4 w-4" />,
  TERMINATE: <Minus className="h-4 w-4" />,
  REASSIGN: <Shuffle className="h-4 w-4" />,
  PRIORITIZE: <ArrowUp className="h-4 w-4" />,
  CONTINUE: <Check className="h-4 w-4" />,
};

const ACTION_CLASS: Record<AdaptiveAction, string> = {
  SPAWN: "border-accent/50 bg-accent/10 text-accent",
  TERMINATE: "border-rose/50 bg-rose/10 text-rose",
  REASSIGN: "border-amber/50 bg-amber/10 text-amber",
  PRIORITIZE: "border-amber/50 bg-amber/10 text-amber",
  CONTINUE: "border-mint/40 bg-mint/10 text-mint",
};

function LoopDiagram({ active }: { active: FlowStage | null }) {
  return (
    <ol className="relative space-y-0">
      <span className="absolute left-[13px] top-2 bottom-2 w-px bg-line-soft" aria-hidden />
      {FLOW_STAGES.map((stage, i) => {
        const isActive = stage === active;
        return (
          <li key={stage} className="relative">
            <div
              className={cn(
                "relative flex items-center gap-3 rounded-lg px-2 py-1.5 transition-all duration-400",
                isActive && "bg-accent/[0.08]",
              )}
            >
              <span
                className={cn(
                  "relative z-10 flex h-6 w-6 shrink-0 items-center justify-center rounded-full border text-[9px]",
                  isActive
                    ? "border-accent/70 bg-accent/15 text-accent"
                    : "border-line-soft bg-panel text-fg-dim",
                )}
              >
                {isActive ? <RefreshCw className="h-3 w-3 animate-spin" style={{ animationDuration: "3s" }} /> : i + 1}
              </span>
              <span className="min-w-0">
                <span
                  className={cn(
                    "mono block text-[11px] uppercase tracking-[0.16em]",
                    isActive ? "text-accent" : "text-fg-muted",
                  )}
                >
                  {stage}
                </span>
                <span className="block truncate text-[10px] text-fg-dim">
                  {STAGE_DETAIL[stage]}
                </span>
              </span>
            </div>
            {i < FLOW_STAGES.length - 1 && (
              <ArrowDown className="ml-[9px] h-3 w-3 text-fg-dim/40" aria-hidden />
            )}
          </li>
        );
      })}
      <li className="mt-1 flex items-center gap-2 pl-1">
        <RefreshCw className="h-3 w-3 text-accent/70" />
        <span className="mono text-[9px] uppercase tracking-[0.16em] text-fg-dim">
          loop repeats while project is active
        </span>
      </li>
    </ol>
  );
}

function MiniStat({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: string;
}) {
  return (
    <div className="rounded-lg border border-line-soft bg-white/[0.02] px-2.5 py-2">
      <div className="mono text-[8px] uppercase tracking-[0.16em] text-fg-dim">
        {label}
      </div>
      <div className={cn("mono mt-0.5 text-sm font-semibold text-fg", tone)}>
        {value}
      </div>
    </div>
  );
}

function BeforeAfter({ decision }: { decision: AdaptiveDecision }) {
  const { before, after } = decision;
  const rows = [
    { label: "Active agents (role)", b: before.activeForRole, a: after.activeForRole },
    { label: "Queue", b: before.queue, a: after.queue },
    { label: "Workload", b: before.workload, a: after.workload },
    { label: "Risk", b: before.risk, a: after.risk },
  ];
  return (
    <div className="mt-3 overflow-hidden rounded-lg border border-line-soft">
      <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-2 border-b border-line-soft bg-white/[0.02] px-3 py-1.5">
        <span className="mono text-[9px] uppercase tracking-[0.18em] text-fg-dim">
          Before
        </span>
        <span className="w-4" />
        <span className="mono text-[9px] uppercase tracking-[0.18em] text-fg-dim">
          After
        </span>
      </div>
      <div className="divide-y divide-line-soft/60">
        {rows.map((r) => {
          const changed = r.b !== r.a;
          return (
            <div
              key={r.label}
              className="grid grid-cols-[1fr_auto_1fr] items-center gap-2 px-3 py-1.5"
            >
              <span className={cn("mono text-[12px]", changed ? "text-fg" : "text-fg-muted")}>
                {r.b}
              </span>
              <ArrowRight className="h-3 w-3 text-fg-dim" />
              <span className="flex items-center justify-between gap-2">
                <span className={cn("mono text-[12px]", changed ? "text-accent" : "text-fg-muted")}>
                  {r.a}
                </span>
                <span className="mono text-[8px] uppercase tracking-[0.12em] text-fg-dim">
                  {r.label}
                </span>
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export function AdaptiveControllerPanel() {
  const { frame } = useDashboard();
  const decision = frame?.latestDecision ?? null;
  const observation = frame?.observation;
  const workload = frame?.workload;
  const risk = frame?.risk;

  return (
    <Panel
      eyebrow="Adaptive Controller"
      title="Deterministic Adaptive Loop"
      icon={<SlidersHorizontal className="h-4 w-4" />}
      subtitle="Measurable orchestration decisions — separate from LLM reasoning."
      actions={<Chip tone="accent">State-driven</Chip>}
      bodyClassName="p-4"
    >
      <div className="grid gap-4 xl:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
        <LoopDiagram active={frame?.flowStage ?? null} />

        <div>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 xl:grid-cols-2">
            <MiniStat
              label="Workload"
              value={`${Math.round(workload?.score ?? 0)}`}
              tone={levelText(workload?.level ?? "NORMAL")}
            />
            <MiniStat
              label="Risk"
              value={`${Math.round(risk?.score ?? 0)}`}
              tone={levelText(risk?.level ?? "NORMAL")}
            />
            <MiniStat label="Queue length" value={`${observation?.queueLength ?? 0}`} />
            <MiniStat
              label="Execution delay"
              value={formatFraction(observation?.executionDelay)}
            />
            <MiniStat
              label="Failure rate"
              value={formatFraction(observation?.failureRate)}
            />
            <MiniStat
              label="Active agents"
              value={`${observation?.activeAgents ?? 0}`}
            />
          </div>

          <div className="mt-3">
            <AnimatePresence mode="wait">
              {decision ? (
                <motion.div
                  key={`${decision.cycle}-${decision.action}-${decision.timestamp}`}
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -6 }}
                  transition={{ duration: 0.35 }}
                  className={cn(
                    "rounded-xl border p-3",
                    decision.action === "CONTINUE"
                      ? "border-line-soft bg-white/[0.02]"
                      : "decision-glow border-cyan-glow/40 bg-cyan-glow/[0.04]",
                  )}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="mono text-[9px] uppercase tracking-[0.22em] text-fg-dim">
                      Adaptive Decision
                    </span>
                    <span className="mono text-[9px] text-fg-dim">
                      cycle {decision.cycle}
                    </span>
                  </div>
                  <div className="mt-2 flex items-center gap-2">
                    <span
                      className={cn(
                        "flex h-8 w-8 items-center justify-center rounded-lg border",
                        ACTION_CLASS[decision.action],
                      )}
                    >
                      {ACTION_ICON[decision.action]}
                    </span>
                    <span className="text-lg font-semibold tracking-wide text-fg">
                      {decision.action}
                    </span>
                    {decision.affectedRole && (
                      <Chip tone="accent">{decision.affectedRole}</Chip>
                    )}
                  </div>
                  <p className="mt-2 text-[12px] leading-relaxed text-fg-muted">
                    {decision.reason}
                  </p>
                  <BeforeAfter decision={decision} />
                </motion.div>
              ) : (
                <motion.div
                  key="no-decision"
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  className="rounded-xl border border-dashed border-line-soft px-3 py-6 text-center"
                >
                  <div className="mono text-[10px] uppercase tracking-[0.2em] text-fg-dim">
                    NO ADAPTATION REQUIRED
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        </div>
      </div>
    </Panel>
  );
}

function formatFraction(value: number | undefined): string {
  if (value === undefined || value === null) return "—";
  return `${Math.round(value * 100)}%`;
}
