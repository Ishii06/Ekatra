# Ekatra — Project Overview

## 1. Project Information

**Project Name:** Ekatra
**Project Type:** B.Tech Minor Project / Academic Research Prototype
**Domain:** Artificial Intelligence, Multi-Agent Systems, Autonomous Software Engineering
**Primary Research Area:** Adaptive Multi-Agent Orchestration


### Project Title

> **Ekatra – Adaptive Multi-Agent Orchestration Framework for Autonomous Software Development**

---

## 2. Abstract

Ekatra is an academic research-oriented prototype that explores the use of adaptive multi-agent orchestration for autonomous software development. The system models a virtual software engineering organization consisting of specialized AI agents responsible for project management, architecture, frontend development, backend development, quality assurance, and security.

Unlike a conventional fixed multi-agent workflow, Ekatra dynamically adapts its agent organization according to the current state of the software development process. A hybrid Project Manager combines LLM-based reasoning for planning and task decomposition with a deterministic Adaptive Controller responsible for measurable decisions such as workload monitoring, risk assessment, task reassignment, agent spawning, and agent termination.

The system continuously observes factors such as task queue length, task complexity, execution delay, failure rate, and security risk. Based on these observations, the orchestration layer can modify the active agent pool to address changing workload and risk conditions.

The research evaluates this adaptive approach against a fixed multi-agent baseline. The objective is to determine whether dynamic agent allocation can achieve comparable or improved software-development outcomes while reducing unnecessary computational resources and improving responsiveness under varying workloads.

---

## 3. Problem Statement

Multi-agent systems have been increasingly explored for automating software development through specialized AI agents. Existing approaches commonly organize agents into predefined roles and workflows, where each agent performs a specific responsibility throughout the development process.

Although role specialization can divide complex software-development tasks effectively, a fixed team composition may not respond efficiently to changing project conditions.

For example, a project may temporarily contain a large number of backend tasks while having relatively few frontend tasks. A fixed organization with one backend agent may create a bottleneck even though other agents have available capacity. Conversely, assigning multiple agents to a lightly loaded role may result in unnecessary computational and token usage.

Software projects can also experience changing risk conditions. A security-sensitive implementation may require additional security analysis even if the initial team composition contains only one security agent.

Therefore, there is a need to investigate whether a software-engineering multi-agent organization can dynamically adapt its team composition according to measurable workload and risk conditions during execution.

---

## 4. Motivation

The motivation behind Ekatra is to investigate whether AI software-development organizations should remain statically configured or dynamically adapt to the requirements of the project at runtime.

Traditional organizational structures generally define responsibilities before execution. However, autonomous software-development environments may experience:

* changing task workloads
* uneven distribution of tasks
* task failures
* execution delays
* dependency bottlenecks
* changing security risks
* varying task complexity

A dynamically managed agent organization could potentially respond to these conditions by allocating computational agents where they are most needed.

Ekatra therefore treats AI agents as dynamic computational resources rather than permanently fixed workers.

---

## 5. Existing Approach

Several multi-agent software-development frameworks demonstrate the use of specialized agents and structured workflows.

Examples include:

### MetaGPT

MetaGPT organizes software-development activities through specialized roles and structured software-development procedures.

### ChatDev

ChatDev models software development as collaboration between role-based agents that communicate through an organized workflow.

### AutoGen

AutoGen provides infrastructure for constructing customizable multi-agent conversations and agent-based workflows.

These systems demonstrate the feasibility of using multiple specialized agents for software-development tasks.

However, Ekatra focuses on a different research question: whether the composition and allocation of such agents can be dynamically adapted according to runtime workload and risk.

---

## 6. Research Gap

The research gap investigated by Ekatra is not the use of multi-agent systems itself.

Multi-agent software-development systems, specialized roles, agent communication, and workflow orchestration are established areas of research and engineering.

The focus of Ekatra is instead:

> **Dynamic workload- and risk-aware adaptation of the software-engineering agent organization during execution.**

A conventional fixed organization may maintain the same number of agents regardless of workload.

Ekatra introduces an Adaptive Controller that can observe the system state and determine whether the current agent allocation should remain unchanged or be modified.

Potential adaptive actions include:

* spawning an additional agent
* terminating an underutilized agent
* reassigning tasks
* reprioritizing tasks
* increasing review effort
* allocating resources toward higher-risk activities

