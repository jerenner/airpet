import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { FlyControls } from 'three/addons/controls/FlyControls.js';
import { DragControls } from 'three/addons/controls/DragControls.js'; // Import DragControls

// Clock
const clock = new THREE.Clock();

// Scene
let scene, camera, viewerContainer, renderer, orbitControls, dragControls, flyControls;
const geometryGroup = new THREE.Group();
let raycaster;
let mouse;
let selectedObjects = []; // Array to hold multiple selected objects
let originalMaterials = new Map(); // Map to store original materials {objectUUID: material}
let currentMode = 'observe'; // 'observe', 'move', 'scale'
let currentCameraMode = 'orbit'; // 'orbit', 'fly'

// Object hierarchy and inspection - adjust for tabs
let structureTreeRoot, definesListRoot, materialsListRoot, solidsListRoot; // UL elements for each tab
let inspectorContentDiv;
let currentlyInspectedItem = null;
let sceneObjectsMap = new Map();

// Tab related variables
let tabButtons, tabPanes;

// View related variables
let isWireframeMode = false;
let toggleWireframeButton;
let gridHelper;
let isGridVisible = true;
let toggleGridButton;
let cameraModeOrbitButton, cameraModeFlyButton;

// Add/delete
let addObjectButton, deleteSelectedObjectButton;
let addObjectModal, modalBackdrop, newObjectTypeSelect, newObjectNameInput, newObjectParamsDiv, confirmAddObjectButton, cancelAddObjectButton;

// Info panel elements
//let infoPanel, infoName, infoType, infoParameters, infoPosition, infoRotation;

// Highlighting
const highlightMaterial = new THREE.MeshLambertMaterial({
    color: 0xffaa00,
    emissive: 0x333300,
    transparent: true,
    opacity: 0.95,
    depthTest: false, // Ensure highlight is visible
    wireframe: isWireframeMode
});

// UI Elements from HTML
let gdmlFileInput, loadGdmlButton, exportGdmlButton,
    saveProjectButton, loadProjectButton, projectFileInput,
    modeObserveButton, modeMoveButton, currentModeDisplay;

function init() {

    // Scene
    scene = new THREE.Scene();
    scene.background = new THREE.Color(0xdddddd);

    // Camera
    camera = new THREE.PerspectiveCamera(75, window.innerWidth / window.innerHeight, 0.1, 20000); // Increased far plane
    camera.position.set(200, 200, 500);

    // Renderer
    viewerContainer = document.getElementById('viewer_container');
    renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setSize(window.innerWidth, window.innerHeight);
    viewerContainer.appendChild(renderer.domElement);

    // Lights
    const ambientLight = new THREE.AmbientLight(0xffffff, 0.7);
    scene.add(ambientLight);
    const directionalLight = new THREE.DirectionalLight(0xffffff, 0.8);
    directionalLight.position.set(1, 1, 1).normalize();
    scene.add(directionalLight);

    // OrbitControls (Camera manipulation)
    orbitControls = new OrbitControls(camera, renderer.domElement);
    orbitControls.enableDamping = true;

    // FlyControls (Camera manipulation)
    flyControls = new FlyControls(camera, renderer.domElement);
    flyControls.movementSpeed = 200;
    flyControls.rollSpeed = Math.PI / 12;
    flyControls.autoForward = false;
    flyControls.dragToLook = true; 
    flyControls.enabled = false;

    setCameraMode('orbit');

    // Add geometry group to scene
    scene.add(geometryGroup);
    
    // Axes Helper
    const axesHelper = new THREE.AxesHelper(300);
    scene.add(axesHelper);

    // Grid Helper
    const gridSize = 2000; // Size of the grid
    const gridDivisions = 40; // Number of divisions (2000/40 = 50mm per square)
    gridHelper = new THREE.GridHelper(gridSize, gridDivisions, 0x888888, 0xcccccc);
    gridHelper.position.y = -0.1; // Slightly below origin to avoid z-fighting with objects on y=0 plane
    scene.add(gridHelper);

    // Raycaster for object selection
    raycaster = new THREE.Raycaster();
    mouse = new THREE.Vector2();
    // IMPORTANT: Event listener on viewerContainer to avoid interference from menu
    viewerContainer.addEventListener('pointerdown', onPointerDown, false); 

    // Old info panel elements
    // infoPanel = document.getElementById('info_panel');
    // infoName = document.getElementById('info_name');
    // infoType = document.getElementById('info_type');
    // infoParameters = document.getElementById('info_parameters');
    // infoPosition = document.getElementById('info_position');
    // infoRotation = document.getElementById('info_rotation');

    // Hierarchy and Inspector panel elements
    structureTreeRoot = document.getElementById('structure_tree_root');
    definesListRoot = document.getElementById('defines_list_root');
    materialsListRoot = document.getElementById('materials_list_root');
    solidsListRoot = document.getElementById('solids_list_root');
    inspectorContentDiv = document.getElementById('inspector_content');

    // View
    toggleWireframeButton = document.getElementById('toggleWireframeButton');
    toggleWireframeButton.addEventListener('click', toggleGlobalWireframe);
    toggleGridButton = document.getElementById('toggleGridButton');
    toggleGridButton.addEventListener('click', toggleGridVisibility);
    cameraModeOrbitButton = document.getElementById('cameraModeOrbitButton');
    cameraModeFlyButton = document.getElementById('cameraModeFlyButton');

    // Add/delete objects
    addObjectButton = document.getElementById('addObjectButton');
    deleteSelectedObjectButton = document.getElementById('deleteSelectedObjectButton');
    
    addObjectModal = document.getElementById('addObjectModal');
    modalBackdrop = document.getElementById('modalBackdrop');
    newObjectTypeSelect = document.getElementById('newObjectType');
    newObjectNameInput = document.getElementById('newObjectName');
    newObjectParamsDiv = document.getElementById('newObjectParams');
    confirmAddObjectButton = document.getElementById('confirmAddObject');
    cancelAddObjectButton = document.getElementById('cancelAddObject');

    // Tab Navigation
    tabButtons = document.querySelectorAll('.tab_button');
    tabPanes = document.querySelectorAll('.tab_pane');
    tabButtons.forEach(button => {
        button.addEventListener('click', () => {
            const targetTabId = button.dataset.tab;
            activateTab(targetTabId);
        });
    });
    activateTab('tab_structure'); // Default tab

    // Initialize DragControls (will be activated/deactivated based on mode)
    // We pass an empty array initially, will update it with selectedObjects
    dragControls = new DragControls([], camera, renderer.domElement);
    dragControls.addEventListener('dragstart', function (event) {
        orbitControls.enabled = false; // Disable camera orbit while dragging
        event.object.userData.isDragging = true;
    });
    dragControls.addEventListener('drag', function(event) {
        // Constrain drag to axes if X, Y, or Z key is held (implementation later)
        if (event.object.userData.isDragging) {
            updateInfoPanelForObject(event.object); // Live update position in panel
        }
    });
    // Modify DragControls 'dragend'
    dragControls.addEventListener('dragend', function (event) {
        orbitControls.enabled = true;
        if (event.object.userData.isDragging) {
            populateInspectorPanel(event.object); // Final update
            event.object.userData.isDragging = false;

            // Send update to backend
            const objData = event.object.userData;
            const updatedPosition = {
                x: event.object.position.x,
                y: event.object.position.y,
                z: event.object.position.z
            };
            // For rotation, you'd get it from event.object.quaternion and convert to ZYX Euler
            // const euler = new THREE.Euler().setFromQuaternion(event.object.quaternion, 'ZYX');
            // const updatedRotation = { x: euler.x, y: euler.y, z: euler.z };

            sendTransformUpdate(objData.id, updatedPosition, null); // Send null for rotation for now
        }
    });
    dragControls.addEventListener('dragend', function (event) {
        orbitControls.enabled = true;
        if (event.object.userData.isDragging) {
             // Final update of info panel after drag
             populateInspectorPanel(event.object);
            event.object.userData.isDragging = false;
        }
    });
    dragControls.enabled = false; // Disabled by default

    // Menu and Mode Buttons
    gdmlFileInput = document.getElementById('gdmlFile');
    loadGdmlButton = document.getElementById('loadGdmlButton');
    exportGdmlButton = document.getElementById('exportGdmlButton');
    saveProjectButton = document.getElementById('saveProjectButton');
    loadProjectButton = document.getElementById('loadProjectButton');
    projectFileInput = document.getElementById('projectFile');       

    modeObserveButton = document.getElementById('modeObserveButton');
    modeMoveButton = document.getElementById('modeMoveButton');
    currentModeDisplay = document.getElementById('currentModeDisplay');

    loadGdmlButton.addEventListener('click', () => gdmlFileInput.click());
    gdmlFileInput.addEventListener('change', (event) => handleFileSelect(event, 'gdml'));
    exportGdmlButton.addEventListener('click', handleExportGdml);

    saveProjectButton.addEventListener('click', handleSaveProject);
    loadProjectButton.addEventListener('click', () => projectFileInput.click());
    projectFileInput.addEventListener('change', handleLoadProject);

    modeObserveButton.addEventListener('click', () => setMode('observe'));
    modeMoveButton.addEventListener('click', () => setMode('move'));

    cameraModeOrbitButton.addEventListener('click', () => setCameraMode('orbit'));
    cameraModeFlyButton.addEventListener('click', () => setCameraMode('fly'));

    projectFileInput.addEventListener('change', (event) => handleFileSelect(event, 'project'));

    addObjectButton.addEventListener('click', showAddObjectModal);
    deleteSelectedObjectButton.addEventListener('click', handleDeleteSelected);
    confirmAddObjectButton.addEventListener('click', handleConfirmAddObject);
    cancelAddObjectButton.addEventListener('click', hideAddObjectModal);
    modalBackdrop.addEventListener('click', hideAddObjectModal); // Click backdrop to close
    newObjectTypeSelect.addEventListener('change', populateAddObjectParams);
    
    setMode('observe'); // Initial mode

    // Handle window resize
    window.addEventListener('resize', onWindowResize, false);

    animate();
}

