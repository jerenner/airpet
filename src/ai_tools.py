# src/ai_tools.py

from typing import List, Dict, Any, Optional
from .geometry_types import GeometryState


def _list_detector_feature_generator_labels(state) -> List[str]:
    labels = []
    for entry in getattr(state, "detector_feature_generators", []) or []:
        if not isinstance(entry, dict):
            continue
        label = entry.get("name") or entry.get("generator_id")
        if isinstance(label, str):
            label = label.strip()
            if label:
                labels.append(label)
    return labels


def _list_scoring_mesh_labels(state) -> List[str]:
    labels = []
    scoring_state = getattr(state, "scoring", None)
    for entry in getattr(scoring_state, "scoring_meshes", []) or []:
        if not isinstance(entry, dict):
            continue
        label = entry.get("name") or entry.get("mesh_id")
        if isinstance(label, str):
            label = label.strip()
            if label:
                labels.append(label)
    return labels


def _list_scoring_tally_labels(state) -> List[str]:
    labels = []
    scoring_state = getattr(state, "scoring", None)
    for entry in getattr(scoring_state, "tally_requests", []) or []:
        if not isinstance(entry, dict):
            continue
        label = entry.get("name") or entry.get("quantity") or entry.get("tally_id")
        if isinstance(label, str):
            label = label.strip()
            if label:
                labels.append(label)
    return labels


def get_project_summary(pm) -> Dict[str, Any]:
    """Returns a high-level summary of the current project structure."""
    state = pm.current_geometry_state
    detector_feature_generator_labels = _list_detector_feature_generator_labels(state)
    scoring_mesh_labels = _list_scoring_mesh_labels(state)
    scoring_tally_labels = _list_scoring_tally_labels(state)
    return {
        "project_name": pm.project_name,
        "world_volume": state.world_volume_ref,
        "counts": {
            "defines": len(state.defines),
            "materials": len(state.materials),
            "elements": len(state.elements),
            "solids": len(state.solids),
            "logical_volumes": len(state.logical_volumes),
            "assemblies": len(state.assemblies),
            "sources": len(state.sources),
            "detector_feature_generators": len(getattr(state, "detector_feature_generators", []) or []),
            "scoring_meshes": len(getattr(state.scoring, "scoring_meshes", []) or []),
            "scoring_tally_requests": len(getattr(state.scoring, "tally_requests", []) or []),
        },
        "names": {
            "materials": list(state.materials.keys()),
            "solids": list(state.solids.keys()),
            "logical_volumes": list(state.logical_volumes.keys()),
            "detector_feature_generators": detector_feature_generator_labels,
            "scoring_meshes": scoring_mesh_labels,
            "scoring_tally_requests": scoring_tally_labels,
        }
    }

def get_component_details(pm, component_type: str, name: str) -> Optional[Dict[str, Any]]:
    """Returns full details for a specific component (define, material, solid, lv, assembly, environment, scoring)."""
    return pm.get_object_details(component_type, name)



# Canonical primitive-solid parameter specs (source of truth for AI schema + backend validation).
def _expr_param(description: str) -> Dict[str, Any]:
    # Keep Gemini-compatible primitive schema types: expression fields are represented as strings.
    return {
        "type": "string",
        "description": f"{description}. Use numeric strings or expressions (e.g., '42', 'radius+5', '360*deg')."
    }


def _int_or_expr_param(description: str) -> Dict[str, Any]:
    # Integer-or-expression fields are represented as strings for cross-provider compatibility.
    return {
        "type": "string",
        "description": f"{description}. Use integer-like strings or expressions."
    }


def _bool_param(description: str) -> Dict[str, Any]:
    return {
        "type": "boolean",
        "description": description,
    }


def _int_param(description: str) -> Dict[str, Any]:
    return {
        "type": "integer",
        "description": description,
    }


PRIMITIVE_SOLID_PARAM_SPECS: Dict[str, Dict[str, Any]] = {
    "box": {
        "required": ["x", "y", "z"],
        "properties": {
            "x": _expr_param("Full X length (mm)"),
            "y": _expr_param("Full Y length (mm)"),
            "z": _expr_param("Full Z length (mm)")
        }
    },
    "tube": {
        "required": ["rmin", "rmax", "z"],
        "properties": {
            "rmin": _expr_param("Inner radius (mm)"),
            "rmax": _expr_param("Outer radius (mm)"),
            "z": _expr_param("Half-length in Z (mm)"),
            "startphi": _expr_param("Start angle (e.g., 0*deg, default: 0)"),
            "deltaphi": _expr_param("Span angle (e.g., 360*deg, default: 360)")
        }
    },
    "cone": {
        "required": ["rmin1", "rmax1", "rmin2", "rmax2", "z"],
        "properties": {
            "rmin1": _expr_param("Inner radius at -Z side (mm)"),
            "rmax1": _expr_param("Outer radius at -Z side (mm)"),
            "rmin2": _expr_param("Inner radius at +Z side (mm)"),
            "rmax2": _expr_param("Outer radius at +Z side (mm)"),
            "z": _expr_param("Half-length in Z (mm)"),
            "startphi": _expr_param("Start angle (e.g., 0*deg, default: 0)"),
            "deltaphi": _expr_param("Span angle (e.g., 360*deg, default: 360)")
        }
    },
    "sphere": {
        "required": ["rmin", "rmax", "startphi", "deltaphi", "starttheta", "deltatheta"],
        "properties": {
            "rmin": _expr_param("Inner radius (mm)"),
            "rmax": _expr_param("Outer radius (mm)"),
            "startphi": _expr_param("Start azimuth angle"),
            "deltaphi": _expr_param("Azimuth span angle"),
            "starttheta": _expr_param("Start polar angle"),
            "deltatheta": _expr_param("Polar span angle")
        }
    },
    "orb": {
        "required": ["r"],
        "properties": {
            "r": _expr_param("Outer radius (mm)")
        }
    },
    "trd": {
        "required": ["x1", "x2", "y1", "y2", "z"],
        "properties": {
            "x1": _expr_param("X length at -Z side (mm)"),
            "x2": _expr_param("X length at +Z side (mm)"),
            "y1": _expr_param("Y length at -Z side (mm)"),
            "y2": _expr_param("Y length at +Z side (mm)"),
            "z": _expr_param("Full Z length (mm)")
        }
    },
    "para": {
        "required": ["x", "y", "z", "alpha", "theta", "phi"],
        "properties": {
            "x": _expr_param("Full X length (mm)"),
            "y": _expr_param("Full Y length (mm)"),
            "z": _expr_param("Full Z length (mm)"),
            "alpha": _expr_param("Alpha angle"),
            "theta": _expr_param("Theta angle"),
            "phi": _expr_param("Phi angle")
        }
    },
    "trap": {
        "required": ["z", "y1", "x1", "x2", "y2", "x3", "x4"],
        "properties": {
            "z": _expr_param("Full Z length (mm)"),
            "theta": _expr_param("Theta angle (default: 0*deg)"),
            "phi": _expr_param("Phi angle (default: 0*deg)"),
            "y1": _expr_param("Y length at -Z side (mm)"),
            "x1": _expr_param("X1 at -Z side (mm)"),
            "x2": _expr_param("X2 at -Z side (mm)"),
            "alpha1": _expr_param("Alpha1 angle (default: 0*deg)"),
            "y2": _expr_param("Y length at +Z side (mm)"),
            "x3": _expr_param("X3 at +Z side (mm)"),
            "x4": _expr_param("X4 at +Z side (mm)"),
            "alpha2": _expr_param("Alpha2 angle (default: 0*deg)")
        }
    },
    "hype": {
        "required": ["rmin", "rmax", "inst", "outst", "z"],
        "properties": {
            "rmin": _expr_param("Inner radius at z=0 (mm)"),
            "rmax": _expr_param("Outer radius at z=0 (mm)"),
            "inst": _expr_param("Inner stereo angle"),
            "outst": _expr_param("Outer stereo angle"),
            "z": _expr_param("Half-length in Z (mm)")
        }
    },
    "twistedbox": {
        "required": ["x", "y", "z", "PhiTwist"],
        "properties": {
            "x": _expr_param("Full X length (mm)"),
            "y": _expr_param("Full Y length (mm)"),
            "z": _expr_param("Full Z length (mm)"),
            "PhiTwist": _expr_param("Twist angle")
        }
    },
    "twistedtrd": {
        "required": ["x1", "x2", "y1", "y2", "z", "PhiTwist"],
        "properties": {
            "x1": _expr_param("X length at -Z side (mm)"),
            "x2": _expr_param("X length at +Z side (mm)"),
            "y1": _expr_param("Y length at -Z side (mm)"),
            "y2": _expr_param("Y length at +Z side (mm)"),
            "z": _expr_param("Full Z length (mm)"),
            "PhiTwist": _expr_param("Twist angle")
        }
    },
    "twistedtrap": {
        "required": ["PhiTwist", "z", "Theta", "Phi", "y1", "x1", "x2", "y2", "x3", "x4", "Alph"],
        "properties": {
            "PhiTwist": _expr_param("Twist angle"),
            "z": _expr_param("Full Z length (mm)"),
            "Theta": _expr_param("Theta angle"),
            "Phi": _expr_param("Phi angle"),
            "y1": _expr_param("Y length at -Z side (mm)"),
            "x1": _expr_param("X1 at -Z side (mm)"),
            "x2": _expr_param("X2 at -Z side (mm)"),
            "y2": _expr_param("Y length at +Z side (mm)"),
            "x3": _expr_param("X3 at +Z side (mm)"),
            "x4": _expr_param("X4 at +Z side (mm)"),
            "Alph": _expr_param("Alpha angle")
        }
    },
    "twistedtubs": {
        "required": ["twistedangle", "endinnerrad", "endouterrad", "zlen", "phi"],
        "properties": {
            "twistedangle": _expr_param("Twist angle"),
            "endinnerrad": _expr_param("Inner radius at endcaps (mm)"),
            "endouterrad": _expr_param("Outer radius at endcaps (mm)"),
            "zlen": _expr_param("Full Z length (mm)"),
            "phi": _expr_param("Angular span")
        }
    },
    "genericPolycone": {
        "required": ["startphi", "deltaphi", "rzpoints"],
        "properties": {
            "startphi": _expr_param("Start angle"),
            "deltaphi": _expr_param("Span angle"),
            "rzpoints": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "r": _expr_param("Radius at point"),
                        "z": _expr_param("Z coordinate at point")
                    },
                    "required": ["r", "z"]
                }
            }
        }
    },
    "genericPolyhedra": {
        "required": ["startphi", "deltaphi", "numsides", "rzpoints"],
        "properties": {
            "startphi": _expr_param("Start angle"),
            "deltaphi": _expr_param("Span angle"),
            "numsides": _int_or_expr_param("Number of polygon sides"),
            "rzpoints": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "r": _expr_param("Radius at point"),
                        "z": _expr_param("Z coordinate at point")
                    },
                    "required": ["r", "z"]
                }
            }
        }
    },
    "xtru": {
        "required": ["twoDimVertices", "sections"],
        "properties": {
            "twoDimVertices": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "x": _expr_param("2D vertex X"),
                        "y": _expr_param("2D vertex Y")
                    },
                    "required": ["x", "y"]
                }
            },
            "sections": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "zOrder": _int_or_expr_param("Section order index"),
                        "zPosition": _expr_param("Section Z position"),
                        "xOffset": _expr_param("Section X offset"),
                        "yOffset": _expr_param("Section Y offset"),
                        "scalingFactor": _expr_param("Section scale factor")
                    },
                    "required": ["zOrder", "zPosition", "xOffset", "yOffset", "scalingFactor"]
                }
            }
        }
    }
}


