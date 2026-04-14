# FILE: virtual-pet/src/geometry_types.py

import uuid # For unique IDs
import math
import re
import numpy as np
from copy import deepcopy

# --- Periodic Table Lookup (element name -> Z) ---
PERIODIC_TABLE = {
    "hydrogen": 1, "helium": 2, "lithium": 3, "beryllium": 4, "boron": 5,
    "carbon": 6, "nitrogen": 7, "oxygen": 8, "fluorine": 9, "neon": 10,
    "sodium": 11, "magnesium": 12, "aluminum": 13, "silicon": 14, "phosphorus": 15,
    "sulfur": 16, "chlorine": 17, "argon": 18, "potassium": 19, "calcium": 20,
    "scandium": 21, "titanium": 22, "vanadium": 23, "chromium": 24, "manganese": 25,
    "iron": 26, "cobalt": 27, "nickel": 28, "copper": 29, "zinc": 30,
    "gallium": 31, "germanium": 32, "arsenic": 33, "selenium": 34, "bromine": 35,
    "krypton": 36, "rubidium": 37, "strontium": 38, "yttrium": 39, "zirconium": 40,
    "niobium": 41, "molybdenum": 42, "technetium": 43, "ruthenium": 44, "rhodium": 45,
    "palladium": 46, "silver": 47, "cadmium": 48, "indium": 49, "tin": 50,
    "antimony": 51, "tellurium": 52, "iodine": 53, "xenon": 54, "cesium": 55,
    "barium": 56, "lanthanum": 57, "cerium": 58, "praseodymium": 59, "neodymium": 60,
    "promethium": 61, "samarium": 62, "europium": 63, "gadolinium": 64, "terbium": 65,
    "dysprosium": 66, "holmium": 67, "erbium": 68, "thulium": 69, "ytterbium": 70,
    "lutetium": 71, "hafnium": 72, "tantalum": 73, "tungsten": 74, "rhenium": 75,
    "osmium": 76, "iridium": 77, "platinum": 78, "gold": 79, "mercury": 80,
    "thallium": 81, "lead": 82, "bismuth": 83, "polonium": 84, "astatine": 85,
    "radon": 86, "francium": 87, "radium": 88, "actinium": 89, "thorium": 90,
    "protactinium": 91, "uranium": 92, "neptunium": 93, "plutonium": 94,
}

# --- Helper for Units (can be expanded) ---
# Geant4 internal units are mm for length, rad for angle
UNIT_FACTORS = {
    "length": {"mm": 1.0, "cm": 10.0, "m": 1000.0},
    "angle": {"rad": 1.0, "deg": math.pi / 180.0}
}
OUTPUT_UNIT_FACTORS = {
    "length": {"mm": 1.0, "cm": 0.1, "m": 0.001},
    "angle": {"rad": 1.0, "deg": 180.0 / math.pi}
}
DEFAULT_OUTPUT_LUNIT = "mm"
DEFAULT_OUTPUT_AUNIT = "rad"

DETECTOR_FEATURE_GENERATOR_SCHEMA_VERSION = 1
_SUPPORTED_DETECTOR_FEATURE_GENERATOR_TYPES = {
    "rectangular_drilled_hole_array",
    "circular_drilled_hole_array",
    "layered_detector_stack",
    "tiled_sensor_array",
    "support_rib_array",
    "channel_cut_array",
    "annular_shield_sleeve",
}
_SUPPORTED_DETECTOR_FEATURE_PATTERN_ANCHORS = {"target_center"}
_SUPPORTED_DETECTOR_FEATURE_LINEAR_AXES = {"x", "y"}
_SUPPORTED_DETECTOR_FEATURE_HOLE_SHAPES = {"cylindrical"}
_SUPPORTED_DETECTOR_FEATURE_HOLE_AXES = {"z"}
_SUPPORTED_DETECTOR_FEATURE_DRILL_FROM = {"positive_z_face"}
_SUPPORTED_DETECTOR_FEATURE_REALIZATION_MODES = {"boolean_subtraction", "layered_stack", "placement_array"}
_SUPPORTED_DETECTOR_FEATURE_REALIZATION_STATUSES = {"spec_only", "generated"}

SCORING_STATE_SCHEMA_VERSION = 1
_SUPPORTED_SCORING_MESH_TYPES = {"box"}
_SUPPORTED_SCORING_REFERENCE_FRAMES = {"world"}
_SUPPORTED_SCORING_TALLY_QUANTITIES = {
    "cell_flux",
    "dose_deposit",
    "energy_deposit",
    "n_of_step",
    "n_of_track",
    "passage_cell_flux",
    "track_length",
}

def convert_to_internal_units(value, unit_str, category="length"):
    if value is None: return None
    try:
        val = float(value)
    except ValueError:
        # Here you might integrate a more complex expression evaluator later
        print(f"Warning: Could not parse '{value}' as float, returning 0.0")
        return 0.0

    if unit_str and category in UNIT_FACTORS and unit_str in UNIT_FACTORS[category]:
        return val * UNIT_FACTORS[category][unit_str]
    return val # Assume already in internal units if unit_str is unknown/None

def convert_from_internal_units(value, target_unit_str, category="length"):
    if value is None: return None
    # Ensure value is float for calculations
    try:
        num_value = float(value)
    except (ValueError, TypeError):
        # If it's already a string (like a ref name), return as is
        # Or handle error if a numerical value was expected but not received
        return str(value)

    if target_unit_str and category in OUTPUT_UNIT_FACTORS and target_unit_str in OUTPUT_UNIT_FACTORS[category]:
        return num_value * OUTPUT_UNIT_FACTORS[category][target_unit_str]
    return num_value

def get_unit_value(unit_str, category="length"):
    # Geant4 internal units are mm, rad
    factors = {
        "length": {"mm": 1.0, "cm": 10.0, "m": 1000.0},
        "angle": {"rad": 1.0, "deg": math.pi / 180.0}
    }
    if unit_str and category in factors and unit_str in factors[category]:
        return factors[category][unit_str]
    return 1.0 # Default multiplier


def _normalize_non_empty_string(value):
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _normalize_positive_float(value, field_name):
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be a positive number.")
    try:
        normalized = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field_name} must be a positive number.")
    if normalized <= 0.0:
        raise ValueError(f"{field_name} must be greater than 0.")
    return normalized


def _normalize_float(value, default, field_name):
    if value is None:
        return default
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be numeric.")
    try:
        return float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field_name} must be numeric.")


def _normalize_positive_int(value, field_name):
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be a positive integer.")

    if isinstance(value, int):
        normalized = value
    elif isinstance(value, float):
        if not value.is_integer():
            raise ValueError(f"{field_name} must be a positive integer.")
        normalized = int(value)
    elif isinstance(value, str):
        stripped = value.strip()
        if not re.fullmatch(r"[+-]?\d+", stripped):
            raise ValueError(f"{field_name} must be a positive integer.")
        normalized = int(stripped)
    else:
        raise ValueError(f"{field_name} must be a positive integer.")

    if normalized <= 0:
        raise ValueError(f"{field_name} must be greater than 0.")
    return normalized


def _normalize_non_negative_int(value, default, field_name):
    if value is None:
        return default

    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be a non-negative integer.")

    if isinstance(value, int):
        normalized = value
    elif isinstance(value, float):
        if not value.is_integer():
            raise ValueError(f"{field_name} must be a non-negative integer.")
        normalized = int(value)
    elif isinstance(value, str):
        stripped = value.strip()
        if not re.fullmatch(r"[+-]?\d+", stripped):
            raise ValueError(f"{field_name} must be a non-negative integer.")
        normalized = int(stripped)
    else:
        raise ValueError(f"{field_name} must be a non-negative integer.")

    if normalized < 0:
        raise ValueError(f"{field_name} must be greater than or equal to 0.")
    return normalized


def _normalize_boolean(value, default, field_name):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    raise ValueError(f"{field_name} must be a boolean.")


def _normalize_non_empty_string_with_default(value, default, field_name):
    if value is None:
        return default
    normalized = _normalize_non_empty_string(value)
    if normalized is None:
        raise ValueError(f"{field_name} must be a non-empty string.")
    return normalized


def _normalize_detector_feature_object_ref(raw_ref, field_name, required=False):
    if raw_ref is None:
        if required:
            raise ValueError(f"{field_name} is required.")
        return None

    if not isinstance(raw_ref, dict):
        raise ValueError(f"{field_name} must be an object reference.")

    ref_id = _normalize_non_empty_string(raw_ref.get("id"))
    ref_name = _normalize_non_empty_string(raw_ref.get("name"))
    if not ref_id and not ref_name:
        if required:
            raise ValueError(f"{field_name} must include id or name.")
        return None

    normalized = {}
    if ref_id:
        normalized["id"] = ref_id
    if ref_name:
        normalized["name"] = ref_name
    return normalized


def _normalize_detector_feature_object_ref_list(raw_refs, field_name):
    if raw_refs is None:
        return []

    if not isinstance(raw_refs, list):
        raise ValueError(f"{field_name} must be an array of object references.")

    normalized_refs = []
    seen_refs = set()
    for index, raw_ref in enumerate(raw_refs):
        normalized_ref = _normalize_detector_feature_object_ref(
            raw_ref,
            f"{field_name}[{index}]",
            required=True,
        )
        ref_key = (normalized_ref.get("id"), normalized_ref.get("name"))
        if ref_key in seen_refs:
            continue
        seen_refs.add(ref_key)
        normalized_refs.append(normalized_ref)

    return normalized_refs


def _normalize_detector_feature_material_ref(value, field_name):
    normalized = _normalize_non_empty_string(value)
    if not normalized:
        raise ValueError(f"{field_name} must be a non-empty material name.")
    return normalized


def _default_scoring_run_manifest_defaults():
    return {
        "events": 1000,
        "threads": 1,
        "seed1": 0,
        "seed2": 0,
        "print_progress": 0,
        "save_hits": True,
        "save_hit_metadata": True,
        "save_particles": False,
        "production_cut": "1.0 mm",
        "hit_energy_threshold": "1 eV",
    }


def _normalize_scoring_mesh_ref(raw_ref, field_name, required=False):
    if raw_ref is None:
        if required:
            raise ValueError(f"{field_name} is required.")
        return None

    if isinstance(raw_ref, str):
        ref_name = _normalize_non_empty_string(raw_ref)
        if not ref_name:
            raise ValueError(f"{field_name} must be a non-empty scoring mesh reference.")
        return {"name": ref_name}

    if not isinstance(raw_ref, dict):
        raise ValueError(f"{field_name} must be a scoring mesh reference object.")

    mesh_id = _normalize_non_empty_string(raw_ref.get("mesh_id", raw_ref.get("id")))
    mesh_name = _normalize_non_empty_string(raw_ref.get("name"))
    if not mesh_id and not mesh_name:
        if required:
            raise ValueError(f"{field_name} must include mesh_id, id, or name.")
        return None

    normalized = {}
    if mesh_id:
        normalized["mesh_id"] = mesh_id
    if mesh_name:
        normalized["name"] = mesh_name
    return normalized


def _normalize_scoring_mesh_entry(raw_entry):
    if not isinstance(raw_entry, dict):
        raise ValueError("scoring.scoring_meshes[] entry must be an object.")

    mesh_id = _normalize_non_empty_string(raw_entry.get("mesh_id"))
    if not mesh_id:
        mesh_id = f"scoring_mesh_{uuid.uuid4().hex}"

    mesh_type = _normalize_non_empty_string(raw_entry.get("mesh_type")) or "box"
    if mesh_type not in _SUPPORTED_SCORING_MESH_TYPES:
        raise ValueError(
            "scoring.scoring_meshes[].mesh_type must be one of: "
            + ", ".join(sorted(_SUPPORTED_SCORING_MESH_TYPES))
            + "."
        )

    reference_frame = _normalize_non_empty_string(raw_entry.get("reference_frame")) or "world"
    if reference_frame not in _SUPPORTED_SCORING_REFERENCE_FRAMES:
        raise ValueError(
            "scoring.scoring_meshes[].reference_frame must be one of: "
            + ", ".join(sorted(_SUPPORTED_SCORING_REFERENCE_FRAMES))
            + "."
        )

    schema_version = _normalize_positive_int(
        raw_entry.get("schema_version", SCORING_STATE_SCHEMA_VERSION),
        "scoring.scoring_meshes[].schema_version",
    )
    enabled = _normalize_boolean(
        raw_entry.get("enabled"),
        True,
        "scoring.scoring_meshes[].enabled",
    )

    geometry = raw_entry.get("geometry", {})
    if geometry is None:
        geometry = {}
    if not isinstance(geometry, dict):
        raise ValueError("scoring.scoring_meshes[].geometry must be an object.")

    center_mm = geometry.get("center_mm", raw_entry.get("center_mm", {}))
    if center_mm is None:
        center_mm = {}
    if not isinstance(center_mm, dict):
        raise ValueError("scoring.scoring_meshes[].geometry.center_mm must be an object.")

    size_mm = geometry.get("size_mm", raw_entry.get("size_mm", {}))
    if size_mm is None:
        size_mm = {}
    if not isinstance(size_mm, dict):
        raise ValueError("scoring.scoring_meshes[].geometry.size_mm must be an object.")

    bins = raw_entry.get("bins", {})
    if bins is None:
        bins = {}
    if not isinstance(bins, dict):
        raise ValueError("scoring.scoring_meshes[].bins must be an object.")

    default_name = f"{mesh_type}_mesh_{mesh_id.split('_')[-1][:8]}"
    return {
        "mesh_id": mesh_id,
        "name": _normalize_non_empty_string(raw_entry.get("name")) or default_name,
        "schema_version": schema_version,
        "enabled": enabled,
        "mesh_type": mesh_type,
        "reference_frame": reference_frame,
        "geometry": {
            "center_mm": {
                "x": _normalize_float(
                    center_mm.get("x"),
                    0.0,
                    "scoring.scoring_meshes[].geometry.center_mm.x",
                ),
                "y": _normalize_float(
                    center_mm.get("y"),
                    0.0,
                    "scoring.scoring_meshes[].geometry.center_mm.y",
                ),
                "z": _normalize_float(
                    center_mm.get("z"),
                    0.0,
                    "scoring.scoring_meshes[].geometry.center_mm.z",
                ),
            },
            "size_mm": {
                "x": _normalize_positive_float(
                    size_mm.get("x", 10.0),
                    "scoring.scoring_meshes[].geometry.size_mm.x",
                ),
                "y": _normalize_positive_float(
                    size_mm.get("y", 10.0),
                    "scoring.scoring_meshes[].geometry.size_mm.y",
                ),
                "z": _normalize_positive_float(
                    size_mm.get("z", 10.0),
                    "scoring.scoring_meshes[].geometry.size_mm.z",
                ),
            },
        },
        "bins": {
            "x": _normalize_positive_int(
                bins.get("x", 10),
                "scoring.scoring_meshes[].bins.x",
            ),
            "y": _normalize_positive_int(
                bins.get("y", 10),
                "scoring.scoring_meshes[].bins.y",
            ),
            "z": _normalize_positive_int(
                bins.get("z", 10),
                "scoring.scoring_meshes[].bins.z",
            ),
        },
    }


def _normalize_scoring_meshes(raw_meshes):
    if raw_meshes is None:
        return []
    if not isinstance(raw_meshes, list):
        raise ValueError("scoring.scoring_meshes must be an array.")

    normalized_meshes = []
    seen_mesh_ids = set()
    for index, raw_entry in enumerate(raw_meshes):
        try:
            normalized_entry = _normalize_scoring_mesh_entry(raw_entry)
        except ValueError as exc:
            print(f"Warning: Skipping scoring mesh at index {index}: {exc}")
            continue

        mesh_id = normalized_entry["mesh_id"]
        if mesh_id in seen_mesh_ids:
            print(
                "Warning: Skipping scoring mesh at index "
                f"{index}: duplicate mesh_id '{mesh_id}'."
            )
            continue

        seen_mesh_ids.add(mesh_id)
        normalized_meshes.append(normalized_entry)

    return normalized_meshes


def _build_scoring_mesh_lookup(scoring_meshes):
    mesh_ids = {}
    mesh_names = {}
    ambiguous_names = set()

    for mesh in scoring_meshes or []:
        mesh_id = mesh.get("mesh_id")
        if mesh_id:
            mesh_ids[mesh_id] = mesh

        mesh_name = mesh.get("name")
        if not mesh_name:
            continue

        if mesh_name in mesh_names:
            ambiguous_names.add(mesh_name)
        else:
            mesh_names[mesh_name] = mesh

    for mesh_name in ambiguous_names:
        mesh_names.pop(mesh_name, None)

    return mesh_ids, mesh_names, ambiguous_names


