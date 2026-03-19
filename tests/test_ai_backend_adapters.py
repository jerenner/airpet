import json
from pathlib import Path

import pytest

from src.ai_backend_adapters import (
    ADAPTER_CONTRACT_VERSION,
    AdapterCapabilities,
    AdapterSpec,
    BackendRequirements,
    DEFAULT_BACKEND_SPECS,
    LlamaCppAdapterConfig,
    LlamaCppTextAdapter,
    LMStudioAdapterConfig,
    LMStudioTextAdapter,
    TextGenerationRequest,
    TextMessage,
    build_capability_matrix,
    invoke_text_request_for_backend,
    resolve_specs_with_runtime_overrides,
    select_backend,
    select_backend_for_text_request,
)


def test_default_capability_matrix_reports_expected_backends_and_contract_version():
    matrix = build_capability_matrix()

    assert matrix["contract_version"] == ADAPTER_CONTRACT_VERSION

    rows_by_id = {row["backend_id"]: row for row in matrix["backends"]}
    assert {"gemini_remote", "llama_cpp", "lm_studio"}.issubset(rows_by_id.keys())

    assert rows_by_id["gemini_remote"]["enabled"] is True
    assert rows_by_id["gemini_remote"]["capabilities"]["supports_tools"] is True

    assert rows_by_id["llama_cpp"]["enabled"] is False
    assert rows_by_id["llama_cpp"]["implementation_status"] == "implemented"
    assert rows_by_id["llama_cpp"]["capabilities"]["supports_json_mode"] is True
    assert rows_by_id["llama_cpp"]["capabilities"]["supports_tools"] is True

    assert rows_by_id["lm_studio"]["enabled"] is False
    assert rows_by_id["lm_studio"]["implementation_status"] == "implemented"
    assert rows_by_id["lm_studio"]["capabilities"]["supports_streaming"] is True


def test_docs_capability_matrix_matches_default_contract_matrix():
    matrix = build_capability_matrix()
    docs_path = Path(__file__).resolve().parents[1] / "docs" / "AI_BACKEND_CAPABILITY_MATRIX.json"
    docs_matrix = json.loads(docs_path.read_text())

    assert docs_matrix == matrix


def test_runtime_overrides_can_enable_llama_cpp_and_override_context_window():
    runtime_config = {
        "backends": {
            "llama_cpp": {
                "enabled": True,
                "max_context_tokens": 24576,
            }
        }
    }

    resolved = resolve_specs_with_runtime_overrides(runtime_config)
    rows_by_id = {spec.backend_id: spec for spec in resolved}

    assert rows_by_id["llama_cpp"].enabled is True
    assert rows_by_id["llama_cpp"].capabilities.max_context_tokens == 24576


def test_runtime_overrides_can_enable_lm_studio_and_override_context_window():
    runtime_config = {
        "backends": {
            "lm_studio": {
                "enabled": True,
                "max_context_tokens": 65536,
            }
        }
    }

    resolved = resolve_specs_with_runtime_overrides(runtime_config)
    rows_by_id = {spec.backend_id: spec for spec in resolved}

    assert rows_by_id["lm_studio"].enabled is True
    assert rows_by_id["lm_studio"].capabilities.max_context_tokens == 65536


def test_runtime_overrides_can_override_backend_capability_flags_from_top_level_fields():
    runtime_config = {
        "backends": {
            "lm_studio": {
                "enabled": True,
                "supports_tools": True,
                "supports_json_mode": "true",
                "supports_streaming": 1,
                "supports_vision": "false",
            }
        }
    }

    resolved = resolve_specs_with_runtime_overrides(runtime_config)
    rows_by_id = {spec.backend_id: spec for spec in resolved}

    assert rows_by_id["lm_studio"].capabilities.supports_tools is True
    assert rows_by_id["lm_studio"].capabilities.supports_json_mode is True
    assert rows_by_id["lm_studio"].capabilities.supports_streaming is True
    assert rows_by_id["lm_studio"].capabilities.supports_vision is False


def test_runtime_overrides_can_override_backend_capability_flags_from_nested_capabilities_block():
    runtime_config = {
        "backends": {
            "llama_cpp": {
                "enabled": True,
                "capabilities": {
                    "supports_tools": False,
                    "max_context_tokens": 4096,
                },
            }
        }
    }

    resolved = resolve_specs_with_runtime_overrides(runtime_config)
    rows_by_id = {spec.backend_id: spec for spec in resolved}

    assert rows_by_id["llama_cpp"].capabilities.supports_tools is False
    assert rows_by_id["llama_cpp"].capabilities.max_context_tokens == 4096


