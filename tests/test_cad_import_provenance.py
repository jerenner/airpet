import sys
import types
import hashlib
import json
from unittest.mock import patch


class _DummyOccObject:
    def __init__(self, *args, **kwargs):
        pass

    def __call__(self, *args, **kwargs):
        return self

    def __getattr__(self, name):
        return self


def _install_occ_stubs():
    if 'OCC' in sys.modules:
        return

    occ_module = types.ModuleType('OCC')
    occ_module.__path__ = []
    core_module = types.ModuleType('OCC.Core')
    core_module.__path__ = []

    sys.modules['OCC'] = occ_module
    sys.modules['OCC.Core'] = core_module

    module_specs = {
        'OCC.Core.STEPControl': {'STEPControl_Reader': _DummyOccObject},
        'OCC.Core.TopAbs': {
            'TopAbs_SOLID': 0,
            'TopAbs_FACE': 1,
            'TopAbs_REVERSED': 2,
        },
        'OCC.Core.TopExp': {'TopExp_Explorer': _DummyOccObject},
        'OCC.Core.BRep': {'BRep_Tool': type('_BRepTool', (), {'Triangulation': staticmethod(lambda *args, **kwargs: None)})},
        'OCC.Core.BRepMesh': {'BRepMesh_IncrementalMesh': _DummyOccObject},
        'OCC.Core.TopLoc': {'TopLoc_Location': _DummyOccObject},
        'OCC.Core.gp': {'gp_Trsf': _DummyOccObject},
        'OCC.Core.TDF': {'TDF_Label': _DummyOccObject, 'TDF_LabelSequence': _DummyOccObject},
        'OCC.Core.XCAFDoc': {
            'XCAFDoc_DocumentTool': type(
                '_XCAFDocDocumentTool',
                (),
                {'ShapeTool': staticmethod(lambda *args, **kwargs: _DummyOccObject())},
            )
        },
        'OCC.Core.STEPCAFControl': {'STEPCAFControl_Reader': _DummyOccObject},
        'OCC.Core.TDocStd': {'TDocStd_Document': _DummyOccObject},
    }

    for module_name, attrs in module_specs.items():
        module = types.ModuleType(module_name)
        for attr_name, value in attrs.items():
            setattr(module, attr_name, value)
        sys.modules[module_name] = module


_install_occ_stubs()

from src.expression_evaluator import ExpressionEvaluator
from src.geometry_types import Assembly, GeometryState, LogicalVolume, PhysicalVolumePlacement, Solid
from src.project_manager import ProjectManager


def _make_pm():
    pm = ProjectManager(ExpressionEvaluator())
    pm.create_empty_project()
    return pm


class DummyStepUpload:
    def __init__(self, data, filename):
        self.data = data
        self.filename = filename

    def save(self, path):
        with open(path, 'wb') as handle:
            handle.write(self.data)


def _build_fake_imported_state(solid_dimensions=('1', '2', '3')):
    state = GeometryState()
    state.grouping_name = 'fixture_import'

    solid = Solid(
        'fixture_solid',
        'box',
        {'x': str(solid_dimensions[0]), 'y': str(solid_dimensions[1]), 'z': str(solid_dimensions[2])},
    )
    state.add_solid(solid)

    lv = LogicalVolume('fixture_lv', solid.name, 'G4_STAINLESS-STEEL')
    state.add_logical_volume(lv)

    assembly = Assembly('fixture_assembly')
    assembly_child = PhysicalVolumePlacement(
        name='fixture_lv_placement',
        volume_ref=lv.name,
        parent_lv_name=assembly.name,
    )
    assembly.add_placement(assembly_child)
    state.add_assembly(assembly)

    top_level_pv = PhysicalVolumePlacement(
        name='fixture_assembly_placement',
        volume_ref=assembly.name,
        parent_lv_name='World',
    )
    state.placements_to_add = [top_level_pv]

    return state, solid, lv, assembly, assembly_child, top_level_pv


