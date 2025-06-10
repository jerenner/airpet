// static/sceneManager.js
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { TransformControls } from 'three/addons/controls/TransformControls.js';
import { FlyControls } from 'three/addons/controls/FlyControls.js';
import { Brush, Evaluator, ADDITION, SUBTRACTION, INTERSECTION } from 'three-bvh-csg';

import { getCurrentMode as getInteractionManagerMode } from './interactionManager.js';

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
let onObjectTransformLiveCallback = null; // callback for live updates

// --- Initialization ---
export function initScene(callbacks) {
    onObjectSelectedCallback = callbacks.onObjectSelectedIn3D;
    onObjectTransformEndCallback = callbacks.onObjectTransformEnd;
    onObjectTransformLiveCallback = callbacks.onObjectTransformLive;
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
        // This event means the attached object's transform has changed in Three.js
        if (transformControls.object && onObjectTransformLiveCallback) { // && _selectedThreeObjects.length === 1 && _selectedThreeObjects[0] === transformControls.object) {
            // Call the new lightweight UI update function directly
            console.log("[SceneManager] objectChange for:", transformControls.object.name);
            onObjectTransformLiveCallback(transformControls.object);
        }
    });
    transformControls.addEventListener('mouseUp', () => { // This signifies the end of a user interaction
        if (transformControls.object && onObjectTransformEndCallback) {
            console.log("[SceneManager] Transform mouseUp, calling onObjectTransformEndCallback for:", transformControls.object.name);
            onObjectTransformEndCallback(transformControls.object); // Send final state to main.js
        }
        // Re-enable orbit controls if no longer dragging with transform gizmo (handled by dragging-changed too)
        // if (!transformControls.dragging) {
        //    if (orbitControls) orbitControls.enabled = true;
        // }
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
    const currentAppMode = getInteractionManagerMode(); // Get current mode

    // If transform controls are active and have an object, let them handle primary interaction.
    // The user might be trying to click the gizmo.
    if (transformControls && transformControls.object && transformControls.enabled) {
        // If the click is NOT on the transform gizmo itself (or its attached object),
        // then we might want to deselect or select a new object.
        // This part is tricky because TransformControls consumes events.
        // For now, if TC is active and attached, we assume it manages its interaction.
        // A click outside the gizmo could be interpreted as a deselection intent.
        
        // Let's simplify: If in a transform mode, primary interaction is via gizmo.
        // Selection of a *new* object should probably happen in 'observe' mode first,
        // or by a specific UI action (e.g. "Select Object" button then click).
        // For now, if we are in translate/rotate/scale, and TC is attached,
        // we don't do raycasting for new selections here. It's done when TC is detached.
        if (currentAppMode !== 'observe') {
            // Check if click was outside the current TC object and its gizmo
            // This logic needs to be robust, possibly using raycaster.intersectObject(transformControls)
            // For now, let's assume if in transform mode, selection is "locked" to the TC object
            // or should be handled by detaching TC first.
            return; 
        }
    }
    
    // If in 'observe' mode, or if TransformControls is not actively manipulating something.
    if (currentAppMode === 'observe' || (transformControls && !transformControls.object) ) {
        const rect = renderer.domElement.getBoundingClientRect();
        mouse.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
        mouse.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;

        raycaster.setFromCamera(mouse, camera);
        const intersects = raycaster.intersectObjects(geometryGroup.children, true);

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
/**
 * Creates a Three.js geometry for a primitive solid definition.
 * @param {object} solidData - The solid definition from the project state.
 * @param {object} projectState - The full project state for lookups.
 * @param {Evaluator} csgEvaluator - The CSG evaluator instance.
 * @returns {THREE.BufferGeometry | null}
 */
export function createPrimitiveGeometry(solidData, projectState, csgEvaluator) {
    let geometry;
    const p = solidData.parameters;

    // Temporary handling of null project state from solid editor
    const defines = (projectState && projectState.defines) ? projectState.defines : {};

    switch (solidData.type) {
        case 'box':
            geometry = new THREE.BoxGeometry(p.x, p.y, p.z);
            break;
        case 'tube':
            if (!p.rmin || p.rmin <= 1e-9) { // Solid Cylinder
                geometry = new THREE.CylinderGeometry(p.rmax, p.rmax, p.dz * 2, 32, 1, false, p.startphi, p.deltaphi);
                geometry.rotateX(Math.PI / 2);
            } else { // Hollow Tube
                const shape = new THREE.Shape();
                shape.moveTo(p.rmax * Math.cos(p.startphi), p.rmax * Math.sin(p.startphi));
                shape.absarc(0, 0, p.rmax, p.startphi, p.startphi + p.deltaphi, false);
                shape.lineTo(p.rmin * Math.cos(p.startphi + p.deltaphi), p.rmin * Math.sin(p.startphi + p.deltaphi));
                shape.absarc(0, 0, p.rmin, p.startphi + p.deltaphi, p.startphi, true);
                shape.closePath();
                const extrudeSettings = { steps: 1, depth: p.dz * 2, bevelEnabled: false };
                geometry = new THREE.ExtrudeGeometry(shape, extrudeSettings);
                geometry.translate(0, 0, -p.dz);
            }
            break;
        case 'cone':
             geometry = new THREE.CylinderGeometry(p.rmax2, p.rmax1, p.dz*2, 32, 1, false, p.startphi, p.deltaphi);
             geometry.rotateX(Math.PI / 2); // Also align to Z-axis
            break;
        case 'sphere':
            geometry = new THREE.SphereGeometry(p.rmax, 32, 16, p.startphi, p.deltaphi, p.starttheta, p.deltatheta);
            break;
        case 'orb':
            geometry = new THREE.SphereGeometry(p.r, 32, 16);
            break;
        case 'torus':
            geometry = new THREE.TorusGeometry(p.rtor, p.rmax, 16, 100, p.deltaphi);
            if(p.startphi !== 0) geometry.rotateZ(p.startphi);
            break;
        case 'polycone':
        case 'genericPolycone':
        case 'polyhedra':
        case 'genericPolyhedra':
            {
                const points = [];
                const isPolyhedra = solidData.type.includes('polyhedra');
                const numSides = isPolyhedra ? (p.numsides || 32) : 32;

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
                const twoDimVertices = p.twoDimVertices;
                const sections = p.sections;

                if (!twoDimVertices || twoDimVertices.length < 3 || !sections || sections.length < 2) {
                    console.error(`[SceneManager] xtru solid '${solidData.name}' has invalid parameters.`);
                    return new THREE.SphereGeometry(10, 8, 8); // Placeholder
                }
                
                geometry = new THREE.BufferGeometry();
                const vertices = [];
                const indices = [];

                // Generate the vertices for each section plane
                const sectionVertices = sections.map(sec => {
                    return twoDimVertices.map(v => {
                        return new THREE.Vector3(
                            v.x * sec.scalingFactor + sec.xOffset,
                            v.y * sec.scalingFactor + sec.yOffset,
                            sec.zPosition
                        );
                    });
                });

                // Create the side faces by connecting the vertices between sections
                for (let i = 0; i < sections.length - 1; i++) {
                    const verts1 = sectionVertices[i];
                    const verts2 = sectionVertices[i + 1];
                    const baseIndex1 = i * twoDimVertices.length;
                    const baseIndex2 = (i + 1) * twoDimVertices.length;

                    for (let j = 0; j < twoDimVertices.length; j++) {
                        const next_j = (j + 1) % twoDimVertices.length;

                        const p1 = baseIndex1 + j;
                        const p2 = baseIndex1 + next_j;
                        const p3 = baseIndex2 + next_j;
                        const p4 = baseIndex2 + j;
                        
                        // Quad (p1, p2, p3, p4) -> two triangles (p1, p2, p3) and (p1, p3, p4)
                        indices.push(p1, p2, p3);
                        indices.push(p1, p3, p4);
                    }
                }

                // Add all the calculated vertices to one flat array
                sectionVertices.forEach(verts => {
                    verts.forEach(v => vertices.push(v.x, v.y, v.z));
                });
                
                // --- Capping the Ends ---
                // We need to triangulate the 2D start and end shapes
                const capPoints = twoDimVertices.map(v => new THREE.Vector2(v.x, v.y));
                
                // --- FIX IS HERE: Use .holes instead of .getHoles() ---
                const capTriangles = THREE.ShapeUtils.triangulateShape(capPoints, []); // GDML xtru does not define holes, so pass an empty array.

                // Add Start Cap
                const startSection = sections[0];
                const startMatrix = new THREE.Matrix4().compose(
                    new THREE.Vector3(startSection.xOffset, startSection.yOffset, startSection.zPosition),
                    new THREE.Quaternion(), // No rotation for caps
                    new THREE.Vector3(startSection.scalingFactor, startSection.scalingFactor, 1)
                );
                
                capTriangles.forEach(tri => {
                    const i1 = tri[0]; const i2 = tri[1]; const i3 = tri[2];
                    const v1 = new THREE.Vector3(twoDimVertices[i1].x, twoDimVertices[i1].y, 0).applyMatrix4(startMatrix);
                    const v2 = new THREE.Vector3(twoDimVertices[i2].x, twoDimVertices[i2].y, 0).applyMatrix4(startMatrix);
                    const v3 = new THREE.Vector3(twoDimVertices[i3].x, twoDimVertices[i3].y, 0).applyMatrix4(startMatrix);
                    
                    const newIndex = vertices.length / 3;
                    vertices.push(v1.x, v1.y, v1.z, v2.x, v2.y, v2.z, v3.x, v3.y, v3.z);
                    indices.push(newIndex + 2, newIndex + 1, newIndex); // Invert winding for start cap
                });

                // Add End Cap
                const endSection = sections[sections.length - 1];
                const endMatrix = new THREE.Matrix4().compose(
                    new THREE.Vector3(endSection.xOffset, endSection.yOffset, endSection.zPosition),
                    new THREE.Quaternion(),
                    new THREE.Vector3(endSection.scalingFactor, endSection.scalingFactor, 1)
                );

                capTriangles.forEach(tri => {
                    const i1 = tri[0]; const i2 = tri[1]; const i3 = tri[2];
                    const v1 = new THREE.Vector3(twoDimVertices[i1].x, twoDimVertices[i1].y, 0).applyMatrix4(endMatrix);
                    const v2 = new THREE.Vector3(twoDimVertices[i2].x, twoDimVertices[i2].y, 0).applyMatrix4(endMatrix);
                    const v3 = new THREE.Vector3(twoDimVertices[i3].x, twoDimVertices[i3].y, 0).applyMatrix4(endMatrix);
                    
                    const newIndex = vertices.length / 3;
                    vertices.push(v1.x, v1.y, v1.z, v2.x, v2.y, v2.z, v3.x, v3.y, v3.z);
                    indices.push(newIndex, newIndex + 1, newIndex + 2); // Normal winding for end cap
                });

                geometry.setAttribute('position', new THREE.Float32BufferAttribute(new Float32Array(vertices), 3));
                geometry.setIndex(indices);
                geometry.computeVertexNormals();
            }
            break;
        case 'tet': // Tetrahedron
            {
                const defines = projectState.defines;
                const v1_ref = defines[p.vertex1_ref];
                const v2_ref = defines[p.vertex2_ref];
                const v3_ref = defines[p.vertex3_ref];
                const v4_ref = defines[p.vertex4_ref];
                
                if (!v1_ref || !v2_ref || !v3_ref || !v4_ref) {
                    console.error(`[SceneManager] Could not find all vertex definitions for tet '${solidData.name}'`);
                    return new THREE.SphereGeometry(10, 8, 8); // Placeholder
                }

                const vertices = new Float32Array([
                    v1_ref.value.x, v1_ref.value.y, v1_ref.value.z,
                    v2_ref.value.x, v2_ref.value.y, v2_ref.value.z,
                    v3_ref.value.x, v3_ref.value.y, v3_ref.value.z,
                    v4_ref.value.x, v4_ref.value.y, v4_ref.value.z,
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
                // A cutTube is a tube intersected with two half-spaces.
                // 1. Create the basic tube geometry.
                let tubeGeom;
                if (!p.rmin || p.rmin <= 1e-9) { // Solid Cylinder
                    tubeGeom = new THREE.CylinderGeometry(p.rmax, p.rmax, p.dz * 2, 50, 1, false, p.startphi, p.deltaphi);
                    tubeGeom.rotateX(Math.PI / 2);
                } else { // Hollow Tube
                    const shape = new THREE.Shape();
                    shape.moveTo(p.rmax * Math.cos(p.startphi), p.rmax * Math.sin(p.startphi));
                    shape.absarc(0, 0, p.rmax, p.startphi, p.startphi + p.deltaphi, false);
                    shape.lineTo(p.rmin * Math.cos(p.startphi + p.deltaphi), p.rmin * Math.sin(p.startphi + p.deltaphi));
                    shape.absarc(0, 0, p.rmin, p.startphi + p.deltaphi, p.startphi, true);
                    shape.closePath();
                    const extrudeSettings = { steps: 1, depth: p.dz * 2, bevelEnabled: false };
                    tubeGeom = new THREE.ExtrudeGeometry(shape, extrudeSettings);
                    tubeGeom.translate(0, 0, -p.dz);
                }
                
                let resultBrush = new Brush(tubeGeom);

                // 2. Create the two cutting planes (as very large boxes representing half-spaces)
                const planeSize = p.rmax * 4; // A size guaranteed to be larger than the tube
                
                // Low normal cut
                const lowNormal = new THREE.Vector3(p.lowNormal.x, p.lowNormal.y, p.lowNormal.z).normalize();
                if (lowNormal.lengthSq() > 0.5) { // A zero vector means no cut
                    const planeGeomLow = new THREE.BoxGeometry(planeSize, planeSize, planeSize);
                    const planeBrushLow = new Brush(planeGeomLow);
                    
                    // Position the box so its face is at the origin
                    planeBrushLow.position.copy(lowNormal).multiplyScalar(planeSize / 2);
                    // Rotate the box so its face's normal aligns with the desired cutting normal
                    planeBrushLow.quaternion.setFromUnitVectors(new THREE.Vector3(0, 0, 1), lowNormal);
                    planeBrushLow.updateMatrixWorld();
                    
                    // Intersect the tube with the half-space
                    resultBrush = csgEvaluator.evaluate(resultBrush, planeBrushLow, INTERSECTION);
                }
                
                // High normal cut
                const highNormal = new THREE.Vector3(p.highNormal.x, p.highNormal.y, p.highNormal.z).normalize();
                 if (highNormal.lengthSq() > 0.5) {
                    const planeGeomHigh = new THREE.BoxGeometry(planeSize, planeSize, planeSize);
                    const planeBrushHigh = new Brush(planeGeomHigh);
                    planeBrushHigh.position.copy(highNormal).multiplyScalar(planeSize / 2);
                    planeBrushHigh.quaternion.setFromUnitVectors(new THREE.Vector3(0, 0, 1), highNormal);
                    planeBrushHigh.updateMatrixWorld();
                    
                    resultBrush = csgEvaluator.evaluate(resultBrush, planeBrushHigh, INTERSECTION);
                }

                geometry = resultBrush.geometry;
            }
            break;
        case 'para': // Parallelepiped
            {
                // A G4Para is a sheared box. We create a box and apply a shear matrix.
                geometry = new THREE.BoxGeometry(p.dx * 2, p.dy * 2, p.dz * 2);
                const alpha = p.alpha;
                const theta = p.theta;
                const phi = p.phi;

                const st = Math.sin(theta);
                const ct = Math.cos(theta);
                const sp = Math.sin(phi);
                const cp = Math.cos(phi);
                const sa = Math.sin(alpha);
                const ca = Math.cos(alpha);

                const matrix = new THREE.Matrix4();
                matrix.set(
                    1,  st*cp,      st*sp,      0,
                    0,  ct,         -st,        0,
                    0,  ca*st*sp,   ca*ct,      0,
                    0,  0,          0,          1
                );
                // The above matrix is based on G4Para implementation, but GDML shearing
                // is often simpler. Let's use a simpler shear matrix for now.
                // It can be adjusted if precise G4Para shearing is needed.
                const shearMatrix = new THREE.Matrix4().makeShear(
                    Math.tan(alpha) * Math.cos(theta) * Math.cos(phi), // xy
                    Math.tan(alpha) * Math.cos(theta) * Math.sin(phi), // xz
                    0, // yx
                    0, // yz
                    0, // zx
                    0  // zy
                );
                // Note: THREE.Matrix4.makeShear is not standard.
                // We will manually create the shear matrix.
                const manualShearMatrix = new THREE.Matrix4().set(
                    1, Math.tan(p.alpha), 0, 0,
                    0, 1, 0, 0,
                    0, 0, 1, 0,
                    0, 0, 0, 1
                );
                // A full G4Para matrix is more complex, involving theta and phi as well.
                // For a basic visual representation, a simple shear might suffice initially.
                // Let's create from vertices for accuracy.
                const dx = p.dx; const dy = p.dy; const dz = p.dz;
                const t_alpha = Math.tan(p.alpha);
                const t_theta_cp = Math.tan(p.theta) * Math.cos(p.phi);
                const t_theta_sp = Math.tan(p.theta) * Math.sin(p.phi);

                const vertices = [
                    -dx - dy*t_alpha - dz*t_theta_cp, -dy - dz*t_theta_sp, -dz, // 0
                     dx - dy*t_alpha - dz*t_theta_cp, -dy - dz*t_theta_sp, -dz, // 1
                     dx + dy*t_alpha - dz*t_theta_cp,  dy - dz*t_theta_sp, -dz, // 2
                    -dx + dy*t_alpha - dz*t_theta_cp,  dy - dz*t_theta_sp, -dz, // 3
                    -dx - dy*t_alpha + dz*t_theta_cp, -dy + dz*t_theta_sp,  dz, // 4
                     dx - dy*t_alpha + dz*t_theta_cp, -dy + dz*t_theta_sp,  dz, // 5
                     dx + dy*t_alpha + dz*t_theta_cp,  dy + dz*t_theta_sp,  dz, // 6
                    -dx + dy*t_alpha + dz*t_theta_cp,  dy + dz*t_theta_sp,  dz  // 7
                ];
                const indices = [
                    0, 1, 2,  0, 2, 3, // bottom
                    4, 6, 5,  4, 7, 6, // top
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
        case 'eltube': // Elliptical Tube
            {
                // Approximate with a scaled cylinder.
                const radius = (p.dx + p.dy) / 2; // Average radius
                geometry = new THREE.CylinderGeometry(radius, radius, p.dz * 2, 32);
                geometry.scale(p.dx / radius, p.dy / radius, 1);
                geometry.rotateX(Math.PI / 2);
            }
            break;
        case 'trap': // General Trapezoid
        case 'arb8': // Generic Trap (arb8 and trap can be treated similarly)
            {
                const vertices = [];
                if (solidData.type === 'trap') {
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
                } else { // arb8
                    const dz = p.dz;
                    p.vertices.forEach((v, i) => {
                        vertices.push(v.x, v.y, (i < 4) ? -dz : dz);
                    });
                }
                
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
        case 'twistedtrd':
            {
                // Both twistedbox and twistedtrd can be handled by the same logic.
                // A twistedbox is just a twistedtrd with dx1=dx2 and dy1=dy2.
                const dz = p.dz;
                const phiTwist = p.phi_twist;
                
                // Define the 2D vertices for the bottom and top faces
                const dx1 = p.dx1 !== undefined ? p.dx1 : p.dx; // Use 'dx' for twistedbox
                const dy1 = p.dy1 !== undefined ? p.dy1 : p.dy;
                const dx2 = p.dx2 !== undefined ? p.dx2 : p.dx;
                const dy2 = p.dy2 !== undefined ? p.dy2 : p.dy;

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
        case 'twistedtubs':
            {
                // This requires parametric surface generation.
                const rmin = p.rmin;
                const rmax = p.rmax;
                const dz = p.dz;
                const dphi = p.dphi;
                const twist = p.twistedangle;
                const radialSegments = 32;
                const heightSegments = 10;
                
                const vertices = [];
                const indices = [];

                // Generate vertices for the inner and outer surfaces
                for (let j = 0; j <= heightSegments; j++) {
                    const v = j / heightSegments; // v is fractional height, from 0 to 1
                    const z = -dz + v * (2 * dz);
                    const currentTwist = twist * (v - 0.5); // twist is centered around z=0

                    for (let i = 0; i <= radialSegments; i++) {
                        const u = i / radialSegments; // u is fractional angle
                        const phi = u * dphi;
                        
                        // Outer surface vertex
                        let x_out = rmax * Math.cos(phi);
                        let y_out = rmax * Math.sin(phi);
                        let vec_out = new THREE.Vector3(x_out, y_out, 0).applyAxisAngle(new THREE.Vector3(0,0,1), currentTwist);
                        vertices.push(vec_out.x, vec_out.y, z);
                        
                        // Inner surface vertex
                        if (rmin > 0) {
                            let x_in = rmin * Math.cos(phi);
                            let y_in = rmin * Math.sin(phi);
                            let vec_in = new THREE.Vector3(x_in, y_in, 0).applyAxisAngle(new THREE.Vector3(0,0,1), currentTwist);
                            vertices.push(vec_in.x, vec_in.y, z);
                        }
                    }
                }
                
                const pointsPerRow = rmin > 0 ? (radialSegments + 1) * 2 : (radialSegments + 1);
                
                // Generate indices for the faces
                for (let j = 0; j < heightSegments; j++) {
                    for (let i = 0; i < radialSegments; i++) {
                        const row1 = j * pointsPerRow;
                        const row2 = (j + 1) * pointsPerRow;
                        
                        // Outer surface
                        const p1_out = row1 + i * (rmin > 0 ? 2 : 1);
                        const p2_out = row1 + (i + 1) * (rmin > 0 ? 2 : 1);
                        const p3_out = row2 + (i + 1) * (rmin > 0 ? 2 : 1);
                        const p4_out = row2 + i * (rmin > 0 ? 2 : 1);
                        indices.push(p1_out, p2_out, p3_out,  p1_out, p3_out, p4_out);

                        // Inner surface
                        if (rmin > 0) {
                            const p1_in = row1 + i * 2 + 1;
                            const p2_in = row1 + (i + 1) * 2 + 1;
                            const p3_in = row2 + (i + 1) * 2 + 1;
                            const p4_in = row2 + i * 2 + 1;
                            indices.push(p1_in, p3_in, p2_in,  p1_in, p4_in, p3_in); // Inverted for inner surface
                        }
                    }
                }

                // Note: Capping for twisted tubs is complex and omitted for this implementation.
                // It would require creating a non-planar polygon and triangulating it.

                geometry = new THREE.BufferGeometry();
                geometry.setAttribute('position', new THREE.Float32BufferAttribute(vertices, 3));
                geometry.setIndex(indices);
                geometry.computeVertexNormals();
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
 * @param {string} solidName - The name of the solid to get/build.
 * @param {object} solidsDict - The dictionary of all solid definitions.
 * @param {object} projectState - The full project state.
 * @param {Map<string, THREE.BufferGeometry>} geometryCache - The cache for built geometries.
 * @param {Evaluator} csgEvaluator - The CSG evaluator instance.
 * @returns {THREE.BufferGeometry | null}
 */
function _getOrBuildGeometry(solidName, solidsDict, projectState, geometryCache, csgEvaluator) {
    // 1. Return from cache if already built
    if (geometryCache.has(solidName)) {
        return geometryCache.get(solidName);
    }

    const solidData = solidsDict[solidName];
    if (!solidData) {
        console.error(`[SceneManager] Solid definition for '${solidName}' not found!`);
        return null;
    }

    let finalGeometry = null;

    // 2. Build geometry based on type
    const booleanTypes = ['union', 'subtraction', 'intersection'];
    if (booleanTypes.includes(solidData.type)) {
        // --- BOOLEAN LOGIC ---
        const params = solidData.parameters;
        
        // Recursively get constituent geometries
        const geomA = _getOrBuildGeometry(params.first_ref, solidsDict, projectState, geometryCache, csgEvaluator);
        const geomB = _getOrBuildGeometry(params.second_ref, solidsDict, projectState, geometryCache, csgEvaluator);

        if (!geomA || !geomB) {
            console.error(`Could not build boolean solid '${solidName}' due to missing components.`);
            return null;
        }

        // The CSG library works on "Brushes" (which are basically Meshes)
        const brushA = new Brush(geomA);
        const brushB = new Brush(geomB);
        
        // Apply transforms *before* the boolean operation
        _applyTransform(brushA, params.transform_first);
        _applyTransform(brushB, params.transform_second);

        // Perform the CSG operation
        let csgResult;
        if (solidData.type === 'union') {
            csgResult = csgEvaluator.evaluate(brushA, brushB, ADDITION);
        } else if (solidData.type === 'subtraction') {
            csgResult = csgEvaluator.evaluate(brushA, brushB, SUBTRACTION);
        } else { // intersection
            csgResult = csgEvaluator.evaluate(brushA, brushB, INTERSECTION);
        }
        finalGeometry = csgResult.geometry;

    } else {
        // --- PRIMITIVE LOGIC ---
        finalGeometry = createPrimitiveGeometry(solidData, projectState, csgEvaluator);
    }
    
    // 3. Cache and return the final geometry
    if (finalGeometry) {
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

    // --- Stage 1: Build and Cache All Geometries ---
    const geometryCache = new Map();
    const csgEvaluator = new Evaluator(); // CSG tool

    for (const solidName in projectState.solids) {
        _getOrBuildGeometry(solidName, projectState.solids, projectState, geometryCache, csgEvaluator);
    }
    console.log("[SceneManager] Geometry cache built. Total items:", geometryCache.size);

    // --- Stage 2: Place Geometries in the Scene ---
    pvDescriptions.forEach(pvData => {
        const solidName = pvData.solid_ref_for_threejs; // Backend should provide this direct ref
        const cachedGeom = geometryCache.get(solidName);

        if (!cachedGeom) {
            console.warn(`[SceneManager] No cached geometry found for solid '${solidName}'. Skipping placement of '${pvData.name}'.`);
            return;
        }

        const geometry = cachedGeom.clone(); // Use a clone for each instance

        const material = new THREE.MeshLambertMaterial({
            color: new THREE.Color(Math.random() * 0xffffff),
            transparent: true,
            opacity: 0.75,
            side: THREE.DoubleSide,
            wireframe: isWireframeMode
        });

        const mesh = new THREE.Mesh(geometry, material);
        mesh.userData = pvData; // Store the full placement data
        mesh.name = pvData.name || `mesh_${pvData.id}`;

        // Apply final placement transform
        if (pvData.position) mesh.position.set(pvData.position.x, pvData.position.y, pvData.position.z);
        if (pvData.rotation) { // ZYX Euler angles in radians
            const euler = new THREE.Euler(pvData.rotation.x, pvData.rotation.y, pvData.rotation.z, 'ZYX');
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
        //orbitControls.target.copy(targetPosition);
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