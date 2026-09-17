"use client";

import { ChevronLeft, ChevronRight, Pause, Play, RotateCcw } from "lucide-react";
import { useDashboard } from "@/lib/dashboard-context";
import { cn } from "@/lib/cn";

export function PlayerControls() {
  const {
    frame,
    frames,
    frameIndex,
    totalFrames,
    playing,
    toggle,
    reset,
    stepForward,
    stepBack,
    jumpTo,
    atStart,
    atEnd,
    isDemo,
    intervalMs,
  } = useDashboard();

  const title = frame?.title ?? (frame ? `Step ${frameIndex + 1}` : "—");

  return (
    <div className="glass rounded-2xl px-4 py-3">
      <div className="flex flex-wrap items-center gap-x-5 gap-y-3">
        <div className="flex items-center gap-1.5">
          <button
            onClick={reset}
            disabled={atStart && !playing}
            className="flex h-8 w-8 items-center justify-center rounded-lg border border-line-soft text-fg-muted transition-colors hover:border-accent/40 hover:text-accent disabled:opacity-40"
            aria-label="Reset"
          >
            <RotateCcw className="h-3.5 w-3.5" />
          </button>
          <button
            onClick={stepBack}
            disabled={atStart}
            className="flex h-8 w-8 items-center justify-center rounded-lg border border-line-soft text-fg-muted transition-colors hover:border-accent/40 hover:text-accent disabled:opacity-40"
            aria-label="Previous step"
          >
            <ChevronLeft className="h-4 w-4" />
          </button>
          <button
            onClick={toggle}
            className={cn(
              "flex h-9 w-9 items-center justify-center rounded-lg border transition-all",
              playing
                ? "border-amber/50 bg-amber/10 text-amber"
                : "border-accent/50 bg-accent/15 text-accent hover:bg-accent/25",
            )}
            aria-label={playing ? "Pause" : "Play"}
          >
            {playing ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
          </button>
          <button
            onClick={stepForward}
            disabled={atEnd}
            className="flex h-8 w-8 items-center justify-center rounded-lg border border-line-soft text-fg-muted transition-colors hover:border-accent/40 hover:text-accent disabled:opacity-40"
            aria-label="Next step"
          >
            <ChevronRight className="h-4 w-4" />
          </button>
        </div>

        <div className="min-w-0 flex-1">
          <div className="mono text-[9px] uppercase tracking-[0.2em] text-accent/80">
            {isDemo ? "Demo walkthrough" : "Recorded run playback"}
          </div>
          <div className="truncate text-[13px] font-medium text-fg">{title}</div>
          {frame?.narrative && (
            <div className="truncate text-[11px] text-fg-dim">{frame.narrative}</div>
          )}
        </div>

        <div className="mono shrink-0 text-right text-[10px] uppercase tracking-[0.14em] text-fg-dim">
          <div>
            Step {frameIndex + 1} / {totalFrames || 1}
          </div>
          <div>{playing ? `auto · ${intervalMs / 1000}s` : "paused"}</div>
        </div>
      </div>

      <div className="mt-3 flex flex-wrap gap-1">
        {frames.map((f, i) => (
          <button
            key={i}
            onClick={() => jumpTo(i)}
            title={f.title ?? `Step ${i + 1}`}
            className={cn(
              "h-1.5 flex-1 rounded-full transition-colors",
              i === frameIndex
                ? "bg-accent"
                : i < frameIndex
                  ? "bg-accent/35"
                  : "bg-line-soft hover:bg-accent/30",
            )}
            aria-label={`Go to step ${i + 1}`}
          />
        ))}
      </div>
    </div>
  );
}
