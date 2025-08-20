// static/interactionManager.js
import * as THREE from 'three'; // Needed for THREE.MathUtils

// --- Module-level variables ---
let appMode = 'observe'; // Current application mode: 'observe', 'translate', 'rotate', 'scale'

let transformControlsInstance = null;
let orbitControlsInstance = null;

let isSnapActive = true;
let translationSnapValue = 10;    // Default in mm
let rotationSnapValueRad = THREE.MathUtils.degToRad(45); // Default in radians

// --- Initialization ---
export function initInteractionManager(transformControls, orbitControls) {
    if (!transformControls || !orbitControls) {
        console.error("InteractionManager: TransformControls or OrbitControls not provided!");
        return;
    }
    transformControlsInstance = transformControls;
    orbitControlsInstance = orbitControls;

    // Apply initial snap settings to TransformControls
    applySnapSettingsToTransformControls();

    console.log("InteractionManager initialized.");
}

// --- Mode Management ---
export function setMode(newMode, selectedSceneObject = null) {
    appMode = newMode;
    console.log(`[InteractionManager] Mode set to: ${appMode}`);

    // Disable all camera/object controls initially, then enable based on mode
    if (orbitControlsInstance) orbitControlsInstance.enabled = false;
    if (transformControlsInstance) {
        transformControlsInstance.enabled = false;
        transformControlsInstance.detach(); // Always detach when changing mode initially
    }


    switch (appMode) {
        case 'observe':
            if (orbitControlsInstance) orbitControlsInstance.enabled = true;
            // If switching from a transform mode, ensure gizmo is detached
            if (transformControlsInstance) transformControlsInstance.detach();
            break;
        case 'translate':
            if (orbitControlsInstance) orbitControlsInstance.enabled = true;
            if (transformControlsInstance) {
                transformControlsInstance.setMode('translate');
                transformControlsInstance.enabled = true;
                if (selectedSceneObject) transformControlsInstance.attach(selectedSceneObject);
            }
            break;
        case 'rotate':
            if (orbitControlsInstance) orbitControlsInstance.enabled = true;
            if (transformControlsInstance) {
                transformControlsInstance.setMode('rotate');
                transformControlsInstance.enabled = true;
                if (selectedSceneObject) transformControlsInstance.attach(selectedSceneObject);
            }
            break;
        case 'scale':
            if (orbitControlsInstance) orbitControlsInstance.enabled = true;
            if (transformControlsInstance) {
                transformControlsInstance.setMode('scale');
                transformControlsInstance.enabled = true;
                if (selectedSceneObject) transformControlsInstance.attach(selectedSceneObject);
            }
            break;
        default:
            console.warn(`[InteractionManager] Unknown mode: ${appMode}. Defaulting to observe.`);
            if (orbitControlsInstance) orbitControlsInstance.enabled = true;
            appMode = 'observe';
            break;
    }
    // Re-apply snap settings in case mode change affects TransformControls
    applySnapSettingsToTransformControls();
}

export function getCurrentMode() {
    return appMode;
}

// --- Snap Control ---
export function toggleSnap() {
    isSnapActive = !isSnapActive;
    applySnapSettingsToTransformControls();
    console.log(`[InteractionManager] Snap to Grid: ${isSnapActive ? 'ON' : 'OFF'}`);
    return isSnapActive; // Return new state for UI update
}

export function updateSnapSettings(newTransSnapMm, newAngleSnapDeg) {
    if (newTransSnapMm !== undefined && !isNaN(parseFloat(newTransSnapMm))) {
        translationSnapValue = parseFloat(newTransSnapMm);
    }
    if (newAngleSnapDeg !== undefined && !isNaN(parseFloat(newAngleSnapDeg))) {
        rotationSnapValueRad = THREE.MathUtils.degToRad(parseFloat(newAngleSnapDeg));
    }
    applySnapSettingsToTransformControls();
    console.log(`[InteractionManager] Snap settings updated. Translation: ${translationSnapValue}mm, Rotation: ${THREE.MathUtils.radToDeg(rotationSnapValueRad)}deg`);
}

function applySnapSettingsToTransformControls() {
    if (transformControlsInstance) {
        transformControlsInstance.setTranslationSnap(isSnapActive ? translationSnapValue : null);
        transformControlsInstance.setRotationSnap(isSnapActive ? rotationSnapValueRad : null);
        // transformControlsInstance.setScaleSnap(isSnapActive ? scaleSnapValue : null); // If scale snap is desired
    }
}

export function isSnapEnabled() {
    return isSnapActive;
}
export function getTranslationSnapValue() { // Returns value in mm
    return translationSnapValue;
}
export function getRotationSnapValue() { // Returns value in Radians
    return rotationSnapValueRad;
}