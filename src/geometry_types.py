# FILE: virtual-pet/src/geometry_types.py

import uuid # For unique IDs
import math
import numpy as np

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
DEFAULT_OUTPUT_LUNIT = "mm"
DEFAULT_OUTPUT_AUNIT = "rad"

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
    def __init__(self, name, type, raw_expression, unit=None, category=None):
        self.id = str(uuid.uuid4())
        self.name = name
        self.type = type # 'position', 'rotation', 'constant', 'quantity'
        self.raw_expression = raw_expression # holds the user-entered string or dict of strings
        self.unit = unit
        self.category = category
        self.value = None # holds the final, evaluated numeric result

    def to_dict(self):
        return {
            "id": self.id, "name": self.name, "type": self.type,
            "raw_expression": self.raw_expression,
            "value": self.value, # The evaluated value
            "unit": self.unit, "category": self.category
        }

    @classmethod
    def from_dict(cls, data):
        # In new projects, raw_expression might be missing, so we create it from value
        raw_expr = data.get('raw_expression')
        if raw_expr is None:
            val = data.get('value')
            if isinstance(val, dict):
                 raw_expr = {k: str(v) for k, v in val.items()}
            else:
                 raw_expr = str(val) if val is not None else '0'

        instance = cls(data['name'], data['type'], raw_expr, data.get('unit'), data.get('category'))
        instance.id = data.get('id', str(uuid.uuid4()))
        instance.value = data.get('value') # Restore evaluated value too
        return instance

class Element:
    """Represents a chemical element, composed of isotopes or defined by Z."""
    def __init__(self, name, formula=None, Z=None, A_expr=None, components=None):
        self.id = str(uuid.uuid4())
        self.name = name
        self.formula = formula
        self.Z = Z # Atomic Number
        self.A_expr = A_expr # Atomic Mass (for simple elements)
        self.components = components if components else [] # For elements made of isotopes

    def to_dict(self):
        return {
            "id": self.id, "name": self.name, "formula": self.formula,
            "Z": self.Z, "A_expr": self.A_expr, "components": self.components
        }

    @classmethod
    def from_dict(cls, data):
        instance = cls(data['name'], data.get('formula'), data.get('Z'),
                       data.get('A_expr'), data.get('components'))
        instance.id = data.get('id', instance.id)
        return instance

class Isotope:
    """Represents a chemical isotope."""
    def __init__(self, name, N, Z, A_expr=None):
        self.id = str(uuid.uuid4())
        self.name = name
        self.N = N # Number of nucleons
        self.Z = Z # Atomic Number
        self.A_expr = A_expr # Atomic Mass

    def to_dict(self):
        return {
            "id": self.id, "name": self.name, "N": self.N,
            "Z": self.Z, "A_expr": self.A_expr
        }

    @classmethod
    def from_dict(cls, data):
        instance = cls(data['name'], data.get('N'), data.get('Z'), data.get('A_expr'))
        instance.id = data.get('id', instance.id)
        return instance

class Material:
    """Represents a material."""
    def __init__(self, name, Z_expr=None, A_expr=None, density_expr="0.0", state=None, components=None):
        self.id = str(uuid.uuid4())
        self.name = name
        
        # --- Store raw expressions ---
        self.Z_expr = Z_expr
        self.A_expr = A_expr 
        self.density_expr = density_expr

        # --- Store evaluated results ---
        self._evaluated_Z = None
        self._evaluated_A = None
        self._evaluated_density = None

        self.state = state 
        self.components = components if components else [] 

    def to_dict(self):
        return {
            "id": self.id, "name": self.name,
            "Z_expr": self.Z_expr, 
            "A_expr": self.A_expr,
            "density_expr": self.density_expr, 
            "_evaluated_Z": self._evaluated_Z,
            "_evaluated_A": self._evaluated_A,
            "_evaluated_density": self._evaluated_density,
            "state": self.state, 
            "components": self.components
        }

    @classmethod
    def from_dict(cls, data):
        Z_expr = data.get('Z_expr', str(data.get('Z', "")))
        A_expr = data.get('A_expr', str(data.get('A', "")))
        density_expr = data.get('density_expr', str(data.get('density', "0.0")))

        instance = cls(data['name'], Z_expr, A_expr, density_expr, data.get('state'), data.get('components'))
        instance.id = data.get('id', str(uuid.uuid4()))
        
        # Restore evaluated values if they exist
        instance._evaluated_Z = data.get('_evaluated_Z')
        instance._evaluated_A = data.get('_evaluated_A')
        instance._evaluated_density = data.get('_evaluated_density')
        
        return instance

