"""Visual decomposition and parametric code generation agent."""

import json
import re
from pathlib import Path
from typing import Tuple, Optional

from vlm_pipeline.models.spec import GeometricSpec, BoundingBox3D
from vlm_pipeline.vision.vlm_client import VLMClient
from vlm_pipeline.config import config


ANALYSIS_SYSTEM_PROMPT = """You are a senior additive manufacturing engineer and computational geometry expert.
Your job is to reverse-engineer a real-world object or technical sketch from 2D images into an exact, printable 3D CAD model.

CRITICAL CONSTRAINTS FOR 3D PRINTING:
1. Target Printer: Bambu Lab P1S (FDM).
2. Units: Millimeters (mm). Scale must be physically accurate.
3. Wall Thickness: Minimum 1.2mm (at least 3 perimeters on a 0.4mm nozzle).
4. Overhangs: Keep overhang angles under 45 degrees where possible, or design for self-supporting chamfers instead of steep fillets.
5. Manifoldness: The mesh must be 100% watertight (no non-manifold edges, no intersecting faces, no zero-area triangles).
6. Orientation: Design with a primary flat reference face that can contact the build plate.

You must output a single valid JSON object containing:
1. "spec": Detailed geometric specification.
2. "bpy_code": A self-contained, robust Blender Python script using `bpy` and `bmesh` that constructs the object.

Do NOT include markdown wrapping outside the JSON. Return raw parseable JSON.
"""

ANALYSIS_USER_TEMPLATE = """Analyze this image and generate the Blender Python (bpy/bmesh) script to model it for 3D printing.

User Dimension/Calibration Guidance:
{user_guidance}

Target Printer Parameters:
- Nozzle: {nozzle}mm
- Max Unsupported Overhang: {overhang}°
- Min Wall Thickness: {wall_thickness}mm

Guidelines for the `bpy_code`:
- Start with `import bpy`, `import bmesh`, `import math`
- Clear existing objects in `bpy.data.objects`
- Create a single active mesh object named 'GeneratedPart'
- Use `bmesh` operations (bmesh.ops.create_cube, bmesh.ops.create_cone, bmesh.ops.bevel, bmesh.ops.extrude_face_region, etc.)
- Remove doubles (`bmesh.ops.remove_doubles`) and recalculate normals outward (`bmesh.ops.recalc_face_normals`)
- Keep dimensions in millimeters
- Ensure the base of the part rests at Z=0 for easy bed adhesion

JSON Output Structure:
{{
  "spec": {{
    "part_name": "example_bracket",
    "bounding_box": {{
      "width_x_mm": 50.0,
      "depth_y_mm": 30.0,
      "height_z_mm": 20.0
    }},
    "symmetry_planes": ["XY"],
    "features": [
      {{"name": "base", "operation": "Extrude", "parameters": {{"x": 50, "y": 30, "z": 5}}}}
    ],
    "critical_tolerances_mm": {{"hole_diameter": 3.2}},
    "suggested_print_orientation": "Z_UP"
  }},
  "bpy_code": "import bpy\\nimport bmesh\\n# ... full executable code ..."
}}
"""


class VisualAnalyzer:
    """Decomposes an image into a geometric specification and generates bpy code."""

    def __init__(self, vlm_client: Optional[VLMClient] = None):
        self.client = vlm_client or VLMClient()

    def analyze_and_generate(
        self,
        image_path: Path,
        user_guidance: str = "Infer scale from context. If a caliper, ruler, or standard object is visible, use it as metric ground truth."
    ) -> Tuple[GeometricSpec, str]:
        """Perform vision inference and generate Blender Python modeling code."""
        prompt = ANALYSIS_USER_TEMPLATE.format(
            user_guidance=user_guidance,
            nozzle=config.print_quality.nozzle_diameter_mm,
            overhang=config.print_quality.max_unsupported_overhang_deg,
            wall_thickness=config.print_quality.min_wall_thickness_mm,
        )

        raw_response = self.client.complete_multimodal(
            prompt=prompt,
            image_paths=[image_path],
            system_prompt=ANALYSIS_SYSTEM_PROMPT,
            temperature=0.2
        )

        return self._parse_response(raw_response)

    def _parse_response(self, text: str) -> Tuple[GeometricSpec, str]:
        """Extract JSON safely from VLM response."""
        cleaned = text.strip()
        # Handle markdown fences if present
        if "```json" in cleaned:
            cleaned = cleaned.split("```json")[1].split("```")[0].strip()
        elif "```" in cleaned:
            cleaned = cleaned.split("```")[1].split("```")[0].strip()

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            # Fallback regex extraction if VLM added commentary
            match = re.search(r"\{[\s\S]*\}", cleaned)
            if match:
                data = json.loads(match.group(0))
            else:
                raise ValueError(f"Failed to parse JSON from VLM output: {text[:200]}...")

        spec = GeometricSpec(**data["spec"])
        bpy_code = data["bpy_code"]
        return spec, bpy_code
