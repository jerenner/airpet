import sys
import types
import hashlib
import json
from pathlib import Path
from unittest.mock import patch

from src.smart_cad_classifier import summarize_candidates


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
import src.step_parser as step_parser

STEP_FIXTURE_CORPUS_DIR = Path(__file__).resolve().parent / 'fixtures' / 'step' / 'corpus'


def _make_pm():
    pm = ProjectManager(ExpressionEvaluator())
    pm.create_empty_project()
    return pm


def test_step_parser_creates_only_the_grouping_named_top_level_assembly(tmp_path):
    class _DummyDocument:
        def __init__(self, *args, **kwargs):
            pass

        def Main(self):
            return object()

    class _DummyReader:
        def ReadFile(self, *args, **kwargs):
            return None

        def Transfer(self, *args, **kwargs):
            return None

    class _DummyShapeTool:
        def GetFreeShapes(self, *args, **kwargs):
            return None

    class _DummyLabelSequence:
        def Length(self):
            return 0

    step_file = tmp_path / 'sample.step'
    step_file.write_bytes(b'STEP-DATA')

    with patch.object(step_parser, 'TDocStd_Document', _DummyDocument), \
        patch.object(step_parser, 'STEPCAFControl_Reader', _DummyReader), \
        patch.object(step_parser.XCAFDoc_DocumentTool, 'ShapeTool', return_value=_DummyShapeTool()), \
        patch.object(step_parser, 'TDF_LabelSequence', _DummyLabelSequence):
        imported_state = step_parser.parse_step_file(
            str(step_file),
            {
                'groupingName': 'fixture_import',
                'placementMode': 'assembly',
            },
        )

    assert list(imported_state.assemblies.keys()) == ['fixture_import']
    assert imported_state.grouping_name == 'fixture_import'


class DummyStepUpload:
    def __init__(self, data, filename):
        self.data = data
        self.filename = filename

    def save(self, path):
        with open(path, 'wb') as handle:
            handle.write(self.data)


def _load_step_fixture_bytes(filename):
    return (STEP_FIXTURE_CORPUS_DIR / filename).read_bytes()


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


def _build_fixture_imported_state(temp_path, options=None):
    fixture_text = Path(temp_path).read_text(encoding='utf-8')

    if 'AIRPET_SCENARIO=fixture_import_base' in fixture_text:
        imported_state, _, _, _, _, _ = _build_fake_imported_state(('1', '2', '3'))
        smart_candidates = [
            {
                'source_id': 'fixture_import_base_box',
                'classification': 'box',
                'confidence': 0.95,
                'params': {'x': 1, 'y': 2, 'z': 3},
                'fallback_reason': None,
                'selected_mode': 'primitive',
            },
            {
                'source_id': 'fixture_import_base_shell',
                'classification': 'tessellated',
                'confidence': 0.1,
                'params': {},
                'fallback_reason': 'no_primitive_match_v1',
                'selected_mode': 'tessellated',
            },
        ]
    elif 'AIRPET_SCENARIO=fixture_import_revised' in fixture_text:
        imported_state, _, _, _, _, _ = _build_fake_imported_state(('4', '5', '6'))
        smart_candidates = [
            {
                'source_id': 'fixture_import_revised_box',
                'classification': 'box',
                'confidence': 0.97,
                'params': {'x': 4, 'y': 5, 'z': 6},
                'fallback_reason': None,
                'selected_mode': 'primitive',
            },
            {
                'source_id': 'fixture_import_revised_cylinder',
                'classification': 'cylinder',
                'confidence': 0.88,
                'params': {'rmax': 4.0, 'z': 12.0},
                'fallback_reason': None,
                'selected_mode': 'primitive',
            },
            {
                'source_id': 'fixture_import_revised_shell',
                'classification': 'tessellated',
                'confidence': 0.2,
                'params': {},
                'fallback_reason': 'below_confidence_threshold',
                'selected_mode': 'tessellated',
            },
        ]
    else:
        raise AssertionError(f'Unexpected STEP fixture marker in {temp_path}')

    imported_state.smart_import_report = {
        'enabled': True,
        'policy': {
            'primitive_confidence_threshold': 0.8,
        },
        'candidates': smart_candidates,
        'summary': summarize_candidates(smart_candidates),
    }

    return imported_state


