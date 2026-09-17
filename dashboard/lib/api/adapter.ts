import type {
  OrgSnapshot,
  Agent,
  Task,
  AdaptiveDecision,
  TimelineEvent,
  MetricsSummary,
  WorkloadSnapshot,
  RiskSnapshot,
  RoleKey,
} from "../types";
import { isSpawnedId } from "../data/demo";
import type { RunStateResponse } from "./client";

function num(value: any, fallback = 0): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function eventKind(type: string): TimelineEvent["kind"] {
  if (type.includes("decision") || type.includes("adaptation")) return "decision";
  if (type.startsWith("agent") || type.includes("spawn") || type.includes("terminate"))
    return "agent";
  if (type.startsWith("task")) return "task";
  if (type.includes("quality") || type.includes("observation")) return "quality";
  return "workflow";
}

function eventTitle(e: any): string {
  const type = String(e.type || e.kind || "event");
  if (type === "workflow_started") return "Workflow started";
  if (type === "workflow_completed") return "Workflow completed";
  if (type === "task_created") return `Task created · ${e.task_id ?? ""}`.trim();
  if (type === "task_assigned")
    return `${e.task_id ?? "Task"} assigned to ${e.agent_id ?? "agent"}`;
  if (type === "task_started")
    return `${e.task_id ?? "Task"} started${e.agent_id ? ` by ${e.agent_id}` : ""}`;
  if (type === "task_completed")
    return `${e.task_id ?? "Task"} completed${e.agent_id ? ` by ${e.agent_id}` : ""}`;
  if (type === "task_failed") return `${e.task_id ?? "Task"} failed`;
  if (type === "adaptation_decision")
    return `Decision: ${e.decision ?? "CONTINUE"} · cycle ${e.cycle ?? 1}`;
  if (type === "agent_spawned") return `${e.agent_id ?? "Agent"} spawned`;
  if (type === "agent_terminated") return `${e.agent_id ?? "Agent"} terminated`;
  return type.replace(/_/g, " ");
}

function eventDetail(e: any): string | undefined {
  if (e.type === "workflow_started") return e.project_description;
  if (e.type === "adaptation_decision") return e.reason;
  if (e.type === "agent_spawned" || e.type === "agent_terminated")
    return e.role ? `role: ${e.role}` : undefined;
  if (e.type === "task_created")
    return [e.role, e.priority != null ? `priority ${e.priority}` : null]

      .filter(Boolean)
      .join(" · ") || undefined;
  if (e.role && (e.type.startsWith("task") || e.type.startsWith("agent")))
    return `role: ${e.role}`;
  return e.detail || e.message;
}

