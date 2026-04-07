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

function normalizeFiniteNumber(rawValue, defaultValue = 0) {
    const parsed = Number(rawValue);
    return Number.isFinite(parsed) ? parsed : defaultValue;
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

export function hasTargetVolume(rawNames, volumeName) {
    const normalizedName = String(volumeName || '').trim();
    if (!normalizedName) {
        return false;
    }
    return normalizeTargetVolumeNames(rawNames).includes(normalizedName);
}

export function setTargetVolumeMembership(rawNames, volumeName, shouldInclude) {
    const normalizedName = String(volumeName || '').trim();
    const normalizedTargets = normalizeTargetVolumeNames(rawNames);

    if (!normalizedName) {
        return normalizedTargets;
    }

    const filteredTargets = normalizedTargets.filter((name) => name !== normalizedName);
    if (!shouldInclude) {
        return filteredTargets;
    }

    return [...filteredTargets, normalizedName];
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

export const REGION_CUTS_AND_LIMITS_OBJECT_TYPE = 'environment';
export const REGION_CUTS_AND_LIMITS_OBJECT_ID = 'region_cuts_and_limits';

export function normalizeRegionCutsAndLimitsState(rawState) {
    const state = rawState && typeof rawState === 'object' ? rawState : {};
    return {
        enabled: normalizeBoolean(state.enabled),
        region_name: typeof state.region_name === 'string' && state.region_name.trim()
            ? state.region_name.trim()
            : 'airpet_region',
        target_volume_names: normalizeTargetVolumeNames(state.target_volume_names),
        production_cut_mm: normalizeFiniteNumber(state.production_cut_mm, 1),
        max_step_mm: normalizeFiniteNumber(state.max_step_mm, 0),
        max_track_length_mm: normalizeFiniteNumber(state.max_track_length_mm, 0),
        max_time_ns: normalizeFiniteNumber(state.max_time_ns, 0),
        min_kinetic_energy_mev: normalizeFiniteNumber(state.min_kinetic_energy_mev, 0),
        min_range_mm: normalizeFiniteNumber(state.min_range_mm, 0),
    };
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

export function formatRegionCutsAndLimitsSummary(state) {
    const regionName = state?.region_name || 'airpet_region';
    const targets = normalizeTargetVolumeNames(state?.target_volume_names);
    const limitParts = [];

    if (Number(state?.production_cut_mm) > 0) {
        limitParts.push(`cut ${Number(state.production_cut_mm)} mm`);
    }
    if (Number(state?.max_step_mm) > 0) {
        limitParts.push(`max step ${Number(state.max_step_mm)} mm`);
    }
    if (Number(state?.max_track_length_mm) > 0) {
        limitParts.push(`max track ${Number(state.max_track_length_mm)} mm`);
    }
    if (Number(state?.max_time_ns) > 0) {
        limitParts.push(`max time ${Number(state.max_time_ns)} ns`);
    }
    if (Number(state?.min_kinetic_energy_mev) > 0) {
        limitParts.push(`min Ek ${Number(state.min_kinetic_energy_mev)} MeV`);
    }
    if (Number(state?.min_range_mm) > 0) {
        limitParts.push(`min range ${Number(state.min_range_mm)} mm`);
    }

    const parts = [`Region cuts and limits: ${state?.enabled ? 'enabled' : 'disabled'} (region ${regionName})`];
    if (targets.length > 0) {
        parts.push(`(targets ${targets.join(', ')})`);
    }
    if (limitParts.length > 0) {
        parts.push(limitParts.join(', '));
    } else {
        parts.push('no user limits');
    }

    return parts.join(' ');
}
