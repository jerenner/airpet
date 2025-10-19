// static/ringArrayEditor.js
import * as ExpressionInput from './expressionInput.js';

let modalElement, titleElement, nameInput, parentLVSelect, lvSelect,
    numDetectorsInput, radiusContainer, centerContainer, orientationContainer,
    pointToCenterCheckbox, inwardAxisContainer, inwardAxisSelect,
    confirmButton, cancelButton,
    axialRepetitionCheckbox, axialParamsContainer, numRingsInput, ringSpacingContainer;
let onConfirmCallback = null;
let currentProjectState = null;

export function initRingArrayEditor(callbacks) {
    onConfirmCallback = callbacks.onConfirm;

    modalElement = document.getElementById('ringArrayEditorModal');
    titleElement = document.getElementById('ringArrayEditorTitle');
    nameInput = document.getElementById('ringArrayName');
    parentLVSelect = document.getElementById('ringArrayParentLV');
    lvSelect = document.getElementById('ringArrayLV');
    numDetectorsInput = document.getElementById('ringArrayNumDetectors');
    radiusContainer = document.getElementById('ring-radius-container');
    centerContainer = document.getElementById('ringArrayCenterInputs');
    orientationContainer = document.getElementById('ringArrayOrientationInputs');
    pointToCenterCheckbox = document.getElementById('ringPointToCenter');
    inwardAxisContainer = document.getElementById('ringInwardAxisContainer');
    inwardAxisSelect = document.getElementById('ringInwardAxis');
    confirmButton = document.getElementById('ringArrayConfirm');
    cancelButton = document.getElementById('ringArrayCancel');
    axialRepetitionCheckbox = document.getElementById('ringAxialRepetition');
    axialParamsContainer = document.getElementById('ring-axial-params-container');
    numRingsInput = document.getElementById('ringArrayNumRings');
    ringSpacingContainer = document.getElementById('ring-spacing-container');

    cancelButton.addEventListener('click', hide);
    confirmButton.addEventListener('click', handleConfirm);
    pointToCenterCheckbox.addEventListener('change', toggleInwardAxis);
    axialRepetitionCheckbox.addEventListener('change', toggleAxialParams);

    console.log("Ring Array Editor Initialized.");
}

export function show(projectState) {
    currentProjectState = projectState;
    if (!projectState) {
        alert("Cannot open Ring Array Editor without a project state.");
        return;
    }

    // Populate dropdowns
    const allLVs = Object.keys(projectState.logical_volumes || {});
    const placeableLVs = allLVs.filter(lvName =>
        projectState.logical_volumes[lvName]?.content_type === 'physvol'
    );

    populateSelect(parentLVSelect, placeableLVs);
    populateSelect(lvSelect, allLVs.filter(name => name !== projectState.world_volume_ref));

    // Set defaults
    nameInput.value = 'detector_ring';
    if (projectState.world_volume_ref) {
        parentLVSelect.value = projectState.world_volume_ref;
    }
    numDetectorsInput.value = 12;

    // Use ExpressionInput for dynamic fields
    radiusContainer.innerHTML = '';
    radiusContainer.appendChild(ExpressionInput.create('ring_radius', 'Ring Radius (mm)', '200'));

    centerContainer.innerHTML = '';
    centerContainer.appendChild(ExpressionInput.create('ring_center_x', 'X', '0'));
    centerContainer.appendChild(ExpressionInput.create('ring_center_y', 'Y', '0'));
    centerContainer.appendChild(ExpressionInput.create('ring_center_z', 'Z', '0'));

    orientationContainer.innerHTML = '';
    orientationContainer.appendChild(ExpressionInput.create('ring_rot_x', 'X', '0'));
    orientationContainer.appendChild(ExpressionInput.create('ring_rot_y', 'Y', '0'));
    orientationContainer.appendChild(ExpressionInput.create('ring_rot_z', 'Z', '0'));

    // --- Reset and set up axial repetition fields ---
    axialRepetitionCheckbox.checked = false;
    numRingsInput.value = 2;
    ringSpacingContainer.innerHTML = '';
    ringSpacingContainer.appendChild(ExpressionInput.create('ring_spacing', 'Ring Spacing (mm)', '25'));
    toggleAxialParams(); // Set initial visibility

    pointToCenterCheckbox.checked = true;
    toggleInwardAxis();

    modalElement.style.display = 'block';
}

function hide() {
    modalElement.style.display = 'none';
}

function toggleInwardAxis() {
    inwardAxisContainer.style.display = pointToCenterCheckbox.checked ? 'flex' : 'none';
}

function toggleAxialParams() {
    axialParamsContainer.style.display = axialRepetitionCheckbox.checked ? 'block' : 'none';
}

function populateSelect(selectElement, optionsArray) {
    selectElement.innerHTML = '';
    optionsArray.forEach(optionText => {
        const option = document.createElement('option');
        option.value = optionText;
        option.textContent = optionText;
        selectElement.appendChild(option);
    });
}

function handleConfirm() {
    if (!onConfirmCallback) return;

    const ringName = nameInput.value.trim();
    if (!ringName) {
        alert("Please provide a name for the ring.");
        return;
    }

    const payload = {
        ring_name: ringName,
        parent_lv_name: parentLVSelect.value,
        lv_to_place: lvSelect.value,
        num_detectors: parseInt(numDetectorsInput.value, 10),
        radius: document.getElementById('ring_radius').value,
        center: {
            x: document.getElementById('ring_center_x').value,
            y: document.getElementById('ring_center_y').value,
            z: document.getElementById('ring_center_z').value,
        },
        orientation: {
            x: document.getElementById('ring_rot_x').value,
            y: document.getElementById('ring_rot_y').value,
            z: document.getElementById('ring_rot_z').value,
        },
        point_to_center: pointToCenterCheckbox.checked,
        inward_axis: inwardAxisSelect.value,
        num_rings: axialRepetitionCheckbox.checked ? numRingsInput.value : 1,
        ring_spacing: axialRepetitionCheckbox.checked ? document.getElementById('ring_spacing').value : '0.0'
    };

    onConfirmCallback(payload);
    hide();
}
