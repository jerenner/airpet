// static/apiService.js

// --- Configuration ---
// It's good practice to have the base URL configurable
const API_BASE_URL = 'http://localhost:5003'; // Empty for same-origin, or e.g., 'http://localhost:5003' if different

// --- Helper Functions ---
async function handleResponse(response) {
    if (!response.ok) {
        // Try to parse error message from JSON response, else use status text
        let errorData;
        try {
            errorData = await response.json();
        } catch (e) {
            // Not a JSON response
            throw new Error(`Network error: ${response.status} ${response.statusText}`);
        }
        throw new Error(errorData.error || `Request failed with status ${response.status}`);
    }
    return response.json(); // Assumes all successful responses are JSON
}

async function handleBlobResponse(response, defaultFilename) {
    if (!response.ok) {
        let errorData;
        try {
            errorData = await response.json();
        } catch (e) {
            throw new Error(`Network error: ${response.status} ${response.statusText}`);
        }
        throw new Error(errorData.error || `Request failed with status ${response.status}`);
    }
    
    // Create a link and trigger a download for the blob data
    const blob = await response.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.style.display = 'none';
    a.href = url;
    a.download = defaultFilename;
    document.body.appendChild(a);
    a.click();
    window.URL.revokeObjectURL(url);
    document.body.removeChild(a);
}

// --- API Functions ---

/**
 * Creates a new, empty project on the backend with a default world volume.
 * @returns {Promise<Object>} A promise that resolves to the new project state.
 */
export async function newProject() {
    const response = await fetch(`${API_BASE_URL}/new_project`, {
        method: 'POST',
    });
    return handleResponse(response);
}

/**
 * Loads a GDML file by sending it to the backend for processing.
 * @param {File} gdmlFile The GDML file object from a file input.
 * @returns {Promise<Array>} A promise that resolves to the Three.js scene description array.
 */
export async function loadGdmlFile(gdmlFile) {
    const formData = new FormData();
    formData.append('gdmlFile', gdmlFile);

    const response = await fetch(`${API_BASE_URL}/process_gdml`, {
        method: 'POST',
        body: formData,
    });
    return handleResponse(response);
}

/**
 * Loads a project JSON file by sending it to the backend.
 * @param {File} projectFile The project JSON file object from a file input.
 * @returns {Promise<Array>} A promise that resolves to the Three.js scene description array.
 */
export async function loadProjectFile(projectFile) {
    const formData = new FormData();
    formData.append('projectFile', projectFile);

    const response = await fetch(`${API_BASE_URL}/load_project_json`, {
        method: 'POST',
        body: formData,
    });
    return handleResponse(response);
}

/**
 * Requests the current project state from the backend and triggers a browser download.
 * @returns {Promise<void>}
 */
export async function saveProject() {
    const response = await fetch(`${API_BASE_URL}/save_project_json`);
    await handleBlobResponse(response, 'project.json');
}

/**
 * Requests the GDML representation of the current project state and triggers a download.
 * @returns {Promise<void>}
 */
export async function exportGdml() {
    const response = await fetch(`${API_BASE_URL}/export_gdml`);
    await handleBlobResponse(response, 'exported_geometry.gdml');
}

/**
 * Gets the entire current project state from the backend.
 * @returns {Promise<Object>} A promise that resolves to the full project state dictionary.
 */
export async function getProjectState() {
    const response = await fetch(`${API_BASE_URL}/get_project_state`);
    return handleResponse(response);
}

/**
 * Gets detailed information for a single object.
 * @param {string} objectType e.g., 'physical_volume', 'solid', 'define'
 * @param {string} objectId The unique ID (for PVs) or name (for others) of the object.
 * @returns {Promise<Object>} A promise that resolves to the object's data dictionary.
 */
export async function getObjectDetails(objectType, objectId) {
    const response = await fetch(`${API_BASE_URL}/get_object_details?type=${objectType}&id=${objectId}`);
    return handleResponse(response);
}

/**
 * Adds a new object to the geometry.
 * @param {string} objectType The type of object to add (e.g., 'solid_box').
 * @param {string} nameSuggestion The user-suggested name for the new object.
 * @param {Object} params A dictionary of parameters for the new object.
 * @returns {Promise<Object>} A promise that resolves to the backend's response, typically including success status and updated scene/project data.
 */
export async function addObject(objectType, nameSuggestion, params) {
    const response = await fetch(`${API_BASE_URL}/add_object`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ object_type: objectType, name: nameSuggestion, params: params })
    });
    return handleResponse(response);
}

/**
 * Deletes an object from the geometry.
 * @param {string} objectType The type of the object to delete.
 * @param {string} objectId The unique ID or name of the object to delete.
 * @returns {Promise<Object>} A promise that resolves to the backend's response.
 */
export async function deleteObject(objectType, objectId) {
    const response = await fetch(`${API_BASE_URL}/delete_object`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ object_type: objectType, object_id: objectId })
    });
    return handleResponse(response);
}

/**
 * Updates the transformation (position, rotation) of a physical volume.
 * @param {string} objectId The unique ID (UUID) of the physical volume.
 * @param {Object} position The new position {x, y, z}.
 * @param {Object} rotation The new rotation (ZYX Euler in radians) {x, y, z}.
 * @returns {Promise<Object>} A promise that resolves to the backend's response.
 */
export async function updateObjectTransform(objectId, position, rotation) {
    const payload = { id: objectId };
    if (position) payload.position = position;
    if (rotation) payload.rotation = rotation;

    const response = await fetch(`${API_BASE_URL}/update_object_transform`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    });
    return handleResponse(response);
}

/**
 * Updates a specific property of any object in the geometry.
 * @param {string} objectType The type of object.
 * @param {string} objectId The unique ID or name of the object.
 * @param {string} propertyPath The path to the property (e.g., 'parameters.x').
 * @param {any} newValue The new value for the property.
 * @returns {Promise<Object>} A promise that resolves to the backend's response, typically including success status and updated scene/project data.
 */
export async function updateProperty(objectType, objectId, propertyPath, newValue) {
    const response = await fetch(`${API_BASE_URL}/update_property`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            object_type: objectType,
            object_id: objectId,
            property_path: propertyPath,
            new_value: newValue
        })
    });
    return handleResponse(response);
}