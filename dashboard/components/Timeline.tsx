"use client";

import { useEffect, useRef } from "react";
import { History } from "lucide-react";
import type { TimelineKind } from "@/lib/types";
import { useDashboard } from "@/lib/dashboard-context";
import { cn } from "@/lib/cn";
import { shortTimestamp } from "@/lib/format";
import { Chip, Panel } from "./ui";

const KIND_COLOR: Record<TimelineKind, string> = {
  workflow: "bg-accent",
  task: "bg-violet",
  agent: "bg-cyan-glow",
  observation: "bg-amber",
  analysis: "bg-violet",
  decision: "bg-accent",
  allocation: "bg-cyan-glow",
  quality: "bg-mint",
};

const KIND_LABEL: Record<TimelineKind, string> = {
  workflow: "workflow",
  task: "task",
  agent: "agent",
  observation: "observe",
  analysis: "analyze",
  decision: "decision",
  allocation: "allocate",
  quality: "quality",
};

export function Timeline() {
  const { frame, isDemo, playing } = useDashboard();
  const events = frame?.events ?? [];
  const scrollRef = useRef<HTMLDivElement>(null);
  const count = events.length;

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, [count, playing]);

  return (
    <Panel
      eyebrow="Observability"
      title="Adaptive Event Timeline"
      icon={<History className="h-4 w-4" />}
      subtitle={
        isDemo
          ? "Simulated presentation events — deterministic fixture data, not an experiment run."
          : "Reconstructed from the M8 run's recorded raw_events."
      }
      actions={<Chip tone={isDemo ? "amber" : "violet"}>{isDemo ? "DEMO" : "M8 RUN"}</Chip>}
      bodyClassName="p-3"
    >
      <div
        ref={scrollRef}
        className="scroll-thin max-h-[420px] space-y-0 overflow-y-auto pr-1"
      >
        {events.length === 0 && (
          <div className="py-6 text-center">
            <span className="mono text-[10px] uppercase tracking-[0.18em] text-fg-dim">
              No events yet
            </span>
          </div>
        )}
        {events.map((event, i) => {
          const isLatest = i === events.length - 1;
          return (
            <div key={event.id} className="relative flex gap-3 py-1.5">
              <div className="relative flex w-14 shrink-0 justify-end">
                <span className="mono pt-0.5 text-[9px] text-fg-dim">
                  {shortTimestamp(event.time)}
                </span>
              </div>
              <div className="relative flex flex-col items-center">
                <span
                  className={cn(
                    "mt-1 h-2 w-2 shrink-0 rounded-full",
                    KIND_COLOR[event.kind],
                    isLatest && "ring-2 ring-accent/40",
                  )}
                />
                {i < events.length - 1 && (
                  <span className="absolute top-3.5 h-full w-px bg-line-soft" />
                )}
              </div>
              <div className="min-w-0 flex-1 pb-1">
                <div className="flex items-center gap-2">
                  <span className="mono text-[8px] uppercase tracking-[0.16em] text-fg-dim">
                    {KIND_LABEL[event.kind]}
                  </span>
                </div>
                <p
                  className={cn(
                    "text-[11px] leading-snug",
                    isLatest ? "text-fg" : "text-fg-muted",
                  )}
                >
                  {event.title}
                </p>
                {event.detail && (
                  <p className="mono text-[9px] text-fg-dim">{event.detail}</p>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </Panel>
  );
}
