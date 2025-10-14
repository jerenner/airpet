# FILE: gdml-studio/app.py

import ast
import glob
import json
import os
import re
import requests
import traceback
import ollama
import subprocess
import threading
import atexit
import uuid
import h5py
import numpy as np
import pandas as pd
import io

from datetime import datetime
from flask import Flask, request, jsonify, render_template, Response, send_from_directory
from flask_cors import CORS

from dotenv import load_dotenv, set_key, find_dotenv
from google import genai  # Correct top-level import
from google.genai import types # Often useful for advanced features
from google.genai import client # For type hinting

from src.expression_evaluator import ExpressionEvaluator 
from src.project_manager import ProjectManager
from src.geometry_types import get_unit_value
from src.geometry_types import Material, Solid, LogicalVolume
from src.geometry_types import GeometryState

from PIL import Image

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)
CORS(app)

# Expression evaluator object to be used in backend and project manager
expression_evaluator = ExpressionEvaluator()
project_manager = ProjectManager(expression_evaluator)

# Projects directory
PROJECTS_BASE_DIR = os.path.join(os.getcwd(), "projects")
os.makedirs(PROJECTS_BASE_DIR, exist_ok=True)
project_manager.projects_dir = PROJECTS_BASE_DIR # Give PM access

# ------------------------------------------------------------------------------
# AI setup
ai_model = "gemma3:12b"
ai_timeout = 3000 # in seconds
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
gemini_client: client.Client | None = None # Configure Gemini client

# Configure the Gemini client
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

# --------------------------------------------------------------------------
# Geant4 integration

# --- New Global Configuration ---
# Path to the Geant4 application directory and executable
# We assume the script is run from the `virtual-pet` root directory
GEANT4_APP_DIR = os.path.join(os.getcwd(), "geant4")
GEANT4_BUILD_DIR = os.path.join(GEANT4_APP_DIR, "build")
GEANT4_EXECUTABLE = os.path.join(GEANT4_BUILD_DIR, "airpet-sim")

# A dictionary to track running simulation processes
SIMULATION_PROCESSES = {}
SIMULATION_STATUS = {}
LATEST_COMPLETED_JOB_ID = None
SIMULATION_LOCK = threading.Lock()

# Track running LOR computation
LOR_PROCESSING_STATUS = {}
LOR_PROCESSING_LOCK = threading.Lock()

# Ensure we terminate any running simulations when the Flask app exits
def cleanup_processes():
    with SIMULATION_LOCK:
        for job_id, process in SIMULATION_PROCESSES.items():
            if process.poll() is None: # Check if the process is still running
                print(f"Terminating running simulation job {job_id}...")
                process.terminate()
                process.wait()

atexit.register(cleanup_processes)

@app.route('/api/set_active_source', methods=['POST'])
def set_active_source_route():
    data = request.get_json()
    source_id = data.get('source_id') # Can be the ID string or null
    
    success, error_msg = project_manager.set_active_source(source_id)
    
    if success:
        # We don't need to send the whole state back for this, a simple success is fine.
        # The frontend can manage the radio button state.
        return jsonify({"success": True, "message": "Active source updated."})
    else:
        return jsonify({"success": False, "error": error_msg}), 500