def _build_fake_imported_state_with_multiple_lvs():
    state = GeometryState()
    state.grouping_name = 'fixture_import'

    solid_a = Solid(
        'fixture_solid_a',
        'box',
        {'x': '1', 'y': '2', 'z': '3'},
    )
    state.add_solid(solid_a)

    solid_b = Solid(
        'fixture_solid_b',
        'box',
        {'x': '4', 'y': '5', 'z': '6'},
    )
    state.add_solid(solid_b)

    lv_a = LogicalVolume('fixture_lv_a', solid_a.name, 'G4_STAINLESS-STEEL')
    lv_b = LogicalVolume('fixture_lv_b', solid_b.name, 'G4_STAINLESS-STEEL')
    state.add_logical_volume(lv_a)
    state.add_logical_volume(lv_b)

    assembly = Assembly('fixture_assembly')
    assembly_child_a = PhysicalVolumePlacement(
        name='fixture_lv_a_placement',
        volume_ref=lv_a.name,
        parent_lv_name=assembly.name,
    )
    assembly_child_b = PhysicalVolumePlacement(
        name='fixture_lv_b_placement',
        volume_ref=lv_b.name,
        parent_lv_name=assembly.name,
    )
    assembly.add_placement(assembly_child_a)
    assembly.add_placement(assembly_child_b)
    state.add_assembly(assembly)

    top_level_pv = PhysicalVolumePlacement(
        name='fixture_assembly_placement',
        volume_ref=assembly.name,
        parent_lv_name='World',
    )
    state.placements_to_add = [top_level_pv]

    return state, (solid_a, solid_b), (lv_a, lv_b), (assembly_child_a, assembly_child_b), top_level_pv


def _build_fake_individual_imported_state(part_specs):
    state = GeometryState()
    state.grouping_name = 'fixture_import'
    state.placements_to_add = []

    for spec in part_specs:
        part_name = spec['name']
        dimensions = spec.get('dimensions', ('1', '2', '3'))
        position = spec.get('position', {'x': '0', 'y': '0', 'z': '0'})
        rotation = spec.get('rotation')
        scale = spec.get('scale')

        solid = Solid(
            f'{part_name}_solid',
            'box',
            {'x': str(dimensions[0]), 'y': str(dimensions[1]), 'z': str(dimensions[2])},
        )
        state.add_solid(solid)

        lv = LogicalVolume(part_name, solid.name, 'G4_STAINLESS-STEEL')
        state.add_logical_volume(lv)

        pv = PhysicalVolumePlacement(
            name=f'{part_name}_placement',
            volume_ref=lv.name,
            parent_lv_name='World',
            position_val_or_ref=position,
            rotation_val_or_ref=rotation,
            scale_val_or_ref=scale,
        )
        state.placements_to_add.append(pv)

    return state


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
    assert import_record['created_object_ids']['top_level_placement_ids'] == [top_level_pv.id]
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


