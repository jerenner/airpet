# src/step_parser.py
import os
import numpy as np

from OCC.Core.STEPControl import STEPControl_Reader
from OCC.Core.TopAbs import TopAbs_SOLID, TopAbs_FACE, TopAbs_REVERSED
from OCC.Core.TopExp import TopExp_Explorer
from OCC.Core.BRep import BRep_Tool
from OCC.Core.BRepMesh import BRepMesh_IncrementalMesh
from OCC.Core.TopLoc import TopLoc_Location
from OCC.Core.gp import gp_Trsf
from OCC.Core.TDF import TDF_Label, TDF_LabelSequence
from OCC.Core.XCAFDoc import XCAFDoc_DocumentTool
from OCC.Core.STEPCAFControl import STEPCAFControl_Reader
from OCC.Core.TDocStd import TDocStd_Document

from .expression_evaluator import ExpressionEvaluator 
from .geometry_types import (
    GeometryState, Define, Solid, LogicalVolume, Material, PhysicalVolumePlacement, Assembly
)
from .smart_cad_classifier import (
    classify_shape,
    summarize_candidates,
    get_smart_import_policy,
    resolve_candidate_selection,
)

def _trsf_to_dict(trsf: gp_Trsf):
    """Converts a gp_Trsf to our position and rotation dict format."""
    quat = trsf.GetRotation()
    tran = trsf.TranslationPart()
    
    # We will borrow the robust method from G4GDMLWriteDefine.cc via GDMLWriter
    # This avoids gimbal lock and other issues with direct Euler conversion.
    try:
        # GetEulerAngles returns angles in Z-Y'-X'' sequence (Tait-Bryan)
        alpha, beta, gamma = quat.GetEulerAngles(0) # Using default sequence, often ZYX
    except Exception:
        # Fallback for identity quaternions or other issues
        alpha, beta, gamma = 0,0,0

    # The order of angles (alpha, beta, gamma) corresponds to (z, y, x) for ZYX Euler sequence.
    return {
        "position": {"x": tran.X(), "y": tran.Y(), "z": tran.Z()},
        "rotation": {"x": gamma, "y": beta, "z": alpha} 
    }

def _as_xyz_dict(value, default=(0.0, 0.0, 0.0)):
    if isinstance(value, dict):
        return {
            'x': float(value.get('x', default[0])),
            'y': float(value.get('y', default[1])),
            'z': float(value.get('z', default[2])),
        }
    if isinstance(value, (list, tuple)) and len(value) == 3:
        return {'x': float(value[0]), 'y': float(value[1]), 'z': float(value[2])}
    return {'x': float(default[0]), 'y': float(default[1]), 'z': float(default[2])}


def _transform_dict_to_matrix(transform_dict):
    pv = PhysicalVolumePlacement(name="_tmp", volume_ref="_tmp")
    pv._evaluated_position = _as_xyz_dict(transform_dict.get('position', {}), default=(0.0, 0.0, 0.0))
    pv._evaluated_rotation = _as_xyz_dict(transform_dict.get('rotation', {}), default=(0.0, 0.0, 0.0))
    pv._evaluated_scale = {'x': 1.0, 'y': 1.0, 'z': 1.0}
    return pv.get_transform_matrix()


def _matrix_to_transform_dict(matrix):
    pos, rot, _ = PhysicalVolumePlacement.decompose_matrix(matrix)
    return {
        'position': {'x': float(pos['x']), 'y': float(pos['y']), 'z': float(pos['z'])},
        'rotation': {'x': float(rot['x']), 'y': float(rot['y']), 'z': float(rot['z'])},
    }


def _compose_transform_dicts(parent_transform, local_transform):
    parent_matrix = _transform_dict_to_matrix(parent_transform)
    local_matrix = _transform_dict_to_matrix(local_transform)
    return _matrix_to_transform_dict(parent_matrix @ local_matrix)


def _normalize_vec3(vec, default=(1.0, 0.0, 0.0)):
    arr = np.array(vec, dtype=float)
    n = np.linalg.norm(arr)
    if n < 1e-12:
        return np.array(default, dtype=float)
    return arr / n