@app.route('/api/simulation/run', methods=['POST'])
def run_simulation():
    if not os.path.exists(GEANT4_EXECUTABLE):
        return jsonify({
            "success": False,
            "error": "Geant4 executable not found. Please compile the application in 'geant4_app/build'."
        }), 500

    sim_params = request.get_json()
    if not sim_params:
        return jsonify({"success": False, "error": "Missing simulation parameters."}), 400

    job_id = str(uuid.uuid4())

    try:
        version_id = project_manager.current_version_id
        # If the project has changed or no version is active, save a new one.
        if project_manager.is_changed or not version_id:
            version_id, _ = project_manager.save_project_version(f"AutoSave_for_Sim_{job_id[:8]}")

        version_dir = project_manager._get_version_dir(version_id)
        run_dir = os.path.join(version_dir, "sim_runs", job_id)
        os.makedirs(run_dir, exist_ok=True)

        # Generate macro and geometry inside the final run directory
        macro_path = project_manager.generate_macro_file(
            job_id, sim_params, GEANT4_BUILD_DIR, run_dir, version_dir
        )
        

        # This will be the function run in a separate thread
        def run_g4_process(job_id, command):
            with SIMULATION_LOCK:
                # The process will run in the 'geant4_app/build' directory
                process = subprocess.Popen(
                    command,
                    cwd=run_dir,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    bufsize=1 # Line-buffered
                )
                SIMULATION_PROCESSES[job_id] = process
                SIMULATION_STATUS[job_id] = {
                    "status": "Running",
                    "progress": 0,
                    "total_events": sim_params.get('events', 1),
                    "stdout": [],
                    "stderr": []
                }

            # Monitor stdout
            if process.stdout:
                for line in iter(process.stdout.readline, ''):
                    line = line.strip()
                    if line:
                        with SIMULATION_LOCK:
                           SIMULATION_STATUS[job_id]['stdout'].append(line)
                           # Example of parsing progress:
                           if ">>> Event" in line and "starts" in line:
                               try:
                                   event_num = int(line.split()[2])
                                   SIMULATION_STATUS[job_id]['progress'] = event_num + 1
                               except (ValueError, IndexError):
                                   pass
                process.stdout.close()

            # Monitor stderr
            if process.stderr:
                for line in iter(process.stderr.readline, ''):
                    line = line.strip()
                    if line:
                        with SIMULATION_LOCK:
                            SIMULATION_STATUS[job_id]['stderr'].append(line)
                process.stderr.close()

            process.wait()
            
            with SIMULATION_LOCK:
                if process.returncode == 0:
                    SIMULATION_STATUS[job_id]['status'] = 'Completed'
                    LATEST_COMPLETED_JOB_ID = job_id
                else:
                    SIMULATION_STATUS[job_id]['status'] = 'Error'
                SIMULATION_PROCESSES.pop(job_id, None)

        # Start the simulation in a background thread so the API call can return immediately
        # The executable path must be absolute or relative to the run_dir
        executable_path = os.path.relpath(GEANT4_EXECUTABLE, run_dir)
        command_to_run = [executable_path, "run.mac"]
        thread = threading.Thread(target=run_g4_process, args=(job_id, command_to_run))
        thread.start()

        return jsonify({
            "success": True,
            "message": "Simulation started.",
            "job_id": job_id,
            "version_id": version_id
        })

    except Exception as e:
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/simulation/status/<job_id>', methods=['GET'])
def get_simulation_status(job_id):

    # Get the line number from which the client wants updates
    last_line_seen = request.args.get('since', 0, type=int)

    with SIMULATION_LOCK:
        status = SIMULATION_STATUS.get(job_id)
        if not status:
            return jsonify({"success": False, "error": "Job ID not found."}), 404
        
        # Create a copy to send back to the user
        status_copy = {
            "status": status["status"],
            "progress": status["progress"],
            "total_events": status["total_events"]
        }

        # Get only the new lines from stdout and stderr
        all_lines = status['stdout'] + [f"stderr: {line}" for line in status['stderr']]
        new_lines = all_lines[last_line_seen:]
        
        status_copy['new_stdout'] = new_lines
        status_copy['total_lines'] = len(all_lines)

        return jsonify({"success": True, "status": status_copy})

@app.route('/api/simulation/metadata/<version_id>/<job_id>', methods=['GET'])
def get_simulation_metadata(version_id, job_id):
    """Fetches the metadata JSON file for a specific simulation run."""
    version_dir = project_manager._get_version_dir(version_id)
    run_dir = os.path.join(version_dir, "sim_runs", job_id)
    metadata_path = os.path.join(run_dir, "metadata.json")

    if not os.path.exists(metadata_path):
        return jsonify({"success": False, "error": "Simulation metadata not found."}), 404

    try:
        with open(metadata_path, 'r') as f:
            metadata = json.load(f)
        return jsonify({"success": True, "metadata": metadata})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/simulation/tracks/<version_id>/<job_id>/<event_spec>', methods=['GET'])
def get_simulation_tracks(version_id, job_id, event_spec):
    version_dir = project_manager._get_version_dir(version_id)
    run_dir = os.path.join(version_dir, "sim_runs", job_id)
    tracks_dir = os.path.join(run_dir, "tracks")

    if not os.path.isdir(tracks_dir):
        return jsonify({"success": False, "error": "Tracks directory not found for this run."}), 404

    # --- Handle multiple event files ---
    all_tracks_content = ""
    track_files = []
    
    if event_spec.lower() == 'all':
        track_files = sorted([f for f in os.listdir(tracks_dir) if f.endswith('_tracks.txt')])
    elif '-' in event_spec:
        try:
            start_str, end_str = event_spec.split('-', 1)
            start = int(start_str)
            end = int(end_str)
            
            if start > end: # A small sanity check to allow users to enter ranges backwards
                start, end = end, start

            for i in range(start, end + 1):
                track_files.append(f"event_{i:04d}_tracks.txt")
        except ValueError:
            return jsonify({"success": False, "error": "Invalid event range format. Use 'start-end' (e.g., '0-99')."}), 400
    else:
        try:
            event_id = int(event_spec)
            track_files = [f"event_{event_id:04d}_tracks.txt"]
        except ValueError:
            return jsonify({"success": False, "error": "Invalid event specification. Use a single number, a range 'start-end', or 'all'."}), 400

    for filename in track_files:
        filepath = os.path.join(tracks_dir, filename)
        if os.path.exists(filepath):
            with open(filepath, 'r') as f:
                all_tracks_content += f.read()
    
    if not all_tracks_content:
        return jsonify({"success": False, "error": "No track files found for the specified events."}), 404
        
    return Response(all_tracks_content, mimetype='text/plain')
    
