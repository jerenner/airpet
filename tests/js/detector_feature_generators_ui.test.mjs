import test from 'node:test';
import assert from 'node:assert/strict';

import {
    buildDetectorFeatureGeneratorEditorModel,
    describeDetectorFeatureGenerator,
    listDetectorFeatureGeneratorParentOptions,
    listDetectorFeatureGeneratorTargetOptions,
} from '../../static/detectorFeatureGeneratorsUi.js';

test('detector feature generator editor model prefers the selected box target', () => {
    const projectState = {
        solids: {
            collimator_block: { id: 'solid-box-1', name: 'collimator_block', type: 'box' },
            fixture_tube: { id: 'solid-tube-1', name: 'fixture_tube', type: 'tube' },
        },
        logical_volumes: {
            World: { id: 'lv-world', name: 'World', solid_ref: 'world_box' },
            collimator_lv: { id: 'lv-collimator', name: 'collimator_lv', solid_ref: 'collimator_block' },
        },
    };

    const options = listDetectorFeatureGeneratorTargetOptions(projectState);
    assert.deepEqual(options.map((option) => option.name), ['collimator_block']);
    assert.equal(options[0].logicalVolumeSummary, '1 logical volume');

    const model = buildDetectorFeatureGeneratorEditorModel(
        projectState,
        null,
        [{ type: 'logical_volume', id: 'collimator_lv', name: 'collimator_lv' }],
    );

    assert.equal(model.selectedHoleTargetName, 'collimator_block');
    assert.equal(model.selectedHoleTargetId, 'solid-box-1');
    assert.equal(model.name, 'collimator_block_holes');
    assert.deepEqual(model.selectedHoleTargetLogicalVolumeNames, ['collimator_lv']);
    assert.equal(model.targetLocked, false);
    assert.equal(model.generatorType, 'rectangular_drilled_hole_array');
});

test('detector feature generator description stays deterministic for generated entries', () => {
    const projectState = {
        solids: {
            collimator_block: { id: 'solid-box-1', name: 'collimator_block', type: 'box' },
            collimator_block_holes__result: {
                id: 'solid-result-1',
                name: 'collimator_block_holes__result',
                type: 'boolean',
            },
            collimator_block_holes__cutter: {
                id: 'solid-cutter-1',
                name: 'collimator_block_holes__cutter',
                type: 'tube',
            },
        },
        logical_volumes: {
            collimator_lv: { id: 'lv-collimator', name: 'collimator_lv', solid_ref: 'collimator_block_holes__result' },
        },
    };

    const described = describeDetectorFeatureGenerator(
        {
            generator_id: 'dfg_rect_fixture',
            name: 'fixture_collimator_holes',
            target: {
                solid_ref: { id: 'solid-box-1', name: 'collimator_block' },
                logical_volume_refs: [],
            },
            pattern: {
                count_x: 4,
                count_y: 3,
                pitch_mm: { x: 7.5, y: 6.0 },
                origin_offset_mm: { x: 1.25, y: -2.5 },
            },
            hole: {
                diameter_mm: 1.5,
                depth_mm: 8.0,
            },
            realization: {
                status: 'generated',
                result_solid_ref: { id: 'solid-result-1', name: 'collimator_block_holes__result' },
                generated_object_refs: {
                    solid_refs: [
                        { id: 'solid-result-1', name: 'collimator_block_holes__result' },
                        { id: 'solid-cutter-1', name: 'collimator_block_holes__cutter' },
                    ],
                    logical_volume_refs: [
                        { id: 'lv-collimator', name: 'collimator_lv' },
                    ],
                },
            },
        },
        projectState,
    );

    assert.equal(
        described.summary,
        'Rectangular drilled holes on collimator_block · 4 x 3 @ 7.5 x 6 mm · dia 1.5 mm depth 8 mm',
    );
    assert.equal(described.statusBadge, 'generated');
    assert.equal(described.detailRows.find((row) => row.label === 'Result Solid').value, 'collimator_block_holes__result');
    assert.equal(
        described.detailRows.find((row) => row.label === 'Target Logical Volumes').value.text,
        'collimator_lv',
    );
    assert.equal(
        described.detailRows.find((row) => row.label === 'Generated Solids').value.text,
        'collimator_block_holes__result, collimator_block_holes__cutter',
    );
});

