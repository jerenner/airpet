# src/gdml_parser.py
import xml.etree.ElementTree as ET
import io
import math
import asteval
from .geometry_types import (
    GeometryState, Define, Material, Solid, LogicalVolume, PhysicalVolumePlacement, Assembly,
    UNIT_FACTORS, convert_to_internal_units, get_unit_value
)

class GDMLParser:
    def __init__(self):
        self.geometry_state = GeometryState()
        self.aeval = asteval.Interpreter(symtable={}, minimal=True, no_if=True, no_for=True, no_while=True, no_try=True)

    def _strip_namespace(self, gdml_content_string):
        it = ET.iterparse(io.StringIO(gdml_content_string))
        for _, el in it:
            if '}' in el.tag:
                el.tag = el.tag.split('}', 1)[1]
        return it.root

    def parse_gdml_string(self, gdml_content_string):
        self.geometry_state = GeometryState() # Reset for new parse
        root = self._strip_namespace(gdml_content_string)

        # Parse sections in order, but evaluation is deferred
        self._parse_defines(root.find('define'))

        self._parse_materials(root.find('materials'))
        self._parse_solids(root.find('solids'))
        self._parse_structure(root.find('structure'))
        self._parse_setup(root.find('setup'))
        
        return self.geometry_state

    def _is_expression(self, value_str):
        if not isinstance(value_str, str):
            return False
        # Improved heuristic: if it contains operators or letters, it's an expression.
        if any(c in value_str for c in "+-*/()"):
            return True
        # Check for letters that are not part of a number format (e.g., 'e' in 1.e-25)
        try:
            float(value_str)
            return False # It's just a number
        except ValueError:
            return True # Contains non-numeric characters

    def _parse_defines(self, define_element):
        if define_element is None: return
        
        for element in define_element:
            name = element.get('name')
            if not name: continue
            
            tag = element.tag
            raw_expression = None
            unit = None
            category = None

            if tag == 'constant' or tag == 'quantity':
                raw_expression = element.get('value')
                unit = element.get('unit') # Can be None
                if unit:
                    for cat_name, u_map in UNIT_FACTORS.items():
                        if unit in u_map:
                            category = cat_name
                            break
                else:
                    category = "dimensionless"
            
            elif tag == 'expression':
                raw_expression = element.text.strip() if element.text else ""
                category = "dimensionless"

            elif tag in ['position', 'rotation', 'scale']:
                raw_expression = {k: v for k, v in element.attrib.items() if k not in ['name', 'unit']}
                unit = element.get('unit')
                if tag == 'rotation': category = 'angle'
                elif tag == 'position': category = 'length'
                else: category = 'dimensionless'
            
            if raw_expression is not None:
                # The 'type' is the XML tag itself, which is what we want.
                define_obj = Define(name, tag, raw_expression, unit, category)
                self.geometry_state.add_define(define_obj)

    def _parse_materials(self, materials_element):
        if materials_element is None: return
        for element in materials_element:
            if element.tag == 'material':
                name = element.get('name')
                if not name: continue

                state = element.get('state')
                Z_expr = element.get('Z') # Can be None
                
                density_expr = None
                d_el = element.find('D')
                if d_el is not None:
                    density_expr = d_el.get('value')
                
                A_expr = None
                atom_el = element.find('atom')
                if atom_el is not None:
                    A_expr = atom_el.get('value')
                
                mat = Material(name, Z_expr=Z_expr, A_expr=A_expr, density_expr=density_expr, state=state)
                
                # Handle components (fractions)
                for frac_el in element.findall('fraction'):
                    mat.components.append({
                        "ref": frac_el.get('ref'),
                        "fraction": frac_el.get('n') # Store as string expression
                    })

                self.geometry_state.add_material(mat)

    def _resolve_transform(self, parent_element):
        pos_val_or_ref, rot_val_or_ref, scale_val_or_ref = None, None, None

        pos_el = parent_element.find('position')
        pos_ref_el = parent_element.find('positionref')
        rot_el = parent_element.find('rotation')
        rot_ref_el = parent_element.find('rotationref')
        scale_el = parent_element.find('scale')
        scale_ref_el = parent_element.find('scaleref')

        if pos_ref_el is not None:
            pos_val_or_ref = pos_ref_el.get('ref')
        elif pos_el is not None:
            pos_val_or_ref = {'x': pos_el.get('x'), 'y': pos_el.get('y'), 'z': pos_el.get('z')}

        if rot_ref_el is not None:
            rot_val_or_ref = rot_ref_el.get('ref')
        elif rot_el is not None:
            rot_val_or_ref = {'x': rot_el.get('x'), 'y': rot_el.get('y'), 'z': rot_el.get('z')}

        if scale_ref_el is not None:
            scale_val_or_ref = scale_ref_el.get('ref')
        elif scale_el is not None:
            scale_val_or_ref = {'x': scale_el.get('x'), 'y': scale_el.get('y'), 'z': scale_el.get('z')}

        return pos_val_or_ref, rot_val_or_ref, scale_val_or_ref

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
            first_ref = current_boolean.raw_parameters.get('first_ref')
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
        base_transform = first_op_in_chain.raw_parameters.get('transform_first')
        
        recipe.append({
            'op': 'base',
            'solid_ref': base_solid_ref,
            'transform': base_transform
        })
        
        # Add the subsequent operations from the chain
        for boolean_op in lineage:
            second_ref = boolean_op.raw_parameters.get('second_ref')
            if not second_ref:
                 raise ValueError(f"Boolean solid '{boolean_op.name}' is missing 'second_ref'.")

            op_name = boolean_op.type
            transform = boolean_op.raw_parameters.get('transform_second')
            
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
            name = solid_el.get('name')
            if not name: continue

            params = {}
            solid_type = solid_el.tag

            # Unit-aware parameters
            params = {}
            
            # Get default units from the solid's tag
            default_lunit = solid_el.get('lunit')
            default_aunit = solid_el.get('aunit')

            # Define which parameters are lengths and which are angles
            length_params = ['x', 'y', 'z', 'rmin', 'rmax', 'r', 'dx', 'dy', 'dz', 'dx1', 'dx2', 'dy1', 'dy2', 'rtor', 'ax', 'by', 'cz', 'zcut1', 'zcut2', 'zmax', 'zcut', 'rlo', 'rhi']
            angle_params = ['startphi', 'deltaphi', 'starttheta', 'deltatheta', 'alpha', 'theta', 'phi', 'inst', 'outst', 'PhiTwist', 'alpha1', 'alpha2', 'Alph', 'Theta', 'Phi', 'twistedangle']

            # Copy all attributes to params, but build expression strings for units
            for key, val in solid_el.attrib.items():
                if key == 'name' or key == 'lunit' or key == 'aunit':
                    continue
                
                # If a parameter has a specific default unit, build the expression
                if key in length_params and default_lunit:
                    params[key] = f"({val}) * {default_lunit}"
                elif key in angle_params and default_aunit:
                    params[key] = f"({val}) * {default_aunit}"
                else:
                    # Otherwise, store the raw value/expression
                    params[key] = val

            # For solids with child tags (polycone, xtru, tessellated, etc.),
            # we need to parse them and add them to the params dictionary.
            if solid_type in ['polycone', 'genericPolycone', 'polyhedra', 'genericPolyhedra']:
                params['zplanes'] = []
                params['rzpoints'] = []
                for child in solid_el:
                    if child.tag == 'zplane':
                        params['zplanes'].append({k: v for k, v in child.attrib.items()})
                    elif child.tag == 'rzpoint':
                        params['rzpoints'].append({k: v for k, v in child.attrib.items()})

            elif solid_type == 'xtru':
                params['twoDimVertices'] = []
                params['sections'] = []
                for child in solid_el:
                    if child.tag == 'twoDimVertex':
                        params['twoDimVertices'].append({k: v for k, v in child.attrib.items()})
                    elif child.tag == 'section':
                        params['sections'].append({k: v for k, v in child.attrib.items()})
                params['sections'].sort(key=lambda s: int(s.get('zOrder', 0)))

            elif solid_type == 'tessellated':
                params['facets'] = []
                for facet_el in solid_el:
                    if facet_el.tag in ['triangular', 'quadrangular']:
                        facet_data = {'type': facet_el.tag, 'vertex_refs': []}
                        if facet_el.tag == 'triangular':
                            facet_data['vertex_refs'] = [facet_el.get('vertex1'), facet_el.get('vertex2'), facet_el.get('vertex3')]
                        else:
                            facet_data['vertex_refs'] = [facet_el.get('vertex1'), facet_el.get('vertex2'), facet_el.get('vertex3'), facet_el.get('vertex4')]
                        params['facets'].append(facet_data)
                        
            elif solid_type in ['union', 'subtraction', 'intersection']:
                first_ref = solid_el.find('first').get('ref')
                second_ref = solid_el.find('second').get('ref')
                pos, rot, _ = self._resolve_transform(solid_el) # For the second solid
                
                # Handling for first solid transform as well
                first_pos_el = solid_el.find('firstposition')
                first_pos_ref_el = solid_el.find('firstpositionref')
                first_rot_el = solid_el.find('firstrotation')
                first_rot_ref_el = solid_el.find('firstrotationref')
                
                first_pos, first_rot = None, None
                if first_pos_ref_el is not None: first_pos = first_pos_ref_el.get('ref')
                elif first_pos_el is not None: first_pos = {k: v for k, v in first_pos_el.attrib.items() if k != 'unit'}

                if first_rot_ref_el is not None: first_rot = first_rot_ref_el.get('ref')
                elif first_rot_el is not None: first_rot = {k: v for k, v in first_rot_el.attrib.items() if k != 'unit'}
                
                params = {
                    'first_ref': first_ref, 'second_ref': second_ref,
                    'transform_second': {'position': pos, 'rotation': rot},
                    'transform_first': {'position': first_pos, 'rotation': first_rot}
                }
            
            temp_solids[name] = Solid(name, solid_type, params)
        
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
                print(f"Parsing lv {element.get('name')}")
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
        if not lv_name or solid_ref_el is None or mat_ref_el is None:
            print(f"Skipping incomplete logical volume: {lv_name}")
            return

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
        name = pv_el.get('name', f"pv_default")
        
        # Store the raw string expression for copy number
        copy_number_expr = pv_el.get('copynumber', '0')
        
        vol_ref_el = pv_el.find('volumeref')
        asm_ref_el = pv_el.find('assemblyref')
        
        if vol_ref_el is None and asm_ref_el is None: return None
        
        volume_ref = vol_ref_el.get('ref') if vol_ref_el is not None else asm_ref_el.get('ref')
        pos_val_or_ref, rot_val_or_ref, scale_val_or_ref = self._resolve_transform(pv_el)

        return PhysicalVolumePlacement(name, volume_ref, copy_number_expr, pos_val_or_ref, rot_val_or_ref, scale_val_or_ref)

    def _parse_setup(self, setup_element):
        if setup_element is None: return
        world_el = setup_element.find('world')
        if world_el is not None:
            self.geometry_state.world_volume_ref = world_el.get('ref')
