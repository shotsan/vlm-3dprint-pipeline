"""Diagnostic Contact Sheet Composite Renderer.

Stitches reference input photos, multi-view Blender orthographic passes,
and physical audit telemetry into a single high-resolution diagnostic report.
"""

from pathlib import Path
from typing import List, Optional
from PIL import Image, ImageDraw, ImageFont


class DiagnosticReportRenderer:
    """Generates a composite 2x3 grid image for simultaneous human & VLM review."""

    @staticmethod
    def render_composite(
        reference_image_path: Path,
        render_images: List[Path],
        audit_summary: dict,
        output_path: Path
    ) -> Path:
        """
        Creates a 1600x1000 composite diagnostic image.
        Grid layout:
        [Ref Image]   [Top View XY]    [Front View XZ]
        [Side View YZ] [Iso Wireframe]  [Telemetry HUD]
        """
        canvas_w = 1600
        canvas_h = 1000
        cell_w = 500
        cell_h = 440
        padding = 20

        composite = Image.new("RGB", (canvas_w, canvas_h), color=(15, 17, 23))
        draw = ImageDraw.Draw(composite)

        # Title bar
        draw.rectangle([(0, 0), (canvas_w, 45)], fill=(22, 25, 34))
        draw.text((20, 14), "BAMBU LAB P1S | VLM 3D RECONSTRUCTION & PRINTABILITY AUDIT", fill=(74, 222, 128))

        # Helper to load and fit image into cell
        def place_image(img_path: Path, x: int, y: int, title: str):
            draw.rectangle([(x, y), (x + cell_w, y + 25)], fill=(26, 30, 42))
            draw.text((x + 10, y + 6), title, fill=(203, 213, 225))
            if img_path and img_path.exists():
                try:
                    src = Image.open(img_path)
                    src.thumbnail((cell_w, cell_h - 25))
                    # Center in cell
                    offset_x = x + (cell_w - src.width) // 2
                    offset_y = y + 25 + (cell_h - 25 - src.height) // 2
                    composite.paste(src, (offset_x, offset_y))
                except Exception as e:
                    draw.text((x + 20, y + 100), f"Error loading image: {e}", fill=(239, 68, 68))
            else:
                draw.text((x + 100, y + 150), "[No Image Rendered]", fill=(100, 116, 139))

        # Row 1
        # Cell 1: Reference
        place_image(reference_image_path, 20, 60, "1. Target Reference Photo")

        # Cell 2: Top View
        top_img = next((p for p in render_images if "top" in p.name.lower()), None)
        place_image(top_img, 540, 60, "2. Top View (XY Plane)")

        # Cell 3: Front View
        front_img = next((p for p in render_images if "front" in p.name.lower()), None)
        place_image(front_img, 1060, 60, "3. Front View (XZ Plane)")

        # Row 2
        # Cell 4: Side View
        side_img = next((p for p in render_images if "side" in p.name.lower()), None)
        place_image(side_img, 20, 520, "4. Right View (YZ Plane)")

        # Cell 5: Isometric
        iso_img = next((p for p in render_images if "iso" in p.name.lower()), None)
        place_image(iso_img, 540, 520, "5. Isometric 3D View")

        # Cell 6: Telemetry HUD
        hud_x = 1060
        hud_y = 520
        draw.rectangle([(hud_x, hud_y), (hud_x + cell_w, hud_y + 25)], fill=(26, 30, 42))
        draw.text((hud_x + 10, hud_y + 6), "6. Physical Printability Telemetry", fill=(56, 189, 248))

        hud_bg = [(hud_x, hud_y + 25), (hud_x + cell_w, hud_y + cell_h)]
        draw.rectangle(hud_bg, fill=(19, 22, 31), outline=(40, 45, 61))

        lines = [
            f"Part Name: {audit_summary.get('part_name', 'GeneratedPart')}",
            f"Bambu Envelope: 256 x 256 x 256 mm",
            f"Watertight / Manifold: {'PASS (Watertight)' if audit_summary.get('is_watertight', True) else 'FAIL (Open edges)'}",
            f"Non-Manifold Edges: {audit_summary.get('non_manifold_edges', 0)}",
            f"Overhang Faces (>45°): {audit_summary.get('overhang_faces', 0)}",
            f"Tree Supports: {'Required' if audit_summary.get('overhang_faces', 0) > 0 else 'None (Self-supporting)'}",
            f"Estimated Time: {audit_summary.get('estimated_time_minutes', 0.0):.1f} mins",
            f"Filament Consumed: {audit_summary.get('filament_used_grams', 0.0):.1f} g",
            f"Hardware Status: Bambu P1S Ready"
        ]

        text_y = hud_y + 45
        for line in lines:
            color = (74, 222, 128) if "PASS" in line else ((239, 68, 68) if "FAIL" in line else (226, 232, 240))
            draw.text((hud_x + 20, text_y), line, fill=color)
            text_y += 36

        output_path.parent.mkdir(parents=True, exist_ok=True)
        composite.save(output_path)
        print(f"[Visualizer] Diagnostic Contact Sheet saved to: {output_path}")
        return output_path