test('circular detector feature generator model and description stay deterministic', () => {
    const projectState = {
        solids: {
            circular_block: { id: 'solid-box-2', name: 'circular_block', type: 'box' },
            circular_holes__result: {
                id: 'solid-result-2',
                name: 'circular_holes__result',
                type: 'boolean',
            },
            circular_holes__cutter: {
                id: 'solid-cutter-2',
                name: 'circular_holes__cutter',
                type: 'tube',
            },
        },
        logical_volumes: {
            circular_lv: { id: 'lv-circular', name: 'circular_lv', solid_ref: 'circular_holes__result' },
        },
    };

    const entry = {
        generator_id: 'dfg_circular_fixture',
        generator_type: 'circular_drilled_hole_array',
        name: 'fixture_circular_holes',
        target: {
            solid_ref: { id: 'solid-box-2', name: 'circular_block' },
            logical_volume_refs: [],
        },
        pattern: {
            count: 6,
            radius_mm: 8,
            orientation_deg: 30,
            origin_offset_mm: { x: 1.5, y: -2.0 },
        },
        hole: {
            diameter_mm: 1.25,
            depth_mm: 6.0,
        },
        realization: {
            status: 'generated',
            result_solid_ref: { id: 'solid-result-2', name: 'circular_holes__result' },
            generated_object_refs: {
                solid_refs: [
                    { id: 'solid-result-2', name: 'circular_holes__result' },
                    { id: 'solid-cutter-2', name: 'circular_holes__cutter' },
                ],
                logical_volume_refs: [
                    { id: 'lv-circular', name: 'circular_lv' },
                ],
            },
        },
    };

    const model = buildDetectorFeatureGeneratorEditorModel(projectState, entry);
    assert.equal(model.generatorType, 'circular_drilled_hole_array');
    assert.equal(model.circularCount, 6);
    assert.equal(model.circularRadius, 8);
    assert.equal(model.circularOrientation, 30);
    assert.equal(model.typeLocked, true);

    const described = describeDetectorFeatureGenerator(entry, projectState);
    assert.equal(
        described.summary,
        'Circular drilled holes on circular_block · 6 holes on r 8 mm @ 30 deg · dia 1.25 mm depth 6 mm',
    );
    assert.equal(
        described.detailRows.find((row) => row.label === 'Pattern').value,
        '6 holes on radius 8 mm',
    );
    assert.equal(
        described.detailRows.find((row) => row.label === 'Orientation').value,
        '30 deg',
    );
});

