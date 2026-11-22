"""Comprehensive Industrial Component Catalog powered by bd_warehouse and BOSL2.

Contains verified parametric standards for:
- ISO & ASME Fasteners (Clearance, Counterbore, Countersink, Nut traps)
- Heat-Set Inserts (Ruthex / CNC Kitchen standards)
- Ball Bearings (608 Skate, 624, 625, 688)
- Motion & Stepper Mounts (NEMA 14, NEMA 17, NEMA 23)
- Structural Brackets, Ribs, and Snap-Fit Joints
"""

from typing import Dict, Any, List
from pydantic import BaseModel, Field


class ParameterBound(BaseModel):
    name: str
    type: str  # float, int, str
    default: Any
    min_val: float = None
    max_val: float = None
    unit: str = "mm"
    description: str


class ComponentDefinition(BaseModel):
    component_type: str
    description: str
    category: str
    standard: str = "Custom"
    parameters: List[ParameterBound]
    boolean_compatible: List[str] = ["UNION", "DIFFERENCE", "INTERSECT"]


COMPONENT_CATALOG: Dict[str, ComponentDefinition] = {
    # -------------------------------------------------------------
    # 1. STRUCTURAL BASES & PLATES
    # -------------------------------------------------------------
    "mounting_plate": ComponentDefinition(
        component_type="mounting_plate",
        category="structural",
        standard="ISO / FDM Optimized",
        description="Planar mounting plate with rounded corners and bottom bed-release chamfer.",
        parameters=[
            ParameterBound(name="width_x", type="float", default=80.0, min_val=10.0, max_val=250.0, description="Width along X axis"),
            ParameterBound(name="depth_y", type="float", default=60.0, min_val=10.0, max_val=250.0, description="Depth along Y axis"),
            ParameterBound(name="thickness_z", type="float", default=4.0, min_val=1.2, max_val=50.0, description="Thickness (min 1.2mm for 3 perimeters)"),
            ParameterBound(name="corner_radius", type="float", default=3.0, min_val=0.0, max_val=25.0, description="Corner fillet radius"),
            ParameterBound(name="edge_chamfer", type="float", default=0.5, min_val=0.0, max_val=3.0, description="Bottom 45° chamfer for bed removal"),
        ]
    ),
    "reinforcement_rib": ComponentDefinition(
        component_type="reinforcement_rib",
        category="structural",
        standard="DFM Gusset",
        description="45-degree triangular gusset/rib to brace perpendicular faces against bending.",
        parameters=[
            ParameterBound(name="length", type="float", default=20.0, min_val=4.0, max_val=100.0, description="Length along horizontal face"),
            ParameterBound(name="height", type="float", default=20.0, min_val=4.0, max_val=100.0, description="Height along vertical face"),
            ParameterBound(name="thickness", type="float", default=2.4, min_val=1.2, max_val=20.0, description="Thickness of the rib"),
        ]
    ),

    # -------------------------------------------------------------
    # 2. INDUSTRIAL FASTENERS (bd_warehouse / ISO 4762)
    # -------------------------------------------------------------
    "iso_screw_hole": ComponentDefinition(
        component_type="iso_screw_hole",
        category="fasteners",
        standard="ISO 4762 / ASME B18.3",
        description="Standard ISO fastener clearance hole with counterbore pocket (bd_warehouse).",
        parameters=[
            ParameterBound(name="size", type="str", default="M3-0.5", description="Thread specification: 'M2-0.4', 'M2.5-0.45', 'M3-0.5', 'M4-0.7', 'M5-0.8'"),
            ParameterBound(name="screw_type", type="str", default="socket_head", description="'socket_head', 'button_head', or 'countersunk'"),
            ParameterBound(name="length", type="float", default=12.0, min_val=4.0, max_val=100.0, description="Nominal screw length"),
            ParameterBound(name="fit", type="str", default="Normal", description="Fit clearance: 'Close', 'Normal', or 'Loose'"),
        ]
    ),
    "heat_set_insert_pocket": ComponentDefinition(
        component_type="heat_set_insert_pocket",
        category="fasteners",
        standard="Ruthex / CNC Kitchen",
        description="Threaded brass heat-set insert cavity with 8-degree draft angle for thermal insertion.",
        parameters=[
            ParameterBound(name="size", type="str", default="M3", description="Insert size: 'M2', 'M2.5', 'M3', 'M4', 'M5'"),
        ]
    ),

    # -------------------------------------------------------------
    # 3. BEARINGS & ROTARY MOTION (bd_warehouse)
    # -------------------------------------------------------------
    "ball_bearing_pocket": ComponentDefinition(
        component_type="ball_bearing_pocket",
        category="motion",
        standard="ISO Deep Groove Bearing",
        description="Press-fit cavity for standard industrial ball bearings with through-shaft bore.",
        parameters=[
            ParameterBound(name="bearing_standard", type="str", default="608", description="Bearing size: '608' (Skate/Extruder), '624', '625' (V-Wheel), '688'"),
            ParameterBound(name="press_fit_clearance_mm", type="float", default=0.15, min_val=0.05, max_val=0.4, description="FDM tolerance offset for snug press-fit"),
        ]
    ),

    # -------------------------------------------------------------
    # 4. MOTOR MOUNTING (BOSL2 / NEMA Standard)
    # -------------------------------------------------------------
    "nema_motor_mount": ComponentDefinition(
        component_type="nema_motor_mount",
        category="motion",
        standard="NEMA ICS 16-2001",
        description="Standard stepper motor mount faceplate: center pilot bore + 4-bolt clearance pattern.",
        parameters=[
            ParameterBound(name="nema_size", type="int", default=17, min_val=14, max_val=23, description="NEMA frame size: 14, 17, or 23"),
        ]
    ),

    # -------------------------------------------------------------
    # 5. COMPLIANT SNAP-FIT JOINTS
    # -------------------------------------------------------------
    "cantilever_snap_fit": ComponentDefinition(
        component_type="cantilever_snap_fit",
        category="joints",
        standard="BOSL2 / Compliant FDM",
        description="Cantilever snap-fit arm with strain-limit protection (<1.5% strain for PLA/PETG).",
        parameters=[
            ParameterBound(name="arm_length", type="float", default=22.0, min_val=10.0, max_val=80.0, description="Length of flexible arm"),
            ParameterBound(name="arm_width", type="float", default=6.0, min_val=3.0, max_val=30.0, description="Width of arm"),
            ParameterBound(name="arm_thickness", type="float", default=1.6, min_val=1.2, max_val=4.0, description="Thickness (governs stiffness)"),
            ParameterBound(name="catch_depth", type="float", default=1.2, min_val=0.5, max_val=4.0, description="Hook engagement depth"),
        ]
    )
}
