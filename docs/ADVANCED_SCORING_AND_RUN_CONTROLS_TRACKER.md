# Advanced Scoring And Run Controls Tracker

Last updated: 2026-04-11

## Mission

Incrementally add the highest-value Geant4 scoring, tally, result-summary, and run-control capabilities to AIRPET so users can answer detector-study questions more directly from inside the product.

## Scope

In scope:

- scoring meshes
- common tallies
- run manifests and artifact metadata
- result summary and comparison surfaces
- AI/backend scoring inspection and result explanation
- focused expert run controls that materially affect scoring workflows

Out of scope for a single cycle:

- new detector-generator families
- multimodal geometry intake
- broad unrelated UI redesign
- multiple loosely related scoring capabilities in one run

## Operating Loop

Each refinement cycle should do exactly one backlog item:

1. Read this tracker and `docs/ADVANCED_SCORING_AND_RUN_CONTROLS_CONTEXT.md`.
2. Pick the task marked `NEXT`.
3. If nothing is marked `NEXT`, pick the highest-priority `PENDING` task and mark it `NEXT`.
4. Implement that task end to end.
5. Add or update focused regression tests, deterministic smoke coverage, or compact example fixtures.
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

- the scoring or run-control capability exists in product code or saved-state contract as required
- focused regression, example, or smoke coverage passes locally
- any required UI and/or AI surfaces are updated to keep the feature usable
- this tracker records the outcome and next task

## Current Status

- Overall phase: roadmap phase R4, active
- Dependency note: detector-generator stabilization is exhausted
- Current priority: establish a compact saved-project scoring and run-controls contract, then land a practical scoring-mesh MVP
- Success metric: AIRPET can define, save, inspect, run, and compare at least one useful scoring workflow without hand-editing Geant4 macros outside the product workflow

## Current NEXT Task

`ASRC-003`: add UI surfaces to create, inspect, and revise scoring meshes and basic tally settings.

## Backlog

Statuses:

- `NEXT`
- `PENDING`
- `IN_PROGRESS`
- `BLOCKED`
- `DONE`

| ID | Priority | Area | Feature | Status | Notes |
| --- | --- | --- | --- | --- | --- |
| ASRC-001 | P0 | Foundation | Define a saved-project scoring and run-controls contract for scoring meshes, tally requests, and run-manifest defaults | DONE | Saved projects now carry a normalized `scoring` contract with shared defaults, validation, and runtime-facing manifest resolution |
| ASRC-002 | P0 | Runtime | Implement a scoring-mesh MVP with Geant4 runtime plumbing and deterministic artifact output | DONE | Runs now force hit retention only when an enabled `energy_deposit` mesh tally needs it, then emit a deterministic `scoring_artifacts.json` bundle plus metadata summary for supported scoring meshes |
| ASRC-003 | P1 | UI | Add UI surfaces to create, inspect, and revise scoring meshes and basic tally settings | NEXT | Keep the first UI narrow and inspector-friendly rather than building a broad analysis dashboard immediately |
| ASRC-004 | P1 | Tallies | Add common tally support such as dose, fluence, or current on the shared scoring abstraction | PENDING | Reuse the scoring contract rather than adding one-off special cases |
| ASRC-005 | P1 | Reproducibility | Add a run manifest and artifact-bundle summary that makes scoring runs easier to audit and compare | PENDING | Include enough structured metadata to identify geometry, environment, scoring config, and output files |
| ASRC-006 | P2 | Analysis UX | Add compact result-summary and multi-run comparison surfaces for scoring outputs | PENDING | Start with deterministic summaries before richer plotting or visualization |
| ASRC-007 | P2 | AI | Add AI/backend tool surfaces for scoring inspection and result explanation | PENDING | The AI should be able to inspect the active scoring setup and summarize the resulting run outputs |
| ASRC-008 | P2 | Expert Controls | Add selected expert run controls that materially improve scoring workflows | PENDING | Focus on controls that improve scoring usefulness rather than broad Geant4 option coverage |

## Cycle Log

