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
import tempfile
from pathlib import Path

from datetime import datetime
from flask import Flask, request, jsonify, render_template, Response, session, send_file
from flask_cors import CORS
from typing import Dict, Any, List, Optional, Tuple

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
from src.surrogate_dataset import build_surrogate_dataset_from_payloads
from src.surrogate_experiment import run_surrogate_experiment, run_surrogate_experiment_from_path
from src.surrogate_synthetic import generate_synthetic_surrogate_benchmark
from src.objective_engine import extract_objective_values_from_hdf5
from src.objective_formula import get_allowed_formula_functions
from src.ai_backend_adapters import (
    ADAPTER_CONTRACT_VERSION,
    LlamaCppAdapterConfig,
    LMStudioAdapterConfig,
    TextGenerationRequest,
    TextMessage,
    invoke_text_request_for_backend,
    select_backend_for_text_request,
)
from src.ai_artifact_store import (
    ARTIFACT_STORE_SCHEMA_VERSION,
    AIArtifactStore,
    AIArtifactValidationError,
)
from src.ai_multimodal_extraction_schema import (
    AIMultimodalSchemaValidationError,
    MULTIMODAL_EXTRACTION_SCHEMA_VERSION,
    MULTIMODAL_REVIEW_ENVELOPE_SCHEMA_VERSION,
    build_review_envelope,
    normalize_extraction_payload,
)
from src.ai_multimodal_planning_schema import (
    MULTIMODAL_PLANNING_ENVELOPE_SCHEMA_VERSION,
    build_planning_envelope,
)
from src.ai_multimodal_operation_bridge import (
    MULTIMODAL_PLANNING_EXECUTION_PLAN_SCHEMA_VERSION,
    build_geometry_execution_plan,
)

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

# --------------------------------------------------------------------------
# Run policy guardrails (Phase A: safety defaults)
RUN_POLICY_MAX_BUDGET = max(1, int(os.getenv("RUN_POLICY_MAX_BUDGET", "200")))
RUN_POLICY_MAX_EVENTS_PER_CANDIDATE = max(1, int(os.getenv("RUN_POLICY_MAX_EVENTS_PER_CANDIDATE", "50000")))
RUN_POLICY_MAX_THREADS = max(1, int(os.getenv("RUN_POLICY_MAX_THREADS", "8")))
RUN_POLICY_MAX_TOTAL_EVENTS = max(1, int(os.getenv("RUN_POLICY_MAX_TOTAL_EVENTS", "2000000")))
RUN_POLICY_MAX_WARMUP_RUNS = max(1, int(os.getenv("RUN_POLICY_MAX_WARMUP_RUNS", "100")))
RUN_POLICY_MAX_CANDIDATE_POOL_SIZE = max(8, int(os.getenv("RUN_POLICY_MAX_CANDIDATE_POOL_SIZE", "4096")))
RUN_POLICY_MAX_WALL_TIME_SECONDS = max(60, int(os.getenv("RUN_POLICY_MAX_WALL_TIME_SECONDS", "3600")))
RUN_POLICY_DEFAULT_WALL_TIME_SECONDS = max(
    60,
    min(RUN_POLICY_MAX_WALL_TIME_SECONDS, int(os.getenv("RUN_POLICY_DEFAULT_WALL_TIME_SECONDS", "900")))
)
RUN_POLICY_REQUIRE_ALLOW_APPLY = os.getenv("RUN_POLICY_REQUIRE_ALLOW_APPLY", "true").strip().lower() in {"1", "true", "yes", "on"}
RUN_POLICY_DEFAULT_APPLY_TO_PROJECT = os.getenv("RUN_POLICY_DEFAULT_APPLY_TO_PROJECT", "false").strip().lower() in {"1", "true", "yes", "on"}
RUN_POLICY_REQUIRE_VERIFY_TOKEN = os.getenv("RUN_POLICY_REQUIRE_VERIFY_TOKEN", "true").strip().lower() in {"1", "true", "yes", "on"}
RUN_POLICY_VERIFY_TOKEN_TTL_SECONDS = max(60, int(os.getenv("RUN_POLICY_VERIFY_TOKEN_TTL_SECONDS", "3600")))
RUN_POLICY_VERIFY_MIN_REPEATS = max(1, int(os.getenv("RUN_POLICY_VERIFY_MIN_REPEATS", "3")))
RUN_POLICY_VERIFY_MIN_SUCCESS_RATE = float(os.getenv("RUN_POLICY_VERIFY_MIN_SUCCESS_RATE", "1.0"))
RUN_POLICY_VERIFY_MAX_STD_RAW = os.getenv("RUN_POLICY_VERIFY_MAX_STD", "").strip()
RUN_POLICY_VERIFY_MAX_STD = float(RUN_POLICY_VERIFY_MAX_STD_RAW) if RUN_POLICY_VERIFY_MAX_STD_RAW else None

APPLY_VERIFY_TOKENS = {}
APPLY_VERIFY_TOKENS_LOCK = threading.Lock()

APPLY_AUDIT_LOGS = {}
APPLY_AUDIT_LOCK = threading.Lock()
APPLY_AUDIT_MAX_ENTRIES = max(10, int(os.getenv("RUN_POLICY_APPLY_AUDIT_MAX_ENTRIES", "100")))
APPLY_AUDIT_STORAGE_FILE = os.getenv(
    "RUN_POLICY_APPLY_AUDIT_STORAGE_FILE",
    os.path.join(PROJECTS_BASE_DIR, ".apply_audit_logs.json"),
)


def _current_user_id_for_policy():
    return session.get('user_id') or 'local_user'


def _project_scope_id_for_policy(pm: Optional[ProjectManager]) -> str:
    scope_id = None
    if pm and pm.current_geometry_state is not None:
        scope_id = getattr(pm.current_geometry_state, 'project_scope_id', None)
        if not scope_id:
            scope_id = str(uuid.uuid4())
            setattr(pm.current_geometry_state, 'project_scope_id', scope_id)
    return str(scope_id or "default-scope")


def _load_apply_audit_logs_from_disk() -> Dict[str, Dict[str, List[Dict[str, Any]]]]:
    path = APPLY_AUDIT_STORAGE_FILE
    if not path:
        return {}

    try:
        if not os.path.exists(path):
            return {}
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as exc:
        print(f"Warning: failed to load apply audit storage '{path}': {exc}")
        return {}

    if not isinstance(data, dict):
        return {}

    normalized: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}
    for user_id, scopes in data.items():
        user_key = str(user_id)
        normalized[user_key] = {}

        # Back-compat with legacy shape: {user_id: [records...]}
        if isinstance(scopes, list):
            clean_entries = [e for e in scopes if isinstance(e, dict)]
            if len(clean_entries) > APPLY_AUDIT_MAX_ENTRIES:
                clean_entries = clean_entries[-APPLY_AUDIT_MAX_ENTRIES:]
            normalized[user_key]["default-scope"] = clean_entries
            continue

        if not isinstance(scopes, dict):
            continue

        for scope_id, entries in scopes.items():
            if not isinstance(entries, list):
                continue
            scope_key = str(scope_id)
            clean_entries = [e for e in entries if isinstance(e, dict)]
            if len(clean_entries) > APPLY_AUDIT_MAX_ENTRIES:
                clean_entries = clean_entries[-APPLY_AUDIT_MAX_ENTRIES:]
            normalized[user_key][scope_key] = clean_entries

    return normalized


def _persist_apply_audit_logs_locked() -> None:
    path = APPLY_AUDIT_STORAGE_FILE
    if not path:
        return

    try:
        storage_dir = os.path.dirname(path)
        if storage_dir:
            os.makedirs(storage_dir, exist_ok=True)
        tmp_path = f"{path}.tmp"
        with open(tmp_path, 'w', encoding='utf-8') as f:
            json.dump(APPLY_AUDIT_LOGS, f, indent=2, sort_keys=True)
        os.replace(tmp_path, path)
    except Exception as exc:
        print(f"Warning: failed to persist apply audit storage '{path}': {exc}")


def _initialize_apply_audit_logs() -> None:
    loaded = _load_apply_audit_logs_from_disk()
    with APPLY_AUDIT_LOCK:
        APPLY_AUDIT_LOGS.clear()
        APPLY_AUDIT_LOGS.update(loaded)


def _cleanup_expired_verify_tokens(user_id):
    now = time.time()
    with APPLY_VERIFY_TOKENS_LOCK:
        user_tokens = APPLY_VERIFY_TOKENS.get(user_id, {})
        stale = [tok for tok, rec in user_tokens.items() if rec.get('expires_at', 0) <= now or rec.get('used')]
        for tok in stale:
            user_tokens.pop(tok, None)
        if not user_tokens and user_id in APPLY_VERIFY_TOKENS:
            APPLY_VERIFY_TOKENS.pop(user_id, None)


def _issue_verify_token(user_id, run_id, verification_record):
    token = str(uuid.uuid4())
    now = time.time()
    expires_at = now + RUN_POLICY_VERIFY_TOKEN_TTL_SECONDS

    rec = {
        'token': token,
        'run_id': run_id,
        'issued_at': now,
        'expires_at': expires_at,
        'used': False,
        'verification_record': verification_record,
    }

    with APPLY_VERIFY_TOKENS_LOCK:
        user_tokens = APPLY_VERIFY_TOKENS.setdefault(user_id, {})
        user_tokens[token] = rec

    return rec


def _consume_verify_token(user_id, run_id, token):
    if not token:
        return None, "verification_token is required when apply_to_project=true."

    _cleanup_expired_verify_tokens(user_id)

    with APPLY_VERIFY_TOKENS_LOCK:
        user_tokens = APPLY_VERIFY_TOKENS.get(user_id, {})
        rec = user_tokens.get(token)
        if not rec:
            return None, "verification_token is missing, expired, or invalid."
        if rec.get('used'):
            return None, "verification_token has already been used."
        if rec.get('run_id') != run_id:
            return None, "verification_token does not match run_id."
        if rec.get('expires_at', 0) <= time.time():
            user_tokens.pop(token, None)
            return None, "verification_token has expired."

        rec['used'] = True
        rec['used_at'] = time.time()
        return rec, None


def _append_apply_audit_record(user_id, scope_id, record):
    now = datetime.utcnow().isoformat() + 'Z'
    rec = {
        'audit_id': str(uuid.uuid4()),
        'created_at': now,
        'rolled_back': False,
        **(record or {}),
    }

    user_key = str(user_id or 'local_user')
    scope_key = str(scope_id or 'default-scope')

    with APPLY_AUDIT_LOCK:
        user_scopes = APPLY_AUDIT_LOGS.setdefault(user_key, {})
        entries = user_scopes.setdefault(scope_key, [])
        entries.append(rec)
        if len(entries) > APPLY_AUDIT_MAX_ENTRIES:
            del entries[:-APPLY_AUDIT_MAX_ENTRIES]
        _persist_apply_audit_logs_locked()

    return rec


def _list_apply_audit_records(user_id, scope_id, limit=20):
    lim = max(1, min(int(limit or 20), 200))
    user_key = str(user_id or 'local_user')
    scope_key = str(scope_id or 'default-scope')

    with APPLY_AUDIT_LOCK:
        user_scopes = APPLY_AUDIT_LOGS.get(user_key, {})
        entries = list(user_scopes.get(scope_key, [])) if isinstance(user_scopes, dict) else []

        # Back-compat fallback for legacy records loaded into default-scope.
        if not entries and scope_key != "default-scope" and isinstance(user_scopes, dict):
            legacy_entries = user_scopes.get("default-scope", [])
            if isinstance(legacy_entries, list):
                entries = list(legacy_entries)

    entries = sorted(entries, key=lambda r: r.get('created_at', ''), reverse=True)
    return entries[:lim]


def _mark_apply_audit_rolled_back(user_id, scope_id, audit_id):
    user_key = str(user_id or 'local_user')
    scope_key = str(scope_id or 'default-scope')

    with APPLY_AUDIT_LOCK:
        user_scopes = APPLY_AUDIT_LOGS.get(user_key, {})
        entries = user_scopes.get(scope_key, []) if isinstance(user_scopes, dict) else []
        for rec in entries:
            if rec.get('audit_id') == audit_id:
                if rec.get('rolled_back'):
                    return rec
                rec['rolled_back'] = True
                rec['rolled_back_at'] = datetime.utcnow().isoformat() + 'Z'
                _persist_apply_audit_logs_locked()
                return rec
    return None


_initialize_apply_audit_logs()


def _run_policy_limits():
    return {
        "max_budget": RUN_POLICY_MAX_BUDGET,
        "max_events_per_candidate": RUN_POLICY_MAX_EVENTS_PER_CANDIDATE,
        "max_threads": RUN_POLICY_MAX_THREADS,
        "max_total_events": RUN_POLICY_MAX_TOTAL_EVENTS,
        "max_warmup_runs": RUN_POLICY_MAX_WARMUP_RUNS,
        "max_candidate_pool_size": RUN_POLICY_MAX_CANDIDATE_POOL_SIZE,
        "max_wall_time_seconds": RUN_POLICY_MAX_WALL_TIME_SECONDS,
        "default_wall_time_seconds": RUN_POLICY_DEFAULT_WALL_TIME_SECONDS,
        "require_allow_apply": RUN_POLICY_REQUIRE_ALLOW_APPLY,
        "default_apply_to_project": RUN_POLICY_DEFAULT_APPLY_TO_PROJECT,
        "require_verify_token": RUN_POLICY_REQUIRE_VERIFY_TOKEN,
        "verify_token_ttl_seconds": RUN_POLICY_VERIFY_TOKEN_TTL_SECONDS,
        "verify_min_repeats": RUN_POLICY_VERIFY_MIN_REPEATS,
        "verify_min_success_rate": RUN_POLICY_VERIFY_MIN_SUCCESS_RATE,
        "verify_max_std": RUN_POLICY_VERIFY_MAX_STD,
        "apply_audit_max_entries": APPLY_AUDIT_MAX_ENTRIES,
        "apply_audit_storage_file": APPLY_AUDIT_STORAGE_FILE,
    }


def _objective_builder_schema():
    formula_functions = get_allowed_formula_functions()

    return {
        "version": "m6-objective-builder-v1",
        "endpoints": {
            "schema": "/api/objective_builder/schema",
            "example": "/api/objective_builder/example?template=weighted_tradeoff",
            "validate": "/api/objective_builder/validate",
            "build": "/api/objective_builder/build",
            "upsert_study": "/api/objective_builder/upsert_study",
            "launch": "/api/objective_builder/launch",
            "extract_objectives": "/api/objectives/extract/<version_id>/<job_id>",
            "run_sim_loop": "/api/param_optimizer/run_simulation_in_loop",
            "run_sim_loop_head_to_head": "/api/param_optimizer/head_to_head_simulation_in_loop",
            "verify_best": "/api/param_optimizer/verify_best",
            "replay_best": "/api/param_optimizer/replay_best",
        },
        "formula": {
            "allowed_functions": formula_functions,
            "notes": [
                "Formulas may reference previously computed objective names.",
                "Formulas may reference context variables and parameter aliases used in study objectives.",
            ],
            "examples": [
                "0.8*edep_sum - 0.2*cost_norm",
                "log(1 + max(edep_sum, 0)) - 0.1*distance_norm",
                "clip(signal_efficiency, 0, 1) - 0.05*cost_norm",
            ],
        },
        "simulation_extract_metrics": [
            {
                "metric": "hdf5_reduce",
                "label": "Reduce HDF5 dataset",
                "required_fields": ["name", "metric", "dataset_path", "reduce"],
                "optional_fields": ["q"],
                "reduce_options": ["sum", "mean", "max", "min", "std", "count", "count_nonzero", "fraction_nonzero", "quantile"],
            },
            {
                "metric": "context_value",
                "label": "Context value",
                "required_fields": ["name", "metric", "key"],
                "optional_fields": ["default"],
            },
            {
                "metric": "constant",
                "label": "Constant numeric value",
                "required_fields": ["name", "metric", "value"],
            },
            {
                "metric": "formula",
                "label": "Formula from extracted values",
                "required_fields": ["name", "metric", "expression"],
                "optional_fields": ["expr"],
            },
        ],
        "study_objective_metrics": [
            {
                "metric": "sim_metric",
                "label": "Simulation metric from extracted map",
                "required_fields": ["name", "metric", "key", "direction"],
                "direction_options": ["maximize", "minimize"],
            },
            {
                "metric": "parameter_value",
                "label": "Parameter value",
                "required_fields": ["name", "metric", "parameter", "direction"],
                "direction_options": ["maximize", "minimize"],
            },
            {
                "metric": "formula",
                "label": "Formula objective",
                "required_fields": ["name", "metric", "expression", "direction"],
                "optional_fields": ["expr"],
                "direction_options": ["maximize", "minimize"],
            },
        ],
        "templates": [
            {
                "id": "weighted_tradeoff",
                "label": "Weighted tradeoff (performance - cost)",
                "extract_objectives": [
                    {"name": "edep_sum", "metric": "hdf5_reduce", "dataset_path": "default_ntuples/Hits/Edep", "reduce": "sum"},
                    {"name": "cost_norm", "metric": "context_value", "key": "cost_norm", "default": 0.0},
                ],
                "study_objectives": [
                    {"name": "edep_sum", "metric": "sim_metric", "key": "edep_sum", "direction": "maximize"},
                    {"name": "score", "metric": "formula", "expression": "0.8*edep_sum - 0.2*cost_norm", "direction": "maximize"},
                ],
            }
        ],
        "run_policy": _run_policy_limits(),
    }


def _objective_builder_example_payload(pm: Optional[ProjectManager], template_id: str = 'weighted_tradeoff'):
    schema = _objective_builder_schema()
    templates = schema.get('templates', []) or []

    selected = None
    for t in templates:
        if isinstance(t, dict) and t.get('id') == template_id:
            selected = t
            break

    if selected is None and templates:
        selected = templates[0]
    if selected is None:
        selected = {
            'id': 'weighted_tradeoff',
            'extract_objectives': [],
            'study_objectives': [],
        }

    study_parameters = []
    if pm and pm.current_geometry_state:
        registry = pm.current_geometry_state.parameter_registry or {}
        study_parameters = sorted(registry.keys())

    if not study_parameters:
        study_parameters = ['p1']

    example = {
        'template_id': selected.get('id', template_id),
        'study_name': f"{selected.get('id', 'objective')}_study",
        'study_mode': 'random',
        'study_parameters': study_parameters,
        'study_random': {
            'samples': 20,
            'seed': 42,
        },
        'extract_objectives': list(selected.get('extract_objectives', []) or []),
        'study_objectives': list(selected.get('study_objectives', []) or []),
        'context': {
            'cost_norm': 0.0,
        },
        'run_method': 'surrogate_gp',
        'run_budget': 20,
        'run_seed': 42,
        'sim_params': {
            'events': 1000,
            'threads': 1,
            'save_hits': True,
            'save_particles': True,
            'hit_energy_threshold': '1 eV',
        },
        'surrogate': {
            'warmup_runs': 4,
            'candidate_pool_size': 128,
            'exploration_beta': 1.0,
        },
    }

    return example


def _validate_formula_expression_for_builder(expression: Any):
    if not isinstance(expression, str) or not expression.strip():
        return False, "Formula expression must be a non-empty string.", []

    allowed_funcs = set(get_allowed_formula_functions())
    try:
        tree = ast.parse(expression, mode='eval')
    except Exception as e:
        return False, f"Invalid formula syntax: {e}", []

    allowed_nodes = (
        ast.Expression,
        ast.BinOp,
        ast.UnaryOp,
        ast.Call,
        ast.Name,
        ast.Load,
        ast.Constant,
        ast.Add,
        ast.Sub,
        ast.Mult,
        ast.Div,
        ast.Pow,
        ast.Mod,
        ast.UAdd,
        ast.USub,
    )

    var_names = set()

    for node in ast.walk(tree):
        if not isinstance(node, allowed_nodes):
            return False, f"Unsupported expression element '{type(node).__name__}'.", []

        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name):
                return False, "Only simple function names are allowed in formulas.", []
            if node.func.id not in allowed_funcs:
                return False, f"Function '{node.func.id}' is not allowed.", []
            if node.keywords:
                return False, "Keyword arguments are not allowed in formulas.", []

        if isinstance(node, ast.Name):
            if node.id not in allowed_funcs:
                var_names.add(node.id)

    return True, None, sorted(var_names)


def _validate_objective_builder_payload(payload, pm: Optional[ProjectManager] = None):
    data = dict(payload or {})
    errors = []
    warnings = []

    extract_objectives = data.get('extract_objectives')
    if extract_objectives is None:
        extract_objectives = data.get('sim_objectives', [])
    if extract_objectives is None:
        extract_objectives = []

    study_objectives = data.get('study_objectives') or []
    study_parameters = data.get('study_parameters') or []

    if not isinstance(extract_objectives, list):
        errors.append("extract_objectives must be a list.")
        extract_objectives = []
    if not isinstance(study_objectives, list):
        errors.append("study_objectives must be a list.")
        study_objectives = []
    if study_parameters and not isinstance(study_parameters, list):
        errors.append("study_parameters must be a list when provided.")
        study_parameters = []

    extract_metric_specs = {m['metric']: m for m in _objective_builder_schema().get('simulation_extract_metrics', [])}
    study_metric_specs = {m['metric']: m for m in _objective_builder_schema().get('study_objective_metrics', [])}

    extract_names = []
    extract_name_set = set()

    for i, obj in enumerate(extract_objectives):
        if not isinstance(obj, dict):
            errors.append(f"extract_objectives[{i}] must be an object.")
            continue

        name = obj.get('name')
        metric = obj.get('metric')

        if not name:
            errors.append(f"extract_objectives[{i}] is missing required field 'name'.")
            continue
        if name in extract_name_set:
            errors.append(f"Duplicate extract objective name '{name}'.")
        extract_name_set.add(name)
        extract_names.append(name)

        if metric not in extract_metric_specs:
            errors.append(f"extract_objectives[{i}] metric '{metric}' is not supported.")
            continue

        required = extract_metric_specs[metric].get('required_fields', [])
        for field in required:
            val = obj.get(field)
            if val is None or (isinstance(val, str) and not val.strip()):
                errors.append(f"extract_objectives[{i}] metric '{metric}' requires field '{field}'.")

        if metric == 'hdf5_reduce':
            reduce_op = obj.get('reduce')
            allowed_reduce = set(extract_metric_specs[metric].get('reduce_options', []))
            if reduce_op not in allowed_reduce:
                errors.append(f"extract_objectives[{i}] reduce='{reduce_op}' is invalid.")
            if reduce_op == 'quantile' and obj.get('q') is None:
                warnings.append(f"extract_objectives[{i}] uses quantile reduce without 'q'; default quantile may be used.")

        if metric == 'formula':
            expr = obj.get('expression') or obj.get('expr')
            ok, err, vars_used = _validate_formula_expression_for_builder(expr)
            if not ok:
                errors.append(f"extract_objectives[{i}] formula invalid: {err}")
            else:
                known = set(extract_names[:-1])
                unknown = [v for v in vars_used if v not in known]
                if unknown:
                    warnings.append(
                        f"extract_objectives[{i}] formula references names not yet defined earlier in extract list: {unknown}"
                    )

    if study_objectives:
        if not study_parameters:
            warnings.append("study_parameters not provided; parameter reference checks are limited.")

        registry_names = set()
        if pm and pm.current_geometry_state:
            registry_names = set((pm.current_geometry_state.parameter_registry or {}).keys())

        for i, obj in enumerate(study_objectives):
            if not isinstance(obj, dict):
                errors.append(f"study_objectives[{i}] must be an object.")
                continue

            metric = obj.get('metric')
            name = obj.get('name')
            direction = obj.get('direction', 'maximize')

            if not name:
                errors.append(f"study_objectives[{i}] missing required field 'name'.")
            if metric not in study_metric_specs:
                errors.append(f"study_objectives[{i}] metric '{metric}' is not supported in objective builder MVP.")
                continue
            if direction not in {'maximize', 'minimize'}:
                errors.append(f"study_objectives[{i}] has invalid direction '{direction}'.")

            required = study_metric_specs[metric].get('required_fields', [])
            for field in required:
                val = obj.get(field)
                if val is None or (isinstance(val, str) and not val.strip()):
                    errors.append(f"study_objectives[{i}] metric '{metric}' requires field '{field}'.")

            if metric == 'parameter_value':
                pname = obj.get('parameter')
                if pname and study_parameters and pname not in study_parameters:
                    errors.append(f"study_objectives[{i}] parameter '{pname}' not found in study_parameters.")
                if pname and registry_names and pname not in registry_names:
                    warnings.append(f"study_objectives[{i}] parameter '{pname}' is not in current parameter registry.")

            if metric == 'sim_metric':
                key = obj.get('key')
                if key and key not in extract_name_set:
                    warnings.append(f"study_objectives[{i}] sim_metric key '{key}' not found in extract_objectives names.")

            if metric == 'formula':
                expr = obj.get('expression') or obj.get('expr')
                ok, err, vars_used = _validate_formula_expression_for_builder(expr)
                if not ok:
                    errors.append(f"study_objectives[{i}] formula invalid: {err}")
                else:
                    known = set(extract_names)
                    known.update(study_parameters if isinstance(study_parameters, list) else [])
                    known.update([x.get('name') for x in study_objectives[:i] if isinstance(x, dict) and x.get('name')])
                    unknown = [v for v in vars_used if v not in known]
                    if unknown:
                        warnings.append(
                            f"study_objectives[{i}] formula references unknown names (check ordering/aliases): {unknown}"
                        )

    study_name = data.get('study_name', '__objective_builder_validation__')
    study_mode = data.get('study_mode', 'random')

    normalized = {
        'extract_objectives': extract_objectives,
        'study': {
            'name': study_name,
            'mode': study_mode,
            'parameters': study_parameters,
            'objectives': study_objectives,
            'grid': data.get('study_grid', {'steps': 3}) or {'steps': 3},
            'random': data.get('study_random', {'samples': 10, 'seed': 42}) or {'samples': 10, 'seed': 42},
        },
    }

    return {
        'valid': len(errors) == 0,
        'errors': errors,
        'warnings': warnings,
        'normalized': normalized,
    }


def _build_objective_builder_payload(payload, validation):
    data = dict(payload or {})
    normalized = (validation or {}).get('normalized', {}) or {}

    extract_objectives = list(normalized.get('extract_objectives', []) or [])
    study = dict(normalized.get('study', {}) or {})
    study_name = study.get('name') or data.get('study_name') or '__objective_builder_study__'
    study_objectives = list(study.get('objectives', []) or [])

    primary_obj = None
    for candidate in study_objectives:
        if isinstance(candidate, dict) and candidate.get('name') == 'score':
            primary_obj = candidate
            break
    if primary_obj is None:
        for candidate in study_objectives:
            if isinstance(candidate, dict) and candidate.get('metric') == 'formula':
                primary_obj = candidate
                break
    if primary_obj is None:
        for candidate in study_objectives:
            if isinstance(candidate, dict):
                primary_obj = candidate
                break

    primary_name = (primary_obj or {}).get('name', 'score')
    primary_direction = (primary_obj or {}).get('direction', 'maximize')

    run_method = str(data.get('run_method', 'surrogate_gp')).strip().lower()
    if run_method not in {'surrogate_gp', 'random_search', 'cmaes'}:
        run_method = 'surrogate_gp'

    budget = data.get('run_budget', data.get('budget', 20))
    seed = data.get('run_seed', data.get('seed', 42))

    sim_params = data.get('sim_params') or {
        'events': 1000,
        'threads': 1,
        'save_hits': True,
        'save_particles': True,
        'hit_energy_threshold': '1 eV',
    }

    surrogate = data.get('surrogate') or {
        'warmup_runs': 4,
        'candidate_pool_size': 128,
        'exploration_beta': 1.0,
    }

    cmaes = data.get('cmaes') or {
        'population_size': 8,
    }

    build = {
        'version': _objective_builder_schema().get('version'),
        'study_upsert_payload': study,
        'sim_objectives': extract_objectives,
        'sim_context': data.get('context', {}) or {},
        'run_sim_loop_payload': {
            'study_name': study_name,
            'method': run_method,
            'budget': budget,
            'seed': seed,
            'objective_name': primary_name,
            'direction': primary_direction,
            'sim_params': sim_params,
            'sim_objectives': extract_objectives,
            'surrogate': surrogate,
            'cmaes': cmaes,
            'context': data.get('context', {}) or {},
            'keep_candidate_runs': bool(data.get('keep_candidate_runs', False)),
            'candidate_runs_root': data.get('candidate_runs_root'),
        },
        'verify_payload_template': {
            'run_id': '<optimizer_run_id>',
            'repeats': RUN_POLICY_VERIFY_MIN_REPEATS,
            'min_repeats': RUN_POLICY_VERIFY_MIN_REPEATS,
            'min_success_rate': RUN_POLICY_VERIFY_MIN_SUCCESS_RATE,
            'max_std': RUN_POLICY_VERIFY_MAX_STD,
        },
        'apply_payload_template': {
            'run_id': '<optimizer_run_id>',
            'apply_to_project': True,
            'allow_apply': True,
            'verification_token': '<apply_token_from_verify_best>',
        },
        'notes': [
            '1) Upsert the study with study_upsert_payload.',
            '2) Run optimization using run_sim_loop_payload.',
            '3) Call /verify_best and obtain apply_token.',
            '4) Apply via /replay_best with allow_apply=true and verification_token.',
        ],
    }

    return build


def _coerce_int(value, field_name, errors):
    try:
        return int(value)
    except Exception:
        errors.append(f"{field_name} must be an integer.")
        return None


def _validate_apply_policy(payload):
    data = dict(payload or {})

    apply_to_project = bool(data.get('apply_to_project', RUN_POLICY_DEFAULT_APPLY_TO_PROJECT))
    dry_run = bool(data.get('dry_run', False))
    allow_apply = bool(data.get('allow_apply', False))
    verification_token = data.get('verification_token')

    notes = []
    if dry_run and apply_to_project:
        apply_to_project = False
        notes.append("dry_run=true forces apply_to_project=false.")

    details = []
    if apply_to_project and RUN_POLICY_REQUIRE_ALLOW_APPLY and not allow_apply:
        details.append("apply_to_project=true requires allow_apply=true.")

    if apply_to_project and RUN_POLICY_REQUIRE_VERIFY_TOKEN and not verification_token:
        details.append("apply_to_project=true requires verification_token from a successful /verify_best call.")

    if details:
        return None, {
            "error": "Apply policy validation failed.",
            "details": details,
            "policy": {
                "require_allow_apply": RUN_POLICY_REQUIRE_ALLOW_APPLY,
                "require_verify_token": RUN_POLICY_REQUIRE_VERIFY_TOKEN,
                "default_apply_to_project": RUN_POLICY_DEFAULT_APPLY_TO_PROJECT,
            },
        }

    return {
        "apply_to_project": apply_to_project,
        "dry_run": dry_run,
        "allow_apply": allow_apply,
        "verification_token": verification_token,
        "notes": notes,
    }, None


def _evaluate_verification_gate(result, data):
    verification = ((result or {}).get('verification_record') or {})
    repeats = max(1, int(verification.get('repeats', 0) or 0))
    success_count = int(verification.get('success_count', 0) or 0)
    stats = verification.get('stats', {}) or {}
    std = stats.get('std')
    stats_count = int(stats.get('count', 0) or 0)

    min_repeats = data.get('min_repeats', RUN_POLICY_VERIFY_MIN_REPEATS)
    try:
        min_repeats = int(min_repeats)
    except Exception:
        min_repeats = RUN_POLICY_VERIFY_MIN_REPEATS
    min_repeats = max(1, min_repeats)

    min_success_rate = data.get('min_success_rate', RUN_POLICY_VERIFY_MIN_SUCCESS_RATE)
    try:
        min_success_rate = float(min_success_rate)
    except Exception:
        min_success_rate = RUN_POLICY_VERIFY_MIN_SUCCESS_RATE
    min_success_rate = max(0.0, min(1.0, min_success_rate))

    max_std = data.get('max_std', RUN_POLICY_VERIFY_MAX_STD)
    if max_std is not None:
        try:
            max_std = float(max_std)
        except Exception:
            max_std = RUN_POLICY_VERIFY_MAX_STD

    success_rate = float(success_count) / float(repeats) if repeats > 0 else 0.0

    passed = True
    reasons = []

    if repeats < min_repeats:
        passed = False
        reasons.append(f"repeats={repeats} < min_repeats={min_repeats}")

    if success_rate < min_success_rate:
        passed = False
        reasons.append(f"success_rate={success_rate:.3f} < min_success_rate={min_success_rate:.3f}")

    if stats_count < min_repeats:
        passed = False
        reasons.append(f"objective_stats_count={stats_count} < min_repeats={min_repeats}")

    if max_std is not None:
        if std is None:
            passed = False
            reasons.append("objective std is unavailable while max_std is enforced.")
        elif float(std) > float(max_std):
            passed = False
            reasons.append(f"std={float(std):.6g} > max_std={float(max_std):.6g}")

    return {
        'passed': bool(passed),
        'reasons': reasons,
        'min_repeats': min_repeats,
        'min_success_rate': min_success_rate,
        'max_std': max_std,
        'success_rate': success_rate,
        'repeats': repeats,
        'stats_count': stats_count,
        'stats_std': std,
    }


def _validate_and_normalize_run_policy(payload, *, head_to_head=False):
    data = dict(payload or {})
    errors = []

    budget = _coerce_int(data.get('budget', 20), 'budget', errors)

    sim_params = data.get('sim_params') or {}
    if not isinstance(sim_params, dict):
        errors.append("sim_params must be an object/dict.")
        sim_params = {}
    else:
        sim_params = dict(sim_params)

    events = _coerce_int(sim_params.get('events', 1), 'sim_params.events', errors)
    threads = _coerce_int(sim_params.get('threads', 1), 'sim_params.threads', errors)

    surrogate_cfg = data.get('surrogate') or {}
    if surrogate_cfg is None:
        surrogate_cfg = {}
    if not isinstance(surrogate_cfg, dict):
        errors.append("surrogate must be an object/dict when provided.")
        surrogate_cfg = {}
    else:
        surrogate_cfg = dict(surrogate_cfg)

    warmup_runs = _coerce_int(surrogate_cfg.get('warmup_runs', 10), 'surrogate.warmup_runs', errors)
    candidate_pool_size = _coerce_int(surrogate_cfg.get('candidate_pool_size', 256), 'surrogate.candidate_pool_size', errors)
    max_wall_time_seconds = _coerce_int(
        data.get('max_wall_time_seconds', RUN_POLICY_DEFAULT_WALL_TIME_SECONDS),
        'max_wall_time_seconds',
        errors,
    )

    if budget is not None and budget < 1:
        errors.append("budget must be >= 1.")
    if budget is not None and budget > RUN_POLICY_MAX_BUDGET:
        errors.append(f"budget={budget} exceeds max_budget={RUN_POLICY_MAX_BUDGET}.")

    if events is not None and events < 1:
        errors.append("sim_params.events must be >= 1.")
    if events is not None and events > RUN_POLICY_MAX_EVENTS_PER_CANDIDATE:
        errors.append(
            f"sim_params.events={events} exceeds max_events_per_candidate={RUN_POLICY_MAX_EVENTS_PER_CANDIDATE}."
        )

    if threads is not None and threads < 1:
        errors.append("sim_params.threads must be >= 1.")
    if threads is not None and threads > RUN_POLICY_MAX_THREADS:
        errors.append(f"sim_params.threads={threads} exceeds max_threads={RUN_POLICY_MAX_THREADS}.")

    if warmup_runs is not None and warmup_runs < 1:
        errors.append("surrogate.warmup_runs must be >= 1.")
    if warmup_runs is not None and warmup_runs > RUN_POLICY_MAX_WARMUP_RUNS:
        errors.append(f"surrogate.warmup_runs={warmup_runs} exceeds max_warmup_runs={RUN_POLICY_MAX_WARMUP_RUNS}.")

    if candidate_pool_size is not None and candidate_pool_size < 8:
        errors.append("surrogate.candidate_pool_size must be >= 8.")
    if candidate_pool_size is not None and candidate_pool_size > RUN_POLICY_MAX_CANDIDATE_POOL_SIZE:
        errors.append(
            f"surrogate.candidate_pool_size={candidate_pool_size} exceeds max_candidate_pool_size={RUN_POLICY_MAX_CANDIDATE_POOL_SIZE}."
        )

    if max_wall_time_seconds is not None and max_wall_time_seconds < 60:
        errors.append("max_wall_time_seconds must be >= 60.")
    if max_wall_time_seconds is not None and max_wall_time_seconds > RUN_POLICY_MAX_WALL_TIME_SECONDS:
        errors.append(
            f"max_wall_time_seconds={max_wall_time_seconds} exceeds max_wall_time_seconds={RUN_POLICY_MAX_WALL_TIME_SECONDS}."
        )

    if budget is not None and events is not None:
        multiplier = 2 if head_to_head else 1
        effective_total_events = budget * events * multiplier
        if effective_total_events > RUN_POLICY_MAX_TOTAL_EVENTS:
            errors.append(
                f"effective_total_events={effective_total_events} exceeds max_total_events={RUN_POLICY_MAX_TOTAL_EVENTS}. "
                f"(computed as budget * events * {multiplier})"
            )

    if errors:
        return None, {
            "error": "Run policy validation failed.",
            "details": errors,
            "limits": _run_policy_limits(),
        }

    data['budget'] = budget
    sim_params['events'] = events
    sim_params['threads'] = threads
    data['sim_params'] = sim_params

    surrogate_cfg['warmup_runs'] = warmup_runs
    surrogate_cfg['candidate_pool_size'] = candidate_pool_size
    data['surrogate'] = surrogate_cfg
    data['max_wall_time_seconds'] = max_wall_time_seconds

    data['_run_policy'] = {
        "head_to_head": bool(head_to_head),
        "budget": budget,
        "events": events,
        "threads": threads,
        "effective_total_events": budget * events * (2 if head_to_head else 1),
        "max_wall_time_seconds": max_wall_time_seconds,
        "surrogate": {
            "warmup_runs": warmup_runs,
            "candidate_pool_size": candidate_pool_size,
        },
    }

    return data, None

