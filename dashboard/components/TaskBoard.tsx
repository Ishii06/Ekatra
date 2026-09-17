"use client";

import { AnimatePresence, LayoutGroup, motion } from "framer-motion";
import { ListChecks } from "lucide-react";
import type { Task, TaskStatus } from "@/lib/types";
import { useDashboard, ALL_TASK_STATUSES } from "@/lib/dashboard-context";
import { cn } from "@/lib/cn";
import { priorityLabel, taskLabel } from "@/lib/format";
import { Chip, Panel, TASK_STATUS_TONE, roleShort } from "./ui";

const COLUMNS: { key: string; label: string; statuses: TaskStatus[] }[] = [
  { key: "pending", label: "Pending", statuses: ["PENDING"] },
  { key: "assigned", label: "Assigned", statuses: ["ASSIGNED"] },
  { key: "running", label: "Running", statuses: ["RUNNING"] },
  { key: "completed", label: "Completed", statuses: ["COMPLETED"] },
  { key: "failed", label: "Failed / Retry", statuses: ["FAILED", "RETRY"] },
];

function priorityTone(priority: number): "rose" | "amber" | "neutral" {
  if (priority >= 3) return "rose";
  if (priority === 2) return "amber";
  return "neutral";
}

function TaskCard({
  task,
  expanded,
  onToggle,
}: {
  task: Task;
  expanded: boolean;
  onToggle: () => void;
}) {
  const running = task.status === "RUNNING";
  const completed = task.status === "COMPLETED";
  return (
    <motion.button
      type="button"
      layoutId={`task-${task.id}`}
      layout
      initial={{ opacity: 0, scale: 0.96 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 0.96 }}
      transition={{ type: "spring", stiffness: 380, damping: 30 }}
      onClick={onToggle}
      className={cn(
        "relative w-full overflow-hidden rounded-lg border px-2.5 py-2 text-left transition-colors",
        running
          ? "border-cyan-glow/40 bg-cyan-glow/[0.05]"
          : completed
            ? "border-mint/25 bg-mint/[0.04]"
            : "border-line-soft bg-white/[0.02] hover:border-accent/35",
      )}
    >
      {running && (
        <span className="pointer-events-none absolute inset-x-0 top-0 h-px shimmer" />
      )}
      <div className="flex items-center justify-between gap-2">
        <span className="mono text-[11px] font-semibold text-fg">{task.id}</span>
        <Chip tone={priorityTone(task.priority)}>{priorityLabel(task.priority)}</Chip>
      </div>
      <p className="mt-1 line-clamp-2 text-[11px] leading-snug text-fg-muted">
        {task.description || "—"}
      </p>
      <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
        <span className="mono rounded border border-line-soft px-1.5 py-[1px] text-[8px] uppercase tracking-[0.12em] text-fg-dim">
          {roleShort(task.role)}
        </span>
        <span className="mono text-[9px] text-fg-dim">C{task.complexity}</span>
        {task.retryCount > 0 && (
          <span className="mono text-[9px] text-amber">retry ×{task.retryCount}</span>
        )}
        <span className="mono ml-auto max-w-[78px] truncate text-[9px] text-fg-dim">
          {task.assignedAgent ?? "unassigned"}
        </span>
      </div>

      <AnimatePresence initial={false}>
        {expanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.22 }}
            className="overflow-hidden"
          >
            <div className="mt-2 space-y-1 border-t border-line-soft pt-2">
              <Detail label="Status" value={taskLabel(task.status)} />
              <Detail label="Risk" value={`${task.risk}`} />
              <Detail
                label="Dependencies"
                value={task.dependencies.length ? task.dependencies.join(", ") : "none"}
              />
              <Detail label="Created" value={task.createdAt} />
              {task.startedAt && <Detail label="Started" value={task.startedAt} />}
              {task.completedAt && <Detail label="Completed" value={task.completedAt} />}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.button>
  );
}

function Detail({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-start justify-between gap-2">
      <span className="mono text-[8px] uppercase tracking-[0.14em] text-fg-dim">
        {label}
      </span>
      <span className="mono max-w-[140px] truncate text-right text-[9px] text-fg-muted">
        {value}
      </span>
    </div>
  );
}

export function TaskBoard() {
  const {
    frame,
    visibleStatuses,
    toggleStatus,
    showAllStatuses,
    selectedTaskId,
    selectTask,
  } = useDashboard();

  const tasks = frame?.tasks ?? [];
  const allVisible = visibleStatuses.length === ALL_TASK_STATUSES.length;

  return (
    <Panel
      eyebrow="Task System"
      title="Task Board"
      icon={<ListChecks className="h-4 w-4" />}
      subtitle="Deterministic task state — PENDING → ASSIGNED → RUNNING → COMPLETED, with a FAILED → RETRY path."
      actions={
        <button
          onClick={showAllStatuses}
          className={cn(
            "mono rounded-md border px-2 py-1 text-[9px] uppercase tracking-[0.14em] transition-colors",
            allVisible
              ? "border-line-soft text-fg-dim"
              : "border-accent/40 text-accent hover:bg-accent/10",
          )}
        >
          All
        </button>
      }
      bodyClassName="p-4"
    >
      <div className="mb-3 flex flex-wrap items-center gap-1.5">
        {ALL_TASK_STATUSES.map((status) => {
          const on = visibleStatuses.includes(status);
          return (
            <button
              key={status}
              onClick={() => toggleStatus(status)}
              className={cn(
                "mono rounded-md border px-2 py-1 text-[9px] uppercase tracking-[0.12em] transition-all",
                on ? TASK_STATUS_TONE[status] : "border-line-soft text-fg-dim/60",
              )}
            >
              {taskLabel(status)}
            </button>
          );
        })}
      </div>

      <LayoutGroup>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-5">
          {COLUMNS.map((col) => {
            const columnVisible = col.statuses.some((s) => visibleStatuses.includes(s));
            const colTasks = tasks.filter(
              (t) => col.statuses.includes(t.status) && visibleStatuses.includes(t.status),
            );
            if (!columnVisible) return null;
            return (
              <div key={col.key} className="flex min-h-[80px] flex-col">
                <div className="mb-2 flex items-center justify-between">
                  <span className="mono text-[9px] uppercase tracking-[0.18em] text-fg-dim">
                    {col.label}
                  </span>
                  <span className="mono text-[9px] text-fg-dim">{colTasks.length}</span>
                </div>
                <div className="space-y-2">
                  <AnimatePresence initial={false}>
                    {colTasks.map((task) => (
                      <TaskCard
                        key={task.id}
                        task={task}
                        expanded={selectedTaskId === task.id}
                        onToggle={() =>
                          selectTask(selectedTaskId === task.id ? null : task.id)
                        }
                      />
                    ))}
                  </AnimatePresence>
                  {colTasks.length === 0 && (
                    <div className="rounded-lg border border-dashed border-line-soft/70 py-3 text-center">
                      <span className="mono text-[9px] text-fg-dim/60">empty</span>
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </LayoutGroup>
      <p className="mono mt-3 border-t border-line-soft pt-2.5 text-[9px] uppercase tracking-[0.14em] text-fg-dim">
        Click a task to expand dependencies and timestamps
      </p>
    </Panel>
  );
}
