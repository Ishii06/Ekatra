"use client";

import { BarChart3 } from "lucide-react";
import type { MetricsSummary } from "@/lib/types";
import { useDashboard } from "@/lib/dashboard-context";
import { buildExperimentRun } from "@/lib/data/m8";
import { fmtDuration, fmtNumber, fmtPct } from "@/lib/format";
import { cn } from "@/lib/cn";
import { Chip, Panel } from "./ui";

function MetricCell({
  label,
  value,
  emphasis,
  muted,
}: {
  label: string;
  value: string;
  emphasis?: boolean;
  muted?: boolean;
}) {
  return (
    <div className="rounded-lg border border-line-soft bg-white/[0.02] px-2.5 py-2">
      <div className="mono text-[8px] uppercase leading-tight tracking-[0.14em] text-fg-dim">
        {label}
      </div>
      <div
        className={cn(
          "mono mt-1 text-[15px] font-semibold",
          muted ? "text-fg-dim" : emphasis ? "text-accent" : "text-fg",
        )}
      >
        {value}
      </div>
    </div>
  );
}

function Group({
  title,
  children,
  cols = 3,
}: {
  title: string;
  children: React.ReactNode;
  cols?: number;
}) {
  return (
    <div>
      <div className="mono mb-2 text-[9px] uppercase tracking-[0.2em] text-accent/70">
        {title}
      </div>
      <div
        className={cn(
          "grid gap-2",
          cols === 3 ? "grid-cols-2 sm:grid-cols-3" : "grid-cols-2",
        )}
      >
        {children}
      </div>
    </div>
  );
}

export function MetricsPanel() {
  const { mode, strategy, scenarioId, scenario, frame } = useDashboard();

  const experimentRun =
    mode === "experiment" ? buildExperimentRun(scenarioId, strategy) : null;
  const m: MetricsSummary = experimentRun?.metrics ?? frame?.metrics ?? emptyMetrics();

  const isFixed = mode === "experiment" && strategy === "fixed";

  return (
    <Panel
      eyebrow="Evaluation"
      title="Research Metrics"
      icon={<BarChart3 className="h-4 w-4" />}
      subtitle="Experimental measurements. Values depend on the workload configuration and are not a ranking of strategies."
      actions={
        <div className="flex flex-col items-end gap-1">
          <Chip tone={isFixed ? "neutral" : "accent"}>
            Strategy · {isFixed ? "FIXED" : "ADAPTIVE"}
          </Chip>
          {mode === "experiment" ? (
            <span className="mono text-[9px] text-fg-dim">source · M8 dataset</span>
          ) : (
            <span className="mono text-[9px] text-fg-dim">source · demo fixture</span>
          )}
        </div>
      }
      bodyClassName="p-4"
    >
      <div className="space-y-4">
        <Group title="Performance" cols={3}>
          <MetricCell label="Total tasks" value={fmtNumber(m.totalTasks)} />
          <MetricCell label="Completed tasks" value={fmtNumber(m.completedTasks)} />
          <MetricCell label="Failed tasks" value={fmtNumber(m.failedTasks)} />
          <MetricCell label="Total execution time" value={fmtDuration(m.totalExecutionSeconds)} />
          <MetricCell
            label="Avg task completion time"
            value={fmtDuration(m.averageTaskCompletionSeconds)}
          />
          <MetricCell label="Queue waiting time" value={fmtDuration(m.queueWaitingSeconds)} />
        </Group>

        <Group title="Resource usage" cols={4}>
          <MetricCell label="Initial agents" value={fmtNumber(m.initialAgents)} />
          <MetricCell label="Peak active agents" value={fmtNumber(m.peakActiveAgents)} />
          <MetricCell
            label="Avg active agents"
            value={m.averageActiveAgents.toFixed(2)}
          />
          <MetricCell label="Agent utilization" value={fmtPct(m.agentUtilization)} />
        </Group>

        <Group title="Adaptation" cols={4}>
          <MetricCell label="Spawn events" value={fmtNumber(m.spawnEvents)} emphasis={m.spawnEvents > 0} />
          <MetricCell label="Termination events" value={fmtNumber(m.terminationEvents)} />
          <MetricCell label="Reassignment events" value={fmtNumber(m.reassignmentEvents)} />
          <MetricCell label="Decision cycles" value={fmtNumber(m.cycleCount)} muted />
        </Group>
      </div>

      <div className="mt-4 flex flex-wrap items-center justify-between gap-2 border-t border-line-soft pt-3">
        <div className="flex flex-wrap items-center gap-2">
          <span className="mono text-[9px] uppercase tracking-[0.14em] text-fg-dim">
            Scenario
          </span>
          <span className="text-[11px] text-fg-muted">{scenario.name}</span>
        </div>
        {m.decisionsByType && Object.keys(m.decisionsByType).length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {Object.entries(m.decisionsByType).map(([action, count]) => (
              <span
                key={action}
                className="mono rounded border border-line-soft px-1.5 py-[1px] text-[9px] text-fg-dim"
              >
                {action} ×{count}
              </span>
            ))}
          </div>
        )}
      </div>
    </Panel>
  );
}

function emptyMetrics(): MetricsSummary {
  return {
    totalTasks: 0,
    completedTasks: 0,
    failedTasks: 0,
    totalExecutionSeconds: 0,
    averageTaskCompletionSeconds: 0,
    queueWaitingSeconds: 0,
    initialAgents: 0,
    peakActiveAgents: 0,
    averageActiveAgents: 0,
    agentUtilization: 0,
    spawnEvents: 0,
    terminationEvents: 0,
    reassignmentEvents: 0,
    decisionsByType: {},
    cycleCount: 0,
  };
}
