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
            print(f"Warning: Reconstructing raw_expression for define '{data.get('name')}'. This may lose original units/expressions.")
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
    def __init__(self, name, mat_type='standard', Z_expr=None, A_expr=None, density_expr="0.0", state=None, components=None):
        self.id = str(uuid.uuid4())
        self.name = name
        self.mat_type = mat_type
        
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
            "id": self.id, "name": self.name, "mat_type": self.mat_type,
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

        name = data['name']

        # A material is considered NIST if its name starts with G4_ AND
        # it has no other defining properties in the dictionary.
        is_nist_name = name.startswith("G4_")
        has_no_components = not data.get('components')
        has_no_z = not data.get('Z') and not data.get('Z_expr')
        
        material_type = 'nist' if is_nist_name and has_no_components and has_no_z else 'standard'
        
        instance = cls(
            name=name, 
            mat_type=data.get('mat_type', material_type),
            Z_expr=data.get('Z_expr', str(data.get('Z', ""))), 
            A_expr=data.get('A_expr', str(data.get('A', ""))), 
            density_expr=data.get('density_expr', str(data.get('density', "0.0"))), 
            state=data.get('state'), 
            components=data.get('components')
        )
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
            "content_type": self.content_type, 
            "content": content_data           
        }

    @classmethod
    def from_dict(cls, data, all_objects_map=None):
        instance = cls(
            data['name'], 
            data['solid_ref'], 
            data['material_ref'], 
            data.get('vis_attributes')
        )
        instance.id = data.get('id', str(uuid.uuid4()))
        instance.content_type = data.get('content_type', 'physvol')
        
        content_data = data.get('content')

        if instance.content_type == 'physvol' and isinstance(content_data, list):
            instance.content = [PhysicalVolumePlacement.from_dict(p) for p in content_data]
        elif content_data and isinstance(content_data, dict):
            # This block handles all single procedural volume objects
            if instance.content_type == 'replica':
                instance.content = ReplicaVolume.from_dict(content_data)
            elif instance.content_type == 'division':
                instance.content = DivisionVolume.from_dict(content_data)
            elif instance.content_type == 'parameterised':
                instance.content = ParamVolume.from_dict(content_data)
            else:
                # If it's a dict but an unknown type, log a warning but don't crash.
                print(f"Warning: Unknown procedural content type '{instance.content_type}' for LV '{instance.name}'. Content will be empty.")
                instance.content = []
                instance.content_type = 'physvol'
        else:
            # Fallback for empty or invalid content
            instance.content = []
            instance.content_type = 'physvol'
        
        return instance


