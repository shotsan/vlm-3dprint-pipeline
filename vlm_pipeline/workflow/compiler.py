"""Deterministic Compiler translating an AssemblyPlan into verified CAD geometry.

Supports the exhaustive mechanical library:
- Fasteners (ISO 4762 Socket Head, Button Head, Countersunk, Hex Head, Ruthex Heat-Set, Hex Nut Traps)
- Bearings (608, 624, 625, 688, 6000, 6001 series)
- Motors (NEMA 8, 11, 14, 17, 23, 34 with belt-tensioning slots)
- Gearing (Involute Spur, D-Shaft bores)
- Structural & Enclosures (Mounting plates, L-brackets, Enclosure tubs)
- DFM (Teardrop self-supporting holes, 45° chamfers)
"""

from pathlib import Path
from typing import Dict, Any
from vlm_pipeline.workflow.schema import AssemblyPlan


class AssemblyCompiler:
    """Compiles a declarative AssemblyPlan into deterministic CAD solids and scripts."""

    @staticmethod
    def compile_to_cad(plan: AssemblyPlan, output_dir: Path) -> Dict[str, Path]:
        """Directly compiles the AssemblyPlan using IndustrialCADBuilder."""
        from vlm_pipeline.library.cad_engine import IndustrialCADBuilder

        base_comp = plan.components[0]
        params = base_comp.parameters

        # 1. Build Base Component
        if base_comp.component_type == "mounting_plate":
            part = IndustrialCADBuilder.build_mounting_plate(
                width_x=params.get("width_x", 80.0),
                depth_y=params.get("depth_y", 60.0),
                thickness_z=params.get("thickness_z", 4.0),
                corner_radius=params.get("corner_radius", 0.0),
                edge_chamfer=params.get("edge_chamfer", 0.0)
            )
        elif base_comp.component_type == "structural_l_bracket":
            part = IndustrialCADBuilder.build_l_bracket(
                leg_1_length=params.get("leg_1_length", 30.0),
                leg_2_length=params.get("leg_2_length", 30.0),
                bracket_width=params.get("bracket_width", 25.0),
                wall_thickness=params.get("wall_thickness", 4.0),
                gusset_thickness=params.get("gusset_thickness", 3.0)
            )
        elif base_comp.component_type in ["enclosure_shell", "enclosure_shell_box"]:
            part = IndustrialCADBuilder.build_enclosure_shell(
                outer_length=params.get("outer_length", 100.0),
                outer_width=params.get("outer_width", 70.0),
                outer_height=params.get("outer_height", 35.0),
                wall_thickness=params.get("wall_thickness", 2.4),
                corner_radius=params.get("corner_radius", 4.0)
            )
        elif base_comp.component_type == "toy_aeroplane":
            part = IndustrialCADBuilder.build_toy_aeroplane(
                fuselage_length=params.get("fuselage_length", 110.0),
                wingspan=params.get("wingspan", 140.0),
                wing_thickness=params.get("wing_thickness", 3.0),
                has_propeller_mount=params.get("has_propeller_mount", True)
            )
        elif base_comp.component_type in ["involute_spur_gear", "spur_gear"]:
            part = IndustrialCADBuilder.build_involute_spur_gear(
                module=params.get("module", 1.0),
                teeth_count=params.get("teeth_count", 24),
                face_width=params.get("face_width", 8.0),
                bore_dia=params.get("bore_dia", 5.0),
                d_flat_depth=params.get("d_flat_depth", 0.5)
            )
        else:
            part = IndustrialCADBuilder.build_mounting_plate(
                width_x=params.get("width_x", 80.0),
                depth_y=params.get("depth_y", 60.0),
                thickness_z=params.get("thickness_z", 5.0),
                corner_radius=params.get("corner_radius", 3.0),
                edge_chamfer=params.get("edge_chamfer", 0.5)
            )

        # 2. Iterate through secondary components
        for comp in plan.components[1:]:
            c_type = comp.component_type
            p = comp.parameters
            trans = tuple(comp.transform.translation_mm)

            if c_type in ["socket_head_cap_screw", "button_head_screw", "countersunk_screw", "hex_head_screw", "iso_screw_hole"]:
                screw_t = p.get("screw_type", "socket_head")
                if c_type == "button_head_screw":
                    screw_t = "button_head"
                elif c_type == "countersunk_screw":
                    screw_t = "countersunk"
                elif c_type == "hex_head_screw":
                    screw_t = "hex_head"

                part = IndustrialCADBuilder.add_iso_fastener_hole(
                    base_part=part,
                    screw_type=screw_t,
                    size=p.get("size", "M3-0.5"),
                    length=p.get("length", 12.0),
                    fit=p.get("fit", "Normal"),
                    position=trans
                )
            elif c_type in ["heat_set_nut_insert", "heat_set_insert_pocket"]:
                part = IndustrialCADBuilder.add_heat_set_insert_pocket(
                    base_part=part,
                    size=p.get("size", "M3"),
                    position=trans,
                    depth_offset=p.get("depth_offset", 0.5)
                )
            elif c_type == "hex_nut_captive_trap":
                part = IndustrialCADBuilder.add_hex_nut_trap(
                    base_part=part,
                    size=p.get("size", "M3"),
                    trap_type=p.get("trap_type", "top"),
                    position=trans
                )
            elif c_type in ["deep_groove_ball_bearing", "ball_bearing_pocket"]:
                part = IndustrialCADBuilder.add_bearing_pocket(
                    base_part=part,
                    bearing_standard=p.get("bearing_standard", "608"),
                    press_fit_clearance_mm=p.get("press_fit_clearance_mm", 0.15),
                    shaft_clearance_mm=p.get("shaft_clearance_mm", 1.0),
                    position=trans
                )
            elif c_type in ["nema_stepper_mount", "nema_motor_mount"]:
                part = IndustrialCADBuilder.add_nema_motor_mount(
                    base_part=part,
                    nema_size=p.get("nema_size", 17),
                    slotted_holes=p.get("slotted_holes", False),
                    slot_travel_mm=p.get("slot_travel_mm", 6.0),
                    position=trans
                )
            elif c_type == "teardrop_horizontal_hole":
                part = IndustrialCADBuilder.add_teardrop_hole(
                    base_part=part,
                    diameter=p.get("diameter", 8.0),
                    length=p.get("length", 30.0),
                    position=trans
                )

        # Export STEP & STL
        return IndustrialCADBuilder.export_cad(part, output_dir, plan.part_name)
