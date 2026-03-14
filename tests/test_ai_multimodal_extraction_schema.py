from copy import deepcopy

import pytest

from src.ai_multimodal_extraction_schema import (
    AIMultimodalSchemaValidationError,
    MULTIMODAL_EXTRACTION_SCHEMA_VERSION,
    MULTIMODAL_REVIEW_ENVELOPE_SCHEMA_VERSION,
    build_review_envelope,
    normalize_extraction_payload,
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


def test_normalize_extraction_payload_is_deterministic_for_field_semantics_and_ordering():
    artifact = _artifact_metadata()

    payload_a = _payload_unsorted()
    payload_b = deepcopy(payload_a)
    payload_b["regions"] = list(reversed(payload_b["regions"]))
    payload_b["dimensions"] = list(reversed(payload_b["dimensions"]))
    payload_b["symbols"] = list(reversed(payload_b["symbols"]))

    normalized_a = normalize_extraction_payload(payload_a, artifact_metadata=artifact)
    normalized_b = normalize_extraction_payload(payload_b, artifact_metadata=artifact)

    assert normalized_a["schema_version"] == MULTIMODAL_EXTRACTION_SCHEMA_VERSION
    assert normalized_a == normalized_b
    assert [item["region_id"] for item in normalized_a["regions"]] == ["region_a", "region_b"]
    assert [item["dimension_id"] for item in normalized_a["dimensions"]] == ["dim_a", "dim_b"]
    assert [item["symbol_id"] for item in normalized_a["symbols"]] == ["sym_a", "sym_b"]
    assert normalized_a["stats"] == {
        "region_count": 2,
        "dimension_count": 2,
        "symbol_count": 2,
    }


def test_normalize_extraction_payload_rejects_provenance_artifact_mismatch():
    artifact = _artifact_metadata()
    payload = _payload_unsorted()
    payload["regions"][0]["provenance"]["artifact_id"] = "artifact_wrong"

    with pytest.raises(AIMultimodalSchemaValidationError) as exc:
        normalize_extraction_payload(payload, artifact_metadata=artifact)

    assert "artifact_id" in str(exc.value)


def test_normalize_extraction_payload_rejects_out_of_range_confidence():
    artifact = _artifact_metadata()
    payload = _payload_unsorted()
    payload["dimensions"][0]["confidence"] = 1.2

    with pytest.raises(AIMultimodalSchemaValidationError) as exc:
        normalize_extraction_payload(payload, artifact_metadata=artifact)

    assert "within [0, 1]" in str(exc.value)


def test_build_review_envelope_exposes_machine_readable_primitives():
    artifact = _artifact_metadata()
    normalized = normalize_extraction_payload(_payload_unsorted(), artifact_metadata=artifact)

    envelope = build_review_envelope(normalized)

    assert envelope["schema_version"] == MULTIMODAL_REVIEW_ENVELOPE_SCHEMA_VERSION
    assert envelope["envelope_id"].startswith("review_")
    assert envelope["status"] == "pending_review"
    assert envelope["summary"]["total_items"] == 6
    assert envelope["summary"]["confidence"]["min"] == 0.74
    assert envelope["summary"]["confidence"]["max"] == 0.93
    assert envelope["decisions"] == []
    assert [item["item_type"] for item in envelope["items"]] == [
        "dimension",
        "dimension",
        "region",
        "region",
        "symbol",
        "symbol",
    ]
    assert {item["review_state"] for item in envelope["items"]} == {"pending"}
