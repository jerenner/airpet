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

function normalizeReimportDiffPart(rawPart) {
    const part = rawPart && typeof rawPart === 'object' ? rawPart : {};

    return {
        kind: normalizeString(part.kind, 'logical_volume'),
        name: normalizeString(part.name, 'unknown'),
        signature: normalizeString(part.signature, ''),
        before_name: normalizeString(part.before_name, ''),
        after_name: normalizeString(part.after_name, ''),
        before_signature: normalizeString(part.before_signature, ''),
        after_signature: normalizeString(part.after_signature, ''),
    };
}

function normalizeReimportCleanupPolicy(rawPolicy) {
    const policy = rawPolicy && typeof rawPolicy === 'object' ? rawPolicy : {};

    return {
        replacement_mode: normalizeString(policy.replacement_mode, 'replace_in_place'),
        obsolete_part_action: normalizeString(policy.obsolete_part_action, 'remove'),
        removed_count: Number.isFinite(Number(policy.removed_count)) ? Number(policy.removed_count) : 0,
        summary_text: normalizeString(
            policy.summary_text,
            'Supported STEP reimport replaces the target import in place and removes obsolete imported parts.',
        ),
    };
}

function normalizeReimportDiffSummary(rawSummary) {
    const summary = rawSummary && typeof rawSummary === 'object' ? rawSummary : {};
    const counts = summary.summary && typeof summary.summary === 'object' ? summary.summary : {};
    const normalizedSummary = {
        total_before: Number.isFinite(Number(counts.total_before)) ? Number(counts.total_before) : 0,
        total_after: Number.isFinite(Number(counts.total_after)) ? Number(counts.total_after) : 0,
        unchanged_count: Number.isFinite(Number(counts.unchanged_count)) ? Number(counts.unchanged_count) : 0,
        added_count: Number.isFinite(Number(counts.added_count)) ? Number(counts.added_count) : 0,
        removed_count: Number.isFinite(Number(counts.removed_count)) ? Number(counts.removed_count) : 0,
        renamed_count: Number.isFinite(Number(counts.renamed_count)) ? Number(counts.renamed_count) : 0,
        changed_count: Number.isFinite(Number(counts.changed_count)) ? Number(counts.changed_count) : 0,
    };

    const addedParts = Array.isArray(summary.added_parts) ? summary.added_parts.map(normalizeReimportDiffPart) : [];
    const removedParts = Array.isArray(summary.removed_parts) ? summary.removed_parts.map(normalizeReimportDiffPart) : [];
    const renamedParts = Array.isArray(summary.renamed_parts) ? summary.renamed_parts.map(normalizeReimportDiffPart) : [];
    const changedParts = Array.isArray(summary.changed_parts) ? summary.changed_parts.map(normalizeReimportDiffPart) : [];
    const cleanupPolicy = summary.cleanup_policy && typeof summary.cleanup_policy === 'object'
        ? normalizeReimportCleanupPolicy(summary.cleanup_policy)
        : null;

    return {
        summary: normalizedSummary,
        summary_text: formatReimportDiffSummaryText(normalizedSummary),
        cleanup_policy: cleanupPolicy,
        added_parts: addedParts,
        removed_parts: removedParts,
        renamed_parts: renamedParts,
        changed_parts: changedParts,
    };
}

function normalizeCountMap(rawCounts) {
    const counts = rawCounts && typeof rawCounts === 'object' ? rawCounts : {};
    const normalized = {};

    Object.entries(counts).forEach(([key, value]) => {
        const count = Number(value);
        if (Number.isFinite(count) && count > 0) {
            normalized[String(key)] = count;
        }
    });

    return normalized;
}

function formatSmartImportSummaryText(primitiveCount, tessellatedCount) {
    return `${primitiveCount} primitive candidates, ${tessellatedCount} tessellated fallbacks`;
}

