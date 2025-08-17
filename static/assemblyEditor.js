import * as ExpressionInput from './expressionInput.js';

let modalElement, titleElement, nameInput, confirmButton, cancelButton, placementsListDiv;
let onConfirmCallback = null;
let isEditMode = false;
let editingAssemblyId = null;
let currentProjectState = null;

// Local state for the list of placements within the assembly
let assemblyPlacements = []; 

export function initAssemblyEditor(callbacks) {
    onConfirmCallback = callbacks.onConfirm;
    modalElement = document.getElementById('assemblyEditorModal');
    titleElement = document.getElementById('assemblyEditorTitle');
    nameInput = document.getElementById('assemblyEditorName');
    placementsListDiv = document.getElementById('assembly-placements-list');
    confirmButton = document.getElementById('assemblyEditorConfirm');
    cancelButton = document.getElementById('assemblyEditorCancel');
    
    cancelButton.addEventListener('click', hide);
    confirmButton.addEventListener('click', handleConfirm);
    document.getElementById('add-assembly-placement-btn').addEventListener('click', addPlacementRow);

    console.log("Assembly Editor Initialized.");
}

export function show(assemblyData = null, projectState = null) {
    currentProjectState = projectState;
    assemblyPlacements = []; // Reset local state

    if (assemblyData) { // EDIT MODE
        isEditMode = true;
        editingAssemblyId = assemblyData.name;
        titleElement.textContent = `Edit Assembly: ${assemblyData.name}`;
        nameInput.value = assemblyData.name;
        nameInput.disabled = true;
        confirmButton.textContent = "Update Assembly";
        // Deep copy the placements into our local state for editing
        assemblyPlacements = JSON.parse(JSON.stringify(assemblyData.placements || []));
    } else { // CREATE MODE
        isEditMode = false;
        editingAssemblyId = null;
        titleElement.textContent = "Create New Assembly";
        nameInput.value = '';
        nameInput.disabled = false;
        confirmButton.textContent = "Create Assembly";
    }

    rebuildPlacementsUI();
    modalElement.style.display = 'block';
}

function hide() {
    modalElement.style.display = 'none';
}

function rebuildPlacementsUI() {
    placementsListDiv.innerHTML = '';

    // Create a combined list of placeable items: LVs and other Assemblies
    const worldRef = currentProjectState.world_volume_ref;
    const availableVolumes = {
        "Logical Volumes": Object.keys(currentProjectState.logical_volumes || {})
            .filter(name => name !== worldRef), // MODIFIED: Filter out the world volume
        "Assemblies": Object.keys(currentProjectState.assemblies || {})
            .filter(name => name !== editingAssemblyId)
    };

    if (assemblyPlacements.length === 0) {
        placementsListDiv.innerHTML = '<p style="text-align: center; color: #888;">No placements defined. Click "+ Add Placement" to begin.</p>';
    }

    assemblyPlacements.forEach((placement, index) => {
        const row = document.createElement('div');
        row.className = 'boolean-recipe-row'; // Reuse this style for the container
        row.innerHTML = `
            <div class="boolean-top-part">
                <div class="property_item" style="flex-grow: 1;">
                    <label for="asm_pv_name_${index}">Name:</label>
                    <input type="text" id="asm_pv_name_${index}" class="pv-name-input" value="${placement.name || ''}" data-index="${index}" placeholder="Placement Name">
                </div>
                <button class="remove-op-btn" data-index="${index}" title="Remove Placement">×</button>
            </div>
            <div class="property_item">
                 <label for="asm_vol_ref_${index}">Volume:</label>
                 <select id="asm_vol_ref_${index}" class="pv-vol-ref-select" data-index="${index}"></select>
            </div>
            <div class="transform-controls-inline" style="border-top: 1px dotted #ccc; margin-top: 5px; padding-top: 5px;">
                <!-- Position and Rotation will be added here -->
            </div>
        `;

        const volRefSelect = row.querySelector('.pv-vol-ref-select');
        populateSelectWithOptions(volRefSelect, availableVolumes);
        volRefSelect.value = placement.volume_ref;
        
        // --- Add Position and Rotation Editors ---
        const transformContainer = row.querySelector('.transform-controls-inline');
        
        const posGroup = document.createElement('div');
        posGroup.className = 'transform-group';
        posGroup.innerHTML = `<span>Position (mm)</span>`;
        ['x', 'y', 'z'].forEach(axis => {
            posGroup.appendChild(ExpressionInput.create(
                `asm_pos_${index}_${axis}`, axis.toUpperCase(), placement.position?.[axis] || '0',
                (newValue) => {
                    if (!assemblyPlacements[index].position) assemblyPlacements[index].position = {};
                    assemblyPlacements[index].position[axis] = newValue;
                }
            ));
        });
        transformContainer.appendChild(posGroup);

        const rotGroup = document.createElement('div');
        rotGroup.className = 'transform-group';
        rotGroup.innerHTML = `<span>Rotation (rad)</span>`;
        ['x', 'y', 'z'].forEach(axis => {
            rotGroup.appendChild(ExpressionInput.create(
                `asm_rot_${index}_${axis}`, axis.toUpperCase(), placement.rotation?.[axis] || '0',
                (newValue) => {
                    if (!assemblyPlacements[index].rotation) assemblyPlacements[index].rotation = {};
                    assemblyPlacements[index].rotation[axis] = newValue;
                }
            ));
        });
        transformContainer.appendChild(rotGroup);

        placementsListDiv.appendChild(row);
    });

    // Attach event listeners after building the DOM
    document.querySelectorAll('.pv-name-input').forEach(input => {
        input.addEventListener('change', (e) => {
            assemblyPlacements[e.target.dataset.index].name = e.target.value;
        });
    });
    document.querySelectorAll('.pv-vol-ref-select').forEach(select => {
        select.addEventListener('change', (e) => {
            assemblyPlacements[e.target.dataset.index].volume_ref = e.target.value;
        });
    });
    document.querySelectorAll('.remove-op-btn').forEach(button => {
        button.addEventListener('click', (e) => {
            assemblyPlacements.splice(parseInt(e.target.dataset.index, 10), 1);
            rebuildPlacementsUI();
        });
    });
}

function addPlacementRow() {
    assemblyPlacements.push({
        name: `placement_${assemblyPlacements.length}`,
        volume_ref: '',
        position: { x: '0', y: '0', z: '0' },
        rotation: { x: '0', y: '0', z: '0' },
        // No scale for placements inside an assembly
    });
    rebuildPlacementsUI();
}

function populateSelectWithOptions(selectElement, optionsData) {
    selectElement.innerHTML = '';
    for (const groupLabel in optionsData) {
        const optgroup = document.createElement('optgroup');
        optgroup.label = groupLabel;
        optionsData[groupLabel].forEach(itemText => {
            const option = document.createElement('option');
            option.value = itemText;
            option.textContent = itemText;
            optgroup.appendChild(option);
        });
        selectElement.appendChild(optgroup);
    }
}

function handleConfirm() {
    const name = nameInput.value.trim();
    if (!name && !isEditMode) {
        alert("Please provide a name for the assembly.");
        return;
    }

    // Validate that all placements have a volume selected
    if (assemblyPlacements.some(p => !p.volume_ref)) {
        alert("All placements must have a volume or assembly selected.");
        return;
    }

    onConfirmCallback({
        isEdit: isEditMode,
        id: isEditMode ? editingAssemblyId : name,
        name: name,
        placements: assemblyPlacements // Send the local state
    });

    hide();
}
