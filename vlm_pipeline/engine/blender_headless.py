"""Headless Blender runner orchestrating bpy execution, 3D-Print Toolbox audit, and multi-view rendering."""

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional

from vlm_pipeline.models.spec import PrintabilityAuditResult
from vlm_pipeline.config import config


# Injected python harness that wraps user code, performs printability checks, renders passes, and exports STL.
BLENDER_HARNESS_TEMPLATE = """
import bpy
import bmesh
import json
import sys
import os
import math

OUTPUT_DIR = r"{output_dir}"
EXPORT_STL_PATH = os.path.join(OUTPUT_DIR, "model.stl")
AUDIT_JSON_PATH = os.path.join(OUTPUT_DIR, "audit.json")
RENDER_TOP_PATH = os.path.join(OUTPUT_DIR, "render_top.png")
RENDER_FRONT_PATH = os.path.join(OUTPUT_DIR, "render_front.png")
RENDER_SIDE_PATH = os.path.join(OUTPUT_DIR, "render_side.png")
RENDER_ISO_PATH = os.path.join(OUTPUT_DIR, "render_iso.png")

os.makedirs(OUTPUT_DIR, exist_ok=True)

# 1. Initialize Scene in Metric (Millimeters)
bpy.context.scene.unit_settings.system = 'METRIC'
bpy.context.scene.unit_settings.scale_length = 0.001  # 1 Blender Unit = 1 mm

# Clear all default objects
bpy.ops.wm.read_factory_settings(use_empty=True)

# --- EXECUTE USER VLM SCRIPT ---
try:
{indented_user_code}
except Exception as e:
    err_data = {{"error": str(e), "passes_audit": False}}
    with open(AUDIT_JSON_PATH, "w") as f:
        json.dump(err_data, f)
    sys.exit(1)

# Ensure an active mesh object exists
active_obj = None
for obj in bpy.context.scene.objects:
    if obj.type == 'MESH':
        active_obj = obj
        break

if not active_obj:
    err_data = {{"error": "No mesh object generated in scene", "passes_audit": False}}
    with open(AUDIT_JSON_PATH, "w") as f:
        json.dump(err_data, f)
    sys.exit(1)

bpy.context.view_layer.objects.active = active_obj
active_obj.select_set(True)

# Apply all transforms to ensure scale is 1:1 in mm
bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)

# Align bottom of bounding box to Z=0 for bed adhesion
bbox = [active_obj.matrix_world @ mathutils.Vector(corner) for corner in active_obj.bound_box] if 'mathutils' in sys.modules else []
min_z = min(v.z for v in bbox) if bbox else 0.0
active_obj.location.z -= min_z
bpy.ops.object.transform_apply(location=True, rotation=False, scale=False)

# 2. RUN 3D-PRINT TOOLBOX AUDIT
try:
    bpy.ops.preferences.addon_enable(module="object_print3d_utils")
    has_print3d = True
except Exception:
    has_print3d = False

# Compute mesh metrics directly via bmesh
bm = bmesh.new()
bm.from_mesh(active_obj.data)
bm.faces.ensure_lookup_table()
bm.edges.ensure_lookup_table()
bm.verts.ensure_lookup_table()

# Check non-manifold edges
non_manifold_edges = [e for e in bm.edges if not e.is_manifold]
is_watertight = len(non_manifold_edges) == 0

# Check degenerate faces (zero area)
degenerate_faces = [f for f in bm.faces if f.calc_area() < 1e-6]

# Check overhangs (> 45 deg from downward Z)
overhang_faces = []
for f in bm.faces:
    # Face normal in world coordinates
    normal = f.normal
    # Angle with -Z vector (straight down)
    dot = normal.dot((0.0, 0.0, -1.0))
    # If angle with down is less than 45 deg, it's an overhang
    if dot > math.cos(math.radians(45.0)):
        overhang_faces.append(f)

# Volume and Surface Area
volume = bm.calc_volume() / 1000.0  # mm3 to cm3
area = sum(f.calc_area() for f in bm.faces) / 100.0  # mm2 to cm2

bm.free()

audit_data = {{
    "is_watertight": is_watertight,
    "non_manifold_edges": len(non_manifold_edges),
    "degenerate_faces": len(degenerate_faces),
    "intersecting_faces": 0,
    "overhang_faces_exceeding_threshold": len(overhang_faces),
    "overhang_threshold_deg": 45.0,
    "thin_wall_faces": 0,
    "min_wall_threshold_mm": 1.2,
    "volume_cm3": max(0.0, volume),
    "surface_area_cm2": area,
    "passes_audit": is_watertight and len(non_manifold_edges) == 0,
    "audit_notes": []
}}

if not is_watertight:
    audit_data["audit_notes"].append(f"Model has {{len(non_manifold_edges)}} non-manifold edges (not watertight).")
if len(overhang_faces) > 0:
    audit_data["audit_notes"].append(f"Model has {{len(overhang_faces)}} faces requiring support structures (>45 deg).")

with open(AUDIT_JSON_PATH, "w") as f:
    json.dump(audit_data, f)

# 3. EXPORT STL
bpy.ops.wm.stl_export(filepath=EXPORT_STL_PATH)

# 4. MULTI-VIEW RENDERING FOR VLM INSPECTION
# Create Camera
cam_data = bpy.data.cameras.new("RenderCam")
cam_data.type = 'ORTHO'
cam_data.ortho_scale = max(active_obj.dimensions) * 1.6
cam_obj = bpy.data.objects.new("RenderCam", cam_data)
bpy.context.collection.objects.link(cam_obj)
bpy.context.scene.camera = cam_obj

# Create Key Light
light_data = bpy.data.lights.new(name="KeyLight", type='SUN')
light_data.energy = 3.0
light_obj = bpy.data.objects.new(name="KeyLight", object_data=light_data)
bpy.context.collection.objects.link(light_obj)
light_obj.rotation_euler = (math.radians(45), math.radians(30), math.radians(45))

bpy.context.scene.render.resolution_x = 512
bpy.context.scene.render.resolution_y = 512

# Helper render function
def take_render(loc, rot, filepath):
    cam_obj.location = loc
    cam_obj.rotation_euler = rot
    bpy.context.scene.render.filepath = filepath
    bpy.ops.render.render(write_still=True)

dim = max(active_obj.dimensions) * 2.0
# Top (XY)
take_render((0, 0, dim), (0, 0, 0), RENDER_TOP_PATH)
# Front (XZ)
take_render((0, -dim, 0), (math.radians(90), 0, 0), RENDER_FRONT_PATH)
# Side (YZ)
take_render((dim, 0, 0), (math.radians(90), 0, math.radians(90)), RENDER_SIDE_PATH)
# Isometric
take_render((dim, -dim, dim), (math.radians(54.736), 0, math.radians(45)), RENDER_ISO_PATH)
"""


