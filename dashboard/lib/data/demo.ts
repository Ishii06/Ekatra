import type {
  AdaptiveAction,
  Agent,
  AgentStatus,
  FlowStage,
  Level,
  OrgSnapshot,
  RoleKey,
  Task,
  TaskStatus,
  TimelineEvent,
  TimelineKind,
} from "../types";
import { DEMO_LABEL } from "./scenarios";

/**
 * Demo beat scripts — deterministic presentation fixtures.
 *
 * Each snapshot is DATA authored for the walkthrough; the reducer below only
 * applies the declared deltas (it never computes orchestration decisions).
 * Every frame is flagged `isDemo: true` and the UI labels it DEMO MODE.
 */

type PartialBy<T, K extends keyof T> = Partial<T> & Pick<T, K>;

export interface TaskInput extends Partial<Omit<Task, "id" | "role">> {
  id: string;
  role: RoleKey;
}

export interface AgentInput {
  agentId: string;
  role: RoleKey;
  status: AgentStatus;
  currentTask?: string | null;
  tasksCompleted?: number;
  tasksFailed?: number;
  createdAt?: string;
}

export interface DecisionInput {
  action: AdaptiveAction;
  cycle: number;
  workloadScore: number;
  riskScore: number;
  workloadLevel: Level;
  riskLevel: Level;
  reason: string;
  affectedRole: RoleKey | null;
  affectedAgent: string | null;
  before: { activeForRole: number; queue: number; workload: number; risk: number };
  after: { activeForRole: number; queue: number; workload: number; risk: number };
}

export interface Beat {
  title: string;
  projectState: string;
  flowStage: FlowStage | null;
  narrative?: string;
  addTasks?: TaskInput[];
  setTasks?: Record<string, PartialBy<TaskInput, "id">>;
  agentStatus?: Record<string, AgentStatus>;
  spawnAgents?: AgentInput[];
  workload?: Partial<OrgSnapshot["workload"]>;
  risk?: Partial<OrgSnapshot["risk"]>;
  decision?: DecisionInput | null;
  events: { kind: TimelineKind; title: string; detail?: string }[];
  activeAgentIds?: string[];
}

export interface WorkloadBase {
  queueLength: number;
  complexity: number;
  executionDelay: number;
  failureRate: number;
  score: number;
  level: Level;
}

export interface RiskBase {
  securityFindings: number;
  authIssues: number;
  suspiciousCode: number;
  failedChecks: number;
  repeatedFailures: number;
  highRiskTasks: number;
  score: number;
  level: Level;
}

export const FLOW_STAGES: FlowStage[] = [
  "OBSERVE",
  "ANALYZE",
  "DECIDE",
  "ALLOCATE",
  "EXECUTE",
  "EVALUATE",
  "ADAPT",
];

// ---------------------------------------------------------------------------
// reducer
// ---------------------------------------------------------------------------

function makeAgent(input: AgentInput, created: string): Agent {
  const baselineId = input.createdAt;
  return {
    agentId: input.agentId,
    role: input.role,
    status: input.status,
    currentTask: input.currentTask ?? null,
    spawned: Boolean(baselineId == null && input.agentId.split("-")[1] !== "1"),
    meta: {
      tasksCompleted: input.tasksCompleted ?? 0,
      tasksFailed: input.tasksFailed ?? 0,
      createdAt: input.createdAt ?? created,
      workload: 0,
      risk: 0,
    },
    lifecycle: [input.status],
  };
}

export function isSpawnedId(agentId: string): boolean {
  const [, n] = agentId.split("-");
  const base = agentId.replace(/-\d+$/, "");
  return base !== "PM" && base !== "ARCH" && Number(n) > 1;
}

export function tickTimestamp(baseIso: string, offsetSeconds: number): string {
  const d = new Date(baseIso);
  d.setSeconds(d.getSeconds() + offsetSeconds);
  return d.toISOString();
}

function buildFrames(
  scenarioName: string,
  baseIsos: string,
  beats: Beat[],
  baseWorkload: WorkloadBase,
  baseRisk: RiskBase,
): OrgSnapshot[] {
  const T0 = baseIsos;
  let t = new Date(T0).getTime();

  const tasksById = new Map<string, Task>();
  const agentsById = new Map<string, Agent>();
  const decisions: OrgSnapshot["decisions"] = [];
  const events: TimelineEvent[] = [];
  let spawnCount = 0;
  let terminationCount = 0;
  let reassignCount = 0;
  let peakActive = 0;
  let wallet: { loopBacklog: number } = { loopBacklog: 0 };

  void wallet;

  const frames: OrgSnapshot[] = [];

  let clockOffset = 0;

  const emits = (kind: TimelineKind, title: string, detail?: string) => {
    events.push({
      id: `evt-${events.length + 1}`,
      time: new Date(t).toISOString(),
      kind,
      title,
      detail,
    });
  };

  beats.forEach((beat, i) => {
    clockOffset = i + 1;
    t = new Date(T0).getTime() + clockOffset * 2800;

    if (beat.spawnAgents) {
      for (const a of beat.spawnAgents) {
        agentsById.set(a.agentId, makeAgent(a, new Date(t).toISOString()));
        spawnCount += 1;
      }
    }
    if (beat.agentStatus) {
      for (const [id, status] of Object.entries(beat.agentStatus)) {
        const agent = agentsById.get(id);
        if (!agent) continue;
        agent.status = status;
        if (agent.lifecycle[agent.lifecycle.length - 1] !== status) {
          agent.lifecycle.push(status);
        }
      }
    }
    if (beat.addTasks) {
      for (const taskInput of beat.addTasks) {
        tasksById.set(taskInput.id, {
          id: taskInput.id,
          role: taskInput.role,
          description: taskInput.description ?? "",
          priority: taskInput.priority ?? 2,
          complexity: taskInput.complexity ?? 3,
          risk: taskInput.risk ?? 20,
          status: taskInput.status ?? "PENDING",
          assignedAgent: taskInput.assignedAgent ?? null,
          retryCount: taskInput.retryCount ?? 0,
          dependencies: taskInput.dependencies ?? [],
          createdAt: taskInput.createdAt ?? new Date(t).toISOString(),
          startedAt: taskInput.startedAt ?? null,
          completedAt: taskInput.completedAt ?? null,
        });
      }
    }
    if (beat.setTasks) {
      for (const patch of Object.values(beat.setTasks)) {
        const current = tasksById.get(patch.id);
        if (!current) continue;
        tasksById.set(patch.id, { ...current, ...patch, id: patch.id });
      }
    }

    for (const e of beat.events) {
      emits(e.kind, e.title, e.detail);
    }

    // A decision declared by this beat must be visible in this beat's frame
    // (the DECIDE stage is the presentation focus of the whole walkthrough).
    if (beat.decision) {
      decisions.push({ ...beat.decision, timestamp: new Date(t).toISOString() });
    }

    const snapshot = buildSnapshot({
      scenarioName,
      agents: [...agentsById.values()],
      tasks: [...tasksById.values()],
      workload: { ...baseWorkload, ...beat.workload },
      risk: { ...baseRisk, ...beat.risk },
      flowStage: beat.flowStage,
      justSpawned: beat.spawnAgents?.[0]?.agentId ?? null,
      events: [...events],
      decisions,
      projectState: beat.projectState,
      narrative: beat.narrative,
      title: beat.title,
      tick: new Date(t).toISOString(),
      cycle: decisions.length > 0 ? decisions[decisions.length - 1].cycle : 0,
      spawnCount,
      terminationCount,
      reassignCount,
      peakActive,
    });

    // Finalize this frame's derived numbers.
    peakActive = snapshot.metrics.peakActiveAgents;
    frames.push(snapshot);
  });

  return frames;
}

