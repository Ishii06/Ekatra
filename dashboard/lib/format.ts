import type { AdaptiveAction, Level, RoleKey, TaskStatus } from "./types";
import { ROLE_LABELS } from "./types";

export const HOUR_MS = 3600 * 1000;

export function fmtTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleTimeString("en-GB", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });
}

export function fmtDuration(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds <= 0) return "—";
  if (seconds < 1) return `${Math.round(seconds * 1000)} ms`;
  if (seconds < 60) return `${seconds.toFixed(1)} s`;
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  return `${m}m ${s}s`;
}

export function fmtPct(ratio: number): string {
  if (!Number.isFinite(ratio)) return "—";
  return `${Math.round(ratio * 100)}%`;
}

export function fmtNumber(n: number): string {
  if (!Number.isFinite(n)) return "—";
  return Number.isInteger(n) ? String(n) : n.toFixed(2);
}

export function priorityLabel(priority: number): string {
  if (priority >= 3) return "HIGH";
  if (priority === 2) return "MED";
  return "LOW";
}

export function levelColor(level: Level): string {
  switch (level) {
    case "HIGH":
      return "text-rose";
    case "ELEVATED":
      return "text-amber";
    default:
      return "text-mint";
  }
}

export function levelTint(level: Level): string {
  switch (level) {
    case "HIGH":
      return "border-rose/40 bg-rose/10 text-rose";
    case "ELEVATED":
      return "border-amber/40 bg-amber/10 text-amber";
    default:
      return "border-mint/40 bg-mint/10 text-mint";
  }
}

export function taskLabel(status: TaskStatus): string {
  return status === "RETRY" ? "FAILED / RETRY" : status;
}

export function roleLabel(role: RoleKey): string {
  return ROLE_LABELS[role];
}

export function actionTone(action: AdaptiveAction): string {
  switch (action) {
    case "SPAWN":
      return "text-accent";
    case "TERMINATE":
      return "text-rose";
    case "REASSIGN":
    case "PRIORITIZE":
      return "text-amber";
    default:
      return "text-mint";
  }
}

export function shortTimestamp(time: string): string {
  // "10:31:04" style from iso or bare.
  const match = time.match(/(\d{2}):(\d{2}):(\d{2})/);
  return match ? `${match[1]}:${match[2]}:${match[3]}` : time;
}