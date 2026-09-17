"""Milestone 8: built-in experiment scenarios (fixtures).

Each fixture returns a shared :class:`ExperimentScenario` object that is handed
verbatim to both the fixed and adaptive strategy. Scenarios control workload
and risk through their task sets; the orchestration strategies are exercised
as-is and no scenario special-cases any strategy.

Tuning targets (deterministic, using the documented formulas and thresholds):

* Workload ``W = 0.40*queue + 0.30*complexity + 0.20*delay + 0.10*failure``,
  queue normalized against ``queue_reference = 10``; levels NORMAL < 40,
  ELEVATED 40-70, HIGH > 70.
* Risk indicators: findings ("finding"/"vulnerab*"), security checks (retries),
  authentication ("auth"/"login"/"permission"/"credential"), suspicious
  ("suspicious"/"malicious"/"unsafe"/"injection"); failure rate and high-risk
  tasks also contribute. Risk becomes HIGH above 70.

The ``expected_characteristics`` blocks are scenario-side statements of intent
used by the tests to verify a scenario is exercising what it claims.
"""

from __future__ import annotations

from ekatra.experiments.scenarios import ExperimentScenario, ExperimentTask
from ekatra.tasks.task import TaskStatus

_M8_TIMESTAMP = "2026-01-01T00:00:00+00:00"


def low_workload() -> ExperimentScenario:
    """Five tasks across five roles with a single-dev backlog per role.

    Both strategies should finish this scenario without any adaptive action;
    the controller is expected to CONTINUE on every observed cycle.
    """
    return ExperimentScenario(
        scenario_id="m8_low_workload",
        name="Low workload across roles",
        description=(
            "One task per execution role, forming the default dependency chain. "
            "Reproduces the fixed baseline's default plan so both strategies "
            "agree on the complete task set."
        ),
        project_description=(
            "Build a wellbeing and counselling support platform for Indian "
            "students with a small, well-scoped v1 feature set."
        ),
        timing={"seed": "ekatra-m8-low", "base_timestamp": _M8_TIMESTAMP},
        expected_characteristics={
            "task_count": 5,
            "roles": ["architect", "backend", "frontend", "qa", "security"],
            "adaptive_workload_level": "NORMAL",
            "adaptive_risk_level": "NORMAL",
            "adaptive_spawn_role": None,
            "fixed_completed_tasks": 5,
        },
        tasks=[
            ExperimentTask(
                key="architecture",
                role="architect",
                description="Define the system architecture and component interfaces.",
                priority=3,
                complexity=3,
                risk=10,
            ),
            ExperimentTask(
                key="backend",
                role="backend",
                description="Implement backend APIs, business logic, and data access.",
                priority=3,
                complexity=4,
                risk=25,
                dependencies=["architecture"],
            ),
            ExperimentTask(
                key="frontend",
                role="frontend",
                description="Implement frontend UI, components, and API integration.",
                priority=2,
                complexity=4,
                risk=15,
                dependencies=["backend"],
            ),
            ExperimentTask(
                key="qa",
                role="qa",
                description="Execute tests, validate requirements, and report defects.",
                priority=3,
                complexity=2,
                risk=20,
                dependencies=["backend", "frontend"],
            ),
            ExperimentTask(
                key="security",
                role="security",
                description="Perform security review and identify vulnerabilities.",
                priority=3,
                complexity=2,
                risk=40,
                dependencies=["backend", "frontend"],
            ),
        ],
    )


