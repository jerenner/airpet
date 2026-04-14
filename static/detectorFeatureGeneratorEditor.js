import { buildDetectorFeatureGeneratorEditorModel } from './detectorFeatureGeneratorsUi.js';

const RECTANGULAR_DRILLED_HOLE_ARRAY = 'rectangular_drilled_hole_array';
const CIRCULAR_DRILLED_HOLE_ARRAY = 'circular_drilled_hole_array';
const LAYERED_DETECTOR_STACK = 'layered_detector_stack';
const TILED_SENSOR_ARRAY = 'tiled_sensor_array';
const SUPPORT_RIB_ARRAY = 'support_rib_array';
const CHANNEL_CUT_ARRAY = 'channel_cut_array';
const ANNULAR_SHIELD_SLEEVE = 'annular_shield_sleeve';

let modalElement;
let titleElement;
let confirmButton;
let cancelButton;
let nameInput;
let generatorTypeSelect;
let targetLabel;
let targetSelect;
let targetSummary;
let targetLockNotice;
let rectangularFields;
let countXInput;
let countYInput;
let pitchXInput;
let pitchYInput;
let circularFields;
let circularCountInput;
let circularRadiusInput;
let circularOrientationInput;
let layeredFields;
let moduleSizeXInput;
let moduleSizeYInput;
let moduleCountInput;
let modulePitchInput;
let absorberThicknessInput;
let absorberMaterialInput;
let sensorThicknessInput;
let sensorMaterialInput;
let sensorSensitiveInput;
let supportThicknessInput;
let supportMaterialInput;
let sensorArrayFields;
let tileSensorSizeXInput;
let tileSensorSizeYInput;
let tileSensorThicknessInput;
let tileSensorMaterialInput;
let tileSensorSensitiveInput;
let linearArrayFields;
let linearCountInput;
let linearPitchInput;
let linearAxisInput;
let supportRibFields;
let ribWidthInput;
let ribHeightInput;
let ribMaterialInput;
let ribSensitiveInput;
let channelFields;
let channelWidthInput;
let channelDepthInput;
let shieldFields;
let shieldInnerRadiusInput;
let shieldOuterRadiusInput;
let shieldLengthInput;
let shieldMaterialInput;
let offsetXInput;
let offsetYInput;
let offsetZRow;
let offsetZInput;
let holeFields;
let holeDiameterInput;
let holeDepthInput;

let onConfirmCallback = null;
let currentGeneratorEntry = null;
let currentHoleTargetOptions = [];
let currentStackTargetOptions = [];
let currentSelectedHoleTargetName = '';
let currentSelectedStackTargetName = '';

export function coerceTiledSensorArrayPitchValue(pitchValue, sensorSizeValue) {
    const numericPitch = Number(pitchValue);
    const numericSensorSize = Number(sensorSizeValue);

    if (!Number.isFinite(numericSensorSize) || numericSensorSize <= 0) {
        return Number.isFinite(numericPitch) && numericPitch > 0 ? numericPitch : null;
    }

    if (!Number.isFinite(numericPitch) || numericPitch <= 0 || numericPitch < numericSensorSize) {
        return numericSensorSize;
    }

    return numericPitch;
}

function syncTiledSensorArrayPitchDefaults() {
    if (!pitchXInput || !pitchYInput || !tileSensorSizeXInput || !tileSensorSizeYInput) {
        return;
    }

    const nextPitchX = coerceTiledSensorArrayPitchValue(pitchXInput.value, tileSensorSizeXInput.value);
    const nextPitchY = coerceTiledSensorArrayPitchValue(pitchYInput.value, tileSensorSizeYInput.value);

    if (nextPitchX != null) {
        pitchXInput.value = String(nextPitchX);
    }
    if (nextPitchY != null) {
        pitchYInput.value = String(nextPitchY);
    }
}

