# CAD Interoperability Refinement Tracker

Last updated: 2026-04-07

## Mission

Incrementally make imported CAD geometry easier to bring into AIRPET, understand, revise, and simulate, with the highest priority on safe STEP reimport and preserved simulation-oriented annotations.

## Scope

In scope:

- STEP import provenance and identity
- STEP reimport/update workflows
- preserved AIRPET-side annotations for supported reimport paths
- import/reimport summaries and reporting
- grouping, naming, and post-import editing improvements for imported CAD

Out of scope for a single cycle:

- full CAD authoring
- broad geometry tooling unrelated to imported CAD workflows
- multiple import/refactor themes in one run

## Operating Loop

Each refinement cycle should do exactly one backlog item:

1. Read this tracker and `docs/CAD_INTEROPERABILITY_REFINEMENT_CONTEXT.md`.
2. Pick the task marked `NEXT`.
3. If nothing is marked `NEXT`, pick the highest-priority `PENDING` task and mark it `NEXT`.
4. Implement that task end to end.
5. Add or update focused regression tests, replay coverage, fixture assets, or deterministic smoke checks.
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

- the CAD import/reimport behavior exists in product code or saved-state contract as required
- focused regression, replay, or fixture coverage passes locally
- any required UI or report surfaces stay aligned with the backend behavior
- this tracker records the outcome and next task

## Current Status

- Overall phase: roadmap phase R2, ready to activate after physics-environment completion
- Current priority: CIR-007
- Success metric: a user can revise an imported STEP-driven subsystem in CAD and update the AIRPET project without duplicating geometry or redoing key simulation annotations by hand

## Current NEXT Task

CIR-007: Add deterministic reimport diff summaries for added, removed, renamed, or changed imported parts.

Reason:

- CIR-006 is done, so the next smallest slice is reimport reporting
- this keeps the CAD-interoperability phase moving toward the safe-update workflow without widening into cleanup yet
- it stays within the same imported-CAD workflow surface and avoids mixing unrelated refactors

## Backlog

Statuses:

- `NEXT`
- `PENDING`
- `IN_PROGRESS`
- `BLOCKED`
- `DONE`

| ID | Priority | Area | Feature | Status | Notes |
| --- | --- | --- | --- | --- | --- |
| CIR-001 | P0 | Provenance | Add saved-project CAD import provenance metadata and stable import identity for STEP imports | DONE | Saved-project `cad_imports` records now persist STEP source digest, stable `import_id`, import options, and created object ids |
| CIR-002 | P0 | Reimport | Add a supported STEP reimport path that targets an existing imported CAD subsystem instead of always merging new names | DONE | Reimport can now target an existing `import_id`, remove the old imported subsystem, and replace it in place without suffixing names |
| CIR-003 | P0 | Reimport | Preserve key AIRPET-side annotations across supported STEP reimports | DONE | Reimport now restores imported LV material, sensitivity, and visual attributes, preserves matching UI group membership, and relinks source bindings onto replacement PVs |
| CIR-004 | P1 | UI | Add UI surfaces to inspect CAD import provenance and launch a supported reimport flow | DONE | Added a CAD Imports accordion, provenance summary cards, and a reimport-seeded STEP modal flow |
| CIR-005 | P1 | Grouping | Improve imported assembly naming, grouping, and top-level selection ergonomics | DONE | Removed the extra placeholder assembly created during STEP parsing, recorded top-level placement ids in provenance, and added a CAD import panel shortcut to select top-level imported placements in the hierarchy |
| CIR-006 | P1 | Editing | Add post-import batch helpers for material and sensitive-volume assignment on imported CAD geometry | DONE | Imported STEP cards now expose batch material and sensitivity helpers backed by an atomic logical-volume batch update path |
| CIR-007 | P1 | Reporting | Add deterministic reimport diff summaries for added, removed, renamed, or changed imported parts | NEXT | Users should be able to see what changed before trusting the update |
| CIR-008 | P2 | Smart Import | Surface primitive-recognition and tessellated-fallback outcomes in saved metadata and user-visible summaries | PENDING | Reuse the existing smart-import classifier and fallback policy instead of creating a separate reporting path |
| CIR-009 | P2 | Testing | Add a compact STEP import/reimport fixture corpus with focused regression coverage | PENDING | Keep fixtures small enough for fast import and reimport verification |
| CIR-010 | P2 | Cleanup | Add explicit replace/remove policy for obsolete imported parts in supported reimport flows | PENDING | Make deletion behavior explicit rather than implicit when CAD revisions remove parts |

