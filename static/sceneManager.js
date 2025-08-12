// static/sceneManager.js
import * as THREE from 'three';
import { AxesHelper } from 'three';
import { EdgesGeometry, LineBasicMaterial, LineSegments } from 'three';
import { FlyControls } from 'three/addons/controls/FlyControls.js';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { TransformControls } from 'three/addons/controls/TransformControls.js';
import { SelectionBox } from 'three/addons/interactive/SelectionBox.js';
import { ConvexGeometry } from 'three/addons/geometries/ConvexGeometry.js';
import { Brush, Evaluator, ADDITION, SUBTRACTION, INTERSECTION } from 'three-bvh-csg';
import { MeshBVH, acceleratedRaycast, computeBoundsTree, disposeBoundsTree } from 'three-mesh-bvh';
import { Line2 } from 'three/addons/lines/Line2.js';
import { LineMaterial } from 'three/addons/lines/LineMaterial.js';
import { LineGeometry } from 'three/addons/lines/LineGeometry.js';

// We must extend the THREE.js objects with the BVH functionality.
THREE.BufferGeometry.prototype.computeBoundsTree = computeBoundsTree;
THREE.BufferGeometry.prototype.disposeBoundsTree = disposeBoundsTree;
THREE.Mesh.prototype.raycast = acceleratedRaycast;

// --- Module-level variables ---
let scene, camera, renderer, viewerContainer;
let orbitControls, transformControls, flyControls;
let clock; // For FlyControls delta time
let sceneAxes, cameraAxes; // For axes gizmo
let axesSize = 100; // This controls the size of the axes view

const geometryGroup = new THREE.Group(); // Parent for all loaded GDML geometry
let gridHelper;
let axesHelper;

let isWireframeMode = false;
let isGridVisible = true;
let isAxesVisible = true;

// Selection box
let selectionBox;
const selectionBoxElement = document.getElementById('selection_box');
let isBoxSelecting = false;
let startPoint = new THREE.Vector2();

// Set to remember visibility state
const hiddenPvIds = new Set();

// Callbacks to main.js or other modules
let onObjectSelectedCallback = null; // Called when an object is selected in 3D view -> (selectedMeshOrNull)
let onObjectTransformEndCallback = null; // Called after a TransformControls operation completes -> (transformedMesh)
let getSnapSettingsCallback = null; // Function to get current snap settings -> {snapEnabled, translationSnap, rotationSnap}
let onObjectTransformLiveCallback = null; // callback for live updates
let onMultiObjectSelectedCallback = null;

// Objects for multi-select and multi-transform
let gizmoAttachmentHelper = new THREE.Object3D(); // Helper for gizmo on multi-select
let initialTransforms = new Map(); // To store initial state on drag start

// --- Initialization ---
export function initScene(callbacks) {
    onObjectSelectedCallback = callbacks.onObjectSelectedIn3D;
    onObjectTransformEndCallback = callbacks.onObjectTransformEnd;
    onObjectTransformLiveCallback = callbacks.onObjectTransformLive;
    getSnapSettingsCallback = callbacks.getInspectorSnapSettings;
    onMultiObjectSelectedCallback = callbacks.onMultiObjectSelected;

    // Basic Scene Setup
    scene = new THREE.Scene();
    scene.background = new THREE.Color(0x444444);
    scene.add(gizmoAttachmentHelper); // Add it to the scene

    viewerContainer = document.getElementById('viewer_container');

    // Camera
    const aspectRatio = viewerContainer.clientWidth / viewerContainer.clientHeight;
    camera = new THREE.PerspectiveCamera(75, aspectRatio, 0.1, 20000);
    camera.position.set(200, 200, 500);

    // Renderer
    renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setPixelRatio(window.devicePixelRatio);
    renderer.setSize(viewerContainer.clientWidth, viewerContainer.clientHeight);
    renderer.autoClear = false; // control clearing manually
    viewerContainer.appendChild(renderer.domElement);

    // Lights
    scene.add(new THREE.AmbientLight(0xcccccc, 1.0)); // Soft, omnipresent light

    const light1 = new THREE.DirectionalLight(0xffffff, 1.5);
    light1.position.set(1, 1, 1).normalize();
    scene.add(light1);

    const light2 = new THREE.DirectionalLight(0xffffff, 1.0);
    light2.position.set(-1, -0.5, -1).normalize();
    scene.add(light2);
    
    // Add a light from below to illuminate bottom faces
    const light3 = new THREE.DirectionalLight(0xffffff, 0.5);
    light3.position.set(0, -1, 0).normalize();
    scene.add(light3);


    // Controls
    orbitControls = new OrbitControls(camera, renderer.domElement);
    orbitControls.enableDamping = true;
    orbitControls.dampingFactor = 0.05;
    orbitControls.enabled = true; // Default

    // Transform controls
    transformControls = new TransformControls(camera, renderer.domElement);

    // Increase the size of the gizmo handles for easier interaction.
    transformControls.setSize(1.2);
    // Tell the internal raycaster to have a larger tolerance for lines
    // This is like giving the mouse a "fat finger" when clicking near a line
    transformControls.getRaycaster().params.Line.threshold = 0.1;

    transformControls.addEventListener('dragging-changed', (event) => {
        orbitControls.enabled = !event.value; // Disable orbit while transforming
        // Optionally call a callback if main.js needs to know about drag start/stop
    });
    transformControls.addEventListener('mouseDown', () => {
        initialTransforms.clear();
        const object = transformControls.object;
        if (!object) return;

        // Check if we are controlling the helper (a group)
        if (object === gizmoAttachmentHelper) {
            initialTransforms.set('helper', gizmoAttachmentHelper.clone());
            // Store initial transforms of all meshes controlled by the helper
            _selectedThreeObjects.forEach(group => {
                initialTransforms.set(group.userData.id, group.clone());
            });
        } else {
            // It's a single object
            initialTransforms.set(object.userData.id, object.clone());
        }
    });
    transformControls.addEventListener('mouseUp', () => {
        if (onObjectTransformEndCallback) {
            const object = transformControls.object;
            if (!object) return;

            // Pass the transformed object AND the initial state map.
            onObjectTransformEndCallback(object, initialTransforms);
        }
        initialTransforms.clear();
    });
    // Listener for live dragging
    transformControls.addEventListener('objectChange', () => {
        const object = transformControls.object;
        if (!object) return;

        // Check if we are controlling the helper (i.e., a group)
        if (object === gizmoAttachmentHelper && initialTransforms.has('helper')) {
            const helperStart = initialTransforms.get('helper');
            const helperCurrent = gizmoAttachmentHelper;

            // Calculate the delta transform
            const helperStartMatrixInv = new THREE.Matrix4().copy(helperStart.matrixWorld).invert();
            const deltaMatrix = new THREE.Matrix4().multiplyMatrices(helperCurrent.matrixWorld, helperStartMatrixInv);

            // Apply this delta to all meshes that were part of the initial selection
            _selectedThreeObjects.forEach(mesh => {
                const initialMesh = initialTransforms.get(mesh.userData.id);
                if (initialMesh) {
                    const finalMatrix = new THREE.Matrix4().multiplyMatrices(deltaMatrix, initialMesh.matrixWorld);
                    
                    const pos = new THREE.Vector3();
                    const rot = new THREE.Quaternion();
                    const scl = new THREE.Vector3();
                    finalMatrix.decompose(pos, rot, scl);
                    
                    mesh.position.copy(pos);
                    mesh.quaternion.copy(rot);
                }
            });
        }
    });

    scene.add(transformControls);
    transformControls.enabled = false; // Start disabled


    // Camera controls
    flyControls = new FlyControls(camera, renderer.domElement);
    flyControls.movementSpeed = 300;
    flyControls.rollSpeed = Math.PI / 6;
    flyControls.autoForward = false;
    flyControls.dragToLook = true; // Mouse down + move to look
    flyControls.enabled = false;

    clock = new THREE.Clock();

    // Selection box
    selectionBox = new SelectionBox(camera, geometryGroup);

    // Grid setup
    const gridSize = 10000; // Increased from 2000
    const gridDivisions = 100; // Increased from 40 for more detail over a larger area
    gridHelper = new THREE.GridHelper(gridSize, gridDivisions, 0x888888, 0xcccccc);
    gridHelper.position.y = -0.1;
    gridHelper.visible = true; // Start hidden
    scene.add(gridHelper);
    isGridVisible = false;

    // --- Setup for Corner Axes Gizmo ---
    isAxesVisible = true;

    // The axes scene
    sceneAxes = new THREE.Scene();
    
    // // The axes helper itself
    // const axes = new THREE.AxesHelper(axesSize * 0.8);
    // axes.material.linewidth = 5;
    // axes.material.depthTest = false; // Solves z-fighting
    // sceneAxes.add(axes);

    // The axes camera: Orthographic is better for this.
    // We define a square viewing area.
    cameraAxes = new THREE.OrthographicCamera(
        -axesSize, axesSize, // left, right
         axesSize, -axesSize, // top, bottom
        -1000, 1000           // near, far
    );
    cameraAxes.up = camera.up;

    // Create axes manually using Line2 for thickness control
    const axesGroup = new THREE.Group();

    const origin = [0, 0, 0];
    const xAxisEnd = [axesSize * 0.8, 0, 0];
    const yAxisEnd = [0, axesSize * 0.8, 0];
    const zAxisEnd = [0, 0, axesSize * 0.8];
    
    // X Axis (Red)
    const xGeo = new LineGeometry();
    xGeo.setPositions([...origin, ...xAxisEnd]);
    const xMat = new LineMaterial({ color: 0xff0000, linewidth: 20 }); // Linewidth is in screen units (pixels)
    const xAxis = new Line2(xGeo, xMat);

    // Y Axis (Green)
    const yGeo = new LineGeometry();
    yGeo.setPositions([...origin, ...yAxisEnd]);
    const yMat = new LineMaterial({ color: 0x00ff00, linewidth: 20 });
    const yAxis = new Line2(yGeo, yMat);

    // Z Axis (Blue)
    const zGeo = new LineGeometry();
    zGeo.setPositions([...origin, ...zAxisEnd]);
    const zMat = new LineMaterial({ color: 0x8888ff, linewidth: 20 });
    const zAxis = new Line2(zGeo, zMat);
    
    axesGroup.add(xAxis, yAxis, zAxis);
    sceneAxes.add(axesGroup);

    // ---

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
    
    // Add event listeners
    const canvas = renderer.domElement; 
    canvas.addEventListener('pointerdown', onPointerDown);
    canvas.addEventListener('pointermove', onPointerMove);
    canvas.addEventListener('pointerup', onPointerUp);
    
    // Prevent the default browser context menu on right-click
    containerElement.addEventListener('contextmenu', event => event.preventDefault());
}