@app.route('/api/simulation/stop/<job_id>', methods=['POST'])
def stop_simulation(job_id):
    with SIMULATION_LOCK:
        process = SIMULATION_PROCESSES.get(job_id)
        if process:
            if process.poll() is None: # Check if the process is still running
                print(f"Terminating simulation job {job_id}...")
                process.terminate()
                # We don't need to wait here, the monitoring thread will handle the status update
                return jsonify({"success": True, "message": f"Stop signal sent to job {job_id}."})
            else:
                return jsonify({"success": False, "error": "Job has already finished."}), 404
        else:
            return jsonify({"success": False, "error": "Job ID not found or already completed."}), 404
    
@app.route('/api/add_source', methods=['POST'])
def add_source_route():
    data = request.get_json()
    name_suggestion = data.get('name', 'gps_source')
    gps_commands = data.get('gps_commands', {})
    position = data.get('position', {'x': '0', 'y': '0', 'z': '0'})
    rotation = data.get('rotation', {'x': '0', 'y': '0', 'z': '0'})
    
    new_source, error_msg = project_manager.add_particle_source(
        name_suggestion, gps_commands, position, rotation)
    if new_source:
        return create_success_response("Particle source created.")
    else:
        return jsonify({"success": False, "error": error_msg}), 500

@app.route('/api/update_source_transform', methods=['POST'])
def update_source_transform_route():
    data = request.get_json()
    source_id = data.get('id')
    new_position = data.get('position')
    new_rotation = data.get('rotation')

    if not source_id:
        return jsonify({"error": "Source ID missing"}), 400
        
    success, error_msg = project_manager.update_source_transform(
        source_id, new_position, new_rotation
    )
    if success:
        return create_success_response(f"Source {source_id} transform updated.")
    else:
        return jsonify({"success": False, "error": error_msg or "Could not update source transform."}), 404

@app.route('/api/update_source', methods=['POST'])
def update_source_route():
    data = request.get_json()
    source_id = data.get('id')
    new_name = data.get('name')
    new_gps_commands = data.get('gps_commands')
    new_position = data.get('position')
    new_rotation = data.get('rotation')

    if not source_id:
        return jsonify({"success": False, "error": "Source ID is required."}), 400

    success, error_msg = project_manager.update_particle_source(
        source_id, new_name, new_gps_commands, new_position, new_rotation
    )

    if success:
        return create_success_response("Particle source updated successfully.")
    else:
        return jsonify({"success": False, "error": error_msg}), 500
    
