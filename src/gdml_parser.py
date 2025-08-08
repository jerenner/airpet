# src/gdml_parser.py
import xml.etree.ElementTree as ET
import io
import math
import asteval
import re
import uuid
from .expression_evaluator import create_configured_asteval
from .geometry_types import (
    GeometryState, Define, Material, Element, Isotope, Solid, LogicalVolume, PhysicalVolumePlacement, 
    Assembly, DivisionVolume, ReplicaVolume, ParamVolume, Parameterisation,
    OpticalSurface, SkinSurface, BorderSurface,
    UNIT_FACTORS, convert_to_internal_units, get_unit_value
)

class GDMLParser:
    def __init__(self):
        self.geometry_state = GeometryState()
        self.aeval = create_configured_asteval()

    def _strip_namespace(self, gdml_content_string):
        it = ET.iterparse(io.StringIO(gdml_content_string))
        for _, el in it:
            if '}' in el.tag:
                el.tag = el.tag.split('}', 1)[1]
        return it.root

    def _evaluate_name(self, name_expr):
        """
        Helper to evaluate a name attribute that might contain a loop variable.
        If evaluation fails, it assumes the name is a literal string.
        """
        if not isinstance(name_expr, str):
            return name_expr

        # Find all substrings that look like variables/expressions inside brackets or on their own
        parts = re.split(r'(\[.*?\])', name_expr)
        
        # A more robust regex to find variables, including those not in brackets
        # This will find 'i', 'j', 'k', and 'ALUCONST' in "ALU[i][j][k]_ALUCONST"
        # It looks for valid python identifiers.
        all_vars = re.findall(r'[a-zA-Z_][a-zA-Z0-9_]*', name_expr)

        evaluated_name = name_expr
        
        for var in set(all_vars): # Use set to avoid duplicate replacements
            if var in self.aeval.symtable:
                try:
                    # Get the value from our stateful asteval instance
                    value = self.aeval.symtable[var]
                    # Replace the variable name (as a whole word) with its value
                    evaluated_name = re.sub(r'\b' + re.escape(var) + r'\b', str(value), evaluated_name)
                except Exception:
                    # Ignore if a variable can't be evaluated; it might be part of a literal string
                    pass
        
        # Final cleanup for common GDML artifacts that are not filesystem-friendly
        return evaluated_name.replace('[','_').replace(']','_').replace('__','_').strip('_')

    def _partially_evaluate(self, expression_str, loop_vars):
        """
        Substitutes the current numeric values of loop variables into an expression string.
        Leaves other variable names as they are.
        Example: if i=2, "64-10*i" becomes "64-10*2". "WorldWidth" remains "WorldWidth".
        """
        if not isinstance(expression_str, str):
            return expression_str
            
        for var, value in loop_vars.items():
            # Use regex to replace only whole words to avoid replacing 'i' in 'sin'
            expression_str = re.sub(r'\b' + re.escape(var) + r'\b', str(value), expression_str)
            
        return expression_str

    def parse_gdml_string(self, gdml_content_string):
        self.aeval = create_configured_asteval()
        self.geometry_state = GeometryState()
        root = self._strip_namespace(gdml_content_string)
        self._parse_defines(root.find('define'))
        self._parse_materials(root.find('materials'))
        self._parse_solids(root.find('solids'))
        self._parse_structure(root.find('structure'))
        self._parse_setup(root.find('setup'))

        # Clean up loop variables after parsing is complete
        self.geometry_state.defines = {
            name: define_obj for name, define_obj in self.geometry_state.defines.items()
            if define_obj.category != "loop_variable"
        }

        return self.geometry_state

    def _is_expression(self, value_str): # This function is no longer strictly necessary but can be kept
        if not isinstance(value_str, str):
            return False
        # A simple check for operators that would indicate an expression
        if any(c in value_str for c in "+-*/()[]"):
            return True
        # If it's not a valid number, it might be a variable reference
        try:
            float(value_str)
            return False
        except ValueError:
            return True

    def _process_children(self, element, handler, **kwargs):
        """
        Iterates over child elements, expanding loops and calling the
        appropriate handler function for each element.
        """
        if element is None:
            return

        for child in element:
            if child.tag == 'loop':
                loop_var_name = child.get('for')
                start_str = child.get('from', '0')
                end_str = child.get('to', '0')
                step_str = child.get('step', '1')

                loop_var_define = self.geometry_state.defines.get(loop_var_name)
                if not loop_var_define or loop_var_define.type != 'variable':
                    print(f"Warning: Loop variable '{loop_var_name}' not defined as a <variable>. Skipping loop.")
                    continue
                
                try:
                    start = int(self.aeval.eval(start_str))
                    end = int(self.aeval.eval(end_str))
                    step = int(self.aeval.eval(step_str))
                except Exception as e:
                    print(f"Warning: Could not evaluate loop parameters. Skipping loop. Error: {e}")
                    continue

                for i in range(start, end + 1, step):
                    self.aeval.symtable[loop_var_name] = i
                    self._process_children(child, handler, **kwargs)
                
                if loop_var_name in self.aeval.symtable:
                    del self.aeval.symtable[loop_var_name]
            else:
                handler(child, **kwargs)

    def _parse_defines(self, define_element):
        if define_element is None: return

        def define_handler(element):
            name_expr = element.get('name')
            if not name_expr: return

            # Evaluate the name
            name = self._evaluate_name(name_expr)

            tag = element.tag
            raw_expression = None
            unit = None
            category = None

            if tag == 'constant' or tag == 'quantity' or tag == 'variable':
                raw_expression = element.get('value')
                unit = element.get('unit')
                if tag == 'variable':
                    category = "loop_variable"
                elif unit:
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
                default_val = '1' if tag == 'scale' else '0'
                # Explicitly get each attribute with a default value
                raw_expression = {
                    'x': element.get('x', default_val),
                    'y': element.get('y', default_val),
                    'z': element.get('z', default_val)
                }
                unit = element.get('unit')
                if tag == 'rotation': category = 'angle'
                elif tag == 'position': category = 'length'
                else: category = 'dimensionless'
            
            if raw_expression is not None:
                define_obj = Define(name, tag, raw_expression, unit, category)
                self.geometry_state.add_define(define_obj)
                # Eagerly evaluate and add to symbol table if possible
                try:
                    if isinstance(raw_expression, dict):
                        # For vectors, just add the name. The values will be evaluated later.
                         self.aeval.symtable[name] = {k: self.aeval.eval(v) for k, v in raw_expression.items()}
                    else:
                        eval_value = self.aeval.eval(str(raw_expression))
                        if unit:
                            eval_value *= get_unit_value(unit, category)
                        define_obj.value = eval_value
                        self.aeval.symtable[name] = eval_value
                except Exception:
                    pass # Will be handled properly in recalculate_geometry_state

        self._process_children(define_element, define_handler)

    def _parse_materials(self, materials_element):
        if materials_element is None: return

        # Find and parse any defines local to the materials block first
        local_defines = materials_element.find('define')
        if local_defines is not None:
            self._parse_defines(local_defines)
            
        def material_handler(element):
            # Process <material> OR <element> tags
            tag = element.tag

            if tag == 'material':
                name_expr = element.get('name')
                if not name_expr: return
                name = self._evaluate_name(name_expr)

                state = element.get('state')
                Z_expr = element.get('Z')
                density_expr = None
                d_el = element.find('D')
                if d_el is not None:
                    density_expr = d_el.get('value')
                A_expr = None
                atom_el = element.find('atom')
                if atom_el is not None:
                    A_expr = atom_el.get('value')
                
                mat = Material(name, Z_expr=Z_expr, A_expr=A_expr, density_expr=density_expr, state=state)
                
                # Handle composition by mass fraction
                for frac_el in element.findall('fraction'):
                    # Evaluate the fraction reference
                    frac_ref_expr = frac_el.get('ref')
                    frac_ref = self._evaluate_name(frac_ref_expr)
                    mat.components.append({
                        "ref": frac_ref,
                        "fraction": frac_el.get('n')
                    })

                # Handle composition by number of atoms
                for comp_el in element.findall('composite'):
                    comp_ref_expr = comp_el.get('ref')
                    comp_ref = self._evaluate_name(comp_ref_expr)
                    mat.components.append({
                        "ref": comp_ref,
                        "natoms": comp_el.get('n') # Keep 'n' as an expression string
                    })

                self.geometry_state.add_material(mat)
            
            elif tag == 'element':
                name_expr = element.get('name')
                if not name_expr: return
                name = self._evaluate_name(name_expr)

                formula = element.get('formula')
                Z_expr = element.get('Z') # Z can be an expression
                
                atom_el = element.find('atom')
                A_expr = atom_el.get('value') if atom_el is not None else None
                
                new_element = Element(name, formula=formula, Z=Z_expr, A_expr=A_expr)

                # Check for isotope fractions (we'll parse isotopes later)
                for frac_el in element.findall('fraction'):
                    iso_ref_expr = frac_el.get('ref')
                    iso_ref = self._evaluate_name(iso_ref_expr)
                    new_element.components.append({
                        "ref": iso_ref,
                        "fraction": frac_el.get('n')
                    })
                
                self.geometry_state.add_element(new_element)
            
            elif tag == 'isotope':
                name_expr = element.get('name')
                if not name_expr: return
                name = self._evaluate_name(name_expr)

                N_expr = element.get('N')
                Z_expr = element.get('Z')

                atom_el = element.find('atom')
                A_expr = atom_el.get('value') if atom_el is not None else None

                new_isotope = Isotope(name, N=N_expr, Z=Z_expr, A_expr=A_expr)
                self.geometry_state.add_isotope(new_isotope)

        self._process_children(materials_element, material_handler)

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
            # FIX 2: Evaluate expressions for x, y, z here
            pos_val_or_ref = {
                'x': str(self.aeval.eval(pos_el.get('x', '0'))),
                'y': str(self.aeval.eval(pos_el.get('y', '0'))),
                'z': str(self.aeval.eval(pos_el.get('z', '0')))
            }
        
        if rot_ref_el is not None:
            rot_val_or_ref = rot_ref_el.get('ref')
        elif rot_el is not None:
            # FIX 2: Evaluate expressions for x, y, z here
            rot_val_or_ref = {
                'x': str(self.aeval.eval(rot_el.get('x', '0'))),
                'y': str(self.aeval.eval(rot_el.get('y', '0'))),
                'z': str(self.aeval.eval(rot_el.get('z', '0')))
            }

        if scale_ref_el is not None:
            scale_val_or_ref = scale_ref_el.get('ref')
        elif scale_el is not None:
            scale_val_or_ref = {'x': scale_el.get('x'), 'y': scale_el.get('y'), 'z': scale_el.get('z')}
            
        return pos_val_or_ref, rot_val_or_ref, scale_val_or_ref

    def _build_boolean_recipe(self, top_level_boolean, all_solids):
        lineage = [top_level_boolean]
        consumed_names = {top_level_boolean.name}
        current_boolean = top_level_boolean

        while True:
            first_ref_expr = current_boolean.raw_parameters.get('first_ref')
            if not first_ref_expr:
                raise ValueError(f"Boolean solid '{current_boolean.name}' is missing 'first_ref'.")
            first_ref = self._evaluate_name(first_ref_expr)
            
            first_solid = all_solids.get(first_ref)
            if not first_solid:
                 raise ValueError(f"Could not find solid '{first_ref}' referenced by '{current_boolean.name}'.")

            if first_solid.type in ['union', 'subtraction', 'intersection']:
                lineage.insert(0, first_solid)
                consumed_names.add(first_solid.name)
                current_boolean = first_solid
            else:
                base_solid_ref = first_solid.name
                break

        recipe = []
        first_op_in_chain = lineage[0]
        base_transform = first_op_in_chain.raw_parameters.get('transform_first')
        recipe.append({
            'op': 'base',
            'solid_ref': base_solid_ref,
            'transform': base_transform
        })

        for boolean_op in lineage:
            second_ref_expr = boolean_op.raw_parameters.get('second_ref')
            if not second_ref_expr:
                 raise ValueError(f"Boolean solid '{boolean_op.name}' is missing 'second_ref'.")
            second_ref = self._evaluate_name(second_ref_expr)

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
        
        # Find and parse any defines local to the solids block first
        local_defines = solids_element.find('define')
        if local_defines is not None:
            self._parse_defines(local_defines)

        temp_solids = {}

        def solid_handler(solid_el):
            # Treat name as a literal string. Loops will create solids with distinct names
            # based on the loop variable, which is handled fine by ProjectManager later.
            name_expr = solid_el.get('name')
            if not name_expr: return

            # Evaluate the name
            name = self._evaluate_name(name_expr)
            solid_type = solid_el.tag

            # Handle opticalsurface tag
            if solid_type == 'opticalsurface':
                model = solid_el.get('model', 'glisur')
                finish = solid_el.get('finish', 'polished')
                surf_type = solid_el.get('type', 'dielectric_dielectric')
                value = solid_el.get('value', '1.0')
                
                optical_surf = OpticalSurface(name, model, finish, surf_type, value)

                # Parse nested <property> tags
                for prop_el in solid_el.findall('property'):
                    prop_name = prop_el.get('name')
                    prop_ref = prop_el.get('ref')
                    if prop_name and prop_ref:
                        optical_surf.properties[prop_name] = prop_ref
                
                self.geometry_state.add_optical_surface(optical_surf)
                return # End processing for this element

            # --- Handle scaledSolid tag ---
            if solid_type == 'scaledSolid':
                params = {}
                solidref_el = solid_el.find('solidref')
                scaleref_el = solid_el.find('scaleref')
                scale_el = solid_el.find('scale')

                if solidref_el is not None:
                    params['solid_ref'] = solidref_el.get('ref')
                
                if scaleref_el is not None:
                    params['scale'] = scaleref_el.get('ref')
                elif scale_el is not None:
                    params['scale'] = {k: v for k, v in scale_el.attrib.items() if k != 'name'}
                
                temp_solids[name] = Solid(name, solid_type, params)
                return # End processing for this element

            # --- Handle reflectedSolid tag ---
            if solid_type == 'reflectedSolid':
                params = {}
                solidref_el = solid_el.find('solidref')
                if solidref_el is not None:
                    params['solid_ref'] = solidref_el.get('ref')
                
                # A reflected solid has a full transform, just like a physvol
                pos, rot, scl = self._resolve_transform(solid_el)
                params['transform'] = {
                    'position': pos,
                    'rotation': rot,
                    'scale': scl
                }
                
                temp_solids[name] = Solid(name, solid_type, params)
                return # End processing for this element

            # --- Handle multiUnion tag ---
            if solid_type == 'multiUnion':
                recipe = []
                # Find all multiUnionNode children
                nodes = solid_el.findall('multiUnionNode')
                if not nodes:
                    print(f"Warning: <multiUnion> solid '{name}' has no nodes. Skipping.")
                    return

                # The first node is the 'base' of our recipe
                first_node = nodes[0]
                base_solid_ref = first_node.find('solid').get('ref')
                recipe.append({
                    'op': 'base',
                    'solid_ref': self._evaluate_name(base_solid_ref),
                    'transform': None # Base solid has no transform relative to itself
                })

                # Subsequent nodes are 'union' operations
                for node in nodes[1:]:
                    solid_ref_expr = node.find('solid').get('ref')
                    pos, rot, _ = self._resolve_transform(node) # Use existing helper
                    recipe.append({
                        'op': 'union',
                        'solid_ref': self._evaluate_name(solid_ref_expr),
                        'transform': {'position': pos, 'rotation': rot}
                    })
                
                # Create a 'boolean' solid in our internal representation
                params = {"recipe": recipe}
                temp_solids[name] = Solid(name, "boolean", params)
                return

            # Unit-aware parameters
            params = {}

            # Get default units from the solid's tag
            default_lunit = solid_el.get('lunit')
            default_aunit = solid_el.get('aunit')

            # Define which parameters are lengths and which are angles
            length_params = ['x', 'y', 'z', 'rmin', 'rmax', 'r', 'dx', 'dy', 'dz', 
                            'dx1', 'dx2', 'dy1', 'dy2', 'rtor', 'ax', 'by', 'cz', 
                            'zcut1', 'zcut2', 'zmax', 'zcut', 'rlo', 'rhi']
            angle_params = ['startphi', 'deltaphi', 'starttheta', 'deltatheta', 'alpha', 
                            'theta', 'phi', 'inst', 'outst', 'PhiTwist', 'alpha1', 'alpha2', 
                            'Alph', 'Theta', 'Phi', 'twistedangle']
            
            # Get current values of loop variables from the asteval instance
            current_loop_vars = {
                k: v for k, v in self.aeval.symtable.items() 
                if self.geometry_state.defines.get(k) and self.geometry_state.defines.get(k).category == 'loop_variable'
            }

            for key, val in solid_el.attrib.items():
                if key in ['name', 'lunit', 'aunit']:
                    continue

                # Partially evaluate the expression, substituting loop variables
                processed_val = val
                try:
                    # If it's a string that looks like an integer but isn't a simple '0',
                    # cast it to float to remove leading zeros, then back to string.
                    if processed_val.startswith('0') and len(processed_val) > 1 and '.' not in processed_val:
                         processed_val = str(float(processed_val))
                except (ValueError, TypeError):
                    # It's not a simple number, so it must be an expression. Leave it as is.
                    pass
                
                partially_eval_val = self._partially_evaluate(processed_val, current_loop_vars)

                if key in length_params and default_lunit:
                    params[key] = f"({partially_eval_val}) * {default_lunit}"
                elif key in angle_params and default_aunit:
                    params[key] = f"({partially_eval_val}) * {default_aunit}"
                else:
                    params[key] = partially_eval_val

            # Handle nested tags for complex solids
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
                pos, rot, _ = self._resolve_transform(solid_el)
                
                first_pos_el = solid_el.find('firstposition')
                first_pos_ref_el = solid_el.find('firstpositionref')
                first_rot_el = solid_el.find('firstrotation')
                first_rot_ref_el = solid_el.find('firstrotationref')
                
                first_pos, first_rot = None, None
                if first_pos_ref_el is not None: first_pos = first_pos_ref_el.get('ref')
                elif first_pos_el is not None: first_pos = {k: v for k, v in first_pos_el.attrib.items() if k != 'unit'}
                
                if first_rot_ref_el is not None: first_rot = first_rot_ref_el.get('ref')
                elif first_rot_el is not None: first_rot = {k: v for k, v in first_rot_el.attrib.items() if k != 'unit'}

                # Overwrite params dict specifically for booleans
                params = {
                    'first_ref': first_ref, 'second_ref': second_ref,
                    'transform_second': {'position': pos, 'rotation': rot},
                    'transform_first': {'position': first_pos, 'rotation': first_rot}
                }
            
            temp_solids[name] = Solid(name, solid_type, params)
        
        self._process_children(solids_element, solid_handler)

        final_solids = {}
        consumed_solids = set()
        for name, solid_obj in temp_solids.items():
            if name in consumed_solids:
                continue
            if solid_obj.type in ['union', 'subtraction', 'intersection']:
                try:
                    recipe, consumed_names = self._build_boolean_recipe(solid_obj, temp_solids)
                    virtual_boolean = Solid(name, "boolean", {"recipe": recipe})
                    final_solids[name] = virtual_boolean
                    consumed_solids.update(consumed_names)
                except (ValueError, KeyError) as e:
                    print(f"Warning: Could not process boolean solid '{name}'. It may be malformed or reference a missing solid. Error: {e}")
                    if name not in final_solids:
                        final_solids[name] = solid_obj
            else:
                final_solids[name] = solid_obj

        self.geometry_state.solids = final_solids

    def _parse_structure(self, structure_element):
        if structure_element is None: return

        # First pass: define all LVs and Assemblies so they can be referenced
        def first_pass_handler(element):
            if element.tag == 'volume':
                self._parse_single_lv(element)
            elif element.tag == 'assembly':
                self._parse_single_assembly(element)

        self._process_children(structure_element, first_pass_handler)
        
        # Second pass: populate the children of the LVs now that all are defined
        def second_pass_handler(element):
            if element.tag == 'volume':
                lv_name = element.get('name')
                lv = self.geometry_state.get_logical_volume(lv_name)
                if lv:
                    self._parse_lv_children(element, lv)
            # Parse surface tags in the second pass
            elif element.tag in ['skinsurface', 'bordersurface']:
                self._parse_surface(element)

        self._process_children(structure_element, second_pass_handler)

    def _parse_surface(self, surf_el):
        """Parses a <skinsurface> or <bordersurface> tag."""
        name = surf_el.get('name')
        if not name: return

        surface_property_ref = surf_el.get('surfaceproperty')
        if not surface_property_ref:
            print(f"Warning: Surface '{name}' is missing a surfaceproperty reference. Skipping.")
            return
        
        if surf_el.tag == 'skinsurface':
            volumeref_el = surf_el.find('volumeref')
            if not volumeref_el:
                print(f"Warning: Skin surface '{name}' is missing a volumeref. Skipping.")
                return
            
            volume_ref = self._evaluate_name(volumeref_el.get('ref'))
            skin_surf = SkinSurface(name, volume_ref, surface_property_ref)
            self.geometry_state.add_skin_surface(skin_surf)

        elif surf_el.tag == 'bordersurface':
            physvol_refs = surf_el.findall('physvolref')
            if len(physvol_refs) < 2:
                print(f"Warning: Border surface '{name}' needs two physvolref tags. Skipping.")
                return
            
            # Note: GDML does not name PV placements. The ref here points to the LV, and Geant4
            # figures out the PVs. Our model needs PV IDs. This is a future challenge.
            # For now, we will store the LV refs and resolve them later.
            # A robust implementation would need to find the unique PV that places LV X inside LV Y.
            # For parsing, we store the *names* of the PVs from the GDML, if they exist.
            # The GDML schema implies these are references to the PV names.
            pv1_ref = self._evaluate_name(physvol_refs[0].get('ref'))
            pv2_ref = self._evaluate_name(physvol_refs[1].get('ref'))
            
            border_surf = BorderSurface(name, pv1_ref, pv2_ref, surface_property_ref)
            self.geometry_state.add_border_surface(border_surf)

    def _parse_single_lv(self, vol_el):
        name_expr = vol_el.get('name')
        if not name_expr: return
        # Evaluate the name
        lv_name = self._evaluate_name(name_expr)

        solid_ref_el = vol_el.find('solidref')
        mat_ref_el = vol_el.find('materialref')

        if not lv_name or solid_ref_el is None or mat_ref_el is None:
            print(f"Skipping incomplete logical volume: {lv_name}")
            return

        solid_ref_expr = solid_ref_el.get('ref')
        solid_ref = self._evaluate_name(solid_ref_expr)
        
        mat_ref_expr = mat_ref_el.get('ref')
        mat_ref = self._evaluate_name(mat_ref_expr)
        
        # Avoid re-defining if it already exists (can happen with loops)
        if not self.geometry_state.get_logical_volume(lv_name):
            lv = LogicalVolume(lv_name, solid_ref, mat_ref)
            self.geometry_state.add_logical_volume(lv)

    def _parse_single_assembly(self, asm_el):
        asm_name = asm_el.get('name')
        if not asm_name: return
        
        # Avoid re-defining
        if not self.geometry_state.get_assembly(asm_name):
            assembly = Assembly(asm_name)
            def pv_handler(pv_el, **kwargs):
                current_assembly = kwargs.get('assembly')
                if pv_el.tag == 'physvol':
                    pv = self._parse_pv_element(pv_el, current_assembly.name)
                    if pv:
                        current_assembly.add_placement(pv)

            self._process_children(asm_el, pv_handler, assembly=assembly)
            self.geometry_state.add_assembly(assembly)

    def _parse_lv_children(self, vol_el, parent_lv: LogicalVolume):
        
        def placement_handler(element, **kwargs):
            parent_lv_obj = kwargs.get('parent_lv')
            if element.tag == 'physvol':
                pv = self._parse_pv_element(element, parent_lv_obj.name)
                if pv:
                    parent_lv_obj.add_child(pv)
            
            elif element.tag == 'replicavol':
                replica = self._parse_replica_vol(element)
                if replica:
                    # Because a loop can contain multiple replica tags (though unusual),
                    # we only process the first one found for a given LV.
                    if parent_lv_obj.content_type == 'physvol':
                        parent_lv_obj.add_child(replica)
                    else:
                        print(f"Warning: Logical Volume '{parent_lv_obj.name}' already has a procedural placement. Skipping extra <replicavol>.")
            
            elif element.tag == 'divisionvol':
                division = self._parse_division_vol(element)
                if division:
                    if parent_lv_obj.content_type == 'physvol':
                        parent_lv_obj.add_child(division)
                    else:
                        print(f"Warning: Logical Volume '{parent_lv_obj.name}' already has a procedural placement. Skipping extra <divisionvol>.")
            
            elif element.tag == 'paramvol':
                param = self._parse_param_vol(element)
                if param:
                    if parent_lv_obj.content_type == 'physvol':
                        parent_lv_obj.add_child(param)
                    else:
                        print(f"Warning: Logical Volume '{parent_lv_obj.name}' already has a procedural placement. Skipping extra <paramvol>.")

        # This call now handles physvols inside loops correctly.
        self._process_children(vol_el, placement_handler, parent_lv=parent_lv)

    def _parse_pv_element(self, pv_el, parent_name):
        """Helper to parse a physvol tag and return a PhysicalVolumePlacement object."""
        name_expr = pv_el.get('name') # Name can be optional in physvol
        name = self._evaluate_name(name_expr) if name_expr else f"pv_default_{uuid.uuid4().hex[:6]}"
        
        # We also need to evaluate the volumeref
        vol_ref_expr = pv_el.find('volumeref').get('ref') if pv_el.find('volumeref') is not None else None
        
        if vol_ref_expr is None: return None

        if vol_ref_expr:
            volume_ref = self._evaluate_name(vol_ref_expr)

        copy_number_expr = pv_el.get('copynumber', '0')
        pos_val_or_ref, rot_val_or_ref, scale_val_or_ref = self._resolve_transform(pv_el)
        
        return PhysicalVolumePlacement(
            name=name,
            volume_ref=volume_ref,
            parent_lv_name=parent_name,
            copy_number_expr=copy_number_expr,
            position_val_or_ref=pos_val_or_ref,
            rotation_val_or_ref=rot_val_or_ref,
            scale_val_or_ref=scale_val_or_ref
        )

    def _parse_replica_vol(self, replica_el):
        """Parses a <replicavol> tag and returns a ReplicaVolume object."""
        # A name for the replica itself is not in the GDML spec,
        # but we can generate one for our UI.
        name = replica_el.get('name', f"replica_{uuid.uuid4().hex[:6]}")
        
        number_expr = replica_el.get('number', '1')
        
        # Initialize defaults
        volume_ref = None
        direction = {}
        width = "0"
        offset = "0"

        # The <replicavol> tag contains a <volumeref> and a <replicate_along_axis> tag.
        volumeref_el = replica_el.find('volumeref')
        if volumeref_el is not None:
            volume_ref = self._evaluate_name(volumeref_el.get('ref'))

        replicator_el = replica_el.find('replicate_along_axis')
        if replicator_el is not None:
            direction_el = replicator_el.find('direction')
            if direction_el is not None:
                direction = {
                    'x': direction_el.get('x', '0'),
                    'y': direction_el.get('y', '0'),
                    'z': direction_el.get('z', '0'),
                }

            width_el = replicator_el.find('width')
            if width_el is not None:
                width = width_el.get('value', '0')
            
            offset_el = replicator_el.find('offset')
            if offset_el is not None:
                offset = offset_el.get('value', '0')

        if not volume_ref:
            print("Warning: <replicavol> found without a <volumeref>. Skipping.")
            return None
        
        return ReplicaVolume(name, volume_ref, number_expr, direction, width, offset)

    def _parse_division_vol(self, division_el):
        """Parses a <divisionvol> tag and returns a DivisionVolume object."""
        # A name for the division itself is not in the GDML spec,
        # but we generate one for our UI representation.
        name = division_el.get('name', f"division_{uuid.uuid4().hex[:6]}")
        
        # Extract attributes from the divisionvol tag itself
        axis = division_el.get('axis')
        number_expr = division_el.get('number')
        width_expr = division_el.get('width')
        offset_expr = division_el.get('offset', '0')
        unit = division_el.get('unit', 'mm')

        if not axis or (not number_expr and not width_expr):
            print("Warning: <divisionvol> is missing required 'axis' and ('number' or 'width') attributes. Skipping.")
            return None

        # Find the nested <volumeref>
        volumeref_el = division_el.find('volumeref')
        if volumeref_el is None:
            print("Warning: <divisionvol> found without a <volumeref>. Skipping.")
            return None
            
        volume_ref = self._evaluate_name(volumeref_el.get('ref'))

        return DivisionVolume(name, volume_ref, axis,
                            number=number_expr,
                            width=width_expr,
                            offset=offset_expr,
                            unit=unit)

    def _parse_setup(self, setup_element):
        if setup_element is None: return
        world_el = setup_element.find('world')
        if world_el is not None:
            self.geometry_state.world_volume_ref = world_el.get('ref')

    def _parse_param_vol(self, param_el):
        """Parses a <paramvol> tag and returns a ParamVolume object."""
        name = param_el.get('name', f"param_{uuid.uuid4().hex[:6]}")
        ncopies = param_el.get('ncopies', '0')
        
        volumeref_el = param_el.find('volumeref')
        if volumeref_el is None:
            print("Warning: <paramvol> is missing <volumeref>. Skipping.")
            return None
        volume_ref = self._evaluate_name(volumeref_el.get('ref'))

        param_vol_obj = ParamVolume(name, volume_ref, ncopies)

        # Look for the wrapper tag, but fall back to searching the whole element.
        search_root = param_el.find('parameterised_position_size')
        if search_root is None:
            search_root = param_el

        for params_el in search_root.iter('parameters'):
            number = params_el.get('number')
            position = None
            dimensions_type = None
            dimensions = {}

            # Find position and dimension tags inside <parameters>
            pos_el = params_el.find('position')
            posref_el = params_el.find('positionref')

            if posref_el is not None:
                position = posref_el.get('ref')
            elif pos_el is not None:
                position = {k: v for k, v in pos_el.attrib.items() if k != 'unit'}

            # Find the first dimensions tag (e.g., <box_dimensions>, <tube_dimensions>)
            for child in params_el:
                if child.tag.endswith('_dimensions'):
                    dimensions_type = child.tag
                    dimensions = {k: v for k, v in child.attrib.items() if k not in ['lunit', 'aunit']}
                    break # Found it, stop searching

            if dimensions_type: # Position can be optional (defaults to origin)
                param_set = Parameterisation(number, position, dimensions_type, dimensions)
                param_vol_obj.add_parameter_set(param_set)
        
        return param_vol_obj