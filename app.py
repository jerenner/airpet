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
import shutil
import sched
import time

from datetime import datetime
from flask import Flask, request, jsonify, render_template, Response, session
from flask_cors import CORS

from dotenv import load_dotenv, set_key, find_dotenv
from google import genai  # Correct top-level import
from google.genai import types # Often useful for advanced features
from google.genai import client # For type hinting

from src.expression_evaluator import ExpressionEvaluator 
from src.project_manager import ProjectManager, AUTOSAVE_VERSION_ID
from src.geometry_types import get_unit_value
from src.geometry_types import Material, Solid, LogicalVolume
from src.geometry_types import GeometryState

from PIL import Image

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "a-default-secret-key-for-development") 
CORS(app)

# Configure session cookies for production (HF Spaces iframe support)
if os.getenv("APP_MODE") == 'production':
    app.config['SESSION_COOKIE_SAMESITE'] = 'None'
    app.config['SESSION_COOKIE_SECURE'] = True

# --- Read server-wide config on startup ---
APP_MODE = os.getenv("APP_MODE", "local")  # Default to 'local' if not set
SERVER_GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")


# ------------------------------------------------------------------------------
# Session management

# --- Server-Side Cache for Project Managers ---
# This dictionary holds one ProjectManager instance per user session.
# The key is the user's session ID (uuid).
project_managers = {}

# Projects directory
PROJECTS_BASE_DIR = os.path.join(os.getcwd(), "projects")
os.makedirs(PROJECTS_BASE_DIR, exist_ok=True)

# For timeout
last_access = {}

def get_project_manager_for_session() -> ProjectManager:
    """
    Retrieves or creates a ProjectManager instance for the current user session.
    Also handles isolating their project save directories.
    """
    # 1. Ensure the user has a unique session ID
    if APP_MODE == 'local':
        # In local mode, everyone shares the same "local_user" ID
        if 'user_id' not in session or session['user_id'] != 'local_user':
            session['user_id'] = 'local_user'
    else: # deployed mode
        if 'user_id' not in session:
            session['user_id'] = str(uuid.uuid4())
    
    user_id = session['user_id']

    # 2. Check if a ProjectManager already exists for this session
    if user_id not in project_managers:
        print(f"Creating new session and ProjectManager for user_id: {user_id}")
        # 3. Create a new ProjectManager if one doesn't exist
        expression_evaluator = ExpressionEvaluator()
        pm = ProjectManager(expression_evaluator)

        # 4. Set a session-specific directory for saving projects
        if APP_MODE == 'local':
            # Local mode uses the main projects directory directly
            pm.projects_dir = PROJECTS_BASE_DIR
        else: # deployed mode
            # Deployed mode uses isolated session directories
            session_projects_dir = os.path.join(PROJECTS_BASE_DIR, user_id)
            os.makedirs(session_projects_dir, exist_ok=True)
            pm.projects_dir = session_projects_dir
        
        # 5. Initialize a new, empty project for the new user
        pm.create_empty_project()

        # 6. Store the new instance in our cache
        project_managers[user_id] = pm

        # --- Seed the API key on first-time session creation ---
        if 'gemini_api_key' not in session and SERVER_GEMINI_API_KEY:
            print("Using SERVER_GEMINI_API_KEY for this session.")
            session['gemini_api_key'] = SERVER_GEMINI_API_KEY

    last_access[user_id] = time.time()
    return project_managers[user_id]

# ------------------------------------------------------------------------------
# AI setup
ai_model = "gemma3:12b"
ai_timeout = 3000 # in seconds

# --- Server-Side Cache for Gemini Clients ---
# Key: user_id from session
# Value: A dictionary {'client': client_instance, 'key': api_key_used}
gemini_clients = {}

def get_gemini_client_for_session() -> client.Client | None:
    """
    Retrieves or creates a Gemini client for the current user's session.
    It uses the API key stored in the session and caches the client.
    If the key changes, it creates a new client.
    """
    if 'user_id' not in session:
        # This should ideally not happen if get_project_manager_for_session is called first
        return None

    user_id = session['user_id']
    api_key = session.get('gemini_api_key')

    # If the user has no API key set in their session, ensure no client is cached and return None.
    if not api_key:
        if user_id in gemini_clients:
            del gemini_clients[user_id]
        return None

    cached_client_info = gemini_clients.get(user_id)

    # If a client exists and was created with the *same* key, return it.
    if cached_client_info and cached_client_info['key'] == api_key:
        return cached_client_info['client']

    # Otherwise, create a new client instance for this user's key.
    print(f"Configuring new Gemini client for user session: {user_id}")
    try:
        new_client = genai.Client(api_key=api_key)
        # Cache the new client and the key used to create it
        gemini_clients[user_id] = {'client': new_client, 'key': api_key}
        return new_client
    except Exception as e:
        print(f"Warning: Failed to configure Gemini client for session {user_id}: {e}")
        # If configuration fails, remove any old entry from the cache
        if user_id in gemini_clients:
            del gemini_clients[user_id]
        return None
    
# GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
# gemini_client: client.Client | None = None # Configure Gemini client

# # Configure the Gemini client
# def configure_gemini_client():
#     """Initializes or re-initializes the Gemini client with the current API key."""
#     global GEMINI_API_KEY, gemini_client
#     GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
#     if GEMINI_API_KEY and GEMINI_API_KEY != "YOUR_API_KEY_HERE":
#         try:
#             gemini_client = genai.Client(api_key=GEMINI_API_KEY)
#             print("Google Gemini client configured successfully.")
#             return True
#         except Exception as e:
#             print(f"Warning: Failed to configure Google Gemini client: {e}")
#             gemini_client = None
#             return False
#     else:
#         print("Warning: GEMINI_API_KEY not found or not set. Gemini models will be unavailable.")
#         gemini_client = None
#         return False

# # Initial configuration on startup
# configure_gemini_client()

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
    pm = get_project_manager_for_session()

    data = request.get_json()
    source_id = data.get('source_id') # Can be the ID string or null
    
    success, error_msg = pm.set_active_source(source_id)
    
    if success:
        # We don't need to send the whole state back for this, a simple success is fine.
        # The frontend can manage the radio button state.
        return jsonify({"success": True, "message": "Active source updated."})
    else:
        return jsonify({"success": False, "error": error_msg}), 500