@app.route('/api/simulation/process_lors/<version_id>/<job_id>', methods=['POST'])
def process_lors_route(version_id, job_id):
    """
    Processes Geant4 hits from HDF5, finds coincidences, and saves LORs.
    """
    data = request.get_json()
    coincidence_window_ns = data.get('coincidence_window_ns', 4.0)  # 4 ns window

    # This function will run in the background
    def process_lors_in_background(app, version_id, job_id, coincidence_window_ns):
        with app.app_context(): # Needed to work within Flask's context
            version_dir = project_manager._get_version_dir(version_id)
            run_dir = os.path.join(version_dir, "sim_runs", job_id)
            hdf5_path = os.path.join(run_dir, "output.hdf5")
            lors_output_path = os.path.join(run_dir, "lors.npz")

            try:
                if not os.path.exists(hdf5_path):
                    raise FileNotFoundError("Simulation output file not found.")

                with LOR_PROCESSING_LOCK:
                    LOR_PROCESSING_STATUS[job_id] = {"status": "Reading HDF5...", "progress": 0, "total": 0}

                data = {}
                with h5py.File(hdf5_path, 'r') as f:
                    group = f['/default_ntuples/Hits']
                    
                    # Load data from the non-metadata keys
                    for key in group.keys():
                        if key not in ['columns', 'entries', 'forms', 'names']:
                            data[key] = group[key]['pages'][:]

                # Use pandas for efficient sorting and searching
                hits_df = pd.DataFrame(data)

                # Geant4 n-tuple column names can be bytes, so decode if necessary
                hits_df.columns = [x.decode('utf-8') if isinstance(x, bytes) else x for x in hits_df.columns]

                # Use the correct column names from the HDF5 file (case-sensitive)
                hits_df.sort_values(by='Time', inplace=True)
                
                unique_event_ids = hits_df['EventID'].unique()
                total_events = len(unique_event_ids)

                with LOR_PROCESSING_LOCK:
                    LOR_PROCESSING_STATUS[job_id] = {"status": "Processing coincidences...", "progress": 0, "total": total_events}

                all_start_coords, all_end_coords, all_tof_bins = [], [], []
                
                # Process events and update progress
                for i, event_id in enumerate(unique_event_ids):
                    event_hits = hits_df[hits_df['EventID'] == event_id]
                    if len(event_hits) >= 2:
                        hit1 = event_hits.iloc[0]
                        hit2 = event_hits.iloc[1]
                        if abs(hit1['Time'] - hit2['Time']) < coincidence_window_ns:
                            pos1 = np.array([hit1['PosX'], hit1['PosY'], hit1['PosZ']])
                            pos2 = np.array([hit2['PosX'], hit2['PosY'], hit2['PosZ']])
                            if hit1['Time'] < hit2['Time']:
                                all_start_coords.append(pos1)
                                all_end_coords.append(pos2)
                            else:
                                all_start_coords.append(pos2)
                                all_end_coords.append(pos1)
                            all_tof_bins.append(0)

                    if (i + 1) % 1000 == 0: # Update status every 1000 events
                        with LOR_PROCESSING_LOCK:
                            LOR_PROCESSING_STATUS[job_id]["progress"] = i + 1
                
                if not all_start_coords:
                    raise ValueError("No valid coincidences found.")
                    
                np.savez_compressed(
                    lors_output_path,
                    start_coords=np.array(all_start_coords),
                    end_coords=np.array(all_end_coords),
                    tof_bins=np.array(all_tof_bins)
                )

                with LOR_PROCESSING_LOCK:
                    LOR_PROCESSING_STATUS[job_id] = {
                        "status": "Completed", 
                        "message": f"Processed {len(all_start_coords)} LORs from {total_events} events."
                    }

            except Exception as e:
                with LOR_PROCESSING_LOCK:
                    LOR_PROCESSING_STATUS[job_id] = {"status": "Error", "message": str(e)}
                traceback.print_exc()

    # Start the background task
    thread = threading.Thread(target=process_lors_in_background, args=(app, version_id, job_id, coincidence_window_ns))
    thread.start()

    return jsonify({"success": True, "message": "LOR processing started."}), 202
    
@app.route('/api/reconstruction/run/<version_id>/<job_id>', methods=['POST'])
def run_reconstruction_route(version_id, job_id):
    """
    Runs MLEM reconstruction using parallelproj on the pre-processed LORs.
    """
    data = request.get_json()
    iterations = data.get('iterations', 1)
    # Get image geometry parameters from the request
    img_shape = tuple(data.get('image_size', [128, 128, 128]))
    voxel_size = tuple(data.get('voxel_size', [2.0, 2.0, 2.0]))

    # This ensures the reconstruction grid is centered at (0,0,0) in world coordinates.
    # We calculate the position of the corner of the first voxel.
    image_origin = - (np.array(img_shape, dtype=np.float32) / 2 - 0.5) * np.array(voxel_size, dtype=np.float32)

    version_dir = project_manager._get_version_dir(version_id)
    run_dir = os.path.join(version_dir, "sim_runs", job_id)
    lors_path = os.path.join(run_dir, "lors.npz")
    recon_output_path = os.path.join(run_dir, "reconstruction.npy")

    if not os.path.exists(lors_path):
        return jsonify({"success": False, "error": "LOR file not found. Please process coincidences first."}), 404

    try:
        lor_data = np.load(lors_path)
        event_start_coords = lor_data['start_coords']
        event_end_coords = lor_data['end_coords']

        # Use parallelproj with numpy backend for this example
        import array_api_compat.numpy as xp
        import parallelproj
        dev = "cpu"

        # Convert LOR data to the array type used by parallelproj
        event_start_coords_xp = xp.asarray(event_start_coords, device=dev)
        event_end_coords_xp = xp.asarray(event_end_coords, device=dev)

        # Setup the listmode projector
        lm_proj = parallelproj.ListmodePETProjector(
            event_start_coords_xp,
            event_end_coords_xp,
            img_shape,
            voxel_size,
            img_origin=xp.asarray(image_origin, device=dev)
        )
        
        # We need an "adjoint_ones" image for sensitivity correction in MLEM.
        # This is the backprojection of a list of ones.
        #sensitivity_image = lm_proj.adjoint(xp.ones(lm_proj.out_shape, dtype=xp.float32, device=dev))
        sensitivity_image = xp.ones(img_shape, dtype=xp.float32, device=dev)

        # --- MLEM Reconstruction Loop ---
        x = xp.ones(img_shape, dtype=xp.float32, device=dev) # Initial image is all ones

        # --- Create a safe version of the sensitivity image for division ---
        sensitivity_image_safe_for_division = xp.where(sensitivity_image <= 0, 1.0, sensitivity_image)

        for i in range(iterations):
            print(f"Running MLEM iteration {i+1}/{iterations}...")
            ybar = lm_proj(x)
            # Add a small epsilon to avoid division by zero
            ybar = xp.where(ybar == 0, 1e-9, ybar)

            # Where sensitivity is 0, the image value should remain unchanged (multiplied by 0 update).
            back_projection = lm_proj.adjoint(1 / ybar)

            # Perform the division using the safe denominator
            update_term = (x / sensitivity_image_safe_for_division) * back_projection

            # Now, apply the update only where sensitivity is valid, otherwise set to 0.
            x = xp.where(sensitivity_image > 0, update_term, 0.0)

            print(f"Iteration {i+1} done.")

        # Save the final numpy array
        reconstructed_image_np = parallelproj.to_numpy_array(x)
        np.save(recon_output_path, reconstructed_image_np)

        return jsonify({
            "success": True, 
            "message": "Reconstruction complete.",
            "image_shape": reconstructed_image_np.shape
        })

    except Exception as e:
        traceback.print_exc()
        return jsonify({"success": False, "error": f"Reconstruction failed: {str(e)}"}), 500

