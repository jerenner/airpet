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
- Current priority: none remaining
- Success metric: AIRPET can define, save, inspect, run, and compare at least one useful scoring workflow without hand-editing Geant4 macros outside the product workflow

## Current NEXT Task

None remaining. `ASRC-008` is complete and this tracker has no `NEXT` or `PENDING` items left.

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
| ASRC-003 | P1 | UI | Add UI surfaces to create, inspect, and revise scoring meshes and basic tally settings | DONE | Properties now exposes a narrow scoring mesh inspector with add/delete flows, inline mesh edits, and per-mesh tally checkboxes |
| ASRC-004 | P1 | Tallies | Add common tally support such as dose, fluence, or current on the shared scoring abstraction | DONE | Runtime scoring now supports `energy_deposit` and `n_of_step` tallies on the shared mesh abstraction, with quantity-aware artifact summaries for mixed outputs |
| ASRC-005 | P1 | Reproducibility | Add a run manifest and artifact-bundle summary that makes scoring runs easier to audit and compare | DONE | Runs now record a deterministic `run_manifest_summary` plus bundle-linked audit metadata that identifies geometry, environment, scoring config, and output files |
| ASRC-006 | P2 | Analysis UX | Add compact result-summary and multi-run comparison surfaces for scoring outputs | DONE | The scoring panel now shows compact loaded-run scoring totals plus an automatic comparison against the previous loaded scoring run using existing run-manifest metadata |
| ASRC-007 | P2 | AI | Add AI/backend tool surfaces for scoring inspection and result explanation | DONE | AI tools can now inspect the saved scoring state directly and fetch a compact per-run scoring summary with bundle status and per-quantity totals |
| ASRC-008 | P2 | Expert Controls | Add selected expert run controls that materially improve scoring workflows | DONE | Saved scoring defaults now expose focused expert controls in the scoring panel and drive run-option defaults unless a user overrides them per run |

## Cycle Log