def _normalize_scoring_tally_request_entry(raw_entry, mesh_lookup=None):
    if not isinstance(raw_entry, dict):
        raise ValueError("scoring.tally_requests[] entry must be an object.")

    tally_id = _normalize_non_empty_string(raw_entry.get("tally_id"))
    if not tally_id:
        tally_id = f"scoring_tally_{uuid.uuid4().hex}"

    schema_version = _normalize_positive_int(
        raw_entry.get("schema_version", SCORING_STATE_SCHEMA_VERSION),
        "scoring.tally_requests[].schema_version",
    )
    enabled = _normalize_boolean(
        raw_entry.get("enabled"),
        True,
        "scoring.tally_requests[].enabled",
    )

    quantity = _normalize_non_empty_string(raw_entry.get("quantity")) or "energy_deposit"
    if quantity not in _SUPPORTED_SCORING_TALLY_QUANTITIES:
        raise ValueError(
            "scoring.tally_requests[].quantity must be one of: "
            + ", ".join(sorted(_SUPPORTED_SCORING_TALLY_QUANTITIES))
            + "."
        )

    mesh_ref = raw_entry.get("mesh_ref")
    if mesh_ref is None:
        if raw_entry.get("mesh_id") is not None:
            mesh_ref = {"mesh_id": raw_entry.get("mesh_id")}
        elif raw_entry.get("mesh_name") is not None:
            mesh_ref = {"name": raw_entry.get("mesh_name")}

    normalized_mesh_ref = _normalize_scoring_mesh_ref(
        mesh_ref,
        "scoring.tally_requests[].mesh_ref",
        required=True,
    )

    if mesh_lookup is not None:
        mesh_ids, mesh_names, ambiguous_names = mesh_lookup
        matched_mesh = None
        mesh_id = normalized_mesh_ref.get("mesh_id")
        mesh_name = normalized_mesh_ref.get("name")

        if mesh_id:
            matched_mesh = mesh_ids.get(mesh_id)
            if matched_mesh is None:
                raise ValueError(
                    f"scoring.tally_requests[].mesh_ref.mesh_id '{mesh_id}' does not match a saved scoring mesh."
                )

        if mesh_name:
            if mesh_name in ambiguous_names:
                raise ValueError(
                    f"scoring.tally_requests[].mesh_ref.name '{mesh_name}' matches multiple saved scoring meshes."
                )
            named_mesh = mesh_names.get(mesh_name)
            if named_mesh is None:
                raise ValueError(
                    f"scoring.tally_requests[].mesh_ref.name '{mesh_name}' does not match a saved scoring mesh."
                )
            if matched_mesh is not None and named_mesh.get("mesh_id") != matched_mesh.get("mesh_id"):
                raise ValueError(
                    "scoring.tally_requests[].mesh_ref must resolve to one saved scoring mesh."
                )
            matched_mesh = named_mesh

        if matched_mesh is not None:
            normalized_mesh_ref["mesh_id"] = matched_mesh.get("mesh_id")
            normalized_mesh_ref["name"] = matched_mesh.get("name")

    default_name = f"{quantity}_{tally_id.split('_')[-1][:8]}"
    return {
        "tally_id": tally_id,
        "name": _normalize_non_empty_string(raw_entry.get("name")) or default_name,
        "schema_version": schema_version,
        "enabled": enabled,
        "mesh_ref": normalized_mesh_ref,
        "quantity": quantity,
    }


def _normalize_scoring_tally_requests(raw_requests, mesh_lookup=None):
    if raw_requests is None:
        return []
    if not isinstance(raw_requests, list):
        raise ValueError("scoring.tally_requests must be an array.")

    normalized_requests = []
    seen_tally_ids = set()
    for index, raw_entry in enumerate(raw_requests):
        try:
            normalized_entry = _normalize_scoring_tally_request_entry(raw_entry, mesh_lookup=mesh_lookup)
        except ValueError as exc:
            print(f"Warning: Skipping scoring tally request at index {index}: {exc}")
            continue

        tally_id = normalized_entry["tally_id"]
        if tally_id in seen_tally_ids:
            print(
                "Warning: Skipping scoring tally request at index "
                f"{index}: duplicate tally_id '{tally_id}'."
            )
            continue

        seen_tally_ids.add(tally_id)
        normalized_requests.append(normalized_entry)

    return normalized_requests


def _normalize_scoring_run_manifest_defaults(raw_defaults):
    defaults = _default_scoring_run_manifest_defaults()
    if raw_defaults is None:
        raw_defaults = {}
    if not isinstance(raw_defaults, dict):
        raise ValueError("scoring.run_manifest_defaults must be an object.")

    return {
        "events": _normalize_positive_int(
            raw_defaults.get("events", defaults["events"]),
            "scoring.run_manifest_defaults.events",
        ),
        "threads": _normalize_positive_int(
            raw_defaults.get("threads", defaults["threads"]),
            "scoring.run_manifest_defaults.threads",
        ),
        "seed1": _normalize_non_negative_int(
            raw_defaults.get("seed1", defaults["seed1"]),
            defaults["seed1"],
            "scoring.run_manifest_defaults.seed1",
        ),
        "seed2": _normalize_non_negative_int(
            raw_defaults.get("seed2", defaults["seed2"]),
            defaults["seed2"],
            "scoring.run_manifest_defaults.seed2",
        ),
        "print_progress": _normalize_non_negative_int(
            raw_defaults.get("print_progress", defaults["print_progress"]),
            defaults["print_progress"],
            "scoring.run_manifest_defaults.print_progress",
        ),
        "save_hits": _normalize_boolean(
            raw_defaults.get("save_hits"),
            defaults["save_hits"],
            "scoring.run_manifest_defaults.save_hits",
        ),
        "save_hit_metadata": _normalize_boolean(
            raw_defaults.get("save_hit_metadata"),
            defaults["save_hit_metadata"],
            "scoring.run_manifest_defaults.save_hit_metadata",
        ),
        "save_particles": _normalize_boolean(
            raw_defaults.get("save_particles"),
            defaults["save_particles"],
            "scoring.run_manifest_defaults.save_particles",
        ),
        "production_cut": _normalize_non_empty_string_with_default(
            raw_defaults.get("production_cut"),
            defaults["production_cut"],
            "scoring.run_manifest_defaults.production_cut",
        ),
        "hit_energy_threshold": _normalize_non_empty_string_with_default(
            raw_defaults.get("hit_energy_threshold"),
            defaults["hit_energy_threshold"],
            "scoring.run_manifest_defaults.hit_energy_threshold",
        ),
    }