@app.route('/api/reconstruction/slice/<version_id>/<job_id>/<axis>/<int:slice_num>')
def get_recon_slice_route(version_id, job_id, axis, slice_num):
    """
    Loads the reconstructed 3D numpy array and returns a single 2D slice as a PNG image.
    """
    version_dir = project_manager._get_version_dir(version_id)
    run_dir = os.path.join(version_dir, "sim_runs", job_id)
    recon_path = os.path.join(run_dir, "reconstruction.npy")

    if not os.path.exists(recon_path):
        return "Reconstruction file not found", 404

    try:
        recon_img = np.load(recon_path)

        # Select the slice
        if axis == 'x':
            slice_2d = recon_img[slice_num, :, :]
        elif axis == 'y':
            slice_2d = recon_img[:, slice_num, :]
        else: # 'z'
            slice_2d = recon_img[:, :, slice_num]
            
        # Normalize and convert to an 8-bit image for display
        slice_2d = np.rot90(slice_2d) # Rotate for better viewing orientation
        max_val = slice_2d.max()
        if max_val > 0:
            # Normalize to 0-255 range
            slice_2d = (slice_2d / max_val) * 255.0
        
        img_pil = Image.fromarray(slice_2d.astype(np.uint8), mode='L') # Grayscale

        # Save image to a memory buffer
        img_io = io.BytesIO()
        img_pil.save(img_io, 'PNG')
        img_io.seek(0)

        return Response(img_io.getvalue(), mimetype='image/png')

    except Exception as e:
        traceback.print_exc()
        return str(e), 500
    
@app.route('/api/lors/status/<job_id>', methods=['GET'])
def get_lor_processing_status(job_id):
    with LOR_PROCESSING_LOCK:
        status = LOR_PROCESSING_STATUS.get(job_id)
        if not status:
            return jsonify({"success": False, "error": "LOR processing job not found."}), 404
        return jsonify({"success": True, "status": status})

@app.route('/api/lors/check/<version_id>/<job_id>', methods=['GET'])
def check_lor_file_route(version_id, job_id):
    """Checks if a pre-processed LOR file exists for a given run."""
    version_dir = project_manager._get_version_dir(version_id)
    run_dir = os.path.join(version_dir, "sim_runs", job_id)
    lors_path = os.path.join(run_dir, "lors.npz")

    if os.path.exists(lors_path):
        try:
            # If the file exists, open it to count the LORs for a helpful message
            with np.load(lors_path) as lor_data:
                num_lors = len(lor_data['start_coords'])
            return jsonify({"success": True, "exists": True, "num_lors": num_lors})
        except Exception as e:
            # If the file is corrupt or unreadable, treat it as non-existent
            return jsonify({"success": False, "error": f"LOR file is corrupt: {str(e)}"}), 500
    else:
        # File does not exist
        return jsonify({"success": True, "exists": False})
# -----------------------------------------------------------------------------------

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
def create_success_response(message="Success",exclude_unchanged_tessellated=True):
    """
    Helper to create a standard success response object, including history state.
    """
    state = project_manager.get_full_project_state_dict(exclude_unchanged_tessellated=exclude_unchanged_tessellated)
    scene = project_manager.get_threejs_description()
    project_name = project_manager.project_name

    # Set the response type based on whether we excluded certain objects.
    if(exclude_unchanged_tessellated):
        response_type = "full_with_exclusions"
    else:
        response_type = "full"

    # Reset the object change tracking.
    project_manager._clear_change_tracker()

    return jsonify({
        "success": True,
        "message": message,
        "project_name": project_name,
        "project_state": state,
        "scene_update": scene,
        "response_type": response_type,
        # --- Add history status to every successful response ---
        "history_status": {
            "can_undo": project_manager.history_index > 0,
            "can_redo": project_manager.history_index < len(project_manager.history) - 1
        }
    })

