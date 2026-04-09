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
- Current priority: move detector-generator launch entry points into Hierarchy `Tools` after tiled-array correctness and visibility fixes
- Success metric: existing detector generators feel dependable in real use, with sane defaults, clear launch points, and generated geometry that is visible and inspectable after creation/regeneration

## Current NEXT Task

DGS-002: move detector-generator creation into Hierarchy `Tools` and include Ring Array in the same tool surface.

Focus for this task:

- add detector-generator creation where users already look for geometry-building tools in the Hierarchy tab
- include Ring Array in that same tool surface instead of keeping it as a separate path
- keep the Properties-side detector-generator cards focused on inspection and regeneration, not as the primary launch path
- add the smallest sufficient UI regression or smoke coverage that protects the new entry point

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
| DGS-002 | P0 | Entry Points | Move detector-generator creation into Hierarchy `Tools` and include Ring Array in the same tool surface | NEXT | Prefer Properties-side cards as inspector/regenerate surfaces rather than the primary launch point |
| DGS-003 | P1 | Properties UX | Reduce Properties-panel generator bulk while keeping saved-generator inspection and regeneration accessible | PENDING | This may be partly solved by DGS-002; keep the slice narrow |
| DGS-004 | P1 | Layered Stack | Audit layered detector stack create/regenerate visibility and revision behavior end to end | PENDING | Focus on generated placements/modules actually appearing and staying inspectable |
| DGS-005 | P1 | Support Ribs | Audit support-rib array create/regenerate visibility and revision behavior end to end | PENDING | Check both placement creation and scene/hierarchy discoverability |
| DGS-006 | P1 | Channel Cuts | Audit channel-cut array realization, target updates, and saved-generator revision behavior end to end | PENDING | Focus on cut-result visibility and target LV retargeting consistency |
| DGS-007 | P1 | Shield Sleeve | Audit annular shield sleeve realization, placement visibility, and revision behavior end to end | PENDING | Confirm generated LV/PV visibility and regeneration are clear in the app |
| DGS-008 | P2 | Shared UX | Add shared generated-object selection or reveal affordances when they materially improve generator discoverability | PENDING | Only if still needed after the earlier fixes |

## Cycle Log

| Date | Task | Outcome | Notes |
| --- | --- | --- | --- |
| 2026-04-09 | Backlog setup | DONE | Created a detector-generator stabilization loop seeded from real post-generator usage feedback, starting with tiled sensor array defaults and generated-placement visibility |
| 2026-04-10 | DGS-001 tiled-array defaults and visible parents | DONE | Files: [`/Volumes/nvme/projects/airpet/static/detectorFeatureGeneratorsUi.js`](/Volumes/nvme/projects/airpet/static/detectorFeatureGeneratorsUi.js), [`/Volumes/nvme/projects/airpet/static/detectorFeatureGeneratorEditor.js`](/Volumes/nvme/projects/airpet/static/detectorFeatureGeneratorEditor.js), [`/Volumes/nvme/projects/airpet/src/project_manager.py`](/Volumes/nvme/projects/airpet/src/project_manager.py), [`/Volumes/nvme/projects/airpet/tests/js/detector_feature_generators_ui.test.mjs`](/Volumes/nvme/projects/airpet/tests/js/detector_feature_generators_ui.test.mjs), [`/Volumes/nvme/projects/airpet/tests/test_detector_feature_generators_state.py`](/Volumes/nvme/projects/airpet/tests/test_detector_feature_generators_state.py), [`/Volumes/nvme/projects/airpet/docs/DETECTOR_GENERATOR_STABILIZATION_TRACKER.md`](/Volumes/nvme/projects/airpet/docs/DETECTOR_GENERATOR_STABILIZATION_TRACKER.md). Tests: `node --check static/detectorFeatureGeneratorsUi.js`; `node --check static/detectorFeatureGeneratorEditor.js`; `python3 -m py_compile src/project_manager.py tests/test_detector_feature_generators_state.py`; `node --test tests/js/detector_feature_generators_ui.test.mjs`; `python3 -m pytest tests/test_detector_feature_generators_state.py -q -k 'tiled_sensor_array'`. Outcome: fixed the tiled-array editor defaults so untouched pitch matches the default sensor size, reproduced the invisible-placement gap as detached parent-LV targeting, limited the parent picker to live scene LVs while preserving existing targets for edits, rejected detached tiled-array parents in backend realization, and added scene-level regression coverage that confirms generated sensor PVs appear in the Three.js scene description. Next: DGS-002 |

## Notes For Future Reordering

- It is fine to pull DGS-002 earlier if the Tools-entry-point change is needed to make manual verification easier.
- Prefer one generator family or one shared UX issue per cycle.
- Keep stabilization tasks small enough that a single automation run can finish one item end to end.