function toggleGlobalWireframe() {
    isWireframeMode = !isWireframeMode;
    geometryGroup.traverse((object) => {
        if (object.isMesh) {
            if (Array.isArray(object.material)) {
                object.material.forEach(mat => mat.wireframe = isWireframeMode);
            } else if (object.material) {
                // If it's the highlight material, we might want to handle it differently
                // or ensure the highlight material also respects wireframe.
                // For simplicity, we'll toggle it too.
                object.material.wireframe = isWireframeMode;
            }
        }
    });
    console.log("Wireframe mode:", isWireframeMode);
}

function toggleGridVisibility() {
    isGridVisible = !isGridVisible;
    gridHelper.visible = isGridVisible;
    console.log("Grid visible:", isGridVisible);
}

function setCameraMode(mode) {
    currentCameraMode = mode;
    if (mode === 'orbit') {
        orbitControls.enabled = true;
        flyControls.enabled = false;
        // Restore orbitControls target if needed
    } else if (mode === 'fly') {
        orbitControls.enabled = false;
        flyControls.enabled = true;
        // FlyControls needs to be updated in the animation loop
    }
    console.log("Camera mode set to:", currentCameraMode);
}

function sendTransformUpdate(objectId, position, rotation) {
    const payload = { id: objectId };
    if (position) payload.position = position;
    if (rotation) payload.rotation = rotation;

    fetch('/update_object_transform', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify(payload),
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            console.log("Backend updated:", data.message);
            // Optionally, you could re-fetch and re-render the entire scene from the backend's
            // "source of truth" to ensure consistency, or trust the local Three.js update for now.
            // For a robust system, re-fetching or getting a delta update is better.
        } else {
            console.error("Backend update failed:", data.error);
            // Potentially revert the visual change on the frontend if the backend fails
        }
    })
    .catch(error => {
        console.error('Error sending transform update:', error);
    });
}

// In renderGdmlObjects:
// Make sure mesh.userData.id is set from the Python backend
// objData (from python) should contain the "id" field of the PhysicalVolumePlacement
// mesh.userData = objData; // This already does it if objData has 'id'

function setMode(mode) {
    currentMode = mode;
    currentModeDisplay.textContent = `Mode: ${mode.charAt(0).toUpperCase() + mode.slice(1)}`;

    // Update button active states
    modeObserveButton.classList.toggle('active_mode', mode === 'observe');
    modeMoveButton.classList.toggle('active_mode', mode === 'move');
    // modeScaleButton.classList.toggle('active_mode', mode === 'scale');

    if (mode === 'move') {
        orbitControls.enabled = false; // Disable orbit when in move mode for clarity
        dragControls.enabled = true;
        dragControls.activate(); // Make sure it's active
        // Update draggable objects if any are selected
        dragControls.getObjects().length = 0; // Clear existing
        selectedObjects.forEach(obj => dragControls.getObjects().push(obj));

    } else { // Observe mode (or other modes in future)
        orbitControls.enabled = true;
        dragControls.enabled = false;
        dragControls.deactivate();
    }
    console.log("Mode set to:", currentMode, "DragControls enabled:", dragControls.enabled);
}


function selectObject(object) {
    if (object && object.isMesh && !selectedObjects.includes(object)) {
        selectedObjects.push(object);
        
        if (object.material !== highlightMaterial) { // Avoid re-cloning if already highlighted by another selection
            originalMaterials.set(object.uuid, {
                material: Array.isArray(object.material) ? object.material[0].clone() : object.material.clone(),
                wasWireframe: Array.isArray(object.material) ? object.material[0].wireframe : object.material.wireframe
            });
        }
        object.material = highlightMaterial;
        highlightMaterial.wireframe = isWireframeMode;
        
        updateInfoPanel(); // Update panel for potentially multiple selections
        //if (selectedObjects.length > 0) infoPanel.style.display = 'block';

        // If in move mode, update DragControls
        if (currentMode === 'move') {
            dragControls.getObjects().length = 0;
            selectedObjects.forEach(obj => dragControls.getObjects().push(obj));
        }
    }
}