def create_shallow_response(message, scene_patch=None, project_state_patch=None, full_scene=None):
    """Creates a lightweight response with a patch and possibly the full scene update."""

    # Construct the patch.
    patch = {}
    if scene_patch:
        patch['scene_update'] = scene_patch
    if project_state_patch:
        patch['project_state'] = project_state_patch

    project_name = project_manager.project_name
    
    return jsonify({
        "success": True,
        "message": message,
        "patch": patch,
        "project_name": project_name,
        "scene_update": full_scene,
        "response_type": "patch", # A new response type
        "history_status": {
            "can_undo": project_manager.history_index > 0,
            "can_redo": project_manager.history_index < len(project_manager.history) - 1
        }
    })

@app.route('/api/begin_transaction', methods=['POST'])
def begin_transaction_route():
    project_manager.begin_transaction()
    return jsonify({"success": True, "message": "Transaction started."})

@app.route('/api/end_transaction', methods=['POST'])
def end_transaction_route():
    data = request.get_json() or {}
    description = data.get('description', 'User action')
    project_manager.end_transaction(description)
    # The final state is captured on the backend, but the frontend needs
    # the updated history status (canUndo/canRedo).
    # We will return the full response so the UI updates correctly.
    return create_success_response("Transaction ended.") # Use your full response helper

@app.route('/api/undo', methods=['POST'])
def undo_route():
    success, message = project_manager.undo()
    if success:
        return create_success_response(message)
    else:
        return jsonify({"success": False, "error": message}), 400

@app.route('/api/redo', methods=['POST'])
def redo_route():
    success, message = project_manager.redo()
    if success:
        return create_success_response(message)
    else:
        return jsonify({"success": False, "error": message}), 400

@app.route('/rename_project', methods=['POST'])
def rename_project_route():

    data = request.get_json()
    project_name = data.get('project_name')

    try:
        project_manager.project_name = project_name
        return jsonify({"success": True, "message": f"Project set to {project_name}"})
    except Exception as e:
        return jsonify({"success": False, "error": f"Failed to save version: {e}"}), 500
    
@app.route('/autosave', methods=['POST'])
def autosave_project_api():
    # No data is needed in the request body. The project manager knows the active project.
    success, message = project_manager.auto_save_project()
    if success:
        return jsonify({"success": True, "message": message})
    else:
        # It's not an error if there was nothing to save, so return success.
        return jsonify({"success": True, "message": "No changes to autosave."})

@app.route('/api/save_version', methods=['POST'])
def save_version_route():

    data = request.get_json() or {}
    description = data.get('description', 'User Save')
    try:
        version_name, message = project_manager.save_project_version(description)
        return jsonify({"success": True, "message": f"Version '{version_name}' saved."})
    except Exception as e:
        return jsonify({"success": False, "error": f"Failed to save version: {e}"}), 500

# Helper to get the path for a specific version
def get_version_dir(project_name, version_id):
    return os.path.join(PROJECTS_BASE_DIR, project_name, "versions", version_id)

@app.route('/api/get_project_history', methods=['GET'])
def get_project_history_route():
    project_name = request.args.get('project_name')
    if not project_name:
        return jsonify({"success": False, "error": "Project name is required."}), 400
    
    versions_path = os.path.join(PROJECTS_BASE_DIR, project_name, "versions")
    if not os.path.isdir(versions_path):
        return jsonify({"success": True, "history": []})

    # List directories instead of files, sorting reverse-chronologically
    version_dirs = sorted([d for d in os.listdir(versions_path) if os.path.isdir(os.path.join(versions_path, d))], reverse=True)
    
    history = []
    for version_id in version_dirs:
        sim_runs_path = os.path.join(versions_path, version_id, "sim_runs")
        runs = []
        if os.path.isdir(sim_runs_path):
            runs = sorted(os.listdir(sim_runs_path), reverse=True)
        
        history.append({
            "id": version_id,
            "timestamp": version_id.split('_')[0], # Extract timestamp from name
            "description": version_id.split('_')[1] if '_' in version_id else "Saved",
            "runs": runs # List of job_ids
        })
        
    return jsonify({"success": True, "history": history})

