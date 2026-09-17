const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export interface ApiScenario {
  scenario_id: string;
  name: string;
  description: string;
  project_description: string;
  task_count: number;
  expected_characteristics: Record<string, any>;
}

export interface RunCreateRequest {
  scenario_id: string;
  strategy: "fixed" | "adaptive";
}

export interface RunResponse {
  run_id: string;
  scenario_id: string;
  strategy: string;
  status: string;
}

export interface RunStateResponse {
  run_id: string;
  scenario_id: string;
  strategy: string;
  status: string;
  agents: any[];
  tasks: any[];
  adaptive_decisions: any[];
  workload: any;
  risk: any;
  communication: any[];
  tool_summary: any;
  observability_events: any[];
  metrics: any;
  project_state: string;
  error?: string | null;
}

export async function getHealth(): Promise<{ status: string }> {
  const res = await fetch(`${API_URL}/api/health`);
  if (!res.ok) throw new Error("Health check failed");
  return res.json();
}

export async function getScenarios(): Promise<ApiScenario[]> {
  const res = await fetch(`${API_URL}/api/scenarios`);
  if (!res.ok) throw new Error("Failed to fetch scenarios");
  return res.json();
}

export async function startRun(
  scenarioId: string,
  strategy: "fixed" | "adaptive",
): Promise<RunResponse> {
  const res = await fetch(`${API_URL}/api/runs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ scenario_id: scenarioId, strategy }),
  });
  if (!res.ok) throw new Error("Failed to start run");
  return res.json();
}

export async function getRun(runId: string): Promise<RunStateResponse> {
  const res = await fetch(`${API_URL}/api/runs/${runId}`);
  if (!res.ok) throw new Error("Failed to fetch run state");
  return res.json();
}

export async function getRunEvents(runId: string): Promise<any[]> {
  const res = await fetch(`${API_URL}/api/runs/${runId}/events`);
  if (!res.ok) throw new Error("Failed to fetch run events");
  return res.json();
}

export async function getRunMetrics(runId: string): Promise<any> {
  const res = await fetch(`${API_URL}/api/runs/${runId}/metrics`);
  if (!res.ok) throw new Error("Failed to fetch run metrics");
  return res.json();
}
