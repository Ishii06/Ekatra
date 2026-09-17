import type { ReactNode } from "react";
import type { AdaptiveAction, AgentStatus, Level, RoleKey, TaskStatus } from "@/lib/types";
import { ROLE_LABELS } from "@/lib/types";
import { cn } from "@/lib/cn";

/* ------------------------------------------------------------------ panel */

export function Panel({
  title,
  eyebrow,
  subtitle,
  icon,
  actions,
  children,
  className,
  bodyClassName,
  dense,
}: {
  title?: ReactNode;
  eyebrow?: ReactNode;
  subtitle?: ReactNode;
  icon?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
  dense?: boolean;
}) {
  return (
    <section className={cn("glass rounded-2xl", className)}>
      {(title || eyebrow || actions) && (
        <header className="flex items-start justify-between gap-3 border-b border-line-soft px-4 py-3">
          <div className="min-w-0">
            {eyebrow && (
              <div className="mono text-[10px] uppercase tracking-[0.22em] text-accent/80">
                {eyebrow}
              </div>
            )}
            {title && (
              <h2 className="mt-0.5 flex items-center gap-2 text-sm font-semibold tracking-tight text-fg">
                {icon && <span className="text-accent">{icon}</span>}
                {title}
              </h2>
            )}
            {subtitle && (
              <p className="mt-1 text-xs leading-relaxed text-fg-dim">{subtitle}</p>
            )}
          </div>
          {actions && <div className="shrink-0">{actions}</div>}
        </header>
      )}
      <div className={cn(dense ? "p-3" : "p-4", bodyClassName)}>{children}</div>
    </section>
  );
}

/* ----------------------------------------------------------------- section */

export function SectionHeader({
  index,
  eyebrow,
  title,
  description,
  right,
}: {
  index?: string;
  eyebrow?: string;
  title: string;
  description?: string;
  right?: ReactNode;
}) {
  return (
    <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
      <div>
        <div className="mono flex items-center gap-2 text-[10px] uppercase tracking-[0.28em] text-accent/80">
          {index && <span className="text-fg-dim">{index}</span>}
          {eyebrow}
        </div>
        <h2 className="mt-1 text-lg font-semibold tracking-tight text-fg">{title}</h2>
        {description && (
          <p className="mt-1 max-w-3xl text-sm leading-relaxed text-fg-muted">
            {description}
          </p>
        )}
      </div>
      {right && <div className="shrink-0">{right}</div>}
    </div>
  );
}

/* ------------------------------------------------------------------- chip */

