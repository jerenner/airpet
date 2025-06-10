// static/solidEditor.js
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
// We will need a way to create geometries, let's assume a helper exists
// for now, we will add it to sceneManager later.
import { createPrimitiveGeometry } from './sceneManager.js';

// --- Module State ---
let scene, camera, renderer, controls;
let currentSolidMesh = null;
let onConfirmCallback = null;
let isEditMode = false;       // flag to track mode
let editingSolidId = null;    // store the ID/name of the solid being edited

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

    // Event Listeners
    document.getElementById('closeSolidEditor').addEventListener('click', hide);
    typeSelect.addEventListener('change', renderParamsUI);
    confirmButton.addEventListener('click', handleConfirm);
    
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
export function show(solidData = null) {
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
        renderParamsUI();
    }
    
    // Hide quick-add options in edit mode, as they don't apply
    document.querySelector('.quick-add-options').style.display = isEditMode ? 'none' : 'flex';

    modalElement.style.display = 'block';
    onWindowResize();
}

export function hide() {
    modalElement.style.display = 'none';
}

// --- Internal Logic ---

function renderParamsUI(params = {}) {
    dynamicParamsDiv.innerHTML = ''; // Clear previous params
    const type = typeSelect.value;

    document.getElementById('solid-ingredients-panel').style.display = 'none';

    // A map to generate UI for each primitive
    const paramUIBuilder = {
        box: () => `
            <div class="property_item"><label for="p_x">Size X (mm)</label><input type="number" id="p_x" value="100"></div>
            <div class="property_item"><label for="p_y">Size Y (mm)</label><input type="number" id="p_y" value="100"></div>
            <div class="property_item"><label for="p_z">Size Z (mm)</label><input type="number" id="p_z" value="100"></div>`,
        tube: () => `
            <div class="property_item"><label for="p_rmin">Inner Radius (mm)</label><input type="number" id="p_rmin" value="0"></div>
            <div class="property_item"><label for="p_rmax">Outer Radius (mm)</label><input type="number" id="p_rmax" value="50"></div>
            <div class="property_item"><label for="p_dz">Full Length Z (mm)</label><input type="number" id="p_dz" value="200"></div>
            <div class="property_item"><label for="p_startphi">Start Phi (rad)</label><input type="number" id="p_startphi" step="any" value="0"></div>
            <div class="property_item"><label for="p_deltaphi">Delta Phi (rad)</label><input type="number" id="p_deltaphi" step="any" value="${(2*Math.PI).toFixed(4)}"></div>`,
        cone: () => `
            <div class="property_item"><label for="p_rmin1">Inner Radius 1 (mm)</label><input type="number" id="p_rmin1" value="0"></div>
            <div class="property_item"><label for="p_rmax1">Outer Radius 1 (mm)</label><input type="number" id="p_rmax1" value="50"></div>
            <div class="property_item"><label for="p_rmin2">Inner Radius 2 (mm)</label><input type="number" id="p_rmin2" value="0"></div>
            <div class="property_item"><label for="p_rmax2">Outer Radius 2 (mm)</label><input type="number" id="p_rmax2" value="75"></div>
            <div class="property_item"><label for="p_dz">Full Length Z (mm)</label><input type="number" id="p_dz" value="200"></div>
            <div class="property_item"><label for="p_startphi">Start Phi (rad)</label><input type="number" id="p_startphi" step="any" value="0"></div>
            <div class="property_item"><label for="p_deltaphi">Delta Phi (rad)</label><input type="number" id="p_deltaphi" step="any" value="${(2*Math.PI).toFixed(4)}"></div>`,
        sphere: () => `
            <div class="property_item"><label for="p_rmin">Inner Radius (mm)</label><input type="number" id="p_rmin" value="0"></div>
            <div class="property_item"><label for="p_rmax">Outer Radius (mm)</label><input type="number" id="p_rmax" value="100"></div>
            <div class="property_item"><label for="p_startphi">Start Phi (rad)</label><input type="number" id="p_startphi" step="any" value="0"></div>
            <div class="property_item"><label for="p_deltaphi">Delta Phi (rad)</label><input type="number" id="p_deltaphi" step="any" value="${(2*Math.PI).toFixed(4)}"></div>
            <div class="property_item"><label for="p_starttheta">Start Theta (rad)</label><input type="number" id="p_starttheta" step="any" value="0"></div>
            <div class="property_item"><label for="p_deltatheta">Delta Theta (rad)</label><input type="number" id="p_deltatheta" step="any" value="${(Math.PI).toFixed(4)}"></div>`,
        union: () => {
            document.getElementById('solid-ingredients-panel').style.display = 'flex';
            return `<div class="boolean-slot" id="slot-a"><h6>Solid A</h6><span>Drag a solid here</span></div>
                    <div class="boolean-slot" id="slot-b"><h6>Solid B</h6><span>Drag a solid here</span></div>
                    <hr><h6>Transform for Solid B</h6>`;
        }
    };
    
    // Add subtraction and intersection to use the same UI as union
    paramUIBuilder.subtraction = paramUIBuilder.union;
    paramUIBuilder.intersection = paramUIBuilder.union;

    if (paramUIBuilder[type]) {
        dynamicParamsDiv.innerHTML = paramUIBuilder[type]();
    } else {
        dynamicParamsDiv.innerHTML = `<p>Parameters for '${type}' not implemented yet.</p>`;
    }

    // Populate the values if in edit mode
    if (isEditMode) {
        const type = typeSelect.value;
        const p_in = (id, val) => { const el = document.getElementById(id); if (el) el.value = val; };
        
        if (type === 'box') {
            p_in('p_x', params.x); p_in('p_y', params.y); p_in('p_z', params.z);
        } else if (type === 'tube') {
            p_in('p_rmin', params.rmin); p_in('p_rmax', params.rmax);
            p_in('p_dz', params.dz * 2.0); // Convert half-length back to full-length for UI
            p_in('p_startphi', params.startphi); p_in('p_deltaphi', params.deltaphi);
        } else if (type === 'cone') {
            p_in('p_rmin1', params.rmin1); p_in('p_rmax1', params.rmax1);
            p_in('p_rmin2', params.rmin2); p_in('p_rmax2', params.rmax2);
            p_in('p_dz', params.dz * 2.0); // Convert half-length back to full-length
            p_in('p_startphi', params.startphi); p_in('p_deltaphi', params.deltaphi);
        } else if (type === 'sphere') {
             p_in('p_rmin', params.rmin); p_in('p_rmax', params.rmax);
             p_in('p_startphi', params.startphi); p_in('p_deltaphi', params.deltaphi);
             p_in('p_starttheta', params.starttheta); p_in('p_deltatheta', params.deltatheta);
        }
    }
    
    dynamicParamsDiv.querySelectorAll('input').forEach(input => {
        input.addEventListener('change', updatePreview);
        input.addEventListener('input', updatePreview);
    });
    
    updatePreview();
}

