# AI Backend Adapter Contract (Spike A Checkpoint 6)

Contract version: `2026-03-19.local-capability-overrides`

This document defines the normalized adapter contract AIRPET uses for AI backends.

## 1) Goal

Provide one deterministic contract across:
- current remote backend (`gemini_remote`)
- implemented local text-first backend (`llama_cpp`)
- implemented local text-first backend (`lm_studio`)

So routing/fallback logic can stay consistent across provider-specific SDK/API differences.

## 2) Normalized capability flags

Every backend adapter reports:

- `supports_tools` (bool)
- `supports_json_mode` (bool)
- `supports_vision` (bool)
- `supports_streaming` (bool)
- `max_context_tokens` (int|null)

These are hard routing constraints when required by a workflow.

## 3) Adapter spec fields

Each backend has a declarative `AdapterSpec`:

- `backend_id` (stable id used by selection)
- `provider_family` (gemini / llama.cpp / lm_studio)
- `adapter_kind` (`remote` or `local`)
- `priority` (lower = preferred when falling back)
- `enabled` (whether backend is currently routable)
- `implementation_status` (`implemented` or `planned`)
- `capabilities` (flags above)

## 4) Selection invariants

Given requirements + optional preferred backend:

1. Try preferred backend first (if provided).
2. Then try remaining backends ordered by `(priority, backend_id)`.
3. Reject backends that are disabled or missing required capabilities.
4. If `allow_fallback=false` and preferred backend fails, stop and return an error.
5. Selection is deterministic and records all attempted backends + missing capabilities.
6. Runtime config can deterministically override backend enablement plus capability flags (`supports_tools`, `supports_json_mode`, `supports_vision`, `supports_streaming`) and context-window limits.

Override keys can be provided either as top-level backend config fields or inside a nested `capabilities` object; top-level fields take precedence when both are present.

## 5) Text-first local adapter paths

Checkpoint 5 includes implemented text-first local adapter scaffolds **and runtime invocation wiring** for both llama.cpp and LM Studio:

- normalized request envelope (`TextGenerationRequest` + `TextMessage`)
- OpenAI-compatible payload mapping (`/v1/chat/completions`)
- deterministic runtime config surfaces:
  - `LlamaCppAdapterConfig`
  - `LMStudioAdapterConfig`
  - shared knobs: `base_url`, `endpoint_path`, `model`, `timeout_seconds`, `max_retries`, `retry_backoff_seconds`, TLS verify, custom headers
- deterministic retry behavior (fixed retry count + fixed backoff)
- normalized response envelope (`TextGenerationResponse`)
- normalized invocation dispatcher (`invoke_text_request_for_backend`) to route runtime requests by resolved backend id

These paths are intended for text-first/JSON-first workflows, with native tool-call loop support enabled for `llama_cpp`; `lm_studio` can opt into tool-requiring selection flows via runtime capability override when the operator confirms model-side tool support.

## 6) `/api/ai/chat` runtime integration notes

When a `backend_selector` payload is provided, `/api/ai/chat` now:

- resolves deterministic backend selection via the adapter contract
- routes local text-first selections (`llama_cpp`, `lm_studio`) through adapter invocation wiring
- preserves deterministic diagnostics in `backend_selection`, including resolved backend, fallback usage, tried list, and execution mode
- preserves backwards-compatible legacy paths:
  - `gemini_remote` → Gemini SDK path
  - no selector (or non-selector local model choice) → existing Ollama path

### 6.1) Session runtime profile defaults (local backends)

To reduce repeated local backend wiring in per-request payloads, AIRPET supports a
session-scoped local runtime profile at:

- `GET|POST|DELETE /api/ai/backends/runtime_config`

Runtime profile API contract:

- `GET /api/ai/backends/runtime_config`
  - returns `{ success: true, runtime_config: <object> }`
  - returns `{}` when no profile is saved in the current session.
- `POST /api/ai/backends/runtime_config`
  - request body must include `runtime_config`.
  - accepted values:
    - object → saved as the current session profile
    - `null` → clears saved profile (same effect as `DELETE`)
  - validation failures:
    - missing key: `Missing required field: runtime_config.` (400)
    - non-object: `runtime_config must be a JSON object.` (400)
- `DELETE /api/ai/backends/runtime_config`
  - clears the session profile and returns `{ success: true, runtime_config: {} }`.

