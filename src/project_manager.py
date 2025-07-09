# src/project_manager.py
import json
import math
import tempfile
import os
import asteval
from .geometry_types import GeometryState, Solid, Define, Material, LogicalVolume, PhysicalVolumePlacement, Assembly, get_unit_value
from .gdml_parser import GDMLParser
from .gdml_writer import GDMLWriter
from .step_parser import parse_step_file

class ProjectManager:
    def __init__(self):
        self.current_geometry_state = GeometryState()
        self.gdml_parser = GDMLParser()

    def _generate_unique_name(self, base_name, existing_names_dict):
        if base_name not in existing_names_dict:
            return base_name
        i = 1
        while f"{base_name}_{i}" in existing_names_dict:
            i += 1
        return f"{base_name}_{i}"

    def _get_next_copy_number(self, parent_lv: LogicalVolume):
        """Finds the highest copy number among children and returns the next one."""
        if not parent_lv.phys_children:
            return 1
        max_copy_no = 0
        for pv in parent_lv.phys_children:
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
        aeval = asteval.Interpreter(symtable={}, minimal=True)
        aeval.symtable.update({
            'pi': math.pi, 'PI': math.pi, 'HALFPI': math.pi / 2.0, 'TWOPI': 2.0 * math.pi,
            'mm': 1.0, 'cm': 10.0, 'm': 1000.0, 'rad': 1.0, 'deg': math.pi / 180.0,
        })
        
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
                        unit_factor = get_unit_value(define_obj.unit, define_obj.category) if define_obj.unit else 1.0
                        for axis in ['x', 'y', 'z']:
                            if axis in raw_dict:
                                val_dict[axis] = aeval.eval(str(raw_dict[axis])) * unit_factor
                        define_obj.value = val_dict
                    else: # constant, quantity, expression
                        raw_expr = str(define_obj.raw_expression)
                        unit_factor = get_unit_value(define_obj.unit, define_obj.category) if define_obj.unit else 1.0
                        define_obj.value = aeval.eval(raw_expr) * unit_factor
                    
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


        # --- Stage 3: Evaluate all solid parameters ---
        for solid in state.solids.values():
            solid._evaluated_parameters = {}
            for key, raw_expr in solid.raw_parameters.items():
                if isinstance(raw_expr, str):
                    try:
                        solid._evaluated_parameters[key] = aeval.eval(raw_expr)
                    except Exception as e:
                        print(f"Warning: Could not eval solid param '{key}' for solid '{solid.name}': {e}")
                        solid._evaluated_parameters[key] = 0
                elif isinstance(raw_expr, (int, float)):
                    # Handle cases where the value is already a number
                    solid._evaluated_parameters[key] = raw_expr
                else:
                    # For other types (like a boolean recipe list), just copy it.
                    solid._evaluated_parameters[key] = raw_expr

        # --- Stage 4: Evaluate all placement transforms ---
        # This includes placements inside LVs and inside Assemblies
        all_volumes_with_placements = list(state.logical_volumes.values()) + list(state.assemblies.values())
        for vol in all_volumes_with_placements:
            placements = getattr(vol, 'placements', getattr(vol, 'phys_children', []))
            for pv in placements:
                # Position
                if isinstance(pv.position, str): # It's a reference to a define
                    pv._evaluated_position = aeval.symtable.get(pv.position, {'x':0,'y':0,'z':0})
                elif isinstance(pv.position, dict): # It's a dict of expressions
                    for axis, raw_expr in pv.position.items():
                        pv._evaluated_position[axis] = aeval.eval(str(raw_expr))
                else: # Default case
                    pv._evaluated_position = {'x':0, 'y':0, 'z':0}

                # Rotation
                if isinstance(pv.rotation, str):
                    pv._evaluated_rotation = aeval.symtable.get(pv.rotation, {'x':0,'y':0,'z':0})
                elif isinstance(pv.rotation, dict):
                    for axis, raw_expr in pv.rotation.items():
                        pv._evaluated_rotation[axis] = aeval.eval(str(raw_expr))
                else:
                    pv._evaluated_rotation = {'x':0, 'y':0, 'z':0}

                # Scale
                if isinstance(pv.scale, str):
                    pv._evaluated_scale = aeval.symtable.get(pv.scale, {'x':1,'y':1,'z':1})
                elif isinstance(pv.scale, dict):
                    for axis, raw_expr in pv.scale.items():
                        pv._evaluated_scale[axis] = aeval.eval(str(raw_expr))
                else:
                    pv._evaluated_scale = {'x':1, 'y':1, 'z':1}

        return True, None

    def load_gdml_from_string(self, gdml_string):
        self.current_geometry_state = self.gdml_parser.parse_gdml_string(gdml_string)
        success, error_msg = self.recalculate_geometry_state()
        if not success:
            print(f"Warning after parsing GDML: {error_msg}")
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
        
        obj = None
        if object_type == "define": obj = self.current_geometry_state.defines.get(object_name_or_id)
        elif object_type == "material": obj = self.current_geometry_state.materials.get(object_name_or_id)
        elif object_type == "solid": obj = self.current_geometry_state.solids.get(object_name_or_id)
        elif object_type == "logical_volume": obj = self.current_geometry_state.logical_volumes.get(object_name_or_id)
        elif object_type == "physical_volume":
            # Search all LVs and Assemblies for the PV by its unique ID
            all_containers = list(self.current_geometry_state.logical_volumes.values()) + list(self.current_geometry_state.assemblies.values())
            for container in all_containers:
                placements = getattr(container, 'placements', getattr(container, 'phys_children', []))
                for pv in placements:
                    if pv.id == object_name_or_id:
                        obj = pv
                        break
                if obj: break
        
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
            all_containers = list(self.current_geometry_state.logical_volumes.values()) + list(self.current_geometry_state.assemblies.values())
            for container in all_containers:
                placements = getattr(container, 'placements', getattr(container, 'phys_children', []))
                for pv in placements:
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

    def add_define(self, name_suggestion, define_type, value_dict, unit=None, category=None):
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

        _, pv_error = self.add_physical_volume(parent_lv_name, pv_name_sugg, new_lv_name, position, rotation)
        if pv_error:
            return False, f"Failed to place physical volume: {pv_error}"
        
        self.recalculate_geometry_state()
        return True, None

    def add_logical_volume(self, name_suggestion, solid_ref, material_ref, vis_attributes=None):
        if not self.current_geometry_state: return None, "No project loaded"
        if solid_ref not in self.current_geometry_state.solids:
            return None, f"Solid '{solid_ref}' not found."
        if material_ref not in self.current_geometry_state.materials:
            return None, f"Material '{material_ref}' not found."

        name = self._generate_unique_name(name_suggestion, self.current_geometry_state.logical_volumes)
        new_lv = LogicalVolume(name, solid_ref, material_ref, vis_attributes)
        self.current_geometry_state.add_logical_volume(new_lv)
        self.recalculate_geometry_state()
        return new_lv.to_dict(), None        

    def update_logical_volume(self, lv_name, new_solid_ref, new_material_ref, new_vis_attributes=None):
        if not self.current_geometry_state: return False, "No project loaded"
        
        lv = self.current_geometry_state.logical_volumes.get(lv_name)
        if not lv:
            return False, f"Logical Volume '{lv_name}' not found."

        if new_solid_ref and new_solid_ref not in self.current_geometry_state.solids:
            return False, f"New solid '{new_solid_ref}' not found."
        if new_material_ref and new_material_ref not in self.current_geometry_state.materials:
            return False, f"New material '{new_material_ref}' not found."
            
        if new_solid_ref:
            lv.solid_ref = new_solid_ref
        if new_material_ref:
            lv.material_ref = new_material_ref
        if new_vis_attributes: 
            lv.vis_attributes = new_vis_attributes
        
        self.recalculate_geometry_state()
        return True, None

    def add_physical_volume(self, parent_lv_name, pv_name_suggestion, placed_lv_ref, position, rotation):
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
                                        rotation_val_or_ref=rotation)
        parent_lv.add_child(new_pv)
        print(f"Added Physical Volume: {pv_name} into {parent_lv_name}")

        self.recalculate_geometry_state()
        return new_pv.to_dict(), None

    def update_physical_volume(self, pv_id, new_name, new_position, new_rotation):
        if not self.current_geometry_state: return False, "No project loaded"
        
        # This just uses the existing update_physical_volume_transform and update_object_property
        # For simplicity, we can do it directly here.
        pv_to_update = None
        for lv in self.current_geometry_state.logical_volumes.values():
            for pv in lv.phys_children:
                if pv.id == pv_id:
                    pv_to_update = pv
                    break
            if pv_to_update: break
        
        if not pv_to_update:
            return False, f"Physical Volume with ID '{pv_id}' not found."
            
        if new_name: pv_to_update.name = new_name
        if new_position: pv_to_update.position = new_position
        if new_rotation: pv_to_update.rotation = new_rotation
        
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

    def delete_object(self, object_type, object_id):
        if not self.current_geometry_state: return False, "No project loaded"

        deleted = False
        error_msg = None

        if object_type == "define":
            # TODO: Check for usages of this define
            if object_id in self.current_geometry_state.defines:
                del self.current_geometry_state.defines[object_id]
                deleted = True
        elif object_type == "material":
            # TODO: Check for LVs using this material
            if object_id in self.current_geometry_state.materials:
                del self.current_geometry_state.materials[object_id]
                deleted = True
        elif object_type == "solid":
            # TODO: Check for LVs using this solid
            if object_id in self.current_geometry_state.solids:
                del self.current_geometry_state.solids[object_id]
                deleted = True
        elif object_type == "logical_volume":
            if object_id in self.current_geometry_state.logical_volumes:
                if self.current_geometry_state.world_volume_ref == object_id:
                    error_msg = "Cannot delete the world volume."
                else:
                    del self.current_geometry_state.logical_volumes[object_id]
                    for lv in self.current_geometry_state.logical_volumes.values():
                        lv.phys_children = [pv for pv in lv.phys_children if pv.volume_ref != object_id]
                    deleted = True
        elif object_type == "physical_volume":
            found_pv = False
            for lv in self.current_geometry_state.logical_volumes.values():
                original_len = len(lv.phys_children)
                lv.phys_children = [pv for pv in lv.phys_children if pv.id != object_id]
                if len(lv.phys_children) < original_len:
                    found_pv = True
                    deleted = True
                    break
            if not found_pv: error_msg = "Physical Volume not found."
        
        if deleted:
            success, error_msg = self.recalculate_geometry_state()
            return success, error_msg
        else:
            return False, error_msg if error_msg else f"Object {object_type} '{object_id}' not found or cannot be deleted."            
          
    def update_physical_volume_transform(self, pv_id, new_position_dict, new_rotation_dict):
        if not self.current_geometry_state or not self.current_geometry_state.world_volume_ref:
            return False, "No project loaded"

        found_pv_object = None
        for lv in self.current_geometry_state.logical_volumes.values():
            for pv in lv.phys_children:
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
            lv.phys_children = [] # Clear any placements, as they are not merged
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
        Processes a structured dictionary from the AI, converting units
        and adding new objects and placements.
        """
        if not self.current_geometry_state:
            return False, "No project loaded."

        # --- Centralized Unit Conversion ---
        # A set of all solid parameter keys that represent angles and need conversion
        angle_param_keys = {
            'startphi', 'deltaphi', 'starttheta', 'deltatheta',
            'alpha', 'theta', 'phi', 'inst', 'outst', 'phi_twist', 'twistedangle',
            'alpha1', 'alpha2'
        }

        # 1. Convert rotation 'defines' from degrees to radians
        if "defines" in ai_data:
            for define_data in ai_data.get("defines", {}).values():
                if define_data.get("type") == "rotation":
                    rot_val = define_data.get("value", {})
                    if isinstance(rot_val, dict):
                        for axis in ['x', 'y', 'z']:
                            rot_val[axis] = math.radians(rot_val.get(axis, 0))

        # 2. Convert solid angular parameters from degrees to radians
        if "solids" in ai_data:
            for solid_data in ai_data.get("solids", {}).values():
                params = solid_data.get("parameters", {})
                if not isinstance(params, dict): continue

                for key, value in params.items():
                    if key in angle_param_keys:
                        try:
                            params[key] = math.radians(float(value))
                        except (ValueError, TypeError):
                            # Handle cases where value might not be a number, though it should be.
                            print(f"Warning: Could not convert angle parameter '{key}' with value '{value}' to radians.")
                            pass

                # Special handling for boolean solid recipes
                if solid_data.get("type") == "boolean":
                    recipe = params.get("recipe", [])
                    for item in recipe:
                        transform = item.get("transform")
                        if transform and isinstance(transform.get("rotation"), dict):
                            rot_val = transform["rotation"]
                            for axis in ['x', 'y', 'z']:
                                rot_val[axis] = math.radians(rot_val.get(axis, 0))

        # 3. Convert placement rotations from degrees to radians
        if "placements" in ai_data:
            for placement_data in ai_data.get("placements", []):
                rot_val = placement_data.get("rotation")
                # Only convert if it's an absolute value dict, not a string reference
                if isinstance(rot_val, dict):
                    for axis in ['x', 'y', 'z']:
                        rot_val[axis] = math.radians(rot_val.get(axis, 0))
        
        # --- End of Unit Conversion ---

        creation_data = {
            "defines": ai_data.get("defines", {}),
            "materials": ai_data.get("materials", {}),
            "solids": ai_data.get("solids", {}),
            "logical_volumes": ai_data.get("logical_volumes", {}),
        }
        
        if any(creation_data.values()):
            temp_state = GeometryState.from_dict(creation_data)
            success, error_msg = self.merge_from_state(temp_state)
            if not success:
                return False, f"Failed to merge AI-defined objects: {error_msg}"

        placements = ai_data.get("placements", [])
        if not isinstance(placements, list):
            return False, "AI response had an invalid 'placements' format (must be a list)."

        for pv_data in placements:
            try:
                parent_lv = pv_data['parent_lv_name']
                volume_ref = pv_data['volume_ref']
                pv_name = pv_data.get('pv_name', f"{volume_ref}_pv")
                position = pv_data.get('position', {'x':0, 'y':0, 'z':0})
                rotation = pv_data.get('rotation', {'x':0, 'y':0, 'z':0})
                
                _, pv_error = self.add_physical_volume(parent_lv, pv_name, volume_ref, position, rotation)
                
                if pv_error:
                    return False, f"Failed to place '{volume_ref}' in '{parent_lv}': {pv_error}"
            except KeyError as e:
                return False, f"AI placement data is missing a required key: {e}"
            except Exception as e:
                return False, f"An error occurred during object placement: {e}"

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