class Solid:
    """Base class for solids. Parameters should be in internal units (e.g., mm)."""
    def __init__(self, name, solid_type, raw_parameters):
        self.id = str(uuid.uuid4())
        self.name = name
        self.type = solid_type

        # This dictionary holds the string expressions from the user or GDML file.
        self.raw_parameters = raw_parameters
        ## This dictionary will hold the final numeric values for rendering.
        self._evaluated_parameters = {}

    def to_dict(self):
        return {
            "id": self.id, "name": self.name, "type": self.type,
            "raw_parameters": self.raw_parameters,
            "_evaluated_parameters": self._evaluated_parameters
        }

    @classmethod
    def from_dict(cls, data):
        raw_params = data.get('raw_parameters', {})
        instance = cls(data['name'], data['type'], raw_params)
        instance.id = data.get('id', str(uuid.uuid4()))
        instance._evaluated_parameters = data.get('_evaluated_parameters', {})
        return instance

# Could have subclasses like BoxSolid(Solid), TubeSolid(Solid) if needed for specific logic

class LogicalVolume:
    """Represents a logical volume."""
    def __init__(self, name, solid_ref, material_ref, vis_attributes=None):
        self.id = str(uuid.uuid4())
        self.name = name
        self.solid_ref = solid_ref # Name/ID of the Solid object
        self.material_ref = material_ref # Name/ID of the Material object
        self.vis_attributes = vis_attributes if vis_attributes is not None else {'color': {'r':0.8, 'g':0.8, 'b':0.8, 'a':1.0}}

        # Unified content model for LVs
        self.content_type = 'physvol'  # Default to standard placements
        self.content = []              # If type is 'physvol', this is a list of PhysicalVolumePlacement
                                       # If another type, this will hold a single procedural object

    def add_child(self, placement):
        if isinstance(placement, PhysicalVolumePlacement):
            if self.content_type == 'physvol':
                self.content.append(placement)
        else: # It's a ReplicaVolume, DivisionVolume, etc.
            self.content_type = placement.type
            self.content = placement # Store the single object

    def to_dict(self):
        content_data = None
        if self.content_type == 'physvol':
            content_data = [child.to_dict() for child in self.content]
        elif self.content: # For replica, division, etc.
            content_data = self.content.to_dict()

        return {
            "id": self.id, "name": self.name,
            "solid_ref": self.solid_ref,
            "material_ref": self.material_ref,
            "vis_attributes": self.vis_attributes,
            "content_type": self.content_type, # NEW
            "content": content_data           # NEW
        }

    @classmethod
    def from_dict(cls, data, all_objects_map=None):
        # This method needs to be updated to handle the new structure
        # but we can do that later when we implement JSON loading.
        # For now, this is sufficient for the GDML import flow.
        instance = cls(data['name'], data['solid_ref'], data['material_ref'], data.get('vis_attributes'))
        instance.id = data.get('id', str(uuid.uuid4()))
        instance.content_type = data.get('content_type', 'physvol')
        
        content_data = data.get('content')
        if instance.content_type == 'physvol' and isinstance(content_data, list):
            instance.content = [PhysicalVolumePlacement.from_dict(p) for p in content_data]
        elif content_data: # It's a dict for a single procedural object
            if instance.content_type == 'replica':
                instance.content = ReplicaVolume.from_dict(content_data)
            # Add elif for other types here...
        
        return instance


