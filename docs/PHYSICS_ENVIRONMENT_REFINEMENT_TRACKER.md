# Physics Environment Refinement Tracker

Last updated: 2026-04-07T16:02:36+02:00

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

- Overall phase: roadmap phase R1, complete
- Dependency note: workflow refinement is exhausted; the physics-environment backlog is complete
- Current priority: complete
- Success metric: AIRPET can define, save, inspect, and run a minimal field-aware simulation without hand-editing Geant4 code or macros outside the product workflow

## Current NEXT Task

No remaining physics-environment tasks.

Reason:

- the physics-environment backlog is complete
- no NEXT or PENDING physics-environment items remain

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
| PER-002 | P0 | Runtime | Thread the global uniform magnetic field from saved project state into Geant4 runtime initialization | DONE | The saved global field now reaches Geant4 startup via `/globalField/setValue` and `G4GlobalMagFieldMessenger`; the run metadata also records the resolved environment |
| PER-003 | P0 | Testing | Add a deterministic field-on versus field-off regression or smoke path using a compact charged-particle example | DONE | Added a silicon-target electron smoke that runs `airpet-sim` twice and asserts the magnetic field produces a clear x-deflection delta while the field-off path remains near-straight |
| PER-004 | P1 | UI | Add UI surfaces for creating, editing, and inspecting a global magnetic field | DONE | Added a project-level Environment accordion in the Properties tab with enabled/vector editors and a read-only summary that writes through the shared environment update-property path |
| PER-005 | P1 | AI | Add AI/backend tool surfaces for reading and writing global magnetic-field configuration | DONE | Added environment inspection through `get_component_details` plus a generic `update_property` AI tool that routes through the shared environment property path |
| PER-006 | P1 | Fields | Add local magnetic-field assignment to selected volumes or regions | DONE | Added a local uniform magnetic field contract for selected logical volumes, threaded it through project serialization, macro generation, Geant4 field-manager attachment, and focused UI/AI/backend regressions |
| PER-007 | P1 | Fields | Add electric-field support on the shared environment abstraction | DONE | Added electric fields to saved project state, UI, AI/backend, macro generation, and Geant4 runtime plumbing; the electric smoke now uses the vacuum box so the charged-particle run stays under the deterministic timeout |
| PER-008 | P2 | Examples | Add compact example assets and templates for field-aware simulations | DONE | Added a field-aware silicon starter asset with explicit saved global field state plus a reusable `field_probe_slab` physics template for compact field comparisons |
| PER-009 | P2 | Environment | Add region-specific production cuts and user limits on the same environment layer | DONE | Added a combined region-controls environment object with saved-state validation, update-property/UI/AI plumbing, region macro emission, and Geant4 runtime application for production cuts plus user limits |
| PER-010 | P2 | Analysis | Add field-aware run metadata and analysis summaries so environment variants are visible in outputs | DONE | Added a deterministic environment summary to run metadata plus simulation metadata/analysis and AI analysis outputs so active field and region variants are visible after the run |

## Cycle Log