function buildSnapshot(args: {
  scenarioName: string;
  agents: Agent[];
  tasks: Task[];
  workload: WorkloadBase;
  risk: RiskBase;
  flowStage: FlowStage | null;
  justSpawned: string | null;
  events: TimelineEvent[];
  decisions: OrgSnapshot["decisions"];
  projectState: string;
  narrative?: string;
  title?: string;
  tick: string;
  cycle: number;
  spawnCount: number;
  terminationCount: number;
  reassignCount: number;
  peakActive: number;
}): OrgSnapshot {
  const { scenarioName, agents, tasks, workload, risk, flowStage, justSpawned, events, decisions, projectState, narrative, tick, spawnCount, terminationCount, reassignCount } = args;

  const completed = tasks.filter((t) => t.status === "COMPLETED");
  const failed = tasks.filter((t) => t.status === "FAILED" || t.status === "RETRY");
  const queueLen = tasks.filter((t) =>
    ["PENDING", "ASSIGNED", "RUNNING", "RETRY"].includes(t.status),
  ).length;
  const running = tasks.filter((t) => t.status === "RUNNING");
  const active = agents.filter((a) => a.status === "ACTIVE");
  const activeCount = active.length;
  const peak = Math.max(args.peakActive, activeCount + running.length);

  const util = agents.length > 0
    ? active.length / agents.length
    : 0;

  const latestDecision = decisions[decisions.length - 1] ?? null;

  let totalWaitSeconds = 0;
  for (const task of tasks) {
    if (!task.startedAt) continue;
    const created = new Date(task.createdAt).getTime();
    const started = new Date(task.startedAt).getTime();
    if (Number.isFinite(created) && Number.isFinite(started)) {
      totalWaitSeconds += Math.max(0, (started - created) / 1000);
    }
  }

  let totalExecSeconds = 0;
  for (const task of completed) {
    if (!task.startedAt || !task.completedAt) continue;
    const s = new Date(task.startedAt).getTime();
    const e = new Date(task.completedAt).getTime();
    if (Number.isFinite(s) && Number.isFinite(e)) {
      totalExecSeconds += Math.max(0, (e - s) / 1000);
    }
  }

  const metrics = {
    totalTasks: tasks.length,
    completedTasks: completed.length,
    failedTasks: failed.length,
    totalExecutionSeconds: totalExecSeconds,
    averageTaskCompletionSeconds: completed.length
      ? totalExecSeconds / completed.length
      : 0,
    queueWaitingSeconds: totalWaitSeconds / Math.max(1, tasks.filter((x) => x.startedAt).length),
    initialAgents: 6,
    peakActiveAgents: peak,
    averageActiveAgents: activeCount,
    agentUtilization: util,
    spawnEvents: spawnCount,
    terminationEvents: terminationCount,
    reassignmentEvents: reassignCount,
    decisionsByType: decisions.reduce<Partial<Record<string, number>>>((acc, d) => {
      acc[d.action] = (acc[d.action] ?? 0) + 1;
      return acc;
    }, {}),
    cycleCount: decisions.length,
  };

  const snapshot: OrgSnapshot = {
    projectState,
    agents: agents.map((a) => ({
      ...a,
      meta: { ...a.meta, workload: workload.score, risk: risk.score },
      lifecycle: a.lifecycle.length > 0 ? a.lifecycle : ["CREATED"],
    })),
    tasks: [...tasks],
    workload,
    risk,
    observation: {
      queueLength: queueLen,
      complexity: workload.complexity,
      executionDelay: workload.executionDelay,
      failureRate: workload.failureRate,
      activeAgents: activeCount,
    },
    latestDecision,
    decisions: [...decisions],
    events: events.map((e) => ({ ...e })),
    metrics,
    flowStage,
    justSpawned,
    activeAgentId: running.map((r) => r.assignedAgent).filter(Boolean)[0] ?? null,
    isDemo: true,
    title: args.title,
    narrative,
    scenarioName,
  };
  return snapshot;
}

// ---------------------------------------------------------------------------
// scenario bases
// ---------------------------------------------------------------------------

const BASE_WORKLOAD: WorkloadBase = {
  queueLength: 5,
  complexity: 0.42,
  executionDelay: 0.3,
  failureRate: 0.12,
  score: 34,
  level: "NORMAL",
};

const BASE_RISK: RiskBase = {
  securityFindings: 0,
  authIssues: 0,
  suspiciousCode: 0,
  failedChecks: 0,
  repeatedFailures: 0,
  highRiskTasks: 0,
  score: 12,
  level: "NORMAL",
};

const T = (id: string, role: RoleKey, description: string, extra: Partial<TaskInput> = {}): TaskInput => ({
  id,
  role,
  description,
  priority: extra.priority ?? 3,
  complexity: extra.complexity ?? 3,
  risk: extra.risk ?? 20,
  dependencies: extra.dependencies ?? [],
  status: extra.status ?? "PENDING",
  retryCount: extra.retryCount ?? 0,
});

const T0 = "2026-01-01T10:30:00.000Z";

export function buildDemoFrames(scenarioId: string): OrgSnapshot[] {
  switch (scenarioId) {
    case "m8_high_backend_workload":
      return HB();
    case "m8_high_frontend_workload":
      return highFrontend();
    case "m8_security_risk":
      return securityRisk();
    case "m8_mixed_high_workload":
      return mixedWorkload();
    default:
      return lowWorkload();
  }
}

// ---------------------------------------------------------------------------
// HIGH BACKEND WORKLOAD — the primary presentation scenario
// ---------------------------------------------------------------------------

const HIGH_BACKEND_TASKS: TaskInput[] = [
  T("TASK-1", "architect", "Define system architecture and component interfaces.", { complexity: 3, risk: 25 }),
  T("TASK-2", "backend", "Implement API gateway and request routing.", { complexity: 5, risk: 30 }),
  T("TASK-3", "backend", "Implement authentication, sessions, and role checks.", { complexity: 5, risk: 30, dependencies: ["TASK-2"] }),
  T("TASK-4", "backend", "Implement notifications and messaging service.", { complexity: 5, risk: 30, dependencies: ["TASK-3"] }),
  T("TASK-5", "backend", "Implement reporting, analytics, and exports.", { complexity: 5, risk: 30, dependencies: ["TASK-4"] }),
  T("TASK-6", "backend", "Implement scheduling and matching logic.", { complexity: 5, risk: 30, dependencies: ["TASK-5"] }),
  T("TASK-7", "backend", "Implement community and feed APIs.", { complexity: 5, risk: 30, dependencies: ["TASK-6"] }),
  T("TASK-8", "backend", "Implement full-text search and resource lookups.", { complexity: 5, risk: 30, dependencies: ["TASK-7"], retryCount: 2 }),
  T("TASK-9", "frontend", "Implement the student-facing web application shell.", { complexity: 4, risk: 15, dependencies: ["TASK-2"] }),
  T("TASK-10", "qa", "Execute acceptance and regression test suites.", { complexity: 2, risk: 20, dependencies: ["TASK-2", "TASK-9"] }),
  T("TASK-11", "security", "Perform security review and identify vulnerabilities.", { complexity: 2, risk: 40, dependencies: ["TASK-2", "TASK-9"] }),
];

