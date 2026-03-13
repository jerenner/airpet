# AI Backend Adapter Contract (Spike A Checkpoint 3)

Contract version: `2026-03-13.checkpoint3`

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

Checkpoint 3 includes implemented text-first local adapter scaffolds for both llama.cpp and LM Studio:

- normalized request envelope (`TextGenerationRequest` + `TextMessage`)
- OpenAI-compatible payload mapping (`/v1/chat/completions`)
- deterministic runtime config surfaces:
  - `LlamaCppAdapterConfig`
  - `LMStudioAdapterConfig`
  - shared knobs: `base_url`, `endpoint_path`, `model`, `timeout_seconds`, `max_retries`, `retry_backoff_seconds`, TLS verify, custom headers
- deterministic retry behavior (fixed retry count + fixed backoff)
- normalized response envelope (`TextGenerationResponse`)

These paths are intended for text-first/JSON-first workflows where tool calling is not required.

## 6) Current matrix

See `docs/AI_BACKEND_CAPABILITY_MATRIX.json`.

Current status at Checkpoint 3:
- `gemini_remote`: enabled + implemented
- `llama_cpp`: implemented (disabled by default until runtime-enabled)
- `lm_studio`: implemented (disabled by default until runtime-enabled)