def test_select_backend_prefers_explicit_backend_when_it_satisfies_requirements():
    selection = select_backend(
        requirements=BackendRequirements(require_json_mode=True),
        specs=DEFAULT_BACKEND_SPECS,
        preferred_backend_id="gemini_remote",
        allow_fallback=True,
    )

    assert selection.backend_id == "gemini_remote"
    assert selection.used_fallback is False
    assert selection.tried[0]["backend_id"] == "gemini_remote"
    assert selection.tried[0]["missing_capabilities"] == []


def test_select_backend_routes_to_llama_cpp_for_tool_requests_when_enabled():
    runtime_config = {"backends": {"llama_cpp": {"enabled": True}}}
    request = TextGenerationRequest(
        messages=(TextMessage(role="user", content="hi"),),
        require_tools=True,
        require_json_mode=True,
    )

    selection = select_backend_for_text_request(
        request=request,
        runtime_config=runtime_config,
        preferred_backend_id="llama_cpp",
        allow_fallback=True,
    )

    assert selection.backend_id == "llama_cpp"
    assert selection.used_fallback is False
    assert selection.tried[0]["backend_id"] == "llama_cpp"
    assert selection.tried[0]["missing_capabilities"] == []


def test_select_text_backend_routes_to_llama_cpp_when_enabled_and_capable():
    runtime_config = {
        "backends": {
            "llama_cpp": {
                "enabled": True,
                "max_context_tokens": 24000,
            }
        }
    }
    request = TextGenerationRequest(
        messages=(TextMessage(role="user", content="Return compact JSON only."),),
        require_tools=False,
        require_json_mode=True,
        min_context_tokens=12000,
    )

    selection = select_backend_for_text_request(
        request=request,
        runtime_config=runtime_config,
        preferred_backend_id="llama_cpp",
        allow_fallback=False,
    )

    assert selection.backend_id == "llama_cpp"
    assert selection.used_fallback is False
    assert selection.tried == ({"backend_id": "llama_cpp", "missing_capabilities": []},)


def test_select_text_backend_routes_to_lm_studio_when_enabled_and_capable():
    runtime_config = {
        "backends": {
            "llama_cpp": {
                "enabled": True,
                "max_context_tokens": 12000,
            },
            "lm_studio": {
                "enabled": True,
                "max_context_tokens": 48000,
            },
        }
    }
    request = TextGenerationRequest(
        messages=(TextMessage(role="user", content="Return compact JSON only."),),
        require_tools=False,
        require_json_mode=True,
        min_context_tokens=20000,
    )

    selection = select_backend_for_text_request(
        request=request,
        runtime_config=runtime_config,
        preferred_backend_id="lm_studio",
        allow_fallback=False,
    )

    assert selection.backend_id == "lm_studio"
    assert selection.used_fallback is False
    assert selection.tried == ({"backend_id": "lm_studio", "missing_capabilities": []},)


def test_select_text_backend_routes_to_lm_studio_for_tool_requests_when_tools_capability_override_is_enabled():
    runtime_config = {
        "backends": {
            "lm_studio": {
                "enabled": True,
                "supports_tools": True,
                "max_context_tokens": 48000,
            },
        }
    }
    request = TextGenerationRequest(
        messages=(TextMessage(role="user", content="Call manage_define."),),
        require_tools=True,
        require_json_mode=True,
    )

    selection = select_backend_for_text_request(
        request=request,
        runtime_config=runtime_config,
        preferred_backend_id="lm_studio",
        allow_fallback=False,
    )

    assert selection.backend_id == "lm_studio"
    assert selection.used_fallback is False
    assert selection.tried == ({"backend_id": "lm_studio", "missing_capabilities": []},)


def test_mixed_local_backends_fall_back_to_gemini_for_lm_studio_tool_requests():
    runtime_config = {
        "backends": {
            "llama_cpp": {"enabled": True},
            "lm_studio": {"enabled": True},
        }
    }
    request = TextGenerationRequest(
        messages=(TextMessage(role="user", content="Call a tool."),),
        require_tools=True,
        require_json_mode=True,
    )

    selection = select_backend_for_text_request(
        request=request,
        runtime_config=runtime_config,
        preferred_backend_id="lm_studio",
        allow_fallback=True,
    )

    assert selection.backend_id == "llama_cpp"
    assert selection.used_fallback is True
    assert selection.tried[0]["backend_id"] == "lm_studio"
    assert selection.tried[0]["missing_capabilities"] == ["tools"]
    assert selection.tried[1] == {"backend_id": "llama_cpp", "missing_capabilities": []}


