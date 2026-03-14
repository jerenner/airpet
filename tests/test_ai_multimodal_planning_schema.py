from copy import deepcopy

import pytest

from src.ai_multimodal_extraction_schema import build_review_envelope, normalize_extraction_payload
from src.ai_multimodal_planning_schema import (
    MULTIMODAL_PLANNING_ENVELOPE_SCHEMA_VERSION,
    build_planning_envelope,
)


def _artifact_metadata():
    return {
        "artifact_id": "artifact_20260314T133000000000Z_deadbeefcafe",
        "sha256": "3f0f9f7dcf5bafe50c7e5f13f2bf8bf4df4c0a31b471ebf89fcbf95f4f4fd123",
    }


def _payload_unsorted():
    artifact = _artifact_metadata()
    return {
        "artifact_id": artifact["artifact_id"],
        "artifact_sha256": artifact["sha256"],
        "regions": [
            {
                "region_id": "region_b",
                "label": "inner detector",
                "page_index": 1,
                "bbox": {"x": 0.4, "y": 0.2, "width": 0.2, "height": 0.3},
                "confidence": 0.81,
                "provenance": {
                    "artifact_id": artifact["artifact_id"],
                    "artifact_sha256": artifact["sha256"],
                    "page_index": 1,
                    "source": "ocr-region",
                },
            },
            {
                "region_id": "region_a",
                "label": "outer vessel",
                "page_index": 0,
                "bbox": {"x": 0.1, "y": 0.1, "width": 0.6, "height": 0.7},
                "confidence": 0.93,
                "provenance": {
                    "artifact_id": artifact["artifact_id"],
                    "artifact_sha256": artifact["sha256"],
                    "page_index": 0,
                    "source": "manual-markup",
                },
            },
        ],
        "dimensions": [
            {
                "dimension_id": "dim_b",
                "region_id": "region_b",
                "value": 17.25,
                "unit": "mm",
                "raw_text": "17.25 mm",
                "confidence": 0.77,
                "provenance": {
                    "artifact_id": artifact["artifact_id"],
                    "artifact_sha256": artifact["sha256"],
                    "page_index": 1,
                    "source": "ocr-text",
                },
            },
            {
                "dimension_id": "dim_a",
                "region_id": "region_a",
                "value": 120.0,
                "unit": "mm",
                "raw_text": "120 mm",
                "confidence": 0.9,
                "provenance": {
                    "artifact_id": artifact["artifact_id"],
                    "artifact_sha256": artifact["sha256"],
                    "page_index": 0,
                    "source": "ocr-text",
                },
            },
        ],
        "symbols": [
            {
                "symbol_id": "sym_b",
                "region_id": "region_b",
                "symbol_type": "material",
                "text": "Si",
                "confidence": 0.86,
                "provenance": {
                    "artifact_id": artifact["artifact_id"],
                    "artifact_sha256": artifact["sha256"],
                    "page_index": 1,
                    "source": "ocr-symbol",
                },
            },
            {
                "symbol_id": "sym_a",
                "region_id": "region_a",
                "symbol_type": "annotation",
                "text": "beam axis",
                "confidence": 0.74,
                "provenance": {
                    "artifact_id": artifact["artifact_id"],
                    "artifact_sha256": artifact["sha256"],
                    "page_index": 0,
                    "source": "manual-markup",
                },
            },
        ],
    }


def test_build_planning_envelope_is_deterministic_for_approved_review_inputs():
    artifact = _artifact_metadata()
    extraction_a = normalize_extraction_payload(_payload_unsorted(), artifact_metadata=artifact)

    extraction_b = normalize_extraction_payload(_payload_unsorted(), artifact_metadata=artifact)
    review_a = build_review_envelope(extraction_a, status="approved")
    review_b = deepcopy(review_a)
    review_b["items"] = list(reversed(review_b["items"]))

    planning_a = build_planning_envelope(extraction_a, review_envelope=review_a)
    planning_b = build_planning_envelope(extraction_b, review_envelope=review_b)

    assert planning_a == planning_b
    assert planning_a["schema_version"] == MULTIMODAL_PLANNING_ENVELOPE_SCHEMA_VERSION
    assert planning_a["status"] == "ready"
    assert planning_a["summary"]["error_count"] == 0
    assert planning_a["summary"]["candidate_operation_count"] == 4


def test_build_planning_envelope_reports_unsupported_units_and_ambiguous_materials():
    artifact = _artifact_metadata()
    extraction_payload = _payload_unsorted()
    extraction_payload["dimensions"].append(
        {
            "dimension_id": "dim_c",
            "region_id": "region_a",
            "value": 7.5,
            "unit": "inch",
            "raw_text": "7.5 in",
            "confidence": 0.88,
            "provenance": {
                "artifact_id": artifact["artifact_id"],
                "artifact_sha256": artifact["sha256"],
                "page_index": 0,
                "source": "ocr-text",
            },
        }
    )
    extraction_payload["symbols"].append(
        {
            "symbol_id": "sym_c",
            "region_id": "region_b",
            "symbol_type": "material",
            "text": "Al",
            "confidence": 0.83,
            "provenance": {
                "artifact_id": artifact["artifact_id"],
                "artifact_sha256": artifact["sha256"],
                "page_index": 1,
                "source": "ocr-symbol",
            },
        }
    )

    extraction = normalize_extraction_payload(extraction_payload, artifact_metadata=artifact)
    review = build_review_envelope(extraction, status="approved")

    planning = build_planning_envelope(extraction, review_envelope=review)

    assert planning["status"] == "blocked"
    assert planning["summary"]["error_count"] == 2
    assert [entry["code"] for entry in planning["diagnostics"]] == [
        "ambiguous_region_material_symbols",
        "unsupported_dimension_unit",
    ]


def test_build_planning_envelope_rejects_mismatched_review_metadata():
    artifact = _artifact_metadata()
    extraction = normalize_extraction_payload(_payload_unsorted(), artifact_metadata=artifact)
    review = build_review_envelope(extraction, status="approved")
    review["extraction_id"] = "extract_other"

    with pytest.raises(ValueError) as exc:
        build_planning_envelope(extraction, review_envelope=review)

    assert "review_envelope.extraction_id" in str(exc.value)
