"""Configuration management for the VLM-to-3D Printing Pipeline."""

import os
from pathlib import Path
from pydantic import BaseModel, Field


class BambuConfig(BaseModel):
    """Bambu Lab P1S/X1/A1 local LAN configuration."""
    ip: str = Field(default_factory=lambda: os.getenv("BAMBU_IP", "192.168.1.100"))
    serial: str = Field(default_factory=lambda: os.getenv("BAMBU_SERIAL", "01P00A000000000"))
    access_code: str = Field(default_factory=lambda: os.getenv("BAMBU_ACCESS_CODE", "12345678"))
    port_mqtt: int = Field(default=8883)
    port_ftps: int = Field(default=990)
    mqtt_user: str = "bblp"  # Standard Bambu Lab internal MQTT username


class PrintQualityConfig(BaseModel):
    """Additive manufacturing constraints (DFM) for Bambu Lab P1S."""
    nozzle_diameter_mm: float = 0.4
    layer_height_mm: float = 0.20
    first_layer_height_mm: float = 0.20
    infill_percentage: int = 15
    infill_pattern: str = "gyroid"
    max_unsupported_overhang_deg: float = 45.0  # Safe threshold before support required
    min_wall_thickness_mm: float = 1.2          # 3 perimeters on 0.4mm nozzle
    min_feature_size_mm: float = 0.8
    bed_temp_c: int = 55                        # Textured PEI plate PLA default
    nozzle_temp_c: int = 220                    # Standard PLA temp
    enable_tree_supports: bool = True


class PipelineConfig(BaseModel):
    """Global pipeline settings."""
    # LLM/VLM Provider: "openai", "anthropic", or "local"
    vlm_provider: str = Field(default_factory=lambda: os.getenv("VLM_PROVIDER", "anthropic"))
    vlm_model: str = Field(
        default_factory=lambda: os.getenv("VLM_MODEL", "claude-3-5-sonnet-20241022")
    )
    vlm_api_key: str = Field(
        default_factory=lambda: os.getenv("VLM_API_KEY", os.getenv("ANTHROPIC_API_KEY", os.getenv("OPENAI_API_KEY", "")))
    )

    # Tooling paths
    blender_bin: str = Field(
        default_factory=lambda: os.getenv("BLENDER_BIN", "blender")
    )
    slicer_bin: str = Field(
        default_factory=lambda: os.getenv("ORCA_SLICER_BIN", os.getenv("BAMBU_STUDIO_BIN", "orca-slicer"))
    )

    # Working Directories
    output_dir: Path = Field(
        default_factory=lambda: Path(os.getenv("OUTPUT_DIR", "./output")).resolve()
    )

    # Closed-loop visual diff settings
    max_critic_iterations: int = 3
    visual_similarity_threshold: float = 0.85

    # Sub-configurations
    bambu: BambuConfig = Field(default_factory=BambuConfig)
    print_quality: PrintQualityConfig = Field(default_factory=PrintQualityConfig)


# Global default instance
config = PipelineConfig()