def _normalize_detector_feature_generator_entry(raw_entry):
    if not isinstance(raw_entry, dict):
        raise ValueError("detector feature generator entry must be an object.")

    generator_type = _normalize_non_empty_string(raw_entry.get("generator_type"))
    if generator_type not in _SUPPORTED_DETECTOR_FEATURE_GENERATOR_TYPES:
        raise ValueError(
            "detector feature generator type must be one of: "
            + ", ".join(sorted(_SUPPORTED_DETECTOR_FEATURE_GENERATOR_TYPES))
            + "."
        )

    generator_id = _normalize_non_empty_string(raw_entry.get("generator_id"))
    if not generator_id:
        generator_id = f"detector_feature_generator_{uuid.uuid4().hex}"

    schema_version = raw_entry.get("schema_version", DETECTOR_FEATURE_GENERATOR_SCHEMA_VERSION)
    schema_version = _normalize_positive_int(schema_version, "detector_feature_generators[].schema_version")

    enabled = raw_entry.get("enabled", True)
    if not isinstance(enabled, bool):
        raise ValueError("detector_feature_generators[].enabled must be a boolean.")

    target = raw_entry.get("target", {})
    if not isinstance(target, dict):
        raise ValueError("detector_feature_generators[].target must be an object.")

    pattern = raw_entry.get("pattern", {})
    if pattern is None:
        pattern = {}
    if not isinstance(pattern, dict):
        raise ValueError("detector_feature_generators[].pattern must be an object.")

    stack = raw_entry.get("stack", {})
    if stack is None:
        stack = {}
    if not isinstance(stack, dict):
        raise ValueError("detector_feature_generators[].stack must be an object.")

    array = raw_entry.get("array", {})
    if array is None:
        array = {}
    if not isinstance(array, dict):
        raise ValueError("detector_feature_generators[].array must be an object.")

    layers = raw_entry.get("layers", {})
    if layers is None:
        layers = {}
    if not isinstance(layers, dict):
        raise ValueError("detector_feature_generators[].layers must be an object.")

    sensor = raw_entry.get("sensor", {})
    if sensor is None:
        sensor = {}
    if not isinstance(sensor, dict):
        raise ValueError("detector_feature_generators[].sensor must be an object.")

    rib = raw_entry.get("rib", {})
    if rib is None:
        rib = {}
    if not isinstance(rib, dict):
        raise ValueError("detector_feature_generators[].rib must be an object.")

    channel = raw_entry.get("channel", {})
    if channel is None:
        channel = {}
    if not isinstance(channel, dict):
        raise ValueError("detector_feature_generators[].channel must be an object.")

    shield = raw_entry.get("shield", {})
    if shield is None:
        shield = {}
    if not isinstance(shield, dict):
        raise ValueError("detector_feature_generators[].shield must be an object.")

    hole = raw_entry.get("hole", {})
    if hole is None:
        hole = {}
    if not isinstance(hole, dict):
        raise ValueError("detector_feature_generators[].hole must be an object.")

    realization = raw_entry.get("realization", {})
    if realization is None:
        realization = {}
    if not isinstance(realization, dict):
        raise ValueError("detector_feature_generators[].realization must be an object.")

    default_realization_mode = (
        "layered_stack"
        if generator_type == "layered_detector_stack"
        else "placement_array"
        if generator_type in {"tiled_sensor_array", "support_rib_array", "annular_shield_sleeve"}
        else "boolean_subtraction"
    )
    realization_mode = _normalize_non_empty_string(realization.get("mode")) or default_realization_mode
    if realization_mode not in _SUPPORTED_DETECTOR_FEATURE_REALIZATION_MODES:
        raise ValueError(
            "detector_feature_generators[].realization.mode must be one of: "
            + ", ".join(sorted(_SUPPORTED_DETECTOR_FEATURE_REALIZATION_MODES))
            + "."
        )

    realization_status = _normalize_non_empty_string(realization.get("status")) or "spec_only"
    if realization_status not in _SUPPORTED_DETECTOR_FEATURE_REALIZATION_STATUSES:
        raise ValueError(
            "detector_feature_generators[].realization.status must be one of: "
            + ", ".join(sorted(_SUPPORTED_DETECTOR_FEATURE_REALIZATION_STATUSES))
            + "."
        )

    generated_object_refs = realization.get("generated_object_refs", {})
    if generated_object_refs is None:
        generated_object_refs = {}
    if not isinstance(generated_object_refs, dict):
        raise ValueError("detector_feature_generators[].realization.generated_object_refs must be an object.")

    normalized_target = {}
    normalized_pattern = None
    normalized_stack = None
    normalized_array = None
    normalized_layers = None
    normalized_sensor = None
    normalized_rib = None
    normalized_channel = None
    normalized_shield = None
    normalized_hole = None

    if generator_type == "rectangular_drilled_hole_array":
        pitch_mm = pattern.get("pitch_mm", {})
        if not isinstance(pitch_mm, dict):
            raise ValueError("detector_feature_generators[].pattern.pitch_mm must be an object.")

        origin_offset_mm = pattern.get("origin_offset_mm", {})
        if origin_offset_mm is None:
            origin_offset_mm = {}
        if not isinstance(origin_offset_mm, dict):
            raise ValueError("detector_feature_generators[].pattern.origin_offset_mm must be an object.")

        anchor = _normalize_non_empty_string(pattern.get("anchor")) or "target_center"
        if anchor not in _SUPPORTED_DETECTOR_FEATURE_PATTERN_ANCHORS:
            raise ValueError(
                "detector_feature_generators[].pattern.anchor must be one of: "
                + ", ".join(sorted(_SUPPORTED_DETECTOR_FEATURE_PATTERN_ANCHORS))
                + "."
            )

        hole_shape = _normalize_non_empty_string(hole.get("shape")) or "cylindrical"
        if hole_shape not in _SUPPORTED_DETECTOR_FEATURE_HOLE_SHAPES:
            raise ValueError(
                "detector_feature_generators[].hole.shape must be one of: "
                + ", ".join(sorted(_SUPPORTED_DETECTOR_FEATURE_HOLE_SHAPES))
                + "."
            )

        hole_axis = _normalize_non_empty_string(hole.get("axis")) or "z"
        if hole_axis not in _SUPPORTED_DETECTOR_FEATURE_HOLE_AXES:
            raise ValueError(
                "detector_feature_generators[].hole.axis must be one of: "
                + ", ".join(sorted(_SUPPORTED_DETECTOR_FEATURE_HOLE_AXES))
                + "."
            )

        drill_from = _normalize_non_empty_string(hole.get("drill_from")) or "positive_z_face"
        if drill_from not in _SUPPORTED_DETECTOR_FEATURE_DRILL_FROM:
            raise ValueError(
                "detector_feature_generators[].hole.drill_from must be one of: "
                + ", ".join(sorted(_SUPPORTED_DETECTOR_FEATURE_DRILL_FROM))
                + "."
            )

        normalized_target = {
            "solid_ref": _normalize_detector_feature_object_ref(
                target.get("solid_ref"),
                "detector_feature_generators[].target.solid_ref",
                required=True,
            ),
            "logical_volume_refs": _normalize_detector_feature_object_ref_list(
                target.get("logical_volume_refs", []),
                "detector_feature_generators[].target.logical_volume_refs",
            ),
        }
        normalized_pattern = {
            "count_x": _normalize_positive_int(
                pattern.get("count_x"),
                "detector_feature_generators[].pattern.count_x",
            ),
            "count_y": _normalize_positive_int(
                pattern.get("count_y"),
                "detector_feature_generators[].pattern.count_y",
            ),
            "pitch_mm": {
                "x": _normalize_positive_float(
                    pitch_mm.get("x"),
                    "detector_feature_generators[].pattern.pitch_mm.x",
                ),
                "y": _normalize_positive_float(
                    pitch_mm.get("y"),
                    "detector_feature_generators[].pattern.pitch_mm.y",
                ),
            },
            "origin_offset_mm": {
                "x": _normalize_float(
                    origin_offset_mm.get("x"),
                    0.0,
                    "detector_feature_generators[].pattern.origin_offset_mm.x",
                ),
                "y": _normalize_float(
                    origin_offset_mm.get("y"),
                    0.0,
                    "detector_feature_generators[].pattern.origin_offset_mm.y",
                ),
            },
            "anchor": anchor,
        }
        normalized_hole = {
            "shape": hole_shape,
            "diameter_mm": _normalize_positive_float(
                hole.get("diameter_mm"),
                "detector_feature_generators[].hole.diameter_mm",
            ),
            "depth_mm": _normalize_positive_float(
                hole.get("depth_mm"),
                "detector_feature_generators[].hole.depth_mm",
            ),
            "axis": hole_axis,
            "drill_from": drill_from,
        }
    elif generator_type == "circular_drilled_hole_array":
        origin_offset_mm = pattern.get("origin_offset_mm", {})
        if origin_offset_mm is None:
            origin_offset_mm = {}
        if not isinstance(origin_offset_mm, dict):
            raise ValueError("detector_feature_generators[].pattern.origin_offset_mm must be an object.")

        anchor = _normalize_non_empty_string(pattern.get("anchor")) or "target_center"
        if anchor not in _SUPPORTED_DETECTOR_FEATURE_PATTERN_ANCHORS:
            raise ValueError(
                "detector_feature_generators[].pattern.anchor must be one of: "
                + ", ".join(sorted(_SUPPORTED_DETECTOR_FEATURE_PATTERN_ANCHORS))
                + "."
            )

        hole_shape = _normalize_non_empty_string(hole.get("shape")) or "cylindrical"
        if hole_shape not in _SUPPORTED_DETECTOR_FEATURE_HOLE_SHAPES:
            raise ValueError(
                "detector_feature_generators[].hole.shape must be one of: "
                + ", ".join(sorted(_SUPPORTED_DETECTOR_FEATURE_HOLE_SHAPES))
                + "."
            )

        hole_axis = _normalize_non_empty_string(hole.get("axis")) or "z"
        if hole_axis not in _SUPPORTED_DETECTOR_FEATURE_HOLE_AXES:
            raise ValueError(
                "detector_feature_generators[].hole.axis must be one of: "
                + ", ".join(sorted(_SUPPORTED_DETECTOR_FEATURE_HOLE_AXES))
                + "."
            )

        drill_from = _normalize_non_empty_string(hole.get("drill_from")) or "positive_z_face"
        if drill_from not in _SUPPORTED_DETECTOR_FEATURE_DRILL_FROM:
            raise ValueError(
                "detector_feature_generators[].hole.drill_from must be one of: "
                + ", ".join(sorted(_SUPPORTED_DETECTOR_FEATURE_DRILL_FROM))
                + "."
            )

        normalized_target = {
            "solid_ref": _normalize_detector_feature_object_ref(
                target.get("solid_ref"),
                "detector_feature_generators[].target.solid_ref",
                required=True,
            ),
            "logical_volume_refs": _normalize_detector_feature_object_ref_list(
                target.get("logical_volume_refs", []),
                "detector_feature_generators[].target.logical_volume_refs",
            ),
        }
        normalized_pattern = {
            "count": _normalize_positive_int(
                pattern.get("count", pattern.get("hole_count")),
                "detector_feature_generators[].pattern.count",
            ),
            "radius_mm": _normalize_positive_float(
                pattern.get("radius_mm"),
                "detector_feature_generators[].pattern.radius_mm",
            ),
            "orientation_deg": _normalize_float(
                pattern.get("orientation_deg"),
                0.0,
                "detector_feature_generators[].pattern.orientation_deg",
            ),
            "origin_offset_mm": {
                "x": _normalize_float(
                    origin_offset_mm.get("x"),
                    0.0,
                    "detector_feature_generators[].pattern.origin_offset_mm.x",
                ),
                "y": _normalize_float(
                    origin_offset_mm.get("y"),
                    0.0,
                    "detector_feature_generators[].pattern.origin_offset_mm.y",
                ),
            },
            "anchor": anchor,
        }
        normalized_hole = {
            "shape": hole_shape,
            "diameter_mm": _normalize_positive_float(
                hole.get("diameter_mm"),
                "detector_feature_generators[].hole.diameter_mm",
            ),
            "depth_mm": _normalize_positive_float(
                hole.get("depth_mm"),
                "detector_feature_generators[].hole.depth_mm",
            ),
            "axis": hole_axis,
            "drill_from": drill_from,
        }
    elif generator_type == "layered_detector_stack":
        stack_anchor = _normalize_non_empty_string(stack.get("anchor")) or "target_center"
        if stack_anchor not in _SUPPORTED_DETECTOR_FEATURE_PATTERN_ANCHORS:
            raise ValueError(
                "detector_feature_generators[].stack.anchor must be one of: "
                + ", ".join(sorted(_SUPPORTED_DETECTOR_FEATURE_PATTERN_ANCHORS))
                + "."
            )

        module_size_mm = stack.get("module_size_mm", stack.get("size_mm", {}))
        if not isinstance(module_size_mm, dict):
            raise ValueError("detector_feature_generators[].stack.module_size_mm must be an object.")

        origin_offset_mm = stack.get("origin_offset_mm", {})
        if origin_offset_mm is None:
            origin_offset_mm = {}
        if not isinstance(origin_offset_mm, dict):
            raise ValueError("detector_feature_generators[].stack.origin_offset_mm must be an object.")

        normalized_target = {
            "parent_logical_volume_ref": _normalize_detector_feature_object_ref(
                target.get("parent_logical_volume_ref"),
                "detector_feature_generators[].target.parent_logical_volume_ref",
                required=True,
            ),
        }

        normalized_layers = {}
        total_thickness_mm = 0.0
        for role in ("absorber", "sensor", "support"):
            raw_layer = layers.get(role)
            if not isinstance(raw_layer, dict):
                raise ValueError(
                    f"detector_feature_generators[].layers.{role} must be an object."
                )

            normalized_layer = {
                "material_ref": _normalize_detector_feature_material_ref(
                    raw_layer.get("material_ref", raw_layer.get("material")),
                    f"detector_feature_generators[].layers.{role}.material_ref",
                ),
                "thickness_mm": _normalize_positive_float(
                    raw_layer.get("thickness_mm"),
                    f"detector_feature_generators[].layers.{role}.thickness_mm",
                ),
                "is_sensitive": bool(
                    raw_layer.get("is_sensitive", role == "sensor")
                ),
            }
            normalized_layers[role] = normalized_layer
            total_thickness_mm += normalized_layer["thickness_mm"]

        raw_module_pitch_mm = stack.get(
            "module_pitch_mm",
            stack.get("pitch_mm", stack.get("module_spacing_mm")),
        )
        if raw_module_pitch_mm is None:
            module_pitch_mm = total_thickness_mm
        else:
            module_pitch_mm = _normalize_positive_float(
                raw_module_pitch_mm,
                "detector_feature_generators[].stack.module_pitch_mm",
            )

        normalized_stack = {
            "module_size_mm": {
                "x": _normalize_positive_float(
                    module_size_mm.get("x"),
                    "detector_feature_generators[].stack.module_size_mm.x",
                ),
                "y": _normalize_positive_float(
                    module_size_mm.get("y"),
                    "detector_feature_generators[].stack.module_size_mm.y",
                ),
            },
            "module_count": _normalize_positive_int(
                stack.get("module_count", stack.get("module_repeat_count", stack.get("count", 1))),
                "detector_feature_generators[].stack.module_count",
            ),
            "module_pitch_mm": module_pitch_mm,
            "origin_offset_mm": {
                "x": _normalize_float(
                    origin_offset_mm.get("x"),
                    0.0,
                    "detector_feature_generators[].stack.origin_offset_mm.x",
                ),
                "y": _normalize_float(
                    origin_offset_mm.get("y"),
                    0.0,
                    "detector_feature_generators[].stack.origin_offset_mm.y",
                ),
                "z": _normalize_float(
                    origin_offset_mm.get("z"),
                    0.0,
                    "detector_feature_generators[].stack.origin_offset_mm.z",
                ),
            },
            "anchor": stack_anchor,
        }
    elif generator_type == "tiled_sensor_array":
        array_anchor = _normalize_non_empty_string(array.get("anchor")) or "target_center"
        if array_anchor not in _SUPPORTED_DETECTOR_FEATURE_PATTERN_ANCHORS:
            raise ValueError(
                "detector_feature_generators[].array.anchor must be one of: "
                + ", ".join(sorted(_SUPPORTED_DETECTOR_FEATURE_PATTERN_ANCHORS))
                + "."
            )

        pitch_mm = array.get("pitch_mm", {})
        if pitch_mm is None:
            pitch_mm = {}
        if not isinstance(pitch_mm, dict):
            raise ValueError("detector_feature_generators[].array.pitch_mm must be an object.")

        origin_offset_mm = array.get("origin_offset_mm", {})
        if origin_offset_mm is None:
            origin_offset_mm = {}
        if not isinstance(origin_offset_mm, dict):
            raise ValueError("detector_feature_generators[].array.origin_offset_mm must be an object.")

        size_mm = sensor.get("size_mm", sensor.get("tile_size_mm", {}))
        if not isinstance(size_mm, dict):
            raise ValueError("detector_feature_generators[].sensor.size_mm must be an object.")

        sensor_size_x = _normalize_positive_float(
            size_mm.get("x"),
            "detector_feature_generators[].sensor.size_mm.x",
        )
        sensor_size_y = _normalize_positive_float(
            size_mm.get("y"),
            "detector_feature_generators[].sensor.size_mm.y",
        )

        normalized_target = {
            "parent_logical_volume_ref": _normalize_detector_feature_object_ref(
                target.get("parent_logical_volume_ref"),
                "detector_feature_generators[].target.parent_logical_volume_ref",
                required=True,
            ),
        }
        normalized_array = {
            "count_x": _normalize_positive_int(
                array.get("count_x", array.get("columns", array.get("num_x"))),
                "detector_feature_generators[].array.count_x",
            ),
            "count_y": _normalize_positive_int(
                array.get("count_y", array.get("rows", array.get("num_y"))),
                "detector_feature_generators[].array.count_y",
            ),
            "pitch_mm": {
                "x": _normalize_positive_float(
                    pitch_mm.get("x", sensor_size_x),
                    "detector_feature_generators[].array.pitch_mm.x",
                ),
                "y": _normalize_positive_float(
                    pitch_mm.get("y", sensor_size_y),
                    "detector_feature_generators[].array.pitch_mm.y",
                ),
            },
            "origin_offset_mm": {
                "x": _normalize_float(
                    origin_offset_mm.get("x"),
                    0.0,
                    "detector_feature_generators[].array.origin_offset_mm.x",
                ),
                "y": _normalize_float(
                    origin_offset_mm.get("y"),
                    0.0,
                    "detector_feature_generators[].array.origin_offset_mm.y",
                ),
                "z": _normalize_float(
                    origin_offset_mm.get("z"),
                    0.0,
                    "detector_feature_generators[].array.origin_offset_mm.z",
                ),
            },
            "anchor": array_anchor,
        }
        normalized_sensor = {
            "size_mm": {
                "x": sensor_size_x,
                "y": sensor_size_y,
            },
            "thickness_mm": _normalize_positive_float(
                sensor.get("thickness_mm"),
                "detector_feature_generators[].sensor.thickness_mm",
            ),
            "material_ref": _normalize_detector_feature_material_ref(
                sensor.get("material_ref", sensor.get("material")),
                "detector_feature_generators[].sensor.material_ref",
            ),
            "is_sensitive": bool(sensor.get("is_sensitive", True)),
        }
    elif generator_type == "support_rib_array":
        array_anchor = _normalize_non_empty_string(array.get("anchor")) or "target_center"
        if array_anchor not in _SUPPORTED_DETECTOR_FEATURE_PATTERN_ANCHORS:
            raise ValueError(
                "detector_feature_generators[].array.anchor must be one of: "
                + ", ".join(sorted(_SUPPORTED_DETECTOR_FEATURE_PATTERN_ANCHORS))
                + "."
            )

        origin_offset_mm = array.get("origin_offset_mm", {})
        if origin_offset_mm is None:
            origin_offset_mm = {}
        if not isinstance(origin_offset_mm, dict):
            raise ValueError("detector_feature_generators[].array.origin_offset_mm must be an object.")

        repeat_axis = _normalize_non_empty_string(array.get("axis", array.get("repeat_axis")))
        if repeat_axis not in _SUPPORTED_DETECTOR_FEATURE_LINEAR_AXES:
            raise ValueError(
                "detector_feature_generators[].array.axis must be one of: "
                + ", ".join(sorted(_SUPPORTED_DETECTOR_FEATURE_LINEAR_AXES))
                + "."
            )

        normalized_target = {
            "parent_logical_volume_ref": _normalize_detector_feature_object_ref(
                target.get("parent_logical_volume_ref"),
                "detector_feature_generators[].target.parent_logical_volume_ref",
                required=True,
            ),
        }
        normalized_array = {
            "count": _normalize_positive_int(
                array.get("count", array.get("rib_count", array.get("repeat_count"))),
                "detector_feature_generators[].array.count",
            ),
            "linear_pitch_mm": _normalize_positive_float(
                array.get("linear_pitch_mm", array.get("pitch_mm", array.get("pitch"))),
                "detector_feature_generators[].array.linear_pitch_mm",
            ),
            "axis": repeat_axis,
            "origin_offset_mm": {
                "x": _normalize_float(
                    origin_offset_mm.get("x"),
                    0.0,
                    "detector_feature_generators[].array.origin_offset_mm.x",
                ),
                "y": _normalize_float(
                    origin_offset_mm.get("y"),
                    0.0,
                    "detector_feature_generators[].array.origin_offset_mm.y",
                ),
                "z": _normalize_float(
                    origin_offset_mm.get("z"),
                    0.0,
                    "detector_feature_generators[].array.origin_offset_mm.z",
                ),
            },
            "anchor": array_anchor,
        }
        normalized_rib = {
            "width_mm": _normalize_positive_float(
                rib.get("width_mm", rib.get("thickness_mm")),
                "detector_feature_generators[].rib.width_mm",
            ),
            "height_mm": _normalize_positive_float(
                rib.get("height_mm"),
                "detector_feature_generators[].rib.height_mm",
            ),
            "material_ref": _normalize_detector_feature_material_ref(
                rib.get("material_ref", rib.get("material")),
                "detector_feature_generators[].rib.material_ref",
            ),
            "is_sensitive": bool(rib.get("is_sensitive", False)),
        }
    elif generator_type == "channel_cut_array":
        array_anchor = _normalize_non_empty_string(array.get("anchor")) or "target_center"
        if array_anchor not in _SUPPORTED_DETECTOR_FEATURE_PATTERN_ANCHORS:
            raise ValueError(
                "detector_feature_generators[].array.anchor must be one of: "
                + ", ".join(sorted(_SUPPORTED_DETECTOR_FEATURE_PATTERN_ANCHORS))
                + "."
            )

        origin_offset_mm = array.get("origin_offset_mm", {})
        if origin_offset_mm is None:
            origin_offset_mm = {}
        if not isinstance(origin_offset_mm, dict):
            raise ValueError("detector_feature_generators[].array.origin_offset_mm must be an object.")

        repeat_axis = _normalize_non_empty_string(array.get("axis", array.get("repeat_axis")))
        if repeat_axis not in _SUPPORTED_DETECTOR_FEATURE_LINEAR_AXES:
            raise ValueError(
                "detector_feature_generators[].array.axis must be one of: "
                + ", ".join(sorted(_SUPPORTED_DETECTOR_FEATURE_LINEAR_AXES))
                + "."
            )

        normalized_target = {
            "solid_ref": _normalize_detector_feature_object_ref(
                target.get("solid_ref"),
                "detector_feature_generators[].target.solid_ref",
                required=True,
            ),
            "logical_volume_refs": _normalize_detector_feature_object_ref_list(
                target.get("logical_volume_refs", []),
                "detector_feature_generators[].target.logical_volume_refs",
            ),
        }
        normalized_array = {
            "count": _normalize_positive_int(
                array.get("count", array.get("channel_count", array.get("repeat_count"))),
                "detector_feature_generators[].array.count",
            ),
            "linear_pitch_mm": _normalize_positive_float(
                array.get("linear_pitch_mm", array.get("pitch_mm", array.get("pitch"))),
                "detector_feature_generators[].array.linear_pitch_mm",
            ),
            "axis": repeat_axis,
            "origin_offset_mm": {
                "x": _normalize_float(
                    origin_offset_mm.get("x"),
                    0.0,
                    "detector_feature_generators[].array.origin_offset_mm.x",
                ),
                "y": _normalize_float(
                    origin_offset_mm.get("y"),
                    0.0,
                    "detector_feature_generators[].array.origin_offset_mm.y",
                ),
            },
            "anchor": array_anchor,
        }
        normalized_channel = {
            "width_mm": _normalize_positive_float(
                channel.get("width_mm"),
                "detector_feature_generators[].channel.width_mm",
            ),
            "depth_mm": _normalize_positive_float(
                channel.get("depth_mm"),
                "detector_feature_generators[].channel.depth_mm",
            ),
        }
    elif generator_type == "annular_shield_sleeve":
        shield_anchor = _normalize_non_empty_string(shield.get("anchor")) or "target_center"
        if shield_anchor not in _SUPPORTED_DETECTOR_FEATURE_PATTERN_ANCHORS:
            raise ValueError(
                "detector_feature_generators[].shield.anchor must be one of: "
                + ", ".join(sorted(_SUPPORTED_DETECTOR_FEATURE_PATTERN_ANCHORS))
                + "."
            )

        origin_offset_mm = shield.get("origin_offset_mm", {})
        if origin_offset_mm is None:
            origin_offset_mm = {}
        if not isinstance(origin_offset_mm, dict):
            raise ValueError("detector_feature_generators[].shield.origin_offset_mm must be an object.")

        normalized_target = {
            "parent_logical_volume_ref": _normalize_detector_feature_object_ref(
                target.get("parent_logical_volume_ref"),
                "detector_feature_generators[].target.parent_logical_volume_ref",
                required=True,
            ),
        }

        inner_radius_mm = _normalize_positive_float(
            shield.get("inner_radius_mm"),
            "detector_feature_generators[].shield.inner_radius_mm",
        )
        outer_radius_mm = _normalize_positive_float(
            shield.get("outer_radius_mm"),
            "detector_feature_generators[].shield.outer_radius_mm",
        )
        if outer_radius_mm <= inner_radius_mm:
            raise ValueError(
                "detector_feature_generators[].shield.outer_radius_mm must be greater than inner_radius_mm."
            )

        normalized_shield = {
            "inner_radius_mm": inner_radius_mm,
            "outer_radius_mm": outer_radius_mm,
            "length_mm": _normalize_positive_float(
                shield.get("length_mm", shield.get("axial_length_mm")),
                "detector_feature_generators[].shield.length_mm",
            ),
            "material_ref": _normalize_detector_feature_material_ref(
                shield.get("material_ref", shield.get("material")),
                "detector_feature_generators[].shield.material_ref",
            ),
            "origin_offset_mm": {
                "x": _normalize_float(
                    origin_offset_mm.get("x"),
                    0.0,
                    "detector_feature_generators[].shield.origin_offset_mm.x",
                ),
                "y": _normalize_float(
                    origin_offset_mm.get("y"),
                    0.0,
                    "detector_feature_generators[].shield.origin_offset_mm.y",
                ),
                "z": _normalize_float(
                    origin_offset_mm.get("z"),
                    0.0,
                    "detector_feature_generators[].shield.origin_offset_mm.z",
                ),
            },
            "anchor": shield_anchor,
        }
    else:
        raise ValueError(
            "detector feature generator type must be one of: "
            + ", ".join(sorted(_SUPPORTED_DETECTOR_FEATURE_GENERATOR_TYPES))
            + "."
        )

    default_name = f"{generator_type}_{generator_id.split('_')[-1][:8]}"
    normalized_entry = {
        "generator_id": generator_id,
        "name": _normalize_non_empty_string(raw_entry.get("name")) or default_name,
        "schema_version": schema_version,
        "generator_type": generator_type,
        "enabled": enabled,
        "target": normalized_target,
        "realization": {
            "mode": realization_mode,
            "status": realization_status,
            "result_solid_ref": _normalize_detector_feature_object_ref(
                realization.get("result_solid_ref"),
                "detector_feature_generators[].realization.result_solid_ref",
                required=False,
            ),
            "generated_object_refs": {
                "solid_refs": _normalize_detector_feature_object_ref_list(
                    generated_object_refs.get("solid_refs", []),
                    "detector_feature_generators[].realization.generated_object_refs.solid_refs",
                ),
                "logical_volume_refs": _normalize_detector_feature_object_ref_list(
                    generated_object_refs.get("logical_volume_refs", []),
                    "detector_feature_generators[].realization.generated_object_refs.logical_volume_refs",
                ),
                "placement_refs": _normalize_detector_feature_object_ref_list(
                    generated_object_refs.get("placement_refs", []),
                    "detector_feature_generators[].realization.generated_object_refs.placement_refs",
                ),
            },
        },
    }

    if normalized_pattern is not None:
        normalized_entry["pattern"] = normalized_pattern
    if normalized_hole is not None:
        normalized_entry["hole"] = normalized_hole
    if normalized_stack is not None:
        normalized_entry["stack"] = normalized_stack
    if normalized_array is not None:
        normalized_entry["array"] = normalized_array
    if normalized_layers is not None:
        normalized_entry["layers"] = normalized_layers
    if normalized_sensor is not None:
        normalized_entry["sensor"] = normalized_sensor
    if normalized_rib is not None:
        normalized_entry["rib"] = normalized_rib
    if normalized_channel is not None:
        normalized_entry["channel"] = normalized_channel
    if normalized_shield is not None:
        normalized_entry["shield"] = normalized_shield

    return normalized_entry