class PhysicalVolumePlacement:
    """Represents a physical volume placement (physvol)."""
    def __init__(self, name, volume_ref, parent_lv_name = None, copy_number_expr="0",
                 position_val_or_ref=None, rotation_val_or_ref=None, scale_val_or_ref=None):
        self.id = str(uuid.uuid4())
        self.name = name
        self.volume_ref = volume_ref
        self.parent_lv_name = parent_lv_name
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

    # Function to clone the PV for Assembly placements
    def clone(self):
        # Creates a shallow copy. This is sufficient as we only modify the ID and parent.
        # The referenced objects (position, rotation dicts) can be shared.
        new_pv = PhysicalVolumePlacement(
            name=self.name,
            volume_ref=self.volume_ref,
            parent_lv_name=self.parent_lv_name,
            copy_number_expr=self.copy_number_expr,
            position_val_or_ref=self.position,
            rotation_val_or_ref=self.rotation,
            scale_val_or_ref=self.scale
        )
        # Copy evaluated properties as well
        new_pv.id = self.id
        new_pv._evaluated_position = self._evaluated_position.copy()
        new_pv._evaluated_rotation = self._evaluated_rotation.copy()
        new_pv._evaluated_scale = self._evaluated_scale.copy()
        new_pv.copy_number = self.copy_number
        
        return new_pv
    
    def get_transform_matrix(self):
        """
        Returns a 4x4 numpy transformation matrix for this placement,
        applying scale, then rotation, then translation.
        """
        pos = self._evaluated_position
        rot = self._evaluated_rotation
        scl = self._evaluated_scale

        # Create Translation Matrix (T)
        T = np.array([[1, 0, 0, pos['x']],
                      [0, 1, 0, pos['y']],
                      [0, 0, 1, pos['z']],
                      [0, 0, 0, 1]])

        # MODIFIED: Negate the angles to match the visual convention expected
        # by Geant4's GDML parser's application order.
        rx = rot['x']
        ry = rot['y']
        rz = rot['z']

        Rx = np.array([[1, 0, 0], [0, math.cos(rx), -math.sin(rx)], [0, math.sin(rx), math.cos(rx)]])
        Ry = np.array([[math.cos(ry), 0, math.sin(ry)], [0, 1, 0], [-math.sin(ry), 0, math.cos(ry)]])
        Rz = np.array([[math.cos(rz), -math.sin(rz), 0], [math.sin(rz), math.cos(rz), 0], [0, 0, 1]])

        # The correct composition for intrinsic ZYX is R = Rz * Ry * Rx
        R_3x3 = Rz @ Ry @ Rx
        
        R = np.eye(4)
        R[:3, :3] = R_3x3
        
        # Create Scaling Matrix (S)
        S = np.array([[scl['x'], 0, 0, 0],
                      [0, scl['y'], 0, 0],
                      [0, 0, scl['z'], 0],
                      [0, 0, 0, 1]])
        
        # Combine them: Final Transform = T * R * S
        return T @ R @ S
    
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
            "parent_lv_name": self.parent_lv_name,
            "_evaluated_position": self._evaluated_position, 
            "_evaluated_rotation": self._evaluated_rotation, 
            "_evaluated_scale": self._evaluated_scale
        }

    @classmethod
    def from_dict(cls, data, all_objects_map=None):
        copy_expr = data.get('copy_number_expr', str(data.get('copy_number', '0')))
        instance = cls(
            data['name'], data['volume_ref'], data.get('parent_lv_name'), copy_expr,
            data.get('position'), data.get('rotation'), data.get('scale')
        )
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
        self.number = number # Raw expression string
        self.width = width   # Raw expression string
        self.offset = offset # Raw expression string
        self.unit = unit
        # Add placeholders for evaluated values
        self._evaluated_number = 0
        self._evaluated_width = 0.0
        self._evaluated_offset = 0.0

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
    def __init__(self, name, volume_ref, number, direction, width=0.0, offset=0.0, start_position=None, start_rotation=None):
        self.id = str(uuid.uuid4())
        self.name = name
        self.type = "replica"
        self.volume_ref = volume_ref
        self.direction = direction
        self.number = number     # Raw expression string
        self.width = width       # Raw expression string
        self.offset = offset     # Raw expression string
        self.start_position = start_position if start_position is not None else {'x': '0', 'y': '0', 'z': '0'}
        self.start_rotation = start_rotation if start_rotation is not None else {'x': '0', 'y': '0', 'z': '0'}
        # Add placeholders for all evaluated values
        self._evaluated_number = 0
        self._evaluated_width = 0.0
        self._evaluated_offset = 0.0
        self._evaluated_start_position = {'x': 0, 'y': 0, 'z': 0}
        self._evaluated_start_rotation = {'x': 0, 'y': 0, 'z': 0}

    def to_dict(self):
        return {
            "id": self.id, "name": self.name, "type": self.type,
            "volume_ref": self.volume_ref, "number": self.number,
            "direction": self.direction, "width": self.width, "offset": self.offset,
            "start_position": self.start_position, "start_rotation": self.start_rotation
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
        start_position = data.get('start_position')
        start_rotation = data.get('start_rotation')
        volume_ref = data.get('volume_ref')
        if not volume_ref:
            # This would be an invalid state, but we can handle it gracefully.
            raise ValueError("ReplicaVolume content data is missing 'volume_ref'")

        instance = cls(name, volume_ref, number, direction, width, offset, start_position, start_rotation)
        instance.id = data.get('id', instance.id) # Use provided ID if it exists
        return instance

class Parameterisation:
    """Represents a single <parameters> block for a parameterised volume."""
    def __init__(self, number, position, dimensions_type, dimensions, rotation=None):
        self.number = number
        self.position = position
        self.rotation = rotation if rotation is not None else {'x': '0', 'y': '0', 'z': '0'}
        self.dimensions_type = dimensions_type # e.g., "box_dimensions"
        self.dimensions = dimensions # A dict of the dimension attrs, e.g. {'x':'10', 'y':'10'}

        self._evaluated_position = {'x': 0, 'y': 0, 'z': 0}
        self._evaluated_rotation = {'x': 0, 'y': 0, 'z': 0}
        self._evaluated_dimensions = {}

    def to_dict(self):
        return {
            "number": self.number,
            "position": self.position,
            "rotation": self.rotation,
            "dimensions_type": self.dimensions_type,
            "dimensions": self.dimensions
        }

    @classmethod
    def from_dict(cls, data):
        # The constructor needs all arguments. We provide defaults if they are missing.
        return cls(
            number=data.get('number'),
            position=data.get('position'),
            dimensions_type=data.get('dimensions_type'),
            dimensions=data.get('dimensions'),
            rotation=data.get('rotation') # This might be None, and that's okay
        )

class ParamVolume:
    """Represents a <paramvol> placement."""
    def __init__(self, name, volume_ref, ncopies):
        self.id = str(uuid.uuid4())
        self.name = name
        self.type = "parameterised"
        self.volume_ref = volume_ref
        self.ncopies = ncopies
        self.parameters = [] # This will be a list of Parameterisation objects

        self._evaluated_ncopies = 0

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

        # Add the world volume itself as a conceptual object (it won't be rendered)
        # We give it a known, stable ID.
        world_pv_id = "WORLD_PV_ID"
        threejs_objects.append({
            "id": world_pv_id,
            "name": world_lv.name,
            "parent_id": None,
            "is_world_volume_placement": True, # A flag to tell the frontend not to render it
            "volume_ref": self.world_volume_ref,
            "position": {'x': 0, 'y': 0, 'z': 0},
            "rotation": {'x': 0, 'y': 0, 'z': 0},
            "scale": {'x': 1, 'y': 1, 'z': 1}
        })

        if world_lv and world_lv.content_type == 'physvol':
            for pv in world_lv.content:
                # Initial call starts with the world as the parent
                self._traverse(pv, parent_pv_id=world_pv_id, path=[world_lv.name], threejs_objects=threejs_objects)

        return threejs_objects

    def _traverse(self, pv, parent_pv_id, path, threejs_objects, owner_pv_id=None, instance_prefix=""):
        
        # The instance_id is unique for every single object in the 3D scene.
        current_instance_id = f"{instance_prefix}{pv.id}"
        # The canonical_id is the original ID from the project's state definition.
        current_canonical_id = pv.id
        # The owner_id is the top-level selectable object in the hierarchy.
        current_owner_id = owner_pv_id or pv.id

        # Case 1: The PV places an Assembly
        assembly = self.get_assembly(pv.volume_ref)
        if assembly:
            
            # Add a non-renderable node for this assembly instance.
            threejs_objects.append({
                "id": current_instance_id,
                "canonical_id": current_canonical_id,
                "name": pv.name,
                "parent_id": parent_pv_id,
                "is_world_volume_placement": False,
                "volume_ref": pv.volume_ref,
                "is_assembly_container": True,
                "is_procedural_container": False,
                "is_procedural_instance": getattr(pv, 'is_procedural_instance', False),
                "position": pv._evaluated_position,
                "rotation": pv._evaluated_rotation,
                "scale": pv._evaluated_scale,
                "owner_pv_id": current_owner_id
            })
            
            if assembly.name in path: return # Prevent infinite recursion
            
            for part_pv_template in assembly.placements:
                # Create a clone of the template PV
                part_pv_instance = part_pv_template.clone()

                # The new instance's parent is this assembly instance.
                # The owner is still the top-level owner.
                # We pass down a new instance_prefix to ensure its children are also unique.
                self._traverse(
                    part_pv_instance,
                    parent_pv_id=current_instance_id,
                    path=path + [assembly.name],
                    threejs_objects=threejs_objects,
                    owner_pv_id=current_owner_id,
                    instance_prefix=f"{current_instance_id}::" # Use a clear separator
                )
            return
        
        # Case 2: The PV places a Logical Volume
        lv = self.get_logical_volume(pv.volume_ref)
        if not lv: return
        if lv.name in path: return

        # This physvol (pv) is the container for the LV's content.
        # It gets a single entry in the scene description with its unique instance ID.
        threejs_objects.append({
            "id": current_instance_id,
            "canonical_id": current_canonical_id,
            "name": pv.name,
            "parent_id": parent_pv_id,
            "is_world_volume_placement": False,
            "volume_ref": pv.volume_ref,
            "owner_pv_id": current_owner_id,
            "is_assembly_container": False,
            "is_procedural_container": lv.content_type != 'physvol',
            "is_procedural_instance": getattr(pv, 'is_procedural_instance', False),
            "solid_ref_for_threejs": lv.solid_ref,
            "position": pv._evaluated_position,
            "rotation": pv._evaluated_rotation,
            "scale": pv._evaluated_scale,
            "vis_attributes": lv.vis_attributes,
            "copy_number": pv.copy_number
        })
        
        if lv.content_type == 'physvol':
            # Recurse into the content of the placed LV
            for child_pv in lv.content:

                # Create a clone
                child_pv_instance = child_pv.clone()

                # For a standard PV, only pass down the owner if it is not the current PV.
                pass_down_owner = None
                if(current_owner_id == pv.id): pass_down_owner = None

                self._traverse(
                    child_pv_instance, 
                    parent_pv_id=current_instance_id, # Children are parented to this instance
                    path=path + [lv.name], 
                    threejs_objects=threejs_objects, 
                    owner_pv_id=pass_down_owner,
                    instance_prefix=f"{current_instance_id}::"
                )
        else: # It's a procedural LV
            # The owner of the unrolled instances is the current instance ID itself.
            owner_id_for_children = current_instance_id

            if lv.content_type == 'replica':
                self._unroll_replica_and_traverse(lv, current_canonical_id, current_instance_id, path, threejs_objects, owner_id=owner_id_for_children)
            elif lv.content_type == 'division':
                 self._unroll_division_and_traverse(lv, current_canonical_id, current_instance_id, path, threejs_objects, owner_id=owner_id_for_children)
            elif lv.content_type == 'parameterised':
                 self._unroll_param_and_traverse(lv, current_canonical_id, current_instance_id, path, threejs_objects, owner_id=owner_id_for_children)

    def _unroll_replica_and_traverse(self, lv, canonical_id, parent_pv_id, path, threejs_objects, owner_id):
        replica = lv.content
        child_lv_template = self.get_logical_volume(replica.volume_ref)
        if not child_lv_template: return
        
        # Use the pre-evaluated attributes from the object for ALL parameters
        number = replica._evaluated_number
        width = replica._evaluated_width
        offset = replica._evaluated_offset
        
        # This part doesn't need evaluation as it's just direction flags
        axis_vec = np.array([
            float(replica.direction['x']),
            float(replica.direction['y']),
            float(replica.direction['z'])
        ])
        
        start_pv = PhysicalVolumePlacement("temp_start", "temp_lv")
        start_pv._evaluated_position = replica._evaluated_start_position
        start_pv._evaluated_rotation = replica._evaluated_start_rotation
        start_transform_matrix = start_pv.get_transform_matrix()

        for i in range(number):
            translation_dist = -width * (number - 1) * 0.5 + i * width + offset
            
            algo_pos = axis_vec * translation_dist
            algo_matrix = np.identity(4)
            algo_matrix[0:3, 3] = algo_pos
            
            final_local_matrix = start_transform_matrix @ algo_matrix

            final_pos, final_rot_rad, _ = PhysicalVolumePlacement.decompose_matrix(final_local_matrix)

            temp_pv = PhysicalVolumePlacement(
                name=f"{lv.name}_replica_{i}",
                volume_ref=child_lv_template.name,
                copy_number_expr=str(i),
                parent_lv_name=lv.name
            )
            temp_pv._evaluated_position = final_pos
            temp_pv._evaluated_rotation = final_rot_rad

            # Add the generated replica instance itself to the list
            threejs_objects.append({
                "id": temp_pv.id,
                "canonical_id": canonical_id,
                "name": temp_pv.name,
                "parent_id": parent_pv_id,
                "owner_pv_id": owner_id,
                "is_world_volume_placement": False,
                "volume_ref": temp_pv.volume_ref,
                "is_assembly_container": False,
                "is_procedural_container": False,
                "is_procedural_instance": True, 
                "solid_ref_for_threejs": child_lv_template.solid_ref,
                "position": temp_pv._evaluated_position,
                "rotation": temp_pv._evaluated_rotation,
                "scale": temp_pv._evaluated_scale,
                "vis_attributes": child_lv_template.vis_attributes,
                "copy_number": i
            })
            
            # Recurse into children of the template LV
            if child_lv_template.content_type == 'physvol' and child_lv_template.content:
                for child_of_child_pv in child_lv_template.content:
                    self._traverse(child_of_child_pv, temp_pv.id, path + [lv.name], threejs_objects, owner_pv_id=owner_id)

    def _unroll_division_and_traverse(self, lv, canonical_id, parent_pv_id, path, threejs_objects, owner_id):
        division = lv.content
        child_lv = self.get_logical_volume(division.volume_ref)
        mother_solid = self.get_solid(lv.solid_ref)
        if not (child_lv and mother_solid and mother_solid.type == 'box'):
            if mother_solid and mother_solid.type != 'box': print(f"Warning: Division of non-box solid '{mother_solid.name}' is not visually supported.")
            return

        number, offset = division._evaluated_number, division._evaluated_offset
        axis_map = {'kxaxis': 'x', 'kyaxis': 'y', 'kzaxis': 'z'}
        axis_key = axis_map.get(division.axis.lower(), 'z')
        mother_params = mother_solid._evaluated_parameters
        mother_extent = mother_params.get(axis_key, 0)
        width = (mother_extent - (2 * offset)) / number if number > 0 else 0
        slice_params = mother_params.copy()
        slice_params[axis_key] = width

        # slice_solid = Solid(f"{mother_solid.name}_slice", 'box', {})
        # slice_solid._evaluated_parameters = slice_params

        for i in range(number):
            # Position of the slice's center within the mother volume's local coordinates
            pos_in_mother = -mother_extent / 2.0 + offset + width / 2.0 + i * width
            copy_pos = {'x': 0, 'y': 0, 'z': 0}; 
            copy_pos[axis_key] = pos_in_mother

            # This temporary solid is unique to this slice
            temp_solid = Solid(
                name=f"{mother_solid.name}_slice_{i}",
                solid_type='box',
                raw_parameters={} 
            )
            temp_solid._evaluated_parameters = slice_params

            # Create a temporary PV to hold the instance's transform
            temp_pv = PhysicalVolumePlacement(
                name=f"{lv.name}_division_{i}",
                volume_ref=child_lv.name,
                copy_number_expr=str(i),
                parent_lv_name=lv.name
            )
            temp_pv._evaluated_position = copy_pos
            temp_pv._evaluated_rotation = {'x': 0, 'y': 0, 'z': 0}
            
            # Add the generated slice itself to the list of objects to be rendered.
            threejs_objects.append({
                "id": temp_pv.id,
                "canonical_id": canonical_id,
                "name": temp_pv.name,
                "parent_id": parent_pv_id, # It's a child of the PV that holds the division rule
                "is_world_volume_placement": False,
                "volume_ref": temp_pv.volume_ref,
                "owner_pv_id": owner_id,   # It belongs to the division rule PV
                "is_assembly_container": False,
                "is_procedural_container": False,
                "is_procedural_instance": True,
                "solid_ref_for_threejs": temp_solid.to_dict(), # Pass the unique slice solid
                "position": temp_pv._evaluated_position,
                "rotation": temp_pv._evaluated_rotation,
                "scale": temp_pv._evaluated_scale,
                "vis_attributes": child_lv.vis_attributes,
                "copy_number": i
            })

            # Now, recurse into the children of the template LV, parenting them to this new slice
            if child_lv.content_type == 'physvol' and child_lv.content:
                for child_of_child_pv in child_lv.content:
                    self._traverse(child_of_child_pv, temp_pv.id, path + [lv.name], threejs_objects, owner_pv_id=owner_id)

    def _unroll_param_and_traverse(self, lv, canonical_id, parent_pv_id, path, threejs_objects, owner_id):
        param_vol = lv.content
        child_lv_template = self.get_logical_volume(param_vol.volume_ref)
        if not child_lv_template: return

        original_solid = self.get_solid(child_lv_template.solid_ref)
        if not original_solid: return

        for i, param_set in enumerate(param_vol.parameters):
            new_solid_params = original_solid.raw_parameters.copy()
            dims_type_clean = param_set.dimensions_type.replace('_dimensions', '')
            new_solid_params.update(param_set.dimensions)

            # Create a temporary Solid object for this specific instance
            temp_solid = Solid(
                name=f"{original_solid.name}_param_{i}",
                solid_type=dims_type_clean,
                raw_parameters=new_solid_params
            )
            temp_solid._evaluated_parameters = param_set._evaluated_dimensions
            
            # Create a temporary PhysicalVolumePlacement for this instance's transform
            temp_pv = PhysicalVolumePlacement(
                name=f"{lv.name}_param_{i}",
                volume_ref=child_lv_template.name,
                copy_number_expr=str(i),
                parent_lv_name=lv.name
            )
            temp_pv._evaluated_position = param_set._evaluated_position
            temp_pv._evaluated_rotation = param_set._evaluated_rotation

            # Create a temporary Logical Volume for this instance so we can recurse
            temp_lv_instance = LogicalVolume(
                name=f"{child_lv_template.name}_param_{i}",
                solid_ref=temp_solid.name, # This solid doesn't exist in the main dict, so we pass the object
                material_ref=child_lv_template.material_ref
            )
            temp_lv_instance.content = child_lv_template.content
            temp_lv_instance.content_type = child_lv_template.content_type

            # We need to add the solid to the description, but also need to pass the object
            # to the recursive call. Let's create a custom object for the scene description.
            threejs_objects.append({
                "id": temp_pv.id,
                "canonical_id": canonical_id,
                "name": temp_pv.name,
                "parent_id": parent_pv_id,
                "is_world_volume_placement": False,
                "volume_ref": temp_pv.volume_ref,
                "owner_pv_id": owner_id,
                "is_assembly_container": False,
                "is_procedural_container": False,
                "is_procedural_instance": True,
                "solid_ref_for_threejs": temp_solid.to_dict(), # Pass the temporary solid's data directly
                "position": temp_pv._evaluated_position,
                "rotation": temp_pv._evaluated_rotation,
                "scale": temp_pv._evaluated_scale,
                "vis_attributes": child_lv_template.vis_attributes,
                "copy_number": i
            })

            # Recurse if the template LV had children
            if child_lv_template.content_type == 'physvol' and child_lv_template.content:
                for child_of_child_pv in child_lv_template.content:
                    # Children are parented to our temporary instance PV
                    self._traverse(child_of_child_pv, temp_pv.id, path + [lv.name], threejs_objects, owner_pv_id=owner_id)
