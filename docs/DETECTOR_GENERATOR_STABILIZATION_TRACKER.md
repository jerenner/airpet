# Detector Generator Stabilization Tracker

Last updated: 2026-04-10

## Mission

Incrementally harden the existing detector generator workflows so they are easier to discover, safer to use, and more trustworthy in end-to-end AIRPET usage.

## Scope

In scope:

- generator launch/discoverability fixes
- generator-specific default and realization bug fixes
- route/scene/hierarchy regressions for generated geometry visibility
- focused UX cleanup for existing generator inspection/regeneration surfaces

Out of scope for a single cycle:

- new generator families
- broad unrelated UI redesign
- large refactors across multiple generator families at once

## Operating Loop

Each stabilization cycle should do exactly one backlog item:

1. Read this tracker and `docs/DETECTOR_GENERATOR_STABILIZATION_CONTEXT.md`.
2. Pick the task marked `NEXT`.
3. If nothing is marked `NEXT`, pick the highest-priority `PENDING` task and mark it `NEXT`.
4. Reproduce the issue or validate the current UX gap.
5. Implement the smallest coherent fix.
6. Add or update the smallest sufficient regression, smoke check, or deterministic manual-replay helper.
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

- the specific stability or UX issue is fixed in product code
- focused regression, replay, or smoke coverage passes locally
- any required UI/backend alignment stays coherent
- this tracker records the outcome and next task

## Current Status

- Overall phase: post-R3 stabilization loop, active
- Current priority: audit annular shield sleeve realization, placement visibility, and saved-generator revision behavior end to end
- Success metric: existing detector generators feel dependable in real use, with sane defaults, clear launch points, and generated geometry that is visible and inspectable after creation/regeneration

## Current NEXT Task

DGS-007: audit annular shield sleeve realization, placement visibility, and revision behavior end to end.

Focus for this task:

- confirm generated shield logical volumes and placements stay visible after create and regenerate
- verify saved shield edits reuse the generated object cleanly when dimensions or offsets change
- keep the audit narrow to shield sleeves rather than broad cross-generator cleanup
- add only the smallest sufficient regression or deterministic replay for any concrete realization or discoverability gap found

## Backlog

Statuses:

- `NEXT`
- `PENDING`
- `IN_PROGRESS`
- `BLOCKED`
- `DONE`

| ID | Priority | Area | Feature | Status | Notes |
| --- | --- | --- | --- | --- | --- |
| DGS-001 | P0 | Tiled Sensor Array | Fix default pitch values and ensure generated placements are visible after create/regenerate | DONE | Default tiled-array pitch now matches the default sensor size, detached parent LVs are rejected/hidden, and scene-level coverage confirms generated PVs appear in the live scene path |
| DGS-002 | P0 | Entry Points | Move detector-generator creation into Hierarchy `Tools` and include Ring Array in the same tool surface | DONE | Hierarchy `+ Tools` now launches both detector generators and Ring Array, while Properties focuses on saved-generator inspection and regeneration |
| DGS-003 | P1 | Properties UX | Reduce Properties-panel generator bulk while keeping saved-generator inspection and regeneration accessible | DONE | Properties cards now stay collapsed when there are multiple saved generators, keep edit/regenerate actions in the card header, and drop redundant per-card copy |
| DGS-004 | P1 | Layered Stack | Audit layered detector stack create/regenerate visibility and revision behavior end to end | DONE | Layered stacks now reject detached parent LVs, and scene-level coverage confirms module placements stay visible after create and regenerate |
| DGS-005 | P1 | Support Ribs | Audit support-rib array create/regenerate visibility and revision behavior end to end | DONE | Support-rib arrays now reject detached parent LVs, scene-level coverage confirms generated rib PVs appear after create/regenerate, and saved-generator inspector rows still expose generated LV/PV names |
| DGS-006 | P1 | Channel Cuts | Audit channel-cut array realization, target updates, and saved-generator revision behavior end to end | DONE | Channel cuts now reject detached target LVs and have focused create/regenerate coverage for targeted-LV revisions |
| DGS-007 | P1 | Shield Sleeve | Audit annular shield sleeve realization, placement visibility, and revision behavior end to end | NEXT | Confirm generated LV/PV visibility and regeneration are clear in the app |
| DGS-008 | P2 | Shared UX | Add shared generated-object selection or reveal affordances when they materially improve generator discoverability | PENDING | Only if still needed after the earlier fixes |

## Cycle Log

