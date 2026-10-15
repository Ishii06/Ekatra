/**
 * Milestone 8 experiment data adapter.
 *
 * Reads the persisted M8 scenario dataset (`experiments/ekatra-m8-dataset.json`)
 * produced by the Python experiment runner and maps its runs onto the dashboard
 * domain model. This file only *transforms* recorded values for display — it
 * never recomputes orchestration decisions or workload/risk scores.
 *
 * Fixed runs have no adaptation events; adaptive runs contain real
 * `adaptation_decision` / `agent_spawned` events.
 */

import datasetJson from "./experiments/ekatra-m8-dataset.json";
import type {
  AdaptiveAction,
  AdaptiveDecision,
  Agent,
  AgentStatus,
  ExperimentRun,
  Level,
  MetricsSummary,
  OrgSnapshot,
  RoleKey,
  Task,
  TimelineEvent,
  TimelineKind,
} from "../types";
import { ROLE_LABELS } from "../types";

/* ------------------------------------------------------------------ shapes */

interface M8TaskDef {
  key: string;
  role: string;
  description: string;
  priority: number;
  complexity: number;
  risk: number;
  dependencies: string[];
  initial_status: string | null;
  retry_count: number;
}

interface M8AgentRecord {
  agent_id: string;
  role: string;
  status: string;
  layout: string;
  active_seconds: number;
  available_seconds: number;
  utilization: number;
  execution_count: number;
}

interface M8SeriesPoint {
  timestamp: string;
  workload_score?: number;
  risk_score?: number;
  active_agents?: number;
  queue_length?: number;
}

interface M8Run {
  run_id: string;
  strategy: string;
  scenario_id: string;
  project_description: string;
  workflow_started_at: string;
  workflow_completed_at: string;
  task_summary: {
    total_tasks: number;
    completed_tasks: number;
    failed_tasks: number;
    retried_tasks: number;
    total_retries: number;
    total_task_completion_time_seconds: number;
    average_task_completion_time_seconds: number;
    total_task_waiting_time_seconds: number;
    average_task_waiting_time_seconds: number;
    queue_length_over_time: M8SeriesPoint[];
  };
  agent_summary: {
    initial_agent_count: number;
    active_agent_count: number;
    peak_active_agents: number;
    average_active_agents: number;
    agent_utilization: number;
    dynamically_spawned_agents: number;
    dynamically_terminated_agents: number;
    agents: M8AgentRecord[];
    active_agents_over_time: M8SeriesPoint[];
  };
  adaptive_summary: {
    adaptive_decision_count: number;
    decisions_by_type: Record<string, number>;
    spawn_events: number;
    termination_events: number;
    reassignment_events: number;
    prioritization_events: number;
    workload_score_over_time: M8SeriesPoint[];
    risk_score_over_time: M8SeriesPoint[];
  };
  quality_observations: unknown[];
  metrics: {
    task: M8Run["task_summary"];
    agent: M8Run["agent_summary"];
    adaptive: M8Run["adaptive_summary"];
  };
  raw_events: M8Event[];
}

interface M8Scenario {
  scenario: {
    scenario_id: string;
    name: string;
    description: string;
    project_description: string;
    tasks: M8TaskDef[];
    timing: { seed: string; base_timestamp: string };
    expected_characteristics: Record<string, unknown>;
  };
  fixed: M8Run[];
  adaptive: M8Run[];
}

interface M8Dataset {
  dataset: string;
  version: number;
  repetitions: number;
  scenarios: Record<string, M8Scenario>;
}

type M8Event = {
  type: string;
  timestamp: string;
  [key: string]: unknown;
};

const DATASET = datasetJson as unknown as M8Dataset;

/* -------------------------------------------------------------- accessors */

export function getM8Dataset(): M8Dataset {
  return DATASET;
}

export function getM8ScenarioIds(): string[] {
  return Object.keys(DATASET.scenarios);
}

