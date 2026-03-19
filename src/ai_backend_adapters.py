from __future__ import annotations

import time
from dataclasses import dataclass, replace
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple
from urllib.parse import urljoin

ADAPTER_CONTRACT_VERSION = "2026-03-19.local-capability-overrides"


@dataclass(frozen=True)
class BackendRequirements:
    """Capability requirements for selecting a backend adapter."""

    require_tools: bool = False
    require_json_mode: bool = False
    require_vision: bool = False
    require_streaming: bool = False
    min_context_tokens: Optional[int] = None


@dataclass(frozen=True)
class AdapterCapabilities:
    """Normalized capability flags exposed by each backend adapter."""

    supports_tools: bool
    supports_json_mode: bool
    supports_vision: bool
    supports_streaming: bool
    max_context_tokens: Optional[int] = None

    def missing_for(self, requirements: BackendRequirements) -> List[str]:
        missing: List[str] = []
        if requirements.require_tools and not self.supports_tools:
            missing.append("tools")
        if requirements.require_json_mode and not self.supports_json_mode:
            missing.append("json_mode")
        if requirements.require_vision and not self.supports_vision:
            missing.append("vision")
        if requirements.require_streaming and not self.supports_streaming:
            missing.append("streaming")
        if requirements.min_context_tokens is not None:
            if self.max_context_tokens is None or self.max_context_tokens < requirements.min_context_tokens:
                missing.append(f"context>={requirements.min_context_tokens}")
        return missing

    def as_dict(self) -> Dict[str, Any]:
        return {
            "supports_tools": self.supports_tools,
            "supports_json_mode": self.supports_json_mode,
            "supports_vision": self.supports_vision,
            "supports_streaming": self.supports_streaming,
            "max_context_tokens": self.max_context_tokens,
        }


@dataclass(frozen=True)
class AdapterSpec:
    """Declarative adapter contract for one provider/backend."""

    backend_id: str
    provider_family: str
    adapter_kind: str  # remote | local
    priority: int
    enabled: bool
    implementation_status: str  # implemented | planned
    capabilities: AdapterCapabilities

    def as_matrix_row(self) -> Dict[str, Any]:
        return {
            "backend_id": self.backend_id,
            "provider_family": self.provider_family,
            "adapter_kind": self.adapter_kind,
            "priority": self.priority,
            "enabled": self.enabled,
            "implementation_status": self.implementation_status,
            "capabilities": self.capabilities.as_dict(),
        }


@dataclass(frozen=True)
class AdapterSelection:
    backend_id: str
    spec: AdapterSpec
    used_fallback: bool
    tried: Tuple[Dict[str, Any], ...]


@dataclass(frozen=True)
class TextMessage:
    role: str
    content: str
    tool_calls: Optional[Tuple[Dict[str, Any], ...]] = None
    tool_call_id: Optional[str] = None
    name: Optional[str] = None

    def as_openai_message(self) -> Dict[str, Any]:
        message: Dict[str, Any] = {"role": self.role, "content": self.content}
        if self.tool_calls:
            message["tool_calls"] = [dict(tc) for tc in self.tool_calls]
        if self.tool_call_id:
            message["tool_call_id"] = self.tool_call_id
        if self.name:
            message["name"] = self.name
        return message


@dataclass(frozen=True)
class TextGenerationRequest:
    """Normalized text-generation request for text-first adapter paths."""

    messages: Tuple[TextMessage, ...]
    require_tools: bool = False
    require_json_mode: bool = True
    require_streaming: bool = False
    min_context_tokens: Optional[int] = None
    temperature: Optional[float] = None
    max_output_tokens: Optional[int] = None
    stop: Optional[Tuple[str, ...]] = None
    tool_schemas: Optional[Tuple[Dict[str, Any], ...]] = None
    tool_choice: Optional[Any] = None


@dataclass(frozen=True)
class TextGenerationResponse:
    backend_id: str
    text: str
    raw_response: Dict[str, Any]
    model: Optional[str] = None
    usage: Optional[Dict[str, Any]] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None


