from flask import Flask, request, jsonify, render_template, Response
from flask_cors import CORS
# Correctly import from the 'src' package
from src.project_manager import ProjectManager
from src.geometry_types import convert_to_internal_units, get_unit_value # if needed directly

app = Flask(__name__)
CORS(app)

# Instantiate ProjectManager globally (or manage per session if needed)
project_manager = ProjectManager()

@app.route('/')
def index():
    return render_template('index.html')

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
            geometry_data_for_threejs = project_manager.get_threejs_description()
            return jsonify(geometry_data_for_threejs)
        except ValueError as e:
             print(f"Error during GDML processing: {e}")
             return jsonify({"error": str(e)}), 500
        except Exception as e:
            print(f"An unexpected error occurred: {e}")
            import traceback
            traceback.print_exc()
            return jsonify({"error": "An unexpected error occurred on the server."}), 500

@app.route('/update_object_transform', methods=['POST'])
def update_object_transform_route():
    data = request.get_json()
    object_id = data.get('id') # This is the unique ID (UUID) of the PVPlacement
    new_position = data.get('position') # {'x': ..., 'y': ..., 'z': ...}
    new_rotation = data.get('rotation') # {'x': ..., 'y': ..., 'z': ...}
    print(f"Updating with id {object_id}")

    if not object_id:
        return jsonify({"error": "Object ID missing"}), 400

    success, error_msg, updated_defines = project_manager.update_physical_volume_transform(object_id, new_position, new_rotation)

    if success:
        return jsonify({
            "success": True, 
            "message": f"Object {object_id} transform updated.",
            "updated_defines": updated_defines # Send back the updated define data
        })
    else:
        return jsonify({"success": False, "error": error_msg or f"Could not update object {object_id} transform."}), 404
    
@app.route('/get_project_state', methods=['GET'])
def get_project_state_route():
    state_dict = project_manager.get_full_project_state_dict()
    if state_dict:
        return jsonify(state_dict)
    return jsonify({"error": "No project loaded"}), 404

@app.route('/get_object_details', methods=['GET'])
def get_object_details_route():
    obj_type = request.args.get('type')
    obj_id = request.args.get('id') # For PVs, this is the UUID. For others, it's the name for now.
    if not obj_type or not obj_id:
        return jsonify({"error": "Type or ID missing"}), 400
    
    details = project_manager.get_object_details(obj_type, obj_id)
    if details:
        return jsonify(details)
    return jsonify({"error": f"{obj_type} '{obj_id}' not found"}), 404

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
        # Important: After backend state changes, frontend needs updated scene data
        new_scene_description = project_manager.get_threejs_description()
        return jsonify({"success": True, "message": "Property updated", "scene_update": new_scene_description})
    else:
        return jsonify({"success": False, "error": "Failed to update property"}), 500