def test_step_import_persists_compact_smart_import_outcome_summary():
    payload_bytes = b'STEP-DATA-SMART-OUTCOME'
    imported_state, solid, lv, assembly, assembly_child, top_level_pv = _build_fake_imported_state()
    smart_candidates = [
        {
            'source_id': 'fixture_solid_0',
            'classification': 'box',
            'confidence': 0.95,
            'params': {'x': 1, 'y': 2, 'z': 3},
            'fallback_reason': None,
            'selected_mode': 'primitive',
        },
        {
            'source_id': 'fixture_solid_1',
            'classification': 'cylinder',
            'confidence': 0.55,
            'params': {'rmin': 0.0, 'rmax': 5.0, 'z': 12.0},
            'fallback_reason': 'below_confidence_threshold',
            'selected_mode': 'tessellated',
        },
        {
            'source_id': 'fixture_solid_2',
            'classification': 'tessellated',
            'confidence': 0.0,
            'params': {},
            'fallback_reason': 'no_primitive_match_v1',
            'selected_mode': 'tessellated',
        },
    ]
    smart_import_report = {
        'enabled': True,
        'policy': {
            'primitive_confidence_threshold': 0.8,
        },
        'candidates': smart_candidates,
        'summary': summarize_candidates(smart_candidates),
    }
    imported_state.smart_import_report = smart_import_report

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
    assert import_report['summary'] == smart_import_report['summary']

    assert len(pm.current_geometry_state.cad_imports) == 1
    import_record = pm.current_geometry_state.cad_imports[0]
    assert import_record['smart_import_summary']['summary'] == smart_import_report['summary']
    assert import_record['smart_import_summary']['summary_text'] == '2 primitive candidates, 2 tessellated fallbacks'
    assert import_record['smart_import_summary']['primitive_candidate_count'] == 2
    assert import_record['smart_import_summary']['selected_primitive_count'] == 1
    assert import_record['smart_import_summary']['selected_tessellated_count'] == 2
    assert import_record['smart_import_summary']['fallback_reason_counts'] == {
        'below_confidence_threshold': 1,
        'no_primitive_match_v1': 1,
    }
    assert import_record['smart_import_summary']['top_fallback_reasons'] == [
        {'reason': 'below_confidence_threshold', 'count': 1},
        {'reason': 'no_primitive_match_v1', 'count': 1},
    ]

    saved_payload = json.loads(pm.save_project_to_json_string())
    assert saved_payload['cad_imports'][0]['smart_import_summary'] == import_record['smart_import_summary']

    pm_round_tripped = ProjectManager(ExpressionEvaluator())
    pm_round_tripped.load_project_from_json_string(json.dumps(saved_payload))
    assert pm_round_tripped.current_geometry_state.cad_imports[0]['smart_import_summary'] == import_record['smart_import_summary']


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
    assert reimport_record['created_object_ids']['top_level_placement_ids'] == [second_top_level_pv.id]

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


def test_step_reimport_records_a_deterministic_part_diff_summary():
    first_payload_bytes = b'STEP-DATA-DIFF-ONE'
    second_payload_bytes = b'STEP-DATA-DIFF-TWO'

    first_imported_state = _build_fake_individual_imported_state([
        {
            'name': 'fixture_part_a',
            'dimensions': ('1', '2', '3'),
            'position': {'x': '0', 'y': '0', 'z': '0'},
        },
        {
            'name': 'fixture_part_b',
            'dimensions': ('4', '5', '6'),
            'position': {'x': '10', 'y': '0', 'z': '0'},
        },
        {
            'name': 'fixture_part_c',
            'dimensions': ('7', '8', '9'),
            'position': {'x': '20', 'y': '0', 'z': '0'},
        },
    ])

    second_imported_state = _build_fake_individual_imported_state([
        {
            'name': 'fixture_part_a',
            'dimensions': ('1.5', '2', '3'),
            'position': {'x': '0', 'y': '0', 'z': '0'},
        },
        {
            'name': 'fixture_part_b_renamed',
            'dimensions': ('4', '5', '6'),
            'position': {'x': '10', 'y': '0', 'z': '0'},
        },
        {
            'name': 'fixture_part_d',
            'dimensions': ('10', '11', '12'),
            'position': {'x': '30', 'y': '0', 'z': '0'},
        },
    ])

    pm = _make_pm()

    with patch('src.project_manager.parse_step_file', side_effect=[first_imported_state, second_imported_state]):
        first_upload = DummyStepUpload(first_payload_bytes, 'fixture.step')
        success, error_msg, import_report = pm.import_step_with_options(
            first_upload,
            {
                'groupingName': 'fixture_import',
                'placementMode': 'individual',
                'parentLVName': 'World',
                'offset': {'x': '0', 'y': '0', 'z': '0'},
                'smartImport': True,
            },
        )

        assert success is True
        assert error_msg is None
        assert import_report is None

        initial_import_id = pm.current_geometry_state.cad_imports[0]['import_id']

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

    reimport_record = pm.current_geometry_state.cad_imports[0]
    reimport_diff = reimport_record['reimport_diff_summary']

    assert reimport_diff['summary'] == {
        'total_before': 3,
        'total_after': 3,
        'unchanged_count': 0,
        'added_count': 1,
        'removed_count': 1,
        'renamed_count': 1,
        'changed_count': 1,
    }
    assert reimport_diff['added_parts'] == [
        {
            'kind': 'logical_volume',
            'name': 'fixture_part_d',
            'signature': reimport_diff['added_parts'][0]['signature'],
        }
    ]
    assert reimport_diff['removed_parts'] == [
        {
            'kind': 'logical_volume',
            'name': 'fixture_part_c',
            'signature': reimport_diff['removed_parts'][0]['signature'],
        }
    ]
    assert reimport_diff['renamed_parts'] == [
        {
            'kind': 'logical_volume',
            'before_name': 'fixture_part_b',
            'after_name': 'fixture_part_b_renamed',
            'signature': reimport_diff['renamed_parts'][0]['signature'],
        }
    ]
    assert reimport_diff['changed_parts'] == [
        {
            'kind': 'logical_volume',
            'name': 'fixture_part_a',
            'before_signature': reimport_diff['changed_parts'][0]['before_signature'],
            'after_signature': reimport_diff['changed_parts'][0]['after_signature'],
        }
    ]
    assert reimport_diff['changed_parts'][0]['before_signature'] != reimport_diff['changed_parts'][0]['after_signature']
    assert reimport_diff['cleanup_policy'] == {
        'replacement_mode': 'replace_in_place',
        'obsolete_part_action': 'remove',
        'removed_count': 1,
        'summary_text': 'Supported STEP reimport replaces the target import in place and removes obsolete imported parts.',
    }

    saved_payload = json.loads(pm.save_project_to_json_string())
    assert saved_payload['cad_imports'][0]['reimport_diff_summary'] == reimport_diff

    pm_round_tripped = ProjectManager(ExpressionEvaluator())
    pm_round_tripped.load_project_from_json_string(json.dumps(saved_payload))
    assert pm_round_tripped.current_geometry_state.cad_imports[0]['reimport_diff_summary'] == reimport_diff


