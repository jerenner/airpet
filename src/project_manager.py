# src/project_manager.py
import json
import math
import tempfile
import os
from .geometry_types import GeometryState, Solid, Define, Material, LogicalVolume, PhysicalVolumePlacement, Assembly
from .gdml_parser import GDMLParser
from .gdml_writer import GDMLWriter
from .step_parser import parse_step_file

class ProjectManager:
    def __init__(self):
        self.current_geometry_state = GeometryState()
        self.gdml_parser = GDMLParser()
        # self.undo_stack = []
        # self.redo_stack = []

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

    def load_gdml_from_string(self, gdml_string):
        self.current_geometry_state = self.gdml_parser.parse_gdml_string(gdml_string)
        # self.undo_stack.clear()
        # self.redo_stack.clear()
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
        # self.undo_stack.clear()
        # self.redo_stack.clear()
        return self.current_geometry_state

    def export_to_gdml_string(self):
        if self.current_geometry_state:
            writer = GDMLWriter(self.current_geometry_state)
            return writer.get_gdml_string()
        return "<?xml version='1.0' encoding='UTF-8'?>\n<gdml />" # Empty GDML
    
    def get_full_project_state_dict(self):
        """ Returns the entire current geometry state as a dictionary. """
        if self.current_geometry_state:
            return self.current_geometry_state.to_dict()
        return {} # Return empty if no state

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
        elif object_type == "physical_volume": # Requires searching
            for lv in self.current_geometry_state.logical_volumes.values():
                for pv in lv.phys_children:
                    if pv.id == object_name_or_id: # Match by unique ID
                        obj = pv
                        break
                if obj: break
        
        return obj.to_dict() if obj else None

    def update_object_property(self, object_type, object_name_or_id_from_frontend, property_path, new_value):
        """
        Updates a property of an object.
        object_name_or_id_from_frontend: unique ID for Solids, LVs, PVs. For Defines/Materials, it's their name.
        property_path: e.g., "name", "parameters.x", "position.x"
        """
        # This needs careful implementation to find the object and update its property.
        # Example for a physical volume's position.x:
        if not self.current_geometry_state: return False
        print(f"Attempting to update: Type='{object_type}', ID/Name='{object_name_or_id_from_frontend}', Path='{property_path}', NewValue='{new_value}'")

        target_obj = None
        # Find the object (this needs to be robust)
        if object_type == "physical_volume":
            for lv_name_key in self.current_geometry_state.logical_volumes: # Iterate through LVs
                lv = self.current_geometry_state.logical_volumes[lv_name_key]
                for pv in lv.phys_children:
                    if pv.id == object_name_or_id_from_frontend:
                        target_obj = pv
                        break
                if target_obj: break
        elif object_type == "solid":
             target_obj = self.current_geometry_state.solids.get(object_name_or_id_from_frontend)
             if not target_obj:
                 print(f"Solid '{object_name_or_id_from_frontend}' not found by name in project_manager.solids.")
             print(f"Target is {target_obj}")
             print(f"All objects are {self.current_geometry_state.solids}")
        elif object_type == "define":
            target_obj = self.current_geometry_state.defines.get(object_name_or_id_from_frontend)
        elif object_type == "material":
            target_obj = self.current_geometry_state.materials.get(object_name_or_id_from_frontend)
        elif object_type == "logical_volume":
            target_obj = self.current_geometry_state.logical_volumes.get(object_name_or_id_from_frontend)

        if not target_obj: 
            print(f"Failed to find target_obj: type='{object_type}', id/name='{object_name_or_id_from_frontend}'")
            if object_type == "solid":
                print(f"Available solids: {list(self.current_geometry_state.solids.keys())}")
            return False

        # Simple path update (e.g., "name", "parameters.x")
        path_parts = property_path.split('.')
        current_level_obj = target_obj
    
        for i, part_key in enumerate(path_parts[:-1]):
            if isinstance(current_level_obj, dict): # If it's a dict like parameters/position
                current_level_obj = current_level_obj[part_key]
            else: # If it's an object
                current_level_obj = getattr(current_level_obj, part_key)
        
        final_key = path_parts[-1]

        # --- Type Coercion ---
        old_value = current_level_obj.get(final_key) if isinstance(current_level_obj, dict) else getattr(current_level_obj, final_key, None)
        converted_value = new_value

        # --- SPECIAL CASE for PV transform properties ---
        # These properties are allowed to be either a string (reference) or a dict (absolute value).
        # We should not try to coerce a string reference into a dict.
        if object_type == 'physical_volume' and final_key in ['position', 'rotation', 'scale']:
            if isinstance(new_value, str) or isinstance(new_value, dict):
                converted_value = new_value # Accept either type as is
            else:
                return False, f"Invalid value type for PV transform: {type(new_value)}"
        
        # --- GENERAL CASE for other properties ---
        elif old_value is not None and not isinstance(new_value, type(old_value)):
            target_type = type(old_value)
            try:
                # If the target is a numeric type (int or float), always
                # convert the new value to float to avoid integer truncation.
                if target_type in [int, float]:
                    converted_value = float(new_value)
                elif target_type == dict:
                    if isinstance(new_value, str):
                        import ast
                        converted_value = ast.literal_eval(new_value)
                    else:
                        converted_value = new_value
                # Add other specific type checks here if needed
            except (ValueError, TypeError, SyntaxError) as e:
                print(f"Update failed: Could not convert new value '{new_value}' to target type '{target_type}'. Error: {e}")
                return False, f"Invalid value format for property '{final_key}'."

        # Set the value
        if isinstance(current_level_obj, dict):
            current_level_obj[final_key] = converted_value
        else:
            setattr(current_level_obj, final_key, converted_value)
        
        print(f"Successfully updated {object_type}:{object_name_or_id_from_frontend} -> {property_path}")
        return True, None # Return success

    def add_define(self, name_suggestion, define_type, value_dict, unit=None, category=None):
        if not self.current_geometry_state: return None, "No project loaded"
        name = self._generate_unique_name(name_suggestion, self.current_geometry_state.defines)
        
        # Value dict for pos/rot needs conversion if units are external
        # Assuming 'value_dict' comes with values already in a format that Define expects
        # or that Define constructor handles necessary conversions based on unit/category
        new_define = Define(name, define_type, value_dict, unit, category)
        self.current_geometry_state.add_define(new_define)
        return new_define.to_dict(), None

    def update_define(self, define_name, new_value, new_unit=None, new_category=None):
        if not self.current_geometry_state:
            return False, "No project loaded."
        
        target_define = self.current_geometry_state.defines.get(define_name)
        if not target_define:
            return False, f"Define '{define_name}' not found."

        target_define.value = new_value
        if new_unit:
            target_define.unit = new_unit
        if new_category:
            target_define.category = new_category

        return True, None

    def add_material(self, name_suggestion, properties_dict):
        if not self.current_geometry_state: return None, "No project loaded"
        name = self._generate_unique_name(name_suggestion, self.current_geometry_state.materials)
        new_material = Material(name, **properties_dict)
        self.current_geometry_state.add_material(new_material)
        return new_material.to_dict(), None

    def update_material(self, mat_name, new_properties):
        if not self.current_geometry_state: return False, "No project loaded"
        target_mat = self.current_geometry_state.materials.get(mat_name)
        if not target_mat: return False, f"Material '{mat_name}' not found."

        # Update properties from the provided dictionary
        if 'density' in new_properties: target_mat.density = new_properties['density']
        if 'Z' in new_properties: target_mat.Z = new_properties['Z']
        if 'A' in new_properties: target_mat.A = new_properties['A']
        if 'components' in new_properties: target_mat.components = new_properties['components']
        
        return True, None

    def add_solid(self, name_suggestion, solid_type, parameters_dict):
        """
        Adds a new solid to the project.
        The parameters_dict comes directly from the frontend UI. This method
        is responsible for any conversions (e.g., full-length to half-length).
        """
        if not self.current_geometry_state:
            return None, "No project loaded"

        if solid_type == "boolean":
            return None, f"'{solid_type}' should be created via the boolean editor endpoint."

        name = self._generate_unique_name(name_suggestion, self.current_geometry_state.solids)
        
        # This will hold the parameters in the internal format (what G4/our renderer expects)
        internal_params = {}
        
        # --- Centralized parameter handling ---
        p = parameters_dict # for brevity
        
        try:
            if solid_type == "box":
                # Box params are already 1-to-1 with G4Box half-lengths in the UI for simplicity,
                # but if the UI sent full lengths, we would divide by 2 here. Let's assume the UI sends full lengths.
                internal_params = {
                    'x': float(p.get('x', 100)),
                    'y': float(p.get('y', 100)),
                    'z': float(p.get('z', 100))
                }
            elif solid_type == "tube":
                internal_params = {
                    'rmin': float(p.get('rmin', 0)),
                    'rmax': float(p.get('rmax', 50)),
                    'dz': float(p.get('dz', 200)) / 2.0, # UI sends full length, store half
                    'startphi': math.radians(float(p.get('startphi', 0))),
                    'deltaphi': math.radians(float(p.get('deltaphi', 360)))
                }
            elif solid_type == "cone":
                internal_params = {
                    'rmin1': float(p.get('rmin1', 0)),
                    'rmax1': float(p.get('rmax1', 50)),
                    'rmin2': float(p.get('rmin2', 0)),
                    'rmax2': float(p.get('rmax2', 75)),
                    'dz': float(p.get('dz', 200)) / 2.0, # UI sends full length, store half
                    'startphi': math.radians(float(p.get('startphi', 0))),
                    'deltaphi': math.radians(float(p.get('deltaphi', 360)))
                }
            elif solid_type == "sphere":
                # Backend directly uses the parameters from the UI
                internal_params = {
                    'rmin': float(p.get('rmin', 0)),
                    'rmax': float(p.get('rmax', 100)),
                    'startphi': math.radians(float(p.get('startphi', 0))),
                    'deltaphi': math.radians(float(p.get('deltaphi', 360))),
                    'starttheta': math.radians(float(p.get('starttheta', 0))),
                    'deltatheta': math.radians(float(p.get('deltatheta', 180)))
                }
            elif solid_type == "orb":
                internal_params = {'r': float(p.get('r', 100))}
            elif solid_type == "torus":
                internal_params = {
                    'rmin': float(p.get('rmin', 20)),
                    'rmax': float(p.get('rmax', 30)),
                    'rtor': float(p.get('rtor', 100)),
                    'startphi': math.radians(float(p.get('startphi', 0))),
                    'deltaphi': math.radians(float(p.get('deltaphi', 360)))
                }
            elif solid_type == "trd":
                internal_params = {
                    'dx1': float(p.get('dx1', 50)), # UI sends half-length
                    'dx2': float(p.get('dx2', 75)),
                    'dy1': float(p.get('dy1', 50)),
                    'dy2': float(p.get('dy2', 75)),
                    'dz': float(p.get('dz', 100)),  # UI sends half-length
                }
            elif solid_type == "para":
                 internal_params = {
                    'dx': float(p.get('dx', 50)), # UI sends half-length
                    'dy': float(p.get('dy', 60)),
                    'dz': float(p.get('dz', 70)),
                    'alpha': math.radians(float(p.get('alpha', 0))),
                    'theta': math.radians(float(p.get('theta', 0))),
                    'phi': math.radians(float(p.get('phi', 0)))
                }
            elif solid_type == "eltube":
                internal_params = {
                    'dx': float(p.get('dx', 50)), # semi-axis
                    'dy': float(p.get('dy', 75)),
                    'dz': float(p.get('dz', 100))  # half-length
                }
            # Add other primitive solids here following the same pattern
            else:
                return None, f"Solid type '{solid_type}' is not supported for creation."

        except (ValueError, TypeError) as e:
            return None, f"Invalid parameter type for solid '{solid_type}': {e}"

        new_solid = Solid(name, solid_type, internal_params)
        self.current_geometry_state.add_solid(new_solid)
        print(f"Added Solid: {name} with params {internal_params}")
        
        return new_solid.to_dict(), None

    def add_boolean_solid(self, name_suggestion, recipe):
        """
        Creates a single 'virtual' boolean solid that stores the recipe.
        """
        if not self.current_geometry_state: return False, "No project loaded."
        if len(recipe) < 2 or recipe[0].get('op') != 'base':
            return False, "Invalid recipe format."

        # Validate that all referenced solids exist
        for item in recipe:
            ref = item.get('solid_ref')
            if not ref or ref not in self.current_geometry_state.solids:
                return False, f"Solid '{ref}' not found in project."

        name = self._generate_unique_name(name_suggestion, self.current_geometry_state.solids)
        params = {"recipe": recipe}
        new_solid = Solid(name, "boolean", params)
        self.current_geometry_state.add_solid(new_solid)
        
        return True, None

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

        target_solid.parameters['recipe'] = new_recipe
        return True, None
    
    def add_solid_object(self, solid_obj):
        """Helper to add an already-created Solid object."""
        self.current_geometry_state.solids[solid_obj.name] = solid_obj

    def add_solid_and_place(self, solid_params, lv_params, pv_params):
        """
        A high-level method to perform the full Solid -> LV -> PV chain.
        This makes the operation atomic from the backend's perspective.
        """
        if not self.current_geometry_state:
            return False, "No project loaded."

        # --- 1. Add the Solid ---
        solid_name_sugg = solid_params['name']
        solid_type = solid_params['type']
        solid_actual_params = solid_params['params']
        
        new_solid_dict, solid_error = self.add_solid(solid_name_sugg, solid_type, solid_actual_params)
        if solid_error:
            return False, f"Failed to create solid: {solid_error}"
        
        new_solid_name = new_solid_dict['name']

        # --- 2. Add the Logical Volume (if requested) ---
        if not lv_params:
            # If no LV params, we're done. Just created a solid.
            return True, None
            
        lv_name_sugg = lv_params.get('name', f"{new_solid_name}_lv")
        material_ref = lv_params.get('material_ref')

        new_lv_dict, lv_error = self.add_logical_volume(lv_name_sugg, new_solid_name, material_ref)
        if lv_error:
            # Here you might want to "roll back" the solid creation, but for now we'll leave it.
            return False, f"Failed to create logical volume: {lv_error}"
            
        new_lv_name = new_lv_dict['name']

        # --- 3. Add the Physical Volume Placement (if requested) ---
        if not pv_params:
            # If no PV params, we're done. Created a solid and an LV.
            return True, None
            
        parent_lv_name = pv_params.get('parent_lv_name')
        pv_name_sugg = pv_params.get('name', f"{new_lv_name}_placement")
        # For quick-add, we assume placement at the origin of the parent.
        position = {'x': 0, 'y': 0, 'z': 0} 
        rotation = {'x': 0, 'y': 0, 'z': 0}

        new_pv_dict, pv_error = self.add_physical_volume(parent_lv_name, pv_name_sugg, new_lv_name, position, rotation)
        if pv_error:
            return False, f"Failed to place physical volume: {pv_error}"
        
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
            
        return True, None

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
            return True, None
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
            if isinstance(found_pv_object.position, str):
                define_name = found_pv_object.position
                position_define = self.current_geometry_state.defines.get(define_name)
                if position_define and position_define.type == 'position':
                    position_define.value = new_position_dict
                else: # was a ref, but define not found; overwrite with values
                    found_pv_object.position = new_position_dict
            else: # was already a dict of values
                found_pv_object.position = new_position_dict

        if new_rotation_dict is not None:
            if isinstance(found_pv_object.rotation, str):
                define_name = found_pv_object.rotation
                rotation_define = self.current_geometry_state.defines.get(define_name)
                if rotation_define and rotation_define.type == 'rotation':
                    rotation_define.value = new_rotation_dict
                else:
                    found_pv_object.rotation = new_rotation_dict
            else:
                found_pv_object.rotation = new_rotation_dict

        return True, None


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

        return True, None

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

        return True, None

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
                
            return True, None
            
        except Exception as e:
            # Ensure we re-raise the error so the API can catch it
            raise e
        finally:
            # Clean up the temporary file
            os.unlink(temp_path)