export function initDetectorFeatureGeneratorEditor(callbacks) {
    onConfirmCallback = callbacks.onConfirm;

    modalElement = document.getElementById('detectorFeatureGeneratorModal');
    titleElement = document.getElementById('detectorFeatureGeneratorTitle');
    confirmButton = document.getElementById('detectorFeatureGeneratorConfirm');
    cancelButton = document.getElementById('detectorFeatureGeneratorCancel');
    nameInput = document.getElementById('detectorFeatureGeneratorName');
    generatorTypeSelect = document.getElementById('detectorFeatureGeneratorType');
    targetLabel = document.getElementById('detectorFeatureGeneratorTargetLabel');
    targetSelect = document.getElementById('detectorFeatureGeneratorTargetSolid');
    targetSummary = document.getElementById('detectorFeatureGeneratorTargetSummary');
    targetLockNotice = document.getElementById('detectorFeatureGeneratorTargetLockNotice');
    rectangularFields = document.getElementById('detectorFeatureGeneratorRectangularFields');
    countXInput = document.getElementById('detectorFeatureGeneratorCountX');
    countYInput = document.getElementById('detectorFeatureGeneratorCountY');
    pitchXInput = document.getElementById('detectorFeatureGeneratorPitchX');
    pitchYInput = document.getElementById('detectorFeatureGeneratorPitchY');
    circularFields = document.getElementById('detectorFeatureGeneratorCircularFields');
    circularCountInput = document.getElementById('detectorFeatureGeneratorCircularCount');
    circularRadiusInput = document.getElementById('detectorFeatureGeneratorCircularRadius');
    circularOrientationInput = document.getElementById('detectorFeatureGeneratorCircularOrientation');
    layeredFields = document.getElementById('detectorFeatureGeneratorLayeredFields');
    moduleSizeXInput = document.getElementById('detectorFeatureGeneratorModuleSizeX');
    moduleSizeYInput = document.getElementById('detectorFeatureGeneratorModuleSizeY');
    moduleCountInput = document.getElementById('detectorFeatureGeneratorModuleCount');
    modulePitchInput = document.getElementById('detectorFeatureGeneratorModulePitch');
    absorberThicknessInput = document.getElementById('detectorFeatureGeneratorAbsorberThickness');
    absorberMaterialInput = document.getElementById('detectorFeatureGeneratorAbsorberMaterial');
    sensorThicknessInput = document.getElementById('detectorFeatureGeneratorSensorThickness');
    sensorMaterialInput = document.getElementById('detectorFeatureGeneratorSensorMaterial');
    sensorSensitiveInput = document.getElementById('detectorFeatureGeneratorSensorSensitive');
    supportThicknessInput = document.getElementById('detectorFeatureGeneratorSupportThickness');
    supportMaterialInput = document.getElementById('detectorFeatureGeneratorSupportMaterial');
    sensorArrayFields = document.getElementById('detectorFeatureGeneratorSensorArrayFields');
    tileSensorSizeXInput = document.getElementById('detectorFeatureGeneratorTileSensorSizeX');
    tileSensorSizeYInput = document.getElementById('detectorFeatureGeneratorTileSensorSizeY');
    tileSensorThicknessInput = document.getElementById('detectorFeatureGeneratorTileSensorThickness');
    tileSensorMaterialInput = document.getElementById('detectorFeatureGeneratorTileSensorMaterial');
    tileSensorSensitiveInput = document.getElementById('detectorFeatureGeneratorTileSensorSensitive');
    linearArrayFields = document.getElementById('detectorFeatureGeneratorLinearArrayFields');
    linearCountInput = document.getElementById('detectorFeatureGeneratorLinearCount');
    linearPitchInput = document.getElementById('detectorFeatureGeneratorLinearPitch');
    linearAxisInput = document.getElementById('detectorFeatureGeneratorLinearAxis');
    supportRibFields = document.getElementById('detectorFeatureGeneratorSupportRibFields');
    ribWidthInput = document.getElementById('detectorFeatureGeneratorRibWidth');
    ribHeightInput = document.getElementById('detectorFeatureGeneratorRibHeight');
    ribMaterialInput = document.getElementById('detectorFeatureGeneratorRibMaterial');
    ribSensitiveInput = document.getElementById('detectorFeatureGeneratorRibSensitive');
    channelFields = document.getElementById('detectorFeatureGeneratorChannelFields');
    channelWidthInput = document.getElementById('detectorFeatureGeneratorChannelWidth');
    channelDepthInput = document.getElementById('detectorFeatureGeneratorChannelDepth');
    shieldFields = document.getElementById('detectorFeatureGeneratorShieldFields');
    shieldInnerRadiusInput = document.getElementById('detectorFeatureGeneratorShieldInnerRadius');
    shieldOuterRadiusInput = document.getElementById('detectorFeatureGeneratorShieldOuterRadius');
    shieldLengthInput = document.getElementById('detectorFeatureGeneratorShieldLength');
    shieldMaterialInput = document.getElementById('detectorFeatureGeneratorShieldMaterial');
    offsetXInput = document.getElementById('detectorFeatureGeneratorOffsetX');
    offsetYInput = document.getElementById('detectorFeatureGeneratorOffsetY');
    offsetZRow = document.getElementById('detectorFeatureGeneratorOffsetZRow');
    offsetZInput = document.getElementById('detectorFeatureGeneratorOffsetZ');
    holeFields = document.getElementById('detectorFeatureGeneratorHoleFields');
    holeDiameterInput = document.getElementById('detectorFeatureGeneratorHoleDiameter');
    holeDepthInput = document.getElementById('detectorFeatureGeneratorHoleDepth');

    cancelButton.addEventListener('click', hide);
    confirmButton.addEventListener('click', handleConfirm);
    generatorTypeSelect.addEventListener('change', updateGeneratorTypeSections);
    targetSelect.addEventListener('change', updateTargetSummary);
    tileSensorSizeXInput.addEventListener('input', () => {
        if (getCurrentGeneratorType() === TILED_SENSOR_ARRAY) {
            syncTiledSensorArrayPitchDefaults();
        }
    });
    tileSensorSizeYInput.addEventListener('input', () => {
        if (getCurrentGeneratorType() === TILED_SENSOR_ARRAY) {
            syncTiledSensorArrayPitchDefaults();
        }
    });
}

