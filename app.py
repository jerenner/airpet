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
import sys
import shutil
import sched
import time

from datetime import datetime
from flask import Flask, request, jsonify, render_template, Response, session, send_file
from flask_cors import CORS
from typing import Dict, Any, List, Optional

from dotenv import load_dotenv, set_key, find_dotenv
from google import genai  # Correct top-level import
from google.genai import types # Often useful for advanced features
from PIL import Image
from google.genai import client # For type hinting

from src.expression_evaluator import ExpressionEvaluator 
from src.project_manager import ProjectManager, AUTOSAVE_VERSION_ID
from src.geometry_types import get_unit_value
from src.geometry_types import Material, Solid, LogicalVolume
from src.geometry_types import GeometryState
from src.ai_tools import AI_GEOMETRY_TOOLS, PRIMITIVE_SOLID_PARAM_SPECS, get_project_summary, get_component_details
from src.templates import PHYSICS_TEMPLATES

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

# Examples directory
EXAMPLES_DIR = os.path.join(os.getcwd(), "examples", "projects")

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

        # --- Seed Example Projects ---
        if os.path.isdir(EXAMPLES_DIR):
            for example_name in os.listdir(EXAMPLES_DIR):
                example_path = os.path.join(EXAMPLES_DIR, example_name)
                if os.path.isdir(example_path):
                    target_path = os.path.join(pm.projects_dir, example_name)
                    if not os.path.exists(target_path):
                        print(f"Seeding example project: {example_name}")
                        shutil.copytree(example_path, target_path)

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
    It uses the API key stored in the session or the server fallback.
    """
    if 'user_id' not in session:
        return None

    user_id = session['user_id']
    # Priority: 1. User Session Key, 2. Server Environment Key
    api_key = session.get('gemini_api_key') or SERVER_GEMINI_API_KEY

    if not api_key:
        if user_id in gemini_clients:
            del gemini_clients[user_id]
        return None

    cached_client_info = gemini_clients.get(user_id)
    if cached_client_info and cached_client_info['key'] == api_key:
        return cached_client_info['client']

    print(f"Configuring Gemini client for user session: {user_id}")
    try:
        new_client = genai.Client(api_key=api_key)
        gemini_clients[user_id] = {'client': new_client, 'key': api_key}
        return new_client
    except Exception as e:
        print(f"Warning: Failed to configure Gemini client: {e}")
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

# --- Helper to get Geant4 environment variables from Conda ---
def get_geant4_env(sim_params=None):
    """
    Attempts to locate Geant4 data directories within the conda environment
    and returns a dictionary of environment variables.
    """
    env = os.environ.copy()
    conda_prefix = os.environ.get("CONDA_PREFIX")
    
    # If not in environment, try common path
    if not conda_prefix:
        conda_prefix = "/Users/marth/miniconda/envs/airpet"
        
    g4_data_root = os.path.join(conda_prefix, "share", "Geant4", "data")
    
    if os.path.isdir(g4_data_root):
        # Map of variable names to their directory patterns (Geant4 11.x)
        data_maps = {
            "G4NEUTRONHPDATA": "NDL",
            "G4LEDATA": "EMLOW",
            "G4LEVELGAMMADATA": "PhotonEvaporation",
            "G4RADIOACTIVEDATA": "RadioactiveDecay",
            "G4PARTICLEXSDATA": "PARTICLEXS",
            "G4SAIDDATA": "SAIDDATA",
            "G4REALSURFACEDATA": "RealSurface",
            "G4ENSDFSTATEDATA": "ENSDFSTATE",
            "G4INCLDATA": "INCL",
            "G4ABLADATA": "ABLA"
        }
        
        for var, pattern in data_maps.items():
            matches = glob.glob(os.path.join(g4_data_root, f"{pattern}*"))
            if matches:
                env[var] = sorted(matches)[-1]
                
    # Add physics configuration from sim_params
    if sim_params:
        if 'physics_list' in sim_params:
            env['G4PHYSICSLIST'] = str(sim_params['physics_list'])
        if 'optical_physics' in sim_params:
            env['G4OPTICALPHYSICS'] = 'true' if sim_params['optical_physics'] else 'false'

    # Also ensure the binary directory is in PATH
    bin_dir = os.path.join(conda_prefix, "bin")
    if bin_dir not in env["PATH"]:
        env["PATH"] = bin_dir + os.pathsep + env["PATH"]
        
    return env

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
                text=True, bufsize=1,
                env=get_geant4_env()
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
                                    parts = line.split()
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
            
            filtered_lines = []
            for line in base_lines:
                s = line.strip()
                if s.startswith("/run/beamOn"): continue
                if s.startswith("/random/setSeeds"): continue
                if s.startswith("/analysis/setFileName"): continue
                if s.startswith("/run/numberOfThreads"): continue 
                if s.startswith("/g4pet/run/saveHits"): continue 
                filtered_lines.append(line)
            
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
                s1 = seed1 + i*1000
                s2 = seed2 + i*1000
                with open(os.path.join(run_dir, macro_name), 'w') as f:
                    f.writelines(filtered_lines)
                    f.write(f"\n/random/setSeeds {s1} {s2}")
                    f.write(f"\n/analysis/setFileName {out_name}")
                    f.write(f"\n/run/beamOn {n_events}\n")
                
                cmd = [executable_path, macro_name]
                p = subprocess.Popen(
                    cmd, cwd=run_dir,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    text=True, bufsize=1,
                    env=get_geant4_env()
                )
                procs.append(p)
            
            with SIMULATION_LOCK:
                SIMULATION_PROCESSES[job_id] = procs 

            monitor_threads = []
            def stdout_reader(proc, idx):
                for line in iter(proc.stdout.readline, ''):
                    line = line.strip()
                    if not line: continue
                    if "Checking overlaps for volume" in line: continue
                    is_interesting = (idx == 0) or ("error" in line.lower()) or ("warning" in line.lower()) or ("exception" in line.lower())
                    if is_interesting:
                        prefix = f"[T{idx}] "
                        with SIMULATION_LOCK:
                            SIMULATION_STATUS[job_id]['stdout'].append(prefix + line)
                            if idx == 0 and ">>> Event" in line and "starts" in line:
                                try:
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
                t_out = threading.Thread(target=stdout_reader, args=(p, i))
                t_out.start()
                monitor_threads.append(t_out)
                t_err = threading.Thread(target=stderr_reader, args=(p, i))
                t_err.start()
                monitor_threads.append(t_err)
            
            for t in monitor_threads: t.join()
            final_return_code = 0
            for p in procs:
                p.wait()
                if p.returncode != 0: final_return_code = p.returncode
            if final_return_code == 0:
                with SIMULATION_LOCK: SIMULATION_STATUS[job_id]['stdout'].append("Parallel tasks completed. Merging...")

        if final_return_code == 0:
            import glob
            import shutil
            t_files = glob.glob(os.path.join(run_dir, "output_t*.hdf5"))
            if not t_files: t_files = glob.glob(os.path.join(run_dir, "run_t*.hdf5"))
            if t_files:
                try: t_files.sort(key=lambda x: int(os.path.basename(x).split('_t')[1].split('.')[0]))
                except: t_files.sort()
                target_path = os.path.join(run_dir, "output.hdf5")
                shutil.copyfile(t_files[0], target_path)
                try:
                    with h5py.File(target_path, 'r+') as f:
                        if 'default_ntuples/Hits' in f:
                            hits = f['default_ntuples/Hits']
                            lim_t0 = 0
                            if 'EventID' in hits and 'pages' in hits['EventID']:
                                ev = hits['EventID']['pages'][:]
                                nz = np.nonzero(ev)[0]
                                lim_t0 = nz[-1] + 1 if len(nz) > 0 else 0
                            for c in hits:
                                if isinstance(hits[c], h5py.Group) and 'pages' in hits[c]:
                                    dset = hits[c]['pages']
                                    data = dset[:lim_t0]
                                    attrs = dict(dset.attrs)
                                    del hits[c]['pages']
                                    dn = hits[c].create_dataset('pages', data=data, maxshape=(None,)+data.shape[1:], chunks=True, compression="gzip")
                                    for k,v in attrs.items(): dn.attrs[k] = v
                except Exception as e: print(f"T0 Clean Error: {e}")
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
                                    lim_src = 0
                                    if 'EventID' in grp_src_hits:
                                            ev = grp_src_hits['EventID']['pages'][:]
                                            nz = np.nonzero(ev)[0]
                                            if len(nz)>0: lim_src = nz[-1]+1
                                    for col in grp_dst_hits:
                                        if col not in grp_src_hits: continue
                                        dst_node = grp_dst_hits[col]
                                        src_node = grp_src_hits[col]
                                        if isinstance(dst_node, h5py.Group) and 'pages' in dst_node:
                                            dst_d = dst_node['pages']
                                            src_d = src_node['pages']
                                            data = src_d[:lim_src]
                                            if col == "EventID":
                                                data = data.astype(np.int64)
                                                if current_offset > 0: data += current_offset
                                            old_len = dst_d.shape[0]
                                            add_len = len(data)
                                            dst_d.resize((old_len+add_len,) + dst_d.shape[1:])
                                            dst_d[old_len:old_len+add_len] = data
                                        elif isinstance(dst_node, h5py.Dataset) and col=='entries':
                                            dst_node[...] += src_node[...]
                except Exception as e: print(f"Merge Loop Error: {e}")
                with SIMULATION_LOCK:
                    SIMULATION_STATUS[job_id]['stdout'].append("Merge finished.")
                    for f in t_files: os.remove(f)

        with SIMULATION_LOCK:
            if final_return_code == 0:
                SIMULATION_STATUS[job_id]['progress'] = total_events
                SIMULATION_STATUS[job_id]['status'] = 'Completed'
            else:
                SIMULATION_STATUS[job_id]['status'] = 'Error'
            SIMULATION_PROCESSES.pop(job_id, None)
    except Exception as e:
        import traceback
        traceback.print_exc()
        with SIMULATION_LOCK:
            SIMULATION_STATUS[job_id]['status'] = 'Error'
            SIMULATION_STATUS[job_id]['stderr'].append(str(e))
        SIMULATION_PROCESSES.pop(job_id, None)

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
                        text=True, bufsize=1,
                        env=get_geant4_env(sim_params)
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
                            text=True, bufsize=1,
                            env=get_geant4_env(sim_params)
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
                    print(f"[Merge] Searching for output files in {run_dir}...")
                    # Look for separate files and sort humerically to ensure correct EventID order
                    t_files = glob.glob(os.path.join(run_dir, "output_t*.hdf5"))
                    if not t_files or len(t_files) == 0:
                         t_files = glob.glob(os.path.join(run_dir, "run_t*.hdf5"))

                    if t_files:
                        print(f"[Merge] Found {len(t_files)} fragments. Starting merge...")
                        try:
                            t_files.sort(key=lambda x: int(os.path.basename(x).split('_t')[1].split('.')[0]))
                        except:
                            t_files.sort()
                        
                        target_path = os.path.join(run_dir, "output.hdf5")
                        shutil.copyfile(t_files[0], target_path)
                        print(f"[Merge] Initialized target file from {t_files[0]}")

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

        # Start the background task
        thread = threading.Thread(target=run_g4_simulation, args=(job_id, run_dir, GEANT4_EXECUTABLE, sim_params))
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

@app.route('/api/simulation/analysis/<version_id>/<job_id>', methods=['GET'])
def get_simulation_analysis(version_id, job_id):
    pm = get_project_manager_for_session()
    version_dir = pm._get_version_dir(version_id)
    run_dir = os.path.join(version_dir, "sim_runs", job_id)
    output_path = os.path.join(run_dir, "output.hdf5")

    if not os.path.exists(output_path):
        import glob
        fragments = glob.glob(os.path.join(run_dir, "output_t*.hdf5"))
        if fragments:
             return jsonify({"success": False, "error": f"Found {len(fragments)} output fragments but the final merged file is missing. The simulation might still be merging or the merge failed."}), 404
        return jsonify({"success": False, "error": "Simulation output not found. This usually means the simulation completed but no hits were recorded. Ensure you have marked a volume as 'Sensitive' and that particles are actually hitting it."}), 404

    try:
        # Parse query parameters
        energy_bins = request.args.get('energy_bins', default=100, type=int)
        spatial_bins = request.args.get('spatial_bins', default=50, type=int)

        analysis_data = {}

        with h5py.File(output_path, 'r') as f:
            # Check for Hits ntuple
            if 'default_ntuples/Hits' not in f:
                 return jsonify({"success": False, "error": "Hits data not found in output file."}), 404
            
            hits_group = f['default_ntuples/Hits']
            
            # Determine number of valid entries
            num_entries = None
            if 'entries' in hits_group:
                try:
                    ent_dset = hits_group['entries']
                    if ent_dset.shape == ():
                        num_entries = int(ent_dset[()])
                    else:
                        num_entries = int(ent_dset[0])
                except:
                    pass
            
            # Helper to safely read a column
            def get_col(name):
                # Handle HDF5 string types properly
                if name in hits_group:
                    dset = hits_group[name]
                    # Check if paginated (Geant4 default for large files) or flat
                    if isinstance(dset, h5py.Group) and 'pages' in dset:
                        data = dset['pages'][:]
                    elif isinstance(dset, h5py.Dataset):
                        data = dset[:] 
                    else:
                        return np.array([])
                    
                    # Slice to valid entries if known
                    if num_entries is not None and len(data) >= num_entries:
                        return data[:num_entries]
                    return data
                return np.array([])

            edep = get_col('Edep')
            pos_x = get_col('PosX')
            pos_y = get_col('PosY')
            pos_z = get_col('PosZ')
            copy_no = get_col('CopyNo')
            particle_name_ds = get_col('ParticleName')
            
            # 1. Energy Spectrum
            if len(edep) > 0:
                hist, bin_edges = np.histogram(edep, bins=energy_bins)
                analysis_data['energy_spectrum'] = {
                    'counts': hist.tolist(),
                    'bin_edges': bin_edges.tolist()
                }
            else:
                 analysis_data['energy_spectrum'] = {'counts': [], 'bin_edges': []}

            # 2. Spatial Heatmaps (XY, XZ, YZ)
            def compute_heatmap(x, y, bins):
                if len(x) == 0 or len(y) == 0:
                    return {'z': [], 'x_edges': [], 'y_edges': []}
                # Use np.histogram2d
                # Note: numpy returns (nx, ny), where x is the first dimension (rows).
                # Plotly expects z as an array of arrays where z[i] is a row.
                # So we might need to transpose depending on convention.
                # Usually: z[y][x].
                # histogram2d returns H[x, y].
                # So H.T is H[y, x].
                h, x_edges, y_edges = np.histogram2d(x, y, bins=bins)
                return {
                    'z': h.T.tolist(), 
                    'x_edges': x_edges.tolist(),
                    'y_edges': y_edges.tolist()
                }

            analysis_data['heatmaps'] = {
                'xy': compute_heatmap(pos_x, pos_y, spatial_bins),
                'xz': compute_heatmap(pos_x, pos_z, spatial_bins),
                'yz': compute_heatmap(pos_y, pos_z, spatial_bins)
            }

            # 3. Volume Summary (Hits per CopyNo)
            if len(copy_no) > 0:
                unique, counts = np.unique(copy_no, return_counts=True)
                # Convert to standard python types
                analysis_data['volume_summary'] = {
                    'copy_numbers': unique.astype(int).tolist(),
                    'counts': counts.tolist()
                }
            else:
                analysis_data['volume_summary'] = {'copy_numbers': [], 'counts': []}

            # 4. Particle Species Breakdown
            if len(particle_name_ds) > 0:
                p_names = []
                for n in particle_name_ds:
                    if isinstance(n, bytes):
                        p_names.append(n.decode('utf-8'))
                    else:
                        p_names.append(str(n))
                
                if p_names:
                    series = pd.Series(p_names)
                    counts = series.value_counts()
                    analysis_data['particle_breakdown'] = {
                        'names': counts.index.tolist(),
                        'counts': counts.values.tolist()
                    }
                else:
                    analysis_data['particle_breakdown'] = {'names': [], 'counts': []}
            else:
                analysis_data['particle_breakdown'] = {'names': [], 'counts': []}
            
            analysis_data['total_hits'] = len(edep)

        return jsonify({"success": True, "analysis": analysis_data})

    except Exception as e:
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/simulation/download/<version_id>/<job_id>', methods=['GET'])
def download_simulation_data(version_id, job_id):
    """
    Returns the raw HDF5 simulation output for download.
    """
    pm = get_project_manager_for_session()
    version_dir = pm._get_version_dir(version_id)
    run_dir = os.path.join(version_dir, "sim_runs", job_id)
    output_path = os.path.join(run_dir, "output.hdf5")

    try:
        # Return the file as an attachment
        if not os.path.exists(output_path):
             import glob
             fragments = glob.glob(os.path.join(run_dir, "output_t*.hdf5"))
             if fragments:
                  return jsonify({"success": False, "error": f"Found {len(fragments)} output fragments but the final merged file is missing."}), 404
             return jsonify({"success": False, "error": f"Simulation output file not found. Did the simulation produce any hits? (Check the 'Analysis' tab to see if hit count is zero)"}), 404
        
        filename = f"sim_{job_id[:8]}_output.hdf5"
        return send_file(output_path, as_attachment=True, download_name=filename, mimetype='application/x-hdf5')
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

        # --- Monte Carlo Sensitivity Matrix (Pre-loaded or Computed) ---
        sensitivity_image = None
        sens_file = os.path.join(run_dir, "sensitivity.h5")
        
        if normalization:
            # TRY TO LOAD
            if os.path.exists(sens_file):
                print(f"Loading pre-computed Sensitivity Matrix from {sens_file}...")
                with h5py.File(sens_file, 'r') as f:
                    sens_data = f['sensitivity'][()]
                    # Check consistency? (Size match)
                    if sens_data.shape == img_shape:
                        sensitivity_image = xp.asarray(sens_data, device=dev)
                    else:
                        print(f"WARNING: Sensitivity matrix shape {sens_data.shape} mismatch with image {img_shape}. Recomputing.")
                        sensitivity_image = None
            
            # IF NOT FOUND or MISMATCH, COMPUTE NOW
            if sensitivity_image is None:
                print("Sensitivity Matrix not found or invalid. Computing now...")
                ac_input = mu_map if (ac_enabled and 'mu_map' in locals()) else ac_mu
                
                # Call helper
                path, sens_cpu = compute_and_save_sensitivity(pm, run_dir, lor_data, img_shape, voxel_size, image_origin,
                                             ac_enabled, ac_shape, ac_input)
                sensitivity_image = xp.asarray(sens_cpu, device=dev)
        
        if normalization and sensitivity_image is not None:
             # Prepare for division
            max_sens = float(xp.max(sensitivity_image))
            sens_threshold = max_sens * 1e-3
            print(f"Sensitivity Threshold used: {sens_threshold:.2e}")
            sensitivity_image_safe_for_division = xp.where(sensitivity_image < sens_threshold, 1.0, sensitivity_image)
            
        
        # --- MLEM Reconstruction Loop ---
        x = xp.ones(img_shape, dtype=xp.float32, device=dev) # Initial image is all ones

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

def compute_and_save_sensitivity(pm, run_dir, lor_data, img_shape, voxel_size, image_origin, 
                                 ac_enabled, ac_shape, ac_mu, num_random_lors=20000000):
    """
    Helper function to compute sensitivity matrix and save to HDF5.
    Returns path to saved file and metadata.
    """
    import numpy as np
    import h5py
    try:
        import parallelproj
    except ImportError:
        print("Parallelproj not installed.")
        raise
    
    # Setup GPU device
    if 'cupy' in sys.modules:
        import cupy as xp
        import cupy
        os.environ["PARALLELPROJ_BACKEND"] = "cupy"
        dev = cupy.cuda.Device(0)
    else:
        import numpy as xp
        os.environ["PARALLELPROJ_BACKEND"] = "numpy"
        dev = "cpu"
        
    print(f"Computing Sensitivity Matrix on {dev}...")

    # 1. Estimate Scanner Geometry from LOR data
    # (We need this to generate valid random LORs)
    
    # Retrieve coordinates columns
    start_coords = lor_data['start_coords']
    end_coords = lor_data['end_coords']
    
    # Start/End Coordinates
    # We take a sample if too large? 100k events is enough for geometry.
    n_total = start_coords.shape[0]
    n_sample = min(100000, n_total)
    sample_indices = np.random.choice(n_total, n_sample, replace=False)
    
    start_sample = start_coords[sample_indices]
    end_sample = end_coords[sample_indices]
    
    x1, y1, z1 = start_sample[:, 0], start_sample[:, 1], start_sample[:, 2]
    x2, y2, z2 = end_sample[:, 0], end_sample[:, 1], end_sample[:, 2]
    
    r_start = np.sqrt(x1**2 + y1**2)
    r_end = np.sqrt(x2**2 + y2**2)
    scanner_radius = float(np.mean(np.concatenate((r_start, r_end))))
    
    z_all = np.concatenate((z1, z2))
    z_min_data = float(np.min(z_all))
    z_max_data = float(np.max(z_all))
    scanner_length = z_max_data - z_min_data
    
    print(f"Scanner Geometry (Sampled): Radius={scanner_radius:.1f}mm, Length={scanner_length:.1f}mm, Z_range=[{z_min_data:.1f}, {z_max_data:.1f}]")

    # 2. Optimization: Restrict random LOR Z-range to the Reconstruction FOV (+ margin)
    fov_z_start = image_origin[2]
    fov_z_end = image_origin[2] + (img_shape[2] * voxel_size[2])
    margin = scanner_radius * 0.5 
    
    z_min_opt = max(z_min_data, fov_z_start - margin)
    z_max_opt = min(z_max_data, fov_z_end + margin)
    z_min, z_max = z_min_opt, z_max_opt
    
    # 3. Generate Random LORs
    print(f"Generating {num_random_lors} random LORs...")
    
    phi1 = np.random.uniform(0, 2*np.pi, num_random_lors)
    z1_rand = np.random.uniform(z_min, z_max, num_random_lors)
    
    phi2 = np.random.uniform(0, 2*np.pi, num_random_lors)
    z2_rand = np.random.uniform(z_min, z_max, num_random_lors)
    
    rand_start = np.zeros((num_random_lors, 3), dtype=np.float32)
    rand_start[:,0] = scanner_radius * np.cos(phi1)
    rand_start[:,1] = scanner_radius * np.sin(phi1)
    rand_start[:,2] = z1_rand
    
    rand_end = np.zeros((num_random_lors, 3), dtype=np.float32)
    rand_end[:,0] = scanner_radius * np.cos(phi2)
    rand_end[:,1] = scanner_radius * np.sin(phi2)
    rand_end[:,2] = z2_rand
    
    rand_start_xp = xp.asarray(rand_start, device=dev)
    rand_end_xp = xp.asarray(rand_end, device=dev)

    # Apply Position Resolution Smearing (if present in LOR data)
    position_resolution = None
    if 'position_resolution' in lor_data:
         # lor_data is npz, might store dict as 0d array
         pr = lor_data['position_resolution']
         if pr.shape == (): position_resolution = pr.item()
         else: position_resolution = pr
         
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
            
    # 4. Create Projector
    sens_proj = parallelproj.ListmodePETProjector(
        rand_start_xp, rand_end_xp, img_shape, voxel_size, 
        img_origin=xp.asarray(image_origin, device=dev)
    )
    
    # 5. Attenuation
    sens_weights = xp.ones(num_random_lors, dtype=xp.float32, device=dev)
    
    if ac_enabled and ac_shape == 'cylinder':
        print("Calculating Attenuation for Sensitivity LORs...")
        
        # Grid Setup
        nx, ny, nz = img_shape
        vx, vy, vz = voxel_size
        ox, oy, oz = image_origin
        
        x_grid = xp.arange(nx, dtype=xp.float32) * vx + ox + vx/2
        y_grid = xp.arange(ny, dtype=xp.float32) * vy + oy + vy/2
        
        # Create Meshgrid on device
        xx, yy = xp.meshgrid(x_grid, y_grid, indexing='ij') 

    if ac_enabled and ac_mu is not None:
         # We expect `ac_mu` to be the VOLUME (3D array) on device if possible, 
         # OR we generate it if we only have scalar mu.
         # Current app approach: Generate volume from scalar mu + radius.
         
         # Let's allow passing PRE-COMPUTED mu_map if available (from reconstruction loop)
         # or params to compute it.
         if isinstance(ac_mu, (float, int)): # It's a scalar value, we need to build map
             # ac_radius is needed.
             # We will fallback to "Generate cylinder mask matching FOV" if no radius given?
             # Or assume radius = FOV_X / 2?
             radius = (img_shape[0] * voxel_size[0]) / 2.0 * 0.9 # Slightly smaller?
             # Looking at reconstruction code: `mask = (xx**2 + yy**2) <= ac_radius**2`
             
             dist_sq = xx**2 + yy**2
             mask = dist_sq <= radius**2

             # Expand to 3D
             mask_3d = xp.repeat(mask[:, :, xp.newaxis], nz, axis=2)
             mu_map_vol = xp.where(mask_3d, float(ac_mu), 0.0)
             
             # Project
             attenuation_integrals_rand = sens_proj(mu_map_vol)
             ac_factors_rand = xp.exp(-attenuation_integrals_rand * 0.1)
             sens_weights *= ac_factors_rand
             
         elif hasattr(ac_mu, 'shape'): # It's an array (mu_map)
             attenuation_integrals_rand = sens_proj(ac_mu)
             ac_factors_rand = xp.exp(-attenuation_integrals_rand * 0.1)
             sens_weights *= ac_factors_rand

    # 6. Backproject
    sensitivity_image = sens_proj.adjoint(sens_weights)
    
    # 7. Smooth
    print("Smoothing Sensitivity Map...")
    from scipy.ndimage import gaussian_filter
    sens_cpu = parallelproj.to_numpy_array(sensitivity_image)
    sigma_vox = [1.0 / float(v) for v in voxel_size] # 1mm smoothing
    sens_smoothed_cpu = gaussian_filter(sens_cpu, sigma=sigma_vox)
    
    # 8. Save
    sens_file = os.path.join(run_dir, "sensitivity.h5")
    with h5py.File(sens_file, 'w') as f:
        dset = f.create_dataset("sensitivity", data=sens_smoothed_cpu)
        dset.attrs['voxel_size'] = voxel_size
        dset.attrs['origin'] = image_origin
        dset.attrs['scanner_radius'] = scanner_radius
        dset.attrs['scanner_length'] = scanner_length
        dset.attrs['num_random_lors'] = num_random_lors
        dset.attrs['ac_enabled'] = ac_enabled
        # Save threshold info
        max_v = float(np.max(sens_smoothed_cpu))
        dset.attrs['threshold'] = max_v * 1e-3
        
    print(f"Sensitivity matrix saved to {sens_file}")
    return sens_file, sens_smoothed_cpu


@app.route('/api/sensitivity/compute', methods=['POST'])
def compute_sensitivity_route():
    pm = get_project_manager_for_session()
    data = request.get_json()
    
    version_id = data.get('version_id')
    job_id = data.get('job_id')
    
    # Reconstruction/Grid Params
    voxel_size_mm = float(data.get('voxel_size', 2.0))
    matrix_size = int(data.get('matrix_size', 128))
    # FOV/Origin
    # Usually computed from matrix_size * voxel_size centered at 0
    fov = matrix_size * voxel_size_mm
    voxel_size = (voxel_size_mm, voxel_size_mm, voxel_size_mm)
    img_shape = (matrix_size, matrix_size, matrix_size)

    # Use exact same logic as run_reconstruction_route to align grids
    i_origin_np = - (np.array(img_shape, dtype=np.float32) / 2 - 0.5) * np.array(voxel_size, dtype=np.float32)
    image_origin = tuple(i_origin_np.tolist())
    
    # AC Params
    ac_enabled = data.get('ac_enabled', False)
    ac_mu = float(data.get('ac_mu', 0.096)) # Default water
    ac_radius = float(data.get('ac_radius', 0.0)) # If 0, use default heuristics
    if ac_radius == 0: ac_radius = fov/2 * 0.9
    
    ran_lors = int(data.get('num_random_lors', 20000000))
    
    try:
        version_dir = pm._get_version_dir(version_id)
        run_dir = os.path.join(version_dir, "sim_runs", job_id)
        
        # Load LOR data for geometry
        lor_path = os.path.join(run_dir, "lors.npz")
        if not os.path.exists(lor_path):
             return jsonify({"success": False, "error": "LOR data not found."}), 404
             
        lor_data = np.load(lor_path, allow_pickle=True)
        
        # Call the helper to compute and save sensitivity
        compute_and_save_sensitivity(pm, run_dir, lor_data, img_shape, voxel_size, image_origin,
                                     ac_enabled, 'cylinder', ac_mu, num_random_lors=ran_lors)
                                     
        return jsonify({"success": True, "message": "Sensitivity Matrix computed."})
        
    except Exception as e:
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/sensitivity/status/<version_id>/<job_id>', methods=['GET'])
def get_sensitivity_status_route(version_id, job_id):
    pm = get_project_manager_for_session()
    try:
        version_dir = pm._get_version_dir(version_id)
        run_dir = os.path.join(version_dir, "sim_runs", job_id)
        sens_file = os.path.join(run_dir, "sensitivity.h5")
        
        if os.path.exists(sens_file):
            with h5py.File(sens_file, 'r') as f:
                dset = f['sensitivity']
                # Read attributes
                info = {
                    "exists": True,
                    "scanner_radius": dset.attrs.get('scanner_radius', 0),
                    "ac_enabled": dset.attrs.get('ac_enabled', False),
                    "timestamp": os.path.getmtime(sens_file)
                }
                return jsonify(info)
        else:
            return jsonify({"exists": False})
    except Exception as e:
        return jsonify({"exists": False, "error": str(e)})

@app.route('/api/reconstruction/slice/<version_id>/<job_id>/<axis>/<int:slice_num>', methods=['GET'])
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
    # Context Management: provide a summary instead of full JSON to save tokens/complexity
    context_summary = project_manager.get_summarized_context()

    full_prompt = (f"{system_prompt}\n\n"
                    f"## Current Project Summary\n\n"
                    f"{context_summary}\n\n"
                    f"## User Request\n\n"
                    f'"{user_prompt}"\n\n'
                    f"NOTE: Use your tools to inspect details or modify the state. If you are in one-shot mode, provide the JSON response for modifications as requested.")

    return full_prompt

# --- Main Application Routes ---

@app.route('/')
def index():
    return render_template('index.html', app_mode=APP_MODE)

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

# --- AI Tool Dispatcher ---
AI_TOOL_PARAM_SCHEMAS = {
    tool["name"]: tool.get("parameters", {}) for tool in AI_GEOMETRY_TOOLS
}

# Aliases that normalize common model mistakes/synonyms into canonical tool args.
AI_TOOL_ARG_ALIASES = {
    "manage_define": {
        "type": "define_type",
        "raw_expression": "value"
    },
    "create_primitive_solid": {
        "dimensions": "params",
        "type": "solid_type"
    },
    "manage_logical_volume": {
        "solid": "solid_ref",
        "material": "material_ref",
        "sensitive": "is_sensitive"
    },
    "place_volume": {
        "mother": "parent_lv_name",
        "parent": "parent_lv_name",
        "volume": "placed_lv_ref"
    },
    "modify_physical_volume": {
        "id": "pv_id",
        "pv_id": "pv_id"
    },
    "create_detector_ring": {
        "mother": "parent_lv_name",
        "volume": "lv_to_place_ref",
        "lv_to_place": "lv_to_place_ref"
    },
    "delete_objects": {
        "items": "objects"
    },
    "batch_geometry_update": {
        "ops": "operations"
    },
    "manage_surface_link": {
        "surfaceproperty_ref": "surface_ref",
        "physvol1_ref": "pv1_id",
        "physvol2_ref": "pv2_id",
        "volume": "volume_ref"
    },
    "manage_ui_group": {
        "target_group_name": "group_name",
        "operation": "action"
    },
    "run_simulation": {
        "num_events": "events",
        "n_events": "events",
        "num_threads": "threads",
        "n_threads": "threads"
    },
    "manage_particle_source": {
        "id": "source_id",
        "source": "source_id",
        "gps": "gps_commands",
        "commands": "gps_commands"
    },
    "set_active_source": {
        "id": "source_id"
    },
    "process_lors": {
        "version": "version_id"
    },
    "check_lor_file": {
        "version": "version_id"
    },
    "run_reconstruction": {
        "version": "version_id",
        "image_shape": "image_size",
        "n_iter": "iterations"
    },
    "compute_sensitivity": {
        "version": "version_id",
        "num_lors": "num_random_lors"
    },
    "get_sensitivity_status": {
        "version": "version_id"
    },
    "get_simulation_metadata": {
        "version": "version_id"
    },
    "get_simulation_analysis": {
        "version": "version_id"
    },
    "rename_ui_group": {
        "from": "old_name",
        "to": "new_name"
    }
}

# Defaults used to keep tool calls resilient when small/fast models omit fields.
AI_TOOL_DEFAULTS = {
    "manage_define": {"define_type": "constant"},
    "create_detector_ring": {
        "parent_lv_name": "World",
        "num_detectors": "10",
        "radius": "100",
        "center": {"x": "0", "y": "0", "z": "0"},
        "orientation": {"x": "0", "y": "0", "z": "0"},
        "point_to_center": True,
        "inward_axis": "+x",
        "num_rings": "1",
        "ring_spacing": "0"
    },
    "run_simulation": {"events": 1000, "threads": 1},
    "manage_ui_group": {"item_ids": []},
    "manage_particle_source": {
        "name": "gps_source",
        "gps_commands": {},
        "position": {"x": "0", "y": "0", "z": "0"},
        "rotation": {"x": "0", "y": "0", "z": "0"},
        "activity": 1.0
    },
    "process_lors": {
        "coincidence_window_ns": 4.0,
        "energy_cut": 0.0,
        "energy_resolution": 0.05,
        "position_resolution": {"x": 0.0, "y": 0.0, "z": 0.0}
    },
    "run_reconstruction": {
        "iterations": 1,
        "image_size": [128, 128, 128],
        "voxel_size": [2.0, 2.0, 2.0],
        "normalization": True,
        "ac_enabled": False,
        "ac_shape": "cylinder",
        "ac_radius": 108.0,
        "ac_length": 186.0,
        "ac_mu": 0.096
    },
    "compute_sensitivity": {
        "voxel_size": 2.0,
        "matrix_size": 128,
        "ac_enabled": False,
        "ac_mu": 0.096,
        "ac_radius": 0.0,
        "num_random_lors": 20000000
    },
    "get_simulation_analysis": {
        "energy_bins": 100,
        "spatial_bins": 50
    }
}

# Canonicalization fallback for common model/user aliases in primitive solid params.
PRIMITIVE_SOLID_PARAM_ALIASES = {
    "tube": {
        "innerradius": "rmin",
        "outerradius": "rmax",
        "halfz": "z",
        "halflength": "z",
        "startangle": "startphi",
        "spanangle": "deltaphi"
    },
    "cone": {
        "innerradius1": "rmin1",
        "outerradius1": "rmax1",
        "innerradius2": "rmin2",
        "outerradius2": "rmax2",
        "halfz": "z",
        "halflength": "z",
        "startangle": "startphi",
        "spanangle": "deltaphi"
    },
    "sphere": {
        "innerradius": "rmin",
        "outerradius": "rmax",
        "startangle": "startphi",
        "spanangle": "deltaphi",
        "startpolarangle": "starttheta",
        "spanpolarangle": "deltatheta"
    }
}

ANGLE_PARAM_NAMES = {"startphi", "deltaphi", "starttheta", "deltatheta", "theta", "phi", "alpha", "inst", "outst", "twistedangle", "phitwist", "alph"}


def _normalize_param_alias_key(key: str) -> str:
    return re.sub(r'[^a-z0-9]', '', str(key).lower())


def _coerce_angle_expr_if_bare_number(expr: Any) -> Any:
    if not isinstance(expr, str):
        return expr

    s = expr.strip().lower()
    if any(tok in s for tok in ('deg', 'rad', 'pi', '*', '/', '+', '-', '(', ')')):
        return expr

    return f"({expr})*deg"


def normalize_primitive_solid_params(solid_type: Any, raw_params: Any) -> Any:
    if not isinstance(raw_params, dict):
        return raw_params

    st = str(solid_type or '').strip()
    aliases = PRIMITIVE_SOLID_PARAM_ALIASES.get(st, {})

    mapped = dict(raw_params)
    for key, value in raw_params.items():
        target = aliases.get(_normalize_param_alias_key(key))
        if target and target not in mapped:
            mapped[target] = value

    for angle_key in list(mapped.keys()):
        if _normalize_param_alias_key(angle_key) in ANGLE_PARAM_NAMES:
            mapped[angle_key] = _coerce_angle_expr_if_bare_number(mapped[angle_key])

    return mapped


def _camel_to_snake(key: str) -> str:
    # parentLvName -> parent_lv_name
    return re.sub(r'(?<!^)(?=[A-Z])', '_', key).lower()


def _parse_json_like(value: Any) -> Any:
    if not isinstance(value, str):
        return value

    stripped = value.strip()
    if not stripped:
        return value

    # Only attempt parsing values that look like structured data.
    if not ((stripped.startswith('{') and stripped.endswith('}')) or
            (stripped.startswith('[') and stripped.endswith(']'))):
        return value

    try:
        return json.loads(stripped)
    except Exception:
        try:
            return ast.literal_eval(stripped)
        except Exception:
            return value


def _coerce_value_by_schema(value: Any, schema: Optional[Dict[str, Any]]) -> Any:
    if schema is None:
        return _parse_json_like(value)

    if value is None:
        return value

    schema_type = schema.get("type")

    if schema_type == "object":
        value = _parse_json_like(value)
        if isinstance(value, dict):
            props = schema.get("properties", {})
            coerced = {}
            for k, v in value.items():
                child_schema = props.get(k)
                coerced[k] = _coerce_value_by_schema(v, child_schema)
            return coerced
        return value

    if schema_type == "array":
        value = _parse_json_like(value)
        if isinstance(value, list):
            item_schema = schema.get("items")
            return [_coerce_value_by_schema(v, item_schema) for v in value]
        return value

    if schema_type == "boolean" and isinstance(value, str):
        low = value.strip().lower()
        if low in ("true", "1", "yes", "on"):
            return True
        if low in ("false", "0", "no", "off"):
            return False
        return value

    if schema_type == "integer" and isinstance(value, str):
        try:
            return int(float(value))
        except Exception:
            return value

    if schema_type == "number" and isinstance(value, str):
        try:
            return float(value)
        except Exception:
            return value

    return _parse_json_like(value)


def _normalize_tool_args(tool_name: str, args: Any) -> tuple[Optional[Dict[str, Any]], Optional[str]]:
    schema = AI_TOOL_PARAM_SCHEMAS.get(tool_name)
    if not schema:
        return None, f"Unknown tool: {tool_name}"

    # Gemini/Ollama can provide dict-like objects or JSON strings.
    if hasattr(args, "to_dict"):
        args = args.to_dict()

    args = _parse_json_like(args)
    if args is None:
        args = {}

    if not isinstance(args, dict):
        return None, f"Tool '{tool_name}' arguments must be an object/dict, got {type(args).__name__}."

    # Normalize top-level keys (camelCase -> snake_case).
    normalized: Dict[str, Any] = {}
    for key, value in args.items():
        key_str = str(key)
        normalized[_camel_to_snake(key_str)] = _parse_json_like(value)

    # Apply per-tool aliases.
    for old_key, canonical_key in AI_TOOL_ARG_ALIASES.get(tool_name, {}).items():
        old_norm = _camel_to_snake(old_key)
        canonical_norm = _camel_to_snake(canonical_key)
        if old_norm in normalized and canonical_norm not in normalized:
            normalized[canonical_norm] = normalized[old_norm]

    # Coerce known values according to schema.
    properties = schema.get("properties", {})
    for key, prop_schema in properties.items():
        if key in normalized:
            normalized[key] = _coerce_value_by_schema(normalized[key], prop_schema)

    # Apply defaults after aliasing/coercion.
    for key, value in AI_TOOL_DEFAULTS.get(tool_name, {}).items():
        if normalized.get(key) is None:
            normalized[key] = value

    return normalized, None


def _validate_create_primitive_solid_args(args: Dict[str, Any]) -> Optional[str]:
    solid_type = args.get('solid_type')
    params = args.get('params')

    if not isinstance(params, dict):
        return "Tool 'create_primitive_solid' expects 'params' to be an object."

    spec = PRIMITIVE_SOLID_PARAM_SPECS.get(str(solid_type))
    if not spec:
        return (
            f"Unsupported solid_type '{solid_type}'. "
            f"Supported: {sorted(PRIMITIVE_SOLID_PARAM_SPECS.keys())}."
        )

    normalized_params = normalize_primitive_solid_params(solid_type, params)
    args['params'] = normalized_params

    required_params = spec.get('required', [])
    missing = [
        key for key in required_params
        if key not in normalized_params or normalized_params.get(key) in (None, "")
    ]
    if not missing:
        return None

    canonical_props = spec.get('properties', {})
    canonical_names = list(canonical_props.keys())

    alias_pairs = PRIMITIVE_SOLID_PARAM_ALIASES.get(str(solid_type), {})
    alias_hint = ""
    if alias_pairs:
        rendered = ", ".join([f"{a}->{c}" for a, c in sorted(alias_pairs.items())])
        alias_hint = f" Common aliases accepted: {rendered}."

    provided_keys = sorted(params.keys()) if isinstance(params, dict) else []

    return (
        f"Tool 'create_primitive_solid' for solid_type='{solid_type}' is missing required param(s): {missing}. "
        f"Use canonical params: {canonical_names}. "
        f"Provided keys: {provided_keys}.{alias_hint}"
    )


def _validate_tool_args(tool_name: str, args: Dict[str, Any]) -> Optional[str]:
    schema = AI_TOOL_PARAM_SCHEMAS.get(tool_name, {})

    required = schema.get("required", [])
    missing = [
        req for req in required
        if req not in args or args[req] is None or args[req] == ""
    ]
    if missing:
        return f"Tool '{tool_name}' missing required argument(s): {', '.join(missing)}."

    properties = schema.get("properties", {})
    for key, prop_schema in properties.items():
        if key not in args or args[key] is None:
            continue

        allowed = prop_schema.get("enum")
        if allowed and args[key] not in allowed:
            return (
                f"Tool '{tool_name}' has invalid value for '{key}': {args[key]!r}. "
                f"Allowed: {allowed}."
            )

    if tool_name == 'create_primitive_solid':
        return _validate_create_primitive_solid_args(args)

    return None


def dispatch_ai_tool(pm: ProjectManager, tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    """Dispatches a tool call from the AI to the appropriate ProjectManager method."""

    # Helper to convert list [x,y,z] to dict {'x':x,'y':y,'z':z}
    def to_vec_dict(val, default_val='0'):
        if isinstance(val, list) and len(val) == 3:
            return {'x': str(val[0]), 'y': str(val[1]), 'z': str(val[2])}
        if isinstance(val, dict):
            # Ensure all keys exist
            return {
                'x': str(val.get('x', default_val)),
                'y': str(val.get('y', default_val)),
                'z': str(val.get('z', default_val))
            }
        return val

    def parse_color_to_rgba(color_str, opacity=1.0):
        if not color_str:
            return None
        # Basic hex to rgba
        if isinstance(color_str, str) and color_str.startswith('#'):
            hex_color = color_str.lstrip('#')
            if len(hex_color) == 6:
                r, g, b = tuple(int(hex_color[i:i+2], 16) / 255.0 for i in (0, 2, 4))
                return {'color': {'r': r, 'g': g, 'b': b, 'a': opacity}}
        # Fallback for common names
        names = {
            'blue': (0, 0, 1), 'red': (1, 0, 0), 'green': (0, 1, 0), 'yellow': (1, 1, 0),
            'cyan': (0, 1, 1), 'magenta': (1, 0, 1), 'white': (1, 1, 1), 'black': (0, 0, 0),
            'gray': (0.5, 0.5, 0.5), 'lead': (0.3, 0.3, 0.3), 'water': (0, 0.5, 1.0),
            'lucite': (0.5, 0.5, 0.9), 'plastic': (0.7, 0.7, 0.7)
        }
        rgb = names.get(str(color_str).lower(), (0.8, 0.8, 0.8))
        return {'color': {'r': rgb[0], 'g': rgb[1], 'b': rgb[2], 'a': opacity}}

    def call_route_json(route_fn, route_args=None, payload=None, query_params=None):
        """Call an existing Flask route function with a synthetic JSON request context."""
        route_args = route_args or []

        current_user_id = session.get('user_id')
        current_api_key = session.get('gemini_api_key')

        with app.test_request_context(json=payload, query_string=query_params):
            if current_user_id is not None:
                session['user_id'] = current_user_id
            if current_api_key is not None:
                session['gemini_api_key'] = current_api_key

            route_result = route_fn(*route_args)

        status_code = 200
        response_obj = route_result
        if isinstance(route_result, tuple):
            response_obj = route_result[0]
            if len(route_result) > 1 and isinstance(route_result[1], int):
                status_code = route_result[1]

        if hasattr(response_obj, 'get_json'):
            body = response_obj.get_json(silent=True)
        else:
            body = response_obj

        if body is None:
            body = {"success": False, "error": "Route returned no JSON body."}

        return status_code, body


    args, normalize_error = _normalize_tool_args(tool_name, args)
    if normalize_error:
        return {"success": False, "error": normalize_error}

    validation_error = _validate_tool_args(tool_name, args)
    if validation_error:
        return {"success": False, "error": validation_error}

    try:
        if tool_name == "get_project_summary":
            return {"success": True, "result": get_project_summary(pm)}

        elif tool_name == "get_component_details":
            details = get_component_details(pm, args['component_type'], args['name'])
            if details:
                return {"success": True, "result": details}
            return {"success": False, "error": f"Component '{args['name']}' not found."}

        elif tool_name == "manage_define":
            name = args.get('name')
            raw_val = args.get('value')
            value = to_vec_dict(raw_val)

            if name in pm.current_geometry_state.defines:
                success, error = pm.update_define(name, value, args.get('unit'))
                if success:
                    return {"success": True, "message": f"Define '{name}' updated."}
                return {"success": False, "error": error}
            else:
                res, error = pm.add_define(name, args.get('define_type', 'constant'), value, args.get('unit'))
                if res:
                    return {"success": True, "message": f"Define '{res['name']}' created."}
                return {"success": False, "error": error}

        elif tool_name == "manage_material":
            name = args.get('name')
            props = {
                "density_expr": args.get('density'),
                "Z_expr": args.get('z') if args.get('z') is not None else args.get('Z'),
                "A_expr": args.get('a') if args.get('a') is not None else args.get('A'),
                "components": args.get('components')
            }
            props = {k: v for k, v in props.items() if v is not None}

            if name in pm.current_geometry_state.materials:
                success, error = pm.update_material(name, props)
                if success:
                    return {"success": True, "message": f"Material '{name}' updated."}
                return {"success": False, "error": error}
            else:
                res, error = pm.add_material(name, props)
                if res:
                    return {"success": True, "message": f"Material '{res['name']}' created."}
                return {"success": False, "error": error}

        elif tool_name == "create_primitive_solid":
            stype = args.get('solid_type')
            p = args.get('params')

            if isinstance(p, list) and len(p) == 3:
                p = {'x': str(p[0]), 'y': str(p[1]), 'z': str(p[2])}

            p = normalize_primitive_solid_params(stype, p)

            res, error = pm.add_solid(args.get('name', 'AI_Solid'), stype, p)
            if res:
                pm.recalculate_geometry_state()
                return {"success": True, "message": f"Solid '{res['name']}' created."}
            return {"success": False, "error": error}

        elif tool_name == "modify_solid":
            success, error = pm.update_solid(args['name'], args['params'])
            if success:
                return {"success": True, "message": f"Solid '{args['name']}' updated."}
            return {"success": False, "error": error}

        elif tool_name == "create_boolean_solid":
            name = args.get('name')
            recipe = args.get('recipe')

            for item in recipe:
                if 'transform' in item and item['transform']:
                    t = item['transform']
                    if 'position' in t:
                        t['position'] = to_vec_dict(t['position'])
                    if 'rotation' in t:
                        t['rotation'] = to_vec_dict(t['rotation'])

            res, error = pm.add_boolean_solid(name, recipe)
            if res:
                return {"success": True, "message": f"Boolean solid '{res['name']}' created."}
            return {"success": False, "error": error}

        elif tool_name == "manage_logical_volume":
            name = args.get('name')
            solid_ref = args.get('solid_ref')
            material_ref = args.get('material_ref')
            is_sensitive = args.get('is_sensitive', False)

            color_str = args.get('color')
            opacity = args.get('opacity', 1.0)
            vis_attrs = parse_color_to_rgba(color_str, opacity)

            if name in pm.current_geometry_state.logical_volumes:
                success, error = pm.update_logical_volume(
                    name, solid_ref, material_ref,
                    new_vis_attributes=vis_attrs,
                    new_is_sensitive=is_sensitive
                )
                if success:
                    return {"success": True, "message": f"Logical volume '{name}' updated."}
                return {"success": False, "error": error}
            else:
                res, error = pm.add_logical_volume(
                    name, solid_ref, material_ref,
                    vis_attributes=vis_attrs,
                    is_sensitive=is_sensitive
                )
                if res:
                    return {"success": True, "message": f"Logical volume '{res['name']}' created."}
                return {"success": False, "error": error}

        elif tool_name == "place_volume":
            parent = args.get('parent_lv_name')
            placed = args.get('placed_lv_ref')

            res, error = pm.add_physical_volume(
                parent, args.get('name'), placed,
                to_vec_dict(args.get('position', {'x': '0', 'y': '0', 'z': '0'})),
                to_vec_dict(args.get('rotation', {'x': '0', 'y': '0', 'z': '0'})),
                to_vec_dict(args.get('scale', {'x': '1', 'y': '1', 'z': '1'}))
            )
            if res:
                return {"success": True, "message": f"Volume placed as '{res['name']}'."}
            return {"success": False, "error": error}

        elif tool_name == "modify_physical_volume":
            success, error = pm.update_physical_volume(
                args['pv_id'], args.get('name'),
                to_vec_dict(args.get('position')),
                to_vec_dict(args.get('rotation')),
                to_vec_dict(args.get('scale'))
            )
            if success:
                return {"success": True, "message": f"Physical volume '{args['pv_id']}' updated."}
            return {"success": False, "error": error}

        elif tool_name == "create_detector_ring":
            ring_name = args.get('ring_name')

            res, error = pm.create_detector_ring(
                parent_lv_name=args.get('parent_lv_name', 'World'),
                lv_to_place_ref=args.get('lv_to_place_ref'),
                ring_name=ring_name,
                num_detectors=args.get('num_detectors', '10'),
                radius=args.get('radius', '100'),
                center=to_vec_dict(args.get('center', {'x': '0', 'y': '0', 'z': '0'})),
                orientation=to_vec_dict(args.get('orientation', {'x': '0', 'y': '0', 'z': '0'})),
                point_to_center=args.get('point_to_center', True),
                inward_axis=args.get('inward_axis', '+x'),
                num_rings=args.get('num_rings', '1'),
                ring_spacing=args.get('ring_spacing', '0')
            )
            if res:
                return {"success": True, "message": f"Detector ring '{ring_name}' created."}
            return {"success": False, "error": error}

        elif tool_name == "delete_objects":
            objs = args.get('objects')
            if not objs or not isinstance(objs, list):
                return {"success": False, "error": "Argument 'objects' must be a list of {type, id}."}

            resolved_objs = []
            for item in objs:
                if isinstance(item, str):
                    item = {"id": item}

                if not isinstance(item, dict):
                    continue

                obj_id = item.get('id') or item.get('name')
                obj_type = item.get('type')

                if not obj_id:
                    continue

                if not obj_type:
                    if obj_id in pm.current_geometry_state.solids:
                        obj_type = "solid"
                    elif obj_id in pm.current_geometry_state.logical_volumes:
                        obj_type = "logical_volume"
                    elif obj_id in pm.current_geometry_state.defines:
                        obj_type = "define"
                    elif obj_id in pm.current_geometry_state.materials:
                        obj_type = "material"
                    else:
                        obj_type = "physical_volume"

                if obj_type == 'physical_volume':
                    pv_to_del = pm._find_pv_by_id(obj_id)
                    if not pv_to_del:
                        for lv in pm.current_geometry_state.logical_volumes.values():
                            if lv.content_type == 'physvol':
                                for pv in lv.content:
                                    if pv.name == obj_id:
                                        pv_to_del = pv
                                        break
                            if pv_to_del:
                                break

                    if pv_to_del:
                        resolved_objs.append({"type": "physical_volume", "id": pv_to_del.id})
                else:
                    resolved_objs.append({"type": obj_type, "id": obj_id})

            if not resolved_objs:
                return {"success": False, "error": "No valid objects found to delete."}

            success, res = pm.delete_objects_batch(resolved_objs)
            if success:
                return {"success": True, "message": f"{len(resolved_objs)} objects deleted."}
            return {"success": False, "error": res}

        elif tool_name == "search_components":
            pattern = args['pattern']
            ctype = args['component_type']
            state = pm.current_geometry_state
            results = []

            items = []
            if ctype == "solid":
                items = list(state.solids.keys())
            elif ctype == "logical_volume":
                items = list(state.logical_volumes.keys())
            elif ctype == "material":
                items = list(state.materials.keys())
            elif ctype == "physical_volume":
                for lv in state.logical_volumes.values():
                    if lv.content_type == 'physvol':
                        for pv in lv.content:
                            if re.search(pattern, pv.name, re.IGNORECASE):
                                results.append({"id": pv.id, "name": pv.name, "parent": lv.name})
                return {"success": True, "results": results}

            for item in items:
                if re.search(pattern, item, re.IGNORECASE):
                    results.append(item)
            return {"success": True, "results": results}

        elif tool_name == "set_volume_appearance":
            name = args.get('name')

            color_str = args.get('color') or args.get('hex')
            if not color_str:
                for cname in ['blue', 'red', 'green', 'yellow', 'cyan', 'magenta', 'white', 'black', 'gray', 'lead']:
                    val = args.get(cname)
                    if val and val != "False" and val != "none":
                        color_str = cname
                        break

            if not color_str:
                return {"success": False, "error": "Argument 'color' (name or hex) is required."}

            vis_attrs = parse_color_to_rgba(color_str, args.get('opacity', 1.0))
            success, error = pm.update_logical_volume(name, None, None, new_vis_attributes=vis_attrs)
            if success:
                return {"success": True, "message": f"Appearance for '{name}' updated to {color_str}."}
            return {"success": False, "error": error}

        elif tool_name == "delete_detector_ring":
            ring_name = args['ring_name']
            state = pm.current_geometry_state
            to_delete = []
            for lv in state.logical_volumes.values():
                if lv.content_type == 'physvol':
                    for pv in lv.content:
                        if pv.name == ring_name:
                            to_delete.append({"type": "physical_volume", "id": pv.id})

            if not to_delete:
                return {"success": False, "error": f"No physical volumes with name '{ring_name}' found."}

            success, res = pm.delete_objects_batch(to_delete)
            if success:
                return {"success": True, "message": f"All {len(to_delete)} instances of ring '{ring_name}' deleted."}
            return {"success": False, "error": res}

        elif tool_name == "run_simulation":
            job_id = str(uuid.uuid4())
            try:
                events = int(args.get("events", 1000))
            except Exception:
                events = 1000
            try:
                threads = int(args.get("threads", 1))
            except Exception:
                threads = 1

            sim_params = {
                "events": events,
                "threads": threads
            }
            version_id = pm.current_version_id
            if pm.is_changed or not version_id:
                version_id, _ = pm.save_project_version(f"AI_Sim_Run_{job_id[:8]}")

            version_dir = pm._get_version_dir(version_id)
            run_dir = os.path.join(version_dir, "sim_runs", job_id)
            os.makedirs(run_dir, exist_ok=True)

            pm.generate_macro_file(
                job_id, sim_params, GEANT4_BUILD_DIR, run_dir, version_dir
            )

            thread = threading.Thread(target=run_g4_simulation, args=(job_id, run_dir, GEANT4_EXECUTABLE, sim_params))
            thread.start()

            return {"success": True, "job_id": job_id, "message": f"Simulation started (ID: {job_id})."}

        elif tool_name == "get_simulation_status":
            job_id = args['job_id']
            with SIMULATION_LOCK:
                status = SIMULATION_STATUS.get(job_id)
                if not status:
                    return {"success": False, "error": "Job ID not found."}
                return {
                    "success": True,
                    "status": status["status"],
                    "progress": status["progress"],
                    "total": status["total_events"]
                }

        elif tool_name == "insert_physics_template":
            template_name = args['template_name']
            if template_name not in PHYSICS_TEMPLATES:
                return {"success": False, "error": f"Template '{template_name}' not found."}

            t_info = PHYSICS_TEMPLATES[template_name]
            t_func = t_info['func']
            t_params = args['params']

            try:
                recipe = t_func(**t_params)
            except Exception as e:
                return {"success": False, "error": f"Failed to generate template: {str(e)}"}

            for solid in recipe.get('solids', []):
                pm.add_solid(solid.name, solid.type, solid.raw_parameters)

            for lv in recipe.get('logical_volumes', []):
                mat_name = lv.material_ref
                if not pm.current_geometry_state.get_material(mat_name):
                    if mat_name.startswith("G4_"):
                        pm.add_material(mat_name, {"mat_type": "nist"})
                    else:
                        return {"success": False, "error": f"Material '{mat_name}' required by template not found."}

                pm.add_logical_volume(lv.name, lv.solid_ref, lv.material_ref, is_sensitive=lv.is_sensitive)

            parent_lv_name = args['parent_lv_name']
            base_pos = to_vec_dict(args.get('position', {'x': '0', 'y': '0', 'z': '0'}))

            created_pvs = []
            for _ in recipe.get('placements', []):
                pass

            if not recipe.get('placements'):
                last_lv = recipe['logical_volumes'][-1]
                pv_res, err = pm.add_physical_volume(parent_lv_name, f"{last_lv.name}_PV", last_lv.name, base_pos, {'x': '0', 'y': '0', 'z': '0'}, {'x': '1', 'y': '1', 'z': '1'})
                if pv_res:
                    created_pvs.append(pv_res['name'])
            else:
                for p_data in recipe['placements']:
                    p_pos = p_data['position']
                    final_pos = {
                        'x': f"({p_pos['x']}) + ({base_pos['x']})",
                        'y': f"({p_pos['y']}) + ({base_pos['y']})",
                        'z': f"({p_pos['z']}) + ({base_pos['z']})"
                    }
                    pv_res, err = pm.add_physical_volume(parent_lv_name, p_data['name'], p_data['volume_ref'], final_pos, p_data['rotation'], {'x': '1', 'y': '1', 'z': '1'})
                    if pv_res:
                        created_pvs.append(pv_res['name'])

            pm.recalculate_geometry_state()
            return {"success": True, "message": f"Inserted {template_name} template into {parent_lv_name}."}

        elif tool_name == "batch_geometry_update":
            ops = args.get('operations')
            if not ops or not isinstance(ops, list):
                return {"success": False, "error": "Argument 'operations' must be a list of tool calls."}
            batch_results = []
            for op in ops:
                if not isinstance(op, dict):
                    batch_results.append({"success": False, "error": f"Invalid operation entry: {op!r}"})
                    continue

                op_tool_name = op.get('tool_name') or op.get('toolName') or op.get('tool')
                op_args = op.get('arguments') if op.get('arguments') is not None else op.get('args', {})

                batch_results.append(dispatch_ai_tool(pm, op_tool_name, op_args))
            return {"success": True, "batch_results": batch_results}

        elif tool_name == "get_analysis_summary":
            job_id = args['job_id']
            version_id = pm.current_version_id
            if not version_id:
                return {"success": False, "error": "No active version."}

            version_dir = pm._get_version_dir(version_id)
            run_dir = os.path.join(version_dir, "sim_runs", job_id)
            output_path = os.path.join(run_dir, "output.hdf5")

            if not os.path.exists(output_path):
                return {"success": False, "error": "Simulation output not yet available."}

            try:
                with h5py.File(output_path, 'r') as f:
                    if 'default_ntuples/Hits' not in f:
                        return {"success": False, "error": "No hits found in output."}

                    hits_group = f['default_ntuples/Hits']

                    def get_hits_len():
                        if 'entries' in hits_group:
                            ent = hits_group['entries']
                            return int(ent[0]) if ent.shape != () else int(ent[()])
                        return 0

                    total_hits = get_hits_len()

                    particles = {}
                    if 'ParticleName' in hits_group:
                        data = hits_group['ParticleName']
                        if isinstance(data, h5py.Group):
                            data = data['pages']
                        names = data[:total_hits]
                        for n in names:
                            n_str = n.decode('utf-8') if isinstance(n, bytes) else str(n)
                            particles[n_str] = particles.get(n_str, 0) + 1

                    return {
                        "success": True,
                        "summary": {
                            "total_hits": total_hits,
                            "particle_breakdown": particles
                        }
                    }
            except Exception as e:
                return {"success": False, "error": str(e)}

        elif tool_name == "manage_optical_surface":
            name = args['name']
            params = {
                'model': args.get('model'),
                'finish': args.get('finish'),
                'surf_type': args.get('type'),
                'value': args.get('value'),
                'properties': args.get('properties', {})
            }
            if name in pm.current_geometry_state.optical_surfaces:
                success, error = pm.update_optical_surface(name, params)
                if success:
                    return {"success": True, "message": f"Optical surface '{name}' updated."}
                return {"success": False, "error": error}
            else:
                res, error = pm.add_optical_surface(name, params)
                if res:
                    return {"success": True, "message": f"Optical surface '{res['name']}' created."}
                return {"success": False, "error": error}

        elif tool_name == "manage_surface_link":
            name = args['name']
            ltype = args['link_type']
            s_ref = args['surface_ref']

            if ltype == 'skin':
                v_ref = args.get('volume_ref')
                if not v_ref:
                    return {"success": False, "error": "'volume_ref' is required for skin surface links."}

                if name in pm.current_geometry_state.skin_surfaces:
                    success, error = pm.update_skin_surface(name, v_ref, s_ref)
                    if success:
                        return {"success": True, "message": f"Skin surface link '{name}' updated."}
                    return {"success": False, "error": error}

                res, error = pm.add_skin_surface(name, v_ref, s_ref)
                if res:
                    return {"success": True, "message": f"Skin surface link '{res['name']}' created."}
                return {"success": False, "error": error}

            if ltype == 'border':
                pv1 = args.get('pv1_id')
                pv2 = args.get('pv2_id')
                if not pv1 or not pv2:
                    return {"success": False, "error": "'pv1_id' and 'pv2_id' are required for border surface links."}

                if name in pm.current_geometry_state.border_surfaces:
                    success, error = pm.update_border_surface(name, pv1, pv2, s_ref)
                    if success:
                        return {"success": True, "message": f"Border surface link '{name}' updated."}
                    return {"success": False, "error": error}

                res, error = pm.add_border_surface(name, pv1, pv2, s_ref)
                if res:
                    return {"success": True, "message": f"Border surface link '{res['name']}' created."}
                return {"success": False, "error": error}

            return {"success": False, "error": f"Invalid link_type '{ltype}'. Expected 'skin' or 'border'."}

        elif tool_name == "manage_assembly":
            name = args['name']
            pls = args['placements']
            for p in pls:
                if 'position' in p:
                    p['position'] = to_vec_dict(p['position'])
                if 'rotation' in p:
                    p['rotation'] = to_vec_dict(p['rotation'])

            if name in pm.current_geometry_state.assemblies:
                success, error = pm.update_assembly(name, pls)
                if success:
                    return {"success": True, "message": f"Assembly '{name}' updated."}
                return {"success": False, "error": error}
            else:
                res, error = pm.add_assembly(name, pls)
                if res:
                    return {"success": True, "message": f"Assembly '{res['name']}' created."}
                return {"success": False, "error": error}

        elif tool_name == "manage_ui_group":
            gtype = args['group_type']
            gname = args['group_name']
            action = args['action']

            if action == 'create':
                success, error = pm.create_group(gtype, gname)
            elif action == 'add_items':
                success, error = pm.move_items_to_group(gtype, args.get('item_ids', []), gname)
            elif action == 'remove_group':
                success, error = pm.delete_group(gtype, gname)
            else:
                return {"success": False, "error": f"Invalid action '{action}' for manage_ui_group."}

            if success:
                return {"success": True, "message": f"UI Group action '{action}' on '{gname}' successful."}
            return {"success": False, "error": error}

        elif tool_name == "evaluate_expression":
            success, res = pm.expression_evaluator.evaluate(args['expression'])
            if success:
                return {"success": True, "result": res}
            return {"success": False, "error": res}

        elif tool_name == "rename_ui_group":
            success, error = pm.rename_group(args['group_type'], args['old_name'], args['new_name'])
            if success:
                return {"success": True, "message": f"Group '{args['old_name']}' renamed to '{args['new_name']}'."}
            return {"success": False, "error": error}

        elif tool_name == "manage_particle_source":
            action = str(args.get('action', '')).lower()
            if action in ('transform', 'move', 'set_transform'):
                action = 'update_transform'

            if action == 'create':
                new_source, error = pm.add_source(
                    args.get('name', 'gps_source'),
                    args.get('gps_commands', {}),
                    to_vec_dict(args.get('position', {'x': '0', 'y': '0', 'z': '0'})),
                    to_vec_dict(args.get('rotation', {'x': '0', 'y': '0', 'z': '0'})),
                    args.get('activity', 1.0),
                    args.get('confine_to_pv'),
                    args.get('volume_link_id')
                )
                if new_source:
                    return {
                        "success": True,
                        "message": f"Particle source '{new_source.get('name', args.get('name', 'gps_source'))}' created.",
                        "source": new_source,
                        "source_id": new_source.get('id')
                    }
                return {"success": False, "error": error}

            if action == 'update':
                source_id = args.get('source_id')
                if not source_id:
                    return {"success": False, "error": "'source_id' is required for action='update'."}

                pos = to_vec_dict(args.get('position')) if args.get('position') is not None else None
                rot = to_vec_dict(args.get('rotation')) if args.get('rotation') is not None else None

                success, error = pm.update_particle_source(
                    source_id,
                    args.get('name'),
                    args.get('gps_commands'),
                    pos,
                    rot,
                    args.get('activity'),
                    args.get('confine_to_pv'),
                    args.get('volume_link_id')
                )
                if success:
                    return {"success": True, "message": f"Particle source '{source_id}' updated."}
                return {"success": False, "error": error}

            if action == 'update_transform':
                source_id = args.get('source_id')
                if not source_id:
                    return {"success": False, "error": "'source_id' is required for action='update_transform'."}

                pos = to_vec_dict(args.get('position')) if args.get('position') is not None else None
                rot = to_vec_dict(args.get('rotation')) if args.get('rotation') is not None else None
                success, error = pm.update_source_transform(source_id, pos, rot)
                if success:
                    return {"success": True, "message": f"Particle source '{source_id}' transform updated."}
                return {"success": False, "error": error}

            return {"success": False, "error": f"Invalid action '{action}' for manage_particle_source."}

        elif tool_name == "set_active_source":
            source_id = args.get('source_id')
            if isinstance(source_id, str) and source_id.strip().lower() in ('', 'none', 'null'):
                source_id = None

            success, msg = pm.set_active_source(source_id)
            if success:
                return {"success": True, "message": msg}
            return {"success": False, "error": msg}

        elif tool_name == "process_lors":
            version_id = args.get('version_id') or pm.current_version_id
            if not version_id:
                return {"success": False, "error": "No active version. Provide 'version_id' or save the project first."}

            payload = {
                "coincidence_window_ns": args.get('coincidence_window_ns', 4.0),
                "energy_cut": args.get('energy_cut', 0.0),
                "energy_resolution": args.get('energy_resolution', 0.05),
                "position_resolution": args.get('position_resolution', {'x': 0.0, 'y': 0.0, 'z': 0.0})
            }
            status_code, body = call_route_json(process_lors_route, [version_id, args['job_id']], payload)
            if status_code >= 400 or body.get('success') is False:
                return {"success": False, "error": body.get('error', f"LOR processing failed (status {status_code}).")}
            return {"success": True, "message": body.get('message', 'LOR processing started.')}

        elif tool_name == "get_lor_status":
            status_code, body = call_route_json(get_lor_processing_status, [args['job_id']])
            if status_code >= 400 or body.get('success') is False:
                return {"success": False, "error": body.get('error', f"Could not fetch LOR status (status {status_code}).")}
            return {"success": True, "status": body.get('status', {})}

        elif tool_name == "check_lor_file":
            version_id = args.get('version_id') or pm.current_version_id
            if not version_id:
                return {"success": False, "error": "No active version. Provide 'version_id'."}
            status_code, body = call_route_json(check_lor_file_route, [version_id, args['job_id']])
            if status_code >= 400 or body.get('success') is False:
                return {"success": False, "error": body.get('error', f"Could not check LOR file (status {status_code}).")}
            return {"success": True, **body}

        elif tool_name == "run_reconstruction":
            version_id = args.get('version_id') or pm.current_version_id
            if not version_id:
                return {"success": False, "error": "No active version. Provide 'version_id' or save the project first."}

            payload = {
                "iterations": args.get('iterations', 1),
                "image_size": args.get('image_size', [128, 128, 128]),
                "voxel_size": args.get('voxel_size', [2.0, 2.0, 2.0]),
                "normalization": args.get('normalization', True),
                "ac_enabled": args.get('ac_enabled', False),
                "ac_shape": args.get('ac_shape', 'cylinder'),
                "ac_radius": args.get('ac_radius', 108.0),
                "ac_length": args.get('ac_length', 186.0),
                "ac_mu": args.get('ac_mu', 0.096)
            }
            status_code, body = call_route_json(run_reconstruction_route, [version_id, args['job_id']], payload)
            if status_code >= 400 or body.get('success') is False:
                return {"success": False, "error": body.get('error', f"Reconstruction failed (status {status_code}).")}
            return {"success": True, **body}

        elif tool_name == "compute_sensitivity":
            version_id = args.get('version_id') or pm.current_version_id
            if not version_id:
                return {"success": False, "error": "No active version. Provide 'version_id' or save the project first."}

            payload = {
                "version_id": version_id,
                "job_id": args['job_id'],
                "voxel_size": args.get('voxel_size', 2.0),
                "matrix_size": args.get('matrix_size', 128),
                "ac_enabled": args.get('ac_enabled', False),
                "ac_mu": args.get('ac_mu', 0.096),
                "ac_radius": args.get('ac_radius', 0.0),
                "num_random_lors": args.get('num_random_lors', 20000000)
            }
            status_code, body = call_route_json(compute_sensitivity_route, payload=payload)
            if status_code >= 400 or body.get('success') is False:
                return {"success": False, "error": body.get('error', f"Sensitivity computation failed (status {status_code}).")}
            return {"success": True, **body}

        elif tool_name == "get_sensitivity_status":
            version_id = args.get('version_id') or pm.current_version_id
            if not version_id:
                return {"success": False, "error": "No active version. Provide 'version_id'."}

            status_code, body = call_route_json(get_sensitivity_status_route, [version_id, args['job_id']])
            if status_code >= 400:
                return {"success": False, "error": body.get('error', f"Could not fetch sensitivity status (status {status_code}).")}
            return {"success": True, "status": body}

        elif tool_name == "stop_simulation":
            job_id = args['job_id']
            with SIMULATION_LOCK:
                process_or_list = SIMULATION_PROCESSES.get(job_id)
                if process_or_list:
                    if isinstance(process_or_list, list):
                        count = 0
                        for p in process_or_list:
                            if p.poll() is None:
                                p.terminate()
                                count += 1
                        return {"success": True, "message": f"Stop signal sent to {count} processes for job {job_id}."}

                    proc = process_or_list
                    if proc.poll() is None:
                        proc.terminate()
                        return {"success": True, "message": f"Stop signal sent to job {job_id}."}
                    return {"success": False, "error": "Job has already finished."}

                return {"success": False, "error": "Job ID not found or already completed."}

        elif tool_name == "get_simulation_metadata":
            version_id = args.get('version_id') or pm.current_version_id
            if not version_id:
                return {"success": False, "error": "No active version. Provide 'version_id'."}

            status_code, body = call_route_json(get_simulation_metadata, [version_id, args['job_id']])
            if status_code >= 400 or body.get('success') is False:
                return {"success": False, "error": body.get('error', f"Could not fetch simulation metadata (status {status_code}).")}
            return {"success": True, "metadata": body.get('metadata', {})}

        elif tool_name == "get_simulation_analysis":
            version_id = args.get('version_id') or pm.current_version_id
            if not version_id:
                return {"success": False, "error": "No active version. Provide 'version_id'."}

            query = {
                "energy_bins": args.get('energy_bins', 100),
                "spatial_bins": args.get('spatial_bins', 50)
            }
            status_code, body = call_route_json(get_simulation_analysis, [version_id, args['job_id']], query_params=query)
            if status_code >= 400 or body.get('success') is False:
                return {"success": False, "error": body.get('error', f"Could not fetch simulation analysis (status {status_code}).")}
            return {"success": True, "analysis": body.get('analysis', {})}

        return {"success": False, "error": f"Unknown tool: {tool_name}"}
    except Exception as e:
        traceback.print_exc()
        return {"success": False, "error": str(e)}

@app.route('/api/ai/chat', methods=['POST'])
def ai_chat_route():
    pm = get_project_manager_for_session()
    data = request.get_json()
    user_message = data.get('message')
    model_id = data.get('model', 'models/gemini-2.0-flash-exp') 
    turn_limit = data.get('turn_limit', 10)
    
    if not user_message:
        return jsonify({"success": False, "error": "No message provided."}), 400

    # Determine if we are using Gemini or Ollama
    is_gemini = model_id.startswith("models/")

    # Initialize chat history if empty
    if not pm.chat_history:
        system_prompt = load_system_prompt()
        if is_gemini:
            pm.chat_history = [
                {"role": "user", "parts": [{"text": system_prompt}]},
                {"role": "model", "parts": [{"text": "Understood. I am AIRPET AI, your detector design assistant. I have my tools ready."}]}
            ]
        else: # Ollama format
            pm.chat_history = [
                {"role": "system", "content": system_prompt},
                {"role": "assistant", "content": "Understood. I am AIRPET AI, your detector design assistant."}
            ]
    
    context_summary = pm.get_summarized_context()
    formatted_user_msg = f"[System Context Update]\n{context_summary}\n\nUser Message: {user_message}"

    if is_gemini:
        client_instance = get_gemini_client_for_session()
        if not client_instance:
            return jsonify({"success": False, "error": "Gemini client not configured. Check your API key."}), 500

        pm.chat_history.append({
            "role": "user", 
            "parts": [{"text": formatted_user_msg}],
            "metadata": {"model_id": model_id, "original_message": user_message} # Store original message for UI
        })

        # --- OPTIMIZATION: Start Transaction ---
        pm.begin_transaction()

        try:
            # Sanitize history for Gemini API (remove our custom metadata)
            sanitized_history = []
            for msg in pm.chat_history:
                sanitized_msg = {
                    "role": msg["role"],
                    "parts": msg["parts"]
                }
                sanitized_history.append(sanitized_msg)

            job_id = None
            version_id = None

            for turn in range(turn_limit):
                # Add a small delay to avoid hitting rate limits on free-tier keys
                time.sleep(1)
                
                print(f"AI Turn {turn+1}/{turn_limit}...")
                try:
                    response = client_instance.models.generate_content(
                        model=model_id,
                        contents=sanitized_history,
                        config=types.GenerateContentConfig(
                            tools=[{"function_declarations": AI_GEOMETRY_TOOLS}]
                        )
                    )
                except Exception as api_err:
                    pm.end_transaction("Gemini API Error")
                    raise api_err
                
                # Update sanitized history with model response
                sanitized_history.append(response.candidates[0].content)
                # And update our persistent history (keeping it as a simple list of dicts for JSON compat)
                pm.chat_history.append({
                    "role": response.candidates[0].content.role,
                    "parts": [{"text": p.text} for p in response.candidates[0].content.parts if p.text] or \
                             [{"function_call": {"name": p.function_call.name, "args": p.function_call.args}} for p in response.candidates[0].content.parts if p.function_call]
                })
                
                tool_calls = response.candidates[0].content.parts
                has_tool_call = False
                tool_results_parts = []
                
                for part in tool_calls:
                    if part.function_call:
                        has_tool_call = True
                        tool_name = part.function_call.name
                        args = part.function_call.args
                        
                        print(f"AI Calling Tool: {tool_name}")
                        result = dispatch_ai_tool(pm, tool_name, args)
                        
                        # Capture simulation metadata for the frontend
                        if "job_id" in result: job_id = result["job_id"]
                        if "version_id" in result: version_id = result["version_id"]
                        
                        tool_results_parts.append(types.Part.from_function_response(
                            name=tool_name,
                            response=result
                        ))

                if not has_tool_call:
                    # End the transaction before responding
                    pm.end_transaction(f"AI: {user_message[:50]}")
                    
                    res_obj = create_success_response(pm, response.text)
                    # Re-inject captured job metadata into the final response
                    if job_id:
                        res_json = res_obj.get_json()
                        res_json['job_id'] = job_id
                        res_json['version_id'] = version_id or pm.current_version_id
                        return jsonify(res_json)
                    return res_obj
                
                # Add results to both histories
                tool_content = types.Content(role="user", parts=tool_results_parts)
                sanitized_history.append(tool_content)
                pm.chat_history.append({
                    "role": "user",
                    "parts": [{"function_response": {"name": p.function_response.name, "response": p.function_response.response}} for p in tool_results_parts]
                })

            pm.end_transaction("AI Timeout")
            return create_success_response(pm, "Too many tool iterations.")

        except Exception as e:
            pm.end_transaction("AI Error")
            traceback.print_exc()
            err_msg = str(e)
            status_code = 500
            if "429" in err_msg or "ResourceExhausted" in err_msg or "Quota" in err_msg:
                err_msg = f"AI Rate Limit Exceeded (429): {err_msg}. Please wait a moment before trying again."
                status_code = 429
            return jsonify({"success": False, "error": err_msg}), status_code

    else: # Ollama Path
        pm.chat_history.append({
            "role": "user", 
            "content": formatted_user_msg,
            "metadata": {"model_id": model_id, "original_message": user_message} # Store original message for UI
        })

        pm.begin_transaction()

        try:
            # Map tool schema to Ollama format (Ollama uses OpenAI-like tool schema)
            ollama_tools = []
            for tool in AI_GEOMETRY_TOOLS:
                ollama_tools.append({
                    "type": "function",
                    "function": {
                        "name": tool["name"],
                        "description": tool["description"],
                        "parameters": tool["parameters"]
                    }
                })

            # --- DEBUG: Dump payload to file ---
            try:
                debug_payload = {
                    "model": model_id,
                    "messages": pm.chat_history,
                    "tools": ollama_tools
                }
                with open("ai_debug_payload.json", "w") as df:
                    json.dump(debug_payload, df, indent=2, default=str)
            except Exception as e:
                print(f"Warning: Could not write debug payload: {e}")
            # -----------------------------------

            # Sanitize history for Ollama API (remove metadata)
            sanitized_history = []
            for msg in pm.chat_history:
                sanitized_msg = {
                    "role": msg["role"],
                    "content": msg.get("content") or msg.get("parts", [{}])[0].get("text", "")
                }
                sanitized_history.append(sanitized_msg)

            job_id = None
            version_id = None

            # Tool loop for Ollama
            for turn in range(turn_limit):
                time.sleep(1)
                print(f"Ollama Turn {turn+1}/{turn_limit}...")
                
                try:
                    response = ollama.chat(
                        model=model_id,
                        messages=sanitized_history,
                        tools=ollama_tools
                    )
                except Exception as ollama_err:
                    pm.end_transaction("Ollama API Error")
                    raise ollama_err
                
                # Convert Ollama Message object to a plain dict for serialization
                raw_assistant_msg = response['message']
                assistant_msg = {
                    "role": getattr(raw_assistant_msg, 'role', 'assistant'),
                    "content": getattr(raw_assistant_msg, 'content', ""),
                }
                if hasattr(raw_assistant_msg, 'tool_calls') and raw_assistant_msg.tool_calls:
                    assistant_msg["tool_calls"] = [
                        {
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments
                            }
                        } for tc in raw_assistant_msg.tool_calls
                    ]
                
                sanitized_history.append(assistant_msg)
                # Keep persistent history simple
                pm.chat_history.append(assistant_msg)
                
                if not assistant_msg.get('tool_calls'):
                    pm.end_transaction(f"AI: {user_message[:50]}")
                    return create_success_response(pm, assistant_msg['content'])

                # Process tool calls
                for tool_call in assistant_msg['tool_calls']:
                    f_name = tool_call['function']['name']
                    f_args = tool_call['function']['arguments']
                    
                    print(f"Ollama AI Calling Tool: {f_name}")
                    result = dispatch_ai_tool(pm, f_name, f_args)
                    
                    if "job_id" in result: job_id = result["job_id"]
                    if "version_id" in result: version_id = result["version_id"]
                    
                    tool_res = {
                        "role": "tool",
                        "content": json.dumps(result)
                    }
                    sanitized_history.append(tool_res)
                    pm.chat_history.append(tool_res)
            
            pm.end_transaction("AI Timeout")
            return create_success_response(pm, "Too many tool iterations (Ollama).")

        except Exception as e:
            pm.end_transaction("AI Error")
            traceback.print_exc()
            err_msg = str(e)
            status_code = 500
            if "429" in err_msg:
                err_msg = f"Local AI Overloaded (429): {err_msg}."
                status_code = 429
            return jsonify({"success": False, "error": err_msg}), status_code

@app.route('/api/ai/history', methods=['GET'])
def get_ai_history():
    pm = get_project_manager_for_session()
    
    # Helper to sanitize data for JSON serialization
    def sanitize_for_json(obj):
        if isinstance(obj, dict):
            return {str(k): sanitize_for_json(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [sanitize_for_json(i) for i in obj]
        elif isinstance(obj, (str, int, float, bool, type(None))):
            return obj
        elif hasattr(obj, 'to_dict'): # Handle objects with to_dict method
            return sanitize_for_json(obj.to_dict())
        else:
            # Handle Gemini SDK objects (Part, Content, etc.) or unknown types
            res = {}
            if hasattr(obj, 'role'): res['role'] = obj.role
            if hasattr(obj, 'parts'):
                res['parts'] = []
                for p in obj.parts:
                    part_data = {}
                    if hasattr(p, 'text') and p.text: part_data['text'] = p.text
                    if hasattr(p, 'function_call') and p.function_call:
                        part_data['function_call'] = {
                            'name': p.function_call.name,
                            'args': sanitize_for_json(p.function_call.args)
                        }
                    if hasattr(p, 'function_response') and p.function_response:
                        part_data['function_response'] = {
                            'name': p.function_response.name,
                            'response': sanitize_for_json(p.function_response.response)
                        }
                    if part_data: res['parts'].append(part_data)
            
            if res: return res
            return str(obj) # Fallback to string representation

    serializable_history = [sanitize_for_json(msg) for msg in pm.chat_history]
    return jsonify({"history": serializable_history})

@app.route('/api/ai/clear', methods=['POST'])
def clear_ai_history():
    pm = get_project_manager_for_session()
    pm.chat_history = []
    return jsonify({"success": True})

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
    # Read the key from the user's session
    api_key = session.get("gemini_api_key", "")
    
    # SECURITY: Do not send the actual server key back to the client.
    is_server_managed = False
    if SERVER_GEMINI_API_KEY and api_key == SERVER_GEMINI_API_KEY:
        api_key = "" # Mask the key
        is_server_managed = True
        
    return jsonify({
        "api_key": api_key,
        "is_server_managed": is_server_managed
    })

# --- Route to set a new API key ---
@app.route('/api/set_gemini_key', methods=['POST'])
def set_gemini_key():
    data = request.get_json()
    new_key = data.get('api_key', '').strip()

    if not new_key:
        # If the user clears the key, revert to the server key if available
        if SERVER_GEMINI_API_KEY:
            session['gemini_api_key'] = SERVER_GEMINI_API_KEY
            msg = "API Key reset to server default."
        else:
            session['gemini_api_key'] = ""
            msg = "API Key cleared."
    else:
        # Store the user's custom key
        session['gemini_api_key'] = new_key
        msg = "Custom API Key updated."
    
    # Attempt to configure the client to validate the key
    client_instance = get_gemini_client_for_session()

    if client_instance:
        return jsonify({"success": True, "message": f"{msg} Client configured successfully."})
    elif not session.get('gemini_api_key'):
         return jsonify({"success": True, "message": msg})
    else:
        # The key was set, but validation failed
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

# Route for terms/privacy policy
@app.route('/legal')
def legal_page():
    return render_template('legal.html')
    
# --- Scheduler to run the cleanup task ---
scheduler = sched.scheduler(time.time, time.sleep)

# Start the scheduler in a background thread
scheduler_thread = threading.Thread(target=run_cleanup_scheduler, args=(scheduler,))
scheduler_thread.daemon = True
scheduler_thread.start()

if __name__ == '__main__':
    app.run(debug=True, port=5003)