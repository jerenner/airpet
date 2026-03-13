# AI Backend Adapter Contract (Spike A Checkpoint 1)

Contract version: `2026-03-13.checkpoint1`

This document defines the normalized adapter contract AIRPET will use for AI backends.

## 1) Goal

Provide one deterministic contract across:
- current remote backend (`gemini_remote`)
- planned local backends (`llama_cpp`, `lm_studio`)

So routing/fallback logic can be consistent regardless of provider-specific SDK quirks.

## 2) Normalized capability flags

Every backend adapter reports:

- `supports_tools` (bool)
- `supports_json_mode` (bool)
- `supports_vision` (bool)
- `supports_streaming` (bool)
- `max_context_tokens` (int|null)

These are treated as hard routing constraints when required by a workflow.

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

## 5) Current matrix

See `docs/AI_BACKEND_CAPABILITY_MATRIX.json`.

Current status at Checkpoint 1:
- `gemini_remote`: enabled + implemented
- `llama_cpp`: planned (text-first adapter is Checkpoint 2)
- `lm_studio`: planned (Checkpoint 3)
