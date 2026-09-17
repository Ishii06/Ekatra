"use client";

import { FlaskConical, Pause, Play, Sparkles } from "lucide-react";
import { useDashboard } from "@/lib/dashboard-context";
import { cn } from "@/lib/cn";
import { Chip } from "./ui";

function LogoMark() {
  return (
    <svg viewBox="0 0 40 40" className="h-9 w-9" aria-hidden>
      <defs>
        <linearGradient id="ekatra-mark" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#7dd3fc" />
          <stop offset="100%" stopColor="#a78bfa" />
        </linearGradient>
      </defs>
      <path
        d="M20 4 L34 12 V28 L20 36 L6 28 V12 Z"
        fill="none"
        stroke="url(#ekatra-mark)"
        strokeWidth="1.4"
        opacity="0.85"
      />
      <circle cx="20" cy="12" r="2.3" fill="#7dd3fc" />
      <circle cx="12" cy="24" r="2.3" fill="#a78bfa" />
      <circle cx="28" cy="24" r="2.3" fill="#38bdf8" />
      <path
        d="M20 12 L12 24 M20 12 L28 24 M12 24 L28 24"
        stroke="url(#ekatra-mark)"
        strokeWidth="1"
        opacity="0.6"
      />
    </svg>
  );
}

function Segmented<T extends string>({
  options,
  value,
  onChange,
  ariaLabel,
}: {
  options: { value: T; label: string; icon?: React.ReactNode }[];
  value: T;
  onChange: (v: T) => void;
  ariaLabel: string;
}) {
  return (
    <div
      role="tablist"
      aria-label={ariaLabel}
      className="inline-flex items-center gap-0.5 rounded-lg border border-line-soft bg-black/20 p-0.5"
    >
      {options.map((opt) => (
        <button
          key={opt.value}
          role="tab"
          aria-selected={value === opt.value}
          onClick={() => onChange(opt.value)}
          className={cn(
            "mono flex items-center gap-1.5 rounded-md px-2.5 py-1 text-[10px] uppercase tracking-[0.14em] transition-colors",
            value === opt.value
              ? "bg-accent/15 text-accent shadow-[inset_0_0_0_1px_rgba(56,189,248,0.35)]"
              : "text-fg-dim hover:text-fg-muted",
          )}
        >
          {opt.icon}
          {opt.label}
        </button>
      ))}
    </div>
  );
}

export function SiteHeader() {
  const {
    mode,
    setMode,
    scenarios,
    scenarioId,
    setScenarioId,
    strategy,
    setStrategy,
    playing,
    toggle,
    provenanceLabel,
    isDemo,
  } = useDashboard();

  const activeScenarioName =
    scenarios.find((s) => s.id === scenarioId)?.name ?? scenarioId;

  return (
    <header className="sticky top-0 z-40 border-b border-line-soft bg-ink/80 backdrop-blur-xl">
      <div className="mx-auto flex max-w-[1600px] flex-wrap items-center gap-x-6 gap-y-3 px-6 py-3">
        <div className="flex items-center gap-3">
          <LogoMark />
          <div className="leading-tight">
            <div className="flex items-center gap-2">
              <span className="text-base font-semibold tracking-[0.16em] text-fg">
                EKATRA
              </span>
              <span className="hidden h-3 w-px bg-line sm:block" />
              <span className="hidden text-[11px] text-fg-dim sm:block">
                Adaptive Multi-Agent Orchestration
              </span>
            </div>
            <div className="mono mt-0.5 text-[9px] uppercase tracking-[0.24em] text-fg-dim">
              Autonomous Software Development · Research Prototype
            </div>
          </div>
        </div>

        <div className="ml-auto flex flex-wrap items-center gap-2.5">
          <StatusIndicator playing={playing} isDemo={isDemo} label={provenanceLabel} />

          <label className="sr-only" htmlFor="scenario-select">
            Scenario
          </label>
          <select
            id="scenario-select"
            value={scenarioId}
            onChange={(e) => setScenarioId(e.target.value)}
            className="mono max-w-[220px] rounded-lg border border-line-soft bg-black/30 px-2.5 py-1.5 text-[11px] text-fg outline-none transition-colors hover:border-accent/40 focus:border-accent/60"
            title={activeScenarioName}
          >
            {scenarios.map((s) => (
              <option key={s.id} value={s.id} className="bg-panel text-fg">
                {s.name}
              </option>
            ))}
          </select>

          <Segmented
            ariaLabel="Data mode"
            value={mode}
            onChange={(v) => setMode(v)}
            options={[
              { value: "demo", label: "Demo", icon: <Sparkles className="h-3 w-3" /> },
              {
                value: "experiment",
                label: "Experiment",
                icon: <FlaskConical className="h-3 w-3" />,
              },
            ]}
          />

          {mode === "experiment" && (
            <Segmented
              ariaLabel="Strategy"
              value={strategy}
              onChange={(v) => setStrategy(v)}
              options={[
                { value: "adaptive", label: "Adaptive" },
                { value: "fixed", label: "Fixed" },
              ]}
            />
          )}

          <button
            onClick={toggle}
            className={cn(
              "mono inline-flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-[11px] uppercase tracking-[0.14em] transition-all",
              playing
                ? "border-amber/50 bg-amber/10 text-amber hover:bg-amber/15"
                : "border-accent/50 bg-accent/15 text-accent hover:bg-accent/25 hover:shadow-[0_0_22px_-8px_rgba(34,211,238,0.7)]",
            )}
          >
            {playing ? (
              <>
                <Pause className="h-3.5 w-3.5" /> Pause
              </>
            ) : (
              <>
                <Play className="h-3.5 w-3.5" />
                {mode === "demo" ? "Run Demo" : "Play Run"}
              </>
            )}
          </button>
        </div>
      </div>
    </header>
  );
}

function StatusIndicator({
  playing,
  isDemo,
  label,
}: {
  playing: boolean;
  isDemo: boolean;
  label: string;
}) {
  return (
    <div className="flex items-center gap-2">
      <Chip tone={isDemo ? "amber" : "violet"}>
        <span
          className={cn(
            "inline-block h-1.5 w-1.5 rounded-full",
            playing ? "animate-pulse bg-cyan-glow" : isDemo ? "bg-amber" : "bg-violet",
          )}
        />
        {label}
      </Chip>
      {playing && <Chip tone="accent">LIVE PLAYBACK</Chip>}
    </div>
  );
}