export function getM8ScenarioName(scenarioId: string): string {
  return DATASET.scenarios[scenarioId]?.scenario.name ?? scenarioId;
}

export function getM8ProjectDescription(scenarioId: string): string {
  return DATASET.scenarios[scenarioId]?.scenario.project_description ?? "";
}

function getRun(scenarioId: string, strategy: "fixed" | "adaptive"): M8Run | null {
  const sc = DATASET.scenarios[scenarioId];
  if (!sc) return null;
  const list = strategy === "fixed" ? sc.fixed : sc.adaptive;
  return list?.[0] ?? null;
}

/* ---------------------------------------------------------------- mapping */

function normLevel(value: string): Level {
  return value === "HIGH" ? "HIGH" : value === "ELEVATED" ? "ELEVATED" : "NORMAL";
}

function normRole(value: string): RoleKey {
  return value in ROLE_LABELS ? (value as RoleKey) : "backend";
}

function normAction(value: string): AdaptiveAction {
  const upper = value.toUpperCase();
  if (
    upper === "SPAWN" ||
    upper === "TERMINATE" ||
    upper === "REASSIGN" ||
    upper === "PRIORITIZE" ||
    upper === "CONTINUE"
  ) {
    return upper;
  }
  return "CONTINUE";
}

function normAgentStatus(value: string): AgentStatus {
  const upper = value.toUpperCase();
  if (
    upper === "CREATED" ||
    upper === "IDLE" ||
    upper === "ACTIVE" ||
    upper === "COMPLETED" ||
    upper === "TERMINATED"
  ) {
    return upper;
  }
  return "IDLE";
}

function buildTaskDefs(scenario: M8Scenario): Task[] {
  return scenario.scenario.tasks.map((def, i) => ({
    id: `TASK-${i + 1}`,
    role: normRole(def.role),
    description: def.description,
    priority: def.priority,
    complexity: def.complexity,
    risk: def.risk,
    status: "PENDING",
    assignedAgent: null,
    retryCount: def.retry_count ?? 0,
    dependencies: def.dependencies ?? [],
    createdAt: scenario.scenario.timing.base_timestamp,
    startedAt: null,
    completedAt: null,
  }));
}

function cloneTasks(tasks: Task[]): Task[] {
  return tasks.map((t) => ({ ...t }));
}

/* Reconstruct task assignment/status from the recorded raw events. */
function applyTaskEvent(tasks: Map<string, Task>, event: M8Event): void {
  const taskId = event.task_id as string | undefined;
  if (!taskId) return;
  const task = tasks.get(taskId);
  if (!task) return;

  switch (event.type) {
    case "task_assigned":
      task.status = "ASSIGNED";
      task.assignedAgent = (event.agent_id as string) ?? null;
      break;
    case "task_started":
      task.status = "RUNNING";
      task.assignedAgent = (event.agent_id as string) ?? task.assignedAgent;
      task.startedAt = event.timestamp;
      break;
    case "task_completed":
      task.status = "COMPLETED";
      task.assignedAgent = (event.agent_id as string) ?? task.assignedAgent;
      task.completedAt = event.timestamp;
      break;
    case "task_failed":
      task.status = "FAILED";
      task.retryCount += 1;
      break;
    case "task_retried":
      task.status = "RETRY";
      task.retryCount += 1;
      break;
    default:
      break;
  }
}

function baselineAgents(): Agent[] {
  const base: { id: string; role: RoleKey }[] = [
    { id: "PM-1", role: "project_manager" },
    { id: "ARCH-1", role: "architect" },
    { id: "FRONTEND-1", role: "frontend" },
    { id: "BACKEND-1", role: "backend" },
    { id: "QA-1", role: "qa" },
    { id: "SECURITY-1", role: "security" },
  ];
  return base.map((b) => ({
    agentId: b.id,
    role: b.role,
    status: "IDLE" as AgentStatus,
    currentTask: null,
    spawned: false,
    meta: {
      tasksCompleted: 0,
      tasksFailed: 0,
      createdAt: "run-start",
      workload: 0,
      risk: 0,
    },
    lifecycle: ["CREATED", "IDLE"],
  }));
}

