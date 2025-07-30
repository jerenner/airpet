// static/solidEditor.js
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { TransformControls } from 'three/addons/controls/TransformControls.js';
import { createPrimitiveGeometry } from './sceneManager.js';
import { Brush, Evaluator, ADDITION, SUBTRACTION, INTERSECTION } from 'three-bvh-csg';
import * as APIService from './apiService.js';
import * as ExpressionInput from './expressionInput.js';

// --- Module State ---
let scene, camera, renderer, controls;
let transformControls;
let currentSolidMesh = null;
let onConfirmCallback = null;
let isEditMode = false;         // flag to track mode
let editingSolidId = null;      // store the ID/name of the solid being edited
let currentProjectState = null; // to hold the project state
let createLVCheckbox, placePVCheckbox, lvOptionsDiv, lvMaterialSelect;

// State for boolean operations
let booleanSolidA = null; // Will hold { name, type, parameters }
let booleanSolidB = null;

// State variable for the boolean recipe
let booleanRecipe = []; // An array of {op, solid, transform}

const editorContainer = document.getElementById('solid_preview_container');
const modalElement = document.getElementById('solidEditorModal');
const titleElement = document.getElementById('solidEditorTitle');
const nameInput = document.getElementById('solidEditorName');
const typeSelect = document.getElementById('solidEditorType');
const dynamicParamsDiv = document.getElementById('solid-editor-dynamic-params');
const confirmButton = document.getElementById('confirmSolidEditor');

// --- Initialization ---
export function initSolidEditor(callbacks) {
    onConfirmCallback = callbacks.onConfirm;

    // Basic Scene Setup
    scene = new THREE.Scene();
    scene.background = new THREE.Color(0xcccccc);
    
    // Camera
    const aspect = editorContainer.clientWidth / editorContainer.clientHeight;
    camera = new THREE.PerspectiveCamera(50, aspect, 0.1, 10000);
    camera.position.set(150, 150, 300);
    scene.add(camera);

    // Lights
    const ambient = new THREE.AmbientLight(0xffffff, 0.7);
    scene.add(ambient);
    const directional = new THREE.DirectionalLight(0xffffff, 0.8);
    directional.position.set(1, 1, 1);
    camera.add(directional); // Attach to camera

    // Renderer
    renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setPixelRatio(window.devicePixelRatio);
    renderer.setSize(editorContainer.clientWidth, editorContainer.clientHeight);
    editorContainer.appendChild(renderer.domElement);

    // Controls
    controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;

    // TransformControls for the editor's scene
    transformControls = new TransformControls(camera, renderer.domElement);
    transformControls.addEventListener('dragging-changed', (event) => {
        controls.enabled = !event.value; // Disable orbit while transforming
    });
    transformControls.addEventListener('objectChange', () => {
        // When the gizmo moves the object, update the UI and the preview
        if (transformControls.object) {
            updateTransformUIFromGizmo();
            updatePreview();
        }
    });
    scene.add(transformControls);

    // Checkboxes
    createLVCheckbox = document.getElementById('createLVCheckbox');
    placePVCheckbox = document.getElementById('placePVCheckbox');
    lvOptionsDiv = document.getElementById('lvOptions');
    lvMaterialSelect = document.getElementById('lvMaterialSelect');

    // Event Listeners
    document.getElementById('closeSolidEditor').addEventListener('click', hide);
    document.getElementById('recenter-solid-preview-btn').addEventListener('click', recenterCamera);
    typeSelect.addEventListener('change', renderParamsUI);
    confirmButton.addEventListener('click', handleConfirm);

    createLVCheckbox.addEventListener('change', () => {
        const isChecked = createLVCheckbox.checked;
        lvOptionsDiv.style.display = isChecked ? 'block' : 'none';
        
        // The "Place PV" checkbox should only be enabled if "Create LV" is also checked
        placePVCheckbox.disabled = !isChecked;
        if (!isChecked) {
            placePVCheckbox.checked = false; // Uncheck it if its parent is unchecked
        }
    });
    
    // Start animation loop
    animate();
    console.log("Solid Editor Initialized.");
}

function animate() {
    requestAnimationFrame(animate);
    controls.update();
    renderer.render(scene, camera);
}

function onWindowResize() {
    if (!renderer || !camera) return;
    const { clientWidth, clientHeight } = editorContainer;
    camera.aspect = clientWidth / clientHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(clientWidth, clientHeight);
}