@app.route('/add_object', methods=['POST'])
def add_object_route():
    data = request.get_json()
    obj_type = data.get('object_type') # e.g., "solid_box", "define_position", "material"
    name_suggestion = data.get('name')
    params = data.get('params', {}) # Specific parameters for the object type

    if not obj_type or not name_suggestion:
        return jsonify({"error": "Object type or name missing"}), 400

    new_obj_data = None
    error = None

    if obj_type == "define_position":
        # Frontend should send params like {'x':0, 'y':0, 'z':0, 'unit':'mm'}
        unit = params.get('unit', 'mm') # Default unit
        val_dict = {'x': params.get('x',0), 'y': params.get('y',0), 'z': params.get('z',0)}
        new_obj_data, error = project_manager.add_define(name_suggestion, "position", val_dict, unit, "length")
    elif obj_type == "material":
        # Frontend sends params like {'density': 1.0, 'state': 'solid'}
        new_obj_data, error = project_manager.add_material(name_suggestion, params)
    elif obj_type.startswith("solid_"):
        solid_actual_type = obj_type.split('_', 1)[1] # "box", "tube"
        # Frontend sends params like {'x':10, 'y':10, 'z':10} (already in internal units or with explicit units)
        # For simplicity, assume frontend sends params already converted to internal units (mm, rad)
        # A more robust way is for frontend to send value+unit, backend converts.
        # For now, project_manager.add_solid expects params in internal units.
        internal_params = {}
        default_lunit_val = get_unit_value('mm') # default internal unit
        default_aunit_val = get_unit_value('rad')

        if solid_actual_type == "box":
            internal_params = {
                'x': float(params.get('x', 100)), # Assume mm if unit not specified by UI
                'y': float(params.get('y', 100)),
                'z': float(params.get('z', 100)),
            }
        elif solid_actual_type == "tube":
             internal_params = {
                'rmin': float(params.get('rmin', 0)),
                'rmax': float(params.get('rmax', 50)),
                'dz': float(params.get('dz', 100)) / 2.0, # Store half-length
                'startphi': float(params.get('startphi', 0)), # Assume rad
                'deltaphi': float(params.get('deltaphi', 2*math.pi)), # Assume rad
            }
        # Add more solid types based on how their parameters are defined in geometry_types.Solid
        
        if internal_params:
            new_obj_data, error = project_manager.add_solid(name_suggestion, solid_actual_type, internal_params)
        else:
            error = f"Parameters for solid type {solid_actual_type} not handled."
    
    # TODO: Add cases for logical_volume, physical_volume which require selecting existing refs

    if new_obj_data:
        return jsonify({
            "success": True, 
            "message": f"{obj_type} '{new_obj_data.get('name')}' added.",
            "new_object": new_obj_data,
            "project_state": project_manager.get_full_project_state_dict(), # For hierarchy refresh
            "scene_update": project_manager.get_threejs_description() # If PV was added directly
        })
    else:
        return jsonify({"success": False, "error": error or "Failed to add object"}), 500


# Modify /delete_object to return full project state for hierarchy refresh
@app.route('/delete_object', methods=['POST'])
def delete_object_route():
    data = request.get_json()
    obj_type = data.get('object_type')
    obj_id = data.get('object_id') # This is name for Define/Mat/Solid/LV, UUID for PV
    
    deleted, error_msg, scene_update = project_manager.delete_object(obj_type, obj_id)
    if deleted:
        return jsonify({
            "success": True, 
            "message": "Object deleted", 
            "scene_update": scene_update, # Can be None if only non-visual item deleted
            "project_state": project_manager.get_full_project_state_dict() # For hierarchy
        })
    else:
        return jsonify({"success": False, "error": error_msg or "Failed to delete object"}), 500

@app.route('/save_project_json', methods=['GET'])
def save_project_json_route():
    try:
        project_json_string = project_manager.save_project_to_json_string()
        return Response(
            project_json_string,
            mimetype="application/json",
            headers={"Content-Disposition": "attachment;filename=project.json"}
        )
    except Exception as e:
        print(f"Error saving project: {e}")
        return jsonify({"error": "Failed to save project data"}), 500

@app.route('/load_project_json', methods=['POST'])
def load_project_json_route():
    if 'projectFile' not in request.files:
        return jsonify({"error": "No project file part"}), 400
    file = request.files['projectFile']
    if file.filename == '':
        return jsonify({"error": "No selected project file"}), 400
    if file:
        try:
            project_json_string = file.read().decode('utf-8')
            project_manager.load_project_from_json_string(project_json_string)
            # After loading, send back the new scene description for Three.js
            geometry_data_for_threejs = project_manager.get_threejs_description()
            return jsonify(geometry_data_for_threejs)
        except json.JSONDecodeError:
            return jsonify({"error": "Invalid JSON file format"}), 400
        except Exception as e:
            print(f"Error loading project: {e}")
            import traceback
            traceback.print_exc()
            return jsonify({"error": f"Failed to load project data: {str(e)}"}), 500

@app.route('/export_gdml', methods=['GET'])
def export_gdml_route():
    try:
        gdml_string = project_manager.export_to_gdml_string()
        return Response(
            gdml_string,
            mimetype="application/xml", # or text/xml
            headers={"Content-Disposition": "attachment;filename=exported_geometry.gdml"}
        )
    except Exception as e:
        print(f"Error exporting GDML: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": "Failed to export GDML data"}), 500

# Add routes for undo/redo later

if __name__ == '__main__':
    app.run(debug=True, port=5003)