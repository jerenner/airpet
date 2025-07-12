import * as THREE from 'three';
import * as ExpressionInput from './expressionInput.js';

let modalElement, titleElement, nameInput, lvSelect, confirmButton, cancelButton;
let onConfirmCallback = null;
let isEditMode = false;
let editingPVId = null;
let parentLVName = null;

let posDefineSelect, rotDefineSelect;
let positionDefines, rotationDefines;
let currentProjectState;

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
    currentProjectState = projectState;

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
    const posDefines = Object.keys(projectState.defines).filter(k => projectState.defines[k].type === 'position');
    const rotDefines = Object.keys(projectState.defines).filter(k => projectState.defines[k].type === 'rotation');
    populateDefineSelect(posDefineSelect, posDefines, 'position');
    populateDefineSelect(rotDefineSelect, rotDefines, 'rotation');

    if (pvData && pvData.id) {
        // --- EDIT MODE ---
        isEditMode = true;
        editingPVId = pvData.id;

        titleElement.textContent = `Edit Placement in '${parentLVName}'`;
        nameInput.value = pvData.name;

        lvSelect.value = pvData.volume_ref;
        lvSelect.disabled = true; // Can't change the LV being placed
        confirmButton.textContent = "Update Placement";

        // Check if position/rotation is a define (string) or absolute (object)
        setupTransformUI('position', pvData.position, posDefineSelect, posDefines);
        setupTransformUI('rotation', pvData.rotation, rotDefineSelect, rotDefines);

    } else {
        // --- CREATE MODE ---
        isEditMode = false;
        editingPVId = null;

        titleElement.textContent = `Place New Volume in '${parentLVName}'`;
        nameInput.value = '';
        lvSelect.disabled = false;
        confirmButton.textContent = "Place Volume";

        // Setup with default absolute values
        setupTransformUI('position', {x:'0',y:'0',z:'0'}, posDefineSelect, posDefines);
        setupTransformUI('rotation', {x:'0',y:'0',z:'0'}, rotDefineSelect, rotDefines);
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
            x: document.getElementById('pv_pos_x').value,
            y: document.getElementById('pv_pos_y').value,
            z: document.getElementById('pv_pos_z').value,
        };
    } else {
        position = posDefineSelect.value; // Send the string name of the define
    }

    if (rotDefineSelect.value === '[Absolute]') {
        rotation = {
            x: `(${document.getElementById('pv_rot_x').value}) * deg`,
            y: `(${document.getElementById('pv_rot_y').value}) * deg`,
            z: `(${document.getElementById('pv_rot_z').value}) * deg`,
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
    const type = select.dataset.transformType;
    const defines = (type === 'position') 
        ? Object.keys(currentProjectState.defines).filter(k => currentProjectState.defines[k].type === 'position')
        : Object.keys(currentProjectState.defines).filter(k => currentProjectState.defines[k].type === 'rotation');
    
    const newValue = select.value === '[Absolute]' ? {x:'0', y:'0', z:'0'} : select.value;
    
    setupTransformUI(type, newValue, select, defines);
}

// This function now builds the entire input block dynamically
function setupTransformUI(type, value, select, defines) {
    const inputsContainerId = `pv_${type}_inputs`;
    let inputsContainer = document.getElementById(inputsContainerId);
    if (!inputsContainer) {
        inputsContainer = document.createElement('div');
        inputsContainer.id = inputsContainerId;
        select.parentElement.parentElement.appendChild(inputsContainer);
    }
    inputsContainer.innerHTML = ''; // Clear previous inputs

    const isAbsolute = typeof value !== 'string';
    select.value = isAbsolute ? '[Absolute]' : value;
    
    let displayValues = {x: '0', y: '0', z: '0'};
    if (isAbsolute) {
        displayValues = value || displayValues;
    } else {
        const define = currentProjectState.defines[value];
        if (define) {
            // Use the raw expression from the define for display
            displayValues = define.raw_expression || displayValues;
        }
    }

    ['x', 'y', 'z'].forEach(axis => {
        const labelText = axis.toUpperCase();
        const initialValue = displayValues[axis] || '0';
        
        if (isAbsolute) {
            let val = initialValue;
            // If it's a rotation, the raw expression is in rad, but UI is in deg
            if (type === 'rotation' && !isNaN(parseFloat(val))) {
                val = THREE.MathUtils.radToDeg(parseFloat(val)).toString();
            }
            const comp = ExpressionInput.create(`pv_${type}_${axis}`, labelText, val, currentProjectState);
            inputsContainer.appendChild(comp);
        } else {
            // Display grayed-out box with evaluated value
            const item = document.createElement('div');
            item.className = 'property_item';
            item.innerHTML = `<label>${labelText}:</label>`;
            const disabledInput = document.createElement('input');
            disabledInput.type = 'text';
            disabledInput.disabled = true;
            disabledInput.className = 'expression-result';
            
            const define = currentProjectState.defines[value];
            if (define && define.value) {
                let evalVal = define.value[axis] || 0;
                if (type === 'rotation') {
                    evalVal = THREE.MathUtils.radToDeg(evalVal);
                }
                disabledInput.value = evalVal.toPrecision(4);
            }
            item.appendChild(disabledInput);
            inputsContainer.appendChild(item);
        }
    });
}