def _normalize_detector_feature_generators(raw_generators):
    if not isinstance(raw_generators, list):
        return []

    normalized_generators = []
    seen_generator_ids = set()
    for index, raw_entry in enumerate(raw_generators):
        try:
            normalized_entry = _normalize_detector_feature_generator_entry(raw_entry)
        except ValueError as exc:
            print(f"Warning: Skipping detector feature generator at index {index}: {exc}")
            continue

        generator_id = normalized_entry["generator_id"]
        if generator_id in seen_generator_ids:
            print(
                "Warning: Skipping detector feature generator at index "
                f"{index}: duplicate generator_id '{generator_id}'."
            )
            continue

        seen_generator_ids.add(generator_id)
        normalized_generators.append(normalized_entry)

    return normalized_generators


def normalize_detector_feature_generator_entry(raw_entry):
    """Public wrapper for validating one detector-feature-generator contract."""
    return _normalize_detector_feature_generator_entry(raw_entry)

class Define:
    """Represents a defined entity like position, rotation, or constant."""
    def __init__(self, name, type, raw_expression, unit=None, category=None):
        self.id = str(uuid.uuid4())
        self.name = name
        self.type = type # 'position', 'rotation', 'constant', 'quantity'
        self.raw_expression = raw_expression # holds the user-entered string or dict of strings
        self.unit = unit
        self.category = category
        self.value = None # holds the final, evaluated numeric result

    def to_dict(self):
        return {
            "id": self.id, "name": self.name, "type": self.type,
            "raw_expression": self.raw_expression,
            "value": self.value, # The evaluated value
            "unit": self.unit, "category": self.category
        }

    @classmethod
    def from_dict(cls, data):
        # In new projects, raw_expression might be missing, so we create it from value
        raw_expr = data.get('raw_expression')
        if raw_expr is None:
            print(f"Warning: Reconstructing raw_expression for define '{data.get('name')}'. This may lose original units/expressions.")
            val = data.get('value')
            if isinstance(val, dict):
                 raw_expr = {k: str(v) for k, v in val.items()}
            else:
                 raw_expr = str(val) if val is not None else '0'

        instance = cls(data['name'], data['type'], raw_expr, data.get('unit'), data.get('category'))
        instance.id = data.get('id', str(uuid.uuid4()))
        instance.value = data.get('value') # Restore evaluated value too
        return instance

class Element:
    """Represents a chemical element, composed of isotopes or defined by Z."""
    def __init__(self, name, formula=None, Z=None, A_expr=None, components=None):
        self.id = str(uuid.uuid4())
        self.name = name
        self.formula = formula
        self.Z = Z # Atomic Number
        self.A_expr = A_expr # Atomic Mass (for simple elements)
        self.components = components if components else [] # For elements made of isotopes

    def to_dict(self):
        return {
            "id": self.id, "name": self.name, "formula": self.formula,
            "Z": self.Z, "A_expr": self.A_expr, "components": self.components
        }

    @classmethod
    def from_dict(cls, data):
        instance = cls(data['name'], data.get('formula'), data.get('Z'),
                       data.get('A_expr'), data.get('components'))
        instance.id = data.get('id', instance.id)
        return instance

class Isotope:
    """Represents a chemical isotope."""
    def __init__(self, name, N, Z, A_expr=None):
        self.id = str(uuid.uuid4())
        self.name = name
        self.N = N # Number of nucleons
        self.Z = Z # Atomic Number
        self.A_expr = A_expr # Atomic Mass

    def to_dict(self):
        return {
            "id": self.id, "name": self.name, "N": self.N,
            "Z": self.Z, "A_expr": self.A_expr
        }

    @classmethod
    def from_dict(cls, data):
        instance = cls(data['name'], data.get('N'), data.get('Z'), data.get('A_expr'))
        instance.id = data.get('id', instance.id)
        return instance

class Material:
    """Represents a material."""
    def __init__(self, name, mat_type='standard', Z_expr=None, A_expr=None, density_expr="0.0", state=None, components=None):
        self.id = str(uuid.uuid4())
        self.name = name
        self.mat_type = mat_type
        
        # --- Store raw expressions ---
        self.Z_expr = Z_expr
        self.A_expr = A_expr 
        self.density_expr = density_expr

        # --- Store evaluated results ---
        self._evaluated_Z = None
        self._evaluated_A = None
        self._evaluated_density = None

        self.state = state 
        self.components = components if components else [] 

    def to_dict(self):
        return {
            "id": self.id, "name": self.name, "mat_type": self.mat_type,
            "Z_expr": self.Z_expr, 
            "A_expr": self.A_expr,
            "density_expr": self.density_expr, 
            "_evaluated_Z": self._evaluated_Z,
            "_evaluated_A": self._evaluated_A,
            "_evaluated_density": self._evaluated_density,
            "state": self.state, 
            "components": self.components
        }

    @classmethod
    def from_dict(cls, data):

        name = data['name']

        # A material is considered NIST if its name starts with G4_ AND
        # it has no other defining properties in the dictionary.
        is_nist_name = name.startswith("G4_")
        has_no_components = not data.get('components')
        has_no_z = not data.get('Z') and not data.get('Z_expr')
        
        material_type = 'nist' if is_nist_name and has_no_components and has_no_z else 'standard'
        
        instance = cls(
            name=name, 
            mat_type=data.get('mat_type', material_type),
            Z_expr=data.get('Z_expr', str(data.get('Z', ""))), 
            A_expr=data.get('A_expr', str(data.get('A', ""))), 
            density_expr=data.get('density_expr', str(data.get('density', "0.0"))), 
            state=data.get('state'), 
            components=data.get('components')
        )
        instance.id = data.get('id', str(uuid.uuid4()))
        
        # Restore evaluated values if they exist
        instance._evaluated_Z = data.get('_evaluated_Z')
        instance._evaluated_A = data.get('_evaluated_A')
        instance._evaluated_density = data.get('_evaluated_density')
        
        return instance

class Solid:
    """Base class for solids. Parameters should be in internal units (e.g., mm)."""
    def __init__(self, name, solid_type, raw_parameters):
        self.id = str(uuid.uuid4())
        self.name = name
        self.type = solid_type

        # This dictionary holds the string expressions from the user or GDML file.
        self.raw_parameters = raw_parameters
        ## This dictionary will hold the final numeric values for rendering.
        self._evaluated_parameters = {}

    def to_dict(self):
        return {
            "id": self.id, "name": self.name, "type": self.type,
            "raw_parameters": self.raw_parameters,
            "_evaluated_parameters": self._evaluated_parameters
        }

    @classmethod
    def from_dict(cls, data):
        raw_params = data.get('raw_parameters', {})
        instance = cls(data['name'], data['type'], raw_params)
        instance.id = data.get('id', str(uuid.uuid4()))
        instance._evaluated_parameters = data.get('_evaluated_parameters', {})
        return instance

class LogicalVolume:
    """Represents a logical volume."""
    def __init__(self, name, solid_ref, material_ref, vis_attributes=None, is_sensitive=False):
        self.id = str(uuid.uuid4())
        self.name = name
        self.solid_ref = solid_ref # Name/ID of the Solid object
        self.material_ref = material_ref # Name/ID of the Material object
        self.vis_attributes = vis_attributes if vis_attributes is not None else {'color': {'r':0.8, 'g':0.8, 'b':0.8, 'a':1.0}}
        self.is_sensitive = is_sensitive

        # Unified content model for LVs
        self.content_type = 'physvol'  # Default to standard placements
        self.content = []              # If type is 'physvol', this is a list of PhysicalVolumePlacement
                                       # If another type, this will hold a single procedural object

    def add_child(self, placement):
        if isinstance(placement, PhysicalVolumePlacement):
            if self.content_type == 'physvol':
                self.content.append(placement)
        else: # It's a ReplicaVolume, DivisionVolume, etc.
            self.content_type = placement.type
            self.content = placement # Store the single object

    def to_dict(self):
        content_data = None
        if self.content_type == 'physvol':
            content_data = [child.to_dict() for child in self.content]
        elif self.content: # For replica, division, etc.
            content_data = self.content.to_dict()

        return {
            "id": self.id, "name": self.name,
            "solid_ref": self.solid_ref,
            "material_ref": self.material_ref,
            "vis_attributes": self.vis_attributes,
            "is_sensitive": self.is_sensitive,
            "content_type": self.content_type, 
            "content": content_data           
        }

    @classmethod
    def from_dict(cls, data, all_objects_map=None):
        instance = cls(
            data['name'], 
            data['solid_ref'], 
            data['material_ref'], 
            data.get('vis_attributes'),
            data.get('is_sensitive', False)
        )
        instance.id = data.get('id', str(uuid.uuid4()))
        instance.content_type = data.get('content_type', 'physvol')
        
        content_data = data.get('content')

        if instance.content_type == 'physvol' and isinstance(content_data, list):
            instance.content = [PhysicalVolumePlacement.from_dict(p) for p in content_data]
        elif content_data and isinstance(content_data, dict):
            # This block handles all single procedural volume objects
            if instance.content_type == 'replica':
                instance.content = ReplicaVolume.from_dict(content_data)
            elif instance.content_type == 'division':
                instance.content = DivisionVolume.from_dict(content_data)
            elif instance.content_type == 'parameterised':
                instance.content = ParamVolume.from_dict(content_data)
            else:
                # If it's a dict but an unknown type, log a warning but don't crash.
                print(f"Warning: Unknown procedural content type '{instance.content_type}' for LV '{instance.name}'. Content will be empty.")
                instance.content = []
                instance.content_type = 'physvol'
        else:
            # Fallback for empty or invalid content
            instance.content = []
            instance.content_type = 'physvol'
        
        return instance


class PhysicalVolumePlacement:
    """Represents a physical volume placement (physvol)."""
    def __init__(self, name, volume_ref, parent_lv_name = None, copy_number_expr="0",
                 position_val_or_ref=None, rotation_val_or_ref=None, scale_val_or_ref=None):
        self.id = str(uuid.uuid4())
        self.name = name
        self.volume_ref = volume_ref
        self.parent_lv_name = parent_lv_name
        ## Store copy number as a raw string expression
        self.copy_number_expr = copy_number_expr
        # This will store the final evaluated integer result
        self.copy_number = 0 # Default to 0
        # This stores the raw data: either a define name (string) 
        # or a dictionary of string expressions for absolute values
        self.position = position_val_or_ref
        self.rotation = rotation_val_or_ref
        self.scale = scale_val_or_ref
        # These will store the final numeric results after evaluation
        self._evaluated_position = {'x': 0, 'y': 0, 'z': 0}
        self._evaluated_rotation = {'x': 0, 'y': 0, 'z': 0}
        self._evaluated_scale = {'x': 1, 'y': 1, 'z': 1}

    # Function to clone the PV for Assembly placements
    def clone(self):
        # Creates a shallow copy. This is sufficient as we only modify the ID and parent.
        # The referenced objects (position, rotation dicts) can be shared.
        new_pv = PhysicalVolumePlacement(
            name=self.name,
            volume_ref=self.volume_ref,
            parent_lv_name=self.parent_lv_name,
            copy_number_expr=self.copy_number_expr,
            position_val_or_ref=self.position,
            rotation_val_or_ref=self.rotation,
            scale_val_or_ref=self.scale
        )
        # Copy evaluated properties as well
        new_pv.id = self.id
        new_pv._evaluated_position = self._evaluated_position.copy()
        new_pv._evaluated_rotation = self._evaluated_rotation.copy()
        new_pv._evaluated_scale = self._evaluated_scale.copy()
        new_pv.copy_number = self.copy_number
        
        return new_pv
    
    def get_transform_matrix(self):
        """
        Returns a 4x4 numpy transformation matrix for this placement,
        applying scale, then rotation, then translation.
        """
        pos = self._evaluated_position
        rot = self._evaluated_rotation
        scl = self._evaluated_scale

        # Create Translation Matrix (T)
        T = np.array([[1, 0, 0, pos['x']],
                      [0, 1, 0, pos['y']],
                      [0, 0, 1, pos['z']],
                      [0, 0, 0, 1]])

        # MODIFIED: Negate the angles to match the visual convention expected
        # by Geant4's GDML parser's application order.
        rx = rot['x']
        ry = rot['y']
        rz = rot['z']

        Rx = np.array([[1, 0, 0], [0, math.cos(rx), -math.sin(rx)], [0, math.sin(rx), math.cos(rx)]])
        Ry = np.array([[math.cos(ry), 0, math.sin(ry)], [0, 1, 0], [-math.sin(ry), 0, math.cos(ry)]])
        Rz = np.array([[math.cos(rz), -math.sin(rz), 0], [math.sin(rz), math.cos(rz), 0], [0, 0, 1]])

        # The correct composition for intrinsic ZYX is R = Rz * Ry * Rx
        R_3x3 = Rz @ Ry @ Rx
        
        R = np.eye(4)
        R[:3, :3] = R_3x3
        
        # Create Scaling Matrix (S)
        S = np.array([[scl['x'], 0, 0, 0],
                      [0, scl['y'], 0, 0],
                      [0, 0, scl['z'], 0],
                      [0, 0, 0, 1]])
        
        # Combine them: Final Transform = T * R * S
        return T @ R @ S
    
    @staticmethod
    def decompose_matrix(matrix):
        """Decomposes a 4x4 numpy matrix into position, rotation (rad), and scale dicts."""
        # Position is straightforward
        position = {'x': matrix[0, 3], 'y': matrix[1, 3], 'z': matrix[2, 3]}

        # Extract rotation matrix part
        R = matrix[:3, :3]
        
        # Decompose scale and rotation
        # Note: This simple method assumes no shear.
        sx = np.linalg.norm(R[:, 0])
        sy = np.linalg.norm(R[:, 1])
        sz = np.linalg.norm(R[:, 2])
        scale = {'x': sx, 'y': sy, 'z': sz}

        # Normalize rotation matrix to remove scaling
        Rs = np.array([R[:, 0]/sx, R[:, 1]/sy, R[:, 2]/sz]).T

        # Calculate Euler angles (ZYX order)
        sy_val = math.sqrt(Rs[0,0] * Rs[0,0] +  Rs[1,0] * Rs[1,0])
        singular = sy_val < 1e-6

        if not singular:
            x = math.atan2(Rs[2,1] , Rs[2,2])
            y = math.atan2(-Rs[2,0], sy_val)
            z = math.atan2(Rs[1,0], Rs[0,0])
        else:
            x = math.atan2(-Rs[1,2], Rs[1,1])
            y = math.atan2(-Rs[2,0], sy_val)
            z = 0
            
        rotation = {'x': x, 'y': y, 'z': z}

        return position, rotation, scale

    def to_dict(self):
        return {
            "id": self.id, "name": self.name, "volume_ref": self.volume_ref, 
            "copy_number_expr": self.copy_number_expr,
            "copy_number": self.copy_number,
            "position": self.position, "rotation": self.rotation, "scale": self.scale,
            "parent_lv_name": self.parent_lv_name,
            "_evaluated_position": self._evaluated_position, 
            "_evaluated_rotation": self._evaluated_rotation, 
            "_evaluated_scale": self._evaluated_scale
        }

    @classmethod
    def from_dict(cls, data, all_objects_map=None):
        copy_expr = data.get('copy_number_expr', str(data.get('copy_number', '0')))
        instance = cls(
            data['name'], data['volume_ref'], data.get('parent_lv_name'), copy_expr,
            data.get('position'), data.get('rotation'), data.get('scale')
        )
        instance.id = data.get('id', str(uuid.uuid4()))
        instance.copy_number = data.get('copy_number', 0)
        instance._evaluated_position = data.get('_evaluated_position', {'x':0, 'y':0, 'z':0})
        instance._evaluated_rotation = data.get('_evaluated_rotation', {'x':0, 'y':0, 'z':0})
        instance._evaluated_scale = data.get('_evaluated_scale', {'x':1, 'y':1, 'z':1})
        return instance

