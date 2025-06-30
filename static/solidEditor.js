// static/solidEditor.js
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { TransformControls } from 'three/addons/controls/TransformControls.js';
import { createPrimitiveGeometry } from './sceneManager.js';
import { Brush, Evaluator, ADDITION, SUBTRACTION, INTERSECTION } from 'three-bvh-csg';

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
            const savedRecipe = solidData.parameters.recipe || [];
            
            // Reconstruct the recipe with full solid objects, not just refs
            booleanRecipe = savedRecipe.map(item => {
                const solidObject = currentProjectState.solids[item.solid_ref];
                return {
                    op: item.op,
                    solid: solidObject, // Use the full solid object
                    transform: item.transform // This is already in the correct format
                };
            });

        }
        
        // Populate parameters after the UI is rendered
        renderParamsUI(solidData.parameters);

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

function renderParamsUI(params = {}) {
    // 1. Clear previous UI and get the current solid type
    dynamicParamsDiv.innerHTML = '';
    const type = typeSelect.value;
    const isBoolean = type === 'boolean';

    // --- Initialize recipe if we just switched to boolean mode ---
    if (isBoolean && booleanRecipe.length === 0) {
        // This is the first time we're rendering the boolean UI for a new solid.
        // Start it with an empty base slot.
        booleanRecipe.push({ op: 'base', solid: null, transform: null });
    } else if (!isBoolean) {
        // If we switch away from boolean, clear the recipe.
        booleanRecipe = [];
    }

    // 2. Show/Hide the ingredients panel based on type
    document.getElementById('solid-ingredients-panel').style.display = isBoolean ? 'flex' : 'none';

    // 3. Main logic branch: Is it a boolean or a primitive?
    if (isBoolean) {
        // --- BOOLEAN UI LOGIC ---
        // Create the container for the recipe list and the "Add" button
        dynamicParamsDiv.innerHTML = `
            <div id="boolean-recipe-list"></div>
            <button id="add-boolean-op-btn" class="add_button" style="margin-top: 10px;">+ Add Operation</button>
        `;
        document.getElementById('add-boolean-op-btn').addEventListener('click', addBooleanOperation);
        
        // Populate the UI from the `booleanRecipe` state variable
        rebuildBooleanUI();

    } else {
        // --- PRIMITIVE UI LOGIC ---
        const paramUIBuilder = {
            box: () => `
                <div class="property_item"><label for="p_x">Size X (mm)</label><input type="number" id="p_x" value="100"></div>
                <div class="property_item"><label for="p_y">Size Y (mm)</label><input type="number" id="p_y" value="100"></div>
                <div class="property_item"><label for="p_z">Size Z (mm)</label><input type="number" id="p_z" value="100"></div>`,
            tube: () => `
                <div class="property_item"><label for="p_rmin">Inner Radius (mm)</label><input type="number" id="p_rmin" value="0"></div>
                <div class="property_item"><label for="p_rmax">Outer Radius (mm)</label><input type="number" id="p_rmax" value="50"></div>
                <div class="property_item"><label for="p_dz">Full Length Z (mm)</label><input type="number" id="p_dz" value="200"></div>
                <div class="property_item"><label for="p_startphi">Start Phi (deg)</label><input type="number" id="p_startphi" step="any" value="0"></div>
                <div class="property_item"><label for="p_deltaphi">Delta Phi (deg)</label><input type="number" id="p_deltaphi" step="any" value="360"></div>`,
            cone: () => `
                <div class="property_item"><label for="p_rmin1">Inner Radius 1 (mm)</label><input type="number" id="p_rmin1" value="0"></div>
                <div class="property_item"><label for="p_rmax1">Outer Radius 1 (mm)</label><input type="number" id="p_rmax1" value="50"></div>
                <div class="property_item"><label for="p_rmin2">Inner Radius 2 (mm)</label><input type="number" id="p_rmin2" value="0"></div>
                <div class="property_item"><label for="p_rmax2">Outer Radius 2 (mm)</label><input type="number" id="p_rmax2" value="75"></div>
                <div class="property_item"><label for="p_dz">Full Length Z (mm)</label><input type="number" id="p_dz" value="200"></div>
                <div class="property_item"><label for="p_startphi">Start Phi (deg)</label><input type="number" id="p_startphi" step="any" value="0"></div>
                <div class="property_item"><label for="p_deltaphi">Delta Phi (deg)</label><input type="number" id="p_deltaphi" step="any" value="360"></div>`,
            sphere: () => `
                <div class="property_item"><label for="p_rmin">Inner Radius (mm)</label><input type="number" id="p_rmin" value="0"></div>
                <div class="property_item"><label for="p_rmax">Outer Radius (mm)</label><input type="number" id="p_rmax" value="100"></div>
                <div class="property_item"><label for="p_startphi">Start Phi (deg)</label><input type="number" id="p_startphi" step="any" value="0"></div>
                <div class="property_item"><label for="p_deltaphi">Delta Phi (deg)</label><input type="number" id="p_deltaphi" step="any" value="360"></div>
                <div class="property_item"><label for="p_starttheta">Start Theta (deg)</label><input type="number" id="p_starttheta" step="any" value="0"></div>
                <div class="property_item"><label for="p_deltatheta">Delta Theta (deg)</label><input type="number" id="p_deltatheta" step="any" value="180"></div>`,
            orb: () => `
            <div class="property_item"><label for="p_r">Radius (mm)</label><input type="number" id="p_r" value="100"></div>`,
        torus: () => `
            <div class="property_item"><label for="p_rmin">Min Radius (mm)</label><input type="number" id="p_rmin" value="20"></div>
            <div class="property_item"><label for="p_rmax">Max Radius (mm)</label><input type="number" id="p_rmax" value="30"></div>
            <div class="property_item"><label for="p_rtor">Torus Radius (mm)</label><input type="number" id="p_rtor" value="100"></div>
            <div class="property_item"><label for="p_startphi">Start Phi (deg)</label><input type="number" id="p_startphi" step="any" value="0"></div>
            <div class="property_item"><label for="p_deltaphi">Delta Phi (deg)</label><input type="number" id="p_deltaphi" step="any" value="360"></div>`,
        trd: () => `
            <div class="property_item"><label for="p_dx1">X Half-Length 1 (mm)</label><input type="number" id="p_dx1" value="50"></div>
            <div class="property_item"><label for="p_dx2">X Half-Length 2 (mm)</label><input type="number" id="p_dx2" value="75"></div>
            <div class="property_item"><label for="p_dy1">Y Half-Length 1 (mm)</label><input type="number" id="p_dy1" value="50"></div>
            <div class="property_item"><label for="p_dy2">Y Half-Length 2 (mm)</label><input type="number" id="p_dy2" value="75"></div>
            <div class="property_item"><label for="p_dz">Z Half-Length (mm)</label><input type="number" id="p_dz" value="100"></div>`,
        para: () => `
            <div class="property_item"><label for="p_dx">X Half-Length (mm)</label><input type="number" id="p_dx" value="50"></div>
            <div class="property_item"><label for="p_dy">Y Half-Length (mm)</label><input type="number" id="p_dy" value="60"></div>
            <div class="property_item"><label for="p_dz">Z Half-Length (mm)</label><input type="number" id="p_dz" value="70"></div>
            <div class="property_item"><label for="p_alpha">Alpha (deg)</label><input type="number" id="p_alpha" step="any" value="15"></div>
            <div class="property_item"><label for="p_theta">Theta (deg)</label><input type="number" id="p_theta" step="any" value="15"></div>
            <div class="property_item"><label for="p_phi">Phi (deg)</label><input type="number" id="p_phi" step="any" value="15"></div>`,
        eltube: () => `
            <div class="property_item"><label for="p_dx">Semi-axis dx (mm)</label><input type="number" id="p_dx" value="50"></div>
            <div class="property_item"><label for="p_dy">Semi-axis dy (mm)</label><input type="number" id="p_dy" value="75"></div>
            <div class="property_item"><label for="p_dz">Half-length dz (mm)</label><input type="number" id="p_dz" value="100"></div>`
        };

        if (paramUIBuilder[type]) {
            dynamicParamsDiv.innerHTML = paramUIBuilder[type]();
        } else {
            dynamicParamsDiv.innerHTML = `<p>Parameters for '${type}' not implemented yet.</p>`;
        }
    }

    // 4. If in Edit Mode, populate the fields with the solid's current data
    if (isEditMode) {
        // The `rebuildBooleanUI` function already handles populating the boolean recipe.
        // We only need to handle primitives here.
        if (!isBoolean) {
            const p_in = (id, val) => { const el = document.getElementById(id); if (el) el.value = val; };
            const r2d = (rad) => THREE.MathUtils.radToDeg(rad);

            if (type === 'box') {
                p_in('p_x', params.x); p_in('p_y', params.y); p_in('p_z', params.z);
            } else if (type === 'tube') {
                p_in('p_rmin', params.rmin); p_in('p_rmax', params.rmax);
                p_in('p_dz', params.dz); // Convert half-length back to full-length
                p_in('p_startphi', THREE.MathUtils.radToDeg(params.startphi)); // rad to deg
                p_in('p_deltaphi', THREE.MathUtils.radToDeg(params.deltaphi)); // rad to deg
            } else if (type === 'cone') {
                p_in('p_rmin1', params.rmin1); p_in('p_rmax1', params.rmax1);
                p_in('p_rmin2', params.rmin2); p_in('p_rmax2', params.rmax2);
                p_in('p_dz', params.dz * 2.0); // Convert half-length back to full-length
                p_in('p_startphi', THREE.MathUtils.radToDeg(params.startphi)); // rad to deg
                p_in('p_deltaphi', THREE.MathUtils.radToDeg(params.deltaphi)); // rad to deg
            } else if (type === 'sphere') {
                 p_in('p_rmin', params.rmin); p_in('p_rmax', params.rmax);
                 p_in('p_startphi', THREE.MathUtils.radToDeg(params.startphi)); // rad to deg
                 p_in('p_deltaphi', THREE.MathUtils.radToDeg(params.deltaphi)); // rad to deg
                 p_in('p_starttheta', THREE.MathUtils.radToDeg(params.starttheta)); // rad to deg
                 p_in('p_deltatheta', THREE.MathUtils.radToDeg(params.deltatheta)); // rad to deg
            } else if (type === 'orb') {
                p_in('p_r', params.r);
            } else if (type === 'torus') {
                p_in('p_rmin', params.rmin); 
                p_in('p_rmax', params.rmax); 
                p_in('p_rtor', params.rtor);
                p_in('p_startphi', r2d(params.startphi));
                p_in('p_deltaphi', r2d(params.deltaphi));
            } else if (type === 'trd') {
                // UI shows half-lengths, which matches backend storage for trd
                p_in('p_dx1', params.dx1); 
                p_in('p_dx2', params.dx2);
                p_in('p_dy1', params.dy1); 
                p_in('p_dy2', params.dy2);
                p_in('p_dz', params.dz);
            } else if (type === 'para') {
                // UI shows half-lengths, which matches backend storage for para
                p_in('p_dx', params.dx); 
                p_in('p_dy', params.dy);
                p_in('p_dz', params.dz);
                p_in('p_alpha', r2d(params.alpha));
                p_in('p_theta', r2d(params.theta));
                p_in('p_phi', r2d(params.phi));
            } else if (type === 'eltube') {
                // UI shows semi-axes/half-length, matches backend
                p_in('p_dx', params.dx);
                p_in('p_dy', params.dy);
                p_in('p_dz', params.dz);
            }
        }
    }

    // 5. Attach listeners and update the 3D preview
    dynamicParamsDiv.querySelectorAll('input, select').forEach(input => {
        input.addEventListener('change', updatePreview);
        input.addEventListener('input', updatePreview);
    });
    
    updatePreview();
}