test('layered detector stack model and description stay deterministic', () => {
    const projectState = {
        solids: {
            layered_stack__module_solid: {
                id: 'solid-module-1',
                name: 'layered_stack__module_solid',
                type: 'box',
            },
            layered_stack__absorber_solid: {
                id: 'solid-abs-1',
                name: 'layered_stack__absorber_solid',
                type: 'box',
            },
        },
        logical_volumes: {
            World: { id: 'lv-world', name: 'World', solid_ref: 'world_box', content_type: 'physvol', content: [] },
            layered_stack__module_lv: {
                id: 'lv-module-1',
                name: 'layered_stack__module_lv',
                solid_ref: 'layered_stack__module_solid',
                content_type: 'physvol',
                content: [],
            },
            layered_stack__absorber_lv: {
                id: 'lv-abs-1',
                name: 'layered_stack__absorber_lv',
                solid_ref: 'layered_stack__absorber_solid',
                content_type: 'physvol',
                content: [],
            },
            layered_stack__sensor_lv: {
                id: 'lv-sensor-1',
                name: 'layered_stack__sensor_lv',
                solid_ref: 'layered_stack__sensor_solid',
                content_type: 'physvol',
                content: [],
            },
            layered_stack__support_lv: {
                id: 'lv-support-1',
                name: 'layered_stack__support_lv',
                solid_ref: 'layered_stack__support_solid',
                content_type: 'physvol',
                content: [],
            },
        },
    };

    const parentOptions = listDetectorFeatureGeneratorParentOptions(projectState);
    assert.deepEqual(parentOptions.map((option) => option.name), [
        'layered_stack__absorber_lv',
        'layered_stack__module_lv',
        'layered_stack__sensor_lv',
        'layered_stack__support_lv',
        'World',
    ]);

    const entry = {
        generator_id: 'dfg_layered_fixture',
        generator_type: 'layered_detector_stack',
        name: 'fixture_layered_stack',
        target: {
            parent_logical_volume_ref: { id: 'lv-world', name: 'World' },
        },
        stack: {
            module_size_mm: { x: 24, y: 18 },
            module_count: 3,
            module_pitch_mm: 8.5,
            origin_offset_mm: { x: 1.5, y: -2.0, z: 3.0 },
        },
        layers: {
            absorber: { material_ref: 'G4_Pb', thickness_mm: 4.0, is_sensitive: false },
            sensor: { material_ref: 'G4_Si', thickness_mm: 1.0, is_sensitive: true },
            support: { material_ref: 'G4_Al', thickness_mm: 2.0, is_sensitive: false },
        },
        realization: {
            status: 'generated',
            generated_object_refs: {
                solid_refs: [
                    { id: 'solid-module-1', name: 'layered_stack__module_solid' },
                    { id: 'solid-abs-1', name: 'layered_stack__absorber_solid' },
                ],
                logical_volume_refs: [
                    { id: 'lv-module-1', name: 'layered_stack__module_lv' },
                    { id: 'lv-abs-1', name: 'layered_stack__absorber_lv' },
                    { id: 'lv-sensor-1', name: 'layered_stack__sensor_lv' },
                    { id: 'lv-support-1', name: 'layered_stack__support_lv' },
                ],
                placement_refs: [
                    { id: 'pv-module-1', name: 'fixture_layered_stack__module_1_pv' },
                    { id: 'pv-module-2', name: 'fixture_layered_stack__module_2_pv' },
                ],
            },
        },
    };

    const model = buildDetectorFeatureGeneratorEditorModel(projectState, entry);
    assert.equal(model.generatorType, 'layered_detector_stack');
    assert.equal(model.selectedStackTargetName, 'World');
    assert.equal(model.selectedStackTargetId, 'lv-world');
    assert.equal(model.moduleSizeX, 24);
    assert.equal(model.moduleSizeY, 18);
    assert.equal(model.moduleCount, 3);
    assert.equal(model.modulePitch, 8.5);
    assert.equal(model.absorberMaterial, 'G4_Pb');
    assert.equal(model.sensorSensitive, true);
    assert.equal(model.typeLocked, true);

    const described = describeDetectorFeatureGenerator(entry, projectState);
    assert.equal(
        described.summary,
        'Layered stack in World · 3 modules @ 8.5 mm pitch · 24 x 18 mm sandwich',
    );
    assert.equal(
        described.detailRows.find((row) => row.label === 'Module Layout').value,
        '3 modules @ 8.5 mm pitch',
    );
    assert.equal(
        described.detailRows.find((row) => row.label === 'Layers').value,
        'absorber 4 mm G4_Pb · sensor 1 mm G4_Si · support 2 mm G4_Al',
    );
});

