// static/sceneManager.js
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { TransformControls } from 'three/addons/controls/TransformControls.js';
import { FlyControls } from 'three/addons/controls/FlyControls.js';

// --- Module-level variables (private to this module) ---
let scene;
let camera;
let renderer;
let viewerContainer;
let orbitControls;
let transformControls;
let flyControls;
let clock; // For FlyControls delta time

const geometryGroup = new THREE.Group(); // Parent for all loaded GDML geometry
let gridHelper;
let axesHelper;

let isWireframeMode = false;
let isGridVisible = true;
let currentCameraMode = 'orbit';

// Callbacks to main.js or other modules
let onObjectSelectedCallback = null; // Called when an object is selected in 3D view -> (selectedMeshOrNull)
let onObjectTransformEndCallback = null; // Called after a TransformControls operation completes -> (transformedMesh)
let getSnapSettingsCallback = null; // Function to get current snap settings -> {snapEnabled, translationSnap, rotationSnap}

// --- Initialization ---
export function initScene(callbacks) {
    onObjectSelectedCallback = callbacks.onObjectSelectedIn3D;
    onObjectTransformEndCallback = callbacks.onObjectTransformEnd;
    getSnapSettingsCallback = callbacks.getInspectorSnapSettings;

    // Basic Scene Setup
    scene = new THREE.Scene();
    scene.background = new THREE.Color(0xdddddd);

    viewerContainer = document.getElementById('viewer_container'); // Assumes this ID exists

    // Camera
    const aspectRatio = viewerContainer.clientWidth / viewerContainer.clientHeight;
    camera = new THREE.PerspectiveCamera(75, aspectRatio, 0.1, 20000);
    camera.position.set(200, 200, 500);

    // Renderer
    renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setSize(viewerContainer.clientWidth, viewerContainer.clientHeight);
    viewerContainer.appendChild(renderer.domElement);

    // Lights
    const ambientLight = new THREE.AmbientLight(0xffffff, 0.8); // Slightly brighter ambient
    scene.add(ambientLight);
    const directionalLight1 = new THREE.DirectionalLight(0xffffff, 0.6);
    directionalLight1.position.set(1, 1, 1).normalize();
    scene.add(directionalLight1);
    const directionalLight2 = new THREE.DirectionalLight(0xffffff, 0.4);
    directionalLight2.position.set(-1, -0.5, -1).normalize();
    scene.add(directionalLight2);


    // Controls
    orbitControls = new OrbitControls(camera, renderer.domElement);
    orbitControls.enableDamping = true;
    orbitControls.dampingFactor = 0.05;
    orbitControls.enabled = true; // Default

    transformControls = new TransformControls(camera, renderer.domElement);
    transformControls.addEventListener('dragging-changed', (event) => {
        orbitControls.enabled = !event.value; // Disable orbit while transforming
        // Optionally call a callback if main.js needs to know about drag start/stop
    });
    transformControls.addEventListener('objectChange', () => {
        // This fires rapidly during transform. Could be used for live updates if very optimized.
        // For now, we use 'mouseUp' for final update.
        if (transformControls.object && onObjectSelectedCallback) { // Update inspector if object is selected
            // This could potentially call a specific "liveUpdateInspector" if different from full selection
            // For simplicity, it might re-trigger selection logic which populates inspector
            // onObjectSelectedCallback(transformControls.object);
        }
    });
    transformControls.addEventListener('mouseUp', () => {
        if (transformControls.object && onObjectTransformEndCallback) {
            onObjectTransformEndCallback(transformControls.object);
        }
    });
    scene.add(transformControls);
    transformControls.enabled = false; // Start disabled


    flyControls = new FlyControls(camera, renderer.domElement);
    flyControls.movementSpeed = 300;
    flyControls.rollSpeed = Math.PI / 6;
    flyControls.autoForward = false;
    flyControls.dragToLook = true; // Mouse down + move to look
    flyControls.enabled = false;

    clock = new THREE.Clock();

    // Helpers
    axesHelper = new THREE.AxesHelper(300);
    scene.add(axesHelper);

    const gridSize = 2000;
    const gridDivisions = 40;
    gridHelper = new THREE.GridHelper(gridSize, gridDivisions, 0x888888, 0xcccccc);
    gridHelper.position.y = -0.1;
    scene.add(gridHelper);
    isGridVisible = true;


    // Add geometry group
    scene.add(geometryGroup);

    // Raycaster for selection
    initRaycaster(viewerContainer);

    // Handle window resize
    window.addEventListener('resize', onWindowResize);
    onWindowResize(); // Initial call to set size

    // Start animation loop
    animate();
    console.log("SceneManager initialized.");
}