class PhysicalVolumePlacement:
    """Represents a physical volume placement (physvol)."""
    def __init__(self, name, volume_ref, copy_number_expr="0",
                 position_val_or_ref=None, rotation_val_or_ref=None, scale_val_or_ref=None):
        self.id = str(uuid.uuid4())
        self.name = name
        self.volume_ref = volume_ref
        ## Store copy number as a raw string expression
        self.copy_number_expr = copy_number_expr
        # This will store the final evaluated integer result
        self.copy_number = 0 # Default to 0
        # This stores the raw data: either a define name (string) 
        # or a dictionary of string expressions for absolute values
        self.position = position_val_or_ref
        self.rotation = rotation_val_or_ref
        self.scale = scale_val_or_ref
        # These will store the final numeric results after evaluation
        self._evaluated_position = {'x': 0, 'y': 0, 'z': 0}
        self._evaluated_rotation = {'x': 0, 'y': 0, 'z': 0}
        self._evaluated_scale = {'x': 1, 'y': 1, 'z': 1}

    def get_transform_matrix(self):
        """Returns a 4x4 numpy transformation matrix for this placement."""
        # Note: Assumes position and rotation are resolved value dicts, not refs
        pos = self._evaluated_position
        rot = self._evaluated_rotation # Assumed ZYX Euler in radians
        
        # Create rotation matrices for each axis
        Rx = np.array([[1, 0, 0], [0, math.cos(rot['x']), -math.sin(rot['x'])], [0, math.sin(rot['x']), math.cos(rot['x'])]])
        Ry = np.array([[math.cos(rot['y']), 0, math.sin(rot['y'])], [0, 1, 0], [-math.sin(rot['y']), 0, math.cos(rot['y'])]])
        Rz = np.array([[math.cos(rot['z']), -math.sin(rot['z']), 0], [math.sin(rot['z']), math.cos(rot['z']), 0], [0, 0, 1]])
        
        # Combine rotations (ZYX order)
        R = Rz @ Ry @ Rx
        
        # Create 4x4 transformation matrix
        T = np.eye(4)
        T[:3, :3] = R
        T[:3, 3] = [pos['x'], pos['y'], pos['z']]
        
        return T
    
    @staticmethod
    def decompose_matrix(matrix):
        """Decomposes a 4x4 numpy matrix into position, rotation (rad), and scale dicts."""
        # Position is straightforward
        position = {'x': matrix[0, 3], 'y': matrix[1, 3], 'z': matrix[2, 3]}

        # Extract rotation matrix part
        R = matrix[:3, :3]
        
        # Decompose scale and rotation
        # Note: This simple method assumes no shear.
        sx = np.linalg.norm(R[:, 0])
        sy = np.linalg.norm(R[:, 1])
        sz = np.linalg.norm(R[:, 2])
        scale = {'x': sx, 'y': sy, 'z': sz}

        # Normalize rotation matrix to remove scaling
        Rs = np.array([R[:, 0]/sx, R[:, 1]/sy, R[:, 2]/sz]).T

        # Calculate Euler angles (ZYX order)
        sy_val = math.sqrt(Rs[0,0] * Rs[0,0] +  Rs[1,0] * Rs[1,0])
        singular = sy_val < 1e-6

        if not singular:
            x = math.atan2(Rs[2,1] , Rs[2,2])
            y = math.atan2(-Rs[2,0], sy_val)
            z = math.atan2(Rs[1,0], Rs[0,0])
        else:
            x = math.atan2(-Rs[1,2], Rs[1,1])
            y = math.atan2(-Rs[2,0], sy_val)
            z = 0
            
        rotation = {'x': x, 'y': y, 'z': z}

        return position, rotation, scale

    def to_dict(self):
        return {
            "id": self.id, "name": self.name, "volume_ref": self.volume_ref, 
            "copy_number_expr": self.copy_number_expr,
            "copy_number": self.copy_number,
            "position": self.position, "rotation": self.rotation, "scale": self.scale,
            "_evaluated_position": self._evaluated_position, 
            "_evaluated_rotation": self._evaluated_rotation, 
            "_evaluated_scale": self._evaluated_scale
        }

    @classmethod
    def from_dict(cls, data, all_objects_map=None):
        copy_expr = data.get('copy_number_expr', str(data.get('copy_number', '0')))
        instance = cls(data['name'], data['volume_ref'], data.get('copy_number', 0), data.get('position'), data.get('rotation'), data.get('scale'))
        instance.id = data.get('id', str(uuid.uuid4()))
        instance.copy_number = data.get('copy_number', 0)
        instance._evaluated_position = data.get('_evaluated_position', {'x':0, 'y':0, 'z':0})
        instance._evaluated_rotation = data.get('_evaluated_rotation', {'x':0, 'y':0, 'z':0})
        instance._evaluated_scale = data.get('_evaluated_scale', {'x':1, 'y':1, 'z':1})
        return instance