export function Chip({
  children,
  className,
  tone = "neutral",
}: {
  children: ReactNode;
  className?: string;
  tone?: "neutral" | "accent" | "violet" | "amber" | "rose" | "mint";
}) {
  const tones: Record<string, string> = {
    neutral: "border-line-soft bg-white/[0.03] text-fg-muted",
    accent: "border-accent/35 bg-accent/10 text-accent",
    violet: "border-violet/35 bg-violet/10 text-violet",
    amber: "border-amber/35 bg-amber/10 text-amber",
    rose: "border-rose/35 bg-rose/10 text-rose",
    mint: "border-mint/35 bg-mint/10 text-mint",
  };
  return (
    <span
      className={cn(
        "mono inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] uppercase tracking-[0.14em]",
        tones[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}

/* ---------------------------------------------------------------- marking */

export const STATUS_TONE: Record<AgentStatus, string> = {
  CREATED: "text-fg-dim border-line-soft bg-white/[0.03]",
  IDLE: "text-fg-muted border-line-soft bg-white/[0.03]",
  ACTIVE: "text-cyan-glow border-cyan-glow/40 bg-cyan-glow/10",
  COMPLETED: "text-mint border-mint/40 bg-mint/10",
  TERMINATED: "text-rose border-rose/40 bg-rose/10",
};

export function StatusDot({ status }: { status: AgentStatus }) {
  const dot: Record<AgentStatus, string> = {
    CREATED: "bg-fg-dim",
    IDLE: "bg-fg-dim",
    ACTIVE: "bg-cyan-glow",
    COMPLETED: "bg-mint",
    TERMINATED: "bg-rose",
  };
  return (
    <span className="relative inline-flex h-1.5 w-1.5">
      <span className={cn("h-1.5 w-1.5 rounded-full", dot[status])} />
      {status === "ACTIVE" && (
        <span className="ping-soft absolute inset-0 rounded-full bg-cyan-glow" />
      )}
    </span>
  );
}

export const TASK_STATUS_TONE: Record<TaskStatus, string> = {
  PENDING: "border-line-soft bg-white/[0.03] text-fg-dim",
  ASSIGNED: "border-violet/35 bg-violet/10 text-violet",
  RUNNING: "border-cyan-glow/40 bg-cyan-glow/10 text-cyan-glow",
  COMPLETED: "border-mint/35 bg-mint/10 text-mint",
  FAILED: "border-rose/40 bg-rose/10 text-rose",
  RETRY: "border-amber/40 bg-amber/10 text-amber",
};

export const ACTION_TONE: Record<AdaptiveAction, "accent" | "rose" | "amber" | "mint"> = {
  SPAWN: "accent",
  TERMINATE: "rose",
  REASSIGN: "amber",
  PRIORITIZE: "amber",
  CONTINUE: "mint",
};

export function levelTone(level: Level): "mint" | "amber" | "rose" {
  if (level === "HIGH") return "rose";
  if (level === "ELEVATED") return "amber";
  return "mint";
}

export function levelText(level: Level): string {
  if (level === "HIGH") return "text-rose";
  if (level === "ELEVATED") return "text-amber";
  return "text-mint";
}

export function levelStroke(level: Level): string {
  if (level === "HIGH") return "#fb7185";
  if (level === "ELEVATED") return "#fbbf24";
  return "#6ee7b7";
}

export function roleShort(role: RoleKey): string {
  switch (role) {
    case "project_manager":
      return "PM";
    case "architect":
      return "ARCH";
    case "backend":
      return "BACKEND";
    case "frontend":
      return "FRONTEND";
    case "qa":
      return "QA";
    case "security":
      return "SECURITY";
  }
}

export function roleLabel(role: RoleKey): string {
  return ROLE_LABELS[role];
}

/* ------------------------------------------------------------------- gauge */

export function RingGauge({
  score,
  level,
  size = 96,
  label,
  sublabel,
}: {
  score: number;
  level: Level;
  size?: number;
  label?: string;
  sublabel?: string;
}) {
  const clamped = Math.max(0, Math.min(100, score));
  const r = 42;
  const c = 2 * Math.PI * r;
  const offset = c * (1 - clamped / 100);
  const color = levelStroke(level);
  return (
    <div className="relative" style={{ width: size, height: size }}>
      <svg viewBox="0 0 100 100" className="h-full w-full -rotate-90">
        <circle
          cx="50"
          cy="50"
          r={r}
          fill="none"
          stroke="rgba(148,163,184,0.14)"
          strokeWidth="6"
        />
        <circle
          cx="50"
          cy="50"
          r={r}
          fill="none"
          stroke={color}
          strokeWidth="6"
          strokeLinecap="round"
          strokeDasharray={c}
          strokeDashoffset={offset}
          style={{ transition: "stroke-dashoffset 700ms cubic-bezier(0.22,1,0.36,1), stroke 400ms ease" }}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className={cn("mono text-xl font-semibold", levelText(level))}>
          {Math.round(clamped)}
        </span>
        {label && (
          <span className="mono text-[9px] uppercase tracking-[0.18em] text-fg-dim">
            {label}
          </span>
        )}
        {sublabel && (
          <span className="mono text-[9px] uppercase tracking-[0.14em] text-fg-dim">
            {sublabel}
          </span>
        )}
      </div>
    </div>
  );
}

export function MeterBar({
  label,
  value,
  max = 1,
  display,
  tone = "accent",
  unavailable,
}: {
  label: string;
  value: number;
  max?: number;
  display?: string;
  tone?: "accent" | "violet" | "amber" | "rose" | "mint";
  unavailable?: boolean;
}) {
  const ratio = unavailable ? 0 : Math.max(0, Math.min(1, value / max));
  const tones: Record<string, string> = {
    accent: "bg-accent",
    violet: "bg-violet",
    amber: "bg-amber",
    rose: "bg-rose",
    mint: "bg-mint",
  };
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between gap-2">
        <span className="text-[11px] text-fg-muted">{label}</span>
        <span className="mono text-[11px] text-fg">
          {unavailable ? "—" : display ?? value.toFixed(2)}
        </span>
      </div>
      <div className="h-1 overflow-hidden rounded-full bg-white/[0.05]">
        <div
          className={cn(
            "h-full rounded-full transition-all duration-700",
            tones[tone],
            unavailable && "bg-transparent",
          )}
          style={{ width: unavailable ? "0%" : `${ratio * 100}%` }}
        />
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------- stats */

export function Stat({
  label,
  value,
  unit,
  emphasis,
}: {
  label: string;
  value: ReactNode;
  unit?: string;
  emphasis?: boolean;
}) {
  return (
    <div className="rounded-xl border border-line-soft bg-white/[0.02] px-3 py-2.5">
      <div className="mono text-[9px] uppercase tracking-[0.18em] text-fg-dim">
        {label}
      </div>
      <div
        className={cn(
          "mono mt-1 text-base font-semibold",
          emphasis ? "text-accent" : "text-fg",
        )}
      >
        {value}
        {unit && <span className="ml-1 text-[10px] text-fg-dim">{unit}</span>}
      </div>
    </div>
  );
}