The proposed mechanism is therefore concerned with **runtime organizational adaptation**, rather than merely adding more specialized agents.

---

## 7. Proposed System

Ekatra represents a virtual software engineering organization composed of specialized AI agents.

The initial organization consists of six core agent roles:

1. Project Manager
2. Architect
3. Frontend Developer
4. Backend Developer
5. QA / Testing Agent
6. Security Agent

The Project Manager is responsible for understanding project requirements, planning the development process, decomposing work into tasks, and coordinating the agent organization.

The Adaptive Controller continuously evaluates measurable system conditions and determines whether changes to the agent allocation are required.

A simplified system flow is:

```text
                PROJECT REQUIREMENT
                        │
                        ▼
                LLM PROJECT MANAGER
                        │
                 Planning & Reasoning
                        │
                        ▼
                   TASK SYSTEM
                        │
                        ▼
               ADAPTIVE CONTROLLER
                        │
        ┌───────────────┼────────────────┐
        │               │                │
      SPAWN          REASSIGN        TERMINATE
        │               │                │
        └───────────────┼────────────────┘
                        │
                        ▼
                    AGENT POOL
                        │
                        ▼
                 TASK EXECUTION
                        │
                ┌───────┴───────┐
                ▼               ▼
               QA           SECURITY
                │               │
                └───────┬───────┘
                        ▼
                    EVALUATION
                        │
                        ▼
                    FEEDBACK
                        │
                        └──────────► ADAPT
```

---

## 8. Research Contribution

The primary proposed contribution of Ekatra is:

> **A workload- and risk-aware adaptive orchestration mechanism that dynamically scales and reallocates AI software-engineering agents during development instead of relying exclusively on a fixed team composition.**

The contribution consists of three major components:

### 8.1 Runtime System Observation

The system collects measurable information about the current development state, including:

* task queue length
* task complexity
* execution delay
* task failures
* retry counts
* workload
* security/risk indicators
* agent utilization

### 8.2 Adaptive Decision Mechanism

A deterministic controller evaluates the observed system state and selects an orchestration action.

Possible actions include:

```text
CONTINUE
SPAWN
TERMINATE
REASSIGN
PRIORITIZE
```

### 8.3 Experimental Comparison

The adaptive organization is evaluated against a fixed multi-agent baseline under controlled workloads.

This allows the effect of adaptive orchestration to be measured rather than assumed.

---

## 9. Research Question

The primary research question is:

> **Can an AI software engineering organization dynamically change its team composition based on workload and risk during software development?**

The evaluation will additionally investigate whether such adaptation affects:

* completion time
* task waiting time
* resource consumption
* task success
* failure and retry rates
* software quality
* security findings
* agent utilization

---

## 10. Research Hypothesis

The initial research hypothesis is:

> **An adaptive orchestration strategy can achieve comparable or improved output quality while reducing completion time and/or unnecessary computational resource usage compared with a fixed multi-agent organization under varying workloads.**

This hypothesis is intentionally testable and does not assume that Ekatra will outperform the baseline in every metric.

The experimental results will determine whether the proposed adaptive strategy provides measurable benefits.

---

## 11. Objectives

The major objectives of Ekatra are:

### Objective 1

Design a virtual software engineering organization using specialized AI agents.

### Objective 2

Develop a structured task-management and state-tracking system.

### Objective 3

Implement a hybrid Project Manager combining LLM reasoning with deterministic orchestration logic.

### Objective 4

Develop an Adaptive Controller capable of monitoring workload and risk.

### Objective 5

Enable runtime agent spawning, termination, task reassignment, and prioritization.

### Objective 6

Maintain observable agent and task lifecycle states.

### Objective 7

Implement a fixed multi-agent baseline for controlled comparison.

### Objective 8

Conduct experiments under different workload and risk conditions.

### Objective 9

Measure the effect of adaptive orchestration on performance, resource utilization, reliability, and quality.

### Objective 10

Analyze the experimental results to determine the effectiveness and limitations of the proposed approach.

---

## 12. System Scope

### Included in the initial prototype

