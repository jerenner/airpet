import json
from pathlib import Path

import pytest

from src.ai_backend_adapters import (
    ADAPTER_CONTRACT_VERSION,
    AdapterCapabilities,
    AdapterSpec,
    BackendRequirements,
    DEFAULT_BACKEND_SPECS,
    build_capability_matrix,
    select_backend,
)


def test_default_capability_matrix_reports_expected_backends_and_contract_version():
    matrix = build_capability_matrix()

    assert matrix["contract_version"] == ADAPTER_CONTRACT_VERSION

    rows_by_id = {row["backend_id"]: row for row in matrix["backends"]}
    assert {"gemini_remote", "llama_cpp", "lm_studio"}.issubset(rows_by_id.keys())

    assert rows_by_id["gemini_remote"]["enabled"] is True
    assert rows_by_id["gemini_remote"]["capabilities"]["supports_tools"] is True

    assert rows_by_id["llama_cpp"]["enabled"] is False
    assert rows_by_id["llama_cpp"]["capabilities"]["supports_json_mode"] is True

    assert rows_by_id["lm_studio"]["enabled"] is False
    assert rows_by_id["lm_studio"]["capabilities"]["supports_streaming"] is True


def test_docs_capability_matrix_matches_default_contract_matrix():
    matrix = build_capability_matrix()
    docs_path = Path(__file__).resolve().parents[1] / "docs" / "AI_BACKEND_CAPABILITY_MATRIX.json"
    docs_matrix = json.loads(docs_path.read_text())

    assert docs_matrix == matrix


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


def test_select_backend_falls_back_when_preferred_backend_cannot_satisfy_requirements():
    selection = select_backend(
        requirements=BackendRequirements(require_tools=True),
        specs=DEFAULT_BACKEND_SPECS,
        preferred_backend_id="llama_cpp",
        allow_fallback=True,
    )

    assert selection.backend_id == "gemini_remote"
    assert selection.used_fallback is True
    assert selection.tried[0]["backend_id"] == "llama_cpp"
    assert "disabled" in selection.tried[0]["missing_capabilities"]


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
