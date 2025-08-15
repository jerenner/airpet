// static/interactionManager.js
import * as THREE from 'three'; // Needed for THREE.MathUtils

// --- Module-level variables ---
let appMode = 'observe'; // Current application mode: 'observe', 'translate', 'rotate', 'scale'

let transformControlsInstance = null;
let orbitControlsInstance = null;
let flyControlsInstance = null; // If you implement camera fly mode

let isSnapActive = true;
let translationSnapValue = 10;    // Default in mm
let rotationSnapValueRad = THREE.MathUtils.degToRad(45); // Default in radians

// --- Initialization ---
export function initInteractionManager(transformControls, orbitControls, flyControls) {
    if (!transformControls || !orbitControls) {
        console.error("InteractionManager: TransformControls or OrbitControls not provided!");
        return;
    }
    transformControlsInstance = transformControls;
    orbitControlsInstance = orbitControls;
    if (flyControls) {
        flyControlsInstance = flyControls;
    }

    // Add global keyboard listeners
    window.addEventListener('keydown', handleKeyDown);
    window.addEventListener('keyup', handleKeyUp);

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
    if (flyControlsInstance) flyControlsInstance.enabled = false;


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
        case 'fly': // Example for camera fly mode
             if (flyControlsInstance) flyControlsInstance.enabled = true;
             if (transformControlsInstance) transformControlsInstance.detach(); // Ensure gizmo off
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


// --- Keyboard Event Handlers for TransformControls Axis Constraints & Shortcuts ---
function handleKeyDown(event) {
    if (!transformControlsInstance || !transformControlsInstance.object || !transformControlsInstance.enabled) {
        // Only act if TransformControls is active and attached to an object
        return;
    }

    // Prevent default browser actions for keys we handle (like Ctrl+X/Y/Z if they are browser shortcuts)
    // event.preventDefault(); // Use with caution, can block normal input fields

    switch (event.key.toUpperCase()) {
        case 'X':
            if (transformControlsInstance.showX) { // If already showing only X, toggle all back on
                transformControlsInstance.showX = true;
                transformControlsInstance.showY = true;
                transformControlsInstance.showZ = true;
            } else { // Show only X
                transformControlsInstance.showX = true;
                transformControlsInstance.showY = false;
                transformControlsInstance.showZ = false;
            }
            break;
        case 'Y':
             if (transformControlsInstance.showY) {
                transformControlsInstance.showX = true;
                transformControlsInstance.showY = true;
                transformControlsInstance.showZ = true;
            } else {
                transformControlsInstance.showX = false;
                transformControlsInstance.showY = true;
                transformControlsInstance.showZ = false;
            }
            break;
        case 'Z':
            if (transformControlsInstance.showZ) {
                transformControlsInstance.showX = true;
                transformControlsInstance.showY = true;
                transformControlsInstance.showZ = true;
            } else {
                transformControlsInstance.showX = false;
                transformControlsInstance.showY = false;
                transformControlsInstance.showZ = true;
            }
            break;
        
        // Hotkeys for switching transform modes (optional, could conflict with text input)
        // Only if not typing in an input field
        if (document.activeElement.tagName === 'INPUT' || document.activeElement.tagName === 'TEXTAREA') return;

        case 'W': // Translate
            if (appMode !== 'translate') {
                // Need to inform main.js/UIManager to update UI if mode changes via shortcut
                // For now, just change TransformControls mode directly.
                // A better way: main.js listens for keydown and calls its handleModeChange
                transformControlsInstance.setMode('translate');
                // UIManager.setActiveModeButton('translate'); // Example
            }
            break;
        case 'E': // Rotate
             if (appMode !== 'rotate') {
                transformControlsInstance.setMode('rotate');
            }
            break;
        case 'R': // Scale (if implemented)
             if (appMode !== 'scale') {
                transformControlsInstance.setMode('scale');
            }
            break;
        case 'ESCAPE':
            // Detach TransformControls and potentially switch to observe mode or deselect
            // This action should ideally be coordinated by main.js
            // For now:
            if(transformControlsInstance.object) {
                // transformControlsInstance.detach(); // This would be done by SceneManager upon deselection
                // Call a higher-level deselect function if available
                // onObjectSelectedCallback(null); // Example, assuming this is available
            }
            break;
    }
}

function handleKeyUp(event) {
    if (!transformControlsInstance || !transformControlsInstance.object || !transformControlsInstance.enabled) {
        return;
    }
    // When an X, Y, or Z key is released, reset the gizmo to show all axes,
    // UNLESS another constraint key is still implicitly held (which is hard to track simply).
    // A simpler approach: if a specific axis was isolated, releasing it shows all axes again.
    // However, TransformControls usually resets its showX/Y/Z itself when dragging ends or mode changes.
    // The main use of X/Y/Z keys with TransformControls is often *during* a drag to constrain to an axis
    // by pressing the key *after* starting the drag, or by directly clicking the gizmo axis.
    // The `showX/Y/Z` properties are more for *permanently* hiding parts of the gizmo.
    //
    // A more standard behavior for TransformControls is:
    // - User starts dragging (e.g., center of gizmo for free move).
    // - While dragging, user presses 'X'. The current drag operation snaps and constrains to X-axis.
    // - User releases 'X'. Drag continues freely or snaps back to the plane it was on.
    // This level of detail is built into TransformControls if `axis` is set during its events.
    // Our current X/Y/Z keydown simply toggles visibility of gizmo parts.
    //
    // For a more robust X/Y/Z constraint during drag:
    // transformControlsInstance.axis = 'X'; // or 'Y', 'Z', 'XY', 'YZ', 'XZ', 'XYZ' (for rotation)
    // And reset to null on keyup.
    //
    // The showX/Y/Z approach is a visual filter. Let's stick to resetting it on keyup for now.
    switch (event.key.toUpperCase()) {
        case 'X':
        case 'Y':
        case 'Z':
            // If no other constraint key is pressed, restore all axes visibility
            // This simple reset is okay for now.
            // transformControlsInstance.showX = true;
            // transformControlsInstance.showY = true;
            // transformControlsInstance.showZ = true;
            // More robustly, TransformControls handles axis locking internally when you press X/Y/Z *during* a drag.
            // Our keydown/keyup is for toggling visibility, which is a bit different.
            // Let's assume this is for PRE-selecting the axis constraint before a drag.
            break;
    }
}