def test_step_import_reimport_fixture_corpus_tracks_compact_summary_and_replacement():
    base_fixture = STEP_FIXTURE_CORPUS_DIR / 'fixture_import_base.step'
    revised_fixture = STEP_FIXTURE_CORPUS_DIR / 'fixture_import_revised.step'

    base_payload_bytes = _load_step_fixture_bytes(base_fixture.name)
    revised_payload_bytes = _load_step_fixture_bytes(revised_fixture.name)
    base_sha256 = hashlib.sha256(base_payload_bytes).hexdigest()
    revised_sha256 = hashlib.sha256(revised_payload_bytes).hexdigest()

    pm = _make_pm()

    with patch('src.project_manager.parse_step_file', side_effect=_build_fixture_imported_state) as mock_parse:
        success, error_msg, base_report = pm.import_step_with_options(
            DummyStepUpload(base_payload_bytes, base_fixture.name),
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
        assert base_report['summary']['selected_mode_counts'] == {'primitive': 1, 'tessellated': 1}

        initial_import_record = pm.current_geometry_state.cad_imports[0]
        initial_import_id = initial_import_record['import_id']
        assert initial_import_record['source']['filename'] == base_fixture.name
        assert initial_import_record['source']['sha256'] == base_sha256
        assert initial_import_record['smart_import_summary']['summary_text'] == '1 primitive candidates, 1 tessellated fallbacks'

        success, error_msg, revised_report = pm.import_step_with_options(
            DummyStepUpload(revised_payload_bytes, revised_fixture.name),
            {
                'reimportTargetImportId': initial_import_id,
            },
        )

    assert success is True
    assert error_msg is None
    assert revised_report['summary']['selected_mode_counts'] == {'primitive': 2, 'tessellated': 1}
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
    assert reimport_record['source']['filename'] == revised_fixture.name
    assert reimport_record['source']['sha256'] == revised_sha256
    assert reimport_record['smart_import_summary']['summary_text'] == '2 primitive candidates, 1 tessellated fallbacks'
    assert reimport_record['reimport_diff_summary']['summary'] == {
        'total_before': 1,
        'total_after': 1,
        'unchanged_count': 0,
        'added_count': 0,
        'removed_count': 0,
        'renamed_count': 0,
        'changed_count': 1,
    }
    assert reimport_record['reimport_diff_summary']['cleanup_policy'] == {
        'replacement_mode': 'replace_in_place',
        'obsolete_part_action': 'remove',
        'removed_count': 0,
        'summary_text': 'Supported STEP reimport replaces the target import in place and removes obsolete imported parts.',
    }

    assert 'fixture_solid_1' not in pm.current_geometry_state.solids
    assert 'fixture_lv_1' not in pm.current_geometry_state.logical_volumes
    assert 'fixture_assembly_1' not in pm.current_geometry_state.assemblies
    assert pm.current_geometry_state.solids['fixture_solid'].raw_parameters == {'x': '4', 'y': '5', 'z': '6'}


def test_step_import_logical_volume_batch_assignment_uses_import_ids_atomically():
    payload_bytes = b'STEP-DATA-BATCH'

    imported_state, _, (lv_a, lv_b), _, _ = _build_fake_imported_state_with_multiple_lvs()

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

    import_record = pm.current_geometry_state.cad_imports[0]
    imported_lv_ids = import_record['created_object_ids']['logical_volume_ids']
    assert set(imported_lv_ids) == {lv_a.id, lv_b.id}

    copper_material, error_msg = pm.add_material(
        'Copper',
        {
            'density_expr': '8.96',
            'Z_expr': '29',
        },
    )
    assert error_msg is None
    assert copper_material['name'] == 'Copper'

    history_index_before = pm.history_index

    success, error_msg, updated_lv_names = pm.update_logical_volume_batch([
        {'id': lv_a.id, 'material_ref': 'Copper', 'is_sensitive': True},
        {'id': lv_b.id, 'material_ref': 'Copper', 'is_sensitive': True},
    ])

    assert success is True
    assert error_msg is None
    assert updated_lv_names == ['fixture_lv_a', 'fixture_lv_b']
    assert pm.current_geometry_state.logical_volumes['fixture_lv_a'].material_ref == 'Copper'
    assert pm.current_geometry_state.logical_volumes['fixture_lv_b'].material_ref == 'Copper'
    assert pm.current_geometry_state.logical_volumes['fixture_lv_a'].is_sensitive is True
    assert pm.current_geometry_state.logical_volumes['fixture_lv_b'].is_sensitive is True
    assert pm.history_index == history_index_before + 1


def test_step_import_logical_volume_batch_rolls_back_on_invalid_material():
    payload_bytes = b'STEP-DATA-BATCH-ROLLBACK'

    imported_state, _, (lv_a, lv_b), _, _ = _build_fake_imported_state_with_multiple_lvs()

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

    original_material_refs = {
        'fixture_lv_a': pm.current_geometry_state.logical_volumes['fixture_lv_a'].material_ref,
        'fixture_lv_b': pm.current_geometry_state.logical_volumes['fixture_lv_b'].material_ref,
    }

    copper_material, error_msg = pm.add_material(
        'Copper',
        {
            'density_expr': '8.96',
            'Z_expr': '29',
        },
    )
    assert error_msg is None
    assert copper_material['name'] == 'Copper'

    history_index_before = pm.history_index

    success, error_msg, updated_lv_names = pm.update_logical_volume_batch([
        {'id': lv_a.id, 'material_ref': 'Copper', 'is_sensitive': True},
        {'id': lv_b.id, 'material_ref': 'MissingMat', 'is_sensitive': True},
    ])

    assert success is False
    assert "MissingMat" in error_msg
    assert updated_lv_names == []
    assert {
        'fixture_lv_a': pm.current_geometry_state.logical_volumes['fixture_lv_a'].material_ref,
        'fixture_lv_b': pm.current_geometry_state.logical_volumes['fixture_lv_b'].material_ref,
    } == original_material_refs
    assert pm.history_index == history_index_before
