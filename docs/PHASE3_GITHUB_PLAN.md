# AIRPET Phase 3 — GitHub Milestones + Issues Breakdown

Use this file as copy/paste source for milestone and issue creation.

---

## Milestones

## M1 — Smart CAD + Preflight Foundation
**Duration:** Sprint 1-2  
**Goal:** Build import report + geometry QA foundation + first primitive mapping pass.

### Issues

1. **[P3][M1] Smart CAD classifier skeleton + confidence model**
- **Labels:** `phase-3`, `smart-cad`, `backend`, `priority-high`
- **Estimate:** 5 pts
- **Depends on:** none
- **Description:**
  - Implement classifier interface for CAD entities.
  - Add confidence score schema.
  - Emit structured mapping decisions for downstream export.
- **Acceptance criteria:**
  - Classifier returns typed candidates + confidence + fallback reason.
  - Unit tests cover classifier outputs for representative fixtures.

2. **[P3][M1] Primitive mapping v1 (plane/cylinder/sphere, cone optional)**
- **Labels:** `phase-3`, `smart-cad`, `geometry`, `priority-high`
- **Estimate:** 8 pts
- **Depends on:** #1
- **Description:**
  - Fit primitive parameters from recognized entities.
  - Build transforms/orientation robustly.
- **Acceptance criteria:**
  - Mapping works for benchmark fixture set.
  - Invalid fits fail safely to tessellated fallback.

3. **[P3][M1] Mixed-mode export pipeline (primitive + tessellated fallback)**
- **Labels:** `phase-3`, `smart-cad`, `backend`
- **Estimate:** 8 pts
- **Depends on:** #1, #2
- **Description:**
  - Export hybrid geometry without breaking existing pipeline.
  - Preserve deterministic output ordering.
- **Acceptance criteria:**
  - Mixed-mode geometry serializes and runs in Geant4.
  - Existing full-tessellated mode remains available.

4. **[P3][M1] Import report UI: conversion ratio, confidence, fallback reasons**
- **Labels:** `phase-3`, `frontend`, `smart-cad`, `ux`
- **Estimate:** 5 pts
- **Depends on:** #1, #3
- **Description:**
  - Add import report panel with summary + per-part diagnostics.
- **Acceptance criteria:**
  - User can identify why any part was fallback-converted.
  - Ratio (% primitive vs tessellated) is visible post-import.

5. **[P3][M1] Geometry preflight checks v1 (overlap/material/tiny-feature)**
- **Labels:** `phase-3`, `qa`, `geometry`, `backend`, `priority-high`
- **Estimate:** 8 pts
- **Depends on:** none
- **Description:**
  - Implement checks before simulation starts.
  - Emit severity-typed diagnostics.
- **Acceptance criteria:**
  - Known-bad fixtures fail fast with actionable messages.
  - Diagnostics include object identifiers.

6. **[P3][M1] Preflight diagnostics UI + run-blocking behavior**
- **Labels:** `phase-3`, `frontend`, `qa`, `ux`
- **Estimate:** 3 pts
- **Depends on:** #5
- **Description:**
  - Display errors/warnings in pre-run flow.
  - Block run on error severity, allow warnings with explicit confirmation.
- **Acceptance criteria:**
  - Run button behavior matches severity rules.
  - User-facing messages require no log reading.

7. **[P3][M1] Benchmark fixture pack for smart import + preflight**
- **Labels:** `phase-3`, `tests`, `benchmark`, `infra`
- **Estimate:** 5 pts
- **Depends on:** none
- **Description:**
  - Curate CAD scenes and expected mapping/preflight outcomes.
- **Acceptance criteria:**
  - Fixtures versioned in repo and used in automated tests.

---

## M2 — Smart CAD Stabilization + Performance Proof
**Duration:** Sprint 3  
**Goal:** Validate hybrid import reliability and demonstrate measurable gains.

### Issues

8. **[P3][M2] Smart CAD reliability hardening and edge-case fallback policy**
- **Labels:** `phase-3`, `smart-cad`, `backend`, `stability`
- **Estimate:** 5 pts
- **Depends on:** M1 complete
- **Acceptance criteria:**
  - No regressions on fixture pack.
  - Fallback policy is documented and test-covered.

9. **[P3][M2] Performance benchmark harness (full tessellated vs hybrid)**
- **Labels:** `phase-3`, `benchmark`, `performance`, `backend`
- **Estimate:** 5 pts
- **Depends on:** #3, #7
- **Acceptance criteria:**
  - Automated benchmark command outputs runtime/memory summary.
  - Results stored in machine-readable format.

10. **[P3][M2] Publish benchmark report + target thresholds**
- **Labels:** `phase-3`, `docs`, `performance`
- **Estimate:** 2 pts
- **Depends on:** #9
- **Acceptance criteria:**
  - Report includes at least one scene with measurable hybrid improvement.
  - Thresholds for regression alerts are defined.

---

## M3 — Parametric Study Engine
**Duration:** Sprint 4  
**Goal:** Enable reproducible parameter sweeps and objective extraction.

### Issues

