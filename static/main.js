// static/main.js
import * as THREE from 'three';

import * as UIManager from './uiManager.js';
import * as SceneManager from './sceneManager.js';
import * as InteractionManager from './interactionManager.js';
import * as APIService from './apiService.js';

// --- Global Application State (Keep this minimal) ---
const AppState = {
    currentProjectState: null,    // Full state dict from backend (defines, materials, solids, LVs, world_ref)
    selectedHierarchyItem: null,  // { type, id, name, data (raw from projectState) }
    selectedThreeObjects: [],      // Managed by SceneManager, but AppState might need to know for coordination
    selectedPVContext: {
        pvId: null,
        positionDefineName: null,
        rotationDefineName: null,
    }
};

// --- Initialization ---
document.addEventListener('DOMContentLoaded', initializeApp);

async function initializeApp() {
    console.log("Initializing GDML Editor Application...");

    // Initialize UI elements and pass callback handlers for UI-triggered actions
    UIManager.initUI({
        onNewProjectClicked: handleNewProject,
        onLoadGdmlClicked: () => UIManager.triggerFileInput('gdmlFile'), // UIManager handles its own file input now
        onLoadProjectClicked: () => UIManager.triggerFileInput('projectFile'),
        onGdmlFileSelected: handleLoadGdml, // Files are passed to handlers
        onProjectFileSelected: handleLoadProject,
        onSaveProjectClicked: handleSaveProject,
        onExportGdmlClicked: handleExportGdml,
        onAddObjectClicked: () => UIManager.showAddObjectModal(), // UIManager shows its modal
        onConfirmAddObject: handleAddObject, // Data from modal comes to this handler
        onDeleteSelectedClicked: handleDeleteSelectedFromHierarchy,
        onModeChangeClicked: handleModeChange, // Passes mode to InteractionManager
        onSnapToggleClicked: InteractionManager.toggleSnap, // Direct call if no complex logic
        onSnapSettingsChanged: InteractionManager.updateSnapSettings,
        onCameraModeChangeClicked: SceneManager.setCameraMode,
        onWireframeToggleClicked: SceneManager.toggleGlobalWireframe,
        onGridToggleClicked: SceneManager.toggleGridVisibility,
        onHierarchyItemSelected: handleHierarchySelection, // When an item in hierarchy panel is clicked
        onInspectorPropertyChanged: handleInspectorPropertyUpdate, // When a property in inspector is changed by user
    });

    // Initialize the 3D scene and its controls
    SceneManager.initScene({
        onObjectSelectedIn3D: handle3DSelection,          // Callback when object clicked in 3D scene
        onObjectTransformEnd: handleTransformEnd,          // Callback when TransformControls drag/rotate/scale ends
        onObjectTransformLive: handleTransformLive,       // Live transformations
        getInspectorSnapSettings: () => { // Provide snap settings to SceneManager/TransformControls
            return { 
                snapEnabled: InteractionManager.isSnapEnabled(), 
                translationSnap: InteractionManager.getTranslationSnapValue(),
                rotationSnap: InteractionManager.getRotationSnapValue() 
            };
        }
    });
    
    // Initialize interaction manager (modes, keyboard shortcuts for transforms)
    InteractionManager.initInteractionManager(
        SceneManager.getTransformControls(), // Pass the TransformControls instance
        SceneManager.getOrbitControls(),     // Pass the OrbitControls instance
        SceneManager.getFlyControls()        // Pass the FlyControls instance
    );

    // Restore session from backend on page load
    console.log("Fetching initial project state from backend...");
    const initialState = await APIService.getProjectState();
    // No try/catch needed, as the backend now guarantees a valid response
    if (initialState && initialState.project_state) {
        console.log("Initializing UI with project state.");
        // We use a simplified sync function here as the structure is slightly different
        AppState.currentProjectState = initialState.project_state;
        UIManager.updateHierarchy(initialState.project_state);
        SceneManager.renderObjects(initialState.scene_update || [], initialState.project_state);
    } else {
        // This case should theoretically not be reached anymore, but is good for safety
        UIManager.showError("Failed to retrieve a valid project state from the server.");
    }

    console.log("Application Initialized.");
    
    // Example: Fetch initial empty state or last saved state if implemented
    // try {
    //     const initialState = await APIService.getProjectState();
    //     if (initialState && Object.keys(initialState).length > 0 && initialState.world_volume_ref) {
    //         AppState.currentProjectState = initialState;
    //         UIManager.updateHierarchy(initialState);
    //         const threeJSDesc = APIService.extractThreeJSDescription(initialState); // Helper might be needed
    //         SceneManager.renderObjects(threeJSDesc || []);
    //     }
    // } catch (error) {
    //     console.warn("No initial project state found or error loading:", error);
    // }
}

