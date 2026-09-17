"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import type {
  Level,
  Mode,
  OrgSnapshot,
  RoleKey,
  Strategy,
  TaskStatus,
} from "./types";
import { buildDemoFrames } from "./data/demo";
import {
  buildExperimentFrames,
  listM8Scenarios,
  type M8ScenarioInfo,
} from "./data/m8";
import {
  DEFAULT_SCENARIO_ID,
  SCENARIOS,
  scenarioById,
  type ScenarioDef,
} from "./data/scenarios";

import { getHealth, getScenarios, startRun, getRun } from "./api/client";
import { convertRunStateToSnapshot } from "./api/adapter";
import type { ApiScenario } from "./api/client";

export type DataSource = "demo" | "experiment" | "live";

export const ALL_TASK_STATUSES: TaskStatus[] = [
  "PENDING",
  "ASSIGNED",
  "RUNNING",
  "COMPLETED",
  "FAILED",
  "RETRY",
];

interface DashboardValue {
  /* data source + scenario */
  mode: DataSource;
  setMode: (mode: DataSource) => void;
  scenario: ScenarioDef;
  scenarioId: string;
  setScenarioId: (id: string) => void;
  scenarios: ScenarioDef[];
  m8Scenarios: M8ScenarioInfo[];
  strategy: Strategy;
  setStrategy: (s: Strategy) => void;

  /* playback */
  frames: OrgSnapshot[];
  frame: OrgSnapshot | null;
  frameIndex: number;
  totalFrames: number;
  playing: boolean;
  intervalMs: number;
  play: () => void;
  pause: () => void;
  toggle: () => void;
  reset: () => void;
  stepForward: () => void;
  stepBack: () => void;
  jumpTo: (index: number) => void;
  atEnd: boolean;
  atStart: boolean;

  /* selection + filters */
  selectedAgentId: string | null;
  selectAgent: (id: string | null) => void;
  visibleStatuses: TaskStatus[];
  toggleStatus: (status: TaskStatus) => void;
  showAllStatuses: () => void;
  selectedTaskId: string | null;
  selectTask: (id: string | null) => void;

  /* provenance */
  isDemo: boolean;
  isLive: boolean;
  provenanceLabel: string;
  spawnRole: RoleKey | null;
  liveError: string | null;
}

const DashboardContext = createContext<DashboardValue | null>(null);

const DEMO_INTERVAL_MS = 2800;
const EXPERIMENT_INTERVAL_MS = 1600;
const LIVE_POLL_MS = 800;

