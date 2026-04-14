function normalizeSolidRegistry(rawRegistry) {
    return rawRegistry && typeof rawRegistry === 'object' ? rawRegistry : {};
}

export function mergeProjectStateWithExclusions(currentProjectState, incomingProjectState, excludedSolidNames = []) {
    const incomingState = incomingProjectState && typeof incomingProjectState === 'object'
        ? incomingProjectState
        : {};
    const incomingSolids = normalizeSolidRegistry(incomingState.solids);
    const currentSolids = normalizeSolidRegistry(currentProjectState?.solids);
    const excludedNames = new Set(
        Array.isArray(excludedSolidNames)
            ? excludedSolidNames.map((name) => String(name || '').trim()).filter(Boolean)
            : []
    );

    const preservedSolids = {};
    excludedNames.forEach((solidName) => {
        if (
            Object.prototype.hasOwnProperty.call(currentSolids, solidName)
            && !Object.prototype.hasOwnProperty.call(incomingSolids, solidName)
        ) {
            preservedSolids[solidName] = currentSolids[solidName];
        }
    });

    return {
        ...incomingState,
        solids: {
            ...preservedSolids,
            ...incomingSolids,
        },
    };
}
