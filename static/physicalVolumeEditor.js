import * as THREE from 'three';

let modalElement, titleElement, nameInput, lvSelect, confirmButton, cancelButton;
let posInputs, rotInputs;
let onConfirmCallback = null;
let isEditMode = false;
let editingPVId = null;
let parentLVName = null;

export function initPVEditor(callbacks) {
    onConfirmCallback = callbacks.onConfirm;

    modalElement = document.getElementById('pvEditorModal');
    titleElement = document.getElementById('pvEditorTitle');
    nameInput = document.getElementById('pvEditorName');
    lvSelect = document.getElementById('pvEditorLV');
    confirmButton = document.getElementById('confirmPVEditor');
    cancelButton = document.getElementById('cancelPVEditor');

    posInputs = {
        x: document.getElementById('pv_pos_x'),
        y: document.getElementById('pv_pos_y'),
        z: document.getElementById('pv_pos_z')
    };
    rotInputs = {
        x: document.getElementById('pv_rot_x'),
        y: document.getElementById('pv_rot_y'),
        z: document.getElementById('pv_rot_z')
    };

    cancelButton.addEventListener('click', hide);
    confirmButton.addEventListener('click', handleConfirm);

    console.log("Physical Volume Editor Initialized.");
}

export function show(pvData = null, projectState = null, parentContext = null) {
    if (!projectState || !parentContext) {
        alert("Cannot open PV Editor without project state and a parent volume.");
        return;
    }
    
    parentLVName = parentContext.name;

    // --- Filter the list of LVs before populating ---
    const allLVs = Object.keys(projectState.logical_volumes);
    const worldRef = projectState.world_volume_ref;
    
    // Create a new array containing all LVs that are:
    // 1. NOT the world volume
    // 2. NOT the parent volume itself
    const placeableLVs = allLVs.filter(lvName => {
        return lvName !== worldRef && lvName !== parentLVName;
    });

    // Populate dropdown with available LVs
    populateSelect(lvSelect, placeableLVs);

    if (pvData && pvData.id) {
        // --- EDIT MODE ---
        isEditMode = true;
        editingPVId = pvData.id;

        titleElement.textContent = `Edit Placement in '${parentLVName}'`;
        nameInput.value = pvData.name;

        lvSelect.value = pvData.volume_ref;
        lvSelect.disabled = true; // Can't change the LV being placed
        confirmButton.textContent = "Update Placement";

        const pos = pvData.position || {x:0, y:0, z:0};
        const rot_rad = pvData.rotation || {x:0, y:0, z:0};
        posInputs.x.value = pos.x; posInputs.y.value = pos.y; posInputs.z.value = pos.z;
        rotInputs.x.value = THREE.MathUtils.radToDeg(rot_rad.x);
        rotInputs.y.value = THREE.MathUtils.radToDeg(rot_rad.y);
        rotInputs.z.value = THREE.MathUtils.radToDeg(rot_rad.z);

    } else {
        // --- CREATE MODE ---
        isEditMode = false;
        editingPVId = null;

        titleElement.textContent = `Place New Volume in '${parentLVName}'`;
        nameInput.value = '';
        lvSelect.disabled = false;
        confirmButton.textContent = "Place Volume";
        
        // Reset transform fields
        Object.values(posInputs).forEach(inp => inp.value = 0);
        Object.values(rotInputs).forEach(inp => inp.value = 0);
    }

    modalElement.style.display = 'block';
}

export function hide() {
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
    if (!onConfirmCallback) return;

    const name = nameInput.value.trim(); // Name can be optional for PVs
    const lvRef = lvSelect.value;
    if (!lvRef) { alert("Please select a Logical Volume to place."); return; }
    
    const position = {
        x: parseFloat(posInputs.x.value),
        y: parseFloat(posInputs.y.value),
        z: parseFloat(posInputs.z.value),
    };
    const rotation = {
        x: THREE.MathUtils.degToRad(parseFloat(rotInputs.x.value)),
        y: THREE.MathUtils.degToRad(parseFloat(rotInputs.y.value)),
        z: THREE.MathUtils.degToRad(parseFloat(rotInputs.z.value)),
    };

    onConfirmCallback({
        isEdit: isEditMode,
        id: isEditMode ? editingPVId : null,
        parent_lv_name: parentLVName,
        name: name,
        volume_ref: lvRef,
        position: position,
        rotation: rotation,
    });
    
    hide();
}