@dataclass(frozen=True)
class LlamaCppAdapterConfig:
    base_url: str = "http://127.0.0.1:8080"
    endpoint_path: str = "/v1/chat/completions"
    model: str = "local-model"
    timeout_seconds: float = 45.0
    max_retries: int = 1
    retry_backoff_seconds: float = 0.25
    verify_tls: bool = True
    headers: Tuple[Tuple[str, str], ...] = ()

    @staticmethod
    def from_runtime_config(runtime_config: Optional[Mapping[str, Any]] = None) -> "LlamaCppAdapterConfig":
        cfg = _runtime_backend_config(runtime_config, "llama_cpp")
        headers_obj = cfg.get("headers")
        header_items: Tuple[Tuple[str, str], ...] = ()
        if isinstance(headers_obj, Mapping):
            header_items = tuple((str(k), str(v)) for k, v in headers_obj.items())

        return LlamaCppAdapterConfig(
            base_url=str(cfg.get("base_url", "http://127.0.0.1:8080")),
            endpoint_path=str(cfg.get("endpoint_path", "/v1/chat/completions")),
            model=str(cfg.get("model", "local-model")),
            timeout_seconds=float(cfg.get("timeout_seconds", 45.0)),
            max_retries=max(0, int(cfg.get("max_retries", 1))),
            retry_backoff_seconds=max(0.0, float(cfg.get("retry_backoff_seconds", 0.25))),
            verify_tls=bool(cfg.get("verify_tls", True)),
            headers=header_items,
        )


class LlamaCppTextAdapter:
    """Text-first adapter for llama.cpp OpenAI-compatible chat endpoint."""

    backend_id = "llama_cpp"

    def __init__(self, config: Optional[LlamaCppAdapterConfig] = None):
        self.config = config or LlamaCppAdapterConfig()

    def endpoint_url(self) -> str:
        return urljoin(self.config.base_url.rstrip("/") + "/", self.config.endpoint_path.lstrip("/"))

    def build_payload(self, request: TextGenerationRequest) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "model": self.config.model,
            "messages": [m.as_openai_message() for m in request.messages],
            "stream": request.require_streaming,
        }
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        if request.max_output_tokens is not None:
            payload["max_tokens"] = request.max_output_tokens
        if request.stop:
            payload["stop"] = list(request.stop)

        using_tools = bool(request.require_tools and request.tool_schemas)
        if request.require_json_mode and not using_tools:
            payload["response_format"] = {"type": "json_object"}
        if using_tools:
            payload["tools"] = list(request.tool_schemas)
            payload["tool_choice"] = request.tool_choice or "auto"
        return payload

    def invoke(
        self,
        request: TextGenerationRequest,
        http_post: Optional[Callable[..., Any]] = None,
    ) -> TextGenerationResponse:
        if http_post is None:
            import requests

            http_post = requests.post

        payload = self.build_payload(request)
        url = self.endpoint_url()
        headers = {"Content-Type": "application/json"}
        headers.update(dict(self.config.headers))

        attempts_total = self.config.max_retries + 1
        last_error: Optional[Exception] = None

        for attempt in range(1, attempts_total + 1):
            try:
                response = http_post(
                    url,
                    json=payload,
                    headers=headers,
                    timeout=self.config.timeout_seconds,
                    verify=self.config.verify_tls,
                )
                if hasattr(response, "raise_for_status"):
                    response.raise_for_status()
                body = response.json() if hasattr(response, "json") else {}
                assistant_message = _extract_openai_style_assistant_message(body)
                if not assistant_message:
                    raise ValueError("llama_cpp response did not include an assistant message")

                text = assistant_message.get("content") or ""
                tool_calls = assistant_message.get("tool_calls")
                if not text and not tool_calls:
                    raise ValueError("llama_cpp response did not include text or tool calls")

                return TextGenerationResponse(
                    backend_id=self.backend_id,
                    text=text,
                    raw_response=body,
                    model=body.get("model") if isinstance(body, dict) else None,
                    usage=body.get("usage") if isinstance(body, dict) else None,
                    tool_calls=tool_calls if isinstance(tool_calls, list) else None,
                )
            except Exception as err:
                last_error = err
                if attempt >= attempts_total:
                    break
                if self.config.retry_backoff_seconds > 0:
                    time.sleep(self.config.retry_backoff_seconds)

        raise RuntimeError(
            f"llama_cpp invocation failed after {attempts_total} attempt(s): {last_error}"
        )