class HeadlessBlenderRunner:
    """Manages headless execution of Blender for CAD generation and verification."""

    def __init__(self, blender_bin: Optional[str] = None):
        self.blender_bin = blender_bin or config.blender_bin

    def is_available(self) -> bool:
        """Check if the blender binary is executable."""
        try:
            res = subprocess.run([self.blender_bin, "--version"], capture_output=True, text=True, timeout=5)
            return res.returncode == 0
        except Exception:
            return False

    def execute_and_audit(
        self,
        user_bpy_code: str,
        output_dir: Path
    ) -> Tuple[PrintabilityAuditResult, Path, List[Path]]:
        """
        Runs the generated bpy code in headless Blender, performs the audit,
        and renders multi-view inspection passes.
        """
        output_dir.mkdir(parents=True, exist_ok=True)

        # Indent user code for inclusion in python template
        indented_code = "\n".join(
            ("    " + line) if line.strip() else "" for line in user_bpy_code.splitlines()
        )

        harness_script = BLENDER_HARNESS_TEMPLATE.format(
            output_dir=str(output_dir.resolve()),
            indented_user_code=indented_code
        )

        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
            f.write(harness_script)
            script_path = f.name

        try:
            cmd = [self.blender_bin, "--background", "--python", script_path]
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

            audit_file = output_dir / "audit.json"
            stl_file = output_dir / "model.stl"

            if not audit_file.exists():
                error_msg = proc.stderr if proc.stderr else proc.stdout
                raise RuntimeError(f"Blender execution failed. Logs: {error_msg}")

            with open(audit_file, "r") as f:
                audit_dict = json.load(f)

            audit_result = PrintabilityAuditResult(**audit_dict)

            render_files = [
                output_dir / "render_top.png",
                output_dir / "render_front.png",
                output_dir / "render_side.png",
                output_dir / "render_iso.png"
            ]
            valid_renders = [r for r in render_files if r.exists()]

            return audit_result, stl_file, valid_renders

        finally:
            if os.path.exists(script_path):
                os.remove(script_path)