// --- Raycasting and Selection ---
let raycaster;
let mouse; // Normalized device coordinates

function initRaycaster(containerElement) {
    raycaster = new THREE.Raycaster();
    mouse = new THREE.Vector2();
    containerElement.addEventListener('pointerdown', handlePointerDownForSelection, false);
}

function handlePointerDownForSelection(event) {
    // Only process clicks if OrbitControls is enabled (i.e., not transforming with gizmo, not flying)
    // Or if currentMode is 'observe'
    if (!orbitControls.enabled && appMode !== 'observe') { // currentMode from InteractionManager/main.js
        // If TransformControls has an object, and we clicked outside, detach/deselect
        if (transformControls.object) {
            const tempRaycaster = new THREE.Raycaster();
            const tempMouse = new THREE.Vector2(
                ((event.clientX - renderer.domElement.getBoundingClientRect().left) / renderer.domElement.clientWidth) * 2 - 1,
                -((event.clientY - renderer.domElement.getBoundingClientRect().top) / renderer.domElement.clientHeight) * 2 + 1
            );
            tempRaycaster.setFromCamera(tempMouse, camera);
            const intersectsGizmoOrObject = tempRaycaster.intersectObject(transformControls, true).length > 0 ||
                                         (transformControls.object && tempRaycaster.intersectObject(transformControls.object, false).length > 0) ;
            if(!intersectsGizmoOrObject) {
                if (onObjectSelectedCallback) onObjectSelectedCallback(null); // Signal deselection
            }
        }
        return;
    }

    const rect = renderer.domElement.getBoundingClientRect();
    mouse.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
    mouse.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;

    raycaster.setFromCamera(mouse, camera);
    const intersects = raycaster.intersectObjects(geometryGroup.children, true); // Recursive check

    if (intersects.length > 0) {
        const firstIntersected = findActualMesh(intersects[0].object);
        if (onObjectSelectedCallback) {
            onObjectSelectedCallback(firstIntersected, event.ctrlKey, event.shiftKey);
        }
    } else {
        if (onObjectSelectedCallback) {
            onObjectSelectedCallback(null, event.ctrlKey, event.shiftKey); // Clicked empty space
        }
    }
}

function findActualMesh(object) { // Helper if selection might hit sub-parts of a complex object
    let current = object;
    while (current.parent && current.parent !== geometryGroup && current.parent !== scene) {
        if (current.userData && current.userData.id) return current; // Found the main mesh with our ID
        current = current.parent;
    }
    return (current.userData && current.userData.id) ? current : object; // Fallback to original if no ID found up chain
}


