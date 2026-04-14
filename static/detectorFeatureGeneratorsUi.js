const RECTANGULAR_DRILLED_HOLE_ARRAY = 'rectangular_drilled_hole_array';
const CIRCULAR_DRILLED_HOLE_ARRAY = 'circular_drilled_hole_array';
const LAYERED_DETECTOR_STACK = 'layered_detector_stack';
const TILED_SENSOR_ARRAY = 'tiled_sensor_array';
const SUPPORT_RIB_ARRAY = 'support_rib_array';
const CHANNEL_CUT_ARRAY = 'channel_cut_array';
const ANNULAR_SHIELD_SLEEVE = 'annular_shield_sleeve';

function normalizeString(value, fallback = '') {
    const text = String(value ?? '').trim();
    return text || fallback;
}

function normalizeObjectRef(rawRef) {
    const ref = rawRef && typeof rawRef === 'object' ? rawRef : {};
    const id = normalizeString(ref.id, '');
    const name = normalizeString(ref.name, '');

    return {
        id,
        name,
    };
}

function resolveObjectName(rawRef, objectsByName) {
    const ref = normalizeObjectRef(rawRef);
    const registry = objectsByName && typeof objectsByName === 'object' ? objectsByName : {};

    if (ref.name && Object.prototype.hasOwnProperty.call(registry, ref.name)) {
        return ref.name;
    }

    if (ref.id) {
        for (const [candidateName, candidate] of Object.entries(registry)) {
            if (candidate && normalizeString(candidate.id, '') === ref.id) {
                return candidateName;
            }
        }
    }

    return ref.name || ref.id || '';
}

function formatNumber(value) {
    const number = Number(value);
    if (!Number.isFinite(number)) {
        return normalizeString(value, '0');
    }
    return String(Number(number.toFixed(6)));
}

function pluralize(count, singular, plural = `${singular}s`) {
    return `${count} ${count === 1 ? singular : plural}`;
}

function buildListValue(items, emptyText = 'None') {
    const normalized = Array.isArray(items)
        ? items.map((item) => normalizeString(item, '')).filter(Boolean)
        : [];

    if (normalized.length === 0) {
        return { text: emptyText, title: emptyText };
    }

    const preview = normalized.slice(0, 3).join(', ');
    return {
        text: normalized.length > 3 ? `${preview}, +${normalized.length - 3} more` : preview,
        title: normalized.join('\n'),
    };
}

function getLogicalVolumeNamesForSolid(projectState, solidName) {
    const logicalVolumes = projectState?.logical_volumes || {};
    return Object.values(logicalVolumes)
        .filter((lv) => lv && normalizeString(lv.solid_ref, '') === solidName)
        .map((lv) => normalizeString(lv.name, ''))
        .filter(Boolean)
        .sort((a, b) => a.localeCompare(b));
}

function countInstantiatedLogicalVolumes(projectState) {
    const logicalVolumes = projectState?.logical_volumes || {};
    const assemblies = projectState?.assemblies || {};
    const worldVolumeName = normalizeString(projectState?.world_volume_ref, '');
    const instanceCounts = new Map();

    function incrementLogicalVolume(name) {
        const normalizedName = normalizeString(name, '');
        if (!normalizedName) {
            return;
        }
        instanceCounts.set(normalizedName, (instanceCounts.get(normalizedName) || 0) + 1);
    }

    function visitPlacedRef(volumeRef, path = []) {
        const normalizedRef = normalizeString(volumeRef, '');
        if (!normalizedRef) {
            return;
        }

        if (Object.prototype.hasOwnProperty.call(logicalVolumes, normalizedRef)) {
            incrementLogicalVolume(normalizedRef);
            visitLogicalVolume(normalizedRef, path);
            return;
        }

        if (Object.prototype.hasOwnProperty.call(assemblies, normalizedRef)) {
            visitAssembly(normalizedRef, path);
        }
    }

    function visitAssembly(assemblyName, path = []) {
        const normalizedName = normalizeString(assemblyName, '');
        const cycleKey = `ASM:${normalizedName}`;
        if (!normalizedName || path.includes(cycleKey)) {
            return;
        }

        const assembly = assemblies[normalizedName];
        if (!assembly) {
            return;
        }

        const nextPath = [...path, cycleKey];
        const placements = Array.isArray(assembly.placements) ? assembly.placements : [];
        placements.forEach((placement) => {
            visitPlacedRef(placement?.volume_ref, nextPath);
        });
    }

    function visitLogicalVolume(logicalVolumeName, path = []) {
        const normalizedName = normalizeString(logicalVolumeName, '');
        const cycleKey = `LV:${normalizedName}`;
        if (!normalizedName || path.includes(cycleKey)) {
            return;
        }

        const logicalVolume = logicalVolumes[normalizedName];
        if (!logicalVolume) {
            return;
        }

        const nextPath = [...path, cycleKey];
        const contentType = normalizeString(logicalVolume.content_type, 'physvol');
        if (contentType === 'physvol') {
            const placements = Array.isArray(logicalVolume.content) ? logicalVolume.content : [];
            placements.forEach((placement) => {
                visitPlacedRef(placement?.volume_ref, nextPath);
            });
            return;
        }

        visitPlacedRef(logicalVolume.content?.volume_ref, nextPath);
    }

    if (!worldVolumeName || !Object.prototype.hasOwnProperty.call(logicalVolumes, worldVolumeName)) {
        return instanceCounts;
    }

    incrementLogicalVolume(worldVolumeName);
    visitLogicalVolume(worldVolumeName, []);
    return instanceCounts;
}

