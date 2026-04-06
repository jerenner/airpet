const FIELD_VECTOR_AXES = ['x', 'y', 'z'];

function normalizeBoolean(rawValue) {
    if (typeof rawValue === 'boolean') {
        return rawValue;
    }

    if (typeof rawValue === 'string') {
        const normalized = rawValue.trim().toLowerCase();
        if (['true', '1', 'yes', 'on'].includes(normalized)) {
            return true;
        }
        if (['false', '0', 'no', 'off'].includes(normalized)) {
            return false;
        }
    }

    return Boolean(rawValue);
}

function normalizeFieldVector(rawVector) {
    const normalized = { x: 0, y: 0, z: 0 };

    if (!rawVector || typeof rawVector !== 'object') {
        return normalized;
    }

    for (const axis of FIELD_VECTOR_AXES) {
        const parsed = Number(rawVector[axis]);
        normalized[axis] = Number.isFinite(parsed) ? parsed : 0;
    }

    return normalized;
}

export function normalizeTargetVolumeNames(rawNames) {
    if (rawNames == null) {
        return [];
    }

    const source = typeof rawNames === 'string'
        ? rawNames.split(/[,;\n]+/)
        : Array.isArray(rawNames)
            ? rawNames
            : [];

    const normalized = [];
    const seen = new Set();

    for (const rawName of source) {
        const name = String(rawName).trim();
        if (!name || seen.has(name)) {
            continue;
        }
        seen.add(name);
        normalized.push(name);
    }

    return normalized;
}

function normalizeFieldState(rawState, { includeTargets, vectorKey }) {
    const state = rawState && typeof rawState === 'object' ? rawState : {};
    const rawVector = state[vectorKey] ?? state.field_vector_tesla ?? state.field_vector_volt_per_meter;
    const normalized = {
        enabled: normalizeBoolean(state.enabled),
        [vectorKey]: normalizeFieldVector(rawVector),
    };

    if (includeTargets) {
        normalized.target_volume_names = normalizeTargetVolumeNames(state.target_volume_names);
    }

    return normalized;
}

function formatVectorSummary(vector) {
    return `(${FIELD_VECTOR_AXES.map((axis) => String(vector?.[axis] ?? 0)).join(', ')})`;
}

function formatFieldSummary(label, state, unit, { includeTargets, vectorKey }) {
    const status = state?.enabled ? 'enabled' : 'disabled';
    const parts = [`${label}: ${status}`];

    if (includeTargets) {
        const targets = normalizeTargetVolumeNames(state?.target_volume_names);
        if (targets.length > 0) {
            parts.push(`(targets ${targets.join(', ')})`);
        }
    }

    const rawVector = state?.[vectorKey] ?? state?.field_vector_tesla ?? state?.field_vector_volt_per_meter;
    parts.push(`${formatVectorSummary(rawVector)} ${unit}`);
    return parts.join(' ');
}

export const GLOBAL_UNIFORM_MAGNETIC_FIELD_OBJECT_TYPE = 'environment';
export const GLOBAL_UNIFORM_MAGNETIC_FIELD_OBJECT_ID = 'global_uniform_magnetic_field';
export const GLOBAL_UNIFORM_MAGNETIC_FIELD_VECTOR_AXES = FIELD_VECTOR_AXES;

export const GLOBAL_UNIFORM_ELECTRIC_FIELD_OBJECT_TYPE = 'environment';
export const GLOBAL_UNIFORM_ELECTRIC_FIELD_OBJECT_ID = 'global_uniform_electric_field';
export const GLOBAL_UNIFORM_ELECTRIC_FIELD_VECTOR_AXES = FIELD_VECTOR_AXES;

export const LOCAL_UNIFORM_MAGNETIC_FIELD_OBJECT_TYPE = 'environment';
export const LOCAL_UNIFORM_MAGNETIC_FIELD_OBJECT_ID = 'local_uniform_magnetic_field';
export const LOCAL_UNIFORM_MAGNETIC_FIELD_VECTOR_AXES = FIELD_VECTOR_AXES;

export const LOCAL_UNIFORM_ELECTRIC_FIELD_OBJECT_TYPE = 'environment';
export const LOCAL_UNIFORM_ELECTRIC_FIELD_OBJECT_ID = 'local_uniform_electric_field';
export const LOCAL_UNIFORM_ELECTRIC_FIELD_VECTOR_AXES = FIELD_VECTOR_AXES;

export function normalizeGlobalMagneticFieldState(rawState) {
    return normalizeFieldState(rawState, {
        includeTargets: false,
        vectorKey: 'field_vector_tesla',
    });
}

export function normalizeGlobalElectricFieldState(rawState) {
    return normalizeFieldState(rawState, {
        includeTargets: false,
        vectorKey: 'field_vector_volt_per_meter',
    });
}

export function normalizeLocalMagneticFieldState(rawState) {
    return normalizeFieldState(rawState, {
        includeTargets: true,
        vectorKey: 'field_vector_tesla',
    });
}

export function normalizeLocalElectricFieldState(rawState) {
    return normalizeFieldState(rawState, {
        includeTargets: true,
        vectorKey: 'field_vector_volt_per_meter',
    });
}

export function formatGlobalMagneticFieldSummary(state) {
    return formatFieldSummary('Global magnetic field', state, 'T', {
        includeTargets: false,
        vectorKey: 'field_vector_tesla',
    });
}

export function formatGlobalElectricFieldSummary(state) {
    return formatFieldSummary('Global electric field', state, 'V/m', {
        includeTargets: false,
        vectorKey: 'field_vector_volt_per_meter',
    });
}

export function formatLocalMagneticFieldSummary(state) {
    return formatFieldSummary('Local magnetic field', state, 'T', {
        includeTargets: true,
        vectorKey: 'field_vector_tesla',
    });
}

export function formatLocalElectricFieldSummary(state) {
    return formatFieldSummary('Local electric field', state, 'V/m', {
        includeTargets: true,
        vectorKey: 'field_vector_volt_per_meter',
    });
}
