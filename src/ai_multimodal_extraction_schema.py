from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Dict, List, Mapping, Optional, Sequence


MULTIMODAL_EXTRACTION_SCHEMA_VERSION = "2026-03-14.multimodal-intake.checkpoint2"
MULTIMODAL_REVIEW_ENVELOPE_SCHEMA_VERSION = "2026-03-14.multimodal-intake.checkpoint2"

_ALLOWED_REVIEW_STATUSES = {
    "pending_review",
    "approved",
    "needs_changes",
    "rejected",
}


class AIMultimodalSchemaValidationError(ValueError):
    """Raised when extraction/review payloads fail deterministic schema validation."""


def normalize_extraction_payload(
    payload: Mapping[str, Any],
    *,
    artifact_metadata: Mapping[str, Any],
) -> Dict[str, Any]:
    """Validate + normalize multimodal extraction payloads for deterministic downstream review."""

    if not isinstance(payload, Mapping):
        raise AIMultimodalSchemaValidationError("payload must be an object.")
    if not isinstance(artifact_metadata, Mapping):
        raise AIMultimodalSchemaValidationError("artifact_metadata must be an object.")

    canonical_artifact_id = _as_non_empty_str(artifact_metadata.get("artifact_id"), "artifact_metadata.artifact_id")
    canonical_artifact_sha = _as_non_empty_str(artifact_metadata.get("sha256"), "artifact_metadata.sha256")

    payload_artifact_id = payload.get("artifact_id")
    if payload_artifact_id is not None and str(payload_artifact_id).strip() != canonical_artifact_id:
        raise AIMultimodalSchemaValidationError(
            "payload.artifact_id must match artifact_metadata.artifact_id."
        )

    payload_artifact_sha = payload.get("artifact_sha256")
    if payload_artifact_sha is not None and str(payload_artifact_sha).strip() != canonical_artifact_sha:
        raise AIMultimodalSchemaValidationError(
            "payload.artifact_sha256 must match artifact_metadata.sha256."
        )

    regions = _normalize_regions(payload.get("regions"), artifact_id=canonical_artifact_id, artifact_sha256=canonical_artifact_sha)
    dimensions = _normalize_dimensions(
        payload.get("dimensions"),
        artifact_id=canonical_artifact_id,
        artifact_sha256=canonical_artifact_sha,
        region_ids={item["region_id"] for item in regions},
    )
    symbols = _normalize_symbols(
        payload.get("symbols"),
        artifact_id=canonical_artifact_id,
        artifact_sha256=canonical_artifact_sha,
        region_ids={item["region_id"] for item in regions},
    )

    canonical_body = {
        "artifact_id": canonical_artifact_id,
        "artifact_sha256": canonical_artifact_sha,
        "regions": regions,
        "dimensions": dimensions,
        "symbols": symbols,
    }

    extraction_id = payload.get("extraction_id")
    if extraction_id is None:
        digest = _stable_digest(canonical_body)
        extraction_id = f"extract_{digest[:16]}"
    extraction_id = _as_non_empty_str(extraction_id, "payload.extraction_id")

    return {
        "schema_version": MULTIMODAL_EXTRACTION_SCHEMA_VERSION,
        "artifact_id": canonical_artifact_id,
        "artifact_sha256": canonical_artifact_sha,
        "extraction_id": extraction_id,
        "regions": regions,
        "dimensions": dimensions,
        "symbols": symbols,
        "stats": {
            "region_count": len(regions),
            "dimension_count": len(dimensions),
            "symbol_count": len(symbols),
        },
    }