@app.route('/api/simulation/run', methods=['POST'])
def run_simulation():
    pm = get_project_manager_for_session()

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
        version_id = pm.current_version_id
        # If the project has changed or no version is active, save a new one.
        if pm.is_changed or not version_id:
            version_id, _ = pm.save_project_version(f"AutoSave_for_Sim_{job_id[:8]}")

        version_dir = pm._get_version_dir(version_id)
        run_dir = os.path.join(version_dir, "sim_runs", job_id)
        os.makedirs(run_dir, exist_ok=True)

        # Generate macro and geometry inside the final run directory
        macro_path = pm.generate_macro_file(
            job_id, sim_params, GEANT4_BUILD_DIR, run_dir, version_dir
        )

        # This will be the function run in a separate thread
        def run_g4_simulation(job_id, run_dir, executable_path, sim_params):
            num_threads = int(sim_params.get('threads', 1))
            total_events = int(sim_params.get('events', 1))
            
            with SIMULATION_LOCK:
                SIMULATION_STATUS[job_id] = {
                    "status": "Running",
                    "progress": 0,
                    "total_events": total_events,
                    "stdout": [],
                    "stderr": []
                }

            try:
                # --- SINGLE PROCESS MODE ---
                if num_threads <= 1:
                    command = [executable_path, "run.mac"]
                    process = subprocess.Popen(
                        command, cwd=run_dir,
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                        text=True, bufsize=1
                    )
                    with SIMULATION_LOCK:
                         SIMULATION_PROCESSES[job_id] = process
                    
                    # Monitor
                    if process.stdout:
                        for line in iter(process.stdout.readline, ''):
                            line = line.strip()
                            if line:
                                with SIMULATION_LOCK:
                                    SIMULATION_STATUS[job_id]['stdout'].append(line)
                                    if ">>> Event" in line and "starts" in line:
                                        try:
                                            # Using regex might be safer but split is okay
                                            parts = line.split()
                                            # format: ">>> Event N starts..."
                                            if len(parts) > 2 and parts[2].isdigit():
                                                SIMULATION_STATUS[job_id]['progress'] = int(parts[2]) + 1
                                        except: pass
                    
                    stdout_remainder, stderr_output = process.communicate()
                    if stderr_output:
                         with SIMULATION_LOCK:
                             SIMULATION_STATUS[job_id]['stderr'].append(stderr_output)
                             
                    final_return_code = process.returncode

                # --- MULTI-PROCESS MODE ---
                else:
                    msg = f"Starting {num_threads} parallel processes for {total_events} events..."
                    with SIMULATION_LOCK:
                        SIMULATION_STATUS[job_id]['stdout'].append(msg)
                    
                    # 1. Prepare Macros
                    base_macro_path = os.path.join(run_dir, "run.mac")
                    with open(base_macro_path, 'r') as f:
                        base_lines = f.readlines()
                    
                    # Filter out commands we will override
                    filtered_lines = []
                    for line in base_lines:
                        s = line.strip()
                        if s.startswith("/run/beamOn"): continue
                        if s.startswith("/random/setSeeds"): continue
                        if s.startswith("/analysis/setFileName"): continue
                        if s.startswith("/run/numberOfThreads"): continue 
                        if s.startswith("/g4pet/run/saveHits"): continue # We force true usually, but read params
                        filtered_lines.append(line)
                    
                    # Base seeds
                    seed1 = int(sim_params.get('seed1', 12345))
                    seed2 = int(sim_params.get('seed2', 67890))
                    
                    events_per_thread = total_events // num_threads
                    remainder = total_events % num_threads
                    
                    procs = []
                    
                    for i in range(num_threads):
                        n_events = events_per_thread + (1 if i < remainder else 0)
                        if n_events <= 0: continue
                        
                        macro_name = f"run_t{i}.mac"
                        out_name = f"output_t{i}.hdf5"
                        
                        # Unique seeds
                        s1 = seed1 + i*1000
                        s2 = seed2 + i*1000
                        
                        # Write specific macro
                        with open(os.path.join(run_dir, macro_name), 'w') as f:
                            f.writelines(filtered_lines)
                            f.write(f"\n/random/setSeeds {s1} {s2}")
                            f.write(f"\n/analysis/setFileName {out_name}")
                            f.write(f"\n/run/beamOn {n_events}\n")
                        
                        cmd = [executable_path, macro_name]
                        p = subprocess.Popen(
                            cmd, cwd=run_dir,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, bufsize=1
                        )
                        procs.append(p)
                    
                    with SIMULATION_LOCK:
                        SIMULATION_PROCESSES[job_id] = procs # Store list for parallel stop handling

                    # 2. Monitor Loop
                    # We launch threads to continuously drain stdout/stderr of all processes
                    # to prevent deadlocks and update progress.
                    monitor_threads = []
                    
                    def stdout_reader(proc, idx):
                        for line in iter(proc.stdout.readline, ''):
                            line = line.strip()
                            if not line: continue
                            
                            # Filter spammy lines
                            if "Checking overlaps for volume" in line: continue
                            
                            # Log T0 fully, others only on error/warning
                            is_interesting = (idx == 0) or ("error" in line.lower()) or ("warning" in line.lower()) or ("exception" in line.lower())
                            
                            if is_interesting:
                                prefix = f"[T{idx}] "
                                with SIMULATION_LOCK:
                                    SIMULATION_STATUS[job_id]['stdout'].append(prefix + line)
                                    
                                    # Parse progress (T0 only) to avoid jitter
                                    if idx == 0 and ">>> Event" in line and "starts" in line:
                                        try:
                                            # Example: ">>> Event 123 starts..."
                                            parts = line.split()
                                            if len(parts) > 2 and parts[2].isdigit():
                                                local_ev = int(parts[2])
                                                SIMULATION_STATUS[job_id]['progress'] = (local_ev + 1) * num_threads
                                        except: pass
                        proc.stdout.close()

                    def stderr_reader(proc, idx):
                        for line in iter(proc.stderr.readline, ''):
                            line = line.strip()
                            if line:
                                with SIMULATION_LOCK:
                                    SIMULATION_STATUS[job_id]['stderr'].append(f"[T{idx}] {line}")
                        proc.stderr.close()

                    for i, p in enumerate(procs):
                        # Start stdout reader
                        t_out = threading.Thread(target=stdout_reader, args=(p, i))
                        t_out.start()
                        monitor_threads.append(t_out)
                        
                        # Start stderr reader
                        t_err = threading.Thread(target=stderr_reader, args=(p, i))
                        t_err.start()
                        monitor_threads.append(t_err)
                    
                    # Wait for all streaming to finish
                    for t in monitor_threads:
                        t.join()
                    
                    # Ensure all processes have exited and set return code
                    final_return_code = 0
                    for p in procs:
                        p.wait()
                        if p.returncode != 0:
                            final_return_code = p.returncode
                    
                    # (The following code expects final_return_code and cleanup)

                    if final_return_code == 0:
                         with SIMULATION_LOCK:
                            SIMULATION_STATUS[job_id]['stdout'].append("Parallel tasks completed. Merging...")

                # --- MERGE LOGIC ---
                if final_return_code == 0:
                    import glob
                    import shutil
                    # Look for separate files and sort humerically to ensure correct EventID order
                    t_files = glob.glob(os.path.join(run_dir, "output_t*.hdf5"))
                    if not t_files or len(t_files) == 0:
                         t_files = glob.glob(os.path.join(run_dir, "run_t*.hdf5"))

                    if t_files:
                        try:
                            t_files.sort(key=lambda x: int(os.path.basename(x).split('_t')[1].split('.')[0]))
                        except:
                            t_files.sort()
                        
                        target_path = os.path.join(run_dir, "output.hdf5")
                        shutil.copyfile(t_files[0], target_path)

                        # Robust Iterative Merge Logic (Matches repair_full_merge.py)
                        # 1. Clean T0 (Base)
                        try:
                            with h5py.File(target_path, 'r+') as f:
                                if 'default_ntuples/Hits' in f:
                                    hits = f['default_ntuples/Hits']
                                    
                                    # Detect limit
                                    lim_t0 = 0
                                    if 'EventID' in hits and 'pages' in hits['EventID']:
                                        ev = hits['EventID']['pages'][:]
                                        nz = np.nonzero(ev)[0]
                                        lim_t0 = nz[-1] + 1 if len(nz) > 0 else 0
                                    
                                    # Clean T0 Columns
                                    for c in hits:
                                        if isinstance(hits[c], h5py.Group) and 'pages' in hits[c]:
                                            dset = hits[c]['pages']
                                            data = dset[:lim_t0]
                                            attrs = dict(dset.attrs)
                                            del hits[c]['pages']
                                            # Create Chunked + Compressed
                                            dn = hits[c].create_dataset('pages', data=data, maxshape=(None,)+data.shape[1:], chunks=True, compression="gzip")
                                            for k,v in attrs.items(): dn.attrs[k] = v
                                    print(f"T0 Initialized: {lim_t0} rows (Compressed)")
                        except Exception as e:
                            print(f"T0 Clean Error: {e}")

                        # 2. Append T1..TN
                        evt_per_thread = total_events // num_threads
                        
                        try:
                            with h5py.File(target_path, 'r+') as f_dst:
                                if 'default_ntuples/Hits' in f_dst:
                                    grp_dst_hits = f_dst['default_ntuples/Hits']
                                    
                                    for src_path in t_files[1:]:
                                        fname = os.path.basename(src_path)
                                        current_offset = 0
                                        try:
                                            t_idx = int(fname.split('_t')[1].split('.')[0])
                                            current_offset = t_idx * evt_per_thread
                                        except: pass
                                        
                                        with h5py.File(src_path, 'r') as f_src:
                                            if 'default_ntuples/Hits' not in f_src: continue
                                            grp_src_hits = f_src['default_ntuples/Hits']
                                            
                                            # Detect Source Limit
                                            lim_src = 0
                                            if 'EventID' in grp_src_hits:
                                                 ev = grp_src_hits['EventID']['pages'][:]
                                                 nz = np.nonzero(ev)[0]
                                                 if len(nz)>0: lim_src = nz[-1]+1
                                            
                                            print(f"Merging {fname}: Limit={lim_src} Offset={current_offset}")

                                            # Merge Columns Iteratively
                                            for col in grp_dst_hits:
                                                if col not in grp_src_hits: continue
                                                
                                                dst_node = grp_dst_hits[col]
                                                src_node = grp_src_hits[col]
                                                
                                                # Handle Pages (Data)
                                                if isinstance(dst_node, h5py.Group) and 'pages' in dst_node:
                                                    dst_d = dst_node['pages']
                                                    src_d = src_node['pages']
                                                    
                                                    # Read valid data
                                                    data = src_d[:lim_src]
                                                    
                                                    # Apply Offset to EventID
                                                    if col == "EventID":
                                                        data = data.astype(np.int64)
                                                        if current_offset > 0: data += current_offset
                                                    
                                                    # Write
                                                    old_len = dst_d.shape[0]
                                                    add_len = len(data)
                                                    dst_d.resize((old_len+add_len,) + dst_d.shape[1:])
                                                    dst_d[old_len:old_len+add_len] = data
                                                
                                                # Handle Metadata (entries)
                                                elif isinstance(dst_node, h5py.Dataset) and col=='entries':
                                                    dst_node[...] += src_node[...]
                        except Exception as e:
                             print(f"Merge Loop Error: {e}")
                                                
                        with SIMULATION_LOCK:
                            SIMULATION_STATUS[job_id]['stdout'].append("Merge finished.")
                            # Cleanup (DISABLE FOR DEBUGGING)
                            for f in t_files: os.remove(f)

                with SIMULATION_LOCK:
                    if final_return_code == 0:
                        SIMULATION_STATUS[job_id]['progress'] = total_events
                        SIMULATION_STATUS[job_id]['status'] = 'Completed'
                        LATEST_COMPLETED_JOB_ID = job_id
                    else:
                        SIMULATION_STATUS[job_id]['status'] = 'Error'
                    SIMULATION_PROCESSES.pop(job_id, None)

            except Exception as e:
                traceback.print_exc()
                with SIMULATION_LOCK:
                    SIMULATION_STATUS[job_id]['status'] = 'Error'
                    SIMULATION_STATUS[job_id]['stderr'].append(str(e))
                SIMULATION_PROCESSES.pop(job_id, None)

        # Start the thread
        executable_path = os.path.relpath(GEANT4_EXECUTABLE, run_dir)
        thread = threading.Thread(target=run_g4_simulation, args=(job_id, run_dir, executable_path, sim_params))
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
    pm = get_project_manager_for_session()
    version_dir = pm._get_version_dir(version_id)
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
    pm = get_project_manager_for_session()
    version_dir = pm._get_version_dir(version_id)
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
        process_or_list = SIMULATION_PROCESSES.get(job_id)
        if process_or_list:
            # Handle List (Parallel execution)
            if isinstance(process_or_list, list):
                count = 0
                for p in process_or_list:
                    if p.poll() is None:
                        p.terminate()
                        count += 1
                return jsonify({"success": True, "message": f"Stop signal sent to {count} processes for job {job_id}."})
            
            # Handle Single (Serial execution)
            else:
                proc = process_or_list
                if proc.poll() is None:
                    print(f"Terminating simulation job {job_id}...")
                    proc.terminate()
                    # We don't need to wait here, the monitoring thread will handle the status update
                    return jsonify({"success": True, "message": f"Stop signal sent to job {job_id}."})
                else:
                    return jsonify({"success": False, "error": "Job has already finished."}), 404
        else:
            return jsonify({"success": False, "error": "Job ID not found or already completed."}), 404
    
@app.route('/api/add_source', methods=['POST'])
def add_source_route():
    pm = get_project_manager_for_session()

    data = request.get_json()
    name_suggestion = data.get('name', 'gps_source')
    gps_commands = data.get('gps_commands', {})
    position = data.get('position', {'x': '0', 'y': '0', 'z': '0'})
    rotation = data.get('rotation', {'x': '0', 'y': '0', 'z': '0'})
    confine_to_pv = data.get('confine_to_pv')
    activity = data.get('activity', 1.0)
    volume_link_id = data.get('volume_link_id')
    
    new_source, error_msg = pm.add_source(
        name_suggestion, gps_commands, position, rotation, activity, confine_to_pv, volume_link_id)
    if new_source:
        return create_success_response(pm, "Particle source created.")
    else:
        return jsonify({"success": False, "error": error_msg}), 500

@app.route('/api/update_source_transform', methods=['POST'])
def update_source_transform_route():
    pm = get_project_manager_for_session()

    data = request.get_json()
    source_id = data.get('id')
    new_position = data.get('position')
    new_rotation = data.get('rotation')

    if not source_id:
        return jsonify({"error": "Source ID missing"}), 400
        
    success, error_msg = pm.update_source_transform(
        source_id, new_position, new_rotation
    )
    if success:
        return create_success_response(pm, f"Source {source_id} transform updated.")
    else:
        return jsonify({"success": False, "error": error_msg or "Could not update source transform."}), 404

@app.route('/api/get_source_params_from_volume', methods=['POST'])
def get_source_params_from_volume_route():
    data = request.json
    volume_id = data.get('volume_id')
    if not volume_id:
        return jsonify({'success': False, 'error': 'No volume_id provided'}), 400
    
    pm = get_project_manager_for_session()
    result = pm.get_source_params_from_volume(volume_id)
    return jsonify(result)

@app.route('/api/update_source', methods=['POST'])
def update_source_route():
    pm = get_project_manager_for_session()

    data = request.get_json()
    source_id = data.get('id')
    new_name = data.get('name')
    new_gps_commands = data.get('gps_commands')
    new_position = data.get('position')
    new_rotation = data.get('rotation')
    new_activity = data.get('activity')
    new_confine_to_pv = data.get('confine_to_pv')
    new_volume_link_id = data.get('volume_link_id')

    if not source_id:
        return jsonify({"success": False, "error": "Source ID is required."}), 400

    success, error_msg = pm.update_particle_source(
        source_id, new_name, new_gps_commands, new_position, new_rotation, new_activity, new_confine_to_pv, new_volume_link_id
    )

    if success:
        return create_success_response(pm, "Particle source updated successfully.")
    else:
        return jsonify({"success": False, "error": error_msg}), 500
    