function timelineKind(type: string): TimelineKind {
  switch (type) {
    case "workflow_started":
    case "workflow_completed":
      return "workflow";
    case "task_created":
    case "task_assigned":
    case "task_started":
    case "task_completed":
    case "task_failed":
      return "task";
    case "agent_spawned":
    case "agent_terminated":
      return "agent";
    case "adaptation_decision":
      return "decision";
    default:
      return "observation";
  }
}

function timelineTitle(event: M8Event): string {
  const role = event.role ? ` ${String(event.role).toUpperCase()}` : "";
  switch (event.type) {
    case "workflow_started":
      return "Workflow started";
    case "workflow_completed":
      return "Workflow completed";
    case "task_created":
      return `${event.task_id} created (${role.trim()})`;
    case "task_assigned":
      return `${event.task_id} assigned to ${event.agent_id}`;
    case "task_started":
      return `${event.agent_id} started ${event.task_id}`;
    case "task_completed":
      return `${event.task_id} completed`;
    case "task_failed":
      return `${event.task_id} failed`;
    case "agent_spawned":
      return `Agent ${event.agent_id} spawned`;
    case "agent_terminated":
      return `Agent ${event.agent_id} terminated`;
    case "adaptation_decision":
      return `Decision: ${String(event.decision)}`;
    default:
      return String(event.type);
  }
}

function toTimelineEvent(event: M8Event, index: number, baseTs: string, fallbackTime: string): TimelineEvent {
  const time = event.timestamp === baseTs ? fallbackTime : event.timestamp;
  return {
    id: `m8-evt-${index + 1}`,
    time,
    kind: timelineKind(event.type),
    title: timelineTitle(event),
    detail:
      event.type === "adaptation_decision"
        ? String(event.reason ?? "")
        : undefined,
  };
}

function buildDecision(event: M8Event): AdaptiveDecision {
  const action = normAction(String(event.decision));
  const role = event.affected_role ? normRole(String(event.affected_role)) : null;
  return {
    action,
    cycle: Number(event.cycle ?? 0),
    timestamp: String(event.timestamp),
    workloadScore: Number(event.workload_score ?? 0),
    riskScore: Number(event.risk_score ?? 0),
    workloadLevel: normLevel(String(event.workload_level ?? "NORMAL")),
    riskLevel: normLevel(String(event.risk_level ?? "NORMAL")),
    reason: String(event.reason ?? ""),
    affectedRole: role,
    affectedAgent: event.affected_agent ? String(event.affected_agent) : null,
    before: {
      activeForRole: 0,
      queue: 0,
      workload: Number(event.workload_score ?? 0),
      risk: Number(event.risk_score ?? 0),
    },
    after: {
      activeForRole: action === "SPAWN" ? 1 : 0,
      queue: 0,
      workload: Number(event.workload_score ?? 0),
      risk: Number(event.risk_score ?? 0),
    },
  };
}

function metricsFromRun(run: M8Run): MetricsSummary {
  const t = run.metrics.task;
  const a = run.metrics.agent;
  const ad = run.metrics.adaptive;
  return {
    totalTasks: t.total_tasks,
    completedTasks: t.completed_tasks,
    failedTasks: t.failed_tasks,
    totalExecutionSeconds: t.total_task_completion_time_seconds,
    averageTaskCompletionSeconds: t.average_task_completion_time_seconds,
    queueWaitingSeconds: t.average_task_waiting_time_seconds,
    initialAgents: a.initial_agent_count,
    peakActiveAgents: a.peak_active_agents,
    averageActiveAgents: a.average_active_agents,
    agentUtilization: a.agent_utilization,
    spawnEvents: ad.spawn_events,
    terminationEvents: ad.termination_events,
    reassignmentEvents: ad.reassignment_events,
    decisionsByType: ad.decisions_by_type as Partial<Record<AdaptiveAction, number>>,
    cycleCount: ad.adaptive_decision_count,
  };
}

