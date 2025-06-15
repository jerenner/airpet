# FILE: gdml-studio/app.py

import json
import math
from flask import Flask, request, jsonify, render_template, Response
from flask_cors import CORS

from src.project_manager import ProjectManager
from src.geometry_types import get_unit_value
from src.geometry_types import Material, Solid, LogicalVolume

app = Flask(__name__)
CORS(app)

project_manager = ProjectManager()

# --- Helper Functions ---

# Function for Consistent API Responses
def create_success_response(message="Success"):
    """
    Helper to create a standard success response object. It packages the
    entire current project state for the frontend to re-render.
    """
    state = project_manager.get_full_project_state_dict()
    scene = project_manager.get_threejs_description()
    return jsonify({
        "success": True,
        "message": message,
        "project_state": state,
        "scene_update": scene
    })

# Function to define a new project
def create_empty_project():

    global project_manager
    # Re-initialize the project manager to clear everything
    project_manager = ProjectManager() 

    # Create a default material for the world (e.g., vacuum)
    world_mat = Material(name="G4_Galactic", Z=1, A=1.01, density=1.e-25, state="gas")
    project_manager.current_geometry_state.add_material(world_mat)
    
    # Create a default solid for the world (e.g., a 10m box)
    world_solid_params = {'x': 10000, 'y': 10000, 'z': 10000} # in mm
    world_solid = Solid(name="world_solid", solid_type="box", parameters=world_solid_params)
    project_manager.current_geometry_state.add_solid(world_solid)

    # Create the logical volume for the world
    world_lv = LogicalVolume(name="World", solid_ref="world_solid", material_ref="G4_Galactic")
    project_manager.current_geometry_state.add_logical_volume(world_lv)

    # Set this logical volume as the world volume
    project_manager.current_geometry_state.world_volume_ref = "World"

# --- Main Application Routes ---

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/new_project', methods=['POST']) # Use POST for an action that changes state
def new_project_route():
    """Clears the current project and creates a new one with a default world."""

    # Call the helper function for creating an empty project.
    create_empty_project()

    return create_success_response("New project created.")

@app.route('/process_gdml', methods=['POST'])
def process_gdml_route():
    if 'gdmlFile' not in request.files:
        return jsonify({"error": "No file part"}), 400
    file = request.files['gdmlFile']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400
    if file:
        gdml_content_str = file.read().decode('utf-8')
        try:
            project_manager.load_gdml_from_string(gdml_content_str)
            return create_success_response("GDML file processed successfully.")
        except Exception as e:
            import traceback
            traceback.print_exc()
            return jsonify({"error": str(e)}), 500

@app.route('/load_project_json', methods=['POST'])
def load_project_json_route():
    if 'projectFile' not in request.files:
        return jsonify({"error": "No project file part"}), 400
    file = request.files['projectFile']
    if file:
        try:
            project_json_string = file.read().decode('utf-8')
            project_manager.load_project_from_json_string(project_json_string)
            return create_success_response("Project loaded successfully.")
        except json.JSONDecodeError:
            return jsonify({"error": "Invalid JSON file format"}), 400
        except Exception as e:
            import traceback
            traceback.print_exc()
            return jsonify({"error": f"Failed to load project data: {str(e)}"}), 500

@app.route('/update_object_transform', methods=['POST'])
def update_object_transform_route():
    data = request.get_json()
    object_id = data.get('id')
    new_position = data.get('position')
    new_rotation = data.get('rotation')

    if not object_id:
        return jsonify({"error": "Object ID missing"}), 400

    success, error_msg = project_manager.update_physical_volume_transform(object_id, new_position, new_rotation)

    if success:
        return create_success_response(f"Object {object_id} transform updated.")
    else:
        return jsonify({"success": False, "error": error_msg or "Could not update transform."}), 404
    
@app.route('/update_property', methods=['POST'])
def update_property_route():
    data = request.get_json()
    obj_type = data.get('object_type')
    obj_id = data.get('object_id')
    prop_path = data.get('property_path')
    new_value = data.get('new_value')

    if not all([obj_type, obj_id, prop_path]):
        return jsonify({"error": "Missing data for property update"}), 400

    success = project_manager.update_object_property(obj_type, obj_id, prop_path, new_value)
    if success:
        return create_success_response("Property updated.")
    else:
        return jsonify({"success": False, "error": "Failed to update property"}), 500