@app.route('/api/simulation/process_lors/<version_id>/<job_id>', methods=['POST'])
def process_lors_route(version_id, job_id):
    """
    Processes Geant4 hits from HDF5, finds coincidences, and saves LORs.
    """
    pm = get_project_manager_for_session()

    data = request.get_json()
    coincidence_window_ns = data.get('coincidence_window_ns', 4.0)  # 4 ns window
    energy_cut = data.get('energy_cut', 0.0)
    energy_resolution = data.get('energy_resolution', 0.05)
    position_resolution = data.get('position_resolution', {'x': 0.0, 'y': 0.0, 'z': 0.0})

    # This function will run in the background
    def process_lors_in_background(app, version_id, job_id, coincidence_window_ns, energy_cut, energy_resolution, position_resolution):
        with app.app_context(): # Needed to work within Flask's context
            version_dir = pm._get_version_dir(version_id)
            run_dir = os.path.join(version_dir, "sim_runs", job_id)
            hdf5_path = os.path.join(run_dir, "output.hdf5")
            lors_output_path = os.path.join(run_dir, "lors.npz")

            try:
                if not os.path.exists(hdf5_path):
                    raise FileNotFoundError("Simulation output file not found.")

                with LOR_PROCESSING_LOCK:
                    LOR_PROCESSING_STATUS[job_id] = {"status": "Reading HDF5...", "progress": 0, "total": 0}

                # CHUNKED PROCESSING WITH INCREMENTAL WRITE TO PREVENT OOM
                # Process in chunks and write valid LORs immediately to a temp HDF5
                CHUNK_SIZE = 50000000 
                temp_h5_path = os.path.join(run_dir, "temp_lors.h5")
                
                total_unique_events = 0
                total_lors_found = 0
                
                # Check for existing temp file and remove it
                if os.path.exists(temp_h5_path):
                    os.remove(temp_h5_path)
                
                # Open temp HDF5 for incremental writing
                # Open temp HDF5 for incremental writing AND input HDF5 for reading
                with h5py.File(temp_h5_path, 'w') as f_out, h5py.File(hdf5_path, 'r') as f:
                    # Create resizable datasets for LOR coordinates
                    # Shape (N, 3), float32 to save space
                    dset_start = f_out.create_dataset('start_coords', shape=(0, 3), maxshape=(None, 3), dtype='float32', chunks=(10000, 3))
                    dset_end   = f_out.create_dataset('end_coords',   shape=(0, 3), maxshape=(None, 3), dtype='float32', chunks=(10000, 3))
                    group = f['/default_ntuples/Hits']
                    cols_to_load = [k for k in group.keys() if k not in ['columns', 'entries', 'forms', 'names']]
                    
                    # Determine total size from EventID
                    ev_dset = group['EventID']['pages']
                    total_hits = ev_dset.shape[0]
                    
                    with LOR_PROCESSING_LOCK:
                        LOR_PROCESSING_STATUS[job_id]["total"] = int(total_hits)
                    
                    current_idx = 0
                    
                    while current_idx < total_hits:
                        # 1. Determine Chunk Boundary (Ensure no broken EventIDs)
                        end_idx = min(current_idx + CHUNK_SIZE, total_hits)
                        
                        if end_idx < total_hits:
                            last_id = ev_dset[end_idx-1]
                            next_id = ev_dset[end_idx]
                            
                            if last_id == next_id:
                                # Scan forward to find boundary to avoid splitting an event
                                buffer_size = 5000
                                search_cursor = end_idx
                                found_boundary = False
                                
                                while search_cursor < total_hits:
                                    buff = ev_dset[search_cursor : min(search_cursor+buffer_size, total_hits)]
                                    diffs = np.where(buff != last_id)[0]
                                    
                                    if len(diffs) > 0:
                                        end_idx = search_cursor + diffs[0]
                                        found_boundary = True
                                        break
                                    else:
                                        search_cursor += len(buff)
                                        
                                    # Safety Break: If we scan too far (e.g. > 500k hits) without finding a boundary,
                                    # something is wrong or the event is absurdly large. 
                                    # Just cut here to prevent OOM. We might lose 1 event, which is acceptable.
                                    if (search_cursor - end_idx) > 500000:
                                        print(f"Warning: Could not find EventID boundary after scanning 500k hits. Force splitting at {end_idx}.")
                                        found_boundary = True # Treat as found to stop using total_hits
                                        # end_idx remains as originally set (current + CHUNK values)
                                        # But wait, original 'end_idx' was the start of the scan.
                                        # We should probably just stick with original end_idx.
                                        break
                                
                                if not found_boundary:
                                    end_idx = total_hits 
                        
                        # 2. Read Chunk
                        data_chunk = {}
                        for k in cols_to_load:
                            data_chunk[k] = group[k]['pages'][current_idx : end_idx]
                            
                        # 3. Process Chunk
                        hits_df = pd.DataFrame(data_chunk)
                        del data_chunk 
                        
                        hits_df.columns = [x.decode('utf-8') if isinstance(x, bytes) else x for x in hits_df.columns]
                        
                        # Energy smearing
                        if energy_resolution > 0:
                            hits_df['Edep'] *= (1 + np.random.normal(0, energy_resolution, size=len(hits_df)))

                        # Energy cut
                        if energy_cut > 0:
                            hits_df = hits_df[hits_df['Edep'] >= energy_cut]
                        
                        # Position smearing
                        sigma_x = position_resolution.get('x', 0.0)
                        sigma_y = position_resolution.get('y', 0.0)
                        sigma_z = position_resolution.get('z', 0.0)

                        if sigma_x > 0: hits_df['PosX'] += np.random.normal(0, sigma_x, size=len(hits_df))
                        if sigma_y > 0: hits_df['PosY'] += np.random.normal(0, sigma_y, size=len(hits_df))
                        if sigma_z > 0: hits_df['PosZ'] += np.random.normal(0, sigma_z, size=len(hits_df))
                        
                        hits_df.sort_values(by=['EventID', 'Time'], inplace=True)
                        
                        total_unique_events += hits_df['EventID'].nunique()
                        
                        hits_df['hit_rank'] = hits_df.groupby('EventID').cumcount()
                
                        # Filter for the first and second hits
                        hits1 = hits_df[hits_df['hit_rank'] == 0]
                        hits2 = hits_df[hits_df['hit_rank'] == 1]
                        
                        # Merge to align pairs by EventID
                        # Inner merge ensures we only keep events that have at least 2 hits
                        pairs = pd.merge(hits1, hits2, on='EventID', suffixes=('_1', '_2'))
                
                        # Apply Coincidence Window
                        dt = (pairs['Time_2'] - pairs['Time_1']).abs()
                        valid_pairs = pairs[dt < coincidence_window_ns]
                        
                        if not valid_pairs.empty:
                            starts = valid_pairs[['PosX_1', 'PosY_1', 'PosZ_1']].values.astype(np.float32)
                            ends = valid_pairs[['PosX_2', 'PosY_2', 'PosZ_2']].values.astype(np.float32)
                            
                            n_new = len(starts)
                            
                            # Incremental Write to Temp HDF5
                            current_size = dset_start.shape[0]
                            new_size = current_size + n_new
                            
                            dset_start.resize((new_size, 3))
                            dset_end.resize((new_size, 3))
                            
                            dset_start[current_size:new_size] = starts
                            dset_end[current_size:new_size] = ends
                            
                            total_lors_found += n_new
                        
                        with LOR_PROCESSING_LOCK:
                             LOR_PROCESSING_STATUS[job_id]["progress"] = int(end_idx)
                             status_msg = f"Processing LORs... ({end_idx*100//total_hits}%)"
                             LOR_PROCESSING_STATUS[job_id]["status"] = status_msg
                        
                        current_idx = end_idx
                        del hits_df, hits1, hits2, pairs, valid_pairs
                        import gc; gc.collect()

                if total_lors_found > 0:
                    print(f"Converting {temp_h5_path} to {lors_output_path}...")
                    # Read from temp HDF5 and save as NPZ
                    # Note: This assumes the compressed LORs fit in RAM. If not, we should keep HDF5.
                    # 100M LORs ~ 2.4GB RAM. Should be OK.
                    with h5py.File(temp_h5_path, 'r') as f_in:
                        final_starts = f_in['start_coords'][:]
                        final_ends = f_in['end_coords'][:]
                        
                    all_tof_bins = np.zeros(len(final_starts), dtype=int)
                    
                    np.savez_compressed(
                        lors_output_path,
                        start_coords=final_starts,
                        end_coords=final_ends,
                        tof_bins=all_tof_bins,
                        energy_cut=energy_cut,
                        energy_resolution=energy_resolution,
                        position_resolution=position_resolution
                    )
                    
                    # Clean up temp file
                    if os.path.exists(temp_h5_path):
                        os.remove(temp_h5_path)
                    
                    msg = f"Processed {total_lors_found} LORs from {total_unique_events} events."
                else:
                    if os.path.exists(temp_h5_path):
                        os.remove(temp_h5_path)
                    raise ValueError("No valid coincidences found.")

                with LOR_PROCESSING_LOCK:
                    LOR_PROCESSING_STATUS[job_id] = {
                        "status": "Completed", 
                        "message": msg
                    }

            except Exception as e:
                import traceback
                traceback.print_exc()
                with LOR_PROCESSING_LOCK:
                    LOR_PROCESSING_STATUS[job_id] = {"status": "Error", "message": str(e)}
                traceback.print_exc()

    # Start the background task
    thread = threading.Thread(target=process_lors_in_background, args=(app, version_id, job_id, coincidence_window_ns, energy_cut, energy_resolution, position_resolution))
    thread.start()

    return jsonify({"success": True, "message": "LOR processing started."}), 202
    
