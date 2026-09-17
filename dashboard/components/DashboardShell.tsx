"use client";

import { DashboardProvider, useDashboard } from "@/lib/dashboard-context";
import { SiteHeader } from "./SiteHeader";
import { Hero } from "./Hero";
import { PlayerControls } from "./PlayerControls";
import { OrgPanel } from "./OrgPanel";
import { AdaptiveControllerPanel } from "./AdaptiveControllerPanel";
import { WorkloadCard, RiskCard } from "./WorkloadRiskCards";
import { TaskBoard } from "./TaskBoard";
import { Timeline } from "./Timeline";
import { MetricsPanel } from "./MetricsPanel";
import { FixedVsAdaptive } from "./FixedVsAdaptive";
import { AgentDetailPanel } from "./AgentDetailPanel";
import { SectionHeader } from "./ui";

function Background() {
  return (
    <div className="pointer-events-none fixed inset-0 -z-10 overflow-hidden">
      <div className="grid-bg absolute inset-0 opacity-40" />
      <div className="absolute -left-40 top-0 h-[420px] w-[420px] rounded-full bg-violet/10 blur-[130px]" />
      <div className="absolute right-0 top-1/3 h-[420px] w-[420px] rounded-full bg-cyan-glow/[0.08] blur-[130px]" />
      <div className="absolute bottom-0 left-1/3 h-[360px] w-[520px] rounded-full bg-accent/[0.05] blur-[120px]" />
      <div className="absolute inset-0 bg-gradient-to-b from-transparent via-transparent to-ink" />
    </div>
  );
}

function Footer() {
  const { isDemo, provenanceLabel, scenario } = useDashboard();
  return (
    <footer className="mx-auto max-w-[1600px] px-6 pb-12 pt-6">
      <div className="glass rounded-2xl px-5 py-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="mono text-[9px] uppercase tracking-[0.16em] text-fg-dim">
            Ekatra · Research prototype dashboard · Not a production deployment
          </div>
          <div className="mono text-[9px] uppercase tracking-[0.16em] text-fg-dim">
            {provenanceLabel} · {scenario.name}
          </div>
        </div>
        <p className="mt-2 text-[11px] leading-relaxed text-fg-dim">
          {isDemo
            ? "This view is a simulated presentation walkthrough using deterministic fixture data. It is clearly separated from recorded experiment runs and must not be presented as an experimental result."
            : "This view replays recorded Milestone 8 experiment events. No values are recomputed in the frontend; orchestration, workload and risk scoring remain in the Python engine."}
        </p>
      </div>
    </footer>
  );
}

function DashboardBody() {
  return (
    <div className="relative min-h-screen">
      <Background />
      <SiteHeader />
      <main>
        <Hero />

        <div className="mx-auto max-w-[1600px] space-y-8 px-6 pb-4 pt-6">
          <PlayerControls />

          <section>
            <SectionHeader
              index="01"
              eyebrow="Live system"
              title="Agent organization & adaptive control"
              description="The organization is observed and, when workload or risk conditions require it, reallocated by the deterministic Adaptive Controller."
            />
            <div className="grid gap-4 xl:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
              <OrgPanel />
              <AdaptiveControllerPanel />
            </div>
          </section>

          <section>
            <SectionHeader
              index="02"
              eyebrow="Analysis"
              title="Workload & risk observation"
              description="Measurable indicators feed the controller. Scores are computed by the engine — the dashboard only visualizes them."
            />
            <div className="grid gap-4 lg:grid-cols-2">
              <WorkloadCard />
              <RiskCard />
            </div>
          </section>

          <section>
            <SectionHeader
              index="03"
              eyebrow="Execution"
              title="Task flow"
              description="Work progresses through deterministic task states, with retries preserving the original task identity."
            />
            <TaskBoard />
          </section>

          <section>
            <SectionHeader
              index="04"
              eyebrow="Observability & evaluation"
              title="Events, metrics & experimental design"
              description="Adaptive events are logged for later analysis; metrics are reported as measurements rather than rankings."
            />
            <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.15fr)]">
              <Timeline />
              <div className="space-y-4">
                <MetricsPanel />
                <FixedVsAdaptive />
              </div>
            </div>
          </section>
        </div>

        <Footer />
      </main>
      <AgentDetailPanel />
    </div>
  );
}

export function DashboardShell() {
  return (
    <DashboardProvider>
      <DashboardBody />
    </DashboardProvider>
  );
}
