# src/geometry_types.py
import uuid # For unique IDs
import math

# --- Helper for Units (can be expanded) ---
# Geant4 internal units are mm for length, rad for angle
UNIT_FACTORS = {
    "length": {"mm": 1.0, "cm": 10.0, "m": 1000.0},
    "angle": {"rad": 1.0, "deg": math.pi / 180.0}
}
OUTPUT_UNIT_FACTORS = {
    "length": {"mm": 1.0, "cm": 0.1, "m": 0.001},
    "angle": {"rad": 1.0, "deg": 180.0 / math.pi}
}

def convert_to_internal_units(value, unit_str, category="length"):
    if value is None: return None
    try:
        val = float(value)
    except ValueError:
        # Here you might integrate a more complex expression evaluator later
        print(f"Warning: Could not parse '{value}' as float, returning 0.0")
        return 0.0

    if unit_str and category in UNIT_FACTORS and unit_str in UNIT_FACTORS[category]:
        return val * UNIT_FACTORS[category][unit_str]
    return val # Assume already in internal units if unit_str is unknown/None

def convert_from_internal_units(value, target_unit_str, category="length"):
    if value is None: return None
    # Ensure value is float for calculations
    try:
        num_value = float(value)
    except (ValueError, TypeError):
        # If it's already a string (like a ref name), return as is
        # Or handle error if a numerical value was expected but not received
        return str(value)

    if target_unit_str and category in OUTPUT_UNIT_FACTORS and target_unit_str in OUTPUT_UNIT_FACTORS[category]:
        return num_value * OUTPUT_UNIT_FACTORS[category][target_unit_str]
    return num_value

def get_unit_value(unit_str, category="length"):
    # Geant4 internal units are mm, rad
    factors = {
        "length": {"mm": 1.0, "cm": 10.0, "m": 1000.0},
        "angle": {"rad": 1.0, "deg": math.pi / 180.0}
    }
    if unit_str and category in factors and unit_str in factors[category]:
        return factors[category][unit_str]
    return 1.0 # Default multiplier

class Define:
    """Represents a defined entity like position, rotation, or constant."""
    def __init__(self, name, type, value, unit=None, category=None):
        self.id = str(uuid.uuid4())
        self.name = name
        self.type = type # 'position', 'rotation', 'constant', 'matrix'
        self.unit = unit
        self.category = category
        # Value can be a dict for position/rotation, a float for constant, etc.
        if type in ['position', 'rotation'] and isinstance(value, dict):
            self.value = {
                k: convert_to_internal_units(v, unit, category) for k, v in value.items()
            }
        elif type == 'constant':
             self.value = convert_to_internal_units(value, unit, category if category else "dimensionless")
        else:
            self.value = value # For matrices or other complex types

    def to_dict(self):
        return {"id": self.id, "name": self.name, "type": self.type, "value": self.value, "unit": self.unit, "category": self.category}

    @classmethod
    def from_dict(cls, data):
        # Note: Direct value assignment assumes units are already internal in the dict
        instance = cls(data['name'], data['type'], data['value'], data.get('unit'), data.get('category'))
        instance.id = data.get('id', str(uuid.uuid4()))
        return instance


class Material:
    """Represents a material."""
    def __init__(self, name, Z=None, A=None, density=None, state=None, components=None):
        self.id = str(uuid.uuid4())
        self.name = name
        self.Z = Z
        self.A = A # Atomic mass in g/mole
        self.density = density # Density in g/cm3 typically in GDML, store as some consistent internal unit or as parsed.
        self.state = state # 'solid', 'liquid', 'gas'
        self.components = components if components else [] # List of {ref, fraction} dicts

    def to_dict(self):
        return {
            "id": self.id, "name": self.name, "Z": self.Z, "A": self.A,
            "density": self.density, "state": self.state, "components": self.components
        }
    @classmethod
    def from_dict(cls, data):
        instance = cls(data['name'], data.get('Z'), data.get('A'), data.get('density'), data.get('state'), data.get('components'))
        instance.id = data.get('id', str(uuid.uuid4()))
        return instance


