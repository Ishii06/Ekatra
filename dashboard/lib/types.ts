/**
 * Shared dashboard domain model.
 *
 * Mirrors the Ekatra backend structures (docs/01..08) so the UI can visualize
 * agent/task/observation/decision data without reimplementing orchestration.
 */

export type RoleKey =
  | "project_manager"
  | "architect"
  | "backend"
  | "frontend"
  | "qa"
  | "security";

export const ROLE_LABELS: Record<RoleKey, string> = {
  project_manager: "Project Manager",
  architect: "Architect",
  backend: "Backend Developer",
  frontend: "Frontend Developer",
  qa: "QA / Testing",
  security: "Security",
};

export type AgentStatus =
  | "CREATED"
  | "IDLE"
  | "ACTIVE"
  | "COMPLETED"
  | "TERMINATED";

export interface Agent {
  agentId: string;
  role: RoleKey;
  status: AgentStatus;
  currentTask: string | null;
  spawned: boolean;
  meta: {
    tasksCompleted: number;
    tasksFailed: number;
    createdAt: string;
    workload: number;
    risk: number;
    utilization?: number;
  };
  /** Lifecycle transitions observed so far, oldest first. */
  lifecycle: AgentStatus[];
}

export type TaskStatus =
  | "PENDING"
  | "ASSIGNED"
  | "RUNNING"
  | "COMPLETED"
  | "FAILED"
  | "RETRY";

export interface Task {
  id: string;
  role: RoleKey;
  description: string;
  priority: number;
  complexity: number;
  risk: number;
  status: TaskStatus;
  assignedAgent: string | null;
  retryCount: number;
  dependencies: string[];
  createdAt: string;
  startedAt?: string | null;
  completedAt?: string | null;
}

export type AdaptiveAction =
  | "CONTINUE"
  | "SPAWN"
  | "TERMINATE"
  | "REASSIGN"
  | "PRIORITIZE";

export type Level = "NORMAL" | "ELEVATED" | "HIGH";

export interface AdaptiveDecision {
  action: AdaptiveAction;
  cycle: number;
  timestamp: string;
  workloadScore: number;
  riskScore: number;
  workloadLevel: Level;
  riskLevel: Level;
  reason: string;
  affectedRole: RoleKey | null;
  affectedAgent: string | null;
  before: {
    activeForRole: number;
    queue: number;
    workload: number;
    risk: number;
  };
  after: {
    activeForRole: number;
    queue: number;
    workload: number;
    risk: number;
  };
}

export interface WorkloadSnapshot {
  queueLength: number;
  complexity: number;
  executionDelay: number;
  failureRate: number;
  score: number;
  level: Level;
  /**
   * Indicator keys the source data does not record (experiment runs only
   * persist the aggregate score). Rendered as "—" rather than a fake value.
   */
  unavailable?: string[];
}

export interface RiskSnapshot {
  securityFindings: number;
  authIssues: number;
  suspiciousCode: number;
  failedChecks: number;
  repeatedFailures: number;
  highRiskTasks: number;
  score: number;
  level: Level;
  unavailable?: string[];
}

export interface Observation {
  queueLength: number;
  complexity: number;
  executionDelay: number;
  failureRate: number;
  activeAgents: number;
}

export type TimelineKind =
  | "workflow"
  | "task"
  | "agent"
  | "observation"
  | "analysis"
  | "decision"
  | "allocation"
  | "quality";

export interface TimelineEvent {
  id: string;
  time: string;
  kind: TimelineKind;
  title: string;
  detail?: string;
}

export interface MetricsSummary {
  totalTasks: number;
  completedTasks: number;
  failedTasks: number;
  totalExecutionSeconds: number;
  averageTaskCompletionSeconds: number;
  queueWaitingSeconds: number;
  initialAgents: number;
  peakActiveAgents: number;
  averageActiveAgents: number;
  agentUtilization: number;
  spawnEvents: number;
  terminationEvents: number;
  reassignmentEvents: number;
  decisionsByType: Partial<Record<AdaptiveAction, number>>;
  cycleCount: number;
}

/** Full renderable snapshot of the system in one display moment. */
export interface OrgSnapshot {
  projectState: string;
  agents: Agent[];
  tasks: Task[];
  workload: WorkloadSnapshot;
  risk: RiskSnapshot;
  observation: Observation;
  latestDecision: AdaptiveDecision | null;
  decisions: AdaptiveDecision[];
  events: TimelineEvent[];
  metrics: MetricsSummary;
  /** Which stage of the adaptive loop is highlighted. */
  flowStage: FlowStage | null;
  /** Newly spawned agent id this frame (pulse emphasis). */
  justSpawned: string | null;
  /** Agent id currently executing (card emphasis). */
  activeAgentId?: string | null;
  /** True when this snapshot is simulated demo content. */
  isDemo: boolean;
  /** Short label for the current beat/step (presentation controls). */
  title?: string;
  /** Optional longer narrative for the current beat. */
  narrative?: string;
  /** Scenario display name, for provenance labels. */
  scenarioName?: string;
}

export type FlowStage =
  | "OBSERVE"
  | "ANALYZE"
  | "DECIDE"
  | "ALLOCATE"
  | "EXECUTE"
  | "EVALUATE"
  | "ADAPT";

export type Mode = "demo" | "experiment";
export type Strategy = "fixed" | "adaptive";

export interface ExperimentRun {
  runId: string;
  strategy: Strategy;
  scenarioId: string;
  scenarioName: string;
  projectDescription: string;
  startedAt: string | null;
  completedAt: string | null;
  metrics: MetricsSummary;
  decisions: AdaptiveDecision[];
  workloadSeries: { timestamp: string; score: number }[];
  riskSeries: { timestamp: string; score: number }[];
  events: TimelineEvent[];
  agents: Agent[];
  tasks: Task[];
  spawnedAgentIds: string[];
  terminatedAgentIds: string[];
}