@app.route('/api/reconstruction/run/<version_id>/<job_id>', methods=['POST'])
def run_reconstruction_route(version_id, job_id):
    """
    Runs MLEM reconstruction using parallelproj on the pre-processed LORs.
    """
    pm = get_project_manager_for_session()

    data = request.get_json()
    iterations = data.get('iterations', 1)
    # Get image geometry parameters from the request
    img_shape = tuple(data.get('image_size', [128, 128, 128]))
    voxel_size = tuple(data.get('voxel_size', [2.0, 2.0, 2.0]))
    normalization = data.get('normalization', True)
    
    # Attenuation Correction Parameters
    ac_enabled = data.get('ac_enabled', False)
    ac_shape = data.get('ac_shape', 'cylinder')
    ac_radius = float(data.get('ac_radius', 108.0)) # Default Jaszczak inner radius
    ac_length = float(data.get('ac_length', 186.0)) # Default Jaszczak height
    ac_mu = float(data.get('ac_mu', 0.096)) # Water attenuation coefficient (cm^-1)

    # This ensures the reconstruction grid is centered at (0,0,0) in world coordinates.
    # We calculate the position of the corner of the first voxel.
    image_origin = - (np.array(img_shape, dtype=np.float32) / 2 - 0.5) * np.array(voxel_size, dtype=np.float32)

    version_dir = pm._get_version_dir(version_id)
    run_dir = os.path.join(version_dir, "sim_runs", job_id)
    lors_path = os.path.join(run_dir, "lors.npz")

    # Save to HDF5
    recon_output_path = os.path.join(run_dir, "reconstruction.h5")

    if not os.path.exists(lors_path):
        return jsonify({"success": False, "error": "LOR file not found. Please process coincidences first."}), 404

    try:
        lor_data = np.load(lors_path, allow_pickle=True)
        event_start_coords = lor_data['start_coords']
        event_end_coords = lor_data['end_coords']
        
        # Load Position Resolution from LOR file to match Geometry
        position_resolution = {}
        if 'position_resolution' in lor_data:
            pr = lor_data['position_resolution']
            if pr.shape == ():
                position_resolution = pr.item()
            else:
                position_resolution = pr.tolist()

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
        
        # --- Attenuation Correction ---
        ac_factors = None
        if ac_enabled:
            print("Generating Mu-Map for Attenuation Correction...")
            # Create a mu-map image (3D array)
            # We assume the phantom defines the attenuation volume.
            
            # Coordinate grid for the image
            xx, yy, zz = xp.meshgrid(
                (xp.arange(img_shape[0], dtype=xp.float32, device=dev) * voxel_size[0]) + image_origin[0] + voxel_size[0]/2,
                (xp.arange(img_shape[1], dtype=xp.float32, device=dev) * voxel_size[1]) + image_origin[1] + voxel_size[1]/2,
                (xp.arange(img_shape[2], dtype=xp.float32, device=dev) * voxel_size[2]) + image_origin[2] + voxel_size[2]/2,
                indexing='ij'
            )
            
            mu_map = xp.zeros(img_shape, dtype=xp.float32, device=dev)
            
            if ac_shape == 'cylinder':
                # Jaszczak phantom definition in phantom.json:
                # Assuming phantom is centered at (0,0,0).
                
                # Equation: x^2 + y^2 < R^2 AND |z| < L/2
                # Note: xx, yy, zz are 3D arrays.
                mask = (xx**2 + yy**2 <= ac_radius**2) & (xp.abs(zz) <= ac_length/2)
                mu_map = xp.where(mask, ac_mu, 0.0)
                
            print(f"Projecting Attenuation Map along {lm_proj.num_events} LORs...")
            # Forward project the mu-map to get line integrals
            attenuation_integrals = lm_proj(mu_map)

            # Calculate attenuation factors: exp(-integral)
            # Factor A_i is the survival probability.
            ac_factors = xp.exp(-attenuation_integrals * 0.1) 
            # Note: voxel_size, ac_radius are in mm. ac_mu is in cm^-1.
            # Integral will be in [mm * cm^-1]. 
            # We need scaling: 1mm = 0.1cm. So multiply integral by 0.1.
            
            print(f"Attenuation Correction factors calculated. Range: [{xp.min(ac_factors):.4f}, {xp.max(ac_factors):.4f}], Mean: {xp.mean(ac_factors):.4f}")

        # --- Monte Carlo Sensitivity Map Generation ---
        # Instead of using measured LORs (which are biased by activity), we generate
        # Random LORs to estimate the true scanner sensitivity (Geometry + Attenuation).
        print("Estimating Scanner Geometry from data...")
        # Calculate R for start/end points
        r_start = xp.sqrt(event_start_coords_xp[:,0]**2 + event_start_coords_xp[:,1]**2)
        r_end = xp.sqrt(event_end_coords_xp[:,0]**2 + event_end_coords_xp[:,1]**2)
        scanner_radius = float(xp.mean(xp.concat((r_start, r_end))))
        
        z_start = event_start_coords_xp[:,2]
        z_end = event_end_coords_xp[:,2]
        z_min = float(xp.min(xp.concat((z_start, z_end))))
        z_max = float(xp.max(xp.concat((z_start, z_end))))
        scanner_length = z_max - z_min
        
        print(f"Scanner Geometry (Full Data): Radius={scanner_radius:.1f}mm, Length={scanner_length:.1f}mm, Z_range=[{z_min:.1f}, {z_max:.1f}]")

        # Optimization: Restrict random LOR Z-range to the Reconstruction FOV (+ margin)
        # This prevents wasting 90% of randoms on empty space if the scanner is long but the image is short.
        fov_z_start = image_origin[2]
        fov_z_end = image_origin[2] + (img_shape[2] * voxel_size[2])
        margin = scanner_radius * 0.5 # Allow oblique rays from reasonably far out
        
        # Clamp, but don't exceed scanner physical limits (if we trust z_min/max from data)
        z_min_opt = max(z_min, fov_z_start - margin)
        z_max_opt = min(z_max, fov_z_end + margin)
        
        print(f"Optimizing Sensitivity Generation Z-Range: [{z_min_opt:.1f}, {z_max_opt:.1f}] (concentrating LORs on FOV)")
        
        # Use optimized Z range for random generation
        z_min, z_max = z_min_opt, z_max_opt

        num_random_lors = 20000000
        print(f"Generating {num_random_lors} random LORs for Unbiased Sensitivity Map...")
        
        # Generate random angles and Z positions
        # Note: We use numpy for generation then move to xp (Device)
        phi1 = np.random.uniform(0, 2*np.pi, num_random_lors)
        z1 = np.random.uniform(z_min, z_max, num_random_lors)
        
        phi2 = np.random.uniform(0, 2*np.pi, num_random_lors)
        z2 = np.random.uniform(z_min, z_max, num_random_lors)
        
        # Convert to Cartesian
        rand_start = np.zeros((num_random_lors, 3), dtype=np.float32)
        rand_start[:,0] = scanner_radius * np.cos(phi1)
        rand_start[:,1] = scanner_radius * np.sin(phi1)
        rand_start[:,2] = z1
        
        rand_end = np.zeros((num_random_lors, 3), dtype=np.float32)
        rand_end[:,0] = scanner_radius * np.cos(phi2)
        rand_end[:,1] = scanner_radius * np.sin(phi2)
        rand_end[:,2] = z2
        
        rand_start_xp = xp.asarray(rand_start, device=dev)
        rand_end_xp = xp.asarray(rand_end, device=dev)

        # Apply Position Resolution Smearing to Sensitivity LORs (Match Data)
        # If we don't do this, the sensitivity map is "sharp" while data is "blurred", causing edge artifacts.
        if position_resolution:
            sigma_x = position_resolution.get('x', 0.0)
            sigma_y = position_resolution.get('y', 0.0)
            sigma_z = position_resolution.get('z', 0.0)
            
            if sigma_x > 0:
                rand_start_xp[:, 0] += xp.asarray(np.random.normal(0, sigma_x, num_random_lors), device=dev)
                rand_end_xp[:, 0]   += xp.asarray(np.random.normal(0, sigma_x, num_random_lors), device=dev)
            if sigma_y > 0:
                rand_start_xp[:, 1] += xp.asarray(np.random.normal(0, sigma_y, num_random_lors), device=dev)
                rand_end_xp[:, 1]   += xp.asarray(np.random.normal(0, sigma_y, num_random_lors), device=dev)
            if sigma_z > 0:
                rand_start_xp[:, 2] += xp.asarray(np.random.normal(0, sigma_z, num_random_lors), device=dev)
                rand_end_xp[:, 2]   += xp.asarray(np.random.normal(0, sigma_z, num_random_lors), device=dev)
        
        # Create a Projector for the Random LORs
        sens_proj = parallelproj.ListmodePETProjector(
            rand_start_xp, rand_end_xp, img_shape, voxel_size, 
            img_origin=xp.asarray(image_origin, device=dev)
        )
        
        # Calculate Attenuation for Random LORs (if AC enabled)
        sens_weights = xp.ones(num_random_lors, dtype=xp.float32, device=dev)
        
        if ac_enabled and ac_shape == 'cylinder':
            print("Calculating Attenuation for Sensitivity LORs...")
            # We must project the mu-map along these random LORs
            # Note: mu_map is already defined/calculated above
            attenuation_integrals_rand = sens_proj(mu_map)
            ac_factors_rand = xp.exp(-attenuation_integrals_rand * 0.1)
            sens_weights *= ac_factors_rand

        # Backproject to get Sensitivity Map
        # We scale by (Total Possible LORs / Simulated LORs) factor? 
        # Actually, scaling constant cancels out in MLEM ratio update x_new = x_old * (Backproj / Sensitivity).
        # As long as relative profile is correct.
        sensitivity_image = sens_proj.adjoint(sens_weights)

        # --- Smoothing Sensitivity Map ---
        # Even with 5M events, the random map will be noisy. We smooth it to get a clean geometric profile.
        print("Smoothing Sensitivity Map (sigma=4mm) to remove Monte Carlo noise...")
        from scipy.ndimage import gaussian_filter
        
        sens_cpu = parallelproj.to_numpy_array(sensitivity_image)
        sigma_mm = 4.0 
        sigma_vox = [sigma_mm / float(v) for v in voxel_size]
        sens_smoothed_cpu = gaussian_filter(sens_cpu, sigma=sigma_vox)
        
        sensitivity_image = xp.asarray(sens_smoothed_cpu, device=dev)

        # --- MLEM Reconstruction Loop ---
        x = xp.ones(img_shape, dtype=xp.float32, device=dev) # Initial image is all ones

        # --- Create a safe version of the sensitivity image for division ---
        max_sens = float(xp.max(sensitivity_image))
        min_sens = float(xp.min(sensitivity_image))
        print(f"Sensitivity Image - Max: {max_sens:.2e}, Min: {min_sens:.2e}")
        
        # Use a relative threshold (e.g., 0.1% or smaller) to avoid exploding values at edges
        # sens_threshold = max_sens * 1e-4 
        # Increase threshold slightly to be safer against edge artifacts?
        sens_threshold = max_sens * 1e-3
        print(f"Sensitivity Threshold used: {sens_threshold:.2e}")
        
        sensitivity_image_safe_for_division = xp.where(sensitivity_image < sens_threshold, 1.0, sensitivity_image)

        for i in range(iterations):
            print(f"Running MLEM iteration {i+1}/{iterations}...")
            
            # Forward projection of current estimate
            ybar = lm_proj(x)
    
            # Ratio = y_measured / Expected = 1 / (Forward(x))        
            ratio_denominator = ybar
            # if ac_enabled and ac_factors is not None:
            #     ratio_denominator *= ac_factors
            
            # Add a small epsilon to avoid division by zero
            ratio_denominator = xp.where(ratio_denominator == 0, 1e-9, ratio_denominator)

            # Backprojection of the ratio
            # Adjoint of 1/Expected
            back_projection = lm_proj.adjoint(1 / ratio_denominator)

            if normalization:
                # Perform the division using the safe denominator (Sensitivity Correction)
                update_term = (x / sensitivity_image_safe_for_division) * back_projection
                # Now, apply the update only where sensitivity is valid (above threshold), otherwise set to 0.
                x = xp.where(sensitivity_image >= sens_threshold, update_term, 0.0)
            else:
                x = x * back_projection

            print(f"Iteration {i+1} done.")
            print(f"  [Debug] ybar: min={float(xp.min(ybar)):.4e}, max={float(xp.max(ybar)):.4e}, mean={float(xp.mean(ybar)):.4e}")
            print(f"  [Debug] ratio_denom: min={float(xp.min(ratio_denominator)):.4e}, max={float(xp.max(ratio_denominator)):.4e}, mean={float(xp.mean(ratio_denominator)):.4e}")
            print(f"  [Debug] back_proj: min={float(xp.min(back_projection)):.4e}, max={float(xp.max(back_projection)):.4e}, mean={float(xp.mean(back_projection)):.4e}")
            print(f"  [Debug] x (image): min={float(xp.min(x)):.4e}, max={float(xp.max(x)):.4e}, mean={float(xp.mean(x)):.4e}")

        # Save the final numpy array to HDF5
        reconstructed_image_np = parallelproj.to_numpy_array(x)
        sensitivity_np = parallelproj.to_numpy_array(sensitivity_image)
        
        with h5py.File(recon_output_path, 'w') as f:
            dset = f.create_dataset("image", data=reconstructed_image_np)
            dset.attrs['voxel_size'] = voxel_size
            dset.attrs['origin'] = image_origin
            dset.attrs['iterations'] = iterations
            dset.attrs['normalization'] = normalization
            
            # Save Sensitivity Map
            dset_sens = f.create_dataset("sensitivity", data=sensitivity_np)
            dset_sens.attrs['threshold'] = sens_threshold
            # Save LOR processing params if available in lors.npz
            if 'energy_cut' in lor_data:
                dset.attrs['energy_cut'] = lor_data['energy_cut']
            if 'energy_resolution' in lor_data:
                dset.attrs['energy_resolution'] = lor_data['energy_resolution']
            if 'position_resolution' in lor_data:
                # position_resolution is a dictionary, save as string or individual attrs
                # h5py doesn't support dicts directly as attrs easily without serialization
                import json
                dset.attrs['position_resolution'] = str(lor_data['position_resolution'])

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
    pm = get_project_manager_for_session()

    version_dir = pm._get_version_dir(version_id)
    run_dir = os.path.join(version_dir, "sim_runs", job_id)
    recon_h5_path = os.path.join(run_dir, "reconstruction.h5")
    recon_npy_path = os.path.join(run_dir, "reconstruction.npy")

    try:
        if os.path.exists(recon_h5_path):
            with h5py.File(recon_h5_path, 'r') as f:
                recon_img = f['image'][:]
        elif os.path.exists(recon_npy_path):
            recon_img = np.load(recon_npy_path)
        else:
            return "Reconstruction file not found", 404

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