class Solid:
    """Base class for solids. Parameters should be in internal units (e.g., mm)."""
    def __init__(self, name, solid_type, parameters):
        self.id = str(uuid.uuid4())
        self.name = name
        self.type = solid_type
        self.parameters = parameters # dict of parameters, e.g., {'x': 100, 'y': 100, 'z': 100}

    def to_dict(self):
        return {"id": self.id, "name": self.name, "type": self.type, "parameters": self.parameters}

    @classmethod
    def from_dict(cls, data):
        # This might need to dispatch to specific solid subclasses if they exist
        instance = cls(data['name'], data['type'], data['parameters'])
        instance.id = data.get('id', str(uuid.uuid4()))
        return instance

# Could have subclasses like BoxSolid(Solid), TubeSolid(Solid) if needed for specific logic

class LogicalVolume:
    """Represents a logical volume."""
    def __init__(self, name, solid_ref, material_ref, vis_attributes=None):
        self.id = str(uuid.uuid4())
        self.name = name
        self.solid_ref = solid_ref # Name/ID of the Solid object
        self.material_ref = material_ref # Name/ID of the Material object
        self.vis_attributes = vis_attributes if vis_attributes is not None else {'color': {'r':0.8, 'g':0.8, 'b':0.8, 'a':0.5}}
        self.phys_children = [] # List of PhysicalVolumePlacement objects

    def add_child(self, placement):
        self.phys_children.append(placement)

    def to_dict(self):
        return {
            "id": self.id, "name": self.name,
            "solid_ref": self.solid_ref,
            "material_ref": self.material_ref,
            "vis_attributes": self.vis_attributes,
            "phys_children": [child.to_dict() for child in self.phys_children]
        }

    @classmethod
    def from_dict(cls, data, all_objects_map=None): # all_objects_map for resolving refs if they are objects not just names
        instance = cls(data['name'], data['solid_ref'], data['material_ref'], data.get('vis_attributes'))
        instance.id = data.get('id', str(uuid.uuid4()))
        instance.phys_children = [
            PhysicalVolumePlacement.from_dict(child_data, all_objects_map)
            for child_data in data.get('phys_children', [])
        ]
        return instance


class PhysicalVolumePlacement:
    """Represents a physical volume placement (physvol)."""
    def __init__(self, name, volume_ref, copy_number=0,
                 position_val_or_ref=None, rotation_val_or_ref=None, scale_val_or_ref=None):
        self.id = str(uuid.uuid4())
        self.name = name
        self.volume_ref = volume_ref # Name/ID of the LogicalVolume being placed
        self.copy_number = copy_number

        # These can store direct values (dict) or a ref_name (str) to a Define object
        self.position = position_val_or_ref if position_val_or_ref else {'x': 0, 'y': 0, 'z': 0}
        self.rotation = rotation_val_or_ref if rotation_val_or_ref else {'x': 0, 'y': 0, 'z': 0} # Euler ZYX in radians
        self.scale = scale_val_or_ref if scale_val_or_ref else {'x': 1, 'y': 1, 'z': 1}

    def to_dict(self):
        return {
            "id": self.id, "name": self.name, "volume_ref": self.volume_ref,
            "copy_number": self.copy_number,
            "position": self.position, "rotation": self.rotation, "scale": self.scale
        }

    @classmethod
    def from_dict(cls, data, all_objects_map=None):
        instance = cls(
            data['name'], data['volume_ref'], data.get('copy_number', 0),
            data.get('position'), data.get('rotation'), data.get('scale')
        )
        instance.id = data.get('id', str(uuid.uuid4()))
        return instance


