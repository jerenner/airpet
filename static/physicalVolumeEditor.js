import * as THREE from 'three';
import * as APIService from './apiService.js';

let modalElement, titleElement, nameInput, lvSelect, confirmButton, cancelButton;
let posInputs, rotInputs;
let onConfirmCallback = null;
let isEditMode = false;
let editingPVId = null;
let parentLVName = null;

let posDefineSelect, rotDefineSelect;
let positionDefines, rotationDefines;

export function initPVEditor(callbacks) {
    onConfirmCallback = callbacks.onConfirm;

    modalElement = document.getElementById('pvEditorModal');
    titleElement = document.getElementById('pvEditorTitle');
    nameInput = document.getElementById('pvEditorName');
    lvSelect = document.getElementById('pvEditorLV');
    confirmButton = document.getElementById('confirmPVEditor');
    cancelButton = document.getElementById('cancelPVEditor');

    posDefineSelect = document.getElementById('pv_pos_define_select');
    rotDefineSelect = document.getElementById('pv_rot_define_select');

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

    posDefineSelect.addEventListener('change', handleDefineSelectionChange);
    rotDefineSelect.addEventListener('change', handleDefineSelectionChange);

    console.log("Physical Volume Editor Initialized.");
}

export async function show(pvData = null, projectState = null, parentContext = null) {
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

    // Fetch available defines
    try {
        positionDefines = await APIService.getDefinesByType('position');
        rotationDefines = await APIService.getDefinesByType('rotation');
    } catch (e) {
        console.error("Could not fetch defines:", e);
        positionDefines = {}; rotationDefines = {};
    }

    // Populate the define dropdowns
    populateDefineSelect(posDefineSelect, positionDefines, 'position');
    populateDefineSelect(rotDefineSelect, rotationDefines, 'rotation');

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

        // Check if position/rotation is a define (string) or absolute (object)
        setupTransformUI('position', pvData.position, posDefineSelect, posInputs, positionDefines);
        setupTransformUI('rotation', pvData.rotation, rotDefineSelect, rotInputs, rotationDefines);

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

        // Set to Absolute by default
        posDefineSelect.value = '[Absolute]';
        rotDefineSelect.value = '[Absolute]';
        handleDefineSelectionChange({target: posDefineSelect}); // Trigger UI update
        handleDefineSelectionChange({target: rotDefineSelect}); // Trigger UI update
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

function populateDefineSelect(selectElement, defines, type) {
    selectElement.innerHTML = '<option value="[Absolute]">[Absolute Value]</option>';
    selectElement.dataset.type = type; // Store type for event handler
    for (const name in defines) {
        const option = document.createElement('option');
        option.value = name;
        option.textContent = name;
        selectElement.appendChild(option);
    }
}

function handleConfirm() {
    if (!onConfirmCallback) return;

    const name = nameInput.value.trim(); // Name can be optional for PVs
    const lvRef = lvSelect.value;
    if (!lvRef) { alert("Please select a Logical Volume to place."); return; }

    // --- Get transform data ---
    let position, rotation;

    if (posDefineSelect.value === '[Absolute]') {
        position = {
            x: parseFloat(posInputs.x.value),
            y: parseFloat(posInputs.y.value),
            z: parseFloat(posInputs.z.value),
        };
    } else {
        position = posDefineSelect.value; // Send the string name of the define
    }

    if (rotDefineSelect.value === '[Absolute]') {
        rotation = {
            x: THREE.MathUtils.degToRad(parseFloat(rotInputs.x.value)),
            y: THREE.MathUtils.degToRad(parseFloat(rotInputs.y.value)),
            z: THREE.MathUtils.degToRad(parseFloat(rotInputs.z.value)),
        };
    } else {
        rotation = rotDefineSelect.value; // Send the string name of the define
    }

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

function handleDefineSelectionChange(event) {
    const select = event.target;
    const type = select.dataset.type;
    const isAbsolute = select.value === '[Absolute]';
    const inputs = (type === 'position') ? posInputs : rotInputs;
    const defines = (type === 'position') ? positionDefines : rotationDefines;

    // Enable/disable text inputs
    Object.values(inputs).forEach(input => input.disabled = !isAbsolute);

    // If a define is selected, populate the fields with its values
    if (!isAbsolute) {
        const define = defines[select.value];
        if (define) {
            const val = define.value;
            if (type === 'rotation') {
                inputs.x.value = THREE.MathUtils.radToDeg(val.x);
                inputs.y.value = THREE.MathUtils.radToDeg(val.y);
                inputs.z.value = THREE.MathUtils.radToDeg(val.z);
            } else {
                inputs.x.value = val.x;
                inputs.y.value = val.y;
                inputs.z.value = val.z;
            }
        }
    }
}

function setupTransformUI(type, value, select, inputs, defines) {
    if (typeof value === 'string' && defines[value]) { // It's a define reference that exists
        select.value = value;
        Object.values(inputs).forEach(input => input.disabled = true);
        const define = defines[value];
        if (define) { // Double check, but should be true
            const val = define.value || { x: 0, y: 0, z: 0 }; // safety default
            if (type === 'rotation') {
                inputs.x.value = THREE.MathUtils.radToDeg(val.x || 0);
                inputs.y.value = THREE.MathUtils.radToDeg(val.y || 0);
                inputs.z.value = THREE.MathUtils.radToDeg(val.z || 0);
            } else { // position
                inputs.x.value = val.x || 0;
                inputs.y.value = val.y || 0;
                inputs.z.value = val.z || 0;
            }
        }
    } else { // It's an absolute value object (or a missing define, treat as absolute)
        select.value = '[Absolute]';
        Object.values(inputs).forEach(input => input.disabled = false);
        const val = (typeof value === 'object' && value !== null) ? value : { x: 0, y: 0, z: 0 }; // safety default
        if (type === 'rotation') {
            inputs.x.value = THREE.MathUtils.radToDeg(val.x || 0);
            inputs.y.value = THREE.MathUtils.radToDeg(val.y || 0);
            inputs.z.value = THREE.MathUtils.radToDeg(val.z || 0);
        } else { // position
            inputs.x.value = val.x || 0;
            inputs.y.value = val.y || 0;
            inputs.z.value = val.z || 0;
        }
    }
}