def high_backend_workload() -> ExperimentScenario:
    """A long backend chain plus a short frontend/closing chain.

    The backlog per role saturates the queue-length component: backend starts
    with 7 in-flight tasks (2 already retrying) which pushes the backend
    workload above the HIGH threshold while every other role stays NORMAL.
    The adaptive controller is expected to spawn an extra backend agent.
    """
    return ExperimentScenario(
        scenario_id="m8_high_backend_workload",
        name="High backend workload",
        description=(
            "Seven backend tasks (two retrying) and one task for each remaining "
            "role. Backend queue saturation drives only the backend workload "
            "HIGH; other roles stay NORMAL so the controller spawns a backend."
        ),
        project_description=(
            "Build a wellbeing and counselling support platform for Indian "
            "students; the backend needs a wide API surface with heavy "
            "business logic."
        ),
        timing={"seed": "ekatra-m8-high-backend", "base_timestamp": _M8_TIMESTAMP},
        expected_characteristics={
            "task_count": 11,
            "backend_tasks": 7,
            "frontend_tasks": 1,
            "qa_tasks": 1,
            "security_tasks": 1,
            "architect_tasks": 1,
            "adaptive_workload_level": "HIGH",
            "adaptive_spawn_role": "backend",
            "fixed_completed_tasks": 11,
        },
        tasks=[
            ExperimentTask(
                key="architecture",
                role="architect",
                description="Define the system architecture and component interfaces.",
                priority=3,
                complexity=3,
                risk=30,
            ),
            ExperimentTask(
                key="backend_gateway",
                role="backend",
                description="Implement the API gateway and request routing.",
                priority=3,
                complexity=5,
                risk=30,
                dependencies=["architecture"],
            ),
            ExperimentTask(
                key="backend_auth",
                role="backend",
                description="Implement authentication, sessions, and role checks.",
                priority=3,
                complexity=5,
                risk=30,
                dependencies=["backend_gateway"],
            ),
            ExperimentTask(
                key="backend_notifications",
                role="backend",
                description="Implement the notifications and messaging service.",
                priority=2,
                complexity=5,
                risk=30,
                dependencies=["backend_auth"],
                initial_status=TaskStatus.RETRY,
                retry_count=2,
            ),
            ExperimentTask(
                key="backend_reports",
                role="backend",
                description="Implement reporting, analytics, and exports.",
                priority=2,
                complexity=5,
                risk=30,
                dependencies=["backend_notifications"],
                initial_status=TaskStatus.RETRY,
                retry_count=2,
            ),
            ExperimentTask(
                key="backend_counsellor",
                role="backend",
                description="Implement the counsellor scheduling and matching logic.",
                priority=3,
                complexity=5,
                risk=30,
                dependencies=["backend_reports"],
            ),
            ExperimentTask(
                key="backend_community",
                role="backend",
                description="Implement community and feed APIs with moderation rules.",
                priority=3,
                complexity=5,
                risk=30,
                dependencies=["backend_counsellor"],
            ),
            ExperimentTask(
                key="backend_search",
                role="backend",
                description="Implement full-text search and resource lookups.",
                priority=3,
                complexity=5,
                risk=30,
                dependencies=["backend_community"],
            ),
            ExperimentTask(
                key="frontend_app",
                role="frontend",
                description="Implement the student-facing web application shell.",
                priority=3,
                complexity=4,
                risk=15,
                dependencies=["backend_gateway"],
            ),
            ExperimentTask(
                key="qa_acceptance",
                role="qa",
                description="Execute acceptance and regression test suites.",
                priority=3,
                complexity=2,
                risk=20,
                dependencies=["backend_gateway", "frontend_app"],
            ),
            ExperimentTask(
                key="security_review",
                role="security",
                description="Perform security review and identify vulnerabilities.",
                priority=3,
                complexity=2,
                risk=40,
                dependencies=["backend_gateway", "frontend_app"],
            ),
        ],
    )