@app.route('/api/reconstruction/projection/<version_id>/<job_id>/<axis>')
def get_recon_projection_route(version_id, job_id, axis):
    """
    Returns a MIP or Sum projection along the specified axis, optionally within a slice range.
    """
    pm = get_project_manager_for_session()
    version_dir = pm._get_version_dir(version_id)
    run_dir = os.path.join(version_dir, "sim_runs", job_id)
    recon_h5_path = os.path.join(run_dir, "reconstruction.h5")
    
    start = request.args.get('start', type=int)
    end = request.args.get('end', type=int)
    mode = request.args.get('mode', 'sum') # 'sum' or 'mip'

    try:
        if os.path.exists(recon_h5_path):
            with h5py.File(recon_h5_path, 'r') as f:
                recon_img = f['image'][:]
        else:
            return "Reconstruction file not found", 404

        # Determine slicing based on axis and optional range
        # Note: image is [x, y, z]
        
        sl = slice(None) # Default to full range
        if start is not None and end is not None:
            sl = slice(start, end)
        
        if axis == 'x':
            # Sum/Max along axis 0
            # Slicing affects the accumulation axis
            sub_vol = recon_img[sl, :, :]
            proj_axis = 0
        elif axis == 'y':
            # Sum/Max along axis 1
            sub_vol = recon_img[:, sl, :]
            proj_axis = 1
        else: # 'z'
            # Sum/Max along axis 2
            sub_vol = recon_img[:, :, sl]
            proj_axis = 2
            
        if mode == 'mip':
            projection = np.max(sub_vol, axis=proj_axis)
        else:
            projection = np.sum(sub_vol, axis=proj_axis)

        # Normalize and convert
        projection = np.rot90(projection)
        max_val = projection.max()
        if max_val > 0:
            projection = (projection / max_val) * 255.0
            
        img_pil = Image.fromarray(projection.astype(np.uint8), mode='L')
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
    pm = get_project_manager_for_session()
    version_dir = pm._get_version_dir(version_id)
    run_dir = os.path.join(version_dir, "sim_runs", job_id)
    lors_path = os.path.join(run_dir, "lors.npz")

    if os.path.exists(lors_path):
        try:
            # If the file exists, open it to count the LORs for a helpful message
            with np.load(lors_path) as lor_data:
                num_lors = len(lor_data['start_coords'])
                info = {"success": True, "exists": True, "num_lors": num_lors}
                if 'energy_cut' in lor_data:
                    info['energy_cut'] = float(lor_data['energy_cut'])
                if 'energy_resolution' in lor_data:
                    info['energy_resolution'] = float(lor_data['energy_resolution'])
                if 'position_resolution' in lor_data:
                    # It's saved as a 0-d array containing the dict if using save_z with dict
                    try:
                        pos_res = lor_data['position_resolution']
                        if pos_res.shape == ():
                            info['position_resolution'] = pos_res.item()
                        else:
                            info['position_resolution'] = pos_res.tolist()
                    except:
                        pass
            return jsonify(info)
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
def create_success_response(project_manager, message="Success",exclude_unchanged_tessellated=True):
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

def create_shallow_response(project_manager, message, scene_patch=None, project_state_patch=None, full_scene=None):
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
    pm = get_project_manager_for_session()
    pm.begin_transaction()
    return jsonify({"success": True, "message": "Transaction started."})

@app.route('/api/end_transaction', methods=['POST'])
def end_transaction_route():
    pm = get_project_manager_for_session()

    data = request.get_json() or {}
    description = data.get('description', 'User action')
    pm.end_transaction(description)
    # The final state is captured on the backend, but the frontend needs
    # the updated history status (canUndo/canRedo).
    # We will return the full response so the UI updates correctly.
    return create_success_response(pm, "Transaction ended.") # Use your full response helper

@app.route('/api/undo', methods=['POST'])
def undo_route():
    pm = get_project_manager_for_session()
    success, message = pm.undo()
    if success:
        return create_success_response(pm, message)
    else:
        return jsonify({"success": False, "error": message}), 400

@app.route('/api/redo', methods=['POST'])
def redo_route():
    pm = get_project_manager_for_session()
    success, message = pm.redo()
    if success:
        return create_success_response(pm, message)
    else:
        return jsonify({"success": False, "error": message}), 400

@app.route('/rename_project', methods=['POST'])
def rename_project_route():
    pm = get_project_manager_for_session()

    data = request.get_json()
    project_name = data.get('project_name')

    try:
        pm.project_name = project_name
        return jsonify({"success": True, "message": f"Project set to {project_name}"})
    except Exception as e:
        return jsonify({"success": False, "error": f"Failed to save version: {e}"}), 500
    
@app.route('/autosave', methods=['POST'])
def autosave_project_api():
    pm = get_project_manager_for_session()

    # No data is needed in the request body. The project manager knows the active project.
    success, message = pm.auto_save_project()
    if success:
        return jsonify({"success": True, "message": message})
    else:
        # It's not an error if there was nothing to save, so return success.
        return jsonify({"success": True, "message": "No changes to autosave."})

@app.route('/api/save_version', methods=['POST'])
def save_version_route():
    pm = get_project_manager_for_session()

    data = request.get_json() or {}
    description = data.get('description', 'User Save')
    try:
        version_name, message = pm.save_project_version(description)
        return jsonify({"success": True, "message": f"Version '{version_name}' saved."})
    except Exception as e:
        return jsonify({"success": False, "error": f"Failed to save version: {e}"}), 500

# Helper to get the path for a specific version
def get_version_dir(project_name, version_id):
    return os.path.join(PROJECTS_BASE_DIR, project_name, "versions", version_id)

@app.route('/api/get_project_history', methods=['GET'])
def get_project_history_route():
    pm = get_project_manager_for_session()

    project_name = request.args.get('project_name')
    if not project_name:
        return jsonify({"success": False, "error": "Project name is required."}), 400
    
    versions_path = os.path.join(pm.projects_dir, project_name, "versions")
    if not os.path.isdir(versions_path):
        return jsonify({"success": True, "history": []})

    try:

        # List directories instead of files, sorting reverse-chronologically
        version_dirs = [d for d in os.listdir(versions_path) if os.path.isdir(os.path.join(versions_path, d))]
        
        history = []
        autosave_data = None

        # Find and process the autosave entry first if it exists
        if AUTOSAVE_VERSION_ID in version_dirs:
            version_dirs.remove(AUTOSAVE_VERSION_ID) # Remove it from the main list
            autosave_path = os.path.join(versions_path, AUTOSAVE_VERSION_ID, "version.json")
            if os.path.exists(autosave_path):
                # Get the modification time of the autosave file for sorting
                mtime = os.path.getmtime(autosave_path)
                autosave_data = {
                    "id": AUTOSAVE_VERSION_ID,
                    "is_autosave": True, # Flag for the frontend
                    "timestamp": datetime.fromtimestamp(mtime).strftime("%Y-%m-%dT%H-%M-%S"),
                    "description": "Latest Autosave",
                    "runs": [] # Autosaves don't have simulation runs
                }

        # Sort the remaining normal versions reverse-chronologically
        version_dirs.sort(reverse=True)

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

        # Prepend the autosave data to the history list so it appears at the top
        if autosave_data:
            history.insert(0, autosave_data)
            
        return jsonify({"success": True, "history": history})
    
    except Exception as e:
        return jsonify({"success": False, "error": f"Failed to read project history: {str(e)}"}), 500

@app.route('/api/load_version', methods=['POST'])
def load_version_route():
    pm = get_project_manager_for_session()

    data = request.get_json()
    version_id = data.get('version_id') # This is the filename
    
    if not version_id:
        return jsonify({"success": False, "error": "Project name and version ID are required."}), 400

    try:
        success, message = pm.load_project_version(version_id)
        if success:
            return create_success_response(pm, message, exclude_unchanged_tessellated=False)
        else:
            return jsonify({"success": False, "error": message}), 500
    except Exception as e:
        return jsonify({"success": False, "error": f"Failed to load version: {e}"}), 500

@app.route('/api/get_project_list', methods=['GET'])
def get_project_list_route():
    """
    Scans the correct project directory (session-specific or local)
    and returns a list of project names for the current user.
    """
    # 1. Get the ProjectManager for the current session.
    pm = get_project_manager_for_session()
    
    # 2. Use the manager's projects_dir, which is already correctly set
    #    to either 'projects/' (local) or 'projects/<session_id>' (deployed).
    user_projects_dir = pm.projects_dir

    if not os.path.isdir(user_projects_dir):
        return jsonify({"success": True, "projects": []})

    try:
        # 3. List only the directories within that specific path.
        project_names = [d for d in os.listdir(user_projects_dir)
                         if os.path.isdir(os.path.join(user_projects_dir, d))]
        return jsonify({"success": True, "projects": sorted(project_names)})
    except Exception as e:
        return jsonify({"success": False, "error": f"Failed to read project directory: {e}"}), 500
    
# Function to construct full AI prompt
def construct_full_ai_prompt(project_manager, user_prompt):

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
    pm = get_project_manager_for_session()
    pm.create_empty_project()

    return create_success_response(pm, "New project created.",exclude_unchanged_tessellated=False)