def _start_managed_optimizer_run(pm, run_payload, *, kind, metadata=None):
    max_wall_time_seconds = None
    if isinstance(run_payload, dict):
        raw = run_payload.get('max_wall_time_seconds')
        if raw is not None:
            try:
                max_wall_time_seconds = int(raw)
            except Exception:
                max_wall_time_seconds = None

    control, err = pm.start_managed_run(
        kind=kind,
        max_wall_time_seconds=max_wall_time_seconds,
        metadata=(metadata or {}),
    )
    if not control:
        return None, jsonify({
            "success": False,
            "error": err or "Another optimization run is already active.",
            "active_run": pm.get_managed_run_status().get('active'),
        }), 409

    return control, None, None


def _finish_managed_optimizer_run(pm, *, status='completed', details=None):
    try:
        pm.finish_managed_run(status=status, details=(details or {}))
    except Exception:
        pass


OBJECTIVE_BUILDER_LAUNCH_JOBS = {}
OBJECTIVE_BUILDER_LAUNCH_LOCK = threading.Lock()


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

def _extract_preflight_summary(payload: Any) -> Optional[Dict[str, Any]]:
    """Accept either a summary dict or wrappers containing one and return a normalized summary."""
    if not isinstance(payload, dict):
        return None

    if isinstance(payload.get('summary'), dict):
        return payload.get('summary')

    if isinstance(payload.get('preflight_summary'), dict):
        return payload.get('preflight_summary')

    if isinstance(payload.get('preflight_report'), dict) and isinstance(payload['preflight_report'].get('summary'), dict):
        return payload['preflight_report']['summary']

    return payload


def compare_preflight_summaries(baseline_summary: Any, candidate_summary: Any) -> Dict[str, Any]:
    """Compare two preflight summaries and report deterministic code-level deltas."""

    def _as_summary(summary_like: Any) -> Dict[str, Any]:
        summary = _extract_preflight_summary(summary_like)
        if not isinstance(summary, dict):
            raise ValueError("Preflight summaries must be objects/dicts.")
        return summary

    def _as_bool(value: Any, default: bool = False) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            low = value.strip().lower()
            if low in ('true', '1', 'yes', 'on'):
                return True
            if low in ('false', '0', 'no', 'off'):
                return False
        return default

    def _as_int(value: Any, default: int = 0) -> int:
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, (int, float)):
            return int(value)
        if isinstance(value, str):
            try:
                return int(float(value.strip()))
            except Exception:
                return default
        return default

    def _normalize_counts(summary: Dict[str, Any]) -> Dict[str, int]:
        raw = summary.get('counts_by_code')
        if not isinstance(raw, dict):
            return {}

        normalized = {}
        for code, count in raw.items():
            code_str = str(code)
            count_int = _as_int(count, default=0)
            if count_int < 0:
                count_int = 0
            normalized[code_str] = count_int

        return dict(sorted(normalized.items()))

    baseline = _as_summary(baseline_summary)
    candidate = _as_summary(candidate_summary)

    baseline_counts = _normalize_counts(baseline)
    candidate_counts = _normalize_counts(candidate)

    all_codes = sorted(set(baseline_counts.keys()) | set(candidate_counts.keys()))

    counts_delta_by_code = {}
    added_counts_by_code = {}
    resolved_counts_by_code = {}
    increased_counts_by_code = {}
    reduced_counts_by_code = {}
    unchanged_counts_by_code = {}

    added_issue_codes = []
    resolved_issue_codes = []

    for code in all_codes:
        base_count = baseline_counts.get(code, 0)
        cand_count = candidate_counts.get(code, 0)
        delta = cand_count - base_count
        if delta != 0:
            counts_delta_by_code[code] = delta
        else:
            unchanged_counts_by_code[code] = cand_count

        if base_count == 0 and cand_count > 0:
            added_issue_codes.append(code)
            added_counts_by_code[code] = cand_count
        elif base_count > 0 and cand_count == 0:
            resolved_issue_codes.append(code)
            resolved_counts_by_code[code] = base_count
        elif delta > 0:
            increased_counts_by_code[code] = delta
        elif delta < 0:
            reduced_counts_by_code[code] = abs(delta)

    baseline_can_run = _as_bool(baseline.get('can_run'), default=False)
    candidate_can_run = _as_bool(candidate.get('can_run'), default=False)

    baseline_issue_count = _as_int(baseline.get('issue_count'), default=sum(baseline_counts.values()))
    candidate_issue_count = _as_int(candidate.get('issue_count'), default=sum(candidate_counts.values()))

    baseline_fingerprint = baseline.get('issue_fingerprint')
    candidate_fingerprint = candidate.get('issue_fingerprint')

    return {
        'baseline': {
            'can_run': baseline_can_run,
            'issue_count': baseline_issue_count,
            'counts_by_code': baseline_counts,
            'issue_fingerprint': baseline_fingerprint,
        },
        'candidate': {
            'can_run': candidate_can_run,
            'issue_count': candidate_issue_count,
            'counts_by_code': candidate_counts,
            'issue_fingerprint': candidate_fingerprint,
        },
        'status': {
            'can_run_changed': baseline_can_run != candidate_can_run,
            'regressed_can_run': baseline_can_run and not candidate_can_run,
            'improved_can_run': (not baseline_can_run) and candidate_can_run,
            'fingerprint_changed': (
                isinstance(baseline_fingerprint, str)
                and isinstance(candidate_fingerprint, str)
                and baseline_fingerprint != candidate_fingerprint
            ),
        },
        'issue_count_delta': candidate_issue_count - baseline_issue_count,
        'added_issue_total': sum(added_counts_by_code.values()),
        'resolved_issue_total': sum(resolved_counts_by_code.values()),
        'increased_issue_total': sum(increased_counts_by_code.values()),
        'reduced_issue_total': sum(reduced_counts_by_code.values()),
        'added_issue_codes': sorted(added_issue_codes),
        'resolved_issue_codes': sorted(resolved_issue_codes),
        'increased_issue_codes': sorted(increased_counts_by_code.keys()),
        'reduced_issue_codes': sorted(reduced_counts_by_code.keys()),
        'unchanged_issue_codes': sorted(unchanged_counts_by_code.keys()),
        'added_counts_by_code': added_counts_by_code,
        'resolved_counts_by_code': resolved_counts_by_code,
        'increased_counts_by_code': increased_counts_by_code,
        'reduced_counts_by_code': reduced_counts_by_code,
        'counts_delta_by_code': counts_delta_by_code,
    }


def _normalize_single_segment_selector_id(
    selector_id: Any,
    *,
    field_name: str,
    required_error: str,
) -> str:
    """Normalize selector ids that must remain a single non-empty path segment."""
    selector_id_norm = str(selector_id or '').strip()
    if not selector_id_norm:
        raise ValueError(required_error)

    if selector_id_norm in {'.', '..'}:
        raise ValueError(f"Invalid {field_name} '{selector_id_norm}'.")

    if '/' in selector_id_norm or '\\' in selector_id_norm:
        raise ValueError(f"Invalid {field_name} '{selector_id_norm}'.")

    return selector_id_norm


def _normalize_preflight_version_selector_id(version_id: Any, *, required_error: str) -> str:
    """Normalize explicit preflight version selectors as single-segment ids."""
    return _normalize_single_segment_selector_id(
        version_id,
        field_name='version_id',
        required_error=required_error,
    )


def _resolve_saved_version_json_path(pm: ProjectManager, project_name: str, version_id: Any) -> tuple[str, str]:
    project_name_norm = str(project_name or '').strip()
    if not project_name_norm:
        raise ValueError("project_name is required to compare saved versions.")

    # Saved/snapshot selectors are directory-name ids under `<project>/versions`.
    # Keep selectors as a single path segment and reject path-like forms
    # deterministically so malformed hostile ids fail as validation errors.
    version_id_norm = _normalize_preflight_version_selector_id(
        version_id,
        required_error="version_id must be a non-empty string.",
    )

    versions_root = os.path.realpath(os.path.join(pm.projects_dir, project_name_norm, 'versions'))
    candidate_path = os.path.realpath(os.path.join(versions_root, version_id_norm, 'version.json'))

    if not (candidate_path == versions_root or candidate_path.startswith(versions_root + os.sep)):
        raise ValueError(f"Invalid version_id '{version_id_norm}'.")

    if not os.path.exists(candidate_path):
        raise FileNotFoundError(f"Version '{version_id_norm}' not found for project '{project_name_norm}'.")

    return version_id_norm, candidate_path


def _run_preflight_for_saved_version_json(version_json_path: str) -> Dict[str, Any]:
    with open(version_json_path, 'r') as handle:
        version_json = handle.read()

    version_pm = ProjectManager(ExpressionEvaluator())
    version_pm.load_project_from_json_string(version_json)
    return version_pm.run_preflight_checks()


def _is_path_within_root(path: str, root: str) -> bool:
    path_real = os.path.realpath(path)
    root_real = os.path.realpath(root)
    return path_real == root_real or path_real.startswith(root_real + os.sep)


def _read_file_mtime_utc(path: str) -> Optional[str]:
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return None
    return datetime.utcfromtimestamp(mtime).strftime('%Y-%m-%dT%H:%M:%SZ')


def _build_version_source_metadata(pm: ProjectManager, project_name: str, version_id: str) -> Dict[str, Any]:
    versions_root = os.path.realpath(os.path.join(pm.projects_dir, project_name, 'versions'))
    version_dir = os.path.realpath(os.path.join(versions_root, version_id))
    version_json_path = os.path.realpath(os.path.join(version_dir, 'version.json'))

    timestamp, description = _extract_version_timestamp_and_description(version_id)
    is_autosave = version_id == AUTOSAVE_VERSION_ID

    return {
        'version_id': version_id,
        'is_autosave': is_autosave,
        'is_autosave_snapshot': _is_autosave_snapshot_version_id(version_id),
        'timestamp_from_version_id': None if is_autosave else timestamp,
        'description_from_version_id': None if is_autosave else description,
        'version_json_path': version_json_path,
        'version_json_exists': os.path.exists(version_json_path),
        'version_json_mtime_utc': _read_file_mtime_utc(version_json_path),
        'source_path_checks': {
            'versions_root_exists': os.path.isdir(versions_root),
            'version_dir_within_versions_root': _is_path_within_root(version_dir, versions_root),
            'version_json_within_versions_root': _is_path_within_root(version_json_path, versions_root),
        },
    }


def compare_preflight_versions(pm: ProjectManager, baseline_version_id: Any, candidate_version_id: Any, project_name: Optional[str] = None) -> Dict[str, Any]:
    """Run preflight checks on two saved versions and compare their deterministic summaries."""
    project_name_norm = str(project_name or pm.project_name or '').strip()

    baseline_id, baseline_path = _resolve_saved_version_json_path(pm, project_name_norm, baseline_version_id)
    candidate_id, candidate_path = _resolve_saved_version_json_path(pm, project_name_norm, candidate_version_id)

    baseline_report = _run_preflight_for_saved_version_json(baseline_path)
    candidate_report = _run_preflight_for_saved_version_json(candidate_path)

    comparison = compare_preflight_summaries(baseline_report, candidate_report)

    versions_root = os.path.realpath(os.path.join(pm.projects_dir, project_name_norm, 'versions'))

    return {
        'project_name': project_name_norm,
        'baseline_version_id': baseline_id,
        'candidate_version_id': candidate_id,
        'baseline_report': baseline_report,
        'candidate_report': candidate_report,
        'comparison': comparison,
        'ordering_metadata': {
            'ordering_basis': 'explicit_version_ids',
            'versions_root': versions_root,
        },
        'version_sources': {
            'baseline': _build_version_source_metadata(pm, project_name_norm, baseline_id),
            'candidate': _build_version_source_metadata(pm, project_name_norm, candidate_id),
        },
    }


def _list_saved_version_ids(pm: ProjectManager, project_name: str) -> List[str]:
    versions_root = os.path.realpath(os.path.join(pm.projects_dir, project_name, 'versions'))
    if not os.path.isdir(versions_root):
        return []

    version_ids = [
        version_id
        for version_id in os.listdir(versions_root)
        if version_id != AUTOSAVE_VERSION_ID and os.path.isdir(os.path.join(versions_root, version_id))
    ]

    return sorted(version_ids, reverse=True)


def compare_latest_preflight_versions(pm: ProjectManager, project_name: Optional[str] = None) -> Dict[str, Any]:
    """Compare preflight summaries for the latest two saved project versions."""
    project_name_norm = str(project_name or pm.project_name or '').strip()
    if not project_name_norm:
        raise ValueError("project_name is required to compare latest saved versions.")

    version_ids = _list_saved_version_ids(pm, project_name_norm)
    if len(version_ids) < 2:
        raise ValueError(
            f"Need at least two saved versions for project '{project_name_norm}' to compare latest preflight checks."
        )

    candidate_version_id = version_ids[0]
    baseline_version_id = version_ids[1]

    result = compare_preflight_versions(
        pm,
        baseline_version_id=baseline_version_id,
        candidate_version_id=candidate_version_id,
        project_name=project_name_norm,
    )

    result['selection'] = {
        'strategy': 'latest_two_saved_versions',
        'ordering_basis': 'manual_saved_versions_sorted_desc_lexicographic',
        'selected_version_ids': [candidate_version_id, baseline_version_id],
        'ordered_manual_saved_version_ids': version_ids,
        'total_saved_versions': len(version_ids),
    }
    return result


def compare_autosave_preflight_vs_latest_saved(pm: ProjectManager, project_name: Optional[str] = None) -> Dict[str, Any]:
    """Compare autosave preflight checks against the latest manually saved project version."""
    project_name_norm = str(project_name or pm.project_name or '').strip()
    if not project_name_norm:
        raise ValueError("project_name is required to compare autosave with latest saved version.")

    version_ids = _list_saved_version_ids(pm, project_name_norm)
    if len(version_ids) < 1:
        raise ValueError(
            f"Need at least one saved version for project '{project_name_norm}' to compare autosave preflight checks."
        )

    latest_saved_version_id = version_ids[0]

    result = compare_preflight_versions(
        pm,
        baseline_version_id=latest_saved_version_id,
        candidate_version_id=AUTOSAVE_VERSION_ID,
        project_name=project_name_norm,
    )

    result['selection'] = {
        'strategy': 'latest_autosave_vs_latest_saved',
        'ordering_basis': 'manual_saved_versions_sorted_desc_lexicographic',
        'selected_version_ids': [AUTOSAVE_VERSION_ID, latest_saved_version_id],
        'ordered_manual_saved_version_ids': version_ids,
        'total_saved_versions': len(version_ids),
    }
    return result


def _list_saved_non_snapshot_version_ids(pm: ProjectManager, project_name: str) -> List[str]:
    """Return saved version ids excluding autosave snapshots (newest-first)."""
    return [
        version_id
        for version_id in _list_saved_version_ids(pm, project_name)
        if not _is_autosave_snapshot_version_id(version_id)
    ]


def _normalize_manual_saved_index(manual_saved_index: Any) -> int:
    """Parse and validate non-negative manual saved index selectors (N-back)."""
    if manual_saved_index is None:
        return 0

    if isinstance(manual_saved_index, bool):
        raise ValueError("manual_saved_index must be a non-negative integer.")

    if isinstance(manual_saved_index, int):
        index = manual_saved_index
    elif isinstance(manual_saved_index, str):
        value = manual_saved_index.strip()
        if not value:
            raise ValueError("manual_saved_index must be a non-negative integer.")
        try:
            index = int(value)
        except ValueError as exc:
            raise ValueError("manual_saved_index must be a non-negative integer.") from exc
    else:
        raise ValueError("manual_saved_index must be a non-negative integer.")

    if index < 0:
        raise ValueError("manual_saved_index must be a non-negative integer.")
    return index


def compare_autosave_preflight_vs_manual_saved_index(
    pm: ProjectManager,
    manual_saved_index: Any = 0,
    project_name: Optional[str] = None,
) -> Dict[str, Any]:
    """Compare autosave preflight checks against an N-back non-snapshot manual saved version."""
    project_name_norm = str(project_name or pm.project_name or '').strip()
    if not project_name_norm:
        raise ValueError("project_name is required to compare autosave with a manual saved version index.")

    manual_saved_index_norm = _normalize_manual_saved_index(manual_saved_index)

    version_ids = _list_saved_version_ids(pm, project_name_norm)
    manual_version_ids = _list_saved_non_snapshot_version_ids(pm, project_name_norm)
    if len(manual_version_ids) < 1:
        raise ValueError(
            f"Need at least one manually saved non-snapshot version for project '{project_name_norm}' to compare autosave preflight checks."
        )
    if manual_saved_index_norm >= len(manual_version_ids):
        raise ValueError(
            f"manual_saved_index={manual_saved_index_norm} is out of range for project '{project_name_norm}' "
            f"(available manual saved versions: {len(manual_version_ids)})."
        )

    selected_manual_saved_version_id = manual_version_ids[manual_saved_index_norm]

    result = compare_preflight_versions(
        pm,
        baseline_version_id=selected_manual_saved_version_id,
        candidate_version_id=AUTOSAVE_VERSION_ID,
        project_name=project_name_norm,
    )

    result['selection'] = {
        'strategy': 'latest_autosave_vs_manual_saved_index',
        'ordering_basis': 'manual_saved_versions_sorted_desc_lexicographic',
        'selected_version_ids': [AUTOSAVE_VERSION_ID, result['baseline_version_id']],
        'ordered_manual_saved_version_ids': manual_version_ids,
        'manual_saved_index': manual_saved_index_norm,
        'selected_manual_saved_version_id': result['baseline_version_id'],
        'total_saved_versions': len(version_ids),
        'total_snapshot_versions': len(version_ids) - len(manual_version_ids),
        'total_manual_saved_versions': len(manual_version_ids),
    }
    return result


def compare_autosave_preflight_vs_previous_manual_saved(pm: ProjectManager, project_name: Optional[str] = None) -> Dict[str, Any]:
    """Compare autosave preflight checks against the latest non-snapshot manually saved project version."""
    result = compare_autosave_preflight_vs_manual_saved_index(
        pm,
        manual_saved_index=0,
        project_name=project_name,
    )
    result['selection']['strategy'] = 'latest_autosave_vs_previous_manual_saved'
    result['selection']['previous_manual_saved_version_id'] = result['baseline_version_id']
    return result


def _normalize_simulation_run_id(simulation_run_id: Any) -> str:
    # Run ids are treated as directory-name selectors under each saved version's
    # `sim_runs/` folder. Keep the selector as a single id segment and reject
    # path-like inputs deterministically.
    return _normalize_single_segment_selector_id(
        simulation_run_id,
        field_name='simulation_run_id',
        required_error="simulation_run_id is required to compare autosave against simulation-linked manual saves.",
    )


def compare_autosave_preflight_vs_manual_saved_for_simulation_run_index(
    pm: ProjectManager,
    simulation_run_id: Any,
    manual_saved_index: Any = 0,
    project_name: Optional[str] = None,
) -> Dict[str, Any]:
    """Compare autosave preflight checks against an N-back manual non-snapshot version matching a simulation run id."""
    project_name_norm = str(project_name or pm.project_name or '').strip()
    if not project_name_norm:
        raise ValueError("project_name is required to compare autosave against simulation-linked manual saves.")

    simulation_run_id_norm = _normalize_simulation_run_id(simulation_run_id)
    manual_saved_index_norm = _normalize_manual_saved_index(manual_saved_index)

    version_ids = _list_saved_version_ids(pm, project_name_norm)
    manual_version_ids = _list_saved_non_snapshot_version_ids(pm, project_name_norm)
    if len(manual_version_ids) < 1:
        raise ValueError(
            f"Need at least one manually saved non-snapshot version for project '{project_name_norm}' to compare autosave preflight checks."
        )

    versions_root = os.path.realpath(os.path.join(pm.projects_dir, project_name_norm, 'versions'))
    matching_manual_version_ids = [
        version_id
        for version_id in manual_version_ids
        if os.path.isdir(os.path.join(versions_root, version_id, 'sim_runs', simulation_run_id_norm))
    ]

    if not matching_manual_version_ids:
        raise ValueError(
            f"No manually saved non-snapshot versions for project '{project_name_norm}' contain simulation_run_id '{simulation_run_id_norm}'."
        )

    if manual_saved_index_norm >= len(matching_manual_version_ids):
        raise ValueError(
            f"manual_saved_index={manual_saved_index_norm} is out of range for simulation_run_id '{simulation_run_id_norm}' "
            f"in project '{project_name_norm}' (available matching manual saved versions: {len(matching_manual_version_ids)})."
        )

    selected_manual_saved_version_id = matching_manual_version_ids[manual_saved_index_norm]

    result = compare_preflight_versions(
        pm,
        baseline_version_id=selected_manual_saved_version_id,
        candidate_version_id=AUTOSAVE_VERSION_ID,
        project_name=project_name_norm,
    )

    result['selection'] = {
        'strategy': 'latest_autosave_vs_manual_saved_for_simulation_run_index',
        'ordering_basis': 'matching_manual_saved_versions_sorted_desc_lexicographic',
        'selected_version_ids': [AUTOSAVE_VERSION_ID, result['baseline_version_id']],
        'simulation_run_id': simulation_run_id_norm,
        'manual_saved_index': manual_saved_index_norm,
        'selected_manual_saved_version_id': result['baseline_version_id'],
        'matching_manual_saved_version_ids': matching_manual_version_ids,
        'ordered_manual_saved_version_ids': manual_version_ids,
        'total_matching_manual_saved_versions': len(matching_manual_version_ids),
        'total_saved_versions': len(version_ids),
        'total_snapshot_versions': len(version_ids) - len(manual_version_ids),
        'total_manual_saved_versions': len(manual_version_ids),
    }
    return result


def compare_autosave_preflight_vs_manual_saved_for_simulation_run(
    pm: ProjectManager,
    simulation_run_id: Any,
    project_name: Optional[str] = None,
) -> Dict[str, Any]:
    """Compare autosave preflight checks against the latest manual non-snapshot version that contains a given simulation run id."""
    result = compare_autosave_preflight_vs_manual_saved_for_simulation_run_index(
        pm,
        simulation_run_id=simulation_run_id,
        manual_saved_index=0,
        project_name=project_name,
    )
    result['selection']['strategy'] = 'latest_autosave_vs_manual_saved_for_simulation_run'
    return result


def list_manual_saved_versions_for_simulation_run(
    pm: ProjectManager,
    simulation_run_id: Any,
    project_name: Optional[str] = None,
    limit: Any = None,
) -> Dict[str, Any]:
    """List newest-first manual non-snapshot versions that contain a specific simulation run id, with deterministic index metadata."""
    project_name_norm = str(project_name or pm.project_name or '').strip()
    if not project_name_norm:
        raise ValueError("project_name is required to list simulation-linked manual saved versions.")

    simulation_run_id_norm = _normalize_simulation_run_id(simulation_run_id)
    limit_norm = _parse_optional_nonnegative_limit(limit)

    version_ids = _list_saved_version_ids(pm, project_name_norm)
    manual_version_ids = _list_saved_non_snapshot_version_ids(pm, project_name_norm)

    versions_root = os.path.realpath(os.path.join(pm.projects_dir, project_name_norm, 'versions'))
    matching_manual_version_ids = [
        version_id
        for version_id in manual_version_ids
        if os.path.isdir(os.path.join(versions_root, version_id, 'sim_runs', simulation_run_id_norm))
    ]

    matching_versions: List[Dict[str, Any]] = []
    for index, version_id in enumerate(matching_manual_version_ids):
        source = _build_version_source_metadata(pm, project_name_norm, version_id)
        matching_versions.append({
            'manual_saved_index': index,
            'version_id': version_id,
            'timestamp': source['timestamp_from_version_id'],
            'timestamp_source': 'version_id_prefix',
            'has_version_json': source['version_json_exists'],
            'version_json_mtime_utc': source['version_json_mtime_utc'],
            'source_path_checks': source['source_path_checks'],
        })

    if limit_norm is not None:
        matching_versions = matching_versions[:limit_norm]

    return {
        'project_name': project_name_norm,
        'simulation_run_id': simulation_run_id_norm,
        'ordering_basis': 'matching_manual_saved_versions_sorted_desc_lexicographic',
        'ordered_manual_saved_version_ids': manual_version_ids,
        'total_saved_versions': len(version_ids),
        'total_snapshot_versions': len(version_ids) - len(manual_version_ids),
        'total_manual_saved_versions': len(manual_version_ids),
        'total_matching_manual_saved_versions': len(matching_manual_version_ids),
        'returned_matching_manual_saved_versions': len(matching_versions),
        'matching_manual_saved_versions': matching_versions,
    }


def compare_manual_preflight_versions_for_simulation_run_indices(
    pm: ProjectManager,
    simulation_run_id: Any,
    baseline_manual_saved_index: Any = 1,
    candidate_manual_saved_index: Any = 0,
    project_name: Optional[str] = None,
) -> Dict[str, Any]:
    """Compare two manual non-snapshot versions selected by N-back indices within one simulation run id."""
    project_name_norm = str(project_name or pm.project_name or '').strip()
    if not project_name_norm:
        raise ValueError("project_name is required to compare simulation-linked manual saved versions.")

    simulation_run_id_norm = _normalize_simulation_run_id(simulation_run_id)
    baseline_manual_saved_index_norm = _normalize_manual_saved_index(baseline_manual_saved_index)
    candidate_manual_saved_index_norm = _normalize_manual_saved_index(candidate_manual_saved_index)

    if baseline_manual_saved_index_norm == candidate_manual_saved_index_norm:
        raise ValueError("baseline_manual_saved_index and candidate_manual_saved_index must be different.")

    version_ids = _list_saved_version_ids(pm, project_name_norm)
    manual_version_ids = _list_saved_non_snapshot_version_ids(pm, project_name_norm)

    versions_root = os.path.realpath(os.path.join(pm.projects_dir, project_name_norm, 'versions'))
    matching_manual_version_ids = [
        version_id
        for version_id in manual_version_ids
        if os.path.isdir(os.path.join(versions_root, version_id, 'sim_runs', simulation_run_id_norm))
    ]

    if len(matching_manual_version_ids) < 2:
        raise ValueError(
            f"Need at least two manually saved non-snapshot versions for project '{project_name_norm}' "
            f"that contain simulation_run_id '{simulation_run_id_norm}' to compare manual preflight checks."
        )

    total_matching = len(matching_manual_version_ids)
    if baseline_manual_saved_index_norm >= total_matching:
        raise ValueError(
            f"baseline_manual_saved_index={baseline_manual_saved_index_norm} is out of range for simulation_run_id "
            f"'{simulation_run_id_norm}' in project '{project_name_norm}' "
            f"(available matching manual saved versions: {total_matching})."
        )

    if candidate_manual_saved_index_norm >= total_matching:
        raise ValueError(
            f"candidate_manual_saved_index={candidate_manual_saved_index_norm} is out of range for simulation_run_id "
            f"'{simulation_run_id_norm}' in project '{project_name_norm}' "
            f"(available matching manual saved versions: {total_matching})."
        )

    baseline_version_id = matching_manual_version_ids[baseline_manual_saved_index_norm]
    candidate_version_id = matching_manual_version_ids[candidate_manual_saved_index_norm]

    result = compare_preflight_versions(
        pm,
        baseline_version_id=baseline_version_id,
        candidate_version_id=candidate_version_id,
        project_name=project_name_norm,
    )

    result['selection'] = {
        'strategy': 'manual_saved_versions_for_simulation_run_indices',
        'ordering_basis': 'matching_manual_saved_versions_sorted_desc_lexicographic',
        'simulation_run_id': simulation_run_id_norm,
        'baseline_manual_saved_index': baseline_manual_saved_index_norm,
        'candidate_manual_saved_index': candidate_manual_saved_index_norm,
        'selected_version_ids': [result['baseline_version_id'], result['candidate_version_id']],
        'matching_manual_saved_version_ids': matching_manual_version_ids,
        'ordered_manual_saved_version_ids': manual_version_ids,
        'total_matching_manual_saved_versions': total_matching,
        'total_saved_versions': len(version_ids),
        'total_snapshot_versions': len(version_ids) - len(manual_version_ids),
        'total_manual_saved_versions': len(manual_version_ids),
    }
    return result


def compare_autosave_preflight_vs_saved_version(pm: ProjectManager, saved_version_id: Any, project_name: Optional[str] = None) -> Dict[str, Any]:
    """Compare autosave preflight checks against a specific manually saved project version."""
    project_name_norm = str(project_name or pm.project_name or '').strip()
    if not project_name_norm:
        raise ValueError("project_name is required to compare autosave with a saved version.")

    saved_version_id_norm = _normalize_preflight_version_selector_id(
        saved_version_id,
        required_error="saved_version_id is required to compare autosave preflight checks.",
    )
    if saved_version_id_norm == AUTOSAVE_VERSION_ID:
        raise ValueError("saved_version_id must refer to a manually saved version, not 'autosave'.")

    result = compare_preflight_versions(
        pm,
        baseline_version_id=saved_version_id_norm,
        candidate_version_id=AUTOSAVE_VERSION_ID,
        project_name=project_name_norm,
    )

    result['selection'] = {
        'strategy': 'latest_autosave_vs_selected_saved_version',
        'ordering_basis': 'explicit_saved_version_id',
        'selected_version_ids': [AUTOSAVE_VERSION_ID, result['baseline_version_id']],
        'saved_version_id': result['baseline_version_id'],
        'total_saved_versions': len(_list_saved_version_ids(pm, project_name_norm)),
    }
    return result


def _extract_version_timestamp_and_description(version_id: str) -> tuple[str, str]:
    if '_' in version_id:
        return version_id.split('_', 1)
    return version_id, ''


def _is_autosave_snapshot_version_id(version_id: str) -> bool:
    if not version_id or version_id == AUTOSAVE_VERSION_ID:
        return False

    _, description = _extract_version_timestamp_and_description(version_id)
    normalized_desc = re.sub(r'[^a-z0-9]+', '_', description.lower()).strip('_')
    return ('autosave' in normalized_desc and 'snapshot' in normalized_desc)


def compare_autosave_preflight_vs_snapshot_version(pm: ProjectManager, autosave_snapshot_version_id: Any, project_name: Optional[str] = None) -> Dict[str, Any]:
    """Compare latest autosave preflight checks against a selected autosave snapshot version."""
    project_name_norm = str(project_name or pm.project_name or '').strip()
    if not project_name_norm:
        raise ValueError("project_name is required to compare autosave with an autosave snapshot version.")

    snapshot_version_id_norm = _normalize_preflight_version_selector_id(
        autosave_snapshot_version_id,
        required_error="autosave_snapshot_version_id is required to compare autosave preflight checks.",
    )
    if snapshot_version_id_norm == AUTOSAVE_VERSION_ID:
        raise ValueError("autosave_snapshot_version_id must refer to a saved autosave snapshot, not 'autosave'.")
    if not _is_autosave_snapshot_version_id(snapshot_version_id_norm):
        raise ValueError(
            "autosave_snapshot_version_id must refer to a saved autosave snapshot version (see list_preflight_versions metadata)."
        )

    result = compare_preflight_versions(
        pm,
        baseline_version_id=snapshot_version_id_norm,
        candidate_version_id=AUTOSAVE_VERSION_ID,
        project_name=project_name_norm,
    )

    result['selection'] = {
        'strategy': 'latest_autosave_vs_selected_autosave_snapshot',
        'ordering_basis': 'explicit_autosave_snapshot_version_id',
        'selected_version_ids': [AUTOSAVE_VERSION_ID, result['baseline_version_id']],
        'autosave_snapshot_version_id': result['baseline_version_id'],
        'total_saved_versions': len(_list_saved_version_ids(pm, project_name_norm)),
    }
    return result


def _list_autosave_snapshot_version_ids(pm: ProjectManager, project_name: str) -> List[str]:
    """Return autosave snapshot version ids ordered newest-first (mtime, then version id)."""
    snapshot_version_ids = [
        version_id
        for version_id in _list_saved_version_ids(pm, project_name)
        if _is_autosave_snapshot_version_id(version_id)
    ]

    versions_root = os.path.realpath(os.path.join(pm.projects_dir, project_name, 'versions'))

    def _snapshot_sort_key(version_id: str) -> tuple[float, str]:
        version_json_path = os.path.join(versions_root, version_id, 'version.json')
        try:
            return (os.path.getmtime(version_json_path), version_id)
        except OSError:
            return (0.0, version_id)

    return sorted(snapshot_version_ids, key=_snapshot_sort_key, reverse=True)


def compare_autosave_preflight_vs_latest_snapshot(pm: ProjectManager, project_name: Optional[str] = None) -> Dict[str, Any]:
    """Compare latest autosave preflight checks against the most recent saved autosave snapshot version."""
    project_name_norm = str(project_name or pm.project_name or '').strip()
    if not project_name_norm:
        raise ValueError("project_name is required to compare autosave with the latest autosave snapshot version.")

    version_ids = _list_saved_version_ids(pm, project_name_norm)
    snapshot_version_ids = _list_autosave_snapshot_version_ids(pm, project_name_norm)
    if len(snapshot_version_ids) < 1:
        raise ValueError(
            f"Need at least one saved autosave snapshot version for project '{project_name_norm}' to compare autosave preflight checks."
        )

    latest_snapshot_version_id = snapshot_version_ids[0]

    result = compare_preflight_versions(
        pm,
        baseline_version_id=latest_snapshot_version_id,
        candidate_version_id=AUTOSAVE_VERSION_ID,
        project_name=project_name_norm,
    )

    result['selection'] = {
        'strategy': 'latest_autosave_vs_latest_autosave_snapshot',
        'ordering_basis': 'autosave_snapshot_versions_sorted_by_mtime_then_version_id_desc',
        'selected_version_ids': [AUTOSAVE_VERSION_ID, result['baseline_version_id']],
        'ordered_snapshot_version_ids': snapshot_version_ids,
        'autosave_snapshot_version_id': result['baseline_version_id'],
        'total_saved_versions': len(version_ids),
        'total_snapshot_versions': len(snapshot_version_ids),
    }
    return result