function onPointerDown(event) {

    // Check for Shift + Left-Click to start box selection
    if (event.shiftKey && event.button === 0) {
        isBoxSelecting = true;
        // Disable orbit controls to prevent camera movement
        orbitControls.enabled = false;

        selectionBoxElement.style.display = 'block';
        
        // Use the event's currentTarget, which is now the canvas.
        const rect = event.currentTarget.getBoundingClientRect();        

        startPoint.set(event.clientX - rect.left, event.clientY); // For some reason, we don't need to subtract rect.top from Y

        selectionBoxElement.style.left = `${startPoint.x}px`;
        selectionBoxElement.style.top = `${startPoint.y}px`;
        selectionBoxElement.style.width = '0px';
        selectionBoxElement.style.height = '0px';

    } else {
        // If not box-selecting, use our existing single-click logic
        handlePointerDownForSelection(event);
    }
}

function onPointerMove(event) {
    if (!isBoxSelecting) return;

    // Use the event's currentTarget (the canvas) for all calculations.
    const rect = event.currentTarget.getBoundingClientRect();

    const currentX = event.clientX - rect.left;
    const currentY = event.clientY; // For some reason, we don't need to subtract rect.top from Y

    // Update the 2D box's dimensions, applying the offset
    selectionBoxElement.style.left = `${Math.min(currentX, startPoint.x)}px`;
    selectionBoxElement.style.top = `${Math.min(currentY, startPoint.y)}px`;
    selectionBoxElement.style.width = `${Math.abs(currentX - startPoint.x)}px`;
    selectionBoxElement.style.height = `${Math.abs(currentY - startPoint.y)}px`;
}

function onPointerUp(event) {
    if (!isBoxSelecting) return;
    
    const rect = event.currentTarget.getBoundingClientRect();
    const endPoint = new THREE.Vector2();
    endPoint.x = event.clientX - rect.left;
    endPoint.y = event.clientY;

    // Don't select if the box is just a point (a click, not a drag)
    if (startPoint.distanceTo(endPoint) < 5) {
        isBoxSelecting = false;
        selectionBoxElement.style.display = 'none';
        orbitControls.enabled = true;
        return;
    }

    // --- Perform the 3D Selection ---
    // Convert 2D screen coordinates to normalized device coordinates (-1 to +1)
    // (For some reason, here we have to subtract rect.top from the y-points)
    const startNDC = new THREE.Vector3( (startPoint.x / rect.width) * 2 - 1, -((startPoint.y - rect.top) / rect.height) * 2 + 1, 0.5);
    const endNDC = new THREE.Vector3( (endPoint.x / rect.width) * 2 - 1, -((endPoint.y - rect.top) / rect.height) * 2 + 1, 0.5);

    // The SelectionBox helper does the hard work of finding meshes inside the frustum
    const allSelectedMeshes = selectionBox.select(startNDC, endNDC);
    const visibleSelectedMeshes = allSelectedMeshes.filter(mesh => isObjectGloballyVisible(mesh));

    // Find the actual top-level mesh for each part found
    const initialSelection = visibleSelectedMeshes.map(mesh => findActualMesh(mesh));

    // --- Expand procedural selections ---
    const expandedSelection = [];
    const processedOwnerIds = new Set();
    const finalSelectionUUIDs = new Set(); // Use UUID to prevent adding the same THREE.Group twice

    initialSelection.forEach(group => {
        if (group.userData && group.userData.owner_pv_id) {
            // This is part of a procedural volume.
            const ownerId = group.userData.owner_pv_id;
            if (!processedOwnerIds.has(ownerId)) {
                // We haven't processed this procedural set yet.
                processedOwnerIds.add(ownerId);
                const allSlices = getMeshesForOwner(ownerId);
                allSlices.forEach(slice => {
                    if (!finalSelectionUUIDs.has(slice.uuid)) {
                        expandedSelection.push(slice);
                        finalSelectionUUIDs.add(slice.uuid);
                    }
                });
            }
        } else {
            // This is a regular, non-procedural physical volume.
            if (!finalSelectionUUIDs.has(group.uuid)) {
                expandedSelection.push(group);
                finalSelectionUUIDs.add(group.uuid);
            }
        }
    });
    
    // Pass the final, expanded array of selected groups to the main controller.
    if (onMultiObjectSelectedCallback) {
        onMultiObjectSelectedCallback(expandedSelection, event.ctrlKey);
    }

    // Cleanup
    isBoxSelecting = false;
    selectionBoxElement.style.display = 'none';
    orbitControls.enabled = true; // Re-enable orbit controls
}

function handlePointerDownForSelection(event) {
    if (event.button !== 0) return;
    if (transformControls.dragging) return;

    // Calculate the mouse coordinates relative to the event's target element,
    // which is the viewerContainer itself.
    const rect = event.currentTarget.getBoundingClientRect();
    mouse.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
    mouse.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;

    raycaster.setFromCamera(mouse, camera);

    let clickedOnGizmo = false;
    if (transformControls.object && transformControls.visible) {
        // --- Use the internal '_gizmo' property ---
        // Accessing _gizmo is necessary to raycast against only the visible handles.
        if (transformControls._gizmo) {
            const gizmoIntersects = raycaster.intersectObjects(transformControls._gizmo.children, true);
            if (gizmoIntersects.length > 0) {
                clickedOnGizmo = true;
            }
        } else {
             // Fallback for safety in case the internal structure changes in a future version.
             // This uses the whole helper, which is less precise but won't crash.
            const gizmoIntersects = raycaster.intersectObject(transformControls.getHelper(), true);
            if (gizmoIntersects.length > 0) {
                 clickedOnGizmo = true;
            }
        }
    }

    if (clickedOnGizmo) {
        // User clicked a handle. Let TransformControls manage the event.
        // We do nothing here to allow the drag to start.
        return;
    }

    // If we reach here, the user did NOT click a gizmo handle.
    
    // 1. Raycast against the *entire* geometry group, recursively. Do NOT pre-filter.
    // We don't need firstHitOnly because we need to check visibility on all hits.
    raycaster.firstHitOnly = false; 
    const intersects = raycaster.intersectObject(geometryGroup, true);

    // 2. Find the first intersected object that is globally visible.
    // Our isObjectGloballyVisible function correctly checks the entire chain up to the scene root.
    const firstVisibleIntersect = intersects.find(intersect => isObjectGloballyVisible(intersect.object));
    
    // 3. Process the result
    if (firstVisibleIntersect) {
        // We found a valid, visible object.
        const firstIntersectedGroup = findActualMesh(firstVisibleIntersect.object);
        if (onObjectSelectedCallback) {
            onObjectSelectedCallback(firstIntersectedGroup, event.ctrlKey, event.shiftKey);
        }
    } else {
        // The user clicked on empty space or only on hidden objects.
        if (!event.ctrlKey && onObjectSelectedCallback) {
            onObjectSelectedCallback(null, false, false);
        }
    }
}

function findActualMesh(object) {
    let current = object;
    // Traverse up the parent chain from the clicked mesh
    while (current) {
        // The first ancestor (or the object itself) that has a 'userData.id' is the
        // top-level group for our physical volume. This is the object we want to select.
        if (current.userData && current.userData.id) {
            return current;
        }
        // If we reach the top of our manageable geometry without finding a valid group, stop.
        if (current === geometryGroup || current === scene) {
            break;
        }
        current = current.parent;
    }
    // As a fallback, if no valid group was found (e.g., clicked an axis helper),
    // return the original intersected object. This prevents errors.
    return object;
}

export function setPVVisibility(pvId, isVisible) {
    const group = findObjectByPvId(pvId);
    if (group) {
        
        // Instead of setting group.visible, we toggle the visibility
        // of the renderable objects *inside* the group.
        // The group itself remains visible, so it doesn't affect its children.
        group.traverse(child => {
            if (child.isMesh || child.isLineSegments) {
                child.visible = isVisible;
            }
        });

        if (isVisible) {
            hiddenPvIds.delete(pvId);
        } else {
            hiddenPvIds.add(pvId);
        }
    }
}

export function setAllPVVisibility(isVisible) {
    // First, update the state Set. This part is correct.
    if (isVisible) {
        hiddenPvIds.clear();
    } else {
        const projectState = callbacks.getProjectState?.();
        if (projectState) {
            // This logic correctly gathers ALL pvIds.
            Object.values(projectState.logical_volumes).forEach(lv => {
                if (lv.content_type === 'physvol') { lv.content.forEach(pv => hiddenPvIds.add(pv.id)); }
                // Could add traversal for assembly children here if needed, but the scene traversal below handles it visually.
            });
             Object.values(projectState.assemblies).forEach(asm => {
                asm.placements.forEach(pv => hiddenPvIds.add(pv.id));
            });
        }
    }

    // Now, apply the new state to all three.js objects by toggling their meshes
    geometryGroup.traverse(group => {
        if (group.isGroup && group.userData.id) {
            const shouldBeVisible = !hiddenPvIds.has(group.userData.id);
            group.traverse(child => {
                if (child.isMesh || child.isLineSegments) {
                    child.visible = shouldBeVisible;
                }
            });
        }
    });
}

/**
 * Checks if a THREE.Object3D is globally visible by traversing up its parent hierarchy.
 * An object is only visible if it and all of its ancestors are visible.
 * @param {THREE.Object3D} object - The object to check.
 * @returns {boolean} - True if the object is rendered in the scene, false otherwise.
 */
function isObjectGloballyVisible(object) {
    let current = object;
    // Traverse up the scene graph
    while (current) {
        // If any parent (or the object itself) is not visible, then it's not globally visible.
        if (!current.visible) {
            return false;
        }
        current = current.parent;
    }
    // If we reached the top of the scene without finding an invisible parent, it's visible.
    return true;
}

// Helper function to find a mesh by its PV ID
export function findObjectByPvId(pvId) { // Renamed
    let foundObject = null;
    geometryGroup.traverse(child => {
        // We are now looking for the parent Group, not the mesh
        if (child.isGroup && child.userData && child.userData.id === pvId) {
            foundObject = child;
        }
    });
    return foundObject;
}

// --- Object Rendering ---
/**
 * Creates a Three.js geometry for a primitive solid definition.
 * @param {object} solidData - The solid definition from the project state.
 * @param {object} projectState - The full project state for lookups.
 * @param {Evaluator} csgEvaluator - The CSG evaluator instance.
 * @returns {THREE.BufferGeometry | null}
 */
