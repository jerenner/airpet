# src/step_parser.py
import os

from OCC.Core.STEPControl import STEPControl_Reader
from OCC.Core.TopAbs import TopAbs_SOLID, TopAbs_FACE
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

def _trsf_to_dict(trsf: gp_Trsf):
    """Converts a gp_Trsf to our position and rotation dict format."""
    quat = trsf.GetRotation()
    tran = trsf.TranslationPart()
    
    # We will borrow the robust method from G4GDMLWriteDefine.cc via GDMLWriter
    # This avoids gimbal lock and other issues with direct Euler conversion.
    # Note: This is a conceptual port; the actual math is in your geometry_types.
    # We can simplify by just getting the ZYX euler angles directly, but must be careful.
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

def parse_step_file(file_path, options):
    """
    Parses a STEP file with assembly structure and converts its geometry
    into a GeometryState object.
    """
    doc = TDocStd_Document("pythonocc-doc")
    reader = STEPCAFControl_Reader()
    reader.ReadFile(file_path)
    reader.Transfer(doc)

    shape_tool = XCAFDoc_DocumentTool.ShapeTool(doc.Main())
    
    # We will build a temporary state and then merge it into the project.
    imported_state = GeometryState()
    
    # Use a generic material. The user can change it later.
    default_mat_name = "G4_STAINLESS-STEEL"
    if not imported_state.get_material(default_mat_name):
        default_mat = Material(name=default_mat_name, density_expr="8.0", state="solid", Z_expr="26", A_expr="55.845")
        imported_state.add_material(default_mat)

    assembly_name = os.path.splitext(os.path.basename(file_path))[0].replace(" ", "_")
    main_assembly = Assembly(name=assembly_name)
    imported_state.add_assembly(main_assembly)

    # Use the grouping name from options.
    grouping_name = options.get('groupingName', 'STEP_Import')
    imported_state.grouping_name = grouping_name

    # This list will store all the LVs created from the top-level solids.
    top_level_lvs = []

    root_labels = TDF_LabelSequence()
    shape_tool.GetFreeShapes(root_labels)

    for i in range(1, root_labels.Length() + 1):
        # The return value is a list of LVs created under this root label.
        created_lvs = process_label(root_labels.Value(i), shape_tool, imported_state, TopLoc_Location(), grouping_name)
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
        global_offset = {'x': '0', 'y': '0', 'z': '0'}
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
            position_val_or_ref=global_offset
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

    return imported_state

def process_label(label, shape_tool, state, parent_loc: TopLoc_Location, grouping_name):
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
                created_lvs.extend(process_label(ref_label, shape_tool, state, current_loc, grouping_name))

    # Case 2: The label is a simple shape (a leaf node in the assembly tree).
    elif shape_tool.IsSimpleShape(label):
        shape = shape_tool.GetShape(label)
        if shape.ShapeType() == TopAbs_SOLID:
            # process_solid now returns the newly created LogicalVolume.
            new_lv = process_solid(shape, state, grouping_name)
            if new_lv:
                # The transform comes from the current location in the assembly tree.
                transform_dict = _trsf_to_dict(current_loc.Transformation())
                created_lvs.append((new_lv, transform_dict))

    return created_lvs


def process_solid(solid_shape, state, grouping_name):
    """Tessellates a single solid and adds it to the state and assembly."""
    solid_index = len(state.solids)
    
    # This is a meshing parameter. Smaller values = finer mesh but slower processing.
    meshing_quality = 0.5 
    mesh = BRepMesh_IncrementalMesh(solid_shape, meshing_quality, True)
    mesh.Perform()
    
    if not mesh.IsDone():
        print(f"Warning: Could not mesh solid #{solid_index}. Skipping.")
        return

    mesh_location = TopLoc_Location()
    breptool_face_explorer = TopExp_Explorer(solid_shape, TopAbs_FACE)
    
    all_vertices, all_faces = [], []
    while breptool_face_explorer.More():
        face = breptool_face_explorer.Current()
        poly = BRep_Tool.Triangulation(face, mesh_location)
        if poly:
            nodes = poly.MapNodeArray()
            triangles = poly.MapTriangleArray()
            offset = len(all_vertices)
            
            for i in range(1, poly.NbNodes() + 1):
                p = nodes.Value(i)
                all_vertices.append((p.X(), p.Y(), p.Z()))
                
            for i in range(1, poly.NbTriangles() + 1):
                n1, n2, n3 = triangles.Value(i).Get()
                all_faces.append((n1 - 1 + offset, n2 - 1 + offset, n3 - 1 + offset))
        
        breptool_face_explorer.Next()
    
    if not all_vertices or not all_faces:
        return

    # Don't create defines. Store vertices directly.
    solid_base_name = f"{grouping_name}_solid_{solid_index}"
    
    # The vertices are already in the correct local coordinate system of the part.
    # The 'location' transform will be applied to the PV placement.
    facets = []
    for face_indices in all_faces:
        v1 = all_vertices[face_indices[0]]
        v2 = all_vertices[face_indices[1]]
        v3 = all_vertices[face_indices[2]]
        facets.append({
            'type': 'triangular',
            'vertex_type': 'ABSOLUTE', # Add this new key
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