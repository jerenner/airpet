# virtual-pet

virtual-pet is a tool intended to assist users in creating and comparing geometries for positron emission tomography (PET) machines in Geant4. It is currently a web-based, AI-assisted visual editor for Geant4 GDML geometries. It provides an intuitive interface for creating, inspecting, and modifying complex geometries without needing to write XML by hand. The integrated AI assistant allows users to generate and place objects using natural language prompts.

![virtual-pet screenshot](static/virtual_pet_screenshot.png)

## Features

-   **3D Visualization:** Real-time, interactive 3D rendering of the geometry using three.js.
-   **Visual Editing:** Manipulate objects in the 3D view with translate and rotate gizmos.
-   **Hierarchical View:** Browse the geometry structure, materials, solids, and defines in a clear, tabbed interface.
-   **Core Geometry Components:** Add/modify/delete core geometry components:
    -   Defines (positions, rotations)
    -   Materials (simple and composite)
    -   Solids (primitives and complex booleans)
    -   Logical and Physical Volumes
-   **File Operations:**
    -   Import/Export full projects in an internal JSON format.
    -   Import full GDML files to start a project.
    -   Import GDML or JSON "parts" to merge into an existing geometry.
    -   Export the final geometry to a standard GDML file for use in Geant4.
-   **AI Assistant:** Leverage a local LLM (via Ollama) to generate geometry from natural language prompts.

## Installation

To run virtual-pet, you need a Python environment and a local instance of the Ollama AI service.

### 1. Prerequisites

-   [Python](https://www.python.org/downloads/) 3.9+
-   [Git](https://git-scm.com/)

### 2. Backend Setup (Python)

First, set up the Python server which handles all the geometry logic.

```bash
# 1. Clone the repository
git clone https://github.com/your-username/virtual-pet.git
cd virtual-pet

# 2. (Recommended) Create and activate a virtual environment
python -m venv venv
source venv/bin/activate  # On Windows, use `venv\Scripts\activate`

# 3. Install the required Python packages
pip install -r requirements.txt
```

### 3. AI Backend Setup (Ollama)

The AI assistant requires a running Ollama instance.

```bash
# 1. Download and install Ollama from the official website:
#    https://ollama.com

# 2. Pull the recommended AI model. We suggest gemma3:12b as a good 
#    starting point for its balance of speed and capability.
#    You can also use other models like `llama3` or `gemma3:27b`.
ollama run gemma3:12b

# 3. IMPORTANT: Leave the Ollama application running in the background.
#    The virtual-pet backend needs to connect to it.
```
*Note: The AI model will be downloaded the first time you run this command, which may take several minutes and require significant disk space (9b models are ~5-6 GB).*

## Running the Application

With both the Python environment and Ollama set up, you can now run the application.

```bash
# 1. Make sure you are in the 'virtual-pet' directory with your
#    virtual environment activated.

# 2. Start the Flask server.
python app.py

# 3. Open your web browser and navigate to:
#    http://localhost:5003
```

The web application should now be running. The AI "Generate" button will be enabled if the application successfully connects to your running Ollama instance.

## Usage

-   **File Menu:** Use the `File` menu to create a new project, open existing GDML/JSON projects, or save/export your work.
-   **Hierarchy Panels:** Use the tabs on the left to browse and select different components of your geometry. Double-click an item to open its editor.
-   **Inspector:** When an item is selected, its properties will appear in the Inspector panel on the bottom-left. For physical volumes, you can edit transforms directly or link them to defines.
-   **3D View:**
    -   **Observe Mode:** Left-click and drag to rotate, right-click and drag to pan, scroll wheel to zoom.
    -   **Translate/Rotate Modes:** Select a physical volume and use the gizmo to modify its position or rotation.
-   **AI Assistant:**
    1.  Type a descriptive prompt into the text box at the bottom right. For example: *"Create a detector made of a 20cm long tube of scintillator with a 5cm radius, and place it pointing up at x=100."*
    2.  Click the "➤" (Generate) button.
    3.  The UI will show a loading state while the AI processes the request. Once complete, the new geometry will appear in the 3D view and hierarchy.
    Note that the accuracy and reliability of the AI will depend on what model you are using. It's likely that current