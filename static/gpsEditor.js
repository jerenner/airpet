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
    shapeSelect.addEventListener('change', () => renderShapeParamsUI());

    console.log("GPS Editor Initialized.");
}

export function show(sourceData = null) {
    if (sourceData) { // EDIT MODE
        isEditMode = true;
        editingSourceId = sourceData.id;
        titleElement.textContent = `Edit Particle Source: ${sourceData.name}`;
        nameInput.value = sourceData.name;
        nameInput.disabled = false;
        confirmButton.textContent = "Update Source";

        // Pre-fill fields from sourceData.gps_commands
        const commands = sourceData.gps_commands || {};
        particleSelect.value = commands['particle'] || 'e+';

        energyContainer.innerHTML = '';
        energyContainer.appendChild(ExpressionInput.create('gps_energy', 'Energy (keV)', commands['energy'] || '0'));

        const shape = commands['pos/type'] || 'Point';
        shapeSelect.value = shape;
        
        // Pass all necessary data to render the UI correctly
        renderShapeParamsUI(shape, commands, sourceData.position, sourceData.rotation);

    } else { // CREATE MODE
        isEditMode = false;
        editingSourceId = null;
        titleElement.textContent = "Create New Particle Source";
        nameInput.value = '';
        nameInput.disabled = false;
        confirmButton.textContent = "Create Source";

        // Set defaults
        particleSelect.value = 'e+';
        energyContainer.innerHTML = '';
        energyContainer.appendChild(ExpressionInput.create('gps_energy', 'Energy (keV)', '0')); // Default to 0 energy for e+
        shapeSelect.value = 'Point';
        renderShapeParamsUI('Point', {}, {x:'0',y:'0',z:'0'}, {x:'0',y:'0',z:'0'});
    }

    modalElement.style.display = 'block';
}


function hide() {
    modalElement.style.display = 'none';
}