/**
    The single function to update the entire UI from a new state object from the backend.
    This is the core of the unidirectional data flow pattern.
    @param {object} responseData The consistent success response object from the backend.
*/
function syncUIWithState(responseData) {
    if (!responseData || !responseData.success) {
        UIManager.showError(responseData.error || "An unknown error occurred during state sync.");
        return;
    }
    console.log("[Main] Syncing UI with new backend state. Message: " + responseData.message);

    // 1. Update the global AppState cache
    AppState.currentProjectState = responseData.project_state;
    AppState.selectedHierarchyItem = null; // Clear old selections
    AppState.selectedThreeObjects = [];
    AppState.selectedPVContext.pvId = null;

    // 2. Re-render the 3D scene
    if (responseData.scene_update) {
        SceneManager.renderObjects(responseData.scene_update, responseData.project_state);
    } else {
        SceneManager.clearScene(); // Ensure scene is cleared if there's no update
    }

    // 3. Re-render the hierarchy panels
    UIManager.updateHierarchy(responseData.project_state);

    // 4. Reset UI elements to a clean state
    UIManager.clearInspector();
    UIManager.clearHierarchySelection();
    SceneManager.unselectAllInScene();
}

// --- Handler Functions (Act as Controllers/Mediators) ---

// Handler for the "New Project" button
async function handleNewProject() {
    if (!UIManager.confirmAction("This will clear the current project. Are you sure?")) return;

    UIManager.showLoading("Creating new project...");
    try {
        const result = await APIService.newProject();
        syncUIWithState(result);
    } catch (error) {
        UIManager.showError("Failed to create new project: " + (error.message || error));
    } finally {
        UIManager.hideLoading();
    }
}

async function handleLoadGdml(file) {
    if (!file) return;
    UIManager.showLoading("Processing GDML...");

    try {
        const result = await APIService.loadGdmlFile(file);
        syncUIWithState(result);
    } catch (error) {
        UIManager.showError("Failed to load GDML: " + (error.message || error));
        SceneManager.clearScene();
        UIManager.clearHierarchy();
    } finally {
        UIManager.hideLoading();
    }
}

async function handleLoadProject(file) {
    if (!file) return;
    UIManager.showLoading("Loading project...");

    try {
        const result = await APIService.loadProjectFile(file);
        syncUIWithState(result);
    } catch (error) {
        UIManager.showError("Failed to load project: " + (error.message || error));
        SceneManager.clearScene();
        UIManager.clearHierarchy();
    } finally {
        UIManager.hideLoading();
    }
}

async function handleSaveProject() {
    UIManager.showLoading("Saving project...");
    try {
        await APIService.saveProject();
    } catch (error) { UIManager.showError("Failed to save project: " + (error.message || error)); }
    finally { UIManager.hideLoading(); }
}

async function handleExportGdml() {
    UIManager.showLoading("Exporting GDML...");
    try {
        await APIService.exportGdml(); // APIService handles the download
    } catch (error) { UIManager.showError("Failed to export GDML: " + (error.message || error)); }
    finally { UIManager.hideLoading(); }
}

async function handleAddObject(objectType, nameSuggestion, paramsFromModal) {
    UIManager.showLoading("Adding object...");
    try {
        const result = await APIService.addObject(objectType, nameSuggestion, paramsFromModal);
        syncUIWithState(result);
        UIManager.hideAddObjectModal();
    } catch (error) {
        UIManager.showError("Error adding object: " + (error.message || error));
    }
    finally { UIManager.hideLoading(); }
}

async function handleDeleteSelectedFromHierarchy() {
    if (!AppState.selectedHierarchyItem) {
        UIManager.showNotification("Please select an item from the hierarchy to delete.");
        return;
    }

    const { type, id, name } = AppState.selectedHierarchyItem;
    if (!UIManager.confirmAction(`Are you sure you want to delete ${type}: ${name}?`)) return;
        UIManager.showLoading("Deleting object...");
    try {
        const result = await APIService.deleteObject(type, id);
        syncUIWithState(result);
    } catch (error) { 
        UIManager.showError("Error deleting object: " + (error.message || error)); 
    }
    finally { UIManager.hideLoading(); }
}

function handleModeChange(newMode) {
    const currentSelectedIn3D = SceneManager.getSelectedObjects();
    InteractionManager.setMode(newMode, currentSelectedIn3D.length === 1 ? currentSelectedIn3D[0] : null);
    if (newMode === 'observe' && SceneManager.getTransformControls().object) {
        SceneManager.getTransformControls().detach();
    } else if (newMode !== 'observe' && AppState.selectedThreeObjects.length === 1){
        SceneManager.attachTransformControls(AppState.selectedThreeObjects[0]);
    }
}