export function show(generatorEntry, projectState, selectedItems = []) {
    const model = buildDetectorFeatureGeneratorEditorModel(projectState, generatorEntry, selectedItems);
    if (model.holeTargetOptions.length === 0 && model.stackTargetOptions.length === 0) {
        alert('Create a box solid or choose a logical volume before adding a detector feature generator.');
        return;
    }

    currentGeneratorEntry = generatorEntry && typeof generatorEntry === 'object' ? generatorEntry : null;
    currentHoleTargetOptions = model.holeTargetOptions;
    currentStackTargetOptions = model.stackTargetOptions;
    currentSelectedHoleTargetName = model.selectedHoleTargetName;
    currentSelectedStackTargetName = model.selectedStackTargetName;

    titleElement.textContent = model.title;
    confirmButton.textContent = model.confirmLabel;
    nameInput.value = model.name;
    generatorTypeSelect.value = model.generatorType;
    countXInput.value = String(model.countX);
    countYInput.value = String(model.countY);
    pitchXInput.value = String(model.pitchX);
    pitchYInput.value = String(model.pitchY);
    circularCountInput.value = String(model.circularCount);
    circularRadiusInput.value = String(model.circularRadius);
    circularOrientationInput.value = String(model.circularOrientation);
    moduleSizeXInput.value = String(model.moduleSizeX);
    moduleSizeYInput.value = String(model.moduleSizeY);
    moduleCountInput.value = String(model.moduleCount);
    modulePitchInput.value = String(model.modulePitch);
    absorberThicknessInput.value = String(model.absorberThickness);
    absorberMaterialInput.value = model.absorberMaterial;
    sensorThicknessInput.value = String(model.sensorThickness);
    sensorMaterialInput.value = model.sensorMaterial;
    sensorSensitiveInput.checked = Boolean(model.sensorSensitive);
    supportThicknessInput.value = String(model.supportThickness);
    supportMaterialInput.value = model.supportMaterial;
    tileSensorSizeXInput.value = String(model.tileSensorSizeX);
    tileSensorSizeYInput.value = String(model.tileSensorSizeY);
    tileSensorThicknessInput.value = String(model.tileSensorThickness);
    tileSensorMaterialInput.value = model.tileSensorMaterial;
    tileSensorSensitiveInput.checked = Boolean(model.tileSensorSensitive);
    linearCountInput.value = String(model.linearCount);
    linearPitchInput.value = String(model.linearPitch);
    linearAxisInput.value = model.linearAxis;
    ribWidthInput.value = String(model.ribWidth);
    ribHeightInput.value = String(model.ribHeight);
    ribMaterialInput.value = model.ribMaterial;
    ribSensitiveInput.checked = Boolean(model.ribSensitive);
    channelWidthInput.value = String(model.channelWidth);
    channelDepthInput.value = String(model.channelDepth);
    shieldInnerRadiusInput.value = String(model.shieldInnerRadius);
    shieldOuterRadiusInput.value = String(model.shieldOuterRadius);
    shieldLengthInput.value = String(model.shieldLength);
    shieldMaterialInput.value = model.shieldMaterial;
    offsetXInput.value = String(model.offsetX);
    offsetYInput.value = String(model.offsetY);
    offsetZInput.value = String(model.offsetZ);
    holeDiameterInput.value = String(model.holeDiameter);
    holeDepthInput.value = String(model.holeDepth);

    targetSelect.disabled = model.targetLocked;
    generatorTypeSelect.disabled = model.typeLocked;
    if (targetLockNotice) {
        targetLockNotice.hidden = !(model.targetLocked || model.typeLocked);
    }

    updateGeneratorTypeSections();
    modalElement.style.display = 'block';
}