export function createPrimitiveGeometry(solidData, projectState, csgEvaluator) {
    let geometry;
    
    // Use the _evaluated_parameters for rendering
    const p = solidData._evaluated_parameters;

    if (!p) {
        console.error(`[NaN TRAP] Solid '${solidData.name}' is missing its _evaluated_parameters. Cannot render.`);
        return new THREE.BoxGeometry(10, 10, 10); // Return a placeholder
    }

    // NaN Trap and Debugger ##
    // This block will check all expected parameters for the given solid type.
    const checkNaN = (paramsToCheck, solidName, solidType) => {
        for (const key of paramsToCheck) {
            const value = p[key];
            if (value === undefined || value === null || isNaN(value)) {
                console.error(
                    `[NaN TRAP] Found NaN or undefined parameter for solid:
                    - Name: ${solidName}
                    - Type: ${solidType}
                    - Parameter: '${key}'
                    - Value: ${value}
                    - Full Parameters Object:`, p
                );
                return true; // Indicates a NaN was found
            }
        }
        return false; // All good
    };
    
    let requiredParams = [];
    const solidType = solidData.type;

    // Define the required numeric parameters for each solid type
    if (solidType === 'box') requiredParams = ['x', 'y', 'z'];
    else if (solidType === 'tube') requiredParams = ['rmin', 'rmax', 'z', 'startphi', 'deltaphi'];
    else if (solidType === 'cone') requiredParams = ['rmin1', 'rmax1', 'rmin2', 'rmax2', 'z', 'startphi', 'deltaphi'];
    else if (solidType === 'sphere') requiredParams = ['rmin', 'rmax', 'startphi', 'deltaphi', 'starttheta', 'deltatheta'];
    else if (solidType === 'orb') requiredParams = ['r'];
    else if (solidType === 'torus') requiredParams = ['rmin', 'rmax', 'rtor', 'startphi', 'deltaphi'];
    // ... add other primitive types here as needed ...

    if (requiredParams.length > 0 && checkNaN(requiredParams, solidData.name, solidType)) {
        // If NaN is found, return a small, visible red box as a visual error indicator.
        const errorMaterial = new THREE.MeshBasicMaterial({ color: 0xff0000 });
        const errorGeometry = new THREE.BoxGeometry(20, 20, 20);
        return errorGeometry; // We don't need to assign a material here, just return the geometry
    }
    // End of NaN Trap

    // Temporary handling of null project state from solid editor
    const defines = (projectState && projectState.defines) ? projectState.defines : {};

    switch (solidData.type) {
        case 'box':
            geometry = new THREE.BoxGeometry(p.x, p.y, p.z);
            break;
        case 'tube':
            if (p.rmin <= 1e-9) { // Solid Cylinder
                geometry = new THREE.CylinderGeometry(p.rmax, p.rmax, p.z, 32, 1, false, p.startphi, p.deltaphi);
                geometry.rotateX(Math.PI / 2);
            } else { // Hollow Tube
                const shape = new THREE.Shape();
                shape.moveTo(p.rmax * Math.cos(p.startphi), p.rmax * Math.sin(p.startphi));
                shape.absarc(0, 0, p.rmax, p.startphi, p.startphi + p.deltaphi, false);
                shape.lineTo(p.rmin * Math.cos(p.startphi + p.deltaphi), p.rmin * Math.sin(p.startphi + p.deltaphi));
                shape.absarc(0, 0, p.rmin, p.startphi + p.deltaphi, p.startphi, true);
                shape.closePath();
                const extrudeSettings = { steps: 1, depth: p.z, bevelEnabled: false };
                geometry = new THREE.ExtrudeGeometry(shape, extrudeSettings);
                geometry.translate(0, 0, -p.z/2);
            }
            break;
        case 'cone':
            {
                // Create the outer cone shape
                const outerConeGeom = new THREE.CylinderGeometry(
                    p.rmax2,           // radiusTop
                    p.rmax1,           // radiusBottom
                    p.z,               // height
                    50,                // radialSegments (increased for smoothness)
                    1,                 // heightSegments
                    false,             // openEnded
                    p.startphi,
                    p.deltaphi
                );
                
                // If there's no inner radius, we are done.
                if (p.rmin1 <= 1e-9 && p.rmin2 <= 1e-9) {
                    geometry = outerConeGeom;
                } else {
                    // There is an inner radius, so we must perform a CSG subtraction.
                    
                    // Create the inner cone shape to subtract
                    const innerConeGeom = new THREE.CylinderGeometry(
                        p.rmin2,       // radiusTop
                        p.rmin1,       // radiusBottom
                        p.z     + 0.1, // height (make it slightly taller to ensure a clean cut)
                        50,            // radialSegments
                        1,
                        false,
                        p.startphi,
                        p.deltaphi
                    );

                    // Ensure both geometries have a BVH for the CSG operation
                    if (!outerConeGeom.boundsTree) {
                        outerConeGeom.computeBoundsTree();
                    }
                    if (!innerConeGeom.boundsTree) {
                        innerConeGeom.computeBoundsTree();
                    }

                    const outerBrush = new Brush(outerConeGeom);
                    const innerBrush = new Brush(innerConeGeom);

                    // Perform the subtraction
                    const resultBrush = csgEvaluator.evaluate(outerBrush, innerBrush, SUBTRACTION);
                    geometry = resultBrush.geometry;
                }
                
                // All G4Cons are aligned with the Z-axis. THREE.CylinderGeometry is aligned with Y.
                // We must rotate it into the correct orientation.
                geometry.rotateX(Math.PI / 2);
            }
            break;
        case 'sphere':
            geometry = new THREE.SphereGeometry(p.rmax, 32, 16, p.startphi, p.deltaphi, p.starttheta, p.deltatheta);
            // To handle the inner radius (hollow sphere), we must use CSG.
            if (p.rmin > 0) {
                const outerSphere = new Brush(geometry);
                const innerSphereGeom = new THREE.SphereGeometry(p.rmin, 32, 16, p.startphi, p.deltaphi, p.starttheta, p.deltatheta);
                const innerSphere = new Brush(innerSphereGeom);
                geometry = csgEvaluator.evaluate(outerSphere, innerSphere, SUBTRACTION).geometry;
            }
            break;
        case 'orb':
            geometry = new THREE.SphereGeometry(p.r, 32, 16);
            break;
        case 'ellipsoid':
            {
                // An ellipsoid is a scaled sphere. To handle z-cuts, we must use CSG.
                const sphereGeom = new THREE.SphereGeometry(1, 48, 24); // Unit sphere
                let resultBrush = new Brush(sphereGeom);
                
                // Apply non-uniform scaling to create the ellipsoid shape
                resultBrush.scale.set(p.ax, p.by, p.cz);
                resultBrush.updateMatrixWorld(); // Apply the scale

                // Z-Cut 1 (bottom)
                if (p.zcut1 !== undefined && p.zcut1 > -p.cz) { // Check if a cut is necessary
                    const planeGeom = new THREE.PlaneGeometry(p.ax * 2.1, p.by * 2.1);
                    const planeBrush = new Brush(planeGeom);
                    planeBrush.position.set(0, 0, p.zcut1 - 0.05); // Position the plane
                    // We need a box to subtract the entire lower portion
                    const cutBoxGeom = new THREE.BoxGeometry(p.ax * 2.2, p.by * 2.2, p.cz * 2);
                    const cutBoxBrush = new Brush(cutBoxGeom);
                    cutBoxBrush.position.set(0, 0, p.zcut1 - p.cz); // Position center of box
                    cutBoxBrush.updateMatrixWorld();
                    resultBrush = csgEvaluator.evaluate(resultBrush, cutBoxBrush, SUBTRACTION);
                }

                // Z-Cut 2 (top)
                if (p.zcut2 !== undefined && p.zcut2 < p.cz) {
                    const cutBoxGeom = new THREE.BoxGeometry(p.ax * 2.2, p.by * 2.2, p.cz * 2);
                    const cutBoxBrush = new Brush(cutBoxGeom);
                    cutBoxBrush.position.set(0, 0, p.zcut2 + p.cz);
                    cutBoxBrush.updateMatrixWorld();
                    resultBrush = csgEvaluator.evaluate(resultBrush, cutBoxBrush, SUBTRACTION);
                }
                
                geometry = resultBrush.geometry;
            }
            break;
        case 'torus':
            geometry = new THREE.TorusGeometry(p.rtor, p.rmax, 16, 100, p.deltaphi);
            if(p.startphi !== 0) geometry.rotateZ(p.startphi);
            break;
        case 'paraboloid':
            {
                const r_lo = p.rlo; // Radius at -dz
                const r_hi = p.rhi; // Radius at +dz
                const half_z = p.dz; // Half-length

                // Parabola equation: r(z) = a*z + b
                // We have two points (-dz, rlo) and (+dz, rhi), but it's r^2 = a*z + b
                // So, rlo^2 = a*(-dz) + b  and  rhi^2 = a*(+dz) + b
                // Solving for a and b:
                // a = (rhi^2 - rlo^2) / (2 * dz)
                // b = (rhi^2 + rlo^2) / 2
                
                const points = [];
                const segments = 20;

                if (Math.abs(half_z) > 1e-9) {
                    const a = (r_hi * r_hi - r_lo * r_lo) / (2 * half_z);
                    const b = (r_hi * r_hi + r_lo * r_lo) / 2;

                    for (let i = 0; i <= segments; i++) {
                        const z = -half_z + (2 * half_z * i) / segments;
                        const r_sq = a * z + b;
                        // Ensure we don't take sqrt of a negative number
                        const r = (r_sq > 0) ? Math.sqrt(r_sq) : 0;
                        points.push(new THREE.Vector2(r, z));
                    }
                }

                if (points.length > 1) {
                    geometry = new THREE.LatheGeometry(points, 32, 0, 2 * Math.PI);
                    geometry.rotateX(-Math.PI / 2);
                } else {
                    geometry = new THREE.SphereGeometry(10, 8, 8); // Placeholder
                }
            }
            break;
        case 'hype':
            {
                const rmin = p.rmin;
                const rmax = p.rmax;
                const halfZ = p.z / 2; // This should be the half-length
                const tanInnerStereo = Math.tan(p.inst);
                const tanOuterStereo = Math.tan(p.outst);

                const points = [];
                const segments = 20; // Number of points to define the curve

                for (let i = 0; i <= segments; i++) {
                    const z = -halfZ + (2 * halfZ * i) / segments;
                    // Hyperbola formula: r^2 = r0^2 + (tan(stereo))^2 * z^2
                    const r_inner = Math.sqrt(rmin * rmin + tanInnerStereo * tanInnerStereo * z * z);
                    points.push(new THREE.Vector2(r_inner, z));
                }
                for (let i = segments; i >= 0; i--) {
                    const z = -halfZ + (2 * halfZ * i) / segments;
                    const r_outer = Math.sqrt(rmax * rmax + tanOuterStereo * tanOuterStereo * z * z);
                    points.push(new THREE.Vector2(r_outer, z));
                }

                // Close the shape if rmin is not zero
                if (rmin > 1e-9) {
                     points.push(points[0]);
                }


                if (points.length > 1) {
                    // Revolve the 2D profile around the Z-axis (which is Y in LatheGeometry's frame)
                    // Note: Hype in GDML doesn't have start/end phi angles, so we use a full circle.
                    geometry = new THREE.LatheGeometry(points, 32, 0, 2 * Math.PI);
                    // LatheGeometry revolves around Y, so rotate to align with the Z-axis.
                    geometry.rotateX(-Math.PI / 2);
                } else {
                    geometry = new THREE.SphereGeometry(10, 8, 8); // Placeholder
                }
            }
            break;
        case 'polycone':
            {
                const zplanes = p.zplanes || [];
                const points = [];
                if (zplanes.length > 1) {
                    // Sort planes by Z just in case they are out of order
                    zplanes.sort((a, b) => a.z - b.z);
                    
                    // Trace the outer profile from bottom to top
                    for (let i = 0; i < zplanes.length; i++) {
                        points.push(new THREE.Vector2(zplanes[i].rmax, zplanes[i].z));
                    }
                    // Trace the inner profile from top to bottom
                    for (let i = zplanes.length - 1; i >= 0; i--) {
                        points.push(new THREE.Vector2(zplanes[i].rmin, zplanes[i].z));
                    }
                    
                    geometry = new THREE.LatheGeometry(points, 50, p.startphi, p.deltaphi);
                    geometry.rotateX(Math.PI / 2); // Align with Z-axis
                } else {
                    geometry = new THREE.SphereGeometry(10, 8, 8); // Placeholder
                }
            }
            break;
        case 'genericPolycone':
        case 'polyhedra':
        case 'genericPolyhedra':
            {
                const points = [];
                const isPolyhedra = solidData.type.includes('polyhedra');
                const numSides = isPolyhedra ? (p.numsides || 8) : 32;

                // GDML polycone is defined by a series of z-planes, each with rmin, rmax, and z.
                // We need to create a 2D profile from these that LatheGeometry can revolve.
                const zplanes = p.zplanes || [];
                if (zplanes.length > 0) {
                    // Create the profile for lathing.
                    // Start at the bottom-outer point
                    points.push(new THREE.Vector2(zplanes[0].rmax, zplanes[0].z));
                    
                    // Inner profile edge
                    for (let i = 0; i < zplanes.length; i++) {
                        points.push(new THREE.Vector2(zplanes[i].rmin, zplanes[i].z));
                    }
                    // Outer profile edge (in reverse)
                    for (let i = zplanes.length - 1; i >= 0; i--) {
                        points.push(new THREE.Vector2(zplanes[i].rmax, zplanes[i].z));
                    }

                } else if (p.rzpoints && p.rzpoints.length > 0) {
                    // For genericPolycone/genericPolyhedra, the profile is given directly by r-z points.
                    p.rzpoints.forEach(point => {
                        points.push(new THREE.Vector2(point.r, point.z));
                    });
                }
                
                if (points.length > 0) {
                    geometry = new THREE.LatheGeometry(points, numSides, p.startphi, p.deltaphi);
                    // LatheGeometry revolves around Y, so we must rotate it to align with Z.
                    geometry.rotateX(-Math.PI / 2);
                } else {
                    console.warn(`[SceneManager] Polycone/hedra '${solidData.name}' has no z-planes or rz-points.`);
                    geometry = new THREE.SphereGeometry(10, 8, 8); // Placeholder
                }
            }
            break;
        case 'xtru':
            {
                // Use the pre-evaluated parameters, which have units already applied.
                const twoDimVertices = p.twoDimVertices;
                const sections = p.sections;

                if (!twoDimVertices || twoDimVertices.length < 3 || !sections || sections.length < 2) {
                    console.error(`[SceneManager] xtru solid '${solidData.name}' has invalid parameters.`);
                    return new THREE.SphereGeometry(10, 8, 8);
                }

                geometry = new THREE.BufferGeometry();
                const vertices = [];
                const indices = [];

                // Generate vertices for each section plane, applying the transform
                const sectionVertices = sections.map(sec => {
                    return twoDimVertices.map(v => {
                        // The evaluated 'p' object contains numeric values in the correct internal unit (mm)
                        return new THREE.Vector3(
                            v.x * sec.scalingFactor + sec.xOffset,
                            v.y * sec.scalingFactor + sec.yOffset,
                            sec.zPosition
                        );
                    });
                });

                // Add all vertices to a single flat array for the BufferGeometry
                sectionVertices.forEach(verts => {
                    verts.forEach(v => vertices.push(v.x, v.y, v.z));
                });
                
                // Create the side faces by connecting vertices between sections
                for (let i = 0; i < sections.length - 1; i++) {
                    const baseIndex1 = i * twoDimVertices.length;
                    const baseIndex2 = (i + 1) * twoDimVertices.length;
                    for (let j = 0; j < twoDimVertices.length; j++) {
                        const next_j = (j + 1) % twoDimVertices.length;
                        const p1 = baseIndex1 + j;
                        const p2 = baseIndex1 + next_j;
                        const p3 = baseIndex2 + next_j;
                        const p4 = baseIndex2 + j;
                        // Correct winding order for outward-facing normals
                        indices.push(p1, p2, p3);
                        indices.push(p1, p3, p4);
                    }
                }
                
                // --- Capping ---
                // We must add the vertices of the caps to our main vertex array
                // and then add the indices. Using ShapeGeometry is better.

                // Let's use a more robust method with ExtrudeGeometry and a custom path.
                
                // 1. Create the 2D base shape
                const shapePoints = twoDimVertices.map(v => new THREE.Vector2(v.x, v.y));
                const shape = new THREE.Shape(shapePoints);
                
                // 2. Define the extrusion settings. Since the path is not a simple line,
                // we have to build the geometry manually. The previous manual logic was correct
                // in principle, but flawed. Let's fix the manual cap triangulation.
                
                // Start Cap (at the first section)
                const startCapPoints = sectionVertices[0]; // These are already transformed Vector3s
                // We need to project them onto a 2D plane for triangulation.
                const startCapPoints2D = startCapPoints.map(v => new THREE.Vector2(v.x, v.y));
                const startCapTriangles = THREE.ShapeUtils.triangulateShape(startCapPoints2D, []);
                const startBaseIndex = 0;
                startCapTriangles.forEach(tri => {
                    // Reversed winding order for the start cap (facing -Z)
                    indices.push(startBaseIndex + tri[0], startBaseIndex + tri[2], startBaseIndex + tri[1]);
                });

                // End Cap (at the last section)
                const endCapPoints = sectionVertices[sections.length - 1];
                const endCapPoints2D = endCapPoints.map(v => new THREE.Vector2(v.x, v.y));
                const endCapTriangles = THREE.ShapeUtils.triangulateShape(endCapPoints2D, []);
                const endBaseIndex = (sections.length - 1) * twoDimVertices.length;
                endCapTriangles.forEach(tri => {
                    // Normal winding order for the end cap (facing +Z)
                    indices.push(endBaseIndex + tri[0], endBaseIndex + tri[1], endBaseIndex + tri[2]);
                });

                geometry.setAttribute('position', new THREE.Float32BufferAttribute(new Float32Array(vertices), 3));
                geometry.setIndex(indices);
                geometry.computeVertexNormals();
            }
            break;
        case 'tet': // Tetrahedron
            {
                const defines = projectState.defines;
                const v1 = p.vertex1;
                const v2 = p.vertex2;
                const v3 = p.vertex3;
                const v4 = p.vertex4;
                
                if (!v1 || !v2 || !v3 || !v4) {
                    console.error(`[SceneManager] Could not find all vertex definitions for tet '${solidData.name}'`);
                    return new THREE.SphereGeometry(10, 8, 8); // Placeholder
                }

                const vertices = new Float32Array([
                    v1.x, v1.y, v1.z,
                    v2.x, v2.y, v2.z,
                    v3.x, v3.y, v3.z,
                    v4.x, v4.y, v4.z,
                ]);

                // Define the 4 triangular faces using vertex indices
                const indices = [
                    0, 2, 1, // Face 1
                    0, 1, 3, // Face 2
                    1, 2, 3, // Face 3
                    2, 0, 3  // Face 4
                ];

                geometry = new THREE.BufferGeometry();
                geometry.setAttribute('position', new THREE.BufferAttribute(vertices, 3));
                geometry.setIndex(indices);
                geometry.computeVertexNormals();
            }
            break;
        
        case 'tessellated':
            {
                const defines = projectState.defines;
                const vertices = [];
                const indices = [];
                const vertexMap = new Map(); // Map to store unique vertex indices { 'vertex_ref_name' -> index }
                let vertexCounter = 0;

                const getVertexIndex = (refName) => {
                    if (vertexMap.has(refName)) {
                        return vertexMap.get(refName);
                    }
                    const vertexDef = defines[refName];
                    if (!vertexDef) {
                        console.error(`[SceneManager] Could not find vertex definition for '${refName}'`);
                        return -1;
                    }
                    vertices.push(vertexDef.value.x, vertexDef.value.y, vertexDef.value.z);
                    const newIndex = vertexCounter;
                    vertexMap.set(refName, newIndex);
                    vertexCounter++;
                    return newIndex;
                };

                p.facets.forEach(facet => {
                    if (facet.type === 'triangular') {
                        const i1 = getVertexIndex(facet.vertex_refs[0]);
                        const i2 = getVertexIndex(facet.vertex_refs[1]);
                        const i3 = getVertexIndex(facet.vertex_refs[2]);
                        if (i1 !== -1 && i2 !== -1 && i3 !== -1) {
                           indices.push(i1, i2, i3);
                        }
                    } else if (facet.type === 'quadrangular') {
                        // A quad is two triangles
                        const i1 = getVertexIndex(facet.vertex_refs[0]);
                        const i2 = getVertexIndex(facet.vertex_refs[1]);
                        const i3 = getVertexIndex(facet.vertex_refs[2]);
                        const i4 = getVertexIndex(facet.vertex_refs[3]);
                         if (i1 !== -1 && i2 !== -1 && i3 !== -1 && i4 !== -1) {
                            indices.push(i1, i2, i3); // First triangle (v1, v2, v3)
                            indices.push(i1, i3, i4); // Second triangle (v1, v3, v4)
                        }
                    }
                });

                geometry = new THREE.BufferGeometry();
                geometry.setAttribute('position', new THREE.BufferAttribute(new Float32Array(vertices), 3));
                geometry.setIndex(indices);
                geometry.computeVertexNormals();
            }
            break;
        case 'cutTube':
            {
                // 1. Create the basic tube geometry.
                let tubeGeom;
                if (p.rmin <= 1e-9) { // Solid Cylinder
                    tubeGeom = new THREE.CylinderGeometry(p.rmax, p.rmax, p.z * 2, 50, 1, false, p.startphi, p.deltaphi);

                    // Need to do some rotations to obtain the same orientation as the hollow tube
                    tubeGeom.rotateX(-Math.PI / 2);
                    tubeGeom.rotateZ(Math.PI / 2);
                } else { // Hollow Tube
                    const shape = new THREE.Shape();
                    shape.moveTo(p.rmax * Math.cos(p.startphi), p.rmax * Math.sin(p.startphi));
                    shape.absarc(0, 0, p.rmax, p.startphi, p.startphi + p.deltaphi, false);
                    shape.lineTo(p.rmin * Math.cos(p.startphi + p.deltaphi), p.rmin * Math.sin(p.startphi + p.deltaphi));
                    shape.absarc(0, 0, p.rmin, p.startphi + p.deltaphi, p.startphi, true);
                    shape.closePath();
                    const extrudeSettings = { steps: 1, depth: p.z * 2, bevelEnabled: false };
                    tubeGeom = new THREE.ExtrudeGeometry(shape, extrudeSettings);
                    tubeGeom.translate(0, 0, -p.z);
                }
                
                // G4CutTubs is aligned to Z axis, which matches our tube extrusion.
                let resultBrush = new Brush(tubeGeom);

                // 2. Create two large boxes representing the half-spaces to KEEP.
                const boxSize = (p.rmax + p.z) * 4;
                
                // Low normal cut
                const lowNormal = new THREE.Vector3(p.lowX, p.lowY, p.lowZ).normalize();
                const boxGeomLow = new THREE.BoxGeometry(boxSize, boxSize, boxSize);
                const boxBrushLow = new Brush(boxGeomLow);
                // Position the box so one face is on the cutting plane and it extends away from the normal
                boxBrushLow.position.copy(lowNormal).multiplyScalar(-boxSize / 2.0);
                boxBrushLow.quaternion.setFromUnitVectors(new THREE.Vector3(0, 0, 1), lowNormal);
                boxBrushLow.updateMatrixWorld();
                
                // 3. Intersect the tube with the first half-space.
                resultBrush = csgEvaluator.evaluate(resultBrush, boxBrushLow, INTERSECTION);

                // High normal cut
                const highNormal = new THREE.Vector3(p.highX, p.highY, p.highZ).normalize();
                const boxGeomHigh = new THREE.BoxGeometry(boxSize, boxSize, boxSize);
                const boxBrushHigh = new Brush(boxGeomHigh);
                // Position this box so one face is on the plane and it extends away from the normal
                boxBrushHigh.position.copy(highNormal).multiplyScalar(boxSize / 2.0);
                boxBrushHigh.quaternion.setFromUnitVectors(new THREE.Vector3(0, 0, -1), highNormal);
                boxBrushHigh.updateMatrixWorld();
                
                // 4. Intersect the result with the second half-space.
                resultBrush = csgEvaluator.evaluate(resultBrush, boxBrushHigh, INTERSECTION);

                geometry = resultBrush.geometry;
            }
            break;
        case 'para': // Parallelepiped
            {
                // p.x, p.y, p.z from the evaluator are the FULL lengths from GDML.
                // The vertex formula requires HALF-lengths.
                const dx = p.x / 2.0;
                const dy = p.y / 2.0;
                const dz = p.z / 2.0;

                const t_alpha = Math.tan(p.alpha);
                const t_theta_cp = Math.tan(p.theta) * Math.cos(p.phi);
                const t_theta_sp = Math.tan(p.theta) * Math.sin(p.phi);

                const vertices = [
                    // This vertex calculation formula is based on half-lengths and is correct.
                    -dx - dy*t_alpha - dz*t_theta_cp, -dy - dz*t_theta_sp, -dz, // 0
                     dx - dy*t_alpha - dz*t_theta_cp, -dy - dz*t_theta_sp, -dz, // 1
                     dx + dy*t_alpha - dz*t_theta_cp,  dy - dz*t_theta_sp, -dz, // 2
                    -dx + dy*t_alpha - dz*t_theta_cp,  dy - dz*t_theta_sp, -dz, // 3
                    -dx - dy*t_alpha + dz*t_theta_cp, -dy + dz*t_theta_sp,  dz, // 4
                     dx - dy*t_alpha + dz*t_theta_cp, -dy + dz*t_theta_sp,  dz, // 5
                     dx + dy*t_alpha + dz*t_theta_cp,  dy + dz*t_theta_sp,  dz, // 6
                    -dx + dy*t_alpha + dz*t_theta_cp,  dy + dz*t_theta_sp,  dz  // 7
                ];
                
                // The indices for the faces are correct.
                const indices = [
                    0, 1, 2,  0, 2, 3, // bottom
                    4, 6, 5,  4, 7, 6, // top
                    0, 4, 5,  0, 5, 1, // front
                    1, 5, 6,  1, 6, 2, // right
                    2, 6, 7,  2, 7, 3, // back
                    3, 7, 4,  3, 4, 0  // left
                ];

                geometry = new THREE.BufferGeometry();
                geometry.setAttribute('position', new THREE.Float32BufferAttribute(new Float32Array(vertices), 3));
                geometry.setIndex(indices);
                geometry.computeVertexNormals();
            }
            break;
        case 'trd': // Trapezoid with parallel z-faces
            {
                // A Trd can be made with CylinderGeometry with 4 sides.
                // We need to map Trd params (dx1, dx2, dy1, dy2) to Cylinder params (radiusTop, radiusBottom).
                // This is only a rough approximation if dx != dy.
                // For accuracy, we'll build it from vertices.
                const dx1 = p.dx1; const dx2 = p.dx2;
                const dy1 = p.dy1; const dy2 = p.dy2;
                const dz = p.dz;
                const vertices = [
                    -dx1, -dy1, -dz, // 0
                     dx1, -dy1, -dz, // 1
                     dx1,  dy1, -dz, // 2
                    -dx1,  dy1, -dz, // 3
                    -dx2, -dy2,  dz, // 4
                     dx2, -dy2,  dz, // 5
                     dx2,  dy2,  dz, // 6
                    -dx2,  dy2,  dz  // 7
                ];
                const indices = [
                    0, 1, 2,  0, 2, 3, // bottom face
                    4, 5, 6,  4, 6, 7, // top face
                    0, 4, 5,  0, 5, 1, // front face
                    1, 5, 6,  1, 6, 2, // right face
                    2, 6, 7,  2, 7, 3, // back face
                    3, 7, 4,  3, 4, 0  // left face
                ];
                geometry = new THREE.BufferGeometry();
                geometry.setAttribute('position', new THREE.Float32BufferAttribute(vertices, 3));
                geometry.setIndex(indices);
                geometry.computeVertexNormals();
            }
            break;
        case 'eltube':
            {
                const dx = p.dx;
                const dy = p.dy;
                const halfZ = p.dz;

                // Create a circular cylinder with radius dx
                geometry = new THREE.CylinderGeometry(dx, dx, halfZ * 2, 32);
                
                // Scale it non-uniformly in the Y direction to make it elliptical
                // (note since we're rotating later, we have to apply the scale to the Z-direction)
                geometry.scale(1, 1, dy/dx);
                
                // Rotate to align with the Z-axis
                geometry.rotateX(Math.PI / 2);
            }
            break;
        case 'elcone':
            {
                const dx = p.dx;
                const dy = p.dy;
                const zMax = p.zmax;
                const zCut = p.zcut;

                // The radius of the circular cone at height z is: r(z) = (dx/zMax) * z
                // For our cone geometry, we need the radius at the base (z=zMax).
                const baseRadius = dx;
                
                // 1. Create a basic circular cone pointing up the Z-axis.
                // It goes from z=0 to z=zMax.
                const coneGeom = new THREE.ConeGeometry(baseRadius, zMax, 32);
                
                // 2. Translate it so its base is at z=0 and its tip is at z=zMax.
                coneGeom.translate(0, zMax / 2, 0);
                
                // 3. Scale it to make it elliptical.
                coneGeom.scale(1, 1, dy / dx); // Scale along Z-axis in this frame

                // 4. Create a large box to perform the z-cut.
                const cutBox = new THREE.BoxGeometry(dx * 4, zMax, dy * 4);
                // Position the box so its top face is at z=zCut
                cutBox.translate(0, (zMax + zCut) / 2, 0);

                // 5. Perform the CSG subtraction.
                const coneBrush = new Brush(coneGeom);
                const cutBrush = new Brush(cutBox);
                const resultBrush = csgEvaluator.evaluate(coneBrush, cutBrush, SUBTRACTION);

                geometry = resultBrush.geometry;

                // 6. Rotate to align with the standard GDML Z-axis.
                geometry.rotateX(-Math.PI / 2);
            }
            break;
        case 'trap': // General Trapezoid
            {
                const vertices = [];
                const dz = p.dz; const th = p.theta; const ph = p.phi;
                const dy1 = p.dy1; const dx1 = p.dx1; const dx2 = p.dx2;
                const dy2 = p.dy2; const dx3 = p.dx3; const dx4 = p.dx4;
                const a1 = p.alpha1; const a2 = p.alpha2;
                const tth_cp = Math.tan(th) * Math.cos(ph);
                const tth_sp = Math.tan(th) * Math.sin(ph);
                const ta1 = Math.tan(a1);
                const ta2 = Math.tan(a2);
                
                vertices.push(
                    -dz*tth_cp - dy1*ta1 - dx1, -dz*tth_sp - dy1, -dz,
                    -dz*tth_cp - dy1*ta1 + dx1, -dz*tth_sp - dy1, -dz,
                    -dz*tth_cp + dy1*ta1 - dx2, -dz*tth_sp + dy1, -dz,
                    -dz*tth_cp + dy1*ta1 + dx2, -dz*tth_sp + dy1, -dz,
                        dz*tth_cp - dy2*ta2 - dx3,  dz*tth_sp - dy2,  dz,
                        dz*tth_cp - dy2*ta2 + dx3,  dz*tth_sp - dy2,  dz,
                        dz*tth_cp + dy2*ta2 - dx4,  dz*tth_sp + dy2,  dz,
                        dz*tth_cp + dy2*ta2 + dx4,  dz*tth_sp + dy2,  dz
                );
                
                const indices = [
                    0, 1, 2,  0, 2, 3, // bottom
                    4, 5, 6,  4, 6, 7, // top
                    0, 4, 5,  0, 5, 1, // front
                    1, 5, 6,  1, 6, 2, // right
                    2, 6, 7,  2, 7, 3, // back
                    3, 7, 4,  3, 4, 0  // left
                ];
                
                geometry = new THREE.BufferGeometry();
                geometry.setAttribute('position', new THREE.Float32BufferAttribute(vertices, 3));
                geometry.setIndex(indices);
                geometry.computeVertexNormals();
            }
            break;
        case 'twistedbox':
            {
                // Both twistedbox and twistedtrd can be handled by the same logic.
                // A twistedbox is just a twistedtrd with dx1=dx2 and dy1=dy2.
                const dz = p.z;
                const phiTwist = p.PhiTwist;
                
                // Define the 2D vertices for the bottom and top faces
                const dx1 = p.x1 !== undefined ? p.x1 : p.x; // Use 'dx' for twistedbox
                const dy1 = p.y1 !== undefined ? p.y1 : p.y;
                const dx2 = p.x2 !== undefined ? p.x2 : p.x;
                const dy2 = p.y2 !== undefined ? p.y2 : p.y;

                const bottomVerts = [
                    new THREE.Vector2(-dx1, -dy1),
                    new THREE.Vector2( dx1, -dy1),
                    new THREE.Vector2( dx1,  dy1),
                    new THREE.Vector2(-dx1,  dy1),
                ];

                const topVerts = [
                    new THREE.Vector2(-dx2, -dy2),
                    new THREE.Vector2( dx2, -dy2),
                    new THREE.Vector2( dx2,  dy2),
                    new THREE.Vector2(-dx2,  dy2),
                ];

                // The core algorithm for a twisted prism:
                const vertices = [];
                const indices = [];
                const rotationAxis = new THREE.Vector3(0, 0, 1);
                
                // Calculate the 3D vertices for top and bottom faces
                const bottom3D = bottomVerts.map(v => new THREE.Vector3(v.x, v.y, -dz));
                const top3D = topVerts.map(v => 
                    new THREE.Vector3(v.x, v.y, 0).applyAxisAngle(rotationAxis, phiTwist).setZ(dz)
                );
                
                vertices.push(...bottom3D.flatMap(v => [v.x, v.y, v.z]));
                vertices.push(...top3D.flatMap(v => [v.x, v.y, v.z]));

                // Create side faces
                for (let i = 0; i < 4; i++) {
                    const next_i = (i + 1) % 4;
                    const p1 = i;         // bottom face, current vertex
                    const p2 = next_i;    // bottom face, next vertex
                    const p3 = next_i + 4;// top face, next vertex
                    const p4 = i + 4;     // top face, current vertex
                    indices.push(p1, p2, p3,  p1, p3, p4);
                }

                // Create caps
                indices.push(0, 2, 1,  0, 3, 2); // Bottom cap
                indices.push(4, 5, 6,  4, 6, 7); // Top cap

                geometry = new THREE.BufferGeometry();
                geometry.setAttribute('position', new THREE.Float32BufferAttribute(vertices, 3));
                geometry.setIndex(indices);
                geometry.computeVertexNormals();
            }
            break;
        case 'twistedtrap':
            {
                const halfZ = p.z;
                const y1 = p.y1; const x1 = p.x1; const x2 = p.x2;
                const y2 = p.y2; const x3 = p.x3; const x4 = p.x4;
                const phiTwist = p.PhiTwist; // Twist angle
                const theta = p.Theta; // Polar angle of line joining face centers
                const phi = p.Phi; // Azimuthal angle of line joining face centers
                const alph = p.Alph; // Tilt angle of y-sides

                // Calculate the 8 vertices of the twisted trap.
                // This logic directly mimics the G4TwistedTrap constructor.
                const tanAlph = Math.tan(alph);
                const tanTheta_cosPhi = Math.tan(theta) * Math.cos(phi);
                const tanTheta_sinPhi = Math.tan(theta) * Math.sin(phi);

                const vertices = [
                    new THREE.Vector3(-tanTheta_cosPhi * halfZ - tanAlph * y1 - x1, -tanTheta_sinPhi * halfZ - y1, -halfZ), // 0
                    new THREE.Vector3(-tanTheta_cosPhi * halfZ - tanAlph * y1 + x1, -tanTheta_sinPhi * halfZ - y1, -halfZ), // 1
                    new THREE.Vector3(-tanTheta_cosPhi * halfZ + tanAlph * y1 - x2, -tanTheta_sinPhi * halfZ + y1, -halfZ), // 2
                    new THREE.Vector3(-tanTheta_cosPhi * halfZ + tanAlph * y1 + x2, -tanTheta_sinPhi * halfZ + y1, -halfZ), // 3
                    new THREE.Vector3( tanTheta_cosPhi * halfZ - tanAlph * y2 - x3,  tanTheta_sinPhi * halfZ - y2,  halfZ), // 4
                    new THREE.Vector3( tanTheta_cosPhi * halfZ - tanAlph * y2 + x3,  tanTheta_sinPhi * halfZ - y2,  halfZ), // 5
                    new THREE.Vector3( tanTheta_cosPhi * halfZ + tanAlph * y2 - x4,  tanTheta_sinPhi * halfZ + y2,  halfZ), // 6
                    new THREE.Vector3( tanTheta_cosPhi * halfZ + tanAlph * y2 + x4,  tanTheta_sinPhi * halfZ + y2,  halfZ)  // 7
                ];
                
                // Apply the twist to the top face (+z) vertices
                const rot = new THREE.Matrix4().makeRotationZ(phiTwist);
                for (let i = 4; i < 8; i++) {
                    vertices[i].applyMatrix4(rot);
                }

                // Create geometry from the 8 vertices. THREE.ConvexGeometry is perfect for this.
                geometry = new ConvexGeometry(vertices);
            }
            break;
        case 'twistedtrd':
            {
                // This is a twisted trd, which is a twisted trapezoid with parallel x-y faces.
                // It's a twistedbox with different dimensions at the top and bottom.
                const dz = p.z; // half-length z
                const phiTwist = p.PhiTwist;

                // Define the 2D vertices for the bottom (-z) and top (+z) faces
                const bottomVerts = [
                    new THREE.Vector2(-p.x1, -p.y1),
                    new THREE.Vector2( p.x1, -p.y1),
                    new THREE.Vector2( p.x1,  p.y1),
                    new THREE.Vector2(-p.x1,  p.y1),
                ];
                const topVerts = [
                    new THREE.Vector2(-p.x2, -p.y2),
                    new THREE.Vector2( p.x2, -p.y2),
                    new THREE.Vector2( p.x2,  p.y2),
                    new THREE.Vector2(-p.x2,  p.y2),
                ];

                // The rendering algorithm is identical to twistedbox, just with different vertices.
                const vertices = [];
                const indices = [];
                const rotationAxis = new THREE.Vector3(0, 0, 1);
                
                const bottom3D = bottomVerts.map(v => new THREE.Vector3(v.x, v.y, -dz));
                const top3D = topVerts.map(v =>
                    new THREE.Vector3(v.x, v.y, 0).applyAxisAngle(rotationAxis, phiTwist).setZ(dz)
                );
                
                vertices.push(...bottom3D.flatMap(v => [v.x, v.y, v.z]));
                vertices.push(...top3D.flatMap(v => [v.x, v.y, v.z]));
                
                // Create side faces
                for (let i = 0; i < 4; i++) {
                    const next_i = (i + 1) % 4;
                    const p1 = i;         // bottom face, current vertex
                    const p2 = next_i;    // bottom face, next vertex
                    const p3 = next_i + 4;// top face, next vertex
                    const p4 = i + 4;     // top face, current vertex
                    indices.push(p1, p2, p3,  p1, p3, p4);
                }
                // Create caps
                indices.push(0, 1, 2,  0, 2, 3); // Bottom cap (flipped winding)
                indices.push(4, 6, 5,  4, 7, 6); // Top cap
                
                geometry = new THREE.BufferGeometry();
                geometry.setAttribute('position', new THREE.Float32BufferAttribute(new Float32Array(vertices), 3));
                geometry.setIndex(indices);
                geometry.computeVertexNormals();
            }
            break;
        case 'twistedtubs':
            {
                // Get parameters from the solid editor
                const rmin = p.endinnerrad;
                const rmax = p.endouterrad;
                const halfZ = p.zlen;
                const dphi = p.phi; // phi sector angle in radians
                const twist = p.twistedangle; // total twist angle in radians

                const radialSegments = 32;
                const heightSegments = 10;
                
                const vertices = [];
                const indices = [];

                // Helper to generate a vertex
                const getVertex = (r, phi, z, currentTwist) => {
                    const x = r * Math.cos(phi);
                    const y = r * Math.sin(phi);
                    const vec = new THREE.Vector3(x, y, 0);
                    vec.applyAxisAngle(new THREE.Vector3(0, 0, 1), currentTwist);
                    vec.z = z;
                    return vec;
                };

                // Generate all vertices for the entire shape first
                for (let j = 0; j <= heightSegments; j++) {
                    const v = j / heightSegments; // Fractional height
                    const z = -halfZ + v * (2 * halfZ);
                    const currentTwist = twist * (v - 0.5); // Twist centered at z=0

                    for (let i = 0; i <= radialSegments; i++) {
                        const u = i / radialSegments; // Fractional angle
                        const phi = u * dphi;
                        
                        // Outer surface vertex
                        vertices.push(getVertex(rmax, phi, z, currentTwist));
                        
                        // Inner surface vertex (if it exists)
                        if (rmin > 0) {
                            vertices.push(getVertex(rmin, phi, z, currentTwist));
                        }
                    }
                }

                const pointsPerRow = (rmin > 0) ? (radialSegments + 1) * 2 : (radialSegments + 1);

                // Generate indices for the faces (sides)
                for (let j = 0; j < heightSegments; j++) {
                    for (let i = 0; i < radialSegments; i++) {
                        const row1 = j * pointsPerRow;
                        const row2 = (j + 1) * pointsPerRow;
                        const pointsPerSegment = (rmin > 0) ? 2 : 1;

                        // Outer surface quad
                        const p1 = row1 + i * pointsPerSegment;
                        const p2 = row1 + (i + 1) * pointsPerSegment;
                        const p3 = row2 + (i + 1) * pointsPerSegment;
                        const p4 = row2 + i * pointsPerSegment;
                        indices.push(p1, p2, p3);
                        indices.push(p1, p3, p4);

                        // Inner surface quad (if it exists)
                        if (rmin > 0) {
                            const p1_in = p1 + 1;
                            const p2_in = p2 + 1;
                            const p3_in = p3 + 1;
                            const p4_in = p4 + 1;
                            // Flipped winding order for inward-facing normals
                            indices.push(p1_in, p3_in, p2_in);
                            indices.push(p1_in, p4_in, p3_in);
                        }
                    }
                }

                // --- Add Caps and Sides for Phi Segments ---
                if (Math.abs(dphi - 2 * Math.PI) > 1e-9) { // If it's not a full tube
                    // Add side face at phi = 0
                    for (let j = 0; j < heightSegments; j++) {
                        const row1 = j * pointsPerRow;
                        const row2 = (j + 1) * pointsPerRow;
                        if (rmin > 0) {
                           const p1 = row1; const p2 = row1 + 1; const p3 = row2 + 1; const p4 = row2;
                           indices.push(p1, p3, p2); indices.push(p1, p4, p3);
                        }
                    }
                    // Add side face at phi = dphi
                    for (let j = 0; j < heightSegments; j++) {
                        const row1 = j * pointsPerRow + radialSegments * ((rmin > 0) ? 2 : 1);
                        const row2 = (j + 1) * pointsPerRow + radialSegments * ((rmin > 0) ? 2 : 1);
                        if (rmin > 0) {
                           const p1 = row1; const p2 = row1 + 1; const p3 = row2 + 1; const p4 = row2;
                           indices.push(p1, p2, p3); indices.push(p1, p4, p2);
                        }
                    }
                }
                
                // Add top and bottom caps (triangulation)
                for (let i = 0; i < radialSegments; i++) {
                    const pointsPerSegment = (rmin > 0) ? 2 : 1;
                    // Bottom cap
                    const b_p1 = i * pointsPerSegment;
                    const b_p2 = (i + 1) * pointsPerSegment;
                    if (rmin > 0) {
                        const b_p3 = (i + 1) * pointsPerSegment + 1;
                        const b_p4 = i * pointsPerSegment + 1;
                        indices.push(b_p1, b_p3, b_p2); indices.push(b_p1, b_p4, b_p3);
                    }
                    // Top cap
                    const topRowOffset = heightSegments * pointsPerRow;
                    const t_p1 = topRowOffset + i * pointsPerSegment;
                    const t_p2 = topRowOffset + (i + 1) * pointsPerSegment;
                    if (rmin > 0) {
                        const t_p3 = topRowOffset + (i + 1) * pointsPerSegment + 1;
                        const t_p4 = topRowOffset + i * pointsPerSegment + 1;
                        indices.push(t_p1, t_p2, t_p3); indices.push(t_p1, t_p3, t_p4);
                    }
                }

                geometry = new THREE.BufferGeometry();
                // We have vertices as an array of Vector3, need to flatten for BufferAttribute
                geometry.setFromPoints(vertices);
                geometry.setIndex(indices);
                geometry.computeVertexNormals();
            }
            break;
        case 'arb8':
            {
                const dz = p.dz; // This is the half-length

                // The 8 vertices are defined by their XY coordinates on two Z planes
                const vertices = [
                    new THREE.Vector3(p.v1x, p.v1y, -dz),
                    new THREE.Vector3(p.v2x, p.v2y, -dz),
                    new THREE.Vector3(p.v3x, p.v3y, -dz),
                    new THREE.Vector3(p.v4x, p.v4y, -dz),
                    new THREE.Vector3(p.v5x, p.v5y,  dz),
                    new THREE.Vector3(p.v6x, p.v6y,  dz),
                    new THREE.Vector3(p.v7x, p.v7y,  dz),
                    new THREE.Vector3(p.v8x, p.v8y,  dz)
                ];
                
                geometry = new ConvexGeometry(vertices);
            }
            break;
        default:
            console.warn('[SceneManager] Unsupported primitive solid type for rendering:', solidData.type, solidData.name);
            // Return a placeholder sphere for unsupported types
            geometry = new THREE.SphereGeometry(10, 8, 8);
            break;
    }
    return geometry;
}