def test_mixed_local_backends_preserve_error_diagnostics_for_lm_studio_when_fallback_disabled():
    runtime_config = {
        "backends": {
            "llama_cpp": {"enabled": True},
            "lm_studio": {"enabled": True},
        }
    }
    request = TextGenerationRequest(
        messages=(TextMessage(role="user", content="Call a tool."),),
        require_tools=True,
        require_json_mode=True,
    )

    with pytest.raises(ValueError, match="No backend satisfies requirements") as exc_info:
        select_backend_for_text_request(
            request=request,
            runtime_config=runtime_config,
            preferred_backend_id="lm_studio",
            allow_fallback=False,
        )

    message = str(exc_info.value)
    assert "preferred=lm_studio" in message
    assert "'backend_id': 'lm_studio'" in message
    assert "'missing_capabilities': ['tools']" in message


def test_select_backend_errors_when_fallback_is_disabled_and_preferred_backend_fails():
    with pytest.raises(ValueError, match="No backend satisfies requirements"):
        select_backend(
            requirements=BackendRequirements(require_tools=True),
            specs=DEFAULT_BACKEND_SPECS,
            preferred_backend_id="llama_cpp",
            allow_fallback=False,
        )


def test_select_backend_enforces_min_context_tokens_in_deterministic_order():
    specs = [
        AdapterSpec(
            backend_id="small_ctx",
            provider_family="test",
            adapter_kind="local",
            priority=10,
            enabled=True,
            implementation_status="implemented",
            capabilities=AdapterCapabilities(
                supports_tools=False,
                supports_json_mode=True,
                supports_vision=False,
                supports_streaming=True,
                max_context_tokens=4096,
            ),
        ),
        AdapterSpec(
            backend_id="large_ctx",
            provider_family="test",
            adapter_kind="local",
            priority=20,
            enabled=True,
            implementation_status="implemented",
            capabilities=AdapterCapabilities(
                supports_tools=False,
                supports_json_mode=True,
                supports_vision=False,
                supports_streaming=True,
                max_context_tokens=32768,
            ),
        ),
    ]

    selection = select_backend(
        requirements=BackendRequirements(require_json_mode=True, min_context_tokens=8000),
        specs=specs,
    )

    assert selection.backend_id == "large_ctx"
    assert selection.tried[0]["backend_id"] == "small_ctx"
    assert selection.tried[0]["missing_capabilities"] == ["context>=8000"]


def test_select_backend_errors_on_unknown_preferred_backend():
    with pytest.raises(ValueError, match="Unknown preferred backend"):
        select_backend(
            requirements=BackendRequirements(),
            specs=DEFAULT_BACKEND_SPECS,
            preferred_backend_id="does_not_exist",
        )


def test_llama_cpp_adapter_builds_openai_chat_payload_for_text_first_json_mode():
    adapter = LlamaCppTextAdapter(
        LlamaCppAdapterConfig(
            base_url="http://localhost:8080",
            model="meta-llama",
            timeout_seconds=11,
            max_retries=0,
            retry_backoff_seconds=0,
        )
    )
    request = TextGenerationRequest(
        messages=(
            TextMessage(role="system", content="You output JSON."),
            TextMessage(role="user", content="Return object with ok=true"),
        ),
        require_json_mode=True,
        max_output_tokens=128,
        temperature=0.1,
    )

    payload = adapter.build_payload(request)

    assert payload["model"] == "meta-llama"
    assert payload["messages"] == [
        {"role": "system", "content": "You output JSON."},
        {"role": "user", "content": "Return object with ok=true"},
    ]
    assert payload["response_format"] == {"type": "json_object"}
    assert payload["max_tokens"] == 128
    assert payload["temperature"] == 0.1


def test_text_message_serializes_tool_fields_for_openai_history():
    msg = TextMessage(
        role="tool",
        content='{"success": true}',
        tool_call_id="call_123",
        name="manage_define",
    )

    assert msg.as_openai_message() == {
        "role": "tool",
        "content": '{"success": true}',
        "tool_call_id": "call_123",
        "name": "manage_define",
    }