test('tiled sensor array model and description stay deterministic', () => {
    const projectState = {
        solids: {
            tiled_sensor_array__sensor_solid: {
                id: 'solid-sensor-array-1',
                name: 'tiled_sensor_array__sensor_solid',
                type: 'box',
            },
        },
        logical_volumes: {
            World: { id: 'lv-world', name: 'World', solid_ref: 'world_box', content_type: 'physvol', content: [] },
            tiled_sensor_array__sensor_lv: {
                id: 'lv-sensor-array-1',
                name: 'tiled_sensor_array__sensor_lv',
                solid_ref: 'tiled_sensor_array__sensor_solid',
                content_type: 'physvol',
                content: [],
            },
        },
    };

    const entry = {
        generator_id: 'dfg_tiled_sensor_fixture',
        generator_type: 'tiled_sensor_array',
        name: 'fixture_sensor_array',
        target: {
            parent_logical_volume_ref: { id: 'lv-world', name: 'World' },
        },
        array: {
            count_x: 4,
            count_y: 3,
            pitch_mm: { x: 6.5, y: 5.0 },
            origin_offset_mm: { x: 1.5, y: -2.0, z: 3.0 },
        },
        sensor: {
            size_mm: { x: 5.8, y: 4.2 },
            thickness_mm: 1.1,
            material_ref: 'G4_Si',
            is_sensitive: true,
        },
        realization: {
            status: 'generated',
            generated_object_refs: {
                solid_refs: [
                    { id: 'solid-sensor-array-1', name: 'tiled_sensor_array__sensor_solid' },
                ],
                logical_volume_refs: [
                    { id: 'lv-sensor-array-1', name: 'tiled_sensor_array__sensor_lv' },
                ],
                placement_refs: [
                    { id: 'pv-sensor-1', name: 'fixture_sensor_array__sensor_r1_c1_pv' },
                    { id: 'pv-sensor-2', name: 'fixture_sensor_array__sensor_r1_c2_pv' },
                    { id: 'pv-sensor-3', name: 'fixture_sensor_array__sensor_r1_c3_pv' },
                    { id: 'pv-sensor-4', name: 'fixture_sensor_array__sensor_r1_c4_pv' },
                ],
            },
        },
    };

    const model = buildDetectorFeatureGeneratorEditorModel(projectState, entry);
    assert.equal(model.generatorType, 'tiled_sensor_array');
    assert.equal(model.selectedStackTargetName, 'World');
    assert.equal(model.countX, 4);
    assert.equal(model.countY, 3);
    assert.equal(model.pitchX, 6.5);
    assert.equal(model.pitchY, 5.0);
    assert.equal(model.tileSensorSizeX, 5.8);
    assert.equal(model.tileSensorSizeY, 4.2);
    assert.equal(model.tileSensorThickness, 1.1);
    assert.equal(model.tileSensorMaterial, 'G4_Si');
    assert.equal(model.tileSensorSensitive, true);

    const described = describeDetectorFeatureGenerator(entry, projectState);
    assert.equal(
        described.summary,
        'Tiled sensor array in World · 4 x 3 @ 6.5 x 5 mm pitch · 5.8 x 4.2 x 1.1 mm G4_Si',
    );
    assert.equal(
        described.detailRows.find((row) => row.label === 'Array Pattern').value,
        '4 x 3 sensors @ 6.5 x 5 mm',
    );
    assert.equal(
        described.detailRows.find((row) => row.label === 'Sensor Cell').value,
        '5.8 x 4.2 x 1.1 mm G4_Si',
    );
    assert.equal(
        described.detailRows.find((row) => row.label === 'Sensitive').value,
        'Yes',
    );
});