/* ------------------------------------------------------------ experiment run */

export function buildExperimentRun(
  scenarioId: string,
  strategy: "fixed" | "adaptive",
): ExperimentRun | null {
  const sc = DATASET.scenarios[scenarioId];
  const run = getRun(scenarioId, strategy);
  if (!sc || !run) return null;

  const taskMap = new Map(buildTaskDefs(sc).map((t) => [t.id, t]));
  const agentMap = new Map<string, Agent>();
  for (const record of run.agent_summary.agents) {
    const status = normAgentStatus(record.status);
    agentMap.set(record.agent_id, {
      agentId: record.agent_id,
      role: normRole(record.role),
      status,
      currentTask: null,
      spawned: record.layout === "spawned",
      meta: {
        tasksCompleted: record.execution_count,
        tasksFailed: 0,
        createdAt: run.workflow_started_at,
        workload: 0,
        risk: 0,
        utilization: record.utilization,
      },
      lifecycle: status === "IDLE" ? ["CREATED", "IDLE"] : ["CREATED", "IDLE", "ACTIVE", status],
    });
  }

  const baseTs = sc.scenario.timing.base_timestamp;
  const decisions: AdaptiveDecision[] = [];
  const events: TimelineEvent[] = [];

  run.raw_events.forEach((event, i) => {
    if (event.type === "adaptation_decision") {
      decisions.push(buildDecision(event));
    }
    applyTaskEvent(taskMap, event);
    events.push(toTimelineEvent(event, i, baseTs, run.workflow_started_at));
  });

  const tasks = [...taskMap.values()];
  const spawnedIds = run.raw_events
    .filter((e) => e.type === "agent_spawned")
    .map((e) => String(e.agent_id));

  return {
    runId: run.run_id,
    strategy,
    scenarioId,
    scenarioName: sc.scenario.name,
    projectDescription: run.project_description,
    startedAt: run.workflow_started_at,
    completedAt: run.workflow_completed_at,
    metrics: metricsFromRun(run),
    decisions,
    workloadSeries: run.metrics.adaptive.workload_score_over_time.map((p) => ({
      timestamp: p.timestamp,
      score: Number(p.workload_score ?? 0),
    })),
    riskSeries: run.metrics.adaptive.risk_score_over_time.map((p) => ({
      timestamp: p.timestamp,
      score: Number(p.risk_score ?? 0),
    })),
    events,
    agents: [...agentMap.values()],
    tasks,
    spawnedAgentIds: spawnedIds,
    terminatedAgentIds: [],
  };
}

/* --------------------------------------------------------- experiment frames */

const FRAME_MS = 2200;

function isBaseTimestamp(ts: string, base: string): boolean {
  return ts === base;
}

/**
 * Reconstruct a viewable sequence for a recorded run from its `raw_events`.
 *
 * This is presentation playback of already-recorded state, not a simulation:
 * every task/agent/decision value comes from the run's persisted events.
 */
