# AIRPET Phase 3 — M1 Validation Checklist

**Branch:** `phase3/smart-cad-classifier-skeleton`  
**Scope:** M1 Smart CAD + Preflight Foundation

## 1) Smart CAD Classifier + Mapping

- [x] Candidate schema includes `source_id`, `classification`, `confidence`, `params`, `fallback_reason`, `selected_mode`.
- [x] Primitive mapping path exists for `box`, `cylinder/tube`, `sphere`.
- [x] Confidence threshold path routes lower-confidence candidates to tessellated fallback.
- [x] Primitive center/orientation local transforms are composed with assembly placement transforms.
- [x] Mixed-mode import preserves deterministic fallback behavior.

### Evidence
- `tests/test_smart_cad_classifier.py`
- `tests/test_cad_parser.py`
- `tests/test_m1_fixture_pack.py::test_smart_import_fixture_pack_summary_contract`

## 2) Import Report UI

- [x] Backend `/import_step_with_options` response includes `step_import_report`.
- [x] Frontend includes Smart Import toggle in STEP modal.
- [x] Post-import report table UI displays:
  - [x] source id
  - [x] classification
  - [x] selected mode
  - [x] confidence
  - [x] fallback reason
- [x] Import summary ratio and counts shown.

### Evidence
- `app.py`
- `src/project_manager.py`
- `static/main.js`
- `static/stepImportEditor.js`
- `templates/index.html`
- `tests/test_step_import_integration.py`

## 3) Preflight QA Foundation

- [x] Preflight checks run through `ProjectManager.run_preflight_checks()`.
- [x] Preflight checks include:
  - [x] material/solid reference validity
  - [x] non-finite / non-positive / tiny dimensions
  - [x] approximate sibling AABB overlap warnings
- [x] `POST /api/preflight/check` endpoint returns full report.
- [x] Simulation run endpoint blocks on preflight errors.
- [x] Simulation UI includes preflight panel and explicit warnings confirmation.

### Evidence
- `tests/test_preflight.py`
- `tests/test_m1_fixture_pack.py::test_preflight_fixture_pack_cases`
- `static/main.js`, `static/uiManager.js`, `templates/index.html`

## 4) Fixture Pack + Integration

- [x] Fixture pack for Smart Import report summary
  - `tests/fixtures/m1/smart_import_report_fixture.json`
- [x] Fixture pack for preflight scenarios
  - `tests/fixtures/m1/preflight_cases.json`
- [x] Integration API test for STEP import report plumbing
  - `tests/test_step_import_integration.py`

## 5) Full Test Pass

- [x] `pytest -q` passes on branch.

---

## M1 Exit Decision

- **Status:** ✅ Ready to merge into `airpet-bot/dev`
- **Carry-over to M2:** hardening edge cases + performance benchmarks + regression thresholds.