@app.route('/add_material', methods=['POST'])
def add_material_route():
    data = request.get_json()
    name_suggestion = data.get('name')
    params = data.get('params')

    if not name_suggestion or params is None:
        return jsonify({"success": False, "error": "Missing name or parameters for material."}), 400

    new_obj, error_msg = project_manager.add_material(name_suggestion, params)

    if new_obj:
        return create_success_response("Material created.")
    else:
        return jsonify({"success": False, "error": error_msg}), 500

@app.route('/update_material', methods=['POST'])
def update_material_route():
    data = request.get_json()
    mat_name = data.get('id')
    new_params = data.get('params')
    
    success, error_msg = project_manager.update_material(mat_name, new_params)
    if success:
        return create_success_response(f"Material '{mat_name}' updated.")
    else:
        return jsonify({"success": False, "error": error_msg}), 500

@app.route('/add_define', methods=['POST'])
def add_define_route():
    data = request.get_json()
    name = data.get('name')
    define_type = data.get('type')
    value = data.get('value')
    unit = data.get('unit')
    category = data.get('category')
    
    new_obj, error_msg = project_manager.add_define(name, define_type, value, unit, category)
    if new_obj:
        return create_success_response("Define created.")
    else:
        return jsonify({"success": False, "error": error_msg}), 500

@app.route('/update_define', methods=['POST'])
def update_define_route():
    data = request.get_json()
    define_name = data.get('id')
    value = data.get('value')
    unit = data.get('unit')
    category = data.get('category')

    success, error_msg = project_manager.update_define(define_name, value, unit, category)

    if success:
        return create_success_response(f"Define '{define_name}' updated.")
    else:
        return jsonify({"success": False, "error": error_msg}), 500

@app.route('/add_solid_and_place', methods=['POST'])
def add_solid_and_place_route():
    data = request.get_json()
    solid_params = data.get('solid_params') # {name, type, params}
    lv_params = data.get('lv_params')       # {name?, material_ref} or None
    pv_params = data.get('pv_params')       # {name?, parent_lv_name} or None

    if not solid_params:
        return jsonify({"success": False, "error": "Solid parameters are required."}), 400

    success, error_msg = project_manager.add_solid_and_place(solid_params, lv_params, pv_params)

    if success:
        return create_success_response("Object(s) created successfully.")
    else:
        return jsonify({"success": False, "error": error_msg}), 500

@app.route('/add_primitive_solid', methods=['POST'])
def add_primitive_solid_route():
    data = request.get_json()
    name_suggestion = data.get('name')
    solid_type = data.get('type')
    params = data.get('params')

    if not all([name_suggestion, solid_type, params]):
        return jsonify({"success": False, "error": "Missing data for primitive solid"}), 400
        
    new_obj, error_msg = project_manager.add_solid(name_suggestion, solid_type, params)
    
    if new_obj:
        return create_success_response("Primitive solid created.")
    else:
        return jsonify({"success": False, "error": error_msg}), 500

@app.route('/add_boolean_solid', methods=['POST'])
def add_boolean_solid_route():
    data = request.get_json()
    name_suggestion = data.get('name')
    recipe = data.get('recipe')
    
    success, error_msg = project_manager.add_boolean_solid(name_suggestion, recipe)

    if success:
        return create_success_response("Boolean solid created.")
    else:
        return jsonify({"success": False, "error": error_msg}), 500

@app.route('/update_boolean_solid', methods=['POST'])
def update_boolean_solid_route():
    data = request.get_json()
    solid_name = data.get('id') # The name of the solid to update
    recipe = data.get('recipe')
    
    success, error_msg = project_manager.update_boolean_solid(solid_name, recipe)

    if success:
        return create_success_response(f"Boolean solid '{solid_name}' updated.")
    else:
        return jsonify({"success": False, "error": error_msg}), 500

@app.route('/add_logical_volume', methods=['POST'])
def add_logical_volume_route():
    data = request.get_json()
    name = data.get('name')
    solid_ref = data.get('solid_ref')
    material_ref = data.get('material_ref')
    
    new_lv, error_msg = project_manager.add_logical_volume(name, solid_ref, material_ref)
    
    if new_lv:
        return create_success_response("Logical Volume created.")
    else:
        return jsonify({"success": False, "error": error_msg}), 500

