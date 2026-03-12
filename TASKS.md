# AIRPET Task Tracker

## In Progress

- None.

## Recently Completed

- **Geant4-oriented preflight confidence: topology/reference issue corpus signatures locked for deterministic baselines** (2026-03-12)
  - Added reusable corpus fixture seed helpers in `tests/test_preflight.py` for high-impact preflight failure families:
    - missing/unknown world reference fixtures
    - missing procedural-definition fixture
    - stale/invalid replica fixture (reference + bounds)
    - invalid division-axis/partition fixture
    - recursive LV cycle fixture
  - Added `_sorted_preflight_issue_signatures(...)` helper to normalize full issue-signature assertions (severity/code/message/object refs/hint/metadata) with deterministic ordering.
  - Added `test_preflight_topology_reference_issue_corpus_signatures_are_deterministic` with a table-driven corpus matrix that locks, per fixture:
    - `summary.counts_by_code`
    - `summary.issue_count`
    - exact `summary.issue_fingerprint`
    - full sorted issue-signature payloads
  - Added replay checks on fresh project-manager instances for each corpus case to ensure cross-run determinism (not just same-instance stability).
  - Why: establishes a reproducible preflight diagnostics baseline for topology/reference failure modes most likely to affect Geant4 geometry reliability and deterministic debugging workflows.

- **Run-linked list stale-version metadata parity (route + AI) and explicit `has_version_json` diagnostics** (2026-03-12)
  - Extended `list_manual_saved_versions_for_simulation_run(...)` in `app.py` to include `has_version_json` for each returned match, aligning list output with existing version-source diagnostics used elsewhere in preflight selectors.
  - Added regression test `test_list_manual_saved_versions_for_simulation_run_preserves_stale_version_json_metadata` in `tests/test_preflight.py` to lock behavior when a run-matching manual version directory exists but `version.json` has been deleted:
    - stale entries remain listed in deterministic order
    - `has_version_json == False`
    - `version_json_mtime_utc == None`
    - source-path check metadata remains present
  - Added route↔AI parity regression test `test_preflight_list_manual_saved_versions_for_simulation_run_route_and_ai_wrappers_share_stale_version_metadata_payloads` in `tests/test_ai_api.py` to lock identical stale-metadata success payloads across HTTP and AI tool surfaces.
  - Why: improves reproducibility/debuggability for partially deleted version artifacts while preserving deterministic selector behavior and cross-surface contract parity.

- **Snapshot/explicit compare route↔AI parity matrix expansion (success + stale-id/not-enough failure contracts)** (2026-03-12)
  - Added snapshot/explicit parity fixture helpers in `tests/test_ai_api.py`:
    - `_seed_preflight_snapshot_route_ai_parity_fixture(...)`
    - `_seed_preflight_snapshot_insufficient_versions_fixture(...)`
  - Added `test_preflight_compare_snapshot_and_explicit_routes_and_ai_wrappers_share_success_payloads` with table-driven route-vs-AI success parity assertions for remaining snapshot/explicit compare surfaces:
    - `POST /api/preflight/compare_autosave_vs_saved_version` ↔ `compare_autosave_preflight_vs_saved_version`
    - `POST /api/preflight/compare_autosave_vs_snapshot_version` ↔ `compare_autosave_preflight_vs_snapshot_version`
    - `POST /api/preflight/compare_autosave_vs_latest_snapshot` ↔ `compare_autosave_preflight_vs_latest_snapshot`
    - `POST /api/preflight/compare_autosave_vs_previous_snapshot` ↔ `compare_autosave_preflight_vs_previous_snapshot`
    - `POST /api/preflight/compare_snapshot_versions` ↔ `compare_autosave_snapshot_preflight_versions`
    - `POST /api/preflight/compare_latest_snapshot_versions` ↔ `compare_latest_autosave_snapshot_preflight_versions`
  - Added `test_preflight_snapshot_selector_routes_and_ai_wrappers_share_stale_id_404_error_envelopes` to lock status-aware 404 parity for stale snapshot ids on explicit selector paths.
  - Added `test_preflight_snapshot_selector_routes_and_ai_wrappers_share_not_enough_versions_400_error_envelopes` to lock status-aware 400 parity for snapshot selectors that require at least two saved snapshots.
  - Why: closes the remaining snapshot/explicit route-vs-AI compare parity gap so deterministic clients and AI automation receive equivalent contracts on both success and key failure modes.

