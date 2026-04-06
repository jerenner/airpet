const DEFAULT_FIELD_VECTOR = Object.freeze({ x: 0, y: 0, z: 0 });
const GLOBAL_FIELD_AXES = Object.freeze(['x', 'y', 'z']);

export const GLOBAL_UNIFORM_MAGNETIC_FIELD_OBJECT_TYPE = 'environment';
export const GLOBAL_UNIFORM_MAGNETIC_FIELD_OBJECT_ID = 'global_uniform_magnetic_field';
export const GLOBAL_UNIFORM_MAGNETIC_FIELD_VECTOR_AXES = GLOBAL_FIELD_AXES;

function normalizeBoolean(value) {
    if (value === true || value === false) {
        return value;
    }

    if (typeof value === 'string') {
        const normalized = value.trim().toLowerCase();
        if (['true', '1', 'yes', 'on'].includes(normalized)) return true;
        if (['false', '0', 'no', 'off', ''].includes(normalized)) return false;
    }

    return Boolean(value);
}

function normalizeFiniteNumber(value) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : 0;
}

export function normalizeGlobalMagneticFieldState(rawField = null) {
    const field = rawField && typeof rawField === 'object' ? rawField : {};
    const vector = field.field_vector_tesla && typeof field.field_vector_tesla === 'object'
        ? field.field_vector_tesla
        : {};

    return {
        enabled: normalizeBoolean(field.enabled),
        field_vector_tesla: {
            x: normalizeFiniteNumber(vector.x ?? DEFAULT_FIELD_VECTOR.x),
            y: normalizeFiniteNumber(vector.y ?? DEFAULT_FIELD_VECTOR.y),
            z: normalizeFiniteNumber(vector.z ?? DEFAULT_FIELD_VECTOR.z),
        },
    };
}

export function formatGlobalMagneticFieldComponent(value) {
    return String(normalizeFiniteNumber(value));
}

export function formatGlobalMagneticFieldSummary(rawField = null) {
    const field = normalizeGlobalMagneticFieldState(rawField);
    const status = field.enabled ? 'enabled' : 'disabled';
    const vector = field.field_vector_tesla;
    return `Global magnetic field: ${status} (${formatGlobalMagneticFieldComponent(vector.x)}, ${formatGlobalMagneticFieldComponent(vector.y)}, ${formatGlobalMagneticFieldComponent(vector.z)}) T`;
}