const HB = (): OrgSnapshot[] => {
  const baseAgents: AgentInput[] = [
    { agentId: "PM-1", role: "project_manager", status: "IDLE" },
    { agentId: "ARCH-1", role: "architect", status: "IDLE" },
    { agentId: "BACKEND-1", role: "backend", status: "IDLE" },
    { agentId: "FRONTEND-1", role: "frontend", status: "IDLE" },
    { agentId: "QA-1", role: "qa", status: "IDLE" },
    { agentId: "SECURITY-1", role: "security", status: "IDLE" },
  ];

  const beats: Beat[] = [
    {
      title: "Project initialized",
      projectState: "PLANNING",
      flowStage: null,
      addTasks: [],
      agentStatus: { "PM-1": "ACTIVE" },
      events: [
        { kind: "workflow", title: "Workflow started", detail: "Project description accepted" },
        { kind: "task", title: "PM-1 begins requirement analysis" },
      ],
      activeAgentIds: ["PM-1"],
    },
    {
      title: "PM decomposes project",
      projectState: "PLANNING",
      flowStage: null,
      addTasks: HIGH_BACKEND_TASKS,
      events: [
        { kind: "task", title: "Project decomposed into 11 tasks", detail: "PM-1 planning & dependency graph" },
        { kind: "task", title: "Tasks created with priorities, complexity, risk" },
      ],
      narrative: "The Project Manager decomposes the requirement into a dependency-ordered task plan.",
    },
    {
      title: "Tasks appear",
      projectState: "PLANNING",
      flowStage: null,
      setTasks: {
        "TASK-1": { id: "TASK-1", status: "PENDING" },
        "TASK-2": { id: "TASK-2", status: "PENDING" },
        "TASK-9": { id: "TASK-9", status: "PENDING" },
      },
      events: [
        { kind: "task", title: "Task plan visible in queue", detail: "5 roles, 11 tasks" },
      ],
      narrative: "The task queue forms the backbone of the organization's work.",
    },
    {
      title: "Agents receive tasks",
      projectState: "EXECUTING",
      flowStage: null,
      agentStatus: { "ARCH-1": "ACTIVE", "BACKEND-1": "ACTIVE", "FRONTEND-1": "ACTIVE" },
      setTasks: {
        "TASK-1": { id: "TASK-1", status: "RUNNING", assignedAgent: "ARCH-1", startedAt: T0 },
        "TASK-2": { id: "TASK-2", status: "ASSIGNED", assignedAgent: "BACKEND-1" },
        "TASK-9": { id: "TASK-9", status: "ASSIGNED", assignedAgent: "FRONTEND-1" },
      },
      workload: { queueLength: 9, executionDelay: 0.34, score: 44, level: "ELEVATED" },
      events: [
        { kind: "task", title: "ARCH-1 starts architecture", detail: "TASK-1" },
        { kind: "task", title: "BACKEND-1 assigned gateway work", detail: "TASK-2" },
        { kind: "task", title: "FRONTEND-1 assigned app shell", detail: "TASK-9" },
      ],
      activeAgentIds: ["ARCH-1"],
    },
    {
      title: "Backend queue increases",
      projectState: "EXECUTING",
      flowStage: null,
      agentStatus: { "BACKEND-1": "ACTIVE" },
      setTasks: {
        "TASK-2": { id: "TASK-2", status: "RUNNING", assignedAgent: "BACKEND-1", startedAt: T0 },
        "TASK-3": { id: "TASK-3", status: "ASSIGNED", assignedAgent: "BACKEND-1" },
        "TASK-4": { id: "TASK-4", status: "ASSIGNED", assignedAgent: "BACKEND-1" },
        "TASK-8": { id: "TASK-8", status: "RETRY", retryCount: 1, assignedAgent: "BACKEND-1" },
      },
      workload: { queueLength: 10, complexity: 0.58, executionDelay: 0.5, failureRate: 0.22, score: 61, level: "ELEVATED" },
      risk: { securityFindings: 1, failedChecks: 1, score: 26, level: "ELEVATED" },
      events: [
        { kind: "task", title: "Backend queue grows to 6 tasks", detail: "7 backend tasks, 1 active agent" },
        { kind: "task", title: "TASK-8 entered retry", detail: "notifications service failing" },
      ],
      narrative: "A single backend agent is now the bottleneck — the queue waits.",
    },
    {
      title: "Workload rises",
      projectState: "EXECUTING",
      flowStage: null,
      agentStatus: { "BACKEND-1": "ACTIVE" },
      setTasks: {
        "TASK-3": { id: "TASK-3", status: "RUNNING", assignedAgent: "BACKEND-1", startedAt: T0 },
        "TASK-5": { id: "TASK-5", status: "ASSIGNED", assignedAgent: "BACKEND-1" },
        "TASK-6": { id: "TASK-6", status: "ASSIGNED", assignedAgent: "BACKEND-1" },
      },
      workload: { queueLength: 12, complexity: 0.7, executionDelay: 0.66, failureRate: 0.3, score: 78, level: "HIGH" },
      risk: { securityFindings: 1, failedChecks: 2, repeatedFailures: 1, score: 34, level: "ELEVATED" },
      events: [
        { kind: "observation", title: "Backend workload crosses HIGH threshold", detail: "Workload 78 (threshold 70)" },
        { kind: "analysis", title: "Queue 12 · complexity 0.70 · delay 0.66 · failures 0.30" },
      ],
      narrative: "Backend workload exceeds the configured HIGH threshold.",
    },
    {
      title: "Controller observes",
      projectState: "EXECUTING",
      flowStage: "OBSERVE",
      events: [
        { kind: "observation", title: "System observed elevated Backend workload", detail: "active agents: 1 · queue: 6 open backend tasks" },
      ],
    },
    {
      title: "Adaptive decision",
      projectState: "EXECUTING",
      flowStage: "DECIDE",
      decision: {
        action: "SPAWN",
        cycle: 1,
        workloadScore: 78,
        riskScore: 34,
        workloadLevel: "HIGH",
        riskLevel: "ELEVATED",
        reason: "Backend workload exceeded threshold",
        affectedRole: "backend",
        affectedAgent: "BACKEND-2",
        before: { activeForRole: 1, queue: 6, workload: 78, risk: 34 },
        after: { activeForRole: 2, queue: 6, workload: 52, risk: 30 },
      },
      events: [
        { kind: "decision", title: "Decision: SPAWN BACKEND-2", detail: "Backend workload exceeded threshold" },
        { kind: "allocation", title: "Allocating an additional backend agent" },
      ],
      narrative: "The deterministic controller allocates capacity where the queue is longest.",
    },
    {
      title: "BACKEND-2 appears",
      projectState: "EXECUTING",
      flowStage: "ALLOCATE",
      spawnAgents: [ { agentId: "BACKEND-2", role: "backend", status: "CREATED" } ],
      agentStatus: { "BACKEND-2": "IDLE" },
      events: [
        { kind: "agent", title: "BACKEND-2 created", detail: "spawned by Adaptive Controller" },
        { kind: "agent", title: "BACKEND-2 joins the backend pool", detail: "BACKEND-1 + BACKEND-2" },
      ],
      narrative: "A second Backend Developer joins the organization.",
    },
    {
      title: "Tasks redistribute",
      projectState: "EXECUTING",
      flowStage: "ALLOCATE",
      agentStatus: { "BACKEND-2": "ACTIVE" },
      setTasks: {
        "TASK-2": { id: "TASK-2", status: "RUNNING", assignedAgent: "BACKEND-1" },
        "TASK-3": { id: "TASK-3", status: "RUNNING", assignedAgent: "BACKEND-2", startedAt: T0 },
        "TASK-4": { id: "TASK-4", status: "ASSIGNED", assignedAgent: "BACKEND-2" },
        "TASK-8": { id: "TASK-8", status: "RETRY", retryCount: 2, assignedAgent: "BACKEND-2" },
      },
      workload: { queueLength: 9, executionDelay: 0.42, failureRate: 0.18, score: 56, level: "ELEVATED" },
      events: [
        { kind: "task", title: "Tasks redistributed across backend pool", detail: "BACKEND-1 · BACKEND-2" },
        { kind: "task", title: "TASK-3 moved to BACKEND-2" },
      ],
      narrative: "Queue time starts to fall as two backend agents drain the backlog.",
    },
    {
      title: "Workload decreases",
      projectState: "EXECUTING",
      flowStage: "EXECUTE",
      agentStatus: { "QA-1": "ACTIVE", "SECURITY-1": "ACTIVE" },
      setTasks: {
        "TASK-8": { id: "TASK-8", status: "RUNNING", assignedAgent: "BACKEND-2", startedAt: T0 },
        "TASK-9": { id: "TASK-9", status: "RUNNING", assignedAgent: "FRONTEND-1", startedAt: T0 },
        "TASK-10": { id: "TASK-10", status: "RUNNING", assignedAgent: "QA-1", startedAt: T0 },
        "TASK-11": { id: "TASK-11", status: "RUNNING", assignedAgent: "SECURITY-1", startedAt: T0 },
      },
      workload: { queueLength: 6, executionDelay: 0.22, failureRate: 0.1, score: 47, level: "ELEVATED" },
      risk: { score: 22, level: "NORMAL" },
      events: [
        { kind: "quality", title: "QA-1 executing acceptance suites" },
        { kind: "quality", title: "SECURITY-1 reviewing authentication paths" },
        { kind: "task", title: "TASK-4 and TASK-5 completed", detail: "queue waiting time reduced" },
      ],
    },
    {
      title: "QA / Security review",
      projectState: "EXECUTING",
      flowStage: "EVALUATE",
      setTasks: {
        "TASK-2": { id: "TASK-2", status: "COMPLETED", assignedAgent: "BACKEND-1", completedAt: T0 },
        "TASK-3": { id: "TASK-3", status: "COMPLETED", assignedAgent: "BACKEND-2", completedAt: T0 },
        "TASK-4": { id: "TASK-4", status: "COMPLETED", assignedAgent: "BACKEND-2", completedAt: T0 },
        "TASK-5": { id: "TASK-5", status: "COMPLETED", assignedAgent: "BACKEND-1", completedAt: T0 },
        "TASK-6": { id: "TASK-6", status: "COMPLETED", assignedAgent: "BACKEND-2", completedAt: T0 },
        "TASK-7": { id: "TASK-7", status: "COMPLETED", assignedAgent: "BACKEND-1", completedAt: T0 },
        "TASK-8": { id: "TASK-8", status: "COMPLETED", assignedAgent: "BACKEND-2", completedAt: T0 },
        "TASK-9": { id: "TASK-9", status: "COMPLETED", assignedAgent: "FRONTEND-1", completedAt: T0 },
      },
      workload: { queueLength: 2, executionDelay: 0.12, failureRate: 0.04, score: 38, level: "NORMAL" },
      risk: { securityFindings: 0, authIssues: 0, suspiciousCode: 0, failedChecks: 0, repeatedFailures: 0, highRiskTasks: 0, score: 14, level: "NORMAL" },
      events: [
        { kind: "quality", title: "QA review requested", detail: "7 tasks verified" },
        { kind: "quality", title: "Security findings: 0 new" },
      ],
      narrative: "Backend queue was reduced — the adaptive change has a measurable effect.",
    },
    {
      title: "Terminal state",
      projectState: "TERMINAL",
      flowStage: "ADAPT",
      agentStatus: { "QA-1": "COMPLETED", "SECURITY-1": "COMPLETED" },
      setTasks: {
        "TASK-10": { id: "TASK-10", status: "COMPLETED", assignedAgent: "QA-1", completedAt: T0 },
        "TASK-11": { id: "TASK-11", status: "COMPLETED", assignedAgent: "SECURITY-1", completedAt: T0 },
      },
      workload: { queueLength: 0, score: 22, level: "NORMAL" },
      risk: { score: 10, level: "NORMAL" },
      events: [
        { kind: "workflow", title: "Workflow completed", detail: "11/11 tasks terminal" },
        { kind: "quality", title: "Evaluation: NO_ADAPT_WINNER", detail: "descriptive measurements only" },
      ],
      narrative: "The loop closes: observe → decide → allocate → execute → evaluate → adapt.",
    },
  ];

  return buildFrames(
    "High Backend Workload",
    T0,
    beats,
    BASE_WORKLOAD,
    BASE_RISK,
  ).map((f) => {
    if (f.agents.length === 0) {
      f.agents = baseAgents.map((a) => makeAgent(a, T0));
    }
    return f;
  });
};

