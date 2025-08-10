# FILE: gdml-studio/app.py

import json
import math
import os
import requests
import traceback
from flask import Flask, request, jsonify, render_template, Response
from flask_cors import CORS
import asteval

from dotenv import load_dotenv, set_key, find_dotenv
from google import genai  # Correct top-level import
from google.genai import types # Often useful for advanced features
from google.genai import client # For type hinting

from src.expression_evaluator import ExpressionEvaluator 
from src.project_manager import ProjectManager
from src.geometry_types import get_unit_value
from src.geometry_types import Material, Solid, LogicalVolume
from src.geometry_types import GeometryState

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)
CORS(app)

ai_model = "gemma3:12b"
ai_timeout = 3000 # in seconds
expression_evaluator = ExpressionEvaluator()
project_manager = ProjectManager(expression_evaluator)

# Configure Gemini client
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
gemini_client: client.Client | None = None

def configure_gemini_client():
    """Initializes or re-initializes the Gemini client with the current API key."""
    global GEMINI_API_KEY, gemini_client
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    if GEMINI_API_KEY and GEMINI_API_KEY != "YOUR_API_KEY_HERE":
        try:
            gemini_client = genai.Client(api_key=GEMINI_API_KEY)
            print("Google Gemini client configured successfully.")
            return True
        except Exception as e:
            print(f"Warning: Failed to configure Google Gemini client: {e}")
            gemini_client = None
            return False
    else:
        print("Warning: GEMINI_API_KEY not found or not set. Gemini models will be unavailable.")
        gemini_client = None
        return False

# Initial configuration on startup
configure_gemini_client()

# --- Helper Functions ---