function unselectObject(object) {
    const index = selectedObjects.indexOf(object);
    if (index > -1) {
        selectedObjects.splice(index, 1);
        if (originalMaterials.has(object.uuid)) {
            const originalState = originalMaterials.get(object.uuid);
            object.material = originalState.material;
            if (Array.isArray(object.material)) {
                object.material.forEach(mat => mat.wireframe = isWireframeMode);
            } else {
                object.material.wireframe = isWireframeMode;
            }
            originalMaterials.delete(object.uuid);
        }
    }
    
    updateInfoPanel();
    //if (selectedObjects.length === 0) infoPanel.style.display = 'none';

    if (currentMode === 'move') {
        dragControls.getObjects().length = 0;
        selectedObjects.forEach(obj => dragControls.getObjects().push(obj));
    }
}

function unselectAllObjects() {
    // Create a copy of the array to iterate over, as unselectObject modifies it
    [...selectedObjects].forEach(obj => unselectObject(obj));
}


function updateInfoPanel() { // This is for the main inspector
    if (!inspectorContentDiv) return;

    if (currentlyInspectedItem) {
        // If an item is selected in the hierarchy (which should also be the case if a 3D object is clicked and linked)
        populateInspectorPanel(currentlyInspectedItem); // Use the full data from hierarchy item
    } else if (selectedObjects.length === 1) {
         // A 3D object is selected, but no corresponding hierarchy item is (or linking failed)
         // Show basic info from the 3D object itself
         updateInfoPanelForObject(selectedObjects[0]);
    }
    else if (selectedObjects.length > 1) {
        inspectorContentDiv.innerHTML = '';
        const title = document.createElement('h4');
        title.textContent = `${selectedObjects.length} objects selected`;
        inspectorContentDiv.appendChild(title);
        inspectorContentDiv.innerHTML += '<p>Multi-edit not yet supported.</p>';
        //if (infoPanel) infoPanel.style.display = 'block'; // Show the inspector panel
    } else {
        inspectorContentDiv.innerHTML = '<p>Select an item.</p>';
        //if (infoPanel) infoPanel.style.display = 'none'; // Hide if using old floating panel
    }
}

function updateInfoPanelForObject(object) {
    if (!inspectorContentDiv) return; // Ensure inspector panel div exists

    // Only update if this object is the one currently focused by the inspector
    // or if no specific hierarchy item is selected but a 3D drag is active.
    if (!currentlyInspectedItem || (currentlyInspectedItem.type === 'physical_volume' && currentlyInspectedItem.id === object.userData.id) || 
        (currentMode === 'move' && selectedObjects.length === 1 && selectedObjects[0] === object) ) {
        
        inspectorContentDiv.innerHTML = ''; // Clear current inspector
        if (!object || !object.userData) {
            inspectorContentDiv.innerHTML = '<p>No data for this object.</p>';
            return;
        }

        const data = object.userData;
        const type = 'physical_volume'; // Assume it's a PV if being dragged
        const id = data.id;
        const name = data.name;

        const title = document.createElement('h4');
        title.textContent = `${type}: ${name}`;
        inspectorContentDiv.appendChild(title);

        // Display subset of info relevant during drag (or full info)
        // For simplicity, let's reuse parts of populateInspectorPanel logic
        // This is a simplified version for live update; populateInspectorPanel is more comprehensive

        const posPropertyDiv = document.createElement('div');
        posPropertyDiv.classList.add('property_item');
        const posLabel = document.createElement('label');
        posLabel.textContent = `position:`;
        posPropertyDiv.appendChild(posLabel);
        const posValueDiv = document.createElement('div');
        posValueDiv.style.paddingLeft = "10px";
        posValueDiv.innerHTML = `<strong>x:</strong> ${object.position.x.toFixed(3)}<br>
                                 <strong>y:</strong> ${object.position.y.toFixed(3)}<br>
                                 <strong>z:</strong> ${object.position.z.toFixed(3)}`;
        posPropertyDiv.appendChild(posValueDiv);
        inspectorContentDiv.appendChild(posPropertyDiv);

        // Could add live rotation if DragControls modified rotation
        // const rotPropertyDiv = ...
        // inspectorContentDiv.appendChild(rotPropertyDiv);

    }
}


function handleSaveProject() {
    // Fetch the JSON data from the backend
    fetch('/save_project_json')
        .then(response => {
            if (!response.ok) {
                throw new Error('Network response was not ok for saving project.');
            }
            return response.blob(); // Get the response as a Blob
        })
        .then(blob => {
            // Create a link and trigger a download
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.style.display = 'none';
            a.href = url;
            a.download = 'project.json'; // Filename for the download
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
            document.body.removeChild(a);
        })
        .catch(error => {
            console.error('Error saving project:', error);
            alert('Error saving project: ' + error.message);
        });
}

function handleLoadProject(event) {
    unselectAllObjects();
    const file = event.target.files[0];
    if (!file) return;

    const formData = new FormData();
    formData.append('projectFile', file);
    
    // Reset file input to allow reloading the same file
    event.target.value = null;


    fetch('/load_project_json', {
        method: 'POST',
        body: formData,
    })
    .then(response => {
        if (!response.ok) {
            return response.json().then(err => { throw new Error(err.error || 'Network response was not ok for loading project.'); });
        }
        return response.json();
    })
    .then(data => { // Data here is the Three.js scene description from the newly loaded project
        console.log('Project loaded, rendering new scene:', data);
        renderGdmlObjects(data); // Re-render the scene with the new data
    })
    .catch(error => {
        console.error('Error loading project:', error);
        alert('Error loading project: ' + error.message);
    });
}


// Modified handleFileSelect to take file type
async function handleFileSelect(event, fileType) {
    unselectAllObjects(); // And clear hierarchy selection
    clearHierarchySelection();
    const file = event.target.files[0];
    if (!file) return;

    const formData = new FormData();
    let endpoint = '';
    let fileKey = '';

    if (fileType === 'gdml') {
        formData.append('gdmlFile', file);
        endpoint = '/process_gdml';
        fileKey = 'gdmlFile';
    } else if (fileType === 'project') {
        formData.append('projectFile', file);
        endpoint = '/load_project_json';
        fileKey = 'projectFile';
    } else {
        return;
    }
    event.target.value = null;

    try {
        const response = await fetch(endpoint, { method: 'POST', body: formData });
        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.error || `Network error processing ${fileType}`);
        }
        
        console.log(`${fileType} processed, rendering scene:`, data);
        renderGdmlObjects(data); // data is the threejs_description
        fetchAndBuildHierarchy(); // Now fetch full state for hierarchy
    } catch (error) {
        console.error(`Error processing ${fileType} file:`, error);
        alert(`Error processing ${fileType}: ${error.message}`);
    }
}

