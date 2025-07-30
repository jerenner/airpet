import * as THREE from 'three';
import * as ExpressionInput from './expressionInput.js';

let modalElement, titleElement, nameInput, lvSelect, confirmButton, cancelButton;
let onConfirmCallback = null;
let isEditMode = false;
let editingPVId = null;
let parentLVName = null;

let posDefineSelect, rotDefineSelect, sclDefineSelect;
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
    sclDefineSelect = document.getElementById('pv_scl_define_select');

    cancelButton.addEventListener('click', hide);
    confirmButton.addEventListener('click', handleConfirm);

    posDefineSelect.addEventListener('change', handleDefineSelectionChange);
    rotDefineSelect.addEventListener('change', handleDefineSelectionChange);
    sclDefineSelect.addEventListener('change', handleDefineSelectionChange);

    console.log("Physical Volume Editor Initialized.");
}

export function show(pvData = null, projectState = null, parentContext = null) {
    if (!projectState || !parentContext) {
        alert("Cannot open PV Editor without project state and a parent volume.");
        return;
    }
    
    parentLVName = parentContext.name;
    currentProjectState = projectState;

    const allLVs = Object.keys(projectState.logical_volumes);
    const worldRef = projectState.world_volume_ref;
    const placeableLVs = allLVs.filter(lvName => lvName !== worldRef && lvName !== parentLVName);
    populateSelect(lvSelect, placeableLVs);

    // Get an array of NAMES, not objects.
    const posDefines = Object.keys(projectState.defines).filter(k => projectState.defines[k].type === 'position');
    const rotDefines = Object.keys(projectState.defines).filter(k => projectState.defines[k].type === 'rotation');
    const sclDefines = Object.keys(projectState.defines).filter(k => projectState.defines[k].type === 'scale');
    populateDefineSelect(posDefineSelect, posDefines);
    populateDefineSelect(rotDefineSelect, rotDefines);
    populateDefineSelect(sclDefineSelect, sclDefines);

    if (pvData && pvData.id) {
        isEditMode = true;
        editingPVId = pvData.id;
        titleElement.textContent = `Edit Placement in '${parentLVName}'`;
        nameInput.value = pvData.name;
        lvSelect.value = pvData.volume_ref;
        lvSelect.disabled = true;
        confirmButton.textContent = "Update Placement";
        
        setupTransformUI('position', pvData.position, posDefineSelect, posDefines);
        setupTransformUI('rotation', pvData.rotation, rotDefineSelect, rotDefines);
        setupTransformUI('scale',    pvData.scale,    sclDefineSelect, sclDefines);
    } else {
        isEditMode = false;
        editingPVId = null;
        titleElement.textContent = `Place New Volume in '${parentLVName}'`;
        nameInput.value = '';
        lvSelect.disabled = false;
        confirmButton.textContent = "Place Volume";
        
        setupTransformUI('position', {x:'0',y:'0',z:'0'}, posDefineSelect, posDefines);
        setupTransformUI('rotation', {x:'0',y:'0',z:'0'}, rotDefineSelect, rotDefines);
        setupTransformUI('scale',    {x:'1',y:'1',z:'1'}, sclDefineSelect, sclDefines);
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

function populateDefineSelect(selectElement, definesArray) {
    selectElement.innerHTML = '<option value="[Absolute]">[Absolute Value]</option>';
    definesArray.forEach(name => {
        const option = document.createElement('option');
        option.value = name;
        option.textContent = name;
        selectElement.appendChild(option);
    });
}

function handleConfirm() {
    if (!onConfirmCallback) return;
    const name = nameInput.value.trim();
    const lvRef = lvSelect.value;
    if (!lvRef) { alert("Please select a Logical Volume to place."); return; }

    let position, rotation, scale;

    if (posDefineSelect.value === '[Absolute]') {
        position = {
            x: document.getElementById('pv_position_x').value,
            y: document.getElementById('pv_position_y').value,
            z: document.getElementById('pv_position_z').value,
        };
    } else {
        position = posDefineSelect.value;
    }

    if (rotDefineSelect.value === '[Absolute]') {
        rotation = {
            x: document.getElementById('pv_rotation_x').value,
            y: document.getElementById('pv_rotation_y').value,
            z: document.getElementById('pv_rotation_z').value,
        };
    } else {
        rotation = rotDefineSelect.value;
    }

    if (sclDefineSelect.value === '[Absolute]') {
        scale = {
            x: document.getElementById('pv_scale_x').value,
            y: document.getElementById('pv_scale_y').value,
            z: document.getElementById('pv_scale_z').value,
        };
    } else {
        scale = sclDefineSelect.value;
    }

    onConfirmCallback({
        isEdit: isEditMode,
        id: isEditMode ? editingPVId : null,
        parent_lv_name: parentLVName,
        name: name,
        volume_ref: lvRef,
        position: position,
        rotation: rotation,
        scale: scale,
    });
    
    hide();
}

function handleDefineSelectionChange(event) {
    const select = event.target;
    const type = select.id.includes('_pos_') ? 'position' : 'rotation';
    
    const defines = (type === 'position') 
        ? Object.keys(currentProjectState.defines).filter(k => currentProjectState.defines[k].type === 'position')
        : Object.keys(currentProjectState.defines).filter(k => currentProjectState.defines[k].type === 'rotation');

    const newValue = select.value === '[Absolute]' ? {x:'0', y:'0', z:'0'} : select.value;
    
    // Call the main UI builder to reconstruct the input fields
    setupTransformUI(type, newValue, select, defines);
}

// This function now builds the entire input block dynamically
function setupTransformUI(type, value, select, defines) {
    const inputsContainerId = `pv_${type}_inputs`;
    let inputsContainer = document.getElementById(inputsContainerId);
    if (!inputsContainer) {
        // This should not happen if the HTML is correct, but as a fallback:
        inputsContainer = document.createElement('div');
        inputsContainer.id = inputsContainerId;
        select.parentElement.parentElement.appendChild(inputsContainer);
    }
    inputsContainer.innerHTML = ''; 

    const isAbsolute = typeof value !== 'string' || !defines.includes(value);
    select.value = isAbsolute ? '[Absolute]' : value;
    
    let displayValues = (type === 'scale') ? {x: '1', y: '1', z: '1'} : {x: '0', y: '0', z: '0'};
    if (isAbsolute) {
        displayValues = value || displayValues;
    } else {
        const define = currentProjectState.defines[value];
        if (define) {
            displayValues = define.raw_expression || displayValues;
        }
    }

    ['x', 'y', 'z'].forEach(axis => {
        const labelText = axis.toUpperCase();
        const initialValue = displayValues[axis] || '0';
        const inputId = `pv_${type}_${axis}`;

        if (isAbsolute) {
            // Create our full component for absolute expressions
            const comp = ExpressionInput.create(inputId, labelText, initialValue, currentProjectState);
            inputsContainer.appendChild(comp);
        } else {
            // Create a grayed-out box with the evaluated value for define references
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