// --- Public API ---
export function show(solidData = null, projectState = null) {
    currentProjectState = projectState; // Cache the state
    booleanRecipe = []; // Reset recipe

    // Populate the material dropdown for the quick-add feature
    if (projectState && projectState.materials) {
        populateSelect(lvMaterialSelect, Object.keys(projectState.materials));
    } else {
        populateSelect(lvMaterialSelect, []); // Clear it if no materials
    }
    
    // Reset checkboxes when opening
    createLVCheckbox.checked = false;
    placePVCheckbox.checked = false;
    placePVCheckbox.disabled = true;
    lvOptionsDiv.style.display = 'none';

    if (solidData && solidData.name) {
        // --- EDIT MODE ---
        isEditMode = true;
        editingSolidId = solidData.name; // For solids, the ID is the name
        
        titleElement.textContent = `Edit Solid: ${solidData.name}`;
        nameInput.value = solidData.name;
        nameInput.disabled = true; // Prevent renaming for now, it's more complex
        typeSelect.value = solidData.type;
        typeSelect.disabled = true; // Prevent changing solid type
        
        confirmButton.textContent = "Update Solid";

        // --- Pre-fill boolean state if applicable ---
        if (solidData.type === 'boolean') {
            // It's a "virtual" boolean solid. The recipe is right here.
            const savedRecipe = solidData.raw_parameters.recipe || [];
            booleanRecipe = JSON.parse(JSON.stringify(savedRecipe)).map(item => {
                // After deep copying, we need to replace the plain solid_ref dict with the actual solid object
                const solidObject = currentProjectState.solids[item.solid_ref];
                return {
                    ...item, // This includes op and transform
                    solid: solidObject, 
                };
            });
        }
        
        // Populate parameters after the UI is rendered
        renderParamsUI(solidData.raw_parameters);

    } else {
        // --- CREATE MODE ---
        isEditMode = false;
        editingSolidId = null;

        titleElement.textContent = "Create New Solid";
        nameInput.value = '';
        nameInput.disabled = false;
        typeSelect.value = 'box';
        typeSelect.disabled = false;
        confirmButton.textContent = "Create Solid";

        // When creating a new boolean, start with an empty base slot.
        if (typeSelect.value === 'boolean') {
             booleanRecipe.push({ op: 'base', solid: null, transform: null });
        }

        renderParamsUI();
    }
    
    // Hide quick-add options in edit mode, as they don't apply
    document.querySelector('.quick-add-options').style.display = isEditMode ? 'none' : 'flex';

    modalElement.style.display = 'block';
    onWindowResize();

    // Automatically set camera: use a small timeout to ensure the preview mesh has 
    // been rendered once before trying to calculate its bounding box.
    setTimeout(recenterCamera, 50);
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

export function hide() {
    modalElement.style.display = 'none';
}

// --- Internal Logic ---


// Helper to create expression-based input box.
function createExpressionInput(id, label, initialValue = '0') {
    return `
        <div class="property_item" style="flex-direction: column; align-items: flex-start;">
            <label for="${id}">${label}:</label>
            <div style="display: flex; width: 80%; align-items: center;">
                <input type="text" id="${id}" class="expression-input" value="${initialValue}" style="flex-grow: 1; font-family: monospace;">
                <input type="text" id="${id}-result" class="expression-result" style="width: 80px; margin-left: 5px;" readonly disabled>
            </div>
        </div>
    `;
}

// Overloaded helper for inline boolean transforms
function createInlineExpressionInput(idPrefix, axis, initialValue = '0') {
    return `
        <input type="text" id="${idPrefix}_${axis}" class="inline-trans expression-input" value="${initialValue}" data-id-prefix="${idPrefix}" data-axis="${axis}">
    `;
}

function attachLiveEvaluation(inputId, resultId) {
    const inputEl = document.getElementById(inputId);
    const resultEl = document.getElementById(resultId);
    
    const evaluate = async () => {
        const expression = inputEl.value;
        if (!expression.trim()) {
            resultEl.value = '';
            resultEl.style.borderColor = '#ccc';
            return;
        }
        try {
            const response = await APIService.evaluateExpression(expression, currentProjectState);
            if (response.success) {
                resultEl.value = response.result.toPrecision(4);
                resultEl.style.borderColor = '#ccc';
                resultEl.title = `Evaluated: ${response.result}`;
            } else {
                resultEl.value = 'Error';
                resultEl.style.borderColor = 'red';
                resultEl.title = response.error;
            }
        } catch (error) {
            resultEl.value = 'Error';
            resultEl.style.borderColor = 'red';
            resultEl.title = error.message;
        }
    };
    
    inputEl.addEventListener('input', () => {
        // Debounce evaluation to avoid spamming the server on every keystroke
        clearTimeout(inputEl.debounceTimer);
        inputEl.debounceTimer = setTimeout(evaluate, 300);
    });
    inputEl.addEventListener('change', evaluate); // Also on change for blur events
    evaluate(); // Trigger initial evaluation
}

function renderParamsUI(params = {}) {
    dynamicParamsDiv.innerHTML = '';
    const type = typeSelect.value;
    const isBoolean = type === 'boolean';
    const isScaled = type === 'scaledSolid';

    if (isBoolean) {
        if (booleanRecipe.length === 0) {
            booleanRecipe.push({ op: 'base', solid: null, transform: { position: {x:'0', y:'0', z:'0'}, rotation: {x:'0', y:'0', z:'0'} } });
        }
        document.getElementById('solid-ingredients-panel').style.display = 'flex';
        dynamicParamsDiv.innerHTML = `
            <div id="boolean-recipe-list"></div>
            <button id="add-boolean-op-btn" class="add_button" style="margin-top: 10px;">+ Add Operation</button>
        `;
        document.getElementById('add-boolean-op-btn').addEventListener('click', addBooleanOperation);
        rebuildBooleanUI();
    }
    else if (isScaled) { 
        document.getElementById('solid-ingredients-panel').style.display = 'none';
        
        // Dropdown to select the solid to be scaled
        const solidItem = document.createElement('div');
        solidItem.className = 'property_item';
        solidItem.innerHTML = `<label for="scaled_solid_ref">Solid to Scale:</label>`;
        const solidRefSelect = document.createElement('select');
        solidRefSelect.id = 'scaled_solid_ref';
        // Populate with all solids EXCEPT the one being edited (to prevent self-reference)
        const allSolids = Object.keys(currentProjectState.solids || {});
        const availableSolids = isEditMode ? allSolids.filter(s => s !== editingSolidId) : allSolids;
        populateSelect(solidRefSelect, availableSolids);
        solidItem.appendChild(solidRefSelect);
        dynamicParamsDiv.appendChild(solidItem);

        // Expression inputs for the scale factors
        dynamicParamsDiv.appendChild(ExpressionInput.create('p_scale_x', 'Scale X', params?.scale?.x || '1.0', currentProjectState));
        dynamicParamsDiv.appendChild(ExpressionInput.create('p_scale_y', 'Scale Y', params?.scale?.y || '1.0', currentProjectState));
        dynamicParamsDiv.appendChild(ExpressionInput.create('p_scale_z', 'Scale Z', params?.scale?.z || '1.0', currentProjectState));

        // Pre-select the solid if in edit mode
        if (params && params.solid_ref) {
            solidRefSelect.value = params.solid_ref;
        }

        // Add change listener to update preview
        dynamicParamsDiv.addEventListener('change', updatePreview);

    } else {
        document.getElementById('solid-ingredients-panel').style.display = 'none';
        
        const p = (key, defaultVal) => params[key] !== undefined ? params[key] : defaultVal;

        const uiBuilders = {
            box: () => [ 
                ExpressionInput.create('p_x', 'Size X (mm)', p('x', '100'), currentProjectState),
                ExpressionInput.create('p_y', 'Size Y (mm)', p('y', '100'), currentProjectState),
                ExpressionInput.create('p_z', 'Size Z (mm)', p('z', '100'), currentProjectState) 
            ],
            tube: () => [
                ExpressionInput.create('p_rmin', 'Inner Radius (mm)', p('rmin', '0'), currentProjectState),
                ExpressionInput.create('p_rmax', 'Outer Radius (mm)', p('rmax', '50'), currentProjectState),
                ExpressionInput.create('p_dz', 'Full Length Z (mm)', p('dz', '200'), currentProjectState),
                ExpressionInput.create('p_startphi', 'Start Phi (rad)', p('startphi', '0'), currentProjectState),
                ExpressionInput.create('p_deltaphi', 'Delta Phi (rad)', p('deltaphi', '2*pi'), currentProjectState)
            ],
            cone: () => [
                ExpressionInput.create('p_rmin1', 'Inner Radius 1 (mm)', p('rmin1', '0'), currentProjectState),
                ExpressionInput.create('p_rmax1', 'Outer Radius 1 (mm)', p('rmax1', '50'), currentProjectState),
                ExpressionInput.create('p_rmin2', 'Inner Radius 2 (mm)', p('rmin2', '0'), currentProjectState),
                ExpressionInput.create('p_rmax2', 'Outer Radius 2 (mm)', p('rmax2', '75'), currentProjectState),
                ExpressionInput.create('p_dz', 'Full Length Z (mm)', p('dz', '200'), currentProjectState),
                ExpressionInput.create('p_startphi', 'Start Phi (rad)', p('startphi', '0'), currentProjectState),
                ExpressionInput.create('p_deltaphi', 'Delta Phi (rad)', p('deltaphi', '360'), currentProjectState)
            ],
            sphere: () => [
                ExpressionInput.create('p_rmin', 'Inner Radius (mm)', p('rmin', '0'), currentProjectState),
                ExpressionInput.create('p_rmax', 'Outer Radius (mm)', p('rmax', '100'), currentProjectState),
                ExpressionInput.create('p_startphi', 'Start Phi (rad)', p('startphi', '0'), currentProjectState),
                ExpressionInput.create('p_deltaphi', 'Delta Phi (rad)', p('deltaphi', '2*pi'), currentProjectState),
                ExpressionInput.create('p_starttheta', 'Start Theta (rad)', p('starttheta', '0'), currentProjectState),
                ExpressionInput.create('p_deltatheta', 'Delta Theta (rad)', p('deltatheta', 'pi'), currentProjectState)
            ],
            orb: () => [
                ExpressionInput.create('p_r', 'Radius (mm)', p('r', '100'), currentProjectState)
            ],
            torus: () => [
                ExpressionInput.create('p_rmin', 'Min Radius (mm)', p('rmin', '20'), currentProjectState),
                ExpressionInput.create('p_rmax', 'Max Radius (mm)', p('rmax', '30'), currentProjectState),
                ExpressionInput.create('p_rtor', 'Torus Radius (mm)', p('rtor', '100'), currentProjectState),
                ExpressionInput.create('p_startphi', 'Start Phi (rad)', p('startphi', '0'), currentProjectState),
                ExpressionInput.create('p_deltaphi', 'Delta Phi (rad)', p('deltaphi', '2*pi'), currentProjectState)
            ],
            trd: () => [
                ExpressionInput.create('p_dx1', 'X Half-Length 1 (mm)', p('dx1', '50'), currentProjectState),
                ExpressionInput.create('p_dx2', 'X Half-Length 2 (mm)', p('dx2', '75'), currentProjectState),
                ExpressionInput.create('p_dy1', 'Y Half-Length 1 (mm)', p('dy1', '50'), currentProjectState),
                ExpressionInput.create('p_dy2', 'Y Half-Length 2 (mm)', p('dy2', '75'), currentProjectState),
                ExpressionInput.create('p_dz', 'Z Half-Length (mm)', p('dz', '100'), currentProjectState)
            ],
            para: () => [
                ExpressionInput.create('p_dx', 'X Half-Length (mm)', p('dx', '50'), currentProjectState),
                ExpressionInput.create('p_dy', 'Y Half-Length (mm)', p('dy', '60'), currentProjectState),
                ExpressionInput.create('p_dz', 'Z Half-Length (mm)', p('dz', '70'), currentProjectState),
                ExpressionInput.create('p_alpha', 'Alpha (rad)', p('alpha', 'pi/12'), currentProjectState),
                ExpressionInput.create('p_theta', 'Theta (rad)', p('theta', 'pi/12'), currentProjectState),
                ExpressionInput.create('p_phi', 'Phi (rad)', p('phi', 'pi/12'), currentProjectState)
            ],
            eltube: () => [
                ExpressionInput.create('p_dx', 'Semi-axis dx (mm)', p('dx', '50'), currentProjectState),
                ExpressionInput.create('p_dy', 'Semi-axis dy (mm)', p('dy', '75'), currentProjectState),
                ExpressionInput.create('p_dz', 'Half-length dz (mm)', p('dz', '100'), currentProjectState)
            ]
        };
        
        const fallbackEl = document.createElement('p');
        fallbackEl.textContent = `Parameters for '${type}' not implemented yet.`;

        const components = uiBuilders[type] ? uiBuilders[type]() : [fallbackEl];
        components.forEach(comp => dynamicParamsDiv.appendChild(comp));

        dynamicParamsDiv.addEventListener('change', updatePreview);
    }
    
    updatePreview();
}

// Copied this helper function from uiManager.js to make it available here.
function populateDefineSelect(selectElement, definesArray) {
    selectElement.innerHTML = '<option value="[Absolute]">[Absolute Value]</option>';
    definesArray.forEach(name => {
        const option = document.createElement('option');
        option.value = name;
        option.textContent = name;
        selectElement.appendChild(option);
    });
}

// This helper creates the UI for one transform type (position or rotation)
function buildSingleTransformUI(index, type, label, defines, transformData) {
    const group = document.createElement('div');
    group.className = 'transform-group';

    const header = document.createElement('div');
    header.className = 'define-header';
    header.innerHTML = `<span>${label}</span>`;
    const select = document.createElement('select');
    select.className = 'define-select';
    select.dataset.index = index;
    select.dataset.transformType = type;
    populateDefineSelect(select, defines);
    header.appendChild(select);
    group.appendChild(header);

    const inputsContainer = document.createElement('div');
    inputsContainer.className = 'inline-inputs-container';
    group.appendChild(inputsContainer);

    const isAbsolute = typeof transformData !== 'string';
    select.value = isAbsolute ? '[Absolute]' : transformData;

    // Get the values to display. If it's a define, look up its evaluated value.
    let displayValues = {x: '0', y: '0', z: '0'};
    if (isAbsolute) {
        displayValues = transformData || {x: '0', y: '0', z: '0'};
    } else {
        const define = currentProjectState.defines[transformData];
        if (define && define.value) {
            displayValues = define.value; // Use the pre-evaluated value
        }
    }
    
    // Create inputs for each axis
    ['x', 'y', 'z'].forEach(axis => {
        const item = document.createElement('div');
        item.className = 'property_item';
        // FIX #4: Add the label
        item.innerHTML = `<label>${axis.toUpperCase()}:</label>`;
        
        // Use the full expression component if absolute, otherwise a simple disabled input
        if (isAbsolute) {
            const exprComp = ExpressionInput.createInline(
                `bool_trans_${index}_${type}_${axis}`,
                displayValues[axis] || '0',
                currentProjectState,
                (newValue) => {
                    if (booleanRecipe[index] && typeof booleanRecipe[index].transform[type] === 'object') {
                        booleanRecipe[index].transform[type][axis] = newValue;
                        updatePreview();
                    }
                }
            );
            item.appendChild(exprComp);
        } else {
            // FIX #3: Show grayed-out evaluated values for defines
            const disabledInput = document.createElement('input');
            disabledInput.type = 'text';
            disabledInput.disabled = true;
            disabledInput.className = 'expression-result'; // Style like a result box
            let val = displayValues[axis] || 0;
            // Convert radians to degrees for rotation display
            if (type === 'rotation') {
                val = THREE.MathUtils.radToDeg(val);
            }
            disabledInput.value = val.toPrecision(4);
            item.appendChild(disabledInput);
        }
        inputsContainer.appendChild(item);
    });

    return group;
}

function rebuildBooleanUI() {
    const recipeListDiv = document.getElementById('boolean-recipe-list');
    const ingredientsPanel = document.getElementById('boolean-ingredients-list');
    recipeListDiv.innerHTML = '';
    ingredientsPanel.innerHTML = ''; 

    if (currentProjectState && currentProjectState.solids) {
        for (const solidName in currentProjectState.solids) {
            if (isEditMode && solidName === editingSolidId) continue;
            const solid = currentProjectState.solids[solidName];
            const div = document.createElement('div');
            div.textContent = solid.name;
            div.draggable = true;
            div.dataset.solidName = solid.name; 
            div.addEventListener('dragstart', (e) => { e.dataTransfer.setData('text/plain', solid.name); });
            ingredientsPanel.appendChild(div);
        }
    }
    
    booleanRecipe.forEach((item, index) => {
        const isBase = index === 0;
        const row = document.createElement('div');
        row.className = 'boolean-recipe-row';

        // Container for the top part (operation and drag slot)
        const topPart = document.createElement('div');
        topPart.className = 'boolean-top-part';

        // FIX #1: Operation dropdown
        const opContainer = document.createElement('div');
        opContainer.className = 'op-container';
        if (!isBase) {
            opContainer.innerHTML = `
                <select class="boolean-op-select" data-index="${index}">
                    <option value="subtraction" ${item.op === 'subtraction' ? 'selected' : ''}>Subtract (-)</option>
                    <option value="union" ${item.op === 'union' ? 'selected' : ''}>Union (+)</option>
                    <option value="intersection" ${item.op === 'intersection' ? 'selected' : ''}>Intersect (∩)</option>
                </select>
            `;
        } else {
            opContainer.innerHTML = '<h6>Base Solid</h6>';
        }
        topPart.appendChild(opContainer);
        
        // Drag slot
        const slotContent = item.solid ? item.solid.name : 'Drag a solid here';
        const slotDiv = document.createElement('div');
        slotDiv.className = `boolean-slot ${item.solid ? 'filled' : ''}`;
        slotDiv.dataset.index = index;
        slotDiv.textContent = slotContent;
        topPart.appendChild(slotDiv);

        row.appendChild(topPart);

        // Container for the bottom part (transforms)
        if (!isBase) {
            const transformWrapper = document.createElement('div');
            transformWrapper.className = 'transform-controls-inline';
            
            const posDefines = currentProjectState.defines ? Object.keys(currentProjectState.defines).filter(k => currentProjectState.defines[k].type === 'position') : [];
            const rotDefines = currentProjectState.defines ? Object.keys(currentProjectState.defines).filter(k => currentProjectState.defines[k].type === 'rotation') : [];
            
            const posEditor = buildSingleTransformUI(index, 'position', 'Position (mm)', posDefines, item.transform.position);
            const rotEditor = buildSingleTransformUI(index, 'rotation', 'Rotation (deg)', rotDefines, item.transform.rotation);

            transformWrapper.appendChild(posEditor);
            transformWrapper.appendChild(rotEditor);
            row.appendChild(transformWrapper);
            
            const removeBtn = document.createElement('button');
            removeBtn.className = 'remove-op-btn';
            removeBtn.dataset.index = index;
            removeBtn.textContent = '×';
            removeBtn.title = "Remove Operation";
            // Add to top part for better alignment
            topPart.appendChild(removeBtn); 
        }

        recipeListDiv.appendChild(row);
    });

    attachBooleanListeners();
}

function attachBooleanListeners() {
    document.querySelectorAll('.boolean-recipe-row .boolean-slot').forEach(slot => {
        slot.addEventListener('dragover', e => e.preventDefault());
        slot.addEventListener('drop', e => {
            e.preventDefault();
            const solidName = e.dataTransfer.getData('text/plain');
            const index = parseInt(slot.dataset.index, 10);
            const solidData = currentProjectState.solids[solidName];
            if (solidData) {
                booleanRecipe[index].solid = solidData;
                rebuildBooleanUI(); // Rebuild to show the name
                updatePreview();    // ## FIX: Explicitly update preview after drop
            }
        });
    });

    document.querySelectorAll('.boolean-op-select').forEach(select => {
        select.addEventListener('change', e => {
            const index = parseInt(e.target.dataset.index, 10);
            booleanRecipe[index].op = e.target.value;
            updatePreview();
        });
    });

    document.querySelectorAll('.remove-op-btn').forEach(button => {
        button.addEventListener('click', e => {
            const index = parseInt(e.target.dataset.index, 10);
            if (index > 0) {
                booleanRecipe.splice(index, 1);
                rebuildBooleanUI();
            }
        });
    });

    // Listener for when a define is selected from the dropdown
    document.querySelectorAll('.define-select').forEach(select => {
        select.addEventListener('change', e => {
            const index = parseInt(e.target.dataset.index, 10);
            const type = e.target.dataset.transformType;
            if (e.target.value === '[Absolute]') {
                booleanRecipe[index].transform[type] = {x:'0', y:'0', z:'0'};
            } else {
                booleanRecipe[index].transform[type] = e.target.value;
            }
            rebuildBooleanUI(); // Re-render to update the inputs
            updatePreview();
        });
    });

    // Listener for when an absolute value expression is changed
    document.querySelectorAll('.inline-trans').forEach(input => {
        const updateTransformState = (e) => {
            const el = e.target;
            const index = parseInt(el.dataset.index, 10);
            const type = el.dataset.transformType; // 'position' or 'rotation'
            const axis = el.dataset.axis;
            
            // This should only fire if the inputs are enabled (i.e., in 'Absolute' mode)
            if (booleanRecipe[index] && typeof booleanRecipe[index].transform[type] === 'object') {
                booleanRecipe[index].transform[type][axis] = el.value;
                updatePreview();
            }
        };
        input.addEventListener('change', updateTransformState);
    });
}

function addBooleanOperation() {
    booleanRecipe.push({
        op: 'subtraction', 
        solid: null,
        transform: { 
            position: {x:'0', y:'0', z:'0'}, 
            rotation: {x:'0', y:'0', z:'0'} 
        }
    });
    rebuildBooleanUI();
}

function getRawParamsFromUI() {
    const type = typeSelect.value;
    const raw_params = {};
    const p = (id) => document.getElementById(id)?.value.trim() || '0';

    if (type === 'scaledSolid') {
        raw_params.solid_ref = document.getElementById('scaled_solid_ref').value;
        raw_params.scale = {
            x: p('p_scale_x'),
            y: p('p_scale_y'),
            z: p('p_scale_z')
        };
    } else if (type === 'box') {
        raw_params.x = p('p_x');
        raw_params.y = p('p_y'); 
        raw_params.z = p('p_z');
    } else if (type === 'tube') {
        raw_params.rmin = p('p_rmin'); raw_params.rmax = p('p_rmax'); 
        raw_params.dz = p('p_dz');
        raw_params.startphi = p('p_startphi');
        raw_params.deltaphi = p('p_deltaphi');
    } else if (type === 'cone') {
        raw_params.rmin1 = p('p_rmin1'); raw_params.rmax1 = p('p_rmax1');
        raw_params.rmin2 = p('p_rmin2'); raw_params.rmax2 = p('p_rmax2');
        raw_params.dz = p('p_dz');
        raw_params.startphi = p('p_startphi');
        raw_params.deltaphi = p('p_deltaphi');
    } else if (type === 'sphere') {
        raw_params.rmin = p('p_rmin'); raw_params.rmax = p('p_rmax');
        raw_params.startphi = p('p_startphi');
        raw_params.deltaphi = p('p_deltaphi');
        raw_params.starttheta = p('p_starttheta');
        raw_params.deltatheta = p('p_deltatheta');
    } else if (type === 'orb') {
        raw_params.r = p('p_r');
    } else if (type === 'torus') {
        raw_params.rmin = p('p_rmin'); raw_params.rmax = p('p_rmax'); raw_params.rtor = p('p_rtor');
        raw_params.startphi = p('p_startphi');
        raw_params.deltaphi = p('p_deltaphi');
    } else if (type === 'trd') {
        raw_params.dx1 = p('p_dx1'); raw_params.dx2 = p('p_dx2');
        raw_params.dy1 = p('p_dy1'); raw_params.dy2 = p('p_dy2');
        raw_params.dz = p('p_dz');
    } else if (type === 'para') {
        raw_params.dx = p('p_dx'); raw_params.dy = p('p_dy'); raw_params.dz = p('p_dz');
        raw_params.alpha = p('p_alpha'); raw_params.theta = p('p_theta');
        raw_params.phi = p('p_phi');
    } else if (type === 'eltube') {
        raw_params.dx = p('p_dx'); raw_params.dy = p('p_dy');
        raw_params.dz = p('p_dz');
    }
    return raw_params;
}

async function updatePreview() {
    if (transformControls.object) {
        transformControls.detach();
    }
    if (currentSolidMesh) {
        scene.remove(currentSolidMesh);
        if (currentSolidMesh.geometry) currentSolidMesh.geometry.dispose();
        if (currentSolidMesh.material) currentSolidMesh.material.dispose();
    }

    const type = typeSelect.value;
    const isBoolean = type === 'boolean';
    let geometry = null;
    const csgEvaluator = new Evaluator();

    if (isBoolean) {
        if (booleanRecipe.length === 0 || !booleanRecipe[0].solid) return;
        
        // ## NEW HELPER FUNCTION to resolve defines before evaluation ##
        const getExpressionsForTransform = (transformPart) => {
            if (typeof transformPart === 'string') {
                // It's a define reference, find it in the project state
                const define = currentProjectState.defines[transformPart];
                return define ? define.raw_expression : {x:'0', y:'0', z:'0'}; // Return default on failure
            }
            // It's already an object of expressions
            return transformPart || {x:'0', y:'0', z:'0'};
        };

        try {
            const baseGeom = createPrimitiveGeometry(booleanRecipe[0].solid, currentProjectState, csgEvaluator);
            if (!baseGeom) return;
            let resultBrush = new Brush(baseGeom);

            if (booleanRecipe.length > 1) {
                for (let i = 1; i < booleanRecipe.length; i++) {
                    const item = booleanRecipe[i];
                    if (!item.solid) continue;

                    const nextSolidGeom = createPrimitiveGeometry(item.solid, currentProjectState, csgEvaluator);
                    if (!nextSolidGeom) continue;

                    const nextBrush = new Brush(nextSolidGeom);
                    
                    const transform = item.transform || {};
                    
                    // ## FIX: Use the new helper to get the actual expressions ##
                    const pos_expr_dict = getExpressionsForTransform(transform.position);
                    const rot_expr_dict = getExpressionsForTransform(transform.rotation);
                    
                    const [posX, posY, posZ] = await Promise.all([
                        APIService.evaluateExpression(pos_expr_dict.x, currentProjectState),
                        APIService.evaluateExpression(pos_expr_dict.y, currentProjectState),
                        APIService.evaluateExpression(pos_expr_dict.z, currentProjectState)
                    ]);
                    const [rotX, rotY, rotZ] = await Promise.all([
                        APIService.evaluateExpression(rot_expr_dict.x, currentProjectState),
                        APIService.evaluateExpression(rot_expr_dict.y, currentProjectState),
                        APIService.evaluateExpression(rot_expr_dict.z, currentProjectState)
                    ]);

                    nextBrush.position.set(posX.result || 0, posY.result || 0, posZ.result || 0);
                    nextBrush.quaternion.setFromEuler(new THREE.Euler(
                        rotX.result || 0, 
                        rotY.result || 0, 
                        rotZ.result || 0, 
                        'ZYX'
                    ));
                    nextBrush.updateMatrixWorld();

                    const op = (item.op === 'union') ? ADDITION : (item.op === 'intersection') ? INTERSECTION : SUBTRACTION;
                    resultBrush = csgEvaluator.evaluate(resultBrush, nextBrush, op);
                }
            }
            if (resultBrush) geometry = resultBrush.geometry;
        } catch (error) {
            console.error("Error building boolean preview:", error);
        }
    } else if (type === 'scaledSolid') { 
        const solidToScaleName = document.getElementById('scaled_solid_ref').value;
        const solidToScaleData = currentProjectState.solids[solidToScaleName];
        if (solidToScaleData) {
            // Get the geometry of the base solid
            geometry = createPrimitiveGeometry(solidToScaleData, currentProjectState, csgEvaluator);
            if (geometry) {
                // Evaluate the scale factors from the UI
                const scaleX = (await APIService.evaluateExpression(document.getElementById('p_scale_x').value, currentProjectState)).result || 1;
                const scaleY = (await APIService.evaluateExpression(document.getElementById('p_scale_y').value, currentProjectState)).result || 1;
                const scaleZ = (await APIService.evaluateExpression(document.getElementById('p_scale_z').value, currentProjectState)).result || 1;
                geometry.scale(scaleX, scaleY, scaleZ);
            }
        }
    } else { // It's a primitive
        const rawParams = getRawParamsFromUI();
        const evalPromises = Object.entries(rawParams).map(async ([key, expr]) => {
            const response = await APIService.evaluateExpression(expr, currentProjectState);
            return [key, response.success ? response.result : 0];
        });
        const evaluatedEntries = await Promise.all(evalPromises);
        const tempSolidData = {
            name: 'preview',
            type: type,
            _evaluated_parameters: Object.fromEntries(evaluatedEntries)
        };
        
        // Normalize values (half-lengths, degrees to rad) for Three.js
        const p = tempSolidData._evaluated_parameters;
        if (p.dz !== undefined) p.dz /= 2.0;
        if (p.startphi !== undefined) p.startphi = p.startphi;
        if (p.deltaphi !== undefined) p.deltaphi = p.deltaphi;
        if (p.starttheta !== undefined) p.starttheta = p.starttheta;
        if (p.deltatheta !== undefined) p.deltatheta = p.deltatheta;
        if (p.alpha !== undefined) p.alpha = p.alpha;
        if (p.theta !== undefined) p.theta = p.theta;
        if (p.phi !== undefined) p.phi = p.phi;
        
        geometry = createPrimitiveGeometry(tempSolidData, currentProjectState, csgEvaluator);
    }
    
    if (geometry) {
        geometry.computeBoundingSphere(); // Important for camera centering
        const material = new THREE.MeshLambertMaterial({ color: 0x9999ff, wireframe: false, side: THREE.DoubleSide });
        currentSolidMesh = new THREE.Mesh(geometry, material);
        scene.add(currentSolidMesh);
    }
}

function updateSlotUI(slot, solidData) {
    const slotContent = slot.id === 'slot-a' ? 'Solid A' : 'Solid B';
    const removeBtnHTML = `<span class="remove-solid-btn" title="Remove Solid">×</span>`;

    if (solidData) {
        slot.innerHTML = `<h6>${slotContent}</h6>${solidData.name}${removeBtnHTML}`;
        slot.classList.add('filled');
        // Add listener to the new remove button
        slot.querySelector('.remove-solid-btn').addEventListener('click', (e) => {
            e.stopPropagation(); // Prevent any parent listeners from firing
            clearSlot(slot);
        });
    } else {
        slot.innerHTML = `<h6>${slotContent}</h6><span>Drag a solid here</span>`;
        slot.classList.remove('filled');
    }
}

function clearSlot(slot) {
    if (slot.id === 'slot-a') {
        booleanSolidA = null;
    } else {
        booleanSolidB = null;
    }
    updateSlotUI(slot, null);
    updatePreview(); // Update preview to show the solid has been removed
}

function handleConfirm() {
    if (!onConfirmCallback) return;
    
    const type = typeSelect.value;
    const isBoolean = type === 'boolean';

    // The data object to be sent back
    const data = {
        isEdit: isEditMode,
        id: isEditMode ? editingSolidId : nameInput.value.trim(),
        name: nameInput.value.trim(),
        type: type,
        isChainedBoolean: isBoolean // This flag is still useful for the main controller
    };

    if (!data.name && !isEditMode) {
        alert("Please enter a name for the solid.");
        return;
    }
    
    if (isBoolean) {
        if (booleanRecipe.length < 1 || !booleanRecipe[0].solid) { alert("Base solid must be filled."); return; }
        if (booleanRecipe.length > 1 && !booleanRecipe.slice(1).every(item => item.solid)) { alert("All operation slots must be filled."); return; }
        
        data.recipe = booleanRecipe.map(item => ({
            op: item.op,
            solid_ref: item.solid.name,
            transform: item.transform
        }));
    } else {
        // For primitives, send the raw expressions from the UI.
        data.params = getRawParamsFromUI(); // The backend expects a 'params' key for primitives
    }
    
    // Checkbox logic
    if (!isEditMode) {
        data.createLV = document.getElementById('createLVCheckbox').checked;
        data.placePV = document.getElementById('placePVCheckbox').checked;
        data.materialRef = data.createLV ? document.getElementById('lvMaterialSelect').value : null;
    }
    
    onConfirmCallback(data);
    hide();
}

function updateTransformUIFromGizmo() {
    const obj = transformControls.object;
    if (!obj) return;
    
    const p_in = (id, val) => { const el = document.getElementById(id); if (el) el.value = val.toFixed(3); };

    p_in('p_pos_x', obj.position.x);
    p_in('p_pos_y', obj.position.y);
    p_in('p_pos_z', obj.position.z);

    const euler = new THREE.Euler().setFromQuaternion(obj.quaternion, 'ZYX');
    p_in('p_rot_x', THREE.MathUtils.radToDeg(euler.x));
    p_in('p_rot_y', THREE.MathUtils.radToDeg(euler.y));
    p_in('p_rot_z', THREE.MathUtils.radToDeg(euler.z));
}

// Helper function to frame the camera on the current mesh
function recenterCamera() {
    if (!currentSolidMesh || !controls || !camera) {
        if(controls) controls.reset();
        return;
    }

    const boundingBox = new THREE.Box3().setFromObject(currentSolidMesh);
    const center = boundingBox.getCenter(new THREE.Vector3());
    const size = boundingBox.getSize(new THREE.Vector3());

    // Get the maximum dimension of the object
    const maxDim = Math.max(size.x, size.y, size.z);
    
    // Calculate camera distance
    const fov = camera.fov * (Math.PI / 180);
    let cameraZ = Math.abs(maxDim / 2 * 3 / Math.tan(fov / 2));
    
    // Give a minimum distance for very small objects
    cameraZ = Math.max(cameraZ, 200); 

    // Update orbit controls
    controls.target.copy(center);
    
    // Position the camera
    camera.position.set(center.x, center.y, center.z + cameraZ);

    // This is important - you must call update after changing camera position/target
    controls.update();
}