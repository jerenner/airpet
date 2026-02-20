# AIRPET Phase 3 PRD

**Status:** Draft  
**Owner:** AIRPET team  
**Target window:** 10-12 weeks (6 sprints, 2 weeks each)

---

## 1) Summary

Phase 3 turns AIRPET from AI-assisted geometry/simulation into an optimization-ready detector design platform.

Core outcomes:
1. **Smart CAD Import v1** (hybrid primitive + tessellated output)
2. **Geometry Preflight QA** (catch failures before simulation)
3. **Parametric Studies + Objective Engine**
4. **Classical Optimizer v1** (Bayesian or CMA-ES)
5. **ML/PINN Feasibility Spike** (go/no-go decision)

---

## 2) Goals and non-goals

### Goals
- Reduce runtime and fragility from all-tessellated imports.
- Improve user trust by surfacing geometry errors before execution.
- Enable repeatable parameter sweeps and objective-driven design.
- Deliver first automated optimization loop with reproducible provenance.
- Decide whether surrogate/ML approaches are worth productizing.

### Non-goals (Phase 3)
- Full CAD kernel replacement.
- Production-grade PINN stack in this phase.
- Enterprise multi-tenant workflow/security features.

---

## 3) User outcomes

### Primary users
- Detector physicists and simulation engineers designing geometry under performance constraints.

### Jobs to be done
- Import CAD and get simulation-ready geometry with fewer manual fixes.
- Detect geometry/material issues early.
- Sweep design parameters and compare objective trade-offs.
- Automatically find stronger candidate designs under constraints.

---

## 4) Scope by workstream

## A. Smart CAD Import v1 (Highest priority)

### Problem
STEP imports currently lean heavily on tessellation, which can hurt performance, editability, and robustness.

### Scope
- Surface/face recognition: plane, cylinder, sphere, cone (torus optional stretch).
- Primitive candidate fitting: dimensions, transforms, orientation.
- Confidence score per mapped body.
- Mixed-mode export: primitive where high confidence, tessellated fallback elsewhere.
- Import report UI:
  - primitive vs tessellated ratio
  - fallback reasons
  - warnings/confidence indicators
- User override toggle: force full tessellated fallback.

### Acceptance criteria
- On benchmark CAD set, **>=50% of eligible parts** map to primitives (target 50-70%).
- Mixed-mode geometry passes validity checks.
- At least one benchmark case shows measurable runtime and/or memory improvement vs full tessellated baseline.
- Import report visible and understandable without log inspection.

---

## B. Geometry Preflight QA

### Problem
Users discover overlap/material/navigation errors too late (during/after failed simulation).

### Scope
- Overlap/intersection checks.
- Tiny/degenerate feature warnings.
- Missing/invalid material assignment checks.
- Navigation-risk heuristics (likely stuck tracks / pathological geometry).
- Actionable diagnostics linked to object IDs.

### Acceptance criteria
- Known-invalid scenes fail fast with clear messages.
- Users can identify offending objects directly from diagnostics.
- Error classes are test-covered and deterministic.

---

## C. Parametric Studies + Objective Engine

### Problem
Optimization loops currently require custom scripting and manual interpretation.

### Scope
- Parameter registry (name, bounds, default, units, constraints).
- Study configuration and persistence in project state.
- Batch execution modes:
  - grid
  - random/LHS
- Objective extraction from HDF5 outputs.
- Result exploration UI:
  - sortable runs table
  - objective scatter/Pareto view

### Acceptance criteria
- One end-to-end multi-objective study reproducibly executes from saved config.
- Objective metrics auto-extract and appear in results table/plot.
- Users can re-run the same study with fixed seed and get consistent sequence.

---

## D. Optimizer v1 (Classical)

### Problem
Users need guided search through high-dimensional design space.

### Scope
- First optimizer implementation: Bayesian optimization **or** CMA-ES.
- Constraint support.
- Early stopping/budget controls.
- Best-candidate replay + verification run.
- Provenance logging (params, objective, seed, run metadata).

### Acceptance criteria
- On at least one benchmark objective, optimizer beats manual baseline.
- End-to-end run reproducible via saved config + seed.
- Failure/restart behavior is robust and recoverable.

---

## E. ML/PINN Feasibility Spike

### Problem
ML/PINN could reduce expensive simulation calls, but cost/complexity is uncertain.

### Scope
- Build dataset from parametric/optimizer runs.
- Train lightweight surrogate baseline (GP/NN).
- Compare speed/accuracy tradeoffs against classical optimizer.
- Decision memo with go/no-go recommendation.

### Exit criteria
- **Go** only if surrogate yields meaningful wall-clock improvements at acceptable objective error.
- Otherwise defer ML to later phase and deepen classical tooling.

---

## 5) UX requirements

- Import and QA messages must be concise, linked to objects, and actionable.
- Study setup should expose sane defaults and prevent invalid parameter bounds.
- Optimization runs should show progress, budget consumed, current best, and fail reasons.

---

## 6) Technical requirements

- Backward compatibility with existing project files.
- Deterministic run option (seeded execution).
- Telemetry/logging for import classification, preflight failures, and optimizer decisions.
- Tests for:
  - parser/mapping correctness
  - fallback behavior
  - objective extraction
  - optimizer reproducibility

---

## 7) Risks and mitigations

1. **CAD mapping false positives**  
   Mitigation: confidence threshold + fallback to tessellated + transparent report.

2. **Preflight false alarms**  
   Mitigation: severity levels (error/warn/info) and tuned thresholds.

3. **Optimizer instability/noisy objectives**  
   Mitigation: retries, smoothing/robust objective definitions, budget caps.

4. **ML complexity overrun**  
   Mitigation: strict spike scope and explicit go/no-go gate.

---

## 8) Milestones and timeline (proposed)

- **Sprint 1:** Preflight QA foundation + import report scaffolding
- **Sprint 2:** Smart CAD primitive mapping (plane/cylinder/sphere)
- **Sprint 3:** Mixed-mode stabilization + benchmark suite
- **Sprint 4:** Parametric studies + objective extraction
- **Sprint 5:** Optimizer v1 + provenance
- **Sprint 6:** Surrogate/PINN feasibility spike + decision memo

---

## 9) Success metrics

- % eligible CAD components mapped to primitives.
- Reduction in failed simulation starts due to geometry/material errors.
- Median simulation wall-clock improvement on benchmark scenes.
- Number of runs to best-known objective (manual vs optimizer).
- Decision quality for ML track (clear go/no-go with data).

---

## 10) Definition of Done (Phase 3)

Phase 3 is complete when:
- Hybrid smart import is stable and measurable.
- Preflight QA prevents common invalid runs.
- Parametric studies and optimization can run without custom scripts.
- Benchmark gains are demonstrated and documented.
- ML feasibility decision is recorded with evidence.
