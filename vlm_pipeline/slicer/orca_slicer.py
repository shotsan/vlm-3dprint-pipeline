"""Headless Slicer interface targeting OrcaSlicer or Bambu Studio CLI.

Translates solid 3D geometries (STL/STEP) into machine-specific toolpaths
(.gcode.3mf) calibrated for the Bambu Lab P1S/X1/A1.
"""

import os
import re
import shutil
import subprocess
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional, Dict, Any, Tuple

from vlm_pipeline.models.spec import SlicerResult
from vlm_pipeline.config import config


PROFILES_DIR = Path(__file__).parent.parent / "resources" / "profiles"


class SlicerNotFoundError(RuntimeError):
    """Raised when no slicing engine binary (orca-slicer or bambu-studio) is found in PATH."""
    pass


class HeadlessSlicer:
    """Invokes OrcaSlicer or Bambu Studio headlessly to slice models for the P1S."""

    def __init__(self, slicer_bin: Optional[str] = None):
        self.slicer_bin = slicer_bin or self._find_slicer_binary()

    @classmethod
    def _find_slicer_binary(cls) -> str:
        """Locates available slicer binary in PATH or standard local bin locations."""
        custom = os.getenv("ORCA_SLICER_BIN") or os.getenv("BAMBU_STUDIO_BIN")
        if custom and shutil.which(custom):
            return custom

        candidates = [
            shutil.which("orca-slicer"),
            shutil.which("bambu-studio"),
            shutil.which("prusa-slicer"),
            str(Path.home() / ".local" / "bin" / "orca-slicer"),
            str(Path.home() / ".local" / "bin" / "bambu-studio")
        ]
        for c in candidates:
            if c and Path(c).is_file() and os.access(c, os.X_OK):
                return str(c)

        return config.slicer_bin or "orca-slicer"

    def is_available(self) -> bool:
        """Check if a real slicing CLI is installed and operational."""
        try:
            res = subprocess.run([self.slicer_bin, "--help"], capture_output=True, text=True, timeout=5)
            return res.returncode in [0, 1]
        except Exception:
            return False

    def slice_to_3mf(
        self,
        input_model_path: Path,
        output_dir: Path,
        filament_type: str = "PLA",
        layer_height: float = 0.20,
        enable_tree_supports: bool = True
    ) -> SlicerResult:
        """
        Runs headless slicing on the target STL using Bambu P1S profiles,
        producing a genuine sliced .gcode.3mf ready for execution.
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        output_3mf = output_dir / f"{input_model_path.stem}.gcode.3mf"

        if not self.is_available():
            error_msg = (
                f"Slicer CLI ('{self.slicer_bin}') is NOT installed or found in PATH.\n"
                "A 3D printer cannot print an un-sliced STL file directly.\n"
                "Please run 'vlm-print setup-slicer' to automatically download and configure OrcaSlicer, "
                "or set ORCA_SLICER_BIN to your local slicer binary."
            )
            return SlicerResult(
                success=False,
                output_3mf_path=None,
                estimated_time_minutes=0.0,
                filament_used_grams=0.0,
                layer_count=0,
                raw_slicer_output=error_msg
            )

        machine_profile = PROFILES_DIR / "machine" / "Bambu Lab P1S 0.4 nozzle.json"
        process_profile = PROFILES_DIR / "process" / "0.20mm Standard @BBL X1C.json"
        filament_profile = (
            PROFILES_DIR / "filament" / "Bambu PETG Basic @BBL X1C.json"
            if "petg" in filament_type.lower()
            else PROFILES_DIR / "filament" / "Bambu PLA Basic @BBL X1C.json"
        )

        load_settings = f"{machine_profile};{process_profile}"

        cmd = [
            self.slicer_bin,
            "--load-settings", load_settings,
            "--load-filaments", str(filament_profile),
            "--slice", "0",
            "--outputdir", str(output_dir),
            "--export-3mf", output_3mf.name,
            str(input_model_path.resolve())
        ]

        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            stdout = proc.stdout + proc.stderr

            if not output_3mf.exists():
                return SlicerResult(
                    success=False,
                    output_3mf_path=None,
                    estimated_time_minutes=0.0,
                    filament_used_grams=0.0,
                    raw_slicer_output=stdout
                )

            # Parse true metadata from generated 3MF archive
            time_min, grams = self._parse_slice_info_metadata(output_3mf)

            return SlicerResult(
                success=True,
                output_3mf_path=str(output_3mf),
                estimated_time_minutes=time_min,
                filament_used_grams=grams,
                raw_slicer_output=stdout
            )
        except Exception as e:
            return SlicerResult(
                success=False,
                output_3mf_path=None,
                estimated_time_minutes=0.0,
                filament_used_grams=0.0,
                raw_slicer_output=f"Headless slicing execution failed: {str(e)}"
            )

    @classmethod
    def _parse_slice_info_metadata(cls, archive_3mf: Path) -> Tuple[float, float]:
        """Extracts exact print time in minutes and filament in grams from Bambu 3MF metadata."""
        time_min = 0.0
        grams = 0.0
        try:
            with zipfile.ZipFile(archive_3mf, "r") as zf:
                if "Metadata/slice_info.config" in zf.namelist():
                    with zf.open("Metadata/slice_info.config") as f:
                        root = ET.fromstring(f.read())
                        pred = root.find('.//metadata[@key="prediction"]')
                        if pred is not None and pred.attrib.get("value"):
                            time_min = round(float(pred.attrib["value"]) / 60.0, 1)

                        fil = root.find(".//filament")
                        if fil is not None:
                            used_g = float(fil.attrib.get("used_g", 0.0))
                            used_m = float(fil.attrib.get("used_m", 0.0))
                            # 1.75mm PLA is ~3.0g/m, PETG ~3.1g/m
                            if used_g > 0:
                                grams = round(used_g, 1)
                            elif used_m > 0:
                                grams = round(used_m * 3.0, 1)
        except Exception:
            pass
        return time_min, grams
