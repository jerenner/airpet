import * as THREE from 'three';

let modalElement, titleElement, nameInput, solidSelect, materialSelect, confirmButton;
let onConfirmCallback = null;
let isEditMode = false;
let editingLVId = null;
let colorInput, alphaInput;

export function initLVEditor(callbacks) {
    onConfirmCallback = callbacks.onConfirm;

    modalElement = document.getElementById('lvEditorModal');
    titleElement = document.getElementById('lvEditorTitle');
    nameInput = document.getElementById('lvEditorName');
    solidSelect = document.getElementById('lvEditorSolid');
    materialSelect = document.getElementById('lvEditorMaterial');
    confirmButton = document.getElementById('confirmLVEditor');
    colorInput = document.getElementById('lvEditorColor');
    alphaInput = document.getElementById('lvEditorAlpha');

    document.getElementById('closeLVEditor').addEventListener('click', hide);
    confirmButton.addEventListener('click', handleConfirm);

    console.log("Logical Volume Editor Initialized.");
}

export function show(lvData = null, projectState = null) {
    if (!projectState) {
        alert("Cannot open LV Editor without a project state.");
        return;
    }

    // Populate dropdowns with available solids and materials
    populateSelect(solidSelect, Object.keys(projectState.solids));
    populateSelect(materialSelect, Object.keys(projectState.materials));

    if (lvData && lvData.name) {
        // --- EDIT MODE ---
        isEditMode = true;
        editingLVId = lvData.name;

        titleElement.textContent = `Edit Logical Volume: ${lvData.name}`;
        nameInput.value = lvData.name;
        nameInput.disabled = true; // Prevent renaming for now

        // Set the selected options
        solidSelect.value = lvData.solid_ref;
        materialSelect.value = lvData.material_ref;

        // Set the color and alpha from existing attributes
        const vis = lvData.vis_attributes || {color: {r:0.8,g:0.8,b:0.8,a:0.5}};
        const color = vis.color;
        // Convert RGB (0-1) to hex string for color input
        colorInput.value = `#${new THREE.Color(color.r, color.g, color.b).getHexString()}`;
        alphaInput.value = color.a;

        confirmButton.textContent = "Update LV";
    } else {
        // --- CREATE MODE ---
        isEditMode = false;
        editingLVId = null;

        titleElement.textContent = "Create New Logical Volume";
        nameInput.value = '';
        nameInput.disabled = false;
        confirmButton.textContent = "Create LV";

        // Set default color/alpha
        colorInput.value = '#cccccc';
        alphaInput.value = 0.5;
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

    const name = nameInput.value.trim();
    if (!name) {
        alert("Please enter a name for the Logical Volume.");
        return;
    }

    const solidRef = solidSelect.value;
    const materialRef = materialSelect.value;
    if (!solidRef || !materialRef) {
        alert("Please select a solid and a material.");
        return;
    }

    // --- Get color and opacity ---
    const colorHex = colorInput.value;
    const alpha = parseFloat(alphaInput.value);
    const threeColor = new THREE.Color(colorHex);
    const visAttributes = {
        color: {
            r: threeColor.r,
            g: threeColor.g,
            b: threeColor.b,
            a: alpha
        }
    };

    onConfirmCallback({
        isEdit: isEditMode,
        id: isEditMode ? editingLVId : name,
        name: name,
        solid_ref: solidRef,
        material_ref: materialRef,
        vis_attributes: visAttributes
    });
    
    hide();
}
