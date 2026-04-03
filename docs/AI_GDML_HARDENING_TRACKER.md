# AI + GDML Hardening Tracker

Last updated: 2026-04-03

## Mission

Incrementally harden AIRPET's AI and GDML capabilities until they are complete enough to be trusted as first-class product features, with each improvement backed by focused regression tests.

This tracker is the working source of truth for that effort. It is expected to evolve as we learn more.

## Scope

In scope:
- AI parity with high-value UI simulation and analysis workflows
- AI reliability and prompt/tool-contract robustness
- GDML export/import correctness for AIRPET-authored geometries
- GDML compatibility hardening for representative external files
- Regression tests and benchmark coverage for both areas

Out of scope for a single cycle:
- broad refactors unrelated to AI/GDML hardening
- starting multiple backlog items in one run

## Operating Loop

Each hardening cycle should do exactly one backlog item:

1. Read this tracker.
2. Pick the task marked `NEXT`.
3. If nothing is marked `NEXT`, pick the highest-priority `PENDING` task and mark it `NEXT`.
4. Implement that task end to end.
5. Add or update focused regression tests.
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

## Definition of Done

A task is only `DONE` when all of the following are true:

- the code path is implemented
- regression tests were added or updated when appropriate
- the relevant targeted tests passed locally
- the tracker was updated with outcome and next task

## Current Status

- Overall phase: backlog bootstrapping
- Release posture: conditional pass, with known bounded gaps in AI/UI parity and GDML import breadth
- Current priority: close correctness gaps first, then broaden parity and corpus coverage

## Current NEXT Task

`GDML-003` Add parameterised solid import mapping for `trap_dimensions`.

Reason:
- highest-priority pending P1 after closing `GDML-002`

## Backlog

Statuses:
- `NEXT`
- `PENDING`
- `IN_PROGRESS`
- `BLOCKED`
- `DONE`

| ID | Priority | Area | Feature | Status | Notes |
| --- | --- | --- | --- | --- | --- |
| GDML-001 | P0 | GDML | Parse `<D unit="...">` on material import and normalize/preserve density meaning on round-trip | DONE | Parser now preserves imported density units in the raw expression; added round-trip coverage for `g/cm3`, `mg/cm3`, and `kg/m3`, plus a materials-only parse edge case |
| AI-001 | P0 | AI | Expand `run_simulation` AI schema/backend to accept key UI simulation options | DONE | Schema now exposes `production_cut`, `hit_energy_threshold`, `save_hits`, `save_hit_metadata`, `save_particles`, `save_tracks_range`, `seed1`, `seed2`, `print_progress`, `physics_list`, `optical_physics`; backend forwards them into macro generation and Geant4 env setup, and the multi-process runner now preserves `save_hits` |
| AI-002 | P0 | AI | Expose `sensitive_detector` filter through AI `get_simulation_analysis` | DONE | Schema now exposes optional `sensitive_detector`, dispatch forwards it through to analysis, and regressions cover schema/bridge alignment |
| GDML-002 | P1 | GDML | Add parameterised solid import mapping for `trd_dimensions` | DONE | Parser now maps `trd_dimensions` to `x1/x2/y1/y2/z`; added a representative import regression for a parameterised `trd` volume |
| GDML-003 | P1 | GDML | Add parameterised solid import mapping for `trap_dimensions` | NEXT | Include parser tests and representative import case |
| GDML-004 | P1 | GDML | Extend parameterised-solid import mappings for additional AIRPET-supported primitives found in the corpus | PENDING | Start with the highest-frequency shapes after corpus review |
| GDML-005 | P1 | GDML | Create a representative AIRPET-authored GDML round-trip corpus and smoke-test suite | PENDING | Include materials, booleans, tessellated solids, assemblies, and parameterised placements |
| AI-003 | P1 | AI | Build an AI benchmark corpus with representative prompts and expected tool traces/results | PENDING | Start with slab + beam, define update, run simulation, analysis filter, and param-study setup |
| AI-004 | P1 | AI | Add targeted AI parity regressions for advanced simulation options and analysis filters | PENDING | This should lock in work from AI-001 and AI-002 |
| GDML-006 | P2 | GDML | Improve unsupported-construct feedback for `<!ENTITY>`, `<file>`, and unmapped parameterised solids | PENDING | Clear user-facing diagnostics are valuable even before deeper compatibility work |
| GDML-007 | P2 | GDML | Evaluate modular GDML `<file>` include support, or formalize explicit non-support in the product/import UX | PENDING | Decide based on value vs complexity after the core corpus is stable |
| AI-005 | P2 | AI | Review remaining UI features against AI tool coverage and close the highest-value gaps | PENDING | Keep this scoped and data-driven; do not chase low-value parity for its own sake |