@app.route('/update_logical_volume', methods=['POST'])
def update_logical_volume_route():
    data = request.get_json()
    lv_name = data.get('id')
    solid_ref = data.get('solid_ref')
    material_ref = data.get('material_ref')

    success, error_msg = project_manager.update_logical_volume(lv_name, solid_ref, material_ref)

    if success:
        return create_success_response(f"Logical Volume '{lv_name}' updated.")
    else:
        return jsonify({"success": False, "error": error_msg}), 500

@app.route('/add_physical_volume', methods=['POST'])
def add_physical_volume_route():
    data = request.get_json()
    parent_lv_name = data.get('parent_lv_name')
    name = data.get('name')
    volume_ref = data.get('volume_ref')
    position = data.get('position')
    rotation = data.get('rotation')
    
    new_pv, error_msg = project_manager.add_physical_volume(parent_lv_name, name, volume_ref, position, rotation)
    
    if new_pv:
        return create_success_response("Physical Volume placed.")
    else:
        return jsonify({"success": False, "error": error_msg}), 500

@app.route('/update_physical_volume', methods=['POST'])
def update_physical_volume_route():
    data = request.get_json()
    pv_id = data.get('id')
    name = data.get('name')
    position = data.get('position')
    rotation = data.get('rotation')

    success, error_msg = project_manager.update_physical_volume(pv_id, name, position, rotation)

    if success:
        return create_success_response(f"Physical Volume '{pv_id}' updated.")
    else:
        return jsonify({"success": False, "error": error_msg}), 500

@app.route('/delete_object', methods=['POST'])
def delete_object_route():
    data = request.get_json()
    obj_type = data.get('object_type')
    obj_id = data.get('object_id')
    
    deleted, error_msg = project_manager.delete_object(obj_type, obj_id)
    if deleted:
        return create_success_response("Object deleted.")
    else:
        return jsonify({"success": False, "error": error_msg or "Failed to delete object"}), 500

# --- Read-only and Export Routes (Do not need full state response) ---

@app.route('/get_project_state', methods=['GET'])
def get_project_state_route():
    """
    This route is for initial page load state restoration.
    If no project exists, it creates a new default one.
    """
    state = project_manager.get_full_project_state_dict()
    
    # Check if the project is empty (no world volume defined)
    if not state or not state.get('world_volume_ref'):
        print("No active project found, creating a new default world.")
        
        # Call the same logic as the /new_project route
        create_empty_project()
        
        # Now get the state and scene again from the newly created project
        state = project_manager.get_full_project_state_dict()
        scene = project_manager.get_threejs_description()
    else:
        # Project already exists, just get the scene
        scene = project_manager.get_threejs_description()

    # Always return a valid state
    return jsonify({
        "project_state": state,
        "scene_update": scene
    })

@app.route('/get_object_details', methods=['GET'])
def get_object_details_route():
    obj_type = request.args.get('type')
    obj_id = request.args.get('id')
    if not obj_type or not obj_id:
        return jsonify({"error": "Type or ID missing"}), 400
    details = project_manager.get_object_details(obj_type, obj_id)
    if details:
        return jsonify(details)
    return jsonify({"error": f"{obj_type} '{obj_id}' not found"}), 404

@app.route('/save_project_json', methods=['GET'])
def save_project_json_route():
    project_json_string = project_manager.save_project_to_json_string()
    return Response(
        project_json_string,
        mimetype="application/json",
        headers={"Content-Disposition": "attachment;filename=project.json"}
    )

@app.route('/export_gdml', methods=['GET'])
def export_gdml_route():
    gdml_string = project_manager.export_to_gdml_string()
    return Response(
        gdml_string,
        mimetype="application/xml",
        headers={"Content-Disposition": "attachment;filename=exported_geometry.gdml"}
    )

@app.route('/get_defines_by_type', methods=['GET'])
def get_defines_by_type_route():
    """Returns a list of define names for a given type (position, rotation, etc.)."""
    define_type = request.args.get('type')
    if not define_type:
        return jsonify({"error": "Define type parameter is missing"}), 400

    if not project_manager.current_geometry_state:
        return jsonify([]) # Return empty list if no project

    # Filter defines based on the requested type
    filtered_defines = {
        name: define.to_dict()
        for name, define in project_manager.current_geometry_state.defines.items()
        if define.type == define_type
    }
    
    return jsonify(filtered_defines)

if __name__ == '__main__':
    app.run(debug=True, port=5003)