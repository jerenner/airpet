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

from .geometry_types import (
    GeometryState, Define, Solid, LogicalVolume, Material, PhysicalVolumePlacement, Assembly
)
from .gdml_writer import GDMLWriter # To borrow its matrix decomposition logic

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

def parse_step_file(file_path):
    """
    Parses a STEP file with assembly structure and converts its geometry
    into a GeometryState object.
    """
    doc = TDocStd_Document("pythonocc-doc")
    reader = STEPCAFControl_Reader()
    reader.ReadFile(file_path)
    reader.Transfer(doc)

    shape_tool = XCAFDoc_DocumentTool.ShapeTool(doc.Main())
    
    imported_state = GeometryState()
    
    default_mat = Material(name="G4_STAINLESS-STEEL", density=8.0, state="solid", Z=26, A=55.845)
    imported_state.add_material(default_mat)

    assembly_name = os.path.splitext(os.path.basename(file_path))[0].replace(" ", "_")
    main_assembly = Assembly(name=assembly_name)
    imported_state.add_assembly(main_assembly)

    root_labels = TDF_LabelSequence()
    shape_tool.GetFreeShapes(root_labels)

    for i in range(1, root_labels.Length() + 1):
        process_label(root_labels.Value(i), shape_tool, imported_state, main_assembly, TopLoc_Location())

    return imported_state

def process_label(label, shape_tool, state, assembly, parent_loc: TopLoc_Location):
    """
    Recursively process labels in the STEP file's document tree.
    This version correctly handles assembly, reference, and simple shape labels.
    """
    
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
                 # We pass the assembly's *current* location as the parent for the children
                process_label(ref_label, shape_tool, state, assembly, current_loc)

    # Case 2: The label is a simple shape (a leaf node in the assembly tree).
    elif shape_tool.IsSimpleShape(label):
        shape = shape_tool.GetShape(label)
        # We only care about solids for our purpose.
        if shape.ShapeType() == TopAbs_SOLID:
            #print(f"Processing solid of shape {shape} for assembly {assembly.name}")
            process_solid(shape, current_loc, state, assembly)


def process_solid(solid_shape, location: TopLoc_Location, state, assembly):
    """Tessellates a single solid and adds it to the state and assembly."""
    solid_index = len(state.solids)
    
    mesh = BRepMesh_IncrementalMesh(solid_shape, 0.1, True) # Set angular deflection to True
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

    solid_base_name = f"CAD_Solid_{solid_index}"
    
    vertex_defines = {}
    for i, v in enumerate(all_vertices):
        define_name = f"{solid_base_name}_v{i}"
        vertex_define = Define(define_name, 'position', {'x': v[0], 'y': v[1], 'z': v[2]})
        state.add_define(vertex_define)
        vertex_defines[i] = define_name

    facets = []
    for face_indices in all_faces:
        facets.append({
            'type': 'triangular',
            'vertex_refs': [
                vertex_defines[face_indices[0]],
                vertex_defines[face_indices[1]],
                vertex_defines[face_indices[2]]
            ]
        })
    
    tessellated_solid = Solid(solid_base_name, 'tessellated', {'facets': facets})
    state.add_solid(tessellated_solid)
    
    lv_name = f"{solid_base_name}_LV"
    lv = LogicalVolume(lv_name, tessellated_solid.name, "G4_STAINLESS-STEEL")
    state.add_logical_volume(lv)
    
    # --- ADD PLACEMENT TO ASSEMBLY ---
    # This is the key change. We use the location passed down from the traversal.
    trsf = location.Transformation()
    transform_dict = _trsf_to_dict(trsf)
    
    pv = PhysicalVolumePlacement(
        name=f"{lv_name}_pv",
        volume_ref=lv_name,
        position_val_or_ref=transform_dict['position'],
        rotation_val_or_ref=transform_dict['rotation']
    )
    assembly.add_placement(pv)