def build_review_envelope(
    extraction_payload: Mapping[str, Any],
    *,
    status: str = "pending_review",
) -> Dict[str, Any]:
    """Build deterministic machine-readable review envelope primitives for extraction payloads."""

    if not isinstance(extraction_payload, Mapping):
        raise AIMultimodalSchemaValidationError("extraction_payload must be an object.")

    artifact_id = _as_non_empty_str(extraction_payload.get("artifact_id"), "extraction_payload.artifact_id")
    artifact_sha256 = _as_non_empty_str(
        extraction_payload.get("artifact_sha256"),
        "extraction_payload.artifact_sha256",
    )
    extraction_id = _as_non_empty_str(extraction_payload.get("extraction_id"), "extraction_payload.extraction_id")

    review_status = _as_non_empty_str(status, "status")
    if review_status not in _ALLOWED_REVIEW_STATUSES:
        allowed = ", ".join(sorted(_ALLOWED_REVIEW_STATUSES))
        raise AIMultimodalSchemaValidationError(f"status must be one of: {allowed}.")

    regions = _as_list(extraction_payload.get("regions"), "extraction_payload.regions")
    dimensions = _as_list(extraction_payload.get("dimensions"), "extraction_payload.dimensions")
    symbols = _as_list(extraction_payload.get("symbols"), "extraction_payload.symbols")

    review_items = _build_review_items(regions=regions, dimensions=dimensions, symbols=symbols)
    confidence_values = [item["confidence"] for item in review_items]
    confidence_summary = {
        "min": min(confidence_values) if confidence_values else None,
        "max": max(confidence_values) if confidence_values else None,
        "mean": (
            round(sum(confidence_values) / len(confidence_values), 6)
            if confidence_values
            else None
        ),
    }

    envelope_body = {
        "artifact_id": artifact_id,
        "artifact_sha256": artifact_sha256,
        "extraction_id": extraction_id,
        "status": review_status,
        "summary": {
            "region_count": len(regions),
            "dimension_count": len(dimensions),
            "symbol_count": len(symbols),
            "total_items": len(review_items),
            "confidence": confidence_summary,
        },
        "items": review_items,
        "decisions": [],
    }

    envelope_id = f"review_{_stable_digest(envelope_body)[:16]}"

    return {
        "schema_version": MULTIMODAL_REVIEW_ENVELOPE_SCHEMA_VERSION,
        "envelope_id": envelope_id,
        **envelope_body,
    }


def _normalize_regions(
    raw_regions: Any,
    *,
    artifact_id: str,
    artifact_sha256: str,
) -> List[Dict[str, Any]]:
    regions_raw = _as_list(raw_regions, "payload.regions")
    normalized: List[Dict[str, Any]] = []
    seen_region_ids: set[str] = set()

    for idx, item in enumerate(regions_raw):
        if not isinstance(item, Mapping):
            raise AIMultimodalSchemaValidationError(f"payload.regions[{idx}] must be an object.")

        region_id = _as_non_empty_str(item.get("region_id"), f"payload.regions[{idx}].region_id")
        if region_id in seen_region_ids:
            raise AIMultimodalSchemaValidationError(f"Duplicate region_id: {region_id}.")
        seen_region_ids.add(region_id)

        normalized_region = {
            "region_id": region_id,
            "label": _as_non_empty_str(item.get("label"), f"payload.regions[{idx}].label"),
            "page_index": _as_non_negative_int(item.get("page_index", 0), f"payload.regions[{idx}].page_index"),
            "bbox": _normalize_bbox(item.get("bbox"), f"payload.regions[{idx}].bbox"),
            "confidence": _as_confidence(item.get("confidence"), f"payload.regions[{idx}].confidence"),
            "provenance": _normalize_provenance(
                item.get("provenance"),
                field=f"payload.regions[{idx}].provenance",
                artifact_id=artifact_id,
                artifact_sha256=artifact_sha256,
            ),
        }
        normalized.append(normalized_region)

    normalized.sort(key=lambda entry: entry["region_id"])
    return normalized