class Assembly:
    """Represents a collection of placed logical volumes."""
    def __init__(self, name):
        self.id = str(uuid.uuid4())
        self.name = name
        self.placements = [] # List of PhysicalVolumePlacement objects

    def add_placement(self, placement):
        self.placements.append(placement)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "placements": [p.to_dict() for p in self.placements]
        }
    
    @classmethod
    def from_dict(cls, data):
        instance = cls(data['name'])
        instance.id = data.get('id', str(uuid.uuid4()))
        instance.placements = [PhysicalVolumePlacement.from_dict(p) for p in data.get('placements', [])]
        return instance

class DivisionVolume:
    """Represents a <divisionvol> placement."""
    def __init__(self, name, volume_ref, axis, number=0, width=0.0, offset=0.0, unit="mm"):
        self.id = str(uuid.uuid4())
        self.name = name  # Not in GDML spec, but useful for our UI
        self.type = "division"
        self.volume_ref = volume_ref
        self.axis = axis # kXAxis, kYAxis, etc.
        self.number = number
        self.width = width
        self.offset = offset
        self.unit = unit

    def to_dict(self):
        return {
            "id": self.id, "name": self.name, "type": self.type,
            "volume_ref": self.volume_ref, "axis": self.axis,
            "number": self.number, "width": self.width, "offset": self.offset,
            "unit": self.unit
        }
    
    @classmethod
    def from_dict(cls, data):
        # We assume name will be generated if not present
        name = data.get('name', f"division_{data.get('id', uuid.uuid4().hex[:6])}")
        return cls(name, data['volume_ref'], data['axis'], data.get('number'), 
                   data.get('width'), data.get('offset'), data.get('unit'))

class ReplicaVolume:
    """Represents a <replicavol> placement."""
    def __init__(self, name, volume_ref, number, direction, width=0.0, offset=0.0):
        self.id = str(uuid.uuid4())
        self.name = name
        self.type = "replica"
        self.volume_ref = volume_ref
        self.number = number
        self.direction = direction # dict like {'x':1, 'y':0, ...}
        self.width = width
        self.offset = offset

    def to_dict(self):
        return {
            "id": self.id, "name": self.name, "type": self.type,
            "volume_ref": self.volume_ref, "number": self.number,
            "direction": self.direction, "width": self.width, "offset": self.offset
        }

    @classmethod
    def from_dict(cls, data):
        """Creates a ReplicaVolume instance from a dictionary."""
        # A name might not be present in the data from the frontend, so we generate one.
        name = data.get('name', f"replica_{data.get('id', uuid.uuid4().hex[:6])}")
        
        # Ensure default values are handled correctly if keys are missing
        number = data.get('number', "1")
        direction = data.get('direction', {'x': '1', 'y': '0', 'z': '0'})
        width = data.get('width', "0.0")
        offset = data.get('offset', "0.0")
        volume_ref = data.get('volume_ref')

        if not volume_ref:
            # This would be an invalid state, but we can handle it gracefully.
            raise ValueError("ReplicaVolume content data is missing 'volume_ref'")

        instance = cls(name, volume_ref, number, direction, width, offset)
        instance.id = data.get('id', instance.id) # Use provided ID if it exists
        return instance

class Parameterisation:
    """Represents a single <parameters> block for a parameterised volume."""
    def __init__(self, number, position, dimensions_type, dimensions):
        self.number = number
        self.position = position
        self.dimensions_type = dimensions_type # e.g., "box_dimensions"
        self.dimensions = dimensions # A dict of the dimension attrs, e.g. {'x':'10', 'y':'10'}

    def to_dict(self):
        return {
            "number": self.number,
            "position": self.position,
            "dimensions_type": self.dimensions_type,
            "dimensions": self.dimensions
        }

    @classmethod
    def from_dict(cls, data):
        return cls(data.get('number'),
                   data.get('position'),
                   data.get('dimensions_type'),
                   data.get('dimensions'))