def test_llama_cpp_adapter_includes_tool_schema_when_tool_calls_required():
    adapter = LlamaCppTextAdapter(
        LlamaCppAdapterConfig(
            base_url="http://localhost:8080",
            model="meta-llama",
            timeout_seconds=11,
            max_retries=0,
            retry_backoff_seconds=0,
        )
    )
    request = TextGenerationRequest(
        messages=(TextMessage(role="user", content="Use tools."),),
        require_json_mode=True,
        require_tools=True,
        tool_schemas=(
            {
                "type": "function",
                "function": {
                    "name": "manage_define",
                    "description": "Create define",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
        ),
    )

    payload = adapter.build_payload(request)

    assert payload["tools"][0]["function"]["name"] == "manage_define"
    assert payload["tool_choice"] == "auto"
    assert "response_format" not in payload


def test_lm_studio_adapter_builds_openai_chat_payload_for_text_first_json_mode():
    adapter = LMStudioTextAdapter(
        LMStudioAdapterConfig(
            base_url="http://localhost:1234",
            model="qwen-local",
            timeout_seconds=9,
            max_retries=0,
            retry_backoff_seconds=0,
        )
    )
    request = TextGenerationRequest(
        messages=(
            TextMessage(role="system", content="You output JSON."),
            TextMessage(role="user", content="Return object with ok=true"),
        ),
        require_json_mode=True,
        max_output_tokens=256,
        temperature=0.2,
    )

    payload = adapter.build_payload(request)

    assert payload["model"] == "qwen-local"
    assert payload["messages"] == [
        {"role": "system", "content": "You output JSON."},
        {"role": "user", "content": "Return object with ok=true"},
    ]
    assert payload["response_format"] == {"type": "json_object"}
    assert payload["max_tokens"] == 256
    assert payload["temperature"] == 0.2


class _FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


def test_llama_cpp_adapter_retries_then_returns_normalized_response():
    adapter = LlamaCppTextAdapter(
        LlamaCppAdapterConfig(
            base_url="http://localhost:8080",
            model="meta-llama",
            timeout_seconds=2,
            max_retries=1,
            retry_backoff_seconds=0,
        )
    )
    request = TextGenerationRequest(
        messages=(TextMessage(role="user", content="hello"),),
        require_json_mode=False,
    )

    calls = []

    def fake_post(url, json, headers, timeout, verify):
        calls.append({
            "url": url,
            "json": json,
            "headers": headers,
            "timeout": timeout,
            "verify": verify,
        })
        if len(calls) == 1:
            raise RuntimeError("temporary connection drop")
        return _FakeResponse(
            {
                "model": "meta-llama",
                "usage": {"prompt_tokens": 12, "completion_tokens": 3},
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "{\"ok\": true}",
                        }
                    }
                ],
            }
        )

    response = adapter.invoke(request, http_post=fake_post)

    assert len(calls) == 2
    assert response.backend_id == "llama_cpp"
    assert response.model == "meta-llama"
    assert response.text == '{"ok": true}'
    assert response.usage == {"prompt_tokens": 12, "completion_tokens": 3}


def test_llama_cpp_adapter_accepts_tool_only_assistant_messages():
    adapter = LlamaCppTextAdapter(
        LlamaCppAdapterConfig(
            base_url="http://localhost:8080",
            model="meta-llama",
            timeout_seconds=2,
            max_retries=0,
            retry_backoff_seconds=0,
        )
    )
    request = TextGenerationRequest(
        messages=(TextMessage(role="user", content="hello"),),
        require_json_mode=False,
        require_tools=True,
        tool_schemas=(
            {
                "type": "function",
                "function": {
                    "name": "manage_define",
                    "description": "Create define",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
        ),
    )

    def fake_post(url, json, headers, timeout, verify):
        return _FakeResponse(
            {
                "model": "meta-llama",
                "usage": {"prompt_tokens": 12, "completion_tokens": 3},
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "",
                            "tool_calls": [
                                {
                                    "id": "call_1",
                                    "type": "function",
                                    "function": {
                                        "name": "manage_define",
                                        "arguments": "{\"name\":\"x\",\"value\":\"1\"}",
                                    },
                                }
                            ],
                        }
                    }
                ],
            }
        )

    response = adapter.invoke(request, http_post=fake_post)
    assert response.backend_id == "llama_cpp"
    assert response.text == ""
    assert isinstance(response.tool_calls, list)
    assert response.tool_calls[0]["function"]["name"] == "manage_define"