export function DashboardProvider({ children }: { children: React.ReactNode }) {
  const [mode, setMode] = useState<DataSource>("demo");
  const [scenarioId, setScenarioId] = useState<string>(DEFAULT_SCENARIO_ID);
  const [strategy, setStrategy] = useState<Strategy>("adaptive");
  const [frameIndex, setFrameIndex] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [selectedAgentId, setSelectedAgentId] = useState<string | null>(null);
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);
  const [visibleStatuses, setVisibleStatuses] = useState<TaskStatus[]>(
    ALL_TASK_STATUSES,
  );

  const m8Scenarios = useMemo(() => listM8Scenarios(), []);
  const [liveSnapshot, setLiveSnapshot] = useState<OrgSnapshot | null>(null);
  const [liveSnapshotKey, setLiveSnapshotKey] = useState<string | null>(null);
  const [liveScenarios, setLiveScenarios] = useState<ApiScenario[]>([]);
  const [liveError, setLiveError] = useState<string | null>(null);

  /* In live mode the scenario catalogue is served by the FastAPI backend. */
  const scenarios = useMemo<ScenarioDef[]>(() => {
    if (mode === "live" && liveScenarios.length > 0) {
      return liveScenarios.map((s) => {
        const expected = s.expected_characteristics ?? {};
        return {
          id: s.scenario_id,
          name: s.name,
          short: s.name,
          description: s.description,
          spawnRole: (expected.adaptive_spawn_role ?? null) as RoleKey | null,
          risk: (expected.adaptive_risk_level ?? "NORMAL") as Level,
          workload: (expected.adaptive_workload_level ?? "NORMAL") as Level,
          demo: false,
        };
      });
    }
    return SCENARIOS;
  }, [mode, liveScenarios]);

  const scenario = useMemo(
    () =>
      scenarios.find((s) => s.id === scenarioId) ??
      scenarios[0] ??
      scenarioById(scenarioId),
    [scenarios, scenarioId],
  );

  /* Probe backend connectivity and load scenarios when live mode is entered. */
  useEffect(() => {
    if (mode !== "live") return;
    let cancelled = false;
    getHealth()
      .then(() => getScenarios())
      .then((list) => {
        if (!cancelled) {
          setLiveScenarios(list);
          setLiveError(null);
        }
      })
      .catch((e: unknown) => {
        if (!cancelled) {
          setLiveError(
            e instanceof Error ? e.message : "Backend unavailable",
          );
        }
      });
    return () => {
      cancelled = true;
    };
  }, [mode]);

  useEffect(() => {
    if (mode !== "live") return;
    let cancelled = false;
    let timer: number | null = null;

    async function runLive() {
      try {
        const started = await startRun(scenarioId, strategy);
        const runId = started.run_id;

        async function poll() {
          if (cancelled) return;
          try {
            const stateRes = await getRun(runId);
            if (!cancelled) {
              const snapshot = convertRunStateToSnapshot(stateRes, scenario.name);
              setLiveSnapshot(snapshot);
              setLiveSnapshotKey(`${scenarioId}|${strategy}`);
              setLiveError(null);
              if (stateRes.status === "completed" || stateRes.status === "failed") {
                setPlaying(false);
                return;
              }
            }
          } catch (e) {
            if (!cancelled) {
              setLiveError(
                e instanceof Error ? e.message : "Lost connection to backend",
              );
              setPlaying(false);
            }
            return;
          }
          if (playing && !cancelled) {
            timer = window.setTimeout(poll, LIVE_POLL_MS);
          }
        }

        poll();
      } catch (e) {
        if (!cancelled) {
          setLiveError(
            e instanceof Error ? e.message : "Failed to start live run",
          );
          setPlaying(false);
        }
      }
    }

    if (playing) {
      runLive();
    }

    return () => {
      cancelled = true;
      if (timer) window.clearTimeout(timer);
    };
  }, [mode, scenarioId, strategy, playing, scenario.name]);

  const frames = useMemo<OrgSnapshot[]>(() => {
    if (mode === "experiment") {
      return buildExperimentFrames(scenarioId, strategy);
    }
    if (mode === "live") {
      const keyMatches = liveSnapshotKey === `${scenarioId}|${strategy}`;
      return keyMatches && liveSnapshot ? [liveSnapshot] : [];
    }
    return buildDemoFrames(scenarioId);
  }, [mode, scenarioId, strategy, liveSnapshot, liveSnapshotKey]);

  const totalFrames = frames.length;
  const intervalMs =
    mode === "demo"
      ? DEMO_INTERVAL_MS
      : mode === "live"
        ? LIVE_POLL_MS
        : EXPERIMENT_INTERVAL_MS;

  /* Reset playback whenever the underlying sequence changes. Live frames are
     replaced on each poll, so playback state must survive them. */
  useEffect(() => {
    if (mode === "live") return;
    setFrameIndex(0);
    setPlaying(false);
    setSelectedAgentId(null);
    setSelectedTaskId(null);
  }, [frames, mode]);

  /* Clamp index defensively. */
  useEffect(() => {
    if (frameIndex > totalFrames - 1) {
      setFrameIndex(Math.max(0, totalFrames - 1));
    }
  }, [frameIndex, totalFrames]);

  /* Auto-advance. */
  useEffect(() => {
    if (!playing || totalFrames <= 1) return;
    if (frameIndex >= totalFrames - 1) {
      setPlaying(false);
      return;
    }
    const id = window.setInterval(() => {
      setFrameIndex((i) => {
        if (i >= totalFrames - 1) {
          setPlaying(false);
          return i;
        }
        return i + 1;
      });
    }, intervalMs);
    return () => window.clearInterval(id);
  }, [playing, totalFrames, intervalMs, frameIndex]);

  const canPlay = mode === "live" || totalFrames > 1;

  const play = useCallback(() => {
    if (!canPlay) return;
    if (totalFrames > 1) {
      setFrameIndex((i) => (i >= totalFrames - 1 ? 0 : i));
    }
    setPlaying(true);
  }, [canPlay, totalFrames]);

  const pause = useCallback(() => setPlaying(false), []);
  const toggle = useCallback(() => {
    if (!canPlay) return;
    setPlaying((p) => {
      if (!p && totalFrames > 1) {
        setFrameIndex((i) => (i >= totalFrames - 1 ? 0 : i));
      }
      return !p;
    });
  }, [canPlay, totalFrames]);

  const reset = useCallback(() => {
    setPlaying(false);
    setFrameIndex(0);
  }, []);

  const stepForward = useCallback(() => {
    setPlaying(false);
    setFrameIndex((i) => Math.min(totalFrames - 1, i + 1));
  }, [totalFrames]);

  const stepBack = useCallback(() => {
    setPlaying(false);
    setFrameIndex((i) => Math.max(0, i - 1));
  }, []);

  const jumpTo = useCallback(
    (index: number) => {
      setPlaying(false);
      setFrameIndex(Math.min(Math.max(0, index), Math.max(0, totalFrames - 1)));
    },
    [totalFrames],
  );

  const selectAgent = useCallback((id: string | null) => {
    setSelectedAgentId(id);
  }, []);

  const selectTask = useCallback((id: string | null) => {
    setSelectedTaskId(id);
  }, []);

  const toggleStatus = useCallback((status: TaskStatus) => {
    setVisibleStatuses((current) => {
      if (current.includes(status)) {
        if (current.length === 1) return current;
        return current.filter((s) => s !== status);
      }
      return [...current, status];
    });
  }, []);

  const showAllStatuses = useCallback(
    () => setVisibleStatuses(ALL_TASK_STATUSES),
    [],
  );

  const frame = frames[frameIndex] ?? frames[frames.length - 1] ?? null;
  const isDemo = frame?.isDemo ?? mode === "demo";

  const provenanceLabel =
    mode === "live"
      ? `LIVE BACKEND · ${strategy.toUpperCase()}`
      : isDemo
      ? "DEMO SCENARIO"
      : `M8 EXPERIMENT · ${strategy.toUpperCase()}`;

  /* Keep the selected agent valid as frames advance. */
  useEffect(() => {
    if (!selectedAgentId || !frame) return;
    if (!frame.agents.some((a) => a.agentId === selectedAgentId)) {
      setSelectedAgentId(null);
    }
  }, [frame, selectedAgentId]);

  const spawnRole =
    mode === "experiment"
      ? m8Scenarios.find((s) => s.id === scenarioId)?.spawnRole ?? null
      : scenario.spawnRole;

  const value: DashboardValue = {
    mode,
    setMode,
    scenario,
    scenarioId,
    setScenarioId,
    scenarios,
    m8Scenarios,
    strategy,
    setStrategy,
    frames,
    frame,
    frameIndex,
    totalFrames,
    playing,
    intervalMs,
    play,
    pause,
    toggle,
    reset,
    stepForward,
    stepBack,
    jumpTo,
    atEnd: totalFrames > 0 && frameIndex >= totalFrames - 1,
    atStart: frameIndex <= 0,
    selectedAgentId,
    selectAgent,
    visibleStatuses,
    toggleStatus,
    showAllStatuses,
    selectedTaskId,
    selectTask,
    isDemo,
    isLive: mode === "live",
    provenanceLabel,
    spawnRole,
    liveError,
  };

  return (
    <DashboardContext.Provider value={value}>
      {children}
    </DashboardContext.Provider>
  );
}

export function useDashboard(): DashboardValue {
  const ctx = useContext(DashboardContext);
  if (!ctx) {
    throw new Error("useDashboard must be used inside <DashboardProvider>");
  }
  return ctx;
}
