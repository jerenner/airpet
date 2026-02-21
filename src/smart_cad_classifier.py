"""Smart CAD classifier utilities for STEP import.

Phase 3 intent:
- classify solids as primitive candidates (box/cylinder/sphere/...) when confidence is high
- otherwise fall back to tessellated with explicit reasons

Note: in this iteration, classification feeds reporting + downstream mapping decisions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from statistics import median
from typing import Any, Dict, Iterable, List, Optional, Tuple

try:
    from OCC.Core.TopAbs import TopAbs_FACE
    from OCC.Core.TopExp import TopExp_Explorer
    from OCC.Core.BRepAdaptor import BRepAdaptor_Surface
    from OCC.Core.GeomAbs import (
        GeomAbs_Plane,
        GeomAbs_Cylinder,
        GeomAbs_Sphere,
        GeomAbs_Cone,
        GeomAbs_Torus,
    )
    from OCC.Core.Bnd import Bnd_OBB
    from OCC.Core.BRepBndLib import brepbndlib_AddOBB

    OCC_AVAILABLE = True
except Exception:
    OCC_AVAILABLE = False


ALLOWED_CLASSIFICATIONS = {
    "box",
    "cylinder",
    "sphere",
    "cone",
    "torus",
    "tessellated",
}

SURFACE_PLANE = "plane"
SURFACE_CYLINDER = "cylinder"
SURFACE_SPHERE = "sphere"
SURFACE_CONE = "cone"
SURFACE_TORUS = "torus"
SURFACE_OTHER = "other"


@dataclass
class SmartCadCandidate:
    """Classifier output contract for one imported source solid."""

    source_id: str
    classification: str
    confidence: float
    params: Dict[str, Any] = field(default_factory=dict)
    fallback_reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_id": self.source_id,
            "classification": self.classification,
            "confidence": self.confidence,
            "params": self.params,
            "fallback_reason": self.fallback_reason,
        }


def _normalize_classification(classification: Optional[str]) -> str:
    value = (classification or "tessellated").strip().lower()
    return value if value in ALLOWED_CLASSIFICATIONS else "tessellated"


def _clamp_confidence(confidence: Any) -> float:
    try:
        c = float(confidence)
    except (TypeError, ValueError):
        return 0.0
    if c < 0.0:
        return 0.0
    if c > 1.0:
        return 1.0
    return c


def _vec3_tuple(obj: Any) -> Tuple[float, float, float]:
    return (float(obj.X()), float(obj.Y()), float(obj.Z()))


def _dot(a: Tuple[float, float, float], b: Tuple[float, float, float]) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _safe_round(v: Any, ndigits: int = 6) -> float:
    try:
        return round(float(v), ndigits)
    except (TypeError, ValueError):
        return 0.0


def build_candidate(
    source_id: str,
    classification: Optional[str] = "tessellated",
    confidence: Any = 0.0,
    params: Optional[Dict[str, Any]] = None,
    fallback_reason: Optional[str] = None,
) -> Dict[str, Any]:
    """Builds a normalized candidate dictionary using classifier contract."""

    normalized_class = _normalize_classification(classification)
    normalized_conf = _clamp_confidence(confidence)

    if normalized_class != "tessellated":
        fallback_reason = None
    elif not fallback_reason:
        fallback_reason = "no_primitive_match_v1"

    candidate = SmartCadCandidate(
        source_id=source_id,
        classification=normalized_class,
        confidence=normalized_conf,
        params=params or {},
        fallback_reason=fallback_reason,
    )
    return candidate.to_dict()


def _extract_face_descriptors(shape: Any) -> List[Dict[str, Any]]:
    """Extracts a lightweight descriptor list from OCC faces."""

    if not OCC_AVAILABLE:
        return []

    descriptors: List[Dict[str, Any]] = []
    explorer = TopExp_Explorer(shape, TopAbs_FACE)

    while explorer.More():
        face = explorer.Current()
        surf = BRepAdaptor_Surface(face)
        surf_type = surf.GetType()

        if surf_type == GeomAbs_Plane:
            plane = surf.Plane()
            descriptors.append(
                {
                    "surface_type": SURFACE_PLANE,
                    "origin": _vec3_tuple(plane.Location()),
                    "normal": _vec3_tuple(plane.Axis().Direction()),
                }
            )

        elif surf_type == GeomAbs_Cylinder:
            cyl = surf.Cylinder()
            descriptors.append(
                {
                    "surface_type": SURFACE_CYLINDER,
                    "radius": float(cyl.Radius()),
                    "origin": _vec3_tuple(cyl.Location()),
                    "axis": _vec3_tuple(cyl.Axis().Direction()),
                }
            )

        elif surf_type == GeomAbs_Sphere:
            sph = surf.Sphere()
            descriptors.append(
                {
                    "surface_type": SURFACE_SPHERE,
                    "radius": float(sph.Radius()),
                    "center": _vec3_tuple(sph.Location()),
                }
            )

        elif surf_type == GeomAbs_Cone:
            cone = surf.Cone()
            descriptors.append(
                {
                    "surface_type": SURFACE_CONE,
                    "semi_angle": float(cone.SemiAngle()),
                    "ref_radius": float(cone.RefRadius()),
                    "origin": _vec3_tuple(cone.Location()),
                    "axis": _vec3_tuple(cone.Axis().Direction()),
                }
            )

        elif surf_type == GeomAbs_Torus:
            tor = surf.Torus()
            descriptors.append(
                {
                    "surface_type": SURFACE_TORUS,
                    "major_radius": float(tor.MajorRadius()),
                    "minor_radius": float(tor.MinorRadius()),
                    "origin": _vec3_tuple(tor.Location()),
                    "axis": _vec3_tuple(tor.Axis().Direction()),
                }
            )

        else:
            descriptors.append({"surface_type": SURFACE_OTHER})

        explorer.Next()

    return descriptors


def _extract_obb_info(shape: Any) -> Optional[Dict[str, Any]]:
    if not OCC_AVAILABLE:
        return None

    try:
        obb = Bnd_OBB()
        try:
            # Preferred signature available on most pythonocc builds.
            brepbndlib_AddOBB(shape, obb, True, True, True)
        except TypeError:
            # Fallback older signature.
            brepbndlib_AddOBB(shape, obb)

        return {
            "center": _vec3_tuple(obb.Center()),
            "axes": [
                _vec3_tuple(obb.XDirection()),
                _vec3_tuple(obb.YDirection()),
                _vec3_tuple(obb.ZDirection()),
            ],
            "half_sizes": [float(obb.XHSize()), float(obb.YHSize()), float(obb.ZHSize())],
        }
    except Exception:
        return None


def _fit_box_candidate(source_id: str, obb_info: Optional[Dict[str, Any]], plane_count: int) -> Dict[str, Any]:
    if not obb_info:
        return build_candidate(
            source_id=source_id,
            classification="tessellated",
            confidence=0.0,
            fallback_reason="box_fit_missing_obb",
        )

    hx, hy, hz = obb_info["half_sizes"]
    x, y, z = 2.0 * hx, 2.0 * hy, 2.0 * hz

    if min(x, y, z) <= 0.0:
        return build_candidate(
            source_id=source_id,
            classification="tessellated",
            confidence=0.0,
            fallback_reason="box_fit_nonpositive_extent",
        )

    conf = 0.75
    if plane_count == 6:
        conf += 0.15
    if plane_count > 6:
        conf -= 0.1

    return build_candidate(
        source_id=source_id,
        classification="box",
        confidence=conf,
        params={
            "x": _safe_round(x),
            "y": _safe_round(y),
            "z": _safe_round(z),
            "center": tuple(_safe_round(v) for v in obb_info["center"]),
            "axes": [tuple(_safe_round(v) for v in axis) for axis in obb_info["axes"]],
        },
    )


def _obb_extent_along_axis(obb_info: Optional[Dict[str, Any]], axis: Tuple[float, float, float]) -> Optional[float]:
    if not obb_info:
        return None
    half_sizes = obb_info["half_sizes"]
    obb_axes = obb_info["axes"]

    half_extent = 0.0
    for h, ax in zip(half_sizes, obb_axes):
        half_extent += abs(_dot(axis, ax)) * h
    return 2.0 * half_extent


def _fit_cylinder_candidate(
    source_id: str,
    descriptors: List[Dict[str, Any]],
    obb_info: Optional[Dict[str, Any]],
    plane_count: int,
) -> Dict[str, Any]:
    cyl_desc = [d for d in descriptors if d.get("surface_type") == SURFACE_CYLINDER]
    if not cyl_desc:
        return build_candidate(source_id=source_id, classification="tessellated", fallback_reason="no_cylinder_face")

    radii = [float(d.get("radius", 0.0)) for d in cyl_desc if float(d.get("radius", 0.0)) > 0.0]
    if not radii:
        return build_candidate(source_id=source_id, classification="tessellated", fallback_reason="invalid_cylinder_radius")

    r_med = median(radii)
    r_spread = ((max(radii) - min(radii)) / max(radii)) if max(radii) > 0 else 1.0

    axis = cyl_desc[0].get("axis", (0.0, 0.0, 1.0))
    center = obb_info.get("center") if isinstance(obb_info, dict) else cyl_desc[0].get("origin", (0.0, 0.0, 0.0))

    height = _obb_extent_along_axis(obb_info, axis)
    if height is None or height <= 0.0:
        return build_candidate(source_id=source_id, classification="tessellated", fallback_reason="invalid_cylinder_height")

    conf = 0.65
    if plane_count in (0, 2):
        conf += 0.15
    if r_spread < 0.01:
        conf += 0.15
    elif r_spread < 0.05:
        conf += 0.05

    return build_candidate(
        source_id=source_id,
        classification="cylinder",
        confidence=conf,
        params={
            "rmin": 0.0,
            "rmax": _safe_round(r_med),
            "z": _safe_round(height),
            "startphi": 0.0,
            "deltaphi": _safe_round(6.283185307179586),
            "axis": tuple(_safe_round(v) for v in axis),
            "center": tuple(_safe_round(v) for v in center),
            "radius_spread": _safe_round(r_spread),
        },
    )


def _fit_sphere_candidate(source_id: str, descriptors: List[Dict[str, Any]]) -> Dict[str, Any]:
    sph_desc = [d for d in descriptors if d.get("surface_type") == SURFACE_SPHERE]
    if not sph_desc:
        return build_candidate(source_id=source_id, classification="tessellated", fallback_reason="no_sphere_face")

    radii = [float(d.get("radius", 0.0)) for d in sph_desc if float(d.get("radius", 0.0)) > 0.0]
    if not radii:
        return build_candidate(source_id=source_id, classification="tessellated", fallback_reason="invalid_sphere_radius")

    r_med = median(radii)
    r_spread = ((max(radii) - min(radii)) / max(radii)) if max(radii) > 0 else 1.0

    conf = 0.7
    if len(sph_desc) == 1:
        conf += 0.2
    if r_spread < 0.01:
        conf += 0.1

    center = sph_desc[0].get("center", (0.0, 0.0, 0.0))

    return build_candidate(
        source_id=source_id,
        classification="sphere",
        confidence=conf,
        params={
            "rmin": 0.0,
            "rmax": _safe_round(r_med),
            "startphi": 0.0,
            "deltaphi": _safe_round(6.283185307179586),
            "starttheta": 0.0,
            "deltatheta": _safe_round(3.141592653589793),
            "center": tuple(_safe_round(v) for v in center),
            "radius_spread": _safe_round(r_spread),
        },
    )


def classify_from_face_descriptors(
    source_id: str,
    descriptors: List[Dict[str, Any]],
    obb_info: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Classifies using extracted face descriptors + optional OBB info."""

    if not descriptors:
        return build_candidate(
            source_id=source_id,
            classification="tessellated",
            confidence=0.0,
            fallback_reason="no_faces_detected",
        )

    surface_types = [d.get("surface_type", SURFACE_OTHER) for d in descriptors]
    total = len(surface_types)

    plane_count = sum(1 for t in surface_types if t == SURFACE_PLANE)
    cyl_count = sum(1 for t in surface_types if t == SURFACE_CYLINDER)
    sph_count = sum(1 for t in surface_types if t == SURFACE_SPHERE)
    cone_count = sum(1 for t in surface_types if t == SURFACE_CONE)
    torus_count = sum(1 for t in surface_types if t == SURFACE_TORUS)
    other_count = sum(1 for t in surface_types if t == SURFACE_OTHER)

    if other_count > 0:
        return build_candidate(
            source_id=source_id,
            classification="tessellated",
            confidence=0.0,
            fallback_reason="unsupported_surface_type",
        )

    # Box candidate: all planar, at least 6 faces.
    if plane_count == total and plane_count >= 6:
        return _fit_box_candidate(source_id, obb_info, plane_count=plane_count)

    # Cylinder candidate: cylindrical side + optional planar caps.
    if cyl_count >= 1 and (plane_count + cyl_count == total):
        return _fit_cylinder_candidate(source_id, descriptors, obb_info, plane_count=plane_count)

    # Sphere candidate: all spherical faces.
    if sph_count >= 1 and sph_count == total:
        return _fit_sphere_candidate(source_id, descriptors)

    # Keep explicit reasons for future cone/torus mappings.
    if cone_count > 0 or torus_count > 0:
        return build_candidate(
            source_id=source_id,
            classification="tessellated",
            confidence=0.0,
            fallback_reason="primitive_type_not_enabled_yet",
        )

    return build_candidate(
        source_id=source_id,
        classification="tessellated",
        confidence=0.0,
        fallback_reason="ambiguous_surface_mix",
    )


