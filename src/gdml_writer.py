# src/gdml_writer.py
import xml.etree.ElementTree as ET
from xml.dom import minidom # For pretty printing
import math
from .geometry_types import (
    GeometryState, Define, Material, Solid, LogicalVolume, PhysicalVolumePlacement,
    UNIT_FACTORS, OUTPUT_UNIT_FACTORS, convert_from_internal_units
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
            if define_obj.type == 'position':
                attrs = {"name": name, "unit": DEFAULT_OUTPUT_LUNIT}
                for axis in ['x', 'y', 'z']:
                    attrs[axis] = str(convert_from_internal_units(define_obj.value[axis], DEFAULT_OUTPUT_LUNIT, "length"))
                ET.SubElement(define_el, "position", attrs)
            elif define_obj.type == 'rotation':
                attrs = {"name": name, "unit": DEFAULT_OUTPUT_AUNIT}
                for axis in ['x', 'y', 'z']: # Assuming ZYX Euler
                    attrs[axis] = str(convert_from_internal_units(define_obj.value[axis], DEFAULT_OUTPUT_AUNIT, "angle"))
                ET.SubElement(define_el, "rotation", attrs)
            elif define_obj.type == 'constant':
                 # Constants might not have intrinsic units in our simple Define, or they might.
                 # If they do, we'd need to store their original category to write them out correctly.
                 # For now, assume dimensionless or handle based on known use.
                attrs = {"name": name, "value": str(define_obj.value)}
                # If define_obj had a unit and category, we could convert back:
                # if define_obj.unit and define_obj.category:
                #     attrs["value"] = str(convert_from_internal_units(define_obj.value, define_obj.unit, define_obj.category))
                #     attrs["unit"] = define_obj.unit
                ET.SubElement(define_el, "constant", attrs)


    def _add_materials(self):
        # ... (same as before or enhance as needed) ...
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
        for name, solid_obj in self.geometry_state.solids.items():
            attrs = {"name": name}
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
            
            elif solid_obj.type in ['union', 'subtraction', 'intersection']:
                ET.SubElement(solid_el, "first", {"ref": p['first_ref']})
                ET.SubElement(solid_el, "second", {"ref": p['second_ref']})
                
                # Add transform for the second solid
                transform_s = p.get('transform_second', {})
                pos_s = transform_s.get('position', {})
                rot_s = transform_s.get('rotation', {})
                if any(abs(v) > 1e-9 for v in pos_s.values()): # Check if non-zero
                    pos_attrs = {"unit":DEFAULT_OUTPUT_LUNIT}
                    for axis_key in ['x','y','z']: pos_attrs[axis_key] = str(convert_from_internal_units(pos_s.get(axis_key,0), DEFAULT_OUTPUT_LUNIT, "length"))
                    ET.SubElement(solid_el, "position", pos_attrs)
                if any(abs(v) > 1e-9 for v in rot_s.values()):
                    rot_attrs = {"unit":DEFAULT_OUTPUT_AUNIT}
                    for axis_key in ['x','y','z']: rot_attrs[axis_key] = str(convert_from_internal_units(rot_s.get(axis_key,0), DEFAULT_OUTPUT_AUNIT, "angle"))
                    ET.SubElement(solid_el, "rotation", rot_attrs)

                # Add transform for the first solid, if present
                transform_f = p.get('transform_first', {})
                pos_f = transform_f.get('position', {})
                rot_f = transform_f.get('rotation', {})
                if any(abs(v) > 1e-9 for v in pos_f.values()):
                    pos_attrs_f = {"unit":DEFAULT_OUTPUT_LUNIT}
                    for axis_key in ['x','y','z']: pos_attrs_f[axis_key] = str(convert_from_internal_units(pos_f.get(axis_key,0), DEFAULT_OUTPUT_LUNIT, "length"))
                    ET.SubElement(solid_el, "firstposition", pos_attrs_f)
                if any(abs(v) > 1e-9 for v in rot_f.values()):
                    rot_attrs_f = {"unit":DEFAULT_OUTPUT_AUNIT}
                    for axis_key in ['x','y','z']: rot_attrs_f[axis_key] = str(convert_from_internal_units(rot_f.get(axis_key,0), DEFAULT_OUTPUT_AUNIT, "angle"))
                    ET.SubElement(solid_el, "firstrotation", rot_attrs_f)

            elif solid_obj.type == 'polycone':
                solid_el.set("startphi", str(convert_from_internal_units(p['startphi'], DEFAULT_OUTPUT_AUNIT, "angle")))
                solid_el.set("deltaphi", str(convert_from_internal_units(p['deltaphi'], DEFAULT_OUTPUT_AUNIT, "angle")))
                for zp in p.get('zplanes', []):
                    ET.SubElement(solid_el, "zplane", {
                        "z": str(zp['z']), "rmin": str(zp['rmin']), "rmax": str(zp['rmax'])
                    }) # Assumes zplanes params are already in output lunit (mm)
            
            elif solid_obj.type == 'genericPolycone':
                solid_el.set("startphi", str(convert_from_internal_units(p['startphi'], DEFAULT_OUTPUT_AUNIT, "angle")))
                solid_el.set("deltaphi", str(convert_from_internal_units(p['deltaphi'], DEFAULT_OUTPUT_AUNIT, "angle")))
                for rzp in p.get('rzpoints', []):
                    ET.SubElement(solid_el, "rzpoint", { "r": str(rzp['r']), "z": str(rzp['z']) })

            elif solid_obj.type == 'polyhedra':
                solid_el.set("startphi", str(convert_from_internal_units(p['startphi'], DEFAULT_OUTPUT_AUNIT, "angle")))
                solid_el.set("deltaphi", str(convert_from_internal_units(p['deltaphi'], DEFAULT_OUTPUT_AUNIT, "angle")))
                solid_el.set("numsides", str(p['numsides']))
                for zp in p.get('zplanes', []): # For G4Polyhedra
                    ET.SubElement(solid_el, "zplane", {
                        "z": str(zp['z']), "rmin": str(zp['rmin']), "rmax": str(zp['rmax'])
                    })
            
            elif solid_obj.type == 'genericPolyhedra':
                solid_el.set("startphi", str(convert_from_internal_units(p['startphi'], DEFAULT_OUTPUT_AUNIT, "angle")))
                solid_el.set("deltaphi", str(convert_from_internal_units(p['deltaphi'], DEFAULT_OUTPUT_AUNIT, "angle")))
                solid_el.set("numsides", str(p['numsides']))
                for rzp in p.get('rzpoints', []): # For G4GenericPolyhedra (uses rzpoints)
                    ET.SubElement(solid_el, "rzpoint", { "r": str(rzp['r']), "z": str(rzp['z']) })
            
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
                solid_el.set("z", str(p['dz'] * 2.0)) # dz was stored as half-length

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
            
            # TODO: Add writer logic for other solid types parsed before...
            # cutTube, reflectedSolid, scaledSolid
            
            elif 'attributes_raw' in p: # Fallback for unhandled solids
                for key, value in p['attributes_raw'].items():
                    solid_el.set(key, str(value)) # Write raw attributes
                print(f"GDML Writer: Solid type '{solid_obj.type}' (name: {name}) written with raw attributes as fallback.")
            else:
                 print(f"GDML Writer: Solid type '{solid_obj.type}' (name: {name}) is not fully supported for writing.")


    def _add_structure(self):
        # ... (same as before, ensure it uses convert_from_internal_units for pos/rot) ...
        if not self.geometry_state.logical_volumes: return
        structure_el = ET.SubElement(self.root, "structure")
        for lv_name, lv_obj in self.geometry_state.logical_volumes.items():
            lv_el = ET.SubElement(structure_el, "volume", {"name": lv_name})
            ET.SubElement(lv_el, "materialref", {"ref": lv_obj.material_ref})
            ET.SubElement(lv_el, "solidref", {"ref": lv_obj.solid_ref})

            for pv_obj in lv_obj.phys_children:
                pv_el = ET.SubElement(lv_el, "physvol", {"name": pv_obj.name})
                if pv_obj.copy_number != 0: # Default is 0, so only write if non-zero
                    pv_el.set("copynumber", str(pv_obj.copy_number))

                ET.SubElement(pv_el, "volumeref", {"ref": pv_obj.volume_ref})

                position_data = pv_obj.position
                if isinstance(position_data, str): # It's a ref
                    ET.SubElement(pv_el, "positionref", {"ref": position_data})
                elif isinstance(position_data, dict) and any(abs(v) > 1e-9 for v in position_data.values()):
                    pos_attrs = {"unit": DEFAULT_OUTPUT_LUNIT}
                    for axis, val in position_data.items():
                        pos_attrs[axis] = str(convert_from_internal_units(val, DEFAULT_OUTPUT_LUNIT, "length"))
                    ET.SubElement(pv_el, "position", pos_attrs)
                
                rotation_data = pv_obj.rotation
                if isinstance(rotation_data, str): # It's a ref
                    ET.SubElement(pv_el, "rotationref", {"ref": rotation_data})
                elif isinstance(rotation_data, dict) and any(abs(v) > 1e-9 for v in rotation_data.values()):
                    rot_attrs = {"unit": DEFAULT_OUTPUT_AUNIT}
                    for axis, val in rotation_data.items(): # Assuming ZYX Euler
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
        # ... (same as before) ...
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
