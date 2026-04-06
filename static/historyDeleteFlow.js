export function normalizeHistoryDeleteSelection(selection) {
    const versionIds = [...new Set((selection?.versionIds || []).filter(Boolean))];
    const selectedVersionIds = new Set(versionIds);
    const runs = [...new Map(
        (selection?.runs || [])
            .filter((item) => item && item.versionId && item.runId)
            .filter((item) => !selectedVersionIds.has(item.versionId))
            .map((item) => [`${item.versionId}::${item.runId}`, {
                versionId: item.versionId,
                runId: item.runId,
            }])
    ).values()];

    return {
        versionIds,
        runs,
        versionCount: versionIds.length,
        runCount: runs.length,
    };
}

export function buildHistoryDeleteConfirmationMessage(selection) {
    const normalizedSelection =
        selection && typeof selection.versionCount === 'number' && typeof selection.runCount === 'number'
            ? selection
            : normalizeHistoryDeleteSelection(selection);

    const parts = [];
    if (normalizedSelection.versionCount > 0) {
        parts.push(`${normalizedSelection.versionCount} version${normalizedSelection.versionCount === 1 ? '' : 's'}`);
    }
    if (normalizedSelection.runCount > 0) {
        parts.push(`${normalizedSelection.runCount} run${normalizedSelection.runCount === 1 ? '' : 's'}`);
    }

    return parts.length > 0 ? `Delete ${parts.join(' and ')}? This cannot be undone.` : '';
}