function hide() {
    modalElement.style.display = 'none';
    currentGeneratorEntry = null;
    currentHoleTargetOptions = [];
    currentStackTargetOptions = [];
    currentSelectedHoleTargetName = '';
    currentSelectedStackTargetName = '';
    targetSelect.disabled = false;
    generatorTypeSelect.disabled = false;
    if (targetLockNotice) {
        targetLockNotice.hidden = true;
    }
    updateGeneratorTypeSections();
}

function getCurrentGeneratorType() {
    return String(generatorTypeSelect?.value || RECTANGULAR_DRILLED_HOLE_ARRAY).trim();
}

function usesParentLogicalVolumeTarget(generatorType) {
    return (
        generatorType === LAYERED_DETECTOR_STACK
        || generatorType === TILED_SENSOR_ARRAY
        || generatorType === SUPPORT_RIB_ARRAY
        || generatorType === ANNULAR_SHIELD_SLEEVE
    );
}

function usesLinearStripArray(generatorType) {
    return generatorType === SUPPORT_RIB_ARRAY || generatorType === CHANNEL_CUT_ARRAY;
}

function getCurrentTargetOptions() {
    return usesParentLogicalVolumeTarget(getCurrentGeneratorType())
        ? currentStackTargetOptions
        : currentHoleTargetOptions;
}

function getEmptyParentTargetSummary(generatorType) {
    if (generatorType === TILED_SENSOR_ARRAY) {
        return 'Select a placed parent logical volume for the tiled sensors.';
    }
    if (generatorType === SUPPORT_RIB_ARRAY) {
        return 'Select a placed parent logical volume for the generated support ribs.';
    }
    if (generatorType === ANNULAR_SHIELD_SLEEVE) {
        return 'Select a placed parent logical volume for the generated shield sleeve.';
    }
    return 'Select a placed parent logical volume for the generated stack.';
}

function getParentTargetSummary(generatorType, optionData) {
    const placementContext = `${optionData.scenePlacementSummary}; ${optionData.placementSummary}`;
    if (generatorType === TILED_SENSOR_ARRAY) {
        return `Parent logical volume: ${placementContext}. Generated sensor cells will be centered on the saved X/Y/Z offset.`;
    }
    if (generatorType === SUPPORT_RIB_ARRAY) {
        return `Parent logical volume: ${placementContext}. Generated ribs will be centered on the saved X/Y/Z offset.`;
    }
    if (generatorType === ANNULAR_SHIELD_SLEEVE) {
        return `Parent logical volume: ${placementContext}. Generated shield sleeves will be centered on the saved X/Y/Z offset.`;
    }
    return `Parent logical volume: ${placementContext}. Generated modules will be centered on the saved offset.`;
}

function populateTargetOptions(options, selectedName, targetType) {
    targetSelect.innerHTML = '';

    options.forEach((optionData) => {
        const option = document.createElement('option');
        option.value = optionData.name;
        option.textContent = optionData.name;
        if (targetType === 'parent') {
            option.dataset.parentLogicalVolumeId = optionData.id || '';
        } else {
            option.dataset.solidId = optionData.id || '';
        }
        targetSelect.appendChild(option);
    });

    if (selectedName) {
        targetSelect.value = selectedName;
    }

    if (!targetSelect.value && options[0]) {
        targetSelect.value = options[0].name;
    }
}

