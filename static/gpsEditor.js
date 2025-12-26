// static/gpsEditor.js
import * as ExpressionInput from './expressionInput.js';
import * as APIService from './apiService.js';

let modalElement, titleElement, nameInput, confirmButton, cancelButton;
let particleSelect, energyContainer, shapeSelect, shapeParamsContainer;
let linkedCheckbox, linkedSelect;
let onConfirmCallback = null;
let isEditMode = false;
let editingSourceId = null;
let currentAvailableVolumes = [];

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

    linkedCheckbox = document.getElementById('gpsLinkedVolumeEnabled');
    linkedSelect = document.getElementById('gpsLinkedVolumeSelect'); // This is now an Input

    // Wire up events
    cancelButton.addEventListener('click', hide);
    confirmButton.addEventListener('click', handleConfirm);
    shapeSelect.addEventListener('change', () => renderShapeParamsUI());
    linkedCheckbox.addEventListener('change', toggleLinkedMode);

    console.log("GPS Editor Initialized.");
}

// handleAutoFill function is removed as per instructions.

export function show(sourceData = null, availableVolumes = []) {
    currentAvailableVolumes = availableVolumes || [];

    // Populate Linked Volume Datalist
    const dataList = document.getElementById('gpsLinkedVolumeList');
    dataList.innerHTML = ''; // Clear previous options

    // With datalist and search, we can probably afford to add all of them,
    // as browsers optimize datalists better than selects for rendering.
    // We populate the options with names.
    currentAvailableVolumes.forEach(vol => {
        const option = document.createElement('option');
        option.value = vol.name; // User learns/types by Name
        // We can't consistently rely on 'label' or innerText being shown across browsers
        // But we store the ID in a way we can lookup later? No, we have the map.
        dataList.appendChild(option);
    });

    if (sourceData) { // EDIT MODE
        isEditMode = true;
        editingSourceId = sourceData.id;
        titleElement.textContent = `Edit Particle Source: ${sourceData.name} `;
        nameInput.value = sourceData.name;
        nameInput.disabled = false;
        confirmButton.textContent = "Update Source";

        const commands = sourceData.gps_commands || {};
        particleSelect.value = commands['particle'] || 'e+';

        energyContainer.innerHTML = '';
        energyContainer.appendChild(ExpressionInput.create('gps_energy', 'Energy (keV)', commands['energy'] || '0'));

        let activityVal = '1.0';
        if (sourceData.activity !== undefined && sourceData.activity !== null) {
            activityVal = sourceData.activity;
        }
        energyContainer.appendChild(ExpressionInput.create('gps_activity', 'Activity (Bq)', activityVal));

        const shape = commands['pos/type'] || 'Point';
        shapeSelect.value = shape;

        // Restore Linked State
        linkedCheckbox.checked = !!sourceData.volume_link_id;
        if (sourceData.volume_link_id) {
            // Find the volume helper to get the Name
            const vol = currentAvailableVolumes.find(v => v.id === sourceData.volume_link_id);
            if (vol) {
                linkedSelect.value = vol.name;
            } else {
                // Fallback if the volume was deleted?
                linkedSelect.value = "";
            }
        } else {
            linkedSelect.value = "";
        }

        renderShapeParamsUI(shape, commands, sourceData.position, sourceData.rotation, sourceData.confine_to_pv);

    } else { // CREATE MODE
        isEditMode = false;
        editingSourceId = null;
        titleElement.textContent = "Create New Particle Source";
        nameInput.value = '';
        nameInput.disabled = false;
        confirmButton.textContent = "Create Source";

        particleSelect.value = 'e+';
        energyContainer.innerHTML = '';
        energyContainer.appendChild(ExpressionInput.create('gps_energy', 'Energy (keV)', '0'));
        energyContainer.appendChild(ExpressionInput.create('gps_activity', 'Activity (Bq)', '1000.0'));

        shapeSelect.value = 'Point';
        linkedCheckbox.checked = false;
        linkedSelect.value = "";

        renderShapeParamsUI('Point', {}, { x: '0', y: '0', z: '0' }, { x: '0', y: '0', z: '0' }, null);
    }
    toggleLinkedMode(); // Apply Linked UI state
    modalElement.style.display = 'block';
}


function hide() {
    modalElement.style.display = 'none';
}