function getParamsFromUI() {
    const type = typeSelect.value;
    const params = {};
    const p = (id) => parseFloat(document.getElementById(id)?.value || 0);

    if (type === 'box') {
        params.x = p('p_x'); params.y = p('p_y'); params.z = p('p_z');
    } else if (type === 'tube') {
        params.rmin = p('p_rmin'); params.rmax = p('p_rmax'); 
        params.dz = p('p_dz'); // Send FULL length to backend
        params.startphi = p('p_startphi'); params.deltaphi = p('p_deltaphi');
    } else if (type === 'cone') {
        params.rmin1 = p('p_rmin1'); params.rmax1 = p('p_rmax1');
        params.rmin2 = p('p_rmin2'); params.rmax2 = p('p_rmax2');
        params.dz = p('p_dz'); // Send FULL length to backend
        params.startphi = p('p_startphi'); params.deltaphi = p('p_deltaphi');
    } else if (type === 'sphere') {
        params.rmin = p('p_rmin'); params.rmax = p('p_rmax');
        params.startphi = p('p_startphi'); params.deltaphi = p('p_deltaphi');
        params.starttheta = p('p_starttheta'); params.deltatheta = p('p_deltatheta');
    }
    return params;
}

function updatePreview() {
    if (currentSolidMesh) {
        scene.remove(currentSolidMesh);
        if (currentSolidMesh.geometry) currentSolidMesh.geometry.dispose();
        if (currentSolidMesh.material) currentSolidMesh.material.dispose();
    }

    const type = typeSelect.value;
    const params = getParamsFromUI();

    // The solidData object must match the structure expected by createPrimitiveGeometry
    const solidData = { name: 'preview', type: type, parameters: params };

    // For primitives, projectState and csgEvaluator can be null
    const geometry = createPrimitiveGeometry(solidData, null, null);
    
    if (geometry) {
        const material = new THREE.MeshLambertMaterial({ color: 0x00ff00, side: THREE.DoubleSide });
        currentSolidMesh = new THREE.Mesh(geometry, material);
        scene.add(currentSolidMesh);
    }
}

function handleConfirm() {
    if (!onConfirmCallback) return;

    if (isEditMode) {
        // --- EDIT LOGIC ---
        const type = typeSelect.value;
        const params = getParamsFromUI(); // This gets the latest values from the UI
        onConfirmCallback({
            isEdit: true,
            id: editingSolidId,
            type: type,
            params: params,
        });
    } else {
        // --- CREATE LOGIC ---
        const name = nameInput.value.trim();
        if (!name) {
            alert("Please enter a name for the solid.");
            return;
        }
        const type = typeSelect.value;
        const params = getParamsFromUI();
        const createLV = document.getElementById('createLVCheckbox').checked;
        const placePV = document.getElementById('placePVCheckbox').checked;
        const materialRef = createLV ? document.getElementById('lvMaterialSelect').value : null;

        onConfirmCallback({
            isEdit: false,
            name, type, params,
            createLV, placePV, materialRef
        });
    }
    hide();
}
