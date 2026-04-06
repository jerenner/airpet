# Physics Environment Refinement Tracker

Last updated: 2026-04-06

## Mission

Incrementally add the highest-value Geant4 simulation-environment capabilities to AIRPET, starting with magnetic-field support and expanding into a coherent detector-focused environment model.

## Scope

In scope:

- magnetic fields
- electric fields
- local field assignment
- region-specific cuts and user limits
- serialization, validation, UI, AI, and runtime plumbing for those features

Out of scope for a single cycle:

- full CAD authoring
- multi-capability mega-refactors
- broad unrelated workflow or parser work

## Operating Loop

Each refinement cycle should do exactly one backlog item:

1. Read this tracker and `docs/PHYSICS_ENVIRONMENT_REFINEMENT_CONTEXT.md`.
2. Pick the task marked `NEXT`.
3. If nothing is marked `NEXT`, pick the highest-priority `PENDING` task and mark it `NEXT`.
4. Implement that task end to end.
5. Add or update focused regression tests, deterministic smoke coverage, or example fixtures.
6. Run the smallest sufficient test suite.
7. Update this tracker:
   - set the finished task to `DONE` or `BLOCKED`
   - add a short cycle-log entry
   - choose the next `NEXT` task
8. Stop after one task.

If blocked:

- record the blocker clearly
- mark the task `BLOCKED`
- nominate the next unblocked task as `NEXT`

## Definition Of Done

A task is only `DONE` when all of the following are true:

- the environment capability exists in saved AIRPET state
- the Geant4 runtime consumes it
- focused regression or smoke coverage passes locally
- any required UI and/or AI surfaces are updated to keep the feature usable
- this tracker records the outcome and next task

## Current Status

- Overall phase: roadmap phase R1, active
- Dependency note: workflow refinement is exhausted; the physics-environment loop is now active
- Current priority: PER-002
- Success metric: AIRPET can define and run a minimal field-aware simulation without hand-editing Geant4 code or macros outside the product workflow

## Current NEXT Task

PER-002: Thread the global uniform magnetic field from saved project state into Geant4 runtime initialization.

Reason:

- the saved-state contract is now explicit and validated
- runtime plumbing is the next unlock for a field-aware simulation path
- it keeps the MVP sequence aligned with the roadmap

## Backlog

Statuses:

- `NEXT`
- `PENDING`
- `IN_PROGRESS`
- `BLOCKED`
- `DONE`

| ID | Priority | Area | Feature | Status | Notes |
| --- | --- | --- | --- | --- | --- |
| PER-001 | P0 | Environment Model | Define a saved-project environment schema for a global uniform magnetic field, including validation and defaults | DONE | Added an explicit environment object with default zero-field state, strict field-vector validation, and legacy top-level migration into the saved-project contract |
| PER-002 | P0 | Runtime | Thread the global uniform magnetic field from saved project state into Geant4 runtime initialization | NEXT | Land runtime plumbing only after the saved-state contract is clear |
| PER-003 | P0 | Testing | Add a deterministic field-on versus field-off regression or smoke path using a compact charged-particle example | PENDING | Prefer a tiny example that makes deflection or trajectory change obvious |
| PER-004 | P1 | UI | Add UI surfaces for creating, editing, and inspecting a global magnetic field | PENDING | Reuse the same saved-state contract from PER-001 |
| PER-005 | P1 | AI | Add AI/backend tool surfaces for reading and writing global magnetic-field configuration | PENDING | Keep AI and UI on the same source of truth |
| PER-006 | P1 | Fields | Add local magnetic-field assignment to selected volumes or regions | PENDING | Extend the same environment abstraction rather than adding a parallel path |
| PER-007 | P1 | Fields | Add electric-field support on the shared environment abstraction | PENDING | Avoid magnetic-only assumptions in the design |
| PER-008 | P2 | Examples | Add compact example assets and templates for field-aware simulations | PENDING | Keep examples tiny and deterministic |
| PER-009 | P2 | Environment | Add region-specific production cuts and user limits on the same environment layer | PENDING | Keep fields, cuts, and limits cohesive |
| PER-010 | P2 | Analysis | Add field-aware run metadata and analysis summaries so environment variants are visible in outputs | PENDING | Make environment configuration easy to inspect after the run |

## Cycle Log

| Date | Task | Outcome | Notes |
| --- | --- | --- | --- |
| 2026-04-06 | Backlog setup | DONE | Created the physics-environment refinement context and seeded the first roadmap phase, starting with global uniform magnetic-field support |
| 2026-04-06 | Tracker refinement | DONE | Split the first-phase backlog into smaller automation-friendly slices and linked it to the broader post-workflow roadmap |
| 2026-04-06T13:21:08+02:00 | PER-001 global uniform magnetic field schema | DONE | Files: `src/geometry_types.py`, `tests/test_environment_state.py`, `docs/PHYSICS_ENVIRONMENT_REFINEMENT_TRACKER.md`. Tests: `/Users/marth/miniconda/envs/airpet/bin/pytest tests/test_environment_state.py -q`. Outcome: added an explicit environment object with default zero-field state, strict validation for the canonical magnetic-field vector, legacy top-level migration, and save/load roundtrip coverage. Next: PER-002 |

## Notes For Future Reordering

- It is fine to reorder tasks if a lower-level abstraction change is discovered first.
- Prefer capabilities that unlock new simulation classes over polish on already-supported flows.
- Keep the environment model unified so fields, cuts, and limits do not become disconnected subsystems.
- Keep task size small enough that one automation cycle can plausibly finish one backlog item end to end.