## Cycle Log

| Date | Task | Outcome | Notes |
| --- | --- | --- | --- |
| 2026-04-07 | Backlog setup | DONE | Created the CAD-interoperability refinement context and seeded the first concrete backlog, starting with saved-project CAD provenance and stable import identity for STEP imports |
| 2026-04-07 | CIR-001 provenance metadata | DONE | Added persisted `cad_imports` state and STEP import identity bookkeeping in [`/Volumes/nvme/projects/airpet/src/geometry_types.py`](/Volumes/nvme/projects/airpet/src/geometry_types.py) and [`/Volumes/nvme/projects/airpet/src/project_manager.py`](/Volumes/nvme/projects/airpet/src/project_manager.py); added regression coverage in [`/Volumes/nvme/projects/airpet/tests/test_cad_import_provenance.py`](/Volumes/nvme/projects/airpet/tests/test_cad_import_provenance.py); verified with `pytest tests/test_cad_import_provenance.py -q` |
| 2026-04-07 | CIR-002 reimport replacement | DONE | Added a targeted STEP reimport path in [`/Volumes/nvme/projects/airpet/src/project_manager.py`](/Volumes/nvme/projects/airpet/src/project_manager.py) that resolves an existing `import_id`, removes the old imported subsystem, and reuses the stable provenance record identity; added regression coverage in [`/Volumes/nvme/projects/airpet/tests/test_cad_import_provenance.py`](/Volumes/nvme/projects/airpet/tests/test_cad_import_provenance.py); verified with `python3 -m pytest tests/test_cad_import_provenance.py -q`; next task is CIR-003 |
| 2026-04-07 | CIR-003 annotation preservation | DONE | Added STEP reimport annotation snapshot/restore logic in [`/Volumes/nvme/projects/airpet/src/project_manager.py`](/Volumes/nvme/projects/airpet/src/project_manager.py) to carry imported LV material/sensitivity/visual state, matching UI group membership, and linked source bindings across supported reimports; added regression coverage in [`/Volumes/nvme/projects/airpet/tests/test_cad_import_provenance.py`](/Volumes/nvme/projects/airpet/tests/test_cad_import_provenance.py); verified with `python3 -m pytest tests/test_cad_import_provenance.py -q`; next task is CIR-004 |
| 2026-04-07 | CIR-004 provenance and reimport UI | DONE | Added provenance helpers in [`/Volumes/nvme/projects/airpet/static/cadImportUi.js`](/Volumes/nvme/projects/airpet/static/cadImportUi.js), a CAD Imports accordion in [`/Volumes/nvme/projects/airpet/templates/index.html`](/Volumes/nvme/projects/airpet/templates/index.html), controller wiring in [`/Volumes/nvme/projects/airpet/static/main.js`](/Volumes/nvme/projects/airpet/static/main.js), [`/Volumes/nvme/projects/airpet/static/uiManager.js`](/Volumes/nvme/projects/airpet/static/uiManager.js), and [`/Volumes/nvme/projects/airpet/static/stepImportEditor.js`](/Volumes/nvme/projects/airpet/static/stepImportEditor.js), plus regression coverage in [`/Volumes/nvme/projects/airpet/tests/js/cad_import_ui.test.mjs`](/Volumes/nvme/projects/airpet/tests/js/cad_import_ui.test.mjs); verified with `node --test tests/js/cad_import_ui.test.mjs`, `node --check static/cadImportUi.js`, `node --check static/stepImportEditor.js`, `node --check static/main.js`, `node --check static/uiManager.js`, and `python3 -m pytest tests/test_cad_import_provenance.py -q`; next task is CIR-005 |
| 2026-04-07 | CIR-005 imported assembly ergonomics | DONE | Removed the extra placeholder assembly from STEP parsing in [`/Volumes/nvme/projects/airpet/src/step_parser.py`](/Volumes/nvme/projects/airpet/src/step_parser.py), recorded `top_level_placement_ids` in provenance via [`/Volumes/nvme/projects/airpet/src/project_manager.py`](/Volumes/nvme/projects/airpet/src/project_manager.py), and added a CAD import panel shortcut plus selection helpers in [`/Volumes/nvme/projects/airpet/static/cadImportUi.js`](/Volumes/nvme/projects/airpet/static/cadImportUi.js), [`/Volumes/nvme/projects/airpet/static/uiManager.js`](/Volumes/nvme/projects/airpet/static/uiManager.js), and [`/Volumes/nvme/projects/airpet/static/main.js`](/Volumes/nvme/projects/airpet/static/main.js); added regression coverage in [`/Volumes/nvme/projects/airpet/tests/test_cad_import_provenance.py`](/Volumes/nvme/projects/airpet/tests/test_cad_import_provenance.py) and [`/Volumes/nvme/projects/airpet/tests/js/cad_import_ui.test.mjs`](/Volumes/nvme/projects/airpet/tests/js/cad_import_ui.test.mjs); verified with `python3 -m pytest tests/test_cad_import_provenance.py -q`, `node --test tests/js/cad_import_ui.test.mjs`, `node --check static/cadImportUi.js`, and `node --check static/uiManager.js && node --check static/main.js`; next task is CIR-006 |
| 2026-04-07 | CIR-006 post-import CAD batch helpers | DONE | Added an atomic logical-volume batch update path in [`/Volumes/nvme/projects/airpet/src/project_manager.py`](/Volumes/nvme/projects/airpet/src/project_manager.py) with a matching route in [`/Volumes/nvme/projects/airpet/app.py`](/Volumes/nvme/projects/airpet/app.py), wired CAD-import panel material/sensitivity actions through [`/Volumes/nvme/projects/airpet/static/main.js`](/Volumes/nvme/projects/airpet/static/main.js), [`/Volumes/nvme/projects/airpet/static/uiManager.js`](/Volumes/nvme/projects/airpet/static/uiManager.js), [`/Volumes/nvme/projects/airpet/static/cadImportUi.js`](/Volumes/nvme/projects/airpet/static/cadImportUi.js), and [`/Volumes/nvme/projects/airpet/static/apiService.js`](/Volumes/nvme/projects/airpet/static/apiService.js), and added focused regression coverage in [`/Volumes/nvme/projects/airpet/tests/test_cad_import_provenance.py`](/Volumes/nvme/projects/airpet/tests/test_cad_import_provenance.py) and [`/Volumes/nvme/projects/airpet/tests/js/cad_import_ui.test.mjs`](/Volumes/nvme/projects/airpet/tests/js/cad_import_ui.test.mjs); verified with `python3 -m pytest tests/test_cad_import_provenance.py -q`, `node --test tests/js/cad_import_ui.test.mjs`, `python3 -m py_compile app.py src/project_manager.py`, and `node --check static/main.js && node --check static/uiManager.js && node --check static/cadImportUi.js && node --check static/apiService.js`; next task is CIR-007 |

## Notes For Future Reordering

- It is fine to reorder tasks if a lower-level import-identity prerequisite is discovered first.
- Prefer preserving user work across CAD revisions over adding new import knobs.
- Keep the first supported reimport flow narrow and deterministic before broadening scope.
- Keep task size small enough that one automation cycle can plausibly finish one backlog item end to end.
