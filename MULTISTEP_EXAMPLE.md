# Multi-Step Detector Design Example

This document demonstrates how to use AIRPET's AI chat interface to build a complete detector geometry through a conversational workflow.

## Overview

The example shows building a simple **calorimeter detector** with:
- World volume
- Detector envelope with 4 layers
- 10×10 arrays of readout channels per layer
- Materials (lead absorber, scintillator active)
- Sensitive detectors for readout

## Prerequisites

- AIRPET server running on port 5003
- AI backend configured (e.g., `llama_cpp::Qwen3.5-27B-Q6_K`)
- Python requests library

## Conversation Flow

### Step 1: Create World and Materials

```
User: Create a detector world: a box 5000mm x 5000mm x 5000mm named "world".
Also create two materials: lead (density 11.35 g/cm³) and scintillator plastic (density 1.03 g/cm³).
```

**Expected AI actions:**
- Create box solid `world` with dimensions 5000×5000×5000 mm
- Create material `lead` with density 11.35 g/cm³
- Create material `scintillator` with density 1.03 g/cm³

### Step 2: Add Detector Layers

```
User: Now create 4 detector layers stacked along z-axis. Each layer is a box 2400mm x 2400mm x 1000mm.
Position them at z = -1500mm, -500mm, 500mm, and 1500mm (spaced 1000mm apart to avoid overlap).
Name them layer_1, layer_2, layer_3, layer_4.
```

**Expected AI actions:**
- Create 4 box solids for the layers
- Apply translations to position each layer along z-axis

### Step 3: Create Channels and Arrays

```
User: Create a channel solid: a box 100mm x 100mm x 1000mm named "channel".
Then create a 10x10 replica array of channels in layer_1, with 100mm spacing in x and y directions.
```

**Expected AI actions:**
- Create box solid `channel` with dimensions 100×100×1000 mm
- Create replica array with 10 divisions in x, 10 in y
- Set spacing to 100mm in both directions

### Step 4: Add Logical Volumes and Sensitive Detectors

```
User: Create a logical volume for the channel using the scintillator material.
Mark this logical volume as a sensitive detector for readout.
```

**Expected AI actions:**
- Create logical volume linking `channel` solid to `scintillator` material
- Set `is_sensitive = true` on the logical volume

## Running the Test

```bash
python test_multistep_detector.py
```

## Expected Output

```
================================================================================
MULTI-STEP DETECTOR DESIGN TEST
================================================================================

--- STEP 1: World and Materials ---
[AI creates world, lead, scintillator]

--- STEP 2: Detector Layers ---
[AI creates layer_1 through layer_4]

--- STEP 3: Channels and Array ---
[AI creates channel solid and replica array]

--- STEP 4: Logical Volume and Sensitive Detector ---
[AI creates logical volume with sensitive detector]

================================================================================
FINAL SUMMARY
================================================================================

📦 Solids:
   - world
   - layer_1
   - layer_2
   - layer_3
   - layer_4
   - channel

🧪 Materials:
   - lead
   - scintillator

📊 Logical Volumes:
   - channel_lv [SENSITIVE]
```

## Key Features Demonstrated

1. **State Persistence**: AI maintains context across multiple turns
2. **Nested Geometry**: World → layers → channels hierarchy
3. **Materials**: Element and compound material creation
4. **Replicas**: 2D arrays with custom spacing
5. **Sensitive Detectors**: Marking volumes for readout
6. **Transforms**: Positioning via translations

## Extending the Example

To build a more complete detector, you could add:

- **More layers**: Apply the same channel array pattern to layers 2-4
- **Boolean operations**: Cut holes or add complex shapes
- **Rotations**: Tilt layers or rotate the entire detector
- **Daughter volumes**: Place electronics or support structures inside volumes
- **Visualization attributes**: Add colors and visibility settings

## API Reference

The test uses these endpoints:

- `POST /new_project` - Create fresh project
- `POST /api/ai/chat` - Send AI messages
- `GET /get_project_state` - Retrieve current geometry

## Troubleshooting

**AI times out**: Increase `turn_limit` parameter (default: 25)

**Wrong naming**: AI may use different names; check actual project state

**Missing features**: Ensure AI backend has tool-calling capability enabled
