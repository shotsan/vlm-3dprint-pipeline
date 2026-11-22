"""Deterministic Compiler translating an AssemblyPlan into verified CAD geometry.

Supports both:
1. IndustrialCADBuilder (build123d + bd_warehouse) -> Generates true mathematical B-Rep STEP & watertight STL.
2. Blender BMesh Engine -> Headless visualization and 3D-Print Toolbox audit.
"""

from pathlib import Path
from typing import Dict, Any
from vlm_pipeline.workflow.schema import AssemblyPlan


class AssemblyCompiler:
    """Compiles a declarative AssemblyPlan into deterministic CAD solids and scripts."""

    @staticmethod
    def compile_to_cad(plan: AssemblyPlan, output_dir: Path) -> Dict[str, Path]:
        """
        Directly compiles the AssemblyPlan using IndustrialCADBuilder (build123d + bd_warehouse).
        Outputs true mathematical STEP and high-res STL without Blender overhead.
        """
        from vlm_pipeline.library.cad_engine import IndustrialCADBuilder

        base_comp = plan.components[0]
        params = base_comp.parameters

        # 1. Build Base
        if base_comp.component_type == "mounting_plate":
            part = IndustrialCADBuilder.build_mounting_plate(
                width_x=params.get("width_x", 80.0),
                depth_y=params.get("depth_y", 60.0),
                thickness_z=params.get("thickness_z", 4.0),
                corner_radius=params.get("corner_radius", 0.0),
                edge_chamfer=params.get("edge_chamfer", 0.0)
            )
        else:
            part = IndustrialCADBuilder.build_mounting_plate(80.0, 60.0, 4.0)

        # 2. Iterate through secondary components
        for comp in plan.components[1:]:
            c_type = comp.component_type
            p = comp.parameters
            trans = tuple(comp.transform.translation_mm)

            if c_type == "iso_screw_hole":
                part = IndustrialCADBuilder.add_iso_fastener_hole(
                    base_part=part,
                    screw_type=p.get("screw_type", "socket_head"),
                    size=p.get("size", "M3-0.5"),
                    length=p.get("length", 12.0),
                    fit=p.get("fit", "Normal"),
                    position=trans
                )
            elif c_type == "heat_set_insert_pocket":
                part = IndustrialCADBuilder.add_heat_set_insert_pocket(
                    base_part=part,
                    size=p.get("size", "M3"),
                    position=trans
                )
            elif c_type == "ball_bearing_pocket":
                part = IndustrialCADBuilder.add_bearing_pocket(
                    base_part=part,
                    bearing_standard=p.get("bearing_standard", "608"),
                    press_fit_clearance_mm=p.get("press_fit_clearance_mm", 0.15),
                    position=trans
                )
            elif c_type == "nema_motor_mount":
                part = IndustrialCADBuilder.add_nema_motor_mount(
                    base_part=part,
                    nema_size=p.get("nema_size", 17),
                    position=trans
                )

        # Export STEP & STL
        return IndustrialCADBuilder.export_cad(part, output_dir, plan.part_name)