def compare_autosave_preflight_vs_previous_snapshot(pm: ProjectManager, project_name: Optional[str] = None) -> Dict[str, Any]:
    """Compare latest autosave preflight checks against the previous saved autosave snapshot version."""
    project_name_norm = str(project_name or pm.project_name or '').strip()
    if not project_name_norm:
        raise ValueError("project_name is required to compare autosave with the previous autosave snapshot version.")

    version_ids = _list_saved_version_ids(pm, project_name_norm)
    snapshot_version_ids = _list_autosave_snapshot_version_ids(pm, project_name_norm)
    if len(snapshot_version_ids) < 2:
        raise ValueError(
            f"Need at least two saved autosave snapshot versions for project '{project_name_norm}' to compare autosave against the previous snapshot."
        )

    latest_snapshot_version_id = snapshot_version_ids[0]
    previous_snapshot_version_id = snapshot_version_ids[1]

    result = compare_preflight_versions(
        pm,
        baseline_version_id=previous_snapshot_version_id,
        candidate_version_id=AUTOSAVE_VERSION_ID,
        project_name=project_name_norm,
    )

    result['selection'] = {
        'strategy': 'latest_autosave_vs_previous_autosave_snapshot',
        'ordering_basis': 'autosave_snapshot_versions_sorted_by_mtime_then_version_id_desc',
        'selected_version_ids': [AUTOSAVE_VERSION_ID, result['baseline_version_id']],
        'ordered_snapshot_version_ids': snapshot_version_ids,
        'autosave_snapshot_version_id': result['baseline_version_id'],
        'previous_snapshot_version_id': result['baseline_version_id'],
        'latest_snapshot_version_id': latest_snapshot_version_id,
        'total_saved_versions': len(version_ids),
        'total_snapshot_versions': len(snapshot_version_ids),
    }
    return result


def compare_latest_autosave_snapshot_preflight_versions(pm: ProjectManager, project_name: Optional[str] = None) -> Dict[str, Any]:
    """Compare deterministic preflight checks between the latest two saved autosave snapshot versions."""
    project_name_norm = str(project_name or pm.project_name or '').strip()
    if not project_name_norm:
        raise ValueError("project_name is required to compare latest autosave snapshot versions.")

    snapshot_version_ids = _list_autosave_snapshot_version_ids(pm, project_name_norm)
    if len(snapshot_version_ids) < 2:
        raise ValueError(
            f"Need at least two saved autosave snapshot versions for project '{project_name_norm}' to compare latest snapshot preflight checks."
        )

    candidate_snapshot_version_id = snapshot_version_ids[0]
    baseline_snapshot_version_id = snapshot_version_ids[1]

    result = compare_preflight_versions(
        pm,
        baseline_version_id=baseline_snapshot_version_id,
        candidate_version_id=candidate_snapshot_version_id,
        project_name=project_name_norm,
    )

    result['selection'] = {
        'strategy': 'latest_two_autosave_snapshot_versions',
        'ordering_basis': 'autosave_snapshot_versions_sorted_by_mtime_then_version_id_desc',
        'selected_version_ids': [result['candidate_version_id'], result['baseline_version_id']],
        'ordered_snapshot_version_ids': snapshot_version_ids,
        'baseline_snapshot_version_id': result['baseline_version_id'],
        'candidate_snapshot_version_id': result['candidate_version_id'],
        'total_snapshot_versions': len(snapshot_version_ids),
    }
    return result


def compare_autosave_snapshot_preflight_versions(
    pm: ProjectManager,
    baseline_snapshot_version_id: Any,
    candidate_snapshot_version_id: Any,
    project_name: Optional[str] = None,
) -> Dict[str, Any]:
    """Compare deterministic preflight checks between two saved autosave snapshot versions."""
    project_name_norm = str(project_name or pm.project_name or '').strip()
    if not project_name_norm:
        raise ValueError("project_name is required to compare autosave snapshot versions.")

    baseline_snapshot_version_id_norm = _normalize_preflight_version_selector_id(
        baseline_snapshot_version_id,
        required_error="baseline_snapshot_version_id is required to compare autosave snapshot versions.",
    )
    candidate_snapshot_version_id_norm = _normalize_preflight_version_selector_id(
        candidate_snapshot_version_id,
        required_error="candidate_snapshot_version_id is required to compare autosave snapshot versions.",
    )

    if baseline_snapshot_version_id_norm == candidate_snapshot_version_id_norm:
        raise ValueError("baseline_snapshot_version_id and candidate_snapshot_version_id must be different snapshot versions.")

    for field_name, version_id in (
        ("baseline_snapshot_version_id", baseline_snapshot_version_id_norm),
        ("candidate_snapshot_version_id", candidate_snapshot_version_id_norm),
    ):
        if version_id == AUTOSAVE_VERSION_ID:
            raise ValueError(f"{field_name} must refer to a saved autosave snapshot, not 'autosave'.")
        if not _is_autosave_snapshot_version_id(version_id):
            raise ValueError(
                f"{field_name} must refer to a saved autosave snapshot version (see list_preflight_versions metadata)."
            )

    result = compare_preflight_versions(
        pm,
        baseline_version_id=baseline_snapshot_version_id_norm,
        candidate_version_id=candidate_snapshot_version_id_norm,
        project_name=project_name_norm,
    )

    snapshot_version_ids = [
        version_id
        for version_id in _list_saved_version_ids(pm, project_name_norm)
        if _is_autosave_snapshot_version_id(version_id)
    ]

    result['selection'] = {
        'strategy': 'selected_autosave_snapshot_versions',
        'ordering_basis': 'explicit_autosave_snapshot_version_ids',
        'selected_version_ids': [result['candidate_version_id'], result['baseline_version_id']],
        'available_snapshot_version_ids_sorted_desc_lexicographic': sorted(snapshot_version_ids, reverse=True),
        'baseline_snapshot_version_id': result['baseline_version_id'],
        'candidate_snapshot_version_id': result['candidate_version_id'],
        'total_snapshot_versions': len(snapshot_version_ids),
    }
    return result


def _parse_optional_nonnegative_limit(value: Any) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError("limit must be a non-negative integer.")
    if isinstance(value, float) and not value.is_integer():
        raise ValueError("limit must be a non-negative integer.")

    try:
        limit = int(value)
    except Exception as exc:
        raise ValueError("limit must be a non-negative integer.") from exc

    if limit < 0:
        raise ValueError("limit must be a non-negative integer.")
    return limit


def list_preflight_versions(
    pm: ProjectManager,
    project_name: Optional[str] = None,
    include_autosave: Any = True,
    limit: Any = None,
) -> Dict[str, Any]:
    """List version ids and metadata that can be used for deterministic preflight comparisons."""
    project_name_norm = str(project_name or pm.project_name or '').strip()
    if not project_name_norm:
        raise ValueError("project_name is required to list preflight versions.")

    include_autosave_norm = bool(include_autosave)
    limit_norm = _parse_optional_nonnegative_limit(limit)

    versions_root = os.path.realpath(os.path.join(pm.projects_dir, project_name_norm, 'versions'))
    if not os.path.isdir(versions_root):
        return {
            'project_name': project_name_norm,
            'ordering_basis': 'autosave_first_then_manual_saved_desc_lexicographic',
            'manual_saved_ordering_basis': 'manual_saved_versions_sorted_desc_lexicographic',
            'versions_root': versions_root,
            'versions_root_exists': False,
            'total_versions': 0,
            'returned_versions': 0,
            'has_autosave': False,
            'versions': [],
        }

    version_dirs = [
        version_id
        for version_id in os.listdir(versions_root)
        if os.path.isdir(os.path.join(versions_root, version_id))
    ]

    manual_version_ids = sorted(
        [version_id for version_id in version_dirs if version_id != AUTOSAVE_VERSION_ID],
        reverse=True,
    )

    versions: List[Dict[str, Any]] = []
    autosave_exists = False

    if include_autosave_norm and AUTOSAVE_VERSION_ID in version_dirs:
        autosave_source = _build_version_source_metadata(pm, project_name_norm, AUTOSAVE_VERSION_ID)
        if autosave_source['version_json_exists']:
            autosave_exists = True
            autosave_timestamp = autosave_source['version_json_mtime_utc']
            versions.append({
                'version_id': AUTOSAVE_VERSION_ID,
                'is_autosave': True,
                'timestamp': datetime.strptime(autosave_timestamp, '%Y-%m-%dT%H:%M:%SZ').strftime('%Y-%m-%dT%H-%M-%S') if autosave_timestamp else None,
                'timestamp_source': 'version_json_mtime_utc',
                'description': 'Latest Autosave',
                'is_autosave_snapshot': False,
                'has_version_json': True,
                'version_json_mtime_utc': autosave_timestamp,
                'source_path_checks': autosave_source['source_path_checks'],
                'sim_run_count': 0,
            })

    for version_id in manual_version_ids:
        source = _build_version_source_metadata(pm, project_name_norm, version_id)
        sim_runs_path = os.path.join(versions_root, version_id, 'sim_runs')

        versions.append({
            'version_id': version_id,
            'is_autosave': False,
            'timestamp': source['timestamp_from_version_id'],
            'timestamp_source': 'version_id_prefix',
            'description': source['description_from_version_id'],
            'is_autosave_snapshot': source['is_autosave_snapshot'],
            'has_version_json': source['version_json_exists'],
            'version_json_mtime_utc': source['version_json_mtime_utc'],
            'source_path_checks': source['source_path_checks'],
            'sim_run_count': len(os.listdir(sim_runs_path)) if os.path.isdir(sim_runs_path) else 0,
        })

    total_versions = len(versions)
    if limit_norm is not None:
        versions = versions[:limit_norm]

    return {
        'project_name': project_name_norm,
        'ordering_basis': 'autosave_first_then_manual_saved_desc_lexicographic',
        'manual_saved_ordering_basis': 'manual_saved_versions_sorted_desc_lexicographic',
        'versions_root': versions_root,
        'versions_root_exists': True,
        'total_versions': total_versions,
        'returned_versions': len(versions),
        'has_autosave': autosave_exists,
        'versions': versions,
    }


@app.route('/api/preflight/check', methods=['POST'])
def preflight_check_route():
    pm = get_project_manager_for_session()
    report = pm.run_preflight_checks()
    return jsonify({
        "success": True,
        "preflight_report": report,
    })


@app.route('/api/preflight/compare_summaries', methods=['POST'])
def preflight_compare_summaries_route():
    data = request.get_json(silent=True) or {}

    baseline_input = (
        data.get('baseline_summary')
        if data.get('baseline_summary') is not None
        else data.get('baseline_report')
    )
    candidate_input = (
        data.get('candidate_summary')
        if data.get('candidate_summary') is not None
        else data.get('candidate_report')
    )

    if baseline_input is None or candidate_input is None:
        return jsonify({
            "success": False,
            "error": "Missing required fields: baseline_summary and candidate_summary (or baseline_report/candidate_report).",
        }), 400

    try:
        comparison = compare_preflight_summaries(baseline_input, candidate_input)
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400

    return jsonify({
        "success": True,
        "comparison": comparison,
    })


@app.route('/api/preflight/compare_versions', methods=['POST'])
def preflight_compare_versions_route():
    pm = get_project_manager_for_session()
    data = request.get_json(silent=True) or {}

    baseline_version_id = (
        data.get('baseline_version_id')
        if data.get('baseline_version_id') is not None
        else data.get('baseline_version')
    )
    candidate_version_id = (
        data.get('candidate_version_id')
        if data.get('candidate_version_id') is not None
        else data.get('candidate_version')
    )
    project_name = data.get('project_name') or pm.project_name

    if baseline_version_id is None or candidate_version_id is None:
        return jsonify({
            "success": False,
            "error": "Missing required fields: baseline_version_id and candidate_version_id.",
        }), 400

    try:
        result = compare_preflight_versions(
            pm,
            baseline_version_id=baseline_version_id,
            candidate_version_id=candidate_version_id,
            project_name=project_name,
        )
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except FileNotFoundError as exc:
        return jsonify({"success": False, "error": str(exc)}), 404

    return jsonify({
        "success": True,
        **result,
    })


@app.route('/api/preflight/compare_latest_versions', methods=['POST'])
def preflight_compare_latest_versions_route():
    pm = get_project_manager_for_session()
    data = request.get_json(silent=True) or {}
    project_name = data.get('project_name') or pm.project_name

    try:
        result = compare_latest_preflight_versions(pm, project_name=project_name)
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except FileNotFoundError as exc:
        return jsonify({"success": False, "error": str(exc)}), 404

    return jsonify({
        "success": True,
        **result,
    })


@app.route('/api/preflight/compare_autosave_vs_latest_saved', methods=['POST'])
def preflight_compare_autosave_vs_latest_saved_route():
    pm = get_project_manager_for_session()
    data = request.get_json(silent=True) or {}
    project_name = data.get('project_name') or pm.project_name

    try:
        result = compare_autosave_preflight_vs_latest_saved(pm, project_name=project_name)
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except FileNotFoundError as exc:
        return jsonify({"success": False, "error": str(exc)}), 404

    return jsonify({
        "success": True,
        **result,
    })


@app.route('/api/preflight/compare_autosave_vs_previous_manual_saved', methods=['POST'])
def preflight_compare_autosave_vs_previous_manual_saved_route():
    pm = get_project_manager_for_session()
    data = request.get_json(silent=True) or {}
    project_name = data.get('project_name') or pm.project_name

    try:
        result = compare_autosave_preflight_vs_previous_manual_saved(
            pm,
            project_name=project_name,
        )
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except FileNotFoundError as exc:
        return jsonify({"success": False, "error": str(exc)}), 404

    return jsonify({
        "success": True,
        **result,
    })


@app.route('/api/preflight/compare_autosave_vs_manual_saved_index', methods=['POST'])
def preflight_compare_autosave_vs_manual_saved_index_route():
    pm = get_project_manager_for_session()
    data = request.get_json(silent=True) or {}
    project_name = data.get('project_name') or pm.project_name

    manual_saved_index = (
        data.get('manual_saved_index')
        if data.get('manual_saved_index') is not None
        else data.get('manual_saved_n_back')
    )
    if manual_saved_index is None:
        manual_saved_index = data.get('n_back')

    try:
        result = compare_autosave_preflight_vs_manual_saved_index(
            pm,
            manual_saved_index=manual_saved_index,
            project_name=project_name,
        )
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except FileNotFoundError as exc:
        return jsonify({"success": False, "error": str(exc)}), 404

    return jsonify({
        "success": True,
        **result,
    })


@app.route('/api/preflight/compare_autosave_vs_manual_saved_for_simulation_run', methods=['POST'])
def preflight_compare_autosave_vs_manual_saved_for_simulation_run_route():
    pm = get_project_manager_for_session()
    data = request.get_json(silent=True) or {}
    project_name = data.get('project_name') or pm.project_name

    simulation_run_id = (
        data.get('simulation_run_id')
        if data.get('simulation_run_id') is not None
        else data.get('run_id')
    )
    if simulation_run_id is None:
        simulation_run_id = data.get('job_id')

    if simulation_run_id is None:
        return jsonify({
            "success": False,
            "error": "Missing required field: simulation_run_id (or run_id/job_id).",
        }), 400

    try:
        result = compare_autosave_preflight_vs_manual_saved_for_simulation_run(
            pm,
            simulation_run_id=simulation_run_id,
            project_name=project_name,
        )
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except FileNotFoundError as exc:
        return jsonify({"success": False, "error": str(exc)}), 404

    return jsonify({
        "success": True,
        **result,
    })


@app.route('/api/preflight/compare_autosave_vs_manual_saved_for_simulation_run_index', methods=['POST'])
def preflight_compare_autosave_vs_manual_saved_for_simulation_run_index_route():
    pm = get_project_manager_for_session()
    data = request.get_json(silent=True) or {}
    project_name = data.get('project_name') or pm.project_name

    simulation_run_id = (
        data.get('simulation_run_id')
        if data.get('simulation_run_id') is not None
        else data.get('run_id')
    )
    if simulation_run_id is None:
        simulation_run_id = data.get('job_id')

    if simulation_run_id is None:
        return jsonify({
            "success": False,
            "error": "Missing required field: simulation_run_id (or run_id/job_id).",
        }), 400

    manual_saved_index = (
        data.get('manual_saved_index')
        if data.get('manual_saved_index') is not None
        else data.get('manual_saved_n_back')
    )
    if manual_saved_index is None:
        manual_saved_index = data.get('n_back')

    try:
        result = compare_autosave_preflight_vs_manual_saved_for_simulation_run_index(
            pm,
            simulation_run_id=simulation_run_id,
            manual_saved_index=manual_saved_index,
            project_name=project_name,
        )
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except FileNotFoundError as exc:
        return jsonify({"success": False, "error": str(exc)}), 404

    return jsonify({
        "success": True,
        **result,
    })


@app.route('/api/preflight/list_manual_saved_versions_for_simulation_run', methods=['POST'])
def preflight_list_manual_saved_versions_for_simulation_run_route():
    pm = get_project_manager_for_session()
    data = request.get_json(silent=True) or {}
    project_name = data.get('project_name') or pm.project_name

    simulation_run_id = (
        data.get('simulation_run_id')
        if data.get('simulation_run_id') is not None
        else data.get('run_id')
    )
    if simulation_run_id is None:
        simulation_run_id = data.get('job_id')

    if simulation_run_id is None:
        return jsonify({
            "success": False,
            "error": "Missing required field: simulation_run_id (or run_id/job_id).",
        }), 400

    limit = data.get('limit')
    if limit is None:
        limit = data.get('max_versions')
    if limit is None:
        limit = data.get('count')

    try:
        result = list_manual_saved_versions_for_simulation_run(
            pm,
            simulation_run_id=simulation_run_id,
            project_name=project_name,
            limit=limit,
        )
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400

    return jsonify({
        "success": True,
        **result,
    })


@app.route('/api/preflight/compare_manual_saved_versions_for_simulation_run_indices', methods=['POST'])
def preflight_compare_manual_saved_versions_for_simulation_run_indices_route():
    pm = get_project_manager_for_session()
    data = request.get_json(silent=True) or {}
    project_name = data.get('project_name') or pm.project_name

    simulation_run_id = (
        data.get('simulation_run_id')
        if data.get('simulation_run_id') is not None
        else data.get('run_id')
    )
    if simulation_run_id is None:
        simulation_run_id = data.get('job_id')

    if simulation_run_id is None:
        return jsonify({
            "success": False,
            "error": "Missing required field: simulation_run_id (or run_id/job_id).",
        }), 400

    baseline_manual_saved_index = (
        data.get('baseline_manual_saved_index')
        if data.get('baseline_manual_saved_index') is not None
        else data.get('baseline_manual_saved_n_back')
    )
    if baseline_manual_saved_index is None:
        baseline_manual_saved_index = data.get('baseline_n_back')
    if baseline_manual_saved_index is None:
        baseline_manual_saved_index = data.get('baseline_index')

    candidate_manual_saved_index = (
        data.get('candidate_manual_saved_index')
        if data.get('candidate_manual_saved_index') is not None
        else data.get('candidate_manual_saved_n_back')
    )
    if candidate_manual_saved_index is None:
        candidate_manual_saved_index = data.get('candidate_n_back')
    if candidate_manual_saved_index is None:
        candidate_manual_saved_index = data.get('candidate_index')

    try:
        result = compare_manual_preflight_versions_for_simulation_run_indices(
            pm,
            simulation_run_id=simulation_run_id,
            baseline_manual_saved_index=baseline_manual_saved_index,
            candidate_manual_saved_index=candidate_manual_saved_index,
            project_name=project_name,
        )
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except FileNotFoundError as exc:
        return jsonify({"success": False, "error": str(exc)}), 404

    return jsonify({
        "success": True,
        **result,
    })


@app.route('/api/preflight/compare_autosave_vs_saved_version', methods=['POST'])
def preflight_compare_autosave_vs_saved_version_route():
    pm = get_project_manager_for_session()
    data = request.get_json(silent=True) or {}
    project_name = data.get('project_name') or pm.project_name

    saved_version_id = (
        data.get('saved_version_id')
        if data.get('saved_version_id') is not None
        else data.get('saved_version')
    )
    if saved_version_id is None:
        saved_version_id = data.get('version_id')

    if saved_version_id is None:
        return jsonify({
            "success": False,
            "error": "Missing required field: saved_version_id (or saved_version/version_id).",
        }), 400

    try:
        result = compare_autosave_preflight_vs_saved_version(
            pm,
            saved_version_id=saved_version_id,
            project_name=project_name,
        )
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except FileNotFoundError as exc:
        return jsonify({"success": False, "error": str(exc)}), 404

    return jsonify({
        "success": True,
        **result,
    })


@app.route('/api/preflight/compare_autosave_vs_snapshot_version', methods=['POST'])
def preflight_compare_autosave_vs_snapshot_version_route():
    pm = get_project_manager_for_session()
    data = request.get_json(silent=True) or {}
    project_name = data.get('project_name') or pm.project_name

    autosave_snapshot_version_id = (
        data.get('autosave_snapshot_version_id')
        if data.get('autosave_snapshot_version_id') is not None
        else data.get('snapshot_version_id')
    )
    if autosave_snapshot_version_id is None:
        autosave_snapshot_version_id = data.get('snapshot_version')
    if autosave_snapshot_version_id is None:
        autosave_snapshot_version_id = data.get('version_id')

    if autosave_snapshot_version_id is None:
        return jsonify({
            "success": False,
            "error": "Missing required field: autosave_snapshot_version_id (or snapshot_version_id/snapshot_version/version_id).",
        }), 400

    try:
        result = compare_autosave_preflight_vs_snapshot_version(
            pm,
            autosave_snapshot_version_id=autosave_snapshot_version_id,
            project_name=project_name,
        )
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except FileNotFoundError as exc:
        return jsonify({"success": False, "error": str(exc)}), 404

    return jsonify({
        "success": True,
        **result,
    })


@app.route('/api/preflight/compare_autosave_vs_latest_snapshot', methods=['POST'])
def preflight_compare_autosave_vs_latest_snapshot_route():
    pm = get_project_manager_for_session()
    data = request.get_json(silent=True) or {}
    project_name = data.get('project_name') or pm.project_name

    try:
        result = compare_autosave_preflight_vs_latest_snapshot(
            pm,
            project_name=project_name,
        )
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except FileNotFoundError as exc:
        return jsonify({"success": False, "error": str(exc)}), 404

    return jsonify({
        "success": True,
        **result,
    })


@app.route('/api/preflight/compare_autosave_vs_previous_snapshot', methods=['POST'])
def preflight_compare_autosave_vs_previous_snapshot_route():
    pm = get_project_manager_for_session()
    data = request.get_json(silent=True) or {}
    project_name = data.get('project_name') or pm.project_name

    try:
        result = compare_autosave_preflight_vs_previous_snapshot(
            pm,
            project_name=project_name,
        )
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except FileNotFoundError as exc:
        return jsonify({"success": False, "error": str(exc)}), 404

    return jsonify({
        "success": True,
        **result,
    })


@app.route('/api/preflight/compare_snapshot_versions', methods=['POST'])
def preflight_compare_snapshot_versions_route():
    pm = get_project_manager_for_session()
    data = request.get_json(silent=True) or {}
    project_name = data.get('project_name') or pm.project_name

    baseline_snapshot_version_id = (
        data.get('baseline_snapshot_version_id')
        if data.get('baseline_snapshot_version_id') is not None
        else data.get('baseline_snapshot_version')
    )
    if baseline_snapshot_version_id is None:
        baseline_snapshot_version_id = data.get('baseline_version_id')
    if baseline_snapshot_version_id is None:
        baseline_snapshot_version_id = data.get('baseline_version')

    candidate_snapshot_version_id = (
        data.get('candidate_snapshot_version_id')
        if data.get('candidate_snapshot_version_id') is not None
        else data.get('candidate_snapshot_version')
    )
    if candidate_snapshot_version_id is None:
        candidate_snapshot_version_id = data.get('candidate_version_id')
    if candidate_snapshot_version_id is None:
        candidate_snapshot_version_id = data.get('candidate_version')

    missing_fields = []
    if baseline_snapshot_version_id is None:
        missing_fields.append('baseline_snapshot_version_id (or baseline_snapshot_version/baseline_version_id/baseline_version)')
    if candidate_snapshot_version_id is None:
        missing_fields.append('candidate_snapshot_version_id (or candidate_snapshot_version/candidate_version_id/candidate_version)')

    if missing_fields:
        return jsonify({
            "success": False,
            "error": f"Missing required field(s): {', '.join(missing_fields)}.",
        }), 400

    try:
        result = compare_autosave_snapshot_preflight_versions(
            pm,
            baseline_snapshot_version_id=baseline_snapshot_version_id,
            candidate_snapshot_version_id=candidate_snapshot_version_id,
            project_name=project_name,
        )
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except FileNotFoundError as exc:
        return jsonify({"success": False, "error": str(exc)}), 404

    return jsonify({
        "success": True,
        **result,
    })


@app.route('/api/preflight/compare_latest_snapshot_versions', methods=['POST'])
def preflight_compare_latest_snapshot_versions_route():
    pm = get_project_manager_for_session()
    data = request.get_json(silent=True) or {}
    project_name = data.get('project_name') or pm.project_name

    try:
        result = compare_latest_autosave_snapshot_preflight_versions(
            pm,
            project_name=project_name,
        )
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except FileNotFoundError as exc:
        return jsonify({"success": False, "error": str(exc)}), 404

    return jsonify({
        "success": True,
        **result,
    })


@app.route('/api/preflight/list_versions', methods=['POST'])
def preflight_list_versions_route():
    pm = get_project_manager_for_session()
    data = request.get_json(silent=True) or {}

    project_name = data.get('project_name') or pm.project_name

    if 'include_autosave' in data:
        include_autosave = data.get('include_autosave')
    elif 'include_latest_autosave' in data:
        include_autosave = data.get('include_latest_autosave')
    else:
        include_autosave = True

    if 'limit' in data:
        limit = data.get('limit')
    elif 'max_versions' in data:
        limit = data.get('max_versions')
    elif 'count' in data:
        limit = data.get('count')
    else:
        limit = None

    try:
        result = list_preflight_versions(
            pm,
            project_name=project_name,
            include_autosave=include_autosave,
            limit=limit,
        )
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400

    return jsonify({
        "success": True,
        **result,
    })


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

    preflight_report = pm.run_preflight_checks()
    if not preflight_report.get('summary', {}).get('can_run', False):
        return jsonify({
            "success": False,
            "error": "Preflight checks failed. Resolve errors before running simulation.",
            "preflight_report": preflight_report,
        }), 400

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
            "version_id": version_id,
            "preflight_summary": preflight_report.get('summary', {}),
        })

    except Exception as e:
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500

