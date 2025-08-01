# src/project_manager.py
import json
import math
import tempfile
import os
import asteval
from .geometry_types import GeometryState, Solid, Define, Material, Element, Isotope, \
                            LogicalVolume, PhysicalVolumePlacement, Assembly, ReplicaVolume, \
                            DivisionVolume, ParamVolume, OpticalSurface, SkinSurface, \
                            BorderSurface
from .gdml_parser import GDMLParser
from .gdml_writer import GDMLWriter
from .step_parser import parse_step_file
from .expression_evaluator import create_configured_asteval, ExpressionEvaluator

class ProjectManager:
    def __init__(self):
        self.current_geometry_state = GeometryState()
        self.gdml_parser = GDMLParser()
        # Give the project manager its own evaluator instance
        self.expression_evaluator = ExpressionEvaluator()

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

        # Use our central factory to get a correctly configured interpreter.
        aeval = create_configured_asteval()

        # Helper function for evaluating transforms ##
        def evaluate_transform_part(part_data, default_val):
            if isinstance(part_data, str): # It's a reference to a define
                return aeval.symtable.get(part_data, default_val)
            elif isinstance(part_data, dict): # It's a dict of expressions
                evaluated_dict = {}
                for axis, raw_expr in part_data.items():
                    try:
                        # Check if it's already a number
                        if isinstance(raw_expr, (int, float)):
                            evaluated_dict[axis] = raw_expr
                        else:
                            evaluated_dict[axis] = aeval.eval(str(raw_expr))
                    except Exception:
                        evaluated_dict[axis] = default_val.get(axis, 0)
                return evaluated_dict
            return default_val
        
        # --- Stage 1: Iteratively resolve all defines ---
        unresolved_defines = list(state.defines.values())
        max_passes = len(unresolved_defines) + 2
        for _ in range(max_passes):
            if not unresolved_defines: break
            
            resolved_this_pass = []
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
                                expr_to_eval = raw_dict[axis]
                                # If a unit is defined on the parent tag, apply it
                                if unit_str:
                                    expr_to_eval = f"({expr_to_eval}) * {unit_str}"
                                val_dict[axis] = aeval.eval(expr_to_eval)
                        define_obj.value = val_dict
                    else: # constant, quantity, expression
                        expr_to_eval = str(define_obj.raw_expression)
                        unit_str = define_obj.unit
                        if unit_str:
                             expr_to_eval = f"({expr_to_eval}) * {unit_str}"
                        define_obj.value = aeval.eval(expr_to_eval)
                    
                    # Add successfully evaluated define to the symbol table for the next ones.
                    aeval.symtable[define_obj.name] = define_obj.value
                    resolved_this_pass.append(define_obj)

                except (NameError, KeyError, TypeError):
                    still_unresolved.append(define_obj) # Depends on another define, try again next pass
                except Exception as e:
                    print(f"Error evaluating define '{define_obj.name}': {e}. Setting value to None.")
                    define_obj.value = None
                    resolved_this_pass.append(define_obj) # Consider it "resolved" to avoid infinite loops

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
                    material._evaluated_Z = aeval.eval(str(material.Z_expr))
                if material.A_expr:
                    material._evaluated_A = aeval.eval(str(material.A_expr))
                if material.density_expr:
                    material._evaluated_density = aeval.eval(str(material.density_expr))
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
                            evaluated_scale[axis] = aeval.eval(str(axis_expr))
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
                        temp_eval_params[key] = aeval.eval(expr_to_eval)
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
                ep['dz'] = p.get('dz', 0) / 2.0
                ep['startphi'] = p.get('startphi', 0)
                ep['deltaphi'] = p.get('deltaphi', 2 * math.pi) # Default is a full circle

            elif solid_type == 'cone':
                ep['rmin1'] = p.get('rmin1', 0)
                ep['rmax1'] = p.get('rmax1', 0)
                ep['rmin2'] = p.get('rmin2', 0)
                ep['rmax2'] = p.get('rmax2', 0)
                ep['dz'] = p.get('dz', 0) / 2.0
                ep['startphi'] = p.get('startphi', 0)
                ep['deltaphi'] = p.get('deltaphi', 2 * math.pi)

            elif solid_type == 'sphere':
                ep['rmin'] = p.get('rmin', 0)
                ep['rmax'] = p.get('rmax', 0)
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
                ep['dx'] = p.get('dx', 0) / 2.0
                ep['dy'] = p.get('dy', 0) / 2.0
                ep['dz'] = p.get('dz', 0) / 2.0
                ep['alpha'] = p.get('alpha', 0)
                ep['theta'] = p.get('theta', 0)
                ep['phi'] = p.get('phi', 0)
            
            elif solid.type == 'hype':
                 ep['dz'] = p.get('dz', 0) / 2.0
                 ep['rmin'] = p.get('rmin', 0)
                 ep['rmax'] = p.get('rmax', 0)
                 ep['inst'] = p.get('inst', 0)
                 ep['outst'] = p.get('outst', 0)

            elif solid_type == 'trap':
                ep['dz'] = p.get('dz', 0) / 2.0
                ep['theta'] = p.get('theta', 0)
                ep['phi'] = p.get('phi', 0)
                ep['dy1'] = p.get('dy1', 0) / 2.0
                ep['dx1'] = p.get('dx1', 0) / 2.0
                ep['dx2'] = p.get('dx2', 0) / 2.0
                ep['alpha1'] = p.get('alpha1', 0)
                ep['dy2'] = p.get('dy2', 0) / 2.0
                ep['dx3'] = p.get('dx3', 0) / 2.0
                ep['dx4'] = p.get('dx4', 0) / 2.0
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
                        pv.copy_number = int(aeval.eval(str(pv.copy_number_expr)))
                    except Exception as e:
                        pv.copy_number = 0
                    
                    pv._evaluated_position = evaluate_transform_part(pv.position, {'x': 0, 'y': 0, 'z': 0})
                    pv._evaluated_rotation = evaluate_transform_part(pv.rotation, {'x': 0, 'y': 0, 'z': 0})
                    pv._evaluated_scale = evaluate_transform_part(pv.scale, {'x': 1, 'y': 1, 'z': 1})
            
            elif lv.content_type in ['replica', 'division']:
                # For procedural placements, we need to evaluate their parameters (width, offset, etc.)
                proc_obj = lv.content
                if proc_obj:
                    # Evaluate numeric properties of the procedural object itself
                    if hasattr(proc_obj, 'width'):
                        proc_obj.width = float(aeval.eval(str(proc_obj.width)))
                    if hasattr(proc_obj, 'offset'):
                        proc_obj.offset = float(aeval.eval(str(proc_obj.offset)))
                    if hasattr(proc_obj, 'number'):
                        proc_obj.number = int(aeval.eval(str(proc_obj.number)))


        # Iterate through Assemblies to evaluate their placements
        for asm in all_asms:
            for pv in asm.placements:
                try:
                    pv.copy_number = int(aeval.eval(str(pv.copy_number_expr)))
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
        return self.current_geometry_state

    def export_to_gdml_string(self):
        if self.current_geometry_state:
            writer = GDMLWriter(self.current_geometry_state)
            return writer.get_gdml_string()
        return "<?xml version='1.0' encoding='UTF-8'?>\n<gdml />"
    
    def get_full_project_state_dict(self):
        """ Returns the entire current geometry state as a dictionary. """
        if self.current_geometry_state:
            return self.current_geometry_state.to_dict()
        return {}

    def get_object_details(self, object_type, object_name_or_id):
        """
        Get details for a specific object by its type and name/ID.
        'object_type' can be 'define', 'material', 'solid', 'logical_volume', 'physical_volume'.
        For 'physical_volume', object_name_or_id would be its unique ID.
        """
        if not self.current_geometry_state: return None
        
        state = self.current_geometry_state
        obj = None

        if object_type == "define": obj = state.defines.get(object_name_or_id)
        elif object_type == "material": obj = state.materials.get(object_name_or_id)
        elif object_type == "element": obj = state.elements.get(object_name_or_id)
        elif object_type == "isotope": obj = state.isotopes.get(object_name_or_id)
        elif object_type == "solid": obj = state.solids.get(object_name_or_id)
        elif object_type == "logical_volume": obj = state.logical_volumes.get(object_name_or_id)
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

        success, error_msg = self.recalculate_geometry_state()
        return success, error_msg

    def add_material(self, name_suggestion, properties_dict):
        if not self.current_geometry_state: return None, "No project loaded"
        name = self._generate_unique_name(name_suggestion, self.current_geometry_state.materials)
        # Assumes properties_dict contains expression strings like Z_expr, A_expr, density_expr
        new_material = Material(name, **properties_dict)
        self.current_geometry_state.add_material(new_material)
        self.recalculate_geometry_state()
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

        self.recalculate_geometry_state()
        return True, None

    def add_isotope(self, name_suggestion, params):
        if not self.current_geometry_state: return None, "No project loaded"
        name = self._generate_unique_name(name_suggestion, self.current_geometry_state.isotopes)
        new_isotope = Isotope(name, Z=params.get('Z'), N=params.get('N'), A_expr=params.get('A_expr'))
        self.current_geometry_state.add_isotope(new_isotope)
        self.recalculate_geometry_state()
        return new_isotope.to_dict(), None

    def update_isotope(self, isotope_name, new_params):
        if not self.current_geometry_state: return False, "No project loaded"
        target_isotope = self.current_geometry_state.isotopes.get(isotope_name)
        if not target_isotope: return False, f"Isotope '{isotope_name}' not found."
        target_isotope.Z = new_params.get('Z', target_isotope.Z)
        target_isotope.N = new_params.get('N', target_isotope.N)
        target_isotope.A_expr = new_params.get('A_expr', target_isotope.A_expr)
        self.recalculate_geometry_state()
        return True, None

    def add_solid(self, name_suggestion, solid_type, raw_parameters):
        """
        Adds a new solid to the project.
        """
        if not self.current_geometry_state:
            return None, "No project loaded"
        
        name = self._generate_unique_name(name_suggestion, self.current_geometry_state.solids)
        new_solid = Solid(name, solid_type, raw_parameters)
        self.current_geometry_state.add_solid(new_solid)
        
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
        return True, None
    
    def add_solid_object(self, solid_obj):
        """Helper to add an already-created Solid object."""
        self.current_geometry_state.solids[solid_obj.name] = solid_obj
        self.recalculate_geometry_state()

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
            self.recalculate_geometry_state()
            return True, None
            
        parent_lv_name = pv_params.get('parent_lv_name')
        pv_name_sugg = pv_params.get('name', f"{new_lv_name}_placement")
        
        position = {'x': '0', 'y': '0', 'z': '0'} 
        rotation = {'x': '0', 'y': '0', 'z': '0'}
        scale    = {'x': '1', 'y': '1', 'z': '1'}

        _, pv_error = self.add_physical_volume(parent_lv_name, pv_name_sugg, new_lv_name, position, rotation, scale)
        if pv_error:
            return False, f"Failed to place physical volume: {pv_error}"
        
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
        if new_vis_attributes:
            lv.vis_attributes = new_vis_attributes
            
        # Update content if provided
        if new_content_type and new_content is not None:
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
        
        self.recalculate_geometry_state()
        return True, None

    def add_physical_volume(self, parent_lv_name, pv_name_suggestion, placed_lv_ref, position, rotation, scale):
        if not self.current_geometry_state: return None, "No project loaded"
        
        parent_lv = self.current_geometry_state.logical_volumes.get(parent_lv_name)
        if not parent_lv:
            return None, f"Parent Logical Volume '{parent_lv_name}' not found."
        if placed_lv_ref not in self.current_geometry_state.logical_volumes:
            return None, f"Placed Logical Volume '{placed_lv_ref}' not found."

        # Generate a unique name for this PV *within its parent* (GDML PV names are not global)
        # For simplicity, we'll use a globally unique suggested name for now.
        # A better approach for pv_name would be to ensure it's unique among siblings.
        pv_name = pv_name_suggestion or f"{placed_lv_ref}_placement"

        # position_dict and rotation_dict are assumed to be {'x':val,...} in internal units
        new_pv = PhysicalVolumePlacement(pv_name, placed_lv_ref,
                                        position_val_or_ref=position,
                                        rotation_val_or_ref=rotation,
                                        scale_val_or_ref=scale)
        parent_lv.add_child(new_pv)
        print(f"Added Physical Volume: {pv_name} into {parent_lv_name}")

        self.recalculate_geometry_state()
        return new_pv.to_dict(), None

    def update_physical_volume(self, pv_id, new_name, new_position, new_rotation, new_scale):
        if not self.current_geometry_state: return False, "No project loaded"
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
            return False, f"Physical Volume with ID '{pv_id}' not found."
            
        if new_name is not None: pv_to_update.name = new_name
        if new_position is not None: pv_to_update.position = new_position
        if new_rotation is not None: pv_to_update.rotation = new_rotation
        if new_scale is not None: pv_to_update.scale = new_scale
        
        success, error_msg = self.recalculate_geometry_state()
        return success, error_msg

    def add_assembly_placement(self, parent_lv_name, assembly_name, placement_name_suggestion, position, rotation):
        """
        'Imprints' an assembly into a parent logical volume.
        This iterates through all placements within the assembly and adds them as
        physical volumes to the parent, applying the given transform.
        """
        if not self.current_geometry_state:
            return None, "No project loaded."

        parent_lv = self.current_geometry_state.get_logical_volume(parent_lv_name)
        if not parent_lv:
            return None, f"Parent Logical Volume '{parent_lv_name}' not found."

        assembly = self.current_geometry_state.get_assembly(assembly_name)
        if not assembly:
            return None, f"Assembly '{assembly_name}' not found."

        # Create the root transformation for the entire assembly placement
        assembly_transform = PhysicalVolumePlacement("temp", "temp", 0, position, rotation).get_transform_matrix()

        # Get a starting copy number for this group of placements
        start_copy_no = self._get_next_copy_number(parent_lv)

        placed_pvs = []

        for i, pv_in_assembly in enumerate(assembly.placements):
            # Get the transformation of the part within the assembly
            part_transform = pv_in_assembly.get_transform_matrix()

            # Combine it with the overall assembly placement transform
            # Final Transform = Assembly Placement Transform * Part's Local Transform
            final_transform_matrix = assembly_transform @ part_transform
            
            # Decompose the final matrix back into position and rotation dicts
            final_pos, final_rot_rad, _ = PhysicalVolumePlacement.decompose_matrix(final_transform_matrix)

            # Create a new physical volume placement inside the parent LV
            # We use a unique name for each imprinted part
            unique_pv_name = f"{placement_name_suggestion}_{i}"
            
            new_pv = PhysicalVolumePlacement(
                name=unique_pv_name,
                volume_ref=pv_in_assembly.volume_ref,
                copy_number=start_copy_no + i,
                position_val_or_ref=final_pos,
                rotation_val_or_ref=final_rot_rad
            )
            parent_lv.add_child(new_pv)
            placed_pvs.append(new_pv.to_dict())

        self.recalculate_geometry_state()
        return placed_pvs, None

    def create_assembly_from_pvs(self, pv_ids, assembly_name_suggestion, parent_lv_name):
        """
        Groups existing PVs into a new assembly, removes them from their original parent,
        and places the new assembly back into that parent.
        """
        if not self.current_geometry_state:
            return None, "No project loaded."
        
        state = self.current_geometry_state
        parent_lv = state.logical_volumes.get(parent_lv_name)
        if not parent_lv or parent_lv.content_type != 'physvol':
            return None, f"Parent volume '{parent_lv_name}' not found or is not a standard volume."

        # 1. Find and collect the PV objects to be moved
        pvs_to_move = []
        pvs_to_keep = []
        pv_id_set = set(pv_ids)

        for pv in parent_lv.content:
            if pv.id in pv_id_set:
                pvs_to_move.append(pv)
            else:
                pvs_to_keep.append(pv)

        if len(pvs_to_move) != len(pv_id_set):
            return None, "Some physical volumes to be assembled were not found in the specified parent."
        
        # 2. Create the new assembly
        assembly_name = self._generate_unique_name(assembly_name_suggestion, state.assemblies)
        new_assembly = Assembly(name=assembly_name)
        
        # 3. Move the PVs from the parent LV to the new assembly
        new_assembly.placements = pvs_to_move
        parent_lv.content = pvs_to_keep

        # 4. Add the assembly to the project state
        state.add_assembly(new_assembly)

        # 5. Create a new physical volume to place the assembly back into the parent LV
        assembly_pv_name = self._generate_unique_name(f"{assembly_name}_placement", 
                                                      {pv.name for pv in parent_lv.content})
        assembly_placement = PhysicalVolumePlacement(
            name=assembly_pv_name,
            volume_ref=assembly_name,
            position_val_or_ref={'x': '0', 'y': '0', 'z': '0'}, # Place at origin of parent
            rotation_val_or_ref={'x': '0', 'y': '0', 'z': '0'}
        )
        parent_lv.add_child(assembly_placement)

        # 6. Recalculate and return
        self.recalculate_geometry_state()
        return assembly_placement.to_dict(), None

    def delete_object(self, object_type, object_id):
        if not self.current_geometry_state: return False, "No project loaded"
        
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

        if deleted:
            success, calc_error = self.recalculate_geometry_state()
            # If there's an error during recalculation, it should be reported
            return success, calc_error or error_msg
        else:
            return False, error_msg if error_msg else f"Object {object_type} '{object_id}' not found or cannot be deleted."
          
    def update_physical_volume_transform(self, pv_id, new_position_dict, new_rotation_dict):
        if not self.current_geometry_state or not self.current_geometry_state.world_volume_ref:
            return False, "No project loaded"

        found_pv_object = None
        # Iterate through LVs and Assemblies using the new data model
        all_lvs = list(self.current_geometry_state.logical_volumes.values())
        for lv in all_lvs:
            if lv.content_type == 'physvol':
                for pv in lv.content:
                    if pv.id == pv_id:
                        found_pv_object = pv
                        break
            if found_pv_object: break

        if not found_pv_object:
            all_asms = list(self.current_geometry_state.assemblies.values())
            for asm in all_asms:
                for pv in asm.placements:
                    if pv.id == pv_id:
                        found_pv_object = pv
                        break
                if found_pv_object: break

        if not found_pv_object:
            return False, f"Physical Volume with ID {pv_id} not found"

        if new_position_dict is not None:
            # Directly overwrite the position property with the absolute numeric dictionary.
            # This "breaks the link" to any previous define reference.
            found_pv_object.position = new_position_dict

        if new_rotation_dict is not None:
            found_pv_object.rotation = new_rotation_dict

        success, error_msg = self.recalculate_geometry_state()
        return success, error_msg


    def merge_from_state(self, incoming_state: GeometryState):
        """
        Merges defines, materials, solids, and LVs from an incoming state
        into the current project, handling name conflicts by renaming.
        """
        if not self.current_geometry_state:
            self.current_geometry_state = incoming_state # If current is empty, just adopt it
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

        success, error_msg = self.recalculate_geometry_state()
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
        return success, error_msg

    def import_step_file(self, step_file_stream):
        """
        Processes an uploaded STEP file stream, imports the geometry,
        and merges it into the current project.
        """
        # The parser needs a file path, not a stream. So we save to a temp file.
        with tempfile.NamedTemporaryFile(delete=False, suffix=".step") as temp_f:
            step_file_stream.save(temp_f.name)
            temp_path = temp_f.name

        try:
            # Call the new parser to get a GeometryState object
            imported_state = parse_step_file(temp_path)
            
            # Use the existing merge logic to add the new objects to the project
            success, error_msg = self.merge_from_state(imported_state)
            
            if not success:
                return False, f"Failed to merge STEP geometry: {error_msg}"
                
            self.recalculate_geometry_state()
            return True, None
            
        except Exception as e:
            # Ensure we re-raise the error so the API can catch it
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
        
        # If target_group_name is None, the items are effectively moved to "ungrouped".
        return True, None

    def _find_and_remove_pv(self, pv_id):
        """
        Helper function to find a PV by its ID anywhere in the geometry,
        remove it from its current parent, and return the PV object and its old parent.
        Returns (pv_object, parent_object) or (None, None).
        """
        state = self.current_geometry_state
        # Search in Logical Volumes
        for lv in state.logical_volumes.values():
            if lv.content_type == 'physvol':
                for i, pv in enumerate(lv.content):
                    if pv.id == pv_id:
                        return lv.content.pop(i), lv
        
        # Search in Assemblies
        for asm in state.assemblies.values():
            for i, pv in enumerate(asm.placements):
                if pv.id == pv_id:
                    return asm.placements.pop(i), asm
        
        return None, None

    def move_pv_to_assembly(self, pv_ids, target_assembly_name):
        """Moves a list of PVs from their current parent to a target assembly."""
        state = self.current_geometry_state
        target_assembly = state.assemblies.get(target_assembly_name)
        if not target_assembly:
            return False, f"Target assembly '{target_assembly_name}' not found."

        for pv_id in pv_ids:
            pv_to_move, old_parent = self._find_and_remove_pv(pv_id)
            if not pv_to_move:
                return False, f"Physical Volume with ID '{pv_id}' not found."
            target_assembly.placements.append(pv_to_move)

        self.recalculate_geometry_state()
        return True, None

    def move_pv_to_lv(self, pv_ids, target_lv_name):
        """Moves a list of PVs from their current parent to a target logical volume."""
        state = self.current_geometry_state
        target_lv = state.logical_volumes.get(target_lv_name)
        if not target_lv:
            return False, f"Target logical volume '{target_lv_name}' not found."
        if target_lv.content_type != 'physvol':
            return False, f"Target '{target_lv_name}' is a procedural volume and cannot accept direct placements."

        for pv_id in pv_ids:
            pv_to_move, old_parent = self._find_and_remove_pv(pv_id)
            if not pv_to_move:
                return False, f"Physical Volume with ID '{pv_id}' not found."
            target_lv.content.append(pv_to_move)

        self.recalculate_geometry_state()
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
        return True, None