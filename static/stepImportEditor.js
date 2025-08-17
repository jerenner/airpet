// static/stepImportEditor.js
import * as ExpressionInput from './expressionInput.js';

// --- Module-level variables ---
let modalElement, confirmButton, cancelButton, stepFileNameEl,
    stepImportGroupName, stepImportParentLV, stepImportOffsetContainer;

let currentFile = null;
let onConfirmCallback = null;
let currentProjectState = null;

/**
 * Initializes the STEP Import Editor modal and its event listeners.
 * @param {object} callbacks - An object containing callback functions, expecting `onConfirm`.
 */
export function initStepImportEditor(callbacks) {
    onConfirmCallback = callbacks.onConfirm;

    modalElement = document.getElementById('stepImportModal');
    confirmButton = document.getElementById('confirmStepImport');
    cancelButton = document.getElementById('cancelStepImport');
    stepFileNameEl = document.getElementById('stepFileName');
    stepImportGroupName = document.getElementById('stepImportGroupName');
    stepImportParentLV = document.getElementById('stepImportParentLV');
    stepImportOffsetContainer = document.getElementById('stepImportOffsetInputs');

    cancelButton.addEventListener('click', hide);
    confirmButton.addEventListener('click', handleConfirm);
    
    console.log("STEP Import Editor Initialized.");
}

/**
 * Shows the STEP import modal and populates it with initial data.
 * @param {File} file - The STEP file selected by the user.
 * @param {object} projectState - The current full project state for context.
 */
export function show(file, projectState) {
    currentFile = file;
    currentProjectState = projectState;
    
    stepFileNameEl.textContent = file.name;
    // Create a default grouping name from the filename, sanitized for GDML.
    stepImportGroupName.value = file.name.replace(/\.[^/.]+$/, "").replace(/[\s\W]/g, '_');

    // Populate the parent LV dropdown with LVs that can contain children.
    const placeableLVs = Object.keys(projectState.logical_volumes || {})
        .filter(lvName => projectState.logical_volumes[lvName]?.content_type === 'physvol');
    populateSelect(stepImportParentLV, placeableLVs);

    // Default the selection to the world volume if it exists.
    if (projectState.world_volume_ref && placeableLVs.includes(projectState.world_volume_ref)) {
        stepImportParentLV.value = projectState.world_volume_ref;
    }

    // Create the expression inputs for the placement offset.
    stepImportOffsetContainer.innerHTML = '';
    stepImportOffsetContainer.appendChild(ExpressionInput.create('step_offset_x', 'X', '0'));
    stepImportOffsetContainer.appendChild(ExpressionInput.create('step_offset_y', 'Y', '0'));
    stepImportOffsetContainer.appendChild(ExpressionInput.create('step_offset_z', 'Z', '0'));

    modalElement.style.display = 'block';
}

/**
 * Hides the STEP import modal.
 */
function hide() {
    modalElement.style.display = 'none';
}

/**
 * Handles the confirm button click, gathering data and calling the main controller.
 */
function handleConfirm() {
    if (onConfirmCallback) {
        const options = {
            file: currentFile,
            groupingName: stepImportGroupName.value.trim(),
            placementMode: document.querySelector('input[name="step_placement_mode"]:checked').value,
            parentLVName: stepImportParentLV.value,
            offset: {
                x: document.getElementById('step_offset_x').value,
                y: document.getElementById('step_offset_y').value,
                z: document.getElementById('step_offset_z').value
            }
        };
        onConfirmCallback(options);
    }
    hide();
}

/**
 * Helper function to populate a select dropdown.
 * @param {HTMLSelectElement} selectElement - The dropdown element.
 * @param {string[]} optionsArray - An array of strings for the options.
 */
function populateSelect(selectElement, optionsArray) {
    selectElement.innerHTML = '';
    optionsArray.forEach(optionText => {
        const option = document.createElement('option');
        option.value = optionText;
        option.textContent = optionText;
        selectElement.appendChild(option);
    });
}