class GeometryState:
    """Holds the entire geometry definition."""
    def __init__(self, world_volume_ref=None):
        self.defines = {} # name: Define object
        self.materials = {} # name: Material object
        self.solids = {}    # name: Solid object
        self.logical_volumes = {} # name: LogicalVolume object
        self.world_volume_ref = world_volume_ref # Name of the world LogicalVolume

    def add_define(self, define_obj):
        self.defines[define_obj.name] = define_obj
    def add_material(self, material_obj):
        self.materials[material_obj.name] = material_obj
    def add_solid(self, solid_obj):
        self.solids[solid_obj.name] = solid_obj
    def add_logical_volume(self, lv_obj):
        self.logical_volumes[lv_obj.name] = lv_obj
    
    def get_define(self, name): return self.defines.get(name)
    def get_material(self, name): return self.materials.get(name)
    def get_solid(self, name): return self.solids.get(name)
    def get_logical_volume(self, name): return self.logical_volumes.get(name)

    def to_dict(self):
        return {
            "defines": {name: define.to_dict() for name, define in self.defines.items()},
            "materials": {name: material.to_dict() for name, material in self.materials.items()},
            "solids": {name: solid.to_dict() for name, solid in self.solids.items()},
            "logical_volumes": {name: lv.to_dict() for name, lv in self.logical_volumes.items()},
            "world_volume_ref": self.world_volume_ref
        }

    @classmethod
    def from_dict(cls, data):
        instance = cls(data.get('world_volume_ref'))
        instance.defines = {name: Define.from_dict(d) for name, d in data.get('defines', {}).items()}
        instance.materials = {name: Material.from_dict(d) for name, d in data.get('materials', {}).items()}
        instance.solids = {name: Solid.from_dict(d) for name, d in data.get('solids', {}).items()}
        
        # For logical volumes, pass the instance itself to resolve internal refs if needed during from_dict
        instance.logical_volumes = {
            name: LogicalVolume.from_dict(lv_data, instance)
            for name, lv_data in data.get('logical_volumes', {}).items()
        }
        return instance

    def get_threejs_scene_description(self):
        """
        Translates the internal geometry state into the flat list format
        expected by the current Three.js frontend.
        This needs to handle hierarchy and transformations.
        """
        threejs_objects = []
        if not self.world_volume_ref or self.world_volume_ref not in self.logical_volumes:
            return []

        # This map will prevent processing the same LV multiple times in complex hierarchies
        processed_lvs = set()
        
        # We start traversal from the world volume
        volumes_to_process = [self.logical_volumes[self.world_volume_ref]]

        while volumes_to_process:
            lv = volumes_to_process.pop(0)
            if lv.name in processed_lvs:
                continue
            processed_lvs.add(lv.name)

            for pv_placement in lv.phys_children:
                child_lv_name = pv_placement.volume_ref
                child_lv = self.logical_volumes.get(child_lv_name)
                if not child_lv:
                    continue

                if child_lv.name not in processed_lvs:
                    volumes_to_process.append(child_lv)

                solid_obj = self.solids.get(child_lv.solid_ref)
                if not solid_obj:
                    continue

                # Flag to identify the world volume's placements for the renderer
                is_world = (child_lv_name == self.world_volume_ref)
                
                # Resolve position
                position_data = pv_placement.position
                if isinstance(pv_placement.position, str): # It's a ref name
                    pos_define = self.defines.get(pv_placement.position)
                    if pos_define and pos_define.type == 'position':
                        position_data = pos_define.value
                    else:
                        position_data = {'x': 0, 'y': 0, 'z': 0}
                
                # Resolve rotation
                rotation_data = pv_placement.rotation
                if isinstance(pv_placement.rotation, str): # It's a ref name
                    rot_define = self.defines.get(pv_placement.rotation)
                    if rot_define and rot_define.type == 'rotation':
                        rotation_data = rot_define.value
                    else:
                        rotation_data = {'x': 0, 'y': 0, 'z': 0}

                threejs_objects.append({
                    "id": pv_placement.id,
                    "name": pv_placement.name,
                    # This new key directly tells the frontend which solid definition to use
                    "solid_ref_for_threejs": child_lv.solid_ref, 
                    "position": position_data,
                    "rotation": rotation_data,
                    "is_world_volume_placement": is_world,
                    "vis_attributes": child_lv.vis_attributes 
                })
        return threejs_objects