function toggleLinkedMode() {
    const isLinked = linkedCheckbox.checked;
    linkedSelect.style.display = isLinked ? 'block' : 'none';

    // Controls to disable/hide
    if (isLinked) {
        // Disable Manual Params
        shapeSelect.disabled = true;
        shapeParamsContainer.style.opacity = '0.3';
        shapeParamsContainer.style.pointerEvents = 'none';
    } else {
        // Enable Manual Params
        shapeSelect.disabled = false;
        shapeParamsContainer.style.opacity = '1.0';
        shapeParamsContainer.style.pointerEvents = 'auto';
    }
}


function renderShapeParamsUI(shapeType = null, commands = {}, position = {}, rotation = {}, confineToPv = null) {
    const shape = shapeType || shapeSelect.value;
    shapeParamsContainer.innerHTML = ''; // Clear previous params

    // --- Position Editor ---
    const posGroup = document.createElement('div');
    posGroup.className = 'transform-group';
    posGroup.innerHTML = `<span>Position (mm)</span>`;
    shapeParamsContainer.appendChild(posGroup);
    ['x', 'y', 'z'].forEach(axis => {
        posGroup.appendChild(ExpressionInput.create(
            `gps_pos_${axis}`, axis.toUpperCase(), position[axis] || '0'
        ));
    });

    // --- Shape Parameters ---
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
            shapeParamsDiv.innerHTML = '';
            const cleanVal = (val, def) => val ? val.replace(' mm', '') : def;

            if (subShape === 'Sphere') {
                shapeParamsDiv.appendChild(ExpressionInput.create('gps_radius', 'Radius (mm)', cleanVal(commands['pos/radius'], '10')));
            } else if (subShape === 'Cylinder') {
                shapeParamsDiv.appendChild(ExpressionInput.create('gps_radius', 'Radius (mm)', cleanVal(commands['pos/radius'], '10')));
                shapeParamsDiv.appendChild(ExpressionInput.create('gps_halfz', 'Half-Z (mm)', cleanVal(commands['pos/halfz'], '10')));
            } else if (subShape === 'Box') {
                shapeParamsDiv.appendChild(ExpressionInput.create('gps_halfx', 'Half-X (mm)', cleanVal(commands['pos/halfx'], '10')));
                shapeParamsDiv.appendChild(ExpressionInput.create('gps_halfy', 'Half-Y (mm)', cleanVal(commands['pos/halfy'], '10')));
                shapeParamsDiv.appendChild(ExpressionInput.create('gps_halfz', 'Half-Z (mm)', cleanVal(commands['pos/halfz'], '10')));
            }
        };

        subShapeSelect.addEventListener('change', renderSubParams);
        renderSubParams();
    }

    // --- Angular Distribution ---
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

    // --- Rotation ---
    const rotGroup = document.createElement('div');
    rotGroup.className = 'transform-group';
    rotGroup.innerHTML = `<span>Orientation (rad)</span>`;
    shapeParamsContainer.appendChild(rotGroup);
    ['x', 'y', 'z'].forEach(axis => {
        rotGroup.appendChild(ExpressionInput.create(
            `gps_rot_${axis}`, axis.toUpperCase(), rotation[axis] || '0'
        ));
    });

    angTypeSelect.addEventListener('change', () => {
        const isIso = angTypeSelect.value === 'iso';
        rotGroup.style.opacity = isIso ? '0.5' : '1.0';
        rotGroup.querySelectorAll('input').forEach(input => input.disabled = isIso);
    });
    // Initial State
    const isIso = angTypeSelect.value === 'iso';
    rotGroup.style.opacity = isIso ? '0.5' : '1.0';
    rotGroup.querySelectorAll('input').forEach(input => input.disabled = isIso);
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
        gpsCommands['energy'] = `${energyValue} `;
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

    // Collect Confinement
    let confineToPv = "";
    let volumeLinkId = null;

    if (linkedCheckbox.checked) {
        // Linked Mode: The input value is the Name. We need to look up the ID.
        confineToPv = linkedSelect.value; // The backend uses the name for `confine_to_pv`

        // Find the corresponding ID for tracking
        const vol = currentAvailableVolumes.find(v => v.name === confineToPv);
        if (vol) {
            volumeLinkId = vol.id;
        } else {
            // Set link to null if not found.
            volumeLinkId = null;
        }
    } else {
        // Free Mode: No confinement allows
        confineToPv = null;
    }

    onConfirmCallback({
        isEdit: isEditMode,
        id: isEditMode ? editingSourceId : name,
        name: name,
        gps_commands: gpsCommands,
        position: position,
        rotation: rotation,
        activity: document.getElementById('gps_activity').value,
        confine_to_pv: confineToPv,
        volume_link_id: volumeLinkId
    });

    hide();
}