# Helper to load the AI system prompt
def load_system_prompt():
    """Loads the AI system prompt from an external file."""
    # Construct a path relative to this file's location
    prompt_path = os.path.join(os.path.dirname(__file__), 'prompts', 'ai_system_prompt.md')
    try:
        with open(prompt_path, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        print(f"Error: AI prompt file not found at {prompt_path}")
        return "You are a helpful assistant." # Fallback prompt

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
    project_manager = ProjectManager(expression_evaluator) 

    ## Create a G4_Galactic material
    world_mat = Material(
        name="G4_Galactic", 
        Z_expr="1", 
        A_expr="1.01", 
        density_expr="1.0e-25", 
        state="gas"
    )
    project_manager.current_geometry_state.add_material(world_mat)
    
    # Create a default solid for the world (e.g., a 10m box)
    # The parameters are now string expressions.
    world_solid_params = {'x': '10000', 'y': '10000', 'z': '10000'}
    world_solid = Solid(name="world_solid", solid_type="box", raw_parameters=world_solid_params)
    project_manager.current_geometry_state.add_solid(world_solid)

    # Create the logical volume for the world
    world_lv = LogicalVolume(name="World", solid_ref="world_solid", material_ref="G4_Galactic")
    project_manager.current_geometry_state.add_logical_volume(world_lv)

    # Set this logical volume as the world volume
    project_manager.current_geometry_state.world_volume_ref = "World"

    # Recalculate to populate evaluated fields
    project_manager.recalculate_geometry_state()

# Function to construct full AI prompt
def construct_full_ai_prompt(user_prompt):

    system_prompt = load_system_prompt()
    current_geometry_json = project_manager.save_project_to_json_string()

    full_prompt = (f"{system_prompt}\n\n"
                    f"## Current Geometry State\n\n"
                    f"```json\n{current_geometry_json}\n```\n\n"
                    f"## User Request\n\n"
                    f'"{user_prompt}"\n\n'
                    f"## Your JSON Response:\n")

    return full_prompt

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

@app.route('/import_gdml_part', methods=['POST'])
def import_gdml_part_route():
    if 'partFile' not in request.files:
        return jsonify({"error": "No file part"}), 400
    file = request.files['partFile']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400
    
    try:
        gdml_content_str = file.read().decode('utf-8')
        # Parse into a temporary state object
        temp_state = project_manager.gdml_parser.parse_gdml_string(gdml_content_str)
        # Call the new merge method
        success, error_msg = project_manager.merge_from_state(temp_state)
        if success:
            return create_success_response("GDML part(s) imported successfully.")
        else:
            return jsonify({"success": False, "error": error_msg or "Failed to merge GDML part."}), 500
    except Exception as e:
        print(f"An unexpected error occurred during GDML part import: {e}")
        traceback.print_exc()
        return jsonify({"error": "An unexpected error occurred on the server while importing GDML."}), 500


@app.route('/import_json_part', methods=['POST'])
def import_json_part_route():
    if 'partFile' not in request.files:
        return jsonify({"error": "No file part"}), 400
    file = request.files['partFile']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400

    try:
        json_string = file.read().decode('utf-8')
        data = json.loads(json_string)
        # Create a temporary GeometryState object from the JSON data
        temp_state = GeometryState.from_dict(data)
        # Call the new merge method
        success, error_msg = project_manager.merge_from_state(temp_state)
        if success:
            return create_success_response("JSON part(s) imported successfully.")
        else:
            return jsonify({"success": False, "error": error_msg or "Failed to merge JSON part."}), 500
    except json.JSONDecodeError:
        return jsonify({"error": "Invalid JSON file format"}), 400
    except Exception as e:
        print(f"An unexpected error occurred during JSON part import: {e}")
        traceback.print_exc()
        return jsonify({"error": f"An unexpected error occurred on the server while importing JSON: {str(e)}"}), 500

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

@app.route('/add_element', methods=['POST'])
def add_element_route():
    data = request.get_json()
    name_suggestion = data.get('name')
    params = {
        'formula': data.get('formula'),
        'Z': data.get('Z'),
        'A_expr': data.get('A_expr'),
        'components': data.get('components', [])
    }
    
    if not name_suggestion:
        return jsonify({"success": False, "error": "Missing name for element."}), 400
    
    new_obj, error_msg = project_manager.add_element(name_suggestion, params)
    
    if new_obj:
        return create_success_response("Element created.")
    else:
        return jsonify({"success": False, "error": error_msg}), 500

@app.route('/update_element', methods=['POST'])
def update_element_route():
    data = request.get_json()
    element_name = data.get('id')
    new_params = {
        'formula': data.get('formula'),
        'Z': data.get('Z'),
        'A_expr': data.get('A_expr'),
        'components': data.get('components', [])
    }

    if not element_name:
        return jsonify({"success": False, "error": "Missing ID for element update."}), 400

    success, error_msg = project_manager.update_element(element_name, new_params)
    
    if success:
        return create_success_response(f"Element '{element_name}' updated.")
    else:
        return jsonify({"success": False, "error": error_msg}), 500

@app.route('/add_isotope', methods=['POST'])
def add_isotope_route():
    data = request.get_json(); name = data.get('name'); params = data
    if not name: return jsonify({"success": False, "error": "Missing name for isotope."}), 400
    new_obj, err = project_manager.add_isotope(name, params)
    if new_obj: return create_success_response("Isotope created.")
    return jsonify({"success": False, "error": err}), 500

@app.route('/update_isotope', methods=['POST'])
def update_isotope_route():
    data = request.get_json(); name = data.get('id'); params = data
    if not name: return jsonify({"success": False, "error": "Missing ID for isotope update."}), 400
    ok, err = project_manager.update_isotope(name, params)
    if ok: return create_success_response(f"Isotope '{name}' updated.")
    return jsonify({"success": False, "error": err}), 500

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
    print(solid_params)

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

@app.route('/update_solid', methods=['POST'])
def update_solid_route():
    data = request.get_json()
    solid_id = data.get('id')
    new_raw_params = data.get('params')
    
    if not solid_id or new_raw_params is None:
        return jsonify({"success": False, "error": "Missing solid ID or new parameters."}), 400

    success, error_msg = project_manager.update_solid(solid_id, new_raw_params)

    if success:
        return create_success_response(f"Solid '{solid_id}' updated successfully.")
    else:
        return jsonify({"success": False, "error": error_msg or "Failed to update solid."}), 500

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
    vis_attributes = data.get('vis_attributes')
    content_type = data.get('content_type', 'physvol')
    content = data.get('content', [])
    
    new_lv ,error_msg = project_manager.add_logical_volume(name, solid_ref, material_ref, vis_attributes, content_type, content)
    
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
    vis_attributes = data.get('vis_attributes')
    content_type = data.get('content_type')
    content = data.get('content')

    success ,error_msg = project_manager.update_logical_volume(lv_name, solid_ref, material_ref, vis_attributes, content_type, content)

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
    scale = data.get('scale')
    
    new_pv, error_msg = project_manager.add_physical_volume(parent_lv_name, name, volume_ref, position, rotation, scale)
    
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
    scale = data.get('scale')

    success, error_msg = project_manager.update_physical_volume(pv_id, name, position, rotation, scale)

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

@app.route('/ai_health_check', methods=['GET'])
def ai_health_check_route():
    response_data = {"success": True, "models": {"ollama": [], "gemini": []}}
    
    # 1. Check for Ollama models
    try:
        ollama_response = requests.get('http://localhost:11434/api/tags', timeout=3)
        if ollama_response.ok:
            ollama_data = ollama_response.json()
            response_data["models"]["ollama"] = [m['name'] for m in ollama_data.get('models', [])]
    except requests.exceptions.RequestException:
        print("Ollama service is unreachable.")
        # We don't fail the whole request, just show no Ollama models

    # 2. Check for Gemini models if the client was initialized
    if gemini_client:
        try:
            gemini_models = []
            # Use the initialized client to list models
            for model in gemini_client.models.list():
                if 'generateContent' in model.supported_actions:
                    # Filter for 2.5 Flash and 2.5 Pro only
                    if(model.name == "models/gemini-2.5-flash" or model.name == "models/gemini-2.5-pro"):
                        gemini_models.append(model.name)
            response_data["models"]["gemini"] = gemini_models
        except Exception as e:
            print(f"Error fetching Gemini models: {e}")
            response_data["error_gemini"] = str(e)

    return jsonify(response_data)

@app.route('/ai_process_prompt', methods=['POST'])
def ai_process_prompt_route():
    data = request.get_json()
    user_prompt = data.get('prompt')
    model_name = data.get('model')

    # Ensure we have a prompt and model name
    if not all([user_prompt, model_name]):
        return jsonify({"success": False, "error": "Prompt or model name missing."}), 400

    try:
        # Step 1: Construct the full prompt
        full_prompt = construct_full_ai_prompt(user_prompt)

        ai_json_string = ""

        # --- Routing logic ---
        if model_name.startswith("models/"): # Gemini models
            if not gemini_client:
                return jsonify({"success": False, "error": "Gemini client is not configured on the server."}), 500
            
            print(f"Sending prompt to Gemini model: {model_name}")
            # Use the global client instance to generate content
            gemini_response = gemini_client.models.generate_content(
                model=model_name,
                contents=full_prompt,
                # To ensure JSON output, we can add a config
                config=types.GenerateContentConfig(
                    response_mime_type="application/json"
                )
            )
            ai_json_string = gemini_response.text

        else: # Assume it's an Ollama model
            print(f"Sending prompt to Ollama model: {model_name}")
            ollama_response = requests.post(
                'http://localhost:11434/api/generate',
                json={ "model": model_name, "prompt": full_prompt, "stream": False, "format": "json"},
                timeout=ai_timeout
            )
            ollama_response.raise_for_status()
            ai_json_string = ollama_response.json().get('response')
        
        # Step 3: Parse and process the response using a new ProjectManager method
        ai_data = json.loads(ai_json_string)
        success, error_msg = project_manager.process_ai_response(ai_data)
        
        if success:
            return create_success_response("AI command processed successfully.")
        else:
            return jsonify({"success": False, "error": error_msg or "Failed to process AI response."}), 500

    except requests.exceptions.RequestException as e:
        return jsonify({"success": False, "error": f"Could not connect to AI service: {e}"}), 500
    except json.JSONDecodeError:
        return jsonify({"success": False, "error": "AI returned invalid JSON."}), 500
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": f"An unexpected error occurred: {e}"}), 500

@app.route('/ai_get_full_prompt', methods=['POST'])
def ai_get_full_prompt_route():
    data = request.get_json()
    user_prompt = data.get('prompt')
    if not user_prompt:
        return jsonify({"success": False, "error": "No prompt provided."}), 400

    try:
        # Construct the prompt
        full_prompt = construct_full_ai_prompt(user_prompt)

        # Return the constructed prompt as plain text
        return Response(full_prompt, mimetype="text/markdown")

    except Exception as e:
        traceback.print_exc()
        return jsonify({"success": False, "error": f"An unexpected error occurred: {e}"}), 500

@app.route('/import_ai_json', methods=['POST'])
def import_ai_json_route():
    if 'aiFile' not in request.files:
        return jsonify({"success": False, "error": "No AI file part"}), 400
    file = request.files['aiFile']
    if file.filename == '':
        return jsonify({"success": False, "error": "No selected file"}), 400

    print("Importing AI Response...");
    try:
        json_string = file.read().decode('utf-8')
        ai_data = json.loads(json_string)

        # Use the existing AI processing logic!
        success, error_msg = project_manager.process_ai_response(ai_data)
        
        if success:
            return create_success_response("AI-generated JSON imported successfully.")
        else:
            return jsonify({"success": False, "error": error_msg or "Failed to process AI JSON file."}), 500

    except json.JSONDecodeError:
        return jsonify({"success": False, "error": "Invalid JSON file format"}), 400
    except Exception as e:
        traceback.print_exc()
        return jsonify({"success": False, "error": f"An unexpected error occurred while importing: {str(e)}"}), 500

# --- Route to get the current API key ---
@app.route('/api/get_gemini_key', methods=['GET'])
def get_gemini_key():
    # Reread the key from the .env file in case it was changed manually
    api_key = os.getenv("GEMINI_API_KEY", "")
    if api_key == "YOUR_API_KEY_HERE":
        api_key = "" # Don't show the placeholder text
    return jsonify({"api_key": api_key})

# --- Route to set a new API key ---
@app.route('/api/set_gemini_key', methods=['POST'])
def set_gemini_key():
    data = request.get_json()
    new_key = data.get('api_key', '')

    try:
        # Find the .env file path
        dotenv_path = find_dotenv()
        if not dotenv_path:
            # If .env doesn't exist, create it in the current directory
            dotenv_path = os.path.join(os.getcwd(), '.env')
            with open(dotenv_path, 'w') as f:
                pass # Create an empty file
        
        # Write the key to the .env file
        set_key(dotenv_path, "GEMINI_API_KEY", new_key)
        
        # Reload environment variables and re-initialize the client
        load_dotenv(override=True)
        success = configure_gemini_client()

        if success:
            return jsonify({"success": True, "message": "API Key updated successfully."})
        else:
            return jsonify({"success": False, "error": "API Key was saved, but failed to configure the client. Key might be invalid."})

    except Exception as e:
        traceback.print_exc()
        return jsonify({"success": False, "error": f"Failed to save API key: {e}"}), 500

@app.route('/import_step', methods=['POST'])
def import_step_route():
    if 'stepFile' not in request.files:
        return jsonify({"error": "No STEP file part"}), 400
    file = request.files['stepFile']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400

    try:
        # Pass the file stream directly to the project manager
        success, error_msg = project_manager.import_step_file(file)
        if success:
            return create_success_response("STEP file imported successfully.")
        else:
            return jsonify({"success": False, "error": error_msg or "Failed to process STEP file."}), 500
    except Exception as e:
        print(f"An unexpected error occurred during STEP import: {e}")
        traceback.print_exc()
        return jsonify({"error": "An unexpected error occurred on the server while importing the STEP file."}), 500

@app.route('/add_assembly', methods=['POST'])
def add_assembly_route():
    data = request.get_json()
    name = data.get('name')
    placements = data.get('placements', [])
    new_asm, error_msg = project_manager.add_assembly(name, placements)
    if new_asm:
        return create_success_response("Assembly created.")
    else:
        return jsonify({"success": False, "error": error_msg}), 500

@app.route('/update_assembly', methods=['POST'])
def update_assembly_route():
    data = request.get_json()
    asm_name = data.get('id')
    placements = data.get('placements', [])
    success, error_msg = project_manager.update_assembly(asm_name, placements)
    if success:
        return create_success_response(f"Assembly '{asm_name}' updated.")
    else:
        return jsonify({"success": False, "error": error_msg}), 500

@app.route('/create_group', methods=['POST'])
def create_group_route():
    data = request.get_json()
    group_type = data.get('group_type')
    group_name = data.get('group_name')

    if not all([group_type, group_name]):
        return jsonify({"success": False, "error": "Missing group type or name."}), 400
    
    success, error_msg = project_manager.create_group(group_type, group_name)
    if success:
        return create_success_response(f"Group '{group_name}' created.")
    else:
        return jsonify({"success": False, "error": error_msg}), 500

@app.route('/rename_group', methods=['POST'])
def rename_group_route():
    data = request.get_json()
    group_type = data.get('group_type')
    old_name = data.get('old_name')
    new_name = data.get('new_name')

    if not all([group_type, old_name, new_name]):
        return jsonify({"success": False, "error": "Missing data for group rename."}), 400
        
    success, error_msg = project_manager.rename_group(group_type, old_name, new_name)
    if success:
        return create_success_response("Group renamed.")
    else:
        return jsonify({"success": False, "error": error_msg}), 500

@app.route('/delete_group', methods=['POST'])
def delete_group_route():
    data = request.get_json()
    group_type = data.get('group_type')
    group_name = data.get('group_name')
    
    if not all([group_type, group_name]):
        return jsonify({"success": False, "error": "Missing data for group deletion."}), 400

    success, error_msg = project_manager.delete_group(group_type, group_name)
    if success:
        return create_success_response("Group deleted.")
    else:
        return jsonify({"success": False, "error": error_msg}), 500

@app.route('/move_items_to_group', methods=['POST'])
def move_items_to_group_route():
    data = request.get_json()
    group_type = data.get('group_type')
    item_ids = data.get('item_ids')
    target_group_name = data.get('target_group_name') # Can be null to ungroup

    if not all([group_type, item_ids]):
        return jsonify({"success": False, "error": "Missing group type or item IDs."}), 400
        
    success, error_msg = project_manager.move_items_to_group(group_type, item_ids, target_group_name)
    if success:
        return create_success_response("Items moved successfully.")
    else:
        return jsonify({"success": False, "error": error_msg}), 500

@app.route('/api/evaluate_expression', methods=['POST'])
def evaluate_expression_route():
    data = request.get_json()
    expression = data.get('expression')
    if expression is None: # Check for None, as "" is a valid (empty) expression
        return jsonify({"success": False, "error": "Missing expression."}), 400

    # Evaluate the expression (the current project state has been set up in
    # the expression evaluator in ProjectManager's recalculate_geometry_state).
    success, result = expression_evaluator.evaluate(expression)

    if success:
        return jsonify({"success": True, "result": result})
    else:
        # The result is the error message string
        return jsonify({"success": False, "error": result}), 400

@app.route('/create_assembly_from_pvs', methods=['POST'])
def create_assembly_from_pvs_route():
    data = request.get_json()
    pv_ids = data.get('pv_ids')
    assembly_name = data.get('assembly_name')
    parent_lv_name = data.get('parent_lv_name')

    if not all([pv_ids, assembly_name, parent_lv_name]):
        return jsonify({"success": False, "error": "Missing data for assembly creation."}), 400

    new_pv, error_msg = project_manager.create_assembly_from_pvs(
        pv_ids, assembly_name, parent_lv_name
    )
    
    if error_msg:
        return jsonify({"success": False, "error": error_msg}), 500
    else:
        return create_success_response(f"Assembly '{assembly_name}' created successfully.")

@app.route('/move_pv_to_assembly', methods=['POST'])
def move_pv_to_assembly_route():
    data = request.get_json()
    pv_ids = data.get('pv_ids')
    target_assembly_name = data.get('target_assembly_name')
    if not all([pv_ids, target_assembly_name]):
        return jsonify({"success": False, "error": "Missing PV IDs or target assembly name."}), 400

    success, error_msg = project_manager.move_pv_to_assembly(pv_ids, target_assembly_name)
    if success:
        return create_success_response("PV moved to assembly.")
    else:
        return jsonify({"success": False, "error": error_msg}), 500

@app.route('/move_pv_to_lv', methods=['POST'])
def move_pv_to_lv_route():
    data = request.get_json()
    pv_ids = data.get('pv_ids')
    target_lv_name = data.get('target_lv_name')
    if not all([pv_ids, target_lv_name]):
        return jsonify({"success": False, "error": "Missing PV IDs or target LV name."}), 400

    success, error_msg = project_manager.move_pv_to_lv(pv_ids, target_lv_name)
    if success:
        return create_success_response("PV moved to logical volume.")
    else:
        return jsonify({"success": False, "error": error_msg}), 500

@app.route('/add_optical_surface', methods=['POST'])
def add_optical_surface_route():
    data = request.get_json()
    name_suggestion = data.get('name')
    params = {
        'model': data.get('model'),
        'finish': data.get('finish'),
        'surf_type': data.get('type'),
        'value': data.get('value'),
        'properties': data.get('properties', {})
    }
    
    if not name_suggestion:
        return jsonify({"success": False, "error": "Missing name for optical surface."}), 400
    
    new_obj, error_msg = project_manager.add_optical_surface(name_suggestion, params)
    
    if new_obj:
        return create_success_response("Optical Surface created.")
    else:
        return jsonify({"success": False, "error": error_msg}), 500

@app.route('/update_optical_surface', methods=['POST'])
def update_optical_surface_route():
    data = request.get_json()
    surface_name = data.get('id')
    new_params = {
        'model': data.get('model'),
        'finish': data.get('finish'),
        'surf_type': data.get('type'),
        'value': data.get('value'),
        'properties': data.get('properties', {})
    }

    if not surface_name:
        return jsonify({"success": False, "error": "Missing ID for optical surface update."}), 400

    success, error_msg = project_manager.update_optical_surface(surface_name, new_params)
    
    if success:
        return create_success_response(f"Optical Surface '{surface_name}' updated.")
    else:
        return jsonify({"success": False, "error": error_msg}), 500

@app.route('/add_skin_surface', methods=['POST'])
def add_skin_surface_route():
    data = request.get_json()
    name_suggestion = data.get('name')
    volume_ref = data.get('volume_ref')
    surface_ref = data.get('surfaceproperty_ref')
    
    if not all([name_suggestion, volume_ref, surface_ref]):
        return jsonify({"success": False, "error": "Missing name, volume reference, or surface reference."}), 400
    
    new_obj, error_msg = project_manager.add_skin_surface(name_suggestion, volume_ref, surface_ref)
    
    if new_obj:
        return create_success_response("Skin Surface created.")
    else:
        return jsonify({"success": False, "error": error_msg}), 500

@app.route('/update_skin_surface', methods=['POST'])
def update_skin_surface_route():
    data = request.get_json()
    surface_name = data.get('id')
    volume_ref = data.get('volume_ref')
    surface_ref = data.get('surfaceproperty_ref')

    if not all([surface_name, volume_ref, surface_ref]):
        return jsonify({"success": False, "error": "Missing name, volume reference, or surface reference for update."}), 400

    success, error_msg = project_manager.update_skin_surface(surface_name, volume_ref, surface_ref)
    
    if success:
        return create_success_response(f"Skin Surface '{surface_name}' updated.")
    else:
        return jsonify({"success": False, "error": error_msg}), 500

@app.route('/add_border_surface', methods=['POST'])
def add_border_surface_route():
    data = request.get_json()
    name_suggestion = data.get('name')
    pv1_ref = data.get('physvol1_ref')
    pv2_ref = data.get('physvol2_ref')
    surface_ref = data.get('surfaceproperty_ref')
    print(f"Surface ref is {surface_ref}")
    
    if not all([name_suggestion, pv1_ref, pv2_ref, surface_ref]):
        return jsonify({"success": False, "error": "Missing name or reference for border surface."}), 400
    
    new_obj, error_msg = project_manager.add_border_surface(name_suggestion, pv1_ref, pv2_ref, surface_ref)
    
    if new_obj:
        return create_success_response("Border Surface created.")
    else:
        return jsonify({"success": False, "error": error_msg}), 500

@app.route('/update_border_surface', methods=['POST'])
def update_border_surface_route():
    data = request.get_json()
    surface_name = data.get('id')
    pv1_ref = data.get('physvol1_ref')
    pv2_ref = data.get('physvol2_ref')
    surface_ref = data.get('surfaceproperty_ref')

    if not all([surface_name, pv1_ref, pv2_ref, surface_ref]):
        return jsonify({"success": False, "error": "Missing data for border surface update."}), 400

    success, error_msg = project_manager.update_border_surface(surface_name, pv1_ref, pv2_ref, surface_ref)
    
    if success:
        return create_success_response(f"Border Surface '{surface_name}' updated.")
    else:
        return jsonify({"success": False, "error": error_msg}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5003)