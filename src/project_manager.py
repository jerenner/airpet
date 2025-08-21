# src/project_manager.py
import json
import math
import tempfile
import os
import re
from .geometry_types import GeometryState, Solid, Define, Material, Element, Isotope, \
                            LogicalVolume, PhysicalVolumePlacement, Assembly, ReplicaVolume, \
                            DivisionVolume, ParamVolume, OpticalSurface, SkinSurface, \
                            BorderSurface
from .gdml_parser import GDMLParser
from .gdml_writer import GDMLWriter
from .step_parser import parse_step_file

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

        # --- Track changed objects (for now only tracking certain solids) ---
        self.changed_object_ids = {'solids': set() } #, 'lvs': set(), 'defines': set()}

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
        os.makedirs(project_path, exist_ok=True)
        autosave_path = os.path.join(project_path, "autosave.json")
        
        json_string = self.save_project_to_json_string()
        with open(autosave_path, 'w') as f:
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
        def evaluate_transform_part(part_data, default_val):
            if isinstance(part_data, str): # It's a reference to a define
                return evaluator.get_symbol(part_data, default_val)
            elif isinstance(part_data, dict): # It's a dict of expressions
                evaluated_dict = {}
                for axis, raw_expr in part_data.items():
                    try:
                        # Check if it's already a number
                        if isinstance(raw_expr, (int, float)):
                            evaluated_dict[axis] = raw_expr
                        else:
                            evaluated_dict[axis] = evaluator.evaluate(str(raw_expr))[1]
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

                                # NOTE: Account for an apparent difference in rotation angle sense
                                #       in THREE.js and GDML
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
                    '_evaluated_position': evaluate_transform_part(transform.get('position'), {'x': 0, 'y': 0, 'z': 0}),
                    '_evaluated_rotation': evaluate_transform_part(transform.get('rotation'), {'x': 0, 'y': 0, 'z': 0}),
                    '_evaluated_scale': evaluate_transform_part(transform.get('scale'), {'x': 1, 'y': 1, 'z': 1})
                }

            elif solid_type == 'box':
                ep['x'] = p.get('x', 0)
                ep['y'] = p.get('y', 0)
                ep['z'] = p.get('z', 0)
            
            elif solid_type == 'tube':
                ep['rmin'] = p.get('rmin', 0)
                ep['rmax'] = p.get('rmax', 0)
                ep['z'] = p.get('z', 0)
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
                    
                    pv._evaluated_position = evaluate_transform_part(pv.position, {'x': 0, 'y': 0, 'z': 0})
                    pv._evaluated_rotation = evaluate_transform_part(pv.rotation, {'x': 0, 'y': 0, 'z': 0})
                    pv._evaluated_scale = evaluate_transform_part(pv.scale, {'x': 1, 'y': 1, 'z': 1})
            
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
                        proc_obj._evaluated_start_position = evaluate_transform_part(proc_obj.start_position, {'x': 0, 'y': 0, 'z': 0})
                    if hasattr(proc_obj, 'start_rotation'):
                        proc_obj._evaluated_start_rotation = evaluate_transform_part(proc_obj.start_rotation, {'x': 0, 'y': 0, 'z': 0})

                    # Add evaluation logic for parameterised volumes
                    if hasattr(proc_obj, 'ncopies'):
                        try:
                            proc_obj._evaluated_ncopies = int(evaluator.evaluate(str(proc_obj.ncopies))[1])
                        except Exception: proc_obj._evaluated_ncopies = 0

                    if hasattr(proc_obj, 'parameters'):
                        for param_set in proc_obj.parameters:
                            # Evaluate the transform for this instance
                            param_set._evaluated_position = evaluate_transform_part(param_set.position, {'x': 0, 'y': 0, 'z': 0})
                            param_set._evaluated_rotation = evaluate_transform_part(param_set.rotation, {'x': 0, 'y': 0, 'z': 0})
                            
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

    def add_logical_volume(self, name_suggestion, solid_ref, material_ref, vis_attributes=None, content_type='physvol', content=None):
        if not self.current_geometry_state: return None, "No project loaded"
        if solid_ref not in self.current_geometry_state.solids:
            return None, f"Solid '{solid_ref}' not found."
        if material_ref not in self.current_geometry_state.materials:
            return None, f"Material '{material_ref}' not found."

        name = self._generate_unique_name(name_suggestion, self.current_geometry_state.logical_volumes)
        new_lv = LogicalVolume(name, solid_ref, material_ref, vis_attributes)

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

    def update_logical_volume(self, lv_name, new_solid_ref, new_material_ref, new_vis_attributes=None, new_content_type=None, new_content=None):
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

        except Exception as e:
            return False, None
        
        # --- Return the patch data  ---
        # (For now, do not attempt to patch, as one transformation may affect several PVs
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
        
        # If everything succeeded, capture the final state and return
        self._capture_history_state(f"Batch update to {len(updated_pv_objects)} PVs")
        return True

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
                "assemblies": [], "optical_surfaces": [], "skin_surfaces": [], "border_surfaces": []
            }
        }
        for item in objects_to_delete:
            obj_type = item['type']
            obj_id = item['id']
            # Map frontend types to backend dictionary keys if they differ
            dict_key = f"{obj_type}s" if obj_type != "assembly" else "assemblies"
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
                    for item in solid.parameters.get('recipe', []):
                        if item['solid_ref'] in rename_map:
                            item['solid_ref'] = rename_map[item['solid_ref']]
                else: # Old style boolean
                    if solid.parameters['first_ref'] in rename_map:
                        solid.parameters['first_ref'] = rename_map[solid.parameters['first_ref']]
                    if solid.parameters['second_ref'] in rename_map:
                        solid.parameters['second_ref'] = rename_map[solid.parameters['second_ref']]

            new_name = self._generate_unique_name(name, self.current_geometry_state.solids)
            if new_name != name:
                rename_map[name] = new_name
            solid.name = new_name
            self.current_geometry_state.add_solid(solid)

        # --- Merge Logical Volumes ---
        for name, lv in incoming_state.logical_volumes.items():
            # Ignore the incoming world volume
            if name == incoming_state.world_volume_ref:
                continue

            # Update references within this LV
            if lv.solid_ref in rename_map: lv.solid_ref = rename_map[lv.solid_ref]
            if lv.material_ref in rename_map: lv.material_ref = rename_map[lv.material_ref]
            
            # Note: We are NOT merging physical volume placements. The user will
            # place the newly imported LVs manually. This is the essence of a "part" import.

            new_name = self._generate_unique_name(name, self.current_geometry_state.logical_volumes)
            if new_name != name:
                rename_map[name] = new_name
            lv.name = new_name
            
            # Clear the new content list and reset the type
            lv.content_type = 'physvol'
            lv.content = [] 

            self.current_geometry_state.add_logical_volume(lv)
        
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

        # --- Process and Add Placements ---
        if hasattr(incoming_state, 'placements_to_add'):
            for pv_to_add in incoming_state.placements_to_add:
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

        # Capture the new state
        self._capture_history_state(f"State merge")

        return success, error_msg

    def process_ai_response(self, ai_data: dict):
        """
        Processes a structured dictionary from the AI, creating new objects
        and applying updates like placements.
        """
        if not self.current_geometry_state:
            return False, "No project loaded."

        print("RECEIVED AI DATA")
        print(ai_data)

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

        # --- 3. Recalculate everything once at the end ---
        success, error_msg = self.recalculate_geometry_state()

        # Capture the new state
        self._capture_history_state(f"Incorporated AI response")

        return success, error_msg

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