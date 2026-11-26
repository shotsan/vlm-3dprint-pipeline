# VLM-to-Bambu 3D Printing Pipeline

Autonomous, closed-loop additive manufacturing pipeline connecting Vision-Language Models (VLMs) directly to OpenCASCADE B-Rep solid modeling, headless slicers, and Bambu Lab 3D printers.

## Overview

Rather than having an LLM write unconstrained CAD code (which introduces non-manifold geometry, inverted normals, and dimensional drift), this pipeline enforces a deterministic workflow:

1. **Constrained Slot-Filling**: The VLM analyzes visual input and selects components from an exhaustive mechanical engineering catalog (`bd_warehouse` and `BOSL2`), outputting an `AssemblyPlan` AST.
2. **Physical Boundary Contract Enforcement**: Pydantic validators enforce physical limits (wall thickness >= 1.2mm, ISO screw clearance tolerances, heat-set insert draft angles, and Bambu P1S bed bounds).
3. **Deterministic OpenCASCADE Compiler**: Compiles the plan into true mathematical B-Rep solids (`.step`) and watertight meshes (`.stl`) using exact CSG booleans.
4. **Interactive 3D Inspection Studio**: Standalone WebGL viewer with side-by-side reference comparison and real-time overhang angle heatmap shaders.
5. **Headless Slicing & Hardware Dispatch**: Automates OrcaSlicer CLI and uploads sliced `.gcode.3mf` directly to the Bambu P1S over local LAN (FTPS port 990, MQTT port 8883).

## Architecture

```
[Reference Image] -> [VLM Slot-Filling (T=0.0)]
                  -> [Physical Contract Validator]
                  -> [OpenCASCADE CAD Compiler]
                  -> [3D Inspection Studio & DFM Audit]
                  -> [Headless Slicer (OrcaSlicer)]
                  -> [Bambu P1S Local LAN (FTPS/MQTT)]
```

## Exhaustive Mechanical Component Library

The pipeline integrates verified industrial standards from `bd_warehouse` (105+ OpenCASCADE classes) and `BOSL2` (56 modules):

### 1. Fasteners, Threads & Inserts
- **Socket Head Cap Screws** (ISO 4762 / ASME B18.3): M2 to M8 with Close, Normal, and Loose clearance holes.
- **Button Head Screws** (ISO 7380-1): Low-profile domed fasteners with shallow counterbore pockets.
- **Countersunk Screws** (ISO 10642 / DIN 7991): Flat 90-degree flush head profiles.
- **Hex Head Bolts** (ISO 4017 / DIN 933): Standard hex bolt clearances and hex retention pockets.
- **Shoulder Screws** (ISO 7379): Precision pivot channels for mechanical linkages and rotating arms.
- **Grub / Set Screws** (ISO 4026): Threaded channels for locking shafts, pulleys, and couplers.
- **Heat-Set Threaded Inserts** (Ruthex / CNC Kitchen / McMaster): Tapered brass insert pockets with 8° draft angles for thermal insertion.
- **Captive Nut Traps** (ISO 4032 / DIN 934): Top-drop and side-slot captive hex nut pockets.
- **Thin Square Nut Slots** (DIN 562): Slide-in retention slots for standard 3D printer hardware.
- **Modelled Helical Threads**: Direct 3D printable ISO metric 60°, ACME, and bottle threads.

### 2. Bearings & Rotary Motion
- **Deep Groove Radial Ball Bearings** (ISO 15 Metric Series): Standard 608 (skate/extruder), 624, 625 (V-wheel), 688, 6000, 6001 with calibrated FDM press-fit offsets and through-shaft bores.
- **Flanged Ball Bearings**: F608, F623, F624 stepped retaining rims for axial belt tension loads.
- **Linear Motion Bearings**: LM8UU, LM10UU, LM12UU cylindrical rod channels with circlip retention.
- **Bushing Mounts**: Eccentric spacer adjustment cavities and sleeve bushings.