function renderShapeParamsUI(shapeType = null, commands = {}, position = {}, rotation = {}) {
    const shape = shapeType || shapeSelect.value;
    shapeParamsContainer.innerHTML = ''; // Clear previous params

    // --- Add Position Editor for all shapes ---
    const posGroup = document.createElement('div');
    posGroup.className = 'transform-group';
    posGroup.innerHTML = `<span>Position (mm)</span>`;
    shapeParamsContainer.appendChild(posGroup);
    ['x', 'y', 'z'].forEach(axis => {
        posGroup.appendChild(ExpressionInput.create(
            `gps_pos_${axis}`, axis.toUpperCase(), position[axis] || '0'
        ));
    });

    // --- Shape-specific parameters ---
    if (shape === 'Volume' || shape === 'Surface') {
        const subShapeContainer = document.createElement('div');
        subShapeContainer.className = 'property_item';
        subShapeContainer.innerHTML = `
            <label for="gpsVolumeShape">Shape:</label>
            <select id="gpsVolumeShape">
                <option value="Sphere">Sphere</option>
                <option value="Cylinder">Cylinder</option>
                <option value="Box">Box</option>
            </select>`;
        shapeParamsContainer.appendChild(subShapeContainer);

        const subShapeSelect = subShapeContainer.querySelector('#gpsVolumeShape');
        subShapeSelect.value = commands['pos/shape'] || 'Sphere';

        const shapeParamsDiv = document.createElement('div');
        shapeParamsDiv.id = 'gps-subshape-params';
        shapeParamsContainer.appendChild(shapeParamsDiv);
        
        const renderSubParams = () => {
            const subShape = subShapeSelect.value;
            shapeParamsDiv.innerHTML = ''; // Clear sub-params
            if (subShape === 'Sphere') {
                shapeParamsDiv.appendChild(ExpressionInput.create('gps_radius', 'Radius (mm)', commands['pos/radius'] ? commands['pos/radius'].replace(' mm', '') : '10'));
            } else if (subShape === 'Cylinder') {
                shapeParamsDiv.appendChild(ExpressionInput.create('gps_radius', 'Radius (mm)', commands['pos/radius'] ? commands['pos/radius'].replace(' mm', '') : '10'));
                shapeParamsDiv.appendChild(ExpressionInput.create('gps_halfz', 'Half-Z (mm)', commands['pos/halfz'] ? commands['pos/halfz'].replace(' mm', '') : '10'));
            } else if (subShape === 'Box') {
                shapeParamsDiv.appendChild(ExpressionInput.create('gps_halfx', 'Half-X (mm)', commands['pos/halfx'] ? commands['pos/halfx'].replace(' mm', '') : '10'));
                shapeParamsDiv.appendChild(ExpressionInput.create('gps_halfy', 'Half-Y (mm)', commands['pos/halfy'] ? commands['pos/halfy'].replace(' mm', '') : '10'));
                shapeParamsDiv.appendChild(ExpressionInput.create('gps_halfz', 'Half-Z (mm)', commands['pos/halfz'] ? commands['pos/halfz'].replace(' mm', '') : '10'));
            }
        };

        subShapeSelect.addEventListener('change', renderSubParams);
        renderSubParams(); // Initial render
    }

    // --- Add Angular Distribution & Rotation ---
    shapeParamsContainer.appendChild(document.createElement('hr'));
    const angGroup = document.createElement('div');
    angGroup.className = 'property_item';
    angGroup.innerHTML = `
        <label for="gpsAngType">Distribution:</label>
        <select id="gpsAngType">
            <option value="iso">Isotropic (Random)</option>
            <option value="beam1d">Beam (Directed)</option>
        </select>
    `;
    shapeParamsContainer.appendChild(angGroup);
    const angTypeSelect = angGroup.querySelector('#gpsAngType');
    angTypeSelect.value = commands['ang/type'] || 'iso';

    const rotGroup = document.createElement('div');
    rotGroup.className = 'transform-group';
    rotGroup.innerHTML = `<span>Orientation (rad)</span>`;
    shapeParamsContainer.appendChild(rotGroup);
    ['x', 'y', 'z'].forEach(axis => {
        rotGroup.appendChild(ExpressionInput.create(
            `gps_rot_${axis}`, axis.toUpperCase(), rotation[axis] || '0'
        ));
    });

    const isIso = angTypeSelect.value === 'iso';
    rotGroup.style.opacity = isIso ? '0.5' : '1.0';
    rotGroup.querySelectorAll('input').forEach(input => input.disabled = isIso);

    angTypeSelect.addEventListener('change', (e) => {
        const isNowIso = e.target.value === 'iso';
        rotGroup.style.opacity = isNowIso ? '0.5' : '1.0';
        rotGroup.querySelectorAll('input').forEach(input => input.disabled = isNowIso);
    });
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
    // For e+, the energy spectrum is usually handled by the physics list,
    // so we set a monoenergetic energy of 0 keV by default unless specified otherwise.
    const energyValue = document.getElementById('gps_energy').value.trim();
    if (particleSelect.value === 'e+' && energyValue === '') {
        gpsCommands['energy'] = '0';
    } else {
        gpsCommands['energy'] = `${energyValue}`;
    }
    
    gpsCommands['ene/type'] = 'Mono'; // For simplicity, always Mono for now

    const shape = shapeSelect.value;
    gpsCommands['pos/type'] = shape;

    if (shape === 'Volume' || shape === 'Surface') {
        const subShape = document.getElementById('gpsVolumeShape').value;
        gpsCommands['pos/shape'] = subShape;
        if (subShape === 'Sphere') {
            gpsCommands['pos/radius'] = document.getElementById('gps_radius').value + ' mm';
        } else if (subShape === 'Cylinder') {
            gpsCommands['pos/radius'] = document.getElementById('gps_radius').value + ' mm';
            gpsCommands['pos/halfz'] = document.getElementById('gps_halfz').value + ' mm';
        } else if (subShape === 'Box') {
            gpsCommands['pos/halfx'] = document.getElementById('gps_halfx').value + ' mm';
            gpsCommands['pos/halfy'] = document.getElementById('gps_halfy').value + ' mm';
            gpsCommands['pos/halfz'] = document.getElementById('gps_halfz').value + ' mm';
        }
    }

    // Also collect the position
    const position = {
        x: document.getElementById('gps_pos_x').value,
        y: document.getElementById('gps_pos_y').value,
        z: document.getElementById('gps_pos_z').value
    };

    // Collect angular commands
    const angType = document.getElementById('gpsAngType').value;
    gpsCommands['ang/type'] = angType;

    // Collect rotation
    const rotation = {
        x: document.getElementById('gps_rot_x').value,
        y: document.getElementById('gps_rot_y').value,
        z: document.getElementById('gps_rot_z').value
    };

    onConfirmCallback({
        isEdit: isEditMode,
        id: isEditMode ? editingSourceId : name,
        name: name,
        gps_commands: gpsCommands,
        position: position,
        rotation: rotation
    });

    hide();
}