@app.route('/import_gdml_part', methods=['POST'])
def import_gdml_part_route():
    pm = get_project_manager_for_session()

    if 'partFile' not in request.files:
        return jsonify({"error": "No file part"}), 400
    file = request.files['partFile']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400
    
    try:
        gdml_content_str = file.read().decode('utf-8')
        # Parse into a temporary state object
        temp_state = pm.gdml_parser.parse_gdml_string(gdml_content_str)
        # Call the new merge method
        success, error_msg = pm.merge_from_state(temp_state)
        if success:
            return create_success_response(pm, "GDML part(s) imported successfully.")
        else:
            return jsonify({"success": False, "error": error_msg or "Failed to merge GDML part."}), 500
    except Exception as e:
        print(f"An unexpected error occurred during GDML part import: {e}")
        traceback.print_exc()
        return jsonify({"error": "An unexpected error occurred on the server while importing GDML."}), 500


@app.route('/import_json_part', methods=['POST'])
def import_json_part_route():
    pm = get_project_manager_for_session()

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
        success, error_msg = pm.merge_from_state(temp_state)
        if success:
            return create_success_response(pm, "JSON part(s) imported successfully.")
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
    pm = get_project_manager_for_session()

    if 'gdmlFile' not in request.files:
        return jsonify({"error": "No file part"}), 400
    file = request.files['gdmlFile']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400
    if file:
        gdml_content_str = file.read().decode('utf-8')
        try:
            pm.load_gdml_from_string(gdml_content_str)
            return create_success_response(pm, "GDML file processed successfully.",exclude_unchanged_tessellated=False)
        except Exception as e:
            import traceback
            traceback.print_exc()
            return jsonify({"error": str(e)}), 500

@app.route('/load_project_json', methods=['POST'])
def load_project_json_route():
    pm = get_project_manager_for_session()

    if 'projectFile' not in request.files:
        return jsonify({"error": "No project file part"}), 400
    file = request.files['projectFile']
    if file:
        try:
            project_json_string = file.read().decode('utf-8')
            pm.load_project_from_json_string(project_json_string)
            return create_success_response(pm, "Project loaded successfully.",exclude_unchanged_tessellated=False)
        except json.JSONDecodeError:
            return jsonify({"error": "Invalid JSON file format"}), 400
        except Exception as e:
            import traceback
            traceback.print_exc()
            return jsonify({"error": f"Failed to load project data: {str(e)}"}), 500

@app.route('/update_object_transform', methods=['POST'])
def update_object_transform_route():
    pm = get_project_manager_for_session()

    data = request.get_json()
    object_id = data.get('id')
    new_position = data.get('position')
    new_rotation = data.get('rotation')

    if not object_id:
        return jsonify({"error": "Object ID missing"}), 400

    success, error_msg = pm.update_physical_volume_transform(object_id, new_position, new_rotation)

    if success:
        return create_success_response(pm, f"Object {object_id} transform updated.")
    else:
        return jsonify({"success": False, "error": error_msg or "Could not update transform."}), 404
    
@app.route('/update_property', methods=['POST'])
def update_property_route():
    pm = get_project_manager_for_session()

    data = request.get_json()
    obj_type = data.get('object_type')
    obj_id = data.get('object_id')
    prop_path = data.get('property_path')
    new_value = data.get('new_value')

    if not all([obj_type, obj_id, prop_path]):
        return jsonify({"error": "Missing data for property update"}), 400

    success = pm.update_object_property(obj_type, obj_id, prop_path, new_value)
    if success:
        return create_success_response(pm, "Property updated.")
    else:
        return jsonify({"success": False, "error": "Failed to update property"}), 500

@app.route('/add_material', methods=['POST'])
def add_material_route():
    pm = get_project_manager_for_session()

    data = request.get_json()
    name_suggestion = data.get('name')
    params = data.get('params')

    if not name_suggestion or params is None:
        return jsonify({"success": False, "error": "Missing name or parameters for material."}), 400

    new_obj, error_msg = pm.add_material(name_suggestion, params)

    if new_obj:
        return create_success_response(pm, "Material created.")
    else:
        return jsonify({"success": False, "error": error_msg}), 500

@app.route('/update_material', methods=['POST'])
def update_material_route():
    pm = get_project_manager_for_session()

    data = request.get_json()
    mat_name = data.get('id')
    new_params = data.get('params')
    
    success, error_msg = pm.update_material(mat_name, new_params)
    if success:
        return create_success_response(pm, f"Material '{mat_name}' updated.")
    else:
        return jsonify({"success": False, "error": error_msg}), 500

@app.route('/add_element', methods=['POST'])
def add_element_route():
    pm = get_project_manager_for_session()

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
    
    new_obj, error_msg = pm.add_element(name_suggestion, params)
    
    if new_obj:
        return create_success_response(pm, "Element created.")
    else:
        return jsonify({"success": False, "error": error_msg}), 500

@app.route('/update_element', methods=['POST'])
def update_element_route():
    pm = get_project_manager_for_session()
    
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

    success, error_msg = pm.update_element(element_name, new_params)
    
    if success:
        return create_success_response(pm, f"Element '{element_name}' updated.")
    else:
        return jsonify({"success": False, "error": error_msg}), 500

@app.route('/add_isotope', methods=['POST'])
def add_isotope_route():
    pm = get_project_manager_for_session()

    data = request.get_json(); name = data.get('name'); params = data
    if not name: return jsonify({"success": False, "error": "Missing name for isotope."}), 400
    new_obj, err = pm.add_isotope(name, params)
    if new_obj: return create_success_response(pm, "Isotope created.")
    return jsonify({"success": False, "error": err}), 500

@app.route('/update_isotope', methods=['POST'])
def update_isotope_route():
    pm = get_project_manager_for_session()

    data = request.get_json(); name = data.get('id'); params = data
    if not name: return jsonify({"success": False, "error": "Missing ID for isotope update."}), 400
    ok, err = pm.update_isotope(name, params)
    if ok: return create_success_response(pm, f"Isotope '{name}' updated.")
    return jsonify({"success": False, "error": err}), 500

@app.route('/add_define', methods=['POST'])
def add_define_route():
    pm = get_project_manager_for_session()

    data = request.get_json()
    name = data.get('name')
    define_type = data.get('type')
    value = data.get('value')
    unit = data.get('unit')
    category = data.get('category')
    
    new_obj, error_msg = pm.add_define(name, define_type, value, unit, category)
    if new_obj:
        return create_success_response(pm, "Define created.")
    else:
        return jsonify({"success": False, "error": error_msg}), 500

@app.route('/update_define', methods=['POST'])
def update_define_route():
    pm = get_project_manager_for_session()

    data = request.get_json()
    define_name = data.get('id')
    value = data.get('value')
    unit = data.get('unit')
    category = data.get('category')

    success, error_msg = pm.update_define(define_name, value, unit, category)

    if success:
        return create_success_response(pm, f"Define '{define_name}' updated.")
    else:
        return jsonify({"success": False, "error": error_msg}), 500

@app.route('/add_solid_and_place', methods=['POST'])
def add_solid_and_place_route():
    pm = get_project_manager_for_session()

    data = request.get_json()
    solid_params = data.get('solid_params') # {name, type, params}
    lv_params = data.get('lv_params')       # {name?, material_ref} or None
    pv_params = data.get('pv_params')       # {name?, parent_lv_name} or None
    print(solid_params)

    if not solid_params:
        return jsonify({"success": False, "error": "Solid parameters are required."}), 400

    success, error_msg = pm.add_solid_and_place(solid_params, lv_params, pv_params)

    if success:
        return create_success_response(pm, "Object(s) created successfully.")
    else:
        return jsonify({"success": False, "error": error_msg}), 500

@app.route('/add_primitive_solid', methods=['POST'])
def add_primitive_solid_route():
    pm = get_project_manager_for_session()

    data = request.get_json()
    name_suggestion = data.get('name')
    solid_type = data.get('type')
    params = data.get('params')

    if not all([name_suggestion, solid_type, params]):
        return jsonify({"success": False, "error": "Missing data for primitive solid"}), 400
        
    new_obj, error_msg = pm.add_solid(name_suggestion, solid_type, params)
    
    if new_obj:
        return create_success_response(pm, "Primitive solid created.")
    else:
        return jsonify({"success": False, "error": error_msg}), 500

@app.route('/update_solid', methods=['POST'])
def update_solid_route():
    pm = get_project_manager_for_session()

    data = request.get_json()
    solid_id = data.get('id')
    new_raw_params = data.get('params')
    
    if not solid_id or new_raw_params is None:
        return jsonify({"success": False, "error": "Missing solid ID or new parameters."}), 400

    success, error_msg = pm.update_solid(solid_id, new_raw_params)

    if success:
        return create_success_response(pm, f"Solid '{solid_id}' updated successfully.")
    else:
        return jsonify({"success": False, "error": error_msg or "Failed to update solid."}), 500

@app.route('/add_boolean_solid', methods=['POST'])
def add_boolean_solid_route():
    pm = get_project_manager_for_session()

    data = request.get_json()
    name_suggestion = data.get('name')
    recipe = data.get('recipe')
    
    success, error_msg = pm.add_boolean_solid(name_suggestion, recipe)

    if success:
        return create_success_response(pm, "Boolean solid created.")
    else:
        return jsonify({"success": False, "error": error_msg}), 500

@app.route('/update_boolean_solid', methods=['POST'])
def update_boolean_solid_route():
    pm = get_project_manager_for_session()

    data = request.get_json()
    solid_name = data.get('id') # The name of the solid to update
    recipe = data.get('recipe')
    
    success, error_msg = pm.update_boolean_solid(solid_name, recipe)

    if success:
        return create_success_response(pm, f"Boolean solid '{solid_name}' updated.")
    else:
        return jsonify({"success": False, "error": error_msg}), 500

@app.route('/add_logical_volume', methods=['POST'])
def add_logical_volume_route():
    pm = get_project_manager_for_session()

    data = request.get_json()
    name = data.get('name')
    solid_ref = data.get('solid_ref')
    material_ref = data.get('material_ref')
    vis_attributes = data.get('vis_attributes')
    is_sensitive = data.get('is_sensitive', False)
    content_type = data.get('content_type', 'physvol')
    content = data.get('content', [])
    
    new_lv ,error_msg = pm.add_logical_volume(
        name, solid_ref, material_ref, vis_attributes, is_sensitive,
        content_type, content
    )
    
    if new_lv:
        return create_success_response(pm, "Logical Volume created.")
    else:
        return jsonify({"success": False, "error": error_msg}), 500

@app.route('/update_logical_volume', methods=['POST'])
def update_logical_volume_route():
    pm = get_project_manager_for_session()

    data = request.get_json()
    lv_name = data.get('id')
    solid_ref = data.get('solid_ref')
    material_ref = data.get('material_ref')
    vis_attributes = data.get('vis_attributes')
    is_sensitive = data.get('is_sensitive')
    content_type = data.get('content_type')
    content = data.get('content')

    success ,error_msg = pm.update_logical_volume(
        lv_name, solid_ref, material_ref, vis_attributes, is_sensitive,
        content_type, content
    )

    if success:
        return create_success_response(pm, f"Logical Volume '{lv_name}' updated.")
    else:
        return jsonify({"success": False, "error": error_msg}), 500

@app.route('/add_physical_volume', methods=['POST'])
def add_physical_volume_route():
    pm = get_project_manager_for_session()

    data = request.get_json()
    parent_lv_name = data.get('parent_lv_name')
    name = data.get('name')
    volume_ref = data.get('volume_ref')
    position = data.get('position')
    rotation = data.get('rotation')
    scale = data.get('scale')
    
    new_pv, error_msg = pm.add_physical_volume(parent_lv_name, name, volume_ref, position, rotation, scale)
    
    if new_pv:
        return create_success_response(pm, "Physical Volume placed.")
    else:
        return jsonify({"success": False, "error": error_msg}), 500