function updateTargetSummary() {
    const generatorType = getCurrentGeneratorType();
    const selectedName = targetSelect.value;
    const optionData = getCurrentTargetOptions().find((option) => option.name === selectedName);

    if (!optionData) {
        targetSummary.textContent = usesParentLogicalVolumeTarget(generatorType)
            ? getEmptyParentTargetSummary(generatorType)
            : 'Select a box solid to target.';
        targetSummary.title = '';
        return;
    }

    if (usesParentLogicalVolumeTarget(generatorType)) {
        targetSummary.textContent = getParentTargetSummary(generatorType, optionData);
        targetSummary.title = '';
        currentSelectedStackTargetName = optionData.name;
        return;
    }

    const names = optionData.logicalVolumeNames || [];
    if (names.length === 0) {
        targetSummary.textContent = generatorType === CHANNEL_CUT_ARRAY
            ? 'Matching logical volumes: none yet. The saved spec will still target this box solid for channel cuts.'
            : 'Matching logical volumes: none yet. The saved spec will still target this box solid.';
        targetSummary.title = '';
        currentSelectedHoleTargetName = optionData.name;
        return;
    }

    const preview = names.slice(0, 3).join(', ');
    const extraCount = names.length > 3 ? `, +${names.length - 3} more` : '';
    targetSummary.textContent = `Matching logical volumes: ${preview}${extraCount}.`;
    targetSummary.title = names.join('\n');
    currentSelectedHoleTargetName = optionData.name;
}

function updateGeneratorTypeSections() {
    const generatorType = getCurrentGeneratorType();
    const isLayeredStack = generatorType === LAYERED_DETECTOR_STACK;
    const isTiledSensorArray = generatorType === TILED_SENSOR_ARRAY;
    const isSupportRibArray = generatorType === SUPPORT_RIB_ARRAY;
    const isChannelCutArray = generatorType === CHANNEL_CUT_ARRAY;
    const isShieldSleeve = generatorType === ANNULAR_SHIELD_SLEEVE;
    const isLinearStripArray = usesLinearStripArray(generatorType);

    if (rectangularFields) {
        rectangularFields.hidden = (
            generatorType !== RECTANGULAR_DRILLED_HOLE_ARRAY
            && !isTiledSensorArray
        );
    }
    if (circularFields) {
        circularFields.hidden = generatorType !== CIRCULAR_DRILLED_HOLE_ARRAY;
    }
    if (layeredFields) {
        layeredFields.hidden = !isLayeredStack;
    }
    if (sensorArrayFields) {
        sensorArrayFields.hidden = !isTiledSensorArray;
    }
    if (linearArrayFields) {
        linearArrayFields.hidden = !isLinearStripArray;
    }
    if (supportRibFields) {
        supportRibFields.hidden = !isSupportRibArray;
    }
    if (channelFields) {
        channelFields.hidden = !isChannelCutArray;
    }
    if (shieldFields) {
        shieldFields.hidden = !isShieldSleeve;
    }
    if (holeFields) {
        holeFields.hidden = isLayeredStack || isTiledSensorArray || isSupportRibArray || isChannelCutArray || isShieldSleeve;
    }
    if (offsetZRow) {
        offsetZRow.hidden = !isLayeredStack && !isTiledSensorArray && !isSupportRibArray && !isShieldSleeve;
    }
    if (targetLabel) {
        targetLabel.textContent = usesParentLogicalVolumeTarget(generatorType) ? 'Parent LV:' : 'Target Solid:';
    }

    if (usesParentLogicalVolumeTarget(generatorType)) {
        populateTargetOptions(currentStackTargetOptions, currentSelectedStackTargetName, 'parent');
    } else {
        populateTargetOptions(currentHoleTargetOptions, currentSelectedHoleTargetName, 'solid');
    }

    if (isTiledSensorArray && !currentGeneratorEntry) {
        syncTiledSensorArrayPitchDefaults();
    }

    updateTargetSummary();
}

function readPositiveInteger(input, labelText) {
    const value = Number.parseInt(input.value, 10);
    if (!Number.isFinite(value) || value <= 0) {
        throw new Error(`${labelText} must be a positive integer.`);
    }
    return value;
}

function readPositiveNumber(input, labelText) {
    const value = Number(input.value);
    if (!Number.isFinite(value) || value <= 0) {
        throw new Error(`${labelText} must be greater than 0.`);
    }
    return value;
}