def _orthonormal_frame_from_axis(axis):
    z = _normalize_vec3(axis, default=(0.0, 0.0, 1.0))
    ref = np.array([1.0, 0.0, 0.0]) if abs(np.dot(z, [1.0, 0.0, 0.0])) < 0.9 else np.array([0.0, 1.0, 0.0])
    x = _normalize_vec3(np.cross(ref, z), default=(1.0, 0.0, 0.0))
    y = _normalize_vec3(np.cross(z, x), default=(0.0, 1.0, 0.0))
    return x, y, z


def _basis_to_rotation_transform(center, x_axis, y_axis, z_axis):
    x = _normalize_vec3(x_axis, default=(1.0, 0.0, 0.0))
    y_tmp = _normalize_vec3(y_axis, default=(0.0, 1.0, 0.0))

    # Gram-Schmidt to keep a numerically stable orthonormal basis.
    y = y_tmp - np.dot(y_tmp, x) * x
    y = _normalize_vec3(y, default=(0.0, 1.0, 0.0))

    z = _normalize_vec3(z_axis, default=(0.0, 0.0, 1.0))
    z = z - np.dot(z, x) * x - np.dot(z, y) * y
    z = _normalize_vec3(z, default=np.cross(x, y))

    # Ensure right-handed frame.
    if np.dot(np.cross(x, y), z) < 0.0:
        z = -z

    m = np.eye(4)
    m[:3, 0] = x
    m[:3, 1] = y
    m[:3, 2] = z
    m[:3, 3] = np.array(center, dtype=float)

    return _matrix_to_transform_dict(m)


def _candidate_local_transform(candidate):
    params = candidate.get('params', {}) or {}
    classification = candidate.get('classification')

    if classification == 'box':
        center = params.get('center', (0.0, 0.0, 0.0))
        axes = params.get('axes', [])
        if isinstance(axes, list) and len(axes) == 3:
            return _basis_to_rotation_transform(center, axes[0], axes[1], axes[2])
        return {
            'position': _as_xyz_dict(center),
            'rotation': {'x': 0.0, 'y': 0.0, 'z': 0.0},
        }

    if classification == 'cylinder':
        center = params.get('center', (0.0, 0.0, 0.0))
        axis = params.get('axis', (0.0, 0.0, 1.0))
        x, y, z = _orthonormal_frame_from_axis(axis)
        return _basis_to_rotation_transform(center, x, y, z)

    if classification == 'sphere':
        center = params.get('center', (0.0, 0.0, 0.0))
        return {
            'position': _as_xyz_dict(center),
            'rotation': {'x': 0.0, 'y': 0.0, 'z': 0.0},
        }

    return {
        'position': {'x': 0.0, 'y': 0.0, 'z': 0.0},
        'rotation': {'x': 0.0, 'y': 0.0, 'z': 0.0},
    }