function handleExportGdml() {
    fetch('/export_gdml') // This is a GET request
        .then(response => {
            if (!response.ok) {
                throw new Error('Network response was not ok for exporting GDML.');
            }
            return response.blob();
        })
        .then(blob => {
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.style.display = 'none';
            a.href = url;
            a.download = 'exported_geometry.gdml';
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
            document.body.removeChild(a);
        })
        .catch(error => {
            console.error('Error exporting GDML:', error);
            alert('Error exporting GDML: ' + error.message);
        });
}

function clearSceneGeometry() {
    unselectAllObjects(); // Ensure no stale selections or materials
    originalMaterials.clear();
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
}

function renderGdmlObjects(objects) {
    clearSceneGeometry();
    sceneObjectsMap.clear();
    if (!Array.isArray(objects)) {
        console.error("Data from backend is not an array:", objects);
        return;
    }

    objects.forEach(objData => {
        let geometry;
        const defaultMaterial = new THREE.MeshLambertMaterial({
            color: new THREE.Color(Math.random() * 0xffffff),
            transparent: true,
            opacity: 0.75,
            side: THREE.DoubleSide
        });
        defaultMaterial.wireframe = isWireframeMode;

        const p = objData.parameters; // Shorthand for parameters

        console.log("[JS renderGdmlObjects] Processing:", JSON.stringify(objData, null, 2));
        switch (objData.solid_type) {
            case 'box':
                geometry = new THREE.BoxGeometry(p.x, p.y, p.z);
                break;
            case 'tube': // For G4Tubs
                geometry = new THREE.CylinderGeometry(
                    p.rmax, p.rmax, // radiusTop, radiusBottom
                    p.dz * 2,      // height (p.dz is half-length)
                    32,             // radialSegments
                    1,              // heightSegments
                    false,          // openEnded
                    p.startphi,     // phiStart
                    p.deltaphi      // phiLength
                );
                break;
            
            case 'cone': // For G4Cons (GDML cone)
                geometry = new THREE.ConeGeometry(
                    p.rmax2,        // radius of base at +dz (GDML rmax2)
                    p.dz * 2,       // height (GDML dz is half-length)
                    32,             // radialSegments
                    1,              // heightSegments
                    false,          // openEnded
                    p.startphi,     // phiStart
                    p.deltaphi      // phiLength
                );
                // Note: This THREE.ConeGeometry assumes rmin1, rmin2 are 0 and rmax1 is for the apex.
                // A true G4Cons with rmin1/rmax1 != 0 would be a frustum, requiring
                // CylinderGeometry with different radiusTop & radiusBottom or custom geometry.
                // For simplicity now, we treat GDML cone like a simple THREE.ConeGeometry based on one end.
                // If p.rmax1 is significant and different from 0, this will not be accurate for G4Cons.
                // A more accurate G4Cons (frustum) would be:
                // geometry = new THREE.CylinderGeometry(p.rmax2, p.rmax1, p.dz * 2, 32, 1, false, p.startphi, p.deltaphi);
                // We should decide which parameters to prioritize for THREE.ConeGeometry, or use Cylinder for frustum.
                // Let's use Cylinder for G4Cons to be more general (handles rmin1/rmax1 and rmin2/rmax2)
                if (p.rmin1 !== undefined && p.rmin2 !== undefined) { // More like a G4Cons
                     geometry = new THREE.CylinderGeometry(
                        p.rmax2,         // radiusTop (at +dz)
                        p.rmax1,         // radiusBottom (at -dz)
                        p.dz * 2,        // height
                        32,              // radialSegments
                        1,               // heightSegments
                        false,           // openEnded
                        p.startphi,      // phiStart
                        p.deltaphi       // phiLength
                    );
                    // For the inner hole (if rmin1 > 0 or rmin2 > 0), CSG would be needed.
                    // This only draws the outer shell.
                } else { // Fallback to simpler cone if parameters are missing for frustum
                     geometry = new THREE.ConeGeometry(p.rmax, p.dz * 2, 32, 1, false, p.startphi, p.deltaphi);
                }
                break;

            case 'sphere': // For G4Sphere
                geometry = new THREE.SphereGeometry(
                    p.rmax,         // radius
                    32,             // widthSegments
                    16,             // heightSegments
                    p.startphi,     // phiStart
                    p.deltaphi,     // phiLength
                    p.starttheta,   // thetaStart
                    p.deltatheta    // thetaLength
                );
                // For inner radius p.rmin > 0, CSG (subtracting a smaller sphere) would be needed.
                // This only draws the outer shell.
                break;

            case 'orb': // For G4Orb (a sphere with rmin=0 and full phi/theta)
                geometry = new THREE.SphereGeometry(
                    p.r,            // radius
                    32,             // widthSegments
                    16              // heightSegments
                    // Full phi and theta are default for THREE.SphereGeometry
                );
                break;

            case 'torus': // For G4Torus
                geometry = new THREE.TorusGeometry(
                    p.rtor,         // radius of the torus (major radius)
                    (p.rmax - p.rmin) / 2.0, // radius of the tube (minor radius, assuming rmin/rmax define thickness)
                                          // This might need adjustment based on how G4Torus rmin/rmax map
                                          // G4Torus: rmin, rmax are min/max radii of the TOROIDAL tube, rtor is swept radius
                                          // So, tube radius is (rmax-rmin)/2 and it's swept at rtor + (rmin+rmax)/2 if rmin isn't 0
                                          // Let's assume GDML rmin/rmax are radii of the tube itself (like a bent G4Tubs)
                                          // A common interpretation for GDML torus: rtor is main radius, rmax is tube radius, rmin is ignored or for inner hole.
                                          // ThreeJS: radius, tube, radialSegments, tubularSegments, arc
                                          // Let's assume p.rtor is the main radius, and p.rmax is the tube's radius if rmin is 0.
                                          // If rmin > 0, it implies a hollow torus tube, not directly supported by THREE.TorusGeometry
                    p.rmax,         // radius of the tube itself, if rmin=0
                    16,             // radialSegments (around the tube)
                    32,             // tubularSegments (segments of the tube)
                    p.deltaphi      // arc length (phi segment)
                );
                // This assumes p.startphi is 0 for simplicity, or you'd need to rotate the geometry.
                // A more accurate mapping might be:
                // Tube radius: (p.rmax + p.rmin) / 2.0 if this is wall center, or just p.rmax if rmin=0.
                // For G4Torus, rmin/rmax are radii of the tube, rtor is radius of torus.
                // ThreeJS: radius = rtor, tube_radius = rmax (if rmin=0, otherwise it gets complex)
                if (p.rmin == 0) {
                     geometry = new THREE.TorusGeometry(p.rtor, p.rmax, 16, 100, p.deltaphi);
                     // We might need to rotate it if p.startphi is not 0
                     if(p.startphi !== 0) {
                        geometry.rotateZ(p.startphi); // Or rotate appropriately around the torus axis
                     }
                } else {
                    console.warn(`Torus ${objData.name} with rmin > 0 not fully supported for direct rendering.`);
                    // Could draw two tori and subtract, or represent as bounding box.
                    // For now, draw the outer shell if rmin is small relative to rmax.
                    geometry = new THREE.TorusGeometry(p.rtor, p.rmax, 16, 100, p.deltaphi);
                    if(p.startphi !== 0) geometry.rotateZ(p.startphi);
                }
                break;

            default:
                console.warn('Unsupported solid type for rendering:', objData.solid_type, objData.name);
                // Optionally, create a small placeholder sphere for unrenderable objects
                // geometry = new THREE.SphereGeometry(10, 8, 8); // Placeholder
                // if (!geometry) return; // Skip if no placeholder either
                return; 
        }

        if(geometry) {

            const mesh = new THREE.Mesh(geometry, defaultMaterial);
            mesh.userData = objData;
            mesh.userData.originalGDMLPosition = {...objData.position};
            mesh.userData.originalGDMLRotation = {...objData.rotation};
            mesh.name = objData.name;

            if (objData.position) {
                mesh.position.set(objData.position.x, objData.position.y, objData.position.z);
            }
            if (objData.rotation) {
                const euler = new THREE.Euler(objData.rotation.x, objData.rotation.y, objData.rotation.z, 'ZYX');
                mesh.quaternion.setFromEuler(euler);
            }
            geometryGroup.add(mesh);
            //console.log("[JS renderGdmlObjects] Added mesh to group:", mesh.name);
            sceneObjectsMap.set(mesh.uuid, { pvId: objData.id, name: objData.name });
        } else {
            console.log("[JS renderGdmlObjects] No geometry created for:", objData.name, objData.solid_type);
        }
    });
}