@app.route('/update_physical_volume', methods=['POST'])
def update_physical_volume_route():
    pm = get_project_manager_for_session()

    data = request.get_json()
    pv_id = data.get('id')
    name = data.get('name')
    position = data.get('position')
    rotation = data.get('rotation')
    scale = data.get('scale')

    success, error_msg = pm.update_physical_volume(pv_id, name, position, rotation, scale)

    if success:
        return create_success_response(pm, f"Physical Volume '{pv_id}' updated.")
    else:
        return jsonify({"success": False, "error": error_msg}), 500
    
@app.route('/api/update_physical_volume_batch', methods=['POST'])
def update_physical_volume_batch_route():
    pm = get_project_manager_for_session()

    data = request.get_json()
    updates_list = data.get('updates')
    if not isinstance(updates_list, list):
        return jsonify({"success": False, "error": "Invalid request: 'updates' must be a list."}), 400

    # The project manager will handle the transaction and recalculation internally
    success, project_state_patch = pm.update_physical_volume_batch(updates_list)

    # Compute the full scene again.
    scene_update = pm.get_threejs_description()

    if success:
        # After a successful batch update, send back the complete new state
        return create_shallow_response(pm, f"Transformed {len(updates_list)} object(s).", 
                                       project_state_patch=project_state_patch, 
                                       full_scene=scene_update)
    else:
        # If it fails, send back an error and the (potentially partially modified) state
        # A more advanced implementation might revert the changes on failure.
        return jsonify({"success": False, "error": "Error creating response after physical volume batch update"}), 500

