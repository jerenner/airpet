# AI Backend Adapter Contract (Spike A Checkpoint 5)

Contract version: `2026-03-14.checkpoint5`

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
6. Runtime config can deterministically override backend enablement and context-window limits.

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

These paths are intended for text-first/JSON-first workflows where tool calling is not required.

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
