// static/main.js (New, refactored version)

import * as UIManager from './uiManager.js';
import * as SceneManager from './sceneManager.js';
import * as InteractionManager from './interactionManager.js';
import * as APIService from './apiService.js';

// --- Global Application State (Keep this minimal) ---
const AppState = {
    currentProjectState: null,    // Full state dict from backend (defines, materials, solids, LVs, world_ref)
    selectedHierarchyItem: null,  // { type, id, name, data (raw from projectState) }
    selectedThreeObjects: []      // Managed by SceneManager, but AppState might need to know for coordination
};

// --- Initialization ---
document.addEventListener('DOMContentLoaded', initializeApp);

async function initializeApp() {
    console.log("Initializing GDML Editor Application...");

    // Initialize UI elements and pass callback handlers for UI-triggered actions
    UIManager.initUI({
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

    // Optionally, load a default state or welcome message
    UIManager.clearInspector();
    UIManager.clearHierarchy();
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

// --- Handler Functions (Act as Controllers/Mediators) ---

async function handleLoadGdml(file) {
    if (!file) return;
    UIManager.showLoading("Processing GDML...");
    try {
        const threeJSData = await APIService.loadGdmlFile(file); // Backend returns threejs_description
        SceneManager.renderObjects(threeJSData || []);
        
        const fullState = await APIService.getProjectState(); // Then fetch the full state
        AppState.currentProjectState = fullState;
        UIManager.updateHierarchy(fullState);
        UIManager.clearInspector();
        SceneManager.unselectAllInScene();
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
        const threeJSData = await APIService.loadProjectFile(file); // Backend returns threejs_description
        SceneManager.renderObjects(threeJSData || []);

        const fullState = await APIService.getProjectState();
        AppState.currentProjectState = fullState;
        UIManager.updateHierarchy(fullState);
        UIManager.clearInspector();
        SceneManager.unselectAllInScene();
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
        await APIService.saveProject(); // APIService handles the download
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
        if (result.success) {
            AppState.currentProjectState = result.project_state;
            UIManager.updateHierarchy(result.project_state);
            if (result.scene_update) SceneManager.renderObjects(result.scene_update);
            UIManager.hideAddObjectModal();
            // Optionally select the new item in hierarchy and inspector
            const newItemId = result.new_object.id || result.new_object.name; // Adjust based on what backend returns for id
            const newItemType = objectType.startsWith('solid_') ? 'solid' : (objectType.startsWith('define_') ? 'define' : objectType);
            UIManager.selectHierarchyItemByTypeAndId(newItemType, newItemId, result.project_state);

        } else {
            UIManager.showError("Failed to add object: " + result.error);
        }
    } catch (error) { UIManager.showError("Error adding object: " + (error.message || error)); }
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
        if (result.success) {
            AppState.currentProjectState = result.project_state;
            UIManager.updateHierarchy(result.project_state);
            if (result.scene_update) SceneManager.renderObjects(result.scene_update);
            UIManager.clearInspector();
            AppState.selectedHierarchyItem = null; // Clear selection
        } else {
            UIManager.showError("Failed to delete object: " + result.error);
        }
    } catch (error) { UIManager.showError("Error deleting object: " + (error.message || error)); }
    finally { UIManager.hideLoading(); }
}

function handleModeChange(newMode) {
    const currentSelectedIn3D = SceneManager.getSelectedObjects(); // Get currently selected 3D objects
    InteractionManager.setMode(newMode, currentSelectedIn3D.length === 1 ? currentSelectedIn3D[0] : null);
    if (newMode === 'observe' && SceneManager.getTransformControls().object) {
        SceneManager.getTransformControls().detach(); // Detach gizmo when switching to observe
    } else if (newMode !== 'observe' && AppState.selectedThreeObjects.length === 1){
        SceneManager.attachTransformControls(AppState.selectedThreeObjects[0]);
    }
}

// Called by UIManager when an item in the hierarchy panel is clicked
function handleHierarchySelection(itemContext) { // itemContext = { type, id, name, data }
    AppState.selectedHierarchyItem = itemContext;
    UIManager.populateInspector(itemContext.data, itemContext.type, itemContext.id); // Pass type and id for property updates

    if (itemContext.type === 'physical_volume') {
        SceneManager.selectObjectInSceneByPvId(itemContext.id); // Highlights in 3D, might attach TransformControls
    } else {
        SceneManager.unselectAllInScene(); // If a non-PV (define, mat, solid) is selected, clear 3D selection
        SceneManager.getTransformControls().detach();
    }
}

// Called by SceneManager when an object is clicked in 3D
function handle3DSelection(selectedThreeObject) { // selectedThreeObject is the THREE.Mesh or null
    SceneManager.updateSelectionState(selectedThreeObject ? [selectedThreeObject] : []); // SceneManager manages its internal selection
    AppState.selectedThreeObjects = selectedThreeObject ? [selectedThreeObject] : [];

    if (selectedThreeObject) {
        const pvId = selectedThreeObject.userData.id;
        UIManager.selectHierarchyItemByTypeAndId('physical_volume', pvId, AppState.currentProjectState); // This will trigger handleHierarchySelection -> populateInspector
        if(InteractionManager.getCurrentMode() !== 'observe'){ // If in a transform mode, attach controls
            SceneManager.attachTransformControls(selectedThreeObject);
        }
    } else { // Clicked empty space
        UIManager.clearHierarchySelection();
        UIManager.clearInspector();
        AppState.selectedHierarchyItem = null;
        SceneManager.getTransformControls().detach();
    }
}

// Called by SceneManager when TransformControls finishes a transformation
async function handleTransformEnd(transformedObject) {
    if (!transformedObject || !transformedObject.userData) return;
    const objData = transformedObject.userData; // Should contain the PV id

    const newPosition = { x: transformedObject.position.x, y: transformedObject.position.y, z: transformedObject.position.z };
    const euler = new THREE.Euler().setFromQuaternion(transformedObject.quaternion, 'ZYX');
    const newRotation = { x: euler.x, y: euler.y, z: euler.z };
    // TODO: Add scale from transformedObject.scale if scale mode is implemented

    UIManager.showLoading("Updating transform...");
    try {
        const result = await APIService.updateObjectTransform(objData.id, newPosition, newRotation);
        if(result.success){
            // TransformControls has already updated the object visually.
            // We need to update the inspector panel if this object is selected.
            if(AppState.selectedHierarchyItem && AppState.selectedHierarchyItem.id === objData.id){
                 const freshDetails = await APIService.getObjectDetails(AppState.selectedHierarchyItem.type, AppState.selectedHierarchyItem.id);
                 if (freshDetails) {
                    AppState.selectedHierarchyItem.data = freshDetails; // Update local copy of data
                    UIManager.populateInspector(freshDetails, AppState.selectedHierarchyItem.type, AppState.selectedHierarchyItem.id);
                 }
            }
        } else {
            UIManager.showError("Transform update failed on backend: " + (result.error || "Unknown error"));
            // TODO: Revert object's transform in Three.js scene to its state before dragging
            // This would involve fetching the last known good state from AppState.currentProjectState
            // and re-applying it to the transformedObject.
        }
    } catch (error) { UIManager.showError("Error saving transform: " + (error.message || error)); }
    finally { UIManager.hideLoading(); }
}

// Called by UIManager when a property is changed in the Inspector Panel
async function handleInspectorPropertyUpdate(objectType, objectId, propertyPath, newValue) {
    UIManager.showLoading("Updating property...");
    try {
        const result = await APIService.updateProperty(objectType, objectId, propertyPath, newValue);
        if (result.success) {
            SceneManager.renderObjects(result.scene_update); // Re-render 3D from backend
            
            const fullState = await APIService.getProjectState(); // Fetch full state again
            AppState.currentProjectState = fullState;
            UIManager.updateHierarchy(fullState); // Rebuild hierarchy
            
            // Re-select and re-populate inspector for the edited item
            UIManager.reselectHierarchyItem(objectType, objectId, fullState);

        } else {
            UIManager.showError("Property update failed: " + (result.error || "Unknown error"));
        }
    } catch (error) { UIManager.showError("Error updating property: " + (error.message || error)); }
    finally { UIManager.hideLoading(); }
}