def _normalize_dimensions(
    raw_dimensions: Any,
    *,
    artifact_id: str,
    artifact_sha256: str,
    region_ids: set[str],
) -> List[Dict[str, Any]]:
    dimensions_raw = _as_list(raw_dimensions, "payload.dimensions")
    normalized: List[Dict[str, Any]] = []
    seen_dimension_ids: set[str] = set()

    for idx, item in enumerate(dimensions_raw):
        if not isinstance(item, Mapping):
            raise AIMultimodalSchemaValidationError(f"payload.dimensions[{idx}] must be an object.")

        dimension_id = _as_non_empty_str(item.get("dimension_id"), f"payload.dimensions[{idx}].dimension_id")
        if dimension_id in seen_dimension_ids:
            raise AIMultimodalSchemaValidationError(f"Duplicate dimension_id: {dimension_id}.")
        seen_dimension_ids.add(dimension_id)

        region_id_value = item.get("region_id")
        region_id = _as_non_empty_str(region_id_value, f"payload.dimensions[{idx}].region_id")
        if region_id not in region_ids:
            raise AIMultimodalSchemaValidationError(
                f"payload.dimensions[{idx}].region_id references unknown region_id '{region_id}'."
            )

        normalized_dimension = {
            "dimension_id": dimension_id,
            "region_id": region_id,
            "value": _as_finite_number(item.get("value"), f"payload.dimensions[{idx}].value"),
            "unit": _as_non_empty_str(item.get("unit"), f"payload.dimensions[{idx}].unit"),
            "raw_text": _as_non_empty_str(item.get("raw_text"), f"payload.dimensions[{idx}].raw_text"),
            "confidence": _as_confidence(item.get("confidence"), f"payload.dimensions[{idx}].confidence"),
            "provenance": _normalize_provenance(
                item.get("provenance"),
                field=f"payload.dimensions[{idx}].provenance",
                artifact_id=artifact_id,
                artifact_sha256=artifact_sha256,
            ),
        }
        normalized.append(normalized_dimension)

    normalized.sort(key=lambda entry: entry["dimension_id"])
    return normalized


def _normalize_symbols(
    raw_symbols: Any,
    *,
    artifact_id: str,
    artifact_sha256: str,
    region_ids: set[str],
) -> List[Dict[str, Any]]:
    symbols_raw = _as_list(raw_symbols, "payload.symbols")
    normalized: List[Dict[str, Any]] = []
    seen_symbol_ids: set[str] = set()

    for idx, item in enumerate(symbols_raw):
        if not isinstance(item, Mapping):
            raise AIMultimodalSchemaValidationError(f"payload.symbols[{idx}] must be an object.")

        symbol_id = _as_non_empty_str(item.get("symbol_id"), f"payload.symbols[{idx}].symbol_id")
        if symbol_id in seen_symbol_ids:
            raise AIMultimodalSchemaValidationError(f"Duplicate symbol_id: {symbol_id}.")
        seen_symbol_ids.add(symbol_id)

        region_id_value = item.get("region_id")
        region_id = _as_non_empty_str(region_id_value, f"payload.symbols[{idx}].region_id")
        if region_id not in region_ids:
            raise AIMultimodalSchemaValidationError(
                f"payload.symbols[{idx}].region_id references unknown region_id '{region_id}'."
            )

        normalized_symbol = {
            "symbol_id": symbol_id,
            "region_id": region_id,
            "symbol_type": _as_non_empty_str(item.get("symbol_type"), f"payload.symbols[{idx}].symbol_type"),
            "text": _as_non_empty_str(item.get("text"), f"payload.symbols[{idx}].text"),
            "confidence": _as_confidence(item.get("confidence"), f"payload.symbols[{idx}].confidence"),
            "provenance": _normalize_provenance(
                item.get("provenance"),
                field=f"payload.symbols[{idx}].provenance",
                artifact_id=artifact_id,
                artifact_sha256=artifact_sha256,
            ),
        }
        normalized.append(normalized_symbol)

    normalized.sort(key=lambda entry: entry["symbol_id"])
    return normalized


def _normalize_provenance(
    raw: Any,
    *,
    field: str,
    artifact_id: str,
    artifact_sha256: str,
) -> Dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise AIMultimodalSchemaValidationError(f"{field} must be an object.")

    provenance_artifact_id = _as_non_empty_str(raw.get("artifact_id"), f"{field}.artifact_id")
    if provenance_artifact_id != artifact_id:
        raise AIMultimodalSchemaValidationError(
            f"{field}.artifact_id must match artifact_id '{artifact_id}'."
        )

    provenance_artifact_sha256 = _as_non_empty_str(raw.get("artifact_sha256"), f"{field}.artifact_sha256")
    if provenance_artifact_sha256 != artifact_sha256:
        raise AIMultimodalSchemaValidationError(
            f"{field}.artifact_sha256 must match artifact_sha256 '{artifact_sha256}'."
        )

    return {
        "artifact_id": provenance_artifact_id,
        "artifact_sha256": provenance_artifact_sha256,
        "page_index": _as_non_negative_int(raw.get("page_index", 0), f"{field}.page_index"),
        "source": _as_non_empty_str(raw.get("source", "artifact"), f"{field}.source"),
    }


