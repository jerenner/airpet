import * as THREE from 'three';
import * as ExpressionInput from './expressionInput.js';

let modalElement, titleElement, nameInput, lvSelect, confirmButton, cancelButton, pvParentLVSelect;
let onConfirmCallback = null;
let isEditMode = false;
let editingPVId = null;

let posDefineSelect, rotDefineSelect, sclDefineSelect;
let currentProjectState;

export function initPVEditor(callbacks) {
    onConfirmCallback = callbacks.onConfirm;

    modalElement = document.getElementById('pvEditorModal');
    titleElement = document.getElementById('pvEditorTitle');
    nameInput = document.getElementById('pvEditorName');
    pvParentLVSelect = document.getElementById('pvEditorParentLV');
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

    // Add a listener to the LV selection dropdown to disable scaling for procedurals
    lvSelect.addEventListener('change', () => {

        // Update parent LV candidates
        updateParentCandidates();
        
        // Only run this logic in Create mode
        if (isEditMode) return;

        const selectedLVName = lvSelect.value;
        const selectedLV = currentProjectState.logical_volumes[selectedLVName];
        const isProcedural = selectedLV && selectedLV.content_type !== 'physvol';
        
        // Get the defines for each type
        const allDefines = currentProjectState.defines || {};
        const posDefines = Object.keys(allDefines).filter(k => allDefines[k].type === 'position');
        const rotDefines = Object.keys(allDefines).filter(k => allDefines[k].type === 'rotation');
        const sclDefines = Object.keys(allDefines).filter(k => allDefines[k].type === 'scale');

        // Re-render all transform UIs with the correct disabled state
        setupTransformUI('position', {x:'0',y:'0',z:'0'}, posDefineSelect, posDefines, { isDisabled: isProcedural });
        setupTransformUI('rotation', {x:'0',y:'0',z:'0'}, rotDefineSelect, rotDefines, { isDisabled: isProcedural });
        setupTransformUI('scale', {x:'1',y:'1',z:'1'}, sclDefineSelect, sclDefines, { isDisabled: isProcedural });
    });
    console.log("Physical Volume Editor Initialized.");
}

export function show(pvData = null, projectState = null, parentContext = null) {
    if (!projectState || !parentContext) {
        alert("Cannot open PV Editor without project state and a parent volume.");
        return;
    }
    
    
    currentProjectState = projectState;
    const allLVs = Object.keys(projectState.logical_volumes);
    const worldRef = projectState.world_volume_ref;

    // --- Populate Parent Dropdown ---
    // Only LVs that can contain physvols are valid parents
    const parentCandidates = allLVs.filter(lvName => 
        projectState.logical_volumes[lvName]?.content_type === 'physvol'
    );
    populateSelect(pvParentLVSelect, parentCandidates);

    // --- Populate Defines ---
    const posDefines = Object.keys(projectState.defines).filter(k => projectState.defines[k].type === 'position');
    const rotDefines = Object.keys(projectState.defines).filter(k => projectState.defines[k].type === 'rotation');
    const sclDefines = Object.keys(projectState.defines).filter(k => projectState.defines[k].type === 'scale');
    populateDefineSelect(posDefineSelect, posDefines);
    populateDefineSelect(rotDefineSelect, rotDefines);
    populateDefineSelect(sclDefineSelect, sclDefines);

    if (pvData && pvData.id) {
        // EDIT MODE

        isEditMode = true;
        editingPVId = pvData.id;

        titleElement.textContent = `Edit Placement: '${pvData.name}'`;
        nameInput.value = pvData.name;
        confirmButton.textContent = "Update Placement";

        // Set and disable the parent LV dropdown
        pvParentLVSelect.value = pvData.parent_lv_name;
        pvParentLVSelect.disabled = true;

        // Set and disable the placed LV dropdown
        populateSelect(lvSelect, allLVs); // Populate with all LVs for context
        lvSelect.value = pvData.volume_ref;
        lvSelect.disabled = true;

        // Check LV type before setting up UI.
        const placedLV = projectState.logical_volumes[pvData.volume_ref];
        const isProcedural = placedLV && placedLV.content_type !== 'physvol';
        setupTransformUI('position', pvData.position, posDefineSelect, posDefines, { isDisabled: isProcedural });
        setupTransformUI('rotation', pvData.rotation, rotDefineSelect, rotDefines, { isDisabled: isProcedural });
        setupTransformUI('scale',    pvData.scale,    sclDefineSelect, sclDefines, { isDisabled: isProcedural });

    } else {
        // CREATE MODE

        isEditMode = false;
        editingPVId = null;

        titleElement.textContent = `Place New Volume`;
        nameInput.value = '';
        confirmButton.textContent = "Place Volume";
        pvParentLVSelect.disabled = false; // Parent LV is selectable

        // Populate the placeable LVs dropdown
        const placeableLVs = allLVs.filter(lvName => lvName !== worldRef && lvName !== parentLVName);
        populateSelect(lvSelect, placeableLVs);
        lvSelect.disabled = false;

        // Pre-select the parent based on the context from where the dialog was opened
        if (parentContext && parentCandidates.includes(parentContext.name)) {
            pvParentLVSelect.value = parentContext.name;
        } else if (worldRef) {
            pvParentLVSelect.value = worldRef; // Fallback to world
        }

        lvSelect.dispatchEvent(new Event('change')); // Trigger change to check initially selected LV
    }
    modalElement.style.display = 'block';
}

// Central function to update the list of valid parents
function updateParentCandidates() {
    const selectedChildLVName = lvSelect.value;
    if (!currentProjectState || !currentProjectState.logical_volumes) return;

    // A valid parent is any LV that is not the selected child.
    // (A more advanced check would prevent cyclical placements, but this is the essential first step).
    const parentCandidates = Object.keys(currentProjectState.logical_volumes)
        .filter(lvName => lvName !== selectedChildLVName && currentProjectState.logical_volumes[lvName].content_type === 'physvol');

    // Preserve the current selection if it's still valid
    const currentParentSelection = pvParentLVSelect.value;
    populateSelect(pvParentLVSelect, parentCandidates);

    if (parentCandidates.includes(currentParentSelection)) {
        pvParentLVSelect.value = currentParentSelection;
    }
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

    // Get the parent LV name from the dropdown
    const parentLVName = pvParentLVSelect.value;

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
function setupTransformUI(type, value, select, defines, options = {}) {
    const { isDisabled = false } = options;

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

    // Apply disabled visual state to the whole container
    const parentGroup = inputsContainer.parentElement;
    if (parentGroup) {
         parentGroup.style.opacity = isDisabled ? '0.5' : '1.0';
         parentGroup.title = isDisabled ? `Scaling is not supported for procedural volumes.` : '';
    }
    select.disabled = isDisabled;

    ['x', 'y', 'z'].forEach(axis => {
        const labelText = axis.toUpperCase();
        const initialValue = displayValues[axis] || '0';
        const inputId = `pv_${type}_${axis}`;

        if (isAbsolute) {
            // Create our full component for absolute expressions
            const comp = ExpressionInput.create(inputId, labelText, initialValue, currentProjectState);
            inputsContainer.appendChild(comp);

            // Disable the input box if the whole container is disabled
            const inputEl = comp.querySelector('.expression-input');
            if (inputEl) inputEl.disabled = isDisabled;
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