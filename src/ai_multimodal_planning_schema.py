from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from typing import Any, Dict, List, Mapping, Optional

from src.ai_multimodal_extraction_schema import AIMultimodalSchemaValidationError


MULTIMODAL_PLANNING_ENVELOPE_SCHEMA_VERSION = "2026-03-14.multimodal-intake.checkpoint4"

_ALLOWED_REVIEW_STATUSES = {
    "pending_review",
    "approved",
    "needs_changes",
    "rejected",
}

_ALLOWED_ITEM_TYPES = {"region", "dimension", "symbol"}
_ALLOWED_ITEM_REVIEW_STATES = {"pending", "approved", "needs_changes", "rejected"}
_SUPPORTED_SYMBOL_TYPES = {"material", "annotation"}

# Normalized conversion factors into mm.
_DIMENSION_UNIT_FACTORS_MM = {
    "mm": 1.0,
    "millimeter": 1.0,
    "millimeters": 1.0,
    "cm": 10.0,
    "centimeter": 10.0,
    "centimeters": 10.0,
    "m": 1000.0,
    "meter": 1000.0,
    "meters": 1000.0,
}


def build_planning_envelope(
    extraction_payload: Mapping[str, Any],
    *,
    review_envelope: Mapping[str, Any],
) -> Dict[str, Any]:
    """Build deterministic planning scaffold from extraction + review envelope payloads."""

    if not isinstance(extraction_payload, Mapping):
        raise AIMultimodalSchemaValidationError("extraction_payload must be an object.")
    if not isinstance(review_envelope, Mapping):
        raise AIMultimodalSchemaValidationError("review_envelope must be an object.")

    artifact_id = _as_non_empty_str(extraction_payload.get("artifact_id"), "extraction_payload.artifact_id")
    artifact_sha256 = _as_non_empty_str(
        extraction_payload.get("artifact_sha256"),
        "extraction_payload.artifact_sha256",
    )
    extraction_id = _as_non_empty_str(extraction_payload.get("extraction_id"), "extraction_payload.extraction_id")

    regions = _as_list(extraction_payload.get("regions"), "extraction_payload.regions")
    dimensions = _as_list(extraction_payload.get("dimensions"), "extraction_payload.dimensions")
    symbols = _as_list(extraction_payload.get("symbols"), "extraction_payload.symbols")

    region_ids = {
        _as_non_empty_str(region.get("region_id"), f"extraction_payload.regions[{idx}].region_id")
        for idx, region in enumerate(regions)
        if isinstance(region, Mapping)
    }
    dimensions_by_id = {
        _as_non_empty_str(item.get("dimension_id"), f"extraction_payload.dimensions[{idx}].dimension_id"): item
        for idx, item in enumerate(dimensions)
        if isinstance(item, Mapping)
    }
    symbols_by_id = {
        _as_non_empty_str(item.get("symbol_id"), f"extraction_payload.symbols[{idx}].symbol_id"): item
        for idx, item in enumerate(symbols)
        if isinstance(item, Mapping)
    }

    review = _normalize_review_envelope(
        review_envelope,
        artifact_id=artifact_id,
        artifact_sha256=artifact_sha256,
        extraction_id=extraction_id,
        region_ids=region_ids,
        dimension_ids=set(dimensions_by_id.keys()),
        symbol_ids=set(symbols_by_id.keys()),
    )

    diagnostics: List[Dict[str, Any]] = []
    operations: List[Dict[str, Any]] = []

    if review["status"] != "approved":
        diagnostics.append(
            {
                "code": "review_not_approved",
                "severity": "error",
                "message": "review_envelope.status must be 'approved' before generating mutation-ready planning operations.",
                "item_type": "review",
                "item_id": review["envelope_id"],
                "details": {
                    "status": review["status"],
                },
            }
        )

    approved_item_states = review["item_states"]
    approved_dimensions = [
        dimensions_by_id[item_id]
        for item_id, state in approved_item_states["dimension"].items()
        if state == "approved"
    ]
    approved_symbols = [
        symbols_by_id[item_id]
        for item_id, state in approved_item_states["symbol"].items()
        if state == "approved"
    ]
    approved_regions = [
        region_id
        for region_id, state in approved_item_states["region"].items()
        if state == "approved"
    ]

    dimension_candidates_by_region: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for idx, dimension in enumerate(approved_dimensions):
        region_id = _as_non_empty_str(dimension.get("region_id"), f"approved_dimensions[{idx}].region_id")
        dimension_id = _as_non_empty_str(dimension.get("dimension_id"), f"approved_dimensions[{idx}].dimension_id")
        unit_raw = _as_non_empty_str(dimension.get("unit"), f"approved_dimensions[{idx}].unit")
        unit_key = unit_raw.strip().lower()

        factor_to_mm = _DIMENSION_UNIT_FACTORS_MM.get(unit_key)
        if factor_to_mm is None:
            diagnostics.append(
                {
                    "code": "unsupported_dimension_unit",
                    "severity": "error",
                    "message": "dimension unit is not supported for deterministic planning.",
                    "item_type": "dimension",
                    "item_id": dimension_id,
                    "region_id": region_id,
                    "details": {
                        "unit": unit_raw,
                        "supported_units": sorted(_DIMENSION_UNIT_FACTORS_MM.keys()),
                    },
                }
            )
            continue

        numeric_value = _as_finite_number(dimension.get("value"), f"approved_dimensions[{idx}].value")
        if numeric_value <= 0:
            diagnostics.append(
                {
                    "code": "unsupported_dimension_value",
                    "severity": "error",
                    "message": "dimension value must be > 0 for planning operations.",
                    "item_type": "dimension",
                    "item_id": dimension_id,
                    "region_id": region_id,
                    "details": {
                        "value": numeric_value,
                    },
                }
            )
            continue

        dimension_candidates_by_region[region_id].append(
            {
                "dimension_id": dimension_id,
                "region_id": region_id,
                "value_mm": round(float(numeric_value) * factor_to_mm, 6),
                "raw_value": round(float(numeric_value), 6),
                "raw_unit": unit_raw,
                "raw_text": _as_non_empty_str(
                    dimension.get("raw_text"),
                    f"approved_dimensions[{idx}].raw_text",
                ),
                "confidence": _as_finite_number(
                    dimension.get("confidence"),
                    f"approved_dimensions[{idx}].confidence",
                ),
            }
        )

    for region_id in sorted(dimension_candidates_by_region.keys()):
        region_dimensions = sorted(
            dimension_candidates_by_region[region_id],
            key=lambda entry: entry["dimension_id"],
        )
        if len(region_dimensions) > 1:
            diagnostics.append(
                {
                    "code": "ambiguous_region_dimension_semantics",
                    "severity": "error",
                    "message": "multiple approved dimensions for one region are ambiguous without explicit semantic mapping.",
                    "item_type": "region",
                    "item_id": region_id,
                    "region_id": region_id,
                    "details": {
                        "dimension_ids": [entry["dimension_id"] for entry in region_dimensions],
                    },
                }
            )
            continue

        candidate = region_dimensions[0]
        operations.append(
            {
                "operation_id": f"plan_dim_{candidate['dimension_id']}",
                "operation_type": "apply_region_dimension_hint",
                "target_region_id": region_id,
                "source_item_type": "dimension",
                "source_item_id": candidate["dimension_id"],
                "parameters": {
                    "value": candidate["value_mm"],
                    "unit": "mm",
                    "raw_value": candidate["raw_value"],
                    "raw_unit": candidate["raw_unit"],
                    "raw_text": candidate["raw_text"],
                },
                "confidence": round(candidate["confidence"], 6),
            }
        )

    material_symbols_by_region: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for idx, symbol in enumerate(approved_symbols):
        region_id = _as_non_empty_str(symbol.get("region_id"), f"approved_symbols[{idx}].region_id")
        symbol_id = _as_non_empty_str(symbol.get("symbol_id"), f"approved_symbols[{idx}].symbol_id")
        symbol_type = _as_non_empty_str(symbol.get("symbol_type"), f"approved_symbols[{idx}].symbol_type").lower()
        symbol_text = _as_non_empty_str(symbol.get("text"), f"approved_symbols[{idx}].text")
        symbol_confidence = round(
            _as_finite_number(symbol.get("confidence"), f"approved_symbols[{idx}].confidence"),
            6,
        )

        if symbol_type not in _SUPPORTED_SYMBOL_TYPES:
            diagnostics.append(
                {
                    "code": "unsupported_symbol_type",
                    "severity": "error",
                    "message": "symbol_type is not supported for deterministic planning.",
                    "item_type": "symbol",
                    "item_id": symbol_id,
                    "region_id": region_id,
                    "details": {
                        "symbol_type": symbol_type,
                        "supported_symbol_types": sorted(_SUPPORTED_SYMBOL_TYPES),
                    },
                }
            )
            continue

        if symbol_type == "annotation":
            operations.append(
                {
                    "operation_id": f"plan_note_{symbol_id}",
                    "operation_type": "capture_region_annotation",
                    "target_region_id": region_id,
                    "source_item_type": "symbol",
                    "source_item_id": symbol_id,
                    "parameters": {
                        "text": symbol_text,
                    },
                    "confidence": symbol_confidence,
                }
            )
            continue

        material_symbols_by_region[region_id].append(
            {
                "symbol_id": symbol_id,
                "text": symbol_text,
                "confidence": symbol_confidence,
            }
        )

    for region_id in sorted(material_symbols_by_region.keys()):
        region_symbols = sorted(material_symbols_by_region[region_id], key=lambda entry: entry["symbol_id"])
        if len(region_symbols) > 1:
            diagnostics.append(
                {
                    "code": "ambiguous_region_material_symbols",
                    "severity": "error",
                    "message": "multiple approved material symbols for one region are ambiguous.",
                    "item_type": "region",
                    "item_id": region_id,
                    "region_id": region_id,
                    "details": {
                        "symbol_ids": [entry["symbol_id"] for entry in region_symbols],
                        "symbol_texts": [entry["text"] for entry in region_symbols],
                    },
                }
            )
            continue

        material = region_symbols[0]
        operations.append(
            {
                "operation_id": f"plan_mat_{material['symbol_id']}",
                "operation_type": "apply_region_material_hint",
                "target_region_id": region_id,
                "source_item_type": "symbol",
                "source_item_id": material["symbol_id"],
                "parameters": {
                    "material": material["text"],
                },
                "confidence": material["confidence"],
            }
        )

    operations.sort(key=lambda item: (item["operation_type"], item["target_region_id"], item["source_item_id"]))
    diagnostics.sort(
        key=lambda item: (
            item.get("severity", ""),
            item.get("code", ""),
            item.get("item_type", ""),
            item.get("item_id", ""),
        )
    )

    error_count = sum(1 for entry in diagnostics if entry.get("severity") == "error")
    warning_count = sum(1 for entry in diagnostics if entry.get("severity") == "warning")
    status = "ready" if error_count == 0 else "blocked"

    envelope_body = {
        "artifact_id": artifact_id,
        "artifact_sha256": artifact_sha256,
        "extraction_id": extraction_id,
        "review_envelope_id": review["envelope_id"],
        "review_status": review["status"],
        "status": status,
        "summary": {
            "approved_region_count": len(approved_regions),
            "approved_dimension_count": len(approved_dimensions),
            "approved_symbol_count": len(approved_symbols),
            "candidate_operation_count": len(operations),
            "diagnostic_count": len(diagnostics),
            "error_count": error_count,
            "warning_count": warning_count,
        },
        "operations": operations,
        "diagnostics": diagnostics,
    }

    planning_envelope_id = f"plan_{_stable_digest(envelope_body)[:16]}"

    return {
        "schema_version": MULTIMODAL_PLANNING_ENVELOPE_SCHEMA_VERSION,
        "planning_envelope_id": planning_envelope_id,
        **envelope_body,
    }