def _build_create_primitive_solid_parameters() -> Dict[str, Any]:
    solid_types = list(PRIMITIVE_SOLID_PARAM_SPECS.keys())

    # Gemini's function schema validator rejects JSON-schema combinators like oneOf/anyOf.
    # We keep discriminated requirements in PRIMITIVE_SOLID_PARAM_SPECS (validated server-side)
    # and expose a comprehensive canonical param catalog here for model guidance.
    all_param_props: Dict[str, Any] = {}
    for spec in PRIMITIVE_SOLID_PARAM_SPECS.values():
        for param_name, param_schema in spec.get("properties", {}).items():
            if param_name not in all_param_props:
                all_param_props[param_name] = param_schema

    required_by_type = "; ".join(
        [f"{solid}: {spec.get('required', [])}" for solid, spec in PRIMITIVE_SOLID_PARAM_SPECS.items()]
    )

    return {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "solid_type": {"type": "string", "enum": solid_types},
            "params": {
                "type": "object",
                "properties": all_param_props,
                "description": (
                    "Canonical GDML-style params for the selected solid_type. "
                    f"Required keys by solid_type: {required_by_type}"
                )
            }
        },
        "required": ["name", "solid_type", "params"]
    }


def _create_primitive_solid_tool() -> Dict[str, Any]:
    return {
        "name": "create_primitive_solid",
        "description": (
            "Create a new primitive shape. "
            "Use canonical GDML-style parameter names from the schema for the selected solid_type."
        ),
        "parameters": _build_create_primitive_solid_parameters()
    }


def _detector_feature_object_ref_param(description: str) -> Dict[str, Any]:
    return {
        "type": "object",
        "description": (
            f"{description} Prefer saved-state style refs with 'id' and 'name' when known; "
            "at least one is required."
        ),
        "properties": {
            "id": {"type": "string"},
            "name": {"type": "string"},
        },
    }


