# src/project_manager.py
import json
import math
import tempfile
import os
import re
import numpy as np
from datetime import datetime
from scipy.spatial.transform import Rotation as R
import shutil

from .geometry_types import GeometryState, Solid, Define, Material, Element, Isotope, \
                            LogicalVolume, PhysicalVolumePlacement, Assembly, ReplicaVolume, \
                            DivisionVolume, ParamVolume, OpticalSurface, SkinSurface, \
                            BorderSurface, ParticleSource
from .gdml_parser import GDMLParser
from .gdml_writer import GDMLWriter
from .step_parser import parse_step_file

AUTOSAVE_VERSION_ID = "autosave"

class ProjectManager:
    def __init__(self, expression_evaluator):
        self.current_geometry_state = GeometryState()
        self.gdml_parser = GDMLParser()
        
        # Give the project manager an evaluator instance
        self.expression_evaluator = expression_evaluator

        # --- History Management ---
        self.history = []
        self.history_index = -1
        self.MAX_HISTORY_SIZE = 50 # Cap the undo stack
        self._is_transaction_open = False
        self._pre_transaction_state = None

        # --- Project Management ---
        self.project_name = "untitled"
        self.projects_dir = "projects"
        self.last_state_hash = None # For auto-save change detection
        self.is_changed = False     # Flag for changes
        self.current_version_id = None # Track the currently loaded version

        # --- Track changed objects (for now only tracking certain solids) ---
        self.changed_object_ids = {'solids': set(), 'sources': set() } #, 'lvs': set(), 'defines': set()}

    def _clear_change_tracker(self):
        self.changed_object_ids = {key: set() for key in self.changed_object_ids}

    def _get_project_path(self):
        return os.path.join(self.projects_dir, self.project_name)

    def _get_next_untitled_name(self):
        base = "untitled"
        if not os.path.exists(self._get_project_path(base)):
            return base
        i = 1
        while True:
            name = f"{base}_{i}"
            if not os.path.exists(self._get_project_path(name)):
                return name
            i += 1
        
    def auto_save_project(self):
        if not self.is_changed:
            return False, "No changes to autosave."
        
        project_path = self._get_project_path()
        autosave_version_dir = os.path.join(project_path, "versions", AUTOSAVE_VERSION_ID)
        os.makedirs(autosave_version_dir, exist_ok=True)

        # The file inside is named version.json, just like any other version
        version_filepath = os.path.join(autosave_version_dir, "version.json")
        
        # Save the current state as a JSON string
        json_string = self.save_project_to_json_string()

        with open(version_filepath, 'w') as f:
            f.write(json_string)
        
        self.is_changed = False
        return True, "Autosaved."
    
    def create_empty_project(self):
        self.current_geometry_state = GeometryState()
        
        ## Create a G4_Galactic material
        world_mat = Material(
            name="G4_Galactic", 
            Z_expr="1", 
            A_expr="1.01", 
            density_expr="1.0e-25", 
            state="gas"
        )
        self.current_geometry_state.add_material(world_mat)
        
        # Create a default solid and LV for the world (e.g., a 10m box)
        world_solid_params = {'x': '10000', 'y': '10000', 'z': '10000'}
        world_solid = Solid(name="world_solid", solid_type="box", raw_parameters=world_solid_params)
        self.current_geometry_state.add_solid(world_solid)

        world_lv = LogicalVolume(name="World", solid_ref="world_solid", material_ref="G4_Galactic")
        self.current_geometry_state.add_logical_volume(world_lv)

        # Create a single box to go in the center of the world
        box_solid_params = {'x': '100', 'y': '100', 'z': '100'}
        box_solid = Solid(name="box_solid", solid_type="box", raw_parameters=box_solid_params)
        self.current_geometry_state.add_solid(box_solid)
        box_lv = LogicalVolume(name="box_LV", solid_ref="box_solid", material_ref="G4_Galactic")
        self.current_geometry_state.add_logical_volume(box_lv)
        self.add_physical_volume("World", "box_PV", "box_LV", 
                                 {'x': '0', 'y': '0', 'z': '0'},
                                 {'x': '0', 'y': '0', 'z': '0'}, 
                                 {'x': '1', 'y': '1', 'z': '1'})

        # Set this logical volume as the world volume
        self.current_geometry_state.world_volume_ref = "World"

        # Recalculate to populate evaluated fields
        self.recalculate_geometry_state()
        
        # Reset history and change tracker
        self.history = []
        self.history_index = -1
        self._clear_change_tracker() # Important for consistency
        self._capture_history_state("New project")

    def load_project_version(self, version_id):
        """Loads a specific project version from its directory."""
        version_filepath = os.path.join(self._get_version_dir(version_id), "version.json")
        with open(version_filepath, 'r') as f:
            json_string = f.read()
        
        self.load_project_from_json_string(json_string)
        self.current_version_id = version_id
        self.is_changed = False
        return True, f"Loaded version {version_id}"
    
    def _get_version_dir(self, version_id):
        """Returns the full path to a specific version directory."""
        project_path = self._get_project_path()
        return os.path.join(project_path, "versions", version_id)
    
    def save_project_version(self, description=""):
        """Saves the current geometry state as a new version."""
        # --- Check to prevent naming a version 'autosave' ---
        if description.replace(' ', '_') == AUTOSAVE_VERSION_ID:
            return None, "Cannot use a reserved name for the version description."
        
        project_path = self._get_project_path()
        versions_path = os.path.join(project_path, "versions")
        os.makedirs(versions_path, exist_ok=True)
        
        # Use a more descriptive name if available
        timestamp = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
        version_name = f"{timestamp}_{description.replace(' ', '_')}" if description else timestamp
        
        version_dir = self._get_version_dir(version_name)
        os.makedirs(version_dir)
        
        # Create a subdirectory for future simulation runs
        os.makedirs(os.path.join(version_dir, "sim_runs"), exist_ok=True)

        version_filepath = os.path.join(version_dir, "version.json")
        json_string = self.save_project_to_json_string()
        with open(version_filepath, 'w') as f:
            f.write(json_string)
            
        self.is_changed = False # The project is now saved
        self.current_version_id = version_name # This is now the active version
        return version_name, "Version saved successfully."

    def begin_transaction(self):
        """Starts a transaction, preventing intermediate history captures."""
        if not self._is_transaction_open:
            print("Beginning transaction...")
            self._is_transaction_open = True
            # Store the state *before* the transaction starts, in case we need to revert.
            self._pre_transaction_state = GeometryState.from_dict(self.current_geometry_state.to_dict())

    def end_transaction(self, description=""):
        """Ends a transaction and captures the final state to the history stack."""
        if self._is_transaction_open:
            print("Ending transaction.")
            self._is_transaction_open = False
            self._pre_transaction_state = None
            # Now, capture the single, final state of the entire operation.
            self._capture_history_state(description)

    def _capture_history_state(self, description=""):
        """Captures the current state for undo/redo."""

        # --- Don't capture state if transaction is open ---
        if self._is_transaction_open:
            # print("Transaction open, skipping intermediate history capture.")
            return # Do nothing if a transaction is in progress
        
        # If we undo and then make a change, invalidate the "redo" stack
        if self.history_index < len(self.history) - 1:
            self.history = self.history[:self.history_index + 1]

        # Use the state's to_dict method for a deep copy
        state_copy = GeometryState.from_dict(self.current_geometry_state.to_dict())
        self.history.append(state_copy)

        # Cap the history size
        if len(self.history) > self.MAX_HISTORY_SIZE:
            self.history.pop(0)
        
        self.history_index = len(self.history) - 1
        #print(f"History captured. Index: {self.history_index}, Size: {len(self.history)}")

        # Mark project as having changes
        self.is_changed = True

    def undo(self):
        """Reverts to the previous state in history and recalculates it."""
        if self.history_index > 0:
            self.history_index -= 1
            # Load the raw state from history
            self.current_geometry_state = GeometryState.from_dict(self.history[self.history_index].to_dict())
            
            # After loading any state, it must be re-evaluated to be valid for rendering.
            success, error_msg = self.recalculate_geometry_state()
            if not success:
                # This would be a serious bug if an undo leads to an invalid state
                print(f"CRITICAL WARNING: Undo operation resulted in an invalid state: {error_msg}")
                return False, f"Undo failed: {error_msg}"

            return True, "Undo successful."
        return False, "Nothing to undo."

    def redo(self):
        """Applies the next state in history and recalculates it."""
        if self.history_index < len(self.history) - 1:
            self.history_index += 1
            # Load the raw state from history
            self.current_geometry_state = GeometryState.from_dict(self.history[self.history_index].to_dict())

            # After loading any state, it must be re-evaluated.
            success, error_msg = self.recalculate_geometry_state()
            if not success:
                print(f"CRITICAL WARNING: Redo operation resulted in an invalid state: {error_msg}")
                return False, f"Redo failed: {error_msg}"

            return True, "Redo successful."
        return False, "Nothing to redo."

    def _generate_unique_name(self, base_name, existing_names_dict):
        if base_name not in existing_names_dict:
            return base_name
        i = 1
        while f"{base_name}_{i}" in existing_names_dict:
            i += 1
        return f"{base_name}_{i}"

    def _get_next_copy_number(self, parent_lv: LogicalVolume):
        """Finds the highest copy number among children and returns the next one."""
        # Check content_type and iterate through the correct list
        if parent_lv.content_type != 'physvol' or not parent_lv.content:
            return 1
        
        max_copy_no = 0
        for pv in parent_lv.content:
            if pv.copy_number > max_copy_no:
                max_copy_no = pv.copy_number
        return max_copy_no + 1

    def recalculate_geometry_state(self):
        """
        This is the core evaluation engine for the entire project.
        Recalculates defines, then material properties, then solid parameters,
        and finally placement transforms, respecting all dependencies.
        """
        if not self.current_geometry_state:
            return False, "No project state to calculate."

        state = self.current_geometry_state
        evaluator = self.expression_evaluator
        evaluator.clear_symbols() # Clear old symbols

        # Helper function for evaluating transforms ##
        def evaluate_transform_part(part_data, default_val, rotation=False):

            # Negate Euler angles for rotations
            rotation_factor = 1
            if(rotation): rotation_factor = -1

            if isinstance(part_data, str): # It's a reference to a define
                return evaluator.get_symbol(part_data, default_val)
            elif isinstance(part_data, dict): # It's a dict of expressions
                evaluated_dict = {}
                for axis, raw_expr in part_data.items():
                    try:
                        # Check if it's already a number
                        if isinstance(raw_expr, (int, float)):
                            evaluated_dict[axis] = raw_expr*rotation_factor
                        else:
                            evaluated_dict[axis] = evaluator.evaluate(str(raw_expr))[1]*rotation_factor
                    except Exception:
                        evaluated_dict[axis] = default_val.get(axis, 0)
                return evaluated_dict
            return default_val
        
        # --- Stage 1: Iteratively resolve all defines ---
        unresolved_defines = list(state.defines.values())
        max_passes = len(unresolved_defines) + 2
        for _ in range(max_passes):
            if not unresolved_defines: break
            
            resolved_this_pass = False
            still_unresolved = []
            for define_obj in unresolved_defines:
                try:
                    # For compound types, evaluate each axis expression.
                    if define_obj.type in ['position', 'rotation', 'scale']:
                        val_dict = {}
                        raw_dict = define_obj.raw_expression
                        # We handle units on the GDML side by multiplying in the expression string now
                        # but we still need to apply the default unit from the parent tag if it exists.
                        unit_str = define_obj.unit
                        for axis in ['x', 'y', 'z']:
                            if axis in raw_dict:
                                expr_to_eval = str(raw_dict[axis])
                                # If a unit is defined on the parent tag, apply it
                                if unit_str:
                                    expr_to_eval = f"({expr_to_eval}) * {unit_str}"
                                _, val = evaluator.evaluate(expr_to_eval)
                                val_dict[axis] = val

                                # NOTE: Account for a difference in rotation angle sense in THREE.js and GDML
                                if(define_obj.type == 'rotation'): val_dict[axis] *= -1

                        # Set define value and add to symbol table
                        define_obj.value = val_dict
                        evaluator.add_symbol(define_obj.name, val_dict)

                    elif define_obj.type == 'matrix':
                        raw_dict = define_obj.raw_expression
                        coldim = int(evaluator.evaluate(str(raw_dict['coldim']))[1])
                        
                        evaluated_values = [evaluator.evaluate(str(v))[1] for v in raw_dict['values']]
                        define_obj.value = evaluated_values # Store the flat list of numbers

                        # Now, expand the matrix into the symbol table like Geant4 does
                        if coldim <= 0:
                            raise ValueError("Matrix coldim must be > 0")
                        if len(evaluated_values) % coldim != 0:
                            raise ValueError("Number of values is not a multiple of coldim")

                        if len(evaluated_values) == coldim or coldim == 1: # 1D array
                             for i, val in enumerate(evaluated_values):
                                evaluator.add_symbol(f"{define_obj.name}_{i}", val)
                        else: # 2D array
                            num_rows = len(evaluated_values) // coldim
                            for r in range(num_rows):
                                for c in range(coldim):
                                    evaluator.add_symbol(f"{define_obj.name}_{r}_{c}", evaluated_values[r * coldim + c])

                    else: # constant, quantity, expression
                        expr_to_eval = str(define_obj.raw_expression)
                        unit_str = define_obj.unit
                        if unit_str:
                             expr_to_eval = f"({expr_to_eval}) * {unit_str}"
                        _, val = evaluator.evaluate(expr_to_eval)

                        # Set define value and add to symbol table
                        define_obj.value = val
                        evaluator.add_symbol(define_obj.name, val)

                    resolved_this_pass = True

                except (NameError, KeyError, TypeError):
                    still_unresolved.append(define_obj) # Depends on another define, try again next pass
                except Exception as e:
                    print(f"Error evaluating define '{define_obj.name}': {e}. Setting value to None.")
                    define_obj.value = None
                    resolved_this_pass = True # Consider it "resolved" to avoid infinite loops

            if not resolved_this_pass and still_unresolved:
                unresolved_names = [d.name for d in unresolved_defines]
                return False, f"Could not resolve defines (circular dependency or missing variable): {unresolved_names}"
            unresolved_defines = still_unresolved
            
        if unresolved_defines:
            return False, f"Could not resolve all defines. Unresolved: {[d.name for d in unresolved_defines]}"

        # --- Stage 2: Evaluate Material properties (Z, A, density) ---
        for material in state.materials.values():
            try:
                if material.Z_expr:
                    material._evaluated_Z = evaluator.evaluate(str(material.Z_expr))[1]
                if material.A_expr:
                    material._evaluated_A = evaluator.evaluate(str(material.A_expr))[1]
                if material.density_expr:
                    material._evaluated_density = evaluator.evaluate(str(material.density_expr))[1]
            except Exception as e:
                print(f"Warning: Could not evaluate material property for '{material.name}': {e}")


        # --- Stage 3: Evaluate and NORMALIZE solid parameters ---
        for solid in state.solids.values():
            solid._evaluated_parameters = {}
            raw_params = solid.raw_parameters
            
            default_lunit = raw_params.get('lunit')
            default_aunit = raw_params.get('aunit')

            length_attrs = ['x', 'y', 'z', 'rmin', 'rmax', 'r', 'dx', 'dy', 'dz', 'dx1', 'dx2', 'dy1', 'y2', 'rtor', 'ax', 'by', 'cz', 'zcut1', 'zcut2', 'zmax', 'zcut', 'rlo', 'rhi', 'rmin1', 'rmax1', 'rmin2', 'rmax2', 'x1', 'x2', 'y1', 'x3', 'x4']
            angle_attrs = ['startphi', 'deltaphi', 'starttheta', 'deltatheta', 'alpha', 'theta', 'phi', 'inst', 'outst', 'PhiTwist', 'alpha1', 'alpha2', 'Alph', 'Theta', 'Phi', 'twistedangle']

            # First, evaluate all expressions into a temporary dictionary
            temp_eval_params = {}
            for key, raw_expr in raw_params.items():
                if key in ['lunit', 'aunit']: continue
                
                # Handle "scale" key for scaledSolid
                if key == 'scale' and isinstance(raw_expr, dict):
                    evaluated_scale = {}
                    for axis, axis_expr in raw_expr.items():
                        try:
                            evaluated_scale[axis] = evaluator.evaluate(str(axis_expr))[1]
                        except Exception as e:
                            print(f"Warning: Could not eval scale param '{axis}' for solid '{solid.name}': {e}")
                            evaluated_scale[axis] = 1.0 # Default to 1 on failure
                    temp_eval_params[key] = evaluated_scale
                # Handle "solid_ref" key for scaledSolid: just pass it along
                elif key == 'solid_ref' and isinstance(raw_expr, str):
                    temp_eval_params[key] = raw_expr
                elif isinstance(raw_expr, (str, int, float)):

                    # Add default units to expression
                    expr_to_eval = str(raw_expr)
                    if key in length_attrs and default_lunit:
                        expr_to_eval = f"({expr_to_eval}) * {default_lunit}"
                    elif key in angle_attrs and default_aunit:
                        expr_to_eval = f"({expr_to_eval}) * {default_aunit}"

                    try:
                        temp_eval_params[key] = evaluator.evaluate(expr_to_eval)[1]
                    except Exception as e:
                        print(f"Warning: Could not eval solid param '{key}' for solid '{solid.name}' with expression '{expr_to_eval}': {e}")
                        temp_eval_params[key] = float('nan')
                else:
                    temp_eval_params[key] = raw_expr

            # Second pass for normalization ##
            p = temp_eval_params
            ep = solid._evaluated_parameters

            solid_type = solid.type
            if solid_type == 'scaledSolid':
                # For scaled solids, the evaluated params are the scale dict and the solid_ref
                ep['scale'] = p.get('scale', {'x': 1.0, 'y': 1.0, 'z': 1.0})
                ep['solid_ref'] = p.get('solid_ref')

            elif solid_type == 'reflectedSolid':
                ep['solid_ref'] = p.get('solid_ref')
                transform = p.get('transform', {})
                ep['transform'] = {
                    '_evaluated_position': evaluate_transform_part(transform.get('position'), {'x': 0, 'y': 0, 'z': 0}, rotation=False),
                    '_evaluated_rotation': evaluate_transform_part(transform.get('rotation'), {'x': 0, 'y': 0, 'z': 0}, rotation=True),
                    '_evaluated_scale': evaluate_transform_part(transform.get('scale'), {'x': 1, 'y': 1, 'z': 1}, rotation=False)
                }

            elif solid_type == 'box':
                ep['x'] = p.get('x', 0)
                ep['y'] = p.get('y', 0)
                ep['z'] = p.get('z', 0)
            
            elif solid_type == 'tube':
                ep['rmin'] = p.get('rmin', 0)
                ep['rmax'] = p.get('rmax', 10)
                ep['z'] = p.get('z', 20)
                ep['startphi'] = p.get('startphi', 0)
                ep['deltaphi'] = p.get('deltaphi', 2 * math.pi) # Default is a full circle

            elif solid_type == 'cone':
                ep['rmin1'] = p.get('rmin1', 0)
                ep['rmax1'] = p.get('rmax1', 10)
                ep['rmin2'] = p.get('rmin2', 0)
                ep['rmax2'] = p.get('rmax2', 10)
                ep['z']     = p.get('z', 0)
                ep['startphi'] = p.get('startphi', 0)
                ep['deltaphi'] = p.get('deltaphi', 2 * math.pi)

            elif solid_type == 'sphere':
                ep['rmin'] = p.get('rmin', 0)
                ep['rmax'] = p.get('rmax', 10)
                ep['startphi'] = p.get('startphi', 0)
                ep['deltaphi'] = p.get('deltaphi', 2 * math.pi)
                ep['starttheta'] = p.get('starttheta', 0)
                ep['deltatheta'] = p.get('deltatheta', math.pi)

            elif solid_type == 'trd':
                ep['dx1'] = p.get('x1', 0) / 2.0
                ep['dx2'] = p.get('x2', 0) / 2.0
                ep['dy1'] = p.get('y1', 0) / 2.0
                ep['dy2'] = p.get('y2', 0) / 2.0
                ep['dz'] = p.get('z', 0) / 2.0

            elif solid.type == 'para':
                ep['x'] = p.get('x', 0)
                ep['y'] = p.get('y', 0)
                ep['z'] = p.get('z', 0)
                ep['alpha'] = p.get('alpha', 0)
                ep['theta'] = p.get('theta', 0)
                ep['phi'] = p.get('phi', 0)
            
            elif solid.type == 'hype':
                 ep['z'] = p.get('z', 0)
                 ep['rmin'] = p.get('rmin', 0)
                 ep['rmax'] = p.get('rmax', 0)
                 ep['inst'] = p.get('inst', 0)
                 ep['outst'] = p.get('outst', 0)

            elif solid_type == 'trap':
                ep['z'] = p.get('z', 0) / 2.0
                ep['theta'] = p.get('theta', 0)
                ep['phi'] = p.get('phi', 0)
                ep['y1'] = p.get('y1', 0) / 2.0
                ep['x1'] = p.get('x1', 0) / 2.0
                ep['x2'] = p.get('x2', 0) / 2.0
                ep['alpha1'] = p.get('alpha1', 0)
                ep['y2'] = p.get('y2', 0) / 2.0
                ep['x3'] = p.get('x3', 0) / 2.0
                ep['x4'] = p.get('x4', 0) / 2.0
                ep['alpha2'] = p.get('alpha2', 0)
                
            elif solid_type == 'twistedbox':
                ep['PhiTwist'] = p.get('PhiTwist', 0)
                ep['x'] = p.get('x', 0) / 2.0
                ep['y'] = p.get('y', 0) / 2.0
                ep['z'] = p.get('z', 0) / 2.0
            
            elif solid_type == 'twistedtrd':
                ep['PhiTwist'] = p.get('PhiTwist', 0)
                ep['x1'] = p.get('x1', 0) / 2.0
                ep['x2'] = p.get('x2', 0) / 2.0
                ep['y1'] = p.get('y1', 0) / 2.0
                ep['y2'] = p.get('y2', 0) / 2.0
                ep['z'] = p.get('z', 0) / 2.0

            elif solid_type == 'twistedtrap':
                ep['PhiTwist'] = p.get('PhiTwist', 0)
                ep['z'] = p.get('z', 0)
                ep['Theta'] = p.get('Theta', 0)
                ep['Phi'] = p.get('Phi', 0)
                ep['y1'] = p.get('y1', 0)
                ep['x1'] = p.get('x1', 0)
                ep['x2'] = p.get('x2', 0)
                ep['y2'] = p.get('y2', 0)
                ep['x3'] = p.get('x3', 0)
                ep['x4'] = p.get('x4', 0)
                ep['Alph'] = p.get('Alph', 0)

            elif solid_type == 'twistedtubs':
                ep['twistedangle'] = p.get('twistedangle', 0)
                ep['endinnerrad'] = p.get('endinnerrad', 0)
                ep['endouterrad'] = p.get('endouterrad', 0)
                ep['zlen'] = p.get('zlen', 0) / 2.0
                ep['phi'] = p.get('phi', 2 * math.pi)

            elif solid_type in ['genericPolycone', 'genericPolyhedra']:
                ep['startphi'] = p.get('startphi', 0)
                ep['deltaphi'] = p.get('deltaphi', 2 * math.pi)
                ep['rzpoints'] = p.get('rzpoints', [])
                if solid_type == 'genericPolyhedra':
                    ep['numsides'] = p.get('numsides', 32)

            elif solid_type == 'xtru':
                # Evaluate all the nested dictionaries of expressions
                ep['twoDimVertices'] = []
                for v in p.get('twoDimVertices', []):
                    ep['twoDimVertices'].append({
                        'x': evaluator.evaluate(str(v.get('x', '0')))[1],
                        'y': evaluator.evaluate(str(v.get('y', '0')))[1]
                    })
                
                ep['sections'] = []
                for s in p.get('sections', []):
                    ep['sections'].append({
                        'zOrder': int(evaluator.evaluate(str(s.get('zOrder', '0')))[1]),
                        'zPosition': evaluator.evaluate(str(s.get('zPosition', '0')))[1],
                        'xOffset': evaluator.evaluate(str(s.get('xOffset', '0')))[1],
                        'yOffset': evaluator.evaluate(str(s.get('yOffset', '0')))[1],
                        'scalingFactor': evaluator.evaluate(str(s.get('scalingFactor', '1.0')))[1]
                    })
                # Sort sections by zOrder just in case
                ep['sections'].sort(key=lambda s: s['zOrder'])

            else:
                # For all other solids, just copy the evaluated params.
                # This is safe because their parameters are generally all required.
                solid._evaluated_parameters = p

        # --- Stage 4: Evaluate all placement transforms ---

        # Get all LVs and Assemblies to check for placements
        all_lvs = list(state.logical_volumes.values())
        all_asms = list(state.assemblies.values())

        # Iterate through LVs to evaluate their placements
        for lv in all_lvs:
            if lv.content_type == 'physvol':
                for pv in lv.content: # Use the new .content attribute
                    try:
                        pv.copy_number = int(evaluator.evaluate(str(pv.copy_number_expr))[1])
                    except Exception as e:
                        pv.copy_number = 0
                    
                    pv._evaluated_position = evaluate_transform_part(pv.position, {'x': 0, 'y': 0, 'z': 0}, rotation=False)
                    pv._evaluated_rotation = evaluate_transform_part(pv.rotation, {'x': 0, 'y': 0, 'z': 0}, rotation=True)
                    pv._evaluated_scale = evaluate_transform_part(pv.scale, {'x': 1, 'y': 1, 'z': 1}, rotation=False)
            
            elif lv.content_type in ['replica', 'division', 'parameterised']:
                # For procedural placements, we need to evaluate their parameters (width, offset, etc.)
                proc_obj = lv.content
                if proc_obj:

                    # Evaluate common procedural parameters if they exist
                    if hasattr(proc_obj, 'width'):
                        try:
                            proc_obj._evaluated_width = float(evaluator.evaluate(str(proc_obj.width))[1])
                        except Exception: proc_obj._evaluated_width = 0.0
                    if hasattr(proc_obj, 'offset'):
                        try:
                            proc_obj._evaluated_offset = float(evaluator.evaluate(str(proc_obj.offset))[1])
                        except Exception: proc_obj._evaluated_offset = 0.0
                    if hasattr(proc_obj, 'number'):
                        try:
                            proc_obj._evaluated_number = int(evaluator.evaluate(str(proc_obj.number))[1])
                        except Exception: proc_obj._evaluated_number = 0
                    
                    # Evaluate replica-specific transforms if they exist
                    if hasattr(proc_obj, 'start_position'):
                        proc_obj._evaluated_start_position = evaluate_transform_part(proc_obj.start_position, {'x': 0, 'y': 0, 'z': 0}, rotation=False)
                    if hasattr(proc_obj, 'start_rotation'):
                        proc_obj._evaluated_start_rotation = evaluate_transform_part(proc_obj.start_rotation, {'x': 0, 'y': 0, 'z': 0}, rotation=True)

                    # Add evaluation logic for parameterised volumes
                    if hasattr(proc_obj, 'ncopies'):
                        try:
                            proc_obj._evaluated_ncopies = int(evaluator.evaluate(str(proc_obj.ncopies))[1])
                        except Exception: proc_obj._evaluated_ncopies = 0

                    if hasattr(proc_obj, 'parameters'):
                        for param_set in proc_obj.parameters:
                            # Evaluate the transform for this instance
                            param_set._evaluated_position = evaluate_transform_part(param_set.position, {'x': 0, 'y': 0, 'z': 0}, rotation=False)
                            param_set._evaluated_rotation = evaluate_transform_part(param_set.rotation, {'x': 0, 'y': 0, 'z': 0}, rotation=True)
                            
                            # Evaluate each dimension expression for this instance
                            evaluated_dims = {}
                            for key, raw_expr in param_set.dimensions.items():
                                try:
                                    evaluated_dims[key] = float(evaluator.evaluate(str(raw_expr))[1])
                                except Exception as e:
                                    print(f"Warning: Could not eval param dimension '{key}' for '{lv.name}': {e}")
                                    evaluated_dims[key] = 0.0
                            param_set._evaluated_dimensions = evaluated_dims


        # Iterate through Assemblies to evaluate their placements
        for asm in all_asms:
            for pv in asm.placements:
                try:
                    pv.copy_number = int(evaluator.evaluate(str(pv.copy_number_expr))[1])
                except Exception as e:
                    pv.copy_number = 0
                
                pv._evaluated_position = evaluate_transform_part(pv.position, {'x': 0, 'y': 0, 'z': 0})
                pv._evaluated_rotation = evaluate_transform_part(pv.rotation, {'x': 0, 'y': 0, 'z': 0})
                pv._evaluated_scale = evaluate_transform_part(pv.scale, {'x': 1, 'y': 1, 'z': 1})

        ## Stage 5 - Evaluate transforms inside boolean solid recipes ##
        for solid in state.solids.values():
            if solid.type == 'boolean':
                recipe = solid.raw_parameters.get('recipe', [])
                for item in recipe:
                    transform = item.get('transform', {})
                    if transform:
                         # Use the same helper to evaluate the nested transforms
                         transform['_evaluated_position'] = evaluate_transform_part(transform.get('position'), {'x':0, 'y':0, 'z':0})
                         transform['_evaluated_rotation'] = evaluate_transform_part(transform.get('rotation'), {'x':0, 'y':0, 'z':0})

        # --- Evaluate Source Positions ---
        for source in state.sources.values():
            source._evaluated_position = evaluate_transform_part(source.position, {'x': 0, 'y': 0, 'z': 0})
            source._evaluated_rotation = evaluate_transform_part(source.rotation, {'x': 0, 'y': 0, 'z': 0}, rotation=True)

        return True, None

    def load_gdml_from_string(self, gdml_string):
        """
        Orchestrates GDML parsing AND evaluation.
        """
        # Step 1: Parse the GDML into a raw state with expressions.
        self.current_geometry_state = self.gdml_parser.parse_gdml_string(gdml_string)
        
        # Step 2: Now that the full raw state is loaded, evaluate everything.
        success, error_msg = self.recalculate_geometry_state()
        if not success:
            print(f"Warning after parsing GDML: {error_msg}")
            # Even if it fails, we return the partially evaluated state for debugging.

        # --- Reset history on load ---
        self.history = []
        self.history_index = -1
        self._capture_history_state("Loaded project from GDML")
        
        return self.current_geometry_state

    def get_threejs_description(self):
        if self.current_geometry_state:
            return self.current_geometry_state.get_threejs_scene_description()
        return []

    def save_project_to_json_string(self):
        if self.current_geometry_state:
            return json.dumps(self.current_geometry_state.to_dict(), indent=2)
        return "{}"

    def load_project_from_json_string(self, json_string):
        data = json.loads(json_string)
        self.current_geometry_state = GeometryState.from_dict(data)
        success, error_msg = self.recalculate_geometry_state()
        if not success:
            print(f"Warning after loading JSON project: {error_msg}")

        # --- Reset history on load ---
        self.history = []
        self.history_index = -1
        self._capture_history_state("Loaded project from JSON")

        return self.current_geometry_state

    def export_to_gdml_string(self):
        if self.current_geometry_state:
            writer = GDMLWriter(self.current_geometry_state)
            return writer.get_gdml_string()
        return "<?xml version='1.0' encoding='UTF-8'?>\n<gdml />"
    
    def get_full_project_state_dict(self, exclude_unchanged_tessellated=False):
        """
        Returns the entire current geometry state as a dictionary.
        Can optionally filter out heavy, unchanged tessellated solids.
        """
        if not self.current_geometry_state:
            return {}

        state_dict = self.current_geometry_state.to_dict()
        
        # For now, the only object tracking optimization involves large tessellated solids.
        if exclude_unchanged_tessellated:
            filtered_solids = {}
            changed_solids_set = self.changed_object_ids['solids'] or set()
            
            for name, solid_data in state_dict['solids'].items():
                is_tessellated = solid_data.get('type') == 'tessellated'
                # A tessellated solid is "static" if its facets have absolute vertices
                is_static = is_tessellated and \
                            len(solid_data['raw_parameters'].get('facets', [])) > 0 and \
                            'vertices' in solid_data['raw_parameters']['facets'][0]
                
                # Keep the solid if:
                # 1. It's not a static tessellated solid.
                # 2. It's one of the solids that was explicitly changed in this operation.
                if not is_static or name in changed_solids_set:
                    filtered_solids[name] = solid_data
            
            state_dict['solids'] = filtered_solids
        
        return state_dict

    def get_object_details(self, object_type, object_name_or_id):
        """
        Get details for a specific object by its type and name/ID.
        'object_type' can be 'define', 'material', 'solid', 'logical_volume', 'physical_volume'.
        For 'physical_volume', object_name_or_id would be its unique ID.
        """
        if not self.current_geometry_state: return None
        
        state = self.current_geometry_state
        obj = None

        if object_type == "define": 
            obj = state.defines.get(object_name_or_id)
        elif object_type == "material": 
            obj = state.materials.get(object_name_or_id)
        elif object_type == "element": 
            obj = state.elements.get(object_name_or_id)
        elif object_type == "isotope": 
            obj = state.isotopes.get(object_name_or_id)
        elif object_type == "solid": 
            obj = state.solids.get(object_name_or_id)
        elif object_type == "logical_volume": 
            obj = state.logical_volumes.get(object_name_or_id)
        elif object_type == "assembly":
            obj = state.assemblies.get(object_name_or_id)
        elif object_type == "optical_surface":
            obj = state.optical_surfaces.get(object_name_or_id)
        elif object_type == "skin_surface":
            obj = state.skin_surfaces.get(object_name_or_id)
        elif object_type == "border_surface":
            obj = state.border_surfaces.get(object_name_or_id)
        elif object_type == "physical_volume":
            # Search through all logical volumes to find the PV
            all_lvs = list(state.logical_volumes.values())
            for lv in all_lvs:
                # We only search in LVs that contain physical placements
                if lv.content_type == 'physvol':
                    for pv in lv.content:
                        if pv.id == object_name_or_id:
                            obj = pv
                            break
                if obj:
                    break
            
            # Also search through assemblies (important for completeness)
            if not obj:
                all_asms = list(state.assemblies.values())
                for asm in all_asms:
                    for pv in asm.placements:
                        if pv.id == object_name_or_id:
                            obj = pv
                            break
                    if obj:
                        break
        
        elif object_type == "particle_source":
            # Search in sources dict. 
            for s in state.sources.values():
                if s.id == object_name_or_id or s.name == object_name_or_id:
                    obj = s
                    break

        return obj.to_dict() if obj else None

    def update_object_property(self, object_type, object_id, property_path, new_value):
        """
        Updates a property of an object.
        object_id: unique ID for Solids, LVs, PVs. For Defines/Materials, it's their name.
        property_path: e.g., "name", "parameters.x", "position.x"
        """
        # This needs careful implementation to find the object and update its property.
        # Example for a physical volume's position.x:
        if not self.current_geometry_state: return False
        print(f"Attempting to update: Type='{object_type}', ID/Name='{object_id}', Path='{property_path}', NewValue='{new_value}'")

        target_obj = None

        # Handle all possible object types.
        if object_type == "define": target_obj = self.current_geometry_state.defines.get(object_id)
        elif object_type == "material": target_obj = self.current_geometry_state.materials.get(object_id)
        elif object_type == "solid": target_obj = self.current_geometry_state.solids.get(object_id)
        elif object_type == "logical_volume": target_obj = self.current_geometry_state.logical_volumes.get(object_id)
        elif object_type == "physical_volume":

            # Iterate through LVs and Assemblies
            all_lvs = list(self.current_geometry_state.logical_volumes.values())
            for lv in all_lvs:
                if lv.content_type == 'physvol':
                    for pv in lv.content:
                        if pv.id == object_id:
                            target_obj = pv
                            break
                if target_obj: break
            
            if not target_obj:
                all_asms = list(self.current_geometry_state.assemblies.values())
                for asm in all_asms:
                    for pv in asm.placements:
                        if pv.id == object_id:
                            target_obj = pv
                            break
                    if target_obj: break

        if not target_obj: 
            return False, f"Could not find object of type '{object_type}' with ID/Name '{object_id}'"

        try:
            path_parts = property_path.split('.')
            current_level_obj = target_obj
            for part in path_parts[:-1]:
                if isinstance(current_level_obj, dict):
                    current_level_obj = current_level_obj[part]
                else:
                    current_level_obj = getattr(current_level_obj, part)
            
            final_key = path_parts[-1]
            if isinstance(current_level_obj, dict):
                current_level_obj[final_key] = new_value
            else:
                setattr(current_level_obj, final_key, new_value)
        except (AttributeError, KeyError) as e:
            return False, f"Invalid property path '{property_path}': {e}"
        
        # Capture the new state
        self._capture_history_state(f"Updated {property_path} of {object_type} {object_id}")

        success, error_msg = self.recalculate_geometry_state()
        if not success:
            # Add logic here to revert the change?
            return False, f"Update failed during recalculation: {error_msg}"
        return True, None

    def add_define(self, name_suggestion, define_type, raw_expression, unit=None, category=None):
        if not self.current_geometry_state: return None, "No project loaded"
        name = self._generate_unique_name(name_suggestion, self.current_geometry_state.defines)
        new_define = Define(name, define_type, raw_expression, unit, category)
        self.current_geometry_state.add_define(new_define)
        self.recalculate_geometry_state()

        # Capture the new state
        self._capture_history_state(f"Added define {name}")

        return new_define.to_dict(), None

    def update_define(self, define_name, new_raw_expression, new_unit=None, new_category=None):
        if not self.current_geometry_state:
            return False, "No project loaded."

        target_define = self.current_geometry_state.defines.get(define_name)
        if not target_define:
            return False, f"Define '{define_name}' not found."
            
        target_define.raw_expression = new_raw_expression
        
        if new_unit is not None: 
            target_define.unit = new_unit
        if new_category is not None: 
            target_define.category = new_category

        # Capture the new state
        self._capture_history_state(f"Updated define {define_name}")

        success, error_msg = self.recalculate_geometry_state()
        return success, error_msg

    def add_material(self, name_suggestion, properties_dict):
        if not self.current_geometry_state: return None, "No project loaded"
        name = self._generate_unique_name(name_suggestion, self.current_geometry_state.materials)
        # Assumes properties_dict contains expression strings like Z_expr, A_expr, density_expr
        new_material = Material(name, **properties_dict)
        self.current_geometry_state.add_material(new_material)
        self.recalculate_geometry_state()

        # Capture the new state
        self._capture_history_state(f"Added material {name}")

        return new_material.to_dict(), None

    def update_material(self, mat_name, new_properties):
        if not self.current_geometry_state: return False, "No project loaded"
        target_mat = self.current_geometry_state.materials.get(mat_name)
        if not target_mat: return False, f"Material '{mat_name}' not found."

        # Update properties from the provided dictionary
        # if 'density' in new_properties: target_mat.density = new_properties['density']
        # if 'Z' in new_properties: target_mat.Z = new_properties['Z']
        # if 'A' in new_properties: target_mat.A = new_properties['A']
        # if 'components' in new_properties: target_mat.components = new_properties['components']
        for key, value in new_properties.items(): setattr(target_mat, key, value)
        
        # Capture the new state
        self._capture_history_state(f"Updated material {mat_name}")

        self.recalculate_geometry_state()
        return True, None

    def add_element(self, name_suggestion, params):
        """Adds a new element to the project."""
        if not self.current_geometry_state:
            return None, "No project loaded"
        
        name = self._generate_unique_name(name_suggestion, self.current_geometry_state.elements)
        
        new_element = Element(
            name=name,
            formula=params.get('formula'),
            Z=params.get('Z'),
            A_expr=params.get('A_expr'),
            components=params.get('components', [])
        )
        
        self.current_geometry_state.add_element(new_element)
        self.recalculate_geometry_state()

        # Capture the new state
        self._capture_history_state(f"Added element {name}")
        
        return new_element.to_dict(), None

    def update_element(self, element_name, new_params):
        """Updates an existing element."""
        if not self.current_geometry_state:
            return False, "No project loaded"
        
        target_element = self.current_geometry_state.elements.get(element_name)
        if not target_element:
            return False, f"Element '{element_name}' not found."

        target_element.formula = new_params.get('formula', target_element.formula)
        target_element.Z = new_params.get('Z', target_element.Z)
        target_element.A_expr = new_params.get('A_expr', target_element.A_expr)
        target_element.components = new_params.get('components', target_element.components)

        # Capture the new state
        self._capture_history_state(f"Updated element {element_name}")

        self.recalculate_geometry_state()
        return True, None

    def add_isotope(self, name_suggestion, params):
        if not self.current_geometry_state: return None, "No project loaded"
        name = self._generate_unique_name(name_suggestion, self.current_geometry_state.isotopes)
        new_isotope = Isotope(name, Z=params.get('Z'), N=params.get('N'), A_expr=params.get('A_expr'))
        self.current_geometry_state.add_isotope(new_isotope)
        self.recalculate_geometry_state()

        # Capture the new state
        self._capture_history_state(f"Added isotope {name}")

        return new_isotope.to_dict(), None

    def update_isotope(self, isotope_name, new_params):
        if not self.current_geometry_state: return False, "No project loaded"
        target_isotope = self.current_geometry_state.isotopes.get(isotope_name)
        if not target_isotope: return False, f"Isotope '{isotope_name}' not found."
        target_isotope.Z = new_params.get('Z', target_isotope.Z)
        target_isotope.N = new_params.get('N', target_isotope.N)
        target_isotope.A_expr = new_params.get('A_expr', target_isotope.A_expr)
        self.recalculate_geometry_state()

        # Capture the new state
        self._capture_history_state(f"Updated isotope {isotope_name}")

        return True, None

    def add_solid(self, name_suggestion, solid_type, raw_parameters):
        """
        Adds a new solid to the project.
        """
        if not self.current_geometry_state:
            return None, "No project loaded"
        
        # Start with a clear change tracker
        self._clear_change_tracker()
        
        name = self._generate_unique_name(name_suggestion, self.current_geometry_state.solids)
        new_solid = Solid(name, solid_type, raw_parameters)
        self.current_geometry_state.add_solid(new_solid)

        # Set the new solid as "changed" so it is sent to the front end for sure
        self.changed_object_ids['solids'].add(name)

        # Capture the new state
        self._capture_history_state(f"Added solid {name}")
        
        return new_solid.to_dict(), None

    def update_solid(self, solid_id, new_raw_parameters):
        """Updates the raw parameters of an existing primitive solid."""
        if not self.current_geometry_state:
            return False, "No project loaded."
        
        target_solid = self.current_geometry_state.solids.get(solid_id)
        if not target_solid:
            return False, f"Solid '{solid_id}' not found."
            
        if target_solid.type == 'boolean':
            return False, "Boolean solids must be updated via the 'update_boolean_solid' method."
            
        target_solid.raw_parameters = new_raw_parameters

        # Capture the new state
        self._capture_history_state(f"Added standard solid {solid_id}")
        
        success, error_msg = self.recalculate_geometry_state()
        return success, error_msg

    def add_boolean_solid(self, name_suggestion, recipe):
        """
        Creates a single 'virtual' boolean solid that stores the recipe.
        """
        if not self.current_geometry_state: return False, "No project loaded."
        if len(recipe) < 2 or recipe[0].get('op') != 'base':
            return False, "Invalid recipe format."

        for item in recipe:
            ref = item.get('solid_ref')
            if not ref or ref not in self.current_geometry_state.solids:
                return False, f"Solid '{ref}' not found in project."

        name = self._generate_unique_name(name_suggestion, self.current_geometry_state.solids)
        params = {"recipe": recipe}
        new_solid = Solid(name, "boolean", params)
        self.current_geometry_state.add_solid(new_solid)

        # Capture the new state
        self._capture_history_state(f"Added boolean solid {name}")
        
        return new_solid.to_dict(), None

    def update_boolean_solid(self, solid_name, new_recipe):
        """
        Updates an existing boolean solid with a new recipe.
        """
        if not self.current_geometry_state: return False, "No project loaded."
        
        target_solid = self.current_geometry_state.solids.get(solid_name)
        if not target_solid or target_solid.type != 'boolean':
            return False, f"Boolean solid '{solid_name}' not found."

        # Validate new recipe
        for item in new_recipe:
            ref = item.get('solid_ref')
            if not ref or ref not in self.current_geometry_state.solids:
                return False, f"Solid '{ref}' not found in project."

        target_solid.raw_parameters['recipe'] = new_recipe
        self.recalculate_geometry_state()

        # Capture the new state
        self._capture_history_state(f"Updated boolean solid {solid_name}")

        return True, None

    def add_solid_and_place(self, solid_params, lv_params, pv_params):
        """
        Handles both primitive and boolean solid creation.
        """
        if not self.current_geometry_state:
            return False, "No project loaded."

        solid_name_sugg = solid_params['name']
        solid_type = solid_params['type']
        
        new_solid_dict = None
        solid_error = None

        # --- 1. Add the Solid (dispatch based on type) ---
        if solid_type == 'boolean':
            recipe = solid_params['recipe']
            new_solid_dict, solid_error = self.add_boolean_solid(solid_name_sugg, recipe)
        else:
            solid_raw_params = solid_params['params']
            new_solid_dict, solid_error = self.add_solid(solid_name_sugg, solid_type, solid_raw_params)
        
        if solid_error:
            return False, f"Failed to create solid: {solid_error}"
        
        new_solid_name = new_solid_dict['name']

        # --- 2. Add the Logical Volume (if requested) ---
        if not lv_params:
            
            # Capture the new state
            self._capture_history_state(f"Added solid {new_solid_name}, no LV or PV")

            self.recalculate_geometry_state() # Recalculate just before returning
            return True, None
            
        lv_name_sugg = lv_params.get('name', f"{new_solid_name}_lv")
        material_ref = lv_params.get('material_ref')

        new_lv_dict, lv_error = self.add_logical_volume(lv_name_sugg, new_solid_name, material_ref)
        if lv_error:
            return False, f"Failed to create logical volume: {lv_error}"
            
        new_lv_name = new_lv_dict['name']

        # --- 3. Add the Physical Volume Placement (if requested) ---
        if not pv_params:

            # Capture the new state
            self._capture_history_state(f"Added solid {new_solid_name} and LV {new_lv_name}, no PV")

            self.recalculate_geometry_state()
            return True, None
            
        parent_lv_name = pv_params.get('parent_lv_name')
        if not parent_lv_name:
             return False, "Parent logical volume for placement was not specified."
        
        pv_name_sugg = pv_params.get('name', f"{new_lv_name}_PV")
        position = {'x': '0', 'y': '0', 'z': '0'} 
        rotation = {'x': '0', 'y': '0', 'z': '0'}
        scale    = {'x': '1', 'y': '1', 'z': '1'}

        new_pv_dict, pv_error = self.add_physical_volume(parent_lv_name, pv_name_sugg, new_lv_name, position, rotation, scale)
        if pv_error:
            return False, f"Failed to place physical volume: {pv_error}"
        
        new_pv_name = new_pv_dict['name']
        
        # Capture the new state
        self._capture_history_state(f"Added solid {new_solid_name}, LV {new_lv_name}, PV {new_pv_name}")
        
        self.recalculate_geometry_state()
        return True, None

    def add_logical_volume(self, name_suggestion, solid_ref, material_ref, 
                           vis_attributes=None, is_sensitive=False,
                           content_type='physvol', content=None):
        
        if not self.current_geometry_state: return None, "No project loaded"
        if solid_ref not in self.current_geometry_state.solids:
            return None, f"Solid '{solid_ref}' not found."
        if material_ref not in self.current_geometry_state.materials:
            return None, f"Material '{material_ref}' not found."

        name = self._generate_unique_name(name_suggestion, self.current_geometry_state.logical_volumes)
        new_lv = LogicalVolume(name, solid_ref, material_ref, vis_attributes, is_sensitive)

        new_lv.content_type = content_type
        if content_type == 'replica':
            new_lv.content = ReplicaVolume.from_dict(content)
        elif content_type == 'division':
            new_lv.content = DivisionVolume.from_dict(content)
        else: # physvol
            new_lv.content = [] # It's a new, empty standard LV

        self.current_geometry_state.add_logical_volume(new_lv)
        self.recalculate_geometry_state()

        # Capture the new state
        self._capture_history_state(f"Added LV {name}")

        return new_lv.to_dict(), None        

    def update_logical_volume(self, lv_name, new_solid_ref, new_material_ref, 
                              new_vis_attributes=None, new_is_sensitive=None,
                              new_content_type=None, new_content=None):
        if not self.current_geometry_state: return False, "No project loaded"
        
        lv = self.current_geometry_state.logical_volumes.get(lv_name)
        if not lv:
            return False, f"Logical Volume '{lv_name}' not found."

        # Update standard properties if provided
        if new_solid_ref and new_solid_ref in self.current_geometry_state.solids:
            lv.solid_ref = new_solid_ref
        if new_material_ref and new_material_ref in self.current_geometry_state.materials:
            lv.material_ref = new_material_ref
        if new_vis_attributes is not None:
            lv.vis_attributes = new_vis_attributes
        if new_is_sensitive is not None:
            lv.is_sensitive = new_is_sensitive
            
        # Update content if provided
        if new_content_type and new_content is not None and len(new_content) > 0:
            print(f"Got new content {new_content}")
            lv.content_type = new_content_type
            if new_content_type == 'replica':
                lv.content = ReplicaVolume.from_dict(new_content)
            elif new_content_type == 'division':
                lv.content = DivisionVolume.from_dict(new_content)
            elif new_content_type == 'parameterised':
                lv.content = ParamVolume.from_dict(new_content)
            else: # physvol
                # This could be more complex, might need to update existing children
                lv.content = [] 

        # Capture the new state
        self._capture_history_state(f"Updated LV {lv_name}")
        
        self.recalculate_geometry_state()
        return True, None

    def add_physical_volume(self, parent_lv_name, pv_name_suggestion, placed_lv_ref, position, rotation, scale):
        if not self.current_geometry_state: return None, "No project loaded"
        
        state = self.current_geometry_state

        # Find the parent LV
        parent_lv = state.logical_volumes.get(parent_lv_name)
        if not parent_lv:
            return None, f"Parent Logical Volume '{parent_lv_name}' not found."
        
        # A placed reference can be either a Logical Volume OR an Assembly.
        is_lv = placed_lv_ref in state.logical_volumes
        is_assembly = placed_lv_ref in state.assemblies
        if not is_lv and not is_assembly:
            return None, f"Placed Volume or Assembly '{placed_lv_ref}' not found."

        # Generate a unique name for this PV *within its parent* (GDML PV names are not global)
        # For simplicity, we'll use a globally unique suggested name for now.
        # A better approach for pv_name would be to ensure it's unique among siblings.
        pv_name = pv_name_suggestion or f"{placed_lv_ref}_placement"

        # position_dict and rotation_dict are assumed to be {'x':val,...} in internal units
        new_pv = PhysicalVolumePlacement(pv_name, placed_lv_ref,
                                        parent_lv_name=parent_lv_name,
                                        position_val_or_ref=position,
                                        rotation_val_or_ref=rotation,
                                        scale_val_or_ref=scale)
        parent_lv.add_child(new_pv)
        
        # Capture the new state
        self._capture_history_state(f"Added PV {pv_name}")

        self.recalculate_geometry_state()
        return new_pv.to_dict(), None

    def update_physical_volume(self, pv_id, new_name, new_position, new_rotation, new_scale):
        if not self.current_geometry_state: return False, "No project loaded"
        
        # Create an updates list of a single element.
        update = [{
                    "id": pv_id,
                    "name": new_name,
                    "position": new_position,
                    "rotation": new_rotation,
                    "scale": new_scale
                 }]
        
        # Call the batched update function.
        return self.update_physical_volume_batch(update)
    
    def _update_single_pv(self, pv_id, new_name, new_position, new_rotation, new_scale):
        pv_to_update = None

        # Search through all logical volumes and their new 'content' list
        all_lvs = list(self.current_geometry_state.logical_volumes.values())
        for lv in all_lvs:
            if lv.content_type == 'physvol':
                for pv in lv.content:
                    if pv.id == pv_id:
                        pv_to_update = pv
                        break
            if pv_to_update:
                break
        
        # Also search assemblies
        if not pv_to_update:
            all_asms = list(self.current_geometry_state.assemblies.values())
            for asm in all_asms:
                for pv in asm.placements:
                    if pv.id == pv_id:
                        pv_to_update = pv
                        break
                if pv_to_update:
                    break
        
        if not pv_to_update:
            return None
            
        if new_name is not None: pv_to_update.name = new_name
        if new_position is not None: pv_to_update.position = new_position
        if new_rotation is not None: pv_to_update.rotation = new_rotation
        if new_scale is not None: pv_to_update.scale = new_scale

        return pv_to_update
    
    def update_physical_volume_batch(self, updates_list):
        """
        Updates a batch of physical volumes' transforms in a single transaction.
        updates_list: A list of dictionaries, each with 'id', 'name', 'position', 'rotation', 'scale'.
        """
        if not self.current_geometry_state:
            return False, "No project loaded."
        
        updated_pv_objects = []
        
        try:
            # Apply all updates.
            for update_data in updates_list:
                pv_id = update_data.get('id')
                if not pv_id: continue

                new_name = update_data.get('name')
                new_position = update_data.get('position')
                new_rotation = update_data.get('rotation')
                new_scale = update_data.get('scale')

                updated_pv = self._update_single_pv(pv_id, new_name, new_position, new_rotation, new_scale)
                updated_pv_objects.append(updated_pv)
                
            # After all updates are applied, recalculate the entire state
            success, error_msg = self.recalculate_geometry_state()
            if not success:
                return False, error_msg

            # --- Sync Bound Sources ---
            # If any PV is moved, it might be a parent/ancestor of a bound volume (e.g. Assembly placement).
            # To ensure consistency, we update ALL bound sources.
            # This is computationally cheap enough (usually < 100 sources) and guarantees correctness without complex tree traversal checks.
            sources_updated = []
            for source in self.current_geometry_state.sources.values():
                if source.volume_link_id:
                    pv = self._find_pv_by_id(source.volume_link_id)
                    if pv:
                        # 1. Update Transform (Global)
                        global_pos, global_rot_rad = self._calculate_global_transform(pv)
                        
                        # Check if it actually changed to avoid unnecessary history spam? 
                        # (Actually, we are in a batch update, so we just append to the patch).
                        
                        source.position = {
                            'x': str(global_pos['x']), 'y': str(global_pos['y']), 'z': str(global_pos['z'])
                        }
                        source.rotation = {
                            'x': str(global_rot_rad['x']), 'y': str(global_rot_rad['y']), 'z': str(global_rot_rad['z'])
                        }
                        
                        # 2. Update Shape Parameters
                        lv = self.current_geometry_state.logical_volumes.get(pv.volume_ref)
                        if lv:
                            solid = self.current_geometry_state.solids.get(lv.solid_ref)
                            if solid:
                                p = solid._evaluated_parameters
                                cmds = source.gps_commands
                            # SAFETY MARGIN: Confinement requires generated points to be strictly INSIDE.
                            # We reduce the source dimensions slightly to stand clear of the boundary.
                            MARGIN = 0.001 # mm
                            
                            if solid.type in ['box']:
                                    cmds['pos/shape'] = 'Box'
                                    cmds['pos/halfx'] = f"{max(0, p.get('x', 0)/2 - MARGIN)} mm"
                                    cmds['pos/halfy'] = f"{max(0, p.get('y', 0)/2 - MARGIN)} mm"
                                    cmds['pos/halfz'] = f"{max(0, p.get('z', 0)/2 - MARGIN)} mm"
                            elif solid.type in ['tube', 'cylinder', 'tubs']:
                                    cmds['pos/shape'] = 'Cylinder'
                                    cmds['pos/radius'] = f"{max(0, p.get('rmax', 0) - MARGIN)} mm"
                                    cmds['pos/halfz'] = f"{max(0, p.get('z', 0)/2 - MARGIN)} mm"
                            elif solid.type in ['sphere', 'orb']:
                                    cmds['pos/shape'] = 'Sphere'
                                    cmds['pos/radius'] = f"{max(0, p.get('rmax', 0) - MARGIN)} mm"
                            else:
                                    cmds['pos/shape'] = 'Sphere'
                                    cmds['pos/radius'] = '50 mm'

                        # Update evaluated position for scene
                        source._evaluated_position = global_pos
                        source._evaluated_rotation = global_rot_rad
                        
                        sources_updated.append(source)

        except Exception as e:
            return False, None
        
        # --- Return the patch data  ---
        # (For now, do not attempt to patch the scene, as one transformation may affect several PVs
        #  and this is not yet accounted for.)
        # scene_patch = {
        #     "updated_transforms": [
        #         {
        #             "id": pv.id, # Ensure we use the object's ID
        #             "position": pv._evaluated_position,
        #             "rotation": pv._evaluated_rotation,
        #             "scale": pv._evaluated_scale
        #         } for pv in updated_pv_objects
        #     ]
        # }

        # This part is for updating the local data model (AppState)
        project_state_patch = {
            "updated": {
                # We need to send the full PV object so the frontend can replace it
                "physical_volumes": {pv.id: pv.to_dict() for pv in updated_pv_objects},
                # Also send updated sources
                "sources": {s.id: s.to_dict() for s in sources_updated}
            }
        }
        
        # If everything succeeded, capture the final state and return
        self._capture_history_state(f"Batch update to {len(updated_pv_objects)} PVs")
        return True, project_state_patch

    def add_assembly(self, name_suggestion, placements_data):
        if not self.current_geometry_state:
            return None, "No project loaded"
        
        name = self._generate_unique_name(name_suggestion, self.current_geometry_state.assemblies)
        new_assembly = Assembly(name)
        
        # Convert placement dicts into PhysicalVolumePlacement objects
        placements = [PhysicalVolumePlacement.from_dict(p_data) for p_data in placements_data]
        new_assembly.placements = placements
        
        self.current_geometry_state.add_assembly(new_assembly)
        self.recalculate_geometry_state()

        # Capture the new state
        self._capture_history_state(f"Added assembly {name}")

        return new_assembly.to_dict(), None

    def update_assembly(self, assembly_name, new_placements_data):
        if not self.current_geometry_state:
            return False, "No project loaded"
        
        target_assembly = self.current_geometry_state.assemblies.get(assembly_name)
        if not target_assembly:
            return False, f"Assembly '{assembly_name}' not found."
            
        # Convert dicts to objects
        new_placements = [PhysicalVolumePlacement.from_dict(p_data) for p_data in new_placements_data]
        target_assembly.placements = new_placements

        success, error_msg = self.recalculate_geometry_state()

        # Capture the new state
        self._capture_history_state(f"Updated assembly {assembly_name}")

        return success, error_msg
    
    def add_particle_source(self, name_suggestion, gps_commands, position, rotation, activity=1.0, confine_to_pv=None):
        if not self.current_geometry_state:
            return None, "No project loaded"

        if confine_to_pv == "":
            confine_to_pv = None

        name = self._generate_unique_name(name_suggestion, self.current_geometry_state.sources)
        new_source = ParticleSource(name, gps_commands, position, rotation, activity=activity, confine_to_pv=confine_to_pv)
        self.current_geometry_state.add_source(new_source)
        self.recalculate_geometry_state()
        self._capture_history_state(f"Added particle source {name}")
        return new_source.to_dict(), None

    def update_source_transform(self, source_id, new_position, new_rotation):
        """Updates just the position of a source."""
        if not self.current_geometry_state:
            return False, "No project loaded"

        source_to_update = None
        for source in self.current_geometry_state.sources.values():
            if source.id == source_id:
                source_to_update = source
                break

        if not source_to_update:
            return False, f"Source with ID '{source_id}' not found."

        if new_position is not None:
            # The new position from the gizmo is already evaluated (floats)
            # We need to store it as strings in the 'raw' position dict
            source_to_update.position = {k: str(v) for k, v in new_position.items()}

        if new_rotation is not None:
            source_to_update.rotation = {k: str(v) for k, v in new_rotation.items()}

        self.recalculate_geometry_state()
        self._capture_history_state(f"Transformed source {source_to_update.name}")
        return True, None
    
    def delete_objects_batch(self, objects_to_delete):
        """
        Deletes a list of objects in a single transaction, after checking all dependencies first.
        objects_to_delete: A list of dictionaries, e.g., [{"type": "solid", "id": "my_box"}, ...]
        """
        if not self.current_geometry_state:
            return False, "No project loaded."
        
        # --- Do not allow deletion of world PV or LV ---
        world_lv = self.current_geometry_state.logical_volumes[self.current_geometry_state.world_volume_ref]
        for item in objects_to_delete:

            print(f"Deleting item {item} for world LV {world_lv}")
    
            # Prevent deletion of the designated World Logical Volume.
            if item.get('type') == 'logical_volume' and item.get('name') == world_lv.name:
                return False, f"Cannot delete the World Logical Volume ('{world_lv.name}'). To start over, use 'File -> New Project'."
            
            # Also prevent deletion of the World's physical placement (though it's not directly selectable yet).
            # This is good future-proofing.
            if item.get('type') == 'physical_volume':
                pv = self._find_pv_by_id(item.get('id'))
                if pv and pv.volume_ref == world_lv.name:
                     return False, f"Cannot delete the world volume's placement."
        
        # --- Pre-deletion Validation Phase ---
        all_dependencies = {}
        for item in objects_to_delete:
            obj_type = item.get('type')
            obj_id = item.get('id')

            # --- SKIP DEPENDENCY CHECK FOR SOURCES ---
            if obj_type == 'particle_source':
                continue
            
            # Find dependencies, but exclude dependencies that are also being deleted in this same batch.
            # This allows deleting an LV and the PV that contains it at the same time.
            dependencies = self._find_dependencies(obj_type, obj_id)
            
            # Filter out dependencies that are also scheduled for deletion in this batch.
            item_ids_being_deleted = {i['id'] for i in objects_to_delete}
            filtered_deps = []
            for dep_string in dependencies:
                is_also_being_deleted = False
                for del_id in item_ids_being_deleted:
                    # Create a regex to match the exact ID as a whole word,
                    # typically inside single quotes.
                    # Example: `f"'({re.escape(del_id)})'"` matches "'Box'" but not "'logBox'".
                    # We add word boundaries (\b) for extra safety.
                    pattern = r"\b" + re.escape(del_id) + r"\b"
                    if re.search(pattern, dep_string):
                        is_also_being_deleted = True
                        break # Found a match, no need to check other del_ids for this dependency
                
                if not is_also_being_deleted:
                    filtered_deps.append(dep_string)

            if filtered_deps:
                all_dependencies[f"{obj_type} '{obj_id}'"] = filtered_deps

        if all_dependencies:
            # Format a comprehensive error message
            error_msg = "Deletion failed. The following objects are still in use:\n"
            for obj, deps in all_dependencies.items():
                dep_list_str = "\n  - " + "\n  - ".join(deps)
                error_msg += f"\n• {obj} is used by:{dep_list_str}"
            return False, error_msg

        # --- Deletion Phase ---
        # If we passed validation, it's safe to delete everything.
        try:
            for item in objects_to_delete:
                # The internal _delete_single_object_no_checks is a new helper
                self._delete_single_object_no_checks(item['type'], item['id'])
        except Exception as e:
            # In case of an unexpected error, revert and report.
            # A more robust solution would be to restore from self._pre_transaction_state
            return False, str(e)
        
        # --- Finalization ---
        # No full geometry recalculation needed here for a simple delete.
        self._capture_history_state(f"Deleted {len(objects_to_delete)} objects")

        # --- Build the patch object for the response ---
        project_state_patch = {
            "deleted": {
                # Initialize with all types that can be deleted
                "solids": [], "logical_volumes": [], "physical_volumes": [],
                "materials": [], "elements": [], "isotopes": [], "defines": [],
                "assemblies": [], "optical_surfaces": [], "skin_surfaces": [], 
                "border_surfaces": [], "particle_sources": []
            }
        }
        for item in objects_to_delete:
            obj_type = item['type']
            obj_id = item['id']
            # Map frontend types to backend dictionary keys if they differ
            dict_key = ""
            if obj_type == "particle_source":
                dict_key = "particle_sources"
            elif obj_type == "assembly":
                dict_key = "assemblies"
            else:
                dict_key = f"{obj_type}s"
            if dict_key in project_state_patch["deleted"]:
                 project_state_patch["deleted"][dict_key].append(obj_id)

        # A deletion might affect the scene, so we should send a full scene update.
        scene_update = self.get_threejs_description()

        patch = {
            "project_state": project_state_patch,
            "scene_update": scene_update
        }
        
        return True, patch

    def _delete_single_object_no_checks(self, object_type, object_id):
        """
        Internal helper that performs the actual deletion from the state dictionaries.
        This function ASSUMES all dependency checks have already passed.
        """
        state = self.current_geometry_state
        deleted = False
        error_msg = None

        if object_type == "define":
            if object_id in state.defines:
                del state.defines[object_id]
                deleted = True
    
        elif object_type == "material":
            if object_id in state.materials:
                del state.materials[object_id]
                deleted = True
    
        elif object_type == "element":
            if object_id in state.elements:
                del state.elements[object_id]
                deleted = True
    
        elif object_type == "isotope":
            if object_id in state.isotopes:
                del state.isotopes[object_id]
                deleted = True
    
        elif object_type == "assembly":
            if object_id in state.assemblies:
                del state.assemblies[object_id]
                deleted = True
    
        elif object_type == "optical_surface":
            if object_id in state.optical_surfaces:
                del state.optical_surfaces[object_id]
                deleted = True
    
        elif object_type == "skin_surface":
            if object_id in state.skin_surfaces:
                del state.skin_surfaces[object_id]
                deleted = True
    
        elif object_type == "border_surface":
            if object_id in state.border_surfaces:
                del state.border_surfaces[object_id]
                deleted = True
    
        elif object_type == "solid":
            if object_id in state.solids:
                del state.solids[object_id]
                deleted = True
        
        elif object_type == "logical_volume":
            if object_id in state.logical_volumes:
                if state.world_volume_ref == object_id:
                    error_msg = "Cannot delete the world volume."
                else:
                    # Delete the LV itself
                    del state.logical_volumes[object_id]
                    
                    # Now, remove any placements that REFER to this deleted LV
                    for lv in state.logical_volumes.values():
                        if lv.content_type == 'physvol':
                            lv.content = [pv for pv in lv.content if pv.volume_ref != object_id]
                        elif lv.content and hasattr(lv.content, 'volume_ref') and lv.content.volume_ref == object_id:
                            # If a procedural volume was replicating the deleted LV, reset it.
                            # A more advanced implementation might delete the procedural LV entirely.
                            lv.content_type = 'physvol'
                            lv.content = []
                    deleted = True
        
        elif object_type == "physical_volume":
            # Iterate through all LVs and check their 'content' list for the PV to delete
            found_and_deleted = False
            for lv in state.logical_volumes.values():
                if lv.content_type == 'physvol':
                    original_len = len(lv.content)
                    # Filter the list, keeping only PVs that DON'T match the ID
                    lv.content = [pv for pv in lv.content if pv.id != object_id]
                    if len(lv.content) < original_len:
                        found_and_deleted = True
                        break # Found and deleted, no need to search further
            
            if found_and_deleted:
                deleted = True
            else:
                error_msg = "Physical Volume not found."

        elif object_type == "particle_source":
            source_to_delete = None
            for name, source in state.sources.items():
                if source.id == object_id:
                    source_to_delete = name
                    break
            if source_to_delete:
                del state.sources[source_to_delete]
                # If the deleted source was the active one, clear the active ID
                if object_id in state.active_source_ids:
                    state.active_source_ids.remove(object_id)
                deleted = True
        
        return deleted, error_msg if error_msg else f"Object {object_type} '{object_id}' not found or cannot be deleted."

    def _find_dependencies(self, object_type, object_id):
        """
        Finds all objects that reference a given object.
        Returns a list of strings describing the dependencies.
        """
        dependencies = []
        state = self.current_geometry_state
        if object_type == 'solid':
            # Check Logical Volumes
            for lv in state.logical_volumes.values():
                if lv.solid_ref == object_id:
                    dependencies.append(f"Logical Volume '{lv.name}'")
            # Check Boolean Solids
            for solid in state.solids.values():
                if solid.type == 'boolean':
                    for item in solid.raw_parameters.get('recipe', []):
                        if item.get('solid_ref') == object_id:
                            dependencies.append(f"Boolean Solid '{solid.name}'")
                            break # Only need to report once per solid

        elif object_type == 'material':
            # Check Logical Volumes
            for lv in state.logical_volumes.values():
                if lv.material_ref == object_id:
                    dependencies.append(f"Logical Volume '{lv.name}'")

        elif object_type == 'define':
            search_str = object_id
            
            # --- 1. Check for usage in other Defines ---
            for define_obj in state.defines.values():
                if define_obj.name == search_str: continue # Don't check against self
                
                # Check raw_expression, which can be a string or a dict
                raw_expr = define_obj.raw_expression
                if isinstance(raw_expr, str):
                    if re.search(r'\b' + re.escape(search_str) + r'\b', raw_expr):
                        dependencies.append(f"Define '{define_obj.name}'")
                elif isinstance(raw_expr, dict):
                    for val in raw_expr.values():
                        if isinstance(val, str) and re.search(r'\b' + re.escape(search_str) + r'\b', val):
                            dependencies.append(f"Define '{define_obj.name}'")
                            break # Found in this dict, no need to check other keys

            # --- 2. Check for usage in Solids ---
            for solid in state.solids.values():
                is_found_in_solid = False
                for key, val in solid.raw_parameters.items():
                    if isinstance(val, str) and re.search(r'\b' + re.escape(search_str) + r'\b', val):
                        dependencies.append(f"Solid '{solid.name}' (parameter '{key}')")
                        is_found_in_solid = True
                        break # Only report once per solid
                    elif isinstance(val, dict): # For nested structures like boolean transforms
                        for sub_val in val.values():
                            if isinstance(sub_val, str) and re.search(r'\b' + re.escape(search_str) + r'\b', sub_val):
                                dependencies.append(f"Solid '{solid.name}' (parameter '{key}')")
                                is_found_in_solid = True
                                break
                    if is_found_in_solid: break
                if is_found_in_solid: continue
                # Also check boolean recipes
                if solid.type == 'boolean':
                    for item in solid.raw_parameters.get('recipe', []):
                        transform = item.get('transform', {})
                        if transform:
                            pos = transform.get('position', {})
                            rot = transform.get('rotation', {})
                            if (isinstance(pos, str) and pos == search_str) or \
                               (isinstance(rot, str) and rot == search_str):
                                dependencies.append(f"Solid '{solid.name}' (transform reference)")
                                break

            # --- 3. Check for usage in all Placements (Standard, Assembly, Procedural) ---
            all_lvs = list(state.logical_volumes.values())
            all_asms = list(state.assemblies.values())
            
            # Standard LV placements
            for lv in all_lvs:
                if lv.content_type == 'physvol':
                    for pv in lv.content:
                        if pv.position == search_str: dependencies.append(f"Placement '{pv.name}' (position)")
                        if pv.rotation == search_str: dependencies.append(f"Placement '{pv.name}' (rotation)")
                        if pv.scale == search_str: dependencies.append(f"Placement '{pv.name}' (scale)")
            
            # Assembly placements
            for asm in all_asms:
                for pv in asm.placements:
                    if pv.position == search_str: dependencies.append(f"Placement '{pv.name}' (position)")
                    if pv.rotation == search_str: dependencies.append(f"Placement '{pv.name}' (rotation)")
                    if pv.scale == search_str: dependencies.append(f"Placement '{pv.name}' (scale)")

            # --- 4. Check for usage in Procedural Volume parameters ---
            for lv in all_lvs:
                if lv.content_type in ['replica', 'division', 'parameterised']:
                    proc_obj = lv.content
                    # Check number/ncopies, width, offset
                    for attr in ['number', 'width', 'offset', 'ncopies']:
                        if hasattr(proc_obj, attr):
                            attr_val = getattr(proc_obj, attr)
                            if isinstance(attr_val, str) and re.search(r'\b' + re.escape(search_str) + r'\b', attr_val):
                                dependencies.append(f"Procedural Volume in '{lv.name}' (parameter '{attr}')")
                                break
                    # Check parameterised volume dimensions
                    if hasattr(proc_obj, 'parameters'):
                        for param_set in proc_obj.parameters:
                            for dim_val in param_set.dimensions.values():
                                if isinstance(dim_val, str) and re.search(r'\b' + re.escape(search_str) + r'\b', dim_val):
                                    dependencies.append(f"Parameterised Volume in '{lv.name}' (dimensions)")
                                    break
                            if param_set.position == search_str:
                                dependencies.append(f"Parameterised Volume in '{lv.name}' (position ref)")
                            if param_set.rotation == search_str:
                                dependencies.append(f"Parameterised Volume in '{lv.name}' (rotation ref)")

            # --- 5. Check for usage in Optical/Skin/Border Surfaces ---
            for surf in state.optical_surfaces.values():
                for key, val in surf.properties.items():
                    if val == search_str:
                        dependencies.append(f"Optical Surface '{surf.name}' (property '{key}')")

        elif object_type == 'logical_volume':
            # Check for placements in other LVs
            for lv in state.logical_volumes.values():
                if lv.content_type == 'physvol':
                    for pv in lv.content:
                        if pv.volume_ref == object_id:
                            dependencies.append(f"Placement '{pv.name}' in Logical Volume '{lv.name}'")
            # Check for placements in Assemblies
            for asm in state.assemblies.values():
                for pv in asm.placements:
                    if pv.volume_ref == object_id:
                        dependencies.append(f"Placement '{pv.name}' in Assembly '{asm.name}'")
            # Check for skin surfaces
            for skin in state.skin_surfaces.values():
                if skin.volume_ref == object_id:
                    dependencies.append(f"Skin Surface '{skin.name}'")

        elif object_type == 'assembly':
            # Check for placements in other LVs
            for lv in state.logical_volumes.values():
                if lv.content_type == 'physvol':
                    for pv in lv.content:
                        if pv.volume_ref == object_id:
                            dependencies.append(f"Placement '{pv.name}' in Logical Volume '{lv.name}'")
            # Check for placements in other Assemblies (nested assemblies)
            for asm in state.assemblies.values():
                for pv in asm.placements:
                    if pv.volume_ref == object_id:
                        dependencies.append(f"Placement '{pv.name}' in Assembly '{asm.name}'")

        # Add more checks for elements, isotopes, optical_surfaces etc. as needed.
        return sorted(list(set(dependencies)))

    def merge_from_state(self, incoming_state: GeometryState):
        """
        Merges defines, materials, solids, and LVs from an incoming state
        into the current project, handling name conflicts by renaming.
        """
        if not self.current_geometry_state:
            self.current_geometry_state = incoming_state
            # Even if it's a fresh state, it might have placements to add
            if hasattr(incoming_state, 'placements_to_add'):
                for pv_to_add in incoming_state.placements_to_add:
                    parent_lv = self.current_geometry_state.logical_volumes.get(pv_to_add.parent_lv_name)
                    if parent_lv:
                        parent_lv.add_child(pv_to_add)
                    else:
                        print(f"Warning: Could not find parent LV '{pv_to_add.parent_lv_name}' for initial placement.")
            return True, None

        rename_map = {} # Tracks old_name -> new_name

        # --- Merge Defines ---
        for name, define in incoming_state.defines.items():
            new_name = self._generate_unique_name(name, self.current_geometry_state.defines)
            if new_name != name:
                rename_map[name] = new_name
            define.name = new_name
            self.current_geometry_state.add_define(define)

        # --- Merge Materials ---
        for name, material in incoming_state.materials.items():
            # Update component references if their names were changed
            if material.components:
                for comp in material.components:
                    if comp['ref'] in rename_map:
                        comp['ref'] = rename_map[comp['ref']]
            
            new_name = self._generate_unique_name(name, self.current_geometry_state.materials)
            if new_name != name:
                rename_map[name] = new_name
            material.name = new_name
            self.current_geometry_state.add_material(material)

        # --- Merge Solids ---
        for name, solid in incoming_state.solids.items():
            # Update solid references within booleans
            if solid.type in ['boolean', 'union', 'subtraction', 'intersection']:
                if solid.type == 'boolean': # New virtual boolean
                    for item in solid.raw_parameters.get('recipe', []):
                        if item['solid_ref'] in rename_map:
                            item['solid_ref'] = rename_map[item['solid_ref']]
                else: # Old style boolean
                    if solid.raw_parameters['first_ref'] in rename_map:
                        solid.raw_parameters['first_ref'] = rename_map[solid.raw_parameters['first_ref']]
                    if solid.raw_parameters['second_ref'] in rename_map:
                        solid.raw_parameters['second_ref'] = rename_map[solid.raw_parameters['second_ref']]

            new_name = self._generate_unique_name(name, self.current_geometry_state.solids)
            if new_name != name:
                rename_map[name] = new_name
            solid.name = new_name
            self.current_geometry_state.add_solid(solid)

        # --- Merge Logical Volumes ---
        processed_lvs = []
        extra_placements = []
        for name, lv in incoming_state.logical_volumes.items():
            # Ignore the incoming world volume BUT capture its placements
            if name == incoming_state.world_volume_ref:
                # Map old world to current world so children can find their new parent
                rename_map[name] = self.current_geometry_state.world_volume_ref
                
                # Extract content to be added as placements
                if lv.content_type == 'physvol' and isinstance(lv.content, list):
                     for pv in lv.content:
                         # Clone via serialization to be safe
                         pv_clone = PhysicalVolumePlacement.from_dict(pv.to_dict())
                         # Explicitly re-parent them to the current world volume
                         pv_clone.parent_lv_name = self.current_geometry_state.world_volume_ref
                         extra_placements.append(pv_clone)
                continue

            # Update references within this LV
            if lv.solid_ref in rename_map: lv.solid_ref = rename_map[lv.solid_ref]
            if lv.material_ref in rename_map: lv.material_ref = rename_map[lv.material_ref]
            
            # Note: We are preserving internal placements (sub-assemblies).
            # We will fix up their references in a second pass.

            new_name = self._generate_unique_name(name, self.current_geometry_state.logical_volumes)
            if new_name != name:
                rename_map[name] = new_name
            lv.name = new_name
            
            self.current_geometry_state.add_logical_volume(lv)
            processed_lvs.append(lv)

        # --- Post-Process LV Content (Fix references in children) ---
        for lv in processed_lvs:
            if lv.content_type == 'physvol' and isinstance(lv.content, list):
                for pv in lv.content:
                    # Update reference to the child volume (if it was renamed)
                    if pv.volume_ref in rename_map:
                        pv.volume_ref = rename_map[pv.volume_ref]
                    
                    # Update reference to the parent volume (this LV, which might have been renamed)
                    pv.parent_lv_name = lv.name 
                    
                    # Update defines in positioning
                    if isinstance(pv.position, str) and pv.position in rename_map:
                         pv.position = rename_map[pv.position]
                    if isinstance(pv.rotation, str) and pv.rotation in rename_map:
                         pv.rotation = rename_map[pv.rotation]
        
        # --- Merge Assemblies ---
        for name, assembly in incoming_state.assemblies.items():
            # Update all references within the assembly's placements
            for pv in assembly.placements:
                if pv.volume_ref in rename_map:
                    pv.volume_ref = rename_map[pv.volume_ref]
                if isinstance(pv.position, str) and pv.position in rename_map:
                    pv.position = rename_map[pv.position]
                if isinstance(pv.rotation, str) and pv.rotation in rename_map:
                    pv.rotation = rename_map[pv.rotation]
            
            new_name = self._generate_unique_name(name, self.current_geometry_state.assemblies)
            if new_name != name:
                rename_map[name] = new_name
            assembly.name = new_name
            self.current_geometry_state.add_assembly(assembly)

        # --- Merge Sources ---
        for name, source in incoming_state.sources.items():
            old_id = source.id
            
            # Generate new unique name
            new_name = self._generate_unique_name(name, self.current_geometry_state.sources)
            if new_name != name:
                rename_map[name] = new_name
            source.name = new_name
            
            # Generate new ID to avoid collisions (especially on re-import)
            import uuid
            new_id = str(uuid.uuid4())
            source.id = new_id
            
            self.current_geometry_state.add_source(source)
            
            # If this source was active in the incoming state, activate it in the current state
            if old_id in incoming_state.active_source_ids:
                self.current_geometry_state.active_source_ids.append(new_id)

        # --- Process and Add Placements ---
        # Combine explicitly requested placements with those extracted from the incoming world
        all_placements_to_add = (getattr(incoming_state, 'placements_to_add', []) or []) + extra_placements
        
        if all_placements_to_add:
            for pv_to_add in all_placements_to_add:
                # 1. Update any renamed references within the placement object
                if pv_to_add.parent_lv_name in rename_map:
                    pv_to_add.parent_lv_name = rename_map[pv_to_add.parent_lv_name]
                
                if pv_to_add.volume_ref in rename_map:
                    pv_to_add.volume_ref = rename_map[pv_to_add.volume_ref]
                
                if isinstance(pv_to_add.position, str) and pv_to_add.position in rename_map:
                    pv_to_add.position = rename_map[pv_to_add.position]
                
                if isinstance(pv_to_add.rotation, str) and pv_to_add.rotation in rename_map:
                    pv_to_add.rotation = rename_map[pv_to_add.rotation]

                # 2. Find the parent LV in the *main* project state
                parent_lv = self.current_geometry_state.logical_volumes.get(pv_to_add.parent_lv_name)

                if parent_lv:
                    if parent_lv.content_type == 'physvol':
                        # Generate a unique name for the placement within its new parent
                        existing_names = {pv.name for pv in parent_lv.content}
                        base_name = pv_to_add.name
                        i = 1
                        while pv_to_add.name in existing_names:
                            pv_to_add.name = f"{base_name}_{i}"
                            i += 1

                        parent_lv.add_child(pv_to_add)
                    else:
                        print(f"Warning: Cannot add placement '{pv_to_add.name}'. Parent LV '{parent_lv.name}' is procedural.")
                else:
                    print(f"Warning: Could not find parent LV '{pv_to_add.parent_lv_name}' for imported placement '{pv_to_add.name}'. Skipping.")
        
        # --- Auto-Grouping Logic ---
        if hasattr(incoming_state, 'grouping_name'):
             grouping_name = incoming_state.grouping_name
             
             # Group Solids
             new_solid_names = [s.name for s in incoming_state.solids.values()]
             if new_solid_names:
                 self.create_group('solid', f"{grouping_name}_solids")
                 self.move_items_to_group('solid', new_solid_names, f"{grouping_name}_solids")

             # Group Logical Volumes
             new_lv_names = [lv.name for lv in incoming_state.logical_volumes.values()]
             if new_lv_names:
                 self.create_group('logical_volume', f"{grouping_name}_lvs")
                 self.move_items_to_group('logical_volume', new_lv_names, f"{grouping_name}_lvs")

             # Group Assembly (if created)
             new_asm_names = [asm.name for asm in incoming_state.assemblies.values()]
             if new_asm_names:
                 self.create_group('assembly', f"{grouping_name}_assemblies")
                 self.move_items_to_group('assembly', new_asm_names, f"{grouping_name}_assemblies")

        # Recalculate the state
        success, error_msg = self.recalculate_geometry_state()

        # RE-SYNC ALL BOUND SOURCES (Crucial for imported parts)
        # Imported bound sources may have outdated shape parameters or positions relative to the new World.
        for source in self.current_geometry_state.sources.values():
            if source.volume_link_id:
                pv = self._find_pv_by_id(source.volume_link_id)
                if pv:
                    # 1. Update Transform (Global)
                    global_pos, global_rot_rad = self._calculate_global_transform(pv)
                    
                    source.position = {
                        'x': str(global_pos['x']), 'y': str(global_pos['y']), 'z': str(global_pos['z'])
                    }
                    source.rotation = {
                        'x': str(global_rot_rad['x']), 'y': str(global_rot_rad['y']), 'z': str(global_rot_rad['z'])
                    }
                    
                    # 2. Update Shape Parameters
                    lv = self.current_geometry_state.logical_volumes.get(pv.volume_ref)
                    if lv:
                        solid = self.current_geometry_state.solids.get(lv.solid_ref)
                        if solid:
                            p = solid._evaluated_parameters
                            cmds = source.gps_commands
                            cmds['pos/type'] = 'Volume'
                            
                            # SAFETY MARGIN: Confinement requires generated points to be strictly INSIDE.
                            # We reduce the source dimensions slightly to stand clear of the boundary.
                            MARGIN = 0.001 # mm
                            
                            if solid.type in ['box']:
                                cmds['pos/shape'] = 'Box'
                                cmds['pos/halfx'] = f"{max(0, p.get('x', 0)/2 - MARGIN)} mm"
                                cmds['pos/halfy'] = f"{max(0, p.get('y', 0)/2 - MARGIN)} mm"
                                cmds['pos/halfz'] = f"{max(0, p.get('z', 0)/2 - MARGIN)} mm"
                            elif solid.type in ['tube', 'cylinder', 'tubs']:
                                cmds['pos/shape'] = 'Cylinder'
                                cmds['pos/radius'] = f"{max(0, p.get('rmax', 0) - MARGIN)} mm"
                                cmds['pos/halfz'] = f"{max(0, p.get('z', 0)/2 - MARGIN)} mm"
                            elif solid.type in ['sphere', 'orb']:
                                cmds['pos/shape'] = 'Sphere'
                                cmds['pos/radius'] = f"{max(0, p.get('rmax', 0) - MARGIN)} mm"
                            else:
                                cmds['pos/shape'] = 'Sphere'
                                cmds['pos/radius'] = '50 mm'

                    source._evaluated_position = global_pos
                    source._evaluated_rotation = global_rot_rad

        # Capture the new state
        self._capture_history_state(f"State merge")

        return success, error_msg

    def _evaluate_vector_expression(self, expr_data, default_dict=None):
        """
        Evaluates a vector-like expression which can be a define reference (string)
        or a dictionary of expression strings.
        """
        if default_dict is None:
            default_dict = {'x': 0.0, 'y': 0.0, 'z': 0.0}

        if isinstance(expr_data, str):
            # It's a reference to a define
            success, value = self.expression_evaluator.evaluate(expr_data)
            if success and isinstance(value, dict):
                return value
            else:
                raise ValueError(f"Define '{expr_data}' did not resolve to a valid dictionary.")
        elif isinstance(expr_data, dict):
            evaluated_dict = {}
            for axis, raw_expr in expr_data.items():
                success, value = self.expression_evaluator.evaluate(str(raw_expr))
                if success:
                    evaluated_dict[axis] = value
                else:
                    raise ValueError(f"Failed to evaluate expression '{raw_expr}' for axis '{axis}'.")
            return evaluated_dict
        else:
            return default_dict
        
    def create_detector_ring(self, parent_lv_name, lv_to_place_ref, ring_name,
                             num_detectors, radius, center, orientation,
                             point_to_center, inward_axis,
                             num_rings=1, ring_spacing=0.0):
        """
        Creates a ring or cylinder of individual physical volumes.
        This method calculates the absolute world transform for each PV.
        """
        if not self.current_geometry_state:
            return None, "No project loaded"

        try:
            # --- Evaluate all expression-capable arguments ---
            success_radius, evaluated_radius = self.expression_evaluator.evaluate(str(radius))
            if not success_radius: raise ValueError(f"Could not evaluate radius expression: '{radius}'")

            success_num_det, evaluated_num_detectors = self.expression_evaluator.evaluate(str(num_detectors))
            if not success_num_det: raise ValueError(f"Could not evaluate num_detectors: '{num_detectors}'")
            evaluated_num_detectors = int(evaluated_num_detectors)

            success_num_rings, evaluated_num_rings = self.expression_evaluator.evaluate(str(num_rings))
            if not success_num_rings: raise ValueError(f"Could not evaluate num_rings: '{num_rings}'")
            evaluated_num_rings = int(evaluated_num_rings)

            success_spacing, evaluated_ring_spacing = self.expression_evaluator.evaluate(str(ring_spacing))
            if not success_spacing: raise ValueError(f"Could not evaluate ring_spacing: '{ring_spacing}'")

            evaluated_center = self._evaluate_vector_expression(center, {'x': 0.0, 'y': 0.0, 'z': 0.0})
            evaluated_orientation = self._evaluate_vector_expression(orientation, {'x': 0.0, 'y': 0.0, 'z': 0.0})

        except (ValueError, TypeError) as e:
            return None, f"Error evaluating tool arguments: {e}"

        state = self.current_geometry_state
        parent_lv = state.logical_volumes.get(parent_lv_name)
        if not parent_lv:
            return None, f"Parent Logical Volume '{parent_lv_name}' not found."
        if parent_lv.content_type != 'physvol':
            return None, f"Parent LV '{parent_lv_name}' is procedural and cannot contain new placements."

        # --- Main Transformation for the entire array ---
        # We use scipy's Rotation which uses intrinsic ZYX order for 'zyx'
        # This matches our convention for the evaluated values.
        global_rotation = R.from_euler('zyx', [evaluated_orientation['z'], evaluated_orientation['y'], evaluated_orientation['x']])
        global_center = np.array([evaluated_center['x'], evaluated_center['y'], evaluated_center['z']])

        total_height = (evaluated_num_rings - 1) * evaluated_ring_spacing
        start_z = -total_height / 2.0

        copy_number_counter = self._get_next_copy_number(parent_lv)

        placements_to_add = []

        for j in range(evaluated_num_rings):
            z_pos = start_z + j * evaluated_ring_spacing
            for i in range(evaluated_num_detectors):
                angle = 2 * math.pi * i / evaluated_num_detectors

                # 1. Position of the crystal in the local XY plane of the ring
                local_position = np.array([evaluated_radius * math.cos(angle),
                                           evaluated_radius * math.sin(angle),
                                           z_pos])

                # 2. Calculate the "look-at" rotation to point the crystal to the center, without roll
                if point_to_center:
                    # The vector from the crystal to the ring axis
                    z_new = -np.array([local_position[0], local_position[1], 0])
                    # Normalize, with a safe guard for the center crystal
                    norm = np.linalg.norm(z_new)
                    if norm > 1e-9:
                        z_new /= norm
                    else:
                        z_new = np.array([0, -1, 0]) # Fallback for a crystal at the origin

                    # The global "up" vector for the ring is its local Z-axis
                    up_vector = np.array([0, 0, 1])

                    # Create an orthonormal basis
                    x_new = np.cross(up_vector, z_new)
                    x_new /= np.linalg.norm(x_new)
                    y_new = np.cross(z_new, x_new)

                    # This matrix transforms from standard axes to the "look-at" axes
                    look_at_matrix = np.column_stack([x_new, y_new, z_new])
                    R_lookat = R.from_matrix(look_at_matrix)
                else:
                    R_lookat = R.identity()

                # 3. Calculate pre-rotation to align the desired crystal axis
                source_vector_map = {
                    '+x': R.from_euler('y', -90, degrees=True),
                    '-x': R.from_euler('y', 90, degrees=True),
                    '+y': R.from_euler('x', 90, degrees=True),
                    '-y': R.from_euler('x', -90, degrees=True),
                    '+z': R.identity(),
                    '-z': R.from_euler('y', 180, degrees=True)
                }
                R_pre_rot = source_vector_map.get(inward_axis, R.identity())

                # 4. Combine rotations: global orientation -> local look-at -> pre-rotation
                final_rotation = global_rotation * R_lookat * R_pre_rot

                # 5. Transform local position to world position
                final_position = global_rotation.apply(local_position) + global_center

                # 6. Convert final rotation back to our negated ZYX Euler angles for storage
                final_euler_rad = final_rotation.as_euler('zyx', degrees=False)
                final_rotation_dict = {
                    'x': str(-final_euler_rad[2]),
                    'y': str(-final_euler_rad[1]),
                    'z': str(-final_euler_rad[0])
                }

                # Create the PhysicalVolumePlacement object for this detector
                pv = PhysicalVolumePlacement(
                    name=ring_name,  # All PVs share the same base name
                    volume_ref=lv_to_place_ref,
                    parent_lv_name=parent_lv_name,
                    copy_number_expr=str(copy_number_counter),
                    position_val_or_ref={'x': str(final_position[0]), 'y': str(final_position[1]), 'z': str(final_position[2])},
                    rotation_val_or_ref=final_rotation_dict
                )
                placements_to_add.append(pv)
                copy_number_counter += 1

        # Add all newly created placements to the parent logical volume
        parent_lv.content.extend(placements_to_add)

        self._capture_history_state(f"Created detector array '{ring_name}'")
        self.recalculate_geometry_state()

        # Returning the last created PV as a representative object, or None
        return placements_to_add[-1].to_dict() if placements_to_add else None, None
    
    def process_ai_response(self, ai_data: dict):
        """
        Processes a structured dictionary from the AI, creating new objects
        and applying updates like placements.
        """
        if not self.current_geometry_state:
            return False, "No project loaded."

        # print("RECEIVED AI DATA")
        # print(ai_data)

        # *** Recursively convert all rotation dictionaries ***
        self._recursively_convert_rotations(ai_data)

        # --- 1. Handle the 'creates' block ---
        # This block defines new, standalone items. We can merge them all at once.
        creation_data = ai_data.get("creates", {})
        if creation_data:
            temp_state = GeometryState.from_dict(creation_data)
            success, error_msg = self.merge_from_state(temp_state)
            if not success:
                return False, f"Failed to merge AI-defined objects: {error_msg}"
        
        # --- 2. Handle the 'updates' block ---
        # This block modifies existing objects, like placing volumes inside another.
        updates = ai_data.get("updates", [])
        if not isinstance(updates, list):
            return False, "AI response had an invalid 'updates' format (must be a list)."

        for update_task in updates:
            try:
                obj_type = update_task['object_type']
                obj_name = update_task['object_name']
                action = update_task['action']
                data = update_task['data']

                if obj_type == "logical_volume" and action == "append_physvol":
                    parent_lv = self.current_geometry_state.logical_volumes.get(obj_name)
                    if not parent_lv:
                        return False, f"Parent logical volume '{obj_name}' not found for placement."
                    
                    if parent_lv.content_type != 'physvol':
                         return False, f"Cannot add a physical volume to '{obj_name}' because it is procedurally defined as a '{parent_lv.content_type}'."

                    # The 'data' dictionary is a complete PhysicalVolumePlacement dictionary
                    new_pv = PhysicalVolumePlacement.from_dict(data)
                    parent_lv.add_child(new_pv)

                else:
                    # Placeholder for future actions like "update_property", "delete_item", etc.
                    print(f"Warning: AI requested unknown action '{action}' on '{obj_type}'. Ignoring.")

            except KeyError as e:
                return False, f"AI update data is missing a required key: {e}"
            except Exception as e:
                return False, f"An error occurred during AI update processing: {e}"

        # --- Handle tool calls ---
        tool_calls = ai_data.get("tool_calls", [])
        if not isinstance(tool_calls, list):
            return False, "AI response 'tool_calls' must be a list."

        for call in tool_calls:
            tool_name = call.get("tool_name")
            arguments = call.get("arguments", {})

            if tool_name == "create_detector_ring":
                try:
                    # The **arguments syntax unpacks the dictionary into keyword arguments
                    _, error_msg = self.create_detector_ring(**arguments)
                    if error_msg:
                        return False, f"Error executing tool '{tool_name}': {error_msg}"
                except TypeError as e:
                    return False, f"Mismatched arguments for tool '{tool_name}': {e}"
                except Exception as e:
                    return False, f"An unexpected error occurred during tool execution: {e}"
            else:
                return False, f"Unknown tool requested by AI: '{tool_name}'"
            
        # --- 3. Recalculate everything once at the end ---
        success, error_msg = self.recalculate_geometry_state()

        # Capture the new state
        self._capture_history_state(f"Incorporated AI response")

        return success, error_msg
    
    def _convert_ai_rotation_to_g4(self, rotation_dict):
        """
        Converts a standard intrinsic ZYX Euler rotation dictionary from the AI
        to the Geant4 extrinsic XYZ Euler rotation with negation.
        Geant4 extrinsic XYZ is equivalent to intrinsic ZYX with negated angles.
        """
        print(f"CONVERTING rotation",rotation_dict)
        if not isinstance(rotation_dict, dict):
            # This is likely a reference to a <define>, leave it as is.
            return rotation_dict

        # We are converting from what Three.js/graphics use (intrinsic ZYX)
        # to what Geant4 GDML uses (extrinsic XYZ). This happens to be
        # a simple negation of each angle.
        converted_rotation = {}
        for axis in ['x', 'y', 'z']:
            original_expr = rotation_dict.get(axis, '0').strip()
            # If the expression is just '0' or '0.0', no need to wrap it
            if original_expr in ['0', '0.0']:
                converted_rotation[axis] = "0"
            else:
                # Wrap the original expression in parentheses and prepend a minus sign
                converted_rotation[axis] = f"-({original_expr})"
        return converted_rotation
    
    def _recursively_convert_rotations(self, data):
        """Recursively traverses a dictionary or list to find and convert 'rotation' dictionaries."""
        if isinstance(data, dict):
            for key, value in data.items():
                if key == 'rotation' and value is not None:
                    data[key] = self._convert_ai_rotation_to_g4(value)
                else:
                    self._recursively_convert_rotations(value)
        elif isinstance(data, list):
            for item in data:
                self._recursively_convert_rotations(item)

    def import_step_with_options(self, step_file_stream, options):
        """
        Processes an uploaded STEP file using options, imports the geometry,
        and merges it into the current project.
        """
        # Save the stream to a temporary file to be read by the STEP parser
        with tempfile.NamedTemporaryFile(delete=False, suffix=".step") as temp_f:
            step_file_stream.save(temp_f.name)
            temp_path = temp_f.name
        
        try:
            # The STEP parser now takes the options dictionary
            imported_state = parse_step_file(temp_path, options)

            # Set the new solids as "changed" so they will be sent to the front end
            newly_created_solid_names = set(imported_state.solids.keys())
            self.changed_object_ids['solids'].update(newly_created_solid_names)
            print(f"Changed solids {self.changed_object_ids['solids']}")
            
            # The merge_from_state function already handles placements and grouping
            success, error_msg = self.merge_from_state(imported_state)
            
            if not success:
                return False, f"Failed to merge STEP geometry: {error_msg}"
            
            # Recalculate is handled inside merge_from_state, but an extra one ensures consistency.
            self.recalculate_geometry_state()
            
            # Capture this entire import as a single history event
            self._capture_history_state(f"Imported STEP file '{options.get('groupingName')}'")

            return True, None
            
        except Exception as e:
            # Ensure we raise the error to be caught by the app route
            raise e
        finally:
            # Clean up the temporary file
            os.unlink(temp_path)

    def create_group(self, group_type, group_name):
        """Creates a new, empty group for a specific object type."""
        if not self.current_geometry_state:
            return False, "No project loaded."
        if group_type not in self.current_geometry_state.ui_groups:
            return False, f"Invalid group type: {group_type}"
        
        # Check for name collision
        if any(g['name'] == group_name for g in self.current_geometry_state.ui_groups[group_type]):
            return False, f"A group named '{group_name}' already exists for {group_type}."
            
        self.current_geometry_state.ui_groups[group_type].append({
            "name": group_name,
            "members": []
        })
        
        # Capture the new state
        self._capture_history_state(f"Created {group_type} group {group_name}")

        return True, None

    def rename_group(self, group_type, old_name, new_name):
        """Renames an existing group."""
        if not self.current_geometry_state:
            return False, "No project loaded."
        if group_type not in self.current_geometry_state.ui_groups:
            return False, f"Invalid group type: {group_type}"
        
        groups = self.current_geometry_state.ui_groups[group_type]
        
        # Check if the new name is already taken (by a different group)
        if any(g['name'] == new_name for g in groups if g['name'] != old_name):
            return False, f"A group named '{new_name}' already exists."

        target_group = next((g for g in groups if g['name'] == old_name), None)
        if not target_group:
            return False, f"Group '{old_name}' not found."
            
        target_group['name'] = new_name

        # Capture the new state
        self._capture_history_state(f"Renamed {group_type} group {old_name} to {new_name}")

        return True, None

    def delete_group(self, group_type, group_name):
        """Deletes a group. Its members become ungrouped."""
        if not self.current_geometry_state:
            return False, "No project loaded."
        if group_type not in self.current_geometry_state.ui_groups:
            return False, f"Invalid group type: {group_type}"

        groups = self.current_geometry_state.ui_groups[group_type]
        
        group_to_delete = next((g for g in groups if g['name'] == group_name), None)
        if not group_to_delete:
            return False, f"Group '{group_name}' not found."
            
        self.current_geometry_state.ui_groups[group_type] = [g for g in groups if g['name'] != group_name]

        # Capture the new state
        self._capture_history_state(f"Deleted {group_type} group {group_name}")

        return True, None

    def move_items_to_group(self, group_type, item_ids, target_group_name):
        """Moves a list of items to a target group, removing them from any previous group."""
        if not self.current_geometry_state:
            return False, "No project loaded."
        if group_type not in self.current_geometry_state.ui_groups:
            return False, f"Invalid group type: {group_type}"

        groups = self.current_geometry_state.ui_groups[group_type]
        item_ids_set = set(item_ids)

        # 1. Remove items from their old groups
        for group in groups:
            group['members'] = [member_id for member_id in group['members'] if member_id not in item_ids_set]

        # 2. Add items to the new group (if a target group is specified)
        if target_group_name:
            target_group = next((g for g in groups if g['name'] == target_group_name), None)
            if not target_group:
                return False, f"Target group '{target_group_name}' not found."
            
            # Add only items that aren't already there to prevent duplicates
            for item_id in item_ids:
                if item_id not in target_group['members']:
                    target_group['members'].append(item_id)
        
        # Capture the new state
        self._capture_history_state(f"Moved items to {group_type} group {target_group_name}")

        # If target_group_name is None, the items are effectively moved to "ungrouped".
        return True, None

    def add_optical_surface(self, name_suggestion, params):
        """Adds a new optical surface to the project."""
        if not self.current_geometry_state:
            return None, "No project loaded"
        
        name = self._generate_unique_name(name_suggestion, self.current_geometry_state.optical_surfaces)
        
        new_surface = OpticalSurface(
            name=name,
            model=params.get('model'),
            finish=params.get('finish'),
            surf_type=params.get('surf_type'),
            value=params.get('value'),
        )
        new_surface.properties = params.get('properties', {})
        
        self.current_geometry_state.add_optical_surface(new_surface)
        self.recalculate_geometry_state() # Recalculate if any values are expressions

        # Capture the new state
        self._capture_history_state(f"Added optical surface {name}")
        
        return new_surface.to_dict(), None

    def update_optical_surface(self, surface_name, new_params):
        """Updates an existing optical surface."""
        if not self.current_geometry_state:
            return False, "No project loaded"
        
        target_surface = self.current_geometry_state.optical_surfaces.get(surface_name)
        if not target_surface:
            return False, f"Optical Surface '{surface_name}' not found."

        # Update attributes from the params dictionary
        target_surface.model = new_params.get('model', target_surface.model)
        target_surface.finish = new_params.get('finish', target_surface.finish)
        target_surface.type = new_params.get('surf_type', target_surface.type)
        target_surface.value = new_params.get('value', target_surface.value)
        target_surface.properties = new_params.get('properties', target_surface.properties)

        self.recalculate_geometry_state()

        # Capture the new state
        self._capture_history_state(f"Updated optical surface {surface_name}")

        return True, None

    def add_skin_surface(self, name_suggestion, volume_ref, surface_ref):
        """Adds a new skin surface link to the project."""
        if not self.current_geometry_state:
            return None, "No project loaded"
        
        state = self.current_geometry_state
        
        # Validate references
        if volume_ref not in state.logical_volumes:
            return None, f"Logical Volume '{volume_ref}' not found."
        if surface_ref not in state.optical_surfaces:
            return None, f"Optical Surface '{surface_ref}' not found."

        name = self._generate_unique_name(name_suggestion, state.skin_surfaces)
        
        new_skin_surface = SkinSurface(
            name=name,
            volume_ref=volume_ref,
            surfaceproperty_ref=surface_ref
        )
        
        state.add_skin_surface(new_skin_surface)
        # No recalculation is needed as this is just a link, but we'll do it for consistency.
        self.recalculate_geometry_state()

        # Capture the new state
        self._capture_history_state(f"Added skin surface {name}")
        
        return new_skin_surface.to_dict(), None

    def update_skin_surface(self, surface_name, new_volume_ref, new_surface_ref):
        """Updates an existing skin surface link."""
        if not self.current_geometry_state:
            return False, "No project loaded"
        
        state = self.current_geometry_state
        target_surface = state.skin_surfaces.get(surface_name)
        if not target_surface:
            return False, f"Skin Surface '{surface_name}' not found."

        # Validate new references before applying them
        if new_volume_ref not in state.logical_volumes:
            return False, f"New Logical Volume '{new_volume_ref}' not found."
        if new_surface_ref not in state.optical_surfaces:
            return False, f"New Optical Surface '{new_surface_ref}' not found."

        # Update attributes
        target_surface.volume_ref = new_volume_ref
        target_surface.surfaceproperty_ref = new_surface_ref

        self.recalculate_geometry_state()

        # Capture the new state
        self._capture_history_state(f"Updated skin surface {surface_name}")

        return True, None

    def _find_pv_by_id(self, pv_id):
        """Helper to find a PV object by its UUID across the entire geometry."""
        state = self.current_geometry_state
        # Search in Logical Volumes
        for lv in state.logical_volumes.values():
            if lv.content_type == 'physvol':
                for pv in lv.content:
                    if pv.id == pv_id:
                        return pv
        # Search in Assemblies
        for asm in state.assemblies.values():
            for pv in asm.placements:
                if pv.id == pv_id:
                    return pv
        return None

    def add_border_surface(self, name_suggestion, pv1_ref_id, pv2_ref_id, surface_ref):
        """Adds a new border surface link to the project."""
        if not self.current_geometry_state:
            return None, "No project loaded"
        
        state = self.current_geometry_state
        
        # Validate references
        if not self._find_pv_by_id(pv1_ref_id):
            return None, f"Physical Volume 1 (ID: {pv1_ref_id}) not found."
        if not self._find_pv_by_id(pv2_ref_id):
            return None, f"Physical Volume 2 (ID: {pv2_ref_id}) not found."
        if surface_ref not in state.optical_surfaces:
            return None, f"Optical Surface '{surface_ref}' not found."

        name = self._generate_unique_name(name_suggestion, state.border_surfaces)
        
        new_border_surface = BorderSurface(
            name=name,
            physvol1_ref=pv1_ref_id,
            physvol2_ref=pv2_ref_id,
            surfaceproperty_ref=surface_ref
        )
        
        state.add_border_surface(new_border_surface)
        self.recalculate_geometry_state()

        # Capture the new state
        self._capture_history_state(f"Added border surface {name}")
        
        return new_border_surface.to_dict(), None

    def update_border_surface(self, surface_name, new_pv1_ref_id, new_pv2_ref_id, new_surface_ref):
        """Updates an existing border surface link."""
        if not self.current_geometry_state:
            return False, "No project loaded"
        
        state = self.current_geometry_state
        target_surface = state.border_surfaces.get(surface_name)
        if not target_surface:
            return False, f"Border Surface '{surface_name}' not found."

        # Validate new references
        if not self._find_pv_by_id(new_pv1_ref_id):
            return False, f"New Physical Volume 1 (ID: {new_pv1_ref_id}) not found."
        if not self._find_pv_by_id(new_pv2_ref_id):
            return False, f"New Physical Volume 2 (ID: {new_pv2_ref_id}) not found."
        if new_surface_ref not in state.optical_surfaces:
            return False, f"New Optical Surface '{new_surface_ref}' not found."

        # Update attributes
        target_surface.physvol1_ref = new_pv1_ref_id
        target_surface.physvol2_ref = new_pv2_ref_id
        target_surface.surfaceproperty_ref = new_surface_ref

        self.recalculate_geometry_state()

        # Capture the new state
        self._capture_history_state(f"Updated border surface {surface_name}")

        return True, None

    def add_source(self, name_suggestion, gps_commands, position, rotation, activity=1.0, confine_to_pv=None, volume_link_id=None):
        """Adds a new particle source to the project, optionally linked to a volume."""
        if not self.current_geometry_state:
            return None, "No project loaded"

        name = self._generate_unique_name(name_suggestion, self.current_geometry_state.sources)
        
        # If Linked, calculate global transform
        if volume_link_id:
             pv = self._find_pv_by_id(volume_link_id)
             if pv:
                # Override position/rotation with GLOBAL transform of the PV
                global_pos, global_rot_rad = self._calculate_global_transform(pv)
                position = {
                    'x': str(global_pos['x']), 'y': str(global_pos['y']), 'z': str(global_pos['z'])
                }
                rotation = {
                    'x': str(global_rot_rad['x']), 'y': str(global_rot_rad['y']), 'z': str(global_rot_rad['z'])
                }
                # Also ensure confine_to_pv is set to the name (required for Geant4) if it wasn't passed or is empty
                if not confine_to_pv:
                    confine_to_pv = pv.name
                
                # Fetch shape info from the linked Logical Volume -> Solid
                lv = self.current_geometry_state.logical_volumes.get(pv.volume_ref)
                if lv:
                    solid = self.current_geometry_state.solids.get(lv.solid_ref)
                    if solid:
                        p = solid._evaluated_parameters
                        
                        # Clear any existing shape parameters to avoid conflicts (e.g. Para vs Cylinder)
                        keys_to_remove = ['pos/shape', 'pos/radius', 'pos/halfx', 'pos/halfy', 'pos/halfz', 'pos/sigma_x', 'pos/sigma_y', 'pos/sigma_r', 'pos/paralp', 'pos/parthe', 'pos/parphi']
                        for k in keys_to_remove:
                            if k in gps_commands:
                                del gps_commands[k]

                        # SAFETY MARGIN: Confinement requires generated points to be strictly INSIDE.
                        MARGIN = 0.001 # mm
                        
                        gps_commands['pos/type'] = 'Volume'
                        if solid.type in ['box']:
                            gps_commands['pos/shape'] = 'Box'
                            gps_commands['pos/halfx'] = f"{max(0, p.get('x', 0)/2 - MARGIN)} mm"
                            gps_commands['pos/halfy'] = f"{max(0, p.get('y', 0)/2 - MARGIN)} mm"
                            gps_commands['pos/halfz'] = f"{max(0, p.get('z', 0)/2 - MARGIN)} mm"
                        elif solid.type in ['tube', 'cylinder', 'tubs']:
                            gps_commands['pos/shape'] = 'Cylinder'
                            gps_commands['pos/radius'] = f"{max(0, p.get('rmax', 0) - MARGIN)} mm"
                            gps_commands['pos/halfz'] = f"{max(0, p.get('z', 0)/2 - MARGIN)} mm"
                        elif solid.type in ['sphere', 'orb']:
                            gps_commands['pos/shape'] = 'Sphere'
                            gps_commands['pos/radius'] = f"{max(0, p.get('rmax', 0) - MARGIN)} mm"
                        else:
                            gps_commands['pos/shape'] = 'Sphere'
                            gps_commands['pos/radius'] = '50 mm'

        new_source = ParticleSource(
            name=name,
            gps_commands=gps_commands,
            position=position,
            rotation=rotation,
            activity=activity,
            confine_to_pv=confine_to_pv,
            volume_link_id=volume_link_id
        )

        self.current_geometry_state.add_source(new_source)
        
        # Auto-activate new manually created sources
        if new_source.id not in self.current_geometry_state.active_source_ids:
            self.current_geometry_state.active_source_ids.append(new_source.id)
            
        self.recalculate_geometry_state()
        self._capture_history_state(f"Added particle source {name}")
        
        return new_source.to_dict(), None

    def update_particle_source(self, source_id, new_name, new_gps_commands, new_position, new_rotation, new_activity=None, new_confine_to_pv=None, new_volume_link_id=None):
        """Updates the properties of an existing particle source."""
        if not self.current_geometry_state:
            return False, "No project loaded"

        source_to_update = None
        for source in self.current_geometry_state.sources.values():
            if source.id == source_id:
                source_to_update = source
                break

        if not source_to_update:
            return False, f"Source with ID '{source_id}' not found."

        # Check for name change and ensure uniqueness if it changed
        if new_name and new_name != source_to_update.name:
            if new_name in self.current_geometry_state.sources:
                return False, f"A source named '{new_name}' already exists."
            # To rename, we remove the old entry and add a new one
            del self.current_geometry_state.sources[source_to_update.name]
            source_to_update.name = new_name
            self.current_geometry_state.sources[new_name] = source_to_update

        if new_gps_commands is not None:
            source_to_update.gps_commands = new_gps_commands

        if new_position is not None:
            source_to_update.position = new_position

        if new_rotation is not None:
            source_to_update.rotation = new_rotation
        
        if new_activity is not None:
            # simple validation
            try:
                source_to_update.activity = float(new_activity)
            except ValueError:
                return False, f"Invalid activity value: {new_activity}"
        
        if new_confine_to_pv is not None:
            # We treat an empty string as "no confinement" (None)
            if new_confine_to_pv == "":
                source_to_update.confine_to_pv = None
            else:
                source_to_update.confine_to_pv = new_confine_to_pv
        
        # Handle Linked Volume Updates
        source_to_update.volume_link_id = new_volume_link_id

        # RE-CALCULATE GLOBAL POSITION AND SHAPE IF LINKED
        if source_to_update.volume_link_id:
             pv = self._find_pv_by_id(source_to_update.volume_link_id)
             if pv:
                # 1. Update Transform
                global_pos, global_rot_rad = self._calculate_global_transform(pv)
                source_to_update.position = {
                    'x': str(global_pos['x']), 'y': str(global_pos['y']), 'z': str(global_pos['z'])
                }
                source_to_update.rotation = {
                    'x': str(global_rot_rad['x']), 'y': str(global_rot_rad['y']), 'z': str(global_rot_rad['z'])
                }
                # Ensure confine name matches
                source_to_update.confine_to_pv = pv.name

                # 2. Update Shape Parameters to match the Volume dimensions
                # Fetch shape info from the linked Logical Volume -> Solid
                lv = self.current_geometry_state.logical_volumes.get(pv.volume_ref)
                if lv:
                    solid = self.current_geometry_state.solids.get(lv.solid_ref)
                    if solid:
                        p = solid._evaluated_parameters
                        cmds = source_to_update.gps_commands
                        
                        # Set default type to Volume
                        cmds['pos/type'] = 'Volume'

                        # SAFETY MARGIN: Confinement requires generated points to be strictly INSIDE.
                        MARGIN = 0.001 # mm
                        
                        cmds['pos/type'] = 'Volume'
                        if solid.type in ['box']:
                            cmds['pos/shape'] = 'Box'
                            cmds['pos/halfx'] = f"{max(0, p.get('x', 0)/2 - MARGIN)} mm"
                            cmds['pos/halfy'] = f"{max(0, p.get('y', 0)/2 - MARGIN)} mm"
                            cmds['pos/halfz'] = f"{max(0, p.get('z', 0)/2 - MARGIN)} mm"
                        elif solid.type in ['tube', 'cylinder', 'tubs']:
                            cmds['pos/shape'] = 'Cylinder'
                            cmds['pos/radius'] = f"{max(0, p.get('rmax', 0) - MARGIN)} mm"
                            cmds['pos/halfz'] = f"{max(0, p.get('z', 0)/2 - MARGIN)} mm"
                        elif solid.type in ['sphere', 'orb']:
                            cmds['pos/shape'] = 'Sphere'
                            cmds['pos/radius'] = f"{max(0, p.get('rmax', 0) - MARGIN)} mm"
                        else:
                            cmds['pos/shape'] = 'Sphere'
                            cmds['pos/radius'] = '50 mm'

             else:
                # Linked ID not found? Maybe deleted. Clear link.
                source_to_update.volume_link_id = None
        else:
             # Standard update of position/rotation if NOT linked (already handled above by basic property updates)
             pass

        self._capture_history_state(f"Updated particle source {source_to_update.name}")
        # Recalculation is not strictly necessary unless commands affect evaluation,
        # but it's good practice to keep it consistent.
        success, error_msg = self.recalculate_geometry_state()
        return success, error_msg
    
    def set_active_source(self, source_id):
        """Sets or toggles the active source for the simulation."""
        if not self.current_geometry_state:
            return False, "No project loaded"

        # If source_id is None, clear all active sources
        if source_id is None:
            self.current_geometry_state.active_source_ids = []
            self.is_changed = True
            return True, "All sources deactivated."

        # Verify the source ID exists
        found = any(s.id == source_id for s in self.current_geometry_state.sources.values())
        if not found:
            return False, f"Source with ID {source_id} not found."

        # Toggle logic: if present, remove it; if absent, add it.
        if source_id in self.current_geometry_state.active_source_ids:
            self.current_geometry_state.active_source_ids.remove(source_id)
            msg = "Source deactivated."
        else:
            self.current_geometry_state.active_source_ids.append(source_id)
            msg = "Source activated."

        self.is_changed = True
        return True, msg

    def _find_pv_by_name(self, pv_name):
        """Helper to find a PV object by its Name across the entire geometry."""
        state = self.current_geometry_state
        # Search in Logical Volumes
        for lv in state.logical_volumes.values():
            if lv.content_type == 'physvol':
                for pv in lv.content:
                    if pv.name == pv_name:
                        return pv
        # Search in Assemblies
        for asm in state.assemblies.values():
            for pv in asm.placements:
                if pv.name == pv_name:
                    return pv
        return None

    def _calculate_global_transform(self, start_pv):
        """
        Calculates the global position and rotation of a PhysicalVolumePlacement
        by traversing up the hierarchy (finding parents recursively).
        
        Returns:
            global_pos (dict): {'x': float, 'y': float, 'z': float}
            global_rot (dict): {'x': float, 'y': float, 'z': float} (Euler angles in radians)
        """
        state = self.current_geometry_state
        if not state:
            return {'x':0,'y':0,'z':0}, {'x':0,'y':0,'z':0}

        # Start with the local transform of the PV
        # Note: get_transform_matrix() uses _evaluated_position/_evaluated_rotation
        current_transform = start_pv.get_transform_matrix()
        
        # Traverse up
        # Assumption: The 'parent_lv_name' is the container.
        # We need to find the PV that PLACES this container.
        # Limitation: If the container LV is placed multiple times, this simple lookup 
        # is ambiguous. We will just find the *first* placement we encounter.
        
        current_parent_lv_name = start_pv.parent_lv_name
        
        # Safety depth counter
        depth = 0
        max_depth = 20

        while current_parent_lv_name and current_parent_lv_name != state.world_volume_ref and depth < max_depth:
            depth += 1
            parent_placement = None
            
            # Find a placement of 'current_parent_lv_name'
            # 1. Search in LVs
            found = False
            for lv in state.logical_volumes.values():
                if lv.content_type == 'physvol':
                    for pv in lv.content:
                        if pv.volume_ref == current_parent_lv_name:
                            parent_placement = pv
                            found = True
                            break
                if found: break
            
            # 2. Search in Assemblies if not found
            if not found:
                for asm in state.assemblies.values():
                    for pv in asm.placements:
                        if pv.volume_ref == current_parent_lv_name:
                            parent_placement = pv
                            found = True
                            break
                    if found: break
            
            if parent_placement:
                # Apply parent transform: Global = Parent * Child
                parent_matrix = parent_placement.get_transform_matrix()
                current_transform = parent_matrix @ current_transform
                
                # Move up one level
                current_parent_lv_name = parent_placement.parent_lv_name
            else:
                # Could be a top-level placement in the World, or orphaned
                # If it's in the world, parent_lv_name should ideally be the world name, 
                # but if we passed check '!= state.world_volume_ref', maybe it's implicitly world.
                # Stop here.
                break
                
        # Now decompose the final global matrix
        pos_dict, rot_dict, scale_dict = PhysicalVolumePlacement.decompose_matrix(current_transform)
        
        return pos_dict, rot_dict

    
    def get_source_params_from_volume(self, volume_id):
        """
        Calculates the appropriate GPS source parameters to emulate a source bound to the specified PhysicalVolume.
        Returns a dictionary with position, rotation, shape type, and shape dimensions.
        """
        pv = self._find_pv_by_id(volume_id)
        if not pv:
            return {'success': False, 'error': f"Physical Volume with ID {volume_id} not found."}

        # 1. Calculate Global Transform (Position & Rotation)
        global_pos, global_rot_rad = self._calculate_global_transform(pv)

        # 2. Determine Shape Parameters from the linked Solid
        state = self.current_geometry_state
        lv = state.logical_volumes.get(pv.volume_ref)
        if not lv:
            return {'success': False, 'error': f"Logical Volume {pv.volume_ref} not found."}
        
        solid = state.solids.get(lv.solid_ref)
        if not solid:
            return {'success': False, 'error': f"Solid {lv.solid_ref} not found."}
        
        # Helper to format float to string
        fstr = lambda x: str(x)
        
        # Default shape commands
        shape_type = 'Volume'
        gps_shape_type = 'Sphere' # Default sub-shape
        shape_params = {}

        p = solid._evaluated_parameters
        
        if solid.type in ['box']:
            gps_shape_type = 'Box'
            # GPS Box uses half-lengths
            shape_params['gps_halfx'] = fstr(p.get('x', 0)/2)
            shape_params['gps_halfy'] = fstr(p.get('y', 0)/2)
            shape_params['gps_halfz'] = fstr(p.get('z', 0)/2)

        elif solid.type in ['tube', 'cylinder', 'tubs']:
            gps_shape_type = 'Cylinder'
            shape_params['gps_radius'] = fstr(p.get('rmax', 0))
            shape_params['gps_halfz'] = fstr(p.get('z', 0)/2)
            
        elif solid.type in ['sphere', 'orb']:
            gps_shape_type = 'Sphere'
            shape_params['gps_radius'] = fstr(p.get('rmax', 0))
        
        else:
            # Fallback for complex shapes: use bounding box approximation?
            # For now, default to a generic Sphere with radius 10
            gps_shape_type = 'Sphere'
            shape_params['gps_radius'] = '10'

        return {
            'success': True,
            'position': {
                'x': fstr(global_pos['x']),
                'y': fstr(global_pos['y']),
                'z': fstr(global_pos['z'])
            },
            'rotation': {
                'x': fstr(global_rot_rad['x']),
                'y': fstr(global_rot_rad['y']),
                'z': fstr(global_rot_rad['z'])
            },
            'shape_type': shape_type,
            'gps_shape_type': gps_shape_type,
            'shape_params': shape_params,
            'confine_pv_name': pv.name
        }

    def _calculate_bounding_params(self, pv_name):
        """
        Finds the PV, looks up its Logical Volume and Solid, 
        and returns appropriate GPS shape params and the PV's evaluated transform.
        """
        pv = self._find_pv_by_name(pv_name)
        if not pv: return None, None, None
        
        # Look up LV
        lv = self.current_geometry_state.logical_volumes.get(pv.volume_ref)
        if not lv: return None, None, None
        
        solid = self.current_geometry_state.solids.get(lv.solid_ref)
        if not solid: return None, None, None

        # Determine tight bounding box based on Solid Type
        p = solid._evaluated_parameters # These are already in mm/rad
        
        shape_cmds = {'pos/shape': 'Para'} 
        
        if solid.type == 'box':
            shape_cmds['pos/halfx'] = f"{p['x']/2} mm"
            shape_cmds['pos/halfy'] = f"{p['y']/2} mm"
            shape_cmds['pos/halfz'] = f"{p['z']/2} mm"
        
        elif solid.type in ['tube', 'cylinder']:
            # For a cylinder, a bounding box is 2*R by 2*R by Z
            shape_cmds['pos/halfx'] = f"{p['rmax']} mm"
            shape_cmds['pos/halfy'] = f"{p['rmax']} mm"
            shape_cmds['pos/halfz'] = f"{p['z']/2} mm"

        elif solid.type == 'sphere':
            shape_cmds['pos/halfx'] = f"{p['rmax']} mm"
            shape_cmds['pos/halfy'] = f"{p['rmax']} mm"
            shape_cmds['pos/halfz'] = f"{p['rmax']} mm"

        else:
            # Fallback for complex shapes
            shape_cmds['pos/halfx'] = "200 mm" 
            shape_cmds['pos/halfy'] = "200 mm" 
            shape_cmds['pos/halfz'] = "200 mm"
        
        return shape_cmds, pv._evaluated_position, pv._evaluated_rotation
    
    def generate_macro_file(self, job_id, sim_params, build_dir, run_dir, version_dir):
        """
        Generates a Geant4 macro file from simulation parameters.

        Args:
            job_id (str): A unique identifier for this simulation run.
            sim_params (dict): A dictionary containing settings from the frontend.
            build_dir (str): The path to the Geant4 build directory.
            run_dir (str): The path to the specific directory for this run's output.
            version_dir (str): The path to the directory of the project version being run.

        Returns:
            str: The path to the generated macro file.
        """
        # --- Save metadata ---
        metadata = {
            'job_id': job_id,
            'timestamp': datetime.now().isoformat(),
            'total_events': sim_params.get('events', 1),
            'sim_options': sim_params 
        }
        metadata_path = os.path.join(run_dir, "metadata.json")
        with open(metadata_path, 'w') as f:
            json.dump(metadata, f, indent=2)
            
        macro_path = os.path.join(run_dir, "run.mac")
        version_json_path = os.path.join(version_dir, "version.json")

        # 1. Load the geometry from the version.json file, not the current state
        try:
            with open(version_json_path, 'r') as f:
                state_dict = json.load(f)
            
            # The GDML writer needs a GeometryState object
            temp_state = GeometryState.from_dict(state_dict)
            gdml_string = GDMLWriter(temp_state).get_gdml_string()
            
            gdml_output_path = os.path.join(run_dir, "geometry.gdml")
            with open(gdml_output_path, 'w') as f:
                f.write(gdml_string)
        except Exception as e:
            raise RuntimeError(f"Failed to process geometry for simulation: {e}")

        # 2. Generate the macro content
        macro_content = []
        macro_content.append("# AirPet Auto-Generated Macro")
        macro_content.append(f"# Job ID: {job_id}")
        macro_content.append("")
        
        # Configure number of threads (Default to multi-threading if requested)
        num_threads = sim_params.get('threads', 12) # Default to 12 threads if not specified, for better performance
        macro_content.append(f"/run/numberOfThreads {num_threads}")
        
        # Disable trajectory storage to prevent Visualization cleanup crashes
        macro_content.append("/tracking/storeTrajectory 0")
        
        # --- Set random seed ---
        seed1 = sim_params.get('seed1', 0)
        seed2 = sim_params.get('seed2', 0)
        macro_content.append("\n# --- Random Seed ---")
        if seed1 > 0 and seed2 > 0:
            macro_content.append(f"/random/setSeeds {seed1} {seed2}")
        else:
            macro_content.append("# Using default/random seeds")

        # --- Configure Sensitive Detectors ---
        macro_content.append("# --- Sensitive Detectors ---")
        # Find all LVs marked as sensitive
        sensitive_lvs = [lv for lv in self.current_geometry_state.logical_volumes.values() if lv.is_sensitive]
        
        if not sensitive_lvs:
            macro_content.append("# No sensitive detectors defined.")
        else:
            for lv in sensitive_lvs:
                sd_name = f"{lv.name}_SD" # Automatic naming
                macro_content.append(f"/g4pet/detector/addSD {lv.name} {sd_name}")
        
        macro_content.append("")

        # --- Load Geometry ---
        macro_content.append(f"/g4pet/detector/readFile geometry.gdml")
        macro_content.append("")

        # --- Initialize ---
        macro_content.append("/run/initialize")
        macro_content.append("")

        # --- Add production cuts ---
        macro_content.append("# --- Physics Cuts for Performance ---")
        macro_content.append("/run/setCut 1.0 mm") # Stop tracking particles that can't travel at least 1mm
        macro_content.append("")

        # --- Add commands to control n-tuple saving ---
        macro_content.append("# --- N-tuple Saving Control ---")
        save_particles = sim_params.get('save_particles', False)
        save_hits = sim_params.get('save_hits', True)
        macro_content.append(f"/g4pet/run/saveParticles {str(save_particles).lower()}")
        macro_content.append(f"/g4pet/run/saveHits {str(save_hits).lower()}")
        
        # Default Hit Energy Threshold to reduce file size
        hit_threshold = sim_params.get('hit_energy_threshold', '100 keV')
        macro_content.append(f"/g4pet/run/hitEnergyThreshold {hit_threshold}")
        macro_content.append("")

        # --- ADD VERBOSITY FOR DEBUGGING ---
        macro_content.append("# --- Verbosity Settings ---")
        #macro_content.append("/tracking/verbose 1") # Print a message for every new track
        #macro_content.append("/hits/verbose 2")     # Print every single hit as it's processed
        macro_content.append("")

        # --- Configure Source (using GPS) ---
        active_ids = self.current_geometry_state.active_source_ids
        active_sources = []
        
        # Collect source objects
        for s_id in active_ids:
            for source in self.current_geometry_state.sources.values():
                if source.id == s_id:
                    active_sources.append(source)
                    break
        
        if not active_sources:
            macro_content.append("# WARNING: No active particle source was specified for this run.")
        else:
            # 1. Calculate Total Activity for Normalization
            total_activity = sum([float(s.activity) for s in active_sources])
            if total_activity == 0: total_activity = 1.0 # Prevent division by zero

            macro_content.append("# --- Primary Particle Source(s) ---")
            
            for i, source in enumerate(active_sources):
                # Calculate relative intensity (0.0 to 1.0)
                relative_intensity = float(source.activity) / total_activity
                
                if i == 0:
                    # First source defines the GPS list
                    macro_content.append(f"/gps/source/intensity {relative_intensity}")
                else:
                    # Subsequent sources are added
                    macro_content.append(f"/gps/source/add {relative_intensity}")

                macro_content.append(f"# Source: {source.name} (Activity: {source.activity} Bq)")
                
                cmds = source.gps_commands.copy()
                
                # Handling Confinement and Transform
                evaluated_pos = source._evaluated_position
                evaluated_rot = source._evaluated_rotation
                
                if source.confine_to_pv:
                    macro_content.append(f"/gps/pos/confine {source.confine_to_pv}")
                
                # Map Box to Para if needed (for Volume sources)
                # Note: The source shape parameters (halfx, radius, etc.) are already set correctly 
                # (with margins) by add_source/update_particle_source, so we trust them.
                if cmds.get('pos/type') == 'Volume' and cmds.get('pos/shape') == 'Box':
                     cmds['pos/shape'] = 'Para'

                # Write GPS commands
                for cmd, value in cmds.items():
                    if cmd == 'pos/confine': continue # Already handled or skipped if logic dictates
                    macro_content.append(f"/gps/{cmd} {value}")
                
                # Write Position (Centre)
                # Use evaluated_pos (either Source origin or PV origin)
                pos = evaluated_pos
                macro_content.append(f"/gps/pos/centre {pos['x']} {pos['y']} {pos['z']} mm")

                # Write Rotation
                # Use evaluated_rot (either Source rot or PV rot)
                rot = evaluated_rot
                r = R.from_euler('zyx', [rot['z'], rot['y'], rot['x']], degrees=False)
                rot_matrix = r.as_matrix()
                x_prime = rot_matrix[:, 0]
                y_prime = rot_matrix[:, 1]
                macro_content.append(f"/gps/ang/rot1 {x_prime[0]} {x_prime[1]} {x_prime[2]}")
                macro_content.append(f"/gps/ang/rot2 {y_prime[0]} {y_prime[1]} {y_prime[2]}")
                
                macro_content.append("")

        # --- Add Track Saving Logic ---
        macro_content.append("\n# --- Output and Visualization ---")
        tracks_dir = os.path.join(run_dir, "tracks")
        os.makedirs(tracks_dir, exist_ok=True)
        macro_content.append(f"/g4pet/event/printTracksToDir tracks/")
        
        save_range_str = sim_params.get('save_tracks_range', '0-0')
        try:
            if '-' in save_range_str:
                start_event, end_event = map(int, save_range_str.split('-'))
            else:
                start_event = end_event = int(save_range_str)
        except (ValueError, IndexError):
            start_event, end_event = 0, 0 # Default on error
        macro_content.append(f"/g4pet/event/setTrackEventRange {start_event} {end_event}")
        
        # Set the output HDF5 file name
        macro_content.append(f"/analysis/setFileName output.hdf5")

        # --- Add the print progress command ---
        print_progress = sim_params.get('print_progress', 0)
        if print_progress > 0:
            macro_content.append(f"/run/printProgress {print_progress}")

        # --- Run Beam On ---
        num_events = sim_params.get('events', 1)
        macro_content.append("\n# --- Start Simulation ---")
        macro_content.append(f"/run/beamOn {num_events}")

        # 3. Write the macro file
        with open(macro_path, 'w') as f:
            f.write("\n".join(macro_content))

        return macro_path