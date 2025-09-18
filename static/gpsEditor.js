// static/gpsEditor.js
import * as ExpressionInput from './expressionInput.js';

let modalElement, titleElement, nameInput, confirmButton, cancelButton;
let particleSelect, energyContainer, shapeSelect, shapeParamsContainer;
let onConfirmCallback = null;
let isEditMode = false;
let editingSourceId = null;

export function initGpsEditor(callbacks) {
    onConfirmCallback = callbacks.onConfirm;
    modalElement = document.getElementById('gpsEditorModal');
    titleElement = document.getElementById('gpsEditorTitle');
    nameInput = document.getElementById('gpsEditorName');
    
    particleSelect = document.getElementById('gpsEditorParticle');
    energyContainer = document.getElementById('gps-energy-params');
    shapeSelect = document.getElementById('gpsEditorShape');
    shapeParamsContainer = document.getElementById('gps-shape-params');
    
    confirmButton = document.getElementById('gpsEditorConfirm');
    cancelButton = document.getElementById('gpsEditorCancel');

    cancelButton.addEventListener('click', hide);
    confirmButton.addEventListener('click', handleConfirm);
    shapeSelect.addEventListener('change', renderShapeParamsUI);

    console.log("GPS Editor Initialized.");
}

export function show(sourceData = null) {
    if (sourceData) { // EDIT MODE
        isEditMode = true;
        editingSourceId = sourceData.id;
        titleElement.textContent = `Edit Particle Source: ${sourceData.name}`;
        nameInput.value = sourceData.name;
        nameInput.disabled = true;
        confirmButton.textContent = "Update Source";

        // Pre-fill fields from sourceData.gps_commands
        const commands = sourceData.gps_commands || {};
        particleSelect.value = commands['particle'] || 'gamma';
        energyContainer.innerHTML = '';
        energyContainer.appendChild(ExpressionInput.create('gps_energy', 'Energy (keV)', commands['energy'] || '511'));
        
        const shape = commands['pos/type'] || 'Point';
        shapeSelect.value = shape;
        renderShapeParamsUI(shape, commands, sourceData.position);

    } else { // CREATE MODE
        isEditMode = false;
        editingSourceId = null;
        titleElement.textContent = "Create New Particle Source";
        nameInput.value = '';
        nameInput.disabled = false;
        confirmButton.textContent = "Create Source";
        
        // Set defaults
        particleSelect.value = 'gamma';
        energyContainer.innerHTML = '';
        energyContainer.appendChild(ExpressionInput.create('gps_energy', 'Energy (keV)', '511'));
        shapeSelect.value = 'Point';
        renderShapeParamsUI();
    }
    modalElement.style.display = 'block';
}

function hide() {
    modalElement.style.display = 'none';
}

function renderShapeParamsUI(shapeType = null, commands = {}, position = {}) {
    const shape = shapeType || shapeSelect.value;
    shapeParamsContainer.innerHTML = ''; // Clear previous params

    // --- ADD POSITION EDITOR FOR ALL SHAPES ---
    const posGroup = document.createElement('div');
    posGroup.className = 'transform-group';
    posGroup.innerHTML = `<span>Position (mm)</span>`;
    shapeParamsContainer.appendChild(posGroup);
    ['x', 'y', 'z'].forEach(axis => {
        posGroup.appendChild(ExpressionInput.create(
            `gps_pos_${axis}`, axis.toUpperCase(), position[axis] || '0'
        ));
    });
    shapeParamsContainer.appendChild(document.createElement('hr'));

    switch (shape) {
        case 'Point':
            // No extra parameters for a point source, position is handled separately.
            break;
        case 'Volume':
            const volShapeDiv = document.createElement('div');
            volShapeDiv.className = 'property_item';
            volShapeDiv.innerHTML = `
                <label for="gpsVolumeShape">Volume Type:</label>
                <select id="gpsVolumeShape">
                    <option value="Sphere">Sphere</option>
                    <option value="Cylinder">Cylinder</option>
                    <option value="Box">Box</option>
                </select>`;
            shapeParamsContainer.appendChild(volShapeDiv);
            shapeParamsContainer.appendChild(ExpressionInput.create('gps_radius', 'Radius (mm)', commands['pos/radius'] || '10'));
            break;
        case 'Surface':
             const surfShapeDiv = document.createElement('div');
             surfShapeDiv.className = 'property_item';
             surfShapeDiv.innerHTML = `
                <label for="gpsSurfaceShape">Surface Type:</label>
                <select id="gpsSurfaceShape">
                    <option value="Sphere">Sphere</option>
                    <option value="Cylinder">Cylinder</option>
                    <option value="Box">Box</option>
                </select>`;
            shapeParamsContainer.appendChild(surfShapeDiv);
            shapeParamsContainer.appendChild(ExpressionInput.create('gps_radius_surf', 'Radius (mm)', commands['pos/radius'] || '10'));
            break;
    }
}

function handleConfirm() {
    const name = nameInput.value.trim();
    if (!name && !isEditMode) {
        alert("Please provide a name for the source.");
        return;
    }

    // Collect all GPS commands into a dictionary
    const gpsCommands = {};
    gpsCommands['particle'] = particleSelect.value;
    gpsCommands['energy'] = document.getElementById('gps_energy').value + ' keV';
    
    const shape = shapeSelect.value;
    gpsCommands['pos/type'] = shape;

    if (shape === 'Volume' || shape === 'Surface') {
        const subShape = (shape === 'Volume') 
            ? document.getElementById('gpsVolumeShape').value
            : document.getElementById('gpsSurfaceShape').value;
        const radius = (shape === 'Volume')
            ? document.getElementById('gps_radius').value
            : document.getElementById('gps_radius_surf').value;
        
        gpsCommands['pos/shape'] = subShape;
        gpsCommands['pos/radius'] = radius + ' mm';
        // Can add more shape parameters here later (halfz, etc.)
    }

    // Also collect the position
    const position = {
        x: document.getElementById('gps_pos_x').value,
        y: document.getElementById('gps_pos_y').value,
        z: document.getElementById('gps_pos_z').value
    };

    onConfirmCallback({
        isEdit: isEditMode,
        id: isEditMode ? editingSourceId : name,
        name: name,
        gps_commands: gpsCommands,
        position: position 
    });
    hide();
}
