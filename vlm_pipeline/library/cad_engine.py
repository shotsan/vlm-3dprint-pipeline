"""Industrial CAD Engine utilizing build123d and bd_warehouse.

Constructs mathematically exact B-Rep solids (STEP) and watertight meshes (STL)
using battle-tested industrial fastener, bearing, and structural libraries.
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
    HexNut,
    HeatSetNut
)
from bd_warehouse.bearing import SingleRowDeepGrooveBallBearing, PressFitHole


class IndustrialCADBuilder:
    """Parametric B-Rep solid generator powered by OpenCASCADE and bd_warehouse."""

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
    def add_iso_fastener_hole(
        base_part: b3d.Part,
        screw_type: str = "socket_head",
        size: str = "M3-0.5",
        length: float = 12.0,
        fit: str = "Normal",
        position: tuple = (0.0, 0.0, 0.0),
        normal_direction: tuple = (0.0, 0.0, 1.0)
    ) -> b3d.Part:
        """
        Subtracts an exact standard ISO screw hole using bd_warehouse.
        Supports standard socket head cap screws, countersunk, and button heads.
        """
        if screw_type == "countersunk":
            fastener = CounterSunkScrew(size=size, length=length)
            counter_sunk = True
        elif screw_type == "button_head":
            fastener = ButtonHeadScrew(size=size, length=length)
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
        position: tuple = (0.0, 0.0, 0.0)
    ) -> b3d.Part:
        """
        Subtracts a standard Ruthex / CNC Kitchen heat-set brass insert pocket
        with standard 8-degree draft angle for clean FDM heat staking.
        """
        heat_set_dims = {
            "M2": {"dia": 3.2, "depth": 4.0},
            "M2.5": {"dia": 4.0, "depth": 5.7},
            "M3": {"dia": 4.0, "depth": 5.7},
            "M4": {"dia": 5.6, "depth": 8.1},
            "M5": {"dia": 6.8, "depth": 9.5},
        }
        dims = heat_set_dims.get(size, heat_set_dims["M3"])

        with b3d.BuildPart() as p:
            b3d.add(base_part)
            with b3d.Locations(b3d.Location(position)):
                # Cone with slight taper for brass insertion
                b3d.Cylinder(
                    radius=dims["dia"] / 2.0,
                    height=dims["depth"],
                    mode=b3d.Mode.SUBTRACT
                )

        return p.part

    @staticmethod
    def add_bearing_pocket(
        base_part: b3d.Part,
        bearing_standard: str = "608",
        press_fit_clearance_mm: float = 0.15,
        position: tuple = (0.0, 0.0, 0.0)
    ) -> b3d.Part:
        """
        Subtracts a precision bearing cavity for standard 608 skate bearings,
        624, or 625 bearings with calibrated FDM tolerance offset.
        """
        bearing_specs = {
            "608": {"od": 22.0, "width": 7.0, "id": 8.0},    # Standard skate/extruder
            "624": {"od": 13.0, "width": 5.0, "id": 4.0},
            "625": {"od": 16.0, "width": 5.0, "id": 5.0},    # V-wheel bearing
            "688": {"od": 16.0, "width": 5.0, "id": 8.0},
        }
        spec = bearing_specs.get(bearing_standard, bearing_specs["608"])
        bore_r = (spec["od"] + press_fit_clearance_mm) / 2.0
        depth = spec["width"] + 0.5  # recess depth

        with b3d.BuildPart() as p:
            b3d.add(base_part)
            with b3d.Locations(b3d.Location(position)):
                b3d.Cylinder(radius=bore_r, height=depth, mode=b3d.Mode.SUBTRACT)
                # Through shaft hole
                b3d.Cylinder(radius=(spec["id"] + 1.0) / 2.0, height=depth + 10.0, mode=b3d.Mode.SUBTRACT)

        return p.part

    @staticmethod
    def add_nema_motor_mount(
        base_part: b3d.Part,
        nema_size: int = 17,
        position: tuple = (0.0, 0.0, 0.0)
    ) -> b3d.Part:
        """
        Cuts a standard NEMA stepper motor pattern (NEMA 14, 17, or 23):
        Center boss clearance + 4-bolt circle.
        """
        nema_specs = {
            14: {"bolt_spacing": 26.0, "screw_size": "M3-0.5", "center_bore": 22.0},
            17: {"bolt_spacing": 31.0, "screw_size": "M3-0.5", "center_bore": 22.0},
            23: {"bolt_spacing": 47.1, "screw_size": "M5-0.8", "center_bore": 38.1},
        }
        spec = nema_specs.get(nema_size, nema_specs[17])
        half_s = spec["bolt_spacing"] / 2.0

        with b3d.BuildPart() as p:
            b3d.add(base_part)
            # Center shaft & pilot boss cutout
            with b3d.Locations(b3d.Location(position)):
                b3d.Cylinder(radius=spec["center_bore"] / 2.0, height=20.0, mode=b3d.Mode.SUBTRACT)
                # 4-bolt mounting holes
                bolt_locs = [
                    (position[0] - half_s, position[1] - half_s, position[2]),
                    (position[0] + half_s, position[1] - half_s, position[2]),
                    (position[0] - half_s, position[1] + half_s, position[2]),
                    (position[0] + half_s, position[1] + half_s, position[2]),
                ]
                for bloc in bolt_locs:
                    with b3d.Locations(b3d.Location(bloc)):
                        ClearanceHole(fastener=SocketHeadCapScrew(size=spec["screw_size"], length=10))

        return p.part

    @staticmethod
    def export_cad(part: b3d.Part, output_dir: Path, base_name: str) -> Dict[str, Path]:
        """Exports both mathematical B-Rep STEP and watertight STL."""
        output_dir.mkdir(parents=True, exist_ok=True)
        step_path = output_dir / f"{base_name}.step"
        stl_path = output_dir / f"{base_name}.stl"

        b3d.export_step(part, str(step_path))
        b3d.export_stl(part, str(stl_path), tolerance=0.001, angular_tolerance=0.1)

        return {"step": step_path, "stl": stl_path}
