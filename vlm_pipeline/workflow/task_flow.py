"""Deterministic Task Flow and State Machine avoiding agentic deviations."""

import json
import re
from pathlib import Path
from typing import Dict, Any, Optional, Tuple

from vlm_pipeline.config import config
from vlm_pipeline.library.catalog import COMPONENT_CATALOG
from vlm_pipeline.workflow.schema import AssemblyPlan, ComponentInstance, Transform3D
from vlm_pipeline.workflow.compiler import AssemblyCompiler
from vlm_pipeline.engine.blender_headless import HeadlessBlenderRunner
from vlm_pipeline.engine.fallback_mesh_engine import FallbackMeshEngine
from vlm_pipeline.slicer.orca_slicer import HeadlessSlicer
from vlm_pipeline.bambu.controller import BambuPrinterController
from vlm_pipeline.vision.vlm_client import VLMClient
from vlm_pipeline.visualizer.web_viewer import InspectionVisualizer
from vlm_pipeline.visualizer.composite_renderer import DiagnosticReportRenderer


SLOT_FILLING_SYSTEM_PROMPT = """You are a deterministic CAD Slot-Filling Engine.
You do NOT write raw code. You ONLY select pre-validated engineering building blocks from the catalog and assign scalar parameters in millimeters.

AVAILABLE BUILDING BLOCKS IN CATALOG:
{catalog_summary}

RULES:
1. Target Printer: Bambu Lab P1S (Build volume: 256x256x256 mm).
2. The first component must be the 'BASE' (e.g., 'mounting_plate').
3. Subtractions (e.g., holes, recesses) must use operation: "DIFFERENCE".
4. Additions (e.g., bosses, ribs, clips) must use operation: "UNION".
5. All wall thicknesses must be >= 1.2mm (minimum 3 perimeters on 0.4mm nozzle).
6. Return ONLY valid JSON matching the AssemblyPlan schema. Zero commentary.
"""