| Date | Task | Outcome | Notes |
| --- | --- | --- | --- |
| 2026-04-11 | Backlog setup | DONE | Created the advanced-scoring-and-run-controls context and seeded the active roadmap phase, starting with a saved-project scoring and run-controls contract before the scoring-mesh MVP |
| 2026-04-11 | ASRC-001 saved scoring/run-controls contract | DONE | Files: [`/Volumes/nvme/projects/airpet/src/geometry_types.py`](/Volumes/nvme/projects/airpet/src/geometry_types.py), [`/Volumes/nvme/projects/airpet/src/project_manager.py`](/Volumes/nvme/projects/airpet/src/project_manager.py), [`/Volumes/nvme/projects/airpet/tests/test_scoring_state.py`](/Volumes/nvme/projects/airpet/tests/test_scoring_state.py), [`/Volumes/nvme/projects/airpet/docs/ADVANCED_SCORING_AND_RUN_CONTROLS_TRACKER.md`](/Volumes/nvme/projects/airpet/docs/ADVANCED_SCORING_AND_RUN_CONTROLS_TRACKER.md). Tests: `python3 -m py_compile src/geometry_types.py src/project_manager.py tests/test_scoring_state.py`; `python3 -m pytest tests/test_scoring_state.py -q`; `python3 - <<'PY' ... pytest.main(['tests/test_geant4_field_macro.py', '-q']) ... PY` (with OCC stub bootstrap). Outcome: added a first-class saved-project `scoring` contract for scoring meshes, tally requests, and run-manifest defaults; normalized and validated that state alongside the rest of `GeometryState`; threaded the saved run-manifest defaults into macro generation and simulation metadata as resolved manifest data plus compact scoring summaries; and added focused regression coverage for contract roundtrips, invalid-entry fallback, and resolved macro defaults. Next: ASRC-002. |
| 2026-04-11 | ASRC-002 scoring-mesh runtime MVP | DONE | Files: [`/Volumes/nvme/projects/airpet/src/scoring_artifacts.py`](/Volumes/nvme/projects/airpet/src/scoring_artifacts.py), [`/Volumes/nvme/projects/airpet/src/project_manager.py`](/Volumes/nvme/projects/airpet/src/project_manager.py), [`/Volumes/nvme/projects/airpet/app.py`](/Volumes/nvme/projects/airpet/app.py), [`/Volumes/nvme/projects/airpet/tests/test_scoring_state.py`](/Volumes/nvme/projects/airpet/tests/test_scoring_state.py), [`/Volumes/nvme/projects/airpet/tests/test_scoring_artifacts.py`](/Volumes/nvme/projects/airpet/tests/test_scoring_artifacts.py), [`/Volumes/nvme/projects/airpet/tests/test_ai_api.py`](/Volumes/nvme/projects/airpet/tests/test_ai_api.py), [`/Volumes/nvme/projects/airpet/docs/ADVANCED_SCORING_AND_RUN_CONTROLS_TRACKER.md`](/Volumes/nvme/projects/airpet/docs/ADVANCED_SCORING_AND_RUN_CONTROLS_TRACKER.md). Tests: `python3 -m py_compile src/scoring_artifacts.py src/project_manager.py app.py tests/test_scoring_state.py tests/test_scoring_artifacts.py tests/test_ai_api.py`; `python3 -m pytest tests/test_scoring_state.py -q`; `python3 - <<'PY' ... write_scoring_artifact_bundle fake-hdf5 smoke ... PY`. Outcome: implemented the first supported scoring-mesh runtime path by resolving enabled `energy_deposit` mesh tallies from saved scoring state, forcing hit retention only when that MVP path needs it, generating a deterministic `scoring_artifacts.json` bundle plus metadata summary after successful runs, and reusing the shared simulation runner for both AI and HTTP launch flows; added focused regression coverage for the forced-manifest behavior plus artifact-bundle generation, while the new h5py-backed pytest files remain present for full-environment runs. Next: ASRC-003. |
| 2026-04-11 | ASRC-003 scoring mesh inspector UI | DONE | Files: [`/Volumes/nvme/projects/airpet/static/scoringUi.js`](/Volumes/nvme/projects/airpet/static/scoringUi.js), [`/Volumes/nvme/projects/airpet/static/uiManager.js`](/Volumes/nvme/projects/airpet/static/uiManager.js), [`/Volumes/nvme/projects/airpet/templates/index.html`](/Volumes/nvme/projects/airpet/templates/index.html), [`/Volumes/nvme/projects/airpet/src/project_manager.py`](/Volumes/nvme/projects/airpet/src/project_manager.py), [`/Volumes/nvme/projects/airpet/app.py`](/Volumes/nvme/projects/airpet/app.py), [`/Volumes/nvme/projects/airpet/tests/js/scoring_ui.test.mjs`](/Volumes/nvme/projects/airpet/tests/js/scoring_ui.test.mjs), [`/Volumes/nvme/projects/airpet/tests/test_scoring_state.py`](/Volumes/nvme/projects/airpet/tests/test_scoring_state.py), [`/Volumes/nvme/projects/airpet/docs/ADVANCED_SCORING_AND_RUN_CONTROLS_TRACKER.md`](/Volumes/nvme/projects/airpet/docs/ADVANCED_SCORING_AND_RUN_CONTROLS_TRACKER.md). Tests: `python3 -m py_compile src/project_manager.py app.py tests/test_scoring_state.py`; `node --check static/scoringUi.js`; `node --check static/uiManager.js`; `node --test tests/js/scoring_ui.test.mjs`; `python3 -m pytest tests/test_scoring_state.py -q`. Outcome: added a narrow Properties-panel scoring surface that creates and deletes saved world-space box meshes, lets users revise mesh geometry and bins inline, and exposes per-mesh tally checkboxes with an explicit runtime-support hint; extended `update_property` so scoring edits persist as one validated saved-state contract instead of ad hoc partial fields; and added focused UI-helper plus backend regression coverage for deterministic mesh/tally creation, rename synchronization, quantity toggles, and invalid scoring-state rejection. Next: ASRC-004. |
| 2026-04-11 | ASRC-004 shared runtime tally extension | DONE | Files: [`/Volumes/nvme/projects/airpet/src/scoring_artifacts.py`](/Volumes/nvme/projects/airpet/src/scoring_artifacts.py), [`/Volumes/nvme/projects/airpet/static/scoringUi.js`](/Volumes/nvme/projects/airpet/static/scoringUi.js), [`/Volumes/nvme/projects/airpet/static/uiManager.js`](/Volumes/nvme/projects/airpet/static/uiManager.js), [`/Volumes/nvme/projects/airpet/tests/js/scoring_ui.test.mjs`](/Volumes/nvme/projects/airpet/tests/js/scoring_ui.test.mjs), [`/Volumes/nvme/projects/airpet/tests/test_scoring_state.py`](/Volumes/nvme/projects/airpet/tests/test_scoring_state.py), [`/Volumes/nvme/projects/airpet/tests/test_scoring_artifacts.py`](/Volumes/nvme/projects/airpet/tests/test_scoring_artifacts.py), [`/Volumes/nvme/projects/airpet/docs/ADVANCED_SCORING_AND_RUN_CONTROLS_TRACKER.md`](/Volumes/nvme/projects/airpet/docs/ADVANCED_SCORING_AND_RUN_CONTROLS_TRACKER.md). Tests: `python3 -m py_compile src/scoring_artifacts.py tests/test_scoring_artifacts.py tests/test_scoring_state.py app.py`; `node --check static/scoringUi.js`; `node --check static/uiManager.js`; `python3 -m pytest tests/test_scoring_state.py -q`; `node --test tests/js/scoring_ui.test.mjs`; `python3 - <<'PY' ... write_scoring_artifact_bundle mixed energy_deposit/n_of_step smoke with patched hit-loader ... PY`. Outcome: extended the shared scoring-mesh runtime from `energy_deposit` only to both `energy_deposit` and `n_of_step`, kept the saved tally abstraction unchanged, made artifact summaries quantity-aware so mixed-unit bundles no longer collapse into one misleading top-level total, and updated the scoring inspector hints/runtime badges accordingly; the h5py-backed artifact pytest file was updated alongside this slice, but this automation shell still lacks `h5py`, so the executed runtime coverage used a deterministic patched-loader smoke plus compile checks. Next: ASRC-005. |
| 2026-04-11 | ASRC-005 run manifest and artifact-bundle audit summary | DONE | Files: [`/Volumes/nvme/projects/airpet/src/scoring_artifacts.py`](/Volumes/nvme/projects/airpet/src/scoring_artifacts.py), [`/Volumes/nvme/projects/airpet/src/project_manager.py`](/Volumes/nvme/projects/airpet/src/project_manager.py), [`/Volumes/nvme/projects/airpet/tests/test_scoring_state.py`](/Volumes/nvme/projects/airpet/tests/test_scoring_state.py), [`/Volumes/nvme/projects/airpet/tests/test_scoring_artifacts.py`](/Volumes/nvme/projects/airpet/tests/test_scoring_artifacts.py), [`/Volumes/nvme/projects/airpet/tests/test_scoring_artifact_summary_smoke.py`](/Volumes/nvme/projects/airpet/tests/test_scoring_artifact_summary_smoke.py), [`/Volumes/nvme/projects/airpet/docs/ADVANCED_SCORING_AND_RUN_CONTROLS_TRACKER.md`](/Volumes/nvme/projects/airpet/docs/ADVANCED_SCORING_AND_RUN_CONTROLS_TRACKER.md). Tests: `python3 -m py_compile src/scoring_artifacts.py src/project_manager.py tests/test_scoring_state.py tests/test_scoring_artifacts.py tests/test_scoring_artifact_summary_smoke.py`; `python3 -m pytest tests/test_scoring_state.py -q -k 'generate_macro_records_scoring_contract_and_resolves_saved_run_manifest_defaults'`; `python3 -m pytest tests/test_scoring_artifact_summary_smoke.py -q`. Outcome: added a deterministic `run_manifest_summary` to generated run metadata, refreshed that summary after scoring bundles are written, and embedded the same audit context in `scoring_artifacts.json` so runs now carry stable geometry/config signatures plus explicit output-file inventory for audit and comparison; the h5py-backed artifact pytest file was updated alongside this slice, but this automation shell still lacks `h5py`, so the executed artifact coverage used a patched-loader smoke test instead. Next: ASRC-006. |
| 2026-04-11 | ASRC-006 scoring result-summary and previous-run comparison surfaces | DONE | Files: [`/Volumes/nvme/projects/airpet/static/scoringUi.js`](/Volumes/nvme/projects/airpet/static/scoringUi.js), [`/Volumes/nvme/projects/airpet/static/uiManager.js`](/Volumes/nvme/projects/airpet/static/uiManager.js), [`/Volumes/nvme/projects/airpet/static/main.js`](/Volumes/nvme/projects/airpet/static/main.js), [`/Volumes/nvme/projects/airpet/templates/index.html`](/Volumes/nvme/projects/airpet/templates/index.html), [`/Volumes/nvme/projects/airpet/tests/js/scoring_ui.test.mjs`](/Volumes/nvme/projects/airpet/tests/js/scoring_ui.test.mjs), [`/Volumes/nvme/projects/airpet/docs/ADVANCED_SCORING_AND_RUN_CONTROLS_TRACKER.md`](/Volumes/nvme/projects/airpet/docs/ADVANCED_SCORING_AND_RUN_CONTROLS_TRACKER.md). Tests: `node --check static/scoringUi.js`; `node --check static/uiManager.js`; `node --check static/main.js`; `node --test tests/js/scoring_ui.test.mjs`. Outcome: added deterministic scoring-result summary helpers on top of existing run metadata, surfaced compact loaded-run scoring totals in the scoring panel, automatically compared the current loaded run against the previous loaded scoring run using manifest signatures plus per-quantity deltas, and refreshed the panel both when historical runs are opened and when a new simulation completes. Next: ASRC-007. |
| 2026-04-11 | ASRC-007 AI scoring inspection and result-summary tools | DONE | Files: [`/Volumes/nvme/projects/airpet/src/scoring_artifacts.py`](/Volumes/nvme/projects/airpet/src/scoring_artifacts.py), [`/Volumes/nvme/projects/airpet/src/project_manager.py`](/Volumes/nvme/projects/airpet/src/project_manager.py), [`/Volumes/nvme/projects/airpet/src/ai_tools.py`](/Volumes/nvme/projects/airpet/src/ai_tools.py), [`/Volumes/nvme/projects/airpet/app.py`](/Volumes/nvme/projects/airpet/app.py), [`/Volumes/nvme/projects/airpet/tests/test_ai_api.py`](/Volumes/nvme/projects/airpet/tests/test_ai_api.py), [`/Volumes/nvme/projects/airpet/tests/test_ai_integration.py`](/Volumes/nvme/projects/airpet/tests/test_ai_integration.py), [`/Volumes/nvme/projects/airpet/docs/ADVANCED_SCORING_AND_RUN_CONTROLS_TRACKER.md`](/Volumes/nvme/projects/airpet/docs/ADVANCED_SCORING_AND_RUN_CONTROLS_TRACKER.md). Tests: `python3 -m py_compile src/scoring_artifacts.py src/project_manager.py src/ai_tools.py app.py tests/test_ai_api.py tests/test_ai_integration.py`; `/Users/marth/miniconda/envs/airpet/bin/python -m pytest tests/test_ai_integration.py -q -k 'environment_ai_schema_exposes_read_and_write_tools'`; `/Users/marth/miniconda/envs/airpet/bin/python -m pytest tests/test_ai_api.py -q -k 'scoring_state or scoring_summary_route_and_ai_wrapper_share_success_payloads'`. Outcome: exposed the saved scoring contract through the AI inspection/update schemas, surfaced scoring mesh and tally labels in the AI project summary, added a compact `/api/simulation/scoring_summary/<version_id>/<job_id>` backend surface plus matching `get_scoring_summary` AI wrapper for per-run scoring explanations, and fixed the synthetic route bridge so route-backed AI scoring lookups reuse the active project manager context. Next: ASRC-008. |
| 2026-04-11 | ASRC-008 saved expert run-control defaults | DONE | Files: [`/Volumes/nvme/projects/airpet/static/scoringUi.js`](/Volumes/nvme/projects/airpet/static/scoringUi.js), [`/Volumes/nvme/projects/airpet/static/uiManager.js`](/Volumes/nvme/projects/airpet/static/uiManager.js), [`/Volumes/nvme/projects/airpet/static/main.js`](/Volumes/nvme/projects/airpet/static/main.js), [`/Volumes/nvme/projects/airpet/tests/js/scoring_ui.test.mjs`](/Volumes/nvme/projects/airpet/tests/js/scoring_ui.test.mjs), [`/Volumes/nvme/projects/airpet/docs/ADVANCED_SCORING_AND_RUN_CONTROLS_TRACKER.md`](/Volumes/nvme/projects/airpet/docs/ADVANCED_SCORING_AND_RUN_CONTROLS_TRACKER.md). Tests: `node --check static/scoringUi.js`; `node --check static/uiManager.js`; `node --check static/main.js`; `node --test tests/js/scoring_ui.test.mjs`. Outcome: added a compact scoring-panel editor for selected saved expert run controls, normalized the frontend scoring run-manifest defaults so numeric and boolean fields stop drifting as strings, and changed simulation-option resolution so saved scoring defaults drive scoring runs by default while the Simulation Options modal still persists only explicit per-run overrides. Next: none. |

## Notes For Future Reordering

- It is fine to pull a runtime slice ahead of UI work if the underlying scoring contract needs proof first.
- Prefer compact scoring workflows that are easy to validate deterministically.
- Keep the first scoring surfaces focused on clear study value, not on exhaustive Geant4 option coverage.
- Multimodal AI geometry intake is intentionally deferred until AIRPET has stronger scoring and result-summary infrastructure to validate what the multimodal path produces.