def test_step_import_provenance_roundtrips_through_saved_project_state():
    payload_bytes = b'STEP-DATA'
    expected_sha256 = hashlib.sha256(payload_bytes).hexdigest()
    imported_state, solid, lv, assembly, assembly_child, top_level_pv = _build_fake_imported_state()

    pm = _make_pm()
    upload = DummyStepUpload(payload_bytes, 'fixture.step')

    with patch('src.project_manager.parse_step_file', return_value=imported_state):
        success, error_msg, import_report = pm.import_step_with_options(
            upload,
            {
                'groupingName': 'fixture_import',
                'placementMode': 'assembly',
                'parentLVName': 'World',
                'offset': {'x': '0', 'y': '0', 'z': '0'},
                'smartImport': True,
            },
        )

    assert success is True
    assert error_msg is None
    assert import_report is None

    assert len(pm.current_geometry_state.cad_imports) == 1
    import_record = pm.current_geometry_state.cad_imports[0]
    assert import_record['import_id'].startswith('step_import_')
    assert import_record['source'] == {
        'format': 'step',
        'filename': 'fixture.step',
        'sha256': expected_sha256,
        'size_bytes': len(payload_bytes),
    }
    assert import_record['options'] == {
        'grouping_name': 'fixture_import',
        'placement_mode': 'assembly',
        'parent_lv_name': 'World',
        'offset': {'x': '0', 'y': '0', 'z': '0'},
        'smart_import_enabled': True,
    }
    assert import_record['created_object_ids']['solid_ids'] == [solid.id]
    assert import_record['created_object_ids']['logical_volume_ids'] == [lv.id]
    assert import_record['created_object_ids']['assembly_ids'] == [assembly.id]
    assert set(import_record['created_object_ids']['placement_ids']) == {assembly_child.id, top_level_pv.id}
    assert import_record['created_group_names'] == {
        'solid': 'fixture_import_solids',
        'logical_volume': 'fixture_import_lvs',
        'assembly': 'fixture_import_assemblies',
    }

    saved_payload = json.loads(pm.save_project_to_json_string())
    assert saved_payload['cad_imports'][0] == import_record

    pm_round_tripped = ProjectManager(ExpressionEvaluator())
    pm_round_tripped.load_project_from_json_string(json.dumps(saved_payload))
    assert pm_round_tripped.current_geometry_state.cad_imports[0] == import_record


def test_step_reimport_targets_existing_import_and_replaces_the_old_subsystem():
    first_payload_bytes = b'STEP-DATA-ONE'
    second_payload_bytes = b'STEP-DATA-TWO'
    second_sha256 = hashlib.sha256(second_payload_bytes).hexdigest()

    first_imported_state, _, _, _, _, _ = _build_fake_imported_state(('1', '2', '3'))
    second_imported_state, second_solid, second_lv, second_assembly, second_assembly_child, second_top_level_pv = _build_fake_imported_state(
        ('4', '5', '6')
    )

    pm = _make_pm()

    with patch('src.project_manager.parse_step_file', side_effect=[first_imported_state, second_imported_state]) as mock_parse:
        first_upload = DummyStepUpload(first_payload_bytes, 'fixture.step')
        success, error_msg, import_report = pm.import_step_with_options(
            first_upload,
            {
                'groupingName': 'fixture_import',
                'placementMode': 'assembly',
                'parentLVName': 'World',
                'offset': {'x': '0', 'y': '0', 'z': '0'},
                'smartImport': True,
            },
        )

        assert success is True
        assert error_msg is None
        assert import_report is None

        initial_import_record = pm.current_geometry_state.cad_imports[0]
        initial_import_id = initial_import_record['import_id']

        second_upload = DummyStepUpload(second_payload_bytes, 'fixture.step')
        success, error_msg, import_report = pm.import_step_with_options(
            second_upload,
            {
                'reimportTargetImportId': initial_import_id,
            },
        )

    assert success is True
    assert error_msg is None
    assert import_report is None
    assert mock_parse.call_count == 2

    second_parse_options = mock_parse.call_args_list[1][0][1]
    assert second_parse_options['groupingName'] == 'fixture_import'
    assert second_parse_options['placementMode'] == 'assembly'
    assert second_parse_options['parentLVName'] == 'World'
    assert second_parse_options['offset'] == {'x': '0', 'y': '0', 'z': '0'}
    assert second_parse_options['smartImport'] is True

    assert len(pm.current_geometry_state.cad_imports) == 1
    reimport_record = pm.current_geometry_state.cad_imports[0]
    assert reimport_record['import_id'] == initial_import_id
    assert reimport_record['source']['sha256'] == second_sha256
    assert reimport_record['created_object_ids']['solid_ids'] == [second_solid.id]
    assert reimport_record['created_object_ids']['logical_volume_ids'] == [second_lv.id]
    assert reimport_record['created_object_ids']['assembly_ids'] == [second_assembly.id]
    assert set(reimport_record['created_object_ids']['placement_ids']) == {second_assembly_child.id, second_top_level_pv.id}

    assert 'fixture_solid_1' not in pm.current_geometry_state.solids
    assert 'fixture_lv_1' not in pm.current_geometry_state.logical_volumes
    assert 'fixture_assembly_1' not in pm.current_geometry_state.assemblies
    assert pm.current_geometry_state.solids['fixture_solid'].raw_parameters == {'x': '4', 'y': '5', 'z': '6'}

    solid_group = next(group for group in pm.current_geometry_state.ui_groups['solid'] if group['name'] == 'fixture_import_solids')
    lv_group = next(group for group in pm.current_geometry_state.ui_groups['logical_volume'] if group['name'] == 'fixture_import_lvs')
    assembly_group = next(group for group in pm.current_geometry_state.ui_groups['assembly'] if group['name'] == 'fixture_import_assemblies')
    assert solid_group['members'] == ['fixture_solid']
    assert lv_group['members'] == ['fixture_lv']
    assert assembly_group['members'] == ['fixture_assembly']
    assert 'fixture_solid_1' not in solid_group['members']
    assert 'fixture_lv_1' not in lv_group['members']
    assert 'fixture_assembly_1' not in assembly_group['members']


