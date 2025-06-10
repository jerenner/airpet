# src/project_manager.py
import json
import math
from .geometry_types import GeometryState, Solid, Define, Material, LogicalVolume, PhysicalVolumePlacement
from .gdml_parser import GDMLParser
from .gdml_writer import GDMLWriter

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
        object_id: unique ID for Solids, LVs, PVs. For Defines/Materials, it's their name.
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
        
        try:
            for i, part_key in enumerate(path_parts[:-1]):
                if isinstance(current_level_obj, dict): # If it's a dict like parameters/position
                    current_level_obj = current_level_obj[part_key]
                else: # If it's an object
                    current_level_obj = getattr(current_level_obj, part_key)
            
            final_key = path_parts[-1]

            # Type conversion for the new value
            converted_value = new_value
            # Get current value to infer type if possible
            current_value_for_type_inference = None
            if isinstance(current_level_obj, dict):
                current_value_for_type_inference = current_level_obj.get(final_key)
            else: # Is an object
                current_value_for_type_inference = getattr(current_level_obj, final_key, None)

            if current_value_for_type_inference is not None and not isinstance(new_value, type(current_value_for_type_inference)):
                try:
                    converted_value = type(current_value_for_type_inference)(new_value)
                    print(f"Converted '{new_value}' ({type(new_value)}) to '{converted_value}' ({type(converted_value)})")
                except (ValueError, TypeError) as e:
                    print(f"Warning: Could not convert '{new_value}' to type '{type(current_value_for_type_inference)}' for property '{property_path}'. Error: {e}. Using as string or original type.")
                    # Fallback to string if number conversion fails but original was not number
                    if not isinstance(current_value_for_type_inference, (int, float)) and isinstance(new_value, str):
                        converted_value = new_value 
                    # else keep new_value as is if conversion fails and original was number. Or reject.
            
            if isinstance(current_level_obj, dict):
                current_level_obj[final_key] = converted_value
            else: # Is an object
                setattr(current_level_obj, final_key, converted_value)
            
            print(f"Successfully updated {object_type} '{object_name_or_id_from_frontend}': {property_path} to {converted_value}")
            # TODO: Add to Undo stack
            return True
        except (AttributeError, KeyError, IndexError, TypeError) as e:
            print(f"Error during property update for {object_type} '{object_name_or_id_from_frontend}', path '{property_path}': {e}")
            # import traceback
            # traceback.print_exc()
            return False

    def add_define(self, name_suggestion, define_type, value_dict, unit=None, category=None):
        if not self.current_geometry_state: return None, "No project loaded"
        name = self._generate_unique_name(name_suggestion, self.current_geometry_state.defines)
        
        # Value dict for pos/rot needs conversion if units are external
        # Assuming 'value_dict' comes with values already in a format that Define expects
        # or that Define constructor handles necessary conversions based on unit/category
        new_define = Define(name, define_type, value_dict, unit, category)
        self.current_geometry_state.add_define(new_define)
        return new_define.to_dict(), None

    def add_material(self, name_suggestion, properties_dict):
        if not self.current_geometry_state: return None, "No project loaded"
        name = self._generate_unique_name(name_suggestion, self.current_geometry_state.materials)
        # properties_dict might contain 'density', 'state', 'components', etc.
        new_material = Material(name, **properties_dict)
        self.current_geometry_state.add_material(new_material)
        print(f"Added Material: {name}")
        # TODO: Add to Undo stack
        return new_material.to_dict(), None

    def add_solid(self, name_suggestion, solid_type, parameters_dict):
        """
        Adds a new solid to the project.
        The parameters_dict comes directly from the frontend UI. This method
        is responsible for any conversions (e.g., full-length to half-length).
        """
        if not self.current_geometry_state:
            return None, "No project loaded"

        name = self._generate_unique_name(name_suggestion, self.current_geometry_state.solids)
        
        # This will hold the parameters in the internal format (what G4/our renderer expects)
        internal_params = {}
        
        # --- NEW: Centralized parameter handling ---
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
                    'startphi': float(p.get('startphi', 0)),
                    'deltaphi': float(p.get('deltaphi', 2 * math.pi))
                }
            elif solid_type == "cone":
                internal_params = {
                    'rmin1': float(p.get('rmin1', 0)),
                    'rmax1': float(p.get('rmax1', 50)),
                    'rmin2': float(p.get('rmin2', 0)),
                    'rmax2': float(p.get('rmax2', 75)),
                    'dz': float(p.get('dz', 200)) / 2.0, # UI sends full length, store half
                    'startphi': float(p.get('startphi', 0)),
                    'deltaphi': float(p.get('deltaphi', 2 * math.pi))
                }
            elif solid_type == "sphere":
                # Backend directly uses the parameters from the UI
                internal_params = {
                    'rmin': float(p.get('rmin', 0)),
                    'rmax': float(p.get('rmax', 100)),
                    'startphi': float(p.get('startphi', 0)),
                    'deltaphi': float(p.get('deltaphi', 2 * math.pi)),
                    'starttheta': float(p.get('starttheta', 0)),
                    'deltatheta': float(p.get('deltatheta', math.pi))
                }
            # Add other primitive solids here following the same pattern
            # ...
            else:
                return None, f"Solid type '{solid_type}' is not supported for creation."

        except (ValueError, TypeError) as e:
            return None, f"Invalid parameter type for solid '{solid_type}': {e}"

        new_solid = Solid(name, solid_type, internal_params)
        self.current_geometry_state.add_solid(new_solid)
        print(f"Added Solid: {name} with params {internal_params}")
        
        return new_solid.to_dict(), None
    
    def add_logical_volume(self, name_suggestion, solid_ref_name, material_ref_name):
        if not self.current_geometry_state: return None, "No project loaded"
        if solid_ref_name not in self.current_geometry_state.solids:
            return None, f"Solid '{solid_ref_name}' not found."
        if material_ref_name not in self.current_geometry_state.materials:
            return None, f"Material '{material_ref_name}' not found."

        name = self._generate_unique_name(name_suggestion, self.current_geometry_state.logical_volumes)
        new_lv = LogicalVolume(name, solid_ref_name, material_ref_name)
        self.current_geometry_state.add_logical_volume(new_lv)
        print(f"Added Logical Volume: {name}")
        return new_lv.to_dict(), None

    def add_physical_volume(self, parent_lv_name, pv_name_suggestion,
                            placed_lv_name, position_dict, rotation_dict, copy_number=0):
        if not self.current_geometry_state: return None, "No project loaded"
        
        parent_lv = self.current_geometry_state.logical_volumes.get(parent_lv_name)
        if not parent_lv:
            return None, f"Parent Logical Volume '{parent_lv_name}' not found."
        if placed_lv_name not in self.current_geometry_state.logical_volumes:
             return None, f"Placed Logical Volume '{placed_lv_name}' not found."

        # Generate a unique name for this PV *within its parent* (GDML PV names are not global)
        # For simplicity, we'll use a globally unique suggested name for now.
        # A better approach for pv_name would be to ensure it's unique among siblings.
        pv_name = pv_name_suggestion # Assume caller suggests a reasonable one

        # position_dict and rotation_dict are assumed to be {'x':val,...} in internal units
        new_pv = PhysicalVolumePlacement(pv_name, placed_lv_name, copy_number,
                                         position_val_or_ref=position_dict,
                                         rotation_val_or_ref=rotation_dict)
        parent_lv.add_child(new_pv)
        print(f"Added Physical Volume: {pv_name} into {parent_lv_name}")
        return new_pv.to_dict(), None


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

    # --- Placeholder for Command Pattern / Undo-Redo ---
    # def execute_command(self, command):
    #     command.execute(self.current_geometry_state)
    #     self.undo_stack.append(command)
    #     self.redo_stack.clear() # Any new action clears the redo stack

    # def undo(self):
    #     if not self.undo_stack: return False
    #     command = self.undo_stack.pop()
    #     command.undo(self.current_geometry_state)
    #     self.redo_stack.append(command)
    #     return True

    # def redo(self):
    #     if not self.redo_stack: return False
    #     command = self.redo_stack.pop()
    #     command.execute(self.current_geometry_state)
    #     self.undo_stack.append(command)
    #     return True

          
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

    
    # def update_physical_volume_transform(self, pv_id, new_position_dict, new_rotation_dict):
    #     """
    #     Updates position and/or rotation of a PhysicalVolumePlacement.
    #     This is typically called after a drag/rotate operation.
    #     """
    #     if not self.current_geometry_state or not self.current_geometry_state.world_volume_ref:
    #         return False, "No project loaded"

    #     found_pv = False
    #     def find_and_update(lv_name_key):
    #         nonlocal found_pv
    #         lv = self.current_geometry_state.logical_volumes.get(lv_name_key)
    #         if not lv: return

    #         for pv_placement in lv.phys_children:
    #             if pv_placement.id == pv_id: # Match by unique UUID
    #                 if new_position_dict is not None:
    #                     # old_pos = pv_placement.position # For undo command
    #                     pv_placement.position = new_position_dict
    #                 if new_rotation_dict is not None:
    #                     # old_rot = pv_placement.rotation # For undo command
    #                     pv_placement.rotation = new_rotation_dict
    #                 found_pv = True
    #                 # TODO: Create and store an UndoCommand for this change
    #                 return
    #             # Recursively search children if not found yet.
    #             # Note: This is a *flat* search if PVs are only direct children of LVs.
    #             # If PVs can place other PVs (GDML has recursive placements!), this needs proper recursion.
    #             # Our current PV structure is flat: PVs are children of LV, not PVs.
    #             # So this direct search is fine if we assume a flat PV structure.
    #             # If PVs can place LVs that in turn have PV children, that implies a need for deeper PV ID lookup.
    #             # The hierarchy is LV -> PVs -> LV -> PVs. So we need to traverse LVs recursively for all PVs.
    #             # No, pv_placement.volume_ref is the LV it places. You iterate that LV's children.
    #             # Correct recursion:
    #             # if not found_pv and pv_placement.volume_ref in self.current_geometry_state.logical_volumes:
    #             #    find_and_update(pv_placement.volume_ref)
    #             if found_pv: return # Stop searching if found

    #     find_and_update(self.current_geometry_state.world_volume_ref)
    #     return found_pv, None

    # --- Example Modification ---
    # def update_object_position(self, object_id, new_position_dict):
    #     # This is a simplified update. A command pattern would be better.
    #     # object_id here would be the ID of a PhysicalVolumePlacement.
    #     # We need to find it in the hierarchy.
        
    #     # For now, let's assume object_id is the name of the physvol for simplicity in threejs_description
    #     # This needs to be more robust using unique IDs.

    #     if not self.current_geometry_state or not self.current_geometry_state.world_volume_ref:
    #         return False
        
    #     found = False
    #     def find_and_update(lv_name):
    #         nonlocal found
    #         lv = self.current_geometry_state.get_logical_volume(lv_name)
    #         if not lv: return

    #         for pv_placement in lv.phys_children:
    #             if pv_placement.id == object_id: # Match by unique ID
    #                 # old_pos = pv_placement.position # For undo command
    #                 pv_placement.position = new_position_dict # new_position_dict should be {'x':val, 'y':val, 'z':val} in mm
    #                 found = True
    #                 # TODO: Create and store an UndoCommand for this change
    #                 return
    #             if not found: # Only recurse if not found yet
    #                 find_and_update(pv_placement.volume_ref)
    #             if found: return # Propagate found up

    #     find_and_update(self.current_geometry_state.world_volume_ref)
    #     return found