def _normalize_bbox(raw_bbox: Any, field: str) -> Dict[str, float]:
    if not isinstance(raw_bbox, Mapping):
        raise AIMultimodalSchemaValidationError(f"{field} must be an object with x/y/width/height.")

    x = _as_finite_number(raw_bbox.get("x"), f"{field}.x")
    y = _as_finite_number(raw_bbox.get("y"), f"{field}.y")
    width = _as_finite_number(raw_bbox.get("width"), f"{field}.width")
    height = _as_finite_number(raw_bbox.get("height"), f"{field}.height")

    if x < 0 or y < 0:
        raise AIMultimodalSchemaValidationError(f"{field}.x and {field}.y must be >= 0.")
    if width <= 0 or height <= 0:
        raise AIMultimodalSchemaValidationError(f"{field}.width and {field}.height must be > 0.")
    if x + width > 1:
        raise AIMultimodalSchemaValidationError(f"{field}.x + width must be <= 1.")
    if y + height > 1:
        raise AIMultimodalSchemaValidationError(f"{field}.y + height must be <= 1.")

    return {
        "x": round(float(x), 6),
        "y": round(float(y), 6),
        "width": round(float(width), 6),
        "height": round(float(height), 6),
    }


def _build_review_items(
    *,
    regions: Sequence[Mapping[str, Any]],
    dimensions: Sequence[Mapping[str, Any]],
    symbols: Sequence[Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []

    for region in regions:
        items.append(
            {
                "item_type": "region",
                "item_id": _as_non_empty_str(region.get("region_id"), "region.region_id"),
                "confidence": _as_confidence(region.get("confidence"), "region.confidence"),
                "review_state": "pending",
                "provenance": region.get("provenance"),
            }
        )

    for dimension in dimensions:
        items.append(
            {
                "item_type": "dimension",
                "item_id": _as_non_empty_str(dimension.get("dimension_id"), "dimension.dimension_id"),
                "confidence": _as_confidence(dimension.get("confidence"), "dimension.confidence"),
                "review_state": "pending",
                "provenance": dimension.get("provenance"),
            }
        )

    for symbol in symbols:
        items.append(
            {
                "item_type": "symbol",
                "item_id": _as_non_empty_str(symbol.get("symbol_id"), "symbol.symbol_id"),
                "confidence": _as_confidence(symbol.get("confidence"), "symbol.confidence"),
                "review_state": "pending",
                "provenance": symbol.get("provenance"),
            }
        )

    items.sort(key=lambda item: (item["item_type"], item["item_id"]))
    return items


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


def _as_non_negative_int(value: Any, field: str) -> int:
    if isinstance(value, bool):
        raise AIMultimodalSchemaValidationError(f"{field} must be a non-negative integer.")
    if isinstance(value, int):
        parsed = value
    elif isinstance(value, float) and value.is_integer():
        parsed = int(value)
    elif isinstance(value, str) and value.strip().isdigit():
        parsed = int(value.strip())
    else:
        raise AIMultimodalSchemaValidationError(f"{field} must be a non-negative integer.")

    if parsed < 0:
        raise AIMultimodalSchemaValidationError(f"{field} must be a non-negative integer.")
    return parsed


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


def _as_confidence(value: Any, field: str) -> float:
    parsed = _as_finite_number(value, field)
    if parsed < 0 or parsed > 1:
        raise AIMultimodalSchemaValidationError(f"{field} must be within [0, 1].")
    return round(parsed, 6)


def _stable_digest(value: Any) -> str:
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