function normalizeSmartImportSummary(rawSummary) {
    const summaryRecord = rawSummary && typeof rawSummary === 'object' ? rawSummary : {};
    const reportSummary = summaryRecord.summary && typeof summaryRecord.summary === 'object'
        ? summaryRecord.summary
        : {};

    const total = Number.isFinite(Number(reportSummary.total)) ? Number(reportSummary.total) : 0;
    const primitiveCount = Number.isFinite(Number(reportSummary.primitive_count)) ? Number(reportSummary.primitive_count) : 0;
    const tessellatedCount = Number.isFinite(Number(reportSummary.tessellated_count)) ? Number(reportSummary.tessellated_count) : 0;
    const primitiveRatio = Number.isFinite(Number(reportSummary.primitive_ratio))
        ? Number(reportSummary.primitive_ratio)
        : (total > 0 ? primitiveCount / total : 0);
    const selectedModeCountsRaw = reportSummary.selected_mode_counts && typeof reportSummary.selected_mode_counts === 'object'
        ? reportSummary.selected_mode_counts
        : {};
    const selectedPrimitiveCount = Number.isFinite(Number(selectedModeCountsRaw.primitive)) ? Number(selectedModeCountsRaw.primitive) : 0;
    const selectedTessellatedCount = Number.isFinite(Number(selectedModeCountsRaw.tessellated)) ? Number(selectedModeCountsRaw.tessellated) : 0;
    const selectedPrimitiveRatio = Number.isFinite(Number(reportSummary.selected_primitive_ratio))
        ? Number(reportSummary.selected_primitive_ratio)
        : (total > 0 ? selectedPrimitiveCount / total : 0);

    const countsByClassification = normalizeCountMap(reportSummary.counts_by_classification);
    const fallbackReasonCounts = normalizeCountMap(summaryRecord.fallback_reason_counts);

    let topFallbackReasons = Array.isArray(summaryRecord.top_fallback_reasons)
        ? summaryRecord.top_fallback_reasons
            .filter((entry) => entry && typeof entry === 'object')
            .map((entry) => ({
                reason: normalizeString(entry.reason, 'no_primitive_match_v1'),
                count: Number.isFinite(Number(entry.count)) ? Number(entry.count) : 0,
            }))
            .filter((entry) => entry.reason && entry.count > 0)
        : [];

    if (topFallbackReasons.length === 0) {
        topFallbackReasons = Object.entries(fallbackReasonCounts)
            .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
            .map(([reason, count]) => ({ reason, count }));
    }

    const summaryText = normalizeString(
        summaryRecord.summary_text,
        formatSmartImportSummaryText(primitiveCount, selectedTessellatedCount),
    );

    return {
        enabled: Boolean(summaryRecord.enabled),
        summary: {
            total,
            primitive_count: primitiveCount,
            tessellated_count: tessellatedCount,
            primitive_ratio: primitiveRatio,
            selected_mode_counts: {
                primitive: selectedPrimitiveCount,
                tessellated: selectedTessellatedCount,
            },
            selected_primitive_ratio: selectedPrimitiveRatio,
            counts_by_classification: countsByClassification,
        },
        summary_text: summaryText,
        primitive_count: primitiveCount,
        selected_primitive_count: selectedPrimitiveCount,
        selected_tessellated_count: selectedTessellatedCount,
        fallback_reason_counts: fallbackReasonCounts,
        top_fallback_reasons: topFallbackReasons,
    };
}

function formatSmartImportSummaryTitle(summary) {
    const reportSummary = summary?.summary || {};
    const total = Number.isFinite(Number(reportSummary.total)) ? Number(reportSummary.total) : 0;
    const primitiveCount = Number.isFinite(Number(reportSummary.primitive_count)) ? Number(reportSummary.primitive_count) : 0;
    const selectedPrimitiveCount = Number.isFinite(Number(summary?.selected_primitive_count)) ? Number(summary.selected_primitive_count) : 0;
    const selectedTessellatedCount = Number.isFinite(Number(summary?.selected_tessellated_count)) ? Number(summary.selected_tessellated_count) : 0;
    const topFallbackReasons = Array.isArray(summary?.top_fallback_reasons) ? summary.top_fallback_reasons : [];

    const lines = [
        `Total solids: ${total}`,
        `Primitive candidates: ${primitiveCount}`,
        `Selected primitive: ${selectedPrimitiveCount}`,
        `Selected tessellated fallback: ${selectedTessellatedCount}`,
    ];

    if (topFallbackReasons.length > 0) {
        const reasonText = topFallbackReasons
            .slice(0, 3)
            .map((entry) => `${entry.reason} x${entry.count}`)
            .join(', ');
        lines.push(`Top fallback reasons: ${reasonText}`);
    }

    return lines.join('\n');
}

function formatReimportDiffSummaryText(summary) {
    const normalizedSummary = summary && typeof summary === 'object' ? summary : {};
    const counts = [
        ['added_count', 'added'],
        ['removed_count', 'removed'],
        ['renamed_count', 'renamed'],
        ['changed_count', 'changed'],
    ]
        .map(([key, label]) => {
            const count = Number.isFinite(Number(normalizedSummary[key])) ? Number(normalizedSummary[key]) : 0;
            return count > 0 ? `${count} ${label}` : '';
        })
        .filter(Boolean);

    if (counts.length === 0) {
        return 'No part-level changes recorded.';
    }

    return `Part changes: ${counts.join(', ')}.`;
}

