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

## 7) Current matrix

See `docs/AI_BACKEND_CAPABILITY_MATRIX.json`.

Current status at Checkpoint 5:
- `gemini_remote`: enabled + implemented
- `llama_cpp`: implemented (disabled by default until runtime-enabled)
- `lm_studio`: implemented (disabled by default until runtime-enabled)

## 8) Local-backend readiness diagnostics (Checkpoint 3 follow-on)

To reduce ambiguity for local text-first paths, AIRPET now emits machine-readable readiness diagnostics in two places:

- `GET|POST /api/ai/backends/diagnostics`
- `/api/ai/chat` error payloads under `backend_diagnostics`

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

### `/api/ai/chat` failure-stage distinction

When local-selector chat paths fail, diagnostics now distinguish failure stages:

- `selector_validation`: malformed selector input (for example invalid `llama_cpp::<model_name>` format)
- `selector_requirements`: backend selection could not satisfy declared requirements
- `backend_runtime`: backend was selected, then invocation failed at runtime

This allows UI/workflow logic to separate user-input fixes from backend availability/remediation steps.

### `/api/ai/chat` remediation payload

`backend_diagnostics` now also includes a deterministic `remediation` object:

- `summary`: human-readable one-line triage summary
- `action_codes`: stable machine-readable next-step codes
- `actions`: deterministic operator-facing guidance

This is intended to let the UI render stable copy for selector/input errors vs runtime failures without guessing from free-form exception text.

## 9) Local-backend remediation playbook (Checkpoint 2/2)

When `/api/ai/chat` returns `backend_diagnostics.failure_stage`, use this default remediation path:

- `selector_validation`
  - expected issue: malformed local selector
  - primary actions:
    - `use_backend_model_selector_format`
    - `select_nonempty_local_model_name`

- `selector_requirements`
  - expected issue: selected backend cannot satisfy requested capabilities
  - primary actions:
    - `review_backend_requirements`
    - `allow_backend_fallback`
    - `switch_backend_for_missing_capabilities`

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