function onWindowResize() {
    // Camera aspect ratio should be based on the actual rendering area if it's not full window
    const viewerRect = viewerContainer.getBoundingClientRect();
    const menuBarHeight = document.getElementById('menu_bar') ? document.getElementById('menu_bar').offsetHeight : 0;

    const effectiveWidth = viewerRect.width;
    const effectiveHeight = viewerRect.height - menuBarHeight;


    camera.aspect = effectiveWidth / effectiveHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(effectiveWidth, effectiveHeight);
}

function animate() {
    requestAnimationFrame(animate);
    const delta = clock.getDelta();

    if (orbitControls.enabled) {
        orbitControls.update(); // Only if enabled
    }
    if (flyControls.enabled) {
        flyControls.update(delta); // FlyControls needs delta time
    }
    renderer.render(scene, camera);
}

function activateTab(tabId) {
    tabButtons.forEach(button => {
        button.classList.toggle('active', button.dataset.tab === tabId);
    });
    tabPanes.forEach(pane => {
        pane.classList.toggle('active', pane.id === tabId);
    });
}

// Hierarchy functions
async function fetchAndBuildHierarchy() {
    try {
        const response = await fetch('/get_project_state');
        const projectState = await response.json();
        if (!response.ok) {
            throw new Error(projectState.error || 'Failed to fetch project state');
        }
        buildHierarchyPanels(projectState);
    } catch (error) {
        console.error("Error fetching project state for hierarchy:", error);
        // Display error in all relevant panels or a general status area
        structureTreeRoot.innerHTML = `<li>Error: ${error.message}</li>`;
        definesListRoot.innerHTML = `<li>Error: ${error.message}</li>`;
        materialsListRoot.innerHTML = `<li>Error: ${error.message}</li>`;
        solidsListRoot.innerHTML = `<li>Error: ${error.message}</li>`;
    }
}

// Renamed and modified function
function buildHierarchyPanels(projectState) {
    // Clear existing content in all tabs
    structureTreeRoot.innerHTML = '';
    definesListRoot.innerHTML = '';
    materialsListRoot.innerHTML = '';
    solidsListRoot.innerHTML = '';

    // Defines
    for (const name in projectState.defines) {
        // Use 'name' as the ID for backend communication for defines
        definesListRoot.appendChild(createTreeItem(name, 'define', name, projectState.defines[name]));
    }
    // Materials
    for (const name in projectState.materials) {
        materialsListRoot.appendChild(createTreeItem(name, 'material', name, projectState.materials[name]));
    }
    // Solids
    for (const name in projectState.solids) {
        solidsListRoot.appendChild(createTreeItem(name, 'solid', name, projectState.solids[name]));
    }
    
    // Populate Structure (Volumes) Tab
    if (projectState.world_volume_ref && projectState.logical_volumes) {
        const worldLV = projectState.logical_volumes[projectState.world_volume_ref];
        if (worldLV) {
            structureTreeRoot.appendChild(buildVolumeNode(worldLV, projectState.logical_volumes, projectState.solids, 0, worldLV.name));
        } else {
            structureTreeRoot.innerHTML = '<li>World volume reference not found in logical volumes.</li>';
        }
    } else {
         structureTreeRoot.innerHTML = '<li>No world volume defined or no logical volumes.</li>';
    }
}

function buildVolumeNode(lvData, allLVs, allSolids, depth, lvIdForBackend) {
    const lvItem = createTreeItem(lvData.name, 'logical_volume', lvIdForBackend, lvData);
    
    // Add expand/collapse toggle if it has children
    if (lvData.phys_children && lvData.phys_children.length > 0) {
        const toggle = document.createElement('span');
        toggle.classList.add('toggle');
        toggle.textContent = '[-] '; // Default to expanded
        toggle.onclick = (e) => {
            e.stopPropagation(); // Prevent item selection
            const childrenUl = lvItem.querySelector('ul');
            if (childrenUl) {
                childrenUl.style.display = childrenUl.style.display === 'none' ? 'block' : 'none';
                toggle.textContent = childrenUl.style.display === 'none' ? '[+] ' : '[-] ';
            }
        };
        lvItem.insertBefore(toggle, lvItem.firstChild.nextSibling); // Insert after icon/name span
    }

    const childrenUl = document.createElement('ul');
    (lvData.phys_children || []).forEach(pvData => {
        const childLVData = allLVs[pvData.volume_ref];
        let displayName = pvData.name;
        if (childLVData) {
             displayName += ` (LV: ${childLVData.name})`;
             const pvItem = createTreeItem(displayName, 'physical_volume', pvData.id, pvData, 
                { lvData: childLVData, solidData: allSolids[childLVData.solid_ref] });
             // pvItem can further expand to show its own LV children if we make it recursive for LVs within PVs
             childrenUl.appendChild(pvItem);
        } else {
            const errorItem = document.createElement('li');
            errorItem.textContent = `Error: LV ${pvData.volume_ref} not found for PV ${pvData.name}`;
            childrenUl.appendChild(errorItem);
        }
    });
    if (childrenUl.children.length > 0) {
        lvItem.appendChild(childrenUl);
    }
    return lvItem;
}