// Function to build/rebuild the boolean UI from the recipe
function rebuildBooleanUI() {
    const recipeListDiv = document.getElementById('boolean-recipe-list');
    const ingredientsPanel = document.getElementById('boolean-ingredients-list'); // Get the panel
    recipeListDiv.innerHTML = '';
    ingredientsPanel.innerHTML = ''; // Clear and re-populate this too

    // Populate ingredients
    if (currentProjectState && currentProjectState.solids) {
        for (const solidName in currentProjectState.solids) {
            if (isEditMode && solidName === editingSolidId) continue;
            const solid = currentProjectState.solids[solidName];
            const div = document.createElement('div');
            div.textContent = solid.name;
            div.draggable = true;
            div.dataset.solidName = solid.name; 
            div.addEventListener('dragstart', (e) => {
                e.dataTransfer.setData('text/plain', solid.name);
            });
            ingredientsPanel.appendChild(div);
        }
    }
    
    booleanRecipe.forEach((item, index) => {
        const isBase = index === 0;
        const opHTML = isBase ? '<h6>Base Solid</h6>' : `
            <select class="boolean-op-select" data-index="${index}">
                <option value="subtraction" ${item.op === 'subtraction' ? 'selected' : ''}>Subtract (-)</option>
                <option value="union" ${item.op === 'union' ? 'selected' : ''}>Union (+)</option>
                <option value="intersection" ${item.op === 'intersection' ? 'selected' : ''}>Intersect (∩)</option>
            </select>
        `;

        const slotClass = item.solid ? 'boolean-slot filled' : 'boolean-slot';
        const slotContent = item.solid ? item.solid.name : 'Drag a solid here';

        // --- Add transform inputs for non-base solids ---
        const transformHTML = isBase ? '' : `
            <div class="transform-controls-inline">
                <div class="transform-group">
                    <label>Pos (mm)</label>
                    <input type="number" class="inline-trans" data-index="${index}" data-axis="x" data-type="pos" value="${item.transform.position.x}">
                    <input type="number" class="inline-trans" data-index="${index}" data-axis="y" data-type="pos" value="${item.transform.position.y}">
                    <input type="number" class="inline-trans" data-index="${index}" data-axis="z" data-type="pos" value="${item.transform.position.z}">
                </div>
                <div class="transform-group">
                    <label>Rot (deg)</label>
                    <input type="number" class="inline-trans" data-index="${index}" data-axis="x" data-type="rot" value="${THREE.MathUtils.radToDeg(item.transform.rotation.x)}">
                    <input type="number" class="inline-trans" data-index="${index}" data-axis="y" data-type="rot" value="${THREE.MathUtils.radToDeg(item.transform.rotation.y)}">
                    <input type="number" class="inline-trans" data-index="${index}" data-axis="z" data-type="rot" value="${THREE.MathUtils.radToDeg(item.transform.rotation.z)}">
                </div>
            </div>
        `;
        
        const row = document.createElement('div');
        row.className = 'boolean-recipe-row';
        row.innerHTML = `
            <div class="op-and-slot">
                ${opHTML}
                <div class="${slotClass}" data-index="${index}">${slotContent}</div>
            </div>
            ${transformHTML}
            <button class="remove-op-btn" data-index="${index}" title="Remove Operation">×</button>
        `;
        recipeListDiv.appendChild(row);
    });

    // Attach all event listeners
    attachBooleanListeners();
    updatePreview();
}