def classify_shape(shape: Any, source_id: str) -> Dict[str, Any]:
    """Classifies a shape into primitive candidate schema.

    Behavior order:
    1) explicit test/developer hint on shape (string or dict)
    2) OCC-based descriptor extraction + heuristic fitting
    3) safe tessellated fallback
    """

    hint = getattr(shape, "airpet_classification_hint", None)
    if hint is None:
        hint = getattr(shape, "_airpet_classification_hint", None)

    if hint is not None:
        if isinstance(hint, str):
            return build_candidate(
                source_id=source_id,
                classification=hint,
                confidence=1.0,
                params={},
                fallback_reason=None,
            )
        if isinstance(hint, dict):
            return build_candidate(
                source_id=source_id,
                classification=hint.get("classification", "tessellated"),
                confidence=hint.get("confidence", 1.0),
                params=hint.get("params", {}),
                fallback_reason=hint.get("fallback_reason"),
            )

    # Guard non-OCC or non-shape objects (common in tests/mocks).
    if shape is None or not hasattr(shape, "ShapeType"):
        return build_candidate(
            source_id=source_id,
            classification="tessellated",
            confidence=0.0,
            fallback_reason="no_primitive_match_v1",
        )

    if not OCC_AVAILABLE:
        return build_candidate(
            source_id=source_id,
            classification="tessellated",
            confidence=0.0,
            fallback_reason="occ_unavailable",
        )

    try:
        descriptors = _extract_face_descriptors(shape)
        obb_info = _extract_obb_info(shape)
        return classify_from_face_descriptors(source_id, descriptors, obb_info=obb_info)
    except Exception:
        return build_candidate(
            source_id=source_id,
            classification="tessellated",
            confidence=0.0,
            fallback_reason="classifier_runtime_error",
        )


