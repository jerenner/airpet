# Smart CAD Import — Fallback Policy (M2)

This document defines the deterministic fallback contract for Smart CAD import.

## Contract

For every smart-import candidate:

- `classification` is one of: `box`, `cylinder`, `sphere`, `cone`, `torus`, `tessellated`.
- `selected_mode` is one of: `primitive`, `tessellated`.
- If `selected_mode == tessellated`, `fallback_reason` **must** be present and belong to the allowed set.

## Allowed fallback reasons

General policy:
- `no_primitive_match_v1`
- `below_confidence_threshold`
- `unsupported_classification`
- `primitive_mapping_unavailable`

Environment/runtime:
- `occ_unavailable`
- `classifier_runtime_error`

Descriptor extraction / surface mix:
- `no_faces_detected`
- `unsupported_surface_type`
- `primitive_type_not_enabled_yet`
- `ambiguous_surface_mix`

Primitive fit failures:
- `box_fit_missing_obb`
- `box_fit_nonpositive_extent`
- `no_cylinder_face`
- `invalid_cylinder_radius`
- `invalid_cylinder_axis`
- `invalid_cylinder_height`
- `inconsistent_cylinder_axes`
- `inconsistent_cylinder_radii`
- `no_sphere_face`
- `invalid_sphere_radius`
- `inconsistent_sphere_centers`
- `inconsistent_sphere_radii`

## Selection rules

1. Classifier proposes candidate (`classification`, `confidence`, optional reason).
2. If candidate is mappable to an enabled primitive and confidence >= threshold (default `0.80`):
   - `selected_mode = primitive`
   - `fallback_reason = null`
3. Otherwise:
   - `selected_mode = tessellated`
   - If primitive exists but confidence is low -> `below_confidence_threshold`
   - If classification is primitive-like but not mapped in exporter -> `primitive_mapping_unavailable`
   - Otherwise keep/normalize classifier-provided fallback reason.

## Normalization policy

Unknown/invalid fallback reasons are normalized to:
- `no_primitive_match_v1`

This keeps downstream reporting stable and testable.

## Policy configuration

Current configurable field:
- `primitive_confidence_threshold` (0..1, default `0.80`)

Accepted import option keys:
- `smartImportConfidenceThreshold`
- `smart_import_confidence_threshold`