/**
 * Applies a GDML transform (position & rotation) to a Three.js mesh.
 * @param {THREE.Mesh} mesh - The mesh to transform.
 * @param {object} transformData - The transform data { position, rotation }.
 */
function _applyTransform(mesh, transformData) {
    if (!transformData) return;

    const position = transformData.position || { x: 0, y: 0, z: 0 };
    const rotation = transformData.rotation || { x: 0, y: 0, z: 0 }; // ZYX Euler

    const posVec = new THREE.Vector3(position.x, position.y, position.z);
    const euler = new THREE.Euler(rotation.x, rotation.y, rotation.z, 'ZYX');
    const quat = new THREE.Quaternion().setFromEuler(euler);

    const matrix = new THREE.Matrix4().compose(posVec, quat, new THREE.Vector3(1, 1, 1));
    mesh.applyMatrix4(matrix);
    mesh.updateMatrixWorld(true); // Ensure matrix is up-to-date
}


/**
 * Recursively gets or builds a geometry for a solid.
 * Caches results to avoid re-computation.
 * @param {string | object} solidRef - The name of the solid OR a dictionary defining the solid.
 * @param {object} solidsDict - The dictionary of all solid definitions.
 * @param {object} projectState - The full project state.
 * @param {Map<string, THREE.BufferGeometry>} geometryCache - The cache for built geometries.
 * @param {Evaluator} csgEvaluator - The CSG evaluator instance.
 * @returns {THREE.BufferGeometry | null}
 */