// ---------------------------------------------------------------------------
// HIGH FRONTEND WORKLOAD
// ---------------------------------------------------------------------------

const HIGH_FRONTEND_TASKS: TaskInput[] = [
  T("TASK-1", "architect", "Define system architecture and component interfaces.", { complexity: 3, risk: 20 }),
  T("TASK-2", "backend", "Implement the API gateway and request routing.", { complexity: 4, risk: 20 }),
  T("TASK-3", "frontend", "Implement app shell, navigation, and theming.", { complexity: 5, risk: 15 }),
  T("TASK-4", "frontend", "Implement counsellor dashboard and widgets.", { complexity: 5, risk: 15, dependencies: ["TASK-3"] }),
  T("TASK-5", "frontend", "Implement session booking and scheduling flows.", { complexity: 5, risk: 15, dependencies: ["TASK-4"] }),
  T("TASK-6", "frontend", "Implement community feed and posting interface.", { complexity: 5, risk: 15, dependencies: ["TASK-5"] }),
  T("TASK-7", "frontend", "Implement profile, settings, and consent screens.", { complexity: 5, risk: 15, dependencies: ["TASK-6"] }),
  T("TASK-8", "frontend", "Implement resource search and filter surfaces.", { complexity: 5, risk: 15, dependencies: ["TASK-7"] }),
  T("TASK-9", "frontend", "Implement offline support and low-bandwidth mode.", { complexity: 5, risk: 15, dependencies: ["TASK-8"] }),
  T("TASK-10", "qa", "Execute acceptance and regression test suites.", { complexity: 2, risk: 20, dependencies: ["TASK-2", "TASK-3"] }),
  T("TASK-11", "security", "Perform security review and identify vulnerabilities.", { complexity: 2, risk: 40, dependencies: ["TASK-2", "TASK-3"] }),
];