Preferred payload shape:

```json
{
  "runtime_config": {
    "backends": {
      "llama_cpp": {
        "enabled": true,
        "base_url": "http://127.0.0.1:8080",
        "model": "Meta-Llama-3.1-8B-Instruct",
        "timeout_seconds": 30,
        "max_retries": 1,
        "retry_backoff_seconds": 0.5,
        "verify_tls": false,
        "headers": {
          "Authorization": "Bearer local-token"
        }
      },
      "lm_studio": {
        "enabled": true,
        "base_url": "http://127.0.0.1:1234",
        "model": "qwen2.5-7b-instruct"
      }
    }
  }
}
```

Notes:

- Runtime profile storage is session-scoped (not global, not persisted across unrelated sessions).
- Diagnostics/chat paths also accept request-level `runtime_config` payloads.
- Effective runtime config is resolved by deterministic deep merge:

  1. session runtime profile defaults
  2. request `runtime_config` overrides (request keys win)

This preserves deterministic per-request override control while making stable endpoint/auth/
timeout defaults reusable across:

- `/api/ai/backends/diagnostics`
- `/ai_health_check`
- `/api/ai/chat`
- `/api/ai/chat/stream`

### 6.2) Runtime-profile diagnostics metadata contract

`GET|POST /api/ai/backends/diagnostics` now emits runtime-profile provenance in two places:

1. top-level `runtime_profile` summary
2. per-backend `diagnostics[].runtime_profile`

Top-level summary fields:

- `source`: one of
  - `built_in_defaults`
  - `session_profile`
  - `request_overrides`
  - `session_profile_plus_request_overrides`
- `session_profile_active` (bool)
- `request_overrides_active` (bool)
- `merge_precedence`: `request_overrides_win_over_session_profile`
- `supported_sources`: deterministic enum list above

Per-backend usage fields:

- `source` (same enum as above)
- `uses_session_profile` (bool)
- `uses_request_overrides` (bool)
- `label` (operator-facing short text)
- `message` (operator-facing precedence context)

Representative payloads:

- built-in defaults only:
  - `examples/ai_backends/backend_diagnostics_runtime_profile_built_in_defaults.json`
- session profile active (no request overrides):
  - `examples/ai_backends/backend_diagnostics_runtime_profile_session_profile.json`
- session profile + request override merge:
  - `examples/ai_backends/backend_diagnostics_runtime_profile_session_plus_request_overrides.json`

### 6.3) Operator flow (API + UI touchpoints)

API-first workflow:

1. Save defaults once with `POST /api/ai/backends/runtime_config`.
2. Verify source/precedence with `GET /api/ai/backends/diagnostics` (`runtime_profile` fields).
3. Run chat with optional request-level `backend_selector.runtime_config` for one-off overrides.
4. Clear defaults with `DELETE /api/ai/backends/runtime_config` when done.

UI workflow (AI panel):

- Open **"Local backends ⚙"**.
- Edit/save session runtime profile defaults for `llama_cpp` / `lm_studio`.
- Use the runtime-profile status chip and diagnostics tooltips to confirm whether AIRPET is using:
  - built-in defaults
  - saved session profile
  - request overrides
  - saved profile + request overrides

This keeps local-backend operations deterministic while still allowing one-off request-specific overrides.

## 7) Current matrix

See `docs/AI_BACKEND_CAPABILITY_MATRIX.json`.

Current status at Checkpoint 5:
- `gemini_remote`: enabled + implemented
- `llama_cpp`: implemented (disabled by default until runtime-enabled)
- `lm_studio`: implemented (disabled by default until runtime-enabled)

## 8) Local-backend readiness diagnostics (Checkpoint 3 follow-on)

To reduce ambiguity for local text-first paths, AIRPET now emits machine-readable readiness diagnostics in three places:

- `GET|POST /api/ai/backends/diagnostics`
- `/api/ai/chat` error payloads under `backend_diagnostics`
- `/api/ai/chat/stream` SSE `type=error` events under `backend_diagnostics`

### Readiness statuses

Local backends are classified into a deterministic status set:

- `healthy`
- `timeout`
- `unreachable`
- `misconfigured`

Each diagnostic entry includes:

- `backend_id`
- `status`
- `readiness_code`
- `ready` (boolean)
- `models_endpoint` (`<base_url>/v1/models` probe target)
- `http_status` (when available)
- `models` / `model_count` (when probe succeeds)
- `runtime_profile` source metadata (`source`, `uses_session_profile`, `uses_request_overrides`)

For local-selector chat failures (`/api/ai/chat` and `/api/ai/chat/stream`), `backend_diagnostics.runtime_profile` and `backend_diagnostics.readiness.runtime_profile` are aligned and reflect the same merge provenance:

1. saved session runtime profile defaults
2. request-level `backend_selector.runtime_config` overrides (request keys win)

### `/api/ai/chat` failure-stage distinction

When local-selector chat paths fail, diagnostics now distinguish failure stages:

- `selector_validation`: malformed selector input (for example invalid `llama_cpp::<model_name>` format)
- `selector_requirements`: backend selection could not satisfy declared requirements
- `backend_runtime`: backend was selected, then invocation failed at runtime

This allows UI/workflow logic to separate user-input fixes from backend availability/remediation steps.

### `/api/ai/chat` contradiction + remediation payloads

`backend_diagnostics` now includes deterministic contradiction/remediation structures in addition to stage/readiness fields.

Core fields:

- `effective_capability_overrides`: normalized local capability flags (`supports_tools`, `supports_json_mode`, `supports_vision`, `supports_streaming`)
- `selector_requirements`: normalized selector requirements when provided
- `contradictions[]`: machine-readable contradiction records
  - `code`
  - `contradiction_class`
  - `summary`
  - `details`
- `remediation`:
  - `summary`
  - `action_codes`
  - `actions`
  - `primary_contradiction_class`
  - `contradiction_classes`
  - `contradiction_codes`

This is intended to let UI/automation logic branch on deterministic contradiction classes and remediation codes instead of parsing free-form exceptions.

### Contradiction classes (checkpoint 3 enriched contract)

- `selector_contract_mismatch`
  - code: `selector_requirement_capability_mismatch`
  - meaning: selector-required capabilities conflict with effective runtime capability overrides.

- `runtime_backend_mismatch`
  - code: `runtime_failure_despite_healthy_readiness`
  - meaning: runtime invocation failed while readiness probes still classify the backend as healthy.

## 9) Local-backend remediation playbook (Checkpoint 3/3)

When `/api/ai/chat` returns `backend_diagnostics.failure_stage`, use this default remediation path:

- `selector_validation`
  - expected issue: malformed local selector
  - primary actions:
    - `use_backend_model_selector_format`
    - `select_nonempty_local_model_name`

- `selector_requirements` + contradiction class `selector_contract_mismatch`
  - expected issue: selector requirements conflict with effective capability overrides
  - primary actions:
    - `align_selector_requirements_with_effective_capabilities`
    - `update_runtime_capability_overrides_for_selected_backend`
    - `allow_fallback_or_choose_capability_compatible_backend`

- `selector_requirements` with no contradiction classes
  - expected issue: requirement mismatch not caused by capability override contradiction (for example context-window constraints)
  - primary actions:
    - `review_backend_requirements`
    - `allow_backend_fallback`
    - `switch_backend_for_missing_capabilities`

- `backend_runtime` + contradiction class `runtime_backend_mismatch`
  - expected issue: runtime/backend behavior drift relative to readiness probe
  - primary actions:
    - `capture_runtime_backend_request_context`
    - `inspect_backend_runtime_logs`
    - `reprobe_backend_after_runtime_failure`

- `backend_runtime` + readiness `timeout`
  - primary actions:
    - `increase_backend_timeout`
    - `retry_after_backend_idle`
    - `verify_local_host_resources`

- `backend_runtime` + readiness `unreachable`
  - primary actions:
    - `start_local_backend_service`
    - `verify_backend_base_url_and_port`
    - `verify_models_endpoint_reachable`

- `backend_runtime` + readiness `misconfigured`
  - primary actions:
    - `fix_backend_configuration`
    - `set_valid_local_model_name`
    - `validate_openai_compatible_models_payload`

Representative examples are available in:

- `examples/ai_backends/chat_error_selector_validation.json`
- `examples/ai_backends/chat_error_selector_requirements.json`
- `examples/ai_backends/chat_error_backend_runtime_unreachable.json`
- `examples/ai_backends/chat_error_backend_runtime_mismatch_healthy_readiness.json`