class ParamVolume:
    """Represents a <paramvol> placement."""
    def __init__(self, name, volume_ref, ncopies):
        self.id = str(uuid.uuid4())
        self.name = name
        self.type = "parameterised"
        self.volume_ref = volume_ref
        self.ncopies = ncopies
        self.parameters = [] # This will be a list of Parameterisation objects

    def add_parameter_set(self, param_set):
        self.parameters.append(param_set)

    def to_dict(self):
        return {
            "id": self.id, "name": self.name, "type": self.type,
            "volume_ref": self.volume_ref, "ncopies": self.ncopies,
            "parameters": [p.to_dict() for p in self.parameters]
        }

    @classmethod
    def from_dict(cls, data):
        # The name is not in the content block, but passed separately.
        # We can use a placeholder.
        name = data.get('name', f"param_{uuid.uuid4().hex[:6]}")
        instance = cls(name, data.get('volume_ref'), data.get('ncopies'))
        
        # Deserialize the list of parameter blocks
        param_data_list = data.get('parameters', [])
        instance.parameters = [Parameterisation.from_dict(p_data) for p_data in param_data_list]
        
        # Ensure ID is preserved if it exists
        if 'id' in data:
            instance.id = data['id']

        return instance

class OpticalSurface:
    """Represents an <opticalsurface> property set."""
    def __init__(self, name, model='glisur', finish='polished', surf_type='dielectric_dielectric', value='1.0'):
        self.id = str(uuid.uuid4())
        self.name = name
        self.model = model
        self.finish = finish
        self.type = surf_type
        self.value = value
        self.properties = {} # Dict to hold property vectors, e.g., {'REFLECTIVITY': 'reflectivity_matrix'}

    def to_dict(self):
        return {
            "id": self.id, "name": self.name, "model": self.model,
            "finish": self.finish, "type": self.type, "value": self.value,
            "properties": self.properties
        }

    @classmethod
    def from_dict(cls, data):
        instance = cls(data['name'], data.get('model', 'glisur'), data.get('finish', 'polished'),
                       data.get('type', 'dielectric_dielectric'), data.get('value', '1.0'))
        instance.id = data.get('id', instance.id)
        instance.properties = data.get('properties', {})
        return instance

class SkinSurface:
    """Represents a <skinsurface> link."""
    def __init__(self, name, volume_ref, surfaceproperty_ref):
        self.id = str(uuid.uuid4())
        self.name = name
        self.type = "skin" # For UI identification
        self.volume_ref = volume_ref # Name of the LogicalVolume
        self.surfaceproperty_ref = surfaceproperty_ref # Name of the OpticalSurface

    def to_dict(self):
        return {
            "id": self.id, "name": self.name, "type": self.type,
            "volume_ref": self.volume_ref,
            "surfaceproperty_ref": self.surfaceproperty_ref
        }

    @classmethod
    def from_dict(cls, data):
        instance = cls(data['name'], data['volume_ref'], data['surfaceproperty_ref'])
        instance.id = data.get('id', instance.id)
        return instance

class BorderSurface:
    """Represents a <bordersurface> link."""
    def __init__(self, name, physvol1_ref, physvol2_ref, surfaceproperty_ref):
        self.id = str(uuid.uuid4())
        self.name = name
        self.type = "border" # For UI identification
        self.physvol1_ref = physvol1_ref # ID of the first PhysicalVolumePlacement
        self.physvol2_ref = physvol2_ref # ID of the second PhysicalVolumePlacement
        self.surfaceproperty_ref = surfaceproperty_ref # Name of the OpticalSurface

    def to_dict(self):
        return {
            "id": self.id, "name": self.name, "type": self.type,
            "physvol1_ref": self.physvol1_ref,
            "physvol2_ref": self.physvol2_ref,
            "surfaceproperty_ref": self.surfaceproperty_ref
        }

    @classmethod
    def from_dict(cls, data):
        instance = cls(data['name'], data['physvol1_ref'], data['physvol2_ref'], data['surfaceproperty_ref'])
        instance.id = data.get('id', instance.id)
        return instance

