"use client";

import { Boxes, GitBranch } from "lucide-react";
import { cn } from "@/lib/cn";
import { Panel } from "./ui";

const FIXED = [
  "Static six-agent organization",
  "No dynamic spawning",
  "No dynamic termination",
  "Tasks executed by fixed role agents",
];

const ADAPTIVE = [
  "Dynamic agent pool",
  "Workload-aware scaling",
  "Risk-aware adaptation",
  "Task reassignment",
  "Task prioritization",
  "Agent lifecycle management",
];

function ListCard({
  title,
  subtitle,
  items,
  tone,
  icon,
}: {
  title: string;
  subtitle: string;
  items: string[];
  tone: "neutral" | "accent";
  icon: React.ReactNode;
}) {
  return (
    <div
      className={cn(
        "rounded-xl border p-4",
        tone === "accent"
          ? "border-accent/30 bg-accent/[0.04]"
          : "border-line-soft bg-white/[0.02]",
      )}
    >
      <div className="flex items-center gap-2">
        <span className={tone === "accent" ? "text-accent" : "text-fg-dim"}>{icon}</span>
        <div>
          <div
            className={cn(
              "mono text-[11px] font-semibold uppercase tracking-[0.16em]",
              tone === "accent" ? "text-accent" : "text-fg-muted",
            )}
          >
            {title}
          </div>
          <div className="mono text-[9px] uppercase tracking-[0.12em] text-fg-dim">
            {subtitle}
          </div>
        </div>
      </div>
      <ul className="mt-3 space-y-1.5">
        {items.map((item) => (
          <li key={item} className="flex items-start gap-2">
            <span
              className={cn(
                "mt-1.5 h-1 w-1 shrink-0 rounded-full",
                tone === "accent" ? "bg-accent" : "bg-fg-dim",
              )}
            />
            <span className="text-[11px] leading-snug text-fg-muted">{item}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function FixedVsAdaptive() {
  return (
    <Panel
      eyebrow="Experimental Design"
      title="Fixed vs Adaptive"
      subtitle="A conceptual comparison of the two orchestration strategies under evaluation."
      bodyClassName="p-4"
    >
      <div className="grid gap-3 md:grid-cols-2">
        <ListCard
          title="Fixed Multi-Agent Baseline"
          subtitle="Static composition"
          items={FIXED}
          tone="neutral"
          icon={<Boxes className="h-4 w-4" />}
        />
        <ListCard
          title="Adaptive — Ekatra"
          subtitle="Runtime adaptation"
          items={ADAPTIVE}
          tone="accent"
          icon={<GitBranch className="h-4 w-4" />}
        />
      </div>
      <p className="mono mt-3 text-[9px] uppercase tracking-[0.14em] text-fg-dim">
        Conceptual comparison — not a ranking. Experimental results determine outcomes.
      </p>
    </Panel>
  );
}
