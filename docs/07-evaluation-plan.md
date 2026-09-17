# Ekatra — Evaluation Plan

## 1. Research Question

> Can an AI software engineering organization dynamically change its team composition based on workload and risk during software development?

---

## 2. Experimental Comparison

Compare two configurations:

### Fixed Baseline

```text
Fixed agent composition
No runtime scaling
No adaptive allocation
```

### Ekatra Adaptive

```text
Dynamic agent allocation
Workload-aware scaling
Risk-aware adaptation
Runtime reassignment
Agent release
```

The two systems should use comparable workloads and conditions.

---

## 3. Experimental Variables

### Independent Variable

Orchestration strategy:

```text
Fixed
vs
Adaptive
```

### Workload Conditions

Experiments should include different levels such as:

```text
Low workload
Medium workload
High workload
Unbalanced workload
Failure-heavy workload
Risk-heavy workload
```

Exact workloads should be defined before running the final experiments.

---

## 4. Metrics

### Performance

* Total completion time
* Average task completion time
* Queue waiting time

### Resource Usage

* Maximum active agents
* Average active agents
* Agent utilization
* Agent active duration

### Adaptation

* Number of spawn events
* Number of termination events
* Number of reallocations
* Workload before/after adaptation
* Risk before/after adaptation

### Reliability

* Task success rate
* Task failure count
* Retry count

### Quality

Depending on the workload:

* Test pass rate
* Functional correctness
* Defects detected
* Security issues identified

---

## 5. Important Principle

Do not assume that adaptive orchestration is automatically better.

The experiments must determine its effects.

Possible outcomes include:

```text
Adaptive improves performance
Adaptive reduces resource usage
Adaptive improves quality
Adaptive introduces overhead
Adaptive performs similarly
```

Results must be reported according to observed data.

---

## 6. Experimental Procedure

For each workload:

```text
1. Prepare workload
2. Run fixed baseline
3. Record metrics
4. Reset environment
5. Run adaptive Ekatra
6. Record metrics
7. Compare results
```

Where practical, repeat experiments to reduce the effect of random variation.

---

## 7. Adaptive Behavior Verification

At least one experiment must demonstrate:

```text
Changed workload/risk
        ↓
Changed system measurement
        ↓
Adaptive decision
        ↓
Changed agent allocation
        ↓
Observable effect
```

This verifies that adaptation is genuinely occurring.

---

## 8. Reproducibility

Record:

* Workload configuration
* Model configuration
* Adaptive thresholds
* Workload weights
* Risk thresholds
* Agent limits
* Experiment timestamp
* Run identifier

Do not change experimental parameters between baseline and adaptive runs without documenting the change.

---

## 9. Result Interpretation

Results should include both raw measurements and derived metrics.

Graphs may include:

* Completion time comparison
* Average active agents
* Queue length over time
* Workload over time
* Agent scaling events
* Task failure/retry comparison

No metric should be selected solely because it produces a favorable result.

---

## 10. Research Limitation

The evaluation will be conducted on controlled software-development workloads and a prototype implementation.

Therefore, conclusions should be limited to the tested conditions and should not automatically be generalized to large-scale production software organizations.