| Date | Task | Outcome | Notes |
| --- | --- | --- | --- |
| 2026-04-06 | Backlog setup | DONE | Created the physics-environment refinement context and seeded the first roadmap phase, starting with global uniform magnetic-field support |
| 2026-04-06 | Tracker refinement | DONE | Split the first-phase backlog into smaller automation-friendly slices and linked it to the broader post-workflow roadmap |
| 2026-04-06T13:21:08+02:00 | PER-001 global uniform magnetic field schema | DONE | Files: `src/geometry_types.py`, `tests/test_environment_state.py`, `docs/PHYSICS_ENVIRONMENT_REFINEMENT_TRACKER.md`. Tests: `/Users/marth/miniconda/envs/airpet/bin/pytest tests/test_environment_state.py -q`. Outcome: added an explicit environment object with default zero-field state, strict validation for the canonical magnetic-field vector, legacy top-level migration, and save/load roundtrip coverage. Next: PER-002 |
| 2026-04-06T15:06:21+02:00 | PER-002 global field runtime initialization | DONE | Files: `src/project_manager.py`, `geant4/include/DetectorConstruction.hh`, `geant4/src/DetectorConstruction.cc`, `tests/test_geant4_field_macro.py`, `docs/PHYSICS_ENVIRONMENT_REFINEMENT_TRACKER.md`. Tests: `python3 -m py_compile src/project_manager.py tests/test_geant4_field_macro.py`; `/Users/marth/miniconda/envs/airpet/bin/pytest tests/test_geant4_field_macro.py tests/test_ai_api.py -k 'directed_source_zero_vector_falls_back_to_positive_z_in_macro or generate_macro_uses_low_default_hit_energy_threshold or generate_macro_respects_explicit_hit_energy_threshold or generate_macro_respects_explicit_production_cut or generate_macro_allows_disabling_hit_metadata or generate_macro_places_sensitive_detector_commands_after_geometry_load' -q`; `cmake --build geant4/build --target airpet-sim -j2`. Outcome: threaded the saved global uniform magnetic field into Geant4 startup via `/globalField/setValue`, `G4GlobalMagFieldMessenger`, and run metadata, with a regression covering the generated macro and metadata. Next: PER-003 |
| 2026-04-06T17:10:51+02:00 | PER-003 field-on vs field-off charged-particle smoke | DONE | Files: `tests/test_geant4_field_smoke.py`, `docs/PHYSICS_ENVIRONMENT_REFINEMENT_TRACKER.md`. Tests: `/Users/marth/miniconda/envs/airpet/bin/pytest tests/test_geant4_field_smoke.py -q`. Outcome: added a deterministic silicon-target electron smoke that runs `airpet-sim` twice and asserts the magnetic field shifts the trajectory in x while the field-off path remains near-straight. Next: PER-004 |
| 2026-04-06T19:09:53+02:00 | PER-004 global magnetic field UI surfaces | DONE | Files: `app.py`, `src/project_manager.py`, `static/environmentFieldUi.js`, `static/uiManager.js`, `templates/index.html`, `tests/js/environment_field_ui.test.mjs`, `tests/test_project_manager_update_property.py`, `tests/test_update_property_api.py`, `docs/PHYSICS_ENVIRONMENT_REFINEMENT_TRACKER.md`. Tests: `node --check static/uiManager.js`; `node --check static/environmentFieldUi.js`; `python3 -m py_compile app.py src/project_manager.py tests/test_update_property_api.py tests/test_project_manager_update_property.py`; `/Users/marth/miniconda/envs/airpet/bin/pytest tests/test_project_manager_update_property.py tests/test_update_property_api.py -q`; `node --test tests/js/environment_field_ui.test.mjs`. Outcome: added a project-level Environment accordion in the Properties tab with enabled/vector editors and a read-only summary, routed updates through the shared environment property path, and locked in the behavior with focused Python and JS regressions. Next: PER-005 |
| 2026-04-06T21:07:52+02:00 | PER-005 AI/backend global magnetic-field tool surfaces | DONE | Files: `app.py`, `src/ai_tools.py`, `src/project_manager.py`, `tests/test_ai_api.py`, `tests/test_ai_integration.py`, `docs/PHYSICS_ENVIRONMENT_REFINEMENT_TRACKER.md`. Tests: `python3 -m py_compile app.py src/ai_tools.py src/project_manager.py tests/test_ai_api.py tests/test_ai_integration.py`; `/Users/marth/miniconda/envs/airpet/bin/pytest tests/test_ai_api.py -k 'environment_field' -q`; `/Users/marth/miniconda/envs/airpet/bin/pytest tests/test_ai_integration.py -k 'environment_ai_schema_exposes_read_and_write_tools' -q`; `/Users/marth/miniconda/envs/airpet/bin/pytest tests/test_update_property_api.py -q`. Outcome: exposed the global field through `get_component_details`, added a generic `update_property` AI tool that drives the shared environment update path, and confirmed the existing update-property route still accepts environment updates. Next: PER-006 |
| 2026-04-06T23:09:43+02:00 | PER-006 local magnetic field assignment | DONE | Files: `src/geometry_types.py`, `src/project_manager.py`, `src/ai_tools.py`, `geant4/include/DetectorConstruction.hh`, `geant4/src/DetectorConstruction.cc`, `static/environmentFieldUi.js`, `static/uiManager.js`, `templates/index.html`, `tests/test_environment_state.py`, `tests/test_project_manager_update_property.py`, `tests/test_update_property_api.py`, `tests/test_ai_api.py`, `tests/test_ai_integration.py`, `tests/test_geant4_field_macro.py`, `tests/test_geant4_field_smoke.py`, `tests/js/environment_field_ui.test.mjs`, `docs/PHYSICS_ENVIRONMENT_REFINEMENT_TRACKER.md`. Tests: `node --check static/environmentFieldUi.js`; `node --check static/uiManager.js`; `node --test tests/js/environment_field_ui.test.mjs`; `python3 -m py_compile src/geometry_types.py src/project_manager.py src/ai_tools.py app.py tests/test_environment_state.py tests/test_project_manager_update_property.py tests/test_update_property_api.py tests/test_ai_api.py tests/test_ai_integration.py`; `cmake --build geant4/build --target airpet-sim -j2`; `/Users/marth/miniconda/envs/airpet/bin/pytest tests/test_environment_state.py::test_environment_state_defaults_and_roundtrip tests/test_environment_state.py::test_environment_state_validation_and_project_roundtrip tests/test_project_manager_update_property.py::test_update_object_property_supports_global_uniform_magnetic_field_updates tests/test_project_manager_update_property.py::test_update_object_property_supports_local_uniform_magnetic_field_updates tests/test_update_property_api.py::test_update_property_route_accepts_environment_object_type tests/test_update_property_api.py::test_update_property_route_accepts_local_environment_object_type tests/test_ai_api.py::test_ai_tool_update_property_and_get_component_details_cover_environment_field tests/test_ai_integration.py::test_environment_ai_schema_exposes_read_and_write_tools tests/test_geant4_field_macro.py::test_generate_macro_threads_saved_global_field_into_runtime_initialization tests/test_geant4_field_smoke.py::test_field_on_vs_field_off_changes_charged_particle_track tests/test_geant4_field_smoke.py::test_local_field_assignment_changes_track_inside_target_volume -q`. Outcome: added a local uniform magnetic-field contract for selected logical volumes, threaded it through saved project state, AI/backend/UI surfaces, Geant4 macro generation, and runtime field-manager attachment, with deterministic coverage for saved-state, update-property, macro emission, and both global/local field smokes. Next: PER-007 |
| 2026-04-07T01:33:48+02:00 | PER-007 electric-field support on the shared environment abstraction | DONE | Files: `src/geometry_types.py`, `src/project_manager.py`, `src/ai_tools.py`, `geant4/include/DetectorConstruction.hh`, `geant4/src/DetectorConstruction.cc`, `static/environmentFieldUi.js`, `static/uiManager.js`, `tests/js/environment_field_ui.test.mjs`, `tests/test_ai_api.py`, `tests/test_ai_integration.py`, `tests/test_environment_state.py`, `tests/test_geant4_field_macro.py`, `tests/test_geant4_field_smoke.py`, `tests/test_project_manager_update_property.py`, `tests/test_update_property_api.py`, `docs/PHYSICS_ENVIRONMENT_REFINEMENT_TRACKER.md`. Tests: `cmake --build geant4/build --target airpet-sim -j2`; `/Users/marth/miniconda/envs/airpet/bin/pytest tests/test_geant4_field_macro.py::test_generate_macro_threads_saved_global_field_into_runtime_initialization tests/test_geant4_field_smoke.py -q`. Outcome: added electric fields to the shared environment model, runtime macro generation, UI, and AI/backend surfaces; fixed the Geant4 messenger/field-builder wiring so the combined field path is valid; and kept the electric charged-particle smoke deterministic by running it in the default vacuum box instead of the silicon stopper. Next: PER-008 |
| 2026-04-07T10:59:19+02:00 | PER-008 field-aware examples and templates | DONE | Files: `examples/field_aware/README.md`, `examples/field_aware/field_aware_silicon_starter.project.json`, `src/ai_tools.py`, `src/templates.py`, `tests/test_ai_api.py`, `tests/test_ai_integration.py`, `tests/test_field_aware_examples.py`, `docs/PHYSICS_ENVIRONMENT_REFINEMENT_TRACKER.md`. Tests: `python3 -m json.tool examples/field_aware/field_aware_silicon_starter.project.json`; `python3 -m py_compile src/templates.py src/ai_tools.py tests/test_ai_api.py tests/test_ai_integration.py tests/test_field_aware_examples.py`; `/Users/marth/miniconda/envs/airpet/bin/pytest tests/test_field_aware_examples.py -q`; `/Users/marth/miniconda/envs/airpet/bin/pytest tests/test_ai_api.py -k 'physics_template or field_probe_slab' -q`; `/Users/marth/miniconda/envs/airpet/bin/pytest tests/test_ai_integration.py -k 'field_probe_slab' -q`. Outcome: added a compact field-aware silicon starter asset with explicit saved global field state plus a reusable sensitive `field_probe_slab` physics template so field-focused projects stay easy to discover and extend. Next: PER-009 |
| 2026-04-07T12:15:45+02:00 | PER-009 region-specific production cuts and user limits | DONE | Files: `src/geometry_types.py`, `src/project_manager.py`, `src/ai_tools.py`, `geant4/include/DetectorConstruction.hh`, `geant4/src/DetectorConstruction.cc`, `static/environmentFieldUi.js`, `static/uiManager.js`, `tests/js/environment_field_ui.test.mjs`, `tests/test_ai_api.py`, `tests/test_ai_integration.py`, `tests/test_environment_state.py`, `tests/test_field_aware_examples.py`, `tests/test_geant4_field_macro.py`, `tests/test_project_manager_update_property.py`, `docs/PHYSICS_ENVIRONMENT_REFINEMENT_CONTEXT.md`, `docs/PHYSICS_ENVIRONMENT_REFINEMENT_ROADMAP.md`, `docs/PHYSICS_ENVIRONMENT_REFINEMENT_TRACKER.md`. Tests: `node --check static/environmentFieldUi.js`; `node --check static/uiManager.js`; `node --test tests/js/environment_field_ui.test.mjs`; `python3 -m py_compile src/geometry_types.py src/project_manager.py src/ai_tools.py tests/test_environment_state.py tests/test_project_manager_update_property.py tests/test_ai_api.py tests/test_ai_integration.py tests/test_geant4_field_macro.py tests/test_field_aware_examples.py`; `PYTHONPATH=/tmp/occ_stub:$PYTHONPATH /Users/marth/miniconda/envs/airpet/bin/pytest tests/test_environment_state.py tests/test_project_manager_update_property.py tests/test_field_aware_examples.py tests/test_geant4_field_macro.py tests/test_ai_api.py tests/test_ai_integration.py -k 'test_environment_state_defaults_and_roundtrip or test_environment_state_validation_and_project_roundtrip or test_update_object_property_supports_region_cuts_and_limits_updates or test_field_aware_silicon_starter_saves_explicit_fields or test_generate_macro_threads_saved_global_field_into_runtime_initialization or test_ai_tool_update_property_and_get_component_details_cover_environment_field or test_environment_ai_schema_exposes_read_and_write_tools' -q`; `cmake --build geant4/build --target airpet-sim -j2`. Outcome: added a combined region-controls environment object with saved-state validation, update-property/UI/AI plumbing, macro emission, and Geant4 runtime application for production cuts plus user limits. Next: PER-010 |
| 2026-04-07T14:07:44+02:00 | PER-010 field-aware run metadata and analysis summaries | DONE | Files: `app.py`, `src/geometry_types.py`, `src/project_manager.py`, `tests/test_ai_api.py`, `tests/test_environment_state.py`, `tests/test_geant4_field_macro.py`. Tests: `python3 -m py_compile app.py tests/test_ai_api.py`; `PYTHONPATH=/tmp/occ_stub:$PYTHONPATH /Users/marth/miniconda/envs/airpet/bin/pytest tests/test_environment_state.py -q`; `PYTHONPATH=/tmp/occ_stub:$PYTHONPATH /Users/marth/miniconda/envs/airpet/bin/pytest tests/test_geant4_field_macro.py -q`; `PYTHONPATH=/tmp/occ_stub:$PYTHONPATH /Users/marth/miniconda/envs/airpet/bin/pytest tests/test_ai_api.py -q -k 'ai_analysis_summary or simulation_metadata_and_analysis_routes_include_environment_summary or ai_tool_route_bridge_get_metadata_and_analysis'`. Outcome: added a deterministic environment summary helper, wrote it into run metadata, surfaced it through simulation metadata/analysis responses and the AI analysis summary tool, and locked the behavior with metadata, route, and AI regression coverage. Next: none.
| 2026-04-07T16:02:36+02:00 | No remaining physics-environment tasks | BLOCKED | Files: none. Tests: none. Outcome: workflow refinement is exhausted, the physics-environment tracker is already complete, and the worktree already has tracked edits in `static/environmentFieldUi.js`, `static/logicalVolumeEditor.js`, `static/main.js`, `templates/index.html`, and `tests/js/environment_field_ui.test.mjs`, so I did not start a new physics-environment slice. Next: none.

## Notes For Future Reordering

- It is fine to reorder tasks if a lower-level abstraction change is discovered first.
- Prefer capabilities that unlock new simulation classes over polish on already-supported flows.
- Keep the environment model unified so fields, cuts, and limits do not become disconnected subsystems.
- Keep task size small enough that one automation cycle can plausibly finish one backlog item end to end.