function listLiveScenePlacementRecords(projectState) {
    const logicalVolumes = projectState?.logical_volumes || {};
    const assemblies = projectState?.assemblies || {};
    const worldVolumeName = normalizeString(projectState?.world_volume_ref, '');
    const livePlacements = [];

    function recordPlacement(placement) {
        const placementId = normalizeString(placement?.id, '');
        if (!placementId) {
            return;
        }

        livePlacements.push({
            id: placementId,
            name: normalizeString(placement?.name, ''),
            volumeRef: normalizeString(placement?.volume_ref, ''),
        });
    }

    function visitPlacedRef(volumeRef, path = []) {
        const normalizedRef = normalizeString(volumeRef, '');
        if (!normalizedRef) {
            return;
        }

        if (Object.prototype.hasOwnProperty.call(logicalVolumes, normalizedRef)) {
            visitLogicalVolume(normalizedRef, path);
            return;
        }

        if (Object.prototype.hasOwnProperty.call(assemblies, normalizedRef)) {
            visitAssembly(normalizedRef, path);
        }
    }

    function visitAssembly(assemblyName, path = []) {
        const normalizedName = normalizeString(assemblyName, '');
        const cycleKey = `ASM:${normalizedName}`;
        if (!normalizedName || path.includes(cycleKey)) {
            return;
        }

        const assembly = assemblies[normalizedName];
        if (!assembly) {
            return;
        }

        const nextPath = [...path, cycleKey];
        const placements = Array.isArray(assembly.placements) ? assembly.placements : [];
        placements.forEach((placement) => {
            recordPlacement(placement);
            visitPlacedRef(placement?.volume_ref, nextPath);
        });
    }

    function visitLogicalVolume(logicalVolumeName, path = []) {
        const normalizedName = normalizeString(logicalVolumeName, '');
        const cycleKey = `LV:${normalizedName}`;
        if (!normalizedName || path.includes(cycleKey)) {
            return;
        }

        const logicalVolume = logicalVolumes[normalizedName];
        if (!logicalVolume) {
            return;
        }

        const nextPath = [...path, cycleKey];
        const contentType = normalizeString(logicalVolume.content_type, 'physvol');
        if (contentType === 'physvol') {
            const placements = Array.isArray(logicalVolume.content) ? logicalVolume.content : [];
            placements.forEach((placement) => {
                recordPlacement(placement);
                visitPlacedRef(placement?.volume_ref, nextPath);
            });
            return;
        }

        visitPlacedRef(logicalVolume.content?.volume_ref, nextPath);
    }

    if (!worldVolumeName || !Object.prototype.hasOwnProperty.call(logicalVolumes, worldVolumeName)) {
        return livePlacements;
    }

    visitLogicalVolume(worldVolumeName, []);
    return livePlacements;
}

