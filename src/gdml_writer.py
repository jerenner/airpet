# src/gdml_writer.py
import xml.etree.ElementTree as ET
from xml.dom import minidom
import math
from .geometry_types import (
    DEFAULT_OUTPUT_LUNIT, DEFAULT_OUTPUT_AUNIT, convert_from_internal_units
)

class GDMLWriter:
    """
    Writes a GeometryState object to a GDML string, handling defines, materials,
    solids (including booleans and multi-unions), structure (including assemblies
    and procedural volumes), and surfaces.
    """
    def __init__(self, geometry_state):
        self.geometry_state = geometry_state
        self.root = ET.Element("gdml", {
            "xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
            "xsi:noNamespaceSchemaLocation": "http://service-spi.web.cern.ch/service-spi/app/releases/GDML/schema/gdml.xsd"
        })
        self.written_solids = set()
        self.written_elements = set()
        self.written_isotopes = set()
        self.written_materials = set()
        self.written_optical_surfaces = set()

    def _add_defines(self):
        if not self.geometry_state.defines: return
        define_el = ET.SubElement(self.root, "define")

        for name, define_obj in self.geometry_state.defines.items():
            if define_obj.type in ['position', 'rotation', 'scale']:
                # Compound defines
                attrs = {"name": name}
                if define_obj.unit: attrs["unit"] = define_obj.unit
                
                raw_expr = define_obj.raw_expression
                if isinstance(raw_expr, dict):
                    attrs.update({k: str(v) for k, v in raw_expr.items()})
                ET.SubElement(define_el, define_obj.type, attrs)

            elif define_obj.type == 'expression':
                # Explicit expression tag
                expr_el = ET.SubElement(define_el, "expression", {"name": name})
                expr_el.text = str(define_obj.raw_expression)

            elif define_obj.type == 'constant':
                # Standard constant with a numeric value
                attrs = {"name": name, "value": str(define_obj.raw_expression)}
                ET.SubElement(define_el, "constant", attrs)

            elif define_obj.type == 'quantity':
                # Quantity with an explicit unit
                attrs = {"name": name, "value": str(define_obj.raw_expression)}
                if define_obj.unit:
                    attrs["unit"] = define_obj.unit
                ET.SubElement(define_el, "quantity", attrs)

            elif define_obj.type == 'matrix':
                raw_expr = define_obj.raw_expression
                attrs = {
                    "name": name,
                    "coldim": str(raw_expr.get('coldim', 1)),
                    "values": " ".join(map(str, raw_expr.get('values', [])))
                }
                ET.SubElement(define_el, "matrix", attrs)


    def _add_materials(self):
        if not (self.geometry_state.materials or self.geometry_state.elements or self.geometry_state.isotopes):
            return
        materials_el = ET.SubElement(self.root, "materials")
        
        # Write isotopes first as they are dependencies for elements
        for name, iso_obj in self.geometry_state.isotopes.items():
            if name in self.written_isotopes: continue
            iso_attrs = {"name": name, "Z": str(iso_obj.Z), "N": str(iso_obj.N)}
            iso_el = ET.SubElement(materials_el, "isotope", iso_attrs)
            ET.SubElement(iso_el, "atom", {"value": str(iso_obj.A_expr)})
            self.written_isotopes.add(name)

        # Write elements, ensuring their isotope dependencies are met
        for name, el_obj in self.geometry_state.elements.items():
            if name in self.written_elements: continue
            el_attrs = {"name": name}
            if el_obj.formula: el_attrs["formula"] = el_obj.formula
            el_el = ET.SubElement(materials_el, "element", el_attrs)
            if el_obj.components:
                for comp in el_obj.components:
                    ET.SubElement(el_el, "fraction", {"ref": comp['ref'], "n": str(comp['fraction'])})
            else:
                el_el.set("Z", str(el_obj.Z))
                ET.SubElement(el_el, "atom", {"value": str(el_obj.A_expr)})
            self.written_elements.add(name)

        # Write materials, ensuring their element/material dependencies are met
        for name, mat_obj in self.geometry_state.materials.items():
            if name in self.written_materials: continue
            
            if mat_obj.mat_type == 'nist':
                # For NIST materials, write only the name and nothing else inside.
                ET.SubElement(materials_el, "material", {"name": name})
                self.written_materials.add(name)
                continue # Move to the next material

            mat_attrs = {"name": name}
            if mat_obj.state: mat_attrs["state"] = mat_obj.state
            mat_el = ET.SubElement(materials_el, "material", mat_attrs)

            if mat_obj.density_expr:
                ET.SubElement(mat_el, "D", {"value": str(mat_obj.density_expr)})

            if mat_obj.components:
                for comp in mat_obj.components:
                    if 'fraction' in comp:
                        ET.SubElement(mat_el, "fraction", {"ref": comp['ref'], "n": str(comp['fraction'])})
                    elif 'natoms' in comp:
                        ET.SubElement(mat_el, "composite", {"ref": comp['ref'], "n": str(comp['natoms'])})
            else:
                if mat_obj.Z_expr: mat_el.set("Z", str(mat_obj.Z_expr))
                if mat_obj.A_expr: ET.SubElement(mat_el, "atom", {"value": str(mat_obj.A_expr)})
            self.written_materials.add(name)

    def _add_solids(self):
        if not self.geometry_state.solids: return
        solids_el = ET.SubElement(self.root, "solids")

        # Keep a set of solids that have already been written to avoid duplicates
        written_solids = set()
        for name, solid_obj in self.geometry_state.solids.items():
            self._write_solid_recursive(solid_obj, solids_el, written_solids)

        for name, surf_obj in self.geometry_state.optical_surfaces.items():
            self._write_optical_surface(surf_obj, solids_el)

    def _write_optical_surface(self, surf_obj, solids_el):
        if surf_obj.name in self.written_optical_surfaces: return
        attrs = {
            "name": surf_obj.name,
            "model": surf_obj.model,
            "finish": surf_obj.finish,
            "type": surf_obj.type,
            "value": str(surf_obj.value)
        }
        surf_el = ET.SubElement(solids_el, "opticalsurface", attrs)
        for key, ref in surf_obj.properties.items():
            ET.SubElement(surf_el, "property", {"name": key, "ref": ref})
        self.written_optical_surfaces.add(surf_obj.name)

    def _write_solid_recursive(self, solid_obj, solids_el, written_solids):
        """
        A recursive helper to ensure that a solid and all its constituent parts
        (for booleans) are written to the GDML file, without duplication.
        """
        if solid_obj.name in written_solids:
            return # Already written, do nothing

        # If it's a boolean, we must first write its children.
        if solid_obj.type == 'boolean':
            recipe = solid_obj.raw_parameters.get('recipe', [])
            for item in recipe:
                child_solid_name = item.get('solid_ref')
                if child_solid_name:
                    child_solid = self.geometry_state.solids.get(child_solid_name)
                    if child_solid:
                        self._write_solid_recursive(child_solid, solids_el, written_solids)

        # Now, write the solid itself
        self._write_single_solid(solid_obj, solids_el)
        written_solids.add(solid_obj.name)

    def _write_chained_boolean(self, final_name, recipe, solids_el):
        """
        Writes a chained boolean solid by creating intermediate solids.
        """
        # The first solid in the recipe is the base.
        current_solid_ref = recipe[0]['solid_ref']
        
        # Iteratively create the nested booleans
        for i, item in enumerate(recipe[1:]):
            op_type = item['op'] # 'union', 'subtraction', or 'intersection'
            next_solid_ref = item['solid_ref']
            
            # Determine the name for this intermediate or final boolean solid
            is_last_step = (i == len(recipe) - 2)
            boolean_name = final_name if is_last_step else f"{final_name}__{i}"
            
            # Create the boolean solid element
            boolean_el = ET.SubElement(solids_el, op_type, {"name": boolean_name})
            
            # Add the first solid reference (which is the result of the previous step)
            ET.SubElement(boolean_el, "first", {"ref": current_solid_ref})
            
            # Add the second solid reference
            ET.SubElement(boolean_el, "second", {"ref": next_solid_ref})
            
            # Add the transform for the second solid, if it exists
            transform = item.get('transform')
            if transform:
                pos = transform.get('position', {})
                rot = transform.get('rotation', {})

                if isinstance(pos, str):
                    ET.SubElement(boolean_el, "positionref", {"ref": pos})
                elif isinstance(pos, dict) and any(float(v) != 0 for v in pos.values()):
                    ET.SubElement(boolean_el, "position", pos)

                if isinstance(rot, str):
                    ET.SubElement(boolean_el, "rotationref", {"ref": rot})
                elif isinstance(rot, dict) and any(float(v) != 0 for v in rot.values()):
                    ET.SubElement(boolean_el, "rotation", rot)
            
            # The result of this operation becomes the 'first' solid for the next iteration
            current_solid_ref = boolean_name

    def _write_multi_union(self, solid_obj, solids_el):
        """Writes a G4MultiUnion solid to the GDML file."""
        recipe = solid_obj.raw_parameters.get('recipe', [])
        
        # Create the top-level <multiUnion> tag
        multi_union_el = ET.SubElement(solids_el, "multiUnion", {"name": solid_obj.name})

        for i, item in enumerate(recipe):
            solid_ref = item.get('solid_ref')
            if not solid_ref: continue

            # Create the <multiUnionNode> for each part
            node_name = f"{solid_obj.name}_node_{i}"
            node_el = ET.SubElement(multi_union_el, "multiUnionNode", {"name": node_name})
            ET.SubElement(node_el, "solid", {"ref": solid_ref})

            # The 'base' solid (index 0) has no transform.
            # Others might have position and/or rotation.
            if i > 0 and 'transform' in item and item['transform']:
                transform = item['transform']
                
                # Write position if it exists and is non-zero
                pos = transform.get('position')
                if isinstance(pos, dict) and any(float(v) != 0 for v in pos.values()):
                    pos_attrs = {"unit": "mm"}
                    for axis, val in pos.items():
                        pos_attrs[axis] = str(val)
                    ET.SubElement(node_el, "position", pos_attrs)
                elif isinstance(pos, str):
                    ET.SubElement(node_el, "positionref", {"ref": pos})

                # Write rotation if it exists and is non-zero
                rot = transform.get('rotation')
                if isinstance(rot, dict) and any(float(v) != 0 for v in rot.values()):
                    rot_attrs = {"unit": "rad"}
                    for axis, val in rot.items():
                        rot_attrs[axis] = str(val)
                    ET.SubElement(node_el, "rotation", rot_attrs)
                elif isinstance(rot, str):
                    ET.SubElement(node_el, "rotationref", {"ref": rot})

    def _write_single_solid(self, solid_obj, solids_el):
        """
        Writes a single solid element. This contains the logic from your
        original _add_solids method.
        """
        # --- Logic for handling our virtual 'boolean' type ---
        if solid_obj.type == 'boolean':
            recipe = solid_obj.raw_parameters.get('recipe', [])
            if len(recipe) < 2:
                print(f"Warning: Skipping invalid boolean solid '{solid_obj.name}' with < 2 parts.")
                return
            
            # Use multi-union if it has 3 or more total parts (1 base + 2 unions)
            # and all operations after the base are 'union'.
            is_pure_union = all(item.get('op') == 'union' for item in recipe[1:])
            if len(recipe) >= 3 and is_pure_union:
                self._write_multi_union(solid_obj, solids_el)
            else:
                # Fallback to the existing chained boolean writer for subtractions, intersections,
                # or simple two-part unions.

                # This function will generate the nested GDML structure
                self._write_chained_boolean(solid_obj.name, recipe, solids_el)
            return

        # --- Existing logic for all other types ---
        attrs = {"name": solid_obj.name}
        p = solid_obj.raw_parameters

        # Determine default units for the solid tag
        has_length_params = any(key in ['x','y','z','dx','dy','dz','rmin','rmax','r','ax','by','cz','zmax','zcut', 'rlo', 'rhi', 'vertex1_ref'] for key in p) or solid_obj.type in ['box','tube','cone','sphere','orb','torus','para','trd','trap','arb8','hype','eltube','ellipsoid','elcone','paraboloid', 'tet']
        has_angle_params = any(key in ['startphi','deltaphi','starttheta','deltatheta','alpha','theta','phi','inst','outst','phi_twist','twistedangle'] for key in p) or solid_obj.type in ['tube','cone','sphere','torus','para','polycone','polyhedra', 'genericPolycone', 'genericPolyhedra', 'trap', 'twistedbox', 'twistedtrd', 'twistedtrap', 'twistedtubs']

        if has_length_params and solid_obj.type not in ['tessellated']: # Tessellated has units on vertex defines
            attrs["lunit"] = DEFAULT_OUTPUT_LUNIT
        if has_angle_params:
            attrs["aunit"] = DEFAULT_OUTPUT_AUNIT

        solid_el = ET.SubElement(solids_el, solid_obj.type, attrs)

        if solid_obj.type == "box":
            solid_el.set("x", str(p['x']))
            solid_el.set("y", str(p['y']))
            solid_el.set("z", str(p['z']))

        elif solid_obj.type == "tube":
            solid_el.set("z", str(p['z']))
            solid_el.set("rmax", str(p['rmax']))
            solid_el.set("deltaphi", str(p.get('deltaphi', '2*pi')))
            solid_el.set("rmin", str(p.get('rmin', '0')))
            solid_el.set("startphi", str(p.get('startphi', '0')))

        elif solid_obj.type == "cone":
            solid_el.set("z", str(p['z']))
            solid_el.set("rmax1", str(p['rmax1']))
            solid_el.set("rmax2", str(p['rmax2']))
            solid_el.set("deltaphi", str(p.get('deltaphi', '2*pi')))
            solid_el.set("rmin1", str(p.get('rmin1', '0')))
            solid_el.set("rmin2", str(p.get('rmin2', '0')))
            solid_el.set("startphi", str(p.get('startphi', '0')))

        elif solid_obj.type == "sphere":
            solid_el.set("rmax", str(p['rmax']))
            solid_el.set("rmin", str(p.get('rmin', '0')))
            solid_el.set("startphi", str(p.get('startphi', '0')))
            solid_el.set("deltaphi", str(p.get('deltaphi', '2*pi')))
            solid_el.set("starttheta", str(p.get('starttheta', '0')))
            solid_el.set("deltatheta", str(p.get('deltatheta', 'pi')))

        elif solid_obj.type == "orb":
            solid_el.set("r", str(p['r']))

        elif solid_obj.type == "torus":
            solid_el.set("rmin", str(p['rmin']))
            solid_el.set("rmax", str(p['rmax']))
            solid_el.set("rtor", str(p['rtor']))
            solid_el.set("startphi", str(p.get('startphi', '0')))
            solid_el.set("deltaphi", str(p.get('deltaphi', '2*pi')))

        elif solid_obj.type == "para":
            solid_el.set("x", str(p['x']))
            solid_el.set("y", str(p['y']))
            solid_el.set("z", str(p['z']))
            solid_el.set("alpha", str(p['alpha']))
            solid_el.set("theta", str(p['theta']))
            solid_el.set("phi", str(p['phi']))

        elif solid_obj.type == "trd":
            solid_el.set("x1", str(p['x1']))
            solid_el.set("x2", str(p['x2']))
            solid_el.set("y1", str(p['y1']))
            solid_el.set("y2", str(p['y2']))
            solid_el.set("z", str(p['z']))

        elif solid_obj.type == "trap":
            solid_el.set("z", str(p['z']))
            solid_el.set("theta", str(p.get('theta', '0')))
            solid_el.set("phi", str(p.get('phi', '0')))
            solid_el.set("y1", str(p['y1']))
            solid_el.set("x1", str(p['x1']))
            solid_el.set("x2", str(p['x2']))
            solid_el.set("alpha1", str(p.get('alpha1', '0')))
            solid_el.set("y2", str(p['y2']))
            solid_el.set("x3", str(p['x3']))
            solid_el.set("x4", str(p['x4']))
            solid_el.set("alpha2", str(p.get('alpha2', '0')))

        elif solid_obj.type == 'polycone':
            solid_el.set("startphi", str(p.get('startphi', '0')))
            solid_el.set("deltaphi", str(p.get('deltaphi', '2*pi')))
            for zp in p.get('zplanes', []):
                ET.SubElement(solid_el, "zplane", zp)

        elif solid_obj.type == 'genericPolycone':
            solid_el.set("startphi", str(p.get('startphi', '0')))
            solid_el.set("deltaphi", str(p.get('deltaphi', '2*pi')))    
            for rzp in p.get('rzpoints', []):
                ET.SubElement(solid_el, "rzpoint", rzp)
        
        elif solid_obj.type == 'polyhedra':
            solid_el.set("startphi", str(p.get('startphi', '0')))
            solid_el.set("deltaphi", str(p.get('deltaphi', '2*pi')))
            solid_el.set("numsides", str(p['numsides']))
            for zp in p.get('zplanes', []):
                ET.SubElement(solid_el, "zplane", zp)

        elif solid_obj.type == 'genericPolyhedra':
            solid_el.set("startphi", str(p.get('startphi', '0')))
            solid_el.set("deltaphi", str(p.get('deltaphi', '2*pi')))
            solid_el.set("numsides", str(p['numsides']))
            for rzp in p.get('rzpoints', []):
                ET.SubElement(solid_el, "rzpoint", rzp)
        
        elif solid_obj.type == 'tessellated':
            # It should have lunit and aunit attributes if vertices are not pre-defined with units
            # but GDML spec usually puts units on <position> defines for vertices.
            # We will assume vertices are defined and referenced.
            solid_el.set("aunit", DEFAULT_OUTPUT_AUNIT) # Default, can be overridden by schema
            solid_el.set("lunit", DEFAULT_OUTPUT_LUNIT) # Default

            for facet in p.get('facets', []):
                facet_attrs = {}
                if facet['type'] == 'triangular':
                    facet_attrs['vertex1'] = facet['vertex_refs'][0]
                    facet_attrs['vertex2'] = facet['vertex_refs'][1]
                    facet_attrs['vertex3'] = facet['vertex_refs'][2]
                elif facet['type'] == 'quadrangular':
                    facet_attrs['vertex1'] = facet['vertex_refs'][0]
                    facet_attrs['vertex2'] = facet['vertex_refs'][1]
                    facet_attrs['vertex3'] = facet['vertex_refs'][2]
                    facet_attrs['vertex4'] = facet['vertex_refs'][3]
                    if 'facet_type_attr' in facet: # e.g. ABSOLUTE/RELATIVE
                        facet_attrs['type'] = facet['facet_type_attr']
                ET.SubElement(solid_el, facet['type'], facet_attrs)

        elif solid_obj.type == 'arb8':
            solid_el.set("dz", str(p['dz']))
            for i in range(1, 9):
                solid_el.set(f"v{i}x", str(p[f'v{i}x']))
                solid_el.set(f"v{i}y", str(p[f'v{i}y']))

        elif solid_obj.type == 'hype':
            solid_el.set("rmin", str(p['rmin']))
            solid_el.set("rmax", str(p['rmax']))
            solid_el.set("inst", str(p['inst']))
            solid_el.set("outst", str(p['outst']))
            solid_el.set("z", str(p['z']))
        
        elif solid_obj.type == 'paraboloid':
            solid_el.set("rlo", str(p['rlo']))
            solid_el.set("rhi", str(p['rhi']))
            solid_el.set("dz", str(p['dz']))

        elif solid_obj.type == 'eltube':
            solid_el.set("dx", str(p['dx']))
            solid_el.set("dy", str(p['dy']))
            solid_el.set("dz", str(p['dz']))

        elif solid_obj.type == 'ellipsoid':
            solid_el.set("ax", str(p['ax']))
            solid_el.set("by", str(p['by']))
            solid_el.set("cz", str(p['cz']))
            if 'zcut1' in p: solid_el.set("zcut1", str(p['zcut1']))
            if 'zcut2' in p: solid_el.set("zcut2", str(p['zcut2']))

        elif solid_obj.type == 'elcone':
            solid_el.set("dx", str(p['dx']))
            solid_el.set("dy", str(p['dy']))
            solid_el.set("zmax", str(p['zmax']))
            solid_el.set("zcut", str(p['zcut']))

        elif solid_obj.type == 'tet':
            solid_el.set("vertex1", p['vertex1'])
            solid_el.set("vertex2", p['vertex2'])
            solid_el.set("vertex3", p['vertex3'])
            solid_el.set("vertex4", p['vertex4'])

        elif solid_obj.type == 'twistedbox':
            solid_el.set("PhiTwist", str(p['PhiTwist']))
            solid_el.set("x", str(p['x']))
            solid_el.set("y", str(p['y']))
            solid_el.set("z", str(p['z']))

        elif solid_obj.type == 'twistedtrd':
            solid_el.set("PhiTwist", str(p['PhiTwist']))
            solid_el.set("x1", str(p['x1']))
            solid_el.set("x2", str(p['x2']))
            solid_el.set("y1", str(p['y1']))
            solid_el.set("y2", str(p['y2']))
            solid_el.set("z", str(p['z']))

        elif solid_obj.type == 'twistedtrap':
            solid_el.set("PhiTwist", str(p['PhiTwist']))
            solid_el.set("z", str(p['z']))
            solid_el.set("Theta", str(p['Theta']))
            solid_el.set("Phi", str(p['Phi']))
            solid_el.set("y1", str(p['y1']))
            solid_el.set("x1", str(p['x1']))
            solid_el.set("x2", str(p['x2']))
            solid_el.set("y2", str(p['y2']))
            solid_el.set("x3", str(p['x3']))
            solid_el.set("x4", str(p['x4']))
            solid_el.set("Alph", str(p['Alph']))

        elif solid_obj.type == 'twistedtubs':
            solid_el.set("twistedangle", str(p['twistedangle']))
            solid_el.set("endinnerrad", str(p['endinnerrad']))
            solid_el.set("endouterrad", str(p['endouterrad']))
            solid_el.set("zlen", str(p['zlen']))
            solid_el.set("phi", str(p.get('phi', '2*pi')))

        elif solid_obj.type == "cutTube":
            solid_el.set("rmin", str(p['rmin']))
            solid_el.set("rmax", str(p['rmax']))
            solid_el.set("z", str(p['z']))
            solid_el.set("startphi", str(p.get('startphi', '0')))
            solid_el.set("deltaphi", str(p.get('deltaphi', '2*pi')))
            solid_el.set("lowX", str(p['lowX']))
            solid_el.set("lowY", str(p['lowY']))
            solid_el.set("lowZ", str(p['lowZ']))
            solid_el.set("highX", str(p['highX']))
            solid_el.set("highY", str(p['highY']))
            solid_el.set("highZ", str(p['highZ']))
        else:
                print(f"GDML Writer: Solid type '{solid_obj.type}' (name: {name}) is not fully supported for writing.")
            

    def _add_structure(self):
        if not self.geometry_state.logical_volumes: return
        structure_el = ET.SubElement(self.root, "structure")

        # First, write all assembly definitions
        for asm_name, asm_obj in self.geometry_state.assemblies.items():
            asm_el = ET.SubElement(structure_el, "assembly", {"name": asm_name})
            for pv_obj in asm_obj.placements:
                self._write_physvol_element(asm_el, pv_obj)

        # Then, write all logical volume definitions and their content
        for lv_name, lv_obj in self.geometry_state.logical_volumes.items():
            lv_el = ET.SubElement(structure_el, "volume", {"name": lv_name})
            ET.SubElement(lv_el, "materialref", {"ref": lv_obj.material_ref})
            ET.SubElement(lv_el, "solidref", {"ref": lv_obj.solid_ref})
            
            if lv_obj.content_type == 'physvol':
                for pv_obj in lv_obj.content:
                    self._write_physvol_element(lv_el, pv_obj)
            elif lv_obj.content_type == 'division':
                self._write_divisionvol(lv_el, lv_obj.content)
            elif lv_obj.content_type == 'replica':
                self._write_replicavol(lv_el, lv_obj.content)
            elif lv_obj.content_type == 'parameterised':
                self._write_paramvol(lv_el, lv_obj.content)

        # Finally, write all surface links
        for name, surf in self.geometry_state.skin_surfaces.items():
            self._write_skin_surface(structure_el, surf)
        for name, surf in self.geometry_state.border_surfaces.items():
            self._write_border_surface(structure_el, surf)

    def _write_physvol_element(self, parent_el, pv_obj, is_assembly_ref=False):
        """Helper to write a physvol or assembly placement tag."""
        pv_el = ET.SubElement(parent_el, "physvol", {"name": pv_obj.name})
        if pv_obj.copy_number != 0:
            pv_el.set("copynumber", str(pv_obj.copy_number))
        
        # The reference tag is different for assemblies vs. volumes
        ref_tag = "assemblyref" if is_assembly_ref else "volumeref"
        ET.SubElement(pv_el, ref_tag, {"ref": pv_obj.volume_ref})

        position_data = pv_obj.position
        if isinstance(position_data, str):
            ET.SubElement(pv_el, "positionref", {"ref": position_data})
        elif isinstance(position_data, dict) and any(abs(float(v)) > 1e-9 for v in position_data.values()):
            pos_attrs = {"unit": DEFAULT_OUTPUT_LUNIT}
            for axis, val in position_data.items():
                pos_attrs[axis] = str(convert_from_internal_units(val, DEFAULT_OUTPUT_LUNIT, "length"))
            ET.SubElement(pv_el, "position", pos_attrs)
        
        rotation_data = pv_obj.rotation
        if isinstance(rotation_data, str):
            ET.SubElement(pv_el, "rotationref", {"ref": rotation_data})
        elif isinstance(rotation_data, dict) and any(abs(float(v)) > 1e-9 for v in rotation_data.values()):
            rot_attrs = {"unit": DEFAULT_OUTPUT_AUNIT}
            for axis, val in rotation_data.items():
                rot_attrs[axis] = str(convert_from_internal_units(val, DEFAULT_OUTPUT_AUNIT, "angle"))
            ET.SubElement(pv_el, "rotation", rot_attrs)

        scale_data = pv_obj.scale
        if isinstance(scale_data, str): # It's a ref
            ET.SubElement(pv_el, "scaleref", {"ref": scale_data})
        elif isinstance(scale_data, dict) and not all(abs(float(v) - 1.0) < 1e-9 for v in scale_data.values()): # Non-identity scale
            scale_attrs = {} # Scale has no unit attribute in GDML
            for axis, val in scale_data.items():
                scale_attrs[axis] = str(val) # Scale factors are unitless
            ET.SubElement(pv_el, "scale", scale_attrs)

    def _write_divisionvol(self, parent_el, div_obj):
        attrs = {
            "axis": div_obj.axis,
            "unit": div_obj.unit
        }
        if div_obj.number is not None: attrs["number"] = str(div_obj.number)
        if div_obj.width is not None: attrs["width"] = str(div_obj.width)
        if div_obj.offset is not None: attrs["offset"] = str(div_obj.offset)
        
        div_el = ET.SubElement(parent_el, "divisionvol", attrs)
        ET.SubElement(div_el, "volumeref", {"ref": div_obj.volume_ref})

    def _write_replicavol(self, parent_el, rep_obj):
        rep_el = ET.SubElement(parent_el, "replicavol", {"number": str(rep_obj.number)})
        ET.SubElement(rep_el, "volumeref", {"ref": rep_obj.volume_ref})
        
        algo_el = ET.SubElement(rep_el, "replicate_along_axis")
        ET.SubElement(algo_el, "direction", rep_obj.direction)
        ET.SubElement(algo_el, "width", {"value": str(rep_obj.width)})
        ET.SubElement(algo_el, "offset", {"value": str(rep_obj.offset)})

    def _write_paramvol(self, parent_el, param_obj):
        param_el = ET.SubElement(parent_el, "paramvol", {"ncopies": str(param_obj.ncopies)})
        ET.SubElement(param_el, "volumeref", {"ref": param_obj.volume_ref})
        
        algo_el = ET.SubElement(param_el, "parameterised_position_size")
        for param_set in param_obj.parameters:
            params_el = ET.SubElement(algo_el, "parameters", {"number": str(param_set.number)})
            
            # Position
            pos = param_set.position
            if isinstance(pos, str):
                ET.SubElement(params_el, "positionref", {"ref": pos})
            elif isinstance(pos, dict):
                ET.SubElement(params_el, "position", pos)
            
            # Rotation (if defined)
            rot = param_set.rotation
            if rot:
                if isinstance(rot, str):
                    ET.SubElement(params_el, "rotationref", {"ref": rot})
                elif isinstance(rot, dict) and any(float(v) != 0 for v in rot.values()):
                    ET.SubElement(params_el, "rotation", rot)

            # Dimensions
            ET.SubElement(params_el, param_set.dimensions_type, param_set.dimensions)

    def _write_skin_surface(self, parent_el, surf_obj):
        surf_el = ET.SubElement(parent_el, "skinsurface", {
            "name": surf_obj.name,
            "surfaceproperty": surf_obj.surfaceproperty_ref
        })
        ET.SubElement(surf_el, "volumeref", {"ref": surf_obj.volume_ref})

    def _write_border_surface(self, parent_el, surf_obj):
        surf_el = ET.SubElement(parent_el, "bordersurface", {
            "name": surf_obj.name,
            "surfaceproperty": surf_obj.surfaceproperty_ref
        })
        # Find the names of the PVs from their IDs
        pv1 = self.geometry_state._find_pv_by_id(surf_obj.physvol1_ref)
        pv2 = self.geometry_state._find_pv_by_id(surf_obj.physvol2_ref)
        if pv1 and pv2:
            ET.SubElement(surf_el, "physvolref", {"ref": pv1.name})
            ET.SubElement(surf_el, "physvolref", {"ref": pv2.name})
        else:
            print(f"Warning: Could not find one or both PVs for border surface '{surf_obj.name}'.")

    def _add_setup(self):
        if not self.geometry_state.world_volume_ref: return
        setup_el = ET.SubElement(self.root, "setup", {"name": "Default", "version": "1.0"})
        ET.SubElement(setup_el, "world", {"ref": self.geometry_state.world_volume_ref})

    def get_gdml_string(self):
        self._add_defines()
        self._add_materials()
        self._add_solids()
        self._add_structure()
        self._add_setup()

        xml_str = ET.tostring(self.root, encoding='unicode', xml_declaration=True)
        # For pretty printing, minidom can be slow for large files.
        # Consider lxml if performance is an issue, or skip pretty printing for large files.
        try:
            dom = minidom.parseString(xml_str)
            return dom.toprettyxml(indent="  ", newl="\n", encoding="UTF-8").decode('utf-8')
        except Exception as e:
            print(f"Error during XML pretty printing: {e}. Returning raw XML.")
            return xml_str