- **Run/manual selector stale-id 404 envelope parity coverage (route + AI wrappers)** (2026-03-12)
  - Added `_seed_preflight_run_selector_stale_version_fixture(...)` in `tests/test_ai_api.py` to deterministically create run-linked selector fixtures where a selected manual version directory still exists but its `version.json` has been removed (stale-id scenario).
  - Added `test_preflight_run_selector_routes_and_ai_wrappers_share_stale_id_404_error_envelopes` with table-driven route-vs-AI parity assertions for stale selected-version lookups across run/manual selector surfaces:
    - `POST /api/preflight/compare_autosave_vs_manual_saved_for_simulation_run` ↔ `compare_autosave_preflight_vs_manual_saved_for_simulation_run`
    - `POST /api/preflight/compare_autosave_vs_manual_saved_for_simulation_run_index` ↔ `compare_autosave_preflight_vs_manual_saved_for_simulation_run_index`
    - `POST /api/preflight/compare_manual_saved_versions_for_simulation_run_indices` ↔ `compare_manual_preflight_versions_for_simulation_run_indices`
  - Locked status-aware 404 parity and metadata-clean failure envelopes (`success/error` only) when selector expansion succeeds but version-file resolution fails.
  - Why: closes a deterministic stale-id reliability gap on run-linked/manual-index compare selectors used by both HTTP clients and AI automation.

- **Route/AI parity checks for preflight list/discovery success payloads** (2026-03-12)
  - Added `test_preflight_list_routes_and_ai_wrappers_share_success_payloads` in `tests/test_ai_api.py`.
  - Added table-driven route-vs-AI success parity assertions for:
    - `POST /api/preflight/list_versions` ↔ `list_preflight_versions`
    - `POST /api/preflight/list_manual_saved_versions_for_simulation_run` ↔ `list_manual_saved_versions_for_simulation_run`
  - Locked equality with mixed alias usage on both route and AI sides (`project`/`project_name`, `run_id`/`job_id`, `count`/`max_versions`) so normalization paths remain contract-consistent.
  - Added deterministic metadata assertions for ordering/source fields (`ordering_basis`, `manual_saved_ordering_basis`, `timestamp_source`, source-path checks, run-linked index metadata).
  - Why: guards deterministic selector/discovery behavior across HTTP and AI workflows before compare selection, improving reproducibility and automation reliability.

- **Route/AI preflight compare parity matrix coverage (table-driven success + failure contracts)** (2026-03-12)
  - Added shared route/fixture helpers in `tests/test_ai_api.py`:
    - `_call_preflight_route_with_pm(...)`
    - `_seed_preflight_compare_route_ai_parity_fixture(...)`
  - Added table-driven success parity regression test to lock full payload equivalence between HTTP routes and `dispatch_ai_tool` wrappers for representative compare selectors:
    - `POST /api/preflight/compare_latest_versions` ↔ `compare_latest_preflight_versions`
    - `POST /api/preflight/compare_autosave_vs_manual_saved_for_simulation_run_index` ↔ `compare_autosave_preflight_vs_manual_saved_for_simulation_run_index`
    - `POST /api/preflight/compare_manual_saved_versions_for_simulation_run_indices` ↔ `compare_manual_preflight_versions_for_simulation_run_indices`
  - Added table-driven failure parity regression test to lock status-aware error-envelope equivalence (metadata-clean `success/error` only) for representative 400/404 compare failures:
    - unknown selected saved version (404)
    - out-of-range run-linked manual index (400)
    - identical run-linked baseline/candidate indices (400)
  - Why: prevents drift between HTTP and AI compare surfaces so deterministic client branching and AI automation get the same response contract for both success and failure paths.

