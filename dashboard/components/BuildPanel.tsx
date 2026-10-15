"use client";

import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import {
  AlertTriangle,
  CheckCircle2,
  FileCode2,
  FileText,
  Hammer,
  Loader2,
  Rocket,
  ScrollText,
  X,
} from "lucide-react";
import { useDashboard } from "@/lib/dashboard-context";
import { getBuildFile, type BuildFile, type BuildIssue } from "@/lib/api/builds";
import { cn } from "@/lib/cn";
import { Chip, Panel } from "./ui";

const AREA_TONE: Record<string, "accent" | "violet" | "amber" | "neutral"> = {
  backend: "accent",
  frontend: "violet",
  docs: "amber",
  project: "neutral",
};

function fmtBytes(n: number): string {
  return n < 1024 ? `${n} B` : `${(n / 1024).toFixed(1)} KB`;
}

function fmtElapsed(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return m > 0 ? `${m}m ${s}s` : `${s}s`;
}

function FileViewer({
  buildId,
  file,
  onClose,
}: {
  buildId: string;
  file: BuildFile;
  onClose: () => void;
}) {
  const [content, setContent] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getBuildFile(buildId, file.path)
      .then((f) => {
        if (!cancelled) setContent(f.truncated ? `${f.content}\n\n… (truncated)` : f.content);
      })
      .catch((e: unknown) => {
        if (!cancelled) setError(e instanceof Error ? e.message : "Could not read file");
      });
    return () => {
      cancelled = true;
    };
  }, [buildId, file.path]);

  return (
    <div className="mt-3 overflow-hidden rounded-xl border border-line-soft bg-black/40">
      <div className="flex items-center justify-between gap-2 border-b border-line-soft px-3 py-2">
        <div className="mono truncate text-[11px] text-fg">{file.path}</div>
        <button
          onClick={onClose}
          aria-label="Close file"
          className="rounded-md p-1 text-fg-dim transition-colors hover:text-fg"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      </div>
      <pre className="scroll-thin max-h-[360px] overflow-auto p-3 text-[11px] leading-relaxed text-fg-muted">
        {error ? error : content === null ? "Loading…" : content}
      </pre>
    </div>
  );
}

function FileList({ buildId, files }: { buildId: string; files: BuildFile[] }) {
  const [open, setOpen] = useState<BuildFile | null>(null);
  const [fresh, setFresh] = useState<Set<string>>(new Set());
  const known = useRef<Set<string>>(new Set());

  /* Highlight files that appeared since the previous snapshot. */
  useEffect(() => {
    const incoming = files.filter((f) => !known.current.has(f.path));
    if (known.current.size > 0 && incoming.length > 0) {
      setFresh((prev) => new Set([...prev, ...incoming.map((f) => f.path)]));
      const timer = window.setTimeout(() => {
        setFresh((prev) => {
          const next = new Set(prev);
          incoming.forEach((f) => next.delete(f.path));
          return next;
        });
      }, 4000);
      files.forEach((f) => known.current.add(f.path));
      return () => window.clearTimeout(timer);
    }
    files.forEach((f) => known.current.add(f.path));
  }, [files]);

  return (
    <div>
      {files.length === 0 ? (
        <div className="rounded-xl border border-dashed border-line-soft px-4 py-6 text-center text-[12px] text-fg-dim">
          No files yet — agents write files as their tasks complete.
        </div>
      ) : (
        <ul className="grid gap-1.5 sm:grid-cols-2">
          <AnimatePresence initial={false}>
            {files.map((f) => {
              const code = /\.(py|js|html|css|json)$/.test(f.path);
              return (
                <motion.li
                  key={f.path}
                  layout
                  initial={{ opacity: 0, y: 8, scale: 0.98 }}
                  animate={{ opacity: 1, y: 0, scale: 1 }}
                  transition={{ duration: 0.25 }}
                >
                  <button
                    onClick={() => setOpen(f)}
                    className={cn(
                      "flex w-full items-center gap-2.5 rounded-lg border px-3 py-2 text-left transition-colors hover:border-accent/50",
                      open?.path === f.path
                        ? "border-accent/60 bg-accent/10"
                        : "border-line-soft bg-black/20",
                      fresh.has(f.path) && "border-mint/60 shadow-[0_0_18px_-8px_rgba(52,211,153,0.8)]",
                    )}
                  >
                    {code ? (
                      <FileCode2 className="h-4 w-4 shrink-0 text-fg-dim" />
                    ) : (
                      <FileText className="h-4 w-4 shrink-0 text-fg-dim" />
                    )}
                    <span className="mono min-w-0 flex-1 truncate text-[11px] text-fg">{f.path}</span>
                    {fresh.has(f.path) && <Chip tone="mint">NEW</Chip>}
                    <Chip tone={AREA_TONE[f.area] ?? "neutral"}>{fmtBytes(f.bytes)}</Chip>
                  </button>
                </motion.li>
              );
            })}
          </AnimatePresence>
        </ul>
      )}
      {open && (
        <FileViewer key={open.path} buildId={buildId} file={open} onClose={() => setOpen(null)} />
      )}
    </div>
  );
}

