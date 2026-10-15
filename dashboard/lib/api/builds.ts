import type { RunResponse, RunStateResponse } from "./client";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export interface BuildFile {
  path: string;
  bytes: number;
  area: "backend" | "frontend" | "docs" | "project";
  modified_at: string;
}

export interface BuildIssue {
  severity: "high" | "medium" | "low";
  owner: string;
  file: string;
  description: string;
}

/** The run state the dashboard already understands, plus build-only fields. */
export interface BuildStateResponse extends RunStateResponse {
  success: boolean | null;
  description: string;
  plan_source: string;
  version: number;
  elapsed_seconds: number;
  files: BuildFile[];
  log: string[];
  final_issues: BuildIssue[];
  out_dir: string;
}

export interface BuildSummary {
  run_id: string;
  description: string;
  strategy: string;
  status: string;
  started_at: number;
}

async function failure(res: Response, fallback: string): Promise<Error> {
  try {
    const body = await res.json();
    if (typeof body?.detail === "string") return new Error(body.detail);
    if (Array.isArray(body?.detail)) return new Error(body.detail[0]?.msg ?? fallback);
  } catch {
    /* fall through */
  }
  return new Error(fallback);
}

export async function startBuild(
  description: string,
  strategy: "fixed" | "adaptive",
  repairRounds = 1,
): Promise<RunResponse> {
  const res = await fetch(`${API_URL}/api/builds`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ description, strategy, repair_rounds: repairRounds }),
  });
  if (!res.ok) throw await failure(res, "Failed to start build");
  return res.json();
}

export async function listBuilds(): Promise<BuildSummary[]> {
  const res = await fetch(`${API_URL}/api/builds`);
  if (!res.ok) throw await failure(res, "Failed to list builds");
  return res.json();
}

export async function getBuild(buildId: string): Promise<BuildStateResponse> {
  const res = await fetch(`${API_URL}/api/builds/${buildId}`);
  if (!res.ok) throw await failure(res, "Failed to fetch build");
  return res.json();
}

export async function getBuildFile(
  buildId: string,
  path: string,
): Promise<{ path: string; content: string; bytes: number; truncated: boolean }> {
  const encoded = path.split("/").map(encodeURIComponent).join("/");
  const res = await fetch(`${API_URL}/api/builds/${buildId}/files/${encoded}`);
  if (!res.ok) throw await failure(res, "Failed to read file");
  return res.json();
}

/**
 * Follow a build over Server-Sent Events. Calls `onUpdate` with every state
 * snapshot, `onDone` once the build has finished, and `onError` if the
 * connection drops first. Returns a function that closes the stream.
 */
export function followBuild(
  buildId: string,
  handlers: {
    onUpdate: (state: BuildStateResponse) => void;
    onDone: () => void;
    onError: (message: string) => void;
  },
): () => void {
  const source = new EventSource(`${API_URL}/api/builds/${buildId}/stream`);
  let finished = false;
  source.onmessage = (event) => {
    try {
      handlers.onUpdate(JSON.parse(event.data) as BuildStateResponse);
    } catch {
      handlers.onError("Received an unreadable update from the backend");
    }
  };
  source.addEventListener("done", () => {
    finished = true;
    source.close();
    handlers.onDone();
  });
  source.onerror = () => {
    if (finished) return;
    source.close();
    handlers.onError("Lost connection to the backend");
  };
  return () => {
    finished = true;
    source.close();
  };
}