@app.route('/api/load_version', methods=['POST'])
def load_version_route():
    data = request.get_json()
    version_id = data.get('version_id') # This is the filename
    
    if not version_id:
        return jsonify({"success": False, "error": "Project name and version ID are required."}), 400

    try:
        success, message = project_manager.load_project_version(version_id)
        if success:
            return create_success_response(message, exclude_unchanged_tessellated=False)
        else:
            return jsonify({"success": False, "error": message}), 500
    except Exception as e:
        return jsonify({"success": False, "error": f"Failed to load version: {e}"}), 500

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
    project_manager.create_empty_project()

    return create_success_response("New project created.",exclude_unchanged_tessellated=False)

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
            return create_success_response("GDML file processed successfully.",exclude_unchanged_tessellated=False)
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
            return create_success_response("Project loaded successfully.",exclude_unchanged_tessellated=False)
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
    is_sensitive = data.get('is_sensitive', False)
    content_type = data.get('content_type', 'physvol')
    content = data.get('content', [])
    
    new_lv ,error_msg = project_manager.add_logical_volume(
        name, solid_ref, material_ref, vis_attributes, is_sensitive,
        content_type, content
    )
    
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
    is_sensitive = data.get('is_sensitive')
    content_type = data.get('content_type')
    content = data.get('content')

    success ,error_msg = project_manager.update_logical_volume(
        lv_name, solid_ref, material_ref, vis_attributes, is_sensitive,
        content_type, content
    )

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
    
@app.route('/api/update_physical_volume_batch', methods=['POST'])
def update_physical_volume_batch_route():
    data = request.get_json()
    updates_list = data.get('updates')
    if not isinstance(updates_list, list):
        return jsonify({"success": False, "error": "Invalid request: 'updates' must be a list."}), 400

    # The project manager will handle the transaction and recalculation internally
    success, project_state_patch = project_manager.update_physical_volume_batch(updates_list)

    # Compute the full scene again.
    scene_update = project_manager.get_threejs_description()

    if success:
        # After a successful batch update, send back the complete new state
        return create_shallow_response(f"Transformed {len(updates_list)} object(s).", 
                                       project_state_patch=project_state_patch, 
                                       full_scene=scene_update)
    else:
        # If it fails, send back an error and the (potentially partially modified) state
        # A more advanced implementation might revert the changes on failure.
        return jsonify({"success": False, "error": "Error creating response after physical volume batch update"}), 500

@app.route('/api/delete_objects_batch', methods=['POST'])
def delete_objects_batch_route():
    data = request.get_json()
    objects_to_delete = data.get('objects')

    if not isinstance(objects_to_delete, list):
        return jsonify({"success": False, "error": "Invalid request: 'objects' must be a list."}), 400

    # First, pre-filter for non-deletable items like assembly members
    assembly_member_ids = set()
    for asm in project_manager.current_geometry_state.assemblies.values():
        for pv in asm.placements:
            assembly_member_ids.add(pv.id)
            
    filtered_deletions = []
    non_deletable_items = []
    for item in objects_to_delete:
        print(f"Item is {item}")
        if item['type'] == 'physical_volume' and item['id'] in assembly_member_ids:
            non_deletable_items.append(item['id'])
        else:
            filtered_deletions.append(item)
    
    if non_deletable_items:
        return jsonify({
            "success": False, 
            "error": f"Cannot directly delete items that are part of an assembly definition: {', '.join(non_deletable_items)}. Please use the Assembly Editor.",
            "error_type": "dependency"
        }), 409

    # Proceed with the filtered list
    deleted, patch_or_error_msg = project_manager.delete_objects_batch(filtered_deletions)
    
    if deleted:
        return create_shallow_response(
            "Objects deleted successfully.",
            scene_patch=None,
            project_state_patch=patch_or_error_msg.get("project_state"),
            full_scene=patch_or_error_msg.get("scene_update")  # need full scene update for delete
        )
    else:
        error_type = "dependency" if "in use by" in (patch_or_error_msg or "") else "generic"
        status_code = 409 if error_type == "dependency" else 500
        return jsonify({"success": False, "error": patch_or_error_msg, "error_type": error_type}), status_code

# --- Read-only and Export Routes ---
@app.route('/get_project_state', methods=['GET'])
def get_project_state_route():
    """
    This route is for initial page load state restoration.
    If no project exists, it creates a new default one.
    """
    state = project_manager.get_full_project_state_dict(exclude_unchanged_tessellated=False)
    project_name = project_manager.project_name

    # Check if the project is empty (no world volume defined)
    if not state or not state.get('world_volume_ref'):
        print("No active project found, creating a new default world.")
        
        # Call the same logic as the /new_project route
        project_manager.create_empty_project()
        
        # Now get the state and scene again from the newly created project
        state = project_manager.get_full_project_state_dict(exclude_unchanged_tessellated=False)
        scene = project_manager.get_threejs_description()
    else:
        # Project already exists, just get the scene
        scene = project_manager.get_threejs_description()

    # Always return a valid state
    return jsonify({
        "project_state": state,
        "scene_update": scene,
        "project_name": project_name
    })