export function _getOrBuildGeometry(solidRef, solidsDict, projectState, geometryCache, csgEvaluator) {

    // --- Differentiate between a reference (string) and a definition (object) ---
    let solidData;
    let solidName;
    let isTemporary = false;

    if (typeof solidRef === 'string') {
        solidName = solidRef;
        solidData = solidsDict[solidName];
    } else if (typeof solidRef === 'object' && solidRef !== null) {
        solidName = solidRef.name; // Use the name from the object for caching
        solidData = solidRef;
        isTemporary = true; // Flag that this is a one-off object
    }

    if (!solidData) {
        console.error(`[SceneManager] Solid definition for '${solidName}' not found!`);
        return null;
    }

    // 1. Return from cache if already built
    if (geometryCache.has(solidName)) {
        return geometryCache.get(solidName);
    }

    let finalGeometry = null;

    // 2. Build geometry based on type
    // --- SCALED SOLID ---
    if (solidData.type === 'scaledSolid') {
        const p = solidData._evaluated_parameters;

        if (p && p.solid_ref && p.scale) {
            // Recursively get the geometry of the solid that is being scaled
            const baseGeometry = _getOrBuildGeometry(p.solid_ref, solidsDict, projectState, geometryCache, csgEvaluator);
            if (baseGeometry) {
                // Clone it so we don't modify the cached original
                finalGeometry = baseGeometry.clone();
                // Apply the scaling transformation
                finalGeometry.scale(p.scale.x, p.scale.y, p.scale.z);
                // The scaled geometry should have its bounding box re-computed for proper camera framing etc.
                finalGeometry.computeBoundingBox();
                finalGeometry.computeBoundingSphere();
            }
        }
        if (!finalGeometry) { // Handle error case
             console.error(`Could not build scaledSolid '${solidName}'`);
             return new THREE.BoxGeometry(10,10,10); // Return a placeholder
        }
    } else if (solidData.type === 'reflectedSolid') {
        const p = solidData._evaluated_parameters;
        if (p && p.solid_ref && p.transform) {
            // Recursively get the geometry of the solid that is being reflected/transformed
            const baseGeometry = _getOrBuildGeometry(p.solid_ref, solidsDict, projectState, geometryCache, csgEvaluator);
            if (baseGeometry) {
                finalGeometry = baseGeometry.clone();
                
                // Create a transformation matrix from the evaluated parameters
                const pos = p.transform._evaluated_position || {x:0, y:0, z:0};
                const rot = p.transform._evaluated_rotation || {x:0, y:0, z:0};
                const scl = p.transform._evaluated_scale || {x:1, y:1, z:1};

                const positionVec = new THREE.Vector3(pos.x, pos.y, pos.z);
                const euler = new THREE.Euler(rot.x, rot.y, rot.z, 'ZYX');
                const quaternion = new THREE.Quaternion().setFromEuler(euler);
                const scaleVec = new THREE.Vector3(scl.x, scl.y, scl.z);

                const matrix = new THREE.Matrix4().compose(positionVec, quaternion, scaleVec);

                // Apply the matrix to the geometry
                finalGeometry.applyMatrix4(matrix);
                finalGeometry.computeBoundingBox();
                finalGeometry.computeBoundingSphere();
            }
        }
        if (!finalGeometry) {
             console.error(`Could not build reflectedSolid '${solidName}'`);
             return new THREE.BoxGeometry(10,10,10);
        }
    } else if (solidData.type === 'boolean') {
        const recipe = solidData.raw_parameters.recipe;
        if (!recipe || recipe.length < 1 || !recipe[0].solid_ref) {
            console.error(`Boolean solid '${solidName}' has an invalid recipe.`);
            return null;
        }

        try {
            // Get the base solid's geometry
            const baseGeom = _getOrBuildGeometry(recipe[0].solid_ref, solidsDict, projectState, geometryCache, csgEvaluator);
            if (!baseGeom) {
                console.error(`Could not build base solid '${recipe[0].solid_ref}' for boolean '${solidName}'.`);
                return null;
            }

            let resultBrush = new Brush(baseGeom);
            const baseTransform = recipe[0].transform;
            if (baseTransform) {
                // Base transform needs to use evaluated values if they exist
                const pos = baseTransform._evaluated_position || {x:0, y:0, z:0};
                const rot = baseTransform._evaluated_rotation || {x:0, y:0, z:0};
                resultBrush.position.set(pos.x, pos.y, pos.z);
                resultBrush.quaternion.setFromEuler(new THREE.Euler(rot.x, rot.y, rot.z, 'ZYX'));
                resultBrush.updateMatrixWorld();
            }

            // Iteratively apply the subsequent operations
            for (let i = 1; i < recipe.length; i++) {
                const item = recipe[i];
                const nextSolidGeom = _getOrBuildGeometry(item.solid_ref, solidsDict, projectState, geometryCache, csgEvaluator);
                if (!nextSolidGeom) continue;
                
                const nextBrush = new Brush(nextSolidGeom);
                const transform = item.transform || {};
                
                // Use evaluated values for CSG operations
                const pos = transform._evaluated_position || {x:0, y:0, z:0};
                const rot = transform._evaluated_rotation || {x:0, y:0, z:0};
                nextBrush.position.set(pos.x, pos.y, pos.z);
                nextBrush.quaternion.setFromEuler(new THREE.Euler(rot.x, rot.y, rot.z, 'ZYX'));
                nextBrush.updateMatrixWorld();

                const op = (item.op === 'union') ? ADDITION : (item.op === 'intersection') ? INTERSECTION : SUBTRACTION;
                resultBrush = csgEvaluator.evaluate(resultBrush, nextBrush, op);
            }
            
            finalGeometry = resultBrush.geometry;
            
            // After a CSG operation, the geometry's bounding box/sphere is often incorrect.
            // Re-computing it ensures the camera and renderer behave as expected.
            finalGeometry.computeBoundingSphere();
            finalGeometry.computeBoundingBox();
        } catch(e) {
            // --- CATCH BLOCK ---
            console.error(`CSG evaluation failed for boolean solid '${solidName}'. The operation will be skipped and a placeholder shown. Error:`, e);
            
            // Create a box as a visual error indicator.
            finalGeometry = new THREE.BoxGeometry(100, 100, 100); 
            // We can also add a property to the geometry's userData to indicate it's an error placeholder
            finalGeometry.userData.isErrorPlaceholder = true; 
        }

    } else {
        finalGeometry = createPrimitiveGeometry(solidData, projectState, csgEvaluator);
    }
    
    // 3. Cache and return the final geometry
    //    Only cache permanent solids, not temporary slices from divisions.
    if (finalGeometry && !isTemporary) {
        geometryCache.set(solidName, finalGeometry);
    }
    return finalGeometry;
}