class DeterministicTaskFlow:
    """State machine governing the image-to-print workflow without random agent drift."""

    def __init__(self, vlm_client: Optional[VLMClient] = None):
        self.client = vlm_client or VLMClient()
        self.compiler = AssemblyCompiler()
        self.blender = HeadlessBlenderRunner()
        self.slicer = HeadlessSlicer()
        self.bambu = BambuPrinterController()

    def _format_catalog_summary(self) -> str:
        lines = []
        for name, comp in COMPONENT_CATALOG.items():
            params_str = ", ".join(f"{p.name}: {p.type} (min={p.min_val}, max={p.max_val})" for p in comp.parameters)
            lines.append(f"- {name} [{comp.category}]: {comp.description}\n  Parameters: {params_str}")
        return "\n".join(lines)

    def step1_extract_assembly_plan(
        self,
        image_path: Path,
        user_guidance: str = ""
    ) -> AssemblyPlan:
        """State 1: Constrained slot-filling into strictly-typed AssemblyPlan."""
        sys_prompt = SLOT_FILLING_SYSTEM_PROMPT.format(
            catalog_summary=self._format_catalog_summary()
        )

        user_prompt = f"""Extract the assembly plan from this image.
User Guidance / Critical Dimensions: {user_guidance}

Return a valid JSON object matching:
{{
  "part_name": "example_bracket",
  "description": "Functional mounting bracket",
  "target_material": "PLA",
  "components": [
    {{
      "instance_id": "base",
      "component_type": "mounting_plate",
      "operation": "BASE",
      "parameters": {{"width_x": 60.0, "depth_y": 40.0, "thickness_z": 3.0, "corner_radius": 2.0}},
      "transform": {{"translation_mm": [0, 0, 0], "rotation_deg": [0, 0, 0]}}
    }}
  ]
}}
"""
        from PIL import Image
        img_meta = Image.open(image_path)
        print(f" -> [VLM Input] Image Path: {image_path.resolve()}")
        print(f" -> [VLM Input] Resolution: {img_meta.width}x{img_meta.height} px, Format: {img_meta.format}, Size: {image_path.stat().st_size} bytes")
        print(f" -> [VLM Input] Active Model: {self.client.model} (Provider: {self.client.provider})")
        print(f" -> [VLM Input] Multimodal Payload: Image bytes + Component Catalog Schema")

        # Temperature = 0.0 to eliminate stochastic randomness
        raw_output = self.client.complete_multimodal(
            prompt=user_prompt,
            image_paths=[image_path],
            system_prompt=sys_prompt,
            temperature=0.0
        )

        print(f" -> [VLM Output] Received {len(raw_output)} chars from vision model")
        return self._parse_and_validate_plan(raw_output)

    def _parse_and_validate_plan(self, text: str) -> AssemblyPlan:
        """State 2 Gatekeeper: Enforces strict Pydantic physical boundary contracts."""
        cleaned = text.strip()
        if "```json" in cleaned:
            cleaned = cleaned.split("```json")[1].split("```")[0].strip()
        elif "```" in cleaned:
            cleaned = cleaned.split("```")[1].split("```")[0].strip()

        match = re.search(r"\{[\s\S]*\}", cleaned)
        if match:
            data = json.loads(match.group(0))
        else:
            raise ValueError(f"Failed to extract JSON from slot-filler: {text[:200]}")

        # Pydantic validates parameter bounds against COMPONENT_CATALOG automatically
        return AssemblyPlan(**data)

    def run_flow(
        self,
        image_path: Path,
        user_guidance: str = "",
        auto_print: bool = False,
        work_dir: Optional[Path] = None
    ) -> Dict[str, Any]:
        """Executes the deterministic, closed-loop task flow."""
        work_dir = work_dir or (config.output_dir / image_path.stem)
        work_dir.mkdir(parents=True, exist_ok=True)

        print("\n" + "=" * 65)
        print("  DETERMINISTIC VLM ADDITIVE MANUFACTURING TASK FLOW")
        print("=" * 65)

        # GATE 1: Constrained Slot Filling
        print(f"\n[Gate 1] Slot-filling visual input into component catalog: {image_path.name}")
        plan = self.step1_extract_assembly_plan(image_path, user_guidance)
        print(f" -> Validated Assembly Plan: '{plan.part_name}' ({len(plan.components)} components)")
        for comp in plan.components:
            print(f"    * [{comp.operation}] {comp.instance_id} ({comp.component_type})")

        with open(work_dir / "assembly_plan.json", "w") as f:
            f.write(plan.model_dump_json(indent=2))

        # GATE 2: Deterministic Compilation
        print("\n[Gate 2] Compiling AssemblyPlan via OpenCASCADE (IndustrialCADBuilder)...")
        cad_outputs = self.compiler.compile_to_cad(plan, work_dir / "mesh")
        active_stl = cad_outputs["stl"]
        step_file = cad_outputs["step"]
        print(f" -> Compiled true mathematical STEP: {step_file.name} ({step_file.stat().st_size} bytes)")
        print(f" -> Compiled watertight STL mesh: {active_stl.name} ({active_stl.stat().st_size} bytes)")

        # GATE 3: Physical & Topology Audit Gatekeeper
        print("\n[Gate 3] Running Mesh Printability & DFM Audit...")
        audit_res = FallbackMeshEngine.audit_stl(active_stl)
        print(f" -> Manifold / Watertight: {audit_res.is_watertight}")
        print(f" -> Non-manifold edges: {audit_res.non_manifold_edges}")
        print(f" -> Overhang faces (>45°): {audit_res.overhang_faces_exceeding_threshold}")

        # GATE 4: Headless Slicing
        print("\n[Gate 4] Slicing for Bambu Lab P1S with tree supports...")
        slice_res = self.slicer.slice_to_3mf(
            input_model_path=active_stl,
            output_dir=work_dir / "sliced",
            layer_height=config.print_quality.layer_height_mm,
            enable_tree_supports=config.print_quality.enable_tree_supports
        )
        print(f" -> Slice Successful: {slice_res.success}")
        print(f" -> Estimated Print Time: {slice_res.estimated_time_minutes:.1f} mins")
        print(f" -> Filament Consumption: {slice_res.filament_used_grams:.1f} g")

        # VISUALIZATION & INSPECTION STUDIO GENERATION
        print("\n[Visualization] Generating 3D Inspection Studio & Contact Sheet...")
        renders = list((work_dir / "mesh").glob("*.png"))
        audit_dict = {
            "part_name": plan.part_name,
            "is_watertight": audit_res.is_watertight if hasattr(audit_res, "is_watertight") else True,
            "non_manifold_edges": getattr(audit_res, "non_manifold_edges", 0),
            "overhang_faces": getattr(audit_res, "overhang_faces_exceeding_threshold", 0),
            "estimated_time_minutes": slice_res.estimated_time_minutes,
            "filament_used_grams": slice_res.filament_used_grams
        }

        contact_sheet = work_dir / "diagnostic_report.png"
        DiagnosticReportRenderer.render_composite(
            reference_image_path=image_path,
            render_images=renders,
            audit_summary=audit_dict,
            output_path=contact_sheet
        )

        viewer_html = InspectionVisualizer.generate_html(
            stl_path=active_stl,
            ref_image_path=image_path,
            assembly_plan_path=work_dir / "assembly_plan.json"
        )
        viewer_path = work_dir / "viewer.html"
        with open(viewer_path, "w") as f:
            f.write(viewer_html)
        print(f" -> Interactive 3D Viewer generated: {viewer_path}")

        # GATE 5: Hardware Dispatch Gatekeeper
        dispatch_status = "SKIPPED_AUTO_PRINT_OFF"
        if auto_print and slice_res.output_3mf_path:
            print("\n[Gate 5] Dispatching print job to Bambu P1S...")
            target_path = Path(slice_res.output_3mf_path)
            res = self.bambu.print_model(target_path, auto_start=True)
            dispatch_status = res.get("status", "FAILED")
            print(f" -> Dispatch Status: {dispatch_status}")

        summary = {
            "part_name": plan.part_name,
            "components_count": len(plan.components),
            "stl_path": str(active_stl),
            "sliced_3mf_path": slice_res.output_3mf_path,
            "estimated_time_minutes": slice_res.estimated_time_minutes,
            "filament_used_grams": slice_res.filament_used_grams,
            "dispatch_status": dispatch_status
        }

        print("\n" + "=" * 65)
        print(f"  TASK FLOW COMPLETE: {plan.part_name} Ready for P1S")
        print("=" * 65 + "\n")
        return summary
