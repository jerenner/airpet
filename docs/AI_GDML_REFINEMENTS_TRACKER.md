# AI + GDML Refinements Tracker

Last updated: 2026-04-04

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

- Overall phase: backlog complete
- Release posture: conditional pass, with the parameterised polycone/polyhedra corpus gap, twisted parameterised-solid importer gap, and remaining AIRPET primitive parameterised-import gap now closed
- Current priority: none; all tracked tasks are DONE

## Current NEXT Task

None; backlog exhausted.

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
| GDML-003 | P1 | GDML | Add parameterised solid import mapping for `trap_dimensions` | DONE | Parser now maps `trap_dimensions` onto the internal trap parameter shape keys; added a representative import regression that asserts the mapping warning is not emitted |
| GDML-004 | P1 | GDML | Extend parameterised-solid import mappings for additional AIRPET-supported primitives found in the corpus | DONE | Parser now maps the additional flat AIRPET primitives used in the review: sphere, orb, torus, ellipsoid, para, and hype; added regressions to lock in the no-warning import path |
| GDML-005 | P1 | GDML | Create a representative AIRPET-authored GDML round-trip corpus and smoke-test suite | DONE | Added a three-file GDML corpus plus a smoke-test suite; parser/writer now preserves procedural-volume names on export, and the round-trip path covers materials, booleans, tessellated solids, assemblies, and parameterised placements |
| AI-003 | P1 | AI | Build an AI benchmark corpus with representative prompts and expected tool traces/results | DONE | Added a five-case prompt/trace corpus plus regression harness for slab+beam, define update, simulation launch, analysis filter, and param-study setup; the test module includes local import shims so it runs in the stripped interpreter here |
| AI-004 | P1 | AI | Add targeted AI parity regressions for advanced simulation options and analysis filters | DONE | Added parity regressions that compare AI dispatch and HTTP handling for advanced `run_simulation` options plus `sensitive_detector` analysis filtering |
| GDML-006 | P2 | GDML | Improve unsupported-construct feedback for `<!ENTITY>`, `<file>`, and unmapped parameterised solids | DONE | Parser now emits clearer `<!ENTITY>`, `<file>`, and unmapped parameterised-solid diagnostics, and it records import warnings for downstream surfaces; added regressions for the fatal entity case, the skipped `<file>` placement, and the unmapped dimensions warning |
| GDML-007 | P2 | GDML | Evaluate modular GDML `<file>` include support, or formalize explicit non-support in the product/import UX | DONE | GDML load/import now surfaces unsupported `<file>` include warnings in the browser, and the file-menu labels/tooltips make the self-contained-only limitation explicit |
| AI-005 | P2 | AI | Review remaining UI features against AI tool coverage and close the highest-value gaps | DONE | Added source-selection parity for `setup_param_study` and simulation-in-loop `run_optimization`; the AI schema now advertises study/run source subsets, dispatch persists and forwards selected source ids, and focused regressions cover schema exposure plus payload forwarding |
| GDML-008 | P1 | GDML | Preserve nested `polycone_dimensions` and `polyhedra_dimensions` through import/export | DONE | Parser now carries nested `zplane` arrays for parameterised polycone/polyhedra volumes, the writer emits them back out, recursive evaluation preserves nested parameter payloads, and focused round-trip coverage passes |
| GDML-009 | P2 | GDML | Add a representative corpus fixture for parameterised polycone/polyhedra volumes | DONE | Promoted into the GDML corpus smoke suite as `parameterised_polycone_polyhedra.gdml` |
| GDML-010 | P2 | GDML | Add parameterised solid import mapping for twistedbox/twistedtrd/twistedtrap/twistedtubs | DONE | Parser now normalizes the AIRPET twisted parameterised solids that the writer/project manager already support, and focused regressions cover all four shapes |
| AI-006 | P2 | AI | Preserve source provenance in downloaded param-study JSON | DONE | Added `tests/js/param_study_export_summary.test.mjs` to lock in run-result provenance, launch-payload fallback, and preview-sweep no-source handling for the export summary helper that feeds downloaded study JSON |
| GDML-011 | P2 | GDML | Add parameterised import mappings for eltube/elcone/paraboloid | DONE | Parser now normalizes the remaining AIRPET primitive parameter blocks that were still imported raw, and the GDML regression table now locks all three shapes warning-free |

