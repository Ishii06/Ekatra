"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import type { Mode, OrgSnapshot, RoleKey, Strategy, TaskStatus } from "./types";
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

export type DataSource = "demo" | "experiment";

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
  provenanceLabel: string;
  spawnRole: RoleKey | null;
}

const DashboardContext = createContext<DashboardValue | null>(null);

const DEMO_INTERVAL_MS = 2800;
const EXPERIMENT_INTERVAL_MS = 1600;

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

  const frames = useMemo<OrgSnapshot[]>(() => {
    if (mode === "experiment") {
      return buildExperimentFrames(scenarioId, strategy);
    }
    return buildDemoFrames(scenarioId);
  }, [mode, scenarioId, strategy]);

  const totalFrames = frames.length;
  const intervalMs = mode === "demo" ? DEMO_INTERVAL_MS : EXPERIMENT_INTERVAL_MS;

  /* Reset playback whenever the underlying sequence changes. */
  useEffect(() => {
    setFrameIndex(0);
    setPlaying(false);
    setSelectedAgentId(null);
    setSelectedTaskId(null);
  }, [frames]);

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

  const play = useCallback(() => {
    if (totalFrames <= 1) return;
    setFrameIndex((i) => (i >= totalFrames - 1 ? 0 : i));
    setPlaying(true);
  }, [totalFrames]);

  const pause = useCallback(() => setPlaying(false), []);
  const toggle = useCallback(() => {
    setPlaying((p) => {
      if (!p && totalFrames > 1) {
        setFrameIndex((i) => (i >= totalFrames - 1 ? 0 : i));
      }
      return !p;
    });
  }, [totalFrames]);

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

  const scenario = useMemo(() => scenarioById(scenarioId), [scenarioId]);

  const frame = frames[frameIndex] ?? frames[frames.length - 1] ?? null;
  const isDemo = frame?.isDemo ?? mode === "demo";

  const provenanceLabel = isDemo
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
    mode === "demo"
      ? scenario.spawnRole
      : m8Scenarios.find((s) => s.id === scenarioId)?.spawnRole ?? null;

  const value: DashboardValue = {
    mode,
    setMode,
    scenario,
    scenarioId,
    setScenarioId,
    scenarios: SCENARIOS,
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
    atEnd: frameIndex >= totalFrames - 1,
    atStart: frameIndex <= 0,
    selectedAgentId,
    selectAgent,
    visibleStatuses,
    toggleStatus,
    showAllStatuses,
    selectedTaskId,
    selectTask,
    isDemo,
    provenanceLabel,
    spawnRole,
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
