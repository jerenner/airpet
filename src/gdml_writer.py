# src/gdml_writer.py
import xml.etree.ElementTree as ET
from xml.dom import minidom
import math
from .geometry_types import (
    GeometryState, Define, Material, Solid, LogicalVolume, PhysicalVolumePlacement,
    UNIT_FACTORS, OUTPUT_UNIT_FACTORS, DEFAULT_OUTPUT_LUNIT, DEFAULT_OUTPUT_AUNIT, 
    convert_from_internal_units
)

class GDMLWriter:
    def __init__(self, geometry_state):
        self.geometry_state = geometry_state
        self.root = ET.Element("gdml", {
            "xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
            "xsi:noNamespaceSchemaLocation": "http://service-spi.web.cern.ch/service-spi/app/releases/GDML/schema/gdml.xsd"
        })

    def _add_defines(self):
        if not self.geometry_state.defines: return
        define_el = ET.SubElement(self.root, "define")
        for name, define_obj in self.geometry_state.defines.items():
            if define_obj.type in ['position', 'rotation', 'scale']:
                # Compound defines
                attrs = {"name": name}
                if define_obj.unit: attrs["unit"] = define_obj.unit
                
                # raw_expression is a dict here
                for axis, raw_val_str in define_obj.raw_expression.items():
                    attrs[axis] = raw_val_str
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


    def _add_materials(self):
        if not self.geometry_state.materials: return
        materials_el = ET.SubElement(self.root, "materials")
        for name, mat_obj in self.geometry_state.materials.items():
            mat_attrs = {"name": name}
            if mat_obj.state: mat_attrs["state"] = mat_obj.state
            mat_el = ET.SubElement(materials_el, "material", mat_attrs)
            if mat_obj.density is not None: # GDML D is g/cm3
                 ET.SubElement(mat_el, "D", {"value": str(mat_obj.density)}) # Add unit if stored differently
            # TODO: Add components, Z, A etc.

    def _add_solids(self):
        if not self.geometry_state.solids: return
        solids_el = ET.SubElement(self.root, "solids")

        # Keep a set of solids that have already been written to avoid duplicates
        written_solids = set()

        for name, solid_obj in self.geometry_state.solids.items():
            self._write_solid_recursive(solid_obj, solids_el, written_solids)

    def _write_solid_recursive(self, solid_obj, solids_el, written_solids):
        """
        A recursive helper to ensure that a solid and all its constituent parts
        (for booleans) are written to the GDML file, without duplication.
        """
        if solid_obj.name in written_solids:
            return # Already written, do nothing

        # If it's a boolean, we must first write its children.
        if solid_obj.type == 'boolean':
            recipe = solid_obj.parameters.get('recipe', [])
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
                if any(abs(v) > 1e-9 for v in pos.values()):
                    pos_attrs = {"unit": "mm"} # Assuming mm for now
                    for axis, val in pos.items():
                        pos_attrs[axis] = str(val)
                    ET.SubElement(boolean_el, "position", pos_attrs)
                if any(abs(v) > 1e-9 for v in rot.values()):
                    rot_attrs = {"unit": "rad"} # Assuming rad for now
                    for axis, val in rot.items():
                        rot_attrs[axis] = str(val)
                    ET.SubElement(boolean_el, "rotation", rot_attrs)
            
            # The result of this operation becomes the 'first' solid for the next iteration
            current_solid_ref = boolean_name

    def _write_single_solid(self, solid_obj, solids_el):
        """
        Writes a single solid element. This contains the logic from your
        original _add_solids method.
        """
        # --- Logic for handling our virtual 'boolean' type ---
        if solid_obj.type == 'boolean':
            recipe = solid_obj.parameters.get('recipe', [])
            if len(recipe) < 2:
                print(f"Warning: Skipping invalid boolean solid '{solid_obj.name}' with < 2 parts.")
                return

            # This function will generate the nested GDML structure
            self._write_chained_boolean(solid_obj.name, recipe, solids_el)
            return # We are done with this solid

        # --- Existing logic for all other types ---
        attrs = {"name": solid_obj.name}
        p = solid_obj.parameters

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
            solid_el.set("rmin", str(p['rmin']))
            solid_el.set("rmax", str(p['rmax']))
            solid_el.set("z", str(p['dz'] * 2.0)) # dz is half-length
            solid_el.set("startphi", str(convert_from_internal_units(p['startphi'], DEFAULT_OUTPUT_AUNIT, "angle")))
            solid_el.set("deltaphi", str(convert_from_internal_units(p['deltaphi'], DEFAULT_OUTPUT_AUNIT, "angle")))
        elif solid_obj.type == "cone":
            solid_el.set("rmin1", str(p['rmin1']))
            solid_el.set("rmax1", str(p['rmax1']))
            solid_el.set("rmin2", str(p['rmin2']))
            solid_el.set("rmax2", str(p['rmax2']))
            solid_el.set("z", str(p['dz'] * 2.0))
            solid_el.set("startphi", str(convert_from_internal_units(p['startphi'], DEFAULT_OUTPUT_AUNIT, "angle")))
            solid_el.set("deltaphi", str(convert_from_internal_units(p['deltaphi'], DEFAULT_OUTPUT_AUNIT, "angle")))
        elif solid_obj.type == "sphere":
            solid_el.set("rmin", str(p['rmin']))
            solid_el.set("rmax", str(p['rmax']))
            solid_el.set("startphi", str(convert_from_internal_units(p['startphi'], DEFAULT_OUTPUT_AUNIT, "angle")))
            solid_el.set("deltaphi", str(convert_from_internal_units(p['deltaphi'], DEFAULT_OUTPUT_AUNIT, "angle")))
            solid_el.set("starttheta", str(convert_from_internal_units(p['starttheta'], DEFAULT_OUTPUT_AUNIT, "angle")))
            solid_el.set("deltatheta", str(convert_from_internal_units(p['deltatheta'], DEFAULT_OUTPUT_AUNIT, "angle")))
        elif solid_obj.type == "orb":
            solid_el.set("r", str(p['r']))
        elif solid_obj.type == "torus":
            solid_el.set("rmin", str(p['rmin']))
            solid_el.set("rmax", str(p['rmax']))
            solid_el.set("rtor", str(p['rtor']))
            solid_el.set("startphi", str(convert_from_internal_units(p['startphi'], DEFAULT_OUTPUT_AUNIT, "angle")))
            solid_el.set("deltaphi", str(convert_from_internal_units(p['deltaphi'], DEFAULT_OUTPUT_AUNIT, "angle")))
        elif solid_obj.type == "para":
            solid_el.set("x", str(p['dx'] * 2.0))
            solid_el.set("y", str(p['dy'] * 2.0))
            solid_el.set("z", str(p['dz'] * 2.0))
            solid_el.set("alpha", str(convert_from_internal_units(p['alpha'], DEFAULT_OUTPUT_AUNIT, "angle")))
            solid_el.set("theta", str(convert_from_internal_units(p['theta'], DEFAULT_OUTPUT_AUNIT, "angle")))
            solid_el.set("phi", str(convert_from_internal_units(p['phi'], DEFAULT_OUTPUT_AUNIT, "angle")))
        elif solid_obj.type == "trd":
            solid_el.set("x1", str(p['dx1'] * 2.0))
            solid_el.set("x2", str(p['dx2'] * 2.0))
            solid_el.set("y1", str(p['dy1'] * 2.0))
            solid_el.set("y2", str(p['dy2'] * 2.0))
            solid_el.set("z", str(p['dz'] * 2.0))
        elif solid_obj.type == "trap":
            solid_el.set("z", str(p['dz'] * 2.0))
            solid_el.set("theta", str(convert_from_internal_units(p['theta'], DEFAULT_OUTPUT_AUNIT, "angle")))
            solid_el.set("phi", str(convert_from_internal_units(p['phi'], DEFAULT_OUTPUT_AUNIT, "angle")))
            solid_el.set("y1", str(p['dy1'] * 2.0))
            solid_el.set("x1", str(p['dx1'] * 2.0))
            solid_el.set("x2", str(p['dx2'] * 2.0))
            solid_el.set("alpha1", str(convert_from_internal_units(p['alpha1'], DEFAULT_OUTPUT_AUNIT, "angle")))
            solid_el.set("y2", str(p['dy2'] * 2.0))
            solid_el.set("x3", str(p['dx3'] * 2.0))
            solid_el.set("x4", str(p['dx4'] * 2.0))
            solid_el.set("alpha2", str(convert_from_internal_units(p['alpha2'], DEFAULT_OUTPUT_AUNIT, "angle")))

        elif solid_obj.type == 'polycone':
            solid_el.set("startphi", str(convert_from_internal_units(p['startphi'], DEFAULT_OUTPUT_AUNIT, "angle")))
            solid_el.set("deltaphi", str(convert_from_internal_units(p['deltaphi'], DEFAULT_OUTPUT_AUNIT, "angle")))
            for zp in p.get('zplanes', []):
                ET.SubElement(solid_el, "zplane", {
                    "z": str(zp['z']), "rmin": str(zp['rmin']), "rmax": str(zp['rmax'])
                }) # Assumes zplanes params are already in output lunit (mm)

        elif solid_obj.type == 'genericPolycone':
            solid_el.set("startphi", str(p['startphi'])) # Write raw expression
            solid_el.set("deltaphi", str(p['deltaphi'])) # Write raw expression
            for rzp in p.get('rzpoints', []):
                # Write raw expressions for r and z
                ET.SubElement(solid_el, "rzpoint", {"r": str(rzp['r']), "z": str(rzp['z'])})
        
        elif solid_obj.type == 'polyhedra':
            solid_el.set("startphi", str(p['startphi']))
            solid_el.set("deltaphi", str(p['deltaphi']))
            solid_el.set("numsides", str(p['numsides']))
            for zp in p.get('zplanes', []):
                ET.SubElement(solid_el, "zplane", {"r": str(zp['r']), "z": str(zp['z']), "rmax": str(zp['rmax'])})

        elif solid_obj.type == 'genericPolyhedra':
            solid_el.set("startphi", str(p['startphi']))
            solid_el.set("deltaphi", str(p['deltaphi']))
            solid_el.set("numsides", str(p['numsides']))
            for rzp in p.get('rzpoints', []):
                ET.SubElement(solid_el, "rzpoint", {"r": str(rzp['r']), "z": str(rzp['z'])})
        
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

        elif solid_obj.type == 'arb8': # G4GenericTrap
            solid_el.set("dz", str(p['dz'] * 2.0)) # dz was stored as half-length
            for i, vertex in enumerate(p.get('vertices', [])):
                solid_el.set(f'v{i+1}x', str(vertex['x']))
                solid_el.set(f'v{i+1}y', str(vertex['y']))

        elif solid_obj.type == 'hype':
            solid_el.set("rmin", str(p['rmin']))
            solid_el.set("rmax", str(p['rmax']))
            solid_el.set("inst", str(convert_from_internal_units(p['inst'], DEFAULT_OUTPUT_AUNIT, "angle")))
            solid_el.set("outst", str(convert_from_internal_units(p['outst'], DEFAULT_OUTPUT_AUNIT, "angle")))
            solid_el.set("dz", str(p['dz'] * 2.0)) # dz was stored as half-length
        
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
            solid_el.set("dx", str(p['dx'])) # ratio
            solid_el.set("dy", str(p['dy'])) # ratio
            solid_el.set("zmax", str(p['zmax']))
            solid_el.set("zcut", str(p['zcut']))

        elif solid_obj.type == 'paraboloid':
            solid_el.set("rlo", str(p['rlo']))
            solid_el.set("rhi", str(p['rhi']))
            solid_el.set("dz", str(p['dz']))

        elif solid_obj.type == 'tet':
            solid_el.set("vertex1", p['vertex1_ref'])
            solid_el.set("vertex2", p['vertex2_ref'])
            solid_el.set("vertex3", p['vertex3_ref'])
            solid_el.set("vertex4", p['vertex4_ref'])

        elif solid_obj.type == 'twistedbox':
            solid_el.set("PhiTwist", str(convert_from_internal_units(p['phi_twist'], DEFAULT_OUTPUT_AUNIT, "angle")))
            solid_el.set("x", str(p['dx'] * 2.0))
            solid_el.set("y", str(p['dy'] * 2.0))
            solid_el.set("z", str(p['dz'] * 2.0))

        elif solid_obj.type == 'twistedtrd':
            solid_el.set("PhiTwist", str(convert_from_internal_units(p['phi_twist'], DEFAULT_OUTPUT_AUNIT, "angle")))
            solid_el.set("x1", str(p['dx1'] * 2.0))
            solid_el.set("x2", str(p['dx2'] * 2.0))
            solid_el.set("y1", str(p['dy1'] * 2.0))
            solid_el.set("y2", str(p['dy2'] * 2.0))
            solid_el.set("z", str(p['dz'] * 2.0))

        elif solid_obj.type == 'twistedtrap':
            solid_el.set("PhiTwist", str(convert_from_internal_units(p['phi_twist'], DEFAULT_OUTPUT_AUNIT, "angle")))
            solid_el.set("z", str(p['dz'] * 2.0))
            solid_el.set("Theta", str(convert_from_internal_units(p['theta'], DEFAULT_OUTPUT_AUNIT, "angle")))
            solid_el.set("Phi", str(convert_from_internal_units(p['phi'], DEFAULT_OUTPUT_AUNIT, "angle")))
            solid_el.set("y1", str(p['dy1'] * 2.0))
            solid_el.set("x1", str(p['dx1'] * 2.0))
            solid_el.set("x2", str(p['dx2'] * 2.0))
            solid_el.set("y2", str(p['dy2'] * 2.0))
            solid_el.set("x3", str(p['dx3'] * 2.0))
            solid_el.set("x4", str(p['dx4'] * 2.0))
            solid_el.set("Alph", str(convert_from_internal_units(p['alpha'], DEFAULT_OUTPUT_AUNIT, "angle"))) # Note 'Alph' in GDML

        elif solid_obj.type == 'twistedtubs':
            solid_el.set("twistedangle", str(convert_from_internal_units(p['twistedangle'], DEFAULT_OUTPUT_AUNIT, "angle")))
            solid_el.set("endinnerrad", str(p['rmin'])) # Map back from our rmin/rmax
            solid_el.set("endouterrad", str(p['rmax']))
            solid_el.set("zlen", str(p['dz'] * 2.0))
            solid_el.set("phi", str(convert_from_internal_units(p['dphi'], DEFAULT_OUTPUT_AUNIT, "angle"))) # map back from dphi
            # nseg could also be written if stored

        elif solid_obj.type == "cutTube":
            solid_el.set("rmin", str(p['rmin']))
            solid_el.set("rmax", str(p['rmax']))
            solid_el.set("z", str(p['dz'] * 2.0))
            solid_el.set("startphi", str(convert_from_internal_units(p['startphi'], DEFAULT_OUTPUT_AUNIT, "angle")))
            solid_el.set("deltaphi", str(convert_from_internal_units(p['deltaphi'], DEFAULT_OUTPUT_AUNIT, "angle")))
            solid_el.set("lowX", str(p['lowNormal']['x']))
            solid_el.set("lowY", str(p['lowNormal']['y']))
            solid_el.set("lowZ", str(p['lowNormal']['z']))
            solid_el.set("highX", str(p['highNormal']['x']))
            solid_el.set("highY", str(p['highNormal']['y']))
            solid_el.set("highZ", str(p['highNormal']['z']))

        # TODO: Add writer logic for other solid types
        # reflectedSolid, scaledSolid

        elif 'attributes_raw' in p: # Fallback for unhandled solids
            for key, value in p['attributes_raw'].items():
                solid_el.set(key, str(value)) # Write raw attributes
            print(f"GDML Writer: Solid type '{solid_obj.type}' (name: {name}) written with raw attributes as fallback.")
        else:
                print(f"GDML Writer: Solid type '{solid_obj.type}' (name: {name}) is not fully supported for writing.")
            

    def _add_structure(self):
        if not self.geometry_state.logical_volumes: return
        structure_el = ET.SubElement(self.root, "structure")

        # --- Write Assemblies First ---
        if self.geometry_state.assemblies:
            for asm_name, asm_obj in self.geometry_state.assemblies.items():
                asm_el = ET.SubElement(structure_el, "assembly", {"name": asm_name})
                for pv_obj in asm_obj.placements:
                    # Write a physvol tag inside the assembly
                    self._write_physvol_element(asm_el, pv_obj)

        # --- Write Volumes ---
        for lv_name, lv_obj in self.geometry_state.logical_volumes.items():
            lv_el = ET.SubElement(structure_el, "volume", {"name": lv_name})
            ET.SubElement(lv_el, "materialref", {"ref": lv_obj.material_ref})
            ET.SubElement(lv_el, "solidref", {"ref": lv_obj.solid_ref})

            for pv_obj in lv_obj.phys_children:
                # Here, a child could be a reference to an assembly
                if self.geometry_state.get_assembly(pv_obj.volume_ref):
                    # This is an assembly placement
                    self._write_physvol_element(lv_el, pv_obj, is_assembly_ref=True)
                else:
                    # This is a regular LV placement
                    self._write_physvol_element(lv_el, pv_obj)

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
        elif isinstance(position_data, dict) and any(abs(v) > 1e-9 for v in position_data.values()):
            pos_attrs = {"unit": DEFAULT_OUTPUT_LUNIT}
            for axis, val in position_data.items():
                pos_attrs[axis] = str(convert_from_internal_units(val, DEFAULT_OUTPUT_LUNIT, "length"))
            ET.SubElement(pv_el, "position", pos_attrs)
        
        rotation_data = pv_obj.rotation
        if isinstance(rotation_data, str):
            ET.SubElement(pv_el, "rotationref", {"ref": rotation_data})
        elif isinstance(rotation_data, dict) and any(abs(v) > 1e-9 for v in rotation_data.values()):
            rot_attrs = {"unit": DEFAULT_OUTPUT_AUNIT}
            for axis, val in rotation_data.items():
                rot_attrs[axis] = str(convert_from_internal_units(val, DEFAULT_OUTPUT_AUNIT, "angle"))
            ET.SubElement(pv_el, "rotation", rot_attrs)

        scale_data = pv_obj.scale
        if isinstance(scale_data, str): # It's a ref
            ET.SubElement(pv_el, "scaleref", {"ref": scale_data})
        elif isinstance(scale_data, dict) and not all(abs(v - 1.0) < 1e-9 for v in scale_data.values()): # Non-identity scale
            scale_attrs = {} # Scale has no unit attribute in GDML
            for axis, val in scale_data.items():
                scale_attrs[axis] = str(val) # Scale factors are unitless
            ET.SubElement(pv_el, "scale", scale_attrs)

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