@dataclass(frozen=True)
class LMStudioAdapterConfig:
    base_url: str = "http://127.0.0.1:1234"
    endpoint_path: str = "/v1/chat/completions"
    model: str = "local-model"
    timeout_seconds: float = 45.0
    max_retries: int = 1
    retry_backoff_seconds: float = 0.25
    verify_tls: bool = True
    headers: Tuple[Tuple[str, str], ...] = ()

    @staticmethod
    def from_runtime_config(runtime_config: Optional[Mapping[str, Any]] = None) -> "LMStudioAdapterConfig":
        cfg = _runtime_backend_config(runtime_config, "lm_studio")
        headers_obj = cfg.get("headers")
        header_items: Tuple[Tuple[str, str], ...] = ()
        if isinstance(headers_obj, Mapping):
            header_items = tuple((str(k), str(v)) for k, v in headers_obj.items())

        return LMStudioAdapterConfig(
            base_url=str(cfg.get("base_url", "http://127.0.0.1:1234")),
            endpoint_path=str(cfg.get("endpoint_path", "/v1/chat/completions")),
            model=str(cfg.get("model", "local-model")),
            timeout_seconds=float(cfg.get("timeout_seconds", 45.0)),
            max_retries=max(0, int(cfg.get("max_retries", 1))),
            retry_backoff_seconds=max(0.0, float(cfg.get("retry_backoff_seconds", 0.25))),
            verify_tls=bool(cfg.get("verify_tls", True)),
            headers=header_items,
        )


class LMStudioTextAdapter:
    """Text-first adapter for LM Studio OpenAI-compatible chat endpoint."""

    backend_id = "lm_studio"

    def __init__(self, config: Optional[LMStudioAdapterConfig] = None):
        self.config = config or LMStudioAdapterConfig()

    def endpoint_url(self) -> str:
        return urljoin(self.config.base_url.rstrip("/") + "/", self.config.endpoint_path.lstrip("/"))

    def build_payload(self, request: TextGenerationRequest) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "model": self.config.model,
            "messages": [m.as_openai_message() for m in request.messages],
            "stream": request.require_streaming,
        }
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        if request.max_output_tokens is not None:
            payload["max_tokens"] = request.max_output_tokens
        if request.stop:
            payload["stop"] = list(request.stop)

        using_tools = bool(request.require_tools and request.tool_schemas)
        if request.require_json_mode and not using_tools:
            payload["response_format"] = {"type": "json_object"}
        if using_tools:
            payload["tools"] = list(request.tool_schemas)
            payload["tool_choice"] = request.tool_choice or "auto"
        return payload

    def invoke(
        self,
        request: TextGenerationRequest,
        http_post: Optional[Callable[..., Any]] = None,
    ) -> TextGenerationResponse:
        if http_post is None:
            import requests

            http_post = requests.post

        payload = self.build_payload(request)
        url = self.endpoint_url()
        headers = {"Content-Type": "application/json"}
        headers.update(dict(self.config.headers))

        attempts_total = self.config.max_retries + 1
        last_error: Optional[Exception] = None

        for attempt in range(1, attempts_total + 1):
            try:
                response = http_post(
                    url,
                    json=payload,
                    headers=headers,
                    timeout=self.config.timeout_seconds,
                    verify=self.config.verify_tls,
                )
                if hasattr(response, "raise_for_status"):
                    response.raise_for_status()
                body = response.json() if hasattr(response, "json") else {}
                assistant_message = _extract_openai_style_assistant_message(body)
                if not assistant_message:
                    raise ValueError("lm_studio response did not include an assistant message")

                text = assistant_message.get("content") or ""
                tool_calls = assistant_message.get("tool_calls")
                if not text and not tool_calls:
                    raise ValueError("lm_studio response did not include text or tool calls")

                return TextGenerationResponse(
                    backend_id=self.backend_id,
                    text=text,
                    raw_response=body,
                    model=body.get("model") if isinstance(body, dict) else None,
                    usage=body.get("usage") if isinstance(body, dict) else None,
                    tool_calls=tool_calls if isinstance(tool_calls, list) else None,
                )
            except Exception as err:
                last_error = err
                if attempt >= attempts_total:
                    break
                if self.config.retry_backoff_seconds > 0:
                    time.sleep(self.config.retry_backoff_seconds)

        raise RuntimeError(
            f"lm_studio invocation failed after {attempts_total} attempt(s): {last_error}"
        )


DEFAULT_BACKEND_SPECS: Tuple[AdapterSpec, ...] = (
    AdapterSpec(
        backend_id="gemini_remote",
        provider_family="gemini",
        adapter_kind="remote",
        priority=10,
        enabled=True,
        implementation_status="implemented",
        capabilities=AdapterCapabilities(
            supports_tools=True,
            supports_json_mode=True,
            supports_vision=True,
            supports_streaming=True,
            max_context_tokens=1_000_000,
        ),
    ),
    AdapterSpec(
        backend_id="llama_cpp",
        provider_family="llama.cpp",
        adapter_kind="local",
        priority=20,
        enabled=False,
        implementation_status="implemented",
        capabilities=AdapterCapabilities(
            supports_tools=True,
            supports_json_mode=True,
            supports_vision=False,
            supports_streaming=True,
            max_context_tokens=16_384,
        ),
    ),
    AdapterSpec(
        backend_id="lm_studio",
        provider_family="lm_studio",
        adapter_kind="local",
        priority=30,
        enabled=False,
        implementation_status="implemented",
        capabilities=AdapterCapabilities(
            supports_tools=False,
            supports_json_mode=True,
            supports_vision=False,
            supports_streaming=True,
            max_context_tokens=32_768,
        ),
    ),
)


