# src/gdml_parser.py
import xml.etree.ElementTree as ET
import io
import math
import asteval
from .geometry_types import (
    GeometryState, Define, Material, Solid, LogicalVolume, PhysicalVolumePlacement, 
    UNIT_FACTORS, convert_to_internal_units, get_unit_value
)

class GDMLParser:
    def __init__(self):
        self.geometry_state = GeometryState()
        self.evaluator_context = { # Pre-define common constants
            'pi': math.pi,
            'PI': math.pi, # Common GDML usage
            'HALFPI': math.pi / 2.0,
            'TWOPI': 2.0 * math.pi,
            # Geant4 system_of_units can be added if expressions use them directly
            'mm': 1.0,
            'cm': 10.0,
            'm': 1000.0,
            'rad': 1.0,
            'deg': math.pi / 180.0,
        }
        self.aeval = asteval.Interpreter(symtable=self.evaluator_context, minimal=True, no_ifexp=True, no_for=True, no_while=True, no_try=True, no_functiondef=True)

    def _strip_namespace(self, gdml_content_string):
        it = ET.iterparse(io.StringIO(gdml_content_string))
        for _, el in it:
            if '}' in el.tag:
                el.tag = el.tag.split('}', 1)[1]
        return it.root
    
    def _evaluate_expression(self, expr_str, default_unit_val_for_bare_numbers=1.0, category="length"):
        if expr_str is None:
            print(f"Warning: Got None for an expression, returning 0.0. This might indicate a missing attribute in the GDML file.")
            return 0.0

        expr_str = str(expr_str).strip() 
        if not expr_str: return 0.0

        eval_result = None

        # First, check for direct reference, but DON'T return.
        # Just get the numerical value and let it fall through to the
        # unit multiplication step at the end.
        if expr_str in self.evaluator_context:
            val_from_context = self.evaluator_context[expr_str]
            if isinstance(val_from_context, (int, float)):
                eval_result = val_from_context  # This is the value, e.g., 360.0
            elif isinstance(val_from_context, dict) and 'value' in val_from_context and isinstance(val_from_context['value'], (int, float)):
                eval_result = val_from_context['value']
        
        # If it was not a direct lookup, use asteval for complex expressions
        if eval_result is None:
            cleaned_expr_str = expr_str
            parsed_unit_val = 1.0  # Reset for this block
            found_unit_in_expr = False

            # This basic unit stripping is for expressions like "10*cm"
            for unit_cat_map_name, unit_cat_map in UNIT_FACTORS.items():
                for unit_symbol, factor in unit_cat_map.items():
                    if cleaned_expr_str.endswith(f"*{unit_symbol}"):
                        cleaned_expr_str = cleaned_expr_str[:-len(f"*{unit_symbol}")].strip()
                        parsed_unit_val = factor
                        found_unit_in_expr = True
                        break
                    elif cleaned_expr_str.endswith(f" * {unit_symbol}"):
                        cleaned_expr_str = cleaned_expr_str[:-len(f" * {unit_symbol}")].strip()
                        parsed_unit_val = factor
                        found_unit_in_expr = True
                        break
                if found_unit_in_expr: break

            self.aeval.error = []
            self.aeval.error_msg = None
            
            temp_result = self.aeval(cleaned_expr_str)

            if self.aeval.error:
                for err in self.aeval.error:
                    print(f"asteval error processing expression='{expr_str}' (cleaned='{cleaned_expr_str}'): {err.msg} at line {err.lineno}, col {err.col_offset}")
                try:
                    eval_result = float(cleaned_expr_str) * (parsed_unit_val if found_unit_in_expr else 1.0)
                except ValueError:
                    print(f"Warning: Cannot evaluate expression '{expr_str}'. Returning 0.")
                    return 0.0
            else:
                 eval_result = temp_result * (parsed_unit_val if found_unit_in_expr else 1.0)
        
        # Apply the unit factor from the GDML tag (like aunit="deg") to the result.
        # This now works for both direct constants and complex expressions.
        if isinstance(eval_result, (int, float)):
            return eval_result * default_unit_val_for_bare_numbers
        else:
            print(f"Warning: Expression '{expr_str}' evaluated to non-numeric type '{type(eval_result)}'. Returning 0.")
            return 0.0

    def parse_gdml_string(self, gdml_content_string):
        self.geometry_state = GeometryState() # Reset for new parse
        self.evaluator_context = {}           # Reset context for each parse
        root = self._strip_namespace(gdml_content_string)

        self._parse_defines(root.find('define'))
        self._parse_materials(root.find('materials'))
        self._parse_solids(root.find('solids'))
        self._parse_structure(root.find('structure'))
        self._parse_setup(root.find('setup'))
        
        return self.geometry_state

    def _parse_defines(self, define_element):
        if define_element is None: return
        
        # First pass for constants and quantities that might be used in expressions
        constants_and_quantities = []
        expressions = []
        positions_rotations_etc = []

        for element in define_element:
            if element.tag in ['constant', 'quantity']:
                constants_and_quantities.append(element)
            elif element.tag == 'expression':
                expressions.append(element)
            else:
                positions_rotations_etc.append(element)

        # Process constants and quantities first
        for element in constants_and_quantities:
            name = element.get('name')
            if not name: continue
            
            val_str = element.get('value')
            if element.tag == 'constant':
                # Evaluate the constant's value string. Constants don't have 'unit' attribute in GDML.
                # Their value is often an expression itself.
                evaluated_value = self._evaluate_expression(val_str, 1.0, "dimensionless")
                define_obj = Define(name, 'constant', evaluated_value) # Store already converted value
                self.geometry_state.add_define(define_obj)
                self.evaluator_context[name] = evaluated_value # Add to asteval context
            
            elif element.tag == 'quantity':
                unit_attr = element.get('unit') # Quantities usually have explicit units
                category = "dimensionless"
                unit_factor_for_internal_conversion = 1.0 # default

                if unit_attr:
                    for cat_name, u_map in UNIT_FACTORS.items():
                        if unit_attr in u_map:
                            category = cat_name
                            unit_factor_for_internal_conversion = u_map[unit_attr]
                            break
                
                # Evaluate the numerical part of the quantity's value
                # The expression itself shouldn't contain units if the tag has a unit attribute.
                # default_unit_val_for_bare_numbers=1.0 because we handle unit conversion *after* evaluation
                numerical_value_from_expr = self._evaluate_expression(val_str, 1.0, category)
                
                # Convert the evaluated numerical value to internal units using the unit_factor
                value_in_internal_units = numerical_value_from_expr * unit_factor_for_internal_conversion

                define_obj = Define(name, 'quantity', value_in_internal_units, unit_attr, category)
                self.geometry_state.add_define(define_obj)
                self.evaluator_context[name] = value_in_internal_units

        # Second pass for expressions, which might use constants/quantities defined above
        for element in expressions:
            name = element.get('name')
            if not name: continue
            if element.tag == 'expression':
                expr_value_str = element.text
                evaluated_expr = self._evaluate_expression(expr_value_str, 1.0, "dimensionless")
                define_obj = Define(name, 'expression_evaluated_constant', evaluated_expr)
                self.geometry_state.add_define(define_obj)
                print(f"[name {name}] for elem {element}: adding {evaluated_expr} to context from {expr_value_str}")
                self.evaluator_context[name] = evaluated_expr
        
        # Third pass for positions, rotations etc. that might use any of the above
        for element in positions_rotations_etc:
            name = element.get('name')
            if not name: continue

            if element.tag == 'position':
                unit = element.get('unit', 'mm') # Default to mm for position tag
                tag_unit_value = get_unit_value(unit, "length")
                pos_val_dict = {
                    'x': self._evaluate_expression(element.get('x', '0'), tag_unit_value),
                    'y': self._evaluate_expression(element.get('y', '0'), tag_unit_value),
                    'z': self._evaluate_expression(element.get('z', '0'), tag_unit_value)
                }
                define_obj = Define(name, 'position', pos_val_dict) # Define stores values in internal units
                self.geometry_state.add_define(define_obj)
                # self.evaluator_context[name] = define_obj.to_dict() # No need to add to context, not used in expr
            elif element.tag == 'rotation':
                unit = element.get('unit', 'rad') # Default to rad for rotation tag
                tag_unit_value = get_unit_value(unit, "angle")
                rot_val_dict = {
                    'x': self._evaluate_expression(element.get('x', '0'), tag_unit_value),
                    'y': self._evaluate_expression(element.get('y', '0'), tag_unit_value),
                    'z': self._evaluate_expression(element.get('z', '0'), tag_unit_value)
                }
                define_obj = Define(name, 'rotation', rot_val_dict)
                self.geometry_state.add_define(define_obj)
            # Add <matrix>, <scale>, <variable> later

    def _parse_materials(self, materials_element):
        if materials_element is None: return
        for element in materials_element:
            if element.tag == 'material':
                name = element.get('name')
                if not name: continue
                density_val = None
                d_el = element.find('D')
                if d_el is not None:
                    # GDML D is g/cm3, our internal units might differ or be unitless if we store as parsed
                    # For now, let's assume density is stored directly as parsed with its GDML unit.
                    density_val = self._evaluate_expression(d_el.get('value'), default_unit_val_for_bare_numbers=1.0) # Store value
                    # Unit for density is more complex (g/cm3), not simple length/angle
                mat = Material(name, density=density_val)
                self.geometry_state.add_material(mat)

    def _resolve_transform(self, solid_el_for_csg):
        """ Helper to resolve position and rotation for CSG components. """
        pos = {'x':0, 'y':0, 'z':0}
        rot = {'x':0, 'y':0, 'z':0} # ZYX Euler in radians

        pos_el = solid_el_for_csg.find('position')
        pos_ref_el = solid_el_for_csg.find('positionref')
        rot_el = solid_el_for_csg.find('rotation')
        rot_ref_el = solid_el_for_csg.find('rotationref')
        # Note: GDML also supports <firstposition>, <firstrotation> for CSG
        # which this simplified helper doesn't distinguish yet.

        if pos_el is not None:
            unit = pos_el.get('unit', 'mm')
            pos = {
                'x': self._evaluate_expression(pos_el.get('x'), get_unit_value(unit, "length")),
                'y': self._evaluate_expression(pos_el.get('y'), get_unit_value(unit, "length")),
                'z': self._evaluate_expression(pos_el.get('z'), get_unit_value(unit, "length"))
            }
        elif pos_ref_el is not None:
            pos_def = self.geometry_state.get_define(pos_ref_el.get('ref'))
            if pos_def and pos_def.type == 'position': pos = pos_def.value

        if rot_el is not None:
            unit = rot_el.get('unit', 'rad')
            rot = {
                'x': self._evaluate_expression(rot_el.get('x'), get_unit_value(unit, "angle")),
                'y': self._evaluate_expression(rot_el.get('y'), get_unit_value(unit, "angle")),
                'z': self._evaluate_expression(rot_el.get('z'), get_unit_value(unit, "angle"))
            }
        elif rot_ref_el is not None:
            rot_def = self.geometry_state.get_define(rot_ref_el.get('ref'))
            if rot_def and rot_def.type == 'rotation': rot = rot_def.value
        
        return {"position": pos, "rotation": rot}

    def _build_boolean_recipe(self, top_level_boolean, all_solids):
        """
        Traces a nested GDML boolean structure back to its base primitive
        and then builds a flat recipe list.
        """
        lineage = [top_level_boolean]
        consumed_names = {top_level_boolean.name}
        current_boolean = top_level_boolean

        # 1. Trace back to the base solid by following 'first_ref'
        while True:
            first_ref = current_boolean.parameters.get('first_ref')
            if not first_ref:
                raise ValueError(f"Boolean solid '{current_boolean.name}' is missing 'first_ref'.")
                
            first_solid = all_solids.get(first_ref)
            if not first_solid:
                 raise ValueError(f"Could not find solid '{first_ref}' referenced by '{current_boolean.name}'.")

            if first_solid.type in ['union', 'subtraction', 'intersection']:
                lineage.insert(0, first_solid)
                consumed_names.add(first_solid.name)
                current_boolean = first_solid
            else:
                # It's a primitive, so we found the base
                base_solid_ref = first_solid.name
                break
        
        # 2. Build the recipe forward from the discovered lineage
        recipe = []
        
        # The first operation in the chain defines the transform for the base solid
        first_op_in_chain = lineage[0]
        base_transform = first_op_in_chain.parameters.get('transform_first')
        
        recipe.append({
            'op': 'base',
            'solid_ref': base_solid_ref,
            'transform': base_transform
        })
        
        # Add the subsequent operations from the chain
        for boolean_op in lineage:
            second_ref = boolean_op.parameters.get('second_ref')
            if not second_ref:
                 raise ValueError(f"Boolean solid '{boolean_op.name}' is missing 'second_ref'.")

            op_name = boolean_op.type
            transform = boolean_op.parameters.get('transform_second')
            
            recipe.append({
                'op': op_name,
                'solid_ref': second_ref,
                'transform': transform
            })

        return recipe, consumed_names

    def _parse_solids(self, solids_element):
        if solids_element is None: return

        temp_solids = {} # Store all parsed solids here first

        for solid_el in solids_element:
            name_attr = solid_el.get('name')
            if not name_attr: continue
            
            # Use _evaluate_expression for name if it can contain variables (e.g. in loops)
            # For simplicity, assume name is direct string for now.
            # name = self._evaluate_expression(name_attr, 1.0, "string_like_no_convert")
            name = name_attr

            params = {}
            solid_type = solid_el.tag

            # Default units for parameters if not on individual attributes
            lunit_val = get_unit_value(solid_el.get('lunit', 'mm'), "length")
            aunit_val = get_unit_value(solid_el.get('aunit', 'rad'), "angle")

            if solid_type == 'box':
                params = {
                    'x': self._evaluate_expression(solid_el.get('x'), lunit_val),
                    'y': self._evaluate_expression(solid_el.get('y'), lunit_val),
                    'z': self._evaluate_expression(solid_el.get('z'), lunit_val),
                }
            elif solid_type == 'tube': # G4Tubs
                params = {
                    'rmin': self._evaluate_expression(solid_el.get('rmin'), lunit_val),
                    'rmax': self._evaluate_expression(solid_el.get('rmax'), lunit_val),
                    'dz': self._evaluate_expression(solid_el.get('z'), lunit_val) / 2.0,
                    'startphi': self._evaluate_expression(solid_el.get('startphi'), aunit_val),
                    'deltaphi': self._evaluate_expression(solid_el.get('deltaphi'), aunit_val),
                }
            elif solid_type == 'cutTube':
                # A cutTube has the same params as a tube, plus two cutting plane normal vectors.
                # The normal vector points *towards the material to be KEPT*.
                params = {
                    'rmin': self._evaluate_expression(solid_el.get('rmin'), lunit_val),
                    'rmax': self._evaluate_expression(solid_el.get('rmax'), lunit_val),
                    'dz': self._evaluate_expression(solid_el.get('z'), lunit_val) / 2.0,
                    'startphi': self._evaluate_expression(solid_el.get('startphi'), aunit_val),
                    'deltaphi': self._evaluate_expression(solid_el.get('deltaphi'), aunit_val),
                    'lowNormal': {
                        'x': self._evaluate_expression(solid_el.get('lowX', '0'), 1.0, "dimensionless"),
                        'y': self._evaluate_expression(solid_el.get('lowY', '0'), 1.0, "dimensionless"),
                        'z': self._evaluate_expression(solid_el.get('lowZ', '0'), 1.0, "dimensionless"),
                    },
                    'highNormal': {
                        'x': self._evaluate_expression(solid_el.get('highX', '0'), 1.0, "dimensionless"),
                        'y': self._evaluate_expression(solid_el.get('highY', '0'), 1.0, "dimensionless"),
                        'z': self._evaluate_expression(solid_el.get('highZ', '0'), 1.0, "dimensionless"),
                    }
                }
            elif solid_type == 'cone': # G4Cons
                params = {
                    'rmin1': self._evaluate_expression(solid_el.get('rmin1'), lunit_val),
                    'rmax1': self._evaluate_expression(solid_el.get('rmax1'), lunit_val),
                    'rmin2': self._evaluate_expression(solid_el.get('rmin2'), lunit_val),
                    'rmax2': self._evaluate_expression(solid_el.get('rmax2'), lunit_val),
                    'dz': self._evaluate_expression(solid_el.get('z'), lunit_val) / 2.0,
                    'startphi': self._evaluate_expression(solid_el.get('startphi'), aunit_val),
                    'deltaphi': self._evaluate_expression(solid_el.get('deltaphi'), aunit_val),
                }
            elif solid_type == 'sphere':
                params = {
                    'rmin': self._evaluate_expression(solid_el.get('rmin'), lunit_val),
                    'rmax': self._evaluate_expression(solid_el.get('rmax'), lunit_val),
                    'startphi': self._evaluate_expression(solid_el.get('startphi'), aunit_val),
                    'deltaphi': self._evaluate_expression(solid_el.get('deltaphi'), aunit_val),
                    'starttheta': self._evaluate_expression(solid_el.get('starttheta'), aunit_val),
                    'deltatheta': self._evaluate_expression(solid_el.get('deltatheta'), aunit_val),
                }
            elif solid_type == 'orb':
                params = {'r': self._evaluate_expression(solid_el.get('r'), lunit_val)}
            elif solid_type == 'torus':
                params = {
                    'rmin': self._evaluate_expression(solid_el.get('rmin'), lunit_val),
                    'rmax': self._evaluate_expression(solid_el.get('rmax'), lunit_val),
                    'rtor': self._evaluate_expression(solid_el.get('rtor'), lunit_val),
                    'startphi': self._evaluate_expression(solid_el.get('startphi'), aunit_val),
                    'deltaphi': self._evaluate_expression(solid_el.get('deltaphi'), aunit_val),
                }
            elif solid_type == 'para': # Parallelepiped G4Para
                params = {
                    'dx': self._evaluate_expression(solid_el.get('x'), lunit_val) / 2.0,
                    'dy': self._evaluate_expression(solid_el.get('y'), lunit_val) / 2.0,
                    'dz': self._evaluate_expression(solid_el.get('z'), lunit_val) / 2.0,
                    'alpha': self._evaluate_expression(solid_el.get('alpha'), aunit_val),
                    'theta': self._evaluate_expression(solid_el.get('theta'), aunit_val),
                    'phi': self._evaluate_expression(solid_el.get('phi'), aunit_val),
                }
            elif solid_type == 'trd':
                params = {
                    'dx1': self._evaluate_expression(solid_el.get('x1'), lunit_val) / 2.0,
                    'dx2': self._evaluate_expression(solid_el.get('x2'), lunit_val) / 2.0,
                    'dy1': self._evaluate_expression(solid_el.get('y1'), lunit_val) / 2.0,
                    'dy2': self._evaluate_expression(solid_el.get('y2'), lunit_val) / 2.0,
                    'dz': self._evaluate_expression(solid_el.get('z'), lunit_val) / 2.0,
                }
            elif solid_type == 'trap': # general G4Trap
                 params = {
                    'dz': self._evaluate_expression(solid_el.get('z'), lunit_val) / 2.0,
                    'theta': self._evaluate_expression(solid_el.get('theta'), aunit_val),
                    'phi': self._evaluate_expression(solid_el.get('phi'), aunit_val),
                    'dy1': self._evaluate_expression(solid_el.get('y1'), lunit_val) / 2.0,
                    'dx1': self._evaluate_expression(solid_el.get('x1'), lunit_val) / 2.0,
                    'dx2': self._evaluate_expression(solid_el.get('x2'), lunit_val) / 2.0,
                    'alpha1': self._evaluate_expression(solid_el.get('alpha1'), aunit_val),
                    'dy2': self._evaluate_expression(solid_el.get('y2'), lunit_val) / 2.0,
                    'dx3': self._evaluate_expression(solid_el.get('x3'), lunit_val) / 2.0,
                    'dx4': self._evaluate_expression(solid_el.get('x4'), lunit_val) / 2.0,
                    'alpha2': self._evaluate_expression(solid_el.get('alpha2'), aunit_val),
                }
            elif solid_type == 'arb8': # G4GenericTrap
                vertices = []
                for i in range(1, 9): # v1x, v1y ... v8x, v8y
                    vertices.append({
                        'x': self._evaluate_expression(solid_el.get(f'v{i}x'), lunit_val),
                        'y': self._evaluate_expression(solid_el.get(f'v{i}y'), lunit_val)
                    })
                params = {
                    'dz': self._evaluate_expression(solid_el.get('dz'), lunit_val) / 2.0, # GDML dz is half-length
                    'vertices': vertices
                }
            elif solid_type == 'hype':
                params = {
                    'rmin': self._evaluate_expression(solid_el.get('rmin'), lunit_val),
                    'rmax': self._evaluate_expression(solid_el.get('rmax'), lunit_val),
                    'inst': self._evaluate_expression(solid_el.get('inst'), aunit_val), # inner stereo angle
                    'outst': self._evaluate_expression(solid_el.get('outst'), aunit_val), # outer stereo angle
                    'dz': self._evaluate_expression(solid_el.get('z'), lunit_val) / 2.0 # G4Hype z is half-length
                }
            elif solid_type == 'eltube': # G4EllipticalTube
                params = {
                    'dx': self._evaluate_expression(solid_el.get('dx'), lunit_val), # semi-axis dx
                    'dy': self._evaluate_expression(solid_el.get('dy'), lunit_val), # semi-axis dy
                    'dz': self._evaluate_expression(solid_el.get('dz'), lunit_val)  # half-length dz
                }
            elif solid_type == 'ellipsoid':
                params = {
                    'ax': self._evaluate_expression(solid_el.get('ax'), lunit_val), # semi-axis x
                    'by': self._evaluate_expression(solid_el.get('by'), lunit_val), # semi-axis y
                    'cz': self._evaluate_expression(solid_el.get('cz'), lunit_val), # semi-axis z
                    'zcut1': self._evaluate_expression(solid_el.get('zcut1'), lunit_val, "length"), # bottom z cut plane
                    'zcut2': self._evaluate_expression(solid_el.get('zcut2'), lunit_val, "length")  # top z cut plane
                }
            elif solid_type == 'elcone': # G4EllipticalCone
                params = {
                    'dx': self._evaluate_expression(solid_el.get('dx'), 1.0, "dimensionless"), # x semi-axis / zMax
                    'dy': self._evaluate_expression(solid_el.get('dy'), 1.0, "dimensionless"), # y semi-axis / zMax
                    'zmax': self._evaluate_expression(solid_el.get('zmax'), lunit_val), # z max height
                    'zcut': self._evaluate_expression(solid_el.get('zcut'), lunit_val)  # upper z cut plane
                }
            elif solid_type == 'paraboloid':
                params = {
                    'rlo': self._evaluate_expression(solid_el.get('rlo'), lunit_val), # radius at -dz
                    'rhi': self._evaluate_expression(solid_el.get('rhi'), lunit_val), # radius at +dz
                    'dz': self._evaluate_expression(solid_el.get('dz'), lunit_val)   # half length in z
                }
            elif solid_type == 'tet': # Tetrahedron G4Tet
                # Vertices are references to <position> defines
                params = {
                    'vertex1_ref': solid_el.get('vertex1'),
                    'vertex2_ref': solid_el.get('vertex2'),
                    'vertex3_ref': solid_el.get('vertex3'),
                    'vertex4_ref': solid_el.get('vertex4'),
                }
            elif solid_type == 'twistedbox':
                params = {
                    'phi_twist': self._evaluate_expression(solid_el.get('PhiTwist'), aunit_val),
                    'dx': self._evaluate_expression(solid_el.get('x'), lunit_val) / 2.0,
                    'dy': self._evaluate_expression(solid_el.get('y'), lunit_val) / 2.0,
                    'dz': self._evaluate_expression(solid_el.get('z'), lunit_val) / 2.0,
                }
            elif solid_type == 'twistedtrd':
                params = {
                    'phi_twist': self._evaluate_expression(solid_el.get('PhiTwist'), aunit_val),
                    'dx1': self._evaluate_expression(solid_el.get('x1'), lunit_val) / 2.0, # x half length at -dz
                    'dx2': self._evaluate_expression(solid_el.get('x2'), lunit_val) / 2.0, # x half length at +dz
                    'dy1': self._evaluate_expression(solid_el.get('y1'), lunit_val) / 2.0, # y half length at -dz
                    'dy2': self._evaluate_expression(solid_el.get('y2'), lunit_val) / 2.0, # y half length at +dz
                    'dz':  self._evaluate_expression(solid_el.get('z'), lunit_val) / 2.0,  # half length in z
                }
            elif solid_type == 'twistedtrap': # G4TwistedTrap
                params = {
                    'phi_twist': self._evaluate_expression(solid_el.get('PhiTwist'), aunit_val),
                    'dz': self._evaluate_expression(solid_el.get('z'), lunit_val) / 2.0,
                    'theta': self._evaluate_expression(solid_el.get('Theta'), aunit_val), # polar angle of the line joining the centres of the faces at -/+ve dz
                    'phi': self._evaluate_expression(solid_el.get('Phi'), aunit_val),     # azimuthal angle of the line joining the centres of the faces at -/+ve dz
                    'dy1': self._evaluate_expression(solid_el.get('y1'), lunit_val) / 2.0, # half Y length of the face at -dz
                    'dx1': self._evaluate_expression(solid_el.get('x1'), lunit_val) / 2.0, # half X length of the side at Y=-dy1 of the face at -dz
                    'dx2': self._evaluate_expression(solid_el.get('x2'), lunit_val) / 2.0, # half X length of the side at Y=+dy1 of the face at -dz
                    'dy2': self._evaluate_expression(solid_el.get('y2'), lunit_val) / 2.0, # half Y length of the face at +dz
                    'dx3': self._evaluate_expression(solid_el.get('x3'), lunit_val) / 2.0, # half X length of the side at Y=-dy2 of the face at +dz
                    'dx4': self._evaluate_expression(solid_el.get('x4'), lunit_val) / 2.0, # half X length of the side at Y=+dy2 of the face at +dz
                    'alpha': self._evaluate_expression(solid_el.get('Alph', solid_el.get('Alpha')), aunit_val) # Alph in G01, Alpha in G4 docs often. Angle with respect to the y axis from the centre of the side to the centre of the face of the +z face
                }
            elif solid_type == 'twistedtubs': # G4TwistedTubs
                params = {
                    'twistedangle': self._evaluate_expression(solid_el.get('twistedangle'), aunit_val), # Angle of twist at z-surfaces
                    'rmin': self._evaluate_expression(solid_el.get('endinnerrad'), lunit_val), # Inner radius at z-surfaces
                    'rmax': self._evaluate_expression(solid_el.get('endouterrad'), lunit_val), # Outer radius at z-surfaces
                    'dz': self._evaluate_expression(solid_el.get('zlen'), lunit_val) / 2.0, # half length
                    'dphi': self._evaluate_expression(solid_el.get('phi', solid_el.get('totphi')), aunit_val), # Sector angle, totphi used in G01 example
                    # nseg is optional, for number of segments, not parsed for now
                }
            elif solid_type in ['union', 'subtraction', 'intersection']:
                first_ref = solid_el.find('first').get('ref')
                second_ref = solid_el.find('second').get('ref')
                transform = self._resolve_transform(solid_el) # For the second solid relative to the first
                
                # Optional: firstsolid transform (G4GDMLReadSolids.cc handles this)
                first_transform = {"position": {'x':0,'y':0,'z':0}, "rotation": {'x':0,'y':0,'z':0}}
                fp_el = solid_el.find('firstposition')
                fp_ref_el = solid_el.find('firstpositionref')
                fr_el = solid_el.find('firstrotation')
                fr_ref_el = solid_el.find('firstrotationref')

                if fp_el is not None:
                     unit = fp_el.get('unit', 'mm')
                     first_transform['position'] = {
                        'x': self._evaluate_expression(fp_el.get('x'), get_unit_value(unit, "length")),
                        'y': self._evaluate_expression(fp_el.get('y'), get_unit_value(unit, "length")),
                        'z': self._evaluate_expression(fp_el.get('z'), get_unit_value(unit, "length"))
                     }
                elif fp_ref_el is not None:
                    pos_def = self.geometry_state.get_define(fp_ref_el.get('ref'))
                    if pos_def and pos_def.type == 'position': first_transform['position'] = pos_def.value

                if fr_el is not None:
                    unit = fr_el.get('unit', 'rad')
                    first_transform['rotation'] = {
                        'x': self._evaluate_expression(fr_el.get('x'), get_unit_value(unit, "angle")),
                        'y': self._evaluate_expression(fr_el.get('y'), get_unit_value(unit, "angle")),
                        'z': self._evaluate_expression(fr_el.get('z'), get_unit_value(unit, "angle"))
                    }
                elif fr_ref_el is not None:
                    rot_def = self.geometry_state.get_define(fr_ref_el.get('ref'))
                    if rot_def and rot_def.type == 'rotation': first_transform['rotation'] = rot_def.value

                params = {
                    'first_ref': first_ref, 'second_ref': second_ref,
                    'transform_second': transform,
                    'transform_first': first_transform
                }

            elif solid_type == 'polycone' or solid_type == 'genericPolycone':
                params['startphi'] = self._evaluate_expression(solid_el.get('startphi'), aunit_val)
                params['deltaphi'] = self._evaluate_expression(solid_el.get('deltaphi'), aunit_val)
                zplanes = []
                rzpoints = []
                for child in solid_el:
                    if child.tag == 'zplane':
                        zplanes.append({
                            'z': self._evaluate_expression(child.get('z'), lunit_val),
                            'rmin': self._evaluate_expression(child.get('rmin'), lunit_val),
                            'rmax': self._evaluate_expression(child.get('rmax'), lunit_val),
                        })
                    elif child.tag == 'rzpoint' and solid_type == 'genericPolycone': # G4GenericPolycone
                         rzpoints.append({
                            'r': self._evaluate_expression(child.get('r'), lunit_val),
                            'z': self._evaluate_expression(child.get('z'), lunit_val),
                        })
                if zplanes: params['zplanes'] = zplanes
                if rzpoints: params['rzpoints'] = rzpoints

            elif solid_type == 'polyhedra' or solid_type == 'genericPolyhedra':
                params['startphi'] = self._evaluate_expression(solid_el.get('startphi'), aunit_val)
                params['deltaphi'] = self._evaluate_expression(solid_el.get('deltaphi'), aunit_val)
                params['numsides'] = int(self._evaluate_expression(solid_el.get('numsides'), 1.0, "dimensionless"))
                zplanes = []
                rzpoints = []
                for child in solid_el:
                    if child.tag == 'zplane': # G4Polyhedra
                        zplanes.append({
                            'z': self._evaluate_expression(child.get('z'), lunit_val),
                            'rmin': self._evaluate_expression(child.get('rmin'), lunit_val),
                            'rmax': self._evaluate_expression(child.get('rmax'), lunit_val),
                        })
                    elif child.tag == 'rzpoint' and solid_type == 'genericPolyhedra': # G4GenericPolyhedra
                         rzpoints.append({
                            'r': self._evaluate_expression(child.get('r'), lunit_val),
                            'z': self._evaluate_expression(child.get('z'), lunit_val),
                        })
                if zplanes: params['zplanes'] = zplanes
                if rzpoints: params['rzpoints'] = rzpoints
            
            elif solid_type == 'xtru':
                two_dim_vertices = []
                sections = []
                for child in solid_el:
                    if child.tag == 'twoDimVertex':
                        two_dim_vertices.append({
                            'x': self._evaluate_expression(child.get('x'), lunit_val),
                            'y': self._evaluate_expression(child.get('y'), lunit_val),
                        })
                    elif child.tag == 'section':
                        sections.append({
                            'zOrder': int(self._evaluate_expression(child.get('zOrder'), 1.0, "dimensionless")),
                            'zPosition': self._evaluate_expression(child.get('zPosition'), lunit_val),
                            'xOffset': self._evaluate_expression(child.get('xOffset'), lunit_val),
                            'yOffset': self._evaluate_expression(child.get('yOffset'), lunit_val),
                            'scalingFactor': self._evaluate_expression(child.get('scalingFactor'), 1.0, "dimensionless"),
                        })
                # Sort sections by zOrder just in case they are not in order in the file
                sections.sort(key=lambda s: s['zOrder'])
                params['twoDimVertices'] = two_dim_vertices
                params['sections'] = sections

            elif solid_type == 'tessellated':
                # <tessellated name=" شکل " lunit="mm" aunit="deg">
                #   <triangular vertex1="v1" vertex2="v2" vertex3="v3"/>
                #   <quadrangular vertex1="v1" vertex2="v2" vertex3="v3" vertex4="v4" type="ABSOLUTE"/>
                # </tessellated>
                # Vertices v1, v2 etc. are refs to <position> defines.
                facets = []
                for facet_el in solid_el:
                    facet_data = {'type': facet_el.tag} # 'triangular' or 'quadrangular'
                    facet_data['vertex_refs'] = []
                    # GDMLReadSolids uses "vertex1", "vertex2" etc. as attribute names.
                    # For a generic approach, we can find all attributes that start with "vertex"
                    # Or rely on a fixed number (3 for triangular, 4 for quadrangular)
                    if facet_el.tag == 'triangular':
                        facet_data['vertex_refs'].extend([
                            facet_el.get('vertex1'), facet_el.get('vertex2'), facet_el.get('vertex3')
                        ])
                    elif facet_el.tag == 'quadrangular':
                        facet_data['vertex_refs'].extend([
                            facet_el.get('vertex1'), facet_el.get('vertex2'),
                            facet_el.get('vertex3'), facet_el.get('vertex4')
                        ])
                        facet_data['facet_type_attr'] = facet_el.get('type', 'ABSOLUTE') # type attr on facet
                    if facet_data['vertex_refs']:
                        facets.append(facet_data)
                params['facets'] = facets
            # Parsing of booleans
            elif solid_type in ['union', 'subtraction', 'intersection']:
                first_ref = solid_el.find('first').get('ref')
                second_ref = solid_el.find('second').get('ref')
                transform = self._resolve_transform(solid_el)
                
                first_transform = {"position": {'x':0,'y':0,'z':0}, "rotation": {'x':0,'y':0,'z':0}}
                fp_el = solid_el.find('firstposition')
                fp_ref_el = solid_el.find('firstpositionref')
                fr_el = solid_el.find('firstrotation')
                fr_ref_el = solid_el.find('firstrotationref')

                if fp_el is not None:
                     unit = fp_el.get('unit', 'mm')
                     first_transform['position'] = {
                        'x': self._evaluate_expression(fp_el.get('x'), get_unit_value(unit, "length")),
                        'y': self._evaluate_expression(fp_el.get('y'), get_unit_value(unit, "length")),
                        'z': self._evaluate_expression(fp_el.get('z'), get_unit_value(unit, "length"))
                     }
                elif fp_ref_el is not None:
                    pos_def = self.geometry_state.get_define(fp_ref_el.get('ref'))
                    if pos_def and pos_def.type == 'position': first_transform['position'] = pos_def.value

                if fr_el is not None:
                    unit = fr_el.get('unit', 'rad')
                    first_transform['rotation'] = {
                        'x': self._evaluate_expression(fr_el.get('x'), get_unit_value(unit, "angle")),
                        'y': self._evaluate_expression(fr_el.get('y'), get_unit_value(unit, "angle")),
                        'z': self._evaluate_expression(fr_el.get('z'), get_unit_value(unit, "angle"))
                    }
                elif fr_ref_el is not None:
                    rot_def = self.geometry_state.get_define(fr_ref_el.get('ref'))
                    if rot_def and rot_def.type == 'rotation': first_transform['rotation'] = rot_def.value

                params = {
                    'first_ref': first_ref, 'second_ref': second_ref,
                    'transform_second': transform,
                    'transform_first': first_transform
                }

            # TODO: Add other solids: reflectedSolid, scaledSolid
            # For reflectedSolid and scaledSolid, store ref to original solid and the transformation params.
            
            else:
                print(f"GDML Parser: Solid type '{solid_type}' (name: {name}) not fully implemented yet. Storing raw attributes.")
                # Store all attributes as strings for unrecognized solids for now
                params['attributes_raw'] = {k: v for k, v in solid_el.attrib.items() if k != 'name'}

            if params or solid_type == 'tessellated': # Tessellated might have empty params dict if facets are complex
                temp_solids[name] = Solid(name, solid_type, params)
                #self.geometry_state.add_solid(Solid(name, solid_type, params))
        
        # --- Post-processing step for booleans ---
        final_solids = {}
        consumed_solids = set()

        for name, solid_obj in temp_solids.items():
            if name in consumed_solids:
                continue

            if solid_obj.type in ['union', 'subtraction', 'intersection']:
                try:
                    recipe, consumed_names = self._build_boolean_recipe(solid_obj, temp_solids)
                    
                    # Create the new "virtual" boolean solid
                    virtual_boolean = Solid(name, "boolean", {"recipe": recipe})
                    final_solids[name] = virtual_boolean
                    
                    consumed_solids.update(consumed_names)
                except (ValueError, KeyError) as e:
                    print(f"Warning: Could not process boolean solid '{name}'. It may be malformed or reference a missing solid. Error: {e}")
                    # As a fallback, add the unprocessed boolean so it doesn't break other references.
                    if name not in final_solids:
                        final_solids[name] = solid_obj
            else: # It's a primitive or other non-boolean solid
                final_solids[name] = solid_obj

        # Replace the solids in the state with the processed ones
        self.geometry_state.solids = final_solids

    def _parse_structure(self, structure_element):
        if structure_element is None: return

        # --- First Pass: Parse all LV and Assembly definitions ---
        for element in structure_element:
            if element.tag == 'volume':
                self._parse_single_lv(element)
            elif element.tag == 'assembly':
                self._parse_single_assembly(element)
        
        # --- Second Pass: Add children to LVs (now that all LVs/Assemblies exist) ---
        for element in structure_element:
            if element.tag == 'volume':
                lv_name = element.get('name')
                lv = self.geometry_state.get_logical_volume(lv_name)
                if lv:
                    self._parse_lv_children(element, lv)
    
    def _parse_single_lv(self, vol_el):
        lv_name = vol_el.get('name')
        solid_ref_el = vol_el.find('solidref')
        mat_ref_el = vol_el.find('materialref')
        if not all([lv_name, solid_ref_el, mat_ref_el]): return

        solid_ref = solid_ref_el.get('ref')
        mat_ref = mat_ref_el.get('ref')
        lv = LogicalVolume(lv_name, solid_ref, mat_ref)
        self.geometry_state.add_logical_volume(lv)

    def _parse_single_assembly(self, asm_el):
        asm_name = asm_el.get('name')
        if not asm_name: return

        assembly = Assembly(asm_name)
        # In an assembly, all children are physvols (no assembly refs)
        for pv_el in asm_el.findall('physvol'):
            pv = self._parse_pv_element(pv_el)
            if pv:
                assembly.add_placement(pv)
        self.geometry_state.add_assembly(assembly)
        
    def _parse_lv_children(self, vol_el, parent_lv: LogicalVolume):
        for pv_el in vol_el.findall('physvol'):
            pv = self._parse_pv_element(pv_el)
            if pv:
                parent_lv.add_child(pv)

    def _parse_pv_element(self, pv_el):
        """Helper to parse a physvol tag and return a PhysicalVolumePlacement object."""
        name = pv_el.get('name', f"pv_{uuid.uuid4().hex[:8]}")
        copy_number = int(self._evaluate_expression(pv_el.get('copynumber', '0'), 1.0, "dimensionless"))
        
        vol_ref_el = pv_el.find('volumeref')
        asm_ref_el = pv_el.find('assemblyref')
        
        if vol_ref_el is None and asm_ref_el is None: return None
        
        volume_ref = vol_ref_el.get('ref') if vol_ref_el is not None else asm_ref_el.get('ref')
        
        # ... (The rest of the position/rotation parsing logic is the same as your old _parse_structure) ...
        pos_val_or_ref, rot_val_or_ref, scale_val_or_ref = None, None, None
        # Position
        pos_el = pv_el.find('position')
        pos_ref_el = pv_el.find('positionref')
        if pos_el is not None:
            unit = pos_el.get('unit', 'mm')
            pos_val_or_ref = {
                'x': self._evaluate_expression(pos_el.get('x'), get_unit_value(unit, "length")),
                'y': self._evaluate_expression(pos_el.get('y'), get_unit_value(unit, "length")),
                'z': self._evaluate_expression(pos_el.get('z'), get_unit_value(unit, "length")),
            }
        elif pos_ref_el is not None:
            pos_val_or_ref = pos_ref_el.get('ref')
        
        # Rotation
        rot_el = pv_el.find('rotation')
        rot_ref_el = pv_el.find('rotationref')
        if rot_el is not None:
            unit = rot_el.get('unit', 'rad')
            rot_val_or_ref = { # ZYX Euler
                'x': self._evaluate_expression(rot_el.get('x'), get_unit_value(unit, "angle")),
                'y': self._evaluate_expression(rot_el.get('y'), get_unit_value(unit, "angle")),
                'z': self._evaluate_expression(rot_el.get('z'), get_unit_value(unit, "angle")),
            }
        elif rot_ref_el is not None:
            rot_val_or_ref = rot_ref_el.get('ref')

        # Scale
        # ... (add scale parsing if needed) ...

        return PhysicalVolumePlacement(name, volume_ref, copy_number, pos_val_or_ref, rot_val_or_ref, scale_val_or_ref)

    def _parse_setup(self, setup_element):
        if setup_element is None: return
        world_el = setup_element.find('world')
        if world_el is not None:
            self.geometry_state.world_volume_ref = world_el.get('ref')
