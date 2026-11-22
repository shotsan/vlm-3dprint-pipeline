"""Declarative Assembly Graph Schema.

The VLM only emits instances of this strictly-typed AST.
It never writes raw geometry or bmesh code directly.
"""

from typing import List, Dict, Any, Literal
from pydantic import BaseModel, Field, model_validator

from vlm_pipeline.library.catalog import COMPONENT_CATALOG


class Transform3D(BaseModel):
    """Spatial placement in millimeters and degrees."""
    translation_mm: List[float] = Field(
        default=[0.0, 0.0, 0.0],
        description="[x, y, z] position in millimeters"
    )
    rotation_deg: List[float] = Field(
        default=[0.0, 0.0, 0.0],
        description="[rx, ry, rz] Euler rotation in degrees"
    )


class ComponentInstance(BaseModel):
    """An instantiated building block in the assembly."""
    instance_id: str
    component_type: str
    operation: Literal["BASE", "UNION", "DIFFERENCE", "INTERSECT"] = "UNION"
    parameters: Dict[str, Any] = Field(default_factory=dict)
    transform: Transform3D = Field(default_factory=Transform3D)

    @model_validator(mode="after")
    def validate_against_catalog(self):
        comp_def = COMPONENT_CATALOG.get(self.component_type)
        if not comp_def:
            valid_types = list(COMPONENT_CATALOG.keys())
            raise ValueError(f"Unknown component_type '{self.component_type}'. Must be one of: {valid_types}")

        # Check parameter bounds
        for param in comp_def.parameters:
            val = self.parameters.get(param.name, param.default)
            if param.min_val is not None and val < param.min_val:
                raise ValueError(
                    f"Parameter '{param.name}' ({val}) below minimum allowed ({param.min_val} {param.unit})"
                )
            if param.max_val is not None and val > param.max_val:
                raise ValueError(
                    f"Parameter '{param.name}' ({val}) exceeds maximum allowed ({param.max_val} {param.unit})"
                )
            # Ensure filled
            self.parameters[param.name] = val

        return self


class AssemblyPlan(BaseModel):
    """Complete declarative assembly plan."""
    part_name: str
    description: str
    target_material: Literal["PLA", "PETG", "ABS", "ASA"] = "PLA"
    components: List[ComponentInstance] = Field(
        min_length=1,
        description="List of component building blocks to assemble"
    )

    @model_validator(mode="after")
    def validate_assembly(self):
        # Enforce that the first component is the BASE
        if self.components[0].operation != "BASE":
            self.components[0].operation = "BASE"

        # Bambu P1S Build Volume Check (256 x 256 x 256 mm)
        for comp in self.components:
            tx, ty, tz = comp.transform.translation_mm
            if abs(tx) > 128 or abs(ty) > 128 or tz < -5 or tz > 256:
                raise ValueError(
                    f"Component '{comp.instance_id}' position [{tx}, {ty}, {tz}] exceeds Bambu P1S bed envelope (256x256x256mm)"
                )
        return self
