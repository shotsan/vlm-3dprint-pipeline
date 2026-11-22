# VLM-to-Bambu 3D Printing Pipeline

Autonomous, closed-loop additive manufacturing pipeline connecting Vision-Language Models (VLMs) directly to OpenCASCADE B-Rep solid modeling, headless slicers, and Bambu Lab 3D printers.

## Overview

Rather than having an LLM write unconstrained CAD code (which introduces non-manifold geometry, inverted normals, and dimensional drift), this pipeline enforces a deterministic workflow:

1. **Constrained Slot-Filling**: The VLM analyzes visual input and selects components from a verified mechanical engineering catalog (`bd_warehouse` and `BOSL2`), outputting an `AssemblyPlan` AST.
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

## Component Library

Integrated libraries provide pre-validated mechanical building blocks:
- **Fasteners**: Standard ISO 4762 socket head cap screws, countersunk screws, and Ruthex heat-set insert pockets.
- **Bearings**: Precision press-fit cavities for 608 skate, 624, and 625 bearings with calibrated FDM tolerance offsets.
- **Motors**: NEMA 14, 17, and 23 stepper faceplates with pilot ring and bolt circle cutouts.
- **Structural**: Mounting plates with corner fillets and 45-degree chamfers, reinforcement gussets.
- **Joints**: Cantilever snap-fit arms with automatic bending strain calculation for PLA/PETG.

## Quickstart

### Installation
```bash
git clone https://github.com/shotsan/vlm-3dprint-pipeline.git
cd vlm-3dprint-pipeline
pip install -e .
```

### Environment Setup
```bash
export ANTHROPIC_API_KEY="your-api-key"
export BAMBU_IP="192.168.1.120"
export BAMBU_SERIAL="01P00A000000000"
export BAMBU_ACCESS_CODE="12345678"
```

### Usage
```bash
# Run full pipeline from an image
vlm-print run part_photo.jpg --guidance "Mounting holes fit M3 socket head screws"

# View catalog of components and parameter limits
vlm-print catalog

# Open interactive 3D inspection studio
vlm-print view output/part_photo/

# Check Bambu printer status over LAN MQTT
vlm-print status
```

## Model Context Protocol (MCP)

This project can be registered as an MCP server for coding agents:
```json
{
  "mcpServers": {
    "bambu-3dprint": {
      "command": "vlm-print",
      "args": ["serve"],
      "env": {
        "ANTHROPIC_API_KEY": "your-api-key",
        "BAMBU_IP": "192.168.1.120",
        "BAMBU_ACCESS_CODE": "12345678"
      }
    }
  }
}
```

## Local Hardware Communication

All printer operations run over your local network without external cloud dependencies:
- **FTPS (Port 990)**: Implicit TLS file transfer to printer SD card.
- **MQTT (Port 8883)**: TLS connection for real-time telemetry and print job dispatch.