| Date | Task | Outcome | Notes |
| --- | --- | --- | --- |
| 2026-04-11 | Backlog setup | DONE | Created the advanced-scoring-and-run-controls context and seeded the active roadmap phase, starting with a saved-project scoring and run-controls contract before the scoring-mesh MVP |
| 2026-04-11 | ASRC-001 saved scoring/run-controls contract | DONE | Files: [`/Volumes/nvme/projects/airpet/src/geometry_types.py`](/Volumes/nvme/projects/airpet/src/geometry_types.py), [`/Volumes/nvme/projects/airpet/src/project_manager.py`](/Volumes/nvme/projects/airpet/src/project_manager.py), [`/Volumes/nvme/projects/airpet/tests/test_scoring_state.py`](/Volumes/nvme/projects/airpet/tests/test_scoring_state.py), [`/Volumes/nvme/projects/airpet/docs/ADVANCED_SCORING_AND_RUN_CONTROLS_TRACKER.md`](/Volumes/nvme/projects/airpet/docs/ADVANCED_SCORING_AND_RUN_CONTROLS_TRACKER.md). Tests: `python3 -m py_compile src/geometry_types.py src/project_manager.py tests/test_scoring_state.py`; `python3 -m pytest tests/test_scoring_state.py -q`; `python3 - <<'PY' ... pytest.main(['tests/test_geant4_field_macro.py', '-q']) ... PY` (with OCC stub bootstrap). Outcome: added a first-class saved-project `scoring` contract for scoring meshes, tally requests, and run-manifest defaults; normalized and validated that state alongside the rest of `GeometryState`; threaded the saved run-manifest defaults into macro generation and simulation metadata as resolved manifest data plus compact scoring summaries; and added focused regression coverage for contract roundtrips, invalid-entry fallback, and resolved macro defaults. Next: ASRC-002. |
| 2026-04-11 | ASRC-002 scoring-mesh runtime MVP | DONE | Files: [`/Volumes/nvme/projects/airpet/src/scoring_artifacts.py`](/Volumes/nvme/projects/airpet/src/scoring_artifacts.py), [`/Volumes/nvme/projects/airpet/src/project_manager.py`](/Volumes/nvme/projects/airpet/src/project_manager.py), [`/Volumes/nvme/projects/airpet/app.py`](/Volumes/nvme/projects/airpet/app.py), [`/Volumes/nvme/projects/airpet/tests/test_scoring_state.py`](/Volumes/nvme/projects/airpet/tests/test_scoring_state.py), [`/Volumes/nvme/projects/airpet/tests/test_scoring_artifacts.py`](/Volumes/nvme/projects/airpet/tests/test_scoring_artifacts.py), [`/Volumes/nvme/projects/airpet/tests/test_ai_api.py`](/Volumes/nvme/projects/airpet/tests/test_ai_api.py), [`/Volumes/nvme/projects/airpet/docs/ADVANCED_SCORING_AND_RUN_CONTROLS_TRACKER.md`](/Volumes/nvme/projects/airpet/docs/ADVANCED_SCORING_AND_RUN_CONTROLS_TRACKER.md). Tests: `python3 -m py_compile src/scoring_artifacts.py src/project_manager.py app.py tests/test_scoring_state.py tests/test_scoring_artifacts.py tests/test_ai_api.py`; `python3 -m pytest tests/test_scoring_state.py -q`; `python3 - <<'PY' ... write_scoring_artifact_bundle fake-hdf5 smoke ... PY`. Outcome: implemented the first supported scoring-mesh runtime path by resolving enabled `energy_deposit` mesh tallies from saved scoring state, forcing hit retention only when that MVP path needs it, generating a deterministic `scoring_artifacts.json` bundle plus metadata summary after successful runs, and reusing the shared simulation runner for both AI and HTTP launch flows; added focused regression coverage for the forced-manifest behavior plus artifact-bundle generation, while the new h5py-backed pytest files remain present for full-environment runs. Next: ASRC-003. |

## Notes For Future Reordering

- It is fine to pull a runtime slice ahead of UI work if the underlying scoring contract needs proof first.
- Prefer compact scoring workflows that are easy to validate deterministically.
- Keep the first scoring surfaces focused on clear study value, not on exhaustive Geant4 option coverage.
- Multimodal AI geometry intake is intentionally deferred until AIRPET has stronger scoring and result-summary infrastructure to validate what the multimodal path produces.