def test_step_reimport_preserves_lv_annotations_and_relinks_sources():
    first_payload_bytes = b'STEP-DATA-FIRST'
    second_payload_bytes = b'STEP-DATA-SECOND'

    first_imported_state, _, _, _, _, _ = _build_fake_imported_state(('1', '2', '3'))
    second_imported_state, _, _, _, _, second_top_level_pv = _build_fake_imported_state(('4', '5', '6'))
    second_top_level_pv.position = {'x': '12', 'y': '34', 'z': '56'}

    pm = _make_pm()

    with patch('src.project_manager.parse_step_file', side_effect=[first_imported_state, second_imported_state]):
        first_upload = DummyStepUpload(first_payload_bytes, 'fixture.step')
        success, error_msg, import_report = pm.import_step_with_options(
            first_upload,
            {
                'groupingName': 'fixture_import',
                'placementMode': 'assembly',
                'parentLVName': 'World',
                'offset': {'x': '0', 'y': '0', 'z': '0'},
                'smartImport': True,
            },
        )

        assert success is True
        assert error_msg is None
        assert import_report is None

        initial_import_id = pm.current_geometry_state.cad_imports[0]['import_id']

        copper_material, error_msg = pm.add_material(
            'Copper',
            {
                'density_expr': '8.96',
                'Z_expr': '29',
            },
        )
        assert error_msg is None
        assert copper_material['name'] == 'Copper'

        success, error_msg = pm.update_logical_volume(
            'fixture_lv',
            'fixture_solid',
            'Copper',
            new_vis_attributes={'color': {'r': 0.1, 'g': 0.2, 'b': 0.3, 'a': 0.9}},
            new_is_sensitive=True,
        )
        assert success is True
        assert error_msg is None

        success, error_msg = pm.create_group('logical_volume', 'manual_import_group')
        assert success is True
        assert error_msg is None
        success, error_msg = pm.move_items_to_group('logical_volume', ['fixture_lv'], 'manual_import_group')
        assert success is True
        assert error_msg is None

        linked_pv = pm._find_pv_by_name('fixture_assembly_placement')
        assert linked_pv is not None
        source_dict, error_msg = pm.add_source(
            'linked_source',
            {'particle': 'gamma', 'energy': '1 MeV'},
            {'x': '0', 'y': '0', 'z': '0'},
            {'x': '0', 'y': '0', 'z': '0'},
            volume_link_id=linked_pv.id,
        )
        assert error_msg is None
        source_name = source_dict['name']
        source_id = source_dict['id']
        assert pm.current_geometry_state.sources[source_name].volume_link_id == linked_pv.id

        second_upload = DummyStepUpload(second_payload_bytes, 'fixture.step')
        success, error_msg, import_report = pm.import_step_with_options(
            second_upload,
            {
                'reimportTargetImportId': initial_import_id,
            },
        )

    assert success is True
    assert error_msg is None
    assert import_report is None

    reimported_lv = pm.current_geometry_state.logical_volumes['fixture_lv']
    assert reimported_lv.material_ref == 'Copper'
    assert reimported_lv.is_sensitive is True
    assert reimported_lv.vis_attributes == {'color': {'r': 0.1, 'g': 0.2, 'b': 0.3, 'a': 0.9}}

    manual_group = next(
        group for group in pm.current_geometry_state.ui_groups['logical_volume']
        if group['name'] == 'manual_import_group'
    )
    assert manual_group['members'] == ['fixture_lv']

    reimported_linked_pv = pm._find_pv_by_name('fixture_assembly_placement')
    assert reimported_linked_pv is not None

    linked_source = pm.current_geometry_state.sources[source_name]
    assert linked_source.id == source_id
    assert linked_source.volume_link_id == reimported_linked_pv.id
    assert linked_source.confine_to_pv == reimported_linked_pv.name
    assert linked_source.position == {'x': '12.0', 'y': '34.0', 'z': '56.0'}