test('support rib array model and description stay deterministic', () => {
    const projectState = {
        solids: {
            support_ribs__rib_solid: {
                id: 'solid-rib-1',
                name: 'support_ribs__rib_solid',
                type: 'box',
            },
        },
        logical_volumes: {
            World: { id: 'lv-world', name: 'World', solid_ref: 'world_box', content_type: 'physvol', content: [] },
            support_ribs__rib_lv: {
                id: 'lv-rib-1',
                name: 'support_ribs__rib_lv',
                solid_ref: 'support_ribs__rib_solid',
                content_type: 'physvol',
                content: [],
            },
        },
    };

    const entry = {
        generator_id: 'dfg_support_ribs_fixture',
        generator_type: 'support_rib_array',
        name: 'fixture_support_ribs',
        target: {
            parent_logical_volume_ref: { id: 'lv-world', name: 'World' },
        },
        array: {
            count: 4,
            linear_pitch_mm: 9,
            axis: 'x',
            origin_offset_mm: { x: 1.5, y: -2.0, z: 3.0 },
        },
        rib: {
            width_mm: 1.5,
            height_mm: 2.5,
            material_ref: 'G4_Al',
            is_sensitive: false,
        },
        realization: {
            status: 'generated',
            generated_object_refs: {
                solid_refs: [
                    { id: 'solid-rib-1', name: 'support_ribs__rib_solid' },
                ],
                logical_volume_refs: [
                    { id: 'lv-rib-1', name: 'support_ribs__rib_lv' },
                ],
                placement_refs: [
                    { id: 'pv-rib-1', name: 'fixture_support_ribs__rib_1_pv' },
                    { id: 'pv-rib-2', name: 'fixture_support_ribs__rib_2_pv' },
                ],
            },
        },
    };

    const model = buildDetectorFeatureGeneratorEditorModel(projectState, entry);
    assert.equal(model.generatorType, 'support_rib_array');
    assert.equal(model.selectedStackTargetName, 'World');
    assert.equal(model.linearCount, 4);
    assert.equal(model.linearPitch, 9);
    assert.equal(model.linearAxis, 'x');
    assert.equal(model.ribWidth, 1.5);
    assert.equal(model.ribHeight, 2.5);
    assert.equal(model.ribMaterial, 'G4_Al');
    assert.equal(model.ribSensitive, false);

    const described = describeDetectorFeatureGenerator(entry, projectState);
    assert.equal(
        described.summary,
        'Support ribs in World · 4 ribs across X @ 9 mm pitch · 1.5 mm wide x 2.5 mm tall G4_Al',
    );
    assert.equal(
        described.detailRows.find((row) => row.label === 'Rib Pattern').value,
        '4 ribs across X @ 9 mm',
    );
    assert.equal(
        described.detailRows.find((row) => row.label === 'Rib Geometry').value,
        '1.5 mm wide x 2.5 mm tall G4_Al',
    );
});

test('channel cut array model and description stay deterministic', () => {
    const projectState = {
        solids: {
            channel_block: { id: 'solid-channel-target', name: 'channel_block', type: 'box' },
            channel_block__result: {
                id: 'solid-channel-result',
                name: 'channel_block__result',
                type: 'boolean',
            },
            channel_block__channel_cutter: {
                id: 'solid-channel-cutter',
                name: 'channel_block__channel_cutter',
                type: 'box',
            },
        },
        logical_volumes: {
            channel_lv: { id: 'lv-channel', name: 'channel_lv', solid_ref: 'channel_block__result' },
        },
    };

    const entry = {
        generator_id: 'dfg_channel_fixture',
        generator_type: 'channel_cut_array',
        name: 'fixture_channels',
        target: {
            solid_ref: { id: 'solid-channel-target', name: 'channel_block' },
            logical_volume_refs: [],
        },
        array: {
            count: 3,
            linear_pitch_mm: 7.5,
            axis: 'y',
            origin_offset_mm: { x: 1.0, y: -1.5 },
        },
        channel: {
            width_mm: 1.25,
            depth_mm: 6.0,
        },
        realization: {
            status: 'generated',
            result_solid_ref: { id: 'solid-channel-result', name: 'channel_block__result' },
            generated_object_refs: {
                solid_refs: [
                    { id: 'solid-channel-result', name: 'channel_block__result' },
                    { id: 'solid-channel-cutter', name: 'channel_block__channel_cutter' },
                ],
                logical_volume_refs: [
                    { id: 'lv-channel', name: 'channel_lv' },
                ],
            },
        },
    };

    const model = buildDetectorFeatureGeneratorEditorModel(projectState, entry);
    assert.equal(model.generatorType, 'channel_cut_array');
    assert.equal(model.selectedHoleTargetName, 'channel_block');
    assert.equal(model.linearCount, 3);
    assert.equal(model.linearPitch, 7.5);
    assert.equal(model.linearAxis, 'y');
    assert.equal(model.channelWidth, 1.25);
    assert.equal(model.channelDepth, 6);

    const described = describeDetectorFeatureGenerator(entry, projectState);
    assert.equal(
        described.summary,
        'Channel cuts on channel_block · 3 channels across Y @ 7.5 mm pitch · 1.25 mm wide depth 6 mm',
    );
    assert.equal(
        described.detailRows.find((row) => row.label === 'Channel Pattern').value,
        '3 channels across Y @ 7.5 mm',
    );
    assert.equal(
        described.detailRows.find((row) => row.label === 'Channel Cut').value,
        '1.25 mm wide, 6 mm deep',
    );
});