def parse_step_file(file_path, options):
    """
    Parses a STEP file with assembly structure and converts its geometry
    into a GeometryState object.
    """
    smart_import_enabled = bool(options.get('smartImport', options.get('smart_import', False)))
    smart_import_policy = get_smart_import_policy(options)

    doc = TDocStd_Document("pythonocc-doc")
    reader = STEPCAFControl_Reader()
    reader.ReadFile(file_path)
    reader.Transfer(doc)

    shape_tool = XCAFDoc_DocumentTool.ShapeTool(doc.Main())
    
    # We will build a temporary state and then merge it into the project.
    imported_state = GeometryState()

    # Smart CAD report scaffold (Phase 3 M1 foundation).
    imported_state.smart_import_report = {
        'enabled': smart_import_enabled,
        'policy': smart_import_policy,
        'candidates': [],
        'summary': summarize_candidates([])
    }
    
    # Use a generic material. The user can change it later.
    default_mat_name = "G4_STAINLESS-STEEL"
    if not imported_state.get_material(default_mat_name):
        default_mat = Material(name=default_mat_name, density_expr="8.0", state="solid", Z_expr="26", A_expr="55.845")
        imported_state.add_material(default_mat)

    # Use the grouping name from options for the imported top-level assembly.
    grouping_name = str(options.get('groupingName', 'STEP_Import'))
    imported_state.grouping_name = grouping_name

    # This list will store all the LVs created from the top-level solids.
    top_level_lvs = []

    root_labels = TDF_LabelSequence()
    shape_tool.GetFreeShapes(root_labels)

    for i in range(1, root_labels.Length() + 1):
        # The return value is a list of LVs created under this root label.
        created_lvs = process_label(
            root_labels.Value(i),
            shape_tool,
            imported_state,
            TopLoc_Location(),
            grouping_name,
            smart_import=smart_import_enabled,
            smart_import_policy=smart_import_policy,
        )
        top_level_lvs.extend(created_lvs)

    # --- Post-processing based on user options ---
    placement_mode = options.get('placementMode', 'assembly')
    parent_lv_name = options.get('parentLVName')
    
    # --- Evaluate the offset expression ---
    # We create a temporary evaluator to resolve any variables in the offset.
    temp_evaluator = ExpressionEvaluator()
    # Note: This simple evaluator doesn't have project defines.
    offset_x_success, offset_x = temp_evaluator.evaluate(options.get('offset', {}).get('x', '0'))
    offset_y_success, offset_y = temp_evaluator.evaluate(options.get('offset', {}).get('y', '0'))
    offset_z_success, offset_z = temp_evaluator.evaluate(options.get('offset', {}).get('z', '0'))
    if(not (offset_x_success and offset_y_success and offset_z_success)):
        global_offset = {'x': 0, 'y': 0, 'z': 0}
    else:
        global_offset = {'x': offset_x, 'y': offset_y, 'z': offset_z}

    if placement_mode == 'assembly':
        # Create a single assembly containing all the top-level LVs.
        assembly_name = grouping_name
        main_assembly = Assembly(name=assembly_name)
        for lv, transform_dict in top_level_lvs:
            pv = PhysicalVolumePlacement(
                name=f"{lv.name}_pv_in_asm",
                volume_ref=lv.name,
                position_val_or_ref=transform_dict['position'],
                rotation_val_or_ref=transform_dict['rotation']
            )
            main_assembly.add_placement(pv)
        imported_state.add_assembly(main_assembly)

        # Create a single PV to place this assembly.
        assembly_placement = PhysicalVolumePlacement(
            name=f"{assembly_name}_placement",
            volume_ref=assembly_name,
            parent_lv_name=parent_lv_name,
            position_val_or_ref={'x': str(global_offset['x']), 'y': str(global_offset['y']), 'z': str(global_offset['z'])}
        )
        # We need a way to add this to the main project state, which will be handled by merge.
        # For now, we can add it to a temporary "placements_to_add" list.
        imported_state.placements_to_add = [assembly_placement]

    else: # 'individual'
        # Place each top-level LV as a separate PV.
        placements = []
        for lv, transform_dict in top_level_lvs:
            part_pos = transform_dict['position']
            
            # Perform vector addition directly in Python
            final_pos = {
                'x': str(part_pos['x'] + global_offset['x']),
                'y': str(part_pos['y'] + global_offset['y']),
                'z': str(part_pos['z'] + global_offset['z'])
            }

            pv = PhysicalVolumePlacement(
                name=f"{lv.name}_pv",
                volume_ref=lv.name,
                parent_lv_name=parent_lv_name,
                position_val_or_ref=final_pos,  # Assign the calculated absolute position
                rotation_val_or_ref=transform_dict['rotation']
            )
            placements.append(pv)
        
        imported_state.placements_to_add = placements

    if smart_import_enabled:
        candidates = imported_state.smart_import_report.get('candidates', [])
        imported_state.smart_import_report['summary'] = summarize_candidates(candidates)

    return imported_state