def classify_candidates(items: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Batch classification helper for fixtures and pipeline tests.

    Each input item expects:
    - source_id: str
    - shape: Any (optional)
    """

    out: List[Dict[str, Any]] = []
    for item in items:
        source_id = str(item.get("source_id", "unknown_source"))
        out.append(classify_shape(item.get("shape"), source_id=source_id))
    return out


def summarize_candidates(candidates: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    """Creates an import-summary payload suitable for UI report scaffolding."""

    cands = list(candidates)
    total = len(cands)
    primitive_count = sum(1 for c in cands if c.get("classification") != "tessellated")
    tess_count = total - primitive_count

    counts_by_class = {key: 0 for key in ALLOWED_CLASSIFICATIONS}
    for c in cands:
        cls = _normalize_classification(c.get("classification"))
        counts_by_class[cls] += 1

    selected_mode_counts = {
        "primitive": sum(1 for c in cands if c.get("selected_mode") == "primitive"),
        "tessellated": sum(1 for c in cands if c.get("selected_mode") == "tessellated"),
    }

    primitive_ratio = (primitive_count / total) if total else 0.0
    selected_primitive_ratio = (selected_mode_counts["primitive"] / total) if total else 0.0

    return {
        "total": total,
        "primitive_count": primitive_count,
        "tessellated_count": tess_count,
        "primitive_ratio": primitive_ratio,
        "selected_mode_counts": selected_mode_counts,
        "selected_primitive_ratio": selected_primitive_ratio,
        "counts_by_classification": counts_by_class,
    }