class Assembly:
    """Represents a collection of placed logical volumes."""
    def __init__(self, name):
        self.id = str(uuid.uuid4())
        self.name = name
        self.placements = [] # List of PhysicalVolumePlacement objects

    def add_placement(self, placement):
        self.placements.append(placement)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "placements": [p.to_dict() for p in self.placements]
        }
    
    @classmethod
    def from_dict(cls, data):
        instance = cls(data['name'])
        instance.id = data.get('id', str(uuid.uuid4()))
        instance.placements = [PhysicalVolumePlacement.from_dict(p) for p in data.get('placements', [])]
        return instance

class DivisionVolume:
    """Represents a <divisionvol> placement."""
    def __init__(self, name, volume_ref, axis, number=0, width=0.0, offset=0.0, unit="mm"):
        self.id = str(uuid.uuid4())
        self.name = name  # Not in GDML spec, but useful for our UI
        self.type = "division"
        self.volume_ref = volume_ref
        self.axis = axis # kXAxis, kYAxis, etc.
        self.number = number # Raw expression string
        self.width = width   # Raw expression string
        self.offset = offset # Raw expression string
        self.unit = unit
        # Add placeholders for evaluated values
        self._evaluated_number = 0
        self._evaluated_width = 0.0
        self._evaluated_offset = 0.0

    def to_dict(self):
        return {
            "id": self.id, "name": self.name, "type": self.type,
            "volume_ref": self.volume_ref, "axis": self.axis,
            "number": self.number, "width": self.width, "offset": self.offset,
            "unit": self.unit
        }
    
    @classmethod
    def from_dict(cls, data):
        # We assume name will be generated if not present
        name = data.get('name', f"division_{data.get('id', uuid.uuid4().hex[:6])}")
        return cls(name, data['volume_ref'], data['axis'], data.get('number'), 
                   data.get('width'), data.get('offset'), data.get('unit'))

class ReplicaVolume:
    """Represents a <replicavol> placement."""
    def __init__(self, name, volume_ref, number, direction, width=0.0, offset=0.0, start_position=None, start_rotation=None):
        self.id = str(uuid.uuid4())
        self.name = name
        self.type = "replica"
        self.volume_ref = volume_ref
        self.direction = direction
        self.number = number     # Raw expression string
        self.width = width       # Raw expression string
        self.offset = offset     # Raw expression string
        self.start_position = start_position if start_position is not None else {'x': '0', 'y': '0', 'z': '0'}
        self.start_rotation = start_rotation if start_rotation is not None else {'x': '0', 'y': '0', 'z': '0'}
        # Add placeholders for all evaluated values
        self._evaluated_number = 0
        self._evaluated_width = 0.0
        self._evaluated_offset = 0.0
        self._evaluated_start_position = {'x': 0, 'y': 0, 'z': 0}
        self._evaluated_start_rotation = {'x': 0, 'y': 0, 'z': 0}

    def to_dict(self):
        return {
            "id": self.id, "name": self.name, "type": self.type,
            "volume_ref": self.volume_ref, "number": self.number,
            "direction": self.direction, "width": self.width, "offset": self.offset,
            "start_position": self.start_position, "start_rotation": self.start_rotation
        }

    @classmethod
    def from_dict(cls, data):
        """Creates a ReplicaVolume instance from a dictionary."""
        # A name might not be present in the data from the frontend, so we generate one.
        name = data.get('name', f"replica_{data.get('id', uuid.uuid4().hex[:6])}")
        
        # Ensure default values are handled correctly if keys are missing
        number = data.get('number', "1")
        direction = data.get('direction', {'x': '1', 'y': '0', 'z': '0'})
        width = data.get('width', "0.0")
        offset = data.get('offset', "0.0")
        start_position = data.get('start_position')
        start_rotation = data.get('start_rotation')
        volume_ref = data.get('volume_ref')
        if not volume_ref:
            # This would be an invalid state, but we can handle it gracefully.
            raise ValueError("ReplicaVolume content data is missing 'volume_ref'")

        instance = cls(name, volume_ref, number, direction, width, offset, start_position, start_rotation)
        instance.id = data.get('id', instance.id) # Use provided ID if it exists
        return instance

class Parameterisation:
    """Represents a single <parameters> block for a parameterised volume."""
    def __init__(self, number, position, dimensions_type, dimensions, rotation=None):
        self.number = number
        self.position = position
        self.rotation = rotation if rotation is not None else {'x': '0', 'y': '0', 'z': '0'}
        self.dimensions_type = dimensions_type # e.g., "box_dimensions"
        self.dimensions = dimensions # A dict of the dimension attrs, e.g. {'x':'10', 'y':'10'}

        self._evaluated_position = {'x': 0, 'y': 0, 'z': 0}
        self._evaluated_rotation = {'x': 0, 'y': 0, 'z': 0}
        self._evaluated_dimensions = {}

    def to_dict(self):
        return {
            "number": self.number,
            "position": self.position,
            "rotation": self.rotation,
            "dimensions_type": self.dimensions_type,
            "dimensions": self.dimensions
        }

    @classmethod
    def from_dict(cls, data):
        # The constructor needs all arguments. We provide defaults if they are missing.
        return cls(
            number=data.get('number'),
            position=data.get('position'),
            dimensions_type=data.get('dimensions_type'),
            dimensions=data.get('dimensions'),
            rotation=data.get('rotation') # This might be None, and that's okay
        )

class ParamVolume:
    """Represents a <paramvol> placement."""
    def __init__(self, name, volume_ref, ncopies):
        self.id = str(uuid.uuid4())
        self.name = name
        self.type = "parameterised"
        self.volume_ref = volume_ref
        self.ncopies = ncopies
        self.parameters = [] # This will be a list of Parameterisation objects

        self._evaluated_ncopies = 0

    def add_parameter_set(self, param_set):
        self.parameters.append(param_set)

    def to_dict(self):
        return {
            "id": self.id, "name": self.name, "type": self.type,
            "volume_ref": self.volume_ref, "ncopies": self.ncopies,
            "parameters": [p.to_dict() for p in self.parameters]
        }

    @classmethod
    def from_dict(cls, data):
        # The name is not in the content block, but passed separately.
        # We can use a placeholder.
        name = data.get('name', f"param_{uuid.uuid4().hex[:6]}")
        instance = cls(name, data.get('volume_ref'), data.get('ncopies'))
        
        # Deserialize the list of parameter blocks
        param_data_list = data.get('parameters', [])
        instance.parameters = [Parameterisation.from_dict(p_data) for p_data in param_data_list]
        
        # Ensure ID is preserved if it exists
        if 'id' in data:
            instance.id = data['id']

        return instance

class OpticalSurface:
    """Represents an <opticalsurface> property set."""
    def __init__(self, name, model='glisur', finish='polished', surf_type='dielectric_dielectric', value='1.0'):
        self.id = str(uuid.uuid4())
        self.name = name
        self.model = model
        self.finish = finish
        self.type = surf_type
        self.value = value
        self.properties = {} # Dict to hold property vectors, e.g., {'REFLECTIVITY': 'reflectivity_matrix'}

    def to_dict(self):
        return {
            "id": self.id, "name": self.name, "model": self.model,
            "finish": self.finish, "type": self.type, "value": self.value,
            "properties": self.properties
        }

    @classmethod
    def from_dict(cls, data):
        instance = cls(data['name'], data.get('model', 'glisur'), data.get('finish', 'polished'),
                       data.get('type', 'dielectric_dielectric'), data.get('value', '1.0'))
        instance.id = data.get('id', instance.id)
        instance.properties = data.get('properties', {})
        return instance

class SkinSurface:
    """Represents a <skinsurface> link."""
    def __init__(self, name, volume_ref, surfaceproperty_ref):
        self.id = str(uuid.uuid4())
        self.name = name
        self.type = "skin" # For UI identification
        self.volume_ref = volume_ref # Name of the LogicalVolume
        self.surfaceproperty_ref = surfaceproperty_ref # Name of the OpticalSurface

    def to_dict(self):
        return {
            "id": self.id, "name": self.name, "type": self.type,
            "volume_ref": self.volume_ref,
            "surfaceproperty_ref": self.surfaceproperty_ref
        }

    @classmethod
    def from_dict(cls, data):
        instance = cls(data['name'], data['volume_ref'], data['surfaceproperty_ref'])
        instance.id = data.get('id', instance.id)
        return instance

class BorderSurface:
    """Represents a <bordersurface> link."""
    def __init__(self, name, physvol1_ref, physvol2_ref, surfaceproperty_ref):
        self.id = str(uuid.uuid4())
        self.name = name
        self.type = "border" # For UI identification
        self.physvol1_ref = physvol1_ref # ID of the first PhysicalVolumePlacement
        self.physvol2_ref = physvol2_ref # ID of the second PhysicalVolumePlacement
        self.surfaceproperty_ref = surfaceproperty_ref # Name of the OpticalSurface

    def to_dict(self):
        return {
            "id": self.id, "name": self.name, "type": self.type,
            "physvol1_ref": self.physvol1_ref,
            "physvol2_ref": self.physvol2_ref,
            "surfaceproperty_ref": self.surfaceproperty_ref
        }

    @classmethod
    def from_dict(cls, data):
        instance = cls(data['name'], data['physvol1_ref'], data['physvol2_ref'], data['surfaceproperty_ref'])
        instance.id = data.get('id', instance.id)
        return instance
    
class ParticleSource:
    """Represents a particle source (G4GeneralParticleSource) in the project."""
    def __init__(self, name, gps_commands=None, position=None, rotation=None, vis_attributes=None, activity=1.0, confine_to_pv=None, volume_link_id=None):
        self.id = str(uuid.uuid4())
        self.name = name
        self.type = "gps" # To distinguish from other potential source types later
        
        # Store the raw GPS commands as a dictionary for easy editing
        self.gps_commands = gps_commands if gps_commands is not None else {}

        # Store the position separately for easy access by the transform gizmo
        self.position = position if position is not None else {'x': '0', 'y': '0', 'z': '0'}
        self.rotation = rotation if rotation is not None else {'x': '0', 'y': '0', 'z': '0'}
        
        # Activity in Becquerels (default to 1.0 Bq if not specified).
        # For non-bound sources or relative comparisons, this acts as a relative weight.
        self.activity = activity

        # Optional: Confine source to a specific physical volume (by Name)
        self.confine_to_pv = confine_to_pv
        
        # Optional: Link to a Physical Volume ID (UUID) for UI tracking/syncing
        self.volume_link_id = volume_link_id

        # Evaluated position for rendering
        self._evaluated_position = {'x': 0, 'y': 0, 'z': 0}
        self._evaluated_rotation = {'x': 0, 'y': 0, 'z': 0}

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "gps_commands": self.gps_commands,
            "position": self.position,
            "rotation": self.rotation,
            "activity": self.activity,
            "confine_to_pv": self.confine_to_pv,
            "volume_link_id": self.volume_link_id,
            "_evaluated_position": self._evaluated_position,
            "_evaluated_rotation": self._evaluated_rotation,
        }

    @classmethod
    def from_dict(cls, data):
        # Handle legacy 'intensity' field by mapping it to activity if activity is missing
        activity = data.get('activity')
        if activity is None:
            activity = data.get('intensity', 1.0)
            
        instance = cls(
            data['name'],
            data.get('gps_commands', {}),
            data.get('position', {'x': '0', 'y': '0', 'z': '0'}),
            data.get('rotation', {'x': '0', 'y': '0', 'z': '0'}),
            activity=activity,
            confine_to_pv=data.get('confine_to_pv'),
            volume_link_id=data.get('volume_link_id')
        )
        instance.id = data.get('id', str(uuid.uuid4()))
        instance._evaluated_position = data.get('_evaluated_position', {'x': 0, 'y': 0, 'z': 0})
        instance._evaluated_rotation = data.get('_evaluated_rotation', {'x': 0, 'y': 0, 'z': 0})
        return instance

def _default_uniform_field_vector():
    return {'x': 0.0, 'y': 0.0, 'z': 0.0}


def _normalize_uniform_field_vector(raw_vector, field_name, vector_field_name):
    if raw_vector is None:
        return _default_uniform_field_vector()

    if not isinstance(raw_vector, dict):
        raise ValueError(f"{field_name}.{vector_field_name} must be an object with x/y/z.")

    normalized = _default_uniform_field_vector()
    for axis in ('x', 'y', 'z'):
        try:
            value = float(raw_vector.get(axis, normalized[axis]))
        except (TypeError, ValueError):
            raise ValueError(f"{field_name}.{vector_field_name}.{axis} must be a finite number.")
        if not math.isfinite(value):
            raise ValueError(f"{field_name}.{vector_field_name}.{axis} must be a finite number.")
        normalized[axis] = value

    return normalized


def _validate_uniform_field_vector(data, field_name, vector_field_name):
    vector = data.get(vector_field_name)
    if vector is not None:
        if not isinstance(vector, dict):
            return False, f"{field_name}.{vector_field_name} must be an object with x/y/z."
        for axis in ('x', 'y', 'z'):
            try:
                value = float(vector.get(axis, 0.0))
            except (TypeError, ValueError):
                return False, f"{field_name}.{vector_field_name}.{axis} must be a finite number."
            if not math.isfinite(value):
                return False, f"{field_name}.{vector_field_name}.{axis} must be a finite number."

    return True, None


def _coerce_target_volume_names(raw_names, field_name):
    if raw_names is None:
        return []

    if isinstance(raw_names, str):
        raw_items = re.split(r"[,\n;]+", raw_names)
    elif isinstance(raw_names, (list, tuple, set)):
        raw_items = list(raw_names)
    else:
        raise ValueError(f"{field_name}.target_volume_names must be an array of strings.")

    normalized = []
    seen = set()
    for raw_item in raw_items:
        name = str(raw_item).strip()
        if not name or name in seen:
            continue
        normalized.append(name)
        seen.add(name)

    return normalized


def _normalize_finite_number(raw_value, field_name, property_name):
    try:
        numeric_value = float(raw_value)
    except (TypeError, ValueError):
        raise ValueError(f"{field_name}.{property_name} must be a finite number.")

    if not math.isfinite(numeric_value):
        raise ValueError(f"{field_name}.{property_name} must be a finite number.")

    return numeric_value


def _validate_finite_number(data, field_name, property_name, default_value=0.0):
    value = data.get(property_name, default_value)
    try:
        numeric_value = float(value)
    except (TypeError, ValueError):
        return False, f"{field_name}.{property_name} must be a finite number."

    if not math.isfinite(numeric_value):
        return False, f"{field_name}.{property_name} must be a finite number."

    return True, None


class GlobalUniformMagneticField:
    """Saved-project contract for a global uniform magnetic field."""

    ENVIRONMENT_FIELD_NAME = "environment.global_uniform_magnetic_field"
    FIELD_VECTOR_NAME = "field_vector_tesla"

    def __init__(self, enabled=False, field_vector_tesla=None):
        if not isinstance(enabled, bool):
            raise ValueError("environment.global_uniform_magnetic_field.enabled must be a boolean.")

        self.enabled = enabled
        self.field_vector_tesla = _normalize_uniform_field_vector(
            field_vector_tesla,
            self.ENVIRONMENT_FIELD_NAME,
            self.FIELD_VECTOR_NAME,
        )

    @classmethod
    def validate(cls, data, field_name=ENVIRONMENT_FIELD_NAME):
        if data is None:
            return True, None
        if not isinstance(data, dict):
            return False, f"{field_name} must be an object."

        enabled = data.get('enabled', False)
        if not isinstance(enabled, bool):
            return False, f"{field_name}.enabled must be a boolean."

        return _validate_uniform_field_vector(data, field_name, cls.FIELD_VECTOR_NAME)

    def to_dict(self):
        return {
            "enabled": self.enabled,
            "field_vector_tesla": dict(self.field_vector_tesla),
        }

    @classmethod
    def from_dict(cls, data):
        if data is None:
            return cls()

        ok, err = cls.validate(data)
        if not ok:
            raise ValueError(err)

        return cls(
            enabled=data.get('enabled', False),
            field_vector_tesla=data.get('field_vector_tesla'),
        )