* six core agent roles
* structured task management
* agent lifecycle management
* agent pool
* workload monitoring
* risk monitoring
* deterministic adaptive controller
* dynamic agent spawning
* dynamic agent termination
* task reassignment
* task prioritization
* QA and security review
* logging and observability
* fixed baseline
* adaptive system
* experimental evaluation

### Outside the initial scope

The following features are not required for the first prototype:

* large-scale production deployment
* fully autonomous production software delivery
* dozens of specialized agents
* distributed computing infrastructure
* multiple LLM providers
* advanced autonomous DevOps
* enterprise-scale cloud deployment
* fully autonomous deployment to production

These may be considered as future extensions.

---

## 13. Core Agents

### 13.1 Project Manager

**Responsibilities:**

* understand project requirements
* plan development
* decompose requirements into tasks
* identify dependencies
* assign tasks
* monitor progress
* coordinate agents
* provide planning and reasoning

The LLM Project Manager does not directly control all measurable resource-allocation decisions.

---

### 13.2 Architect

**Responsibilities:**

* design system architecture
* identify components
* define interfaces
* recommend technologies
* produce technical design information
* review architectural consistency

---

### 13.3 Frontend Developer

**Responsibilities:**

* implement frontend components
* develop user interfaces
* implement client-side functionality
* integrate frontend components with APIs
* address frontend development tasks

---

### 13.4 Backend Developer

**Responsibilities:**

* implement APIs
* develop server-side logic
* implement data-access functionality
* integrate backend services
* address backend development tasks

---

### 13.5 QA / Testing Agent

**Responsibilities:**

* generate tests
* execute tests
* validate functionality
* identify defects
* report failures
* verify fixes

---

### 13.6 Security Agent

**Responsibilities:**

* perform security reviews
* identify common vulnerabilities
* inspect authentication and authorization logic
* identify suspicious code patterns
* report security findings
* validate security-related fixes

---

## 14. Adaptive Orchestration

Ekatra follows a continuous feedback loop:

```text
OBSERVE
   ↓
ANALYZE
   ↓
DECIDE
   ↓
ALLOCATE
   ↓
EXECUTE
   ↓
EVALUATE
   ↓
ADAPT
   ↺
```

The Adaptive Controller receives system-state information and calculates workload and risk indicators.

For example:

```text
Backend Queue = 12 tasks
Workload Score = 82
        │
        ▼
Adaptive Controller
        │
        ▼
SPAWN Backend-2
        │
        ▼
Backend Pool
├── Backend-1
└── Backend-2
```

If the workload subsequently decreases:

```text
Backend-2
    │
    ▼
IDLE
    │
    ▼
Termination/Release Decision
```

The exact workload weights and thresholds are treated as experimental parameters rather than established scientific constants.

---

## 15. Fixed vs Adaptive Architecture

### Fixed Baseline

The baseline maintains a predefined number of agents:

```text
                 PROJECT MANAGER
                        │
             ┌──────────┼──────────┐
             ▼          ▼          ▼
        ARCHITECT    FRONTEND    BACKEND
             │          │          │
             └──────────┼──────────┘
                        ▼
                       QA
                        │
                     SECURITY
```

The number of agents remains fixed during execution.

---

### Ekatra Adaptive System

The adaptive system initially starts with a similar organization:

```text
PROJECT MANAGER
├── Architect
├── Frontend-1
├── Backend-1
├── QA-1
└── Security-1
```

The Adaptive Controller can modify the organization according to system conditions.

For example:

```text
Backend workload increases
          ↓
Workload exceeds configured condition
          ↓
Adaptive Controller
          ↓
Spawn Backend-2
```

Result:

```text
PROJECT MANAGER
├── Architect
├── Frontend-1
├── Backend-1
├── Backend-2
├── QA-1
└── Security-1
```

The adaptive system may later release or terminate an unnecessary agent when its workload falls.

---

## 16. Technology Stack

### Programming Language

**Python 3.13**

The prototype uses the available Python 3.13 environment to avoid unnecessary version-management complexity.

### Agent Orchestration

**LangGraph**

LangGraph provides graph-based workflow and state-management infrastructure.

LangGraph itself is an implementation technology and is **not considered the research novelty**.

### LLM

**Google Gemini API**

Used for LLM-based planning, reasoning, task decomposition, and agent behavior
(see `docs/decisions/ADR-006-gemini.md`).

### Backend

**FastAPI**