def _coerce_bool(value: Any, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        v = value.strip().lower()
        if v in {"1", "true", "yes", "y", "on"}:
            return True
        if v in {"0", "false", "no", "n", "off"}:
            return False
    return default


def _normalize_sim_log_source(value: Any) -> str:
    log_source = (str(value or "both")).strip().lower()
    if log_source not in {"stdout", "stderr", "both"}:
        return "both"
    return log_source


def _normalize_log_contains_term(value: Any) -> Optional[str]:
    if value is None:
        return None
    normalized = str(value).strip().lower()
    if not normalized:
        return None
    return normalized


def _normalize_log_contains_any_terms(raw_terms: Any, *, split_commas: bool = False) -> Optional[List[str]]:
    if raw_terms is None:
        return None

    if isinstance(raw_terms, (list, tuple, set)):
        items = list(raw_terms)
    else:
        items = [raw_terms]

    normalized_terms: List[str] = []
    for term in items:
        parts = str(term).split(',') if split_commas else [term]
        for part in parts:
            normalized = str(part).strip().lower()
            if normalized and normalized not in normalized_terms:
                normalized_terms.append(normalized)

    if not normalized_terms:
        return None
    return normalized_terms


def _parse_nonnegative_int_arg(value: Any, *, arg_name: str) -> tuple[Optional[int], Optional[str]]:
    if value is None:
        return None, None

    # Keep validation strict and deterministic across HTTP (string args) and
    # AI tool calls (native JSON types): bools and non-integral floats should
    # not silently coerce to integers.
    if isinstance(value, bool):
        return None, f"Argument '{arg_name}' must be an integer >= 0."

    if isinstance(value, float) and not value.is_integer():
        return None, f"Argument '{arg_name}' must be an integer >= 0."

    try:
        parsed = int(value)
    except Exception:
        return None, f"Argument '{arg_name}' must be an integer >= 0."

    if parsed < 0:
        return None, f"Argument '{arg_name}' must be an integer >= 0."

    return parsed, None


def _parse_simulation_status_log_options(
    *,
    get_value,
    has_key,
    get_list=None,
    include_log_summary_default: bool,
    include_log_entries_default: bool,
    tail_lines_default: Optional[int],
    apply_legacy_since_default: bool,
    split_commas_for_contains_any: bool,
) -> tuple[Optional[Dict[str, Any]], Optional[str]]:
    include_logs = _coerce_bool(get_value('include_logs'), default=True)
    include_log_summary = _coerce_bool(get_value('include_log_summary'), default=include_log_summary_default)
    include_log_entries = _coerce_bool(get_value('include_log_entries'), default=include_log_entries_default)

    since = None
    has_since = bool(has_key('since'))
    if has_since:
        since, err = _parse_nonnegative_int_arg(get_value('since'), arg_name='since')
        if err:
            return None, err

    has_tail_lines = bool(has_key('tail_lines'))
    if has_tail_lines:
        tail_lines, err = _parse_nonnegative_int_arg(get_value('tail_lines'), arg_name='tail_lines')
        if err:
            return None, err
    else:
        tail_lines = tail_lines_default

    if apply_legacy_since_default and since is None and not has_tail_lines:
        since = 0

    max_lines = None
    if get_value('max_lines') is not None:
        max_lines, err = _parse_nonnegative_int_arg(get_value('max_lines'), arg_name='max_lines')
        if err:
            return None, err

    log_source = _normalize_sim_log_source(get_value('log_source', 'both'))

    log_contains = _normalize_log_contains_term(get_value('log_contains'))
    if log_contains is None:
        log_contains = _normalize_log_contains_term(get_value('contains'))

    raw_contains_any = None
    if get_list is not None:
        raw_contains_any = get_list('log_contains_any')
        if not raw_contains_any:
            raw_contains_any = get_list('search_any')
        if not raw_contains_any:
            raw_contains_any = get_list('contains_any')

    if raw_contains_any in (None, []):
        raw_contains_any = get_value('log_contains_any')
    if raw_contains_any in (None, []):
        raw_contains_any = get_value('search_any')
    if raw_contains_any in (None, []):
        raw_contains_any = get_value('contains_any')

    log_contains_any_terms = _normalize_log_contains_any_terms(
        raw_contains_any,
        split_commas=split_commas_for_contains_any,
    )

    return {
        'include_logs': include_logs,
        'include_log_summary': include_log_summary,
        'include_log_entries': include_log_entries,
        'since': since,
        'tail_lines': tail_lines,
        'max_lines': max_lines,
        'log_source': log_source,
        'log_contains': log_contains,
        'log_contains_any_terms': log_contains_any_terms,
    }, None


def _build_simulation_log_payload(
    stdout_lines: List[Any],
    stderr_lines: List[Any],
    *,
    include_logs: bool,
    include_log_summary: bool,
    include_log_entries: bool,
    log_source: str,
    log_contains: Optional[str],
    log_contains_any_terms: Optional[List[str]],
    since: Optional[int],
    tail_lines: Optional[int],
    max_lines: Optional[int],
    include_legacy_fields: bool,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {}

    if include_log_summary:
        payload["log_summary"] = {
            "stdout_lines": len(stdout_lines),
            "stderr_lines": len(stderr_lines),
            "has_errors": len(stderr_lines) > 0,
            "latest_stdout": stdout_lines[-1] if stdout_lines else None,
            "latest_stderr": stderr_lines[-1] if stderr_lines else None,
        }

    if not include_logs:
        return payload

    selected_entries = []

    def _append_log_line(source: str, line: Any) -> None:
        text_line = str(line)
        text_line_lower = text_line.lower()
        if log_contains is not None and log_contains not in text_line_lower:
            return
        if log_contains_any_terms is not None and not any(term in text_line_lower for term in log_contains_any_terms):
            return
        selected_entries.append({
            "cursor": len(selected_entries),
            "source": source,
            "line": text_line,
        })

    if log_source in {"stdout", "both"}:
        for line in stdout_lines:
            _append_log_line("stdout", line)
    if log_source in {"stderr", "both"}:
        for line in stderr_lines:
            _append_log_line("stderr", line)

    total_lines = len(selected_entries)
    cursor = 0

    if since is not None:
        cursor = min(since, total_lines)
        log_entries = selected_entries[cursor:]
    elif tail_lines and tail_lines > 0:
        log_entries = selected_entries[-tail_lines:]
    else:
        log_entries = []

    if max_lines is not None and len(log_entries) > max_lines:
        if since is not None:
            log_entries = log_entries[:max_lines]
        else:
            log_entries = log_entries[-max_lines:] if max_lines > 0 else []

    log_lines = [
        entry["line"] if entry["source"] == "stdout" else f"stderr: {entry['line']}"
        for entry in log_entries
    ]

    if since is not None:
        next_since = cursor + len(log_entries)
        has_more_logs = next_since < total_lines
    else:
        next_since = total_lines
        has_more_logs = total_lines > len(log_entries)

    if include_legacy_fields:
        payload['new_stdout'] = log_lines
        payload['total_lines'] = total_lines

    payload['log_total_lines'] = total_lines
    payload['next_since'] = next_since
    payload['has_more_logs'] = has_more_logs
    payload['log_lines'] = log_lines
    payload['returned_lines'] = len(log_lines)
    if include_log_entries:
        payload['log_entries'] = log_entries

    return payload


@app.route('/api/simulation/status/<job_id>', methods=['GET'])
def get_simulation_status(job_id):
    parsed_opts, err = _parse_simulation_status_log_options(
        get_value=request.args.get,
        has_key=lambda key: key in request.args,
        get_list=request.args.getlist,
        include_log_summary_default=False,
        include_log_entries_default=False,
        tail_lines_default=None,
        apply_legacy_since_default=True,
        split_commas_for_contains_any=True,
    )
    if err:
        return jsonify({"success": False, "error": err}), 400

    include_logs = parsed_opts['include_logs']
    include_log_summary = parsed_opts['include_log_summary']
    include_log_entries = parsed_opts['include_log_entries']
    since = parsed_opts['since']
    tail_lines = parsed_opts['tail_lines']
    max_lines = parsed_opts['max_lines']
    log_source = parsed_opts['log_source']
    log_contains = parsed_opts['log_contains']
    log_contains_any_terms = parsed_opts['log_contains_any_terms']

    with SIMULATION_LOCK:
        status = SIMULATION_STATUS.get(job_id)
        if not status:
            return jsonify({"success": False, "error": "Job ID not found."}), 404

        stdout_lines = list(status.get('stdout') or [])
        stderr_raw = list(status.get('stderr') or [])

        status_copy = {
            "status": status["status"],
            "progress": status["progress"],
            "total_events": status["total_events"],
        }
        status_copy.update(_build_simulation_log_payload(
            stdout_lines,
            stderr_raw,
            include_logs=include_logs,
            include_log_summary=include_log_summary,
            include_log_entries=include_log_entries,
            log_source=log_source,
            log_contains=log_contains,
            log_contains_any_terms=log_contains_any_terms,
            since=since,
            tail_lines=tail_lines,
            max_lines=max_lines,
            include_legacy_fields=True,
        ))

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

def _build_simulation_candidate_evaluator(
    pm,
    sim_params,
    sim_objectives,
    *,
    context_static=None,
    keep_candidate_runs=False,
    candidate_runs_root=None,
):
    static_ctx = dict(context_static or {})
    keep_runs = bool(keep_candidate_runs)
    candidate_runs_root = candidate_runs_root or os.path.join(os.getcwd(), "surrogate", "simloop_runs")
    candidate_runs_root = os.path.abspath(candidate_runs_root)
    if keep_runs:
        os.makedirs(candidate_runs_root, exist_ok=True)

    def evaluator(*, run_record, project_manager, study):
        job_id = str(uuid.uuid4())

        with tempfile.TemporaryDirectory(prefix="simloop_") as tmp:
            version_dir = os.path.join(tmp, "version")
            os.makedirs(version_dir, exist_ok=True)

            state_payload = json.dumps(project_manager.current_geometry_state.to_dict(), indent=2)
            with open(os.path.join(version_dir, "version.json"), "w", encoding="utf-8") as f:
                f.write(state_payload)

            run_dir = os.path.join(version_dir, "sim_runs", job_id)
            os.makedirs(run_dir, exist_ok=True)

            try:
                project_manager.generate_macro_file(
                    job_id=job_id,
                    sim_params=sim_params,
                    build_dir=GEANT4_BUILD_DIR,
                    run_dir=run_dir,
                    version_dir=version_dir,
                )
            except Exception as e:
                return {
                    "success": False,
                    "error": f"Failed to generate macro for candidate: {e}",
                    "sim_metrics": {},
                    "simulation": {
                        "job_id": job_id,
                    },
                }

            run_g4_simulation(job_id=job_id, run_dir=run_dir, executable_path=GEANT4_EXECUTABLE, sim_params=sim_params)

            with SIMULATION_LOCK:
                status = dict(SIMULATION_STATUS.get(job_id, {}))
                SIMULATION_STATUS.pop(job_id, None)
                SIMULATION_PROCESSES.pop(job_id, None)

            if status.get("status") != "Completed":
                err_lines = status.get("stderr", []) if isinstance(status.get("stderr"), list) else []
                err_msg = err_lines[-1] if err_lines else "Simulation run failed."
                return {
                    "success": False,
                    "error": err_msg,
                    "sim_metrics": {},
                    "simulation": {
                        "job_id": job_id,
                        "status": status.get("status", "Error"),
                    },
                }

            output_path = os.path.join(run_dir, "output.hdf5")
            if not os.path.exists(output_path):
                return {
                    "success": False,
                    "error": "Simulation completed but output.hdf5 was not found.",
                    "sim_metrics": {},
                    "simulation": {
                        "job_id": job_id,
                        "status": "CompletedWithoutOutput",
                    },
                }

            context = {}
            context.update(static_ctx)
            context.update(run_record.get("values", {}) or {})
            context.update(run_record.get("metrics", {}) or {})

            sim_metrics, warnings, _available = extract_objective_values_from_hdf5(
                output_path=output_path,
                objectives=sim_objectives,
                context=context,
            )

            simulation_info = {
                "job_id": job_id,
                "status": "Completed",
                "warnings": warnings,
            }

            if keep_runs:
                candidate_dir = os.path.join(candidate_runs_root, f"candidate_{run_record.get('run_index', 0):04d}_{job_id}")
                shutil.copytree(run_dir, candidate_dir, dirs_exist_ok=True)
                simulation_info["saved_run_dir"] = candidate_dir

            return {
                "success": True,
                "sim_metrics": sim_metrics,
                "simulation": simulation_info,
            }

    return evaluator


def _read_hits_columns_for_objectives(output_path):
    """Read minimal columns needed for objective extraction."""
    with h5py.File(output_path, 'r') as f:
        if 'default_ntuples/Hits' not in f:
            raise RuntimeError("Hits data not found in output file.")

        hits_group = f['default_ntuples/Hits']

        num_entries = None
        if 'entries' in hits_group:
            try:
                ent_dset = hits_group['entries']
                if ent_dset.shape == ():
                    num_entries = int(ent_dset[()])
                else:
                    num_entries = int(ent_dset[0])
            except Exception:
                num_entries = None

        def get_col(name):
            if name not in hits_group:
                return np.array([])
            dset = hits_group[name]
            if isinstance(dset, h5py.Group) and 'pages' in dset:
                data = dset['pages'][:]
            elif isinstance(dset, h5py.Dataset):
                data = dset[:]
            else:
                return np.array([])
            if num_entries is not None and len(data) >= num_entries:
                return data[:num_entries]
            return data

        return {
            'Edep': get_col('Edep'),
            'CopyNo': get_col('CopyNo'),
            'ParticleName': get_col('ParticleName'),
        }


@app.route('/api/objective_builder/schema', methods=['GET'])
def objective_builder_schema_route():
    return jsonify({
        "success": True,
        "schema": _objective_builder_schema(),
    })


@app.route('/api/objective_builder/example', methods=['GET'])
def objective_builder_example_route():
    pm = get_project_manager_for_session()
    template_id = (request.args.get('template') or 'weighted_tradeoff').strip()

    schema = _objective_builder_schema()
    template_ids = [t.get('id') for t in (schema.get('templates') or []) if isinstance(t, dict) and t.get('id')]
    if template_id and template_ids and template_id not in template_ids:
        return jsonify({
            "success": False,
            "error": f"Unknown template '{template_id}'.",
            "available_templates": template_ids,
            "schema_version": schema.get('version'),
        }), 400

    payload = _objective_builder_example_payload(pm=pm, template_id=template_id or 'weighted_tradeoff')
    return jsonify({
        "success": True,
        "payload": payload,
        "template_id": payload.get('template_id'),
        "schema_version": schema.get('version'),
    })


@app.route('/api/objective_builder/validate', methods=['POST'])
def objective_builder_validate_route():
    pm = get_project_manager_for_session()
    payload = request.get_json() or {}
    if not isinstance(payload, dict):
        return jsonify({"success": False, "error": "Payload must be an object/dict."}), 400

    result = _validate_objective_builder_payload(payload, pm=pm)
    return jsonify({
        "success": True,
        "validation": result,
        "schema_version": _objective_builder_schema().get('version'),
    })


@app.route('/api/objective_builder/build', methods=['POST'])
def objective_builder_build_route():
    pm = get_project_manager_for_session()
    payload = request.get_json() or {}
    if not isinstance(payload, dict):
        return jsonify({"success": False, "error": "Payload must be an object/dict."}), 400

    validation = _validate_objective_builder_payload(payload, pm=pm)
    if not validation.get('valid'):
        return jsonify({
            "success": False,
            "error": "Objective builder payload is invalid.",
            "validation": validation,
            "schema_version": _objective_builder_schema().get('version'),
        }), 400

    build = _build_objective_builder_payload(payload, validation)
    return jsonify({
        "success": True,
        "build": build,
        "validation": validation,
        "schema_version": _objective_builder_schema().get('version'),
    })


@app.route('/api/objective_builder/upsert_study', methods=['POST'])
def objective_builder_upsert_study_route():
    pm = get_project_manager_for_session()
    payload = request.get_json() or {}
    if not isinstance(payload, dict):
        return jsonify({"success": False, "error": "Payload must be an object/dict."}), 400

    dry_run = bool(payload.get('dry_run', False))

    # Accept either full builder payload or direct study_upsert_payload from /build response.
    source = 'builder_payload'
    validation = None

    if isinstance(payload.get('study_upsert_payload'), dict):
        study_payload = dict(payload.get('study_upsert_payload') or {})
        source = 'study_upsert_payload'
    else:
        validation = _validate_objective_builder_payload(payload, pm=pm)
        if not validation.get('valid'):
            return jsonify({
                "success": False,
                "error": "Objective builder payload is invalid.",
                "validation": validation,
                "schema_version": _objective_builder_schema().get('version'),
            }), 400
        study_payload = dict((validation.get('normalized') or {}).get('study') or {})

    study_name = study_payload.get('name')
    if not study_name:
        return jsonify({"success": False, "error": "Study payload must include field 'name'."}), 400

    if dry_run:
        ok, err = pm._validate_param_study(study_name, study_payload)
        if not ok:
            return jsonify({
                "success": False,
                "error": err,
                "dry_run": True,
                "source": source,
            }), 400

        return jsonify({
            "success": True,
            "dry_run": True,
            "source": source,
            "study_name": study_name,
            "study_upsert_payload": study_payload,
            "validation": validation,
            "schema_version": _objective_builder_schema().get('version'),
        })

    existed = bool(pm.current_geometry_state and (study_name in (pm.current_geometry_state.param_studies or {})))
    upserted, err = pm.upsert_param_study(study_name, study_payload)
    if not upserted:
        return jsonify({
            "success": False,
            "error": err,
            "source": source,
            "study_upsert_payload": study_payload,
        }), 400

    return jsonify({
        "success": True,
        "dry_run": False,
        "source": source,
        "action": "updated" if existed else "created",
        "study": upserted,
        "study_name": study_name,
        "validation": validation,
        "schema_version": _objective_builder_schema().get('version'),
    })


@app.route('/api/objective_builder/launch', methods=['POST'])
def objective_builder_launch_route():
    pm = get_project_manager_for_session()
    payload = request.get_json() or {}
    if not isinstance(payload, dict):
        return jsonify({"success": False, "error": "Payload must be an object/dict."}), 400

    dry_run = bool(payload.get('dry_run', False))

    source = 'builder_payload'
    validation = None

    build_payload = payload.get('build')
    if isinstance(build_payload, dict):
        source = 'build_payload'
        build = dict(build_payload)
    else:
        validation = _validate_objective_builder_payload(payload, pm=pm)
        if not validation.get('valid'):
            return jsonify({
                "success": False,
                "error": "Objective builder payload is invalid.",
                "validation": validation,
                "schema_version": _objective_builder_schema().get('version'),
            }), 400
        build = _build_objective_builder_payload(payload, validation)

    study_payload = dict(build.get('study_upsert_payload') or {})
    study_name = study_payload.get('name')
    if not study_name:
        return jsonify({"success": False, "error": "Build payload must include study_upsert_payload.name."}), 400

    run_payload = dict(build.get('run_sim_loop_payload') or {})
    run_overrides = payload.get('run_overrides') or {}
    if run_overrides:
        if not isinstance(run_overrides, dict):
            return jsonify({"success": False, "error": "run_overrides must be an object/dict when provided."}), 400
        run_payload.update(run_overrides)

    run_payload['study_name'] = study_name
    if 'sim_objectives' not in run_payload:
        run_payload['sim_objectives'] = build.get('sim_objectives') or []
    if 'context' not in run_payload:
        run_payload['context'] = build.get('sim_context') or {}

    sim_objectives = run_payload.get('sim_objectives') or []
    if not isinstance(sim_objectives, list) or not sim_objectives:
        return jsonify({"success": False, "error": "sim_objectives must be a non-empty list."}), 400

    ok, err = pm._validate_param_study(study_name, study_payload)
    if not ok:
        return jsonify({
            "success": False,
            "error": err,
            "source": source,
            "study_upsert_payload": study_payload,
        }), 400

    existed = bool(pm.current_geometry_state and (study_name in (pm.current_geometry_state.param_studies or {})))

    normalized_run, policy_error = _validate_and_normalize_run_policy(run_payload, head_to_head=False)
    if policy_error:
        return jsonify({"success": False, **policy_error}), 400
    run_payload = normalized_run

    preflight_report = pm.run_preflight_checks()
    preflight_summary = preflight_report.get('summary', {})

    if dry_run:
        return jsonify({
            "success": True,
            "dry_run": True,
            "launched": False,
            "source": source,
            "study_action": "would_update" if existed else "would_create",
            "study_name": study_name,
            "study_upsert_payload": study_payload,
            "run_payload": run_payload,
            "preflight_summary": preflight_summary,
            "validation": validation,
            "schema_version": _objective_builder_schema().get('version'),
        })

    if not os.path.exists(GEANT4_EXECUTABLE):
        return jsonify({
            "success": False,
            "error": "Geant4 executable not found. Please compile the application in 'geant4/build'.",
        }), 500

    if not preflight_summary.get('can_run', False):
        return jsonify({
            "success": False,
            "error": "Preflight checks failed. Resolve errors before launching objective builder run.",
            "preflight_report": preflight_report,
        }), 400

    upserted, err = pm.upsert_param_study(study_name, study_payload)
    if not upserted:
        return jsonify({
            "success": False,
            "error": err,
            "source": source,
            "study_upsert_payload": study_payload,
        }), 400

    method = (run_payload.get('method') or 'surrogate_gp').strip().lower()
    if method not in {'surrogate_gp', 'random_search', 'cmaes'}:
        return jsonify({"success": False, "error": f"Unsupported method '{method}'."}), 400

    sim_params = run_payload.get('sim_params') or {}

    evaluator = _build_simulation_candidate_evaluator(
        pm=pm,
        sim_params=sim_params,
        sim_objectives=sim_objectives,
        context_static=(run_payload.get('context') or {}),
        keep_candidate_runs=bool(run_payload.get('keep_candidate_runs', False)),
        candidate_runs_root=run_payload.get('candidate_runs_root'),
    )

    control, response, status = _start_managed_optimizer_run(
        pm,
        run_payload,
        kind='objective_builder_launch',
        metadata={'study_name': study_name, 'method': method},
    )
    if response is not None:
        return response, status

    pm.update_managed_run_progress(
        total_evaluations=run_payload.get('budget', 20),
        evaluations_completed=0,
        success_count=0,
        failure_count=0,
        phase='starting',
        message=f"Objective Builder launch started ({method}).",
    )

    def _run_launch_job():
        final_status = 'completed'
        result, err = None, None
        try:
            if method == 'surrogate_gp':
                result, err = pm.run_simulation_in_loop_optimizer(
                    study_name=study_name,
                    method='surrogate_gp',
                    budget=run_payload.get('budget', 20),
                    seed=run_payload.get('seed', 42),
                    objective_name=run_payload.get('objective_name'),
                    direction=run_payload.get('direction'),
                    surrogate_config=run_payload.get('surrogate') or {},
                    evaluator=evaluator,
                )
            else:
                result, err = pm.run_simulation_in_loop_optimizer(
                    study_name=study_name,
                    method=method,
                    budget=run_payload.get('budget', 20),
                    seed=run_payload.get('seed', 42),
                    objective_name=run_payload.get('objective_name'),
                    direction=run_payload.get('direction'),
                    cmaes_config=run_payload.get('cmaes'),
                    evaluator=evaluator,
                )

            if err:
                final_status = 'failed'
            elif isinstance(result, dict) and result.get('stop_reason') in {'user_requested_stop', 'wall_time_exceeded'}:
                final_status = 'stopped'
        except Exception as ex:
            err = str(ex)
            final_status = 'failed'
        finally:
            details = {
                'study_name': study_name,
                'method': method,
                'stop_reason': (result or {}).get('stop_reason') if isinstance(result, dict) else None,
                'run_id': (result or {}).get('run_id') if isinstance(result, dict) else None,
                'evaluations_used': (result or {}).get('evaluations_used') if isinstance(result, dict) else None,
            }
            _finish_managed_optimizer_run(pm, status=final_status, details=details)

            with OBJECTIVE_BUILDER_LAUNCH_LOCK:
                rec = OBJECTIVE_BUILDER_LAUNCH_JOBS.get(control['run_control_id'], {})
                rec.update({
                    'job_status': final_status,
                    'completed_at': datetime.utcnow().isoformat() + 'Z',
                    'result': {
                        "success": bool(result),
                        "dry_run": False,
                        "launched": True,
                        "source": source,
                        "study_action": "updated" if existed else "created",
                        "study_name": study_name,
                        "study": upserted,
                        "optimizer_result": result,
                        "preflight_summary": preflight_summary,
                        "run_payload": run_payload,
                        "run_policy": run_payload.get('_run_policy'),
                        "validation": validation,
                        "schema_version": _objective_builder_schema().get('version'),
                    } if result else None,
                    'error': err,
                })
                OBJECTIVE_BUILDER_LAUNCH_JOBS[control['run_control_id']] = rec

    run_async = bool(payload.get('run_async', True))
    if run_async:
        run_control_id = control['run_control_id']
        with OBJECTIVE_BUILDER_LAUNCH_LOCK:
            OBJECTIVE_BUILDER_LAUNCH_JOBS[run_control_id] = {
                'job_status': 'running',
                'created_at': datetime.utcnow().isoformat() + 'Z',
                'study_name': study_name,
                'method': method,
                'result': None,
                'error': None,
            }

        t = threading.Thread(target=_run_launch_job, daemon=True)
        t.start()

        return jsonify({
            "success": True,
            "dry_run": False,
            "launched": True,
            "async": True,
            "run_control_id": run_control_id,
            "source": source,
            "study_action": "updated" if existed else "created",
            "study_name": study_name,
            "study": upserted,
            "preflight_summary": preflight_summary,
            "run_payload": run_payload,
            "run_policy": run_payload.get('_run_policy'),
            "validation": validation,
            "schema_version": _objective_builder_schema().get('version'),
        })

    _run_launch_job()
    with OBJECTIVE_BUILDER_LAUNCH_LOCK:
        rec = OBJECTIVE_BUILDER_LAUNCH_JOBS.get(control['run_control_id'], {})
    if rec.get('result'):
        return jsonify(rec['result'])
    return jsonify({"success": False, "error": rec.get('error') or 'Objective builder launch failed.'}), 400


@app.route('/api/objective_builder/launch_status/<run_control_id>', methods=['GET'])
def objective_builder_launch_status_route(run_control_id):
    pm = get_project_manager_for_session()
    managed = pm.get_managed_run_status()

    with OBJECTIVE_BUILDER_LAUNCH_LOCK:
        rec = OBJECTIVE_BUILDER_LAUNCH_JOBS.get(run_control_id)

    if not rec:
        return jsonify({"success": False, "error": f"No launch job found for run_control_id '{run_control_id}'."}), 404

    return jsonify({
        "success": True,
        "run_control_id": run_control_id,
        "job_status": rec.get('job_status', 'unknown'),
        "created_at": rec.get('created_at'),
        "completed_at": rec.get('completed_at'),
        "study_name": rec.get('study_name'),
        "method": rec.get('method'),
        "error": rec.get('error'),
        "result": rec.get('result'),
        "active_run": managed.get('active'),
        "last_run": managed.get('last'),
    })


@app.route('/api/objectives/extract/<version_id>/<job_id>', methods=['POST'])
def extract_objectives(version_id, job_id):
    pm = get_project_manager_for_session()
    version_dir = pm._get_version_dir(version_id)
    run_dir = os.path.join(version_dir, "sim_runs", job_id)
    output_path = os.path.join(run_dir, "output.hdf5")

    if not os.path.exists(output_path):
        return jsonify({"success": False, "error": "Simulation output not found."}), 404

    payload = request.get_json() or {}
    objectives = payload.get('objectives', []) or []
    if not isinstance(objectives, list):
        return jsonify({"success": False, "error": "objectives must be a list."}), 400

    try:
        context = payload.get('context', {}) or {}
        if not isinstance(context, dict):
            return jsonify({"success": False, "error": "context must be an object/dict when provided."}), 400

        objective_values, warnings, available_metrics = extract_objective_values_from_hdf5(
            output_path=output_path,
            objectives=objectives,
            context=context,
        )

        return jsonify({
            "success": True,
            "objective_values": objective_values,
            "warnings": warnings,
            "available_metrics": available_metrics,
        })
    except Exception as e:
        traceback.print_exc()
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
def create_success_response(project_manager, message="Success", exclude_unchanged_tessellated=True, extra_payload=None):
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

    payload = {
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
    }

    if isinstance(extra_payload, dict):
        payload.update(extra_payload)

    return jsonify(payload)

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

@app.route('/api/rename_version', methods=['POST'])
def rename_version_route():
    pm = get_project_manager_for_session()

    data = request.get_json() or {}
    project_name = data.get('project_name') or pm.project_name
    version_id = data.get('version_id')
    new_description = (data.get('new_description') or '').strip()

    if not version_id or not new_description:
        return jsonify({"success": False, "error": "version_id and new_description are required."}), 400

    if version_id == AUTOSAVE_VERSION_ID:
        return jsonify({"success": False, "error": "Autosave entry cannot be renamed."}), 400

    if '_' in version_id:
        timestamp = version_id.split('_', 1)[0]
    else:
        timestamp = version_id

    safe_desc = re.sub(r'[^a-zA-Z0-9_\- ]', '', new_description).strip().replace(' ', '_')
    if not safe_desc:
        return jsonify({"success": False, "error": "Description became empty after sanitization."}), 400

    new_version_id = f"{timestamp}_{safe_desc}"
    if new_version_id == version_id:
        return jsonify({"success": True, "message": "Version name unchanged.", "version_id": version_id})

    old_dir = os.path.join(pm.projects_dir, project_name, 'versions', version_id)
    new_dir = os.path.join(pm.projects_dir, project_name, 'versions', new_version_id)

    if not os.path.isdir(old_dir):
        return jsonify({"success": False, "error": f"Version '{version_id}' not found."}), 404
    if os.path.exists(new_dir):
        return jsonify({"success": False, "error": f"A version named '{new_version_id}' already exists."}), 409

    try:
        os.rename(old_dir, new_dir)
        if pm.current_version_id == version_id:
            pm.current_version_id = new_version_id
        return jsonify({"success": True, "message": "Version renamed.", "version_id": new_version_id})
    except Exception as e:
        return jsonify({"success": False, "error": f"Failed to rename version: {e}"}), 500

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
    
UPDATE_PROPERTY_ALLOWED_OBJECT_TYPES = {
    "define",
    "material",
    "solid",
    "logical_volume",
    "physical_volume",
}


def _normalize_update_property_payload(data):
    if not isinstance(data, dict):
        return None, "Invalid JSON payload for property update"

    normalized = {
        "object_type": data.get("object_type"),
        "object_id": data.get("object_id"),
        "property_path": data.get("property_path"),
        "new_value": data.get("new_value"),
    }

    for field in ("object_type", "object_id", "property_path"):
        raw_value = normalized[field]
        if not isinstance(raw_value, str) or not raw_value.strip():
            return None, f"Missing or invalid '{field}' for property update"
        normalized[field] = raw_value.strip()

    if normalized["object_type"] not in UPDATE_PROPERTY_ALLOWED_OBJECT_TYPES:
        return None, f"Unsupported object_type '{normalized['object_type']}' for property update"

    path_parts = normalized["property_path"].split(".")
    if any(not part for part in path_parts):
        return None, f"Invalid property_path '{normalized['property_path']}'"

    return normalized, None


def _status_code_for_update_property_failure(update_error):
    if not update_error:
        return 500

    error_text = str(update_error).strip().lower()
    if error_text.startswith("invalid property path"):
        return 400
    if error_text.startswith("could not find object"):
        return 404

    return 500


@app.route('/update_property', methods=['POST'])
def update_property_route():
    data = request.get_json(silent=True)
    normalized, validation_error = _normalize_update_property_payload(data)
    if validation_error:
        return jsonify({"success": False, "error": validation_error}), 400

    pm = get_project_manager_for_session()

    obj_type = normalized["object_type"]
    obj_id = normalized["object_id"]
    prop_path = normalized["property_path"]
    new_value = normalized["new_value"]

    update_result = pm.update_object_property(obj_type, obj_id, prop_path, new_value)
    update_error = None

    # Compatibility: older codepaths may still return a bare bool while
    # ProjectManager currently returns (success, error_message).
    if isinstance(update_result, tuple):
        success = bool(update_result[0])
        if len(update_result) > 1:
            update_error = update_result[1]
    else:
        success = bool(update_result)

    if success:
        return create_success_response(pm, "Property updated.")

    return jsonify({"success": False, "error": update_error or "Failed to update property"}), _status_code_for_update_property_failure(update_error)

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

@app.route('/api/parameter_registry/list', methods=['GET'])
def parameter_registry_list_route():
    pm = get_project_manager_for_session()
    registry = pm.list_parameter_registry()
    return jsonify({"success": True, "parameter_registry": registry})


@app.route('/api/parameter_registry/upsert', methods=['POST'])
def parameter_registry_upsert_route():
    pm = get_project_manager_for_session()

    data = request.get_json() or {}
    name = data.get('name')
    if not name:
        return jsonify({"success": False, "error": "Parameter name is required."}), 400

    entry, err = pm.upsert_parameter_registry_entry(name, data)
    if entry:
        return create_success_response(pm, f"Parameter '{name}' saved.")
    return jsonify({"success": False, "error": err}), 400


@app.route('/api/parameter_registry/delete', methods=['POST'])
def parameter_registry_delete_route():
    pm = get_project_manager_for_session()

    data = request.get_json() or {}
    name = data.get('name')
    if not name:
        return jsonify({"success": False, "error": "Parameter name is required."}), 400

    ok, err = pm.delete_parameter_registry_entry(name)
    if ok:
        return create_success_response(pm, f"Parameter '{name}' deleted.")
    return jsonify({"success": False, "error": err}), 404


@app.route('/api/param_study/list', methods=['GET'])
def param_study_list_route():
    pm = get_project_manager_for_session()
    studies = pm.list_param_studies()
    return jsonify({"success": True, "param_studies": studies})


@app.route('/api/param_study/upsert', methods=['POST'])
def param_study_upsert_route():
    pm = get_project_manager_for_session()
    data = request.get_json() or {}
    name = data.get('name')
    if not name:
        return jsonify({"success": False, "error": "Study name is required."}), 400

    study, err = pm.upsert_param_study(name, data)
    if study:
        return create_success_response(pm, f"Param study '{name}' saved.")
    return jsonify({"success": False, "error": err}), 400


@app.route('/api/param_study/delete', methods=['POST'])
def param_study_delete_route():
    pm = get_project_manager_for_session()
    data = request.get_json() or {}
    name = data.get('name')
    if not name:
        return jsonify({"success": False, "error": "Study name is required."}), 400

    ok, err = pm.delete_param_study(name)
    if ok:
        return create_success_response(pm, f"Param study '{name}' deleted.")
    return jsonify({"success": False, "error": err}), 404


@app.route('/api/param_study/run', methods=['POST'])
def param_study_run_route():
    pm = get_project_manager_for_session()
    data = request.get_json() or {}
    name = data.get('name')
    if not name:
        return jsonify({"success": False, "error": "Study name is required."}), 400

    normalized, policy_error = _validate_and_normalize_run_policy(data, head_to_head=False)
    if policy_error:
        return jsonify({"success": False, **policy_error}), 400
    data = normalized

    _, response, status = _start_managed_optimizer_run(
        pm,
        data,
        kind='param_study',
        metadata={'study_name': name},
    )
    if response is not None:
        return response, status

    max_runs = data.get('max_runs')
    final_status = 'completed'
    result, err = None, None
    try:
        result, err = pm.run_param_study(name, max_runs=max_runs)
        if err:
            final_status = 'failed'
        elif isinstance(result, dict) and result.get('stop_reason') in {'user_requested_stop', 'wall_time_exceeded'}:
            final_status = 'stopped'
    finally:
        details = {
            'study_name': name,
            'stop_reason': (result or {}).get('stop_reason') if isinstance(result, dict) else None,
            'evaluations_used': (result or {}).get('evaluations_used') if isinstance(result, dict) else None,
        }
        _finish_managed_optimizer_run(pm, status=final_status, details=details)

    if result:
        return jsonify({"success": True, "study_result": result, "run_policy": data.get('_run_policy')})
    return jsonify({"success": False, "error": err}), 400


@app.route('/api/param_study/apply_candidate', methods=['POST'])
def param_study_apply_candidate_route():
    pm = get_project_manager_for_session()
    data = request.get_json() or {}

    study_name = data.get('study_name') or data.get('name')
    values = data.get('values')

    if not study_name:
        return jsonify({"success": False, "error": "study_name is required."}), 400
    if not isinstance(values, dict) or not values:
        return jsonify({"success": False, "error": "values must be a non-empty object/dict."}), 400

    applied, err = pm.apply_study_candidate_values(study_name, values)
    if not applied:
        return jsonify({"success": False, "error": err}), 400

    response = create_success_response(pm, f"Applied candidate values to study '{study_name}'.")
    payload = response.get_json() or {}
    payload['applied_candidate'] = applied
    return jsonify(payload)


@app.route('/api/param_optimizer/list', methods=['GET'])
def param_optimizer_list_route():
    pm = get_project_manager_for_session()
    study_name = request.args.get('study_name')
    limit = request.args.get('limit', default=50, type=int)
    runs = pm.list_optimizer_runs(study_name=study_name, limit=limit)
    return jsonify({"success": True, "optimizer_runs": runs})


@app.route('/api/param_optimizer/active_run_status', methods=['GET'])
def param_optimizer_active_run_status_route():
    pm = get_project_manager_for_session()
    status = pm.get_managed_run_status()
    return jsonify({"success": True, **status})


@app.route('/api/param_optimizer/stop_active_run', methods=['POST'])
def param_optimizer_stop_active_run_route():
    pm = get_project_manager_for_session()
    data = request.get_json(silent=True) or {}
    reason = data.get('reason') if isinstance(data, dict) else None
    stop_result = pm.request_stop_managed_run(reason=reason or 'user_requested_stop')
    return jsonify({"success": True, **stop_result})


@app.route('/api/param_optimizer/run', methods=['POST'])
def param_optimizer_run_route():
    pm = get_project_manager_for_session()
    data = request.get_json() or {}

    study_name = data.get('study_name') or data.get('name')
    if not study_name:
        return jsonify({"success": False, "error": "study_name is required."}), 400

    normalized, policy_error = _validate_and_normalize_run_policy(data, head_to_head=False)
    if policy_error:
        return jsonify({"success": False, **policy_error}), 400
    data = normalized

    method = data.get('method', 'random_search')
    budget = data.get('budget', 20)
    seed = data.get('seed', 42)
    objective_name = data.get('objective_name')
    direction = data.get('direction')

    _, response, status = _start_managed_optimizer_run(
        pm,
        data,
        kind='optimizer',
        metadata={'study_name': study_name, 'method': method},
    )
    if response is not None:
        return response, status

    final_status = 'completed'
    result, err = None, None
    try:
        result, err = pm.run_param_optimizer(
            study_name=study_name,
            method=method,
            budget=budget,
            seed=seed,
            objective_name=objective_name,
            direction=direction,
            cmaes_config=data.get('cmaes'),
        )
        if err:
            final_status = 'failed'
        elif isinstance(result, dict) and result.get('stop_reason') in {'user_requested_stop', 'wall_time_exceeded'}:
            final_status = 'stopped'
    finally:
        details = {
            'study_name': study_name,
            'method': method,
            'stop_reason': (result or {}).get('stop_reason') if isinstance(result, dict) else None,
            'evaluations_used': (result or {}).get('evaluations_used') if isinstance(result, dict) else None,
            'run_id': (result or {}).get('run_id') if isinstance(result, dict) else None,
        }
        _finish_managed_optimizer_run(pm, status=final_status, details=details)

    if result:
        return jsonify({"success": True, "optimizer_result": result, "run_policy": data.get('_run_policy')})
    return jsonify({"success": False, "error": err}), 400


@app.route('/api/param_optimizer/run_surrogate', methods=['POST'])
def param_optimizer_run_surrogate_route():
    pm = get_project_manager_for_session()
    data = request.get_json() or {}

    study_name = data.get('study_name') or data.get('name')
    if not study_name:
        return jsonify({"success": False, "error": "study_name is required."}), 400

    normalized, policy_error = _validate_and_normalize_run_policy(data, head_to_head=False)
    if policy_error:
        return jsonify({"success": False, **policy_error}), 400
    data = normalized

    _, response, status = _start_managed_optimizer_run(
        pm,
        data,
        kind='surrogate_optimizer',
        metadata={'study_name': study_name, 'method': 'surrogate_gp'},
    )
    if response is not None:
        return response, status

    final_status = 'completed'
    result, err = None, None
    try:
        result, err = pm.run_surrogate_param_optimizer(
            study_name=study_name,
            budget=data.get('budget', 40),
            seed=data.get('seed', 42),
            objective_name=data.get('objective_name'),
            direction=data.get('direction'),
            warmup_runs=(data.get('surrogate') or {}).get('warmup_runs', 10),
            candidate_pool_size=(data.get('surrogate') or {}).get('candidate_pool_size', 256),
            exploration_beta=(data.get('surrogate') or {}).get('exploration_beta', data.get('exploration_beta', 1.0)),
            gp_noise=(data.get('surrogate') or {}).get('gp_noise', data.get('gp_noise', 1e-6)),
        )
        if err:
            final_status = 'failed'
        elif isinstance(result, dict) and result.get('stop_reason') in {'user_requested_stop', 'wall_time_exceeded'}:
            final_status = 'stopped'
    finally:
        details = {
            'study_name': study_name,
            'method': 'surrogate_gp',
            'stop_reason': (result or {}).get('stop_reason') if isinstance(result, dict) else None,
            'evaluations_used': (result or {}).get('evaluations_used') if isinstance(result, dict) else None,
            'run_id': (result or {}).get('run_id') if isinstance(result, dict) else None,
        }
        _finish_managed_optimizer_run(pm, status=final_status, details=details)

    if result:
        return jsonify({"success": True, "optimizer_result": result, "run_policy": data.get('_run_policy')})
    return jsonify({"success": False, "error": err}), 400


@app.route('/api/param_optimizer/head_to_head', methods=['POST'])
def param_optimizer_head_to_head_route():
    pm = get_project_manager_for_session()
    data = request.get_json() or {}

    study_name = data.get('study_name') or data.get('name')
    if not study_name:
        return jsonify({"success": False, "error": "study_name is required."}), 400

    normalized, policy_error = _validate_and_normalize_run_policy(data, head_to_head=True)
    if policy_error:
        return jsonify({"success": False, **policy_error}), 400
    data = normalized

    _, response, status = _start_managed_optimizer_run(
        pm,
        data,
        kind='head_to_head',
        metadata={'study_name': study_name, 'method': data.get('classical_method', 'cmaes')},
    )
    if response is not None:
        return response, status

    final_status = 'completed'
    result, err = None, None
    try:
        result, err = pm.run_optimizer_head_to_head(
            study_name=study_name,
            budget=data.get('budget', 40),
            seed=data.get('seed', 42),
            objective_name=data.get('objective_name'),
            direction=data.get('direction'),
            classical_method=data.get('classical_method', 'cmaes'),
            cmaes_config=data.get('cmaes'),
            surrogate_config=data.get('surrogate') or {},
        )
        if err:
            final_status = 'failed'
        else:
            stop_reasons = {
                ((result.get('classical') or {}).get('stop_reason')),
                ((result.get('surrogate') or {}).get('stop_reason')),
            }
            if 'user_requested_stop' in stop_reasons or 'wall_time_exceeded' in stop_reasons:
                final_status = 'stopped'
    finally:
        details = {
            'study_name': study_name,
            'method': 'head_to_head',
            'run_ids': (result or {}).get('run_ids') if isinstance(result, dict) else None,
        }
        _finish_managed_optimizer_run(pm, status=final_status, details=details)

    if result:
        return jsonify({"success": True, "comparison": result, "run_policy": data.get('_run_policy')})
    return jsonify({"success": False, "error": err}), 400


@app.route('/api/param_optimizer/run_simulation_in_loop', methods=['POST'])
def param_optimizer_run_simulation_in_loop_route():
    pm = get_project_manager_for_session()
    data = request.get_json() or {}

    study_name = data.get('study_name') or data.get('name')
    if not study_name:
        return jsonify({"success": False, "error": "study_name is required."}), 400

    if not os.path.exists(GEANT4_EXECUTABLE):
        return jsonify({
            "success": False,
            "error": "Geant4 executable not found. Please compile the application in 'geant4/build'.",
        }), 500

    sim_objectives = data.get('sim_objectives') or []
    if not isinstance(sim_objectives, list) or not sim_objectives:
        return jsonify({"success": False, "error": "sim_objectives must be a non-empty list."}), 400

    normalized, policy_error = _validate_and_normalize_run_policy(data, head_to_head=False)
    if policy_error:
        return jsonify({"success": False, **policy_error}), 400
    data = normalized
    sim_params = data['sim_params']

    preflight_report = pm.run_preflight_checks()
    if not preflight_report.get('summary', {}).get('can_run', False):
        return jsonify({
            "success": False,
            "error": "Preflight checks failed. Resolve errors before running simulation-in-loop optimization.",
            "preflight_report": preflight_report,
        }), 400

    method = (data.get('method') or 'surrogate_gp').strip().lower()

    evaluator = _build_simulation_candidate_evaluator(
        pm=pm,
        sim_params=sim_params,
        sim_objectives=sim_objectives,
        context_static=(data.get('context') or {}),
        keep_candidate_runs=bool(data.get('keep_candidate_runs', False)),
        candidate_runs_root=data.get('candidate_runs_root'),
    )

    _, response, status = _start_managed_optimizer_run(
        pm,
        data,
        kind='simulation_in_loop',
        metadata={'study_name': study_name, 'method': method},
    )
    if response is not None:
        return response, status

    final_status = 'completed'
    result, err = None, None
    try:
        if method == 'surrogate_gp':
            result, err = pm.run_simulation_in_loop_optimizer(
                study_name=study_name,
                method='surrogate_gp',
                budget=data.get('budget', 20),
                seed=data.get('seed', 42),
                objective_name=data.get('objective_name'),
                direction=data.get('direction'),
                surrogate_config=data.get('surrogate') or {},
                evaluator=evaluator,
            )
        elif method in {'random_search', 'cmaes'}:
            result, err = pm.run_simulation_in_loop_optimizer(
                study_name=study_name,
                method=method,
                budget=data.get('budget', 20),
                seed=data.get('seed', 42),
                objective_name=data.get('objective_name'),
                direction=data.get('direction'),
                cmaes_config=data.get('cmaes'),
                evaluator=evaluator,
            )
        else:
            final_status = 'failed'
            return jsonify({"success": False, "error": f"Unsupported method '{method}'."}), 400

        if err:
            final_status = 'failed'
        elif isinstance(result, dict) and result.get('stop_reason') in {'user_requested_stop', 'wall_time_exceeded'}:
            final_status = 'stopped'
    finally:
        details = {
            'study_name': study_name,
            'method': method,
            'stop_reason': (result or {}).get('stop_reason') if isinstance(result, dict) else None,
            'evaluations_used': (result or {}).get('evaluations_used') if isinstance(result, dict) else None,
            'run_id': (result or {}).get('run_id') if isinstance(result, dict) else None,
        }
        _finish_managed_optimizer_run(pm, status=final_status, details=details)

    if result:
        return jsonify({
            "success": True,
            "optimizer_result": result,
            "preflight_summary": preflight_report.get('summary', {}),
            "run_policy": data.get('_run_policy'),
        })
    return jsonify({"success": False, "error": err}), 400


@app.route('/api/param_optimizer/head_to_head_simulation_in_loop', methods=['POST'])
def param_optimizer_head_to_head_simulation_in_loop_route():
    pm = get_project_manager_for_session()
    data = request.get_json() or {}

    study_name = data.get('study_name') or data.get('name')
    if not study_name:
        return jsonify({"success": False, "error": "study_name is required."}), 400

    if not os.path.exists(GEANT4_EXECUTABLE):
        return jsonify({"success": False, "error": "Geant4 executable not found."}), 500

    sim_objectives = data.get('sim_objectives') or []
    if not isinstance(sim_objectives, list) or not sim_objectives:
        return jsonify({"success": False, "error": "sim_objectives must be a non-empty list."}), 400

    normalized, policy_error = _validate_and_normalize_run_policy(data, head_to_head=True)
    if policy_error:
        return jsonify({"success": False, **policy_error}), 400
    data = normalized
    sim_params = data['sim_params']

    preflight_report = pm.run_preflight_checks()
    if not preflight_report.get('summary', {}).get('can_run', False):
        return jsonify({
            "success": False,
            "error": "Preflight checks failed. Resolve errors before running simulation-in-loop optimization.",
            "preflight_report": preflight_report,
        }), 400

    evaluator = _build_simulation_candidate_evaluator(
        pm=pm,
        sim_params=sim_params,
        sim_objectives=sim_objectives,
        context_static=(data.get('context') or {}),
        keep_candidate_runs=bool(data.get('keep_candidate_runs', False)),
        candidate_runs_root=data.get('candidate_runs_root'),
    )

    _, response, status = _start_managed_optimizer_run(
        pm,
        data,
        kind='head_to_head_simulation_in_loop',
        metadata={'study_name': study_name, 'method': data.get('classical_method', 'cmaes')},
    )
    if response is not None:
        return response, status

    final_status = 'completed'
    result, err = None, None
    try:
        result, err = pm.run_optimizer_head_to_head(
            study_name=study_name,
            budget=data.get('budget', 20),
            seed=data.get('seed', 42),
            objective_name=data.get('objective_name'),
            direction=data.get('direction'),
            classical_method=data.get('classical_method', 'cmaes'),
            cmaes_config=data.get('cmaes'),
            surrogate_config=data.get('surrogate') or {},
            evaluator=evaluator,
        )

        if err:
            final_status = 'failed'
        elif isinstance(result, dict):
            stop_reasons = {
                ((result.get('classical') or {}).get('stop_reason')),
                ((result.get('surrogate') or {}).get('stop_reason')),
            }
            if 'user_requested_stop' in stop_reasons or 'wall_time_exceeded' in stop_reasons:
                final_status = 'stopped'
    finally:
        details = {
            'study_name': study_name,
            'method': 'head_to_head_simulation_in_loop',
            'run_ids': (result or {}).get('run_ids') if isinstance(result, dict) else None,
        }
        _finish_managed_optimizer_run(pm, status=final_status, details=details)

    if result:
        result['simulation_in_loop'] = True
        return jsonify({
            "success": True,
            "comparison": result,
            "preflight_summary": preflight_report.get('summary', {}),
            "run_policy": data.get('_run_policy'),
        })
    return jsonify({"success": False, "error": err}), 400


@app.route('/api/param_optimizer/apply_audit_history', methods=['GET'])
def param_optimizer_apply_audit_history_route():
    pm = get_project_manager_for_session()
    user_id = _current_user_id_for_policy()
    scope_id = _project_scope_id_for_policy(pm)

    limit_raw = request.args.get('limit', 20)
    try:
        limit = int(limit_raw)
    except Exception:
        limit = 20

    audits = _list_apply_audit_records(user_id, scope_id, limit=limit)
    return jsonify({
        "success": True,
        "audits": audits,
        "count": len(audits),
        "project_scope_id": scope_id,
    })


@app.route('/api/param_optimizer/apply_audit_diagnostics', methods=['GET'])
def param_optimizer_apply_audit_diagnostics_route():
    pm = get_project_manager_for_session()
    user_id = _current_user_id_for_policy()
    scope_id = _project_scope_id_for_policy(pm)

    user_key = str(user_id or 'local_user')
    scope_key = str(scope_id or 'default-scope')

    with APPLY_AUDIT_LOCK:
        user_scopes = APPLY_AUDIT_LOGS.get(user_key, {})
        if isinstance(user_scopes, dict):
            scope_entries = user_scopes.get(scope_key, [])
            default_entries = user_scopes.get('default-scope', [])
            scope_count = len(scope_entries) if isinstance(scope_entries, list) else 0
            legacy_default_count = len(default_entries) if isinstance(default_entries, list) else 0
            user_scope_count = len(user_scopes)
            total_user_entries = sum(len(v) for v in user_scopes.values() if isinstance(v, list))
        else:
            scope_count = 0
            legacy_default_count = 0
            user_scope_count = 0
            total_user_entries = 0

    storage_path = APPLY_AUDIT_STORAGE_FILE
    storage_exists = bool(storage_path and os.path.exists(storage_path))
    storage_size_bytes = os.path.getsize(storage_path) if storage_exists else 0

    return jsonify({
        "success": True,
        "project_scope_id": scope_key,
        "project_name": pm.project_name,
        "user_id": user_key,
        "scope_entry_count": scope_count,
        "legacy_default_scope_entry_count": legacy_default_count,
        "user_scope_count": user_scope_count,
        "user_total_entries": total_user_entries,
        "storage": {
            "path": storage_path,
            "exists": storage_exists,
            "size_bytes": storage_size_bytes,
            "max_entries_per_scope": APPLY_AUDIT_MAX_ENTRIES,
        },
    })


@app.route('/api/param_optimizer/rollback_last_apply', methods=['POST'])
def param_optimizer_rollback_last_apply_route():
    pm = get_project_manager_for_session()
    data = request.get_json() or {}

    user_id = _current_user_id_for_policy()
    scope_id = _project_scope_id_for_policy(pm)
    audits = _list_apply_audit_records(user_id, scope_id, limit=200)
    if not audits:
        return jsonify({"success": False, "error": "No apply audit entries found."}), 400

    audit_id = data.get('audit_id')
    latest_unrolled = next((a for a in audits if not a.get('rolled_back')), None)
    if latest_unrolled is None:
        return jsonify({"success": False, "error": "No unapplied rollback entries found."}), 400

    target = latest_unrolled
    if audit_id:
        match = next((a for a in audits if a.get('audit_id') == audit_id), None)
        if not match:
            return jsonify({"success": False, "error": "audit_id not found."}), 400
        target = match

    # Safety: only rollback the latest unapplied apply action.
    if target.get('audit_id') != latest_unrolled.get('audit_id'):
        return jsonify({
            "success": False,
            "error": "Only the latest unapplied apply action can be rolled back safely.",
            "latest_unrolled_audit_id": latest_unrolled.get('audit_id'),
        }), 400

    if not pm.current_geometry_state:
        return jsonify({"success": False, "error": "No active geometry state available to rollback."}), 400

    if pm.history_index < 0 or len(pm.history or []) == 0:
        return jsonify({"success": False, "error": "No history state available to rollback."}), 400

    # Constrained safety: rollback endpoint only supports undoing the current top-of-history
    # apply action recorded in audit. If history moved forward since apply, require manual undo.
    expected_top_index = target.get('history_post_apply_index')
    if expected_top_index is not None and pm.history_index != expected_top_index:
        return jsonify({
            "success": False,
            "error": "Rollback blocked: current history tip does not match selected apply action. Use manual Undo to reach that state.",
            "current_history_index": pm.history_index,
            "expected_history_index": expected_top_index,
        }), 400

    if pm.history_index <= 0:
        return jsonify({
            "success": False,
            "error": "Rollback blocked: cannot undo past initial history state.",
            "current_history_index": pm.history_index,
        }), 400

    undo_result, err = pm.undo()
    if not undo_result:
        return jsonify({"success": False, "error": err or "Rollback failed."}), 400

    rolled = _mark_apply_audit_rolled_back(user_id, scope_id, target.get('audit_id'))

    return create_success_response(
        pm,
        "Rolled back last applied optimizer candidate.",
        extra_payload={
            "rollback_result": undo_result,
            "rolled_back_audit": rolled,
            "apply_audits": _list_apply_audit_records(user_id, scope_id, limit=20),
            "project_scope_id": scope_id,
        }
    )


@app.route('/api/param_optimizer/replay_best', methods=['POST'])
def param_optimizer_replay_best_route():
    pm = get_project_manager_for_session()
    data = request.get_json() or {}
    run_id = data.get('run_id')
    if not run_id:
        return jsonify({"success": False, "error": "run_id is required."}), 400

    apply_policy, policy_error = _validate_apply_policy(data)
    if policy_error:
        return jsonify({"success": False, **policy_error}), 400

    apply_to_project = bool(apply_policy.get('apply_to_project', False))

    token_record = None
    if apply_to_project and RUN_POLICY_REQUIRE_VERIFY_TOKEN:
        user_id = _current_user_id_for_policy()
        token_record, token_err = _consume_verify_token(
            user_id=user_id,
            run_id=run_id,
            token=apply_policy.get('verification_token'),
        )
        if token_err:
            return jsonify({
                "success": False,
                "error": "Apply policy validation failed.",
                "details": [token_err],
                "policy": {
                    "require_verify_token": RUN_POLICY_REQUIRE_VERIFY_TOKEN,
                    "verify_token_ttl_seconds": RUN_POLICY_VERIFY_TOKEN_TTL_SECONDS,
                },
            }), 400

    pre_apply_history_index = pm.history_index
    pre_apply_history_size = len(pm.history or [])

    result, err = pm.replay_optimizer_best_candidate(run_id=run_id, apply_to_project=apply_to_project)
    if not result:
        return jsonify({"success": False, "error": err}), 400

    if apply_to_project:
        user_id = _current_user_id_for_policy()
        scope_id = _project_scope_id_for_policy(pm)
        replay_result = result.get('replay_result', {}) if isinstance(result, dict) else {}
        run_record = replay_result.get('run_record', {}) if isinstance(replay_result, dict) else {}

        audit_record = _append_apply_audit_record(user_id, scope_id, {
            'run_id': run_id,
            'project_name': pm.project_name,
            'project_scope_id': scope_id,
            'study_name': replay_result.get('study_name'),
            'candidate_run_index': run_record.get('run_index'),
            'candidate_success': bool(run_record.get('success', False)),
            'candidate_error': run_record.get('error'),
            'candidate_values': run_record.get('values', {}),
            'candidate_objectives': run_record.get('objectives', {}),
            'verification': token_record.get('verification_record') if token_record else None,
            'verification_token': {
                'run_id': token_record.get('run_id') if token_record else None,
                'issued_at': token_record.get('issued_at') if token_record else None,
                'used_at': token_record.get('used_at') if token_record else None,
                'expires_at': token_record.get('expires_at') if token_record else None,
            } if token_record else None,
            'history_pre_apply_index': pre_apply_history_index,
            'history_pre_apply_size': pre_apply_history_size,
            'history_post_apply_index': pm.history_index,
            'history_post_apply_size': len(pm.history or []),
        })

        return create_success_response(
            pm,
            f"Replayed best candidate from optimizer run '{run_id}'.",
            extra_payload={
                "replay_result": result,
                "apply_policy": apply_policy,
                "verification_token_record": {
                    "run_id": token_record.get('run_id') if token_record else None,
                    "issued_at": token_record.get('issued_at') if token_record else None,
                    "used_at": token_record.get('used_at') if token_record else None,
                    "expires_at": token_record.get('expires_at') if token_record else None,
                } if token_record else None,
                "apply_audit": audit_record,
                "apply_audits": _list_apply_audit_records(user_id, scope_id, limit=20),
                "project_scope_id": scope_id,
            }
        )

    return jsonify({"success": True, "replay_result": result, "apply_policy": apply_policy})


@app.route('/api/param_optimizer/verify_best', methods=['POST'])
def param_optimizer_verify_best_route():
    pm = get_project_manager_for_session()
    data = request.get_json() or {}
    run_id = data.get('run_id')
    if not run_id:
        return jsonify({"success": False, "error": "run_id is required."}), 400

    repeats = data.get('repeats', RUN_POLICY_VERIFY_MIN_REPEATS)
    result, err = pm.verify_optimizer_best_candidate(run_id=run_id, repeats=repeats)
    if not result:
        return jsonify({"success": False, "error": err}), 400

    gate = _evaluate_verification_gate(result, data)

    apply_token = None
    apply_token_record = None
    if gate.get('passed'):
        user_id = _current_user_id_for_policy()
        _cleanup_expired_verify_tokens(user_id)
        rec = _issue_verify_token(user_id=user_id, run_id=run_id, verification_record=result.get('verification_record'))
        apply_token = rec.get('token')
        apply_token_record = {
            'run_id': rec.get('run_id'),
            'issued_at': rec.get('issued_at'),
            'expires_at': rec.get('expires_at'),
        }

    return jsonify({
        "success": True,
        "verification_result": result,
        "verification_gate": gate,
        "apply_token": apply_token,
        "apply_token_record": apply_token_record,
    })


@app.route('/api/surrogate/dataset/export', methods=['POST'])
def surrogate_dataset_export_route():
    pm = get_project_manager_for_session()
    data = request.get_json() or {}

    output_root = data.get('output_root', 'surrogate/datasets')
    dataset_name = data.get('dataset_name')
    target_objective = data.get('target_objective')
    val_ratio = data.get('val_ratio', 0.2)
    split_seed = data.get('split_seed', 42)
    only_success = bool(data.get('only_success', False))

    payloads = []

    include_current_optimizer_runs = bool(data.get('include_current_optimizer_runs', True))
    if include_current_optimizer_runs:
        optimizer_runs = {}
        if pm.current_geometry_state:
            optimizer_runs = pm.current_geometry_state.optimizer_runs or {}
        payloads.append(("current_session.optimizer_runs", {"optimizer_runs": optimizer_runs}))

    if isinstance(data.get('study_result'), dict):
        payloads.append(("request.study_result", {"study_result": data.get('study_result')}))

    req_optimizer_runs = data.get('optimizer_runs')
    if isinstance(req_optimizer_runs, (dict, list)):
        payloads.append(("request.optimizer_runs", {"optimizer_runs": req_optimizer_runs}))

    if not payloads:
        return jsonify({"success": False, "error": "No data sources provided for dataset export."}), 400

    try:
        manifest = build_surrogate_dataset_from_payloads(
            payloads=payloads,
            output_root=output_root,
            dataset_name=dataset_name,
            target_objective=target_objective,
            val_ratio=val_ratio,
            split_seed=split_seed,
            only_success=only_success,
        )
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

    return jsonify({"success": True, "manifest": manifest})


@app.route('/api/surrogate/experiment/run', methods=['POST'])
def surrogate_experiment_run_route():
    data = request.get_json() or {}

    config_path = data.get('config_path')
    config = data.get('config')

    try:
        if config_path:
            report = run_surrogate_experiment_from_path(config_path)
        else:
            if not isinstance(config, dict):
                return jsonify({"success": False, "error": "Provide either 'config_path' or inline 'config' object."}), 400
            report = run_surrogate_experiment(config=config, config_dir=Path(os.getcwd()))
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

    return jsonify({"success": True, "report": report})


@app.route('/api/surrogate/synthetic/generate', methods=['POST'])
def surrogate_synthetic_generate_route():
    data = request.get_json() or {}

    try:
        report = generate_synthetic_surrogate_benchmark(
            preset=data.get('preset', 'nonlinear_3d'),
            n_runs=data.get('runs', 300),
            seed=data.get('seed', 42),
            noise_sigma=data.get('noise_sigma', 0.05),
            failure_probability=data.get('failure_probability', 0.08),
            dataset_output_root=data.get('dataset_output_root', 'surrogate/datasets'),
            artifacts_root=data.get('artifacts_root', 'surrogate/benchmarks'),
            dataset_name=data.get('dataset_name'),
            target_objective=data.get('target_objective', 'score'),
            val_ratio=data.get('val_ratio', 0.2),
            split_seed=data.get('split_seed', 42),
            only_success=bool(data.get('only_success', False)),
            write_example_configs=not bool(data.get('no_example_configs', False)),
        )
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

    return jsonify({"success": True, "benchmark": report})


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
    recipe = _normalize_boolean_recipe(data.get('recipe'))
    
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
    recipe = _normalize_boolean_recipe(data.get('recipe'))
    
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

LOCAL_BACKEND_DIAGNOSTICS_SCHEMA_VERSION = "2026-03-15.local-backend-diagnostics.checkpoint3"
LOCAL_BACKEND_STATUS_VALUES = ("healthy", "timeout", "unreachable", "misconfigured")


def _normalize_model_names(raw_names: List[Any]) -> List[str]:
    normalized: List[str] = []
    seen = set()
    for raw_name in raw_names:
        if raw_name is None:
            continue
        name = str(raw_name).strip()
        if not name or name in seen:
            continue
        seen.add(name)
        normalized.append(name)
    return normalized


def _resolve_local_backend_probe_config(
    backend_id: str,
    runtime_config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    if backend_id == "llama_cpp":
        cfg = LlamaCppAdapterConfig.from_runtime_config(runtime_config)
        return {
            "backend_id": backend_id,
            "provider_family": "llama.cpp",
            "base_url": cfg.base_url,
            "timeout_seconds": min(max(float(cfg.timeout_seconds), 0.1), 5.0),
        }

    if backend_id == "lm_studio":
        cfg = LMStudioAdapterConfig.from_runtime_config(runtime_config)
        return {
            "backend_id": backend_id,
            "provider_family": "lm_studio",
            "base_url": cfg.base_url,
            "timeout_seconds": min(max(float(cfg.timeout_seconds), 0.1), 5.0),
        }

    raise ValueError(f"Unsupported local backend for readiness probe: {backend_id}")


def _classify_backend_probe_exception(exc: Exception) -> Dict[str, str]:
    if isinstance(exc, (requests.exceptions.ConnectTimeout, requests.exceptions.ReadTimeout, requests.exceptions.Timeout)):
        return {
            "status": "timeout",
            "readiness_code": "backend_timeout",
            "message": "Timed out while connecting to backend models endpoint.",
        }

    if isinstance(exc, requests.exceptions.ConnectionError):
        return {
            "status": "unreachable",
            "readiness_code": "backend_unreachable",
            "message": "Backend service is unreachable.",
        }

    if isinstance(exc, (requests.exceptions.InvalidURL, requests.exceptions.InvalidSchema, requests.exceptions.MissingSchema, requests.exceptions.SSLError)):
        return {
            "status": "misconfigured",
            "readiness_code": "backend_misconfigured",
            "message": "Backend endpoint appears misconfigured.",
        }

    return {
        "status": "unreachable",
        "readiness_code": "backend_request_error",
        "message": "Backend readiness probe failed.",
    }


def _probe_openai_compatible_models_endpoint(
    backend_id: str,
    *,
    provider_family: str,
    base_url: str,
    timeout_seconds: float,
    requests_get=None,
) -> Dict[str, Any]:
    requests_get = requests_get or requests.get
    models_url = f"{str(base_url).rstrip('/')}/v1/models"

    base_payload = {
        "backend_id": backend_id,
        "provider_family": provider_family,
        "adapter_kind": "local",
        "checked_via": "v1_models_probe",
        "models_endpoint": models_url,
        "status": "unreachable",
        "readiness_code": "backend_request_error",
        "ready": False,
        "message": "Backend readiness probe did not run.",
        "http_status": None,
        "model_count": 0,
        "models": [],
    }

    try:
        response = requests_get(models_url, timeout=timeout_seconds)
    except requests.exceptions.RequestException as exc:
        failure = _classify_backend_probe_exception(exc)
        return {
            **base_payload,
            "status": failure["status"],
            "readiness_code": failure["readiness_code"],
            "message": failure["message"],
        }
    except Exception as exc:
        return {
            **base_payload,
            "status": "misconfigured",
            "readiness_code": "backend_probe_exception",
            "message": f"Backend readiness probe raised an unexpected error: {exc}",
        }

    http_status = getattr(response, "status_code", None)
    response_ok = getattr(response, "ok", None)
    if response_ok is None:
        if isinstance(http_status, int):
            response_ok = 200 <= http_status < 300
        else:
            response_ok = True

    if not response_ok:
        if http_status in (408, 504):
            status = "timeout"
            readiness_code = "backend_timeout"
            message = f"Backend models endpoint timed out (HTTP {http_status})."
        elif isinstance(http_status, int) and http_status >= 500:
            status = "unreachable"
            readiness_code = "backend_http_error"
            message = f"Backend models endpoint returned upstream error HTTP {http_status}."
        elif http_status in (401, 403):
            status = "misconfigured"
            readiness_code = "backend_auth_required"
            message = f"Backend models endpoint rejected the request (HTTP {http_status})."
        elif http_status == 404:
            status = "misconfigured"
            readiness_code = "backend_models_endpoint_not_found"
            message = "Backend models endpoint was not found (HTTP 404)."
        else:
            status = "misconfigured"
            readiness_code = "backend_http_error"
            message = f"Backend models endpoint returned HTTP {http_status}."

        return {
            **base_payload,
            "status": status,
            "readiness_code": readiness_code,
            "message": message,
            "http_status": http_status,
        }

    try:
        payload = response.json() or {}
    except Exception:
        return {
            **base_payload,
            "status": "misconfigured",
            "readiness_code": "invalid_models_payload",
            "message": "Backend models endpoint returned invalid JSON payload.",
            "http_status": http_status,
        }

    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, list):
        return {
            **base_payload,
            "status": "misconfigured",
            "readiness_code": "invalid_models_payload",
            "message": "Backend models endpoint payload is missing list field 'data'.",
            "http_status": http_status,
        }

    model_ids: List[Any] = []
    for item in data:
        if isinstance(item, dict):
            model_ids.append(item.get("id"))

    models = _normalize_model_names(model_ids)
    return {
        **base_payload,
        "status": "healthy",
        "readiness_code": "ok",
        "ready": True,
        "message": "Backend models endpoint is reachable.",
        "http_status": http_status,
        "model_count": len(models),
        "models": models,
    }


def build_local_backend_readiness_diagnostic(
    backend_id: str,
    *,
    runtime_config: Optional[Dict[str, Any]] = None,
    requests_get=None,
) -> Dict[str, Any]:
    probe_cfg = _resolve_local_backend_probe_config(backend_id, runtime_config=runtime_config)
    diagnostic = _probe_openai_compatible_models_endpoint(
        backend_id=backend_id,
        provider_family=probe_cfg["provider_family"],
        base_url=probe_cfg["base_url"],
        timeout_seconds=probe_cfg["timeout_seconds"],
        requests_get=requests_get,
    )
    diagnostic["schema_version"] = LOCAL_BACKEND_DIAGNOSTICS_SCHEMA_VERSION
    return diagnostic


def _build_local_backend_diagnostics_payload(
    *,
    backend_ids: Optional[List[str]] = None,
    runtime_config: Optional[Dict[str, Any]] = None,
    requests_get=None,
) -> Dict[str, Any]:
    normalized_backend_ids = backend_ids or ["llama_cpp", "lm_studio"]
    diagnostics: List[Dict[str, Any]] = []

    for backend_id in normalized_backend_ids:
        if backend_id not in {"llama_cpp", "lm_studio"}:
            raise ValueError(f"Unsupported backend id: {backend_id}")
        diagnostics.append(
            build_local_backend_readiness_diagnostic(
                backend_id,
                runtime_config=runtime_config,
                requests_get=requests_get,
            )
        )

    summary = {
        "checked_backend_count": len(diagnostics),
        "status_counts": {status: 0 for status in LOCAL_BACKEND_STATUS_VALUES},
        "ready_backend_count": 0,
    }

    for diagnostic in diagnostics:
        status = str(diagnostic.get("status") or "").strip()
        if status in summary["status_counts"]:
            summary["status_counts"][status] += 1
        if diagnostic.get("ready") is True:
            summary["ready_backend_count"] += 1

    return {
        "schema_version": LOCAL_BACKEND_DIAGNOSTICS_SCHEMA_VERSION,
        "diagnostics": diagnostics,
        "summary": summary,
    }


@app.route('/api/ai/backends/diagnostics', methods=['GET', 'POST'])
def ai_backend_diagnostics_route():
    payload = request.get_json(silent=True) if request.method == 'POST' else request.args
    payload = payload or {}

    raw_backends = payload.get('backends')
    backend_ids: Optional[List[str]] = None
    if raw_backends is not None:
        if isinstance(raw_backends, str):
            backend_ids = [raw_backends]
        elif isinstance(raw_backends, list):
            backend_ids = [str(item).strip() for item in raw_backends if str(item).strip()]
        else:
            return jsonify({"success": False, "error": "backends must be a string or list of strings."}), 400

    runtime_config_raw = payload.get('runtime_config')
    runtime_config = runtime_config_raw if isinstance(runtime_config_raw, dict) else None

    try:
        diagnostics_payload = _build_local_backend_diagnostics_payload(
            backend_ids=backend_ids,
            runtime_config=runtime_config,
        )
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400

    return jsonify({
        "success": True,
        **diagnostics_payload,
    })


@app.route('/ai_health_check', methods=['GET'])
def ai_health_check_route():
    response_data = {
        "success": True,
        "models": {
            "ollama": [],
            "gemini": [],
            "llama_cpp": [],
            "lm_studio": [],
        },
    }

    # 1. Check for Ollama models
    try:
        ollama_response = requests.get('http://localhost:11434/api/tags', timeout=3)
        if ollama_response.ok:
            ollama_data = ollama_response.json() or {}
            model_rows = ollama_data.get('models')
            discovered_names: List[Any] = []
            if isinstance(model_rows, list):
                for row in model_rows:
                    if isinstance(row, dict):
                        discovered_names.append(row.get('name'))
            response_data["models"]["ollama"] = _normalize_model_names(discovered_names)
    except requests.exceptions.RequestException:
        print("Ollama service is unreachable.")
        # We don't fail the whole request, just show no Ollama models
    except Exception as e:
        print(f"Error fetching Ollama models: {e}")
        response_data["error_ollama"] = str(e)

    # 2. Check local OpenAI-compatible model servers (llama.cpp + LM Studio)
    local_diag_payload = _build_local_backend_diagnostics_payload()
    diagnostics_by_id = {
        item["backend_id"]: item
        for item in local_diag_payload.get("diagnostics", [])
        if isinstance(item, dict)
    }

    llama_diag = diagnostics_by_id.get("llama_cpp", {})
    lm_diag = diagnostics_by_id.get("lm_studio", {})

    response_data["models"]["llama_cpp"] = list(llama_diag.get("models", [])) if isinstance(llama_diag.get("models"), list) else []
    response_data["models"]["lm_studio"] = list(lm_diag.get("models", [])) if isinstance(lm_diag.get("models"), list) else []
    response_data["local_backend_diagnostics"] = diagnostics_by_id

    # 3. Check for Gemini models if the client was initialized
    gemini_client = get_gemini_client_for_session()
    if gemini_client:
        try:
            allowed_model_names = {
                "models/gemini-3-flash-preview",
                "models/gemini-2.5-flash",
                "models/gemini-2.5-pro",
            }
            gemini_models: List[Any] = []
            # Use the initialized client to list models
            for model in gemini_client.models.list():
                supported_actions = getattr(model, "supported_actions", []) or []
                model_name = getattr(model, "name", None)
                if 'generateContent' in supported_actions and model_name in allowed_model_names:
                    gemini_models.append(model_name)
            response_data["models"]["gemini"] = _normalize_model_names(gemini_models)
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

    if isinstance(model_name, str) and (
        model_name.startswith("llama_cpp::") or model_name.startswith("lm_studio::")
    ):
        return jsonify({
            "success": False,
            "error": (
                "One-shot AI generate currently supports Gemini/Ollama model ids only. "
                "Use /api/ai/chat for llama.cpp/LM Studio local models."
            ),
        }), 400

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
    "create_boolean_solid": {
        "operations": "recipe",
        "ops": "recipe"
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
    "get_simulation_status": {
        "since_line": "since",
        "from_line": "since",
        "tail": "tail_lines",
        "include_output": "include_logs",
        "summary": "include_log_summary",
        "include_summary": "include_log_summary",
        "logs": "log_source",
        "log_stream": "log_source",
        "stream": "log_source",
        "include_entries": "include_log_entries",
        "with_entries": "include_log_entries",
        "structured_logs": "include_log_entries",
        "max_logs": "max_lines",
        "line_limit": "max_lines",
        "limit": "max_lines",
        "contains": "log_contains",
        "filter": "log_contains",
        "search": "log_contains",
        "contains_any": "log_contains_any",
        "search_any": "log_contains_any",
        "filter_any": "log_contains_any"
    },
    "compare_preflight_summaries": {
        "baseline": "baseline_summary",
        "before_summary": "baseline_summary",
        "base_summary": "baseline_summary",
        "candidate": "candidate_summary",
        "after_summary": "candidate_summary",
        "new_summary": "candidate_summary"
    },
    "compare_preflight_versions": {
        "baseline": "baseline_version_id",
        "baseline_version": "baseline_version_id",
        "before_version": "baseline_version_id",
        "base_version": "baseline_version_id",
        "candidate": "candidate_version_id",
        "candidate_version": "candidate_version_id",
        "after_version": "candidate_version_id",
        "new_version": "candidate_version_id",
        "project": "project_name"
    },
    "compare_latest_preflight_versions": {
        "project": "project_name"
    },
    "compare_autosave_preflight_vs_latest_saved": {
        "project": "project_name"
    },
    "compare_autosave_preflight_vs_previous_manual_saved": {
        "project": "project_name"
    },
    "compare_autosave_preflight_vs_manual_saved_index": {
        "project": "project_name",
        "manual_saved_n_back": "manual_saved_index",
        "n_back": "manual_saved_index",
        "index": "manual_saved_index",
        "previous_manual_saved_index": "manual_saved_index"
    },
    "compare_autosave_preflight_vs_manual_saved_for_simulation_run": {
        "project": "project_name",
        "run_id": "simulation_run_id",
        "job_id": "simulation_run_id",
        "simulation_job_id": "simulation_run_id"
    },
    "compare_autosave_preflight_vs_manual_saved_for_simulation_run_index": {
        "project": "project_name",
        "run_id": "simulation_run_id",
        "job_id": "simulation_run_id",
        "simulation_job_id": "simulation_run_id",
        "manual_saved_n_back": "manual_saved_index",
        "n_back": "manual_saved_index",
        "index": "manual_saved_index",
        "previous_manual_saved_index": "manual_saved_index"
    },
    "list_manual_saved_versions_for_simulation_run": {
        "project": "project_name",
        "run_id": "simulation_run_id",
        "job_id": "simulation_run_id",
        "simulation_job_id": "simulation_run_id",
        "max_versions": "limit",
        "count": "limit"
    },
    "compare_manual_preflight_versions_for_simulation_run_indices": {
        "project": "project_name",
        "run_id": "simulation_run_id",
        "job_id": "simulation_run_id",
        "simulation_job_id": "simulation_run_id",
        "baseline_manual_saved_n_back": "baseline_manual_saved_index",
        "baseline_n_back": "baseline_manual_saved_index",
        "baseline_index": "baseline_manual_saved_index",
        "candidate_manual_saved_n_back": "candidate_manual_saved_index",
        "candidate_n_back": "candidate_manual_saved_index",
        "candidate_index": "candidate_manual_saved_index"
    },
    "compare_autosave_preflight_vs_saved_version": {
        "project": "project_name",
        "saved_version": "saved_version_id",
        "version": "saved_version_id",
        "version_id": "saved_version_id",
        "baseline_version": "saved_version_id"
    },
    "compare_autosave_preflight_vs_snapshot_version": {
        "project": "project_name",
        "autosave_snapshot_version": "autosave_snapshot_version_id",
        "snapshot_version": "autosave_snapshot_version_id",
        "snapshot_version_id": "autosave_snapshot_version_id",
        "version": "autosave_snapshot_version_id",
        "version_id": "autosave_snapshot_version_id",
        "baseline_version": "autosave_snapshot_version_id"
    },
    "compare_autosave_preflight_vs_latest_snapshot": {
        "project": "project_name"
    },
    "compare_autosave_preflight_vs_previous_snapshot": {
        "project": "project_name"
    },
    "compare_autosave_snapshot_preflight_versions": {
        "project": "project_name",
        "baseline": "baseline_snapshot_version_id",
        "baseline_version": "baseline_snapshot_version_id",
        "baseline_version_id": "baseline_snapshot_version_id",
        "baseline_snapshot_version": "baseline_snapshot_version_id",
        "candidate": "candidate_snapshot_version_id",
        "candidate_version": "candidate_snapshot_version_id",
        "candidate_version_id": "candidate_snapshot_version_id",
        "candidate_snapshot_version": "candidate_snapshot_version_id"
    },
    "compare_latest_autosave_snapshot_preflight_versions": {
        "project": "project_name"
    },
    "list_preflight_versions": {
        "project": "project_name",
        "max_versions": "limit",
        "count": "limit",
        "include_latest_autosave": "include_autosave"
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
    "get_simulation_status": {"include_logs": True, "include_log_summary": True, "include_log_entries": False, "tail_lines": 20, "log_source": "both"},
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

    def _coerce_unit_expr_if_bare_number(expr: Any) -> Any:
        if not isinstance(expr, str):
            return expr
        s = expr.strip()
        # e.g. "70mm", "70 mm", "360deg" -> "(70)*mm", "(360)*deg"
        m = re.match(r'^([+-]?(?:\d+\.?\d*|\d*\.\d+)(?:[eE][+-]?\d+)?)\s*([A-Za-z]+)$', s)
        if not m:
            return expr
        num, unit = m.group(1), m.group(2)
        known_units = {
            'mm', 'cm', 'm', 'um', 'nm', 'km',
            'deg', 'rad',
            'g', 'kg', 'mg',
            's', 'ms', 'us', 'ns'
        }
        if unit.lower() in known_units:
            return f"({num})*{unit}"
        return expr

    st = str(solid_type or '').strip()
    aliases = PRIMITIVE_SOLID_PARAM_ALIASES.get(st, {})

    mapped = dict(raw_params)

    # 1) Canonicalize key casing/format against the selected solid spec.
    spec = PRIMITIVE_SOLID_PARAM_SPECS.get(st, {})
    canonical_props = list((spec.get('properties') or {}).keys())
    canonical_norm = {_normalize_param_alias_key(k): k for k in canonical_props}

    for key, value in list(raw_params.items()):
        norm = _normalize_param_alias_key(key)
        canonical_key = canonical_norm.get(norm)
        if canonical_key and canonical_key not in mapped:
            mapped[canonical_key] = value

    # 2) Apply common alias mappings (innerRadius->rmin, halfZ->z, ...)
    for key, value in raw_params.items():
        target = aliases.get(_normalize_param_alias_key(key))
        if target and target not in mapped:
            mapped[target] = value

    # 3) Normalize numeric-with-unit shortcuts and angle defaults.
    for k in list(mapped.keys()):
        mapped[k] = _coerce_unit_expr_if_bare_number(mapped[k])
        if _normalize_param_alias_key(k) in ANGLE_PARAM_NAMES:
            mapped[k] = _coerce_angle_expr_if_bare_number(mapped[k])

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


def _normalize_boolean_recipe(recipe: Any) -> Any:
    recipe = _parse_json_like(recipe)
    if isinstance(recipe, dict):
        recipe = recipe.get('recipe') or recipe.get('operations') or recipe.get('ops')

    if not isinstance(recipe, list):
        return recipe

    op_aliases = {
        'subtract': 'subtraction',
        'difference': 'subtraction',
        'minus': 'subtraction',
        'intersect': 'intersection',
        'and': 'intersection',
        'add': 'union',
        'merge': 'union'
    }

    normalized = []
    for item in recipe:
        if not isinstance(item, dict):
            normalized.append(item)
            continue

        mapped = dict(item)

        op_raw = mapped.get('op')
        if op_raw is None:
            op_raw = mapped.get('action') or mapped.get('operation')
        if isinstance(op_raw, str):
            op_norm = op_aliases.get(op_raw.strip().lower(), op_raw.strip().lower())
            mapped['op'] = op_norm

        solid_ref = mapped.get('solid_ref')
        if solid_ref is None:
            solid_ref = mapped.get('solid') or mapped.get('solid_name') or mapped.get('name')
        if solid_ref is not None and mapped.get('solid_ref') is None:
            mapped['solid_ref'] = solid_ref

        t = mapped.get('transform')
        if isinstance(t, dict):
            if 'position' not in t and 'pos' in t:
                t['position'] = t.get('pos')
            if 'rotation' not in t and 'rot' in t:
                t['rotation'] = t.get('rot')
            mapped['transform'] = t

        normalized.append(mapped)

    return normalized


def _validate_create_boolean_solid_args(args: Dict[str, Any]) -> Optional[str]:
    recipe = _normalize_boolean_recipe(args.get('recipe'))
    args['recipe'] = recipe

    if not isinstance(recipe, list) or len(recipe) < 2:
        return (
            "Tool 'create_boolean_solid' requires 'recipe' as a list with at least two steps. "
            "Expected recipe format example: "
            "[{\"op\":\"base\",\"solid_ref\":\"BaseSolid\"},"
            "{\"op\":\"subtraction\",\"solid_ref\":\"HoleSolid\","
            "\"transform\":{\"position\":{\"x\":\"0\",\"y\":\"0\",\"z\":\"0\"}}}]"
        )

    first = recipe[0] if recipe else None
    if not isinstance(first, dict) or first.get('op') != 'base' or not first.get('solid_ref'):
        return (
            "Tool 'create_boolean_solid' recipe must start with {'op':'base','solid_ref':'<existing solid>'}. "
            "Subsequent steps must use op in ['union','subtraction','intersection'] and a valid solid_ref."
        )

    for i, item in enumerate(recipe):
        if not isinstance(item, dict):
            return f"Tool 'create_boolean_solid' recipe step {i} must be an object."
        op = item.get('op')
        if op not in ('base', 'union', 'subtraction', 'intersection'):
            return (
                f"Tool 'create_boolean_solid' recipe step {i} has invalid op {op!r}. "
                "Allowed: ['base','union','subtraction','intersection']."
            )
        if not item.get('solid_ref'):
            return f"Tool 'create_boolean_solid' recipe step {i} missing solid_ref."

    return None


def _validate_tool_args(tool_name: str, args: Dict[str, Any]) -> Optional[str]:
    schema = AI_TOOL_PARAM_SCHEMAS.get(tool_name, {})

    required = schema.get("required", [])
    missing = [
        req for req in required
        if req not in args or args[req] is None or args[req] == ""
    ]
    if missing:
        # Keep explicit preflight compare selector missing-field behavior aligned
        # with route contracts. These tools provide route-matched required-field
        # diagnostics (including alias-aware wording) in dispatch.
        route_aligned_required_fields = {
            "compare_preflight_versions": {"baseline_version_id", "candidate_version_id"},
            "compare_autosave_preflight_vs_manual_saved_for_simulation_run": {"simulation_run_id"},
            "compare_autosave_preflight_vs_manual_saved_for_simulation_run_index": {"simulation_run_id"},
            "list_manual_saved_versions_for_simulation_run": {"simulation_run_id"},
            "compare_manual_preflight_versions_for_simulation_run_indices": {"simulation_run_id"},
            "compare_autosave_preflight_vs_saved_version": {"saved_version_id"},
            "compare_autosave_preflight_vs_snapshot_version": {"autosave_snapshot_version_id"},
            "compare_autosave_snapshot_preflight_versions": {
                "baseline_snapshot_version_id",
                "candidate_snapshot_version_id",
            },
        }

        if not (
            tool_name in route_aligned_required_fields
            and set(missing).issubset(route_aligned_required_fields[tool_name])
        ):
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

    if tool_name == 'create_boolean_solid':
        return _validate_create_boolean_solid_args(args)

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

    def _resolve_simulation_run_id_with_aliases(raw_args: Dict[str, Any]) -> Any:
        simulation_run_id = (
            raw_args.get("simulation_run_id")
            if raw_args.get("simulation_run_id") is not None
            else raw_args.get("run_id")
        )
        if simulation_run_id is None:
            simulation_run_id = raw_args.get("job_id")
        if simulation_run_id is None:
            simulation_run_id = raw_args.get("simulation_job_id")
        return simulation_run_id


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
            recipe = _normalize_boolean_recipe(args.get('recipe'))

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

        elif tool_name == "run_preflight_checks":
            report = pm.run_preflight_checks()
            return {
                "success": True,
                "preflight_report": report,
                "preflight_summary": report.get("summary", {}),
            }

        elif tool_name == "compare_preflight_summaries":
            try:
                comparison = compare_preflight_summaries(
                    args.get("baseline_summary"),
                    args.get("candidate_summary"),
                )
            except ValueError as exc:
                return {"success": False, "error": str(exc)}

            return {
                "success": True,
                "comparison": comparison,
            }

        elif tool_name == "compare_preflight_versions":
            baseline_version_id = (
                args.get("baseline_version_id")
                if args.get("baseline_version_id") is not None
                else args.get("baseline_version")
            )
            if baseline_version_id is None:
                baseline_version_id = args.get("baseline")
            if baseline_version_id is None:
                baseline_version_id = args.get("before_version")
            if baseline_version_id is None:
                baseline_version_id = args.get("base_version")

            candidate_version_id = (
                args.get("candidate_version_id")
                if args.get("candidate_version_id") is not None
                else args.get("candidate_version")
            )
            if candidate_version_id is None:
                candidate_version_id = args.get("candidate")
            if candidate_version_id is None:
                candidate_version_id = args.get("after_version")
            if candidate_version_id is None:
                candidate_version_id = args.get("new_version")

            if baseline_version_id is None or candidate_version_id is None:
                return {
                    "success": False,
                    "error": "Missing required fields: baseline_version_id and candidate_version_id.",
                }

            try:
                result = compare_preflight_versions(
                    pm,
                    baseline_version_id=baseline_version_id,
                    candidate_version_id=candidate_version_id,
                    project_name=args.get("project_name"),
                )
            except (ValueError, FileNotFoundError) as exc:
                return {"success": False, "error": str(exc)}

            return {
                "success": True,
                **result,
            }

        elif tool_name == "compare_latest_preflight_versions":
            try:
                result = compare_latest_preflight_versions(
                    pm,
                    project_name=args.get("project_name"),
                )
            except (ValueError, FileNotFoundError) as exc:
                return {"success": False, "error": str(exc)}

            return {
                "success": True,
                **result,
            }

        elif tool_name == "compare_autosave_preflight_vs_latest_saved":
            try:
                result = compare_autosave_preflight_vs_latest_saved(
                    pm,
                    project_name=args.get("project_name"),
                )
            except (ValueError, FileNotFoundError) as exc:
                return {"success": False, "error": str(exc)}

            return {
                "success": True,
                **result,
            }

        elif tool_name == "compare_autosave_preflight_vs_previous_manual_saved":
            try:
                result = compare_autosave_preflight_vs_previous_manual_saved(
                    pm,
                    project_name=args.get("project_name"),
                )
            except (ValueError, FileNotFoundError) as exc:
                return {"success": False, "error": str(exc)}

            return {
                "success": True,
                **result,
            }

        elif tool_name == "compare_autosave_preflight_vs_manual_saved_index":
            try:
                result = compare_autosave_preflight_vs_manual_saved_index(
                    pm,
                    manual_saved_index=args.get("manual_saved_index"),
                    project_name=args.get("project_name"),
                )
            except (ValueError, FileNotFoundError) as exc:
                return {"success": False, "error": str(exc)}

            return {
                "success": True,
                **result,
            }

        elif tool_name == "compare_autosave_preflight_vs_manual_saved_for_simulation_run":
            simulation_run_id = _resolve_simulation_run_id_with_aliases(args)
            if simulation_run_id is None:
                return {
                    "success": False,
                    "error": "Missing required field: simulation_run_id (or run_id/job_id).",
                }

            try:
                result = compare_autosave_preflight_vs_manual_saved_for_simulation_run(
                    pm,
                    simulation_run_id=simulation_run_id,
                    project_name=args.get("project_name"),
                )
            except (ValueError, FileNotFoundError) as exc:
                return {"success": False, "error": str(exc)}

            return {
                "success": True,
                **result,
            }

        elif tool_name == "compare_autosave_preflight_vs_manual_saved_for_simulation_run_index":
            simulation_run_id = _resolve_simulation_run_id_with_aliases(args)
            if simulation_run_id is None:
                return {
                    "success": False,
                    "error": "Missing required field: simulation_run_id (or run_id/job_id).",
                }

            try:
                result = compare_autosave_preflight_vs_manual_saved_for_simulation_run_index(
                    pm,
                    simulation_run_id=simulation_run_id,
                    manual_saved_index=args.get("manual_saved_index"),
                    project_name=args.get("project_name"),
                )
            except (ValueError, FileNotFoundError) as exc:
                return {"success": False, "error": str(exc)}

            return {
                "success": True,
                **result,
            }

        elif tool_name == "list_manual_saved_versions_for_simulation_run":
            simulation_run_id = _resolve_simulation_run_id_with_aliases(args)
            if simulation_run_id is None:
                return {
                    "success": False,
                    "error": "Missing required field: simulation_run_id (or run_id/job_id).",
                }

            try:
                result = list_manual_saved_versions_for_simulation_run(
                    pm,
                    simulation_run_id=simulation_run_id,
                    project_name=args.get("project_name"),
                    limit=args.get("limit"),
                )
            except ValueError as exc:
                return {"success": False, "error": str(exc)}

            return {
                "success": True,
                **result,
            }

        elif tool_name == "compare_manual_preflight_versions_for_simulation_run_indices":
            simulation_run_id = _resolve_simulation_run_id_with_aliases(args)
            if simulation_run_id is None:
                return {
                    "success": False,
                    "error": "Missing required field: simulation_run_id (or run_id/job_id).",
                }

            try:
                result = compare_manual_preflight_versions_for_simulation_run_indices(
                    pm,
                    simulation_run_id=simulation_run_id,
                    baseline_manual_saved_index=args.get("baseline_manual_saved_index"),
                    candidate_manual_saved_index=args.get("candidate_manual_saved_index"),
                    project_name=args.get("project_name"),
                )
            except (ValueError, FileNotFoundError) as exc:
                return {"success": False, "error": str(exc)}

            return {
                "success": True,
                **result,
            }

        elif tool_name == "compare_autosave_preflight_vs_saved_version":
            saved_version_id = (
                args.get("saved_version_id")
                if args.get("saved_version_id") is not None
                else args.get("saved_version")
            )
            if saved_version_id is None:
                saved_version_id = args.get("version_id")
            if saved_version_id is None:
                saved_version_id = args.get("version")
            if saved_version_id is None:
                saved_version_id = args.get("baseline_version")

            if saved_version_id is None:
                return {
                    "success": False,
                    "error": "Missing required field: saved_version_id (or saved_version/version_id).",
                }

            try:
                result = compare_autosave_preflight_vs_saved_version(
                    pm,
                    saved_version_id=saved_version_id,
                    project_name=args.get("project_name"),
                )
            except (ValueError, FileNotFoundError) as exc:
                return {"success": False, "error": str(exc)}

            return {
                "success": True,
                **result,
            }

        elif tool_name == "compare_autosave_preflight_vs_snapshot_version":
            autosave_snapshot_version_id = (
                args.get("autosave_snapshot_version_id")
                if args.get("autosave_snapshot_version_id") is not None
                else args.get("snapshot_version_id")
            )
            if autosave_snapshot_version_id is None:
                autosave_snapshot_version_id = args.get("snapshot_version")
            if autosave_snapshot_version_id is None:
                autosave_snapshot_version_id = args.get("version_id")
            if autosave_snapshot_version_id is None:
                autosave_snapshot_version_id = args.get("version")
            if autosave_snapshot_version_id is None:
                autosave_snapshot_version_id = args.get("baseline_version")
            if autosave_snapshot_version_id is None:
                autosave_snapshot_version_id = args.get("autosave_snapshot_version")

            if autosave_snapshot_version_id is None:
                return {
                    "success": False,
                    "error": "Missing required field: autosave_snapshot_version_id (or snapshot_version_id/snapshot_version/version_id).",
                }

            try:
                result = compare_autosave_preflight_vs_snapshot_version(
                    pm,
                    autosave_snapshot_version_id=autosave_snapshot_version_id,
                    project_name=args.get("project_name"),
                )
            except (ValueError, FileNotFoundError) as exc:
                return {"success": False, "error": str(exc)}

            return {
                "success": True,
                **result,
            }

        elif tool_name == "compare_autosave_preflight_vs_latest_snapshot":
            try:
                result = compare_autosave_preflight_vs_latest_snapshot(
                    pm,
                    project_name=args.get("project_name"),
                )
            except (ValueError, FileNotFoundError) as exc:
                return {"success": False, "error": str(exc)}

            return {
                "success": True,
                **result,
            }

        elif tool_name == "compare_autosave_preflight_vs_previous_snapshot":
            try:
                result = compare_autosave_preflight_vs_previous_snapshot(
                    pm,
                    project_name=args.get("project_name"),
                )
            except (ValueError, FileNotFoundError) as exc:
                return {"success": False, "error": str(exc)}

            return {
                "success": True,
                **result,
            }

        elif tool_name == "compare_autosave_snapshot_preflight_versions":
            baseline_snapshot_version_id = (
                args.get("baseline_snapshot_version_id")
                if args.get("baseline_snapshot_version_id") is not None
                else args.get("baseline_snapshot_version")
            )
            if baseline_snapshot_version_id is None:
                baseline_snapshot_version_id = args.get("baseline_version_id")
            if baseline_snapshot_version_id is None:
                baseline_snapshot_version_id = args.get("baseline_version")
            if baseline_snapshot_version_id is None:
                baseline_snapshot_version_id = args.get("baseline")

            candidate_snapshot_version_id = (
                args.get("candidate_snapshot_version_id")
                if args.get("candidate_snapshot_version_id") is not None
                else args.get("candidate_snapshot_version")
            )
            if candidate_snapshot_version_id is None:
                candidate_snapshot_version_id = args.get("candidate_version_id")
            if candidate_snapshot_version_id is None:
                candidate_snapshot_version_id = args.get("candidate_version")
            if candidate_snapshot_version_id is None:
                candidate_snapshot_version_id = args.get("candidate")

            missing_fields = []
            if baseline_snapshot_version_id is None:
                missing_fields.append('baseline_snapshot_version_id (or baseline_snapshot_version/baseline_version_id/baseline_version)')
            if candidate_snapshot_version_id is None:
                missing_fields.append('candidate_snapshot_version_id (or candidate_snapshot_version/candidate_version_id/candidate_version)')

            if missing_fields:
                return {
                    "success": False,
                    "error": f"Missing required field(s): {', '.join(missing_fields)}.",
                }

            try:
                result = compare_autosave_snapshot_preflight_versions(
                    pm,
                    baseline_snapshot_version_id=baseline_snapshot_version_id,
                    candidate_snapshot_version_id=candidate_snapshot_version_id,
                    project_name=args.get("project_name"),
                )
            except (ValueError, FileNotFoundError) as exc:
                return {"success": False, "error": str(exc)}

            return {
                "success": True,
                **result,
            }

        elif tool_name == "compare_latest_autosave_snapshot_preflight_versions":
            try:
                result = compare_latest_autosave_snapshot_preflight_versions(
                    pm,
                    project_name=args.get("project_name"),
                )
            except (ValueError, FileNotFoundError) as exc:
                return {"success": False, "error": str(exc)}

            return {
                "success": True,
                **result,
            }

        elif tool_name == "list_preflight_versions":
            try:
                result = list_preflight_versions(
                    pm,
                    project_name=args.get("project_name"),
                    include_autosave=args.get("include_autosave", True),
                    limit=args.get("limit"),
                )
            except ValueError as exc:
                return {"success": False, "error": str(exc)}

            return {
                "success": True,
                **result,
            }

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

            parsed_opts, err = _parse_simulation_status_log_options(
                get_value=args.get,
                has_key=lambda key: key in args,
                include_log_summary_default=True,
                include_log_entries_default=False,
                tail_lines_default=20,
                apply_legacy_since_default=False,
                split_commas_for_contains_any=True,
            )
            if err:
                return {"success": False, "error": err}

            include_logs = parsed_opts['include_logs']
            include_log_summary = parsed_opts['include_log_summary']
            include_log_entries = parsed_opts['include_log_entries']
            since = parsed_opts['since']
            tail_lines = parsed_opts['tail_lines']
            max_lines = parsed_opts['max_lines']
            log_source = parsed_opts['log_source']
            log_contains = parsed_opts['log_contains']
            log_contains_any_terms = parsed_opts['log_contains_any_terms']

            with SIMULATION_LOCK:
                status = SIMULATION_STATUS.get(job_id)
                if not status:
                    return {"success": False, "error": "Job ID not found."}

                stdout_lines = list(status.get("stdout") or [])
                stderr_raw = list(status.get("stderr") or [])

                response = {
                    "success": True,
                    "status": status["status"],
                    "progress": status["progress"],
                    "total": status["total_events"]
                }
                response.update(_build_simulation_log_payload(
                    stdout_lines,
                    stderr_raw,
                    include_logs=include_logs,
                    include_log_summary=include_log_summary,
                    include_log_entries=include_log_entries,
                    log_source=log_source,
                    log_contains=log_contains,
                    log_contains_any_terms=log_contains_any_terms,
                    since=since,
                    tail_lines=tail_lines,
                    max_lines=max_lines,
                    include_legacy_fields=False,
                ))

                return response

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

                op_tool_name = op.get('tool_name') or op.get('toolName') or op.get('tool') or op.get('type')
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
            name = args.get('name')
            raw_placements = args.get('placements')

            if not isinstance(name, str) or not name.strip():
                return {"success": False, "error": "'name' is required for manage_assembly."}
            if not isinstance(raw_placements, list):
                return {"success": False, "error": "'placements' must be an array for manage_assembly."}

            normalized_placements = []
            for idx, raw_p in enumerate(raw_placements):
                if not isinstance(raw_p, dict):
                    return {"success": False, "error": f"placements[{idx}] must be an object."}

                placement = dict(raw_p)
                volume_ref = (
                    placement.get('volume_ref')
                    or placement.get('logical_volume_ref')
                    or placement.get('volume')
                    or placement.get('lv_name')
                )
                if not volume_ref:
                    return {
                        "success": False,
                        "error": f"placements[{idx}] is missing required field 'volume_ref'."
                    }

                placement_name = (
                    placement.get('name')
                    or placement.get('placement_name')
                    or placement.get('id')
                    or f"{name}_placement_{idx + 1}"
                )

                normalized = {
                    'name': str(placement_name),
                    'volume_ref': str(volume_ref),
                }

                if placement.get('id') is not None:
                    normalized['id'] = str(placement.get('id'))
                if placement.get('parent_lv_name') is not None:
                    normalized['parent_lv_name'] = str(placement.get('parent_lv_name'))
                if placement.get('copy_number_expr') is not None:
                    normalized['copy_number_expr'] = str(placement.get('copy_number_expr'))
                elif placement.get('copy_number') is not None:
                    normalized['copy_number'] = placement.get('copy_number')
                if placement.get('position') is not None:
                    normalized['position'] = to_vec_dict(placement.get('position'))
                if placement.get('rotation') is not None:
                    normalized['rotation'] = to_vec_dict(placement.get('rotation'))
                if placement.get('scale') is not None:
                    normalized['scale'] = to_vec_dict(placement.get('scale'))

                normalized_placements.append(normalized)

            if name in pm.current_geometry_state.assemblies:
                success, error = pm.update_assembly(name, normalized_placements)
                if success:
                    return {"success": True, "message": f"Assembly '{name}' updated."}
                return {"success": False, "error": error}
            else:
                res, error = pm.add_assembly(name, normalized_placements)
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

        elif tool_name == "create_parameter_registry":
            param_name = args.get('param_name')
            target_type = args.get('target_type')
            target_ref = args.get('target_ref')
            bounds = args.get('bounds')
            default = args.get('default')

            if not param_name or not target_type or not isinstance(target_ref, dict) or not isinstance(bounds, dict):
                return {"success": False, "error": "Missing/invalid required fields: param_name, target_type, target_ref(object), bounds(object)."}

            # PM validation requires numeric default; if absent, default to midpoint.
            if default is None:
                try:
                    min_v = float(bounds.get('min'))
                    max_v = float(bounds.get('max'))
                    default = 0.5 * (min_v + max_v)
                except Exception:
                    return {"success": False, "error": "bounds.min and bounds.max must be numeric when default is omitted."}

            entry = {
                'target_type': target_type,
                'target_ref': target_ref,
                'bounds': bounds,
                'default': default,
                'units': args.get('units', ''),
                'enabled': args.get('enabled', True),
                'constraint_group': args.get('constraint_group'),
            }

            result, err = pm.upsert_parameter_registry_entry(param_name, entry)
            if err:
                return {"success": False, "error": err}
            return {"success": True, "parameter": result}

        elif tool_name == "setup_param_study":
            study_name = args.get('study_name')
            parameters = args.get('parameters')
            objectives = args.get('objectives')
            mode = (args.get('mode') or ('random' if args.get('random') else 'grid')).strip().lower() if isinstance(args.get('mode') or ('random' if args.get('random') else 'grid'), str) else 'grid'

            if not study_name or not isinstance(parameters, list) or not parameters or not isinstance(objectives, list) or not objectives:
                return {"success": False, "error": "Missing/invalid required fields: study_name, parameters(non-empty list), objectives(non-empty list)."}

            config = {
                'mode': mode,
                'parameters': parameters,
                'objectives': objectives,
                'grid': args.get('grid') if isinstance(args.get('grid'), dict) else {},
                'random': args.get('random') if isinstance(args.get('random'), dict) else {},
            }

            result, err = pm.upsert_param_study(study_name, config)
            if err:
                return {"success": False, "error": err}
            return {"success": True, "study": result}

        elif tool_name == "run_optimization":
            study_name = args.get('study_name')
            method = (args.get('method') or '').strip().lower()

            if not study_name or not method:
                return {"success": False, "error": "Missing required fields: study_name, method."}

            try:
                budget = int(args.get('budget', 20))
            except Exception:
                return {"success": False, "error": "budget must be an integer."}

            payload = {
                'study_name': study_name,
                'method': method,
                'budget': budget,
                'seed': args.get('seed', 42),
                'objective_name': args.get('objective_name'),
                'direction': args.get('direction'),
            }

            cmaes_config = args.get('cmaes_config')
            if isinstance(cmaes_config, dict):
                payload['cmaes'] = cmaes_config

            surrogate_config = args.get('surrogate_config')
            if isinstance(surrogate_config, dict):
                payload['surrogate'] = surrogate_config

            sim_params = args.get('sim_params') if isinstance(args.get('sim_params'), dict) else {}
            if not sim_params and (args.get('sim_events') is not None or args.get('sim_threads') is not None):
                sim_params = {
                    'events': args.get('sim_events', 1),
                    'threads': args.get('sim_threads', 1),
                }
            if sim_params:
                payload['sim_params'] = sim_params

            if args.get('max_wall_time_seconds') is not None:
                payload['max_wall_time_seconds'] = args.get('max_wall_time_seconds')

            if isinstance(args.get('context'), dict):
                payload['context'] = args.get('context')
            if isinstance(args.get('candidate_runs_root'), str):
                payload['candidate_runs_root'] = args.get('candidate_runs_root')
            if args.get('keep_candidate_runs') is not None:
                payload['keep_candidate_runs'] = bool(args.get('keep_candidate_runs'))

            simulation_in_loop = bool(args.get('simulation_in_loop', False) or args.get('sim_objectives') is not None)
            if simulation_in_loop:
                sim_objectives = args.get('sim_objectives')
                if not isinstance(sim_objectives, list) or not sim_objectives:
                    return {"success": False, "error": "simulation_in_loop=true requires sim_objectives as a non-empty list."}
                payload['sim_objectives'] = sim_objectives

                status_code, body = call_route_json(param_optimizer_run_simulation_in_loop_route, payload=payload)
            else:
                if method == 'surrogate_gp':
                    status_code, body = call_route_json(param_optimizer_run_surrogate_route, payload=payload)
                else:
                    status_code, body = call_route_json(param_optimizer_run_route, payload=payload)

            if status_code >= 400 or body.get('success') is False:
                return {
                    "success": False,
                    "error": body.get('error', f"Optimization failed (status {status_code})."),
                    "details": body.get('details'),
                }

            response = {
                "success": True,
                "optimization_result": body.get('optimizer_result'),
            }
            if body.get('preflight_summary') is not None:
                response['preflight_summary'] = body.get('preflight_summary')
            if body.get('run_policy') is not None:
                response['run_policy'] = body.get('run_policy')
            return response

        elif tool_name == "apply_best_result":
            run_id = args.get('run_id')
            apply_to_project = args.get('apply_to_project', True)

            if not run_id:
                return {"success": False, "error": "Missing required field: run_id"}

            result, err = pm.replay_optimizer_best_candidate(run_id, apply_to_project=apply_to_project)
            if err:
                return {"success": False, "error": err}
            return {"success": True, "result": result}

        elif tool_name == "list_optimizer_runs":
            study_name = args.get('study_name')
            limit = args.get('limit', 50)

            try:
                runs = pm.list_optimizer_runs(study_name=study_name, limit=limit)
            except Exception as e:
                return {"success": False, "error": str(e)}
            return {"success": True, "runs": runs}

        elif tool_name == "verify_best_candidate":
            run_id = args.get('run_id')
            repeats = args.get('repeats', 3)

            if not run_id:
                return {"success": False, "error": "Missing required field: run_id"}

            result, err = pm.verify_optimizer_best_candidate(run_id, repeats=repeats)
            if err:
                return {"success": False, "error": err}
            return {"success": True, "verification": result}

        return {"success": False, "error": f"Unknown tool: {tool_name}"}
    except Exception as e:
        traceback.print_exc()
        return {"success": False, "error": str(e)}


def _coerce_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
    return default


def _coerce_optional_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        parsed = int(value)
        return parsed if parsed >= 0 else None
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            parsed = int(stripped)
            return parsed if parsed >= 0 else None
        except ValueError:
            return None
    return None


def _build_openai_tool_schema_from_ai_tools() -> List[Dict[str, Any]]:
    tool_schemas: List[Dict[str, Any]] = []
    for tool in AI_GEOMETRY_TOOLS:
        tool_schemas.append({
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool["description"],
                "parameters": tool["parameters"],
            },
        })
    return tool_schemas


def _coerce_tool_arguments(arguments: Any) -> Dict[str, Any]:
    if isinstance(arguments, dict):
        return arguments
    if isinstance(arguments, str):
        stripped = arguments.strip()
        if not stripped:
            return {}
        try:
            parsed = json.loads(stripped)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            return {}
    return {}


def _normalize_tool_calls_payload(raw_tool_calls: Any) -> List[Dict[str, Any]]:
    if not isinstance(raw_tool_calls, list):
        return []

    normalized: List[Dict[str, Any]] = []
    for call in raw_tool_calls:
        if not isinstance(call, dict):
            continue

        call_id = call.get("id")
        function_obj = call.get("function") if isinstance(call.get("function"), dict) else None

        tool_name = None
        arguments: Any = {}

        if function_obj:
            tool_name = function_obj.get("name")
            arguments = function_obj.get("arguments", {})
        else:
            fallback_name = call.get("name")
            tool_name = call.get("tool") or call.get("tool_name")
            fallback_used_as_tool_name = False
            if tool_name is None and isinstance(fallback_name, str):
                tool_name = fallback_name
                fallback_used_as_tool_name = True

            if "arguments" in call:
                arguments = call.get("arguments")
            elif "params" in call:
                arguments = call.get("params")
            else:
                exclude_fields = {"id", "tool", "tool_name", "function", "tool_call_id"}
                if fallback_used_as_tool_name:
                    exclude_fields.add("name")
                arguments = {
                    k: v for k, v in call.items()
                    if k not in exclude_fields
                }

        if not tool_name or not isinstance(tool_name, str):
            continue

        normalized.append({
            "id": call_id,
            "name": tool_name,
            "arguments": _coerce_tool_arguments(arguments),
        })

    return normalized


def _extract_tool_calls_from_json_text(content: str) -> List[Dict[str, Any]]:
    if not isinstance(content, str) or not content.strip():
        return []

    candidates: List[str] = []
    stripped = content.strip()
    candidates.append(stripped)

    fenced_blocks = re.findall(r"```(?:json)?\s*([\s\S]*?)```", content, flags=re.IGNORECASE)
    candidates.extend(block.strip() for block in fenced_blocks if isinstance(block, str) and block.strip())

    if "tool_calls" in content:
        first_brace = content.find("{")
        last_brace = content.rfind("}")
        if first_brace != -1 and last_brace > first_brace:
            candidates.append(content[first_brace:last_brace + 1].strip())

    seen: set[str] = set()
    for candidate in candidates:
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)

        try:
            parsed = json.loads(candidate)
        except Exception:
            continue

        raw_tool_calls = None
        if isinstance(parsed, dict):
            if isinstance(parsed.get("tool_calls"), list):
                raw_tool_calls = parsed.get("tool_calls")
            elif isinstance(parsed.get("calls"), list):
                raw_tool_calls = parsed.get("calls")
        elif isinstance(parsed, list):
            raw_tool_calls = parsed

        normalized = _normalize_tool_calls_payload(raw_tool_calls)
        if normalized:
            return normalized

    return []


def _extract_openai_assistant_payload(raw_response: Dict[str, Any], fallback_text: str = "") -> Dict[str, Any]:
    content = fallback_text or ""
    tool_calls: List[Dict[str, Any]] = []

    if isinstance(raw_response, dict):
        choices = raw_response.get("choices")
        if isinstance(choices, list) and choices:
            first = choices[0]
            if isinstance(first, dict):
                message = first.get("message")
                if isinstance(message, dict):
                    raw_content = message.get("content")
                    if isinstance(raw_content, str):
                        content = raw_content.strip()
                    elif isinstance(raw_content, list):
                        text_parts: List[str] = []
                        for part in raw_content:
                            if isinstance(part, dict) and isinstance(part.get("text"), str):
                                text_parts.append(part["text"])
                        content = "\n".join(p.strip() for p in text_parts if p and p.strip())

                    tool_calls = _normalize_tool_calls_payload(message.get("tool_calls"))

    if not tool_calls:
        tool_calls = _extract_tool_calls_from_json_text(content or fallback_text or "")

    return {
        "content": content,
        "tool_calls": tool_calls,
    }


def _to_openai_tool_calls(raw_tool_calls: Any, *, id_prefix: str = "call") -> List[Dict[str, Any]]:
    normalized_calls = _normalize_tool_calls_payload(raw_tool_calls)
    openai_calls: List[Dict[str, Any]] = []

    for idx, call in enumerate(normalized_calls):
        tool_name = call.get("name")
        if not isinstance(tool_name, str) or not tool_name:
            continue

        arguments = call.get("arguments")
        if not isinstance(arguments, dict):
            arguments = _coerce_tool_arguments(arguments)

        call_id = str(call.get("id") or f"{id_prefix}_{idx}_{tool_name}")
        openai_calls.append({
            "id": call_id,
            "type": "function",
            "function": {
                "name": tool_name,
                "arguments": json.dumps(arguments, ensure_ascii=False),
            },
        })

    return openai_calls


def _build_local_adapter_message_history(chat_history: List[Dict[str, Any]]) -> List[TextMessage]:
    messages: List[TextMessage] = []

    for msg in chat_history:
        if not isinstance(msg, dict):
            continue

        role = str(msg.get("role") or "").strip().lower()
        if role == "model":
            role = "assistant"
        if role not in {"system", "user", "assistant", "tool"}:
            continue

        content = msg.get("content")
        if not isinstance(content, str):
            parts = msg.get("parts")
            if isinstance(parts, list) and parts:
                first_part = parts[0]
                if isinstance(first_part, dict) and isinstance(first_part.get("text"), str):
                    content = first_part.get("text")
        if not isinstance(content, str):
            content = ""

        kwargs: Dict[str, Any] = {}

        if role == "assistant" and isinstance(msg.get("tool_calls"), list):
            openai_tool_calls = _to_openai_tool_calls(msg.get("tool_calls"), id_prefix="hist")
            if openai_tool_calls:
                kwargs["tool_calls"] = tuple(openai_tool_calls)

        if role == "tool":
            tool_call_id = msg.get("tool_call_id")
            if tool_call_id is not None and str(tool_call_id).strip():
                kwargs["tool_call_id"] = str(tool_call_id).strip()
            tool_name = msg.get("name")
            if isinstance(tool_name, str) and tool_name.strip():
                kwargs["name"] = tool_name.strip()

        messages.append(TextMessage(role=role, content=content, **kwargs))

    return messages


def _build_executable_tool_calls(parsed_tool_calls: List[Dict[str, Any]], turn: int) -> List[Dict[str, Any]]:
    executable_calls: List[Dict[str, Any]] = []

    for idx, tool_call in enumerate(parsed_tool_calls):
        if not isinstance(tool_call, dict):
            continue

        tool_name = tool_call.get("name")
        if not isinstance(tool_name, str) or not tool_name:
            continue

        arguments = tool_call.get("arguments")
        if not isinstance(arguments, dict):
            arguments = _coerce_tool_arguments(arguments)

        call_id = str(tool_call.get("id") or f"call_{turn}_{idx}_{tool_name}")
        executable_calls.append({
            "id": call_id,
            "name": tool_name,
            "arguments": arguments,
        })

    return executable_calls


def _infer_local_backend_selector_from_model_id(model_id: Any) -> tuple[Optional[Dict[str, Any]], Optional[str]]:
    if not isinstance(model_id, str):
        return None, None

    normalized_model_id = model_id.strip()
    prefix_to_backend = {
        "llama_cpp::": "llama_cpp",
        "lm_studio::": "lm_studio",
    }

    for prefix, backend_id in prefix_to_backend.items():
        if not normalized_model_id.startswith(prefix):
            continue

        local_model_name = normalized_model_id[len(prefix):].strip()
        if not local_model_name:
            return None, (
                f"Invalid local model selector '{model_id}'. "
                f"Expected '{backend_id}::<model_name>' with a non-empty model name."
            )

        inferred_require_tools = backend_id == "llama_cpp"

        return {
            "preferred_backend_id": backend_id,
            "allow_fallback": False,
            "runtime_config": {
                "backends": {
                    backend_id: {
                        "enabled": True,
                        "model": local_model_name,
                    }
                }
            },
            "requirements": {
                "require_tools": inferred_require_tools,
                "require_json_mode": True,
                "require_streaming": False,
            },
        }, None

    return None, None


def _get_ai_artifact_store_for_session(pm: Optional[ProjectManager] = None) -> AIArtifactStore:
    pm = pm or get_project_manager_for_session()
    return AIArtifactStore(
        base_dir=Path(pm.projects_dir) / ".airpet_ai_artifacts",
        workspace_root=Path(os.getcwd()),
    )


@app.route('/api/ai/artifacts/upload', methods=['POST'])
def upload_ai_artifact_route():
    pm = get_project_manager_for_session()
    file = request.files.get('artifact') or request.files.get('file')
    if file is None:
        return jsonify({"success": False, "error": "Missing artifact file upload (field: artifact)."}), 400

    source_path = request.form.get('source_path')
    source_label = request.form.get('source_label')
    store = _get_ai_artifact_store_for_session(pm)

    try:
        artifact = store.ingest_upload(file, source_path=source_path, source_label=source_label)
        return jsonify({
            "success": True,
            "schema_version": ARTIFACT_STORE_SCHEMA_VERSION,
            "artifact": artifact,
        })
    except AIArtifactValidationError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except Exception as exc:
        traceback.print_exc()
        return jsonify({"success": False, "error": f"Failed to ingest AI artifact: {exc}"}), 500


@app.route('/api/ai/artifacts/list', methods=['GET', 'POST'])
def list_ai_artifacts_route():
    pm = get_project_manager_for_session()
    store = _get_ai_artifact_store_for_session(pm)

    if request.method == 'POST':
        payload = request.get_json(silent=True) or {}
    else:
        payload = request.args or {}

    raw_limit = payload.get('limit', 50)
    try:
        limit = int(raw_limit)
    except (TypeError, ValueError):
        return jsonify({"success": False, "error": "limit must be a non-negative integer."}), 400

    include_missing_files = _coerce_bool(payload.get('include_missing_files'), False)

    try:
        artifacts = store.list_metadata(limit=limit, include_missing_files=include_missing_files)
        return jsonify({
            "success": True,
            "schema_version": ARTIFACT_STORE_SCHEMA_VERSION,
            "count": len(artifacts),
            "artifacts": artifacts,
        })
    except AIArtifactValidationError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except Exception as exc:
        traceback.print_exc()
        return jsonify({"success": False, "error": f"Failed to list AI artifacts: {exc}"}), 500


@app.route('/api/ai/artifacts/<artifact_id>', methods=['GET'])
def get_ai_artifact_metadata_route(artifact_id):
    pm = get_project_manager_for_session()
    store = _get_ai_artifact_store_for_session(pm)

    try:
        artifact = store.get_metadata(artifact_id)
    except AIArtifactValidationError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except Exception as exc:
        traceback.print_exc()
        return jsonify({"success": False, "error": f"Failed to read AI artifact metadata: {exc}"}), 500

    if artifact is None:
        return jsonify({"success": False, "error": f"Artifact not found: {artifact_id}"}), 404

    return jsonify({
        "success": True,
        "schema_version": ARTIFACT_STORE_SCHEMA_VERSION,
        "artifact": artifact,
    })


MULTIMODAL_EXTRACTION_ROUTE_SCHEMA_VERSION = "2026-03-14.multimodal-intake.checkpoint3"
MULTIMODAL_PLANNING_ROUTE_SCHEMA_VERSION = "2026-03-14.multimodal-intake.checkpoint4"
MULTIMODAL_PLANNING_EXECUTION_ROUTE_SCHEMA_VERSION = "2026-03-15.multimodal-intake.checkpoint9"


def _classify_multimodal_execution_failure_code(tool_name: str, error_text: str) -> str:
    normalized_tool = str(tool_name or "").strip().lower()
    normalized_error = str(error_text or "").strip().lower()

    if not normalized_error:
        return "operation_failed"

    if "not found" in normalized_error:
        if "logical volume" in normalized_error:
            return "invalid_target_logical_volume"
        if "material" in normalized_error:
            return "invalid_material_ref"
        if "define" in normalized_error:
            return "invalid_target_define"

    if normalized_tool == "manage_logical_volume" and "material" in normalized_error:
        return "invalid_material_ref"

    return "operation_failed"


def _detect_multimodal_execution_postcondition_failure(
    pm: ProjectManager,
    *,
    tool_name: str,
    arguments: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    normalized_tool = str(tool_name or "").strip().lower()
    geometry_state = getattr(pm, "current_geometry_state", None)

    if normalized_tool == "manage_logical_volume" and geometry_state is not None:
        lv_name = str(arguments.get("name") or "").strip()
        requested_material_ref = arguments.get("material_ref")
        requested_material_ref = str(requested_material_ref or "").strip()

        if lv_name:
            target_lv = geometry_state.logical_volumes.get(lv_name)
            if target_lv is None:
                return {
                    "status": "failed",
                    "status_code": "invalid_target_logical_volume",
                    "message": f"Logical volume '{lv_name}' was not found during execution.",
                    "details": {"logical_volume_name": lv_name},
                }

            if requested_material_ref:
                applied_material_ref = str(getattr(target_lv, "material_ref", "") or "").strip()
                if applied_material_ref != requested_material_ref:
                    return {
                        "status": "failed",
                        "status_code": "invalid_material_ref",
                        "message": "Requested material_ref was not applied to the target logical volume.",
                        "details": {
                            "logical_volume_name": lv_name,
                            "requested_material_ref": requested_material_ref,
                            "applied_material_ref": applied_material_ref,
                        },
                    }

    return None


def _build_multimodal_execution_outcome(
    pm: ProjectManager,
    *,
    execution_plan: Dict[str, Any],
    batch_result: Optional[Dict[str, Any]],
    execute_requested: bool,
) -> Dict[str, Any]:
    geometry_operations_raw = execution_plan.get("geometry_operations") if isinstance(execution_plan, dict) else []
    geometry_operations = geometry_operations_raw if isinstance(geometry_operations_raw, list) else []

    batch_results_raw = batch_result.get("batch_results") if isinstance(batch_result, dict) else []
    batch_results = batch_results_raw if isinstance(batch_results_raw, list) else []

    operation_results: List[Dict[str, Any]] = []

    if not execute_requested:
        for idx, operation in enumerate(geometry_operations):
            op = operation if isinstance(operation, dict) else {}
            op_args = op.get("arguments", {}) if isinstance(op.get("arguments"), dict) else {}
            operation_results.append(
                {
                    "operation_index": idx,
                    "source_operation_id": op.get("source_operation_id"),
                    "source_operation_type": op.get("source_operation_type"),
                    "target_region_id": op.get("target_region_id"),
                    "tool_name": op.get("tool_name"),
                    "status": "not_executed",
                    "status_code": "execution_not_requested",
                    "message": "Execution was not requested for this operation.",
                    "arguments": op_args,
                    "raw_result": None,
                }
            )

        return {
            "status": "not_requested",
            "summary": {
                "candidate_operation_count": len(geometry_operations),
                "attempted_operation_count": 0,
                "applied_operation_count": 0,
                "failed_operation_count": 0,
                "not_executed_operation_count": len(geometry_operations),
                "batch_result_count": 0,
                "unexpected_batch_result_count": 0,
            },
            "operation_results": operation_results,
            "diagnostics": [],
        }

    for idx, operation in enumerate(geometry_operations):
        op = operation if isinstance(operation, dict) else {}
        tool_name = op.get("tool_name")
        op_args = op.get("arguments", {}) if isinstance(op.get("arguments"), dict) else {}

        raw_result = batch_results[idx] if idx < len(batch_results) and isinstance(batch_results[idx], dict) else None
        status = "failed"
        status_code = "missing_batch_result"
        message = "No batch result entry was returned for this operation."
        details = None

        if raw_result is not None:
            if raw_result.get("success") is True:
                postcondition_failure = _detect_multimodal_execution_postcondition_failure(
                    pm,
                    tool_name=str(tool_name or ""),
                    arguments=op_args,
                )
                if postcondition_failure is None:
                    status = "applied"
                    status_code = "applied"
                    message = str(raw_result.get("message") or "Operation applied.")
                else:
                    status = str(postcondition_failure.get("status") or "failed")
                    status_code = str(postcondition_failure.get("status_code") or "operation_failed")
                    message = str(postcondition_failure.get("message") or "Operation postcondition check failed.")
                    details = postcondition_failure.get("details")
            else:
                postcondition_failure = _detect_multimodal_execution_postcondition_failure(
                    pm,
                    tool_name=str(tool_name or ""),
                    arguments=op_args,
                )
                if postcondition_failure is not None:
                    status_code = str(postcondition_failure.get("status_code") or "operation_failed")
                    message = str(postcondition_failure.get("message") or "Operation failed.")
                    details = postcondition_failure.get("details")
                else:
                    error_text = str(raw_result.get("error") or "")
                    status_code = _classify_multimodal_execution_failure_code(str(tool_name or ""), error_text)
                    message = error_text or "Operation failed."

        operation_results.append(
            {
                "operation_index": idx,
                "source_operation_id": op.get("source_operation_id"),
                "source_operation_type": op.get("source_operation_type"),
                "target_region_id": op.get("target_region_id"),
                "tool_name": tool_name,
                "status": status,
                "status_code": status_code,
                "message": message,
                "details": details,
                "arguments": op_args,
                "raw_result": raw_result,
            }
        )

    unexpected_batch_result_count = max(0, len(batch_results) - len(geometry_operations))
    diagnostics: List[Dict[str, Any]] = []
    if unexpected_batch_result_count > 0:
        diagnostics.append(
            {
                "code": "unexpected_batch_result_entries",
                "severity": "warning",
                "message": "batch_geometry_update returned more result entries than requested operations.",
                "details": {
                    "batch_result_count": len(batch_results),
                    "operation_count": len(geometry_operations),
                    "unexpected_batch_result_count": unexpected_batch_result_count,
                },
            }
        )

    attempted_operation_count = len(operation_results)
    applied_operation_count = sum(1 for item in operation_results if item.get("status") == "applied")
    failed_operation_count = sum(1 for item in operation_results if item.get("status") == "failed")

    if attempted_operation_count == 0:
        outcome_status = "no_operations"
    elif failed_operation_count == 0:
        outcome_status = "success"
    elif applied_operation_count == 0:
        outcome_status = "failed"
    else:
        outcome_status = "partial_failure"

    return {
        "status": outcome_status,
        "summary": {
            "candidate_operation_count": len(geometry_operations),
            "attempted_operation_count": attempted_operation_count,
            "applied_operation_count": applied_operation_count,
            "failed_operation_count": failed_operation_count,
            "not_executed_operation_count": 0,
            "batch_result_count": len(batch_results),
            "unexpected_batch_result_count": unexpected_batch_result_count,
        },
        "operation_results": operation_results,
        "diagnostics": diagnostics,
    }


def _build_multimodal_execution_preflight_crosscheck(
    *,
    execution_outcome: Dict[str, Any],
    baseline_preflight_report: Optional[Dict[str, Any]],
    candidate_preflight_report: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    execution_summary = execution_outcome.get("summary") if isinstance(execution_outcome, dict) else {}
    if not isinstance(execution_summary, dict):
        execution_summary = {}

    def _as_non_negative_int(value: Any) -> int:
        if isinstance(value, bool):
            parsed = int(value)
        elif isinstance(value, (int, float)):
            parsed = int(value)
        elif isinstance(value, str):
            try:
                parsed = int(float(value.strip()))
            except Exception:
                parsed = 0
        else:
            parsed = 0
        return max(0, parsed)

    execution_status = str(execution_outcome.get("status") or "").strip() if isinstance(execution_outcome, dict) else ""
    attempted_operation_count = _as_non_negative_int(execution_summary.get("attempted_operation_count"))
    applied_operation_count = _as_non_negative_int(execution_summary.get("applied_operation_count"))
    failed_operation_count = _as_non_negative_int(execution_summary.get("failed_operation_count"))

    baseline_summary = _extract_preflight_summary(baseline_preflight_report)
    candidate_summary = _extract_preflight_summary(candidate_preflight_report)

    if not isinstance(baseline_summary, dict) or not isinstance(candidate_summary, dict):
        return {
            "status": "not_available",
            "execution_status": execution_status,
            "invariants": {
                "attempted_operation_count": attempted_operation_count,
                "applied_operation_count": applied_operation_count,
                "failed_operation_count": failed_operation_count,
            },
            "mismatch_classes": ["preflight_summary_unavailable"],
            "diagnostics": [
                {
                    "code": "preflight_summary_unavailable",
                    "severity": "warning",
                    "message": "Unable to compare multimodal execution against preflight invariants because baseline or candidate summary is missing.",
                }
            ],
            "baseline_preflight_summary": baseline_summary if isinstance(baseline_summary, dict) else None,
            "candidate_preflight_summary": candidate_summary if isinstance(candidate_summary, dict) else None,
            "comparison": None,
        }

    comparison = compare_preflight_summaries(baseline_summary, candidate_summary)
    comparison_status = comparison.get("status", {}) if isinstance(comparison.get("status"), dict) else {}

    issue_count_delta_raw = comparison.get("issue_count_delta")
    if isinstance(issue_count_delta_raw, (int, float)):
        issue_count_delta = int(issue_count_delta_raw)
    else:
        issue_count_delta = 0

    regressed_can_run = bool(comparison_status.get("regressed_can_run"))
    can_run_changed = bool(comparison_status.get("can_run_changed"))
    fingerprint_changed = bool(comparison_status.get("fingerprint_changed"))

    diagnostics: List[Dict[str, Any]] = []

    if regressed_can_run:
        diagnostics.append(
            {
                "code": "preflight_can_run_regressed",
                "severity": "error",
                "message": "Preflight can_run regressed after multimodal execution.",
                "details": {
                    "baseline_can_run": comparison.get("baseline", {}).get("can_run"),
                    "candidate_can_run": comparison.get("candidate", {}).get("can_run"),
                },
            }
        )

    if execution_status == "success":
        if issue_count_delta > 0:
            diagnostics.append(
                {
                    "code": "preflight_issue_count_regressed_after_success",
                    "severity": "error",
                    "message": "Execution reported success but preflight issue count increased.",
                    "details": {
                        "issue_count_delta": issue_count_delta,
                        "added_issue_codes": comparison.get("added_issue_codes", []),
                        "increased_issue_codes": comparison.get("increased_issue_codes", []),
                    },
                }
            )
        elif issue_count_delta < 0:
            diagnostics.append(
                {
                    "code": "preflight_issue_count_improved_after_success",
                    "severity": "info",
                    "message": "Execution reported success and preflight issue count improved.",
                    "details": {
                        "issue_count_delta": issue_count_delta,
                        "resolved_issue_codes": comparison.get("resolved_issue_codes", []),
                        "reduced_issue_codes": comparison.get("reduced_issue_codes", []),
                    },
                }
            )
        elif can_run_changed or fingerprint_changed:
            diagnostics.append(
                {
                    "code": "preflight_fingerprint_changed_after_success",
                    "severity": "warning",
                    "message": "Execution reported success but preflight fingerprint/can_run changed with no issue-count delta.",
                    "details": {
                        "can_run_changed": can_run_changed,
                        "fingerprint_changed": fingerprint_changed,
                    },
                }
            )
        else:
            diagnostics.append(
                {
                    "code": "preflight_invariants_stable_after_success",
                    "severity": "info",
                    "message": "Execution reported success and preflight invariants remained stable.",
                }
            )
    elif execution_status == "partial_failure":
        if issue_count_delta > 0:
            diagnostics.append(
                {
                    "code": "preflight_issue_count_regressed_under_partial_failure",
                    "severity": "warning",
                    "message": "Execution reported partial failure and preflight issue count increased.",
                    "details": {
                        "issue_count_delta": issue_count_delta,
                        "added_issue_codes": comparison.get("added_issue_codes", []),
                        "increased_issue_codes": comparison.get("increased_issue_codes", []),
                    },
                }
            )
        else:
            diagnostics.append(
                {
                    "code": "preflight_invariants_stable_under_partial_failure",
                    "severity": "info",
                    "message": "Execution reported partial failure and preflight invariants remained stable or improved.",
                    "details": {
                        "issue_count_delta": issue_count_delta,
                    },
                }
            )
    elif execution_status == "failed":
        if applied_operation_count == 0 and (issue_count_delta != 0 or can_run_changed or fingerprint_changed):
            diagnostics.append(
                {
                    "code": "preflight_changed_without_applied_operations",
                    "severity": "warning",
                    "message": "Execution failed without applied operations but preflight invariants changed.",
                    "details": {
                        "issue_count_delta": issue_count_delta,
                        "can_run_changed": can_run_changed,
                        "fingerprint_changed": fingerprint_changed,
                    },
                }
            )

    severity_rank = {"error": 0, "warning": 1, "info": 2}
    diagnostics.sort(
        key=lambda item: (
            severity_rank.get(str(item.get("severity") or "").lower(), 9),
            str(item.get("code") or ""),
        )
    )

    mismatch_classes = sorted(
        {
            str(item.get("code") or "")
            for item in diagnostics
            if str(item.get("severity") or "").lower() in {"error", "warning"} and str(item.get("code") or "")
        }
    )

    if any(str(item.get("severity") or "").lower() == "error" for item in diagnostics):
        status = "mismatch_error"
    elif mismatch_classes:
        status = "mismatch_warning"
    else:
        status = "consistent"

    return {
        "status": status,
        "execution_status": execution_status,
        "invariants": {
            "attempted_operation_count": attempted_operation_count,
            "applied_operation_count": applied_operation_count,
            "failed_operation_count": failed_operation_count,
            "issue_count_delta": issue_count_delta,
            "can_run_changed": can_run_changed,
            "regressed_can_run": regressed_can_run,
            "fingerprint_changed": fingerprint_changed,
        },
        "mismatch_classes": mismatch_classes,
        "diagnostics": diagnostics,
        "baseline_preflight_summary": baseline_summary,
        "candidate_preflight_summary": candidate_summary,
        "comparison": comparison,
    }


def _resolve_multimodal_execution_operation_group(operation_result: Dict[str, Any]) -> Dict[str, str]:
    source_operation_type = str(operation_result.get("source_operation_type") or "").strip().lower()
    tool_name = str(operation_result.get("tool_name") or "").strip().lower()

    if source_operation_type == "apply_region_dimension_hint" or tool_name == "manage_define":
        return {"group_id": "dimension_hints", "label": "Dimension hint mutations"}

    if source_operation_type == "apply_region_material_hint" or tool_name == "manage_logical_volume":
        return {"group_id": "material_updates", "label": "Material update mutations"}

    return {"group_id": "other_mutations", "label": "Other mutation operations"}


def _build_multimodal_execution_operation_groups(execution_outcome: Dict[str, Any]) -> List[Dict[str, Any]]:
    operation_results_raw = execution_outcome.get("operation_results") if isinstance(execution_outcome, dict) else []
    operation_results = operation_results_raw if isinstance(operation_results_raw, list) else []

    groups: Dict[str, Dict[str, Any]] = {}

    for operation_result in operation_results:
        if not isinstance(operation_result, dict):
            continue

        group_meta = _resolve_multimodal_execution_operation_group(operation_result)
        group_id = group_meta["group_id"]
        group_label = group_meta["label"]

        entry = groups.get(group_id)
        if entry is None:
            entry = {
                "group_id": group_id,
                "label": group_label,
                "operation_count": 0,
                "applied_operation_count": 0,
                "failed_operation_count": 0,
                "not_executed_operation_count": 0,
                "operation_indices": [],
                "_operation_types": set(),
                "_tool_names": set(),
                "_status_codes": set(),
            }
            groups[group_id] = entry

        entry["operation_count"] += 1

        operation_index = operation_result.get("operation_index")
        if isinstance(operation_index, int):
            entry["operation_indices"].append(operation_index)

        source_operation_type = str(operation_result.get("source_operation_type") or "").strip()
        if source_operation_type:
            entry["_operation_types"].add(source_operation_type)

        tool_name = str(operation_result.get("tool_name") or "").strip()
        if tool_name:
            entry["_tool_names"].add(tool_name)

        status_code = str(operation_result.get("status_code") or "").strip()
        if status_code:
            entry["_status_codes"].add(status_code)

        status = str(operation_result.get("status") or "").strip().lower()
        if status == "applied":
            entry["applied_operation_count"] += 1
        elif status == "failed":
            entry["failed_operation_count"] += 1
        elif status == "not_executed":
            entry["not_executed_operation_count"] += 1

    normalized_groups: List[Dict[str, Any]] = []
    for group_id in sorted(groups.keys()):
        entry = groups[group_id]
        normalized_groups.append(
            {
                "group_id": entry["group_id"],
                "label": entry["label"],
                "operation_count": entry["operation_count"],
                "applied_operation_count": entry["applied_operation_count"],
                "failed_operation_count": entry["failed_operation_count"],
                "not_executed_operation_count": entry["not_executed_operation_count"],
                "operation_indices": sorted(entry["operation_indices"]),
                "operation_types": sorted(entry["_operation_types"]),
                "tool_names": sorted(entry["_tool_names"]),
                "status_codes": sorted(entry["_status_codes"]),
            }
        )

    return normalized_groups


_MULTIMODAL_OPERATION_GROUP_LABELS: Dict[str, str] = {
    "dimension_hints": "Dimension hint mutations",
    "material_updates": "Material update mutations",
    "other_mutations": "Other mutation operations",
}

_MULTIMODAL_ISSUE_CODE_FAMILY_EXACT_HINTS: Dict[str, str] = {
    "missing_material_reference": "material_updates",
    "unknown_material_reference": "material_updates",
    "invalid_replica_instance_count": "dimension_hints",
    "invalid_replica_width": "dimension_hints",
    "invalid_replica_direction": "dimension_hints",
    "invalid_division_axis": "dimension_hints",
    "invalid_division_partition_bounds": "dimension_hints",
    "invalid_division_slice_width": "dimension_hints",
    "invalid_parameterised_ncopies": "dimension_hints",
    "missing_parameterised_parameters": "dimension_hints",
    "parameterised_parameter_count_mismatch": "dimension_hints",
    "non_finite_dimension": "dimension_hints",
    "non_positive_dimension": "dimension_hints",
    "tiny_dimension": "dimension_hints",
    "invalid_radial_bounds": "dimension_hints",
    "low_facet_count": "dimension_hints",
    "possible_overlap_aabb": "dimension_hints",
    "overlap_report_truncated": "dimension_hints",
    "missing_world_volume_reference": "other_mutations",
    "unknown_world_volume_reference": "other_mutations",
    "missing_placement_volume_reference": "other_mutations",
    "unknown_placement_volume_reference": "other_mutations",
    "world_volume_referenced_as_child": "other_mutations",
    "missing_procedural_placement_definition": "other_mutations",
    "missing_procedural_volume_reference": "other_mutations",
    "unknown_procedural_volume_reference": "other_mutations",
    "placement_hierarchy_cycle": "other_mutations",
    "placement_hierarchy_cycle_report_truncated": "other_mutations",
    "missing_solid_reference": "other_mutations",
    "missing_project_state": "other_mutations",
    "recalculation_failed": "other_mutations",
}

_MULTIMODAL_ISSUE_CODE_FAMILY_KEYWORD_HINTS: Dict[str, List[str]] = {
    "material_updates": ["material"],
    "dimension_hints": [
        "dimension",
        "radial",
        "replica",
        "division",
        "parameterised",
        "facet",
        "overlap",
        "slice_width",
    ],
    "other_mutations": [
        "world_volume",
        "placement",
        "hierarchy",
        "cycle",
        "solid_reference",
        "procedural",
        "project_state",
        "recalculation",
    ],
}


def _order_multimodal_operation_group_ids(group_ids: List[str]) -> List[str]:
    ordering = ["dimension_hints", "material_updates", "other_mutations"]
    rank = {group_id: index for index, group_id in enumerate(ordering)}
    return sorted(group_ids, key=lambda item: (rank.get(item, 99), item))


def _resolve_multimodal_issue_code_family_hints(issue_code: str) -> Dict[str, Any]:
    normalized_code = str(issue_code or "").strip().lower()
    if not normalized_code:
        return {
            "family_ids": ["other_mutations"],
            "confidence": "low",
            "reason_codes": ["missing_issue_code"],
        }

    exact_match = _MULTIMODAL_ISSUE_CODE_FAMILY_EXACT_HINTS.get(normalized_code)
    if exact_match:
        return {
            "family_ids": [exact_match],
            "confidence": "high",
            "reason_codes": ["exact_issue_code_family_match"],
        }

    matched_families: List[str] = []
    for family_id, keywords in _MULTIMODAL_ISSUE_CODE_FAMILY_KEYWORD_HINTS.items():
        if any(keyword in normalized_code for keyword in keywords):
            matched_families.append(family_id)

    matched_families = _order_multimodal_operation_group_ids(list(dict.fromkeys(matched_families)))
    if matched_families:
        return {
            "family_ids": matched_families,
            "confidence": "medium",
            "reason_codes": ["keyword_issue_code_family_match"],
        }

    return {
        "family_ids": ["other_mutations"],
        "confidence": "low",
        "reason_codes": ["fallback_issue_code_family_other_mutations"],
    }


def _build_multimodal_issue_code_family_correlations(
    *,
    issue_code_delta: Dict[str, List[str]],
    comparison: Dict[str, Any],
    operation_groups: List[Dict[str, Any]],
) -> Dict[str, Any]:
    if not isinstance(issue_code_delta, dict):
        issue_code_delta = {}
    if not isinstance(comparison, dict):
        comparison = {}

    groups_by_id = {
        str(group.get("group_id") or ""): group
        for group in operation_groups
        if isinstance(group, dict) and str(group.get("group_id") or "")
    }

    executed_group_ids = _order_multimodal_operation_group_ids(
        [
            group_id
            for group_id, group in groups_by_id.items()
            if int(group.get("operation_count") or 0) > 0
        ]
    )

    counts_delta_by_code_raw = comparison.get("counts_delta_by_code")
    counts_delta_by_code: Dict[str, int] = {}
    if isinstance(counts_delta_by_code_raw, dict):
        for issue_code, delta in counts_delta_by_code_raw.items():
            issue_code_text = str(issue_code or "").strip()
            if not issue_code_text:
                continue
            if isinstance(delta, bool):
                counts_delta_by_code[issue_code_text] = int(delta)
            elif isinstance(delta, (int, float)):
                counts_delta_by_code[issue_code_text] = int(delta)
            elif isinstance(delta, str):
                try:
                    counts_delta_by_code[issue_code_text] = int(float(delta.strip()))
                except Exception:
                    continue

    change_kind_specs = [
        ("added", "added_issue_codes", 1),
        ("increased", "increased_issue_codes", 1),
        ("resolved", "resolved_issue_codes", -1),
        ("reduced", "reduced_issue_codes", -1),
    ]

    entries: List[Dict[str, Any]] = []
    confidence_counts = {"high": 0, "medium": 0, "low": 0}
    with_overlap_count = 0

    for change_kind, delta_key, fallback_delta_sign in change_kind_specs:
        codes_raw = issue_code_delta.get(delta_key)
        if not isinstance(codes_raw, list):
            continue

        codes = sorted({str(item or "").strip() for item in codes_raw if str(item or "").strip()})
        for issue_code in codes:
            family_hint = _resolve_multimodal_issue_code_family_hints(issue_code)
            family_ids = _order_multimodal_operation_group_ids(
                [
                    str(group_id or "").strip()
                    for group_id in family_hint.get("family_ids", [])
                    if str(group_id or "").strip()
                ]
            )
            if not family_ids:
                family_ids = ["other_mutations"]

            observed_overlap_ids = [group_id for group_id in family_ids if group_id in executed_group_ids]

            confidence = str(family_hint.get("confidence") or "low").strip().lower()
            if confidence not in {"high", "medium", "low"}:
                confidence = "low"

            reason_codes = [
                str(code or "").strip()
                for code in family_hint.get("reason_codes", [])
                if str(code or "").strip()
            ]

            if observed_overlap_ids:
                reason_codes.append("overlap_with_executed_operation_groups")
            elif executed_group_ids:
                reason_codes.append("no_overlap_with_executed_operation_groups")
                if confidence == "high":
                    confidence = "medium"
                elif confidence == "medium":
                    confidence = "low"
            else:
                reason_codes.append("no_executed_operation_groups_available")

            if confidence in confidence_counts:
                confidence_counts[confidence] += 1

            if observed_overlap_ids:
                with_overlap_count += 1

            delta = counts_delta_by_code.get(issue_code)
            if delta is None:
                delta = fallback_delta_sign

            likely_families: List[Dict[str, Any]] = []
            for group_id in family_ids:
                group = groups_by_id.get(group_id)
                label = str(
                    (group or {}).get("label")
                    or _MULTIMODAL_OPERATION_GROUP_LABELS.get(group_id)
                    or group_id
                )
                likely_families.append(
                    {
                        "group_id": group_id,
                        "label": label,
                        "observed_in_execution": group_id in executed_group_ids,
                    }
                )

            deduped_reason_codes: List[str] = []
            for code in reason_codes:
                if code not in deduped_reason_codes:
                    deduped_reason_codes.append(code)

            entries.append(
                {
                    "issue_code": issue_code,
                    "change_kind": change_kind,
                    "delta": int(delta),
                    "confidence": confidence,
                    "reason_codes": deduped_reason_codes,
                    "likely_operation_family_ids": [entry["group_id"] for entry in likely_families],
                    "likely_operation_families": likely_families,
                    "observed_overlap_operation_family_ids": observed_overlap_ids,
                }
            )

    return {
        "summary": {
            "changed_issue_code_count": len(entries),
            "with_observed_overlap_count": with_overlap_count,
            "without_observed_overlap_count": max(0, len(entries) - with_overlap_count),
            "confidence_counts": confidence_counts,
        },
        "entries": entries,
    }


def _build_multimodal_geant4_parity_report(
    *,
    execution_outcome: Dict[str, Any],
    preflight_crosscheck: Dict[str, Any],
) -> Dict[str, Any]:
    operation_groups = _build_multimodal_execution_operation_groups(execution_outcome)
    operation_groups_by_id = {
        str(group.get("group_id") or ""): group
        for group in operation_groups
        if str(group.get("group_id") or "")
    }

    execution_status = str(execution_outcome.get("status") or "").strip() if isinstance(execution_outcome, dict) else ""
    preflight_status = str(preflight_crosscheck.get("status") or "").strip() if isinstance(preflight_crosscheck, dict) else ""

    invariants = preflight_crosscheck.get("invariants") if isinstance(preflight_crosscheck, dict) else {}
    if not isinstance(invariants, dict):
        invariants = {}

    issue_count_delta_raw = invariants.get("issue_count_delta")
    if isinstance(issue_count_delta_raw, bool):
        issue_count_delta = int(issue_count_delta_raw)
    elif isinstance(issue_count_delta_raw, (int, float)):
        issue_count_delta = int(issue_count_delta_raw)
    elif isinstance(issue_count_delta_raw, str):
        try:
            issue_count_delta = int(float(issue_count_delta_raw.strip()))
        except Exception:
            issue_count_delta = 0
    else:
        issue_count_delta = 0

    regressed_can_run = bool(invariants.get("regressed_can_run"))

    comparison = preflight_crosscheck.get("comparison") if isinstance(preflight_crosscheck, dict) else {}
    if not isinstance(comparison, dict):
        comparison = {}

    def _as_sorted_str_list(value: Any) -> List[str]:
        if not isinstance(value, list):
            return []
        unique: List[str] = []
        for item in value:
            text = str(item or "").strip()
            if text and text not in unique:
                unique.append(text)
        return sorted(unique)

    issue_code_delta = {
        "added_issue_codes": _as_sorted_str_list(comparison.get("added_issue_codes")),
        "increased_issue_codes": _as_sorted_str_list(comparison.get("increased_issue_codes")),
        "resolved_issue_codes": _as_sorted_str_list(comparison.get("resolved_issue_codes")),
        "reduced_issue_codes": _as_sorted_str_list(comparison.get("reduced_issue_codes")),
    }

    issue_code_family_correlations = _build_multimodal_issue_code_family_correlations(
        issue_code_delta=issue_code_delta,
        comparison=comparison,
        operation_groups=operation_groups,
    )

    diagnostics_raw = preflight_crosscheck.get("diagnostics") if isinstance(preflight_crosscheck, dict) else []
    diagnostics = diagnostics_raw if isinstance(diagnostics_raw, list) else []

    high_signal_diagnostics: List[Dict[str, str]] = []
    seen_mismatch_codes: set[str] = set()
    for diagnostic in diagnostics:
        if not isinstance(diagnostic, dict):
            continue
        code = str(diagnostic.get("code") or "").strip()
        severity = str(diagnostic.get("severity") or "").strip().lower()
        message = str(diagnostic.get("message") or "").strip()
        if not code or severity not in {"error", "warning"}:
            continue
        seen_mismatch_codes.add(code)
        high_signal_diagnostics.append(
            {
                "code": code,
                "severity": severity,
                "message": message,
            }
        )

    mismatch_classes_raw = preflight_crosscheck.get("mismatch_classes") if isinstance(preflight_crosscheck, dict) else []
    mismatch_classes = _as_sorted_str_list(mismatch_classes_raw)
    for mismatch_code in mismatch_classes:
        if mismatch_code in seen_mismatch_codes:
            continue
        inferred_severity = "error" if preflight_status == "mismatch_error" else "warning"
        high_signal_diagnostics.append(
            {
                "code": mismatch_code,
                "severity": inferred_severity,
                "message": f"Preflight mismatch class detected: {mismatch_code}.",
            }
        )

    def _select_affected_group_ids(mismatch_code: str) -> List[str]:
        def _sorted_ids_for(predicate) -> List[str]:
            return sorted(
                [
                    str(group.get("group_id") or "")
                    for group in operation_groups
                    if str(group.get("group_id") or "") and predicate(group)
                ]
            )

        if mismatch_code in {
            "preflight_can_run_regressed",
            "preflight_issue_count_regressed_after_success",
            "preflight_fingerprint_changed_after_success",
        }:
            selected = _sorted_ids_for(lambda group: int(group.get("applied_operation_count") or 0) > 0)
        elif mismatch_code == "preflight_issue_count_regressed_under_partial_failure":
            selected = _sorted_ids_for(
                lambda group: int(group.get("applied_operation_count") or 0) > 0
                or int(group.get("failed_operation_count") or 0) > 0
            )
        elif mismatch_code == "preflight_changed_without_applied_operations":
            selected = _sorted_ids_for(lambda group: int(group.get("failed_operation_count") or 0) > 0)
        else:
            selected = _sorted_ids_for(lambda group: int(group.get("operation_count") or 0) > 0)

        if selected:
            return selected

        return _sorted_ids_for(lambda group: int(group.get("operation_count") or 0) > 0)

    high_signal_mismatches: List[Dict[str, Any]] = []
    affected_group_ids_union: List[str] = []

    for diagnostic in high_signal_diagnostics:
        mismatch_code = diagnostic["code"]
        affected_group_ids = _select_affected_group_ids(mismatch_code)
        for group_id in affected_group_ids:
            if group_id not in affected_group_ids_union:
                affected_group_ids_union.append(group_id)

        affected_groups: List[Dict[str, Any]] = []
        for group_id in affected_group_ids:
            group = operation_groups_by_id.get(group_id)
            if not isinstance(group, dict):
                continue
            affected_groups.append(
                {
                    "group_id": group.get("group_id"),
                    "label": group.get("label"),
                    "operation_count": int(group.get("operation_count") or 0),
                    "applied_operation_count": int(group.get("applied_operation_count") or 0),
                    "failed_operation_count": int(group.get("failed_operation_count") or 0),
                    "status_codes": list(group.get("status_codes") or []),
                }
            )

        high_signal_mismatches.append(
            {
                "mismatch_class": mismatch_code,
                "severity": diagnostic["severity"],
                "message": diagnostic["message"],
                "affected_operation_groups": affected_groups,
            }
        )

    reason_codes: List[str] = []
    if preflight_status == "mismatch_error":
        reason_codes.append("preflight_mismatch_error")
    elif preflight_status == "mismatch_warning":
        reason_codes.append("preflight_mismatch_warning")
    elif preflight_status in {"not_available", "not_requested"}:
        reason_codes.append("preflight_crosscheck_not_available")
    elif preflight_status == "consistent":
        reason_codes.append("preflight_invariants_consistent")

    reason_codes.append(f"execution_status_{execution_status or 'unknown'}")

    for mismatch_code in mismatch_classes:
        if mismatch_code not in reason_codes:
            reason_codes.append(mismatch_code)

    if preflight_status in {"not_available", "not_requested"}:
        parity_status = "not_available"
        confidence_label = "not_available"
        confidence_score = 0
    elif preflight_status == "mismatch_error":
        parity_status = "mismatch_error"
        confidence_label = "low"
        confidence_score = 25
    elif preflight_status == "mismatch_warning":
        parity_status = "mismatch_warning"
        confidence_label = "guarded"
        confidence_score = 55
    else:
        parity_status = "compatible"
        if execution_status == "success":
            confidence_label = "high"
            confidence_score = 90
        elif execution_status == "partial_failure":
            confidence_label = "guarded"
            confidence_score = 60
        elif execution_status == "failed":
            confidence_label = "low"
            confidence_score = 30
        else:
            confidence_label = "guarded"
            confidence_score = 50

    high_signal_mismatch_classes = [
        str(item.get("mismatch_class") or "")
        for item in high_signal_mismatches
        if str(item.get("mismatch_class") or "")
    ]

    return {
        "status": parity_status,
        "execution_status": execution_status,
        "preflight_crosscheck_status": preflight_status,
        "geant4_compatibility_confidence": {
            "label": confidence_label,
            "score": confidence_score,
            "reason_codes": reason_codes,
        },
        "summary": {
            "operation_group_count": len(operation_groups),
            "high_signal_mismatch_count": len(high_signal_mismatches),
            "high_signal_mismatch_classes": high_signal_mismatch_classes,
            "affected_operation_group_count": len(affected_group_ids_union),
            "issue_count_delta": issue_count_delta,
            "regressed_can_run": regressed_can_run,
        },
        "issue_code_delta": issue_code_delta,
        "issue_code_family_correlations": issue_code_family_correlations,
        "operation_groups": operation_groups,
        "high_signal_mismatches": high_signal_mismatches,
    }


@app.route('/api/ai/artifacts/<artifact_id>/extraction/review', methods=['POST'])
def build_ai_artifact_extraction_review_route(artifact_id):
    pm = get_project_manager_for_session()
    store = _get_ai_artifact_store_for_session(pm)

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"success": False, "error": "Request body must be a JSON object."}), 400

    extraction_payload = payload.get("extraction")
    if extraction_payload is None:
        extraction_payload = payload
    if not isinstance(extraction_payload, dict):
        return jsonify({"success": False, "error": "extraction must be a JSON object."}), 400

    review_status = payload.get("review_status")
    if review_status is None:
        review_status = payload.get("status", "pending_review")

    try:
        artifact = store.get_metadata(artifact_id)
    except AIArtifactValidationError as exc:
        return jsonify({"success": False, "error": str(exc), "error_code": "artifact_validation_error"}), 400
    except Exception as exc:
        traceback.print_exc()
        return jsonify({"success": False, "error": f"Failed to read AI artifact metadata: {exc}", "error_code": "artifact_metadata_error"}), 500

    if artifact is None:
        return jsonify({
            "success": False,
            "error": f"Artifact not found: {artifact_id}",
            "error_code": "artifact_not_found",
        }), 404

    if store.resolve_artifact_path(artifact_id) is None:
        return jsonify({
            "success": False,
            "error": f"Artifact blob file missing for artifact_id: {artifact_id}",
            "error_code": "artifact_blob_missing",
        }), 409

    try:
        normalized_extraction = normalize_extraction_payload(
            extraction_payload,
            artifact_metadata=artifact,
        )
        review_envelope = build_review_envelope(normalized_extraction, status=str(review_status))
        return jsonify({
            "success": True,
            "schema_version": MULTIMODAL_EXTRACTION_ROUTE_SCHEMA_VERSION,
            "artifact_schema_version": ARTIFACT_STORE_SCHEMA_VERSION,
            "extraction_schema_version": MULTIMODAL_EXTRACTION_SCHEMA_VERSION,
            "review_schema_version": MULTIMODAL_REVIEW_ENVELOPE_SCHEMA_VERSION,
            "artifact": artifact,
            "extraction": normalized_extraction,
            "review_envelope": review_envelope,
        })
    except AIMultimodalSchemaValidationError as exc:
        return jsonify({"success": False, "error": str(exc), "error_code": "extraction_validation_error"}), 400
    except Exception as exc:
        traceback.print_exc()
        return jsonify({"success": False, "error": f"Failed to build extraction/review payloads: {exc}", "error_code": "extraction_pipeline_error"}), 500


@app.route('/api/ai/artifacts/<artifact_id>/planning/envelope', methods=['POST'])
def build_ai_artifact_planning_envelope_route(artifact_id):
    pm = get_project_manager_for_session()
    store = _get_ai_artifact_store_for_session(pm)

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"success": False, "error": "Request body must be a JSON object."}), 400

    extraction_payload = payload.get("extraction")
    if not isinstance(extraction_payload, dict):
        return jsonify({"success": False, "error": "extraction must be a JSON object."}), 400

    review_envelope_payload = payload.get("review_envelope")
    if not isinstance(review_envelope_payload, dict):
        return jsonify({"success": False, "error": "review_envelope must be a JSON object."}), 400

    try:
        artifact = store.get_metadata(artifact_id)
    except AIArtifactValidationError as exc:
        return jsonify({"success": False, "error": str(exc), "error_code": "artifact_validation_error"}), 400
    except Exception as exc:
        traceback.print_exc()
        return jsonify({"success": False, "error": f"Failed to read AI artifact metadata: {exc}", "error_code": "artifact_metadata_error"}), 500

    if artifact is None:
        return jsonify({
            "success": False,
            "error": f"Artifact not found: {artifact_id}",
            "error_code": "artifact_not_found",
        }), 404

    if store.resolve_artifact_path(artifact_id) is None:
        return jsonify({
            "success": False,
            "error": f"Artifact blob file missing for artifact_id: {artifact_id}",
            "error_code": "artifact_blob_missing",
        }), 409

    try:
        normalized_extraction = normalize_extraction_payload(
            extraction_payload,
            artifact_metadata=artifact,
        )
        planning_envelope = build_planning_envelope(
            normalized_extraction,
            review_envelope=review_envelope_payload,
        )
        return jsonify({
            "success": True,
            "schema_version": MULTIMODAL_PLANNING_ROUTE_SCHEMA_VERSION,
            "artifact_schema_version": ARTIFACT_STORE_SCHEMA_VERSION,
            "extraction_schema_version": MULTIMODAL_EXTRACTION_SCHEMA_VERSION,
            "review_schema_version": MULTIMODAL_REVIEW_ENVELOPE_SCHEMA_VERSION,
            "planning_schema_version": MULTIMODAL_PLANNING_ENVELOPE_SCHEMA_VERSION,
            "artifact": artifact,
            "extraction": normalized_extraction,
            "review_envelope": review_envelope_payload,
            "planning_envelope": planning_envelope,
        })
    except AIMultimodalSchemaValidationError as exc:
        return jsonify({"success": False, "error": str(exc), "error_code": "planning_validation_error"}), 400
    except Exception as exc:
        traceback.print_exc()
        return jsonify({"success": False, "error": f"Failed to build planning envelope: {exc}", "error_code": "planning_pipeline_error"}), 500