| Date | Task | Outcome | Notes |
| --- | --- | --- | --- |
| 2026-04-09 | Backlog setup | DONE | Created a detector-generator stabilization loop seeded from real post-generator usage feedback, starting with tiled sensor array defaults and generated-placement visibility |
| 2026-04-10 | DGS-001 tiled-array defaults and visible parents | DONE | Files: [`/Volumes/nvme/projects/airpet/static/detectorFeatureGeneratorsUi.js`](/Volumes/nvme/projects/airpet/static/detectorFeatureGeneratorsUi.js), [`/Volumes/nvme/projects/airpet/static/detectorFeatureGeneratorEditor.js`](/Volumes/nvme/projects/airpet/static/detectorFeatureGeneratorEditor.js), [`/Volumes/nvme/projects/airpet/src/project_manager.py`](/Volumes/nvme/projects/airpet/src/project_manager.py), [`/Volumes/nvme/projects/airpet/tests/js/detector_feature_generators_ui.test.mjs`](/Volumes/nvme/projects/airpet/tests/js/detector_feature_generators_ui.test.mjs), [`/Volumes/nvme/projects/airpet/tests/test_detector_feature_generators_state.py`](/Volumes/nvme/projects/airpet/tests/test_detector_feature_generators_state.py), [`/Volumes/nvme/projects/airpet/docs/DETECTOR_GENERATOR_STABILIZATION_TRACKER.md`](/Volumes/nvme/projects/airpet/docs/DETECTOR_GENERATOR_STABILIZATION_TRACKER.md). Tests: `node --check static/detectorFeatureGeneratorsUi.js`; `node --check static/detectorFeatureGeneratorEditor.js`; `python3 -m py_compile src/project_manager.py tests/test_detector_feature_generators_state.py`; `node --test tests/js/detector_feature_generators_ui.test.mjs`; `python3 -m pytest tests/test_detector_feature_generators_state.py -q -k 'tiled_sensor_array'`. Outcome: fixed the tiled-array editor defaults so untouched pitch matches the default sensor size, reproduced the invisible-placement gap as detached parent-LV targeting, limited the parent picker to live scene LVs while preserving existing targets for edits, rejected detached tiled-array parents in backend realization, and added scene-level regression coverage that confirms generated sensor PVs appear in the Three.js scene description. Next: DGS-002 |
| 2026-04-10 | DGS-002 hierarchy tools detector-generator entry point | DONE | Files: [`/Volumes/nvme/projects/airpet/static/detectorFeatureGeneratorsUi.js`](/Volumes/nvme/projects/airpet/static/detectorFeatureGeneratorsUi.js), [`/Volumes/nvme/projects/airpet/static/uiManager.js`](/Volumes/nvme/projects/airpet/static/uiManager.js), [`/Volumes/nvme/projects/airpet/static/main.js`](/Volumes/nvme/projects/airpet/static/main.js), [`/Volumes/nvme/projects/airpet/templates/index.html`](/Volumes/nvme/projects/airpet/templates/index.html), [`/Volumes/nvme/projects/airpet/tests/js/detector_feature_generators_ui.test.mjs`](/Volumes/nvme/projects/airpet/tests/js/detector_feature_generators_ui.test.mjs), [`/Volumes/nvme/projects/airpet/docs/DETECTOR_GENERATOR_STABILIZATION_TRACKER.md`](/Volumes/nvme/projects/airpet/docs/DETECTOR_GENERATOR_STABILIZATION_TRACKER.md). Tests: `node --check static/detectorFeatureGeneratorsUi.js`; `node --check static/uiManager.js`; `node --check static/main.js`; `node --test tests/js/detector_feature_generators_ui.test.mjs`. Outcome: validated the split launch-path gap in the current UI wiring, added detector-generator launch beside Ring Array under Hierarchy `+ Tools`, closed that dropdown when either tool launches, shifted the Properties detector-generator panel to inspector/regenerate guidance instead of a primary create action, and added focused smoke coverage for the shared tools surface plus deterministic launch-state messaging. Next: DGS-003 |
| 2026-04-10 | DGS-003 Properties panel cleanup | DONE | Files: [`/Volumes/nvme/projects/airpet/static/detectorFeatureGeneratorsUi.js`](/Volumes/nvme/projects/airpet/static/detectorFeatureGeneratorsUi.js), [`/Volumes/nvme/projects/airpet/static/uiManager.js`](/Volumes/nvme/projects/airpet/static/uiManager.js), [`/Volumes/nvme/projects/airpet/templates/index.html`](/Volumes/nvme/projects/airpet/templates/index.html), [`/Volumes/nvme/projects/airpet/tests/js/detector_feature_generators_ui.test.mjs`](/Volumes/nvme/projects/airpet/tests/js/detector_feature_generators_ui.test.mjs), [`/Volumes/nvme/projects/airpet/docs/DETECTOR_GENERATOR_STABILIZATION_TRACKER.md`](/Volumes/nvme/projects/airpet/docs/DETECTOR_GENERATOR_STABILIZATION_TRACKER.md). Tests: `node --check static/detectorFeatureGeneratorsUi.js`; `node --check static/uiManager.js`; `node --test tests/js/detector_feature_generators_ui.test.mjs`. Outcome: validated that the post-DGS-002 Properties panel still rendered redundant launch copy, auto-opened the newest saved generator card, and appended verbose per-generator notes; trimmed that chrome by collapsing multi-generator cards by default, moving edit/regenerate actions into the card header, and suppressing the extra launch hint once saved generators exist, with focused UI-state coverage for the leaner panel behavior. Next: DGS-004 |
| 2026-04-10 | DGS-004 layered-stack visibility audit | DONE | Files: [`/Volumes/nvme/projects/airpet/src/project_manager.py`](/Volumes/nvme/projects/airpet/src/project_manager.py), [`/Volumes/nvme/projects/airpet/tests/test_detector_feature_generators_state.py`](/Volumes/nvme/projects/airpet/tests/test_detector_feature_generators_state.py), [`/Volumes/nvme/projects/airpet/docs/DETECTOR_GENERATOR_STABILIZATION_TRACKER.md`](/Volumes/nvme/projects/airpet/docs/DETECTOR_GENERATOR_STABILIZATION_TRACKER.md). Tests: `python3 -m py_compile src/project_manager.py tests/test_detector_feature_generators_state.py`; `python3 -m pytest tests/test_detector_feature_generators_state.py -q -k 'layered_detector_stack'`. Outcome: reproduced a detached-parent visibility gap where layered stacks reported success but produced no live-scene module instances, kept the UI audit narrow by confirming saved layered-stack cards still list generated logical volumes and placements clearly enough for inspection, rejected detached parent LVs in backend realization, and added scene-level create/regenerate coverage plus a detached-parent regression so visible module placements stay trustworthy. Next: DGS-005 |
| 2026-04-10 | DGS-005 support-rib visibility audit | DONE | Files: [`/Volumes/nvme/projects/airpet/src/project_manager.py`](/Volumes/nvme/projects/airpet/src/project_manager.py), [`/Volumes/nvme/projects/airpet/tests/test_detector_feature_generators_state.py`](/Volumes/nvme/projects/airpet/tests/test_detector_feature_generators_state.py), [`/Volumes/nvme/projects/airpet/tests/js/detector_feature_generators_ui.test.mjs`](/Volumes/nvme/projects/airpet/tests/js/detector_feature_generators_ui.test.mjs), [`/Volumes/nvme/projects/airpet/docs/DETECTOR_GENERATOR_STABILIZATION_TRACKER.md`](/Volumes/nvme/projects/airpet/docs/DETECTOR_GENERATOR_STABILIZATION_TRACKER.md). Tests: `python3 -m py_compile src/project_manager.py tests/test_detector_feature_generators_state.py`; `python3 -m pytest tests/test_detector_feature_generators_state.py -q -k 'support_rib_array'`; `node --test tests/js/detector_feature_generators_ui.test.mjs --test-name-pattern='support rib array'`. Outcome: reproduced a detached-parent visibility gap where support-rib arrays reported success, recorded generated rib placements, and still produced no live-scene instances; rejected detached parent LVs in backend realization, added scene-level create/regenerate coverage for generated rib PVs, and kept the inspector audit narrow with a UI smoke check that saved rib arrays still expose generated LV/PV names clearly enough for discoverability. Next: DGS-006 |
| 2026-04-10 | DGS-006 channel-cut visibility and revision audit | DONE | Files: [`/Volumes/nvme/projects/airpet/src/project_manager.py`](/Volumes/nvme/projects/airpet/src/project_manager.py), [`/Volumes/nvme/projects/airpet/tests/test_detector_feature_generators_state.py`](/Volumes/nvme/projects/airpet/tests/test_detector_feature_generators_state.py), [`/Volumes/nvme/projects/airpet/docs/DETECTOR_GENERATOR_STABILIZATION_TRACKER.md`](/Volumes/nvme/projects/airpet/docs/DETECTOR_GENERATOR_STABILIZATION_TRACKER.md). Tests: `python3 -m py_compile src/project_manager.py tests/test_detector_feature_generators_state.py`; `python3 -m pytest tests/test_detector_feature_generators_state.py -q -k 'channel_cut_array'`. Outcome: reproduced a detached-target visibility gap where channel-cut generators reported success and rewired saved logical volumes even when no targeted LV was placed in the live scene; rejected detached channel-cut targets in backend realization, added a focused regression for that failure mode, and extended channel-cut coverage to confirm result/cutter solids are reused while targeted-LV subsets stay stable across saved-spec revisions. Next: DGS-007 |

## Notes For Future Reordering

- It is fine to pull DGS-002 earlier if the Tools-entry-point change is needed to make manual verification easier.
- Prefer one generator family or one shared UX issue per cycle.
- Keep stabilization tasks small enough that a single automation run can finish one item end to end.