function formatReimportDiffPartList(parts) {
    const normalizedParts = Array.isArray(parts) ? parts.filter((part) => part && typeof part === 'object') : [];
    if (normalizedParts.length === 0) {
        return { text: 'None', title: 'No parts in this category.' };
    }

    const lines = normalizedParts.map((part) => {
        if (part.before_name && part.after_name) {
            return `${part.before_name} -> ${part.after_name}`;
        }
        return `${part.name}${part.signature ? ` (${part.signature.slice(0, 12)}...)` : ''}`;
    });

    const preview = lines.slice(0, 4).join(', ');
    const text = lines.length > 4 ? `${preview}, +${lines.length - 4} more` : preview;

    return {
        text,
        title: lines.join('\n'),
    };
}

function formatReimportCleanupPolicyTitle(policy) {
    const normalizedPolicy = policy && typeof policy === 'object' ? policy : {};
    const replacementMode = normalizeString(normalizedPolicy.replacement_mode, 'replace_in_place').replace(/_/g, ' ');
    const obsoletePartAction = normalizeString(normalizedPolicy.obsolete_part_action, 'remove');
    const removedCount = Number.isFinite(Number(normalizedPolicy.removed_count))
        ? Number(normalizedPolicy.removed_count)
        : 0;

    return [
        `Replacement mode: ${replacementMode}`,
        `Obsolete parts action: ${obsoletePartAction}`,
        `Obsolete parts removed: ${removedCount}`,
    ].join('\n');
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
    const reimportDiffSummary = record.reimport_diff_summary && typeof record.reimport_diff_summary === 'object'
        ? normalizeReimportDiffSummary(record.reimport_diff_summary)
        : null;
    const smartImportSummary = record.smart_import_summary && typeof record.smart_import_summary === 'object'
        ? normalizeSmartImportSummary(record.smart_import_summary)
        : null;

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
        smart_import_summary: smartImportSummary,
        reimport_diff_summary: reimportDiffSummary,
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
        noticeText: `Reimport target: ${sourceLabel}. Supported annotations will be preserved where the backend can match them. Obsolete imported parts will be removed if the revised STEP drops them.`,
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
    const actionLabel = record.reimport_diff_summary ? 'reimport' : 'import';
    const smartImportSummaryText = record.smart_import_summary?.summary_text || '';
    const summaryParts = [
        `STEP ${actionLabel} from ${record.source.filename}`,
        `placement mode: ${placementMode}`,
        `smart CAD ${record.options.smart_import_enabled ? 'on' : 'off'}`,
    ];
    if (smartImportSummaryText) {
        summaryParts.push(smartImportSummaryText);
    }
    const summary = summaryParts.join(' · ');

    const detailRows = [
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
        record.smart_import_summary ? {
            label: 'Smart CAD Outcome',
            value: {
                text: record.smart_import_summary.summary_text,
                title: formatSmartImportSummaryTitle(record.smart_import_summary),
            },
        } : null,
        { label: 'Created Objects', value: createdObjectSummary },
        { label: 'Created Groups', value: createdGroupSummary },
        { label: 'Imported Logical Volumes', value: batchContext.logicalVolumeSummary },
        { label: 'Top-Level Selection', value: selectionContext.selectionSummary },
    ].filter(Boolean);

    if (record.reimport_diff_summary) {
        detailRows.push({
            label: 'Reimport Diff',
            value: record.reimport_diff_summary.summary_text,
        });

        if (record.reimport_diff_summary.cleanup_policy) {
            detailRows.push({
                label: 'Reimport Cleanup',
                value: {
                    text: record.reimport_diff_summary.cleanup_policy.summary_text,
                    title: formatReimportCleanupPolicyTitle(record.reimport_diff_summary.cleanup_policy),
                },
            });
        }

        const addedParts = formatReimportDiffPartList(record.reimport_diff_summary.added_parts);
        const removedParts = formatReimportDiffPartList(record.reimport_diff_summary.removed_parts);
        const renamedParts = formatReimportDiffPartList(record.reimport_diff_summary.renamed_parts);
        const changedParts = formatReimportDiffPartList(record.reimport_diff_summary.changed_parts);

        if (record.reimport_diff_summary.added_parts.length > 0) {
            detailRows.push({ label: 'Added Parts', value: addedParts });
        }
        if (record.reimport_diff_summary.removed_parts.length > 0) {
            detailRows.push({ label: 'Removed Parts', value: removedParts });
        }
        if (record.reimport_diff_summary.renamed_parts.length > 0) {
            detailRows.push({ label: 'Renamed Parts', value: renamedParts });
        }
        if (record.reimport_diff_summary.changed_parts.length > 0) {
            detailRows.push({ label: 'Changed Parts', value: changedParts });
        }
    }

    return {
        title: record.options.grouping_name || record.source.filename || record.import_id,
        summary,
        detailRows,
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