/**
 * The main rendering function, now refactored.
 * @param {Array} pvDescriptions - Flat list of physical volume placements from the backend.
 * @param {object} projectState - The full project state dictionary from the backend.
 */
export function renderObjects(pvDescriptions, projectState) {
    clearScene();
    if (!Array.isArray(pvDescriptions) || !projectState || !projectState.solids) {
        console.error("[SceneManager] Invalid data for rendering.", { pvDescriptions, projectState });
        return;
    }
    
    const geometryCache = new Map();
    const csgEvaluator = new Evaluator();
    for (const solidName in projectState.solids) {
        _getOrBuildGeometry(solidName, projectState.solids, projectState, geometryCache, csgEvaluator);
    }

    // NEW: Use a map to build the hierarchy
    const objectMap = new Map();

    // First pass: create all THREE.Group objects
    pvDescriptions.forEach(pvData => {
        const group = new THREE.Group();
        group.userData = pvData;
        group.name = pvData.name || `group_${pvData.id}`;

        // Store it in the map by its unique PV ID
        objectMap.set(pvData.id, group);

        // Only create meshes for actual, renderable volumes
        const isRenderable = !pvData.is_world_volume_placement 
                             && !pvData.is_assembly_placement 
                             && !pvData.is_procedural_container;

        if (isRenderable) {
            const solidRef = pvData.solid_ref_for_threejs;
            const geometry = _getOrBuildGeometry(solidRef, projectState.solids, projectState, geometryCache, csgEvaluator);
            if (geometry) {
                const vis = pvData.vis_attributes || {color: {r:0.8,g:0.8,b:0.8,a:1.0}};
                const color = vis.color;
                const meshMaterial = new THREE.MeshPhongMaterial({
                    color: new THREE.Color(color.r, color.g, color.b),
                    transparent: color.a < 1.0,
                    opacity: color.a,
                    side: THREE.DoubleSide,
                    shininess: 30,
                    polygonOffset: true,
                    polygonOffsetFactor: 1,
                    polygonOffsetUnits: 1
                });
                const solidMesh = new THREE.Mesh(geometry, meshMaterial);
                const edges = new EdgesGeometry(geometry, 1);
                const lineMaterial = new LineBasicMaterial({ color: 0x000000, linewidth: 2 });
                const wireframe = new LineSegments(edges, lineMaterial);
                group.add(solidMesh);
                group.add(wireframe);
            }
        } 
        // else {
        //     // Make non-renderable containers invisible.
        //     group.visible = false;
        // }
    });

    // Second pass: parent the objects and apply LOCAL transforms
    pvDescriptions.forEach(pvData => {
        const obj = objectMap.get(pvData.id);
        if (!obj) return;

        // Apply LOCAL transforms, not world transforms
        const position = pvData.position || { x: 0, y: 0, z: 0 };
        const rotation = pvData.rotation || { x: 0, y: 0, z: 0 };
        const scale = pvData.scale || { x: 1, y: 1, z: 1 };
        
        obj.position.set(position.x, position.y, position.z);
        const euler = new THREE.Euler(rotation.x, rotation.y, rotation.z, 'ZYX');
        obj.quaternion.setFromEuler(euler);
        obj.scale.set(scale.x, scale.y, scale.z);
        
        // Find the parent and attach
        const parentObj = objectMap.get(pvData.parent_id);
        if (parentObj) {
            parentObj.add(obj);
        } else {
            // If no parent is found in the map, it's a top-level object (child of the world)
            geometryGroup.add(obj);
        }
    });

    // IMPORTANT: Update world matrices for the entire hierarchy
    geometryGroup.updateMatrixWorld(true);

    console.log("[SceneManager] Rendered objects with nested hierarchy. Total top-level:", geometryGroup.children.length);
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

    // --- Clear the visibility state when the scene is fully cleared ---
    //hiddenPvIds.clear();

    console.log("[SceneManager] Scene cleared.");
}

