function normalizeString(value, fallback = '') {
    const text = String(value ?? '').trim();
    return text || fallback;
}

function normalizeOffset(rawOffset) {
    const offset = rawOffset && typeof rawOffset === 'object' ? rawOffset : {};
    return {
        x: normalizeString(offset.x, '0'),
        y: normalizeString(offset.y, '0'),
        z: normalizeString(offset.z, '0'),
    };
}

function normalizeCadImportRecord(rawRecord) {
    const record = rawRecord && typeof rawRecord === 'object' ? rawRecord : {};
    const source = record.source && typeof record.source === 'object' ? record.source : {};
    const options = record.options && typeof record.options === 'object' ? record.options : {};
    const createdObjectIds = record.created_object_ids && typeof record.created_object_ids === 'object'
        ? record.created_object_ids
        : {};
    const createdGroupNames = record.created_group_names && typeof record.created_group_names === 'object'
        ? record.created_group_names
        : {};

    const solidIds = Array.isArray(createdObjectIds.solid_ids) ? createdObjectIds.solid_ids.filter(Boolean) : [];
    const logicalVolumeIds = Array.isArray(createdObjectIds.logical_volume_ids) ? createdObjectIds.logical_volume_ids.filter(Boolean) : [];
    const assemblyIds = Array.isArray(createdObjectIds.assembly_ids) ? createdObjectIds.assembly_ids.filter(Boolean) : [];
    const placementIds = Array.isArray(createdObjectIds.placement_ids) ? createdObjectIds.placement_ids.filter(Boolean) : [];
    const topLevelPlacementIds = Array.isArray(createdObjectIds.top_level_placement_ids)
        ? createdObjectIds.top_level_placement_ids.filter(Boolean)
        : [];
    const normalizedTopLevelPlacementIds = topLevelPlacementIds.length > 0
        ? topLevelPlacementIds
        : placementIds.slice(0, 1);

    const groupingName = normalizeString(
        options.grouping_name ?? options.groupingName,
        normalizeString(source.filename, '')
    );
    const placementMode = normalizeString(options.placement_mode ?? options.placementMode, 'assembly');
    const parentLvName = normalizeString(options.parent_lv_name ?? options.parentLVName, 'World');
    const sha256 = normalizeString(source.sha256, 'unknown');
    const shortSha256 = sha256.length > 12 ? `${sha256.slice(0, 12)}...` : sha256;

    return {
        import_id: normalizeString(record.import_id, 'unknown'),
        source: {
            format: normalizeString(source.format, 'step'),
            filename: normalizeString(source.filename, 'unknown.step'),
            sha256,
            short_sha256: shortSha256,
            size_bytes: Number.isFinite(Number(source.size_bytes)) ? Number(source.size_bytes) : 0,
        },
        options: {
            grouping_name: groupingName,
            placement_mode: placementMode,
            parent_lv_name: parentLvName,
            offset: normalizeOffset(options.offset),
            smart_import_enabled: Boolean(options.smart_import_enabled ?? options.smartImport),
        },
        created_object_ids: {
            solid_ids: solidIds,
            logical_volume_ids: logicalVolumeIds,
            assembly_ids: assemblyIds,
            placement_ids: placementIds,
            top_level_placement_ids: normalizedTopLevelPlacementIds,
        },
        created_group_names: {
            solid: normalizeString(createdGroupNames.solid, ''),
            logical_volume: normalizeString(createdGroupNames.logical_volume, ''),
            assembly: normalizeString(createdGroupNames.assembly, ''),
        },
    };
}

function formatCount(count, noun) {
    return `${count} ${noun}${count === 1 ? '' : 's'}`;
}

function formatCreatedObjectSummary(record) {
    const parts = [];
    const { solid_ids: solidIds, logical_volume_ids: logicalVolumeIds, assembly_ids: assemblyIds, placement_ids: placementIds } = record.created_object_ids;

    if (solidIds.length > 0) parts.push(formatCount(solidIds.length, 'solid'));
    if (logicalVolumeIds.length > 0) parts.push(formatCount(logicalVolumeIds.length, 'logical volume'));
    if (assemblyIds.length > 0) parts.push(formatCount(assemblyIds.length, 'assembly'));
    if (placementIds.length > 0) parts.push(formatCount(placementIds.length, 'placement'));

    return parts.length > 0 ? parts.join(', ') : 'No imported object ids recorded.';
}

