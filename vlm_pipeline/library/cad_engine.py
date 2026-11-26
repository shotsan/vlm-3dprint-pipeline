"""Industrial CAD Engine utilizing build123d, bd_warehouse, and OpenCASCADE.

Constructs mathematically exact B-Rep solids (STEP) and watertight meshes (STL)
using battle-tested industrial fastener, bearing, gearing, and structural libraries.
"""

import math
from pathlib import Path
from typing import Dict, Any, List, Optional
import build123d as b3d
from bd_warehouse.fastener import (
    ClearanceHole,
    InsertHole,
    SocketHeadCapScrew,
    ButtonHeadScrew,
    CounterSunkScrew,
    HexHeadScrew,
    SetScrew,
    HexNut,
    SquareNut,
    HeatSetNut
)
from bd_warehouse.bearing import (
    SingleRowDeepGrooveBallBearing,
    SingleRowCappedDeepGrooveBallBearing,
    PressFitHole
)
from bd_warehouse.gear import SpurGear
from bd_warehouse.open_builds import VSlotLinearRail


class IndustrialCADBuilder:
    """Parametric B-Rep solid generator powered by OpenCASCADE and bd_warehouse."""

    # -------------------------------------------------------------------------
    # 1. STRUCTURAL BASES & PLATES
    # -------------------------------------------------------------------------
    @staticmethod
    def build_mounting_plate(
        width_x: float,
        depth_y: float,
        thickness_z: float,
        corner_radius: float = 0.0,
        edge_chamfer: float = 0.0
    ) -> b3d.Part:
        """Creates a rectangular mounting base with optional corner roundings and bottom chamfer."""
        with b3d.BuildPart() as part:
            with b3d.BuildSketch():
                if corner_radius > 0:
                    b3d.RectangleRounded(width_x, depth_y, radius=corner_radius)
                else:
                    b3d.Rectangle(width_x, depth_y)
            b3d.extrude(amount=thickness_z)

            # Optional 45-degree bed-release bottom chamfer
            if edge_chamfer > 0:
                bottom_edges = part.edges().filter_by(b3d.Axis.Z, reverse=True)
                if bottom_edges:
                    b3d.chamfer(bottom_edges, length=edge_chamfer)

        return part.part

    @staticmethod
    def build_l_bracket(
        leg_1_length: float = 30.0,
        leg_2_length: float = 30.0,
        bracket_width: float = 25.0,
        wall_thickness: float = 4.0,
        gusset_thickness: float = 3.0
    ) -> b3d.Part:
        """Constructs a rigid 90-degree corner L-bracket with a central reinforcement gusset."""
        with b3d.BuildPart() as p:
            # Leg 1 (horizontal base)
            with b3d.Locations((leg_1_length / 2.0, 0, wall_thickness / 2.0)):
                b3d.Box(leg_1_length, bracket_width, wall_thickness)
            # Leg 2 (vertical upright)
            with b3d.Locations((wall_thickness / 2.0, 0, leg_2_length / 2.0)):
                b3d.Box(wall_thickness, bracket_width, leg_2_length)
            # Central triangular reinforcement gusset
            if gusset_thickness > 0:
                with b3d.BuildSketch(b3d.Plane.XZ):
                    b3d.Polygon([
                        (wall_thickness, wall_thickness),
                        (leg_1_length * 0.85, wall_thickness),
                        (wall_thickness, leg_2_length * 0.85)
                    ])
                b3d.extrude(amount=gusset_thickness, both=True)

        return p.part

    @staticmethod
    def build_enclosure_shell(
        outer_length: float = 100.0,
        outer_width: float = 70.0,
        outer_height: float = 35.0,
        wall_thickness: float = 2.4,
        corner_radius: float = 4.0
    ) -> b3d.Part:
        """Constructs a hollow enclosure tub with uniform wall thickness and rounded corners."""
        with b3d.BuildPart() as p:
            with b3d.BuildSketch():
                b3d.RectangleRounded(outer_length, outer_width, radius=corner_radius)
            b3d.extrude(amount=outer_height)
            # Hollow out interior from top
            with b3d.BuildSketch(b3d.Plane.XY.offset(wall_thickness)):
                b3d.RectangleRounded(
                    outer_length - (2 * wall_thickness),
                    outer_width - (2 * wall_thickness),
                    radius=max(1.0, corner_radius - wall_thickness)
                )
            b3d.extrude(amount=outer_height, mode=b3d.Mode.SUBTRACT)

        return p.part

    @staticmethod
    def build_toy_aeroplane(
        fuselage_length: float = 110.0,
        wingspan: float = 140.0,
        wing_thickness: float = 3.0,
        has_propeller_mount: bool = True
    ) -> b3d.Part:
        """Constructs an aerodynamic, 100% 2-manifold printable toy airplane airframe."""
        half_span = wingspan / 2.0
        fuse_r = max(6.0, fuselage_length * 0.075)

        with b3d.BuildPart() as plane:
            # 1. Aerodynamic Fuselage
            with b3d.BuildSketch(b3d.Plane.YZ):
                b3d.Circle(radius=fuse_r)
            b3d.extrude(amount=fuselage_length)

            # 2. Swept Main Wings
            w_root = fuselage_length * 0.35
            w_tip = fuselage_length * 0.15
            with b3d.BuildSketch(b3d.Plane.XY.offset(0.0)):
                b3d.Polygon([
                    (fuselage_length * 0.30, -half_span),
                    (fuselage_length * 0.30 + w_tip, -half_span),
                    (fuselage_length * 0.30 + w_root, 0.0),
                    (fuselage_length * 0.30 + w_tip, half_span),
                    (fuselage_length * 0.30, half_span),
                    (fuselage_length * 0.25, 0.0)
                ])
            b3d.extrude(amount=wing_thickness)

            # 3. Horizontal Stabilizer (Rear)
            h_span = half_span * 0.4
            with b3d.BuildSketch(b3d.Plane.XY.offset(1.0)):
                b3d.Polygon([
                    (fuselage_length * 0.86, -h_span),
                    (fuselage_length * 0.94, -h_span),
                    (fuselage_length * 0.96, 0.0),
                    (fuselage_length * 0.94, h_span),
                    (fuselage_length * 0.86, h_span),
                    (fuselage_length * 0.84, 0.0)
                ])
            b3d.extrude(amount=max(2.0, wing_thickness * 0.8))

            # 4. Vertical Stabilizer Fin
            fin_h = fuse_r * 2.8
            with b3d.BuildSketch(b3d.Plane.XZ.offset(0.0)):
                b3d.Polygon([
                    (fuselage_length * 0.78, fuse_r * 0.5),
                    (fuselage_length * 0.96, fuse_r * 0.5),
                    (fuselage_length * 0.94, fin_h),
                    (fuselage_length * 0.84, fin_h)
                ])
            b3d.extrude(amount=max(2.0, wing_thickness * 0.8), both=True)

            # 5. Optional Propeller / Axle Nose Hole
            if has_propeller_mount:
                with b3d.BuildSketch(b3d.Plane.YZ):
                    b3d.Circle(radius=1.75)  # 3.5mm shaft clearance for M3 pin
                b3d.extrude(amount=15.0, mode=b3d.Mode.SUBTRACT)

        return plane.part

    # -------------------------------------------------------------------------
    # 2. INDUSTRIAL FASTENERS (ISO, ASME, Ruthex)
    # -------------------------------------------------------------------------
    @staticmethod
    def add_iso_fastener_hole(
        base_part: b3d.Part,
        screw_type: str = "socket_head",
        size: str = "M3-0.5",
        length: float = 12.0,
        fit: str = "Normal",
        position: tuple = (0.0, 0.0, 0.0)
    ) -> b3d.Part:
        """Subtracts standard ISO 4762/7380/10642 clearance hole with counterbore."""
        if screw_type == "countersunk":
            fastener = CounterSunkScrew(size=size, length=length)
            counter_sunk = True
        elif screw_type == "button_head":
            fastener = ButtonHeadScrew(size=size, length=length)
            counter_sunk = False
        elif screw_type == "hex_head":
            fastener = HexHeadScrew(size=size, length=length)
            counter_sunk = False
        else:
            fastener = SocketHeadCapScrew(size=size, length=length)
            counter_sunk = False

        with b3d.BuildPart() as p:
            b3d.add(base_part)
            with b3d.Locations(b3d.Location(position)):
                ClearanceHole(fastener=fastener, fit=fit, counter_sunk=counter_sunk)

        return p.part

    @staticmethod
    def add_heat_set_insert_pocket(
        base_part: b3d.Part,
        size: str = "M3",
        position: tuple = (0.0, 0.0, 0.0),
        depth_offset: float = 0.5
    ) -> b3d.Part:
        """Subtracts a standard Ruthex / CNC Kitchen heat-set brass insert pocket with 8° draft angle."""
        heat_set_dims = {
            "M2": {"top_dia": 3.4, "bot_dia": 3.1, "depth": 4.0},
            "M2.5": {"top_dia": 4.2, "bot_dia": 3.9, "depth": 5.7},
            "M3": {"top_dia": 4.2, "bot_dia": 3.9, "depth": 5.7},
            "M4": {"top_dia": 5.8, "bot_dia": 5.4, "depth": 8.1},
            "M5": {"top_dia": 7.0, "bot_dia": 6.6, "depth": 9.5},
            "M6": {"top_dia": 8.8, "bot_dia": 8.3, "depth": 12.7},
        }
        dims = heat_set_dims.get(size, heat_set_dims["M3"])

        with b3d.BuildPart() as p:
            b3d.add(base_part)
            with b3d.Locations(b3d.Location(position)):
                # Conical draft hole for clean heat staking
                b3d.Cone(
                    bottom_radius=dims["top_dia"] / 2.0,
                    top_radius=dims["bot_dia"] / 2.0,
                    height=dims["depth"] + depth_offset,
                    mode=b3d.Mode.SUBTRACT
                )

        return p.part

    @staticmethod
    def add_hex_nut_trap(
        base_part: b3d.Part,
        size: str = "M3",
        trap_type: str = "top",
        position: tuple = (0.0, 0.0, 0.0)
    ) -> b3d.Part:
        """Subtracts a captive hex nut pocket (DIN 934) for locking steel nuts into printed parts."""
        nut_dims = {
            "M2": {"width_across_flats": 4.0, "thickness": 1.6, "bolt_dia": 2.4},
            "M2.5": {"width_across_flats": 5.0, "thickness": 2.0, "bolt_dia": 2.9},
            "M3": {"width_across_flats": 5.5, "thickness": 2.4, "bolt_dia": 3.4},
            "M4": {"width_across_flats": 7.0, "thickness": 3.2, "bolt_dia": 4.5},
            "M5": {"width_across_flats": 8.0, "thickness": 4.0, "bolt_dia": 5.5},
            "M6": {"width_across_flats": 10.0, "thickness": 5.0, "bolt_dia": 6.6},
        }
        dims = nut_dims.get(size, nut_dims["M3"])
        flat_r = (dims["width_across_flats"] + 0.2) / (2.0 * math.cos(math.radians(30)))

        with b3d.BuildPart() as p:
            b3d.add(base_part)
            with b3d.Locations(b3d.Location(position)):
                # Bolt through-hole
                b3d.Cylinder(radius=dims["bolt_dia"] / 2.0, height=30.0, mode=b3d.Mode.SUBTRACT)
                # Hex socket
                with b3d.BuildSketch():
                    b3d.RegularPolygon(radius=flat_r, side_count=6)
                b3d.extrude(amount=dims["thickness"] + 0.3, mode=b3d.Mode.SUBTRACT)

        return p.part

    # -------------------------------------------------------------------------
    # 3. BEARINGS & ROTARY MOTION
    # -------------------------------------------------------------------------
    @staticmethod
    def add_bearing_pocket(
        base_part: b3d.Part,
        bearing_standard: str = "608",
        press_fit_clearance_mm: float = 0.15,
        shaft_clearance_mm: float = 1.0,
        position: tuple = (0.0, 0.0, 0.0)
    ) -> b3d.Part:
        """Subtracts a precision bearing cavity for standard radial bearings with through-shaft bore."""
        bearing_specs = {
            "608": {"od": 22.0, "width": 7.0, "id": 8.0},    # Standard skate/extruder
            "624": {"od": 13.0, "width": 5.0, "id": 4.0},
            "625": {"od": 16.0, "width": 5.0, "id": 5.0},    # V-wheel bearing
            "688": {"od": 16.0, "width": 5.0, "id": 8.0},
            "6000": {"od": 26.0, "width": 8.0, "id": 10.0},
            "6001": {"od": 28.0, "width": 8.0, "id": 12.0},
        }
        spec = bearing_specs.get(bearing_standard, bearing_specs["608"])
        bore_r = (spec["od"] + press_fit_clearance_mm) / 2.0
        depth = spec["width"] + 0.4

        with b3d.BuildPart() as p:
            b3d.add(base_part)
            with b3d.Locations(b3d.Location(position)):
                # Outer bearing pocket
                b3d.Cylinder(radius=bore_r, height=depth, mode=b3d.Mode.SUBTRACT)
                # Inner through-shaft clearance hole
                b3d.Cylinder(radius=(spec["id"] + shaft_clearance_mm) / 2.0, height=depth + 20.0, mode=b3d.Mode.SUBTRACT)

        return p.part

    # -------------------------------------------------------------------------
    # 4. MOTORS & POWER TRANSMISSION
    # -------------------------------------------------------------------------
    @staticmethod
    def add_nema_motor_mount(
        base_part: b3d.Part,
        nema_size: int = 17,
        slotted_holes: bool = False,
        slot_travel_mm: float = 6.0,
        position: tuple = (0.0, 0.0, 0.0)
    ) -> b3d.Part:
        """Cuts standard NEMA stepper motor pattern (NEMA 8, 11, 14, 17, 23, 34)."""
        nema_specs = {
            8: {"bolt_spacing": 16.0, "screw_size": "M2-0.4", "center_bore": 15.0},
            11: {"bolt_spacing": 23.0, "screw_size": "M2.5-0.45", "center_bore": 22.0},
            14: {"bolt_spacing": 26.0, "screw_size": "M3-0.5", "center_bore": 22.0},
            17: {"bolt_spacing": 31.0, "screw_size": "M3-0.5", "center_bore": 22.0},
            23: {"bolt_spacing": 47.1, "screw_size": "M5-0.8", "center_bore": 38.1},
            34: {"bolt_spacing": 69.6, "screw_size": "M6-1.0", "center_bore": 73.0},
        }
        spec = nema_specs.get(nema_size, nema_specs[17])
        half_s = spec["bolt_spacing"] / 2.0

        with b3d.BuildPart() as p:
            b3d.add(base_part)
            with b3d.Locations(b3d.Location(position)):
                # Center circular pilot bore
                b3d.Cylinder(radius=spec["center_bore"] / 2.0, height=25.0, mode=b3d.Mode.SUBTRACT)
                # 4-bolt clearance pattern
                bolt_coords = [
                    (-half_s, -half_s, 0),
                    (half_s, -half_s, 0),
                    (-half_s, half_s, 0),
                    (half_s, half_s, 0),
                ]
                for bx, by, bz in bolt_coords:
                    with b3d.Locations(b3d.Location((bx, by, bz))):
                        if slotted_holes:
                            with b3d.BuildSketch():
                                b3d.SlotOverall(slot_travel_mm + 3.4, 3.4)
                            b3d.extrude(amount=25.0, mode=b3d.Mode.SUBTRACT)
                        else:
                            ClearanceHole(fastener=SocketHeadCapScrew(size=spec["screw_size"], length=12))

        return p.part

    @staticmethod
    def build_involute_spur_gear(
        module: float = 1.0,
        teeth_count: int = 24,
        face_width: float = 8.0,
        bore_dia: float = 5.0,
        d_flat_depth: float = 0.5
    ) -> b3d.Part:
        """Constructs an exact mathematical involute spur gear with center shaft bore."""
        gear = SpurGear(
            module=module,
            tooth_count=teeth_count,
            pressure_angle=20.0,
            thickness=face_width
        )

        with b3d.BuildPart() as p:
            b3d.add(gear)
            # Subtract shaft bore
            if bore_dia > 0:
                with b3d.BuildSketch():
                    b3d.Circle(radius=bore_dia / 2.0)
                    if d_flat_depth > 0:
                        # D-shaft flat
                        b3d.Rectangle(bore_dia, d_flat_depth, mode=b3d.Mode.SUBTRACT)
                b3d.extrude(amount=face_width + 1.0, mode=b3d.Mode.SUBTRACT)

        return p.part

    # -------------------------------------------------------------------------
    # 5. DFM 3D PRINTING UTILITIES
    # -------------------------------------------------------------------------
    @staticmethod
    def add_teardrop_hole(
        base_part: b3d.Part,
        diameter: float = 8.0,
        length: float = 30.0,
        position: tuple = (0.0, 0.0, 0.0)
    ) -> b3d.Part:
        """
        Subtracts a horizontal hole with a 45-degree pointed teardrop top.
        Eliminates bridging droop and requires zero support structures!
        """
        r = diameter / 2.0
        with b3d.BuildPart() as p:
            b3d.add(base_part)
            with b3d.Locations(b3d.Location(position)):
                with b3d.BuildSketch(b3d.Plane.YZ):
                    # Lower half-circle + upper 45° triangle
                    b3d.Circle(radius=r)
                    b3d.Polygon([
                        (0, 0),
                        (r, 0),
                        (0, r * math.sqrt(2)),
                        (-r, 0)
                    ])
                b3d.extrude(amount=length, both=True, mode=b3d.Mode.SUBTRACT)

        return p.part

    # -------------------------------------------------------------------------
    # 6. EXPORT
    # -------------------------------------------------------------------------
    @staticmethod
    def export_cad(part: b3d.Part, output_dir: Path, base_name: str) -> Dict[str, Path]:
        """Exports mathematical B-Rep STEP and watertight STL."""
        output_dir.mkdir(parents=True, exist_ok=True)
        step_path = output_dir / f"{base_name}.step"
        stl_path = output_dir / f"{base_name}.stl"

        b3d.export_step(part, str(step_path))
        b3d.export_stl(part, str(stl_path), tolerance=0.001, angular_tolerance=0.1)

        return {"step": step_path, "stl": stl_path}