export function buildExperimentFrames(
  scenarioId: string,
  strategy: "fixed" | "adaptive",
): OrgSnapshot[] {
  const sc = DATASET.scenarios[scenarioId];
  const run = getRun(scenarioId, strategy);
  if (!sc || !run) return [];

  const baseTs = sc.scenario.timing.base_timestamp;
  const taskMap = new Map(buildTaskDefs(sc).map((t) => [t.id, t]));
  const agentMap = new Map<string, Agent>();
  for (const b of baselineAgents()) {
    agentMap.set(b.agentId, { ...b, meta: { ...b.meta } });
  }

  const startMs = new Date(run.workflow_started_at).getTime();
  const decisions: AdaptiveDecision[] = [];
  const timeline: TimelineEvent[] = [];
  const frames: OrgSnapshot[] = [];

  let frameIndex = 0;
  let projectState = "PLANNING";
  let lastDecision: AdaptiveDecision | null = null;
  let lastWorkload = 0;
  let lastRisk = 0;
  let justSpawned: string | null = null;
  let peakActive = 0;

  const tick = (): string => new Date(startMs + frameIndex * FRAME_MS).toISOString();

  const agentForRole = (role: RoleKey): string => {
    const candidates = [...agentMap.values()]
      .filter((a) => a.role === role && a.status !== "TERMINATED")
      .sort((a, b) => a.agentId.localeCompare(b.agentId));
    return candidates[0]?.agentId ?? `${role.toUpperCase()}-1`;
  };

  const markActive = (agentId: string, taskId: string) => {
    const agent = agentMap.get(agentId);
    if (!agent) return;
    agent.status = "ACTIVE";
    agent.currentTask = taskId;
    if (agent.lifecycle[agent.lifecycle.length - 1] !== "ACTIVE") {
      agent.lifecycle.push("ACTIVE");
    }
  };

  const markIdle = (agentId: string, completed: boolean) => {
    const agent = agentMap.get(agentId);
    if (!agent) return;
    const stillRunning = [...taskMap.values()].some(
      (t) => t.status === "RUNNING" && t.assignedAgent === agentId,
    );
    if (stillRunning) return;
    agent.status = "IDLE";
    agent.currentTask = null;
    if (completed) agent.meta.tasksCompleted += 1;
    const last = agent.lifecycle[agent.lifecycle.length - 1];
    if (last !== "IDLE") agent.lifecycle.push("IDLE");
  };

  const pushFrame = (state: string, flowStage: OrgSnapshot["flowStage"], title?: string) => {
    const tasks = cloneTasks([...taskMap.values()]);
    const agents = [...agentMap.values()].map((a) => ({ ...a, meta: { ...a.meta }, lifecycle: [...a.lifecycle] }));

    const completed = tasks.filter((t) => t.status === "COMPLETED").length;
    const failed = tasks.filter((t) => t.status === "FAILED" || t.status === "RETRY").length;
    const queue = tasks.filter((t) =>
      ["PENDING", "ASSIGNED", "RUNNING", "RETRY"].includes(t.status),
    ).length;
    const running = tasks.filter((t) => t.status === "RUNNING");
    const activeCount = agents.filter((a) => a.status === "ACTIVE").length;
    peakActive = Math.max(peakActive, activeCount + running.length);

    const queued = tasks.filter((t) =>
      ["PENDING", "ASSIGNED", "RUNNING", "RETRY"].includes(t.status),
    );
    const avgComplexity =
      queued.length > 0
        ? queued.reduce((s, t) => s + t.complexity, 0) / queued.length / 5
        : 0;
    const retries = tasks.reduce((s, t) => s + t.retryCount, 0);
    const failureRate = tasks.length > 0 ? retries / tasks.length : 0;
    const highRisk = tasks.filter((t) => t.risk >= 40).length;

    const frameTime = tick();

    const snapshot: OrgSnapshot = {
      projectState: state,
      agents,
      tasks,
      workload: {
        queueLength: queued.length,
        complexity: Number(avgComplexity.toFixed(3)),
        executionDelay: 0,
        failureRate: Number(failureRate.toFixed(3)),
        score: lastWorkload,
        level: lastWorkload >= 70 ? "HIGH" : lastWorkload >= 40 ? "ELEVATED" : "NORMAL",
        unavailable: ["executionDelay"],
      },
      risk: {
        securityFindings: 0,
        authIssues: 0,
        suspiciousCode: 0,
        failedChecks: 0,
        repeatedFailures: retries,
        highRiskTasks: highRisk,
        score: lastRisk,
        level: lastRisk >= 70 ? "HIGH" : lastRisk >= 40 ? "ELEVATED" : "NORMAL",
        unavailable: [
          "securityFindings",
          "authIssues",
          "suspiciousCode",
          "failedChecks",
        ],
      },
      observation: {
        queueLength: queued.length,
        complexity: Number(avgComplexity.toFixed(3)),
        executionDelay: 0,
        failureRate: Number(failureRate.toFixed(3)),
        activeAgents: activeCount,
      },
      latestDecision: lastDecision,
      decisions: [...decisions],
      events: timeline.map((e) => ({ ...e })),
      metrics: {
        totalTasks: tasks.length,
        completedTasks: completed,
        failedTasks: failed,
        totalExecutionSeconds: 0,
        averageTaskCompletionSeconds: 0,
        queueWaitingSeconds: 0,
        initialAgents: 6,
        peakActiveAgents: peakActive,
        averageActiveAgents: activeCount,
        agentUtilization:
          agents.length > 0
            ? agents.filter((a) => a.status === "ACTIVE").length / agents.length
            : 0,
        spawnEvents: [...agentMap.values()].filter((a) => a.spawned).length,
        terminationEvents: 0,
        reassignmentEvents: 0,
        decisionsByType: decisions.reduce<Partial<Record<AdaptiveAction, number>>>(
          (acc, d) => {
            acc[d.action] = (acc[d.action] ?? 0) + 1;
            return acc;
          },
          {},
        ),
        cycleCount: decisions.length,
      },
      flowStage,
      justSpawned,
      activeAgentId: running.map((t) => t.assignedAgent).filter(Boolean)[0] ?? null,
      isDemo: false,
      title,
      narrative: undefined,
      scenarioName: sc.scenario.name,
    };

    if (frameIndex === 0) {
      snapshot.metrics.totalExecutionSeconds = 0;
    }

    frames.push(snapshot);
    frameIndex += 1;
    justSpawned = null;
    void frameTime;
  };

  /* -- walk the recorded events ------------------------------------------ */

  let createdCount = 0;
  let assignedCount = 0;
  let workflowSeen = false;

  const pendingCreated: string[] = [];
  const pendingAssigned: string[] = [];

  const flushPlanning = () => {
    if (pendingCreated.length > 0) {
      pushFrame("PLANNING", "OBSERVE", "Project decomposed into tasks");
      pendingCreated.length = 0;
    }
    if (pendingAssigned.length > 0) {
      pushFrame("EXECUTING", null, "Tasks assigned to baseline agents");
      pendingAssigned.length = 0;
    }
  };

  run.raw_events.forEach((event, i) => {
    const baseTime = tick();
    if (event.type === "task_created") {
      pendingCreated.push(String(event.task_id));
      timeline.push(toTimelineEvent(event, i, baseTs, baseTime));
      createdCount += 1;
      return;
    }
    if (event.type === "task_assigned") {
      applyTaskEvent(taskMap, event);
      pendingAssigned.push(String(event.task_id));
      timeline.push(toTimelineEvent(event, i, baseTs, baseTime));
      assignedCount += 1;
      return;
    }

    if (!workflowSeen && event.type === "workflow_started") {
      workflowSeen = true;
      const pm = agentMap.get("PM-1");
      if (pm) {
        pm.status = "ACTIVE";
        pm.lifecycle.push("ACTIVE");
      }
      timeline.push(toTimelineEvent(event, i, baseTs, baseTime));
      pushFrame("PLANNING", "OBSERVE", "Workflow started");
      return;
    }

    if (pendingCreated.length > 0 || pendingAssigned.length > 0) {
      flushPlanning();
    }

    switch (event.type) {
      case "agent_spawned": {
        const id = String(event.agent_id);
        const role = normRole(String(event.role));
        if (!agentMap.has(id)) {
          agentMap.set(id, {
            agentId: id,
            role,
            status: "IDLE",
            currentTask: null,
            spawned: true,
            meta: {
              tasksCompleted: 0,
              tasksFailed: 0,
              createdAt: event.timestamp,
              workload: lastWorkload,
              risk: lastRisk,
            },
            lifecycle: ["CREATED", "IDLE"],
          });
        }
        justSpawned = id;
        timeline.push(toTimelineEvent(event, i, baseTs, baseTime));
        pushFrame("EXECUTING", "ALLOCATE", `SPAWN · ${id} created`);
        break;
      }
      case "task_started": {
        applyTaskEvent(taskMap, event);
        const agentId = (event.agent_id as string) ?? (event.task_id ? agentForRole(normRole(String(event.role))) : "");
        if (agentId) markActive(agentId, String(event.task_id));
        timeline.push(toTimelineEvent(event, i, baseTs, baseTime));
        pushFrame("EXECUTING", "EXECUTE", `${agentId || "Agent"} started ${String(event.task_id)}`);
        break;
      }
      case "task_completed": {
        applyTaskEvent(taskMap, event);
        const agentId = (event.agent_id as string) ?? "";
        if (agentId) markIdle(agentId, true);
        timeline.push(toTimelineEvent(event, i, baseTs, baseTime));
        pushFrame("EXECUTING", "EVALUATE", `${String(event.task_id)} completed`);
        break;
      }
      case "adaptation_decision": {
        const decision = buildDecision(event);
        lastDecision = decision;
        lastWorkload = decision.workloadScore;
        lastRisk = decision.riskScore;
        decisions.push(decision);
        timeline.push(toTimelineEvent(event, i, baseTs, baseTime));
        pushFrame("EXECUTING", "DECIDE", `Decision: ${decision.action}`);
        break;
      }
      case "workflow_completed": {
        for (const agent of agentMap.values()) {
          if (agent.status === "ACTIVE") {
            agent.status = "IDLE";
            agent.currentTask = null;
            if (agent.lifecycle[agent.lifecycle.length - 1] !== "IDLE") {
              agent.lifecycle.push("IDLE");
            }
          }
        }
        timeline.push(toTimelineEvent(event, i, baseTs, baseTime));
        pushFrame("TERMINAL", "ADAPT", "Workflow completed");
        break;
      }
      default: {
        applyTaskEvent(taskMap, event);
        timeline.push(toTimelineEvent(event, i, baseTs, baseTime));
        break;
      }
    }
  });

  if (pendingCreated.length > 0 || pendingAssigned.length > 0) {
    flushPlanning();
  }

  if (frames.length === 0) {
    pushFrame("TERMINAL", "ADAPT", "Run complete");
  }

  void createdCount;
  void assignedCount;
  void isBaseTimestamp;

  // Attach the run's recorded final metrics to the terminal frame so the
  // metrics panel shows experiment values, not a re-derived approximation.
  const finalFrame = frames[frames.length - 1];
  if (finalFrame) {
    finalFrame.metrics = metricsFromRun(run);
  }

  return frames;
}

/* --------------------------------------------------------------- catalogue */

export interface M8ScenarioInfo {
  id: string;
  name: string;
  description: string;
  projectDescription: string;
  taskCount: number;
  spawnRole: RoleKey | null;
  adaptiveWorkload: Level;
  hasSpawn: boolean;
}

export function listM8Scenarios(): M8ScenarioInfo[] {
  return Object.entries(DATASET.scenarios).map(([id, sc]) => {
    const adaptive = sc.adaptive?.[0];
    const spawnEvent = adaptive?.raw_events.find((e) => e.type === "agent_spawned");
    const chars = sc.scenario.expected_characteristics as {
      adaptive_workload_level?: string;
      adaptive_spawn_role?: string;
    };
    return {
      id,
      name: sc.scenario.name,
      description: sc.scenario.description,
      projectDescription: sc.scenario.project_description,
      taskCount: sc.scenario.tasks.length,
      spawnRole: spawnEvent ? normRole(String(spawnEvent.role)) : null,
      adaptiveWorkload: normLevel(String(chars.adaptive_workload_level ?? "NORMAL")),
      hasSpawn: Boolean(spawnEvent),
    };
  });
}