class GeometryState:
    """Holds the entire geometry definition."""
    def __init__(self, world_volume_ref=None):
        self.defines = {} # name: Define object
        self.materials = {} # name: Material object
        self.elements = {}  # name: Element object
        self.isotopes = {}  # name: Isotope object
        self.solids = {}    # name: Solid object
        self.logical_volumes = {} # name: LogicalVolume object
        self.assemblies = {} # name: Assembly object
        self.world_volume_ref = world_volume_ref # Name of the world LogicalVolume

        # Dictionaries for surface properties
        self.optical_surfaces = {}
        self.skin_surfaces = {}
        self.border_surfaces = {}

        # --- Dictionary to hold UI grouping information ---
        # Format: { 'solids': [{'name': 'MyCrystals', 'members': ['solid1_name', 'solid2_name']}], ... }
        self.ui_groups = {
            'define': [],
            'material': [],
            'element': [],
            'solid': [],
            'logical_volume': [],
            'assembly': [],
            'optical_surface': [], 
            'skin_surface': [], 
            'border_surface': []
        }

    def add_define(self, define_obj):
        self.defines[define_obj.name] = define_obj
    def add_material(self, material_obj):
        self.materials[material_obj.name] = material_obj
    def add_element(self, element_obj):
        self.elements[element_obj.name] = element_obj
    def add_isotope(self, isotope_obj):
        self.isotopes[isotope_obj.name] = isotope_obj
    def add_solid(self, solid_obj):
        self.solids[solid_obj.name] = solid_obj
    def add_logical_volume(self, lv_obj):
        self.logical_volumes[lv_obj.name] = lv_obj
    def add_assembly(self, assembly_obj):
        self.assemblies[assembly_obj.name] = assembly_obj
    def add_optical_surface(self, surf_obj):
        self.optical_surfaces[surf_obj.name] = surf_obj
    def add_skin_surface(self, surf_obj):
        self.skin_surfaces[surf_obj.name] = surf_obj
    def add_border_surface(self, surf_obj):
        self.border_surfaces[surf_obj.name] = surf_obj
    
    def get_define(self, name): return self.defines.get(name)
    def get_material(self, name): return self.materials.get(name)
    def get_element(self, name): return self.elements.get(name)
    def get_isotope(self, name): return self.isotopes.get(name)
    def get_solid(self, name): return self.solids.get(name)
    def get_logical_volume(self, name): return self.logical_volumes.get(name)
    def get_assembly(self, name): return self.assemblies.get(name)
    def get_optical_surface(self, name): return self.optical_surfaces.get(name)
    def get_skin_surface(self, name): return self.skin_surfaces.get(name)
    def get_border_surface(self, name): return self.border_surfaces.get(name)

    def to_dict(self):
        return {
            "defines": {name: define.to_dict() for name, define in self.defines.items()},
            "materials": {name: material.to_dict() for name, material in self.materials.items()},
            "elements": {name: element.to_dict() for name, element in self.elements.items()},
            "isotopes": {name: isotope.to_dict() for name, isotope in self.isotopes.items()},
            "solids": {name: solid.to_dict() for name, solid in self.solids.items()},
            "logical_volumes": {name: lv.to_dict() for name, lv in self.logical_volumes.items()},
            "assemblies": {name: asm.to_dict() for name, asm in self.assemblies.items()},
            "world_volume_ref": self.world_volume_ref,
            "optical_surfaces": {name: surf.to_dict() for name, surf in self.optical_surfaces.items()},
            "skin_surfaces": {name: surf.to_dict() for name, surf in self.skin_surfaces.items()},
            "border_surfaces": {name: surf.to_dict() for name, surf in self.border_surfaces.items()},
            "ui_groups": self.ui_groups 
        }

    @classmethod
    def from_dict(cls, data):
        instance = cls(data.get('world_volume_ref'))
        instance.defines = {name: Define.from_dict(d) for name, d in data.get('defines', {}).items()}
        instance.materials = {name: Material.from_dict(d) for name, d in data.get('materials', {}).items()}
        instance.elements = {name: Element.from_dict(d) for name, d in data.get('elements', {}).items()}
        instance.isotopes = {name: Isotope.from_dict(d) for name, d in data.get('isotopes', {}).items()}
        instance.solids = {name: Solid.from_dict(d) for name, d in data.get('solids', {}).items()}
        
        # For logical volumes, pass the instance itself to resolve internal refs if needed during from_dict
        instance.logical_volumes = {
            name: LogicalVolume.from_dict(lv_data, instance)
            for name, lv_data in data.get('logical_volumes', {}).items()
        }
        instance.assemblies = {name: Assembly.from_dict(d) for name, d in data.get('assemblies', {}).items()}

        # Deserialize the surface dictionaries
        instance.optical_surfaces = {name: OpticalSurface.from_dict(d) for name, d in data.get('optical_surfaces', {}).items()}
        instance.skin_surfaces = {name: SkinSurface.from_dict(d) for name, d in data.get('skin_surfaces', {}).items()}
        instance.border_surfaces = {name: BorderSurface.from_dict(d) for name, d in data.get('border_surfaces', {}).items()}

        # --- Deserialize the groups ---
        # Use data.get to provide a default empty dict for older project files
        default_groups = {'define': [], 'material': [], 'element': [], 'solid': [], 'logical_volume': [], 'assembly': [],
                          'optical_surface': [], 'skin_surface': [], 'border_surface': []}
        instance.ui_groups = data.get('ui_groups', default_groups)

        return instance

    def get_threejs_scene_description(self):
        if not self.world_volume_ref or self.world_volume_ref not in self.logical_volumes:
            return []
        threejs_objects = []
        world_lv = self.get_logical_volume(self.world_volume_ref)
        if world_lv and world_lv.content_type == 'physvol':
            initial_transform = np.identity(4)
            for pv in world_lv.content:
                self._traverse(pv, initial_transform, [world_lv.name], threejs_objects)
        return threejs_objects

    def _traverse(self, pv, parent_transform_matrix, path, threejs_objects, owner_pv_id=None):
        current_owner_id = owner_pv_id or pv.id
        local_transform_matrix = pv.get_transform_matrix()
        world_transform_matrix = parent_transform_matrix @ local_transform_matrix
        
        # Case 1: The PV places an Assembly
        assembly = self.get_assembly(pv.volume_ref)
        if assembly:
            if assembly.name in path: return
            for part_pv in assembly.placements:
                self._traverse(part_pv, world_transform_matrix, path + [assembly.name], threejs_objects, owner_pv_id=current_owner_id)
            return

        # Case 2: The PV places a Logical Volume
        lv = self.get_logical_volume(pv.volume_ref)
        if not lv: return
        if lv.name in path: return

        # Render the LV's solid IF it's a standard volume
        if lv.content_type not in ['replica', 'division', 'parameterised']:
            final_pos, final_rot_rad, _ = PhysicalVolumePlacement.decompose_matrix(world_transform_matrix)
            threejs_objects.append({
                "id": pv.id, "name": pv.name, "owner_pv_id": current_owner_id,
                "solid_ref_for_threejs": lv.solid_ref,
                "position": final_pos, "rotation": final_rot_rad,
                "vis_attributes": lv.vis_attributes, "copy_number": pv.copy_number
            })

        # Recurse into the content of the placed LV
        child_placements = []
        if lv.content_type == 'physvol':
            child_placements = lv.content
        elif lv.content_type == 'replica':
            child_placements = self._unroll_replica(lv)
        
        for child_pv in child_placements:
            self._traverse(child_pv, world_transform_matrix, path + [lv.name], threejs_objects, owner_pv_id=current_owner_id)
        
        # Handle division separately as it renders and recurses differently
        if lv.content_type == 'division':
            self._unroll_division_and_traverse(lv, world_transform_matrix, path, threejs_objects, owner_id=current_owner_id)
        elif lv.content_type == 'parameterised':
            self._unroll_param_and_traverse(lv, world_transform_matrix, path, threejs_objects, owner_id=current_owner_id)

    def _unroll_replica(self, lv):
        replica = lv.content
        child_lv = self.get_logical_volume(replica.volume_ref)
        if not child_lv: return []
        placements = []
        number, width, offset = int(replica.number), replica.width, replica.offset
        axis_vec = np.array([float(replica.direction['x']), float(replica.direction['y']), float(replica.direction['z'])])
        for i in range(number):
            translation = -width * (number - 1) * 0.5 + i * width + offset
            copy_pos = {'x': axis_vec[0] * translation, 'y': axis_vec[1] * translation, 'z': axis_vec[2] * translation}
            temp_pv = PhysicalVolumePlacement(f"{lv.name}_replica_{i}", child_lv.name, str(i))
            temp_pv._evaluated_position = copy_pos
            temp_pv._evaluated_rotation = {'x': 0, 'y': 0, 'z': 0}
            placements.append(temp_pv)
        return placements

    def _unroll_division_and_traverse(self, lv, parent_matrix, path, threejs_objects, owner_id):
        division = lv.content
        child_lv = self.get_logical_volume(division.volume_ref)
        mother_solid = self.get_solid(lv.solid_ref)
        if not (child_lv and mother_solid and mother_solid.type == 'box'):
            if mother_solid and mother_solid.type != 'box': print(f"Warning: Division of non-box solid '{mother_solid.name}' is not visually supported.")
            return

        number, offset = int(division.number), division.offset
        axis_map = {'kxaxis': 'x', 'kyaxis': 'y', 'kzaxis': 'z'}
        axis_key = axis_map.get(division.axis.lower(), 'z')
        mother_params = mother_solid._evaluated_parameters
        mother_extent = mother_params.get(axis_key, 0)
        width = (mother_extent - (2 * offset)) / number if number > 0 else 0

        slice_params = mother_params.copy()
        slice_params[axis_key] = width
        slice_solid = Solid(f"{mother_solid.name}_slice", 'box', {})
        slice_solid._evaluated_parameters = slice_params

        for i in range(number):
            pos_in_mother = -mother_extent / 2.0 + offset + width / 2.0 + i * width
            copy_pos = {'x': 0, 'y': 0, 'z': 0}; copy_pos[axis_key] = pos_in_mother
            
            temp_pv = PhysicalVolumePlacement(f"{lv.name}_division_{i}", child_lv.name, str(i))
            temp_pv._evaluated_position = copy_pos
            temp_pv._evaluated_rotation = {'x': 0, 'y': 0, 'z': 0}
            
            slice_world_matrix = parent_matrix @ temp_pv.get_transform_matrix()
            final_pos, final_rot_rad, _ = PhysicalVolumePlacement.decompose_matrix(slice_world_matrix)
            threejs_objects.append({
                "id": temp_pv.id, "name": temp_pv.name, "owner_pv_id": owner_id,
                "solid_ref_for_threejs": slice_solid.to_dict(),
                "position": final_pos, "rotation": final_rot_rad,
                "vis_attributes": child_lv.vis_attributes, "copy_number": i
            })

            # Recurse on the children of the ORIGINAL divided LV, placing them inside this new slice
            if child_lv.content_type == 'physvol' and child_lv.content:
                for child_of_child_pv in child_lv.content:
                    self._traverse(child_of_child_pv, slice_world_matrix, path + [lv.name], threejs_objects, owner_pv_id=owner_id)

    def _unroll_param_and_traverse(self, lv, parent_matrix, path, threejs_objects, owner_id):
        param_vol = lv.content
        child_lv_template = self.get_logical_volume(param_vol.volume_ref)
        if not child_lv_template: return

        original_solid = self.get_solid(child_lv_template.solid_ref)
        if not original_solid: return

        for i, param_set in enumerate(param_vol.parameters):
            # 1. Create a new, temporary solid with the specified dimensions
            new_solid_params = original_solid.raw_parameters.copy()
            # The dimension keys in GDML don't have the '_dimensions' suffix
            dims_type_clean = param_set.dimensions_type.replace('_dimensions', '')
            
            # Update the parameters with the values from this specific copy
            new_solid_params.update(param_set.dimensions)

            temp_solid = Solid(f"{original_solid.name}_param_{i}",
                               dims_type_clean,
                               new_solid_params)
            # We must manually evaluate these new raw parameters
            # This is a simplified evaluation for rendering purposes
            temp_solid._evaluated_parameters = {k: float(v) for k, v in param_set.dimensions.items()}


            # 2. Create a temporary PV for this copy's placement
            temp_pv = PhysicalVolumePlacement(
                name=f"{lv.name}_param_{i}",
                volume_ref=child_lv_template.name,
                copy_number_expr=str(i)
            )
            # The position can be a ref or a dict of expressions, which should have been evaluated
            temp_pv._evaluated_position = param_set.position 
            temp_pv._evaluated_rotation = {'x': 0, 'y': 0, 'z': 0}

            # 3. Render this specific instance
            instance_world_matrix = parent_matrix @ temp_pv.get_transform_matrix()
            final_pos, final_rot_rad, _ = PhysicalVolumePlacement.decompose_matrix(instance_world_matrix)
            threejs_objects.append({
                "id": temp_pv.id, "name": temp_pv.name, "owner_pv_id": owner_id,
                "solid_ref_for_threejs": temp_solid.to_dict(), # Pass the temp solid definition
                "position": final_pos, "rotation": final_rot_rad,
                "vis_attributes": child_lv_template.vis_attributes, "copy_number": i
            })

            # 4. Recurse into the ORIGINAL child LV's content, placed inside this new instance
            if child_lv_template.content_type == 'physvol' and child_lv_template.content:
                for child_of_child_pv in child_lv_template.content:
                    self._traverse(child_of_child_pv, instance_world_matrix, path + [lv.name], threejs_objects, owner_pv_id=owner_id)