def high_frontend_workload() -> ExperimentScenario:
    """Mirror of ``high_backend_workload`` with the long chain on frontend.

    Seven frontend tasks (two retrying) saturate the frontend backlog; only the
    frontend workload becomes HIGH. The adaptive controller is expected to
    spawn an extra frontend agent.
    """
    return ExperimentScenario(
        scenario_id="m8_high_frontend_workload",
        name="High frontend workload",
        description=(
            "Mirror scenario that saturates a different role's backlog: seven "
            "frontend tasks (two retrying) drive only the frontend workload "
            "HIGH so the controller spawns a frontend agent."
        ),
        project_description=(
            "Build a wellbeing and counselling support platform for Indian "
            "students; the frontend is a large multi-screen progressive web "
            "application."
        ),
        timing={"seed": "ekatra-m8-high-frontend", "base_timestamp": _M8_TIMESTAMP},
        expected_characteristics={
            "task_count": 11,
            "backend_tasks": 1,
            "frontend_tasks": 7,
            "qa_tasks": 1,
            "security_tasks": 1,
            "architect_tasks": 1,
            "adaptive_workload_level": "HIGH",
            "adaptive_spawn_role": "frontend",
            "fixed_completed_tasks": 11,
        },
        tasks=[
            ExperimentTask(
                key="architecture",
                role="architect",
                description="Define the system architecture and component interfaces.",
                priority=3,
                complexity=3,
                risk=20,
            ),
            ExperimentTask(
                key="backend_gateway",
                role="backend",
                description="Implement the API gateway and request routing.",
                priority=3,
                complexity=4,
                risk=20,
                dependencies=["architecture"],
            ),
            ExperimentTask(
                key="frontend_shell",
                role="frontend",
                description="Implement the app shell, navigation, and theming.",
                priority=3,
                complexity=5,
                risk=15,
                dependencies=["backend_gateway"],
            ),
            ExperimentTask(
                key="frontend_dashboard",
                role="frontend",
                description="Implement the counsellor dashboard and widgets.",
                priority=3,
                complexity=5,
                risk=15,
                dependencies=["frontend_shell"],
            ),
            ExperimentTask(
                key="frontend_booking",
                role="frontend",
                description="Implement the session booking and scheduling flows.",
                priority=2,
                complexity=5,
                risk=15,
                dependencies=["frontend_dashboard"],
                initial_status=TaskStatus.RETRY,
                retry_count=2,
            ),
            ExperimentTask(
                key="frontend_community",
                role="frontend",
                description="Implement the community feed and posting interface.",
                priority=2,
                complexity=5,
                risk=15,
                dependencies=["frontend_booking"],
                initial_status=TaskStatus.RETRY,
                retry_count=2,
            ),
            ExperimentTask(
                key="frontend_profile",
                role="frontend",
                description="Implement profile, settings, and consent screens.",
                priority=3,
                complexity=5,
                risk=15,
                dependencies=["frontend_community"],
            ),
            ExperimentTask(
                key="frontend_search",
                role="frontend",
                description="Implement resource search and filter surfaces.",
                priority=3,
                complexity=5,
                risk=15,
                dependencies=["frontend_profile"],
            ),
            ExperimentTask(
                key="frontend_offline",
                role="frontend",
                description="Implement offline support and low-bandwidth mode.",
                priority=3,
                complexity=5,
                risk=15,
                dependencies=["frontend_search"],
            ),
            ExperimentTask(
                key="qa_acceptance",
                role="qa",
                description="Execute acceptance and regression test suites.",
                priority=3,
                complexity=2,
                risk=20,
                dependencies=["backend_gateway", "frontend_shell"],
            ),
            ExperimentTask(
                key="security_review",
                role="security",
                description="Perform security review and identify vulnerabilities.",
                priority=3,
                complexity=2,
                risk=40,
                dependencies=["backend_gateway", "frontend_shell"],
            ),
        ],
    )