def process_label(label, shape_tool, state, parent_loc: TopLoc_Location, grouping_name, smart_import=False, smart_import_policy=None):
    """
    Recursively process labels in the STEP file's document tree.
    This version correctly handles assembly, reference, and simple shape labels.
    """
    created_lvs = []

    # Each label can have its own location relative to its parent.
    # We multiply it with the parent's location to get the absolute position.
    current_loc = parent_loc.Multiplied(shape_tool.GetLocation(label))

    # Case 1: The label is an assembly of other components.
    if shape_tool.IsAssembly(label):
        components = TDF_LabelSequence()
        shape_tool.GetComponents(label, components)
        for i in range(1, components.Length() + 1):
            component_label = components.Value(i)
            # An assembly component is a "reference" to another shape definition.
            # We need to get the actual shape definition it's referring to.
            ref_label = TDF_Label()
            if shape_tool.GetReferredShape(component_label, ref_label):
                # Recurse and aggregate the results from children.
                created_lvs.extend(
                    process_label(
                        ref_label,
                        shape_tool,
                        state,
                        current_loc,
                        grouping_name,
                        smart_import=smart_import,
                        smart_import_policy=smart_import_policy,
                    )
                )

    # Case 2: The label is a simple shape (a leaf node in the assembly tree).
    elif shape_tool.IsSimpleShape(label):
        shape = shape_tool.GetShape(label)
        if shape.ShapeType() == TopAbs_SOLID:
            # process_solid now returns the newly created LogicalVolume.
            new_lv = process_solid(
                shape,
                state,
                grouping_name,
                smart_import=smart_import,
                smart_import_policy=smart_import_policy,
            )
            if new_lv:
                # Base transform comes from the component location in the assembly tree.
                transform_dict = _trsf_to_dict(current_loc.Transformation())

                # Primitive-mapped solids can carry additional local center/orientation.
                local_transform = getattr(new_lv, '_smart_local_transform', None)
                if local_transform:
                    transform_dict = _compose_transform_dicts(transform_dict, local_transform)

                created_lvs.append((new_lv, transform_dict))

    return created_lvs


def _candidate_to_primitive(candidate):
    """Maps a smart CAD candidate to primitive Solid params + local transform."""
    classification = candidate.get('classification')
    params = candidate.get('params', {}) or {}

    if classification == 'box':
        return 'box', {
            'x': params.get('x', 0.0),
            'y': params.get('y', 0.0),
            'z': params.get('z', 0.0),
        }, _candidate_local_transform(candidate)

    if classification == 'cylinder':
        return 'tube', {
            'rmin': params.get('rmin', 0.0),
            'rmax': params.get('rmax', 0.0),
            'z': params.get('z', 0.0),
            'startphi': params.get('startphi', 0.0),
            'deltaphi': params.get('deltaphi', 6.283185307179586),
        }, _candidate_local_transform(candidate)

    if classification == 'sphere':
        return 'sphere', {
            'rmin': params.get('rmin', 0.0),
            'rmax': params.get('rmax', 0.0),
            'startphi': params.get('startphi', 0.0),
            'deltaphi': params.get('deltaphi', 6.283185307179586),
            'starttheta': params.get('starttheta', 0.0),
            'deltatheta': params.get('deltatheta', 3.141592653589793),
        }, _candidate_local_transform(candidate)

    return None, None, None


def _build_lv_for_solid(state, solid_name, solid_type, raw_params):
    solid_obj = Solid(solid_name, solid_type, raw_params)
    state.add_solid(solid_obj)

    lv_name = f"{solid_name}_LV"
    lv = LogicalVolume(lv_name, solid_obj.name, "G4_STAINLESS-STEEL")
    state.add_logical_volume(lv)
    return lv


