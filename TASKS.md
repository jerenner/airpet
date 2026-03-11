# AIRPET Task Tracker

## In Progress

- None.

## Recently Completed

- **Negative-path compare metadata contract checks (route + AI wrappers, representative 400/404 paths)** (2026-03-11)
  - Added shared helpers to lock error-envelope shape on compare failures:
    - `tests/test_preflight.py`: `_assert_compare_route_error_payload_excludes_success_metadata(...)`
    - `tests/test_ai_api.py`: `_assert_compare_ai_error_payload_excludes_success_metadata(...)`
  - Added/updated regression tests to assert compare failure responses keep `success/error` while excluding success-only metadata fields (`comparison`, `selection`, `ordering_metadata`, `version_sources`, version ids/reports):
    - Route: missing required compare-version id (`POST /api/preflight/compare_versions`, 400)
    - Route: invalid manual saved index (`POST /api/preflight/compare_autosave_vs_manual_saved_index`, 400)
    - Route: missing saved versions (`POST /api/preflight/compare_versions`, 404)
    - AI wrapper: missing saved versions (`compare_preflight_versions`)
    - AI wrapper: invalid manual saved index (`compare_autosave_preflight_vs_manual_saved_index`)
  - Why: gives deterministic client branching guarantees in common compare failure modes and prevents accidental leakage of partial success metadata on errors.

- **AI compare-wrapper selection/source metadata contract coverage across preflight compare tools** (2026-03-11)
  - Added shared helper `_assert_compare_ai_selection_and_source_metadata(...)` in `tests/test_ai_api.py` to lock AI compare-response metadata contract:
    - `ordering_metadata.ordering_basis == "explicit_version_ids"`
    - `version_sources.{baseline,candidate}` id/path/mtime + within-root checks
    - optional `selection.ordering_basis` checks per wrapper strategy
  - Extended AI-dispatch compare success tests to assert deterministic metadata contracts for:
    - `compare_preflight_versions`
    - `compare_latest_preflight_versions`
    - `compare_autosave_preflight_vs_latest_saved`
    - `compare_autosave_preflight_vs_previous_manual_saved`
    - `compare_autosave_preflight_vs_manual_saved_index`
    - `compare_autosave_preflight_vs_manual_saved_for_simulation_run`
    - `compare_autosave_preflight_vs_manual_saved_for_simulation_run_index`
    - `compare_manual_preflight_versions_for_simulation_run_indices`
    - `compare_autosave_preflight_vs_saved_version`
    - `compare_autosave_preflight_vs_snapshot_version`
    - `compare_autosave_preflight_vs_latest_snapshot`
    - `compare_autosave_preflight_vs_previous_snapshot`
    - `compare_autosave_snapshot_preflight_versions`
    - `compare_latest_autosave_snapshot_preflight_versions`
  - Why: keeps AI wrapper contracts aligned with route-level deterministic diagnostics expectations used by automation.

- **Route-level selection/source metadata contract coverage across preflight compare endpoints** (2026-03-11)
  - Added shared assertion helper `_assert_compare_route_selection_and_source_metadata(...)` in `tests/test_preflight.py` to lock compare-response metadata contract:
    - `ordering_metadata.ordering_basis == "explicit_version_ids"`
    - `version_sources.{baseline,candidate}` id/path/mtime + within-root checks
    - optional `selection.ordering_basis` checks per endpoint strategy
  - Extended all route-level `*_returns_comparison_payload` compare endpoint tests to assert deterministic metadata contracts for:
    - `compare_versions`
    - `compare_latest_versions`
    - `compare_autosave_vs_latest_saved`
    - `compare_autosave_vs_previous_manual_saved`
    - `compare_autosave_vs_manual_saved_index`
    - `compare_autosave_vs_manual_saved_for_simulation_run`
    - `compare_autosave_vs_manual_saved_for_simulation_run_index`
    - `compare_manual_saved_versions_for_simulation_run_indices`
    - `compare_autosave_vs_saved_version`
    - `compare_autosave_vs_snapshot_version`
    - `compare_autosave_vs_latest_snapshot`
    - `compare_autosave_vs_previous_snapshot`
    - `compare_snapshot_versions`
    - `compare_latest_snapshot_versions`
  - Why: prevents silent drift in reproducibility/debug metadata across endpoint variants that AI agents and deterministic workflows depend on.