@app.route('/api/ai/artifacts/<artifact_id>/planning/execute', methods=['POST'])
def execute_ai_artifact_planning_route(artifact_id):
    pm = get_project_manager_for_session()
    store = _get_ai_artifact_store_for_session(pm)

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"success": False, "error": "Request body must be a JSON object."}), 400

    extraction_payload = payload.get("extraction")
    if not isinstance(extraction_payload, dict):
        return jsonify({"success": False, "error": "extraction must be a JSON object."}), 400

    review_envelope_payload = payload.get("review_envelope")
    if not isinstance(review_envelope_payload, dict):
        return jsonify({"success": False, "error": "review_envelope must be a JSON object."}), 400

    region_bindings = payload.get("region_bindings")
    if region_bindings is None:
        region_bindings = payload.get("bindings", {})
    if region_bindings is None:
        region_bindings = {}
    if not isinstance(region_bindings, dict):
        return jsonify({"success": False, "error": "region_bindings must be a JSON object."}), 400

    execute_mutations = _coerce_bool(payload.get("execute"), True)

    try:
        artifact = store.get_metadata(artifact_id)
    except AIArtifactValidationError as exc:
        return jsonify({"success": False, "error": str(exc), "error_code": "artifact_validation_error"}), 400
    except Exception as exc:
        traceback.print_exc()
        return jsonify({"success": False, "error": f"Failed to read AI artifact metadata: {exc}", "error_code": "artifact_metadata_error"}), 500

    if artifact is None:
        return jsonify({
            "success": False,
            "error": f"Artifact not found: {artifact_id}",
            "error_code": "artifact_not_found",
        }), 404

    if store.resolve_artifact_path(artifact_id) is None:
        return jsonify({
            "success": False,
            "error": f"Artifact blob file missing for artifact_id: {artifact_id}",
            "error_code": "artifact_blob_missing",
        }), 409

    try:
        normalized_extraction = normalize_extraction_payload(
            extraction_payload,
            artifact_metadata=artifact,
        )
        planning_envelope = build_planning_envelope(
            normalized_extraction,
            review_envelope=review_envelope_payload,
        )
        execution_plan = build_geometry_execution_plan(
            planning_envelope,
            region_bindings=region_bindings,
        )
    except AIMultimodalSchemaValidationError as exc:
        return jsonify({"success": False, "error": str(exc), "error_code": "planning_execution_validation_error"}), 400
    except Exception as exc:
        traceback.print_exc()
        return jsonify({"success": False, "error": f"Failed to build planning execution payloads: {exc}", "error_code": "planning_execution_pipeline_error"}), 500

    response_payload = {
        "schema_version": MULTIMODAL_PLANNING_EXECUTION_ROUTE_SCHEMA_VERSION,
        "artifact_schema_version": ARTIFACT_STORE_SCHEMA_VERSION,
        "extraction_schema_version": MULTIMODAL_EXTRACTION_SCHEMA_VERSION,
        "review_schema_version": MULTIMODAL_REVIEW_ENVELOPE_SCHEMA_VERSION,
        "planning_schema_version": MULTIMODAL_PLANNING_ENVELOPE_SCHEMA_VERSION,
        "execution_plan_schema_version": MULTIMODAL_PLANNING_EXECUTION_PLAN_SCHEMA_VERSION,
        "artifact": artifact,
        "extraction": normalized_extraction,
        "review_envelope": review_envelope_payload,
        "planning_envelope": planning_envelope,
        "execution_plan": execution_plan,
    }

    planning_ready = planning_envelope.get("status") == "ready"
    if execute_mutations and not planning_ready:
        return jsonify({
            "success": False,
            "error": "planning_envelope.status must be 'ready' before mutation execution.",
            "error_code": "planning_not_ready_for_execution",
            "execution": {
                "attempted": False,
                "execute_requested": True,
                "planning_status": planning_envelope.get("status"),
                "execution_plan_status": execution_plan.get("status"),
            },
            **response_payload,
        }), 409

    execution_plan_ready = execution_plan.get("status") == "ready"
    if execute_mutations and not execution_plan_ready:
        return jsonify({
            "success": False,
            "error": "execution_plan.status is blocked; resolve execution diagnostics before applying mutations.",
            "error_code": "execution_plan_blocked",
            "execution": {
                "attempted": False,
                "execute_requested": True,
                "planning_status": planning_envelope.get("status"),
                "execution_plan_status": execution_plan.get("status"),
            },
            **response_payload,
        }), 409

    batch_operations = [
        {
            "tool_name": operation.get("tool_name"),
            "arguments": operation.get("arguments", {}),
        }
        for operation in execution_plan.get("geometry_operations", [])
    ]

    baseline_preflight_report = None
    candidate_preflight_report = None

    batch_result = None
    executed = False
    if execute_mutations:
        baseline_preflight_report = pm.run_preflight_checks()
        batch_result = dispatch_ai_tool(pm, "batch_geometry_update", {"operations": batch_operations})
        candidate_preflight_report = pm.run_preflight_checks()
        executed = True

    execution_outcome = _build_multimodal_execution_outcome(
        pm,
        execution_plan=execution_plan,
        batch_result=batch_result,
        execute_requested=execute_mutations,
    )

    if execute_mutations:
        preflight_crosscheck = _build_multimodal_execution_preflight_crosscheck(
            execution_outcome=execution_outcome,
            baseline_preflight_report=baseline_preflight_report,
            candidate_preflight_report=candidate_preflight_report,
        )
    else:
        preflight_crosscheck = {
            "status": "not_requested",
            "execution_status": execution_outcome.get("status"),
            "invariants": {
                "attempted_operation_count": 0,
                "applied_operation_count": 0,
                "failed_operation_count": 0,
            },
            "mismatch_classes": [],
            "diagnostics": [],
            "baseline_preflight_summary": None,
            "candidate_preflight_summary": None,
            "comparison": None,
        }

    parity_report = _build_multimodal_geant4_parity_report(
        execution_outcome=execution_outcome,
        preflight_crosscheck=preflight_crosscheck,
    )

    return jsonify({
        "success": True,
        **response_payload,
        "execution": {
            "attempted": execute_mutations,
            "execute_requested": execute_mutations,
            "executed": executed,
            "operation_count": len(batch_operations),
            "status": execution_outcome.get("status"),
            "summary": execution_outcome.get("summary"),
            "operation_results": execution_outcome.get("operation_results"),
            "diagnostics": execution_outcome.get("diagnostics"),
            "preflight_crosscheck": preflight_crosscheck,
            "parity_report": parity_report,
            "batch_result": batch_result,
        },
    })


