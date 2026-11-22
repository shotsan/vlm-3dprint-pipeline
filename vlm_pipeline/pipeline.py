"""Master orchestration pipeline for VLM Image-to-Bambu 3D Printing."""

import json
from pathlib import Path
from typing import Dict, Any, Optional

from vlm_pipeline.config import config
from vlm_pipeline.vision.analyzer import VisualAnalyzer
from vlm_pipeline.vision.critic import VisualCritic
from vlm_pipeline.engine.blender_headless import HeadlessBlenderRunner
from vlm_pipeline.engine.fallback_mesh_engine import FallbackMeshEngine
from vlm_pipeline.slicer.orca_slicer import HeadlessSlicer
from vlm_pipeline.bambu.controller import BambuPrinterController


class VLM3DPrintPipeline:
    """
    End-to-end pipeline:
    Image -> VLM Vision Parsing -> BMesh Generation -> Headless Blender Audit
          -> Visual Diff Self-Refinement -> Headless Slicing -> Bambu P1S Dispatch.
    """

    def __init__(self):
        self.analyzer = VisualAnalyzer()
        self.critic = VisualCritic()
        self.blender = HeadlessBlenderRunner()
        self.slicer = HeadlessSlicer()
        self.bambu = BambuPrinterController()

    def run(
        self,
        image_path: Path,
        user_guidance: str = "",
        auto_print: bool = False,
        work_dir: Optional[Path] = None
    ) -> Dict[str, Any]:
        """Executes the complete generative manufacturing loop."""
        work_dir = work_dir or (config.output_dir / image_path.stem)
        work_dir.mkdir(parents=True, exist_ok=True)

        print("\n" + "=" * 60)
        print("  VLM-TO-3D PRINT PIPELINE: BAMBU LAB P1S")
        print("=" * 60)

        # -------------------------------------------------------------
        # STAGE 1: VISUAL DECOMPOSITION & INITIAL CODE GENERATION
        # -------------------------------------------------------------
        print(f"\n[Stage 1/5] Ingesting visual input: {image_path.name}")
        spec, current_code = self.analyzer.analyze_and_generate(
            image_path=image_path,
            user_guidance=user_guidance
        )
        print(f" -> Identified part: {spec.part_name}")
        print(f" -> Estimated Envelope: {spec.bounding_box.width_x_mm} x {spec.bounding_box.depth_y_mm} x {spec.bounding_box.height_z_mm} mm")
        print(f" -> Primary features: {[f.name for f in spec.features]}")

        # Save initial spec & code
        with open(work_dir / "spec.json", "w") as f:
            f.write(spec.model_dump_json(indent=2))
        with open(work_dir / "initial_script.py", "w") as f:
            f.write(current_code)

        # -------------------------------------------------------------
        # STAGE 2 & 3: HEADLESS BLENDER EXECUTION & CRITIC LOOP
        # -------------------------------------------------------------
        active_stl: Optional[Path] = None
        final_audit = None

        if self.blender.is_available():
            print("\n[Stage 2/5] Running Headless Blender with 3D-Print Toolbox...")
            for iteration in range(1, config.max_critic_iterations + 1):
                iter_dir = work_dir / f"iter_{iteration}"
                print(f" -> Iteration {iteration}/{config.max_critic_iterations} compilation & render pass...")

                audit_res, stl_file, renders = self.blender.execute_and_audit(
                    user_bpy_code=current_code,
                    output_dir=iter_dir
                )
                active_stl = stl_file
                final_audit = audit_res

                print(f"    * Watertight / Manifold: {audit_res.is_watertight}")
                print(f"    * Overhang faces (>45°): {audit_res.overhang_faces_exceeding_threshold}")
                print(f"    * Volume: {round(audit_res.volume_cm3, 2)} cm³")

                if audit_res.passes_audit and iteration >= 2:
                    print(" -> Physical audit passed and geometry stabilized.")
                    break

                # Run Visual Diff Critique
                print(" -> Running VLM Visual Diff Critic...")
                feedback, updated_code = self.critic.evaluate(
                    reference_image_path=image_path,
                    render_image_paths=renders,
                    audit_result=audit_res,
                    current_code=current_code,
                    iteration=iteration
                )

                print(f"    * Critic Alignment Score: {feedback.alignment_score:.2f}")
                if feedback.discrepancies:
                    print(f"    * Discrepancies noted: {feedback.discrepancies}")

                if feedback.approved_for_slicing or feedback.alignment_score >= config.visual_similarity_threshold:
                    print(" -> Visual Critic approved geometry for slicing.")
                    break

                current_code = updated_code
                with open(iter_dir / "refined_script.py", "w") as f:
                    f.write(current_code)
        else:
            print("\n[Stage 2/5] Blender binary not detected in PATH. Using simulated / fallback engine.")
            mock_stl = work_dir / "model.stl"
            # Write a placeholder STL if not present
            if not mock_stl.exists():
                with open(mock_stl, "w") as f:
                    f.write("solid part\nendsolid part\n")
            active_stl = mock_stl
            final_audit = FallbackMeshEngine.audit_stl(active_stl)

        # -------------------------------------------------------------
        # STAGE 4: HEADLESS SLICING (ORCASLICER / BAMBU STUDIO)
        # -------------------------------------------------------------
        print("\n[Stage 4/5] Slicing model for Bambu Lab P1S...")
        slice_result = self.slicer.slice_to_3mf(
            input_model_path=active_stl,
            output_dir=work_dir / "sliced",
            layer_height=config.print_quality.layer_height_mm,
            enable_tree_supports=config.print_quality.enable_tree_supports
        )

        print(f" -> Slice Successful: {slice_result.success}")
        print(f" -> Estimated Print Time: {slice_result.estimated_time_minutes:.1f} minutes")
        print(f" -> Filament Consumption: {slice_result.filament_used_grams:.1f} grams")

        # -------------------------------------------------------------
        # STAGE 5: PRINTER DISPATCH (LOCAL LAN FTPS + MQTT)
        # -------------------------------------------------------------
        dispatch_result = {"status": "SKIPPED_AUTO_PRINT_OFF"}
        if auto_print and slice_result.output_3mf_path:
            print("\n[Stage 5/5] Dispatching print job to Bambu P1S...")
            target_file = Path(slice_result.output_3mf_path)
            dispatch_result = self.bambu.print_model(
                file_path=target_file,
                auto_start=True
            )
            print(f" -> Dispatch Status: {dispatch_result.get('status')}")
        else:
            print("\n[Stage 5/5] Ready for print. (Auto-print disabled; file saved on disk).")

        summary = {
            "part_name": spec.part_name,
            "bounding_box": spec.bounding_box.model_dump(),
            "stl_path": str(active_stl) if active_stl else None,
            "sliced_3mf_path": slice_result.output_3mf_path,
            "estimated_time_minutes": slice_result.estimated_time_minutes,
            "filament_used_grams": slice_result.filament_used_grams,
            "printability_audit": final_audit.model_dump() if final_audit else None,
            "dispatch_result": dispatch_result
        }

        with open(work_dir / "pipeline_summary.json", "w") as f:
            json.dump(summary, f, indent=2)

        print("\n" + "=" * 60)
        print("  PIPELINE COMPLETE")
        print(f"  Artifacts saved in: {work_dir}")
        print("=" * 60 + "\n")

        return summary