function readFiniteNumber(input, labelText) {
    const value = Number(input.value);
    if (!Number.isFinite(value)) {
        throw new Error(`${labelText} must be a finite number.`);
    }
    return value;
}

function readRequiredText(input, labelText) {
    const value = String(input.value || '').trim();
    if (!value) {
        throw new Error(`${labelText} is required.`);
    }
    return value;
}

function buildPatternPayload(generatorType) {
    const originOffset = {
        x: readFiniteNumber(offsetXInput, 'Offset X'),
        y: readFiniteNumber(offsetYInput, 'Offset Y'),
    };

    if (generatorType === CIRCULAR_DRILLED_HOLE_ARRAY) {
        return {
            count: readPositiveInteger(circularCountInput, 'Circular count'),
            radius_mm: readPositiveNumber(circularRadiusInput, 'Circle radius'),
            orientation_deg: readFiniteNumber(circularOrientationInput, 'Orientation'),
            origin_offset_mm: originOffset,
            anchor: 'target_center',
        };
    }

    return {
        count_x: readPositiveInteger(countXInput, 'Count X'),
        count_y: readPositiveInteger(countYInput, 'Count Y'),
        pitch_mm: {
            x: readPositiveNumber(pitchXInput, 'Pitch X'),
            y: readPositiveNumber(pitchYInput, 'Pitch Y'),
        },
        origin_offset_mm: originOffset,
        anchor: 'target_center',
    };
}

function buildLayeredStackPayload() {
    return {
        stack: {
            module_size_mm: {
                x: readPositiveNumber(moduleSizeXInput, 'Module size X'),
                y: readPositiveNumber(moduleSizeYInput, 'Module size Y'),
            },
            module_count: readPositiveInteger(moduleCountInput, 'Module count'),
            module_pitch_mm: readPositiveNumber(modulePitchInput, 'Module pitch'),
            origin_offset_mm: {
                x: readFiniteNumber(offsetXInput, 'Offset X'),
                y: readFiniteNumber(offsetYInput, 'Offset Y'),
                z: readFiniteNumber(offsetZInput, 'Offset Z'),
            },
            anchor: 'target_center',
        },
        layers: {
            absorber: {
                material_ref: readRequiredText(absorberMaterialInput, 'Absorber material'),
                thickness_mm: readPositiveNumber(absorberThicknessInput, 'Absorber thickness'),
                is_sensitive: false,
            },
            sensor: {
                material_ref: readRequiredText(sensorMaterialInput, 'Sensor material'),
                thickness_mm: readPositiveNumber(sensorThicknessInput, 'Sensor thickness'),
                is_sensitive: Boolean(sensorSensitiveInput.checked),
            },
            support: {
                material_ref: readRequiredText(supportMaterialInput, 'Support material'),
                thickness_mm: readPositiveNumber(supportThicknessInput, 'Support thickness'),
                is_sensitive: false,
            },
        },
    };
}

function buildTiledSensorArrayPayload() {
    return {
        array: {
            count_x: readPositiveInteger(countXInput, 'Count X'),
            count_y: readPositiveInteger(countYInput, 'Count Y'),
            pitch_mm: {
                x: readPositiveNumber(pitchXInput, 'Pitch X'),
                y: readPositiveNumber(pitchYInput, 'Pitch Y'),
            },
            origin_offset_mm: {
                x: readFiniteNumber(offsetXInput, 'Offset X'),
                y: readFiniteNumber(offsetYInput, 'Offset Y'),
                z: readFiniteNumber(offsetZInput, 'Offset Z'),
            },
            anchor: 'target_center',
        },
        sensor: {
            size_mm: {
                x: readPositiveNumber(tileSensorSizeXInput, 'Sensor size X'),
                y: readPositiveNumber(tileSensorSizeYInput, 'Sensor size Y'),
            },
            thickness_mm: readPositiveNumber(tileSensorThicknessInput, 'Sensor thickness'),
            material_ref: readRequiredText(tileSensorMaterialInput, 'Sensor material'),
            is_sensitive: Boolean(tileSensorSensitiveInput.checked),
        },
    };
}

