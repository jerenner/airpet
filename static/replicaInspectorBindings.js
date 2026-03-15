const DEFAULT_REPLICA_EXPRESSION_BY_FIELD = Object.freeze({
    number: '1',
    width: '0',
    offset: '0',
});

export const REPLICA_INSPECTOR_EDITABLE_FIELDS = Object.freeze([
    Object.freeze({ key: 'number', label: 'Number:', propertyPath: 'content.number' }),
    Object.freeze({ key: 'width', label: 'Width:', propertyPath: 'content.width' }),
    Object.freeze({ key: 'offset', label: 'Offset:', propertyPath: 'content.offset' }),
]);

const REPLICA_INSPECTOR_EDITABLE_PATHS = new Set(
    REPLICA_INSPECTOR_EDITABLE_FIELDS.map((field) => field.propertyPath)
);

export function toReplicaExpressionString(value, fallbackValue = '') {
    if (value === null || value === undefined) {
        return fallbackValue;
    }
    return String(value);
}

export function getReplicaInspectorEditableFieldSpecs(replicaContent = {}) {
    return REPLICA_INSPECTOR_EDITABLE_FIELDS.map((field) => ({
        ...field,
        value: toReplicaExpressionString(
            replicaContent[field.key],
            DEFAULT_REPLICA_EXPRESSION_BY_FIELD[field.key]
        ),
    }));
}

export function buildReplicaInspectorPropertyUpdateArgs(logicalVolumeId, propertyPath, expressionValue) {
    const objectId = toReplicaExpressionString(logicalVolumeId).trim();
    if (!objectId) {
        throw new Error('logicalVolumeId must be a non-empty string.');
    }

    if (!REPLICA_INSPECTOR_EDITABLE_PATHS.has(propertyPath)) {
        throw new Error(`Unsupported replica inspector property path: ${propertyPath}`);
    }

    return {
        objectType: 'logical_volume',
        objectId,
        propertyPath,
        newValue: toReplicaExpressionString(expressionValue),
    };
}