// Function to add a new, empty operation to the recipe
function addBooleanOperation() {
    booleanRecipe.push({
        op: 'subtraction', // Default to the most common operation
        solid: null,
        transform: { position: {x:0, y:0, z:0}, rotation: {x:0, y:0, z:0} }
    });
    rebuildBooleanUI();
}

// Centralized listener attachment
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
                rebuildBooleanUI();
            }
        });
        // TODO: Add click listener to show transform editor for this slot
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
            booleanRecipe.splice(index, 1);
            rebuildBooleanUI();
        });
    });

    // --- Listener for transform inputs ---
    document.querySelectorAll('.inline-trans').forEach(input => {
        const updateTransformState = (e) => {
            const index = parseInt(e.target.dataset.index, 10);
            const axis = e.target.dataset.axis;
            const type = e.target.dataset.type;
            let value = parseFloat(e.target.value);

            if (type === 'pos') {
                booleanRecipe[index].transform.position[axis] = value;
            } else { // rot
                // Convert UI degrees to radians for internal state
                booleanRecipe[index].transform.rotation[axis] = THREE.MathUtils.degToRad(value);
            }
            updatePreview();
        };
        input.addEventListener('change', updateTransformState);
        input.addEventListener('input', updateTransformState);
    });
}

function getParamsFromUI() {
    const type = typeSelect.value;
    const params = {};
    const p = (id) => parseFloat(document.getElementById(id)?.value || 0);
    const d2r = (id) => THREE.MathUtils.degToRad(p(id)); // degrees to radians helper
    const isBoolean = type === 'boolean';

    if (isBoolean) {
        // Handled by the handleConfirm logic
    } else if (type === 'box') {
        params.x = p('p_x'); params.y = p('p_y'); params.z = p('p_z');
    } else if (type === 'tube') {
        params.rmin = p('p_rmin'); params.rmax = p('p_rmax'); 
        params.dz = p('p_dz'); // Send FULL length
        params.startphi = d2r('p_startphi'); // Convert to rad
        params.deltaphi = d2r('p_deltaphi'); // Convert to rad
    } else if (type === 'cone') {
        params.rmin1 = p('p_rmin1'); params.rmax1 = p('p_rmax1');
        params.rmin2 = p('p_rmin2'); params.rmax2 = p('p_rmax2');
        params.dz = p('p_dz'); // Send FULL length
        params.startphi = d2r('p_startphi');
        params.deltaphi = d2r('p_deltaphi');
    } else if (type === 'sphere') {
        params.rmin = p('p_rmin'); params.rmax = p('p_rmax');
        params.startphi = d2r('p_startphi');
        params.deltaphi = d2r('p_deltaphi');
        params.starttheta = d2r('p_starttheta');
        params.deltatheta = d2r('p_deltatheta');
    } else if (type === 'orb') {
        params.r = p('p_r');
    } else if (type === 'torus') {
        params.rmin = p('p_rmin'); params.rmax = p('p_rmax'); params.rtor = p('p_rtor');
        params.startphi = d2r('p_startphi'); params.deltaphi = d2r('p_deltaphi');
    } else if (type === 'trd') {
        params.dx1 = p('p_dx1'); params.dx2 = p('p_dx2');
        params.dy1 = p('p_dy1'); params.dy2 = p('p_dy2');
        params.dz = p('p_dz');
    } else if (type === 'para') {
        params.dx = p('p_dx'); params.dy = p('p_dy'); params.dz = p('p_dz');
        params.alpha = d2r('p_alpha'); params.theta = d2r('p_theta'); params.phi = d2r('p_phi');
    } else if (type === 'eltube') {
        params.dx = p('p_dx'); params.dy = p('p_dy'); params.dz = p('p_dz');
    }
    return params;
}