function buildLinearArrayPayload(includeZOffset = false) {
    const originOffset = {
        x: readFiniteNumber(offsetXInput, 'Offset X'),
        y: readFiniteNumber(offsetYInput, 'Offset Y'),
    };
    if (includeZOffset) {
        originOffset.z = readFiniteNumber(offsetZInput, 'Offset Z');
    }

    return {
        array: {
            count: readPositiveInteger(linearCountInput, 'Feature count'),
            linear_pitch_mm: readPositiveNumber(linearPitchInput, 'Feature pitch'),
            axis: readRequiredText(linearAxisInput, 'Repeat axis').toLowerCase(),
            origin_offset_mm: originOffset,
            anchor: 'target_center',
        },
    };
}

function buildSupportRibPayload() {
    return {
        ...buildLinearArrayPayload(true),
        rib: {
            width_mm: readPositiveNumber(ribWidthInput, 'Rib width'),
            height_mm: readPositiveNumber(ribHeightInput, 'Rib height'),
            material_ref: readRequiredText(ribMaterialInput, 'Rib material'),
            is_sensitive: Boolean(ribSensitiveInput.checked),
        },
    };
}

function buildChannelCutPayload() {
    return {
        ...buildLinearArrayPayload(false),
        channel: {
            width_mm: readPositiveNumber(channelWidthInput, 'Channel width'),
            depth_mm: readPositiveNumber(channelDepthInput, 'Channel depth'),
        },
    };
}

function buildShieldPayload() {
    return {
        shield: {
            inner_radius_mm: readPositiveNumber(shieldInnerRadiusInput, 'Shield inner radius'),
            outer_radius_mm: readPositiveNumber(shieldOuterRadiusInput, 'Shield outer radius'),
            length_mm: readPositiveNumber(shieldLengthInput, 'Shield length'),
            material_ref: readRequiredText(shieldMaterialInput, 'Shield material'),
            origin_offset_mm: {
                x: readFiniteNumber(offsetXInput, 'Offset X'),
                y: readFiniteNumber(offsetYInput, 'Offset Y'),
                z: readFiniteNumber(offsetZInput, 'Offset Z'),
            },
            anchor: 'target_center',
        },
    };
}

function handleConfirm() {
    if (!onConfirmCallback) {
        return;
    }

    try {
        const generatorName = String(nameInput.value || '').trim();
        if (!generatorName) {
            throw new Error('Please provide a generator name.');
        }

        const generatorType = getCurrentGeneratorType();
        const selectedOption = targetSelect.selectedOptions?.[0];
        const targetName = String(targetSelect.value || '').trim();
        if (!targetName) {
            throw new Error(usesParentLogicalVolumeTarget(generatorType)
                ? 'Please choose a parent logical volume.'
                : 'Please choose a target solid.');
        }

        if (usesParentLogicalVolumeTarget(generatorType)) {
            onConfirmCallback({
                generator_id: currentGeneratorEntry?.generator_id,
                generator_type: generatorType,
                name: generatorName,
                target: {
                    parent_logical_volume_ref: {
                        id: String(selectedOption?.dataset?.parentLogicalVolumeId || '').trim(),
                        name: targetName,
                    },
                },
                ...(generatorType === ANNULAR_SHIELD_SLEEVE
                    ? buildShieldPayload()
                    : generatorType === TILED_SENSOR_ARRAY
                    ? buildTiledSensorArrayPayload()
                    : generatorType === SUPPORT_RIB_ARRAY
                        ? buildSupportRibPayload()
                        : buildLayeredStackPayload()),
                realize_now: true,
            });
            hide();
            return;
        }

        onConfirmCallback({
            generator_id: currentGeneratorEntry?.generator_id,
            generator_type: generatorType,
            name: generatorName,
            target: {
                solid_ref: {
                    id: String(selectedOption?.dataset?.solidId || '').trim(),
                    name: targetName,
                },
                logical_volume_refs: [],
            },
            ...(generatorType === CHANNEL_CUT_ARRAY
                ? buildChannelCutPayload()
                : {
                    pattern: buildPatternPayload(generatorType),
                    hole: {
                        shape: 'cylindrical',
                        diameter_mm: readPositiveNumber(holeDiameterInput, 'Hole diameter'),
                        depth_mm: readPositiveNumber(holeDepthInput, 'Hole depth'),
                        axis: 'z',
                        drill_from: 'positive_z_face',
                    },
                }),
            realize_now: true,
        });
        hide();
    } catch (error) {
        alert(error.message || error);
    }
}
