import type { Level, RoleKey } from "../types";

/**
 * Scenario catalogue for the dashboard.
 *
 * Seven of these (all but demo) map 1:1 to the Milestone 8 experiment
 * scenarios in `src/ekatra/experiments/fixtures.py`. The `demo` flag marks the
 * deterministic presentation simulation (never experiment data).
 */
export interface ScenarioDef {
  id: string;
  name: string;
  short: string;
  description: string;
  spawnRole: RoleKey | null;
  risk: Level;
  workload: Level;
  demo: boolean;
}

export const SCENARIOS: ScenarioDef[] = [
  {
    id: "m8_high_backend_workload",
    name: "High Backend Workload",
    short: "High Backend",
    description:
      "Seven backend tasks (two retrying) saturate the backend queue. Backend workload crosses HIGH and the controller spawns BACKEND-2.",
    spawnRole: "backend",
    risk: "NORMAL",
    workload: "HIGH",
    demo: true,
  },
  {
    id: "m8_high_frontend_workload",
    name: "High Frontend Workload",
    short: "High Frontend",
    description:
      "Seven frontend tasks (two retrying) saturate the frontend backlog. Frontend workload crosses HIGH and the controller spawns FRONTEND-2.",
    spawnRole: "frontend",
    risk: "NORMAL",
    workload: "HIGH",
    demo: true,
  },
  {
    id: "m8_security_risk",
    name: "Security Risk Concentration",
    short: "Security Risk",
    description:
      "Security review workload is saturated and risk indicators concentrate in the backend/security modules. Risk climbs HIGH and the controller spawns SECURITY-2.",
    spawnRole: "security",
    risk: "HIGH",
    workload: "HIGH",
    demo: true,
  },
  {
    id: "m8_low_workload",
    name: "Low Workload",
    short: "Low Workload",
    description:
      "One task per execution role. No adaptive action is required; the controller CONTINUEs every cycle and the fixed six-agent team finishes.",
    spawnRole: null,
    risk: "NORMAL",
    workload: "NORMAL",
    demo: true,
  },
  {
    id: "m8_mixed_high_workload",
    name: "Mixed Elevated Workload",
    short: "Mixed Elevated",
    description:
      "Balanced demand across backend, frontend, QA, and security with one retrying task per implementation role. Risk NORMAL, workload ELEVATED — no spawn.",
    spawnRole: null,
    risk: "NORMAL",
    workload: "ELEVATED",
    demo: true,
  },
];

export const DEFAULT_SCENARIO_ID = "m8_high_backend_workload";

export function scenarioById(id: string): ScenarioDef {
  return SCENARIOS.find((s) => s.id === id) ?? SCENARIOS[0];
}

export const DEMO_LABEL = "DEMO";
export const DEMO_SIMULATED_NOTE =
  "Simulated presentation walkthrough — deterministic fixture data, not an experiment run.";