function getTransformFromUI() {
    const p = (id) => parseFloat(document.getElementById(id)?.value || 0);
    const pos = { x: p('p_pos_x'), y: p('p_pos_y'), z: p('p_pos_z') };
    
    // Convert degrees from UI to radians for Three.js
    const rot = {
        x: THREE.MathUtils.degToRad(p('p_rot_x')),
        y: THREE.MathUtils.degToRad(p('p_rot_y')),
        z: THREE.MathUtils.degToRad(p('p_rot_z'))
    };
    return { position: pos, rotation: rot };
}

function updatePreview() {
    // --- Detach gizmo before clearing the scene ---
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

    if (isBoolean) {
        // --- BOOLEAN RENDERING LOGIC ---
        if (booleanRecipe.length === 0 || !booleanRecipe[0].solid) return; // Need at least a base solid
        
        let resultBrush = new Brush(createPrimitiveGeometry(booleanRecipe[0].solid, currentProjectState));
        
        if (booleanRecipe.length > 1) {
            const csgEvaluator = new Evaluator();
            for (let i = 1; i < booleanRecipe.length; i++) {
                const item = booleanRecipe[i];
                if (!item.solid) continue;

                const nextBrush = new Brush(createPrimitiveGeometry(item.solid, currentProjectState));
                
                // --- USE THE STORED TRANSFORM ---
                const transform = item.transform;
                nextBrush.position.set(transform.position.x, transform.position.y, transform.position.z);
                nextBrush.quaternion.setFromEuler(new THREE.Euler(transform.rotation.x, transform.rotation.y, transform.rotation.z, 'ZYX'));
                nextBrush.updateMatrixWorld();

                const op = (item.op === 'union') ? ADDITION : (item.op === 'intersection') ? INTERSECTION : SUBTRACTION;
                resultBrush = csgEvaluator.evaluate(resultBrush, nextBrush, op);
            }
        }
        if (resultBrush) geometry = resultBrush.geometry;

    } else {
        // --- PRIMITIVE RENDERING LOGIC (Unchanged) ---
        const params = getParamsFromUI();
        const solidData = { name: 'preview', type: type, parameters: params };
        geometry = createPrimitiveGeometry(solidData, null, null);
    }
    
    if (geometry) {
        const material = new THREE.MeshLambertMaterial({ /* ... */ });
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

    if (isEditMode) {
        // --- EDIT LOGIC ---
        const data = {
            isEdit: true,
            id: editingSolidId,
            type: type,
            isChainedBoolean: isBoolean
        };

        if (isBoolean) {
            if (booleanRecipe.length < 1 || !booleanRecipe[0].solid) {
                alert("The base solid for the boolean operation must be filled.");
                return;
            }
            if (booleanRecipe.length > 1 && !booleanRecipe.slice(1).every(item => item.solid)) {
                alert("All subsequent boolean operation slots must be filled.");
                return;
            }
            data.recipe = booleanRecipe.map(item => ({
                op: item.op,
                solid_ref: item.solid.name,
                transform: item.transform
            }));
        } else {
            data.params = getParamsFromUI();
        }
        onConfirmCallback(data);

    } else {
        // --- CREATE LOGIC ---
        const name = nameInput.value.trim();
        if (!name) { alert("Please enter a name for the solid."); return; }
        
        if (isBoolean) {
            if (booleanRecipe.length < 1 || !booleanRecipe[0].solid) {
                alert("The base solid for the boolean operation must be filled.");
                return;
            }
            if (booleanRecipe.length > 1 && !booleanRecipe.slice(1).every(item => item.solid)) {
                alert("All subsequent boolean operation slots must be filled.");
                return;
            }
            const recipeForBackend = booleanRecipe.map(item => ({
                op: item.op,
                solid_ref: item.solid.name,
                transform: item.transform
            }));
            onConfirmCallback({
                isChainedBoolean: true, // This flag is the key differentiator
                name: name,
                recipe: recipeForBackend
            });
        } else {
            const params = getParamsFromUI();
            const createLV = document.getElementById('createLVCheckbox').checked;
            const placePV = document.getElementById('placePVCheckbox').checked;
            const materialRef = createLV ? document.getElementById('lvMaterialSelect').value : null;

            onConfirmCallback({
                isEdit: false,
                isChainedBoolean: false, // Explicitly false
                name, type, params,
                createLV, placePV, materialRef
            });
        }
    }
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