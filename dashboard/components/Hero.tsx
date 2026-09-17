"use client";

import { motion } from "framer-motion";
import { ChevronRight } from "lucide-react";
import type { FlowStage } from "@/lib/types";
import { useDashboard } from "@/lib/dashboard-context";
import { cn } from "@/lib/cn";
import { Chip } from "./ui";

const PIPELINE = [
  { short: "Project", long: "Project Requirement" },
  { short: "Project Manager", long: "LLM Project Manager" },
  { short: "Task Decomposition", long: "Task Decomposition" },
  { short: "Specialized Agents", long: "Specialized Agent Pools" },
  { short: "Observe Workload / Risk", long: "Workload & Risk Observation" },
  { short: "Adaptive Decision", long: "Adaptive Decision" },
  { short: "Spawn / Reassign / Prioritize", long: "Resource Reallocation" },
  { short: "Execution", long: "Task Execution" },
  { short: "Evaluation", long: "Evaluation & Feedback" },
];

const STAGE_TO_PIPELINE: Record<FlowStage, number> = {
  OBSERVE: 4,
  ANALYZE: 4,
  DECIDE: 5,
  ALLOCATE: 6,
  EXECUTE: 7,
  EVALUATE: 8,
  ADAPT: 8,
};

function FlowPipeline() {
  const { frame } = useDashboard();
  const active = frame?.flowStage ? STAGE_TO_PIPELINE[frame.flowStage] : -1;

  return (
    <div className="glass mt-8 rounded-2xl px-4 py-4">
      <div className="mono mb-3 flex items-center gap-2 text-[10px] uppercase tracking-[0.28em] text-accent/80">
        <span className="h-1 w-1 rounded-full bg-accent" />
        Orchestration Flow
      </div>
      <div className="flex flex-wrap items-stretch gap-y-2">
        {PIPELINE.map((stage, i) => {
          const isActive = i === active;
          return (
            <div key={stage.long} className="flex items-center">
              <div
                className={cn(
                  "relative rounded-lg border px-3 py-2 transition-all duration-500",
                  isActive
                    ? "border-accent/60 bg-accent/10 shadow-[0_0_24px_-10px_rgba(34,211,238,0.8)]"
                    : "border-line-soft bg-white/[0.02]",
                )}
              >
                <div
                  className={cn(
                    "mono text-[9px] uppercase tracking-[0.16em]",
                    isActive ? "text-accent" : "text-fg-dim",
                  )}
                >
                  {String(i + 1).padStart(2, "0")}
                </div>
                <div
                  className={cn(
                    "mt-0.5 text-[11px] font-medium leading-tight",
                    isActive ? "text-fg" : "text-fg-muted",
                  )}
                >
                  {stage.short}
                </div>
                {isActive && (
                  <motion.span
                    layoutId="pipeline-active"
                    className="absolute inset-0 -z-10 rounded-lg bg-accent/5"
                    transition={{ type: "spring", stiffness: 320, damping: 30 }}
                  />
                )}
              </div>
              {i < PIPELINE.length - 1 && (
                <ChevronRight
                  className={cn(
                    "mx-0.5 h-3.5 w-3.5 shrink-0",
                    i < active ? "text-accent/70" : "text-fg-dim/50",
                  )}
                />
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

export function Hero() {
  const { frame, isDemo, provenanceLabel, scenario, mode, strategy } = useDashboard();

  return (
    <section className="relative overflow-hidden">
      <div className="grid-bg pointer-events-none absolute inset-0 opacity-60" />
      <div className="pointer-events-none absolute -top-40 left-1/2 h-80 w-[900px] -translate-x-1/2 rounded-full bg-cyan-glow/10 blur-[120px]" />
      <div className="relative mx-auto max-w-[1600px] px-6 pb-2 pt-10">
        <div className="flex flex-wrap items-end justify-between gap-6">
          <div className="max-w-3xl">
            <motion.h1
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.5 }}
              className="text-gradient text-5xl font-semibold tracking-tight sm:text-6xl"
            >
              Ekatra
            </motion.h1>
            <motion.p
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.5, delay: 0.06 }}
              className="mt-3 text-lg font-medium text-fg"
            >
              Adaptive Multi-Agent Orchestration for Autonomous Software Development
            </motion.p>
            <motion.p
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.5, delay: 0.12 }}
              className="mt-3 max-w-2xl text-sm leading-relaxed text-fg-muted"
            >
              An AI software engineering organization that dynamically adapts its
              agent workforce based on workload and risk — treating agents as
              allocatable computational resources rather than permanently fixed
              workers.
            </motion.p>
          </div>

          <div className="flex flex-col items-start gap-2">
            <Chip tone={isDemo ? "amber" : "violet"}>{provenanceLabel}</Chip>
            <div className="text-xs text-fg-muted">
              Scenario:{" "}
              <span className="text-fg">{scenario.name}</span>
            </div>
            <div className="mono text-[10px] uppercase tracking-[0.16em] text-fg-dim">
              Strategy · {mode === "experiment" ? strategy : "adaptive (simulated)"}
            </div>
            <div className="mono text-[10px] uppercase tracking-[0.16em] text-fg-dim">
              Project state · {frame?.projectState ?? "—"}
            </div>
          </div>
        </div>

        <FlowPipeline />
      </div>
    </section>
  );
}