@app.route('/get_object_details', methods=['GET'])
def get_object_details_route():
    obj_type = request.args.get('type')
    obj_id = request.args.get('id')
    if not obj_type or not obj_id:
        return jsonify({"error": "Type or ID missing"}), 400
    
    if obj_type == "particle_source":
        # For sources, the 'id' from the frontend is the unique ID
        details = None
        for source in project_manager.current_geometry_state.sources.values():
            if source.id == obj_id:
                details = source.to_dict()
                break
    else:
        details = project_manager.get_object_details(obj_type, obj_id)

    if details:
        return jsonify(details)
    
    error_key = "ID" if obj_type in ["physical_volume", "particle_source"] else "name"
    return jsonify({"error": f"{obj_type} with {error_key} '{obj_id}' not found"}), 404

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
            print(f"GEMINI RESPONSE ({model_name}):\n")
            print(ai_json_string)

        else: # Assume it's an Ollama model
            print(f"Sending prompt to Ollama model: {model_name}")
            # messages = [
            #     {
            #         "role": "system",
            #         "content": "You are a helpful assistant. Reasoning: high. Please provide a detailed step-by-step reasoning process before giving the final answer."
            #     },
            #     {
            #         "role": "user",
            #         "content": full_prompt
            #     }
            # ]
            # ollama_response = requests.post(
            #     'http://localhost:11434/api/chat',
            #     json={ "model": model_name,
            #         "messages": messages, 
            #         "stream": False, 
            #         "format": "json",
            #         "options": {
            #             "temperature": 0.7,
            #             "top_p": 0.9,
            #             "num_ctx": 65536
            #         }
            #     },
            #     timeout=ai_timeout
            # )

            # Process the response
            ollama_response = ollama.generate(model=model_name, prompt=full_prompt)
            ai_json_string = ollama_response['response'].strip()
            print(f"OLLAMA RESPONSE ({model_name}):\n")
            print(ai_json_string)

        # Step 3: Parse and process the response using a new ProjectManager method
        ai_data = json.loads(ai_json_string)
        success, error_msg = project_manager.process_ai_response(ai_data)
        
        if success:
            return create_success_response("AI command processed successfully.")
        else:
            return jsonify({"success": False, "error": error_msg or "Failed to process AI response."}), 500

            # else:
            #     print(f"Request failed with status code: {ollama_response.status_code}")
            #     print(ollama_response.text)

            #ollama_response.raise_for_status()
            # print(ollama_response.json().get('response'))
            # response_text = ollama_response.json().get('response').strip()
            # print("\n\nTEXT")
            # print(response_text)

            # # Extract JSON from Markdown code fences if present
            # json_match = re.search(r'```json\s*(.*?)\s*```', response_text, re.DOTALL)
            # if json_match:
            #     json_text = json_match.group(1).strip()
            # else:
            #     json_text = response_text  # Fallback: try parsing raw response

    except requests.exceptions.RequestException as e:
        return jsonify({"success": False, "error": f"Could not connect to AI service: {e}"}), 500
    except json.JSONDecodeError:
        return jsonify({"success": False, "error": "AI returned invalid JSON."}), 500
    except ollama.ResponseError as e:
                print('Ollama error:', e.error)
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
        ai_json_string = file.read().decode('utf-8')
        ai_data = None
        try:
            # First, try the standard, strict JSON parser
            ai_data = json.loads(ai_json_string)
        except json.JSONDecodeError:
            print("AI response was not valid JSON, attempting to parse as Python literal...")
            try:
                # If JSON fails, try parsing it as a Python dictionary literal.
                # This is much safer than eval().
                ai_data = ast.literal_eval(ai_json_string)
            except (ValueError, SyntaxError) as e:
                print(f"Failed to parse AI response as Python literal: {e}")
                return jsonify({"success": False, "error": "AI returned an invalid JSON or Python dictionary string."}), 500

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

@app.route('/import_step_with_options', methods=['POST'])
def import_step_with_options_route():
    if 'stepFile' not in request.files:
        return jsonify({"error": "No STEP file part"}), 400
    if 'options' not in request.form:
        return jsonify({"error": "Missing import options"}), 400
        
    file = request.files['stepFile']
    try:
        options_json = request.form['options']
        options = json.loads(options_json)
    except (json.JSONDecodeError, KeyError) as e:
        return jsonify({"error": f"Invalid options format: {e}"}), 400

    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400
        
    try:
        # We need a new method in ProjectManager to handle this
        success, error_msg = project_manager.import_step_with_options(file, options)
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