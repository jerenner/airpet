# Workflow Refinement Tracker

Last updated: 2026-04-05

## Mission

Incrementally harden AIRPET's highest-value end-to-end workflows until they are trustworthy as product experiences, with each improvement backed by a focused automated regression, replay artifact, or deterministic smoke test.

## Scope

In scope:

- tutorial and first-run workflows
- AI-assisted workflow replays
- simulation / analysis / param-study / optimization workflow contracts
- history and artifact flows that affect user trust

Out of scope for a single cycle:

- broad parser or infrastructure work not anchored to a workflow
- doing multiple workflow tasks in one run

## Operating Loop

Each refinement cycle should do exactly one backlog item:

1. Read this tracker and `docs/WORKFLOW_REFINEMENT_CONTEXT.md`.
2. Pick the task marked `NEXT`.
3. If nothing is marked `NEXT`, pick the highest-priority `PENDING` task and mark it `NEXT`.
4. Implement that task end to end.
5. Add or update focused regression tests, replay artifacts, or deterministic smoke coverage.
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

- the workflow path is protected by an automated regression, replay artifact, or deterministic smoke test
- any required code or contract changes are implemented
- the relevant targeted tests passed locally
- this tracker records the outcome and next task

## Current Status

- Overall phase: workflow backlog execution
- Dependency note: the separate AI/GDML refinements loop still has one remaining GDML task (`GDML-013`); workflow refinement continues independently
- Current priority: WF-002

## Current NEXT Task

WF-002: Add an AI geometry -> preflight -> simulation launch -> analysis smoke workflow.

Reason:

- it is the next highest-value user-visible workflow after the silicon first-run path
- it should exercise geometry edits, preflight gating, simulation launch, and analysis fetch in one compact smoke

## Backlog

Statuses:

- `NEXT`
- `PENDING`
- `IN_PROGRESS`
- `BLOCKED`
- `DONE`

| ID | Priority | Area | Feature | Status | Notes |
| --- | --- | --- | --- | --- | --- |
| WF-001 | P0 | Workflow | Add a deterministic regression for the silicon detector "first run" param-study workflow | DONE | Built a backend regression around `examples/silicon_detector/silicon_optimizer_starter.project.json`; the starter study now records its active source binding and the launch path is deterministic under a mock evaluator |
| WF-002 | P0 | Workflow | Add an AI geometry -> preflight -> simulation launch -> analysis smoke workflow | NEXT | Prefer a compact replay or benchmark-style artifact over a heavy browser test |
| WF-003 | P1 | Preflight | Extend workflow replay coverage for saved-version preflight compare flows | PENDING | Build on the existing scoped preflight replay harness and version-compare fixtures |
| WF-004 | P1 | Analysis | Lock in end-to-end analysis/export workflow contract coverage | PENDING | Focus on sensitive-detector filtering and downloaded artifact structure |
| WF-005 | P1 | Optimization | Add a simulation-in-loop optimization workflow regression with selected source subsets | PENDING | Use the existing selected-source parity work as the starting point |
| WF-006 | P2 | History | Add workflow-level regression coverage for single-delete and bulk-delete history flows | PENDING | Cover both backend behavior and the JS selection flow where practical |
| WF-007 | P2 | AI Session | Add a refresh-persistence workflow regression for prompts, replies, and saved tool activity | PENDING | Aim at the trust-critical "refresh after AI turn" path |

## Cycle Log

| Date | Task | Outcome | Notes |
| --- | --- | --- | --- |
| 2026-04-04 | Backlog setup | DONE | Created the workflow-refinement context and seeded the first workflow backlog from live AIRPET assets plus historical audit findings moved under `docs/old/` |
| 2026-04-05 | WF-001 silicon first-run regression | DONE | Files: `examples/silicon_detector/silicon_optimizer_starter.project.json`, `tests/test_silicon_detector_first_run_workflow.py`. Test: `PYTHONPATH=/tmp/occ_stub:$PYTHONPATH pytest tests/test_silicon_detector_first_run_workflow.py`. Outcome: locked in deterministic surrogate-GP coverage for the silicon starter project and recorded the active source provenance in the study contract. Next: WF-002 |

## Notes For Future Reordering

- It is fine to reorder tasks if a newly discovered workflow bug is more urgent.
- Prefer canonical user journeys before edge workflows.
- Prefer deterministic coverage using existing project/example assets before inventing synthetic scenarios.