- **Cycle-truncation metadata preservation coverage for run-linked/manual-index compare wrappers (route + AI)** (2026-03-11)
  - Added AI-dispatch regression tests in `tests/test_ai_api.py` for:
    - `compare_autosave_preflight_vs_manual_saved_index`
    - `compare_autosave_preflight_vs_manual_saved_for_simulation_run`
    - `compare_autosave_preflight_vs_manual_saved_for_simulation_run_index`
    - `compare_manual_preflight_versions_for_simulation_run_indices`
    locking preservation of `placement_hierarchy_cycle_report_truncated` diagnostics through run-linked/manual-index compare selectors.
  - Added route-level regression tests in `tests/test_preflight.py` for:
    - `POST /api/preflight/compare_autosave_vs_manual_saved_index`
    - `POST /api/preflight/compare_autosave_vs_manual_saved_for_simulation_run`
    - `POST /api/preflight/compare_autosave_vs_manual_saved_for_simulation_run_index`
    - `POST /api/preflight/compare_manual_saved_versions_for_simulation_run_indices`
    ensuring truncation issue message + metadata (`max_cycles`, `reported_cycles`, `truncated`) are preserved in candidate reports and compare deltas.
  - Forced deterministic truncation behavior in all new tests by patching `_find_preflight_hierarchy_cycles(..., max_cycles=1)`.
  - Why: completes medium-impact contract protection for deterministic compare entry points keyed by manual indices and simulation-run linkage.

- **Cycle-truncation metadata preservation coverage for explicit compare surfaces (route + AI)** (2026-03-11)
  - Added shared truncation-assert helpers in `tests/test_preflight.py` and `tests/test_ai_api.py` to lock exact truncation diagnostics contract:
    - code `placement_hierarchy_cycle_report_truncated`
    - message text `Cycle reporting truncated at max_cycles=1; reported 1 cycle findings.`
    - metadata payload (`max_cycles`, `reported_cycles`, `truncated`)
  - Added route regression coverage in `tests/test_preflight.py` for:
    - `POST /api/preflight/compare_versions`
    - `POST /api/preflight/compare_snapshot_versions`
    ensuring candidate reports preserve truncation metadata through explicit version/snapshot comparison surfaces.
  - Added AI-dispatch regression coverage in `tests/test_ai_api.py` for:
    - `compare_preflight_versions`
    - `compare_autosave_snapshot_preflight_versions`
    ensuring metadata stability through explicit-version AI wrappers.
  - Forced deterministic truncation via patched `_find_preflight_hierarchy_cycles(..., max_cycles=1)` to make assertions reproducible.
  - Why: broadens contract protection from autosave-vs-latest-only to explicit compare paths used by deterministic debugging workflows.

- **Cycle-truncation metadata API-surface regression coverage (route + AI compare wrapper)** (2026-03-11)
  - Added route-level regression test in `tests/test_preflight.py` for `POST /api/preflight/compare_autosave_vs_latest_saved` to lock preservation of `placement_hierarchy_cycle_report_truncated` diagnostics emitted by core preflight logic.
  - Added AI-dispatch regression test in `tests/test_ai_api.py` for `compare_autosave_preflight_vs_latest_saved` to ensure wrapper responses keep truncation diagnostics unchanged.
  - Added deterministic multi-cycle helper in `tests/test_ai_api.py` and constrained cycle discovery to `max_cycles=1` via patched `_find_preflight_hierarchy_cycles(...)` so truncation behavior is forced and reproducible.
  - Locked both truncation message text and `metadata` payload contract (`max_cycles`, `reported_cycles`, `truncated`) in wrapper responses.
  - Why: prevents accidental metadata loss between core preflight diagnostics and higher-level API/AI compare surfaces used for debugging and automation.

- **Cycle-report truncation metadata enrichment (`max_cycles`)** (2026-03-11)
  - Updated `_find_preflight_hierarchy_cycles(...)` in `src/project_manager.py` to return structured metadata alongside cycles:
    - `max_cycles`
    - `reported_cycles`
    - `truncated`
  - Updated `run_preflight_checks()` truncation diagnostics to emit explicit cap metadata in both message text and issue payload:
    - `placement_hierarchy_cycle_report_truncated`
    - message now includes `max_cycles` + reported count
    - issue now includes a `metadata` object for deterministic downstream parsing
  - Extended preflight issue signature normalization to include optional issue `metadata`, keeping summary fingerprints aligned with enriched diagnostics payloads.
  - Updated regression tests in `tests/test_preflight.py` to lock helper metadata and truncation issue metadata behavior.
  - Why: improves machine-readable failure diagnostics and keeps helper/issue contracts consistent for debugging and AI automation.

- **Cycle-report truncation diagnostics regression coverage (`max_cycles`)** (2026-03-11)
  - Added `_build_multi_cycle_lv_triangle(...)` test helper in `tests/test_preflight.py` to construct a deterministic multi-cycle LV graph for cap-behavior validation.
  - Added `test_find_preflight_hierarchy_cycles_respects_max_cycles_cap_deterministically` to lock `_find_preflight_hierarchy_cycles(..., max_cycles=...)` behavior:
    - deterministic cycle ordering
    - deterministic cap at `max_cycles`
    - deterministic `truncated=True` signaling when the cap is reached
  - Added `test_preflight_reports_cycle_truncation_issue_when_cycle_report_hits_cap` to lock emission of the `placement_hierarchy_cycle_report_truncated` info diagnostic from `run_preflight_checks()`.
  - Why: preserves debuggable, predictable failure-mode reporting when recursive geometry graphs produce many cycles.