def security_risk() -> ExperimentScenario:
    """Backend-module risk concentration with an already-strained security role.

    Eight security-review tasks are retrying and five backend tasks have failed,
    seeding "finding"/"vulnerab*", authentication and suspicious-activity
    indicators plus a large high-risk share. Risk becomes HIGH and the security
    backlog saturates, so the controller is expected to spawn a security agent.
    """
    return ExperimentScenario(
        scenario_id="m8_security_risk",
        name="Security risk concentration",
        description=(
            "Security review workload is saturated and risk indicators are "
            "concentrated in the backend and security modules (findings, "
            "authentication, suspicious activity, failed tasks). Drives the "
            "security role workload HIGH and overall risk HIGH."
        ),
        project_description=(
            "Build a wellbeing and counselling support platform for Indian "
            "students; counselling must meet strict clinical-data and "
            "safety standards."
        ),
        timing={"seed": "ekatra-m8-security-risk", "base_timestamp": _M8_TIMESTAMP},
        expected_characteristics={
            "task_count": 22,
            "backend_tasks": 11,
            "security_tasks": 8,
            "frontend_tasks": 1,
            "qa_tasks": 1,
            "architect_tasks": 1,
            "adaptive_workload_level": "HIGH",
            "adaptive_risk_level": "HIGH",
            "adaptive_spawn_role": "security",
            "fixed_completed_tasks": 17,
        },
        tasks=[
            ExperimentTask(
                key="architecture",
                role="architect",
                description="Define the system architecture and component interfaces.",
                priority=3,
                complexity=3,
                risk=30,
            ),
            ExperimentTask(
                key="backend_gateway",
                role="backend",
                description="Implement the API gateway and request routing.",
                priority=3,
                complexity=4,
                risk=90,
                dependencies=["architecture"],
            ),
            ExperimentTask(
                key="backend_auth",
                role="backend",
                description="Implement authentication, sessions, and role checks.",
                priority=3,
                complexity=4,
                risk=90,
                dependencies=["backend_gateway"],
            ),
            ExperimentTask(
                key="backend_profiles",
                role="backend",
                description="Implement consent-aware profile and data storage.",
                priority=3,
                complexity=4,
                risk=90,
                dependencies=["backend_auth"],
            ),
            ExperimentTask(
                key="backend_messaging",
                role="backend",
                description="Implement secure messaging and session records.",
                priority=3,
                complexity=4,
                risk=90,
                dependencies=["backend_profiles"],
            ),
            ExperimentTask(
                key="backend_safety",
                role="backend",
                description="Implement safety flags, escalation, and audit logs.",
                priority=3,
                complexity=4,
                risk=90,
                dependencies=["backend_messaging"],
            ),
            ExperimentTask(
                key="backend_integrations",
                role="backend",
                description="Implement support integrations with permission scoping.",
                priority=3,
                complexity=4,
                risk=90,
                dependencies=["backend_safety"],
            ),
            ExperimentTask(
                key="backend_failed_auth",
                role="backend",
                description="Resolve authentication and permission errors.",
                priority=3,
                complexity=4,
                risk=90,
                dependencies=["backend_integrations"],
                initial_status=TaskStatus.FAILED,
            ),
            ExperimentTask(
                key="backend_failed_login",
                role="backend",
                description="Detect suspicious login injection patterns.",
                priority=3,
                complexity=4,
                risk=90,
                dependencies=["backend_integrations"],
                initial_status=TaskStatus.FAILED,
            ),
            ExperimentTask(
                key="backend_failed_input",
                role="backend",
                description="Fix unsafe input injection handling.",
                priority=3,
                complexity=4,
                risk=90,
                dependencies=["backend_integrations"],
                initial_status=TaskStatus.FAILED,
            ),
            ExperimentTask(
                key="backend_failed_credential",
                role="backend",
                description="Resolve credential and permission mistakes.",
                priority=3,
                complexity=4,
                risk=90,
                dependencies=["backend_integrations"],
                initial_status=TaskStatus.FAILED,
            ),
            ExperimentTask(
                key="backend_failed_suspicious",
                role="backend",
                description="Investigate suspicious login and unsafe patterns.",
                priority=3,
                complexity=4,
                risk=90,
                dependencies=["backend_integrations"],
                initial_status=TaskStatus.FAILED,
            ),
            ExperimentTask(
                key="frontend_auth_ui",
                role="frontend",
                description="Build the login and settings screens.",
                priority=3,
                complexity=4,
                risk=90,
                dependencies=["backend_gateway"],
            ),
            ExperimentTask(
                key="qa_auth",
                role="qa",
                description="Verify authentication flows and sign-in paths.",
                priority=3,
                complexity=2,
                risk=90,
                dependencies=["backend_gateway", "frontend_auth_ui"],
            ),
        ]
        + [
            ExperimentTask(
                key=f"security_review_{n}",
                role="security",
                description=(
                    "Perform security review of the authentication module; "
                    "record findings and vulnerabilities."
                ),
                priority=3,
                complexity=3,
                risk=90,
                dependencies=(
                    ["backend_gateway", "frontend_auth_ui"]
                    if n == 1
                    else [f"security_review_{n - 1}"]
                ),
                initial_status=TaskStatus.RETRY,
                retry_count=1,
            )
            for n in range(1, 9)
        ],
    )


