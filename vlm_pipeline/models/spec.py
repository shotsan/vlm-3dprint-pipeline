"""Data models and schemas for the VLM 3D Printing Pipeline."""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class BoundingBox3D(BaseModel):
    """Estimated bounding envelope in millimeters."""
    width_x_mm: float = Field(description="Width along X axis in mm")
    depth_y_mm: float = Field(description="Depth along Y axis in mm")
    height_z_mm: float = Field(description="Height along Z axis in mm")


class FeatureItem(BaseModel):
    """A distinct geometric feature identified by the VLM."""
    name: str = Field(description="Semantic name (e.g., 'base_plate', 'mounting_hole_array')")
    operation: str = Field(description="Extrude, Cut, Revolve, Fillet, Chamfer, Pattern")
    target_faces: Optional[str] = Field(default=None, description="Planar normal or location")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Dimensions, radii, counts")


class GeometricSpec(BaseModel):
    """Structured parametric specification extracted from image input."""
    part_name: str
    bounding_box: BoundingBox3D
    symmetry_planes: List[str] = Field(default_factory=list, description="e.g. ['XY', 'YZ']")
    features: List[FeatureItem] = Field(default_factory=list)
    critical_tolerances_mm: Dict[str, float] = Field(
        default_factory=dict,
        description="Fit tolerances for holes, slots, or mating interfaces"
    )
    suggested_print_orientation: str = Field(
        default="Z_UP",
        description="Best bed-contact face to maximize bed adhesion and minimize overhangs"
    )


class PrintabilityAuditResult(BaseModel):
    """Output from Blender's 3D-Print Toolbox or headless mesh audit."""
    is_watertight: bool
    non_manifold_edges: int = 0
    degenerate_faces: int = 0
    intersecting_faces: int = 0
    overhang_faces_exceeding_threshold: int = 0
    overhang_threshold_deg: float = 45.0
    thin_wall_faces: int = 0
    min_wall_threshold_mm: float = 1.2
    volume_cm3: float = 0.0
    surface_area_cm2: float = 0.0
    passes_audit: bool = False
    audit_notes: List[str] = Field(default_factory=list)


class CriticFeedback(BaseModel):
    """Feedback from the VLM comparing synthetic renders to the reference photo."""
    iteration: int
    alignment_score: float = Field(
        ge=0.0, le=1.0,
        description="1.0 is exact geometric and visual match"
    )
    discrepancies: List[str] = Field(
        default_factory=list,
        description="Concrete visual or dimensional discrepancies found"
    )
    code_modifications: List[str] = Field(
        default_factory=list,
        description="Surgical changes required in the bpy / bmesh script"
    )
    approved_for_slicing: bool = False


class SlicerResult(BaseModel):
    """Output telemetry from headless OrcaSlicer/BambuStudio execution."""
    success: bool
    gcode_path: Optional[str] = None
    output_3mf_path: Optional[str] = None
    estimated_time_minutes: float = 0.0
    filament_used_grams: float = 0.0
    layer_count: int = 0
    support_volume_cm3: float = 0.0
    raw_slicer_output: str = ""
