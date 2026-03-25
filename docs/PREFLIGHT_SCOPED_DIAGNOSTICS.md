# Scoped Preflight Drift Diagnostics (`check_scope` / `run_preflight_scope`)

This note defines the deterministic semantics for scoped preflight drift diagnostics returned by:

- Route: `POST /api/preflight/check_scope`
- AI wrapper: `run_preflight_scope`

Both surfaces return identical payload structure for:

- `summary_delta`
- `issue_family_correlations`

## `summary_delta` semantics

`summary_delta` partitions full-geometry issue totals into scoped and outside-scope buckets:

- `summary_delta.scope`: counts (`errors`, `warnings`, `infos`, `issue_count`) from the scoped report.
- `summary_delta.outside_scope`: `full_summary - scoped_summary` per stat key, clamped at `>= 0`.

## `issue_family_correlations` semantics

`issue_family_correlations` is derived from preflight `summary.counts_by_code` in both full and scoped reports.

### Top-level buckets

- `scope`: issue-code counts attributable to the scoped report.
- `outside_scope`: issue-code counts attributable to the outside-scope remainder (`full - scope`, clamped at `>= 0`).

Each bucket includes:

- `issue_count`: sum of its `counts_by_code` values.
- `issue_codes`: sorted issue-code list.
- `counts_by_code`: deterministic issue-code → count mapping.

### Family-class lists

- `scope_only_issue_codes`: sorted codes where `scope_count > 0` and `outside_scope_count == 0`.
- `outside_scope_only_issue_codes`: sorted codes where `outside_scope_count > 0` and `scope_count == 0`.
- `shared_issue_codes`: sorted codes where both counts are non-zero.

### `entries` list

`entries` is deterministically ordered by `issue_code` (ascending lexical sort over the union of full/scoped code sets).

Each entry includes:

- `issue_code`
- `scope_count`
- `outside_scope_count`
- `correlation`:
  - `scope`: code appears only in scoped diagnostics
  - `outside_scope`: code appears only outside scope
  - `shared`: code appears in both scoped and outside-scope diagnostics

## Scoped selector normalization + validation-failure semantics

Both scoped surfaces use the same selector normalization contract (`_normalize_preflight_scope_input(...)`).

### Canonical + alias precedence

- Canonical nested keys have strict precedence:
  - scope type: `scope.type` > `scope.scope_type` > `scope.scopeType` > top-level `scope_type` > top-level `scopeType`
  - scope name: `scope.name` > `scope.scope_name` > `scope.scopeName` > top-level `scope_name` > top-level `scopeName`
- If a higher-precedence key is present, lower-precedence aliases are not consulted.

### Canonical-null / malformed alias behavior

- Canonical keys present-but-null/blank are treated as authoritative malformed input and do **not** fall back to aliases.
- A malformed earlier alias (for example `scope_type: "volume_group"`) blocks fallback to later aliases (for example `scopeType: "logical_volume"`).
- Unsupported nested alias keys such as `scope.scope_kind` / `scope.scope_label` are ignored and do not satisfy required selector fields.

### Validation-failure envelope contract

For scoped selector validation failures, both route and AI wrapper return deterministic 400 payloads with only:

- `success` (always `false`)
- `error` (string)

Success-only scoped fields are excluded from failure envelopes:

- `scope`
- `preflight_report`
- `scoped_preflight_report`
- `summary_delta`
- `issue_family_correlations`
- `preflight_summary`

## Representative examples

- Scoped drift/correlation success payload:
  - `examples/preflight/scoped_preflight_drift_issue_family_correlations.json`
- Scoped selector malformed-input parity matrix (route ↔ AI, metadata-clean 400 envelopes):
  - `examples/preflight/scoped_preflight_selector_validation_error_matrix.json`
- End-to-end route↔AI scoped workflow replay artifact:
  - `examples/preflight/scoped_preflight_route_ai_workflow_replay.json`

The malformed-input matrix includes canonical-null precedence and malformed-alias-precedence cases to document deterministic route/AI failure parity.

## Route↔AI scoped workflow replay (compact reproducibility flow)

Use `examples/preflight/scoped_preflight_route_ai_workflow_replay.json` when you need one compact artifact that captures:

- selector input (route + AI wrapper forms)
- expected scoped-vs-outside summary deltas
- expected issue-family correlation partitioning
- route↔AI payload-identical success contract

Replay recipe:

1. Seed a known scoped-drift fixture (same shape as `_seed_scoped_preflight_drift_replica_overlap_fixture(...)`).
2. Run route request (`POST /api/preflight/check_scope`) with the artifact `workflow.route_payload`.
3. Run AI wrapper (`run_preflight_scope`) with `workflow.ai_args`.
4. Verify:
   - HTTP route status is `200`
   - route and AI payloads are identical
   - `summary_delta`, scoped issue-code set, and `issue_family_correlations` match the artifact `expected_response_excerpt`.

Executable harness (preferred for CI/local triage):

```bash
source /Users/marth/miniconda/etc/profile.d/conda.sh && conda activate airpet && python scripts/run_scoped_preflight_replay.py --artifact examples/preflight/scoped_preflight_route_ai_workflow_replay.json
```

The harness emits a compact PASS/FAIL report and a bounded unified diff when any contract field drifts.

Debugging guidance:

- If scoped-vs-global divergence looks suspicious, check `summary_delta.outside_scope` against `full.summary - scoped.summary` first.
- If route↔AI outputs diverge, inspect scoped selector normalization precedence (`_normalize_preflight_scope_input(...)`) before checking downstream preflight logic.