function createTreeItem(name, type, id, data, additionalData = {}) {
    const item = document.createElement('li');
    const nameSpan = document.createElement('span');
    nameSpan.textContent = name;
    item.appendChild(nameSpan);

    item.dataset.type = type;
    item.dataset.id = id; // Unique ID of the object (e.g., pv.id, solid.name, lv.name)
    item.dataset.name = name; // Display name

    // Store full data for inspector (can be large, consider fetching on demand for very large scenes)
    item.appData = {...data, ...additionalData}; 

    item.addEventListener('click', (event) => {
        event.stopPropagation();
        handleHierarchyItemSelect(item);
    });
    return item;
}

function handleHierarchyItemSelect(itemElement) {
    clearHierarchySelection();
    unselectAllObjects(); // Deselect 3D objects

    itemElement.classList.add('selected_item');
    currentlyInspectedItem = {
        type: itemElement.dataset.type,
        id: itemElement.dataset.id, // For PVs, this is UUID. For others, it's name.
        name: itemElement.dataset.name,
        element: itemElement,
        data: itemElement.appData // Full data associated with the tree item
    };
    populateInspectorPanel(currentlyInspectedItem);

    // Target position for orbit controls
    let targetPosition = new THREE.Vector3(); // Default to origin

    // Try to highlight corresponding 3D object if it's a physical volume
    if (itemElement.dataset.type === 'physical_volume') {
        const pvIdToFind = itemElement.dataset.id;
        const threeMesh = findThreeObjectByPvId(pvIdToFind);
        if (threeMesh) {
            selectObject(threeMesh); // Highlights in 3D
            // Get world position of the selected mesh to set as orbit target
            threeMesh.getWorldPosition(targetPosition);
        }
    } else if (itemElement.dataset.type === 'logical_volume' && itemElement.appData && itemElement.appData.phys_children && itemElement.appData.phys_children.length > 0) {
        // For an LV, maybe target the center of its first child or its bounding box center
        // This is more complex, for now, let's focus on PVs
        const firstPvId = itemElement.appData.phys_children[0].id;
        const threeMesh = findThreeObjectByPvId(firstPvId);
        if (threeMesh) {
             threeMesh.getWorldPosition(targetPosition);
        }
    }
    // Add similar logic for other types if they have a clear 3D representation or position

    // orbitControls.target.copy(targetPosition);
    // orbitControls.update(); // Important after changing target
    // console.log("OrbitControls target set to:", targetPosition);
}

function clearHierarchySelection() {
    if (currentlyInspectedItem && currentlyInspectedItem.element) {
        currentlyInspectedItem.element.classList.remove('selected_item');
    }
    currentlyInspectedItem = null;
    inspectorContentDiv.innerHTML = '<p>Select an item from the hierarchy.</p>';
}


function populateInspectorPanel(inspectedItem) {
    inspectorContentDiv.innerHTML = ''; // Clear previous

    if (!inspectedItem || !inspectedItem.data) {
        inspectorContentDiv.innerHTML = '<p>No item selected or no data.</p>';
        return;
    }

    const { type, id, name, data } = inspectedItem; // 'data' is item.appData

    const title = document.createElement('h4');
    title.textContent = `${type.replace('_', ' ')}: ${name}`; // Display name is already descriptive
    inspectorContentDiv.appendChild(title);
    
    let dataToShow = data; // By default, show the main data object
    let objectIdForUpdate = name; // For defines, materials, solids, Id for update is their name

    if (type === 'physical_volume') {
        // For PVs, 'data' is pvData. We also have lvData and solidData in item.appData
        // The 'id' for a PV is its UUID.
        objectIdForUpdate = data.id; // Ensure we use the PV's UUID for updates

        // Display PV specific info
        displayObjectProperties(inspectorContentDiv, "Physical Volume", data, type, objectIdForUpdate, ['lvData', 'solidData', 'volume_ref']);
        
        if(data.lvData) {
            displayObjectProperties(inspectorContentDiv, "Logical Volume ("+data.lvData.name+")", data.lvData, 'logical_volume', data.lvData.name, ['phys_children', 'solid_ref', 'material_ref']);
        }
        if(data.solidData) {
            displayObjectProperties(inspectorContentDiv, "Solid ("+data.solidData.name+")", data.solidData, 'solid', data.solidData.name, ['parameters']);
            if(data.solidData.parameters){ // Display parameters of the solid
                 const paramsContainer = document.createElement('div');
                 paramsContainer.style.paddingLeft = "10px";
                 const paramsTitle = document.createElement('strong');
                 paramsTitle.textContent = "parameters:";
                 paramsContainer.appendChild(paramsTitle);
                 displayObjectProperties(paramsContainer, null, data.solidData.parameters, 'solid', data.solidData.name, [], "parameters"); // Pass a base path
                 inspectorContentDiv.appendChild(paramsContainer);
            }
        }
    } else if (type === 'logical_volume') {
        objectIdForUpdate = data.name;
        displayObjectProperties(inspectorContentDiv, null, data, type, objectIdForUpdate, ['phys_children']);
    } else if (type === 'solid') {
        objectIdForUpdate = data.name;
        console.log("Solid")
        displayObjectProperties(inspectorContentDiv, null, data, type, objectIdForUpdate, ['parameters']);
        if(data.parameters){
             const paramsContainer = document.createElement('div');
             paramsContainer.style.paddingLeft = "10px";
             const paramsTitle = document.createElement('strong');
             paramsTitle.textContent = "parameters:";
             paramsContainer.appendChild(paramsTitle);
             displayObjectProperties(paramsContainer, null, data.parameters, 'solid', objectIdForUpdate, [], "parameters");
             inspectorContentDiv.appendChild(paramsContainer);
        }
    } else { // Defines, Materials
        objectIdForUpdate = data.name;
        displayObjectProperties(inspectorContentDiv, null, data, type, objectIdForUpdate);
    }

    // Add Hide/Delete buttons (ensure 'id' here is the correct one for the backend)
    const objIdForActions = (type === 'physical_volume') ? data.id : (data.id || data.name);
    addInspectorActions(type, objIdForActions);
}

function displayObjectProperties(parentElement, sectionTitleText, objectData, objectType, objectId, keysToSkip = [], basePath = "") {
    if (sectionTitleText){
        const sectionTitle = document.createElement('h5');
        sectionTitle.textContent = sectionTitleText;
        sectionTitle.style.marginTop = "10px";
        sectionTitle.style.borderTop = "1px dashed #ccc";
        sectionTitle.style.paddingTop = "5px";
        parentElement.appendChild(sectionTitle);
    }

    for (const key in objectData) {
        if (key === 'id' || keysToSkip.includes(key) || typeof objectData[key] === 'function') continue;

        const propertyDiv = document.createElement('div');
        propertyDiv.classList.add('property_item');

        const label = document.createElement('label');
        label.textContent = `${key}:`;
        propertyDiv.appendChild(label);

        let value = objectData[key];
        const currentPropertyPath = basePath ? `${basePath}.${key}` : key;

        if (typeof value === 'object' && value !== null && !Array.isArray(value)) {
            const subDiv = document.createElement('div');
            subDiv.style.paddingLeft = "10px";
            // Recursively display sub-object properties, passing down the objectId of the main selected item
            displayObjectProperties(subDiv, null, value, objectType, objectId, [], currentPropertyPath);
            propertyDiv.appendChild(subDiv);
        } else if (Array.isArray(value)) {
            const valSpan = document.createElement('span');
            valSpan.textContent = `[Array with ${value.length} items]`; // Simple display for arrays
            propertyDiv.appendChild(valSpan);
        }
        else {
            createEditableField(propertyDiv, objectData, key, currentPropertyPath, objectType, objectId);
        }
        parentElement.appendChild(propertyDiv);
    }
}