### 3. Structural Framing & Linear Motion (OpenBuilds)
- **V-Slot Extrusion Mounts**: 2020, 2040, and 4040 aluminum extrusion mating tabs and brackets.
- **C-Beam Gantry Plates**: Multi-wheel carriage plates for heavy linear actuators.
- **Drop-In T-Nut Slots**: 20-series (6mm) and 40-series (8mm) roll-in and hammer-head T-nut channels.

### 4. Power Transmission & Gearing
- **Involute Spur Gears**: Metric module 0.5 to 4.0, 20° pressure angle, center shaft bore with optional D-shaft flat.
- **GT2 Timing Pulleys**: 2mm pitch Gates GT2 pulleys (16T, 20T, 36T, 60T) with retention flanges and set-screw hubs.
- **Roller Chain Sprockets**: ANSI #25 and ISO 06B roller chain profiles.

### 5. Motors & Actuators
- **NEMA Stepper Motor Mounts**: NEMA 08, 11, 14, 17, 23, and 34 faceplates with center pilot boss registers and circular/slotted bolt patterns for belt tensioning.
- **CNC Spindle Clamps**: Split-collar pinch clamps for 52mm, 65mm, and 80mm motor bodies.

### 6. Structural Plates, Brackets & Enclosures
- **Mounting Plates**: Planar bases with corner fillets, mounting arrays, and 45° bottom bed-release chamfers.
- **Reinforced L-Brackets**: Rigid 90° corner brackets with central triangular webbing gussets.
- **Electronics Enclosure Tubs**: Hollow shells with corner screw standoffs and lid retention lips.
- **Sealing Rims**: Step flange lip-and-groove mating profiles for dust-sealed enclosures.
- **CubeTruss Spaceframes**: Ultra-lightweight high-rigidity diagonal strut trusses.

### 7. Joinery, Hinges & Compliant Mechanisms
- **Cantilever Snap-Fits**: Bending-strain optimized arms (epsilon <= 0.015 for PLA/PETG) with lead-in ramps.
- **Print-in-Place Knuckle Hinges**: Pre-assembled single-print hinges with calibrated 0.35mm internal gaps.
- **Dovetail Slide Joints**: 60° trapezoidal slide-in connectors with end stops.
- **Compliant Snap Pins**: Double-ended tool-less joining pins.

### 8. DFM Printability Utilities
- **Teardrop Horizontal Holes**: Converts horizontal cylindrical holes into 45° pointed teardrops to eliminate bridging droop without supports.
- **Hexagonal Ventilation Grills**: Honeycomb airflow patterns with 45° overhang walls for zero-support printing.
- **Tripod Camera Mounts**: Standard 1/4"-20 UNC nut pockets and Arca-Swiss dovetail rails.

## Quickstart

### Installation
```bash
git clone https://github.com/shotsan/vlm-3dprint-pipeline.git
cd vlm-3dprint-pipeline
pip install -e .
```

### Environment Setup
```bash
# Set your VLM API Key (Gemini, Claude, or OpenAI)
export GEMINI_API_KEY="your-gemini-key"
# Or: export ANTHROPIC_API_KEY="your-anthropic-key"
# Or: export OPENAI_API_KEY="your-openai-key"

# Set your Bambu P1S local LAN credentials
export BAMBU_IP="192.168.1.120"
export BAMBU_SERIAL="01P00A000000000"
export BAMBU_ACCESS_CODE="12345678"
```

### CLI Usage
```bash
# View the exhaustive component catalog:
vlm-print catalog

# Run full pipeline on an image or drawing:
vlm-print run examples/motor_bracket_sample.png --guidance "Mounting holes fit M3 socket head screws"

# Open the interactive 3D WebGL inspection studio:
vlm-print view output/motor_bracket_sample/

# Query Bambu P1S telemetry over local LAN MQTT:
vlm-print status
```

## Local Hardware Communication

All printer operations run over your local network without external cloud dependencies:
- **FTPS (Port 990)**: Implicit TLS file transfer to printer SD card.
- **MQTT (Port 8883)**: TLS connection for real-time telemetry and print job dispatch.
