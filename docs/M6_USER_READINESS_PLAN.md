# M6 — User Readiness Plan

_Last updated: 2026-02-25_

## Goal
Move from research/prototype workflows to a user-ready optimization experience.

M6 focuses on:
1. Objective Builder UX (non-JSON)
2. Robust guardrails/defaults
3. Clear run management + explainability
4. Safe "apply best candidate" workflow

---

## Scope and Success Criteria

### In Scope
- User-facing controls for defining objectives without editing raw JSON.
- Safety defaults and hard limits to prevent runaway jobs or unsafe apply actions.
- Better visibility into optimization progress and candidate quality.
- Verification gate before applying geometry changes.

### Out of Scope
- New model families (e.g., PINNs) unless needed to unblock UX.
- Large benchmark campaigns beyond lightweight regression checks.
- Full product polishing (styling, docs overhaul, onboarding flows).

### M6 Exit Criteria
- A user can define an objective, launch a run, understand outcomes, and safely apply a verified candidate without touching internal JSON.

---

## Phase A — Safety + Control Foundation (Priority: P0)

### Objectives
- Prevent dangerous defaults and accidental destructive actions.
- Ensure every optimization run is bounded and interruptible.

### Deliverables
- Default safety caps:
  - max budget
  - max events per candidate
  - max wall-time per run
- Explicit mode controls:
  - classical only
  - surrogate only
  - head-to-head
- Dry-run / preview mode (no apply).
- Confirmation step before any geometry apply.

### Acceptance Criteria
- Runs cannot exceed configured hard caps.
- User cannot apply geometry without explicit confirmation.
- User can stop/cancel active runs safely.

---

## Phase B — Objective Builder MVP (Priority: P0)

### Objectives
- Replace JSON authoring with a practical UI/form flow.

### Deliverables
- Objective builder with composable blocks:
  - simulation metric term (e.g., `edep_sum`)
  - parameter penalty term (e.g., thickness/cost)
  - optional formula composition
- Validation and inline errors (missing keys, invalid formula, unsupported fields).
- "Preview generated objective config" panel for transparency.

### Acceptance Criteria
- User can create a working objective end-to-end via UI.
- Validation catches invalid objective definitions before run start.
- Generated objective config matches backend schema.

---

## Phase C — Run Management + Explainability (Priority: P1)

### Objectives
- Make optimization runs understandable and debuggable to non-developers.

### Deliverables
- Run dashboard with:
  - status/progress
  - budget used
  - current best score
  - success/failure counts
- Candidate table/leaderboard with objective decomposition
  (e.g., `edep_sum`, `cost_norm`, `distance_norm`, `score`).
- "Why selected" summary for top candidate
  (surrogate acquisition info or classical selection rationale).

### Acceptance Criteria
- User can identify best candidate and why it is best.
- Failures are visible with actionable reasons.
- Run summary is available without opening raw logs.

---

## Phase D — Safe Apply + Verification Workflow (Priority: P0)

### Objectives
- Ensure candidate application is reliable and reversible.

### Deliverables
- Verification step before apply:
  - replay best candidate for N repeats
  - report mean/variance and pass/fail rule
- Apply gate:
  - apply only if verification threshold passes
  - otherwise require explicit override
- Apply audit record:
  - candidate values
  - objective results
  - verification stats
  - timestamp/operator

### Acceptance Criteria
- Best candidate is not applied automatically without verification.
- Apply action leaves a clear audit trail.
- User can revert to previous geometry/version safely.

---

## Parallel Lightweight Regression Checks (during M6)

Keep these running as smoke/regression tests while implementing UX:
- Silicon v1.1 (1-parameter sim-loop)
- Silicon v2.1 (2-parameter sim-loop)
- Silicon v3.1b (5-parameter robust-normalized sim-loop)

Purpose: catch regressions while prioritizing user-readiness work.

---

## Suggested Execution Order
1. Phase A (P0)
2. Phase B (P0)
3. Phase D (P0)
4. Phase C (P1)

Rationale: safety and objective creation first; explainability can iterate in parallel once core guardrails and apply safety exist.

---

## Dependencies
- Existing simulation-in-loop API routes and objective engine (already in place from M5).
- Existing benchmark artifacts for sanity checks.

---

## Notes
- M6 is a productization milestone, not a model-research milestone.
- GP/classical competitiveness can continue to evolve in the background; user safety and clarity are the immediate priorities.
