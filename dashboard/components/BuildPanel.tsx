"use client";

import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import {
  AlertTriangle,
  CheckCircle2,
  FileCode2,
  FileText,
  Hammer,
  ExternalLink,
  Globe,
  Loader2,
  FlaskConical,
  Play,
  Rocket,
  Square,
  ScrollText,
  Wrench,
  X,
} from "lucide-react";
import { useDashboard } from "@/lib/dashboard-context";
import {
  getBuildFile,
  getSiteStatus,
  launchSite,
  runDemo,
  runTests,
  stopSite,
  type BuildFile,
  type BuildIssue,
  type BuildStateResponse,
  type CommandResult,
} from "@/lib/api/builds";
import { cn } from "@/lib/cn";
import { Chip, Panel } from "./ui";

const AREA_TONE: Record<string, "accent" | "violet" | "amber" | "mint" | "neutral"> = {
  backend: "accent",
  frontend: "violet",
  source: "accent",
  tests: "mint",
  docs: "amber",
  data: "neutral",
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


function SitePreview({ build }: { build: BuildStateResponse }) {
  const buildId = build.run_id;
  const isApi = build.runnable === "api";
  const [site, setSite] = useState<{ url: string; docs: string | null } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const adopt = (s: { url: string | null; docs_url?: string | null }) =>
    setSite(s.url ? { url: s.url, docs: s.docs_url ?? null } : null);

  /* Re-attach to a site that is already running for this build. */
  useEffect(() => {
    let cancelled = false;
    getSiteStatus(buildId)
      .then((s) => {
        if (!cancelled) adopt(s);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [buildId]);

  async function run() {
    setBusy(true);
    setError(null);
    try {
      adopt(await launchSite(buildId));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not start the site");
    } finally {
      setBusy(false);
    }
  }

  async function stop() {
    setBusy(true);
    try {
      await stopSite(buildId);
      setSite(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not stop the site");
    } finally {
      setBusy(false);
    }
  }

  const shown = site ? (isApi && site.docs ? site.docs : site.url) : null;

  return (
    <Panel
      eyebrow="Result"
      title={isApi ? "Running API service" : "Final website"}
      icon={<Globe className="h-4 w-4" />}
      subtitle={
        isApi
          ? "Starts the generated API on your machine (localhost only) and shows its interactive documentation. This executes the generated code, so it starts only when you press Run."
          : "Runs the generated backend on your machine (localhost only) and shows the site it serves. This executes the generated code, so it starts only when you press Run."
      }
      actions={site ? <Chip tone="mint">RUNNING</Chip> : <Chip tone="neutral">STOPPED</Chip>}
      bodyClassName="p-4"
    >
      <div className="flex flex-wrap items-center gap-3">
        {site && shown ? (
          <>
            <a
              href={shown}
              target="_blank"
              rel="noreferrer"
              className="mono inline-flex items-center gap-2 rounded-lg border border-accent/50 bg-accent/15 px-3 py-2 text-[11px] uppercase tracking-[0.14em] text-accent hover:bg-accent/25"
            >
              <ExternalLink className="h-3.5 w-3.5" /> {isApi ? "Open API docs" : "Open in new tab"}
            </a>
            <button
              onClick={stop}
              disabled={busy}
              className="mono inline-flex items-center gap-2 rounded-lg border border-rose/40 bg-rose/10 px-3 py-2 text-[11px] uppercase tracking-[0.14em] text-rose hover:bg-rose/15 disabled:opacity-50"
            >
              <Square className="h-3.5 w-3.5" /> {isApi ? "Stop service" : "Stop site"}
            </button>
            <span className="mono text-[10px] text-fg-dim">{site.url}</span>
          </>
        ) : (
          <button
            onClick={run}
            disabled={busy}
            className="mono inline-flex items-center gap-2 rounded-lg border border-accent/50 bg-accent/15 px-4 py-2 text-[11px] uppercase tracking-[0.14em] text-accent hover:bg-accent/25 disabled:opacity-50"
          >
            {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Rocket className="h-3.5 w-3.5" />}
            {busy ? "Starting…" : isApi ? "Run service" : "Run site"}
          </button>
        )}
      </div>
      {error && (
        <pre className="scroll-thin mt-3 max-h-40 overflow-auto whitespace-pre-wrap rounded-lg border border-rose/40 bg-rose/10 p-3 text-[11px] text-rose">
          {error}
        </pre>
      )}
      {shown && (
        <iframe
          key={shown}
          src={shown}
          title={isApi ? "Generated API documentation" : "Generated website"}
          className="mt-4 h-[560px] w-full rounded-xl border border-line-soft bg-white"
        />
      )}
    </Panel>
  );
}

function ResultBlock({ result }: { result: CommandResult }) {
  return (
    <div className="mt-3 overflow-hidden rounded-xl border border-line-soft bg-black/40">
      <div className="flex items-center justify-between gap-2 border-b border-line-soft px-3 py-2">
        <div className="mono truncate text-[11px] text-fg">{result.command}</div>
        <Chip tone={result.ok ? "mint" : "rose"}>
          {result.ok ? "PASSED" : result.exit_code === null ? "TIMED OUT" : `EXIT ${result.exit_code}`}
        </Chip>
      </div>
      <pre className="scroll-thin max-h-[320px] overflow-auto whitespace-pre-wrap p-3 text-[11px] leading-relaxed text-fg-muted">
        {result.output || "(no output)"}
      </pre>
    </div>
  );
}

function ProjectChecks({ build }: { build: BuildStateResponse }) {
  const buildId = build.run_id;
  const [busy, setBusy] = useState<"tests" | "demo" | null>(null);
  const [results, setResults] = useState<CommandResult[]>([]);
  const [error, setError] = useState<string | null>(null);

  async function go(kind: "tests" | "demo") {
    setBusy(kind);
    setError(null);
    try {
      setResults(kind === "tests" ? [await runTests(buildId)] : (await runDemo(buildId)).results);
    } catch (e) {
      setResults([]);
      setError(e instanceof Error ? e.message : "Could not run the command");
    } finally {
      setBusy(null);
    }
  }

  const button =
    "mono inline-flex items-center gap-2 rounded-lg border border-accent/50 bg-accent/15 px-4 py-2 text-[11px] uppercase tracking-[0.14em] text-accent hover:bg-accent/25 disabled:opacity-50";

  return (
    <Panel
      eyebrow="Result"
      title={`Run the ${build.project_label.toLowerCase()}`}
      icon={<FlaskConical className="h-4 w-4" />}
      subtitle="Runs the generated project's own tests and demo command on your machine. This executes the generated code, so it starts only when you press a button."
      bodyClassName="p-4"
    >
      <div className="flex flex-wrap items-center gap-3">
        <button onClick={() => go("tests")} disabled={busy !== null} className={button}>
          {busy === "tests" ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <FlaskConical className="h-3.5 w-3.5" />}
          Run tests
        </button>
        <button onClick={() => go("demo")} disabled={busy !== null} className={button}>
          {busy === "demo" ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Play className="h-3.5 w-3.5" />}
          Run demo
        </button>
      </div>
      {error && (
        <div className="mt-3 rounded-lg border border-rose/40 bg-rose/10 px-3 py-2 text-[12px] text-rose">{error}</div>
      )}
      {results.map((r, i) => (
        <ResultBlock key={`${r.command}-${i}`} result={r} />
      ))}
    </Panel>
  );
}

const CHANGE_EXAMPLES = [
  "Add a dark mode toggle",
  "The list command should also show the due date",
  "Validate that the email field really looks like an email address",
];

function ChangePanel({ build }: { build: BuildStateResponse }) {
  const { changeBuild } = useDashboard();
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const hasIssues = build.final_issues.length > 0;

  async function apply(request?: string) {
    setBusy(true);
    await changeBuild(request);
    if (request) setText("");
    setBusy(false);
  }

  const button =
    "mono inline-flex items-center gap-2 rounded-lg border px-4 py-2 text-[11px] uppercase tracking-[0.14em] transition-all disabled:cursor-not-allowed disabled:opacity-50";

  return (
    <Panel
      eyebrow="Change"
      title="Change or fix this project"
      icon={<Wrench className="h-4 w-4" />}
      subtitle="Describe what should be different. The Project Manager plans the smallest change, agents rewrite only the files involved, QA updates the tests, and the checks run again — a change that breaks something is repaired or reported."
      actions={build.changes.length > 0 ? <Chip tone="violet">{build.changes.length} APPLIED</Chip> : undefined}
      bodyClassName="p-4"
    >
      <label htmlFor="change-request" className="sr-only">
        Change request
      </label>
      <textarea
        id="change-request"
        value={text}
        onChange={(e) => setText(e.target.value)}
        disabled={busy}
        rows={2}
        maxLength={600}
        placeholder={`e.g. ${CHANGE_EXAMPLES[build.changes.length % CHANGE_EXAMPLES.length]}`}
        className="w-full resize-none rounded-xl border border-line-soft bg-black/30 px-3 py-2.5 text-[13px] text-fg outline-none transition-colors placeholder:text-fg-dim focus:border-accent/60 disabled:opacity-60"
      />
      <div className="mt-3 flex flex-wrap items-center gap-3">
        <button
          onClick={() => apply(text)}
          disabled={busy || text.trim().length < 5}
          className={cn(button, "border-accent/50 bg-accent/15 text-accent hover:bg-accent/25")}
        >
          {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Wrench className="h-3.5 w-3.5" />}
          Apply change
        </button>
        {hasIssues && (
          <button
            onClick={() => apply()}
            disabled={busy}
            className={cn(button, "border-amber/50 bg-amber/10 text-amber hover:bg-amber/15")}
          >
            <AlertTriangle className="h-3.5 w-3.5" />
            Fix {build.final_issues.length} remaining issue{build.final_issues.length === 1 ? "" : "s"}
          </button>
        )}
        <span className="text-[11px] text-fg-dim">{text.length}/600</span>
      </div>
      {build.change_error && (
        <div className="mt-3 flex items-start gap-2 rounded-lg border border-amber/40 bg-amber/10 px-3 py-2 text-[12px] text-amber">
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          <span>
            The change was not applied: {build.change_error} The project is as it was before.
          </span>
        </div>
      )}
      {build.changes.length > 0 && (
        <div className="mt-4 border-t border-line-soft pt-3">
          <div className="mono mb-1.5 text-[9px] uppercase tracking-[0.2em] text-accent/80">Changes so far</div>
          <ol className="list-decimal space-y-1 pl-5 text-[12px] text-fg-muted">
            {build.changes.map((c, i) => (
              <li key={`${c.at}-${i}`}>{c.request}</li>
            ))}
          </ol>
        </div>
      )}
    </Panel>
  );
}

/** The commands a person would run themselves, per project type. */
function runInstructions(build: BuildStateResponse): string {
  const pkg = build.package || "app";
  const cd = `cd "${build.out_dir}"`;
  switch (build.project_type) {
    case "web":
      return `${cd}\npip install -r requirements.txt\nuvicorn backend.main:app --reload`;
    case "api":
      return `${cd}\npip install -r requirements.txt\nuvicorn ${pkg}.main:app --reload`;
    case "library":
      return `${cd}\npip install -r requirements.txt\npython -m pytest`;
    case "automation":
      return `${cd}\npython -m ${pkg} --target <folder>          # dry run\npython -m ${pkg} --target <folder> --apply`;
    default:
      return `${cd}\npython -m ${pkg}${build.project_type === "cli" ? " --help" : ""}\npython -m pytest`;
  }
}

export function BuildPanel() {
  const {
    buildDescription,
    setBuildDescription,
    profiles,
    projectType,
    setProjectType,
    build,
    buildRunning,
    buildStarting,
    startBuild,
    liveError,
    strategy,
  } = useDashboard();
  const selectedProfile = profiles.find((p) => p.key === projectType);

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
        title="Build software with Gemini-driven agents"
        icon={<Hammer className="h-4 w-4" />}
        subtitle="Pick a project type and describe it. The Project Manager plans it, agents write real files in parallel, QA writes and runs tests, Security reviews — orchestrated by the strategy selected above."
        actions={statusChip}
        bodyClassName="p-4"
      >
        <div className="mb-3" role="radiogroup" aria-label="Project type">
          <div className="mono mb-1.5 text-[9px] uppercase tracking-[0.2em] text-accent/80">Project type</div>
          <div className="flex flex-wrap gap-1.5">
            {(profiles.length > 0 ? profiles : [{ key: "web", label: "Web app" }]).map((p) => (
              <button
                key={p.key}
                role="radio"
                aria-checked={projectType === p.key}
                disabled={buildRunning}
                onClick={() => setProjectType(p.key)}
                className={cn(
                  "mono rounded-lg border px-2.5 py-1.5 text-[10px] uppercase tracking-[0.12em] transition-colors disabled:opacity-60",
                  projectType === p.key
                    ? "border-accent/60 bg-accent/15 text-accent"
                    : "border-line-soft text-fg-dim hover:border-accent/40 hover:text-fg-muted",
                )}
              >
                {p.label}
              </button>
            ))}
          </div>
          {selectedProfile && (
            <p className="mt-2 text-[12px] text-fg-dim">
              {selectedProfile.summary}{" "}
              <button
                onClick={() => setBuildDescription(selectedProfile.example)}
                disabled={buildRunning}
                className="text-accent underline-offset-2 hover:underline disabled:opacity-50"
              >
                Use an example
              </button>
            </p>
          )}
        </div>
        <label htmlFor="build-description" className="sr-only">
          Project description
        </label>
        <textarea
          id="build-description"
          value={buildDescription}
          onChange={(e) => setBuildDescription(e.target.value)}
          disabled={buildRunning}
          rows={3}
          maxLength={600}
          placeholder="Describe what the software should do, with a few concrete features"
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
                    {runInstructions(build)}
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

      {finished && build.status === "completed" && (
        <ChangePanel key={`${build.run_id}-${build.changes.length}`} build={build} />
      )}
      {finished && build.status === "completed" && build.runnable && (
        <SitePreview key={build.run_id} build={build} />
      )}
      {finished && build.status === "completed" && build.has_tests && (
        <ProjectChecks key={build.run_id} build={build} />
      )}
    </div>
  );
}