def test_lm_studio_adapter_retries_then_returns_normalized_response():
    adapter = LMStudioTextAdapter(
        LMStudioAdapterConfig(
            base_url="http://localhost:1234",
            model="qwen-local",
            timeout_seconds=2,
            max_retries=1,
            retry_backoff_seconds=0,
        )
    )
    request = TextGenerationRequest(
        messages=(TextMessage(role="user", content="hello"),),
        require_json_mode=False,
    )

    calls = []

    def fake_post(url, json, headers, timeout, verify):
        calls.append(
            {
                "url": url,
                "json": json,
                "headers": headers,
                "timeout": timeout,
                "verify": verify,
            }
        )
        if len(calls) == 1:
            raise RuntimeError("temporary connection drop")
        return _FakeResponse(
            {
                "model": "qwen-local",
                "usage": {"prompt_tokens": 18, "completion_tokens": 6},
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "{\"ok\": true}",
                        }
                    }
                ],
            }
        )

    response = adapter.invoke(request, http_post=fake_post)

    assert len(calls) == 2
    assert response.backend_id == "lm_studio"
    assert response.model == "qwen-local"
    assert response.text == '{"ok": true}'
    assert response.usage == {"prompt_tokens": 18, "completion_tokens": 6}


def test_lm_studio_adapter_accepts_tool_only_assistant_messages():
    adapter = LMStudioTextAdapter(
        LMStudioAdapterConfig(
            base_url="http://localhost:1234",
            model="qwen-local",
            timeout_seconds=2,
            max_retries=0,
            retry_backoff_seconds=0,
        )
    )
    request = TextGenerationRequest(
        messages=(TextMessage(role="user", content="hello"),),
        require_json_mode=False,
        require_tools=True,
        tool_schemas=(
            {
                "type": "function",
                "function": {
                    "name": "manage_define",
                    "description": "Create define",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
        ),
    )

    def fake_post(url, json, headers, timeout, verify):
        return _FakeResponse(
            {
                "model": "qwen-local",
                "usage": {"prompt_tokens": 12, "completion_tokens": 3},
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "",
                            "tool_calls": [
                                {
                                    "id": "call_1",
                                    "type": "function",
                                    "function": {
                                        "name": "manage_define",
                                        "arguments": "{\"name\":\"x\",\"value\":\"1\"}",
                                    },
                                }
                            ],
                        }
                    }
                ],
            }
        )

    response = adapter.invoke(request, http_post=fake_post)
    assert response.backend_id == "lm_studio"
    assert response.text == ""
    assert isinstance(response.tool_calls, list)
    assert response.tool_calls[0]["function"]["name"] == "manage_define"


def test_invoke_text_request_for_backend_dispatches_to_llama_cpp_with_runtime_model_override():
    runtime_config = {
        "backends": {
            "llama_cpp": {
                "enabled": True,
                "base_url": "http://localhost:9001",
                "model": "llama-local-override",
            }
        }
    }
    request = TextGenerationRequest(
        messages=(TextMessage(role="user", content="hello"),),
        require_json_mode=False,
    )

    captured_calls = []

    def fake_post(url, json, headers, timeout, verify):
        captured_calls.append({"url": url, "json": json})
        return _FakeResponse(
            {
                "model": "llama-local-override",
                "usage": {"prompt_tokens": 5, "completion_tokens": 2},
                "choices": [{"message": {"role": "assistant", "content": "ok"}}],
            }
        )

    response = invoke_text_request_for_backend(
        "llama_cpp",
        request,
        runtime_config=runtime_config,
        http_post=fake_post,
    )

    assert captured_calls[0]["url"] == "http://localhost:9001/v1/chat/completions"
    assert captured_calls[0]["json"]["model"] == "llama-local-override"
    assert response.backend_id == "llama_cpp"
    assert response.model == "llama-local-override"
    assert response.text == "ok"


def test_invoke_text_request_for_backend_rejects_unsupported_backend_id():
    request = TextGenerationRequest(
        messages=(TextMessage(role="user", content="hello"),),
        require_json_mode=False,
    )

    with pytest.raises(ValueError, match="Unsupported text-first backend"):
        invoke_text_request_for_backend("gemini_remote", request)
