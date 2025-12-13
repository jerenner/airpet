// static/gpsEditor.js
import * as ExpressionInput from './expressionInput.js';

let modalElement, titleElement, nameInput, confirmButton, cancelButton;
let particleSelect, energyContainer, shapeSelect, shapeParamsContainer;
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

    cancelButton.addEventListener('click', hide);
    confirmButton.addEventListener('click', handleConfirm);
    shapeSelect.addEventListener('change', () => renderShapeParamsUI());

    console.log("GPS Editor Initialized.");
}

export function show(sourceData = null, availableVolumes = []) {
    currentAvailableVolumes = availableVolumes || [];

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

        console.log("Edit Source Data:", sourceData);
        // Pass all necessary data to render the UI correctly
        renderShapeParamsUI(shape, commands, sourceData.position, sourceData.rotation, sourceData.confine_to_pv);

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
        renderShapeParamsUI('Point', {}, { x: '0', y: '0', z: '0' }, { x: '0', y: '0', z: '0' }, null);
    }

    modalElement.style.display = 'block';
}


function hide() {
    modalElement.style.display = 'none';
}


function renderShapeParamsUI(shapeType = null, commands = {}, position = {}, rotation = {}, confineToPv = null) {
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

    // --- Confinement UI ---
    shapeParamsContainer.appendChild(document.createElement('hr'));
    const confineGroup = document.createElement('div');
    confineGroup.className = 'property_item';
    confineGroup.innerHTML = `
        <div style="display: flex; align-items: center; margin-bottom: 5px;">
            <input type="checkbox" id="gpsConfineEnabled" style="margin-right: 8px;">
            <label for="gpsConfineEnabled" style="margin: 0;">Confine to Volume</label>
        </div>
        <select id="gpsConfineVolume" style="width: 100%; display: none;">
            <option value="">-- Select Volume --</option>
        </select>
    `;
    shapeParamsContainer.appendChild(confineGroup);

    const confineCheckbox = confineGroup.querySelector('#gpsConfineEnabled');
    const confineSelect = confineGroup.querySelector('#gpsConfineVolume');

    // Populate volumes
    if (currentAvailableVolumes && currentAvailableVolumes.length > 0) {
        currentAvailableVolumes.forEach(vol => {
            const option = document.createElement('option');
            option.value = vol.name; // Use name as the confinement target
            option.textContent = vol.name;
            confineSelect.appendChild(option);
        });
    } else {
        const option = document.createElement('option');
        option.textContent = "No volumes available";
        option.disabled = true;
        confineSelect.appendChild(option);
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

    // --- Handling Confinement UI Interactions ---
    const updateConfinementState = () => {
        const isConfined = confineCheckbox.checked;
        confineSelect.style.display = isConfined ? 'block' : 'none';

        // When confined, we WANT the user to be able to set the sampling volume (Shape & Dimensions).
        // But we must enforce Shape = Volume (or Surface) for confinement to make sense.
        // Actually, you can confine a Point source, but it's inefficient.
        // Standard practice is Volume.

        if (isConfined) {
            // If Point or Beam is selected, switch to Volume (default box)
            if (shapeSelect.value !== 'Volume' && shapeSelect.value !== 'Surface') {
                shapeSelect.value = 'Volume';
                // Trigger change to render sub-params
                renderShapeParamsUI();
                return; // renderShapeParamsUI will call us back if we set it up that way, 
                // but actually we passed parameters in render.
                // Let's just manually trigger the redraw or let the user see the switch.
            }
        }

        // We do NOT disable the other inputs anymore.
        // The user needs to define the "Search Volume" (e.g. Box 100mm) that GPS will sample from.
        // GPS then checks if point is in Confine Volume.

        // Ensure visual feedback is clear.
        // Maybe highlight that these params define the "Search Region".
    };

    // Attach listener
    confineCheckbox.addEventListener('change', updateConfinementState);

    // Apply Initial State
    if (confineToPv) {
        confineCheckbox.checked = true;
        confineSelect.value = confineToPv;
    }
    updateConfinementState();
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

    // Collect Confinement
    let confineToPv = "";
    const confineCheckbox = document.getElementById('gpsConfineEnabled');
    if (confineCheckbox && confineCheckbox.checked) {
        const confineSelect = document.getElementById('gpsConfineVolume');
        confineToPv = confineSelect.value; // Can be "" if selection is empty, which is fine
    }

    onConfirmCallback({
        isEdit: isEditMode,
        id: isEditMode ? editingSourceId : name,
        name: name,
        gps_commands: gpsCommands,
        position: position,
        rotation: rotation,
        confine_to_pv: confineToPv
    });

    hide();
}