function addInspectorActions(objectType, objectId){
     if (['physical_volume', 'logical_volume', 'solid', 'define', 'material'].includes(objectType)) {
        const actionsDiv = document.createElement('div');
        actionsDiv.style.marginTop = '10px';

        if (objectType === 'physical_volume') {
            const hideButton = document.createElement('button');
            const threeObj = findThreeObjectByPvId(objectId);
            hideButton.textContent = (threeObj && !threeObj.visible) ? "Show" : "Hide";
            hideButton.onclick = () => toggleObjectVisibility(objectId, objectType, hideButton);
            actionsDiv.appendChild(hideButton);
        }

        const deleteButton = document.createElement('button');
        deleteButton.textContent = "Delete";
        deleteButton.style.marginLeft = "5px";
        deleteButton.onclick = () => deleteHierarchyObject(objectId, objectType);
        actionsDiv.appendChild(deleteButton);
        
        inspectorContentDiv.appendChild(actionsDiv); // Append to the main inspector content
    }
}

function createEditableField(parentDiv, objectData, key, propertyPath, objectType, objectId) {
    const input = document.createElement('input');
    input.type = (typeof objectData[key] === 'number') ? 'number' : 'text';
    if (input.type === 'number') input.step = 'any'; // Allow decimals
    
    input.value = (objectData[key] === null || objectData[key] === undefined) ? '' : objectData[key];
    
    input.addEventListener('change', (e) => {
        handlePropertyChange(objectType, objectId, propertyPath, e.target.value);
    });
    parentDiv.appendChild(input);
}

async function handlePropertyChange(objectType, objectId, propertyPath, newValue) {
    console.log(`Attempting to update: ${objectType} [${objectId}], path: ${propertyPath}, new value: ${newValue}`);
    try {
        const response = await fetch('/update_property', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ object_type: objectType, object_id: objectId, property_path: propertyPath, new_value: newValue })
        });
        const result = await response.json();
        if (result.success) {
            console.log("Property updated successfully on backend.");
            // Refresh the 3D scene and hierarchy from backend's source of truth
            renderGdmlObjects(result.scene_update);
            fetchAndBuildHierarchy(); // This will also re-select and repopulate inspector if an item was selected
            // To re-select and update inspector after hierarchy rebuild:
            if(currentlyInspectedItem && currentlyInspectedItem.id === objectId && currentlyInspectedItem.type === objectType){
                // The element might be new, so query for it
                const newElement = document.querySelector(`#structure_tree_root li[data-id="${objectId}"][data-type="${objectType}"]`);
                if(newElement) {
                    // Fetch new details for the inspector
                    const detailResponse = await fetch(`/get_object_details?type=${objectType}&id=${objectId}`);
                    const detailData = await detailResponse.json();
                    if(detailResponse.ok){
                        newElement.appData = detailData; // Update the data on the new DOM element
                        handleHierarchyItemSelect(newElement); // This will call populateInspectorPanel
                    }
                }
            }

        } else {
            alert(`Error updating property: ${result.error}`);
        }
    } catch (error) {
        console.error("Error sending property update:", error);
        alert("Failed to send property update to server.");
    }
}

function findThreeObjectByPvId(pvId) {
    for (const obj of geometryGroup.children) {
        if (obj.userData && obj.userData.id === pvId) {
            return obj;
        }
    }
    return null;
}

function toggleObjectVisibility(itemId, itemType, button) {
    if (itemType === 'physical_volume') {
        const threeObj = findThreeObjectByPvId(itemId);
        if (threeObj) {
            threeObj.visible = !threeObj.visible;
            button.textContent = threeObj.visible ? "Hide" : "Show";
            // Update hierarchy item appearance
            if (currentlyInspectedItem && currentlyInspectedItem.id === itemId) {
                 currentlyInspectedItem.element.classList.toggle('hidden_item', !threeObj.visible);
            }
            // TODO: Persist this visibility state on the backend if desired
        }
    } else {
        console.log(`Visibility toggle not implemented for type: ${itemType}`);
    }
}

async function deleteHierarchyObject(itemId, itemType) {
    if (!confirm(`Are you sure you want to delete this ${itemType}: ${itemId}? This action may affect other parts of the geometry.`)) {
        return;
    }
    console.log(`Attempting to delete: ${itemType} [${itemId}]`);
    try {
        const response = await fetch('/delete_object', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ object_type: itemType, object_id: itemId })
        });
        const result = await response.json();
        if (result.success) {
            console.log("Object deletion request successful on backend.");
            renderGdmlObjects(result.scene_update); // Refresh 3D view
            fetchAndBuildHierarchy(); // Refresh hierarchy
            inspectorContentDiv.innerHTML = '<p>Item deleted. Select an item.</p>'; // Clear inspector
        } else {
            alert(`Error deleting object: ${result.error}`);
        }
    } catch (error) {
        console.error("Error sending delete request:", error);
        alert("Failed to send delete request to server.");
    }
}

function selectHierarchyItemByPvId(pvId) {
    const itemElement = document.querySelector(`#structure_tree_root li[data-type="physical_volume"][data-id="${pvId}"]`);
    if (itemElement) {
        // Potentially scroll to item if hierarchy is long: itemElement.scrollIntoView({behavior: "smooth", block: "nearest"});
        itemElement.scrollIntoView({ behavior: "smooth", block: "nearest" });
        handleHierarchyItemSelect(itemElement); // This will also update the inspector
    } else {
        console.warn("[JS] Could not find hierarchy item for PV ID:", pvId);
        // If not found, the inspector won't get fully populated by this path.
        // We might still want to show some basic info from the 3D object if it's selected.
         if (selectedObjects.length === 1) {
            // Fallback to showing some info directly from the 3D object if hierarchy link fails
            updateInfoPanelForObject(selectedObjects[0]); 
         }
    }
}

// Object functions
function showAddObjectModal() {
    newObjectNameInput.value = '';
    populateAddObjectParams(); // Populate for default selection
    addObjectModal.style.display = 'block';
    modalBackdrop.style.display = 'block';
}

function hideAddObjectModal() {
    addObjectModal.style.display = 'none';
    modalBackdrop.style.display = 'none';
}