class GlobalUniformElectricField:
    """Saved-project contract for a global uniform electric field."""

    ENVIRONMENT_FIELD_NAME = "environment.global_uniform_electric_field"
    FIELD_VECTOR_NAME = "field_vector_volt_per_meter"

    def __init__(self, enabled=False, field_vector_volt_per_meter=None):
        if not isinstance(enabled, bool):
            raise ValueError("environment.global_uniform_electric_field.enabled must be a boolean.")

        self.enabled = enabled
        self.field_vector_volt_per_meter = _normalize_uniform_field_vector(
            field_vector_volt_per_meter,
            self.ENVIRONMENT_FIELD_NAME,
            self.FIELD_VECTOR_NAME,
        )

    @classmethod
    def validate(cls, data, field_name=ENVIRONMENT_FIELD_NAME):
        if data is None:
            return True, None
        if not isinstance(data, dict):
            return False, f"{field_name} must be an object."

        enabled = data.get('enabled', False)
        if not isinstance(enabled, bool):
            return False, f"{field_name}.enabled must be a boolean."

        return _validate_uniform_field_vector(data, field_name, cls.FIELD_VECTOR_NAME)

    def to_dict(self):
        return {
            "enabled": self.enabled,
            "field_vector_volt_per_meter": dict(self.field_vector_volt_per_meter),
        }

    @classmethod
    def from_dict(cls, data):
        if data is None:
            return cls()

        ok, err = cls.validate(data)
        if not ok:
            raise ValueError(err)

        return cls(
            enabled=data.get('enabled', False),
            field_vector_volt_per_meter=data.get('field_vector_volt_per_meter'),
        )


class LocalUniformMagneticField:
    """Saved-project contract for a local uniform magnetic field assignment."""

    ENVIRONMENT_FIELD_NAME = "environment.local_uniform_magnetic_field"
    FIELD_VECTOR_NAME = "field_vector_tesla"

    def __init__(self, enabled=False, target_volume_names=None, field_vector_tesla=None):
        if not isinstance(enabled, bool):
            raise ValueError("environment.local_uniform_magnetic_field.enabled must be a boolean.")

        self.enabled = enabled
        self.target_volume_names = self._normalize_target_volume_names(target_volume_names)
        self.field_vector_tesla = _normalize_uniform_field_vector(
            field_vector_tesla,
            self.ENVIRONMENT_FIELD_NAME,
            self.FIELD_VECTOR_NAME,
        )

    @staticmethod
    def _coerce_target_volume_names(raw_names):
        return _coerce_target_volume_names(
            raw_names,
            "environment.local_uniform_magnetic_field",
        )

    @classmethod
    def _normalize_target_volume_names(cls, raw_names):
        return cls._coerce_target_volume_names(raw_names)

    @classmethod
    def validate(cls, data, field_name="environment.local_uniform_magnetic_field"):
        if data is None:
            return True, None
        if not isinstance(data, dict):
            return False, f"{field_name} must be an object."

        enabled = data.get('enabled', False)
        if not isinstance(enabled, bool):
            return False, f"{field_name}.enabled must be a boolean."

        target_names = data.get('target_volume_names')
        if target_names is not None:
            try:
                cls._coerce_target_volume_names(target_names)
            except ValueError:
                return False, f"{field_name}.target_volume_names must be an array of strings."

        return _validate_uniform_field_vector(data, field_name, cls.FIELD_VECTOR_NAME)

    def to_dict(self):
        return {
            "enabled": self.enabled,
            "target_volume_names": list(self.target_volume_names),
            "field_vector_tesla": dict(self.field_vector_tesla),
        }

    @classmethod
    def from_dict(cls, data):
        if data is None:
            return cls()

        ok, err = cls.validate(data)
        if not ok:
            raise ValueError(err)

        return cls(
            enabled=data.get('enabled', False),
            target_volume_names=data.get('target_volume_names'),
            field_vector_tesla=data.get('field_vector_tesla'),
        )


class LocalUniformElectricField:
    """Saved-project contract for a local uniform electric field assignment."""

    ENVIRONMENT_FIELD_NAME = "environment.local_uniform_electric_field"
    FIELD_VECTOR_NAME = "field_vector_volt_per_meter"

    def __init__(self, enabled=False, target_volume_names=None, field_vector_volt_per_meter=None):
        if not isinstance(enabled, bool):
            raise ValueError("environment.local_uniform_electric_field.enabled must be a boolean.")

        self.enabled = enabled
        self.target_volume_names = self._normalize_target_volume_names(target_volume_names)
        self.field_vector_volt_per_meter = _normalize_uniform_field_vector(
            field_vector_volt_per_meter,
            self.ENVIRONMENT_FIELD_NAME,
            self.FIELD_VECTOR_NAME,
        )

    @staticmethod
    def _coerce_target_volume_names(raw_names):
        return _coerce_target_volume_names(
            raw_names,
            "environment.local_uniform_electric_field",
        )

    @classmethod
    def _normalize_target_volume_names(cls, raw_names):
        return cls._coerce_target_volume_names(raw_names)

    @classmethod
    def validate(cls, data, field_name="environment.local_uniform_electric_field"):
        if data is None:
            return True, None
        if not isinstance(data, dict):
            return False, f"{field_name} must be an object."

        enabled = data.get('enabled', False)
        if not isinstance(enabled, bool):
            return False, f"{field_name}.enabled must be a boolean."

        target_names = data.get('target_volume_names')
        if target_names is not None:
            try:
                cls._coerce_target_volume_names(target_names)
            except ValueError:
                return False, f"{field_name}.target_volume_names must be an array of strings."

        return _validate_uniform_field_vector(data, field_name, cls.FIELD_VECTOR_NAME)

    def to_dict(self):
        return {
            "enabled": self.enabled,
            "target_volume_names": list(self.target_volume_names),
            "field_vector_volt_per_meter": dict(self.field_vector_volt_per_meter),
        }

    @classmethod
    def from_dict(cls, data):
        if data is None:
            return cls()

        ok, err = cls.validate(data)
        if not ok:
            raise ValueError(err)

        return cls(
            enabled=data.get('enabled', False),
            target_volume_names=data.get('target_volume_names'),
            field_vector_volt_per_meter=data.get('field_vector_volt_per_meter'),
        )


class RegionCutsAndLimits:
    """Saved-project contract for region-specific production cuts and user limits."""

    ENVIRONMENT_FIELD_NAME = "environment.region_cuts_and_limits"
    DEFAULT_REGION_NAME = "airpet_region"
    ENVIRONMENT_STRING_PROPERTIES = {"region_name"}
    ENVIRONMENT_NUMERIC_PROPERTIES = {
        "production_cut_mm": 1.0,
        "max_step_mm": 0.0,
        "max_track_length_mm": 0.0,
        "max_time_ns": 0.0,
        "min_kinetic_energy_mev": 0.0,
        "min_range_mm": 0.0,
    }

    def __init__(
        self,
        enabled=False,
        region_name=None,
        target_volume_names=None,
        production_cut_mm=1.0,
        max_step_mm=0.0,
        max_track_length_mm=0.0,
        max_time_ns=0.0,
        min_kinetic_energy_mev=0.0,
        min_range_mm=0.0,
    ):
        if not isinstance(enabled, bool):
            raise ValueError("environment.region_cuts_and_limits.enabled must be a boolean.")

        self.enabled = enabled
        self.region_name = self._normalize_region_name(region_name)
        self.target_volume_names = self._normalize_target_volume_names(target_volume_names)
        self.production_cut_mm = _normalize_finite_number(
            production_cut_mm,
            self.ENVIRONMENT_FIELD_NAME,
            "production_cut_mm",
        )
        self.max_step_mm = _normalize_finite_number(
            max_step_mm,
            self.ENVIRONMENT_FIELD_NAME,
            "max_step_mm",
        )
        self.max_track_length_mm = _normalize_finite_number(
            max_track_length_mm,
            self.ENVIRONMENT_FIELD_NAME,
            "max_track_length_mm",
        )
        self.max_time_ns = _normalize_finite_number(
            max_time_ns,
            self.ENVIRONMENT_FIELD_NAME,
            "max_time_ns",
        )
        self.min_kinetic_energy_mev = _normalize_finite_number(
            min_kinetic_energy_mev,
            self.ENVIRONMENT_FIELD_NAME,
            "min_kinetic_energy_mev",
        )
        self.min_range_mm = _normalize_finite_number(
            min_range_mm,
            self.ENVIRONMENT_FIELD_NAME,
            "min_range_mm",
        )

    @staticmethod
    def _normalize_region_name(raw_name):
        if raw_name is None:
            return RegionCutsAndLimits.DEFAULT_REGION_NAME

        name = str(raw_name).strip()
        return name or RegionCutsAndLimits.DEFAULT_REGION_NAME

    @staticmethod
    def _coerce_target_volume_names(raw_names):
        return _coerce_target_volume_names(
            raw_names,
            RegionCutsAndLimits.ENVIRONMENT_FIELD_NAME,
        )

    @classmethod
    def _normalize_target_volume_names(cls, raw_names):
        return cls._coerce_target_volume_names(raw_names)

    @classmethod
    def validate(cls, data, field_name=ENVIRONMENT_FIELD_NAME):
        if data is None:
            return True, None
        if not isinstance(data, dict):
            return False, f"{field_name} must be an object."

        enabled = data.get('enabled', False)
        if not isinstance(enabled, bool):
            return False, f"{field_name}.enabled must be a boolean."

        region_name = data.get('region_name', cls.DEFAULT_REGION_NAME)
        if not isinstance(region_name, str) or not region_name.strip():
            return False, f"{field_name}.region_name must be a non-empty string."

        target_names = data.get('target_volume_names')
        if target_names is not None:
            try:
                cls._coerce_target_volume_names(target_names)
            except ValueError:
                return False, f"{field_name}.target_volume_names must be an array of strings."

        for property_name, default_value in cls.ENVIRONMENT_NUMERIC_PROPERTIES.items():
            ok, err = _validate_finite_number(data, field_name, property_name, default_value)
            if not ok:
                return ok, err

        return True, None

    def to_dict(self):
        return {
            "enabled": self.enabled,
            "region_name": self.region_name,
            "target_volume_names": list(self.target_volume_names),
            "production_cut_mm": self.production_cut_mm,
            "max_step_mm": self.max_step_mm,
            "max_track_length_mm": self.max_track_length_mm,
            "max_time_ns": self.max_time_ns,
            "min_kinetic_energy_mev": self.min_kinetic_energy_mev,
            "min_range_mm": self.min_range_mm,
        }

    @classmethod
    def from_dict(cls, data):
        if data is None:
            return cls()

        ok, err = cls.validate(data)
        if not ok:
            raise ValueError(err)

        return cls(
            enabled=data.get('enabled', False),
            region_name=data.get('region_name', cls.DEFAULT_REGION_NAME),
            target_volume_names=data.get('target_volume_names'),
            production_cut_mm=data.get('production_cut_mm', 1.0),
            max_step_mm=data.get('max_step_mm', 0.0),
            max_track_length_mm=data.get('max_track_length_mm', 0.0),
            max_time_ns=data.get('max_time_ns', 0.0),
            min_kinetic_energy_mev=data.get('min_kinetic_energy_mev', 0.0),
            min_range_mm=data.get('min_range_mm', 0.0),
        )

class EnvironmentState:
    """Saved-project environment state shared by UI, AI, and runtime plumbing."""

    @staticmethod
    def _summary_number(value):
        try:
            return f"{float(value):g}"
        except (TypeError, ValueError):
            return str(value)

    @classmethod
    def _summary_vector(cls, vector, unit_label):
        vector = vector if isinstance(vector, dict) else {}
        return (
            f"({cls._summary_number(vector.get('x', 0.0))}, "
            f"{cls._summary_number(vector.get('y', 0.0))}, "
            f"{cls._summary_number(vector.get('z', 0.0))}) {unit_label}"
        )

    def __init__(
        self,
        global_uniform_magnetic_field=None,
        global_uniform_electric_field=None,
        local_uniform_magnetic_field=None,
        local_uniform_electric_field=None,
        region_cuts_and_limits=None,
    ):
        if isinstance(global_uniform_magnetic_field, GlobalUniformMagneticField):
            self.global_uniform_magnetic_field = global_uniform_magnetic_field
        else:
            self.global_uniform_magnetic_field = GlobalUniformMagneticField.from_dict(global_uniform_magnetic_field)

        if isinstance(global_uniform_electric_field, GlobalUniformElectricField):
            self.global_uniform_electric_field = global_uniform_electric_field
        else:
            self.global_uniform_electric_field = GlobalUniformElectricField.from_dict(global_uniform_electric_field)

        if isinstance(local_uniform_magnetic_field, LocalUniformMagneticField):
            self.local_uniform_magnetic_field = local_uniform_magnetic_field
        else:
            self.local_uniform_magnetic_field = LocalUniformMagneticField.from_dict(local_uniform_magnetic_field)

        if isinstance(local_uniform_electric_field, LocalUniformElectricField):
            self.local_uniform_electric_field = local_uniform_electric_field
        else:
            self.local_uniform_electric_field = LocalUniformElectricField.from_dict(local_uniform_electric_field)

        if isinstance(region_cuts_and_limits, RegionCutsAndLimits):
            self.region_cuts_and_limits = region_cuts_and_limits
        else:
            self.region_cuts_and_limits = RegionCutsAndLimits.from_dict(region_cuts_and_limits)

    @classmethod
    def validate(cls, data, field_name="environment"):
        if data is None:
            return True, None
        if not isinstance(data, dict):
            return False, f"{field_name} must be an object."

        field_data = data.get('global_uniform_magnetic_field')
        if field_data is None and 'global_magnetic_field' in data:
            field_data = data.get('global_magnetic_field')

        ok, err = GlobalUniformMagneticField.validate(
            field_data,
            field_name=f"{field_name}.global_uniform_magnetic_field",
        )
        if not ok:
            return ok, err

        electric_field_data = data.get('global_uniform_electric_field')
        if electric_field_data is None and 'global_electric_field' in data:
            electric_field_data = data.get('global_electric_field')

        ok, err = GlobalUniformElectricField.validate(
            electric_field_data,
            field_name=f"{field_name}.global_uniform_electric_field",
        )
        if not ok:
            return ok, err

        local_field_data = data.get('local_uniform_magnetic_field')
        if local_field_data is None and 'local_magnetic_field' in data:
            local_field_data = data.get('local_magnetic_field')

        ok, err = LocalUniformMagneticField.validate(
            local_field_data,
            field_name=f"{field_name}.local_uniform_magnetic_field",
        )
        if not ok:
            return ok, err

        local_electric_field_data = data.get('local_uniform_electric_field')
        if local_electric_field_data is None and 'local_electric_field' in data:
            local_electric_field_data = data.get('local_electric_field')

        ok, err = LocalUniformElectricField.validate(
            local_electric_field_data,
            field_name=f"{field_name}.local_uniform_electric_field",
        )
        if not ok:
            return ok, err

        region_controls_data = data.get('region_cuts_and_limits')
        if region_controls_data is None and 'region_controls' in data:
            region_controls_data = data.get('region_controls')

        return RegionCutsAndLimits.validate(
            region_controls_data,
            field_name=f"{field_name}.region_cuts_and_limits",
        )

    def to_dict(self):
        return {
            "global_uniform_magnetic_field": self.global_uniform_magnetic_field.to_dict(),
            "global_uniform_electric_field": self.global_uniform_electric_field.to_dict(),
            "local_uniform_magnetic_field": self.local_uniform_magnetic_field.to_dict(),
            "local_uniform_electric_field": self.local_uniform_electric_field.to_dict(),
            "region_cuts_and_limits": self.region_cuts_and_limits.to_dict(),
        }

    def to_summary_dict(self):
        active_controls = []

        def add_control(kind, label, description, state):
            active_controls.append({
                "kind": kind,
                "label": label,
                "description": description,
                "state": state,
            })

        global_magnetic_field = self.global_uniform_magnetic_field
        if global_magnetic_field.enabled:
            add_control(
                "global_uniform_magnetic_field",
                "Global magnetic field",
                f"Global magnetic field: {self._summary_vector(global_magnetic_field.field_vector_tesla, 'T')}",
                global_magnetic_field.to_dict(),
            )

        global_electric_field = self.global_uniform_electric_field
        if global_electric_field.enabled:
            add_control(
                "global_uniform_electric_field",
                "Global electric field",
                f"Global electric field: {self._summary_vector(global_electric_field.field_vector_volt_per_meter, 'V/m')}",
                global_electric_field.to_dict(),
            )

        local_magnetic_field = self.local_uniform_magnetic_field
        if local_magnetic_field.enabled:
            targets = ", ".join(local_magnetic_field.target_volume_names) or "(no targets)"
            add_control(
                "local_uniform_magnetic_field",
                "Local magnetic field",
                f"Local magnetic field: targets {targets}, {self._summary_vector(local_magnetic_field.field_vector_tesla, 'T')}",
                local_magnetic_field.to_dict(),
            )

        local_electric_field = self.local_uniform_electric_field
        if local_electric_field.enabled:
            targets = ", ".join(local_electric_field.target_volume_names) or "(no targets)"
            add_control(
                "local_uniform_electric_field",
                "Local electric field",
                f"Local electric field: targets {targets}, {self._summary_vector(local_electric_field.field_vector_volt_per_meter, 'V/m')}",
                local_electric_field.to_dict(),
            )

        region_controls = self.region_cuts_and_limits
        if region_controls.enabled:
            targets = ", ".join(region_controls.target_volume_names) or "(no targets)"
            add_control(
                "region_cuts_and_limits",
                "Region cuts and limits",
                (
                    f"Region cuts and limits: region {region_controls.region_name}, targets {targets}, "
                    f"cut {self._summary_number(region_controls.production_cut_mm)} mm, "
                    f"max step {self._summary_number(region_controls.max_step_mm)} mm, "
                    f"max track {self._summary_number(region_controls.max_track_length_mm)} mm, "
                    f"max time {self._summary_number(region_controls.max_time_ns)} ns, "
                    f"min Ek {self._summary_number(region_controls.min_kinetic_energy_mev)} MeV, "
                    f"min range {self._summary_number(region_controls.min_range_mm)} mm"
                ),
                region_controls.to_dict(),
            )

        summary_text = "No environment controls enabled."
        if active_controls:
            summary_text = "; ".join(control["description"] for control in active_controls)

        return {
            "has_active_controls": bool(active_controls),
            "active_control_count": len(active_controls),
            "summary_text": summary_text,
            "active_controls": active_controls,
        }

    @classmethod
    def from_dict(cls, data):
        if data is None:
            return cls()

        if not isinstance(data, dict):
            print("Warning: Environment payload is not an object. Using defaults.")
            return cls()

        field_data = data.get('global_uniform_magnetic_field')
        if field_data is None and 'global_magnetic_field' in data:
            field_data = data.get('global_magnetic_field')
        electric_field_data = data.get('global_uniform_electric_field')
        if electric_field_data is None and 'global_electric_field' in data:
            electric_field_data = data.get('global_electric_field')
        local_field_data = data.get('local_uniform_magnetic_field')
        if local_field_data is None and 'local_magnetic_field' in data:
            local_field_data = data.get('local_magnetic_field')
        local_electric_field_data = data.get('local_uniform_electric_field')
        if local_electric_field_data is None and 'local_electric_field' in data:
            local_electric_field_data = data.get('local_electric_field')
        region_controls_data = data.get('region_cuts_and_limits')
        if region_controls_data is None and 'region_controls' in data:
            region_controls_data = data.get('region_controls')

        try:
            field = GlobalUniformMagneticField.from_dict(field_data)
        except ValueError as exc:
            print(f"Warning: Invalid global uniform magnetic field payload: {exc}. Using defaults.")
            field = GlobalUniformMagneticField()

        try:
            electric_field = GlobalUniformElectricField.from_dict(electric_field_data)
        except ValueError as exc:
            print(f"Warning: Invalid global uniform electric field payload: {exc}. Using defaults.")
            electric_field = GlobalUniformElectricField()

        try:
            local_field = LocalUniformMagneticField.from_dict(local_field_data)
        except ValueError as exc:
            print(f"Warning: Invalid local uniform magnetic field payload: {exc}. Using defaults.")
            local_field = LocalUniformMagneticField()

        try:
            local_electric_field = LocalUniformElectricField.from_dict(local_electric_field_data)
        except ValueError as exc:
            print(f"Warning: Invalid local uniform electric field payload: {exc}. Using defaults.")
            local_electric_field = LocalUniformElectricField()

        try:
            region_cuts_and_limits = RegionCutsAndLimits.from_dict(region_controls_data)
        except ValueError as exc:
            print(f"Warning: Invalid region cuts and limits payload: {exc}. Using defaults.")
            region_cuts_and_limits = RegionCutsAndLimits()

        return cls(field, electric_field, local_field, local_electric_field, region_cuts_and_limits)