def _create_manage_detector_feature_generator_tool() -> Dict[str, Any]:
    object_ref_schema = _detector_feature_object_ref_param("Object reference.")
    return {
        "name": "manage_detector_feature_generator",
        "description": (
            "Create or update a saved detector feature generator. Current MVP supports "
            "rectangular drilled-hole arrays, a narrow circular bolt-circle variant, "
            "a fixed absorber/sensor/support layered detector stack, a rectangular tiled sensor array, "
            "a repeated support-rib array, a straight channel-cut array, and an annular shield sleeve. "
            "Reuse generator_id to update an existing generator and keep realize_now=true "
            "when you want regenerated geometry plus a deterministic realization summary back."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "generator_id": {
                    "type": "string",
                    "description": "Stable generator id. Reuse an existing id to update that generator in place.",
                },
                "name": {
                    "type": "string",
                    "description": "Human-readable generator name. Defaults to a deterministic type-based name.",
                },
                "generator_type": {
                    "type": "string",
                    "enum": [
                        "rectangular_drilled_hole_array",
                        "circular_drilled_hole_array",
                        "layered_detector_stack",
                        "tiled_sensor_array",
                        "support_rib_array",
                        "channel_cut_array",
                        "annular_shield_sleeve",
                    ],
                    "description": "Detector feature generator type.",
                },
                "enabled": {
                    "type": "boolean",
                    "description": "Whether the saved generator stays enabled.",
                },
                "realize_now": {
                    "type": "boolean",
                    "description": "If true, realize the saved generator into geometry immediately (default: true).",
                },
                "target": {
                    "type": "object",
                    "description": "Saved-state target contract for the generator.",
                    "properties": {
                        "solid_ref": _detector_feature_object_ref_param(
                            "Target solid reference."
                        ),
                        "logical_volume_refs": {
                            "type": "array",
                            "description": (
                                "Optional logical-volume refs to retarget. When omitted, matching logical "
                                "volumes using the target solid are updated automatically."
                            ),
                            "items": object_ref_schema,
                        },
                        "parent_logical_volume_ref": _detector_feature_object_ref_param(
                            "Parent logical-volume reference for layered detector stacks, tiled sensor arrays, support-rib arrays, and annular shield sleeves."
                        ),
                    },
                },
                "pattern": {
                    "type": "object",
                    "description": (
                        "Pattern parameters for the drilled-hole array. "
                        "Rectangular arrays use count_x/count_y/pitch_mm. "
                        "Circular arrays use count/radius_mm/orientation_deg."
                    ),
                    "properties": {
                        "count_x": {"type": "integer"},
                        "count_y": {"type": "integer"},
                        "count": {"type": "integer"},
                        "pitch_mm": {
                            "type": "object",
                            "properties": {
                                "x": {"type": "number"},
                                "y": {"type": "number"},
                            },
                            "required": ["x", "y"],
                        },
                        "radius_mm": {"type": "number"},
                        "orientation_deg": {"type": "number"},
                        "origin_offset_mm": {
                            "type": "object",
                            "properties": {
                                "x": {"type": "number"},
                                "y": {"type": "number"},
                            },
                        },
                        "anchor": {
                            "type": "string",
                            "enum": ["target_center"],
                        },
                    },
                },
                "hole": {
                    "type": "object",
                    "description": "Hole geometry parameters for the generator.",
                    "properties": {
                        "shape": {
                            "type": "string",
                            "enum": ["cylindrical"],
                        },
                        "diameter_mm": {"type": "number"},
                        "depth_mm": {"type": "number"},
                        "axis": {
                            "type": "string",
                            "enum": ["z"],
                        },
                        "drill_from": {
                            "type": "string",
                            "enum": ["positive_z_face"],
                        },
                    },
                },
                "stack": {
                    "type": "object",
                    "description": (
                        "Layered-stack parameters. Layered detector stacks use module_size_mm, "
                        "module_count, module_pitch_mm, and origin_offset_mm."
                    ),
                    "properties": {
                        "module_size_mm": {
                            "type": "object",
                            "properties": {
                                "x": {"type": "number"},
                                "y": {"type": "number"},
                            },
                            "required": ["x", "y"],
                        },
                        "module_count": {"type": "integer"},
                        "module_pitch_mm": {"type": "number"},
                        "origin_offset_mm": {
                            "type": "object",
                            "properties": {
                                "x": {"type": "number"},
                                "y": {"type": "number"},
                                "z": {"type": "number"},
                            },
                        },
                        "anchor": {
                            "type": "string",
                            "enum": ["target_center"],
                        },
                    },
                },
                "array": {
                    "type": "object",
                    "description": (
                        "Rectangular tiled-sensor-array parameters. Tiled sensor arrays use "
                        "count_x/count_y, pitch_mm, and origin_offset_mm. Support-rib arrays and "
                        "channel-cut arrays use count, linear_pitch_mm, axis, and origin_offset_mm."
                    ),
                    "properties": {
                        "count": {"type": "integer"},
                        "count_x": {"type": "integer"},
                        "count_y": {"type": "integer"},
                        "linear_pitch_mm": {"type": "number"},
                        "axis": {
                            "type": "string",
                            "enum": ["x", "y"],
                        },
                        "pitch_mm": {
                            "type": "object",
                            "properties": {
                                "x": {"type": "number"},
                                "y": {"type": "number"},
                            },
                        },
                        "origin_offset_mm": {
                            "type": "object",
                            "properties": {
                                "x": {"type": "number"},
                                "y": {"type": "number"},
                                "z": {"type": "number"},
                            },
                        },
                        "anchor": {
                            "type": "string",
                            "enum": ["target_center"],
                        },
                    },
                },
                "rib": {
                    "type": "object",
                    "description": (
                        "Generated support-rib parameters. Provide width_mm, height_mm, "
                        "material_ref, and optional is_sensitive."
                    ),
                    "properties": {
                        "width_mm": {"type": "number"},
                        "height_mm": {"type": "number"},
                        "material_ref": {"type": "string"},
                        "is_sensitive": {"type": "boolean"},
                    },
                },
                "channel": {
                    "type": "object",
                    "description": (
                        "Straight channel-cut parameters for box targets. Provide width_mm and depth_mm."
                    ),
                    "properties": {
                        "width_mm": {"type": "number"},
                        "depth_mm": {"type": "number"},
                    },
                },
                "shield": {
                    "type": "object",
                    "description": (
                        "Annular shield-sleeve parameters. Provide inner_radius_mm, outer_radius_mm, "
                        "length_mm, material_ref, and optional origin_offset_mm."
                    ),
                    "properties": {
                        "inner_radius_mm": {"type": "number"},
                        "outer_radius_mm": {"type": "number"},
                        "length_mm": {"type": "number"},
                        "material_ref": {"type": "string"},
                        "origin_offset_mm": {
                            "type": "object",
                            "properties": {
                                "x": {"type": "number"},
                                "y": {"type": "number"},
                                "z": {"type": "number"},
                            },
                        },
                        "anchor": {
                            "type": "string",
                            "enum": ["target_center"],
                        },
                    },
                },
                "sensor": {
                    "type": "object",
                    "description": (
                        "Generated sensor-cell parameters for tiled sensor arrays. "
                        "Provide size_mm, thickness_mm, material_ref, and optional is_sensitive."
                    ),
                    "properties": {
                        "size_mm": {
                            "type": "object",
                            "properties": {
                                "x": {"type": "number"},
                                "y": {"type": "number"},
                            },
                            "required": ["x", "y"],
                        },
                        "thickness_mm": {"type": "number"},
                        "material_ref": {"type": "string"},
                        "is_sensitive": {"type": "boolean"},
                    },
                },
                "layers": {
                    "type": "object",
                    "description": (
                        "Fixed three-layer sandwich for layered detector stacks. "
                        "Provide absorber, sensor, and support entries with material_ref "
                        "and thickness_mm; sensor can also set is_sensitive."
                    ),
                    "properties": {
                        "absorber": {
                            "type": "object",
                            "properties": {
                                "material_ref": {"type": "string"},
                                "thickness_mm": {"type": "number"},
                                "is_sensitive": {"type": "boolean"},
                            },
                            "required": ["material_ref", "thickness_mm"],
                        },
                        "sensor": {
                            "type": "object",
                            "properties": {
                                "material_ref": {"type": "string"},
                                "thickness_mm": {"type": "number"},
                                "is_sensitive": {"type": "boolean"},
                            },
                            "required": ["material_ref", "thickness_mm"],
                        },
                        "support": {
                            "type": "object",
                            "properties": {
                                "material_ref": {"type": "string"},
                                "thickness_mm": {"type": "number"},
                                "is_sensitive": {"type": "boolean"},
                            },
                            "required": ["material_ref", "thickness_mm"],
                        },
                    },
                },
            },
            "required": ["generator_type", "target"],
        },
    }


RUN_SIMULATION_OPTION_SPECS: Dict[str, Dict[str, Any]] = {
    "production_cut": _expr_param(
        "Geant4 production cut passed to /run/setCut (e.g. '1.0 mm')"
    ),
    "hit_energy_threshold": _expr_param(
        "Hit energy threshold passed to /g4pet/run/hitEnergyThreshold (e.g. '1 eV')"
    ),
    "save_hits": _bool_param("Whether to save hit ntuples during the run."),
    "save_hit_metadata": _bool_param("Whether to save per-hit metadata."),
    "save_particles": _bool_param("Whether to save particle ntuples."),
    "save_tracks_range": {
        "type": "string",
        "description": "Track event range to persist, e.g. '0-99'.",
    },
    "seed1": _int_param("Primary random seed. Use 0 to keep the Geant4 default."),
    "seed2": _int_param("Secondary random seed. Use 0 to keep the Geant4 default."),
    "print_progress": _int_param("Print progress every N events; use 0 to disable."),
    "physics_list": {
        "type": "string",
        "description": "Physics list name for G4PHYSICSLIST (e.g. 'FTFP_BERT').",
    },
    "optical_physics": _bool_param("Whether to enable optical physics via G4OPTICALPHYSICS."),
}


RUN_SIMULATION_OPTION_KEYS = tuple(RUN_SIMULATION_OPTION_SPECS.keys())