11. **[P3][M3] Parameter registry schema + persistence**
- **Labels:** `phase-3`, `backend`, `optimization`
- **Estimate:** 5 pts
- **Depends on:** none
- **Acceptance criteria:**
  - Parameters include bounds/default/units/constraints.
  - Config saved/restored with project.

12. **[P3][M3] Batch runner (grid + random/LHS)**
- **Labels:** `phase-3`, `backend`, `optimization`, `runner`
- **Estimate:** 8 pts
- **Depends on:** #11
- **Acceptance criteria:**
  - Runs execute in configured batch modes.
  - Seeded execution produces reproducible run order.

13. **[P3][M3] Objective extraction from HDF5 outputs**
- **Labels:** `phase-3`, `backend`, `analysis`, `optimization`
- **Estimate:** 5 pts
- **Depends on:** #12
- **Acceptance criteria:**
  - Objectives configurable and extracted automatically.
  - Failures produce clear per-run diagnostics.

14. **[P3][M3] Study UI (config, runs table, Pareto/objective plots)**
- **Labels:** `phase-3`, `frontend`, `optimization`, `ux`
- **Estimate:** 8 pts
- **Depends on:** #11, #12, #13
- **Acceptance criteria:**
  - User can configure, launch, inspect, and re-run studies from UI.

---

## M4 — Optimizer v1 (Classical)
**Duration:** Sprint 5  
**Goal:** Deliver automated constrained optimization.

### Issues

15. **[P3][M4] Optimizer core (Bayesian or CMA-ES) with constraints**
- **Labels:** `phase-3`, `optimizer`, `backend`, `priority-high`
- **Estimate:** 8 pts
- **Depends on:** M3 complete
- **Acceptance criteria:**
  - Supports objective minimization/maximization with constraints.
  - Configurable budget/early stopping.

16. **[P3][M4] Provenance logging + replay/verification flow**
- **Labels:** `phase-3`, `optimizer`, `backend`, `reproducibility`
- **Estimate:** 5 pts
- **Depends on:** #15
- **Acceptance criteria:**
  - Best candidate replayed and verified.
  - Complete metadata saved (seed, params, objective, status).

17. **[P3][M4] Optimizer UI (progress, budget, current best, fail reasons)**
- **Labels:** `phase-3`, `frontend`, `optimizer`, `ux`
- **Estimate:** 5 pts
- **Depends on:** #15, #16
- **Acceptance criteria:**
  - Live status shows progress and current best objective.
  - Failures are surfaced with actionable context.

18. **[P3][M4] Baseline comparison report (manual vs optimizer)**
- **Labels:** `phase-3`, `benchmark`, `optimizer`, `docs`
- **Estimate:** 3 pts
- **Depends on:** #15, #16
- **Acceptance criteria:**
  - At least one benchmark shows optimizer improvement over manual baseline.

---

## M5 — ML/PINN Feasibility Spike
**Duration:** Sprint 6  
**Goal:** Produce evidence-based go/no-go decision.

### Issues

19. **[P3][M5] Dataset export pipeline for surrogate experiments**
- **Labels:** `phase-3`, `ml-spike`, `backend`, `data`
- **Estimate:** 3 pts
- **Depends on:** M3 complete
- **Acceptance criteria:**
  - Study outputs can be exported into training-ready format.

20. **[P3][M5] Surrogate baseline experiment (GP/NN) + evaluation script**
- **Labels:** `phase-3`, `ml-spike`, `research`
- **Estimate:** 5 pts
- **Depends on:** #19
- **Acceptance criteria:**
  - Reproducible experiment comparing prediction error and speed.

21. **[P3][M5] Decision memo: PINN/surrogate go-no-go for Phase 4**
- **Labels:** `phase-3`, `ml-spike`, `docs`, `decision`
- **Estimate:** 2 pts
- **Depends on:** #20
- **Acceptance criteria:**
  - Written recommendation with quantitative evidence.
  - If go: define minimum production scope for next phase.

---

## Cross-cutting engineering issues

22. **[P3][X] Test expansion for smart-cad/preflight/studies/optimizer**
- **Labels:** `phase-3`, `tests`, `quality`
- **Estimate:** 8 pts (ongoing)
- **Depends on:** parallel to all milestones
- **Acceptance criteria:**
  - New code paths are covered by unit/integration tests.

23. **[P3][X] Developer docs: architecture + runbooks for Phase 3 systems**
- **Labels:** `phase-3`, `docs`, `devex`
- **Estimate:** 3 pts
- **Depends on:** ongoing
- **Acceptance criteria:**
  - Setup and troubleshooting docs exist for each workstream.

24. **[P3][X] CI checks for benchmark regression thresholds**
- **Labels:** `phase-3`, `ci`, `performance`, `quality`
- **Estimate:** 5 pts
- **Depends on:** #9, #10
- **Acceptance criteria:**
  - CI reports benchmark deltas and flags threshold breaches.

---

## Suggested labels to create

- `phase-3`
- `smart-cad`
- `preflight-qa`
- `optimization`
- `optimizer`
- `ml-spike`
- `benchmark`
- `reproducibility`
- `priority-high`
- `ux`
- `stability`

---

## Suggested issue template sections (for consistency)

- Problem statement
- User value
- Scope (in/out)
- Technical plan
- Risks
- Acceptance criteria
- Test plan
- Dependencies
