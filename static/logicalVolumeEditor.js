import * as THREE from 'three';
import * as ExpressionInput from './expressionInput.js';

let modalElement, titleElement, nameInput, solidSelect, materialSelect, confirmButton;
let onConfirmCallback = null;
let isEditMode = false;
let editingLVId = null;
let colorInput, alphaInput;
let currentProjectState = null;
let contentTypeRadios, proceduralParamsDiv;

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
    contentTypeRadios = document.getElementById('lvContentTypeRadios');
    proceduralParamsDiv = document.getElementById('lv-procedural-params');

    document.getElementById('closeLVEditor').addEventListener('click', hide);
    confirmButton.addEventListener('click', handleConfirm);

    // Add event listener to radio buttons
    contentTypeRadios.addEventListener('change', (event) => {
        renderProceduralParams(event.target.value);
    });

    console.log("Logical Volume Editor Initialized.");
}

export function show(lvData = null, projectState = null) {
    currentProjectState = projectState;
    if (!projectState) {
        alert("Cannot open LV Editor without a project state.");
        return;
    }

    // Populate dropdowns with available solids and materials
    populateSelect(solidSelect, Object.keys(projectState.solids));
    populateSelect(materialSelect, Object.keys(projectState.materials));

    // Disable content type switching when editing
    const radios = contentTypeRadios.querySelectorAll('input[type="radio"]');
    radios.forEach(radio => radio.disabled = (lvData && lvData.name));

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
        const vis = lvData.vis_attributes || {color: {r:0.8,g:0.8,b:0.8,a:1.0}};
        const color = vis.color;
        // Convert RGB (0-1) to hex string for color input
        colorInput.value = `#${new THREE.Color(color.r, color.g, color.b).getHexString()}`;
        alphaInput.value = color.a;

        confirmButton.textContent = "Update LV";

        // Set the correct radio button and render its params
        const contentType = lvData.content_type || 'physvol';
        
        document.getElementById(`lv_type_${contentType}`).checked = true;
        renderProceduralParams(contentType, lvData.content);

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
        alphaInput.value = 1.0;

        // Default to standard physvol type
        document.getElementById('lv_type_physvol').checked = true;
        renderProceduralParams('physvol');
    }

    modalElement.style.display = 'block';
}