Used for exposing application functionality through APIs where required.

### Data Validation

**Pydantic**

Used for structured data models and validation.

### Database

**SQLite**

Used initially for lightweight persistent state and experimental data.

### ORM / Database Layer

**SQLAlchemy**

### Asynchronous Execution

**asyncio**

### Evaluation

* Pandas
* Matplotlib
* pytest
* Python logging

Additional technologies may be introduced only when they provide a clear requirement for the prototype or evaluation.

---

## 17. Evaluation Strategy

Ekatra will be evaluated through a comparison between:

```text
FIXED MULTI-AGENT BASELINE
              VS
ADAPTIVE MULTI-AGENT SYSTEM
```

The experiments will expose both systems to controlled software-development workloads.

Potential evaluation dimensions include:

### Performance

* total project completion time
* average task completion time
* task queue waiting time

### Resource Efficiency

* LLM token usage
* number of active agents
* average active-agent count
* agent utilization
* unnecessary agent lifetime

### Reliability

* task success rate
* task failure rate
* retry count
* defect detection

### Quality

* functional correctness
* test success
* code quality
* security findings

### Adaptation

* number of spawn events
* number of termination events
* number of task reallocations
* workload before adaptation
* workload after adaptation
* risk before adaptation
* risk after adaptation

The exact experimental methodology, workload scenarios, statistical analysis, and evaluation metrics will be formally defined in `07-evaluation-plan.md`.

---

## 18. SDG Alignment

### Primary: SDG 9 — Industry, Innovation and Infrastructure

Ekatra primarily aligns with **Sustainable Development Goal 9**, particularly through its focus on:

* technological innovation
* AI-based software engineering
* intelligent computational resource allocation
* scalable software-development infrastructure
* research and experimentation in emerging technologies

### Secondary Alignment

The project may also have secondary relevance to:

**SDG 8 — Decent Work and Economic Growth**

Through exploration of AI-assisted software-development processes and productivity.

**SDG 12 — Responsible Consumption and Production**

Through investigation of computational resource efficiency and avoidance of unnecessary agent execution.

SDG 9 remains the primary alignment of the project.

---

## 19. Limitations

Ekatra is an academic research prototype and therefore has several limitations.

### LLM Dependence

Agent behavior may depend on the capabilities, limitations, and variability of the selected LLM.

### Limited Agent Set

The initial prototype contains six core agent roles and does not attempt to model a complete software organization.

### Simplified Workload Model

Initial workload calculations are based on measurable heuristics. Their effectiveness must be experimentally validated rather than assumed.

### Simplified Risk Model

The initial risk score represents a controlled prototype mechanism and should not be interpreted as a comprehensive cybersecurity risk assessment.

### Experimental Environment

Results may depend on the selected software tasks, prompts, LLM model, hardware, and experimental configuration.

### Cost Measurement

Token consumption and computational cost may vary across model versions and API configurations.

### Autonomous Software Development

The prototype is intended to investigate orchestration mechanisms and should not be interpreted as demonstrating fully autonomous production-grade software development.

---

## 20. Future Scope

Potential future extensions include:

* additional specialized agents
* dynamic role creation
* more advanced workload prediction
* predictive rather than reactive scaling
* reinforcement-learning-based orchestration
* cost-aware orchestration
* distributed agent execution
* persistent project memory
* Git-based development workflows
* automated CI/CD integration
* performance optimization agents
* DevOps agents
* documentation agents
* human-in-the-loop orchestration
* multi-LLM orchestration
* larger-scale experimental evaluation

These features are outside the scope of the initial prototype unless later experiments demonstrate a clear need for them.

---

## 21. Project Design Principle

The central design principle of Ekatra is:

> **Agents should be treated as dynamically allocatable computational resources whose number and assignment can change according to the state of the software-development process.**

The system should therefore demonstrate more than communication between multiple AI agents.

A successful prototype must visibly demonstrate the complete adaptive cycle:

```text
Requirement
    ↓
Task Decomposition
    ↓
Task Execution
    ↓
System Observation
    ↓
Workload / Risk Analysis
    ↓
Adaptive Decision
    ↓
Agent Allocation
    ↓
Task Execution
    ↓
Feedback
    ↺
```

This adaptive feedback mechanism constitutes the central research focus of Ekatra.