const highFrontend = (): OrgSnapshot[] =>
  buildFrames(
    "High Frontend Workload",
    T0,
    [
      {
        title: "Project initialized",
        projectState: "PLANNING",
        flowStage: null,
        agentStatus: { "PM-1": "ACTIVE" },
        events: [
          { kind: "workflow", title: "Workflow started" },
          { kind: "task", title: "PM-1 begins requirement analysis" },
        ],
      },
      {
        title: "PM decomposes project",
        projectState: "PLANNING",
        flowStage: null,
        addTasks: HIGH_FRONTEND_TASKS,
        events: [
          { kind: "task", title: "Project decomposed into 11 tasks" },
          { kind: "task", title: "Frontend backlog identified", detail: "7 UI tasks" },
        ],
      },
      {
        title: "Agents receive tasks",
        projectState: "EXECUTING",
        flowStage: null,
        agentStatus: { "ARCH-1": "ACTIVE", "BACKEND-1": "ACTIVE", "FRONTEND-1": "ACTIVE" },
        setTasks: {
          "TASK-1": { id: "TASK-1", status: "RUNNING", assignedAgent: "ARCH-1", startedAt: T0 },
          "TASK-2": { id: "TASK-2", status: "RUNNING", assignedAgent: "BACKEND-1", startedAt: T0 },
          "TASK-3": { id: "TASK-3", status: "RUNNING", assignedAgent: "FRONTEND-1", startedAt: T0 },
        },
        workload: { queueLength: 8, score: 41, level: "ELEVATED" },
        events: [
          { kind: "task", title: "FRONTEND-1 starts app shell", detail: "TASK-3" },
        ],
      },
      {
        title: "Frontend queue increases",
        projectState: "EXECUTING",
        flowStage: null,
        agentStatus: { "FRONTEND-1": "ACTIVE" },
        setTasks: {
          "TASK-4": { id: "TASK-4", status: "ASSIGNED", assignedAgent: "FRONTEND-1" },
          "TASK-5": { id: "TASK-5", status: "RETRY", retryCount: 1, assignedAgent: "FRONTEND-1" },
          "TASK-6": { id: "TASK-6", status: "ASSIGNED", assignedAgent: "FRONTEND-1" },
        },
        workload: { queueLength: 11, complexity: 0.66, executionDelay: 0.6, failureRate: 0.24, score: 74, level: "HIGH" },
        events: [
          { kind: "task", title: "Frontend queue grows to 7 tasks" },
          { kind: "task", title: "TASK-5 entered retry", detail: "booking flow failing" },
        ],
      },
      {
        title: "Controller observes",
        projectState: "EXECUTING",
        flowStage: "OBSERVE",
        events: [{ kind: "observation", title: "System observed elevated Frontend workload", detail: "active agents: 1 · queue: 6 open frontend tasks" }],
      },
      {
        title: "Adaptive decision",
        projectState: "EXECUTING",
        flowStage: "DECIDE",
        decision: {
          action: "SPAWN",
          cycle: 1,
          workloadScore: 74,
          riskScore: 22,
          workloadLevel: "HIGH",
          riskLevel: "NORMAL",
          reason: "Frontend workload exceeded threshold",
          affectedRole: "frontend",
          affectedAgent: "FRONTEND-2",
          before: { activeForRole: 1, queue: 5, workload: 74, risk: 22 },
          after: { activeForRole: 2, queue: 5, workload: 49, risk: 20 },
        },
        events: [
          { kind: "decision", title: "Decision: SPAWN FRONTEND-2", detail: "Frontend workload exceeded threshold" },
        ],
      },
      {
        title: "FRONTEND-2 appears",
        projectState: "EXECUTING",
        flowStage: "ALLOCATE",
        spawnAgents: [{ agentId: "FRONTEND-2", role: "frontend", status: "CREATED" }],
        agentStatus: { "FRONTEND-2": "ACTIVE" },
        setTasks: {
          "TASK-4": { id: "TASK-4", status: "RUNNING", assignedAgent: "FRONTEND-2", startedAt: T0 },
        },
        workload: { queueLength: 8, score: 55, level: "ELEVATED" },
        events: [
          { kind: "agent", title: "FRONTEND-2 created", detail: "spawned by Adaptive Controller" },
          { kind: "task", title: "Tasks redistributed across frontend pool" },
        ],
      },
      {
        title: "Execution continues",
        projectState: "EXECUTING",
        flowStage: "EXECUTE",
        agentStatus: { "QA-1": "ACTIVE", "SECURITY-1": "ACTIVE" },
        setTasks: {
          "TASK-3": { id: "TASK-3", status: "COMPLETED", assignedAgent: "FRONTEND-1", completedAt: T0 },
          "TASK-5": { id: "TASK-5", status: "RUNNING", assignedAgent: "FRONTEND-2", startedAt: T0 },
          "TASK-7": { id: "TASK-7", status: "RUNNING", assignedAgent: "FRONTEND-2", startedAt: T0 },
        },
        workload: { queueLength: 5, executionDelay: 0.2, failureRate: 0.08, score: 43, level: "ELEVATED" },
        events: [
          { kind: "task", title: "TASK-3 completed", detail: "app shell done" },
          { kind: "quality", title: "QA-1 and SECURITY-1 begin review" },
        ],
      },
      {
        title: "QA / Security review",
        projectState: "EXECUTING",
        flowStage: "EVALUATE",
        setTasks: {
          "TASK-4": { id: "TASK-4", status: "COMPLETED", assignedAgent: "FRONTEND-2", completedAt: T0 },
          "TASK-5": { id: "TASK-5", status: "COMPLETED", assignedAgent: "FRONTEND-2", completedAt: T0 },
          "TASK-6": { id: "TASK-6", status: "COMPLETED", assignedAgent: "FRONTEND-1", completedAt: T0 },
          "TASK-7": { id: "TASK-7", status: "COMPLETED", assignedAgent: "FRONTEND-2", completedAt: T0 },
          "TASK-8": { id: "TASK-8", status: "COMPLETED", assignedAgent: "FRONTEND-1", completedAt: T0 },
          "TASK-9": { id: "TASK-9", status: "COMPLETED", assignedAgent: "FRONTEND-2", completedAt: T0 },
        },
        workload: { queueLength: 1, score: 32, level: "NORMAL" },
        events: [{ kind: "quality", title: "QA review requested", detail: "7 UI tasks verified" }],
      },
      {
        title: "Terminal state",
        projectState: "TERMINAL",
        flowStage: "ADAPT",
        setTasks: {
          "TASK-10": { id: "TASK-10", status: "COMPLETED", assignedAgent: "QA-1", completedAt: T0 },
          "TASK-11": { id: "TASK-11", status: "COMPLETED", assignedAgent: "SECURITY-1", completedAt: T0 },
        },
        events: [{ kind: "workflow", title: "Workflow completed", detail: "11/11 tasks terminal" }],
      },
    ],
    { ...BASE_WORKLOAD, complexity: 0.45, score: 30, level: "NORMAL" },
    BASE_RISK,
  );