- **Negative-path envelope consistency for preflight list/discovery selectors (route + AI wrappers)** (2026-03-11)
  - Added shared list-failure envelope assertion helpers to lock clean `success/error` contracts:
    - `tests/test_preflight.py`: `_assert_preflight_list_route_error_payload_excludes_success_metadata(...)`
    - `tests/test_ai_api.py`: `_assert_preflight_list_ai_error_payload_excludes_success_metadata(...)`
  - Added/strengthened route-level failure-contract coverage for discovery/list selectors:
    - `POST /api/preflight/list_versions` (invalid negative `limit`)
    - `POST /api/preflight/list_versions` (missing `project_name`)
    - `POST /api/preflight/list_manual_saved_versions_for_simulation_run` (invalid negative `limit`)
    - `POST /api/preflight/list_manual_saved_versions_for_simulation_run` (missing `simulation_run_id` aliases)
  - Added/strengthened AI-wrapper failure-contract coverage for:
    - `list_manual_saved_versions_for_simulation_run` (invalid `limit`)
    - `list_manual_saved_versions_for_simulation_run` (missing `simulation_run_id`)
    - `list_preflight_versions` (invalid `limit`)
    - `list_preflight_versions` (missing `project_name`)
  - Why: extends deterministic, metadata-clean error-envelope guarantees from compare surfaces to preflight discovery/list selectors that clients and AI agents use before choosing compare targets.

- **Compare-failure 404 envelope matrix for explicit selectors (route + AI wrappers)** (2026-03-11)
  - Added deterministic 404 regression coverage for explicit compare selector paths so stale user-supplied ids keep clean failure envelopes (no success-only compare metadata):
    - Route: `POST /api/preflight/compare_autosave_vs_saved_version` with unknown `saved_version_id`
    - Route: `POST /api/preflight/compare_autosave_vs_snapshot_version` with unknown snapshot id
    - Route: `POST /api/preflight/compare_snapshot_versions` with unknown snapshot candidate id
    - AI wrapper: `compare_autosave_preflight_vs_saved_version` with unknown `saved_version_id`
    - AI wrapper: `compare_autosave_preflight_vs_snapshot_version` with unknown snapshot id
    - AI wrapper: `compare_autosave_snapshot_preflight_versions` with unknown snapshot candidate id
  - Reused existing compare error-envelope assertion helpers to lock payload contract (`success/error` only, excluding `comparison`, `selection`, `ordering_metadata`, `version_sources`, and reports) on all new 404 paths.
  - Why: strengthens deterministic client branching for stale-id failures across explicit selector surfaces used by both HTTP clients and AI tooling.