export function isPvHidden(pvId) {
    return hiddenPvIds.has(pvId);
}

// --- Selection and Highlighting in 3D ---
const _highlightMaterial = new THREE.MeshLambertMaterial({
    color: 0xffaa00, emissive: 0x333300, transparent: true,
    opacity: 0.95, depthTest: false
});
let _selectedThreeObjects = []; // Internal list of THREE.Mesh objects
let _originalMaterialsMap = new Map(); // UUID -> { material, wasWireframe }

export function updateSelectionState(groupsToSelect = []) {
    
    // 1. Unhighlight all previously selected objects
    _selectedThreeObjects.forEach(group => {
        // This is a robust way to find all meshes, wherever they are nested
        group.traverse(child => {
            if (child.isMesh && _originalMaterialsMap.has(child.uuid)) {
                child.material = _originalMaterialsMap.get(child.uuid).material;
                _originalMaterialsMap.delete(child.uuid);
            }
        });
    });

    // 2. The groups passed in ARE the selected objects. No need to clear and re-populate.
    _selectedThreeObjects = groupsToSelect;

    if (!_selectedThreeObjects || _selectedThreeObjects.length === 0) {
        return; // Nothing to select
    }

    // 3. Highlight all renderable meshes within the selected groups and their descendants.
    _selectedThreeObjects.forEach(group => {
        group.traverse(child => {
            if (child.isMesh) { // Find every mesh inside the selected group
                if (!_originalMaterialsMap.has(child.uuid)) {
                    _originalMaterialsMap.set(child.uuid, { material: child.material });
                }
                child.material = _highlightMaterial;
            }
        });
    });
}