class ScoringState:
    """Saved-project scoring and run-control contract shared by UI, AI, and runtime plumbing."""

    def __init__(
        self,
        schema_version=SCORING_STATE_SCHEMA_VERSION,
        scoring_meshes=None,
        tally_requests=None,
        run_manifest_defaults=None,
    ):
        self.schema_version = schema_version
        self.scoring_meshes = [deepcopy(entry) for entry in (scoring_meshes or [])]
        self.tally_requests = [deepcopy(entry) for entry in (tally_requests or [])]
        self.run_manifest_defaults = deepcopy(
            run_manifest_defaults if run_manifest_defaults is not None else _default_scoring_run_manifest_defaults()
        )

    @classmethod
    def validate(cls, data, field_name="scoring"):
        if data is None:
            return True, None
        if not isinstance(data, dict):
            return False, f"{field_name} must be an object."

        try:
            _normalize_positive_int(
                data.get("schema_version", SCORING_STATE_SCHEMA_VERSION),
                f"{field_name}.schema_version",
            )
            scoring_meshes_raw = data.get("scoring_meshes", [])
            if scoring_meshes_raw is None:
                scoring_meshes_raw = []
            if not isinstance(scoring_meshes_raw, list):
                raise ValueError(f"{field_name}.scoring_meshes must be an array.")

            scoring_meshes = []
            seen_mesh_ids = set()
            for index, raw_entry in enumerate(scoring_meshes_raw):
                normalized_entry = _normalize_scoring_mesh_entry(raw_entry)
                mesh_id = normalized_entry["mesh_id"]
                if mesh_id in seen_mesh_ids:
                    raise ValueError(
                        f"{field_name}.scoring_meshes[{index}].mesh_id duplicates '{mesh_id}'."
                    )
                seen_mesh_ids.add(mesh_id)
                scoring_meshes.append(normalized_entry)

            mesh_lookup = _build_scoring_mesh_lookup(scoring_meshes)
            tally_requests_raw = data.get("tally_requests", [])
            if tally_requests_raw is None:
                tally_requests_raw = []
            if not isinstance(tally_requests_raw, list):
                raise ValueError(f"{field_name}.tally_requests must be an array.")

            seen_tally_ids = set()
            for index, raw_entry in enumerate(tally_requests_raw):
                normalized_entry = _normalize_scoring_tally_request_entry(
                    raw_entry,
                    mesh_lookup=mesh_lookup,
                )
                tally_id = normalized_entry["tally_id"]
                if tally_id in seen_tally_ids:
                    raise ValueError(
                        f"{field_name}.tally_requests[{index}].tally_id duplicates '{tally_id}'."
                    )
                seen_tally_ids.add(tally_id)

            _normalize_scoring_run_manifest_defaults(data.get("run_manifest_defaults"))
        except ValueError as exc:
            return False, str(exc)

        return True, None

    def to_dict(self):
        return {
            "schema_version": self.schema_version,
            "scoring_meshes": [deepcopy(entry) for entry in self.scoring_meshes],
            "tally_requests": [deepcopy(entry) for entry in self.tally_requests],
            "run_manifest_defaults": deepcopy(self.run_manifest_defaults),
        }

    def resolve_run_manifest(self, overrides=None):
        candidate = deepcopy(self.run_manifest_defaults)
        if isinstance(overrides, dict):
            for key in candidate.keys():
                if key in overrides:
                    candidate[key] = overrides.get(key)
        return _normalize_scoring_run_manifest_defaults(candidate)

    def to_summary_dict(self):
        enabled_meshes = [entry for entry in self.scoring_meshes if entry.get("enabled", True)]
        enabled_tallies = [entry for entry in self.tally_requests if entry.get("enabled", True)]
        default_run_manifest = _default_scoring_run_manifest_defaults()
        has_run_manifest_overrides = self.run_manifest_defaults != default_run_manifest

        summary_parts = []
        if self.scoring_meshes:
            summary_parts.append(
                f"{len(enabled_meshes)} of {len(self.scoring_meshes)} scoring mesh(es) enabled"
            )
        else:
            summary_parts.append("No scoring meshes configured")

        if self.tally_requests:
            summary_parts.append(
                f"{len(enabled_tallies)} of {len(self.tally_requests)} tally request(s) enabled"
            )
        else:
            summary_parts.append("No tally requests configured")

        if has_run_manifest_overrides:
            summary_parts.append(
                "Run manifest defaults: "
                f"{self.run_manifest_defaults.get('events', 0)} event(s), "
                f"{self.run_manifest_defaults.get('threads', 0)} thread(s)"
            )
        else:
            summary_parts.append("Run manifest defaults unchanged")

        return {
            "has_configured_scoring": bool(enabled_meshes or enabled_tallies),
            "scoring_mesh_count": len(self.scoring_meshes),
            "enabled_scoring_mesh_count": len(enabled_meshes),
            "tally_request_count": len(self.tally_requests),
            "enabled_tally_request_count": len(enabled_tallies),
            "has_run_manifest_overrides": has_run_manifest_overrides,
            "run_manifest_defaults": deepcopy(self.run_manifest_defaults),
            "summary_text": "; ".join(summary_parts),
        }

    @classmethod
    def from_dict(cls, data):
        if data is None:
            return cls()

        if not isinstance(data, dict):
            print("Warning: Scoring payload is not an object. Using defaults.")
            return cls()

        try:
            schema_version = _normalize_positive_int(
                data.get("schema_version", SCORING_STATE_SCHEMA_VERSION),
                "scoring.schema_version",
            )
        except ValueError as exc:
            print(f"Warning: Invalid scoring schema_version: {exc}. Using defaults.")
            schema_version = SCORING_STATE_SCHEMA_VERSION

        try:
            scoring_meshes = _normalize_scoring_meshes(data.get("scoring_meshes", []))
        except ValueError as exc:
            print(f"Warning: Invalid scoring meshes payload: {exc}. Using defaults.")
            scoring_meshes = []

        mesh_lookup = _build_scoring_mesh_lookup(scoring_meshes)
        try:
            tally_requests = _normalize_scoring_tally_requests(
                data.get("tally_requests", []),
                mesh_lookup=mesh_lookup,
            )
        except ValueError as exc:
            print(f"Warning: Invalid scoring tally payload: {exc}. Using defaults.")
            tally_requests = []

        try:
            run_manifest_defaults = _normalize_scoring_run_manifest_defaults(
                data.get("run_manifest_defaults")
            )
        except ValueError as exc:
            print(f"Warning: Invalid scoring run manifest defaults: {exc}. Using defaults.")
            run_manifest_defaults = _default_scoring_run_manifest_defaults()

        return cls(
            schema_version=schema_version,
            scoring_meshes=scoring_meshes,
            tally_requests=tally_requests,
            run_manifest_defaults=run_manifest_defaults,
        )

