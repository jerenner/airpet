const DEFAULT_DIVISION_EXPRESSION_BY_FIELD = Object.freeze({
    number: '1',
    width: '0',
    offset: '0',
});

export const DIVISION_INSPECTOR_EDITABLE_FIELDS = Object.freeze([
    Object.freeze({ key: 'number', label: 'Number:', propertyPath: 'content.number' }),
    Object.freeze({ key: 'width', label: 'Width:', propertyPath: 'content.width' }),
    Object.freeze({ key: 'offset', label: 'Offset:', propertyPath: 'content.offset' }),
]);

const DIVISION_INSPECTOR_EDITABLE_PATHS = new Set(
    DIVISION_INSPECTOR_EDITABLE_FIELDS.map((field) => field.propertyPath)
);

export function toDivisionExpressionString(value, fallbackValue = '') {
    if (value === null || value === undefined) {
        return fallbackValue;
    }
    return String(value);
}

export function getDivisionInspectorEditableFieldSpecs(divisionContent = {}) {
    return DIVISION_INSPECTOR_EDITABLE_FIELDS.map((field) => ({
        ...field,
        value: toDivisionExpressionString(
            divisionContent[field.key],
            DEFAULT_DIVISION_EXPRESSION_BY_FIELD[field.key]
        ),
    }));
}

export function buildDivisionInspectorPropertyUpdateArgs(logicalVolumeId, propertyPath, expressionValue) {
    const objectId = toDivisionExpressionString(logicalVolumeId).trim();
    if (!objectId) {
        throw new Error('logicalVolumeId must be a non-empty string.');
    }

    if (!DIVISION_INSPECTOR_EDITABLE_PATHS.has(propertyPath)) {
        throw new Error(`Unsupported division inspector property path: ${propertyPath}`);
    }

    return {
        objectType: 'logical_volume',
        objectId,
        propertyPath,
        newValue: toDivisionExpressionString(expressionValue),
    };
}
