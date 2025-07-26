// static/skinSurfaceEditor.js

let modalElement, titleElement, nameInput, lvSelect, surfaceSelect,
    confirmButton, cancelButton;
let onConfirmCallback = null;
let isEditMode = false;
let editingSSId = null;
let currentProjectState = null;

export function initSkinSurfaceEditor(callbacks) {
    onConfirmCallback = callbacks.onConfirm;
    modalElement = document.getElementById('skinSurfaceEditorModal');
    titleElement = document.getElementById('skinSurfaceEditorTitle');
    nameInput = document.getElementById('ssEditorName');
    lvSelect = document.getElementById('ssEditorLVRef');
    surfaceSelect = document.getElementById('ssEditorSurfaceRef');
    confirmButton = document.getElementById('ssEditorConfirm');
    cancelButton = document.getElementById('ssEditorCancel');

    cancelButton.addEventListener('click', hide);
    confirmButton.addEventListener('click', handleConfirm);

    console.log("Skin Surface Editor Initialized.");
}

export function show(ssData = null, projectState = null) {
    currentProjectState = projectState;
    if (!projectState) {
        alert("Cannot open Skin Surface Editor without a project state.");
        return;
    }

    // Populate dropdowns
    populateSelect(lvSelect, Object.keys(projectState.logical_volumes || {}));
    populateSelect(surfaceSelect, Object.keys(projectState.optical_surfaces || {}));

    if (ssData) { // EDIT MODE
        isEditMode = true;
        editingSSId = ssData.name;
        titleElement.textContent = `Edit Skin Surface: ${ssData.name}`;
        nameInput.value = ssData.name;
        nameInput.disabled = true;
        confirmButton.textContent = "Update Surface";

        lvSelect.value = ssData.volume_ref;
        surfaceSelect.value = ssData.surfaceproperty_ref;

    } else { // CREATE MODE
        isEditMode = false;
        editingSSId = null;
        titleElement.textContent = "Create New Skin Surface";
        nameInput.value = '';
        nameInput.disabled = false;
        confirmButton.textContent = "Create Surface";
    }

    modalElement.style.display = 'block';
}

function hide() {
    modalElement.style.display = 'none';
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
    const name = nameInput.value.trim();
    if (!name && !isEditMode) {
        alert("Please provide a name.");
        return;
    }

    const volumeRef = lvSelect.value;
    const surfaceRef = surfaceSelect.value;

    if (!volumeRef || !surfaceRef) {
        alert("Please select both a Logical Volume and an Optical Surface.");
        return;
    }

    onConfirmCallback({
        isEdit: isEditMode,
        id: isEditMode ? editingSSId : name,
        name: name,
        volume_ref: volumeRef,
        surfaceproperty_ref: surfaceRef
    });

    hide();
}