// ---------------------------------------------------------------------------
// SECURITY RISK
// ---------------------------------------------------------------------------

const SECURITY_TASKS: TaskInput[] = [
  T("TASK-1", "architect", "Define system architecture and component interfaces.", { complexity: 3, risk: 30 }),
  T("TASK-2", "backend", "Implement API gateway and request routing.", { complexity: 4, risk: 90 }),
  T("TASK-3", "frontend", "Build the login and settings screens.", { complexity: 4, risk: 90 }),
  T("TASK-4", "backend", "Resolve authentication and permission errors.", { complexity: 4, risk: 90 }),
  T("TASK-5", "backend", "Detect suspicious login injection patterns.", { complexity: 4, risk: 90 }),
  T("TASK-6", "backend", "Fix unsafe input injection handling.", { complexity: 4, risk: 90 }),
  T("TASK-7", "security", "Review authentication module; record findings.", { complexity: 3, risk: 90, status: "RETRY", retryCount: 1 }),
  T("TASK-8", "security", "Review session handling; report vulnerabilities.", { complexity: 3, risk: 90, status: "RETRY", retryCount: 1 }),
  T("TASK-9", "security", "Review authorization scope; identify gaps.", { complexity: 3, risk: 90, status: "RETRY", retryCount: 1 }),
  T("TASK-10", "security", "Review data access and consent controls.", { complexity: 3, risk: 90, status: "RETRY", retryCount: 1 }),
  T("TASK-11", "qa", "Verify authentication flows and sign-in paths.", { complexity: 2, risk: 90 }),
];

const securityRisk = (): OrgSnapshot[] =>
  buildFrames(
    "Security Risk",
    T0,
    [
      {
        title: "Project initialized",
        projectState: "PLANNING",
        flowStage: null,
        agentStatus: { "PM-1": "ACTIVE" },
        addTasks: SECURITY_TASKS,
        events: [
          { kind: "workflow", title: "Workflow started" },
          { kind: "task", title: "PM-1 decomposes security-sensitive project", detail: "11 tasks, high-risk module" },
        ],
      },
      {
        title: "Agents receive tasks",
        projectState: "EXECUTING",
        flowStage: null,
        agentStatus: { "BACKEND-1": "ACTIVE", "SECURITY-1": "ACTIVE", "ARCH-1": "ACTIVE" },
        setTasks: {
          "TASK-2": { id: "TASK-2", status: "RUNNING", assignedAgent: "BACKEND-1", startedAt: T0 },
          "TASK-1": { id: "TASK-1", status: "RUNNING", assignedAgent: "ARCH-1", startedAt: T0 },
          "TASK-7": { id: "TASK-7", status: "ASSIGNED", assignedAgent: "SECURITY-1" },
          "TASK-8": { id: "TASK-8", status: "ASSIGNED", assignedAgent: "SECURITY-1" },
        },
        workload: { queueLength: 8, score: 48, level: "ELEVATED" },
        risk: { securityFindings: 3, authIssues: 2, failedChecks: 2, score: 52, level: "ELEVATED" },
        events: [
          { kind: "task", title: "BACKEND-1 starts gateway work" },
          { kind: "quality", title: "SECURITY-1 takes on authentication reviews" },
        ],
      },
      {
        title: "Security backlog grows",
        projectState: "EXECUTING",
        flowStage: null,
        setTasks: {
          "TASK-7": { id: "TASK-7", status: "RETRY", retryCount: 2, assignedAgent: "SECURITY-1" },
          "TASK-8": { id: "TASK-8", status: "RETRY", retryCount: 2, assignedAgent: "SECURITY-1" },
          "TASK-9": { id: "TASK-9", status: "ASSIGNED", assignedAgent: "SECURITY-1" },
          "TASK-10": { id: "TASK-10", status: "ASSIGNED", assignedAgent: "SECURITY-1" },
          "TASK-4": { id: "TASK-4", status: "FAILED", assignedAgent: "BACKEND-1" },
          "TASK-5": { id: "TASK-5", status: "FAILED", assignedAgent: "BACKEND-1" },
        },
        workload: { queueLength: 9, complexity: 0.62, executionDelay: 0.5, failureRate: 0.4, score: 71, level: "HIGH" },
        risk: {
          securityFindings: 5,
          authIssues: 3,
          suspiciousCode: 2,
          failedChecks: 4,
          repeatedFailures: 3,
          highRiskTasks: 6,
          score: 84,
          level: "HIGH",
        },
        events: [
          { kind: "quality", title: "Security findings accumulate", detail: "5 findings · 3 auth issues" },
          { kind: "observation", title: "Risk score crosses HIGH", detail: "84 (threshold 70)" },
        ],
        narrative: "Risk indicators concentrate — the security role is overloaded.",
      },
      {
        title: "Controller observes",
        projectState: "EXECUTING",
        flowStage: "OBSERVE",
        events: [{ kind: "observation", title: "System observed HIGH security risk", detail: "risk 84 · security queue saturated" }],
      },
      {
        title: "Adaptive decision",
        projectState: "EXECUTING",
        flowStage: "DECIDE",
        decision: {
          action: "SPAWN",
          cycle: 1,
          workloadScore: 71,
          riskScore: 84,
          workloadLevel: "HIGH",
          riskLevel: "HIGH",
          reason: "Security risk exceeded threshold",
          affectedRole: "security",
          affectedAgent: "SECURITY-2",
          before: { activeForRole: 1, queue: 4, workload: 71, risk: 84 },
          after: { activeForRole: 2, queue: 4, workload: 55, risk: 46 },
        },
        events: [
          { kind: "decision", title: "Decision: SPAWN SECURITY-2", detail: "Security risk exceeded threshold" },
        ],
      },
      {
        title: "SECURITY-2 appears",
        projectState: "EXECUTING",
        flowStage: "ALLOCATE",
        spawnAgents: [{ agentId: "SECURITY-2", role: "security", status: "CREATED" }],
        agentStatus: { "SECURITY-2": "ACTIVE" },
        setTasks: {
          "TASK-8": { id: "TASK-8", status: "RUNNING", assignedAgent: "SECURITY-2", startedAt: T0 },
          "TASK-9": { id: "TASK-9", status: "RUNNING", assignedAgent: "SECURITY-2", startedAt: T0 },
        },
        risk: { securityFindings: 5, failedChecks: 3, repeatedFailures: 2, score: 62, level: "ELEVATED" },
        events: [
          { kind: "agent", title: "SECURITY-2 created", detail: "spawned by Adaptive Controller" },
          { kind: "allocation", title: "Security reviews redistributed across two agents" },
        ],
      },
      {
        title: "Findings resolved",
        projectState: "EXECUTING",
        flowStage: "EXECUTE",
        setTasks: {
          "TASK-4": { id: "TASK-4", status: "RUNNING", assignedAgent: "BACKEND-1", startedAt: T0 },
          "TASK-5": { id: "TASK-5", status: "RUNNING", assignedAgent: "QA-1", startedAt: T0 },
        },
        agentStatus: { "QA-1": "ACTIVE" },
        risk: { securityFindings: 4, authIssues: 2, suspiciousCode: 1, failedChecks: 2, repeatedFailures: 1, highRiskTasks: 3, score: 51, level: "ELEVATED" },
        workload: { queueLength: 6, score: 54, level: "ELEVATED" },
        events: [
          { kind: "quality", title: "Suspicious login patterns investigated", detail: "injection handler fixed" },
          { kind: "quality", title: "Risk decreasing after reallocation" },
        ],
      },
      {
        title: "QA / Security review",
        projectState: "EXECUTING",
        flowStage: "EVALUATE",
        agentStatus: { "SECURITY-1": "COMPLETED", "QA-1": "COMPLETED" },
        setTasks: {
          "TASK-7": { id: "TASK-7", status: "COMPLETED", assignedAgent: "SECURITY-1", completedAt: T0 },
          "TASK-8": { id: "TASK-8", status: "COMPLETED", assignedAgent: "SECURITY-2", completedAt: T0 },
          "TASK-9": { id: "TASK-9", status: "COMPLETED", assignedAgent: "SECURITY-2", completedAt: T0 },
          "TASK-10": { id: "TASK-10", status: "COMPLETED", assignedAgent: "SECURITY-1", completedAt: T0 },
          "TASK-11": { id: "TASK-11", status: "COMPLETED", assignedAgent: "QA-1", completedAt: T0 },
        },
        risk: { score: 32, level: "NORMAL" },
        workload: { queueLength: 1, score: 35, level: "NORMAL" },
        events: [{ kind: "quality", title: "All security reviews completed", detail: "findings resolved" }],
      },
      {
        title: "Terminal state",
        projectState: "TERMINAL",
        flowStage: "ADAPT",
        setTasks: {
          "TASK-2": { id: "TASK-2", status: "COMPLETED", assignedAgent: "BACKEND-1", completedAt: T0 },
          "TASK-3": { id: "TASK-3", status: "COMPLETED", assignedAgent: "FRONTEND-1", completedAt: T0 },
          "TASK-6": { id: "TASK-6", status: "COMPLETED", assignedAgent: "BACKEND-1", completedAt: T0 },
        },
        events: [{ kind: "workflow", title: "Workflow completed", detail: "all security reviews done" }],
      },
    ],
    { ...BASE_WORKLOAD, level: "NORMAL" },
    { ...BASE_RISK, score: 20, level: "NORMAL" },
  );

