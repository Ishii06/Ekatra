"use client";

import { Gauge, ShieldAlert, TrendingUp } from "lucide-react";
import { useDashboard } from "@/lib/dashboard-context";
import { MeterBar, Panel, RingGauge, levelText } from "./ui";

function isUnavailable(list: string[] | undefined, key: string): boolean {
  return Boolean(list?.includes(key));
}

export function WorkloadCard() {
  const { frame } = useDashboard();
  const w = frame?.workload;

  return (
    <Panel
      eyebrow="Workload Model"
      title="Workload"
      icon={<TrendingUp className="h-4 w-4" />}
      subtitle="W = 0.40·Queue + 0.30·Complexity + 0.20·Delay + 0.10·Failure (normalized 0–100)"
      bodyClassName="p-4"
    >
      <div className="flex flex-col items-center gap-4 sm:flex-row sm:items-center">
        <RingGauge
          score={w?.score ?? 0}
          level={w?.level ?? "NORMAL"}
          label="Score"
        />
        <div className="w-full flex-1 space-y-2.5">
          <MeterBar
            label="Queue Length"
            value={w?.queueLength ?? 0}
            max={12}
            display={`${w?.queueLength ?? 0}`}
            tone="accent"
            unavailable={isUnavailable(w?.unavailable, "queueLength")}
          />
          <MeterBar
            label="Task Complexity"
            value={w?.complexity ?? 0}
            max={1}
            display={`${Math.round((w?.complexity ?? 0) * 100)}%`}
            tone="violet"
            unavailable={isUnavailable(w?.unavailable, "complexity")}
          />
          <MeterBar
            label="Execution Delay"
            value={w?.executionDelay ?? 0}
            max={1}
            display={`${Math.round((w?.executionDelay ?? 0) * 100)}%`}
            tone="amber"
            unavailable={isUnavailable(w?.unavailable, "executionDelay")}
          />
          <MeterBar
            label="Failure Rate"
            value={w?.failureRate ?? 0}
            max={1}
            display={`${Math.round((w?.failureRate ?? 0) * 100)}%`}
            tone="rose"
            unavailable={isUnavailable(w?.unavailable, "failureRate")}
          />
        </div>
      </div>
      <div className="mt-3 flex items-center justify-between border-t border-line-soft pt-3">
        <span className="mono text-[9px] uppercase tracking-[0.16em] text-fg-dim">
          Level
        </span>
        <span className={`mono text-[11px] font-semibold ${levelText(w?.level ?? "NORMAL")}`}>
          {w?.level ?? "NORMAL"}
        </span>
      </div>
    </Panel>
  );
}

export function RiskCard() {
  const { frame } = useDashboard();
  const r = frame?.risk;

  const rows: { key: keyof NonNullable<typeof r>; label: string }[] = [
    { key: "securityFindings", label: "Security findings" },
    { key: "authIssues", label: "Auth / AuthZ issues" },
    { key: "suspiciousCode", label: "Suspicious code" },
    { key: "failedChecks", label: "Security check failures" },
    { key: "repeatedFailures", label: "Repeated failures" },
    { key: "highRiskTasks", label: "High-risk tasks" },
  ];

  return (
    <Panel
      eyebrow="Risk Model"
      title="Risk"
      icon={<ShieldAlert className="h-4 w-4" />}
      subtitle="Aggregated from measurable security indicators (normalized 0–100)."
      bodyClassName="p-4"
    >
      <div className="flex flex-col items-center gap-4 sm:flex-row sm:items-center">
        <RingGauge
          score={r?.score ?? 0}
          level={r?.level ?? "NORMAL"}
          label="Score"
        />
        <div className="w-full flex-1 space-y-2">
          {rows.map((row) => {
            const raw = (r?.[row.key] as number | undefined) ?? 0;
            return (
              <MeterBar
                key={String(row.key)}
                label={row.label}
                value={raw}
                max={5}
                display={`${raw}`}
                tone="rose"
                unavailable={isUnavailable(r?.unavailable, String(row.key))}
              />
            );
          })}
        </div>
      </div>
      <div className="mt-3 flex items-center justify-between border-t border-line-soft pt-3">
        <span className="mono text-[9px] uppercase tracking-[0.16em] text-fg-dim">
          Level
        </span>
        <span className={`mono text-[11px] font-semibold ${levelText(r?.level ?? "NORMAL")}`}>
          {r?.level ?? "NORMAL"}
        </span>
      </div>
    </Panel>
  );
}
