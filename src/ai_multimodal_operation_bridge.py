from __future__ import annotations

import hashlib
import json
import math
import re
from typing import Any, Dict, List, Mapping, Optional

from src.ai_multimodal_extraction_schema import AIMultimodalSchemaValidationError


MULTIMODAL_PLANNING_EXECUTION_PLAN_SCHEMA_VERSION = "2026-03-14.multimodal-intake.checkpoint5"


def build_geometry_execution_plan(
    planning_envelope: Mapping[str, Any],
    *,
    region_bindings: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Translate planning-envelope candidates into deterministic AI geometry-tool operations."""

    if not isinstance(planning_envelope, Mapping):
        raise AIMultimodalSchemaValidationError("planning_envelope must be a JSON object.")

    if region_bindings is None:
        region_bindings = {}
    if not isinstance(region_bindings, Mapping):
        raise AIMultimodalSchemaValidationError("region_bindings must be a JSON object.")

    planning_envelope_id = _as_non_empty_str(
        planning_envelope.get("planning_envelope_id"),
        "planning_envelope.planning_envelope_id",
    )
    artifact_id = _as_non_empty_str(planning_envelope.get("artifact_id"), "planning_envelope.artifact_id")
    artifact_sha256 = _as_non_empty_str(
        planning_envelope.get("artifact_sha256"),
        "planning_envelope.artifact_sha256",
    )
    extraction_id = _as_non_empty_str(
        planning_envelope.get("extraction_id"),
        "planning_envelope.extraction_id",
    )
    review_envelope_id = _as_non_empty_str(
        planning_envelope.get("review_envelope_id"),
        "planning_envelope.review_envelope_id",
    )

    planning_status = _as_non_empty_str(planning_envelope.get("status"), "planning_envelope.status").lower()
    if planning_status not in {"ready", "blocked"}:
        raise AIMultimodalSchemaValidationError("planning_envelope.status must be one of: ready, blocked.")

    operations_raw = _as_list(planning_envelope.get("operations"), "planning_envelope.operations")

    diagnostics: List[Dict[str, Any]] = []
    geometry_operations: List[Dict[str, Any]] = []
    annotation_notes: List[Dict[str, Any]] = []

    if planning_status != "ready":
        diagnostics.append(
            {
                "code": "planning_not_ready",
                "severity": "error",
                "message": "planning_envelope.status must be 'ready' before mutation operations can execute.",
                "item_type": "planning_envelope",
                "item_id": planning_envelope_id,
                "details": {
                    "status": planning_status,
                },
            }
        )

    for idx, operation in enumerate(operations_raw):
        if not isinstance(operation, Mapping):
            raise AIMultimodalSchemaValidationError(
                f"planning_envelope.operations[{idx}] must be a JSON object."
            )

        operation_id = _as_non_empty_str(
            operation.get("operation_id"),
            f"planning_envelope.operations[{idx}].operation_id",
        )
        operation_type = _as_non_empty_str(
            operation.get("operation_type"),
            f"planning_envelope.operations[{idx}].operation_type",
        )
        target_region_id = _as_non_empty_str(
            operation.get("target_region_id"),
            f"planning_envelope.operations[{idx}].target_region_id",
        )
        source_item_id = _as_non_empty_str(
            operation.get("source_item_id"),
            f"planning_envelope.operations[{idx}].source_item_id",
        )

        raw_parameters = operation.get("parameters")
        if not isinstance(raw_parameters, Mapping):
            raise AIMultimodalSchemaValidationError(
                f"planning_envelope.operations[{idx}].parameters must be a JSON object."
            )
        parameters = dict(raw_parameters)

        binding = _resolve_region_binding(region_bindings, target_region_id)

        if operation_type == "apply_region_dimension_hint":
            try:
                value_mm = _as_finite_number(
                    parameters.get("value"),
                    f"planning_envelope.operations[{idx}].parameters.value",
                )
            except AIMultimodalSchemaValidationError as exc:
                diagnostics.append(
                    {
                        "code": "invalid_dimension_hint",
                        "severity": "error",
                        "message": str(exc),
                        "item_type": "operation",
                        "item_id": operation_id,
                        "region_id": target_region_id,
                    }
                )
                continue

            if value_mm <= 0:
                diagnostics.append(
                    {
                        "code": "invalid_dimension_hint",
                        "severity": "error",
                        "message": "Dimension-hint value must be > 0.",
                        "item_type": "operation",
                        "item_id": operation_id,
                        "region_id": target_region_id,
                        "details": {
                            "value": round(value_mm, 6),
                        },
                    }
                )
                continue

            unit = _as_non_empty_str(
                parameters.get("unit", "mm"),
                f"planning_envelope.operations[{idx}].parameters.unit",
            ).lower()
            if unit != "mm":
                diagnostics.append(
                    {
                        "code": "unsupported_dimension_hint_unit",
                        "severity": "error",
                        "message": "Execution bridge only accepts mm-based dimension hints.",
                        "item_type": "operation",
                        "item_id": operation_id,
                        "region_id": target_region_id,
                        "details": {
                            "unit": unit,
                        },
                    }
                )
                continue

            define_name = _resolve_dimension_define_name(binding, target_region_id, source_item_id)
            define_value = _format_decimal(value_mm)

            geometry_operations.append(
                {
                    "source_operation_id": operation_id,
                    "source_operation_type": operation_type,
                    "target_region_id": target_region_id,
                    "tool_name": "manage_define",
                    "arguments": {
                        "name": define_name,
                        "define_type": "constant",
                        "value": define_value,
                        "unit": "mm",
                    },
                    "metadata": {
                        "raw_text": parameters.get("raw_text"),
                    },
                }
            )
            continue

        if operation_type == "apply_region_material_hint":
            logical_volume_name = _resolve_material_target(binding)
            if not logical_volume_name:
                diagnostics.append(
                    {
                        "code": "missing_material_target_binding",
                        "severity": "warning",
                        "message": "No logical_volume_name binding found for material hint; operation skipped.",
                        "item_type": "operation",
                        "item_id": operation_id,
                        "region_id": target_region_id,
                    }
                )
                continue

            material_hint = _as_non_empty_str(
                parameters.get("material"),
                f"planning_envelope.operations[{idx}].parameters.material",
            )
            resolved_material = _resolve_material_ref(material_hint, binding)

            geometry_operations.append(
                {
                    "source_operation_id": operation_id,
                    "source_operation_type": operation_type,
                    "target_region_id": target_region_id,
                    "tool_name": "manage_logical_volume",
                    "arguments": {
                        "name": logical_volume_name,
                        "material_ref": resolved_material,
                    },
                    "metadata": {
                        "material_hint": material_hint,
                    },
                }
            )
            continue

        if operation_type == "capture_region_annotation":
            annotation_text = _as_non_empty_str(
                parameters.get("text"),
                f"planning_envelope.operations[{idx}].parameters.text",
            )
            annotation_notes.append(
                {
                    "operation_id": operation_id,
                    "target_region_id": target_region_id,
                    "source_item_id": source_item_id,
                    "text": annotation_text,
                }
            )
            continue

        diagnostics.append(
            {
                "code": "unsupported_execution_operation_type",
                "severity": "error",
                "message": "Unsupported planning operation_type for execution bridge.",
                "item_type": "operation",
                "item_id": operation_id,
                "region_id": target_region_id,
                "details": {
                    "operation_type": operation_type,
                },
            }
        )

    diagnostics.sort(
        key=lambda item: (
            item.get("severity", ""),
            item.get("code", ""),
            item.get("item_type", ""),
            item.get("item_id", ""),
        )
    )

    error_count = sum(1 for item in diagnostics if item.get("severity") == "error")
    warning_count = sum(1 for item in diagnostics if item.get("severity") == "warning")
    status = "ready" if error_count == 0 else "blocked"

    execution_body = {
        "artifact_id": artifact_id,
        "artifact_sha256": artifact_sha256,
        "extraction_id": extraction_id,
        "review_envelope_id": review_envelope_id,
        "planning_envelope_id": planning_envelope_id,
        "planning_status": planning_status,
        "status": status,
        "summary": {
            "candidate_operation_count": len(operations_raw),
            "mutation_operation_count": len(geometry_operations),
            "annotation_note_count": len(annotation_notes),
            "diagnostic_count": len(diagnostics),
            "error_count": error_count,
            "warning_count": warning_count,
        },
        "geometry_operations": geometry_operations,
        "annotation_notes": annotation_notes,
        "diagnostics": diagnostics,
    }

    execution_plan_id = f"exec_{_stable_digest(execution_body)[:16]}"

    return {
        "schema_version": MULTIMODAL_PLANNING_EXECUTION_PLAN_SCHEMA_VERSION,
        "execution_plan_id": execution_plan_id,
        **execution_body,
    }


def _resolve_region_binding(region_bindings: Mapping[str, Any], region_id: str) -> Dict[str, Any]:
    raw_binding = region_bindings.get(region_id, {})
    if raw_binding is None:
        return {}
    if not isinstance(raw_binding, Mapping):
        raise AIMultimodalSchemaValidationError(
            f"region_bindings.{region_id} must be a JSON object when provided."
        )
    return dict(raw_binding)


def _resolve_dimension_define_name(binding: Mapping[str, Any], region_id: str, source_item_id: str) -> str:
    custom_name = binding.get("dimension_define_name")
    if custom_name is not None:
        return _as_non_empty_str(
            custom_name,
            f"region_bindings.{region_id}.dimension_define_name",
        )
    return f"MM_DIM_{_slug(region_id)}_{_slug(source_item_id)}"


def _resolve_material_target(binding: Mapping[str, Any]) -> Optional[str]:
    target = binding.get("logical_volume_name")
    if target is None:
        target = binding.get("logical_volume")
    if target is None:
        return None
    return _as_non_empty_str(target, "region_bindings.<region>.logical_volume_name")


def _resolve_material_ref(material_hint: str, binding: Mapping[str, Any]) -> str:
    material_map_raw = binding.get("material_map")
    if material_map_raw is None:
        return material_hint
    if not isinstance(material_map_raw, Mapping):
        raise AIMultimodalSchemaValidationError(
            "region_bindings.<region>.material_map must be a JSON object when provided."
        )

    normalized_map = {str(key).strip().lower(): str(value).strip() for key, value in material_map_raw.items()}
    key = material_hint.strip().lower()
    mapped = normalized_map.get(key)
    if mapped:
        return mapped
    return material_hint


def _slug(value: str) -> str:
    compact = re.sub(r"[^a-zA-Z0-9]+", "_", value).strip("_")
    return compact or "item"


def _as_non_empty_str(value: Any, field: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise AIMultimodalSchemaValidationError(f"{field} must be a non-empty string.")
    return text


def _as_list(value: Any, field: str) -> List[Any]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise AIMultimodalSchemaValidationError(f"{field} must be an array.")
    return value


def _as_finite_number(value: Any, field: str) -> float:
    if isinstance(value, bool):
        raise AIMultimodalSchemaValidationError(f"{field} must be a finite number.")
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        raise AIMultimodalSchemaValidationError(f"{field} must be a finite number.") from None

    if not math.isfinite(parsed):
        raise AIMultimodalSchemaValidationError(f"{field} must be a finite number.")
    return parsed


def _format_decimal(value: float) -> str:
    rounded = round(float(value), 6)
    return format(rounded, "g")


def _stable_digest(value: Any) -> str:
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