function populateAddObjectParams() {
    newObjectParamsDiv.innerHTML = ''; // Clear previous params
    const type = newObjectTypeSelect.value;

    if (type === 'define_position') {
        newObjectParamsDiv.innerHTML = `
            <label>X:</label><input type="number" id="define_pos_x" value="0"><br>
            <label>Y:</label><input type="number" id="define_pos_y" value="0"><br>
            <label>Z:</label><input type="number" id="define_pos_z" value="0"><br>
            <label>Unit:</label><input type="text" id="define_pos_unit" value="mm">`;
    } else if (type === 'material') {
        newObjectParamsDiv.innerHTML = `
            <label>Density (g/cm3):</label><input type="number" id="mat_density" value="1.0"><br>
            <label>State (optional):</label><input type="text" id="mat_state" placeholder="solid/liquid/gas">`;
    } else if (type === 'solid_box') {
        newObjectParamsDiv.innerHTML = `
            <label>X (mm):</label><input type="number" id="box_x" value="100"><br>
            <label>Y (mm):</label><input type="number" id="box_y" value="100"><br>
            <label>Z (mm):</label><input type="number" id="box_z" value="100">`;
    } else if (type === 'solid_tube') {
        newObjectParamsDiv.innerHTML = `
            <label>RMin (mm):</label><input type="number" id="tube_rmin" value="0"><br>
            <label>RMax (mm):</label><input type="number" id="tube_rmax" value="50"><br>
            <label>DZ (Half-Length, mm):</label><input type="number" id="tube_dz" value="100"><br>
            <label>StartPhi (rad):</label><input type="number" step="any" id="tube_startphi" value="0"><br>
            <label>DeltaPhi (rad):</label><input type="number" step="any" id="tube_deltaphi" value="${2 * Math.PI.toFixed(4)}">`;
    }
    // Add more cases for other types
}

async function handleConfirmAddObject() {
    const objectType = newObjectTypeSelect.value;
    const nameSuggestion = newObjectNameInput.value.trim();
    if (!nameSuggestion) {
        alert("Please enter a name for the new object.");
        return;
    }

    let params = {};
    // Collect parameters based on type
    if (objectType === 'define_position') {
        params = {
            x: document.getElementById('define_pos_x').value,
            y: document.getElementById('define_pos_y').value,
            z: document.getElementById('define_pos_z').value,
            unit: document.getElementById('define_pos_unit').value
        };
    } else if (objectType === 'material') {
        params = {
            density: parseFloat(document.getElementById('mat_density').value),
            state: document.getElementById('mat_state').value || null
        };
    } else if (objectType === 'solid_box') {
        params = { // Assuming these are sent as strings and backend converts if needed, or convert here.
            x: parseFloat(document.getElementById('box_x').value), // Send as numbers
            y: parseFloat(document.getElementById('box_y').value),
            z: parseFloat(document.getElementById('box_z').value)
        };
    } else if (objectType === 'solid_tube') {
        params = {
            rmin: parseFloat(document.getElementById('tube_rmin').value),
            rmax: parseFloat(document.getElementById('tube_rmax').value),
            dz: parseFloat(document.getElementById('tube_dz').value) * 2, // Send full length, backend will half it for storage
            startphi: parseFloat(document.getElementById('tube_startphi').value),
            deltaphi: parseFloat(document.getElementById('tube_deltaphi').value),
        };
    }
    // Add more param collection for other types

    try {
        const response = await fetch('/add_object', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ object_type: objectType, name: nameSuggestion, params: params })
        });
        const result = await response.json();
        if (result.success) {
            console.log(result.message, result.new_object);
            hideAddObjectModal();
            if (result.project_state) buildHierarchyPanels(result.project_state);
            if (result.scene_update) renderGdmlObjects(result.scene_update); // If adding a PV directly
        } else {
            alert(`Error adding object: ${result.error}`);
        }
    } catch (error) {
        console.error("Error sending add object request:", error);
        alert("Failed to send add object request to server.");
    }
}

async function handleDeleteSelected() {
    if (!currentlyInspectedItem) {
        alert("Please select an item from the hierarchy to delete.");
        return;
    }
    const { type, id, name } = currentlyInspectedItem; // 'id' is name for Define/Mat/Solid/LV, UUID for PV

    if (!confirm(`Are you sure you want to delete ${type}: ${name}? This may affect other geometry parts.`)) {
        return;
    }

    try {
        const response = await fetch('/delete_object', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ object_type: type, object_id: id })
        });
        const result = await response.json();
        if (result.success) {
            console.log("Object deletion successful on backend.");
            if (result.project_state) buildHierarchyPanels(result.project_state);
            if (result.scene_update) renderGdmlObjects(result.scene_update);
            inspectorContentDiv.innerHTML = '<p>Item deleted. Select an item.</p>';
            currentlyInspectedItem = null; // Clear inspector
        } else {
            alert(`Error deleting object: ${result.error}`);
        }
    } catch (error) {
        console.error("Error sending delete object request:", error);
        alert("Failed to send delete object request to server.");
    }
}

function onPointerDown(event) {
    const viewerRect = viewerContainer.getBoundingClientRect();
    const menuBarHeight = document.getElementById('menu_bar').offsetHeight; // Get actual menu bar height

    // Check if click is within the viewer_container bounds, considering menu bar
    if (event.clientX < viewerRect.left || event.clientX > viewerRect.right ||
        event.clientY < (viewerRect.top + menuBarHeight) || event.clientY > viewerRect.bottom) {
        return; // Click was outside effective viewer area
    }

    // Calculate mouse position relative to the viewer_container, accounting for its offset and menu bar
    mouse.x = ((event.clientX - viewerRect.left) / viewerRect.width) * 2 - 1;
    mouse.y = -((event.clientY - (viewerRect.top + menuBarHeight)) / (viewerRect.height - menuBarHeight)) * 2 + 1;


    if (currentMode === 'observe') {
        raycaster.setFromCamera(mouse, camera);
        const intersects = raycaster.intersectObjects(geometryGroup.children, true);

        if (intersects.length > 0) {
            const firstIntersected = intersects[0].object;
            // If already selected and not Ctrl-clicking, do nothing or allow deselection by clicking again
            if (selectedObjects.includes(firstIntersected) && !event.ctrlKey) {
                // Optional: toggle selection or just keep it selected
                // For now, let's assume clicking an already selected object keeps it selected and inspector populated
                return; 
            }
            
            if (!event.ctrlKey) { // If not holding Ctrl, clear previous selections
                unselectAllObjects();       // Clears 3D selection
                clearHierarchySelection();  // Clears hierarchy selection & inspector
            }
            
            selectObject(firstIntersected); // Selects in 3D (and updates DragControls if in 'move' mode)
            selectHierarchyItemByPvId(firstIntersected.userData.id); // Selects in hierarchy and populates inspector

            // Set orbital target
            // const newTarget = new THREE.Vector3();
            // firstIntersected.getWorldPosition(newTarget);
            // orbitControls.target.copy(newTarget);
            // orbitControls.update();
        
        } else { // Clicked on empty space
            if (!event.ctrlKey) {
                unselectAllObjects();
                clearHierarchySelection();

                // Reset orbital target to origin if clicking empty space
                // orbitControls.target.set(0,0,0);
                // orbitControls.update();
            }
        }
    }
    // DragControls handles its own logic in 'move' mode
}

init();