class GeometryState:
    """Holds the entire geometry definition."""
    def __init__(self, world_volume_ref=None):
        self.defines = {} # name: Define object
        self.materials = {} # name: Material object
        self.elements = {}  # name: Element object
        self.isotopes = {}  # name: Isotope object
        self.solids = {}    # name: Solid object
        self.logical_volumes = {} # name: LogicalVolume object
        self.assemblies = {} # name: Assembly object
        self.world_volume_ref = world_volume_ref # Name of the world LogicalVolume
        self.environment = EnvironmentState()
        self.scoring = ScoringState()

        # Dictionaries for surface properties
        self.optical_surfaces = {}
        self.skin_surfaces = {}
        self.border_surfaces = {}

        # To hold radioactive sources
        self.sources = {}
        # Changed from single ID to list of IDs for multiple active sources
        self.active_source_ids = [] 

        # Parameter registry for M3 studies/optimization.
        # Format:
        # {
        #   'param_name': {
        #       'name': 'param_name',
        #       'target_type': 'define|solid|source|sim_option',
        #       'target_ref': {...},
        #       'bounds': {'min': x, 'max': y},
        #       'default': x,
        #       'units': 'mm',
        #       'enabled': True,
        #       'constraint_group': None,
        #   }
        # }
        self.parameter_registry = {}

        # Parametric study definitions (M3).
        # {
        #   'study_name': {
        #       'name': 'study_name',
        #       'mode': 'grid|random',
        #       'parameters': ['p1', 'p2'],
        #       'grid': {'steps': 3, 'per_parameter_steps': {'p1': 5}},
        #       'random': {'samples': 20, 'seed': 42},
        #   }
        # }
        self.param_studies = {}

        # Optimizer run history/provenance (M3 classical optimizer).
        # {
        #   '<run_id>': {
        #       'run_id': ..., 'study_name': ..., 'method': ..., 'seed': ...,
        #       'budget': ..., 'objective': ..., 'best_run': {...}, 'candidates': [...]
        #   }
        # }
        self.optimizer_runs = {}

        # Provenance records for imported CAD subsystems.
        self.cad_imports = []

        # Saved detector-oriented feature generator contracts and realized outputs.
        self.detector_feature_generators = []

        # Stable project scope identifier used by policy/audit systems to
        # associate records with this project instance across save/load cycles.
        self.project_scope_id = str(uuid.uuid4())

        # --- Dictionary to hold UI grouping information ---
        # Format: { 'solids': [{'name': 'MyCrystals', 'members': ['solid1_name', 'solid2_name']}], ... }
        self.ui_groups = {
            'define': [],
            'material': [],
            'element': [],
            'solid': [],
            'logical_volume': [],
            'assembly': [],
            'optical_surface': [], 
            'skin_surface': [], 
            'border_surface': []
        }

    def add_define(self, define_obj):
        self.defines[define_obj.name] = define_obj
    def add_material(self, material_obj):
        self.materials[material_obj.name] = material_obj
    def add_element(self, element_obj):
        self.elements[element_obj.name] = element_obj
    def add_isotope(self, isotope_obj):
        self.isotopes[isotope_obj.name] = isotope_obj
    def add_solid(self, solid_obj):
        self.solids[solid_obj.name] = solid_obj
    def add_logical_volume(self, lv_obj):
        self.logical_volumes[lv_obj.name] = lv_obj
    def add_assembly(self, assembly_obj):
        self.assemblies[assembly_obj.name] = assembly_obj
    def add_optical_surface(self, surf_obj):
        self.optical_surfaces[surf_obj.name] = surf_obj
    def add_skin_surface(self, surf_obj):
        self.skin_surfaces[surf_obj.name] = surf_obj
    def add_border_surface(self, surf_obj):
        self.border_surfaces[surf_obj.name] = surf_obj
    def add_source(self, source_obj):
        self.sources[source_obj.name] = source_obj
    
    def to_dict(self):
        return {
            "defines": {k: v.to_dict() for k, v in self.defines.items()},
            "materials": {k: v.to_dict() for k, v in self.materials.items()},
            "elements": {k: v.to_dict() for k, v in self.elements.items()},
            "isotopes": {k: v.to_dict() for k, v in self.isotopes.items()},
            "solids": {k: v.to_dict() for k, v in self.solids.items()},
            "logical_volumes": {k: v.to_dict() for k, v in self.logical_volumes.items()},
            "assemblies": {k: v.to_dict() for k, v in self.assemblies.items()},
            "world_volume_ref": self.world_volume_ref,
            "environment": self.environment.to_dict(),
            "scoring": self.scoring.to_dict(),
            "optical_surfaces": {k: v.to_dict() for k, v in self.optical_surfaces.items()},
            "skin_surfaces": {k: v.to_dict() for k, v in self.skin_surfaces.items()},
            "border_surfaces": {k: v.to_dict() for k, v in self.border_surfaces.items()},
            "sources": {k: v.to_dict() for k, v in self.sources.items()},
            "active_source_ids": self.active_source_ids,
            "parameter_registry": self.parameter_registry,
            "param_studies": self.param_studies,
            "optimizer_runs": self.optimizer_runs,
            "cad_imports": deepcopy(self.cad_imports),
            "detector_feature_generators": deepcopy(self.detector_feature_generators),
            "project_scope_id": self.project_scope_id,
            "ui_groups": self.ui_groups
        }

    @classmethod
    def from_dict(cls, data):
        instance = cls(data.get('world_volume_ref'))
        
        # Helper to safely load dicts
        def load_objects(key, cls_type, target_dict):
            for k, v in data.get(key, {}).items():
                try:
                    target_dict[k] = cls_type.from_dict(v)
                except Exception as e:
                    print(f"Error loading {key} '{k}': {e}")

        load_objects('defines', Define, instance.defines)
        load_objects('materials', Material, instance.materials)
        load_objects('elements', Element, instance.elements)
        load_objects('isotopes', Isotope, instance.isotopes)
        load_objects('solids', Solid, instance.solids)
        load_objects('logical_volumes', LogicalVolume, instance.logical_volumes)
        load_objects('assemblies', Assembly, instance.assemblies)
        load_objects('optical_surfaces', OpticalSurface, instance.optical_surfaces)
        load_objects('skin_surfaces', SkinSurface, instance.skin_surfaces)
        load_objects('border_surfaces', BorderSurface, instance.border_surfaces)
        load_objects('sources', ParticleSource, instance.sources)
        instance.environment = EnvironmentState.from_dict(data.get('environment'))
        instance.scoring = ScoringState.from_dict(data.get('scoring'))
        legacy_environment = {}
        for legacy_key in (
            'global_uniform_magnetic_field',
            'global_uniform_electric_field',
            'local_uniform_magnetic_field',
            'local_uniform_electric_field',
            'region_cuts_and_limits',
        ):
            if data.get(legacy_key) is not None:
                legacy_environment[legacy_key] = data.get(legacy_key)

        if legacy_environment and data.get('environment') is None:
            instance.environment = EnvironmentState.from_dict(legacy_environment)

        # Migration: Handle legacy active_source_id (single string)
        legacy_id = data.get('active_source_id')
        new_ids = data.get('active_source_ids')
        
        if new_ids is not None:
            instance.active_source_ids = new_ids
        elif legacy_id:
            instance.active_source_ids = [legacy_id]
        else:
            instance.active_source_ids = []

        registry = data.get('parameter_registry', {})
        if isinstance(registry, dict):
            instance.parameter_registry = registry
        else:
            instance.parameter_registry = {}

        param_studies = data.get('param_studies', {})
        if isinstance(param_studies, dict):
            instance.param_studies = param_studies
        else:
            instance.param_studies = {}

        optimizer_runs = data.get('optimizer_runs', {})
        if isinstance(optimizer_runs, dict):
            instance.optimizer_runs = optimizer_runs
        else:
            instance.optimizer_runs = {}

        cad_imports = data.get('cad_imports', [])
        if isinstance(cad_imports, list):
            instance.cad_imports = [deepcopy(entry) for entry in cad_imports if isinstance(entry, dict)]
        else:
            instance.cad_imports = []

        instance.detector_feature_generators = _normalize_detector_feature_generators(
            data.get('detector_feature_generators', [])
        )

        project_scope_id = data.get('project_scope_id')
        if isinstance(project_scope_id, str) and project_scope_id.strip():
            instance.project_scope_id = project_scope_id.strip()
        else:
            instance.project_scope_id = str(uuid.uuid4())

        instance.ui_groups = data.get('ui_groups', instance.ui_groups)

        return instance
        
    def get_define(self, name): return self.defines.get(name)
    def get_material(self, name): return self.materials.get(name)
    def get_element(self, name): return self.elements.get(name)
    def get_isotope(self, name): return self.isotopes.get(name)
    def get_solid(self, name): return self.solids.get(name)
    def get_logical_volume(self, name): return self.logical_volumes.get(name)
    def get_assembly(self, name): return self.assemblies.get(name)
    def get_optical_surface(self, name): return self.optical_surfaces.get(name)
    def get_skin_surface(self, name): return self.skin_surfaces.get(name)
    def get_border_surface(self, name): return self.border_surfaces.get(name)
    def get_source(self, name): return self.sources.get(name)

    def get_threejs_scene_description(self):
        if not self.world_volume_ref or self.world_volume_ref not in self.logical_volumes:
            return []
        
        threejs_objects = []
        world_lv = self.get_logical_volume(self.world_volume_ref)

        # Add the world volume itself as a conceptual object (it won't be rendered)
        # We give it a known, stable ID.
        world_pv_id = "WORLD_PV_ID"
        threejs_objects.append({
            "id": world_pv_id,
            "name": world_lv.name,
            "parent_id": None,
            "is_world_volume_placement": True, # A flag to tell the frontend not to render it
            "volume_ref": self.world_volume_ref,
            "position": {'x': 0, 'y': 0, 'z': 0},
            "rotation": {'x': 0, 'y': 0, 'z': 0},
            "scale": {'x': 1, 'y': 1, 'z': 1}
        })

        if world_lv and world_lv.content_type == 'physvol':
            for pv in world_lv.content:
                # Initial call starts with the world as the parent
                self._traverse(pv, parent_pv_id=world_pv_id, path=[world_lv.name], threejs_objects=threejs_objects)

        # After the geometry traversal, add the sources
        for source in self.sources.values():
            threejs_objects.append({
                "id": source.id,
                "name": source.name,
                "parent_id": world_pv_id, # Attach to the world physical volume
                "is_source": True,
                "position": source._evaluated_position,
                "rotation": source._evaluated_rotation,
                "scale": {'x': 1, 'y': 1, 'z': 1},
                "gps_commands": source.gps_commands,
                "confine_to_pv": source.confine_to_pv,
                "volume_link_id": source.volume_link_id
            })

        return threejs_objects

    def _traverse(self, pv, parent_pv_id, path, threejs_objects, owner_pv_id=None, instance_prefix=""):
        
        # The instance_id is unique for every single object in the 3D scene.
        current_instance_id = f"{instance_prefix}{pv.id}"
        # The canonical_id is the original ID from the project's state definition.
        current_canonical_id = pv.id
        # The owner_id is the top-level selectable object in the hierarchy.
        current_owner_id = owner_pv_id or pv.id

        # Case 1: The PV places an Assembly
        assembly = self.get_assembly(pv.volume_ref)
        if assembly:
            
            # Add a non-renderable node for this assembly instance.
            threejs_objects.append({
                "id": current_instance_id,
                "canonical_id": current_canonical_id,
                "name": pv.name,
                "parent_id": parent_pv_id,
                "is_world_volume_placement": False,
                "volume_ref": pv.volume_ref,
                "is_assembly_container": True,
                "is_procedural_container": False,
                "is_procedural_instance": getattr(pv, 'is_procedural_instance', False),
                "position": pv._evaluated_position,
                "rotation": pv._evaluated_rotation,
                "scale": pv._evaluated_scale,
                "owner_pv_id": current_owner_id
            })
            
            if assembly.name in path: return # Prevent infinite recursion
            
            for part_pv_template in assembly.placements:
                # Create a clone of the template PV
                part_pv_instance = part_pv_template.clone()

                # The new instance's parent is this assembly instance.
                # The owner is still the top-level owner.
                # We pass down a new instance_prefix to ensure its children are also unique.
                self._traverse(
                    part_pv_instance,
                    parent_pv_id=current_instance_id,
                    path=path + [assembly.name],
                    threejs_objects=threejs_objects,
                    owner_pv_id=current_owner_id,
                    instance_prefix=f"{current_instance_id}::" # Use a clear separator
                )
            return
        
        # Case 2: The PV places a Logical Volume
        lv = self.get_logical_volume(pv.volume_ref)
        if not lv: return
        if lv.name in path: return

        # This physvol (pv) is the container for the LV's content.
        # It gets a single entry in the scene description with its unique instance ID.
        threejs_objects.append({
            "id": current_instance_id,
            "canonical_id": current_canonical_id,
            "name": pv.name,
            "parent_id": parent_pv_id,
            "is_world_volume_placement": False,
            "volume_ref": pv.volume_ref,
            "owner_pv_id": current_owner_id,
            "is_assembly_container": False,
            "is_procedural_container": lv.content_type != 'physvol',
            "is_procedural_instance": getattr(pv, 'is_procedural_instance', False),
            "solid_ref_for_threejs": lv.solid_ref,
            "position": pv._evaluated_position,
            "rotation": pv._evaluated_rotation,
            "scale": pv._evaluated_scale,
            "vis_attributes": lv.vis_attributes,
            "copy_number": pv.copy_number
        })
        
        if lv.content_type == 'physvol':
            # Recurse into the content of the placed LV
            for child_pv in lv.content:

                # Create a clone
                child_pv_instance = child_pv.clone()

                # For a standard PV, only pass down the owner if it is not the current PV.
                pass_down_owner = None
                if(current_owner_id == pv.id): pass_down_owner = None

                self._traverse(
                    child_pv_instance, 
                    parent_pv_id=current_instance_id, # Children are parented to this instance
                    path=path + [lv.name], 
                    threejs_objects=threejs_objects, 
                    owner_pv_id=pass_down_owner,
                    instance_prefix=f"{current_instance_id}::"
                )
        else: # It's a procedural LV
            # The owner of the unrolled instances is the current instance ID itself.
            owner_id_for_children = current_instance_id

            if lv.content_type == 'replica':
                self._unroll_replica_and_traverse(lv, current_canonical_id, current_instance_id, path, threejs_objects, owner_id=owner_id_for_children)
            elif lv.content_type == 'division':
                 self._unroll_division_and_traverse(lv, current_canonical_id, current_instance_id, path, threejs_objects, owner_id=owner_id_for_children)
            elif lv.content_type == 'parameterised':
                 self._unroll_param_and_traverse(lv, current_canonical_id, current_instance_id, path, threejs_objects, owner_id=owner_id_for_children)

    def _unroll_replica_and_traverse(self, lv, canonical_id, parent_pv_id, path, threejs_objects, owner_id):
        replica = lv.content
        child_lv_template = self.get_logical_volume(replica.volume_ref)
        if not child_lv_template: return
        
        # Use the pre-evaluated attributes from the object for ALL parameters
        number = replica._evaluated_number
        width = replica._evaluated_width
        offset = replica._evaluated_offset
        
        # This part doesn't need evaluation as it's just direction flags
        axis_vec = np.array([
            float(replica.direction['x']),
            float(replica.direction['y']),
            float(replica.direction['z'])
        ])
        
        start_pv = PhysicalVolumePlacement("temp_start", "temp_lv")
        start_pv._evaluated_position = replica._evaluated_start_position
        start_pv._evaluated_rotation = replica._evaluated_start_rotation
        start_transform_matrix = start_pv.get_transform_matrix()

        for i in range(number):
            translation_dist = -width * (number - 1) * 0.5 + i * width + offset
            
            algo_pos = axis_vec * translation_dist
            algo_matrix = np.identity(4)
            algo_matrix[0:3, 3] = algo_pos
            
            final_local_matrix = start_transform_matrix @ algo_matrix

            final_pos, final_rot_rad, _ = PhysicalVolumePlacement.decompose_matrix(final_local_matrix)

            temp_pv = PhysicalVolumePlacement(
                name=f"{lv.name}_replica_{i}",
                volume_ref=child_lv_template.name,
                copy_number_expr=str(i),
                parent_lv_name=lv.name
            )
            temp_pv._evaluated_position = final_pos
            temp_pv._evaluated_rotation = final_rot_rad

            # Add the generated replica instance itself to the list
            threejs_objects.append({
                "id": temp_pv.id,
                "canonical_id": canonical_id,
                "name": temp_pv.name,
                "parent_id": parent_pv_id,
                "owner_pv_id": owner_id,
                "is_world_volume_placement": False,
                "volume_ref": temp_pv.volume_ref,
                "is_assembly_container": False,
                "is_procedural_container": False,
                "is_procedural_instance": True, 
                "solid_ref_for_threejs": child_lv_template.solid_ref,
                "position": temp_pv._evaluated_position,
                "rotation": temp_pv._evaluated_rotation,
                "scale": temp_pv._evaluated_scale,
                "vis_attributes": child_lv_template.vis_attributes,
                "copy_number": i
            })
            
            # Recurse into children of the template LV
            if child_lv_template.content_type == 'physvol' and child_lv_template.content:
                for child_of_child_pv in child_lv_template.content:
                    self._traverse(child_of_child_pv, temp_pv.id, path + [lv.name], threejs_objects, owner_pv_id=owner_id)

    def _unroll_division_and_traverse(self, lv, canonical_id, parent_pv_id, path, threejs_objects, owner_id):
        division = lv.content
        child_lv = self.get_logical_volume(division.volume_ref)
        mother_solid = self.get_solid(lv.solid_ref)
        if not (child_lv and mother_solid and mother_solid.type == 'box'):
            if mother_solid and mother_solid.type != 'box': print(f"Warning: Division of non-box solid '{mother_solid.name}' is not visually supported.")
            return

        number, offset = division._evaluated_number, division._evaluated_offset
        axis_map = {'kxaxis': 'x', 'kyaxis': 'y', 'kzaxis': 'z'}
        axis_key = axis_map.get(division.axis.lower(), 'z')
        mother_params = mother_solid._evaluated_parameters
        mother_extent = mother_params.get(axis_key, 0)
        width = (mother_extent - (2 * offset)) / number if number > 0 else 0
        slice_params = mother_params.copy()
        slice_params[axis_key] = width

        # slice_solid = Solid(f"{mother_solid.name}_slice", 'box', {})
        # slice_solid._evaluated_parameters = slice_params

        for i in range(number):
            # Position of the slice's center within the mother volume's local coordinates
            pos_in_mother = -mother_extent / 2.0 + offset + width / 2.0 + i * width
            copy_pos = {'x': 0, 'y': 0, 'z': 0}; 
            copy_pos[axis_key] = pos_in_mother

            # This temporary solid is unique to this slice
            temp_solid = Solid(
                name=f"{mother_solid.name}_slice_{i}",
                solid_type='box',
                raw_parameters={} 
            )
            temp_solid._evaluated_parameters = slice_params

            # Create a temporary PV to hold the instance's transform
            temp_pv = PhysicalVolumePlacement(
                name=f"{lv.name}_division_{i}",
                volume_ref=child_lv.name,
                copy_number_expr=str(i),
                parent_lv_name=lv.name
            )
            temp_pv._evaluated_position = copy_pos
            temp_pv._evaluated_rotation = {'x': 0, 'y': 0, 'z': 0}
            
            # Add the generated slice itself to the list of objects to be rendered.
            threejs_objects.append({
                "id": temp_pv.id,
                "canonical_id": canonical_id,
                "name": temp_pv.name,
                "parent_id": parent_pv_id, # It's a child of the PV that holds the division rule
                "is_world_volume_placement": False,
                "volume_ref": temp_pv.volume_ref,
                "owner_pv_id": owner_id,   # It belongs to the division rule PV
                "is_assembly_container": False,
                "is_procedural_container": False,
                "is_procedural_instance": True,
                "solid_ref_for_threejs": temp_solid.to_dict(), # Pass the unique slice solid
                "position": temp_pv._evaluated_position,
                "rotation": temp_pv._evaluated_rotation,
                "scale": temp_pv._evaluated_scale,
                "vis_attributes": child_lv.vis_attributes,
                "copy_number": i
            })

            # Now, recurse into the children of the template LV, parenting them to this new slice
            if child_lv.content_type == 'physvol' and child_lv.content:
                for child_of_child_pv in child_lv.content:
                    self._traverse(child_of_child_pv, temp_pv.id, path + [lv.name], threejs_objects, owner_pv_id=owner_id)

    def _unroll_param_and_traverse(self, lv, canonical_id, parent_pv_id, path, threejs_objects, owner_id):
        param_vol = lv.content
        child_lv_template = self.get_logical_volume(param_vol.volume_ref)
        if not child_lv_template: return

        original_solid = self.get_solid(child_lv_template.solid_ref)
        if not original_solid: return

        for i, param_set in enumerate(param_vol.parameters):
            new_solid_params = original_solid.raw_parameters.copy()
            dims_type_clean = param_set.dimensions_type.replace('_dimensions', '')
            new_solid_params.update(param_set.dimensions)

            # Create a temporary Solid object for this specific instance
            temp_solid = Solid(
                name=f"{original_solid.name}_param_{i}",
                solid_type=dims_type_clean,
                raw_parameters=new_solid_params
            )
            temp_solid._evaluated_parameters = param_set._evaluated_dimensions
            
            # Create a temporary PhysicalVolumePlacement for this instance's transform
            temp_pv = PhysicalVolumePlacement(
                name=f"{lv.name}_param_{i}",
                volume_ref=child_lv_template.name,
                copy_number_expr=str(i),
                parent_lv_name=lv.name
            )
            temp_pv._evaluated_position = param_set._evaluated_position
            temp_pv._evaluated_rotation = param_set._evaluated_rotation

            # Create a temporary Logical Volume for this instance so we can recurse
            temp_lv_instance = LogicalVolume(
                name=f"{child_lv_template.name}_param_{i}",
                solid_ref=temp_solid.name, # This solid doesn't exist in the main dict, so we pass the object
                material_ref=child_lv_template.material_ref
            )
            temp_lv_instance.content = child_lv_template.content
            temp_lv_instance.content_type = child_lv_template.content_type

            # We need to add the solid to the description, but also need to pass the object
            # to the recursive call. Let's create a custom object for the scene description.
            threejs_objects.append({
                "id": temp_pv.id,
                "canonical_id": canonical_id,
                "name": temp_pv.name,
                "parent_id": parent_pv_id,
                "is_world_volume_placement": False,
                "volume_ref": temp_pv.volume_ref,
                "owner_pv_id": owner_id,
                "is_assembly_container": False,
                "is_procedural_container": False,
                "is_procedural_instance": True,
                "solid_ref_for_threejs": temp_solid.to_dict(), # Pass the temporary solid's data directly
                "position": temp_pv._evaluated_position,
                "rotation": temp_pv._evaluated_rotation,
                "scale": temp_pv._evaluated_scale,
                "vis_attributes": child_lv_template.vis_attributes,
                "copy_number": i
            })

            # Recurse if the template LV had children
            if child_lv_template.content_type == 'physvol' and child_lv_template.content:
                for child_of_child_pv in child_lv_template.content:
                    # Children are parented to our temporary instance PV
                    self._traverse(child_of_child_pv, temp_pv.id, path + [lv.name], threejs_objects, owner_pv_id=owner_id)