// ---------------------------------------------------------------------------
// MIXED ELEVATED WORKLOAD (no spawn)
// ---------------------------------------------------------------------------

const mixedWorkload = (): OrgSnapshot[] =>
  buildFrames(
    "Mixed Elevated Workload",
    T0,
    [
      {
        title: "Project initialized",
        projectState: "PLANNING",
        flowStage: null,
        agentStatus: { "PM-1": "ACTIVE" },
        addTasks: [
          T("TASK-1", "architect", "Define system architecture and component interfaces."),
          T("TASK-2", "backend", "Implement core domain APIs and data access."),
          T("TASK-3", "frontend", "Implement app shell and navigation."),
          T("TASK-4", "backend", "Implement messaging and notifications service."),
          T("TASK-5", "frontend", "Implement dashboard and session widgets."),
          T("TASK-6", "backend", "Implement reporting and exports.", { status: "RETRY", retryCount: 1 }),
          T("TASK-7", "frontend", "Implement booking and scheduling screens.", { status: "RETRY", retryCount: 1 }),
          T("TASK-8", "qa", "Execute end-to-end and acceptance test suites."),
          T("TASK-9", "security", "Perform security review and identify vulnerabilities."),
          T("TASK-10", "qa", "Validate performance and low-bandwidth behaviour."),
          T("TASK-11", "security", "Validate privacy and compliance controls."),
        ],
        events: [
          { kind: "workflow", title: "Workflow started" },
          { kind: "task", title: "PM-1 decomposes a balanced 11-task plan" },
        ],
      },
      {
        title: "Agents receive tasks",
        projectState: "EXECUTING",
        flowStage: null,
        agentStatus: { "BACKEND-1": "ACTIVE", "FRONTEND-1": "ACTIVE", "ARCH-1": "ACTIVE" },
        setTasks: {
          "TASK-1": { id: "TASK-1", status: "RUNNING", assignedAgent: "ARCH-1", startedAt: T0 },
          "TASK-2": { id: "TASK-2", status: "RUNNING", assignedAgent: "BACKEND-1", startedAt: T0 },
          "TASK-3": { id: "TASK-3", status: "RUNNING", assignedAgent: "FRONTEND-1", startedAt: T0 },
        },
        workload: { queueLength: 10, score: 52, level: "ELEVATED" },
        events: [
          { kind: "task", title: "Three roles start simultaneously" },
        ],
      },
      {
        title: "Workload distributes evenly",
        projectState: "EXECUTING",
        flowStage: null,
        setTasks: {
          "TASK-4": { id: "TASK-4", status: "RUNNING", assignedAgent: "BACKEND-1", startedAt: T0 },
          "TASK-5": { id: "TASK-5", status: "RUNNING", assignedAgent: "FRONTEND-1", startedAt: T0 },
          "TASK-6": { id: "TASK-6", status: "RETRY", retryCount: 1, assignedAgent: "BACKEND-1" },
          "TASK-7": { id: "TASK-7", status: "RETRY", retryCount: 1, assignedAgent: "FRONTEND-1" },
        },
        workload: { queueLength: 11, complexity: 0.55, executionDelay: 0.4, failureRate: 0.15, score: 58, level: "ELEVATED" },
        events: [
          { kind: "observation", title: "No single role crosses HIGH", detail: "workload 58 (ELEVATED band)" },
        ],
        narrative: "Demand is spread across roles — no threshold is crossed.",
      },
      {
        title: "Controller observes",
        projectState: "EXECUTING",
        flowStage: "OBSERVE",
        events: [{ kind: "observation", title: "System observed ELEVATED workload", detail: "workload 58 · no role saturated" }],
      },
      {
        title: "Adaptive decision",
        projectState: "EXECUTING",
        flowStage: "DECIDE",
        decision: {
          action: "CONTINUE",
          cycle: 1,
          workloadScore: 58,
          riskScore: 18,
          workloadLevel: "ELEVATED",
          riskLevel: "NORMAL",
          reason: "No role workload exceeded the spawn threshold",
          affectedRole: null,
          affectedAgent: null,
          before: { activeForRole: 1, queue: 5, workload: 58, risk: 18 },
          after: { activeForRole: 1, queue: 5, workload: 58, risk: 18 },
        },
        events: [
          { kind: "decision", title: "Decision: CONTINUE", detail: "Workload within configured band" },
        ],
        narrative: "Not every observation leads to a change — CONTINUE is also a decision.",
      },
      {
        title: "Execution continues",
        projectState: "EXECUTING",
        flowStage: "EXECUTE",
        agentStatus: { "QA-1": "ACTIVE", "SECURITY-1": "ACTIVE" },
        setTasks: {
          "TASK-6": { id: "TASK-6", status: "RUNNING", assignedAgent: "BACKEND-1", startedAt: T0 },
          "TASK-7": { id: "TASK-7", status: "RUNNING", assignedAgent: "FRONTEND-1", startedAt: T0 },
          "TASK-8": { id: "TASK-8", status: "RUNNING", assignedAgent: "QA-1", startedAt: T0 },
          "TASK-9": { id: "TASK-9", status: "RUNNING", assignedAgent: "SECURITY-1", startedAt: T0 },
        },
        workload: { queueLength: 6, score: 46, level: "ELEVATED" },
        events: [
          { kind: "task", title: "Retries recovered", detail: "TASK-6, TASK-7 back on track" },
          { kind: "quality", title: "QA and Security begin review" },
        ],
      },
      {
        title: "QA / Security review",
        projectState: "EXECUTING",
        flowStage: "EVALUATE",
        setTasks: {
          "TASK-2": { id: "TASK-2", status: "COMPLETED", assignedAgent: "BACKEND-1", completedAt: T0 },
          "TASK-3": { id: "TASK-3", status: "COMPLETED", assignedAgent: "FRONTEND-1", completedAt: T0 },
          "TASK-4": { id: "TASK-4", status: "COMPLETED", assignedAgent: "BACKEND-1", completedAt: T0 },
          "TASK-5": { id: "TASK-5", status: "COMPLETED", assignedAgent: "FRONTEND-1", completedAt: T0 },
        },
        workload: { queueLength: 2, score: 34, level: "NORMAL" },
        events: [{ kind: "quality", title: "QA review requested", detail: "end-to-end suites passing" }],
      },
      {
        title: "Terminal state",
        projectState: "TERMINAL",
        flowStage: "ADAPT",
        setTasks: {
          "TASK-10": { id: "TASK-10", status: "COMPLETED", assignedAgent: "QA-1", completedAt: T0 },
          "TASK-11": { id: "TASK-11", status: "COMPLETED", assignedAgent: "SECURITY-1", completedAt: T0 },
          "TASK-6": { id: "TASK-6", status: "COMPLETED", assignedAgent: "BACKEND-1", completedAt: T0 },
          "TASK-7": { id: "TASK-7", status: "COMPLETED", assignedAgent: "FRONTEND-1", completedAt: T0 },
        },
        events: [{ kind: "workflow", title: "Workflow completed", detail: "11/11 tasks terminal" }],
      },
    ],
    { ...BASE_WORKLOAD, score: 32, level: "NORMAL" },
    BASE_RISK,
  );