export function convertRunStateToSnapshot(
  runState: RunStateResponse,
  scenarioName: string,
): OrgSnapshot {
  const agents: Agent[] = (runState.agents || []).map((a: any) => ({
    agentId: a.agent_id || a.agentId,
    role: a.role as RoleKey,
    status: a.status,
    currentTask: a.current_task || a.currentTask || null,
    spawned: isSpawnedId(a.agent_id || a.agentId),
    meta: {
      tasksCompleted: 0,
      tasksFailed: 0,
      createdAt: new Date().toISOString(),
      workload: runState.workload?.score ?? 0,
      risk: runState.risk?.score ?? 0,
    },
    lifecycle: a.lifecycle || [a.status],
  }));

  const tasks: Task[] = (runState.tasks || []).map((t: any) => ({
    id: t.id,
    role: t.role as RoleKey,
    description: t.description || "",
    priority: t.priority ?? 1,
    complexity: t.complexity ?? 3,
    risk: t.risk ?? 20,
    status: t.status,
    assignedAgent: t.assigned_agent || t.assignedAgent || null,
    retryCount: t.retry_count ?? t.retryCount ?? 0,
    dependencies: t.dependencies || [],
    createdAt: t.created_at || t.createdAt || new Date().toISOString(),
    startedAt: t.started_at || t.startedAt || null,
    completedAt: t.completed_at || t.completedAt || null,
  }));

  const decisions: AdaptiveDecision[] = (runState.adaptive_decisions || []).map(
    (d: any) => {
      const prev = d.previous_state || {};
      const workloadScores: Record<string, number> = prev.workload_scores || {};
      const queue: Record<string, number> = prev.queue_length || {};
      const agentsByRole: Record<string, number> = prev.agents || {};
      const role =
        d.affected_role ||
        Object.entries(workloadScores).sort((a, b) => b[1] - a[1])[0]?.[0] ||
        null;

      const before = {
        activeForRole: num(agentsByRole[role as string], 0),
        queue: num(queue[role as string], 0),
        workload: num(workloadScores[role as string], num(d.workload_score, 0)),
        risk: num(prev.risk_score, num(d.risk_score, 0)),
      };

      let afterActive = before.activeForRole;
      if (d.decision === "SPAWN") afterActive = before.activeForRole + 1;
      if (d.decision === "TERMINATE")
        afterActive = Math.max(0, before.activeForRole - 1);

      return {
        action: d.decision,
        cycle: num(d.cycle, 1),
        timestamp: d.timestamp || new Date().toISOString(),
        workloadScore: num(d.workload_score, 0),
        riskScore: num(d.risk_score, 0),
        workloadLevel: d.workload_level || "NORMAL",
        riskLevel: d.risk_level || "NORMAL",
        reason: d.reason || "",
        affectedRole: d.affected_role || null,
        affectedAgent: d.affected_agent || null,
        before,
        after: { ...before, activeForRole: afterActive },
      };
    },
  );

  const latestDecision = decisions[decisions.length - 1] ?? null;

  const events: TimelineEvent[] = (runState.observability_events || []).map(
    (e: any, idx: number) => ({
      id: e.id || `evt-${idx + 1}`,
      time: e.timestamp || e.time || new Date().toISOString(),
      kind: eventKind(String(e.type || e.kind || "")),
      title: eventTitle(e),
      detail: eventDetail(e),
    }),
  );

  const rawMetrics = runState.metrics || {};
  const tMetrics = rawMetrics.task || {};
  const aMetrics = rawMetrics.agent || {};
  const adMetrics = rawMetrics.adaptive || {};

  const metrics: MetricsSummary = {
    totalTasks: tMetrics.total_tasks ?? tasks.length,
    completedTasks: tMetrics.completed_tasks ?? 0,
    failedTasks: tMetrics.failed_tasks ?? 0,
    totalExecutionSeconds: rawMetrics.timing?.duration_seconds ?? 0,
    averageTaskCompletionSeconds:
      tMetrics.average_task_completion_time_seconds ?? 0,
    queueWaitingSeconds: tMetrics.average_task_waiting_time_seconds ?? 0,
    initialAgents: aMetrics.initial_agent_count ?? 6,
    peakActiveAgents:
      aMetrics.peak_active_agents ??
      agents.filter((a) => a.status === "ACTIVE").length,
    averageActiveAgents:
      aMetrics.average_active_agents ??
      agents.filter((a) => a.status === "ACTIVE").length,
    agentUtilization: aMetrics.agent_utilization ?? 0,
    spawnEvents: adMetrics.spawn_events ?? 0,
    terminationEvents: adMetrics.termination_events ?? 0,
    reassignmentEvents: adMetrics.reassignment_events ?? 0,
    decisionsByType: adMetrics.decisions_by_type ?? {},
    cycleCount: adMetrics.adaptive_decision_count ?? decisions.length,
  };

  const workloadObj = runState.workload || {};
  const riskObj = runState.risk || {};
  const runningTasks = tasks.filter((t) => t.status === "RUNNING");

  const workload: WorkloadSnapshot = {
    queueLength:
      workloadObj.queueLength ??
      tasks.filter((t) =>
        ["PENDING", "ASSIGNED", "RUNNING", "RETRY"].includes(t.status),
      ).length,
    complexity: workloadObj.complexity ?? 0.42,
    executionDelay: workloadObj.executionDelay ?? 0.3,
    failureRate: workloadObj.failureRate ?? 0.12,
    score: workloadObj.score ?? 0,
    level: workloadObj.level ?? "NORMAL",
  };

  const risk: RiskSnapshot = {
    securityFindings: riskObj.securityFindings ?? 0,
    authIssues: riskObj.authIssues ?? 0,
    suspiciousCode: riskObj.suspiciousCode ?? 0,
    failedChecks: riskObj.failedChecks ?? 0,
    repeatedFailures: riskObj.repeatedFailures ?? 0,
    highRiskTasks: riskObj.highRiskTasks ?? 0,
    score: riskObj.score ?? 0,
    level: riskObj.level ?? "NORMAL",
  };

  return {
    projectState: runState.project_state || "EXECUTING",
    agents,
    tasks,
    workload,
    risk,
    observation: {
      queueLength: workload.queueLength,
      complexity: workload.complexity,
      executionDelay: workload.executionDelay,
      failureRate: workload.failureRate,
      activeAgents: agents.filter((a) => a.status === "ACTIVE").length,
    },
    latestDecision,
    decisions,
    events,
    metrics,
    flowStage: latestDecision ? "DECIDE" : null,
    justSpawned:
      latestDecision?.action === "SPAWN"
        ? latestDecision.affectedAgent
        : null,
    activeAgentId: runningTasks[0]?.assignedAgent || null,
    isDemo: false,
    title:
      runState.status === "completed" ? "Workflow completed" : "Live execution",
    narrative: latestDecision
      ? latestDecision.reason
      : "Ekatra running live via the FastAPI backend.",
    scenarioName,
  };
}