function formatCreatedGroupSummary(record) {
    const groupNames = [
        record.created_group_names.solid,
        record.created_group_names.logical_volume,
        record.created_group_names.assembly,
    ].filter(Boolean);

    return groupNames.length > 0 ? groupNames.join(', ') : 'No created groups recorded.';
}

function buildSelectionContextFromRecord(record) {
    const selectionIds = record.created_object_ids.top_level_placement_ids;
    return {
        selectionIds,
        selectionSummary: selectionIds.length > 0
            ? formatCount(selectionIds.length, 'top-level placement')
            : 'No top-level placements recorded.',
    };
}

function getPlacementModeLabel(placementMode) {
    return placementMode === 'individual' ? 'individual' : 'assembly';
}

export function buildCadImportBatchContext(rawRecord) {
    const record = normalizeCadImportRecord(rawRecord);
    const logicalVolumeIds = record.created_object_ids.logical_volume_ids;

    return {
        logicalVolumeIds,
        logicalVolumeCount: logicalVolumeIds.length,
        logicalVolumeSummary: logicalVolumeIds.length > 0
            ? formatCount(logicalVolumeIds.length, 'logical volume')
            : 'No imported logical volumes recorded.',
        hasLogicalVolumes: logicalVolumeIds.length > 0,
    };
}

export function buildCadImportReimportContext(rawRecord) {
    const record = normalizeCadImportRecord(rawRecord);
    const sourceLabel = `${record.source.filename} (${record.import_id})`;

    return {
        reimportTargetImportId: record.import_id,
        groupingName: record.options.grouping_name,
        placementMode: getPlacementModeLabel(record.options.placement_mode),
        parentLVName: record.options.parent_lv_name === 'World' ? 'World' : record.options.parent_lv_name,
        offset: { ...record.options.offset },
        smartImport: record.options.smart_import_enabled,
        sourceLabel,
        noticeText: `Reimport target: ${sourceLabel}. Supported annotations will be preserved where the backend can match them.`,
    };
}

export function buildCadImportSelectionContext(rawRecord) {
    return buildSelectionContextFromRecord(normalizeCadImportRecord(rawRecord));
}

export function describeCadImportRecord(rawRecord) {
    const record = normalizeCadImportRecord(rawRecord);
    const createdObjectSummary = formatCreatedObjectSummary(record);
    const createdGroupSummary = formatCreatedGroupSummary(record);
    const selectionContext = buildSelectionContextFromRecord(record);
    const batchContext = buildCadImportBatchContext(record);
    const placementMode = getPlacementModeLabel(record.options.placement_mode);
    const sourceLabel = `${record.source.filename} (${record.import_id})`;
    const summary = `STEP import from ${record.source.filename} · placement mode: ${placementMode} · smart CAD ${record.options.smart_import_enabled ? 'on' : 'off'}`;

    return {
        title: record.options.grouping_name || record.source.filename || record.import_id,
        summary,
        detailRows: [
            { label: 'Import ID', value: record.import_id },
            { label: 'Source File', value: record.source.filename },
            { label: 'Source SHA256', value: { text: record.source.short_sha256, title: record.source.sha256 } },
            { label: 'Grouping Name', value: record.options.grouping_name },
            { label: 'Placement Mode', value: placementMode },
            { label: 'Parent LV', value: record.options.parent_lv_name },
            {
                label: 'Placement Offset',
                value: `x=${record.options.offset.x}, y=${record.options.offset.y}, z=${record.options.offset.z}`,
            },
            { label: 'Smart CAD', value: record.options.smart_import_enabled ? 'Enabled' : 'Disabled' },
            { label: 'Created Objects', value: createdObjectSummary },
            { label: 'Created Groups', value: createdGroupSummary },
            { label: 'Imported Logical Volumes', value: batchContext.logicalVolumeSummary },
            { label: 'Top-Level Selection', value: selectionContext.selectionSummary },
        ],
        createdObjectSummary,
        createdGroupSummary,
        selectionContext,
        batchContext,
        reimportContext: {
            ...buildCadImportReimportContext(record),
            sourceLabel,
        },
    };
}