// --- Object Rendering ---
export function renderObjects(objectsDescription) {
    clearScene(); // Clear previous geometry

    if (!Array.isArray(objectsDescription)) {
        console.error("[SceneManager] renderObjects: input is not an array.", objectsDescription);
        return;
    }

    objectsDescription.forEach(objData => {
        let geometry;
        const defaultMaterial = new THREE.MeshLambertMaterial({
            color: new THREE.Color(Math.random() * 0xffffff),
            transparent: true,
            opacity: 0.75,
            side: THREE.DoubleSide,
            wireframe: isWireframeMode // Apply current wireframe state
        });

        const p = objData.parameters;

        switch (objData.solid_type) {
            case 'box': geometry = new THREE.BoxGeometry(p.x, p.y, p.z); break;
            case 'tube': geometry = new THREE.CylinderGeometry(p.rmax, p.rmax, p.dz * 2, 32, 1, false, p.startphi, p.deltaphi); break;
            case 'cone':
                if (p.rmin1 !== undefined && p.rmin2 !== undefined) {
                     geometry = new THREE.CylinderGeometry(p.rmax2, p.rmax1,p.dz*2,32,1,false,p.startphi,p.deltaphi);
                } else {
                     geometry = new THREE.ConeGeometry((p.rmax || (p.rmax1+p.rmax2)/2 || 10), p.dz*2,32,1,false,p.startphi,p.deltaphi);
                }
                break;
            case 'sphere': geometry = new THREE.SphereGeometry(p.rmax,32,16,p.startphi,p.deltaphi,p.starttheta,p.deltatheta); break;
            case 'orb': geometry = new THREE.SphereGeometry(p.r,32,16); break;
            case 'torus':
                 if (p.rmin == 0) {
                     geometry = new THREE.TorusGeometry(p.rtor, p.rmax, 16, 100, p.deltaphi);
                     if(p.startphi !== 0 && geometry) geometry.rotateZ(p.startphi);
                } else {
                    console.warn(`[SceneManager] Torus ${objData.name} with rmin > 0 not fully supported. Drawing outer shell.`);
                    geometry = new THREE.TorusGeometry(p.rtor, p.rmax, 16, 100, p.deltaphi);
                    if(p.startphi !== 0 && geometry) geometry.rotateZ(p.startphi);
                }
                break;
            // TODO: Add more solid types here (polycone, tessellated, CSG results, etc.)
            default:
                console.warn('[SceneManager] Unsupported solid type for rendering:', objData.solid_type, objData.name);
                // geometry = new THREE.SphereGeometry(10, 8, 8); // Placeholder
                // break; // or return to skip adding
                return; // Skip this object
        }
        
        if (!geometry) {
            console.error("[SceneManager] Geometry creation failed for:", objData);
            return;
        }

        const mesh = new THREE.Mesh(geometry, defaultMaterial);
        mesh.userData = objData; // Store the full GDML-derived data
        mesh.name = objData.name || `mesh_${objData.id}`; // Ensure a name for debugging

        if (objData.position) mesh.position.set(objData.position.x, objData.position.y, objData.position.z);
        if (objData.rotation) { // ZYX Euler angles in radians
            const euler = new THREE.Euler(objData.rotation.x, objData.rotation.y, objData.rotation.z, 'ZYX');
            mesh.quaternion.setFromEuler(euler);
        }
        geometryGroup.add(mesh);
    });
    console.log("[SceneManager] Rendered objects. Total in group:", geometryGroup.children.length);
}

export function clearScene() {
    unselectAllInScene(); // Detach transform controls and clear selection arrays
    while (geometryGroup.children.length > 0) {
        const object = geometryGroup.children[0];
        if (object.geometry) object.geometry.dispose();
        if (object.material) {
            if (Array.isArray(object.material)) {
                object.material.forEach(material => material.dispose());
            } else {
                object.material.dispose();
            }
        }
        geometryGroup.remove(object);
    }
    console.log("[SceneManager] Scene cleared.");
}

// --- Selection and Highlighting in 3D ---
const _highlightMaterial = new THREE.MeshLambertMaterial({
    color: 0xffaa00, emissive: 0x333300, transparent: true,
    opacity: 0.95, depthTest: false
});
let _selectedThreeObjects = []; // Internal list of THREE.Mesh objects
let _originalMaterialsMap = new Map(); // UUID -> { material, wasWireframe }

export function updateSelectionState(newSelectedMeshes = []) {
    // Unhighlight previously selected
    _selectedThreeObjects.forEach(obj => {
        if (_originalMaterialsMap.has(obj.uuid)) {
            const originalState = _originalMaterialsMap.get(obj.uuid);
            obj.material = originalState.material;
            // Ensure wireframe status is consistent with global mode AFTER restoring material
            if (Array.isArray(obj.material)) obj.material.forEach(m => m.wireframe = isWireframeMode);
            else obj.material.wireframe = isWireframeMode;
            _originalMaterialsMap.delete(obj.uuid);
        }
    });
    _selectedThreeObjects = [];

    // Highlight new selection
    newSelectedMeshes.forEach(mesh => {
        if (mesh && mesh.isMesh) {
            _selectedThreeObjects.push(mesh);
            if (mesh.material !== _highlightMaterial) {
                _originalMaterialsMap.set(mesh.uuid, {
                    material: Array.isArray(mesh.material) ? mesh.material[0].clone() : mesh.material.clone(),
                    // wasWireframe property is not strictly needed if we always conform to global
                });
            }
            mesh.material = _highlightMaterial;
            _highlightMaterial.wireframe = isWireframeMode;
        }
    });

    // Manage TransformControls attachment
    if (_selectedThreeObjects.length === 1 && transformControls.enabled) {
        transformControls.attach(_selectedThreeObjects[0]);
    } else {
        transformControls.detach();
    }
}