// ---------------------------------------------------------------------------
// LOW WORKLOAD (no spawn)
// ---------------------------------------------------------------------------

const lowWorkload = (): OrgSnapshot[] =>
  buildFrames(
    "Low Workload",
    T0,
    [
      {
        title: "Project initialized",
        projectState: "PLANNING",
        flowStage: null,
        agentStatus: { "PM-1": "ACTIVE" },
        addTasks: [
          T("TASK-1", "architect", "Define the system architecture and component interfaces."),
          T("TASK-2", "backend", "Implement backend APIs, business logic, and data access."),
          T("TASK-3", "frontend", "Implement frontend UI, components, and API integration."),
          T("TASK-4", "qa", "Execute tests, validate requirements, and report defects."),
          T("TASK-5", "security", "Perform security review and identify vulnerabilities."),
        ],
        events: [
          { kind: "workflow", title: "Workflow started" },
          { kind: "task", title: "PM-1 decomposes project into 5 tasks" },
        ],
      },
      {
        title: "Agents receive tasks",
        projectState: "EXECUTING",
        flowStage: null,
        agentStatus: { "ARCH-1": "ACTIVE", "BACKEND-1": "ACTIVE" },
        setTasks: {
          "TASK-1": { id: "TASK-1", status: "RUNNING", assignedAgent: "ARCH-1", startedAt: T0 },
          "TASK-2": { id: "TASK-2", status: "ASSIGNED", assignedAgent: "BACKEND-1" },
        },
        workload: { queueLength: 4, score: 31, level: "NORMAL" },
        events: [
          { kind: "task", title: "ARCH-1 starts architecture" },
          { kind: "task", title: "BACKEND-1 assigned API work" },
        ],
      },
      {
        title: "Workload stays flat",
        projectState: "EXECUTING",
        flowStage: null,
        setTasks: {
          "TASK-1": { id: "TASK-1", status: "COMPLETED", assignedAgent: "ARCH-1", completedAt: T0 },
          "TASK-2": { id: "TASK-2", status: "RUNNING", assignedAgent: "BACKEND-1", startedAt: T0 },
          "TASK-3": { id: "TASK-3", status: "RUNNING", assignedAgent: "FRONTEND-1", startedAt: T0 },
        },
        agentStatus: { "FRONTEND-1": "ACTIVE" },
        workload: { queueLength: 2, score: 29, level: "NORMAL" },
        events: [
          { kind: "observation", title: "Workload remains NORMAL", detail: "below 40 · no adaptation" },
        ],
      },
      {
        title: "Controller observes",
        projectState: "EXECUTING",
        flowStage: "OBSERVE",
        events: [{ kind: "observation", title: "System observed low workload", detail: "queue 2 · workload 29" }],
      },
      {
        title: "Adaptive decision",
        projectState: "EXECUTING",
        flowStage: "DECIDE",
        decision: {
          action: "CONTINUE",
          cycle: 1,
          workloadScore: 29,
          riskScore: 12,
          workloadLevel: "NORMAL",
          riskLevel: "NORMAL",
          reason: "Workload below the spawn threshold",
          affectedRole: null,
          affectedAgent: null,
          before: { activeForRole: 1, queue: 2, workload: 29, risk: 12 },
          after: { activeForRole: 1, queue: 2, workload: 29, risk: 12 },
        },
        events: [
          { kind: "decision", title: "Decision: CONTINUE", detail: "six-agent organization is sufficient" },
        ],
      },
      {
        title: "Execution completes",
        projectState: "EXECUTING",
        flowStage: "EXECUTE",
        agentStatus: { "QA-1": "ACTIVE", "SECURITY-1": "ACTIVE" },
        setTasks: {
          "TASK-2": { id: "TASK-2", status: "COMPLETED", assignedAgent: "BACKEND-1", completedAt: T0 },
          "TASK-3": { id: "TASK-3", status: "COMPLETED", assignedAgent: "FRONTEND-1", completedAt: T0 },
          "TASK-4": { id: "TASK-4", status: "RUNNING", assignedAgent: "QA-1", startedAt: T0 },
          "TASK-5": { id: "TASK-5", status: "RUNNING", assignedAgent: "SECURITY-1", startedAt: T0 },
        },
        events: [
          { kind: "quality", title: "QA and Security review", detail: "acceptance suites" },
        ],
      },
      {
        title: "Terminal state",
        projectState: "TERMINAL",
        flowStage: "ADAPT",
        setTasks: {
          "TASK-4": { id: "TASK-4", status: "COMPLETED", assignedAgent: "QA-1", completedAt: T0 },
          "TASK-5": { id: "TASK-5", status: "COMPLETED", assignedAgent: "SECURITY-1", completedAt: T0 },
        },
        events: [{ kind: "workflow", title: "Workflow completed", detail: "5/5 tasks terminal" }],
      },
    ],
    BASE_WORKLOAD,
    BASE_RISK,
  );

export const DEMO_SCRIPT = DEMO_LABEL;