# Mapping of AI tools to ProjectManager methods
AI_GEOMETRY_TOOLS = [
    {
        "name": "get_project_summary",
        "description": "Get a high-level overview of the project structure, including names of all volumes and materials.",
        "parameters": {"type": "object", "properties": {}}
    },
    {
        "name": "get_component_details",
        "description": "Get the full JSON definition of a specific component to see its current parameters, including the saved environment, scoring state, field state, region cuts/limits state, and detector feature generator state.",
        "parameters": {
            "type": "object",
            "properties": {
                "component_type": {
                    "type": "string", 
                    "enum": ["define", "material", "element", "solid", "logical_volume", "assembly", "particle_source", "physical_volume", "environment", "scoring", "detector_feature_generator"]
                },
                "name": {"type": "string", "description": "The name of the component, its unique ID (for physical_volumes), the singleton scoring id/name (for scoring), or the generator_id/name for detector feature generators."}
            },
            "required": ["component_type", "name"]
        }
    },
    {
        "name": "update_property",
        "description": (
            "Update a single property on a project object using the same path contract as the backend "
            "/update_property route. For the global magnetic field, use object_type='environment', "
            "object_id='global_uniform_magnetic_field', and property paths like 'enabled' or "
            "'field_vector_tesla.x'. For the global electric field, use "
            "object_id='global_uniform_electric_field' and property paths like 'enabled' or "
            "'field_vector_volt_per_meter.y'. For local magnetic field assignments, use "
            "object_id='local_uniform_magnetic_field' and property paths like 'enabled', "
            "'target_volume_names', or 'field_vector_tesla.z'. For local electric field assignments, "
            "use object_id='local_uniform_electric_field' and property paths like 'enabled', "
            "'target_volume_names', or 'field_vector_volt_per_meter.z'. For region cuts and limits, use "
            "object_id='region_cuts_and_limits' and property paths like 'enabled', "
            "'region_name', 'target_volume_names', 'production_cut_mm', 'max_step_mm', "
            "'max_track_length_mm', 'max_time_ns', 'min_kinetic_energy_mev', or 'min_range_mm'. "
            "For scoring state, use object_type='scoring', object_id='scoring_state', and property paths "
            "like 'state', 'scoring_meshes', 'tally_requests', or 'run_manifest_defaults'."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "object_type": {
                    "type": "string",
                    "enum": ["define", "material", "solid", "logical_volume", "physical_volume", "environment", "scoring"],
                    "description": "Type of object to update."
                },
                "object_id": {
                    "type": "string",
                    "description": "Name or ID of the target object."
                },
                "property_path": {
                    "type": "string",
                    "description": "Dot-separated property path, for example 'enabled', 'field_vector_tesla.z', or 'field_vector_volt_per_meter.z'."
                },
                "new_value": {
                    "type": "string",
                    "description": "New value to assign. Use JSON text or simple scalar strings such as 'true' or '1.5'."
                }
            },
            "required": ["object_type", "object_id", "property_path", "new_value"]
        }
    },
    _create_manage_detector_feature_generator_tool(),
    {
        "name": "search_components",
        "description": "Search for components by name using a regex pattern.",
        "parameters": {
            "type": "object",
            "properties": {
                "component_type": {
                    "type": "string",
                    "enum": ["solid", "logical_volume", "material", "physical_volume"]
                },
                "pattern": {"type": "string", "description": "Regex pattern to match names."}
            },
            "required": ["component_type", "pattern"]
        }
    },
    {
        "name": "manage_define",
        "description": "Create or update a project variable (constant, expression, position, rotation).",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "define_type": {"type": "string", "enum": ["constant", "expression", "position", "rotation", "variable"]},
                "value": {"type": "string", "description": "The expression string or a dict for position/rotation."},
                "unit": {"type": "string", "description": "Optional unit (mm, cm, deg, rad, etc.)"}
            },
            "required": ["name", "define_type", "value"]
        }
    },
    {
        "name": "manage_material",
        "description": "Create or update a material or element. Prefer built-in Geant4/NIST materials when available (for silicon use 'G4_Si'). For compound materials, use components array with element names as ref values (e.g., 'nickel', 'oxygen'). Elements will be auto-created if they don't exist. For custom elemental materials, use plain numeric A/Z values or supported expressions like density='2.33*g/cm3'.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "density": {"type": "string", "description": "Density expression, e.g. '2.33*g/cm3' or '2.33'."},
                "Z": {"type": "string", "description": "Atomic number expression, e.g. '14'."},
                "A": {"type": "string", "description": "Atomic mass expression, e.g. '28.085'. Avoid inventing unsupported unit symbols."},
                "state": {"type": "string", "description": "Material state: 'solid' (default), 'liquid', or 'gas'."},
                "components": {
                    "type": "array",
                    "description": "Array of component elements for compound materials. Each component has 'ref' (element name like 'nickel' or 'oxygen'), 'fraction' (weight fraction as string), and optionally 'natoms'.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "ref": {"type": "string", "description": "Element name (lowercase, e.g., 'nickel', 'oxygen', 'carbon')"},
                            "fraction": {"type": "string", "description": "Weight fraction as string (e.g., '0.787' for 78.7%)"},
                            "natoms": {"type": "string", "description": "Number of atoms (optional)"}
                        }
                    }
                }
            },
            "required": ["name"]
        }
    },
    _create_primitive_solid_tool(),
    {
        "name": "modify_solid",
        "description": "Update parameters of an existing solid.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "params": {"type": "object", "description": "Dict of parameters to update or replace."}
            },
            "required": ["name", "params"]
        }
    },
    {
        "name": "create_boolean_solid",
        "description": "Create a new boolean solid from existing solids.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "recipe": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "op": {"type": "string", "enum": ["base", "union", "subtraction", "intersection"]},
                            "solid_ref": {"type": "string"},
                            "transform": {
                                "type": "object",
                                "properties": {
                                    "position": {"type": "object"},
                                    "rotation": {"type": "object"}
                                }
                            }
                        }
                    }
                }
            },
            "required": ["name", "recipe"]
        }
    },
    {
        "name": "manage_logical_volume",
        "description": "Create or update a logical volume (binds a solid to a material and sets visual appearance). If the LV should record deposited-energy hits, explicitly set is_sensitive=true. When updating an existing LV, omitting is_sensitive preserves the current value.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "solid_ref": {"type": "string"},
                "material_ref": {"type": "string"},
                "is_sensitive": {"type": "boolean"},
                "color": {"type": "string", "description": "Hex color string (e.g., '#0000ff' for blue) or CSS color name."},
                "opacity": {"type": "number", "description": "Opacity from 0.0 (transparent) to 1.0 (opaque)."}
            },
            "required": ["name"]
        }
    },
    {
        "name": "place_volume",
        "description": "Place a volume (Physical Volume) inside another volume.",
        "parameters": {
            "type": "object",
            "properties": {
                "parent_lv_name": {"type": "string"},
                "placed_lv_ref": {"type": "string"},
                "name": {"type": "string", "description": "Optional name for the placement."},
                "position": {"type": "object"},
                "rotation": {"type": "object"},
                "scale": {"type": "object"},
                "copy_number_expr": {"type": "string", "description": "Expression or define name for copy number (e.g., '10' or 'num_copies')."}
            },
            "required": ["parent_lv_name", "placed_lv_ref"]
        }
    },
    {
        "name": "modify_physical_volume",
        "description": "Update the transform or name of an existing physical volume placement.",
        "parameters": {
            "type": "object",
            "properties": {
                "pv_id": {"type": "string", "description": "The unique ID of the physical volume."},
                "name": {"type": "string"},
                "position": {"type": "object"},
                "rotation": {"type": "object"},
                "scale": {"type": "object"}
            },
            "required": ["pv_id"]
        }
    },
    {
        "name": "create_detector_ring",
        "description": "High-level tool to create a ring array of volumes (e.g., a PET ring).",
        "parameters": {
            "type": "object",
            "properties": {
                "parent_lv_name": {"type": "string"},
                "lv_to_place_ref": {"type": "string"},
                "ring_name": {"type": "string"},
                "num_detectors": {"type": "string", "description": "Number of detectors in one ring (expression string)."},
                "radius": {"type": "string", "description": "Radius of the ring (expression string)."},
                "center": {"type": "object", "description": "Center of the ring {'x':..., 'y':..., 'z':...}"},
                "orientation": {"type": "object", "description": "Orientation of the ring axes."},
                "point_to_center": {"type": "boolean", "description": "If true, detectors rotate to face the center."},
                "inward_axis": {"type": "string", "enum": ["+x", "-x", "+y", "-y", "+z", "-z"], "description": "Which local axis of the detector should point inward."},
                "num_rings": {"type": "string", "description": "Number of axial rings (expression string)."},
                "ring_spacing": {"type": "string", "description": "Axial distance between rings."}
            },
            "required": ["parent_lv_name", "lv_to_place_ref", "ring_name", "num_detectors", "radius"]
        }
    },
    {
        "name": "delete_objects",
        "description": "Delete one or more objects from the project.",
        "parameters": {
            "type": "object",
            "properties": {
                "objects": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "type": {"type": "string", "enum": ["solid", "logical_volume", "physical_volume", "material", "define", "assembly"]},
                            "id": {"type": "string", "description": "The name or ID of the object."}
                        }
                    }
                }
            },
            "required": ["objects"]
        }
    },
    {
        "name": "create_parameter_registry",
        "description": "Register a project parameter for optimization by linking it to a component property (e.g., define, solid parameter, source field).",
        "parameters": {
            "type": "object",
            "properties": {
                "param_name": {"type": "string", "description": "Unique name for this parameter in the registry."},
                "target_type": {"type": "string", "enum": ["define", "solid", "source", "sim_option"], "description": "Type of component to modify."},
                "target_ref": {"type": "object", "description": "Reference to the target component and property."},
                "bounds": {"type": "object", "description": "Min/max bounds for optimization."},
                "default": {"type": "number", "description": "Default value for the parameter."}
            },
            "required": ["param_name", "target_type", "target_ref", "bounds"]
        }
    },
    {
        "name": "setup_param_study",
        "description": "Create a parameter study configuration for optimization. Define which parameters to vary and what objectives to optimize.",
        "parameters": {
            "type": "object",
            "properties": {
                "study_name": {"type": "string", "description": "Unique name for this parameter study."},
                "mode": {"type": "string", "enum": ["grid", "random"], "description": "Study mode: 'grid' for systematic sweeps, 'random' for random sampling."},
                "parameters": {"type": "array", "items": {"type": "string"}, "description": "List of parameter names from the registry to include."},
                "objectives": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string", "description": "Objective name (e.g., 'efficiency', 'timing_resolution')."},
                            "direction": {"type": "string", "enum": ["maximize", "minimize"]},
                            "metric": {"type": "string", "description": "Metric to compute (for grid/random mode studies)."},
                            "weight": {"type": "number", "description": "Weight for multi-objective optimization."}
                        }
                    },
                    "description": "Objectives to optimize. At least one required for optimizer runs."
                },
                "simulation_source_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional source ids to persist with the study so simulation-in-loop runs use the same selected source subset as the UI."
                },
                "grid": {"type": "object", "description": "Grid-specific settings (steps, per_parameter_steps)."},
                "random": {"type": "object", "description": "Random-specific settings (samples, seed)."}
            },
            "required": ["study_name", "mode", "parameters", "objectives"]
        }
    },
    {
        "name": "run_optimization",
        "description": "Run an optimizer on an existing parameter study. Supports regular optimization and optional simulation-in-loop optimization.",
        "parameters": {
            "type": "object",
            "properties": {
                "study_name": {"type": "string", "description": "Name of the parameter study to optimize."},
                "method": {"type": "string", "enum": ["random_search", "cmaes", "surrogate_gp"], "description": "Optimization algorithm to use."},
                "budget": {"type": "integer", "description": "Maximum number of candidate evaluations (policy-capped)."},
                "seed": {"type": "integer", "description": "Random seed for reproducibility."},
                "objective_name": {"type": "string", "description": "Which objective to optimize (if study has multiple)."},
                "direction": {"type": "string", "enum": ["maximize", "minimize"], "description": "Optimization direction."},
                "cmaes_config": {"type": "object", "description": "CMA-ES specific configuration (population_size, sigma, etc.)."},
                "surrogate_config": {"type": "object", "description": "Surrogate model config (warmup_runs, candidate_pool_size, exploration_beta, gp_noise)."},
                "simulation_in_loop": {"type": "boolean", "description": "If true, run simulation-in-loop optimization."},
                "sim_objectives": {"type": "array", "items": {"type": "object"}, "description": "Required when simulation_in_loop=true. Objective extraction specs for simulation output."},
                "sim_params": {"type": "object", "description": "Simulation runtime params (events, threads)."},
                "sim_events": {"type": "integer", "description": "Legacy alias for sim_params.events."},
                "sim_threads": {"type": "integer", "description": "Legacy alias for sim_params.threads."},
                "selected_source_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional source ids to use for simulation-in-loop runs."
                },
                "max_wall_time_seconds": {"type": "integer", "description": "Optional run wall-time budget."},
                "context": {"type": "object", "description": "Optional static context exposed to simulation objective extraction formulas."},
                "keep_candidate_runs": {"type": "boolean", "description": "If true, persist per-candidate simulation output folders."},
                "candidate_runs_root": {"type": "string", "description": "Directory where per-candidate run artifacts are stored when keep_candidate_runs=true."}
            },
            "required": ["study_name", "method", "budget"]
        }
    },
    {
        "name": "apply_best_result",
        "description": "Apply the best parameters from an optimization run to the current geometry.",
        "parameters": {
            "type": "object",
            "properties": {
                "run_id": {"type": "string", "description": "ID of the optimization run."},
                "apply_to_project": {"type": "boolean", "description": "If true, permanently apply to project. If false, just preview."}
            },
            "required": ["run_id"]
        }
    },
    {
        "name": "list_optimizer_runs",
        "description": "List past optimization runs, optionally filtered by study name.",
        "parameters": {
            "type": "object",
            "properties": {
                "study_name": {"type": "string", "description": "Filter runs by study name."},
                "limit": {"type": "integer", "description": "Maximum number of runs to return."}
            }
        }
    },
    {
        "name": "verify_best_candidate",
        "description": "Verify an optimization result by re-running the best candidate multiple times to check consistency.",
        "parameters": {
            "type": "object",
            "properties": {
                "run_id": {"type": "string", "description": "ID of the optimization run."},
                "repeats": {"type": "integer", "description": "Number of verification runs (max 100)."}
            },
            "required": ["run_id"]
        }
    },
    {
        "name": "set_volume_appearance",
        "description": "Set the visual color and opacity of a logical volume.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "The name of the logical volume."},
                "color": {"type": "string", "description": "Hex color string or common name (blue, red, lead, etc.)."},
                "opacity": {"type": "number", "description": "Opacity from 0.0 to 1.0."}
            },
            "required": ["name", "color"]
        }
    },
    {
        "name": "delete_detector_ring",
        "description": "Delete all instances of a detector ring by its name.",
        "parameters": {
            "type": "object",
            "properties": {
                "ring_name": {"type": "string", "description": "The base name of the ring to delete (e.g., 'PET_ring')."}
            },
            "required": ["ring_name"]
        }
    },
    {
        "name": "run_preflight_checks",
        "description": "Run deterministic geometry preflight validation and return issue diagnostics plus summary metadata.",
        "parameters": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "run_preflight_scope",
        "description": "Run deterministic preflight checks, then return both full-geometry and scoped-subtree diagnostics plus summary deltas.",
        "parameters": {
            "type": "object",
            "properties": {
                "scope": {
                    "type": "object",
                    "description": "Scope selector object.",
                    "properties": {
                        "type": {
                            "type": "string",
                            "description": "Scope type (logical_volume or assembly; aliases like lv/asm accepted)."
                        },
                        "name": {
                            "type": "string",
                            "description": "Logical volume or assembly name to scope preflight to."
                        }
                    }
                }
            },
            "required": ["scope"]
        }
    },
    {
        "name": "compare_preflight_summaries",
        "description": "Compare two preflight summaries and highlight added/resolved issue codes with deterministic deltas.",
        "parameters": {
            "type": "object",
            "properties": {
                "baseline_summary": {
                    "type": "object",
                    "description": "Reference preflight summary (usually from an earlier version/run)."
                },
                "candidate_summary": {
                    "type": "object",
                    "description": "New preflight summary to compare against baseline."
                }
            },
            "required": ["baseline_summary", "candidate_summary"]
        }
    },
    {
        "name": "compare_preflight_versions",
        "description": "Run deterministic preflight checks on two saved project versions and compare their summaries.",
        "parameters": {
            "type": "object",
            "properties": {
                "baseline_version_id": {
                    "type": "string",
                    "description": "Reference version id to use as baseline."
                },
                "candidate_version_id": {
                    "type": "string",
                    "description": "Version id to evaluate as candidate."
                },
                "project_name": {
                    "type": "string",
                    "description": "Optional project name. Defaults to the currently active project."
                }
            },
            "required": ["baseline_version_id", "candidate_version_id"]
        }
    },
    {
        "name": "compare_latest_preflight_versions",
        "description": "Compare deterministic preflight summaries for the latest two saved project versions.",
        "parameters": {
            "type": "object",
            "properties": {
                "project_name": {
                    "type": "string",
                    "description": "Optional project name. Defaults to the currently active project."
                }
            }
        }
    },
    {
        "name": "compare_autosave_preflight_vs_latest_saved",
        "description": "Compare deterministic preflight summaries for the latest autosave version against the latest manually saved version.",
        "parameters": {
            "type": "object",
            "properties": {
                "project_name": {
                    "type": "string",
                    "description": "Optional project name. Defaults to the currently active project."
                }
            }
        }
    },
    {
        "name": "compare_autosave_preflight_vs_previous_manual_saved",
        "description": "Compare deterministic preflight summaries for the latest autosave version against the latest manually saved non-snapshot version (excluding autosave snapshots automatically).",
        "parameters": {
            "type": "object",
            "properties": {
                "project_name": {
                    "type": "string",
                    "description": "Optional project name. Defaults to the currently active project."
                }
            }
        }
    },
    {
        "name": "compare_autosave_preflight_vs_manual_saved_index",
        "description": "Compare deterministic preflight summaries for the latest autosave version against an N-back manually saved non-snapshot version (0 = latest manual save, 1 = previous, etc.).",
        "parameters": {
            "type": "object",
            "properties": {
                "manual_saved_index": {
                    "type": "integer",
                    "description": "Non-negative N-back index into manually saved non-snapshot versions sorted newest-first (default: 0)."
                },
                "project_name": {
                    "type": "string",
                    "description": "Optional project name. Defaults to the currently active project."
                }
            }
        }
    },
    {
        "name": "compare_autosave_preflight_vs_manual_saved_for_simulation_run",
        "description": "Compare deterministic preflight summaries for the latest autosave version against the latest manually saved non-snapshot version that contains a specific simulation run id.",
        "parameters": {
            "type": "object",
            "properties": {
                "simulation_run_id": {
                    "type": "string",
                    "description": "Simulation run id (job id) that must exist under the baseline version's sim_runs directory."
                },
                "project_name": {
                    "type": "string",
                    "description": "Optional project name. Defaults to the currently active project."
                }
            },
            "required": ["simulation_run_id"]
        }
    },
    {
        "name": "compare_autosave_preflight_vs_manual_saved_for_simulation_run_index",
        "description": "Compare deterministic preflight summaries for the latest autosave version against an N-back manually saved non-snapshot version matching a specific simulation run id (0 = latest matching manual save).",
        "parameters": {
            "type": "object",
            "properties": {
                "simulation_run_id": {
                    "type": "string",
                    "description": "Simulation run id (job id) that must exist under the baseline version's sim_runs directory."
                },
                "manual_saved_index": {
                    "type": "integer",
                    "description": "Non-negative N-back index into matching manually saved non-snapshot versions sorted newest-first (default: 0)."
                },
                "project_name": {
                    "type": "string",
                    "description": "Optional project name. Defaults to the currently active project."
                }
            },
            "required": ["simulation_run_id"]
        }
    },
    {
        "name": "list_manual_saved_versions_for_simulation_run",
        "description": "List manually saved non-snapshot versions that contain a specific simulation run id, sorted newest-first with deterministic manual_saved_index metadata.",
        "parameters": {
            "type": "object",
            "properties": {
                "simulation_run_id": {
                    "type": "string",
                    "description": "Simulation run id (job id) used to filter matching manually saved non-snapshot versions."
                },
                "project_name": {
                    "type": "string",
                    "description": "Optional project name. Defaults to the currently active project."
                },
                "limit": {
                    "type": "integer",
                    "description": "Optional maximum number of matching versions to return."
                }
            },
            "required": ["simulation_run_id"]
        }
    },
    {
        "name": "compare_manual_preflight_versions_for_simulation_run_indices",
        "description": "Compare deterministic preflight summaries between two manually saved non-snapshot versions selected by N-back indices within one simulation run id (defaults: baseline=1 previous, candidate=0 latest).",
        "parameters": {
            "type": "object",
            "properties": {
                "simulation_run_id": {
                    "type": "string",
                    "description": "Simulation run id (job id) that must exist under both selected manual version sim_runs directories."
                },
                "baseline_manual_saved_index": {
                    "type": "integer",
                    "description": "Non-negative N-back index for the baseline manual version among matching non-snapshot versions sorted newest-first (default: 1)."
                },
                "candidate_manual_saved_index": {
                    "type": "integer",
                    "description": "Non-negative N-back index for the candidate manual version among matching non-snapshot versions sorted newest-first (default: 0)."
                },
                "project_name": {
                    "type": "string",
                    "description": "Optional project name. Defaults to the currently active project."
                }
            },
            "required": ["simulation_run_id"]
        }
    },
    {
        "name": "compare_autosave_preflight_vs_saved_version",
        "description": "Compare deterministic preflight summaries for the latest autosave version against a specific manually saved version.",
        "parameters": {
            "type": "object",
            "properties": {
                "saved_version_id": {
                    "type": "string",
                    "description": "Saved version id to use as baseline for autosave comparison."
                },
                "project_name": {
                    "type": "string",
                    "description": "Optional project name. Defaults to the currently active project."
                }
            },
            "required": ["saved_version_id"]
        }
    },
    {
        "name": "compare_autosave_preflight_vs_snapshot_version",
        "description": "Compare deterministic preflight summaries for the latest autosave version against a selected saved autosave snapshot version.",
        "parameters": {
            "type": "object",
            "properties": {
                "autosave_snapshot_version_id": {
                    "type": "string",
                    "description": "Saved autosave snapshot version id to use as baseline for comparison. Use list_preflight_versions metadata to discover valid snapshot ids."
                },
                "project_name": {
                    "type": "string",
                    "description": "Optional project name. Defaults to the currently active project."
                }
            },
            "required": ["autosave_snapshot_version_id"]
        }
    },
    {
        "name": "compare_autosave_preflight_vs_latest_snapshot",
        "description": "Compare deterministic preflight summaries for the latest autosave version against the most recent saved autosave snapshot version.",
        "parameters": {
            "type": "object",
            "properties": {
                "project_name": {
                    "type": "string",
                    "description": "Optional project name. Defaults to the currently active project."
                }
            }
        }
    },
    {
        "name": "compare_autosave_preflight_vs_previous_snapshot",
        "description": "Compare deterministic preflight summaries for the latest autosave version against the previous saved autosave snapshot version.",
        "parameters": {
            "type": "object",
            "properties": {
                "project_name": {
                    "type": "string",
                    "description": "Optional project name. Defaults to the currently active project."
                }
            }
        }
    },
    {
        "name": "compare_autosave_snapshot_preflight_versions", 
        "description": "Compare deterministic preflight summaries between two selected saved autosave snapshot versions.",
        "parameters": {
            "type": "object",
            "properties": {
                "baseline_snapshot_version_id": {
                    "type": "string",
                    "description": "Reference autosave snapshot version id to use as baseline."
                },
                "candidate_snapshot_version_id": {
                    "type": "string",
                    "description": "Autosave snapshot version id to evaluate as candidate."
                },
                "project_name": {
                    "type": "string",
                    "description": "Optional project name. Defaults to the currently active project."
                }
            },
            "required": ["baseline_snapshot_version_id", "candidate_snapshot_version_id"]
        }
    },
    {
        "name": "compare_latest_autosave_snapshot_preflight_versions",
        "description": "Compare deterministic preflight summaries between the latest two saved autosave snapshot versions.",
        "parameters": {
            "type": "object",
            "properties": {
                "project_name": {
                    "type": "string",
                    "description": "Optional project name. Defaults to the currently active project."
                }
            }
        }
    },
    {
        "name": "list_preflight_versions",
        "description": "List available autosave/manual version ids and metadata to support deterministic preflight comparisons.",
        "parameters": {
            "type": "object",
            "properties": {
                "project_name": {
                    "type": "string",
                    "description": "Optional project name. Defaults to the currently active project."
                },
                "include_autosave": {
                    "type": "boolean",
                    "description": "Whether to include the latest autosave entry when present (default: true)."
                },
                "limit": {
                    "type": "integer",
                    "description": "Optional maximum number of version entries to return."
                }
            }
        }
    },
    {
        "name": "run_simulation",
        "description": "Start a Geant4 simulation run to test the current geometry.",
        "parameters": {
            "type": "object",
            "properties": {
                "events": {"type": "integer", "description": "Number of events to simulate (default: 1000)."},
                "threads": {"type": "integer", "description": "Number of CPU threads (default: 1)."},
                **RUN_SIMULATION_OPTION_SPECS,
            }
        }
    },
    {
        "name": "get_simulation_status",
        "description": "Check the status of a previously started simulation job.",
        "parameters": {
            "type": "object",
            "properties": {
                "job_id": {"type": "string", "description": "The unique ID of the simulation job."},
                "include_logs": {"type": "boolean", "description": "Whether to include log output from the solver (default: true)."},
                "include_log_summary": {"type": "boolean", "description": "Whether to include compact log diagnostics (line counts + latest lines, default: true)."},
                "include_log_entries": {"type": "boolean", "description": "Whether to include structured log entries with source and cursor fields for reliable incremental parsing (default: false)."},
                "tail_lines": {"type": "integer", "description": "How many lines from the end of the requested log stream to return when 'since' is not provided."},
                "max_lines": {"type": "integer", "description": "Maximum number of log lines to return. With 'since', this enables chunked pagination; response.next_since advances by the returned count."},
                "since": {"type": "integer", "description": "Return log lines starting from this line index (0-based)."},
                "log_contains": {"type": "string", "description": "Optional case-insensitive substring filter applied before pagination. Useful for pulling only warnings/errors or keyword-matched lines."},
                "log_contains_any": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional case-insensitive OR filter. Keep lines containing at least one provided substring (e.g. ['warn', 'error']). Combines with log_contains when both are present."
                },
                "log_source": {
                    "type": "string",
                    "enum": ["stdout", "stderr", "both"],
                    "description": "Whether to return stdout, stderr, or both streams (default: both)."
                }
            },
            "required": ["job_id"]
        }
    },
    {
        "name": "get_analysis_summary",
        "description": "Get a physics-based summary of the simulation results (energy peaks, hit counts, etc.).",
        "parameters": {
            "type": "object",
            "properties": {
                "job_id": {"type": "string", "description": "The unique ID of the simulation job."}
            },
            "required": ["job_id"]
        }
    },
    {
        "name": "batch_geometry_update",
        "description": "Execute multiple geometry operations in a single high-efficiency batch. Use this when you have many objects to create or modify at once.",
        "parameters": {
            "type": "object",
            "properties": {
                "operations": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "tool_name": {"type": "string", "description": "Name of the tool to call."},
                            "arguments": {"type": "object", "description": "Arguments for that tool."}
                        }
                    }
                }
            },
            "required": ["operations"]
        }
    },
    {
        "name": "insert_physics_template",
        "description": "Insert a pre-defined high-level physics component (like a SiPM array, cryostat, phantom, or field probe slab).",
        "parameters": {
            "type": "object",
            "properties": {
                "template_name": {"type": "string", "enum": ["sipm_array", "cryostat", "phantom", "field_probe_slab"]},
                "params": {"type": "object", "description": "Parameters for the chosen template."},
                "parent_lv_name": {"type": "string", "description": "Which volume to place the component into."},
                "position": {"type": "object", "description": "Relative position of the whole component {'x':..., 'y':..., 'z':...}"}
            },
            "required": ["template_name", "params", "parent_lv_name"]
        }
    },
    {
        "name": "manage_optical_surface",
        "description": "Create or update an optical surface (properties for mirrors, scintillators, etc.).",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "model": {"type": "string", "enum": ["glisur", "unified"]},
                "finish": {"type": "string", "enum": ["polished", "polishedfrontpainted", "polishedbackpainted", "ground", "groundfrontpainted", "groundbackpainted"]},
                "type": {"type": "string", "enum": ["dielectric_metal", "dielectric_dielectric", "dielectric_LUT", "firsov", "x_ray"]},
                "value": {"type": "string", "description": "Surface property value (e.g., sigma alpha)."},
                "properties": {"type": "object", "description": "Optical properties (REFLECTIVITY, RINDEX, etc.) as name-value or name-array pairs."}
            },
            "required": ["name"]
        }
    },
    {
        "name": "manage_surface_link",
        "description": "Link an optical surface to a volume (Skin Surface) or an interface between two volumes (Border Surface).",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "surface_ref": {"type": "string", "description": "Name of the optical surface to apply."},
                "link_type": {"type": "string", "enum": ["skin", "border"]},
                "volume_ref": {"type": "string", "description": "For 'skin' type: the logical volume name."},
                "pv1_id": {"type": "string", "description": "For 'border' type: the first physical volume ID."},
                "pv2_id": {"type": "string", "description": "For 'border' type: the second physical volume ID."}
            },
            "required": ["name", "surface_ref", "link_type"]
        }
    },
    {
        "name": "manage_assembly",
        "description": "Create or update an assembly (a reusable group of placements).",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "placements": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string", "description": "Optional placement name. If omitted, AIRPET auto-generates a deterministic name."},
                            "placement_name": {"type": "string", "description": "Alias for placement name."},
                            "volume_ref": {"type": "string"},
                            "position": {"type": "object"},
                            "rotation": {"type": "object"},
                            "copy_number": {"type": "integer"}
                        },
                        "required": ["volume_ref"]
                    }
                }
            },
            "required": ["name", "placements"]
        }
    },
    {
        "name": "manage_ui_group",
        "description": "Organize project components into visual groups in the UI.",
        "parameters": {
            "type": "object",
            "properties": {
                "group_type": {"type": "string", "enum": ["solid", "logical_volume", "material", "assembly", "define"]},
                "group_name": {"type": "string"},
                "item_ids": {"type": "array", "items": {"type": "string"}, "description": "List of component names/IDs to move to this group."},
                "action": {"type": "string", "enum": ["create", "add_items", "remove_group"]}
            },
            "required": ["group_type", "group_name", "action"]
        }
    },
    {
        "name": "evaluate_expression",
        "description": "Evaluate a mathematical expression or check a variable value.",
        "parameters": {
            "type": "object",
            "properties": {
                "expression": {"type": "string"}
            },
            "required": ["expression"]
        }
    },
    {
        "name": "manage_particle_source",
        "description": "Low-level GPS tool for creating or editing particle sources directly. Prefer configure_incident_beam for simple monoenergetic beams aimed at a target volume. All gps_commands values must be strings with units. Energy format: use '100*keV' or '1*GeV' (with * operator). Geant4 angular modes are ang/type='beam1d' for directed beams and ang/type='iso' for isotropic emission; friendly aliases like 'Direction' and 'Isotropic' are normalized. Geant4 particle names prefer 'e-' and 'e+'; common aliases like 'electron'/'positron' are normalized.",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["create", "update", "update_transform"]},
                "source_id": {"type": "string", "description": "Required for update/update_transform."},
                "name": {"type": "string"},
                "gps_commands": {"type": "object", "description": "GPS commands as key-value pairs. ALL values must be strings. Use energy format '100*keV' or '1*GeV'. Examples: {'particle': 'e-', 'energy': '10*keV', 'pos/type': 'Point', 'ang/type': 'beam1d', 'ang/dir1': '0 0 1'}. Common particles: gamma, e-, e+, proton. Use ang/type='beam1d' for directed beams and ang/type='iso' for isotropic emission. Friendly aliases like distribution/direction/electron are normalized."},
                "position": {"type": "object"},
                "rotation": {"type": "object"},
                "activity": {"type": "number"},
                "confine_to_pv": {"type": "string"},
                "volume_link_id": {"type": "string"}
            },
            "required": ["action"]
        }
    },
    {
        "name": "configure_incident_beam",
        "description": "Create or update a monoenergetic directed beam aimed at the center of a target volume. Prefer this over raw GPS commands for requests like '10 keV electron incident on a 10 micrometer silicon slab'. The target may be a physical-volume id/name or a logical-volume name if that LV has exactly one placement. By default this also marks the target logical volume sensitive so deposited-energy hits will be recorded.",
        "parameters": {
            "type": "object",
            "properties": {
                "target": {"type": "string", "description": "Target physical volume id/name, or logical volume name if uniquely placed."},
                "source_name": {"type": "string", "description": "Optional source name; defaults to 'incident_beam'."},
                "particle": {"type": "string", "description": "Beam particle, e.g. 'e-', 'gamma', 'proton'. Common aliases like 'electron' are normalized."},
                "energy": {"type": "string", "description": "Beam energy, e.g. '10*keV'."},
                "incident_axis": {"type": "string", "enum": ["+x", "-x", "+y", "-y", "+z", "-z"], "description": "Beam travel direction in the target's local coordinates."},
                "offset": {"type": "string", "description": "Upstream distance from the target surface to the source point, e.g. '1*mm'."},
                "activity": {"type": "number", "description": "Relative source activity/intensity."},
                "mark_target_sensitive": {"type": "boolean", "description": "If true, mark the target logical volume sensitive so hits are recorded. Defaults to true."},
                "activate": {"type": "boolean", "description": "If true, activate the configured beam source."},
                "exclusive_activation": {"type": "boolean", "description": "If true, make this the only active source."}
            },
            "required": ["target", "particle", "energy"]
        }
    },
    {
        "name": "set_active_source",
        "description": "Activate/deactivate a source by id, or clear all active sources by passing null/empty source_id.",
        "parameters": {
            "type": "object",
            "properties": {
                "source_id": {"type": "string"}
            }
        }
    },
    {
        "name": "process_lors",
        "description": "Process simulation hits into coincidence LORs for PET reconstruction.",
        "parameters": {
            "type": "object",
            "properties": {
                "version_id": {"type": "string"},
                "job_id": {"type": "string"},
                "coincidence_window_ns": {"type": "number"},
                "energy_cut": {"type": "number"},
                "energy_resolution": {"type": "number"},
                "position_resolution": {"type": "object"}
            },
            "required": ["job_id"]
        }
    },
    {
        "name": "get_lor_status",
        "description": "Get status/progress of a background LOR processing job.",
        "parameters": {
            "type": "object",
            "properties": {
                "job_id": {"type": "string"}
            },
            "required": ["job_id"]
        }
    },
    {
        "name": "check_lor_file",
        "description": "Check whether a processed LOR file exists for a run and return metadata if available.",
        "parameters": {
            "type": "object",
            "properties": {
                "version_id": {"type": "string"},
                "job_id": {"type": "string"}
            },
            "required": ["job_id"]
        }
    },
    {
        "name": "run_reconstruction",
        "description": "Run PET image reconstruction from LORs (MLEM + optional normalization/attenuation correction).",
        "parameters": {
            "type": "object",
            "properties": {
                "version_id": {"type": "string"},
                "job_id": {"type": "string"},
                "iterations": {"type": "integer"},
                "image_size": {"type": "array", "items": {"type": "integer"}},
                "voxel_size": {"type": "array", "items": {"type": "number"}},
                "normalization": {"type": "boolean"},
                "ac_enabled": {"type": "boolean"},
                "ac_shape": {"type": "string", "enum": ["cylinder"]},
                "ac_radius": {"type": "number"},
                "ac_length": {"type": "number"},
                "ac_mu": {"type": "number"}
            },
            "required": ["job_id"]
        }
    },
    {
        "name": "compute_sensitivity",
        "description": "Compute/store a Monte Carlo sensitivity matrix for a run.",
        "parameters": {
            "type": "object",
            "properties": {
                "version_id": {"type": "string"},
                "job_id": {"type": "string"},
                "voxel_size": {"type": "number"},
                "matrix_size": {"type": "integer"},
                "ac_enabled": {"type": "boolean"},
                "ac_mu": {"type": "number"},
                "ac_radius": {"type": "number"},
                "num_random_lors": {"type": "integer"}
            },
            "required": ["job_id"]
        }
    },
    {
        "name": "get_sensitivity_status",
        "description": "Check if a sensitivity matrix exists for a run.",
        "parameters": {
            "type": "object",
            "properties": {
                "version_id": {"type": "string"},
                "job_id": {"type": "string"}
            },
            "required": ["job_id"]
        }
    },
    {
        "name": "stop_simulation",
        "description": "Stop a running Geant4 simulation job.",
        "parameters": {
            "type": "object",
            "properties": {
                "job_id": {"type": "string"}
            },
            "required": ["job_id"]
        }
    },
    {
        "name": "get_simulation_metadata",
        "description": "Fetch metadata for a simulation run (job config, paths, etc.).",
        "parameters": {
            "type": "object",
            "properties": {
                "version_id": {"type": "string"},
                "job_id": {"type": "string"}
            },
            "required": ["job_id"]
        }
    },
    {
        "name": "get_scoring_summary",
        "description": "Fetch a compact scoring-result summary for one simulation run, including the saved scoring setup summary, bundle status, and per-quantity totals when scoring artifacts exist.",
        "parameters": {
            "type": "object",
            "properties": {
                "version_id": {"type": "string"},
                "job_id": {"type": "string"}
            },
            "required": ["job_id"]
        }
    },
    {
        "name": "get_simulation_analysis",
        "description": "Fetch rich analysis outputs (spectra, heatmaps, volume/particle breakdown). Optionally filter by sensitive_detector.",
        "parameters": {
            "type": "object",
            "properties": {
                "version_id": {"type": "string"},
                "job_id": {"type": "string"},
                "energy_bins": {"type": "integer"},
                "spatial_bins": {"type": "integer"},
                "sensitive_detector": {
                    "type": "string",
                    "description": "Optional sensitive detector name to filter hits before building histograms and summaries."
                }
            },
            "required": ["job_id"]
        }
    },
    {
        "name": "rename_ui_group",
        "description": "Rename an existing UI group.",
        "parameters": {
            "type": "object",
            "properties": {
                "group_type": {"type": "string", "enum": ["solid", "logical_volume", "material", "assembly", "define"]},
                "old_name": {"type": "string"},
                "new_name": {"type": "string"}
            },
            "required": ["group_type", "old_name", "new_name"]
        }
    }
]