## Cycle Log

| Date | Task | Outcome | Notes |
| --- | --- | --- | --- |
| 2026-04-02 | Backlog setup | DONE | Created tracker and seeded the first ordered hardening backlog from the release audit |
| 2026-04-02 | GDML-001 | DONE | Files: `src/gdml_parser.py`, `src/expression_evaluator.py`, `tests/test_gdml.py`; tests: `conda run --no-capture-output -n virtualpet pytest /Users/jrenner/local/jerenner/airpet/tests/test_gdml.py -q` (`7 passed`); outcome: imported density units now survive parse/eval/export and materials-only GDML no longer trips empty-solid pruning |
| 2026-04-02 | AI-001 | DONE | Files: `src/ai_tools.py`, `app.py`, `tests/test_ai_api.py`, `tests/test_ai_integration.py`; tests: `conda run --no-capture-output -n virtualpet pytest /Users/jrenner/local/jerenner/airpet/tests/test_ai_integration.py /Users/jrenner/local/jerenner/airpet/tests/test_ai_api.py -q -k 'test_ai_geometry_tools_schema_is_valid_for_gemini_generate_content_config or test_run_simulation_ai_schema_exposes_advanced_simulation_options or test_ai_simulation_tools or test_ai_run_simulation_forwards_advanced_simulation_options or test_ai_run_simulation_blocks_on_preflight_failure or test_run_g4_simulation_preserves_save_hits_and_passes_sim_params_to_geant4_env'` (`6 passed`); outcome: `run_simulation` now accepts the advanced UI options, forwards them through the AI dispatcher, and preserves `save_hits` in multi-process launches |
| 2026-04-03 | AI-002 | DONE | Files: `src/ai_tools.py`, `app.py`, `tests/test_ai_api.py`, `tests/test_ai_integration.py`; tests: `conda run --no-capture-output -n virtualpet pytest /Users/jrenner/local/jerenner/airpet/tests/test_ai_api.py -q -k 'test_ai_tool_route_bridge_get_metadata_and_analysis or test_ai_tool_route_bridge_get_analysis_without_request_context'` (`2 passed`) and `conda run --no-capture-output -n virtualpet pytest /Users/jrenner/local/jerenner/airpet/tests/test_ai_integration.py -q -k 'test_get_simulation_analysis_ai_schema_exposes_sensitive_detector_filter or test_run_simulation_ai_schema_exposes_advanced_simulation_options'` (`2 passed`); outcome: AI analysis now accepts an optional `sensitive_detector` filter end to end and the schema/docs stay aligned; local commit `b62f07f` created, but push to `origin dev` is blocked here because `github.com` does not resolve |
| 2026-04-03 | GDML-002 | DONE | Files: `src/gdml_parser.py`, `tests/test_gdml.py`; tests: `conda run --no-capture-output -n virtualpet pytest /Users/jrenner/local/jerenner/airpet/tests/test_gdml.py -q` (`8 passed`); outcome: `trd_dimensions` now maps onto the internal `Parameterisation` shape keys during import, and the new regression covers a representative parameterised `trd` GDML file |
| 2026-04-03 | GDML-003 | DONE | Files: `src/gdml_parser.py`, `tests/test_gdml.py`; tests: `conda run --no-capture-output -n virtualpet pytest /Users/jrenner/local/jerenner/airpet/tests/test_gdml.py -q -k 'parameterised_trd_dimensions_are_mapped_on_import or parameterised_trap_dimensions_are_mapped_on_import'` (`2 passed`); outcome: `trap_dimensions` now maps onto the internal trap parameter keys during import, and the new regression covers a representative parameterised `trap` GDML file |
| 2026-04-03 | GDML-004 | DONE | Files: `src/gdml_parser.py`, `tests/test_gdml.py`; tests: `conda run --no-capture-output -n virtualpet pytest /Users/jrenner/local/jerenner/airpet/tests/test_gdml.py -q -k 'parameterised_'` (`8 passed, 7 deselected`); outcome: parameterised import now covers the additional flat AIRPET primitives used in the review (`sphere`, `orb`, `torus`, `ellipsoid`, `para`, `hype`), and the regressions lock in the no-warning path |
| 2026-04-03 | GDML-005 | DONE | Files: `src/gdml_writer.py`, `tests/test_gdml_corpus.py`, `tests/fixtures/gdml/corpus/materials_boolean.gdml`, `tests/fixtures/gdml/corpus/assembly_tessellated.gdml`, `tests/fixtures/gdml/corpus/parameterised_placements.gdml`; tests: `conda run --no-capture-output -n virtualpet pytest /Users/jrenner/local/jerenner/airpet/tests/test_gdml_corpus.py -q` (`3 passed`); outcome: added a representative AIRPET-authored GDML corpus and smoke-test suite covering materials, booleans, tessellated solids, assemblies, and parameterised placements, and the writer now preserves procedural-volume names on export so round-trips stay stable |
| 2026-04-03 18:53:45 CEST | AI-003 | DONE | Files: `tests/fixtures/ai/benchmark_corpus.json`, `tests/test_ai_benchmark_corpus.py`, `docs/AI_GDML_REFINEMENTS_TRACKER.md`; tests: `pytest /Volumes/nvme/projects/airpet/tests/test_ai_benchmark_corpus.py -q` (`5 passed`); outcome: created a five-case AI benchmark corpus with expected tool traces/results plus a focused regression harness, recorded the next task as `AI-004`, and committed the change as `17aa302` locally, but push to `origin dev` is blocked here because `github.com` does not resolve |
| 2026-04-03 20:05:37 CEST | AI-004 | DONE | Files: `tests/test_ai_api.py`; tests: `source /Users/marth/miniconda/etc/profile.d/conda.sh && conda run -n airpet python -m pytest /Volumes/nvme/projects/airpet/tests/test_ai_api.py -q -k 'ai_and_http_run_simulation_share_advanced_option_payload or ai_and_http_simulation_analysis_share_sensitive_detector_filter'` (`2 passed`); outcome: added parity regressions that lock advanced simulation option forwarding and `sensitive_detector` analysis filtering across both AI dispatch and HTTP routes, then promoted `GDML-006` to `NEXT` |
| 2026-04-03 22:06:10 CEST | GDML-006 | DONE | Files: `src/gdml_parser.py`, `tests/test_gdml.py`; tests: `source /Users/marth/miniconda/etc/profile.d/conda.sh && conda run -n airpet python -m pytest /Volumes/nvme/projects/airpet/tests/test_gdml.py -q` (`18 passed`); outcome: the parser now emits clearer diagnostics for `<!ENTITY>`, `<file>`, and unmapped parameterised-solid imports, records import warnings for downstream use, and the regression suite covers all three unsupported-construct paths |
| 2026-04-04 00:05:46 CEST | GDML-007 | DONE | Files: `app.py`, `static/main.js`, `templates/index.html`, `tests/test_gdml.py`; tests: `source /Users/marth/miniconda/etc/profile.d/conda.sh && conda run -n airpet python -m pytest /Volumes/nvme/projects/airpet/tests/test_gdml.py -q` (`20 passed`); outcome: GDML open/import responses now propagate parser warnings, the browser surfaces unsupported `<file>` includes as an explicit warning, and the menu labels/tooltips now call out self-contained-only GDML imports; local commit `e766bf7` created, but `git push origin dev` is still blocked here because `github.com` does not resolve; next task is `AI-005` |
| 2026-04-04 02:06:19 CEST | AI-005 | DONE | Files: `src/ai_tools.py`, `app.py`, `tests/test_ai_integration.py`, `tests/test_ai_api.py`, `docs/AI_GDML_REFINEMENTS_TRACKER.md`; tests: `source /Users/marth/miniconda/etc/profile.d/conda.sh && conda run -n airpet python -m pytest tests/test_ai_integration.py -q -k 'param_study_ai_schema_exposes_simulation_source_selection'` (`1 passed`) and `source /Users/marth/miniconda/etc/profile.d/conda.sh && conda run -n airpet python -m pytest tests/test_ai_api.py -q -k 'setup_param_study_persists_simulation_source_ids or run_optimization_forwards_selected_source_ids_to_simulation_in_loop_route'` (`2 passed`); outcome: AI param-study and simulation-in-loop optimization now accept source-subset selection, the schema advertises the new fields, dispatch persists study sources and forwards selected source ids to the launch route, the remaining tracked backlog is empty, and local commit `534c31d` is ready while `git push origin dev` is blocked because `github.com` does not resolve here |
| 2026-04-04 11:41:22 CEST | GDML-008 | DONE | Files: `src/gdml_parser.py`, `src/gdml_writer.py`, `src/project_manager.py`, `tests/test_gdml.py`; tests: `source /Users/marth/miniconda/etc/profile.d/conda.sh && conda run -n airpet python -m pytest tests/test_gdml.py -q -k 'parameterised_'` (`11 passed, 11 deselected`); outcome: parameterised polycone/polyhedra GDML now imports with nested `zplane` payloads intact, exports them back out, and preserves nested evaluation/dependency handling; local commit `6ccbdaf` created, but `git push origin dev` is blocked here because `github.com` does not resolve; next task is `GDML-009` |
| 2026-04-04 13:02:46 CEST | GDML-009 | DONE | Files: `tests/test_gdml_corpus.py`, `tests/fixtures/gdml/corpus/parameterised_polycone_polyhedra.gdml`; tests: `source /Users/marth/miniconda/etc/profile.d/conda.sh && conda run -n airpet python -m pytest tests/test_gdml_corpus.py -q` (`4 passed`); outcome: added a representative corpus smoke fixture covering parameterised polycone and polyhedra volumes, and the new case round-trips cleanly with nested `zplane` payloads preserved; no NEXT tasks remain |
| 2026-04-04 17:04:48 CEST | GDML-010 | DONE | Files: `src/gdml_parser.py`, `tests/test_gdml.py`, `docs/AI_GDML_REFINEMENTS_TRACKER.md`; tests: `source /Users/marth/miniconda/etc/profile.d/conda.sh && conda run -n airpet python -m pytest tests/test_gdml.py -q -k 'twisted_dimensions'` (`4 passed, 22 deselected`); outcome: normalized twistedbox/twistedtrd/twistedtrap/twistedtubs parameterised imports so they no longer fall back to raw GDML names, and focused regressions now lock the four AIRPET-supported twisted shapes; local commit `d61dae6` created, but `git push origin dev` is blocked here because `github.com` does not resolve; backlog remains exhausted and there is still no NEXT task |
| 2026-04-04 15:05:17 CEST | AI-006 | DONE | Files: `tests/js/param_study_export_summary.test.mjs`, `docs/AI_GDML_REFINEMENTS_TRACKER.md`; tests: `node --test tests/js/param_study_export_summary.test.mjs` (`3 passed`); outcome: added regression coverage that keeps source provenance in the downloaded param-study JSON summary helper aligned with run-result provenance, launch-payload fallback, and preview-sweep behavior; backlog remains exhausted and there is still no NEXT task |
| 2026-04-04 19:06:54 CEST | GDML-011 | DONE | Files: `src/gdml_parser.py`, `tests/test_gdml.py`, `docs/AI_GDML_REFINEMENTS_TRACKER.md`; tests: `source /Users/marth/miniconda/etc/profile.d/conda.sh && conda run -n airpet python -m pytest tests/test_gdml.py -q -k 'parameterised_additional_dimensions_are_mapped_on_import'` (`9 passed, 20 deselected`); outcome: normalized `eltube_dimensions`, `elcone_dimensions`, and `paraboloid_dimensions` during parameterised import, and the regression table now keeps those AIRPET primitives warning-free; backlog remains exhausted and there is still no NEXT task |

## Notes For Future Reordering

- It is fine to reorder tasks if a newly discovered correctness bug is more urgent.
- Prefer correctness and regression protection before breadth.
- Prefer AIRPET-authored GDML round-trips before broader external compatibility.