- **Cycle-path diagnostics regression coverage for mixed physvol/procedural/assembly hierarchies** (2026-03-11)
  - Added `test_preflight_mixed_cycle_path_is_deterministic_and_deduplicated` in `tests/test_preflight.py` to lock deterministic cycle reporting for a mixed-edge loop:
    - `ASM → LV` via assembly placement
    - `LV → LV` via procedural container (`replica`)
    - `LV → ASM` via `physvol`
  - Test intentionally creates duplicate placements that collapse to the same graph edge and asserts only one `placement_hierarchy_cycle` issue is emitted, protecting de-duplication behavior.
  - Added `test_preflight_cycle_signature_normalization_deduplicates_rotations` to lock cycle-signature normalization for rotated representations of the same cycle.
  - Why: preserves deterministic, high-signal preflight diagnostics as mixed hierarchy graphs grow in complexity.

- **Placement hierarchy cycle detection now includes procedural-container edges** (2026-03-10)
  - Extended `_build_preflight_hierarchy_adjacency(...)` so procedural logical volumes (`replica`, `division`, `parameterised`) contribute deterministic LV→LV edges for cycle detection.
  - Added regression test `test_preflight_detects_procedural_placement_cycle` in `tests/test_preflight.py` covering recursive procedural-container loops.
  - Why: prevents recursive topology faults from escaping cycle diagnostics when loops are introduced through procedural containers instead of `physvol` placements.

- **Preflight guards for procedural placements (replica/division/parameterised)** (2026-03-10)
  - Added procedural preflight validation in `ProjectManager.run_preflight_checks()` for logical volumes using non-`physvol` content.
  - New checks include:
    - missing/unknown procedural `volume_ref`
    - world volume incorrectly used as a procedural child target
    - replica bounds sanity (`number`, `width`, non-zero direction)
    - division sanity (supported axis, partition bounds, derived slice width positivity for box mothers)
    - parameterised sanity (`ncopies` and parameter-block presence/count mismatch warning)
  - Added regression tests in `tests/test_preflight.py` for replica/division/parameterised invalid procedural configurations.
  - Why: catches stale procedural references and broken procedural bounds earlier, improving deterministic diagnostics before simulation/export.

- **Preflight version selection diagnostics: ordering + source metadata** (2026-03-10)
  - Added explicit ordering metadata across preflight version compare/list responses, including selection ordering basis for:
    - latest manual saved comparisons
    - autosave vs manual/snapshot comparisons
    - simulation-run-indexed manual comparison selectors
  - Added deterministic version source metadata in compare responses:
    - per-version source path checks (`version_dir_within_versions_root`, `version_json_within_versions_root`)
    - resolved version JSON mtime timestamps (`version_json_mtime_utc`)
    - timestamp provenance (`timestamp_from_version_id` for saved versions)
  - Expanded `list_preflight_versions` and run-id manual version listings with:
    - `ordering_basis` and root metadata
    - per-entry `timestamp_source`, `version_json_mtime_utc`, and source path checks
  - Added regression assertions in `tests/test_preflight.py` to lock ordering/source-metadata behavior.
  - Why: improves reproducibility and debugging by making version selection semantics explicit and auditable for both human users and AI agents.

- **Preflight cycle detection for LV/assembly placement hierarchy** (2026-03-10)
  - Added deterministic graph traversal in `ProjectManager.run_preflight_checks()` to detect recursive placement loops across:
    - logical volume → logical volume
    - logical volume ↔ assembly
    - assembly ↔ assembly
  - New preflight error code: `placement_hierarchy_cycle` with explicit cycle path diagnostics (e.g. `LV:A -> ASM:B -> LV:A`).
  - Added cycle de-duplication + deterministic ordering for stable summaries/fingerprints.
  - Added regression tests in `tests/test_preflight.py` for both LV↔LV and LV↔ASM loops.
  - Why: recursive placement loops are high-impact topology faults that can silently poison traversal/export logic and are hard to debug without explicit path-level reporting.

- **Preflight integrity hardening for world/placement references** (2026-03-10)
  - Added new preflight error checks for:
    - missing `world_volume_ref`
    - unknown `world_volume_ref`
    - missing placement `volume_ref`
    - unknown placement `volume_ref` (LV/assembly not found)
    - world volume incorrectly referenced as a child placement
  - Added regression tests in `tests/test_preflight.py` to lock behavior.
  - Why: these are simulation-blocking topology problems that should fail fast in deterministic preflight instead of surfacing later during run/export.

## Next Candidates

1. **Response-shape parity checks between route and AI compare surfaces (success + failure)**
   - Add table-driven tests that compare key payload fields (`selection`, `ordering_metadata`, `version_sources`, and error envelopes) between HTTP routes and `dispatch_ai_tool` wrappers for the same scenarios.
   - Impact: medium (prevents contract drift between human/API and AI tool entry points).

2. **Expand negative-path metadata checks across the remaining compare selectors**
   - Extend the new error-envelope contract assertions to additional compare endpoints/wrappers (simulation-run selectors, snapshot selectors, alias-missing paths) to complete matrix coverage.
   - Impact: medium (broadens deterministic failure contracts across the full compare surface).