def build_capability_matrix(specs: Sequence[AdapterSpec] = DEFAULT_BACKEND_SPECS) -> Dict[str, Any]:
    ordered = sorted(specs, key=lambda s: (s.priority, s.backend_id))
    return {
        "contract_version": ADAPTER_CONTRACT_VERSION,
        "backends": [spec.as_matrix_row() for spec in ordered],
    }


def _parse_bool_override(value: Any) -> Optional[bool]:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return None


def _runtime_capability_override(
    backend_cfg: Mapping[str, Any],
    key: str,
) -> Any:
    if key in backend_cfg:
        return backend_cfg.get(key)

    nested_capabilities = backend_cfg.get("capabilities")
    if isinstance(nested_capabilities, Mapping):
        return nested_capabilities.get(key)

    return None


def resolve_specs_with_runtime_overrides(
    runtime_config: Optional[Mapping[str, Any]],
    specs: Sequence[AdapterSpec] = DEFAULT_BACKEND_SPECS,
) -> Tuple[AdapterSpec, ...]:
    resolved: List[AdapterSpec] = []

    for spec in specs:
        backend_cfg = _runtime_backend_config(runtime_config, spec.backend_id)
        if not backend_cfg:
            resolved.append(spec)
            continue

        enabled = spec.enabled
        enabled_override = _parse_bool_override(backend_cfg.get("enabled"))
        if enabled_override is not None:
            enabled = enabled_override

        implementation_status = str(backend_cfg.get("implementation_status", spec.implementation_status))

        supports_tools = spec.capabilities.supports_tools
        supports_tools_override = _parse_bool_override(_runtime_capability_override(backend_cfg, "supports_tools"))
        if supports_tools_override is not None:
            supports_tools = supports_tools_override

        supports_json_mode = spec.capabilities.supports_json_mode
        supports_json_mode_override = _parse_bool_override(_runtime_capability_override(backend_cfg, "supports_json_mode"))
        if supports_json_mode_override is not None:
            supports_json_mode = supports_json_mode_override

        supports_vision = spec.capabilities.supports_vision
        supports_vision_override = _parse_bool_override(_runtime_capability_override(backend_cfg, "supports_vision"))
        if supports_vision_override is not None:
            supports_vision = supports_vision_override

        supports_streaming = spec.capabilities.supports_streaming
        supports_streaming_override = _parse_bool_override(_runtime_capability_override(backend_cfg, "supports_streaming"))
        if supports_streaming_override is not None:
            supports_streaming = supports_streaming_override

        max_context_tokens = spec.capabilities.max_context_tokens
        max_context_tokens_override = _runtime_capability_override(backend_cfg, "max_context_tokens")
        if max_context_tokens_override is not None:
            max_context_tokens = int(max_context_tokens_override)

        resolved_capabilities = replace(
            spec.capabilities,
            supports_tools=supports_tools,
            supports_json_mode=supports_json_mode,
            supports_vision=supports_vision,
            supports_streaming=supports_streaming,
            max_context_tokens=max_context_tokens,
        )
        resolved.append(
            replace(
                spec,
                enabled=enabled,
                implementation_status=implementation_status,
                capabilities=resolved_capabilities,
            )
        )

    return tuple(resolved)


def text_requirements_for_request(request: TextGenerationRequest) -> BackendRequirements:
    return BackendRequirements(
        require_tools=request.require_tools,
        require_json_mode=request.require_json_mode,
        require_streaming=request.require_streaming,
        min_context_tokens=request.min_context_tokens,
    )


def select_backend_for_text_request(
    request: TextGenerationRequest,
    *,
    runtime_config: Optional[Mapping[str, Any]] = None,
    specs: Sequence[AdapterSpec] = DEFAULT_BACKEND_SPECS,
    preferred_backend_id: Optional[str] = None,
    allow_fallback: bool = True,
) -> AdapterSelection:
    resolved_specs = resolve_specs_with_runtime_overrides(runtime_config, specs=specs)
    return select_backend(
        requirements=text_requirements_for_request(request),
        specs=resolved_specs,
        preferred_backend_id=preferred_backend_id,
        allow_fallback=allow_fallback,
    )