def process_solid(solid_shape, state, grouping_name, smart_import=False, smart_import_policy=None):
    """Builds a solid from STEP geometry.

    Smart import path:
    - classify primitive candidates (box/cylinder/sphere)
    - if confidence is high enough, create primitive GDML solid directly
    - otherwise fallback to tessellated mesh construction
    """
    solid_index = len(state.solids)
    solid_base_name = f"{grouping_name}_solid_{solid_index}"

    # Smart CAD candidate attempt before tessellation.
    if smart_import and hasattr(state, 'smart_import_report'):
        candidate = classify_shape(solid_shape, source_id=solid_base_name)

        primitive_type, primitive_params, local_transform = _candidate_to_primitive(candidate)
        selected = resolve_candidate_selection(
            candidate,
            primitive_mappable=bool(primitive_type),
            policy=smart_import_policy,
        )

        if selected.get('selected_mode') == 'primitive':
            state.smart_import_report.setdefault('candidates', []).append(selected)

            lv = _build_lv_for_solid(state, solid_base_name, primitive_type, primitive_params)
            setattr(lv, '_smart_local_transform', local_transform)
            return lv

        state.smart_import_report.setdefault('candidates', []).append(selected)
    
    # Improved meshing quality. 
    # Linear deflection: max distance between mesh and geometry surface (mm).
    linear_deflection = 0.05 # 50 micrometers
    # Angular deflection in radians.
    angular_deflection = 0.5
    
    mesh = BRepMesh_IncrementalMesh(solid_shape, linear_deflection, False, angular_deflection, True)
    mesh.Perform()
    
    if not mesh.IsDone():
        print(f"Warning: Could not mesh solid #{solid_index}. Skipping.")
        return

    mesh_location = TopLoc_Location()
    breptool_face_explorer = TopExp_Explorer(solid_shape, TopAbs_FACE)
    
    unique_vertices = []
    vertex_map = {} # (x, y, z) -> index
    all_faces = []
    
    while breptool_face_explorer.More():
        face = breptool_face_explorer.Current()
        is_reversed = (face.Orientation() == TopAbs_REVERSED)
        poly = BRep_Tool.Triangulation(face, mesh_location)
        
        if poly:
            nodes = poly.MapNodeArray()
            triangles = poly.MapTriangleArray()
            
            local_to_global_idx = {}
            for i in range(1, poly.NbNodes() + 1):
                p = nodes.Value(i)
                # Round to 8 decimal places for deduplication
                # Coordinates are in the local system of the part.
                coord = (round(p.X(), 8), round(p.Y(), 8), round(p.Z(), 8))
                if coord not in vertex_map:
                    idx = len(unique_vertices)
                    vertex_map[coord] = idx
                    unique_vertices.append(coord)
                local_to_global_idx[i-1] = vertex_map[coord]
                
            for i in range(1, poly.NbTriangles() + 1):
                n1, n2, n3 = triangles.Value(i).Get()
                
                # --- NEW: Area and Edge Check ---
                v1_idx = local_to_global_idx[n1-1]
                v2_idx = local_to_global_idx[n2-1]
                v3_idx = local_to_global_idx[n3-1]
                
                # Check for degenerate triangle (same vertices)
                if v1_idx == v2_idx or v2_idx == v3_idx or v3_idx == v1_idx:
                    continue
                
                # Calculate sides to check for tiny triangles (Geant4 11.x strictness)
                # P0->P1, P1->P2, P2->P0
                p1 = unique_vertices[v1_idx]
                p2 = unique_vertices[v2_idx]
                p3 = unique_vertices[v3_idx]
                
                def dist_sq(a, b):
                    return (a[0]-b[0])**2 + (a[1]-b[1])**2 + (a[2]-b[2])**2
                
                # Skip if any side is effectively zero (less than 1e-12 mm^2 distance)
                EPS = 1e-12
                if dist_sq(p1, p2) < EPS or dist_sq(p2, p3) < EPS or dist_sq(p3, p1) < EPS:
                    continue

                # Correct winding order based on face orientation
                if is_reversed:
                    all_faces.append((v1_idx, v3_idx, v2_idx))
                else:
                    all_faces.append((v1_idx, v2_idx, v3_idx))
        
        breptool_face_explorer.Next()
    
    if not unique_vertices or not all_faces:
        return

    # Don't create defines. Store vertices directly.
    facets = []
    for face_indices in all_faces:
        v1 = unique_vertices[face_indices[0]]
        v2 = unique_vertices[face_indices[1]]
        v3 = unique_vertices[face_indices[2]]
        facets.append({
            'type': 'triangular',
            'vertex_type': 'ABSOLUTE',
            'vertices': [
                {'x': v1[0], 'y': v1[1], 'z': v1[2]},
                {'x': v2[0], 'y': v2[1], 'z': v2[2]},
                {'x': v3[0], 'y': v3[1], 'z': v3[2]}
            ]
        })
    
    tessellated_solid = Solid(solid_base_name, 'tessellated', {'facets': facets})
    state.add_solid(tessellated_solid)
    
    lv_name = f"{solid_base_name}_LV"
    lv = LogicalVolume(lv_name, tessellated_solid.name, "G4_STAINLESS-STEEL")
    state.add_logical_volume(lv)

    return lv