def _normalize_review_envelope(
    review_envelope: Mapping[str, Any],
    *,
    artifact_id: str,
    artifact_sha256: str,
    extraction_id: str,
    region_ids: set[str],
    dimension_ids: set[str],
    symbol_ids: set[str],
) -> Dict[str, Any]:
    envelope_id = _as_non_empty_str(review_envelope.get("envelope_id"), "review_envelope.envelope_id")

    review_artifact_id = _as_non_empty_str(review_envelope.get("artifact_id"), "review_envelope.artifact_id")
    if review_artifact_id != artifact_id:
        raise AIMultimodalSchemaValidationError(
            "review_envelope.artifact_id must match extraction_payload.artifact_id."
        )

    review_artifact_sha256 = _as_non_empty_str(
        review_envelope.get("artifact_sha256"),
        "review_envelope.artifact_sha256",
    )
    if review_artifact_sha256 != artifact_sha256:
        raise AIMultimodalSchemaValidationError(
            "review_envelope.artifact_sha256 must match extraction_payload.artifact_sha256."
        )

    review_extraction_id = _as_non_empty_str(review_envelope.get("extraction_id"), "review_envelope.extraction_id")
    if review_extraction_id != extraction_id:
        raise AIMultimodalSchemaValidationError(
            "review_envelope.extraction_id must match extraction_payload.extraction_id."
        )

    status = _as_non_empty_str(review_envelope.get("status"), "review_envelope.status")
    if status not in _ALLOWED_REVIEW_STATUSES:
        allowed = ", ".join(sorted(_ALLOWED_REVIEW_STATUSES))
        raise AIMultimodalSchemaValidationError(f"review_envelope.status must be one of: {allowed}.")

    items_raw = _as_list(review_envelope.get("items"), "review_envelope.items")
    decisions_raw = _as_list(review_envelope.get("decisions", []), "review_envelope.decisions")

    valid_item_ids = {
        "region": set(region_ids),
        "dimension": set(dimension_ids),
        "symbol": set(symbol_ids),
    }

    item_states: Dict[str, Dict[str, str]] = {
        "region": {},
        "dimension": {},
        "symbol": {},
    }

    for idx, item in enumerate(items_raw):
        if not isinstance(item, Mapping):
            raise AIMultimodalSchemaValidationError(f"review_envelope.items[{idx}] must be an object.")

        item_type = _as_non_empty_str(item.get("item_type"), f"review_envelope.items[{idx}].item_type").lower()
        if item_type not in _ALLOWED_ITEM_TYPES:
            allowed = ", ".join(sorted(_ALLOWED_ITEM_TYPES))
            raise AIMultimodalSchemaValidationError(
                f"review_envelope.items[{idx}].item_type must be one of: {allowed}."
            )

        item_id = _as_non_empty_str(item.get("item_id"), f"review_envelope.items[{idx}].item_id")
        if item_id not in valid_item_ids[item_type]:
            raise AIMultimodalSchemaValidationError(
                f"review_envelope.items[{idx}].item_id references unknown {item_type} '{item_id}'."
            )

        review_state_raw = item.get("review_state", "pending")
        review_state = _normalize_review_state(
            review_state_raw,
            field=f"review_envelope.items[{idx}].review_state",
        )

        if item_id in item_states[item_type] and item_states[item_type][item_id] != review_state:
            raise AIMultimodalSchemaValidationError(
                f"review_envelope.items contains conflicting review_state values for {item_type} '{item_id}'."
            )
        item_states[item_type][item_id] = review_state

    decision_states: Dict[tuple[str, str], str] = {}
    for idx, decision in enumerate(decisions_raw):
        if not isinstance(decision, Mapping):
            raise AIMultimodalSchemaValidationError(f"review_envelope.decisions[{idx}] must be an object.")

        item_type = _as_non_empty_str(decision.get("item_type"), f"review_envelope.decisions[{idx}].item_type").lower()
        if item_type not in _ALLOWED_ITEM_TYPES:
            allowed = ", ".join(sorted(_ALLOWED_ITEM_TYPES))
            raise AIMultimodalSchemaValidationError(
                f"review_envelope.decisions[{idx}].item_type must be one of: {allowed}."
            )

        item_id = _as_non_empty_str(decision.get("item_id"), f"review_envelope.decisions[{idx}].item_id")
        if item_id not in valid_item_ids[item_type]:
            raise AIMultimodalSchemaValidationError(
                f"review_envelope.decisions[{idx}].item_id references unknown {item_type} '{item_id}'."
            )

        decision_state = _normalize_review_state(
            decision.get("decision", decision.get("review_state", decision.get("status"))),
            field=f"review_envelope.decisions[{idx}]",
        )

        key = (item_type, item_id)
        previous = decision_states.get(key)
        if previous is not None and previous != decision_state:
            raise AIMultimodalSchemaValidationError(
                f"review_envelope.decisions contains conflicting decisions for {item_type} '{item_id}'."
            )
        decision_states[key] = decision_state

    resolved_states: Dict[str, Dict[str, str]] = {
        "region": {},
        "dimension": {},
        "symbol": {},
    }

    for item_type in sorted(item_states.keys()):
        for item_id in sorted(item_states[item_type].keys()):
            state = item_states[item_type][item_id]
            decided_state = decision_states.get((item_type, item_id))
            if decided_state is not None:
                state = decided_state
            elif status == "approved" and state == "pending":
                # Checkpoint-3 review envelopes mark items as pending by default;
                # when the envelope is globally approved, interpret pending as approved.
                state = "approved"
            resolved_states[item_type][item_id] = state

    return {
        "envelope_id": envelope_id,
        "status": status,
        "item_states": resolved_states,
    }


def _normalize_review_state(value: Any, *, field: str) -> str:
    if value is None:
        raise AIMultimodalSchemaValidationError(f"{field} must include decision/review_state/status.")

    text = _as_non_empty_str(value, field).lower()
    aliases = {
        "accept": "approved",
        "accepted": "approved",
        "approve": "approved",
        "ok": "approved",
        "reject": "rejected",
        "change": "needs_changes",
        "changes": "needs_changes",
        "needs_change": "needs_changes",
    }
    canonical = aliases.get(text, text)
    if canonical not in _ALLOWED_ITEM_REVIEW_STATES:
        allowed = ", ".join(sorted(_ALLOWED_ITEM_REVIEW_STATES))
        raise AIMultimodalSchemaValidationError(f"{field} must resolve to one of: {allowed}.")
    return canonical


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


def _stable_digest(value: Any) -> str:
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