@app.route('/api/delete_objects_batch', methods=['POST'])
def delete_objects_batch_route():
    pm = get_project_manager_for_session()

    data = request.get_json()
    objects_to_delete = data.get('objects')

    if not isinstance(objects_to_delete, list):
        return jsonify({"success": False, "error": "Invalid request: 'objects' must be a list."}), 400

    # First, pre-filter for non-deletable items like assembly members
    assembly_member_ids = set()
    for asm in pm.current_geometry_state.assemblies.values():
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
    deleted, patch_or_error_msg = pm.delete_objects_batch(filtered_deletions)
    
    if deleted:
        return create_shallow_response(
            pm,
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
    pm = get_project_manager_for_session()

    state = pm.get_full_project_state_dict(exclude_unchanged_tessellated=False)
    project_name = pm.project_name

    # Check if the project is empty (no world volume defined)
    if not state or not state.get('world_volume_ref'):
        print("No active project found, creating a new default world.")
        
        # Call the same logic as the /new_project route
        pm.create_empty_project()
        
        # Now get the state and scene again from the newly created project
        state = pm.get_full_project_state_dict(exclude_unchanged_tessellated=False)
        scene = pm.get_threejs_description()
    else:
        # Project already exists, just get the scene
        scene = pm.get_threejs_description()

    # Always return a valid state
    return jsonify({
        "project_state": state,
        "scene_update": scene,
        "project_name": project_name
    })

@app.route('/get_object_details', methods=['GET'])
def get_object_details_route():
    pm = get_project_manager_for_session()

    obj_type = request.args.get('type')
    obj_id = request.args.get('id')
    if not obj_type or not obj_id:
        return jsonify({"error": "Type or ID missing"}), 400
    
    if obj_type == "particle_source":
        # For sources, the 'id' from the frontend is the unique ID
        details = None
        for source in pm.current_geometry_state.sources.values():
            if source.id == obj_id:
                details = source.to_dict()
                break
    else:
        details = pm.get_object_details(obj_type, obj_id)

    if details:
        return jsonify(details)
    
    error_key = "ID" if obj_type in ["physical_volume", "particle_source"] else "name"
    return jsonify({"error": f"{obj_type} with {error_key} '{obj_id}' not found"}), 404

@app.route('/save_project_json', methods=['GET'])
def save_project_json_route():
    pm = get_project_manager_for_session()

    project_json_string = pm.save_project_to_json_string()
    return Response(
        project_json_string,
        mimetype="application/json",
        headers={"Content-Disposition": "attachment;filename=project.json"}
    )

@app.route('/export_gdml', methods=['GET'])
def export_gdml_route():
    pm = get_project_manager_for_session()

    gdml_string = pm.export_to_gdml_string()
    return Response(
        gdml_string,
        mimetype="application/xml",
        headers={"Content-Disposition": "attachment;filename=exported_geometry.gdml"}
    )

@app.route('/get_defines_by_type', methods=['GET'])
def get_defines_by_type_route():
    """Returns a list of define names for a given type (position, rotation, etc.)."""
    pm = get_project_manager_for_session()

    define_type = request.args.get('type')
    if not define_type:
        return jsonify({"error": "Define type parameter is missing"}), 400

    if not pm.current_geometry_state:
        return jsonify([]) # Return empty list if no project

    # Filter defines based on the requested type
    filtered_defines = {
        name: define.to_dict()
        for name, define in pm.current_geometry_state.defines.items()
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
    gemini_client = get_gemini_client_for_session()
    if gemini_client:
        try:
            gemini_models = []
            # Use the initialized client to list models
            for model in gemini_client.models.list():
                if 'generateContent' in model.supported_actions:
                    # Filter for certain Gemini models only
                    if(model.name == "models/gemini-3-flash-preview" or model.name == "models/gemini-2.5-flash" or model.name == "models/gemini-2.5-pro"):
                        gemini_models.append(model.name)
            response_data["models"]["gemini"] = gemini_models
        except Exception as e:
            print(f"Error fetching Gemini models: {e}")
            response_data["error_gemini"] = str(e)

    return jsonify(response_data)

@app.route('/ai_process_prompt', methods=['POST'])
def ai_process_prompt_route():
    pm = get_project_manager_for_session()

    data = request.get_json()
    user_prompt = data.get('prompt')
    model_name = data.get('model')

    # Ensure we have a prompt and model name
    if not all([user_prompt, model_name]):
        return jsonify({"success": False, "error": "Prompt or model name missing."}), 400

    try:
        # Step 1: Construct the full prompt
        full_prompt = construct_full_ai_prompt(pm, user_prompt)
        ai_json_string = ""

        # --- Routing logic ---
        if model_name.startswith("models/"): # Gemini models

            # Get the Gemini client for the current session
            gemini_client = get_gemini_client_for_session()
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

            # Process the response
            ollama_response = ollama.generate(model=model_name, prompt=full_prompt)
            ai_json_string = ollama_response['response'].strip()
            print(f"OLLAMA RESPONSE ({model_name}):\n")
            print(ai_json_string)

        # Step 3: Parse and process the response using a new ProjectManager method
        ai_data = json.loads(ai_json_string)
        success, error_msg = pm.process_ai_response(ai_data)
        
        if success:
            return create_success_response(pm, "AI command processed successfully.")
        else:
            return jsonify({"success": False, "error": error_msg or "Failed to process AI response."}), 500

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
    pm = get_project_manager_for_session()

    data = request.get_json()
    user_prompt = data.get('prompt')
    if not user_prompt:
        return jsonify({"success": False, "error": "No prompt provided."}), 400

    try:
        # Construct the prompt
        full_prompt = construct_full_ai_prompt(pm, user_prompt)

        # Return the constructed prompt as plain text
        return Response(full_prompt, mimetype="text/markdown")

    except Exception as e:
        traceback.print_exc()
        return jsonify({"success": False, "error": f"An unexpected error occurred: {e}"}), 500

@app.route('/import_ai_json', methods=['POST'])
def import_ai_json_route():
    pm = get_project_manager_for_session()

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
        success, error_msg = pm.process_ai_response(ai_data)
        
        if success:
            return create_success_response(pm, "AI-generated JSON imported successfully.")
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
    # Read the key directly from the user's session
    api_key = session.get("gemini_api_key", "")
    return jsonify({"api_key": api_key})

# --- Route to set a new API key ---
@app.route('/api/set_gemini_key', methods=['POST'])
def set_gemini_key():
    data = request.get_json()
    new_key = data.get('api_key', '')

    # Store the new key in the user's session. Flask handles the secure cookie.
    session['gemini_api_key'] = new_key
    
    # Attempt to configure the client for this session to validate the key.
    client_instance = get_gemini_client_for_session()

    if client_instance:
        return jsonify({"success": True, "message": "API Key updated and client configured."})
    elif not new_key:
        # This handles the case where the user intentionally clears the key.
        return jsonify({"success": True, "message": "API Key cleared."})
    else:
        # The key was set, but the client failed to initialize (likely an invalid key).
        return jsonify({
            "success": False,
            "error": "API Key was saved to your session, but the Gemini client failed to initialize. The key might be invalid."
        })

    # try:
    #     # Find the .env file path
    #     dotenv_path = find_dotenv()
    #     if not dotenv_path:
    #         # If .env doesn't exist, create it in the current directory
    #         dotenv_path = os.path.join(os.getcwd(), '.env')
    #         with open(dotenv_path, 'w') as f:
    #             pass # Create an empty file
        
    #     # Write the key to the .env file
    #     set_key(dotenv_path, "GEMINI_API_KEY", new_key)
        
    #     # Reload environment variables and re-initialize the client
    #     load_dotenv(override=True)
    #     success = configure_gemini_client()

    #     if success:
    #         return jsonify({"success": True, "message": "API Key updated successfully."})
    #     else:
    #         return jsonify({"success": False, "error": "API Key was saved, but failed to configure the client. Key might be invalid."})

    # except Exception as e:
    #     traceback.print_exc()
    #     return jsonify({"success": False, "error": f"Failed to save API key: {e}"}), 500

@app.route('/import_step_with_options', methods=['POST'])
def import_step_with_options_route():
    pm = get_project_manager_for_session()

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
        success, error_msg = pm.import_step_with_options(file, options)
        if success:
            return create_success_response(pm, "STEP file imported successfully.")
        else:
            return jsonify({"success": False, "error": error_msg or "Failed to process STEP file."}), 500
            
    except Exception as e:
        print(f"An unexpected error occurred during STEP import: {e}")
        traceback.print_exc()
        return jsonify({"error": "An unexpected error occurred on the server while importing the STEP file."}), 500

@app.route('/add_assembly', methods=['POST'])
def add_assembly_route():
    pm = get_project_manager_for_session()

    data = request.get_json()
    name = data.get('name')
    placements = data.get('placements', [])
    new_asm, error_msg = pm.add_assembly(name, placements)
    if new_asm:
        return create_success_response(pm, "Assembly created.")
    else:
        return jsonify({"success": False, "error": error_msg}), 500

@app.route('/update_assembly', methods=['POST'])
def update_assembly_route():
    pm = get_project_manager_for_session()

    data = request.get_json()
    asm_name = data.get('id')
    placements = data.get('placements', [])
    success, error_msg = pm.update_assembly(asm_name, placements)
    if success:
        return create_success_response(pm, f"Assembly '{asm_name}' updated.")
    else:
        return jsonify({"success": False, "error": error_msg}), 500

@app.route('/create_group', methods=['POST'])
def create_group_route():
    pm = get_project_manager_for_session()

    data = request.get_json()
    group_type = data.get('group_type')
    group_name = data.get('group_name')

    if not all([group_type, group_name]):
        return jsonify({"success": False, "error": "Missing group type or name."}), 400
    
    success, error_msg = pm.create_group(group_type, group_name)
    if success:
        return create_success_response(pm, f"Group '{group_name}' created.")
    else:
        return jsonify({"success": False, "error": error_msg}), 500

@app.route('/rename_group', methods=['POST'])
def rename_group_route():
    pm = get_project_manager_for_session()

    data = request.get_json()
    group_type = data.get('group_type')
    old_name = data.get('old_name')
    new_name = data.get('new_name')

    if not all([group_type, old_name, new_name]):
        return jsonify({"success": False, "error": "Missing data for group rename."}), 400
        
    success, error_msg = pm.rename_group(group_type, old_name, new_name)
    if success:
        return create_success_response(pm, "Group renamed.")
    else:
        return jsonify({"success": False, "error": error_msg}), 500

@app.route('/delete_group', methods=['POST'])
def delete_group_route():
    pm = get_project_manager_for_session()

    data = request.get_json()
    group_type = data.get('group_type')
    group_name = data.get('group_name')
    
    if not all([group_type, group_name]):
        return jsonify({"success": False, "error": "Missing data for group deletion."}), 400

    success, error_msg = pm.delete_group(group_type, group_name)
    if success:
        return create_success_response(pm, "Group deleted.")
    else:
        return jsonify({"success": False, "error": error_msg}), 500

@app.route('/move_items_to_group', methods=['POST'])
def move_items_to_group_route():
    pm = get_project_manager_for_session()

    data = request.get_json()
    group_type = data.get('group_type')
    item_ids = data.get('item_ids')
    target_group_name = data.get('target_group_name') # Can be null to ungroup

    if not all([group_type, item_ids]):
        return jsonify({"success": False, "error": "Missing group type or item IDs."}), 400
        
    success, error_msg = pm.move_items_to_group(group_type, item_ids, target_group_name)
    if success:
        return create_success_response(pm, "Items moved successfully.")
    else:
        return jsonify({"success": False, "error": error_msg}), 500

@app.route('/api/evaluate_expression', methods=['POST'])
def evaluate_expression_route():
    pm = get_project_manager_for_session()

    data = request.get_json()
    expression = data.get('expression')
    if expression is None: # Check for None, as "" is a valid (empty) expression
        return jsonify({"success": False, "error": "Missing expression."}), 400

    # Evaluate the expression (the current project state has been set up in
    # the expression evaluator in ProjectManager's recalculate_geometry_state).
    success, result = pm.expression_evaluator.evaluate(expression)

    if success:
        return jsonify({"success": True, "result": result})
    else:
        # The result is the error message string
        return jsonify({"success": False, "error": result}), 400

@app.route('/create_assembly_from_pvs', methods=['POST'])
def create_assembly_from_pvs_route():
    pm = get_project_manager_for_session()
    
    data = request.get_json()
    pv_ids = data.get('pv_ids')
    assembly_name = data.get('assembly_name')
    parent_lv_name = data.get('parent_lv_name')

    if not all([pv_ids, assembly_name, parent_lv_name]):
        return jsonify({"success": False, "error": "Missing data for assembly creation."}), 400

    new_pv, error_msg = pm.create_assembly_from_pvs(
        pv_ids, assembly_name, parent_lv_name
    )
    
    if error_msg:
        return jsonify({"success": False, "error": error_msg}), 500
    else:
        return create_success_response(pm, f"Assembly '{assembly_name}' created successfully.")

@app.route('/move_pv_to_assembly', methods=['POST'])
def move_pv_to_assembly_route():
    pm = get_project_manager_for_session()

    data = request.get_json()
    pv_ids = data.get('pv_ids')
    target_assembly_name = data.get('target_assembly_name')
    if not all([pv_ids, target_assembly_name]):
        return jsonify({"success": False, "error": "Missing PV IDs or target assembly name."}), 400

    success, error_msg = pm.move_pv_to_assembly(pv_ids, target_assembly_name)
    if success:
        return create_success_response(pm, "PV moved to assembly.")
    else:
        return jsonify({"success": False, "error": error_msg}), 500

@app.route('/move_pv_to_lv', methods=['POST'])
def move_pv_to_lv_route():
    pm = get_project_manager_for_session()

    data = request.get_json()
    pv_ids = data.get('pv_ids')
    target_lv_name = data.get('target_lv_name')
    if not all([pv_ids, target_lv_name]):
        return jsonify({"success": False, "error": "Missing PV IDs or target LV name."}), 400

    success, error_msg = pm.move_pv_to_lv(pv_ids, target_lv_name)
    if success:
        return create_success_response(pm, "PV moved to logical volume.")
    else:
        return jsonify({"success": False, "error": error_msg}), 500

@app.route('/add_optical_surface', methods=['POST'])
def add_optical_surface_route():
    pm = get_project_manager_for_session()

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
    
    new_obj, error_msg = pm.add_optical_surface(name_suggestion, params)
    
    if new_obj:
        return create_success_response(pm, "Optical Surface created.")
    else:
        return jsonify({"success": False, "error": error_msg}), 500

@app.route('/update_optical_surface', methods=['POST'])
def update_optical_surface_route():
    pm = get_project_manager_for_session()

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

    success, error_msg = pm.update_optical_surface(surface_name, new_params)
    
    if success:
        return create_success_response(pm, f"Optical Surface '{surface_name}' updated.")
    else:
        return jsonify({"success": False, "error": error_msg}), 500

@app.route('/add_skin_surface', methods=['POST'])
def add_skin_surface_route():
    pm = get_project_manager_for_session()

    data = request.get_json()
    name_suggestion = data.get('name')
    volume_ref = data.get('volume_ref')
    surface_ref = data.get('surfaceproperty_ref')
    
    if not all([name_suggestion, volume_ref, surface_ref]):
        return jsonify({"success": False, "error": "Missing name, volume reference, or surface reference."}), 400
    
    new_obj, error_msg = pm.add_skin_surface(name_suggestion, volume_ref, surface_ref)
    
    if new_obj:
        return create_success_response(pm, "Skin Surface created.")
    else:
        return jsonify({"success": False, "error": error_msg}), 500

@app.route('/update_skin_surface', methods=['POST'])
def update_skin_surface_route():
    pm = get_project_manager_for_session()

    data = request.get_json()
    surface_name = data.get('id')
    volume_ref = data.get('volume_ref')
    surface_ref = data.get('surfaceproperty_ref')

    if not all([surface_name, volume_ref, surface_ref]):
        return jsonify({"success": False, "error": "Missing name, volume reference, or surface reference for update."}), 400

    success, error_msg = pm.update_skin_surface(surface_name, volume_ref, surface_ref)
    
    if success:
        return create_success_response(pm, f"Skin Surface '{surface_name}' updated.")
    else:
        return jsonify({"success": False, "error": error_msg}), 500

@app.route('/add_border_surface', methods=['POST'])
def add_border_surface_route():
    pm = get_project_manager_for_session()

    data = request.get_json()
    name_suggestion = data.get('name')
    pv1_ref = data.get('physvol1_ref')
    pv2_ref = data.get('physvol2_ref')
    surface_ref = data.get('surfaceproperty_ref')
    print(f"Surface ref is {surface_ref}")
    
    if not all([name_suggestion, pv1_ref, pv2_ref, surface_ref]):
        return jsonify({"success": False, "error": "Missing name or reference for border surface."}), 400
    
    new_obj, error_msg = pm.add_border_surface(name_suggestion, pv1_ref, pv2_ref, surface_ref)
    
    if new_obj:
        return create_success_response(pm, "Border Surface created.")
    else:
        return jsonify({"success": False, "error": error_msg}), 500

@app.route('/update_border_surface', methods=['POST'])
def update_border_surface_route():
    pm = get_project_manager_for_session()

    data = request.get_json()
    surface_name = data.get('id')
    pv1_ref = data.get('physvol1_ref')
    pv2_ref = data.get('physvol2_ref')
    surface_ref = data.get('surfaceproperty_ref')

    if not all([surface_name, pv1_ref, pv2_ref, surface_ref]):
        return jsonify({"success": False, "error": "Missing data for border surface update."}), 400

    success, error_msg = pm.update_border_surface(surface_name, pv1_ref, pv2_ref, surface_ref)
    
    if success:
        return create_success_response(pm, f"Border Surface '{surface_name}' updated.")
    else:
        return jsonify({"success": False, "error": error_msg}), 500

@app.route('/api/create_detector_ring', methods=['POST'])
def create_detector_ring_route():
    pm = get_project_manager_for_session()

    data = request.get_json()
    # Check for required fields
    required_fields = ['parent_lv_name', 'lv_to_place', 'ring_name', 'num_detectors',
                       'radius', 'center', 'orientation', 'point_to_center', 'inward_axis']
    if not all(k in data for k in required_fields):
        return jsonify({"success": False, "error": "Missing parameters for ring creation."}), 400

    # Pass all arguments, including optional ones with defaults
    new_pv_assembly, error_msg = pm.create_detector_ring(
        parent_lv_name=data['parent_lv_name'],
        lv_to_place_ref=data['lv_to_place'],
        ring_name=data['ring_name'],
        num_detectors=data['num_detectors'],
        radius=data['radius'],
        center=data['center'],
        orientation=data['orientation'],
        point_to_center=data['point_to_center'],
        inward_axis=data['inward_axis'],
        num_rings=data.get('num_rings', 1),         
        ring_spacing=data.get('ring_spacing', 0.0)
    )

    if error_msg:
        return jsonify({"success": False, "error": error_msg}), 500
    else:
        return create_success_response(pm, f"Detector ring '{data['ring_name']}' created successfully.")

# -------------------------------------------------------------------------------
# Session timeout management
SESSION_TIMEOUT_SECONDS = 300  # 5 mins

def cleanup_inactive_sessions():

    # Do not perform cleanup in local mode
    if APP_MODE == 'local':
        return
    
    with SIMULATION_LOCK: # Reuse your lock to be safe
        now = time.time()
        inactive_sessions = [
            user_id for user_id, last_time in last_access.items() 
            if now - last_time > SESSION_TIMEOUT_SECONDS
        ]

        for user_id in inactive_sessions:
            print(f"Cleaning up inactive session: {user_id}")
            # Remove from the manager cache
            if user_id in project_managers:
                del project_managers[user_id]
            # Remove from last access tracker
            if user_id in last_access:
                del last_access[user_id]
            
            # Remove the user's project directory
            session_project_dir = os.path.join(PROJECTS_BASE_DIR, user_id)
            if os.path.exists(session_project_dir):
                shutil.rmtree(session_project_dir) # Be careful with this!

def run_cleanup_scheduler(sc):
    cleanup_inactive_sessions()
    # Re-schedule the cleanup to run again in 1 hour
    sc.enter(SESSION_TIMEOUT_SECONDS, 1, run_cleanup_scheduler, (sc,))

# --- Scheduler to run the cleanup task ---
scheduler = sched.scheduler(time.time, time.sleep)

# Start the scheduler in a background thread
scheduler_thread = threading.Thread(target=run_cleanup_scheduler, args=(scheduler,))
scheduler_thread.daemon = True
scheduler_thread.start()

if __name__ == '__main__':
    app.run(debug=True, port=5003)