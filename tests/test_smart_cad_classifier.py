import json
from pathlib import Path

from src.smart_cad_classifier import (
    ALLOWED_CLASSIFICATIONS,
    build_candidate,
    classify_candidates,
    classify_shape,
    classify_from_face_descriptors,
    summarize_candidates,
)


class DummyShape:
    def __init__(self, hint=None):
        self.airpet_classification_hint = hint


def _fixture_cases():
    fixture_path = Path(__file__).parent / "fixtures" / "smart_cad" / "classifier_cases.json"
    with open(fixture_path, "r", encoding="utf-8") as f:
        return json.load(f)


def test_build_candidate_normalization_and_confidence_clamping():
    c = build_candidate(
        source_id="s1",
        classification="NOT_A_REAL_CLASS",
        confidence=9.9,
        params={"x": 1},
    )

    assert c["source_id"] == "s1"
    assert c["classification"] == "tessellated"
    assert c["confidence"] == 1.0
    assert c["fallback_reason"] == "no_primitive_match_v1"


def test_classify_shape_defaults_to_tessellated():
    c = classify_shape(shape=object(), source_id="fallback_case")
    assert c["classification"] == "tessellated"
    assert c["fallback_reason"] == "no_primitive_match_v1"
    assert c["confidence"] == 0.0


def test_fixture_classifier_cases_contract_and_expectations():
    cases = _fixture_cases()

    items = []
    for case in cases:
        hint = case.get("hint")
        shape = DummyShape(hint=hint) if hint is not None else DummyShape()
        items.append({"source_id": case["source_id"], "shape": shape})

    candidates = classify_candidates(items)

    assert len(candidates) == len(cases)

    for case, candidate in zip(cases, candidates):
        # Contract checks
        assert set(candidate.keys()) == {
            "source_id",
            "classification",
            "confidence",
            "params",
            "fallback_reason",
        }
        assert candidate["classification"] in ALLOWED_CLASSIFICATIONS
        assert 0.0 <= candidate["confidence"] <= 1.0

        # Fixture expectations
        expected = case["expected"]
        assert candidate["classification"] == expected["classification"]
        assert candidate["fallback_reason"] == expected["fallback_reason"]


def test_summary_counts_and_ratio():
    candidates = [
        build_candidate("a", classification="box", confidence=0.9),
        build_candidate("b", classification="cylinder", confidence=0.8),
        build_candidate("c", classification="tessellated", confidence=0.0),
    ]

    summary = summarize_candidates(candidates)

    assert summary["total"] == 3
    assert summary["primitive_count"] == 2
    assert summary["tessellated_count"] == 1
    assert summary["primitive_ratio"] == 2 / 3
    assert summary["selected_mode_counts"]["primitive"] == 0
    assert summary["selected_mode_counts"]["tessellated"] == 0
    assert summary["selected_primitive_ratio"] == 0.0
    assert summary["counts_by_classification"]["box"] == 1
    assert summary["counts_by_classification"]["cylinder"] == 1
    assert summary["counts_by_classification"]["tessellated"] == 1


def test_classify_from_face_descriptors_box():
    descriptors = [{"surface_type": "plane"} for _ in range(6)]
    obb_info = {
        "center": (0.0, 0.0, 0.0),
        "axes": [(1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)],
        "half_sizes": [5.0, 10.0, 15.0],
    }

    c = classify_from_face_descriptors("box_case", descriptors, obb_info=obb_info)

    assert c["classification"] == "box"
    assert c["fallback_reason"] is None
    assert c["params"]["x"] == 10.0
    assert c["params"]["y"] == 20.0
    assert c["params"]["z"] == 30.0


def test_classify_from_face_descriptors_cylinder():
    descriptors = [
        {"surface_type": "cylinder", "radius": 12.0, "axis": (0.0, 0.0, 1.0)},
        {"surface_type": "plane"},
        {"surface_type": "plane"},
    ]
    obb_info = {
        "center": (0.0, 0.0, 0.0),
        "axes": [(1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)],
        "half_sizes": [12.0, 12.0, 25.0],
    }

    c = classify_from_face_descriptors("cyl_case", descriptors, obb_info=obb_info)

    assert c["classification"] == "cylinder"
    assert c["fallback_reason"] is None
    assert c["params"]["rmax"] == 12.0
    assert c["params"]["z"] == 50.0
    assert c["params"]["center"] == (0.0, 0.0, 0.0)


def test_classify_from_face_descriptors_sphere():
    descriptors = [{"surface_type": "sphere", "radius": 8.5, "center": (1.0, 2.0, 3.0)}]

    c = classify_from_face_descriptors("sphere_case", descriptors, obb_info=None)

    assert c["classification"] == "sphere"
    assert c["fallback_reason"] is None
    assert c["params"]["rmax"] == 8.5


def test_classify_from_face_descriptors_ambiguous_fallback():
    descriptors = [
        {"surface_type": "plane"},
        {"surface_type": "sphere", "radius": 10.0},
    ]

    c = classify_from_face_descriptors("mixed_case", descriptors, obb_info=None)

    assert c["classification"] == "tessellated"
    assert c["fallback_reason"] == "ambiguous_surface_mix"