## Cycle Log

| Date | Task | Outcome | Notes |
| --- | --- | --- | --- |
| 2026-04-02 | Backlog setup | DONE | Created tracker and seeded the first ordered hardening backlog from the release audit |
| 2026-04-02 | GDML-001 | DONE | Files: `src/gdml_parser.py`, `src/expression_evaluator.py`, `tests/test_gdml.py`; tests: `conda run --no-capture-output -n virtualpet pytest /Users/jrenner/local/jerenner/airpet/tests/test_gdml.py -q` (`7 passed`); outcome: imported density units now survive parse/eval/export and materials-only GDML no longer trips empty-solid pruning |
| 2026-04-02 | AI-001 | DONE | Files: `src/ai_tools.py`, `app.py`, `tests/test_ai_api.py`, `tests/test_ai_integration.py`; tests: `conda run --no-capture-output -n virtualpet pytest /Users/jrenner/local/jerenner/airpet/tests/test_ai_integration.py /Users/jrenner/local/jerenner/airpet/tests/test_ai_api.py -q -k 'test_ai_geometry_tools_schema_is_valid_for_gemini_generate_content_config or test_run_simulation_ai_schema_exposes_advanced_simulation_options or test_ai_simulation_tools or test_ai_run_simulation_forwards_advanced_simulation_options or test_ai_run_simulation_blocks_on_preflight_failure or test_run_g4_simulation_preserves_save_hits_and_passes_sim_params_to_geant4_env'` (`6 passed`); outcome: `run_simulation` now accepts the advanced UI options, forwards them through the AI dispatcher, and preserves `save_hits` in multi-process launches |
| 2026-04-03 | AI-002 | DONE | Files: `src/ai_tools.py`, `app.py`, `tests/test_ai_api.py`, `tests/test_ai_integration.py`; tests: `conda run --no-capture-output -n virtualpet pytest /Users/jrenner/local/jerenner/airpet/tests/test_ai_api.py -q -k 'test_ai_tool_route_bridge_get_metadata_and_analysis or test_ai_tool_route_bridge_get_analysis_without_request_context'` (`2 passed`) and `conda run --no-capture-output -n virtualpet pytest /Users/jrenner/local/jerenner/airpet/tests/test_ai_integration.py -q -k 'test_get_simulation_analysis_ai_schema_exposes_sensitive_detector_filter or test_run_simulation_ai_schema_exposes_advanced_simulation_options'` (`2 passed`); outcome: AI analysis now accepts an optional `sensitive_detector` filter end to end and the schema/docs stay aligned; local commit `b62f07f` created, but push to `origin dev` is blocked here because `github.com` does not resolve |
| 2026-04-03 | GDML-002 | DONE | Files: `src/gdml_parser.py`, `tests/test_gdml.py`; tests: `conda run --no-capture-output -n virtualpet pytest /Users/jrenner/local/jerenner/airpet/tests/test_gdml.py -q` (`8 passed`); outcome: `trd_dimensions` now maps onto the internal `Parameterisation` shape keys during import, and the new regression covers a representative parameterised `trd` GDML file |

## Notes For Future Reordering

- It is fine to reorder tasks if a newly discovered correctness bug is more urgent.
- Prefer correctness and regression protection before breadth.
- Prefer AIRPET-authored GDML round-trips before broader external compatibility.