async function handleHierarchySelection(itemContext) {
    AppState.selectedHierarchyItem = itemContext;
    const { type, id } = itemContext;

    // Fetch fresh details for the inspector
    const details = await APIService.getObjectDetails(type, id);
    if (!details) {
        UIManager.showError(`Could not fetch details for ${type} ${id}`);
        return;
    }

    itemContext.data = details;
    UIManager.populateInspector(itemContext);

    // If a physical volume is selected, cache its define references for live updates and select in 3D
    if (type === 'physical_volume') {
        SceneManager.selectObjectInSceneByPvId(id);
        AppState.selectedThreeObjects = SceneManager.getSelectedObjects();
        AppState.selectedPVContext.pvId = id;
        AppState.selectedPVContext.positionDefineName = typeof details.position === 'string' ? details.position : null;
        AppState.selectedPVContext.rotationDefineName = typeof details.rotation === 'string' ? details.rotation : null;
        
        if (InteractionManager.getCurrentMode() !== 'observe') {
            const selectedMesh = AppState.selectedThreeObjects[0];
            if(selectedMesh) SceneManager.attachTransformControls(selectedMesh);
        }
    } else {
        // Clear PV context and 3D selection if something else is selected
        AppState.selectedPVContext.pvId = null;
        AppState.selectedPVContext.positionDefineName = null;
        AppState.selectedPVContext.rotationDefineName = null;
        SceneManager.unselectAllInScene();
        AppState.selectedThreeObjects = [];
    }
}

// Called by SceneManager when an object is clicked in 3D
function handle3DSelection(selectedThreeObject) {
    if (selectedThreeObject) {
        const pvId = selectedThreeObject.userData.id;
        // This will now trigger the async data fetch and context update via the hierarchy
        UIManager.selectHierarchyItemByTypeAndId('physical_volume', pvId, AppState.currentProjectState);
    } else {
        UIManager.clearHierarchySelection();
        AppState.selectedHierarchyItem = null;
        AppState.selectedThreeObjects = [];
        AppState.selectedPVContext.pvId = null;
    }
}

// function handle3DSelection(selectedThreeObject) {
//     if (selectedThreeObject) {
//         SceneManager.updateSelectionState([selectedThreeObject]);
//         AppState.selectedThreeObjects = [selectedThreeObject];
//         const pvId = selectedThreeObject.userData.id;
//         // This will now trigger the async data fetch and context update
//         UIManager.selectHierarchyItemByTypeAndId('physical_volume', pvId, AppState.currentProjectState);
//     } else {
//         SceneManager.unselectAllInScene();
//         UIManager.clearHierarchySelection();
//         AppState.selectedHierarchyItem = null;
//         AppState.selectedThreeObjects = [];
//         // Clear PV context
//         AppState.selectedPVContext.pvId = null;
//         AppState.selectedPVContext.positionDefineName = null;
//         AppState.selectedPVContext.rotationDefineName = null;
//     }
// }

function handleTransformLive(liveObject) {
    // 1. Update the PV's own inspector (if it has inline values)
    if (AppState.selectedHierarchyItem && AppState.selectedHierarchyItem.id === liveObject.userData.id) {
        UIManager.updateInspectorTransform(liveObject);
    }

    // 2. If the transform is linked to a define, update THAT define's inspector
    const euler = new THREE.Euler().setFromQuaternion(liveObject.quaternion, 'ZYX');
    const newPosition = { x: liveObject.position.x, y: liveObject.position.y, z: liveObject.position.z };
    const newRotation = { x: euler.x, y: euler.y, z: euler.z };

    if (AppState.selectedPVContext.positionDefineName) {
        UIManager.updateDefineInspectorValues(AppState.selectedPVContext.positionDefineName, newPosition);
    }
    if (AppState.selectedPVContext.rotationDefineName) {
        UIManager.updateDefineInspectorValues(AppState.selectedPVContext.rotationDefineName, newRotation, true); // true for rotation
    }
}

// Called by SceneManager when TransformControls finishes a transformation
async function handleTransformEnd(transformedObject) {
    if (!transformedObject || !transformedObject.userData) return;
        UIManager.showLoading("Updating transform...");
    try {
        const objData = transformedObject.userData;
        const newPosition = { x: transformedObject.position.x, y: transformedObject.position.y, z: transformedObject.position.z };
        const euler = new THREE.Euler().setFromQuaternion(transformedObject.quaternion, 'ZYX');
        const newRotation = { x: euler.x, y: euler.y, z: euler.z };

        const result = await APIService.updateObjectTransform(objData.id, newPosition, newRotation);
        syncUIWithState(result);

    } catch (error) { 
        UIManager.showError("Error saving transform: " + (error.message || error)); 
        // TODO: Could add logic here to revert the object's transform in Three.js on failure.
    }
    finally { UIManager.hideLoading(); }
}

// Called by UIManager when a property is changed in the Inspector Panel
async function handleInspectorPropertyUpdate(objectType, objectId, propertyPath, newValue) {
    UIManager.showLoading("Updating property...");
    try {
        const result = await APIService.updateProperty(objectType, objectId, propertyPath, newValue);
        syncUIWithState(result);
    } catch (error) {
        UIManager.showError("Error updating property: " + (error.message || error));
    }
    finally { UIManager.hideLoading(); }
}