export function selectObjectInSceneByPvId(pvId) {
    let foundMesh = null;
    geometryGroup.traverse(child => {
        if (child.isMesh && child.userData && child.userData.id === pvId) {
            foundMesh = child;
        }
    });
    updateSelectionState(foundMesh ? [foundMesh] : []);
    if (foundMesh) { // If found, also set orbit target
        const targetPosition = new THREE.Vector3();
        foundMesh.getWorldPosition(targetPosition);
        orbitControls.target.copy(targetPosition);
    }
}

export function unselectAllInScene() {
    updateSelectionState([]);
}

// --- Transform Controls Management ---
export function attachTransformControls(object) {
    if (transformControls.enabled && object && object.isMesh) {
        transformControls.attach(object);
    }
}
export function getTransformControls() { return transformControls; }
export function getOrbitControls() { return orbitControls; }
export function getFlyControls() { return flyControls; }
export function getSelectedObjects() { return _selectedThreeObjects; } // Expose the list of selected THREE.Mesh

// --- Viewer Options ---
export function toggleGlobalWireframe() {
    isWireframeMode = !isWireframeMode;
    _highlightMaterial.wireframe = isWireframeMode; // Update highlight material too
    geometryGroup.traverse((object) => {
        if (object.isMesh) {
            const isSelected = _selectedThreeObjects.includes(object);
            if (!isSelected && object.material !== _highlightMaterial) { // Don't mess with highlight directly if not selected
                if (Array.isArray(object.material)) {
                    object.material.forEach(mat => mat.wireframe = isWireframeMode);
                } else if (object.material) {
                    object.material.wireframe = isWireframeMode;
                }
            } else if (isSelected) { // If selected, its material is _highlightMaterial
                 // Already handled by _highlightMaterial.wireframe update
            }
        }
    });
}

export function toggleGridVisibility() {
    isGridVisible = !isGridVisible;
    if (gridHelper) gridHelper.visible = isGridVisible;
}

export function setCameraMode(mode) { // mode is 'orbit' or 'fly'
    currentCameraMode = mode; // Internal state for SceneManager if needed
    
    // InteractionManager's setMode will typically handle OrbitControls.enabled
    // This function is more about activating/deactivating FlyControls
    if (orbitControls) orbitControls.enabled = (mode === 'orbit');
    if (flyControls) flyControls.enabled = (mode === 'fly');
    
    if (transformControls && transformControls.enabled && mode === 'fly') {
        // If switching to fly mode while transforming, detach gizmo
        // InteractionManager.setMode should handle detaching transformControls before enabling fly.
    }
    console.log("[SceneManager] Camera control set to:", mode);
}

// --- Animation Loop and Resize ---
function animate() {
    requestAnimationFrame(animate);
    const delta = clock.getDelta();

    if (orbitControls.enabled) orbitControls.update();
    if (flyControls.enabled) flyControls.update(delta);
    // TransformControls updates internally if attached

    renderer.render(scene, camera);
}

function onWindowResize() {
    const viewerRect = viewerContainer.getBoundingClientRect();
    // Assuming menu bar is outside viewerContainer for this calculation
    // If menu is on top of viewerContainer, adjust viewerContainer's effective height.
    // For the provided HTML, menu_bar is outside viewer_container.
    // We should get the actual size of the renderer's DOM element parent.

    const mainContentArea = document.getElementById('main_content_area');
    const menuBar = document.getElementById('menu_bar');
    const effectiveWidth = mainContentArea.clientWidth; // viewer_container fills this
    const effectiveHeight = mainContentArea.clientHeight - (menuBar ? menuBar.offsetHeight : 0);


    if (camera && renderer) {
        camera.aspect = effectiveWidth / effectiveHeight;
        camera.updateProjectionMatrix();
        renderer.setSize(effectiveWidth, effectiveHeight);
    }
}