function IssueList({ issues }: { issues: BuildIssue[] }) {
  if (issues.length === 0) {
    return (
      <div className="flex items-center gap-2 text-[12px] text-mint">
        <CheckCircle2 className="h-4 w-4" /> Static validation found no issues.
      </div>
    );
  }
  return (
    <ul className="space-y-1.5">
      {issues.map((i, idx) => (
        <li key={idx} className="flex items-start gap-2 text-[11px] text-fg-muted">
          <Chip tone={i.severity === "high" ? "rose" : i.severity === "medium" ? "amber" : "neutral"}>
            {i.severity.toUpperCase()}
          </Chip>
          <span className="mono shrink-0 text-fg">{i.file}</span>
          <span className="min-w-0">{i.description}</span>
        </li>
      ))}
    </ul>
  );
}

export function BuildPanel() {
  const {
    buildDescription,
    setBuildDescription,
    build,
    buildRunning,
    buildStarting,
    startBuild,
    liveError,
    strategy,
  } = useDashboard();

  const logRef = useRef<HTMLDivElement>(null);
  const logLength = build?.log.length ?? 0;
  useEffect(() => {
    const el = logRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [logLength]);

  const tasks = build?.tasks ?? [];
  const done = tasks.filter((t) => t.status === "COMPLETED").length;
  const planning = buildRunning && tasks.length === 0;
  const finished = build && build.status !== "running";

  const statusChip = !build ? null : planning ? (
    <Chip tone="amber">PLANNING</Chip>
  ) : buildRunning ? (
    <Chip tone="accent">
      BUILDING · {done}/{tasks.length}
    </Chip>
  ) : build.status === "failed" ? (
    <Chip tone="rose">FAILED</Chip>
  ) : build.success ? (
    <Chip tone="mint">COMPLETED</Chip>
  ) : (
    <Chip tone="amber">COMPLETED WITH ISSUES</Chip>
  );

  return (
    <div className="space-y-4">
      <Panel
        eyebrow="Real build"
        title="Build a website with Gemini-driven agents"
        icon={<Hammer className="h-4 w-4" />}
        subtitle="Describe a site. The Project Manager plans it, agents write real files in parallel, QA and Security review it — orchestrated by the strategy selected above."
        actions={statusChip}
        bodyClassName="p-4"
      >
        <label htmlFor="build-description" className="sr-only">
          Website description
        </label>
        <textarea
          id="build-description"
          value={buildDescription}
          onChange={(e) => setBuildDescription(e.target.value)}
          disabled={buildRunning}
          rows={3}
          maxLength={600}
          placeholder="e.g. A bakery website with a menu, online ordering and an order tracker"
          className="w-full resize-none rounded-xl border border-line-soft bg-black/30 px-3 py-2.5 text-[13px] text-fg outline-none transition-colors placeholder:text-fg-dim focus:border-accent/60 disabled:opacity-60"
        />
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <button
            onClick={startBuild}
            disabled={buildRunning || buildStarting}
            className="mono inline-flex items-center gap-2 rounded-lg border border-accent/50 bg-accent/15 px-4 py-2 text-[11px] uppercase tracking-[0.14em] text-accent transition-all hover:bg-accent/25 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {buildRunning || buildStarting ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Rocket className="h-3.5 w-3.5" />
            )}
            {buildStarting ? "Starting…" : buildRunning ? "Building…" : "Start build"}
          </button>
          <span className="mono text-[10px] uppercase tracking-[0.16em] text-fg-dim">
            Strategy · {strategy}
          </span>
          {build && (
            <span className="mono text-[10px] uppercase tracking-[0.16em] text-fg-dim">
              {fmtElapsed(build.elapsed_seconds)} elapsed
              {build.plan_source && ` · plan: ${build.plan_source.startsWith("llm") ? "Gemini" : "fallback"}`}
            </span>
          )}
        </div>
        {liveError && (
          <div className="mt-3 flex items-start gap-2 rounded-lg border border-rose/40 bg-rose/10 px-3 py-2 text-[12px] text-rose">
            <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
            <span>{liveError}</span>
          </div>
        )}
        {build?.plan_source.startsWith("fallback") && (
          <div className="mt-3 text-[11px] text-amber">
            Gemini&apos;s plan was unusable ({build.plan_source.replace("fallback: ", "")}); the built-in
            7-task plan is being used.
          </div>
        )}
      </Panel>

      {build && (
        <div className="grid gap-4 xl:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
          <Panel
            eyebrow="Output"
            title={`Generated files (${build.files.length})`}
            icon={<FileCode2 className="h-4 w-4" />}
            subtitle="Files appear as agents finish their tasks. Click one to read it."
            bodyClassName="p-4"
          >
            <FileList key={build.run_id} buildId={build.run_id} files={build.files} />
            {finished && (
              <div className="mt-4 space-y-3 border-t border-line-soft pt-4">
                <div>
                  <div className="mono mb-1.5 text-[9px] uppercase tracking-[0.2em] text-accent/80">
                    Validation
                  </div>
                  <IssueList issues={build.final_issues} />
                </div>
                <div>
                  <div className="mono mb-1.5 text-[9px] uppercase tracking-[0.2em] text-accent/80">
                    Run it
                  </div>
                  <pre className="scroll-thin overflow-x-auto rounded-lg border border-line-soft bg-black/40 p-3 text-[11px] text-fg-muted">
                    {`cd "${build.out_dir}"\npip install -r requirements.txt\nuvicorn backend.main:app --reload`}
                  </pre>
                </div>
              </div>
            )}
          </Panel>

          <Panel
            eyebrow="Activity"
            title="Agent activity log"
            icon={<ScrollText className="h-4 w-4" />}
            subtitle="Task starts and finishes, retries and controller decisions, as they happen."
            bodyClassName="p-3"
          >
            <div
              ref={logRef}
              className="scroll-thin mono max-h-[420px] space-y-0.5 overflow-y-auto pr-1 text-[10.5px] leading-relaxed text-fg-muted"
            >
              {build.log.map((line, i) => (
                <div
                  key={i}
                  className={cn(
                    "whitespace-pre-wrap break-words",
                    line.includes("FAILED") && "text-rose",
                    line.includes("controller") && "text-accent",
                    line.includes("finished") && "text-mint",
                  )}
                >
                  {line}
                </div>
              ))}
              {buildRunning && (
                <div className="flex items-center gap-1.5 text-fg-dim">
                  <Loader2 className="h-3 w-3 animate-spin" /> working…
                </div>
              )}
            </div>
          </Panel>
        </div>
      )}
    </div>
  );
}