function buildDefaultGeneratorName(targetName, generatorType) {
    const base = normalizeString(targetName, 'detector_feature').replace(/[^\w]+/g, '_');
    if (generatorType === LAYERED_DETECTOR_STACK) {
        return `${base}_detector_stack`;
    }
    if (generatorType === TILED_SENSOR_ARRAY) {
        return `${base}_sensor_array`;
    }
    if (generatorType === SUPPORT_RIB_ARRAY) {
        return `${base}_support_ribs`;
    }
    if (generatorType === CHANNEL_CUT_ARRAY) {
        return `${base}_channels`;
    }
    if (generatorType === ANNULAR_SHIELD_SLEEVE) {
        return `${base}_shield`;
    }
    return `${base}_holes`;
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

function normalizeSelectedItems(selectedItems) {
    return Array.isArray(selectedItems) ? selectedItems.filter((item) => item && typeof item === 'object') : [];
}

function resolveSelectedTargetSolidName(projectState, selectedItems) {
    const solids = projectState?.solids || {};
    const logicalVolumes = projectState?.logical_volumes || {};

    for (const item of normalizeSelectedItems(selectedItems)) {
        if (item.type === 'solid') {
            const solidName = normalizeString(item.name || item.id, '');
            if (solidName && solids[solidName]?.type === 'box') {
                return solidName;
            }
        }

        if (item.type === 'logical_volume') {
            const lvName = normalizeString(item.name || item.id, '');
            const lv = logicalVolumes[lvName];
            const solidName = normalizeString(lv?.solid_ref, '');
            if (solidName && solids[solidName]?.type === 'box') {
                return solidName;
            }
        }
    }

    return '';
}

function resolveSelectedParentLogicalVolumeName(projectState, selectedItems) {
    const logicalVolumes = projectState?.logical_volumes || {};

    for (const item of normalizeSelectedItems(selectedItems)) {
        if (item.type !== 'logical_volume') {
            continue;
        }
        const lvName = normalizeString(item.name || item.id, '');
        const lv = logicalVolumes[lvName];
        const contentType = normalizeString(lv?.content_type, 'physvol');
        if (lvName && lv && contentType === 'physvol') {
            return lvName;
        }
    }

    return '';
}

function getGeneratorType(rawType, fallbackType = RECTANGULAR_DRILLED_HOLE_ARRAY) {
    const normalizedType = normalizeString(rawType, fallbackType);
    if (normalizedType === CIRCULAR_DRILLED_HOLE_ARRAY) {
        return CIRCULAR_DRILLED_HOLE_ARRAY;
    }
    if (normalizedType === LAYERED_DETECTOR_STACK) {
        return LAYERED_DETECTOR_STACK;
    }
    if (normalizedType === TILED_SENSOR_ARRAY) {
        return TILED_SENSOR_ARRAY;
    }
    if (normalizedType === SUPPORT_RIB_ARRAY) {
        return SUPPORT_RIB_ARRAY;
    }
    if (normalizedType === CHANNEL_CUT_ARRAY) {
        return CHANNEL_CUT_ARRAY;
    }
    if (normalizedType === ANNULAR_SHIELD_SLEEVE) {
        return ANNULAR_SHIELD_SLEEVE;
    }
    return RECTANGULAR_DRILLED_HOLE_ARRAY;
}

function formatAxisLabel(axis) {
    const normalizedAxis = normalizeString(axis, 'x').toLowerCase();
    return normalizedAxis === 'y' ? 'Y' : 'X';
}

export function listDetectorFeatureGeneratorTargetOptions(projectState) {
    const solids = projectState?.solids || {};

    return Object.values(solids)
        .filter((solid) => solid && solid.type === 'box')
        .map((solid) => {
            const solidName = normalizeString(solid.name, '');
            const logicalVolumeNames = getLogicalVolumeNamesForSolid(projectState, solidName);
            return {
                id: normalizeString(solid.id, ''),
                name: solidName,
                logicalVolumeNames,
                logicalVolumeSummary: logicalVolumeNames.length > 0
                    ? pluralize(logicalVolumeNames.length, 'logical volume')
                    : 'no matching logical volumes yet',
            };
        })
        .sort((a, b) => a.name.localeCompare(b.name));
}

export function listDetectorFeatureGeneratorParentOptions(projectState, includeDetachedLogicalVolumeName = '') {
    const logicalVolumes = projectState?.logical_volumes || {};
    const instantiatedLogicalVolumeCounts = countInstantiatedLogicalVolumes(projectState);
    const includedDetachedName = normalizeString(includeDetachedLogicalVolumeName, '');
    const shouldFilterByScenePlacement = instantiatedLogicalVolumeCounts.size > 0;

    return Object.values(logicalVolumes)
        .filter((lv) => lv && normalizeString(lv.content_type, 'physvol') === 'physvol')
        .map((lv) => {
            const placementCount = Array.isArray(lv.content) ? lv.content.length : 0;
            const name = normalizeString(lv.name, '');
            const scenePlacementCount = instantiatedLogicalVolumeCounts.get(name) || 0;
            const isInstantiated = !shouldFilterByScenePlacement || scenePlacementCount > 0;
            return {
                id: normalizeString(lv.id, ''),
                name,
                placementCount,
                placementSummary: placementCount > 0
                    ? pluralize(placementCount, 'child placement')
                    : 'no child placements yet',
                scenePlacementCount,
                scenePlacementSummary: isInstantiated
                    ? pluralize(scenePlacementCount || 1, 'live scene instance')
                    : 'not placed in the live scene yet',
                isInstantiated,
            };
        })
        .filter((option) => option.name)
        .filter((option) => option.isInstantiated || option.name === includedDetachedName)
        .sort((a, b) => a.name.localeCompare(b.name));
}

export function describeDetectorFeatureGeneratorLaunchState(projectState) {
    const holeTargetOptions = listDetectorFeatureGeneratorTargetOptions(projectState);
    const parentTargetOptions = listDetectorFeatureGeneratorParentOptions(projectState);

    if (holeTargetOptions.length > 0) {
        return {
            canLaunch: true,
            title: 'Create a new detector generator from Hierarchy > + Tools.',
            hint: 'Hierarchy > + Tools is the primary launch surface for drilled-hole patterns, stacks, tiled arrays, ribs, channels, and shield sleeves.',
        };
    }

    if (parentTargetOptions.length > 0) {
        return {
            canLaunch: true,
            title: 'Create a new detector generator from Hierarchy > + Tools.',
            hint: 'No box-solid targets are available yet, but parent-logical-volume generators can still launch from Hierarchy > + Tools.',
        };
    }

    return {
        canLaunch: false,
        title: 'Create a box solid or place a logical volume in the live scene before launching a detector generator.',
        hint: 'Detector-generator launch is disabled until there is at least one eligible box solid or placed parent logical volume.',
    };
}

export function describeDetectorFeatureGeneratorPanelState(projectState) {
    const launchState = describeDetectorFeatureGeneratorLaunchState(projectState);
    const generators = Array.isArray(projectState?.detector_feature_generators)
        ? projectState.detector_feature_generators.filter((entry) => entry && typeof entry === 'object')
        : [];

    return {
        intro: generators.length > 0
            ? 'Create detector generators from Hierarchy > + Tools. Saved generators stay editable and can be regenerated here.'
            : launchState.canLaunch
                ? 'Create detector generators from Hierarchy > + Tools.'
                : launchState.title,
        hint: launchState.canLaunch && generators.length > 0 ? '' : launchState.hint,
        empty: generators.length > 0 ? '' : 'No detector feature generators saved yet.',
        defaultExpandedIndex: generators.length === 1 ? 0 : -1,
    };
}

export function buildDetectorFeatureGeneratorSelectionContext(rawEntry, projectState) {
    const entry = rawEntry && typeof rawEntry === 'object' ? rawEntry : {};
    const target = entry.target && typeof entry.target === 'object' ? entry.target : {};
    const realization = entry.realization && typeof entry.realization === 'object'
        ? entry.realization
        : {};
    const generatedRefs = realization.generated_object_refs && typeof realization.generated_object_refs === 'object'
        ? realization.generated_object_refs
        : {};
    const status = normalizeString(realization.status, 'spec_only');
    const buttonLabel = 'Select Geometry';

    if (status !== 'generated') {
        return {
            selectionIds: [],
            selectionSummary: 'No generated geometry to select yet.',
            buttonLabel,
            buttonTitle: 'Generate this detector feature first to select related geometry.',
        };
    }

    const livePlacements = listLiveScenePlacementRecords(projectState);
    const livePlacementIds = new Set(livePlacements.map((placement) => placement.id));
    const generatedPlacementIds = Array.isArray(generatedRefs.placement_refs)
        ? generatedRefs.placement_refs
            .map((ref) => normalizeObjectRef(ref).id)
            .filter((placementId) => livePlacementIds.has(placementId))
        : [];

    if (generatedPlacementIds.length > 0) {
        const selectionSummary = pluralize(generatedPlacementIds.length, 'generated placement');
        return {
            selectionIds: generatedPlacementIds,
            selectionSummary,
            buttonLabel,
            buttonTitle: `Select ${selectionSummary} in the hierarchy and highlight ${generatedPlacementIds.length === 1 ? 'it' : 'them'} in the live scene.`,
        };
    }

    const generatedLogicalVolumeNames = Array.isArray(generatedRefs.logical_volume_refs)
        ? generatedRefs.logical_volume_refs
            .map((ref) => resolveObjectName(ref, projectState?.logical_volumes || {}))
            .filter(Boolean)
        : [];
    const targetedLogicalVolumeNames = Array.isArray(target.logical_volume_refs)
        ? target.logical_volume_refs
            .map((ref) => resolveObjectName(ref, projectState?.logical_volumes || {}))
            .filter(Boolean)
        : [];
    const targetSolidName = resolveObjectName(target.solid_ref, projectState?.solids || {});
    const fallbackLogicalVolumeNames = targetSolidName
        ? getLogicalVolumeNamesForSolid(projectState, targetSolidName)
        : [];
    const logicalVolumeNames = generatedLogicalVolumeNames.length > 0
        ? generatedLogicalVolumeNames
        : (targetedLogicalVolumeNames.length > 0 ? targetedLogicalVolumeNames : fallbackLogicalVolumeNames);
    const logicalVolumeNameSet = new Set(logicalVolumeNames);
    const affectedPlacementIds = livePlacements
        .filter((placement) => logicalVolumeNameSet.has(placement.volumeRef))
        .map((placement) => placement.id);

    if (affectedPlacementIds.length > 0) {
        const selectionSummary = pluralize(affectedPlacementIds.length, 'affected placement');
        return {
            selectionIds: affectedPlacementIds,
            selectionSummary,
            buttonLabel,
            buttonTitle: `Select ${selectionSummary} in the hierarchy and highlight ${affectedPlacementIds.length === 1 ? 'it' : 'them'} in the live scene.`,
        };
    }

    return {
        selectionIds: [],
        selectionSummary: 'No live geometry available to select.',
        buttonLabel,
        buttonTitle: 'No generated or affected live-scene placements are available to select for this detector feature.',
    };
}

export function buildDetectorFeatureGeneratorEditorModel(projectState, generatorEntry = null, selectedItems = []) {
    const holeTargetOptions = listDetectorFeatureGeneratorTargetOptions(projectState);
    const stackTargetOptions = listDetectorFeatureGeneratorParentOptions(
        projectState,
        resolveObjectName(generatorEntry?.target?.parent_logical_volume_ref, projectState?.logical_volumes || {}),
    );
    const fallbackType = holeTargetOptions.length > 0
        ? RECTANGULAR_DRILLED_HOLE_ARRAY
        : SUPPORT_RIB_ARRAY;
    const generatorType = getGeneratorType(generatorEntry?.generator_type, fallbackType);

    const selectedHoleTargetName = (
        generatorEntry
            ? resolveObjectName(generatorEntry.target?.solid_ref, projectState?.solids || {})
            : ''
    ) || resolveSelectedTargetSolidName(projectState, selectedItems) || holeTargetOptions[0]?.name || '';
    const selectedStackTargetName = (
        generatorEntry
            ? resolveObjectName(generatorEntry.target?.parent_logical_volume_ref, projectState?.logical_volumes || {})
            : ''
    ) || resolveSelectedParentLogicalVolumeName(projectState, selectedItems) || stackTargetOptions[0]?.name || '';

    const selectedHoleTarget = holeTargetOptions.find((option) => option.name === selectedHoleTargetName) || holeTargetOptions[0] || null;
    const selectedStackTarget = stackTargetOptions.find((option) => option.name === selectedStackTargetName) || stackTargetOptions[0] || null;

    const pattern = generatorEntry?.pattern || {};
    const pitch = pattern.pitch_mm || {};
    const patternOriginOffset = pattern.origin_offset_mm || {};
    const hole = generatorEntry?.hole || {};
    const stack = generatorEntry?.stack || {};
    const stackSize = stack.module_size_mm || {};
    const stackOriginOffset = stack.origin_offset_mm || {};
    const array = generatorEntry?.array || {};
    const arrayPitch = array.pitch_mm || {};
    const arrayOriginOffset = array.origin_offset_mm || {};
    const layers = generatorEntry?.layers || {};
    const absorber = layers.absorber || {};
    const sensor = layers.sensor || {};
    const support = layers.support || {};
    const tiledSensor = generatorEntry?.sensor || {};
    const tiledSensorSize = tiledSensor.size_mm || {};
    const rib = generatorEntry?.rib || {};
    const channel = generatorEntry?.channel || {};
    const shield = generatorEntry?.shield || {};
    const shieldOriginOffset = shield.origin_offset_mm || {};
    const defaultTileSensorSizeX = Number.isFinite(Number(tiledSensorSize.x)) ? Number(tiledSensorSize.x) : 6;
    const defaultTileSensorSizeY = Number.isFinite(Number(tiledSensorSize.y)) ? Number(tiledSensorSize.y) : 6;
    const parentOriginOffset = (
        generatorType === TILED_SENSOR_ARRAY || generatorType === SUPPORT_RIB_ARRAY
    )
        ? arrayOriginOffset
        : generatorType === ANNULAR_SHIELD_SLEEVE
            ? shieldOriginOffset
            : stackOriginOffset;

    const defaultTargetName = usesParentLogicalVolumeTarget(generatorType)
        ? selectedStackTarget?.name || 'detector_stack'
        : selectedHoleTarget?.name || 'patterned_holes';
    const isLinearStripArray = usesLinearStripArray(generatorType);

    return {
        isEdit: Boolean(generatorEntry),
        generatorId: normalizeString(generatorEntry?.generator_id, ''),
        generatorType,
        title: generatorEntry ? 'Edit Detector Feature Generator' : 'New Detector Feature Generator',
        confirmLabel: generatorEntry ? 'Save & Generate' : 'Create & Generate',
        holeTargetOptions,
        stackTargetOptions,
        selectedHoleTargetName: selectedHoleTarget?.name || '',
        selectedHoleTargetId: selectedHoleTarget?.id || '',
        selectedHoleTargetLogicalVolumeNames: selectedHoleTarget?.logicalVolumeNames || [],
        selectedHoleTargetLogicalVolumeSummary: selectedHoleTarget?.logicalVolumeSummary || 'No eligible box solids.',
        selectedStackTargetName: selectedStackTarget?.name || '',
        selectedStackTargetId: selectedStackTarget?.id || '',
        selectedStackTargetPlacementSummary: selectedStackTarget?.placementSummary || 'No eligible parent logical volumes.',
        targetLocked: Boolean(generatorEntry),
        typeLocked: Boolean(generatorEntry),
        name: normalizeString(generatorEntry?.name, buildDefaultGeneratorName(defaultTargetName, generatorType)),
        countX: Number.isFinite(Number(
            generatorType === TILED_SENSOR_ARRAY ? array.count_x : pattern.count_x
        )) ? Number(generatorType === TILED_SENSOR_ARRAY ? array.count_x : pattern.count_x) : 3,
        countY: Number.isFinite(Number(
            generatorType === TILED_SENSOR_ARRAY ? array.count_y : pattern.count_y
        )) ? Number(generatorType === TILED_SENSOR_ARRAY ? array.count_y : pattern.count_y) : 3,
        pitchX: Number.isFinite(Number(
            generatorType === TILED_SENSOR_ARRAY ? arrayPitch.x : pitch.x
        )) ? Number(generatorType === TILED_SENSOR_ARRAY ? arrayPitch.x : pitch.x) : (
            generatorType === TILED_SENSOR_ARRAY ? defaultTileSensorSizeX : 5
        ),
        pitchY: Number.isFinite(Number(
            generatorType === TILED_SENSOR_ARRAY ? arrayPitch.y : pitch.y
        )) ? Number(generatorType === TILED_SENSOR_ARRAY ? arrayPitch.y : pitch.y) : (
            generatorType === TILED_SENSOR_ARRAY ? defaultTileSensorSizeY : 5
        ),
        linearCount: Number.isFinite(Number(array.count)) ? Number(array.count) : 4,
        linearPitch: Number.isFinite(Number(array.linear_pitch_mm)) ? Number(array.linear_pitch_mm) : 8,
        linearAxis: normalizeString(array.axis, 'x').toLowerCase() === 'y' ? 'y' : 'x',
        circularCount: Number.isFinite(Number(pattern.count)) ? Number(pattern.count) : 6,
        circularRadius: Number.isFinite(Number(pattern.radius_mm)) ? Number(pattern.radius_mm) : 8,
        circularOrientation: Number.isFinite(Number(pattern.orientation_deg)) ? Number(pattern.orientation_deg) : 0,
        offsetX: Number.isFinite(Number(
            usesParentLogicalVolumeTarget(generatorType)
                ? parentOriginOffset.x
                : isLinearStripArray ? arrayOriginOffset.x : patternOriginOffset.x
        )) ? Number(
            usesParentLogicalVolumeTarget(generatorType)
                ? parentOriginOffset.x
                : isLinearStripArray ? arrayOriginOffset.x : patternOriginOffset.x
        ) : 0,
        offsetY: Number.isFinite(Number(
            usesParentLogicalVolumeTarget(generatorType)
                ? parentOriginOffset.y
                : isLinearStripArray ? arrayOriginOffset.y : patternOriginOffset.y
        )) ? Number(
            usesParentLogicalVolumeTarget(generatorType)
                ? parentOriginOffset.y
                : isLinearStripArray ? arrayOriginOffset.y : patternOriginOffset.y
        ) : 0,
        offsetZ: Number.isFinite(Number(
            generatorType === TILED_SENSOR_ARRAY || generatorType === SUPPORT_RIB_ARRAY
                ? arrayOriginOffset.z
                : generatorType === ANNULAR_SHIELD_SLEEVE
                    ? shieldOriginOffset.z
                : stackOriginOffset.z
        )) ? Number(
            generatorType === TILED_SENSOR_ARRAY || generatorType === SUPPORT_RIB_ARRAY
                ? arrayOriginOffset.z
                : generatorType === ANNULAR_SHIELD_SLEEVE
                    ? shieldOriginOffset.z
                : stackOriginOffset.z
        ) : 0,
        holeDiameter: Number.isFinite(Number(hole.diameter_mm)) ? Number(hole.diameter_mm) : 2,
        holeDepth: Number.isFinite(Number(hole.depth_mm)) ? Number(hole.depth_mm) : 5,
        moduleSizeX: Number.isFinite(Number(stackSize.x)) ? Number(stackSize.x) : 24,
        moduleSizeY: Number.isFinite(Number(stackSize.y)) ? Number(stackSize.y) : 18,
        moduleCount: Number.isFinite(Number(stack.module_count)) ? Number(stack.module_count) : 3,
        modulePitch: Number.isFinite(Number(stack.module_pitch_mm)) ? Number(stack.module_pitch_mm) : 8,
        absorberThickness: Number.isFinite(Number(absorber.thickness_mm)) ? Number(absorber.thickness_mm) : 4,
        absorberMaterial: normalizeString(absorber.material_ref, 'G4_Pb'),
        sensorThickness: Number.isFinite(Number(sensor.thickness_mm)) ? Number(sensor.thickness_mm) : 1,
        sensorMaterial: normalizeString(sensor.material_ref, 'G4_Si'),
        sensorSensitive: Boolean(sensor.is_sensitive ?? true),
        supportThickness: Number.isFinite(Number(support.thickness_mm)) ? Number(support.thickness_mm) : 2,
        supportMaterial: normalizeString(support.material_ref, 'G4_Al'),
        tileSensorSizeX: defaultTileSensorSizeX,
        tileSensorSizeY: defaultTileSensorSizeY,
        tileSensorThickness: Number.isFinite(Number(tiledSensor.thickness_mm)) ? Number(tiledSensor.thickness_mm) : 1,
        tileSensorMaterial: normalizeString(tiledSensor.material_ref, 'G4_Si'),
        tileSensorSensitive: Boolean(tiledSensor.is_sensitive ?? true),
        ribWidth: Number.isFinite(Number(rib.width_mm)) ? Number(rib.width_mm) : 1.5,
        ribHeight: Number.isFinite(Number(rib.height_mm)) ? Number(rib.height_mm) : 3,
        ribMaterial: normalizeString(rib.material_ref, 'G4_Al'),
        ribSensitive: Boolean(rib.is_sensitive ?? false),
        channelWidth: Number.isFinite(Number(channel.width_mm)) ? Number(channel.width_mm) : 1.5,
        channelDepth: Number.isFinite(Number(channel.depth_mm)) ? Number(channel.depth_mm) : 4,
        shieldInnerRadius: Number.isFinite(Number(shield.inner_radius_mm)) ? Number(shield.inner_radius_mm) : 8,
        shieldOuterRadius: Number.isFinite(Number(shield.outer_radius_mm)) ? Number(shield.outer_radius_mm) : 12,
        shieldLength: Number.isFinite(Number(shield.length_mm)) ? Number(shield.length_mm) : 30,
        shieldMaterial: normalizeString(shield.material_ref, 'G4_Pb'),
    };
}

export function describeDetectorFeatureGenerator(rawEntry, projectState) {
    const entry = rawEntry && typeof rawEntry === 'object' ? rawEntry : {};
    const generatorType = getGeneratorType(entry.generator_type);
    const target = entry.target && typeof entry.target === 'object' ? entry.target : {};
    const realization = entry.realization && typeof entry.realization === 'object'
        ? entry.realization
        : {};
    const generatedRefs = realization.generated_object_refs && typeof realization.generated_object_refs === 'object'
        ? realization.generated_object_refs
        : {};
    const generatorName = normalizeString(entry.name, 'detector_feature_generator');
    const generatorId = normalizeString(entry.generator_id, 'unknown_generator');
    const status = normalizeString(realization.status, 'spec_only');
    const generatedSolidNames = Array.isArray(generatedRefs.solid_refs)
        ? generatedRefs.solid_refs.map((ref) => resolveObjectName(ref, projectState?.solids || {})).filter(Boolean)
        : [];
    const generatedLogicalVolumeNames = Array.isArray(generatedRefs.logical_volume_refs)
        ? generatedRefs.logical_volume_refs.map((ref) => resolveObjectName(ref, projectState?.logical_volumes || {})).filter(Boolean)
        : [];
    const generatedPlacementNames = Array.isArray(generatedRefs.placement_refs)
        ? generatedRefs.placement_refs.map((ref) => resolveObjectName(ref, projectState?.logical_volumes || {})).filter(Boolean)
        : [];

    if (generatorType === LAYERED_DETECTOR_STACK) {
        const stack = entry.stack && typeof entry.stack === 'object' ? entry.stack : {};
        const stackSize = stack.module_size_mm && typeof stack.module_size_mm === 'object' ? stack.module_size_mm : {};
        const stackOriginOffset = stack.origin_offset_mm && typeof stack.origin_offset_mm === 'object' ? stack.origin_offset_mm : {};
        const layers = entry.layers && typeof entry.layers === 'object' ? entry.layers : {};
        const absorber = layers.absorber && typeof layers.absorber === 'object' ? layers.absorber : {};
        const sensor = layers.sensor && typeof layers.sensor === 'object' ? layers.sensor : {};
        const support = layers.support && typeof layers.support === 'object' ? layers.support : {};
        const moduleCount = Number.isFinite(Number(stack.module_count)) ? Number(stack.module_count) : 0;
        const modulePitch = formatNumber(stack.module_pitch_mm);
        const moduleSizeX = formatNumber(stackSize.x);
        const moduleSizeY = formatNumber(stackSize.y);
        const offsetX = formatNumber(stackOriginOffset.x);
        const offsetY = formatNumber(stackOriginOffset.y);
        const offsetZ = formatNumber(stackOriginOffset.z);
        const parentLogicalVolumeName = resolveObjectName(
            target.parent_logical_volume_ref,
            projectState?.logical_volumes || {},
        ) || 'unknown_parent';
        const layerSummary = [
            `absorber ${formatNumber(absorber.thickness_mm)} mm ${normalizeString(absorber.material_ref, 'unknown')}`,
            `sensor ${formatNumber(sensor.thickness_mm)} mm ${normalizeString(sensor.material_ref, 'unknown')}`,
            `support ${formatNumber(support.thickness_mm)} mm ${normalizeString(support.material_ref, 'unknown')}`,
        ].join(' · ');

        return {
            title: generatorName,
            summary: `Layered stack in ${parentLogicalVolumeName} · ${moduleCount} modules @ ${modulePitch} mm pitch · ${moduleSizeX} x ${moduleSizeY} mm sandwich`,
            statusBadge: status === 'generated' ? 'generated' : 'spec only',
            detailRows: [
                { label: 'Generator ID', value: generatorId },
                { label: 'Status', value: status === 'generated' ? 'Generated geometry is current.' : 'Saved spec only.' },
                { label: 'Parent Logical Volume', value: parentLogicalVolumeName },
                { label: 'Module Layout', value: `${moduleCount} modules @ ${modulePitch} mm pitch` },
                { label: 'Module Size', value: `${moduleSizeX} x ${moduleSizeY} mm` },
                { label: 'Origin Offset', value: `${offsetX}, ${offsetY}, ${offsetZ} mm` },
                { label: 'Layers', value: layerSummary },
                { label: 'Generated Logical Volumes', value: buildListValue(generatedLogicalVolumeNames, 'No generated logical volumes recorded') },
                { label: 'Generated Solids', value: buildListValue(generatedSolidNames, 'No generated solids recorded') },
                { label: 'Generated Placements', value: buildListValue(generatedPlacementNames, 'No generated placements recorded') },
            ],
        };
    }

    if (generatorType === TILED_SENSOR_ARRAY) {
        const array = entry.array && typeof entry.array === 'object' ? entry.array : {};
        const pitch = array.pitch_mm && typeof array.pitch_mm === 'object' ? array.pitch_mm : {};
        const originOffset = array.origin_offset_mm && typeof array.origin_offset_mm === 'object' ? array.origin_offset_mm : {};
        const sensor = entry.sensor && typeof entry.sensor === 'object' ? entry.sensor : {};
        const sensorSize = sensor.size_mm && typeof sensor.size_mm === 'object' ? sensor.size_mm : {};
        const countX = Number.isFinite(Number(array.count_x)) ? Number(array.count_x) : 0;
        const countY = Number.isFinite(Number(array.count_y)) ? Number(array.count_y) : 0;
        const pitchX = formatNumber(pitch.x);
        const pitchY = formatNumber(pitch.y);
        const offsetX = formatNumber(originOffset.x);
        const offsetY = formatNumber(originOffset.y);
        const offsetZ = formatNumber(originOffset.z);
        const sensorSizeX = formatNumber(sensorSize.x);
        const sensorSizeY = formatNumber(sensorSize.y);
        const sensorThickness = formatNumber(sensor.thickness_mm);
        const sensorMaterial = normalizeString(sensor.material_ref, 'unknown');
        const parentLogicalVolumeName = resolveObjectName(
            target.parent_logical_volume_ref,
            projectState?.logical_volumes || {},
        ) || 'unknown_parent';

        return {
            title: generatorName,
            summary: `Tiled sensor array in ${parentLogicalVolumeName} · ${countX} x ${countY} @ ${pitchX} x ${pitchY} mm pitch · ${sensorSizeX} x ${sensorSizeY} x ${sensorThickness} mm ${sensorMaterial}`,
            statusBadge: status === 'generated' ? 'generated' : 'spec only',
            detailRows: [
                { label: 'Generator ID', value: generatorId },
                { label: 'Status', value: status === 'generated' ? 'Generated geometry is current.' : 'Saved spec only.' },
                { label: 'Parent Logical Volume', value: parentLogicalVolumeName },
                { label: 'Array Pattern', value: `${countX} x ${countY} sensors @ ${pitchX} x ${pitchY} mm` },
                { label: 'Origin Offset', value: `${offsetX}, ${offsetY}, ${offsetZ} mm` },
                { label: 'Sensor Cell', value: `${sensorSizeX} x ${sensorSizeY} x ${sensorThickness} mm ${sensorMaterial}` },
                { label: 'Sensitive', value: sensor.is_sensitive === false ? 'No' : 'Yes' },
                { label: 'Generated Logical Volumes', value: buildListValue(generatedLogicalVolumeNames, 'No generated logical volumes recorded') },
                { label: 'Generated Solids', value: buildListValue(generatedSolidNames, 'No generated solids recorded') },
                { label: 'Generated Placements', value: buildListValue(generatedPlacementNames, 'No generated placements recorded') },
            ],
        };
    }

    if (generatorType === SUPPORT_RIB_ARRAY) {
        const array = entry.array && typeof entry.array === 'object' ? entry.array : {};
        const originOffset = array.origin_offset_mm && typeof array.origin_offset_mm === 'object' ? array.origin_offset_mm : {};
        const rib = entry.rib && typeof entry.rib === 'object' ? entry.rib : {};
        const count = Number.isFinite(Number(array.count)) ? Number(array.count) : 0;
        const pitch = formatNumber(array.linear_pitch_mm);
        const axisLabel = formatAxisLabel(array.axis);
        const offsetX = formatNumber(originOffset.x);
        const offsetY = formatNumber(originOffset.y);
        const offsetZ = formatNumber(originOffset.z);
        const ribWidth = formatNumber(rib.width_mm);
        const ribHeight = formatNumber(rib.height_mm);
        const ribMaterial = normalizeString(rib.material_ref, 'unknown');
        const parentLogicalVolumeName = resolveObjectName(
            target.parent_logical_volume_ref,
            projectState?.logical_volumes || {},
        ) || 'unknown_parent';

        return {
            title: generatorName,
            summary: `Support ribs in ${parentLogicalVolumeName} · ${count} ribs across ${axisLabel} @ ${pitch} mm pitch · ${ribWidth} mm wide x ${ribHeight} mm tall ${ribMaterial}`,
            statusBadge: status === 'generated' ? 'generated' : 'spec only',
            detailRows: [
                { label: 'Generator ID', value: generatorId },
                { label: 'Status', value: status === 'generated' ? 'Generated geometry is current.' : 'Saved spec only.' },
                { label: 'Parent Logical Volume', value: parentLogicalVolumeName },
                { label: 'Rib Pattern', value: `${count} ribs across ${axisLabel} @ ${pitch} mm` },
                { label: 'Origin Offset', value: `${offsetX}, ${offsetY}, ${offsetZ} mm` },
                { label: 'Rib Geometry', value: `${ribWidth} mm wide x ${ribHeight} mm tall ${ribMaterial}` },
                { label: 'Sensitive', value: rib.is_sensitive === true ? 'Yes' : 'No' },
                { label: 'Generated Logical Volumes', value: buildListValue(generatedLogicalVolumeNames, 'No generated logical volumes recorded') },
                { label: 'Generated Solids', value: buildListValue(generatedSolidNames, 'No generated solids recorded') },
                { label: 'Generated Placements', value: buildListValue(generatedPlacementNames, 'No generated placements recorded') },
            ],
        };
    }

    if (generatorType === ANNULAR_SHIELD_SLEEVE) {
        const shield = entry.shield && typeof entry.shield === 'object' ? entry.shield : {};
        const originOffset = shield.origin_offset_mm && typeof shield.origin_offset_mm === 'object'
            ? shield.origin_offset_mm
            : {};
        const innerRadius = formatNumber(shield.inner_radius_mm);
        const outerRadius = formatNumber(shield.outer_radius_mm);
        const length = formatNumber(shield.length_mm);
        const material = normalizeString(shield.material_ref, 'unknown');
        const offsetX = formatNumber(originOffset.x);
        const offsetY = formatNumber(originOffset.y);
        const offsetZ = formatNumber(originOffset.z);
        const parentLogicalVolumeName = resolveObjectName(
            target.parent_logical_volume_ref,
            projectState?.logical_volumes || {},
        ) || 'unknown_parent';

        return {
            title: generatorName,
            summary: `Annular shield sleeve in ${parentLogicalVolumeName} · r ${innerRadius} to ${outerRadius} mm x ${length} mm ${material}`,
            statusBadge: status === 'generated' ? 'generated' : 'spec only',
            detailRows: [
                { label: 'Generator ID', value: generatorId },
                { label: 'Status', value: status === 'generated' ? 'Generated geometry is current.' : 'Saved spec only.' },
                { label: 'Parent Logical Volume', value: parentLogicalVolumeName },
                { label: 'Shield Geometry', value: `rmin ${innerRadius} mm, rmax ${outerRadius} mm, length ${length} mm` },
                { label: 'Origin Offset', value: `${offsetX}, ${offsetY}, ${offsetZ} mm` },
                { label: 'Material', value: material },
                { label: 'Generated Logical Volumes', value: buildListValue(generatedLogicalVolumeNames, 'No generated logical volumes recorded') },
                { label: 'Generated Solids', value: buildListValue(generatedSolidNames, 'No generated solids recorded') },
                { label: 'Generated Placements', value: buildListValue(generatedPlacementNames, 'No generated placements recorded') },
            ],
        };
    }

    const targetSolidName = resolveObjectName(target.solid_ref, projectState?.solids || {}) || 'unknown_target';
    const resultSolidName = realization.result_solid_ref
        ? resolveObjectName(realization.result_solid_ref, projectState?.solids || {})
        : '';
    const targetedLogicalVolumeNames = Array.isArray(target.logical_volume_refs) && target.logical_volume_refs.length > 0
        ? target.logical_volume_refs.map((ref) => resolveObjectName(ref, projectState?.logical_volumes || {})).filter(Boolean)
        : (Array.isArray(generatedRefs.logical_volume_refs) && generatedRefs.logical_volume_refs.length > 0
            ? generatedRefs.logical_volume_refs.map((ref) => resolveObjectName(ref, projectState?.logical_volumes || {})).filter(Boolean)
            : getLogicalVolumeNamesForSolid(projectState, targetSolidName));

    if (generatorType === CHANNEL_CUT_ARRAY) {
        const array = entry.array && typeof entry.array === 'object' ? entry.array : {};
        const originOffset = array.origin_offset_mm && typeof array.origin_offset_mm === 'object' ? array.origin_offset_mm : {};
        const channel = entry.channel && typeof entry.channel === 'object' ? entry.channel : {};
        const count = Number.isFinite(Number(array.count)) ? Number(array.count) : 0;
        const pitch = formatNumber(array.linear_pitch_mm);
        const axisLabel = formatAxisLabel(array.axis);
        const offsetX = formatNumber(originOffset.x);
        const offsetY = formatNumber(originOffset.y);
        const channelWidth = formatNumber(channel.width_mm);
        const channelDepth = formatNumber(channel.depth_mm);

        return {
            title: generatorName,
            summary: `Channel cuts on ${targetSolidName} · ${count} channels across ${axisLabel} @ ${pitch} mm pitch · ${channelWidth} mm wide depth ${channelDepth} mm`,
            statusBadge: status === 'generated' ? 'generated' : 'spec only',
            detailRows: [
                { label: 'Generator ID', value: generatorId },
                { label: 'Status', value: status === 'generated' ? 'Generated geometry is current.' : 'Saved spec only.' },
                { label: 'Target Solid', value: targetSolidName },
                { label: 'Target Logical Volumes', value: buildListValue(targetedLogicalVolumeNames, 'All matching logical volumes') },
                { label: 'Channel Pattern', value: `${count} channels across ${axisLabel} @ ${pitch} mm` },
                { label: 'Origin Offset', value: `${offsetX}, ${offsetY} mm` },
                { label: 'Channel Cut', value: `${channelWidth} mm wide, ${channelDepth} mm deep` },
                { label: 'Result Solid', value: resultSolidName || 'Not generated yet' },
                { label: 'Generated Solids', value: buildListValue(generatedSolidNames, 'No generated solids recorded') },
            ],
        };
    }

    const pattern = entry.pattern && typeof entry.pattern === 'object' ? entry.pattern : {};
    const pitch = pattern.pitch_mm && typeof pattern.pitch_mm === 'object' ? pattern.pitch_mm : {};
    const originOffset = pattern.origin_offset_mm && typeof pattern.origin_offset_mm === 'object' ? pattern.origin_offset_mm : {};
    const hole = entry.hole && typeof entry.hole === 'object' ? entry.hole : {};
    const offsetX = formatNumber(originOffset.x);
    const offsetY = formatNumber(originOffset.y);
    const holeDiameter = formatNumber(hole.diameter_mm);
    const holeDepth = formatNumber(hole.depth_mm);

    if (generatorType === CIRCULAR_DRILLED_HOLE_ARRAY) {
        const count = Number.isFinite(Number(pattern.count)) ? Number(pattern.count) : 0;
        const radius = formatNumber(pattern.radius_mm);
        const orientation = formatNumber(pattern.orientation_deg);

        return {
            title: generatorName,
            summary: `Circular drilled holes on ${targetSolidName} · ${count} holes on r ${radius} mm @ ${orientation} deg · dia ${holeDiameter} mm depth ${holeDepth} mm`,
            statusBadge: status === 'generated' ? 'generated' : 'spec only',
            detailRows: [
                { label: 'Generator ID', value: generatorId },
                { label: 'Status', value: status === 'generated' ? 'Generated geometry is current.' : 'Saved spec only.' },
                { label: 'Target Solid', value: targetSolidName },
                { label: 'Target Logical Volumes', value: buildListValue(targetedLogicalVolumeNames, 'All matching logical volumes') },
                { label: 'Pattern', value: `${count} holes on radius ${radius} mm` },
                { label: 'Orientation', value: `${orientation} deg` },
                { label: 'Origin Offset', value: `${offsetX}, ${offsetY} mm` },
                { label: 'Hole', value: `cylindrical dia ${holeDiameter} mm, depth ${holeDepth} mm` },
                { label: 'Result Solid', value: resultSolidName || 'Not generated yet' },
                { label: 'Generated Solids', value: buildListValue(generatedSolidNames, 'No generated solids recorded') },
            ],
        };
    }

    const countX = Number.isFinite(Number(pattern.count_x)) ? Number(pattern.count_x) : 0;
    const countY = Number.isFinite(Number(pattern.count_y)) ? Number(pattern.count_y) : 0;
    const pitchX = formatNumber(pitch.x);
    const pitchY = formatNumber(pitch.y);

    return {
        title: generatorName,
        summary: `Rectangular drilled holes on ${targetSolidName} · ${countX} x ${countY} @ ${pitchX} x ${pitchY} mm · dia ${holeDiameter} mm depth ${holeDepth} mm`,
        statusBadge: status === 'generated' ? 'generated' : 'spec only',
        detailRows: [
            { label: 'Generator ID', value: generatorId },
            { label: 'Status', value: status === 'generated' ? 'Generated geometry is current.' : 'Saved spec only.' },
            { label: 'Target Solid', value: targetSolidName },
            { label: 'Target Logical Volumes', value: buildListValue(targetedLogicalVolumeNames, 'All matching logical volumes') },
            { label: 'Pattern', value: `${countX} x ${countY} holes @ ${pitchX} x ${pitchY} mm` },
            { label: 'Origin Offset', value: `${offsetX}, ${offsetY} mm` },
            { label: 'Hole', value: `cylindrical dia ${holeDiameter} mm, depth ${holeDepth} mm` },
            { label: 'Result Solid', value: resultSolidName || 'Not generated yet' },
            { label: 'Generated Solids', value: buildListValue(generatedSolidNames, 'No generated solids recorded') },
        ],
    };
}