def mixed_high_workload() -> ExperimentScenario:
    """Broad elevated demand across several roles.

    Backend and frontend both start a four-task chain with one retry each so
    several role workloads sit in the ELEVATED band without crossing HIGH. No
    spawn is expected; both strategies complete the full task set.
    """
    return ExperimentScenario(
        scenario_id="m8_mixed_high_workload",
        name="Mixed elevated workload",
        description=(
            "Balanced demand across backend, frontend, QA, and security with one "
            "retrying task per implementation role. Workload sits in the "
            "ELEVATED band, no role crosses HIGH, and neither strategy should "
            "spawn."
        ),
        project_description=(
            "Build a wellbeing and counselling support platform for Indian "
            "students with a medium-size v2 feature set touching every module."
        ),
        timing={"seed": "ekatra-m8-mixed", "base_timestamp": _M8_TIMESTAMP},
        expected_characteristics={
            "task_count": 13,
            "backend_tasks": 4,
            "frontend_tasks": 4,
            "qa_tasks": 2,
            "security_tasks": 2,
            "architect_tasks": 1,
            "adaptive_workload_level": "ELEVATED",
            "adaptive_risk_level": "NORMAL",
            "adaptive_spawn_role": None,
            "fixed_completed_tasks": 13,
        },
        tasks=[
            ExperimentTask(
                key="architecture",
                role="architect",
                description="Define the system architecture and component interfaces.",
                priority=3,
                complexity=3,
                risk=30,
            ),
            ExperimentTask(
                key="backend_core",
                role="backend",
                description="Implement core domain APIs and data access.",
                priority=3,
                complexity=5,
                risk=40,
                dependencies=["architecture"],
            ),
            ExperimentTask(
                key="backend_messaging",
                role="backend",
                description="Implement messaging and notifications service.",
                priority=3,
                complexity=5,
                risk=40,
                dependencies=["backend_core"],
            ),
            ExperimentTask(
                key="backend_scheduling",
                role="backend",
                description="Implement scheduling and matching logic.",
                priority=2,
                complexity=5,
                risk=40,
                dependencies=["backend_messaging"],
                initial_status=TaskStatus.RETRY,
                retry_count=1,
            ),
            ExperimentTask(
                key="backend_reports",
                role="backend",
                description="Implement reporting and exports.",
                priority=3,
                complexity=5,
                risk=40,
                dependencies=["backend_scheduling"],
            ),
            ExperimentTask(
                key="frontend_shell",
                role="frontend",
                description="Implement the app shell and navigation.",
                priority=3,
                complexity=5,
                risk=40,
                dependencies=["backend_core"],
            ),
            ExperimentTask(
                key="frontend_dashboard",
                role="frontend",
                description="Implement dashboard and session widgets.",
                priority=3,
                complexity=5,
                risk=40,
                dependencies=["frontend_shell"],
            ),
            ExperimentTask(
                key="frontend_booking",
                role="frontend",
                description="Implement booking and scheduling screens.",
                priority=2,
                complexity=5,
                risk=40,
                dependencies=["frontend_dashboard"],
                initial_status=TaskStatus.RETRY,
                retry_count=1,
            ),
            ExperimentTask(
                key="frontend_settings",
                role="frontend",
                description="Implement profile, settings, and consent screens.",
                priority=3,
                complexity=5,
                risk=40,
                dependencies=["frontend_booking"],
            ),
            ExperimentTask(
                key="qa_e2e",
                role="qa",
                description="Execute end-to-end and acceptance test suites.",
                priority=3,
                complexity=3,
                risk=40,
                dependencies=["backend_core", "frontend_shell"],
            ),
            ExperimentTask(
                key="qa_performance",
                role="qa",
                description="Validate performance and low-bandwidth behaviour.",
                priority=3,
                complexity=3,
                risk=40,
                dependencies=["qa_e2e"],
            ),
            ExperimentTask(
                key="security_review",
                role="security",
                description="Perform security review and identify vulnerabilities.",
                priority=3,
                complexity=3,
                risk=40,
                dependencies=["backend_core", "frontend_shell"],
            ),
            ExperimentTask(
                key="security_compliance",
                role="security",
                description="Validate privacy and compliance controls.",
                priority=3,
                complexity=3,
                risk=40,
                dependencies=["security_review"],
            ),
        ],
    )


def all_scenarios() -> list[ExperimentScenario]:
    """Return every built-in scenario in a stable order."""
    return [
        low_workload(),
        high_backend_workload(),
        high_frontend_workload(),
        security_risk(),
        mixed_high_workload(),
    ]


__all__ = [
    "all_scenarios",
    "high_backend_workload",
    "high_frontend_workload",
    "low_workload",
    "mixed_high_workload",
    "security_risk",
]