- **Run/manual compare-selector failure-envelope metadata contract coverage (route + AI wrappers)** (2026-03-11)
  - Extended regression assertions so remaining run/manual compare failure paths explicitly keep `success/error` envelopes while excluding success-only compare metadata (`comparison`, `selection`, `ordering_metadata`, `version_sources`, version ids/reports).
  - Added/strengthened route-level negative-path contract assertions for:
    - `POST /api/preflight/compare_latest_versions` (fewer than two saved versions)
    - `POST /api/preflight/compare_autosave_vs_latest_saved` (missing autosave)
    - `POST /api/preflight/compare_autosave_vs_previous_manual_saved` (no non-snapshot manual baseline)
    - `POST /api/preflight/compare_autosave_vs_manual_saved_for_simulation_run` (missing matching run/manual baseline)
    - `POST /api/preflight/compare_autosave_vs_manual_saved_for_simulation_run_index` (out-of-range index)
    - `POST /api/preflight/compare_manual_saved_versions_for_simulation_run_indices` (identical baseline/candidate indices)
    - required-field failures for missing `simulation_run_id` on run-linked compare routes.
  - Added/strengthened AI-wrapper negative-path contract assertions for:
    - `compare_latest_preflight_versions` (fewer than two saved versions)
    - `compare_autosave_preflight_vs_latest_saved` (missing autosave)
    - `compare_autosave_preflight_vs_previous_manual_saved` (no non-snapshot manual baseline)
    - `compare_autosave_preflight_vs_manual_saved_for_simulation_run` (missing matching run/manual baseline)
    - `compare_autosave_preflight_vs_manual_saved_for_simulation_run_index` (out-of-range index)
    - `compare_manual_preflight_versions_for_simulation_run_indices` (identical indices)
    - required-argument failures for missing `simulation_run_id` on run-linked compare wrappers.
  - Why: closes the remaining medium-impact error-envelope contract gaps across run/manual compare selectors used by deterministic debugging and AI automation flows.

- **Snapshot/selected-compare failure-envelope metadata contract coverage (route + AI wrappers)** (2026-03-11)
  - Extended regression assertions so representative snapshot/selected compare failures explicitly exclude success-only compare metadata fields (`comparison`, `selection`, `ordering_metadata`, `version_sources`, version ids/reports) while preserving `success/error` envelopes.
  - Route-level negative-path contract assertions now cover:
    - `POST /api/preflight/compare_autosave_vs_saved_version` (missing `saved_version_id`)
    - `POST /api/preflight/compare_autosave_vs_snapshot_version` (missing snapshot id)
    - `POST /api/preflight/compare_autosave_vs_latest_snapshot` (no snapshot versions)
    - `POST /api/preflight/compare_autosave_vs_previous_snapshot` (fewer than two snapshot versions)
    - `POST /api/preflight/compare_snapshot_versions` (missing candidate snapshot id)
    - `POST /api/preflight/compare_latest_snapshot_versions` (fewer than two snapshot versions)
  - AI-wrapper negative-path contract assertions now cover:
    - `compare_autosave_preflight_vs_saved_version` (missing `saved_version_id`)
    - `compare_autosave_preflight_vs_snapshot_version` (missing snapshot id + non-snapshot id rejection)
    - `compare_autosave_preflight_vs_latest_snapshot` (no snapshot versions)
    - `compare_autosave_preflight_vs_previous_snapshot` (fewer than two snapshot versions)
    - `compare_latest_autosave_snapshot_preflight_versions` (fewer than two snapshot versions)
  - Why: broadens deterministic failure contracts for snapshot/selected compare selectors used by debugging and automation workflows.

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

1. **Cross-surface parity for compare selector validation errors (400 aliases + required-field diagnostics)**
   - Add route-vs-AI parity checks that intentionally exercise malformed selector aliases (e.g., conflicting/missing snapshot/saved fields) to lock equivalent validation messaging and metadata-clean error envelopes.
   - Impact: medium (hardens deterministic client/agent branching for invalid-input recovery paths).

2. **Run-linked compare selector discovery preflight (`list → compare`) reproducibility fixture**
   - Add end-to-end regression coverage that starts from `list_manual_saved_versions_for_simulation_run` and feeds returned indices/ids into compare selectors, asserting deterministic behavior under mixed valid/stale artifacts.
   - Impact: medium-high (protects real workflow chaining that human + AI tools use in practice).

3. **Topology/reference corpus surfaced through version-compare workflows (`check → save → compare`)**
   - Add regression fixtures that persist selected corpus failures as saved versions and assert compare outputs (`added_issue_codes`, `resolved_issue_codes`, fingerprints) remain deterministic when transitioning between failure families.
   - Impact: high (extends deterministic Geant4-confidence baselines from raw preflight checks into reproducible compare/debug workflows used by humans and AI agents).