function renderProceduralParams(type, data = null) {
    proceduralParamsDiv.innerHTML = ''; // Clear previous params
    proceduralParamsDiv.style.display = 'block';

    if (type === 'replica') {
        // We need a dropdown of all LVs that can be replicated
        const allLVs = Object.keys(currentProjectState.logical_volumes);
        const availableLVs = isEditMode ? allLVs.filter(name => name !== editingLVId) : allLVs;
        
        const replicaLVSelect = document.createElement('select');
        replicaLVSelect.id = 'replica_lv_ref';
        populateSelect(replicaLVSelect, availableLVs);
        if (data) replicaLVSelect.value = data.volume_ref;
        
        const item = document.createElement('div');
        item.className = 'property_item';
        item.innerHTML = `<label for="replica_lv_ref">Volume to Replicate:</label>`;
        item.appendChild(replicaLVSelect);
        proceduralParamsDiv.appendChild(item);
        
        // Use ExpressionInput for number, width, offset
        proceduralParamsDiv.appendChild(ExpressionInput.create('replica_number', 'Number of Copies', data?.number || '1', currentProjectState));
        proceduralParamsDiv.appendChild(ExpressionInput.create('replica_width', 'Width (mm)', data?.width || '100', currentProjectState));
        proceduralParamsDiv.appendChild(ExpressionInput.create('replica_offset', 'Offset (mm)', data?.offset || '0', currentProjectState));

        // Radio buttons for axis
        const axisDiv = document.createElement('div');
        axisDiv.className = 'property_item';
        axisDiv.innerHTML = `<label>Axis:</label>
                             <div>
                                <input type="radio" name="replica_axis" value="x" id="replica_axis_x" checked><label for="replica_axis_x">X</label>
                                <input type="radio" name="replica_axis" value="y" id="replica_axis_y"><label for="replica_axis_y">Y</label>
                                <input type="radio" name="replica_axis" value="z" id="replica_axis_z"><label for="replica_axis_z">Z</label>
                             </div>`;
        proceduralParamsDiv.appendChild(axisDiv);

        if (data && data.direction) {
            if (parseFloat(data.direction.y) === 1) document.getElementById('replica_axis_y').checked = true;
            else if (parseFloat(data.direction.z) === 1) document.getElementById('replica_axis_z').checked = true;
            else document.getElementById('replica_axis_x').checked = true;
        }
    } else if (type === 'division') {
        const allLVs = Object.keys(currentProjectState.logical_volumes);
        const availableLVs = isEditMode ? allLVs.filter(name => name !== editingLVId) : allLVs;

        const divisionLVSelect = document.createElement('select');
        divisionLVSelect.id = 'division_lv_ref';
        populateSelect(divisionLVSelect, availableLVs);
        if (data) divisionLVSelect.value = data.volume_ref;

        const item = document.createElement('div');
        item.className = 'property_item';
        item.innerHTML = `<label for="division_lv_ref">Volume to Divide:</label>`;
        item.appendChild(divisionLVSelect);
        proceduralParamsDiv.appendChild(item);

        proceduralParamsDiv.appendChild(ExpressionInput.create('division_number', 'Number of Divisions', data?.number || '1', currentProjectState));
        proceduralParamsDiv.appendChild(ExpressionInput.create('division_width', 'Width (mm)', data?.width || '0', currentProjectState));
        proceduralParamsDiv.appendChild(ExpressionInput.create('division_offset', 'Offset (mm)', data?.offset || '0', currentProjectState));
        
        // Dropdown for axis
        const axisDiv = document.createElement('div');
        axisDiv.className = 'property_item';
        axisDiv.innerHTML = `<label for="division_axis">Axis:</label>
                             <select id="division_axis">
                                <option value="kXAxis">X Axis</option>
                                <option value="kYAxis">Y Axis</option>
                                <option value="kZAxis">Z Axis</option>
                                <option value="kRho">Rho</option>
                                <option value="kPhi">Phi</option>
                             </select>`;
        proceduralParamsDiv.appendChild(axisDiv);

        if (data && data.axis) {
            document.getElementById('division_axis').value = data.axis;
        }
    } else if (type === 'parameterised') {
        proceduralParamsDiv.innerHTML = `<p style="color:#888;"><i>Editor for '${type}' content not yet implemented.</i></p>`;
    } else if (type === 'physvol') {
        proceduralParamsDiv.style.display = 'none'; // Nothing to show for standard LVs
    } else {
        proceduralParamsDiv.innerHTML = `<p style="color:#888;"><i>Editor for '${type}' content not yet implemented.</i></p>`;
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

    const contentType = document.querySelector('input[name="lv_content_type"]:checked').value;
    let content = null;

    if (contentType === 'replica') {
        const selectedAxis = document.querySelector('input[name="replica_axis"]:checked').value;
        content = {
            type: 'replica',
            volume_ref: document.getElementById('replica_lv_ref').value,
            number: document.getElementById('replica_number').value,
            width: document.getElementById('replica_width').value,
            offset: document.getElementById('replica_offset').value,
            direction: {
                x: selectedAxis === 'x' ? '1' : '0',
                y: selectedAxis === 'y' ? '1' : '0',
                z: selectedAxis === 'z' ? '1' : '0'
            }
        };
    } else if (contentType === 'division') {
        content = {
            type: 'division',
            volume_ref: document.getElementById('division_lv_ref').value,
            number: document.getElementById('division_number').value,
            width: document.getElementById('division_width').value,
            offset: document.getElementById('division_offset').value,
            axis: document.getElementById('division_axis').value
        };
    } else {
        // For 'physvol', content is an empty list by default upon creation.
        content = [];
    }

    onConfirmCallback({
        isEdit: isEditMode,
        id: isEditMode ? editingLVId : name,
        name: name,
        solid_ref: solidRef,
        material_ref: materialRef,
        vis_attributes: visAttributes,
        content_type: contentType,
        content: content
    });
    
    hide();
}