// A simple utility to get all meshes belonging to an owner.
export function getMeshesForOwner(ownerPvId) {
    const meshes = [];
    geometryGroup.traverse(child => {
        if (child.isGroup && child.userData && child.userData.owner_pv_id === ownerPvId) {
            meshes.push(child);
        }
    });
    return meshes;
}

function highlightObject(obj) {
    if (obj.material !== _highlightMaterial) {
        _originalMaterialsMap.set(obj.uuid, { material: obj.material.clone() });
    }
    obj.material = _highlightMaterial;
}

function unhighlightObject(obj) {
    if (_originalMaterialsMap.has(obj.uuid)) {
        obj.material = _originalMaterialsMap.get(obj.uuid).material;
        _originalMaterialsMap.delete(obj.uuid);
    }
}

function unhighlightAll() {
    _selectedThreeObjects.forEach(obj => unhighlightObject(obj));
}

export function unselectAllInScene() {
    updateSelectionState([]);
}

// --- Transform Controls Management ---
export function attachTransformControls(groups) { 
    transformControls.detach();
    
    // The check must be on the function's parameter `objects`.
    if (!transformControls.enabled || !groups || groups.length === 0) {
        return;
    }

    if (groups.length === 1) {
        // Simple case: attach directly to the single group
        transformControls.attach(groups[0]);
    } else {
        // Multi-object case (from a replica or user multi-select)
        const box = new THREE.Box3();
        groups.forEach(group => {
            // It's safer to check if the mesh is valid before expanding the box
            if (group) {
                box.expandByObject(group);
            }
        });
        const center = new THREE.Vector3();
        box.getCenter(center);
        
        // Position our helper object at this center
        gizmoAttachmentHelper.position.copy(center);
        
        // For rotation to work correctly, the helper's initial orientation
        // must match the orientation of the object(s) it controls.
        // For a group, we can assume they all have the same orientation,
        // so we just take it from the first object in the list.
        if (groups[0]) {
            gizmoAttachmentHelper.quaternion.copy(groups[0].quaternion);
        } else {
            gizmoAttachmentHelper.rotation.set(0,0,0);
        }
        
        gizmoAttachmentHelper.scale.set(1,1,1);

        // The first mesh's owner_pv_id will be the same for all meshes in the group.
        gizmoAttachmentHelper.userData.controlledObjectId = groups[0].userData.owner_pv_id || groups[0].userData.id;
        
        transformControls.attach(gizmoAttachmentHelper);
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

/**
 * Toggles the visibility of the main XYZ axes helper in the scene.
 */
export function toggleAxesVisibility() {
    isAxesVisible = !isAxesVisible;
    if (axesHelper) {
        axesHelper.visible = isAxesVisible;
    }
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

    // --- Resize check ---
    // This ensures the renderer and camera are always perfectly synced to the DOM element size.
    const canvas = renderer.domElement;
    const width = viewerContainer.clientWidth;
    const height = viewerContainer.clientHeight;
    if (canvas.width !== width || canvas.height !== height) {
        // This is a simplified version of onWindowResize
        renderer.setSize(width, height, false); // `false` prevents it from setting the canvas style, which we handle with CSS
        camera.aspect = width / height;
        camera.updateProjectionMatrix();
    }
    // ---  ---

    const delta = clock.getDelta();

    if (orbitControls.enabled) orbitControls.update();
    if (flyControls.enabled) flyControls.update(delta);
    // TransformControls updates internally if attached

    // 1. Clear everything from the last frame.
    renderer.clear();

    // 2. Render the main scene into the full viewport.
    renderer.setViewport(0, 0, viewerContainer.clientWidth, viewerContainer.clientHeight);
    renderer.render(scene, camera);

    // --- Render the axes gizmo on top ---
    if (isAxesVisible) {
        // We must clear the DEPTH buffer only, so the gizmo appears on top.
        renderer.clearDepth();

        // Set a small viewport in the bottom-left corner.
        const viewportSize = 120;
        renderer.setViewport(10, 10, viewportSize, viewportSize);

        // --- FIX for Axes Orientation ---
        // 1. Get the direction vector of the main camera.
        const cameraDirection = new THREE.Vector3();
        camera.getWorldDirection(cameraDirection);

        // 2. Position the axes camera along that direction vector.
        // The distance controls the size of the gizmo.
        cameraAxes.position.copy(cameraDirection).multiplyScalar(-200); // Move it back from the origin

        // 3. Point the axes camera back at the center of the axes scene.
        cameraAxes.lookAt(sceneAxes.position); // Look at (0,0,0)

        // Update material resolution
        sceneAxes.traverse(child => {
            if (child.isLine2) {
                child.material.resolution.set(viewerContainer.clientWidth, viewerContainer.clientHeight);
            }
        });

        // Render the axes scene. Because autoClear is false, this will
        // draw ON TOP of the main scene render.
        renderer.render(sceneAxes, cameraAxes);
    }
}

function onWindowResize() {
    if (!renderer || !viewerContainer) return;
    renderer.setSize(viewerContainer.clientWidth, viewerContainer.clientHeight);
    camera.aspect = viewerContainer.clientWidth / viewerContainer.clientHeight;
    camera.updateProjectionMatrix();
}