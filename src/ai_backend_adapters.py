from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

ADAPTER_CONTRACT_VERSION = "2026-03-13.checkpoint1"


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
        implementation_status="planned",
        capabilities=AdapterCapabilities(
            supports_tools=False,
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
        implementation_status="planned",
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

    return preferred + [s for s in ordered if s.backend_id != preferred_backend_id]


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