def _infer_local_backend_id_from_model_prefix(model_id: Any) -> Optional[str]:
    if not isinstance(model_id, str):
        return None

    normalized_model_id = model_id.strip()
    if normalized_model_id.startswith("llama_cpp::"):
        return "llama_cpp"
    if normalized_model_id.startswith("lm_studio::"):
        return "lm_studio"
    return None


def _build_chat_backend_remediation(
    *,
    failure_stage: str,
    error_code: str,
    backend_id: Optional[str],
    readiness: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    readiness_status = str((readiness or {}).get("status") or "unknown").lower()
    backend_label = {
        "llama_cpp": "llama.cpp",
        "lm_studio": "LM Studio",
    }.get(backend_id, backend_id or "local backend")

    action_codes: List[str]
    actions: List[str]
    summary: str

    if failure_stage == "selector_validation":
        summary = "Local model selector is malformed."
        action_codes = [
            "use_backend_model_selector_format",
            "select_nonempty_local_model_name",
        ]
        actions = [
            "Use '<backend>::<model_name>' for local models (for example 'llama_cpp::llama-3.2-local').",
            "Pick a local model option from the model dropdown so selector fields are auto-filled.",
        ]
    elif failure_stage == "selector_requirements":
        summary = "Selected backend cannot satisfy the requested capabilities."
        action_codes = [
            "review_backend_requirements",
            "allow_backend_fallback",
            "switch_backend_for_missing_capabilities",
        ]
        actions = [
            "Review backend selector requirements (tools/json/streaming/context) and align them with the selected backend.",
            "Set allow_fallback=true if automatic fallback to another backend is acceptable.",
            "If a capability is missing, switch to a backend that supports it (for example Gemini for vision-heavy tasks).",
        ]
    else:
        if readiness_status == "timeout":
            summary = f"{backend_label} timed out before completing the request."
            action_codes = [
                "increase_backend_timeout",
                "retry_after_backend_idle",
                "verify_local_host_resources",
            ]
            actions = [
                "Increase local backend timeout_seconds or reduce prompt size.",
                "Retry after the local model server is idle.",
                "Verify local CPU/RAM load is not saturating model inference.",
            ]
        elif readiness_status == "unreachable":
            summary = f"{backend_label} is unreachable from AIRPET."
            action_codes = [
                "start_local_backend_service",
                "verify_backend_base_url_and_port",
                "verify_models_endpoint_reachable",
            ]
            actions = [
                "Start the local backend service (llama.cpp server or LM Studio local server).",
                "Verify backend base_url and port match the running service.",
                "Confirm '<base_url>/v1/models' is reachable from this machine.",
            ]
        elif readiness_status == "misconfigured":
            summary = f"{backend_label} is reachable but misconfigured for OpenAI-compatible chat."
            action_codes = [
                "fix_backend_configuration",
                "set_valid_local_model_name",
                "validate_openai_compatible_models_payload",
            ]
            actions = [
                "Fix backend runtime_config (base_url, endpoint_path, auth headers if required).",
                "Set a valid model id exposed by '/v1/models'.",
                "Validate that '/v1/models' returns an OpenAI-compatible payload shape.",
            ]
        else:
            summary = f"{backend_label} failed at runtime after selector resolution."
            action_codes = [
                "retry_request",
                "inspect_backend_logs",
                "refresh_backend_diagnostics",
            ]
            actions = [
                "Retry the request once to rule out transient local failures.",
                "Inspect local backend logs for request/response errors.",
                "Refresh backend diagnostics to confirm current readiness state.",
            ]

    return {
        "schema_version": LOCAL_BACKEND_DIAGNOSTICS_SCHEMA_VERSION,
        "failure_stage": failure_stage,
        "error_code": error_code,
        "backend_id": backend_id,
        "readiness_status": readiness_status,
        "summary": summary,
        "action_codes": action_codes,
        "actions": actions,
    }


def _build_chat_backend_diagnostics(
    *,
    failure_stage: str,
    error_code: str,
    backend_id: Optional[str] = None,
    runtime_config: Optional[Dict[str, Any]] = None,
    message: Optional[str] = None,
) -> Dict[str, Any]:
    stage_to_error_class = {
        "selector_validation": "selector_input_validation",
        "selector_requirements": "selector_requirement_mismatch",
        "backend_runtime": "backend_runtime_failure",
    }

    diagnostics: Dict[str, Any] = {
        "schema_version": LOCAL_BACKEND_DIAGNOSTICS_SCHEMA_VERSION,
        "failure_stage": failure_stage,
        "error_class": stage_to_error_class.get(failure_stage, "backend_diagnostics_error"),
        "error_code": error_code,
        "backend_id": backend_id,
    }

    if message:
        diagnostics["message"] = message

    if backend_id in {"llama_cpp", "lm_studio"}:
        readiness = build_local_backend_readiness_diagnostic(
            backend_id,
            runtime_config=runtime_config,
        )
    else:
        readiness = {
            "schema_version": LOCAL_BACKEND_DIAGNOSTICS_SCHEMA_VERSION,
            "status": "misconfigured",
            "readiness_code": "readiness_not_applicable",
            "ready": False,
            "message": "Readiness probe is only available for local text-first backends.",
            "backend_id": backend_id,
        }

    diagnostics["readiness"] = readiness
    diagnostics["remediation"] = _build_chat_backend_remediation(
        failure_stage=failure_stage,
        error_code=error_code,
        backend_id=backend_id,
        readiness=readiness,
    )

    return diagnostics


@app.route('/api/ai/chat', methods=['POST'])
def ai_chat_route():
    pm = get_project_manager_for_session()
    data = request.get_json() or {}
    user_message = data.get('message')
    model_id = data.get('model', 'models/gemini-2.0-flash-exp')
    turn_limit = data.get('turn_limit', 10)

    if not user_message:
        return jsonify({"success": False, "error": "No message provided."}), 400

    backend_selection_payload = None
    selector_runtime_config = None
    selector_requirements = None

    selector_cfg_raw = data.get("backend_selector")
    if selector_cfg_raw is not None and not isinstance(selector_cfg_raw, dict):
        return jsonify({
            "success": False,
            "error": "Invalid backend_selector payload. Expected an object.",
            "backend_diagnostics": _build_chat_backend_diagnostics(
                failure_stage="selector_validation",
                error_code="invalid_backend_selector_payload",
                backend_id=None,
                message="backend_selector must be a JSON object when provided.",
            ),
        }), 400

    selector_cfg = selector_cfg_raw if isinstance(selector_cfg_raw, dict) else None
    selector_inferred_from_model = False

    if selector_cfg is None:
        inferred_selector_cfg, infer_error = _infer_local_backend_selector_from_model_id(model_id)
        if infer_error:
            inferred_backend_id = _infer_local_backend_id_from_model_prefix(model_id)
            return jsonify({
                "success": False,
                "error": infer_error,
                "backend_diagnostics": _build_chat_backend_diagnostics(
                    failure_stage="selector_validation",
                    error_code="invalid_local_model_selector",
                    backend_id=inferred_backend_id,
                    message="Local model prefixes must follow '<backend>::<model_name>'.",
                ),
            }), 400
        if inferred_selector_cfg is not None:
            selector_cfg = inferred_selector_cfg
            selector_inferred_from_model = True

    if isinstance(selector_cfg, dict):
        requirements_cfg = selector_cfg.get("requirements")
        if not isinstance(requirements_cfg, dict):
            requirements_cfg = {}

        runtime_config = selector_cfg.get("runtime_config")
        if not isinstance(runtime_config, dict):
            runtime_config = None
        selector_runtime_config = runtime_config

        preferred_backend_id = (
            selector_cfg.get("preferred_backend_id")
            if selector_cfg.get("preferred_backend_id") is not None
            else selector_cfg.get("preferred_backend")
        )
        if preferred_backend_id is not None:
            preferred_backend_id = str(preferred_backend_id)

        allow_fallback = _coerce_bool(selector_cfg.get("allow_fallback"), True)

        text_request = TextGenerationRequest(
            messages=(TextMessage(role="user", content=str(user_message)),),
            require_tools=_coerce_bool(requirements_cfg.get("require_tools"), True),
            require_json_mode=_coerce_bool(requirements_cfg.get("require_json_mode"), True),
            require_streaming=_coerce_bool(requirements_cfg.get("require_streaming"), False),
            min_context_tokens=_coerce_optional_int(requirements_cfg.get("min_context_tokens")),
        )

        requirements_payload = {
            "require_tools": text_request.require_tools,
            "require_json_mode": text_request.require_json_mode,
            "require_streaming": text_request.require_streaming,
            "min_context_tokens": text_request.min_context_tokens,
        }
        selector_requirements = dict(requirements_payload)

        try:
            selection = select_backend_for_text_request(
                request=text_request,
                runtime_config=runtime_config,
                preferred_backend_id=preferred_backend_id,
                allow_fallback=allow_fallback,
            )
        except ValueError as exc:
            return jsonify({
                "success": False,
                "error": f"AI backend selection failed: {exc}",
                "backend_selection": {
                    "contract_version": ADAPTER_CONTRACT_VERSION,
                    "preferred_backend_id": preferred_backend_id,
                    "allow_fallback": allow_fallback,
                    "requirements": requirements_payload,
                    "selection_error": str(exc),
                },
                "backend_diagnostics": _build_chat_backend_diagnostics(
                    failure_stage="selector_requirements",
                    error_code="backend_selection_failed",
                    backend_id=preferred_backend_id if preferred_backend_id in {"llama_cpp", "lm_studio"} else None,
                    runtime_config=runtime_config,
                    message="Backend selector requirements could not be satisfied by the preferred backend configuration.",
                ),
            }), 400

        backend_selection_payload = {
            "contract_version": ADAPTER_CONTRACT_VERSION,
            "preferred_backend_id": preferred_backend_id,
            "allow_fallback": allow_fallback,
            "requirements": requirements_payload,
            "resolved_backend_id": selection.backend_id,
            "resolved_provider_family": selection.spec.provider_family,
            "resolved_adapter_kind": selection.spec.adapter_kind,
            "used_fallback": selection.used_fallback,
            "tried": list(selection.tried),
            "selector_source": "model_prefix" if selector_inferred_from_model else "request_payload",
        }

    selected_backend_id = backend_selection_payload.get("resolved_backend_id") if backend_selection_payload else None
    local_text_backends = {"llama_cpp", "lm_studio"}
    use_local_text_adapter = selected_backend_id in local_text_backends

    # Determine if we are using Gemini or Ollama. If selector is present, its
    # resolved backend wins over model-id heuristics.
    if selected_backend_id == "gemini_remote":
        is_gemini = True
    elif selected_backend_id in local_text_backends:
        is_gemini = False
    else:
        is_gemini = model_id.startswith("models/")

    chat_extra_payload = {"backend_selection": backend_selection_payload} if backend_selection_payload else None

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

    if use_local_text_adapter:
        pm.chat_history.append({
            "role": "user",
            "content": formatted_user_msg,
            "metadata": {
                "model_id": model_id,
                "original_message": user_message,
                "resolved_backend_id": selected_backend_id,
            },
        })

        pm.begin_transaction()

        try:
            require_tools = bool((selector_requirements or {}).get("require_tools", False))
            require_json_mode = bool((selector_requirements or {}).get("require_json_mode", True))
            require_streaming = bool((selector_requirements or {}).get("require_streaming", False))
            min_context_tokens = _coerce_optional_int((selector_requirements or {}).get("min_context_tokens"))

            # Mirror the working local flow from feature/llama-lmstudio-ui:
            # keep full sanitized history (assistant tool_calls + tool tool_call_id)
            # so llama.cpp can continue native function-calling turns reliably.
            local_messages = _build_local_adapter_message_history(pm.chat_history)
            if not local_messages:
                local_messages = [
                    TextMessage(role="system", content=load_system_prompt()),
                    TextMessage(role="user", content=formatted_user_msg),
                ]

            openai_tool_schemas: Tuple[Dict[str, Any], ...] = tuple(_build_openai_tool_schema_from_ai_tools())
            use_native_tool_loop = bool(selected_backend_id == "llama_cpp")
            effective_require_tools = bool(require_tools or use_native_tool_loop)

            job_id = None
            version_id = None
            last_execution_payload = {
                "backend_id": selected_backend_id,
                "model": None,
                "usage": None,
            }

            for turn in range(turn_limit):
                invocation_request = TextGenerationRequest(
                    messages=tuple(local_messages),
                    require_tools=effective_require_tools,
                    require_json_mode=require_json_mode,
                    require_streaming=require_streaming,
                    min_context_tokens=min_context_tokens,
                    tool_schemas=openai_tool_schemas if effective_require_tools else None,
                    tool_choice="auto" if effective_require_tools else None,
                )

                adapter_response = invoke_text_request_for_backend(
                    selected_backend_id,
                    invocation_request,
                    runtime_config=selector_runtime_config,
                )

                last_execution_payload = {
                    "backend_id": adapter_response.backend_id,
                    "model": adapter_response.model,
                    "usage": adapter_response.usage,
                }

                assistant_payload = _extract_openai_assistant_payload(
                    adapter_response.raw_response,
                    fallback_text=adapter_response.text,
                )
                assistant_text = assistant_payload.get("content") or adapter_response.text or ""
                parsed_tool_calls = assistant_payload.get("tool_calls") or []

                # Prefer native tool_calls from backend response when present.
                if not parsed_tool_calls and isinstance(adapter_response.tool_calls, list):
                    parsed_tool_calls = _normalize_tool_calls_payload(adapter_response.tool_calls)

                executable_tool_calls = _build_executable_tool_calls(parsed_tool_calls, turn)
                assistant_openai_tool_calls = _to_openai_tool_calls(executable_tool_calls, id_prefix=f"turn_{turn}")

                assistant_history_entry: Dict[str, Any] = {
                    "role": "assistant",
                    "content": assistant_text,
                    "metadata": {
                        "resolved_backend_id": adapter_response.backend_id,
                        "provider_model": adapter_response.model,
                    },
                }
                if assistant_openai_tool_calls:
                    assistant_history_entry["tool_calls"] = assistant_openai_tool_calls

                pm.chat_history.append(assistant_history_entry)
                local_messages.append(
                    TextMessage(
                        role="assistant",
                        content=assistant_text,
                        tool_calls=tuple(assistant_openai_tool_calls) if assistant_openai_tool_calls else None,
                    )
                )

                if backend_selection_payload is not None:
                    backend_selection_payload["execution_mode"] = "local_text_adapter"
                    backend_selection_payload["resolved_model"] = adapter_response.model

                if not executable_tool_calls:
                    final_text = assistant_text or adapter_response.text or "Done."
                    local_extra_payload = dict(chat_extra_payload or {})
                    local_extra_payload["backend_execution"] = last_execution_payload

                    pm.end_transaction(f"AI: {user_message[:50]}")
                    res_obj = create_success_response(pm, final_text, extra_payload=local_extra_payload)
                    if job_id:
                        res_json = res_obj.get_json()
                        res_json['job_id'] = job_id
                        res_json['version_id'] = version_id or pm.current_version_id
                        return jsonify(res_json)
                    return res_obj

                for tool_call in executable_tool_calls:
                    tool_name = tool_call.get("name")
                    if not tool_name:
                        continue

                    args = tool_call.get("arguments", {})
                    print(f"Local Adapter AI Calling Tool: {tool_name}")
                    result = dispatch_ai_tool(pm, tool_name, args)

                    if isinstance(result, dict):
                        if "job_id" in result:
                            job_id = result["job_id"]
                        if "version_id" in result:
                            version_id = result["version_id"]

                    tool_result_payload = json.dumps(result)
                    tool_call_id = str(tool_call.get("id") or f"call_{turn}_{tool_name}")
                    pm.chat_history.append({
                        "role": "tool",
                        "name": tool_name,
                        "content": tool_result_payload,
                        "tool_call_id": tool_call_id,
                    })
                    local_messages.append(
                        TextMessage(
                            role="tool",
                            content=tool_result_payload,
                            tool_call_id=tool_call_id,
                            name=tool_name,
                        )
                    )

            pm.end_transaction("AI Timeout")
            timeout_extra_payload = dict(chat_extra_payload or {})
            timeout_extra_payload["backend_execution"] = last_execution_payload
            return create_success_response(pm, "Too many tool iterations (local adapter).", extra_payload=timeout_extra_payload)

        except Exception as e:
            pm.end_transaction("AI Error")
            traceback.print_exc()
            err_payload = {
                "success": False,
                "error": f"AI backend invocation failed ({selected_backend_id}): {e}",
                "backend_diagnostics": _build_chat_backend_diagnostics(
                    failure_stage="backend_runtime",
                    error_code="local_backend_invocation_failed",
                    backend_id=selected_backend_id,
                    runtime_config=selector_runtime_config,
                    message="Local backend invocation failed after selection succeeded.",
                ),
            }
            if backend_selection_payload:
                backend_selection_payload["execution_mode"] = "local_text_adapter"
                err_payload["backend_selection"] = backend_selection_payload
            return jsonify(err_payload), 502

    if is_gemini:
        if backend_selection_payload is not None:
            backend_selection_payload["execution_mode"] = "gemini_sdk"
            backend_selection_payload["resolved_model"] = model_id

        client_instance = get_gemini_client_for_session()
        if not client_instance:
            err_payload = {"success": False, "error": "Gemini client not configured. Check your API key."}
            if backend_selection_payload:
                err_payload["backend_selection"] = backend_selection_payload
            return jsonify(err_payload), 500

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
                
                candidates = getattr(response, 'candidates', None) or []
                candidate = candidates[0] if candidates else None
                content = getattr(candidate, 'content', None) if candidate else None

                # Gemini occasionally returns a candidate with no content (e.g. filtered/empty output).
                # Fall back to response.text when available, otherwise return a repair-friendly error.
                if content is None:
                    fallback_text = getattr(response, 'text', None)
                    if fallback_text:
                        pm.chat_history.append({
                            "role": "model",
                            "parts": [{"text": fallback_text}]
                        })
                        pm.end_transaction(f"AI: {user_message[:50]}")
                        return create_success_response(pm, fallback_text, extra_payload=chat_extra_payload)

                    raise RuntimeError(
                        "Gemini returned an empty candidate content (possibly filtered/empty output). "
                        "Please retry or simplify the request."
                    )

                response_parts = getattr(content, 'parts', None) or []
                response_role = getattr(content, 'role', None) or 'model'

                # Update sanitized history with model response
                sanitized_history.append(content)

                assistant_parts = []
                for p in response_parts:
                    if getattr(p, 'text', None):
                        assistant_parts.append({"text": p.text})
                    if getattr(p, 'function_call', None):
                        assistant_parts.append({
                            "function_call": {
                                "name": p.function_call.name,
                                "args": p.function_call.args
                            }
                        })

                if not assistant_parts and getattr(response, 'text', None):
                    assistant_parts = [{"text": response.text}]

                # And update our persistent history (keeping it as a simple list of dicts for JSON compat)
                pm.chat_history.append({
                    "role": response_role,
                    "parts": assistant_parts
                })
                
                tool_calls = response_parts
                has_tool_call = False
                tool_results_parts = []
                
                for part in tool_calls:
                    if getattr(part, 'function_call', None):
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

                    final_text = getattr(response, 'text', None)
                    if not final_text:
                        text_parts = [p.get('text') for p in assistant_parts if isinstance(p, dict) and p.get('text')]
                        final_text = "\n".join(text_parts) if text_parts else "Done."
                    
                    res_obj = create_success_response(pm, final_text, extra_payload=chat_extra_payload)
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
            return create_success_response(pm, "Too many tool iterations.", extra_payload=chat_extra_payload)

        except Exception as e:
            pm.end_transaction("AI Error")
            traceback.print_exc()
            err_msg = str(e)
            status_code = 500
            if "429" in err_msg or "ResourceExhausted" in err_msg or "Quota" in err_msg:
                err_msg = f"AI Rate Limit Exceeded (429): {err_msg}. Please wait a moment before trying again."
                status_code = 429
            err_payload = {"success": False, "error": err_msg}
            if backend_selection_payload:
                err_payload["backend_selection"] = backend_selection_payload
            return jsonify(err_payload), status_code

    else: # Ollama Path
        if backend_selection_payload is not None:
            backend_selection_payload["execution_mode"] = "ollama_legacy"
            backend_selection_payload["resolved_model"] = model_id

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
                    err_text = str(ollama_err).lower()
                    if "error parsing tool call" in err_text:
                        print("Ollama tool-call parse error detected. Requesting one retry with strict JSON re-emission...")
                        retry_instruction = {
                            "role": "user",
                            "content": (
                                "Your previous tool call JSON was invalid and could not be parsed. "
                                "Re-emit the same intent as valid tool-call JSON only. "
                                "No explanatory text."
                            )
                        }
                        sanitized_history.append(retry_instruction)

                        try:
                            response = ollama.chat(
                                model=model_id,
                                messages=sanitized_history,
                                tools=ollama_tools
                            )
                        except Exception as retry_err:
                            raise retry_err
                    else:
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
                    return create_success_response(pm, assistant_msg['content'], extra_payload=chat_extra_payload)

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
            return create_success_response(pm, "Too many tool iterations (Ollama).", extra_payload=chat_extra_payload)

        except Exception as e:
            pm.end_transaction("AI Error")
            traceback.print_exc()
            err_msg = str(e)
            status_code = 500
            if "429" in err_msg:
                err_msg = f"Local AI Overloaded (429): {err_msg}."
                status_code = 429
            err_payload = {"success": False, "error": err_msg}
            if backend_selection_payload:
                err_payload["backend_selection"] = backend_selection_payload
            return jsonify(err_payload), status_code

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

@app.route('/api/ai/context_stats', methods=['GET'])
def get_ai_context_stats():
    pm = get_project_manager_for_session()
    model_id = request.args.get('model', '').strip()

    # Rough estimate: ~4 chars/token for English-ish mixed content.
    serialized = json.dumps(pm.chat_history, ensure_ascii=False, default=str)
    estimated_tokens = max(0, int(len(serialized) / 4))

    max_context_tokens = None
    context_source = "unknown"
    if model_id.startswith('models/'):
        context_source = "gemini"
        gemini_client = get_gemini_client_for_session()
        if gemini_client:
            try:
                for model in gemini_client.models.list():
                    if model.name == model_id:
                        max_context_tokens = getattr(model, 'input_token_limit', None)
                        break
            except Exception:
                pass
    elif model_id.startswith('llama_cpp::'):
        context_source = "llama_cpp"
        try:
            runtime_model = model_id.split('::', 1)[1]
            if runtime_model:
                max_context_tokens = 16_384
        except Exception:
            pass
    elif model_id.startswith('lm_studio::'):
        context_source = "lm_studio"
        try:
            runtime_model = model_id.split('::', 1)[1]
            if runtime_model:
                max_context_tokens = 32_768
        except Exception:
            pass
    elif model_id and model_id != '--export--':
        context_source = "ollama"
        # Try to read Ollama context length from local model metadata.
        try:
            show_resp = requests.post(
                'http://localhost:11434/api/show',
                json={'model': model_id},
                timeout=2
            )
            if show_resp.ok:
                info = show_resp.json() or {}
                model_info = info.get('model_info') or {}

                # Common keys: llama.context_length, qwen2.context_length, etc.
                for k, v in model_info.items():
                    if str(k).endswith('.context_length'):
                        try:
                            max_context_tokens = int(v)
                            break
                        except Exception:
                            pass

                # Fallback: parse modelfile parameters for num_ctx
                if max_context_tokens is None:
                    params_text = info.get('parameters') or ''
                    m = re.search(r'\bnum_ctx\s+(\d+)\b', str(params_text))
                    if m:
                        max_context_tokens = int(m.group(1))
        except Exception:
            pass

    utilization = None
    if isinstance(max_context_tokens, int) and max_context_tokens > 0:
        utilization = round((estimated_tokens / max_context_tokens) * 100.0, 2)

    return jsonify({
        "success": True,
        "model": model_id,
        "context_source": context_source,
        "estimated_tokens": estimated_tokens,
        "max_context_tokens": max_context_tokens,
        "utilization_pct": utilization
    })

@app.route('/api/ai/clear', methods=['POST'])
def clear_ai_history():
    pm = get_project_manager_for_session()
    pm.chat_history = []
    pm.is_changed = True
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
        success, error_msg, import_report = pm.import_step_with_options(file, options)
        if success:
            return create_success_response(
                pm,
                "STEP file imported successfully.",
                extra_payload={"step_import_report": import_report}
            )
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