def invoke_text_request_for_backend(
    backend_id: str,
    request: TextGenerationRequest,
    *,
    runtime_config: Optional[Mapping[str, Any]] = None,
    http_post: Optional[Callable[..., Any]] = None,
) -> TextGenerationResponse:
    """Invoke a normalized text request for an implemented text-first backend."""

    if backend_id == LlamaCppTextAdapter.backend_id:
        adapter = LlamaCppTextAdapter(
            LlamaCppAdapterConfig.from_runtime_config(runtime_config)
        )
    elif backend_id == LMStudioTextAdapter.backend_id:
        adapter = LMStudioTextAdapter(
            LMStudioAdapterConfig.from_runtime_config(runtime_config)
        )
    else:
        raise ValueError(f"Unsupported text-first backend for adapter invocation: {backend_id}")

    return adapter.invoke(request, http_post=http_post)


def _ordered_candidates(
    specs: Sequence[AdapterSpec],
    preferred_backend_id: Optional[str],
) -> List[AdapterSpec]:
    ordered = sorted(specs, key=lambda s: (s.priority, s.backend_id))
    if not preferred_backend_id:
        return ordered

    preferred = [s for s in ordered if s.backend_id == preferred_backend_id]
    if not preferred:
        raise ValueError(f"Unknown preferred backend: {preferred_backend_id}")

    remaining = [s for s in ordered if s.backend_id != preferred_backend_id]
    if any(s.adapter_kind == "local" for s in remaining) and any(s.adapter_kind != "local" for s in remaining):
        local_remaining = [s for s in remaining if s.adapter_kind == "local"]
        remote_remaining = [s for s in remaining if s.adapter_kind != "local"]
        remaining = local_remaining + remote_remaining

    return preferred + remaining


def select_backend(
    requirements: BackendRequirements,
    specs: Sequence[AdapterSpec] = DEFAULT_BACKEND_SPECS,
    preferred_backend_id: Optional[str] = None,
    allow_fallback: bool = True,
) -> AdapterSelection:
    """
    Deterministically choose a backend that satisfies required capabilities.

    Selection order:
    1) preferred backend (if provided)
    2) remaining backends sorted by (priority, backend_id)
    """
    candidates = _ordered_candidates(specs, preferred_backend_id)
    tried: List[Dict[str, Any]] = []

    for spec in candidates:
        missing: List[str] = []
        if not spec.enabled:
            missing.append("disabled")
        else:
            missing.extend(spec.capabilities.missing_for(requirements))

        tried.append({"backend_id": spec.backend_id, "missing_capabilities": missing})

        if missing:
            if preferred_backend_id == spec.backend_id and not allow_fallback:
                break
            continue

        used_fallback = preferred_backend_id is not None and spec.backend_id != preferred_backend_id
        return AdapterSelection(
            backend_id=spec.backend_id,
            spec=spec,
            used_fallback=used_fallback,
            tried=tuple(tried),
        )

    raise ValueError(
        "No backend satisfies requirements "
        f"(preferred={preferred_backend_id}, allow_fallback={allow_fallback}, tried={tried})"
    )


def _runtime_backend_config(
    runtime_config: Optional[Mapping[str, Any]],
    backend_id: str,
) -> Dict[str, Any]:
    if not isinstance(runtime_config, Mapping):
        return {}

    backends_map = runtime_config.get("backends")
    if isinstance(backends_map, Mapping):
        cfg = backends_map.get(backend_id)
        if isinstance(cfg, Mapping):
            return dict(cfg)

    # Legacy shape fallback: runtime_config[backend_id] = {...}
    legacy = runtime_config.get(backend_id)
    if isinstance(legacy, Mapping):
        return dict(legacy)

    return {}


def _extract_openai_style_assistant_message(body: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not isinstance(body, dict):
        return None

    choices = body.get("choices")
    if not isinstance(choices, list) or not choices:
        return None

    first = choices[0]
    if not isinstance(first, dict):
        return None

    message = first.get("message")
    if not isinstance(message, dict):
        return None

    content = message.get("content")
    normalized_content = ""
    if isinstance(content, str):
        normalized_content = content.strip()
    elif isinstance(content, list):
        text_segments: List[str] = []
        for part in content:
            if isinstance(part, dict) and isinstance(part.get("text"), str):
                text_segments.append(part["text"])
        normalized_content = "\n".join(seg.strip() for seg in text_segments if seg and seg.strip())

    tool_calls = message.get("tool_calls")
    if not isinstance(tool_calls, list):
        tool_calls = []

    return {
        "role": str(message.get("role") or "assistant"),
        "content": normalized_content,
        "tool_calls": tool_calls,
    }
