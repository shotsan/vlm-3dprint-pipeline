"""Command Line Interface for the VLM 3D Printing Pipeline."""

import argparse
import sys
from pathlib import Path

from vlm_pipeline.pipeline import VLM3DPrintPipeline
from vlm_pipeline.bambu.controller import BambuPrinterController
from vlm_pipeline.engine.fallback_mesh_engine import FallbackMeshEngine


def main():
    parser = argparse.ArgumentParser(
        description="Autonomous VLM-to-3D-Printing Pipeline for Bambu Lab P1S"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Command: run
    run_parser = subparsers.add_parser("run", help="Run the full image-to-print pipeline")
    run_parser.add_argument("image", type=str, help="Path to reference image or sketch")
    run_parser.add_argument("--guidance", type=str, default="", help="Caliper or dimensional guidance")
    run_parser.add_argument("--auto-print", action="store_true", help="Automatically dispatch print to P1S")
    run_parser.add_argument("--outdir", type=str, default=None, help="Custom output directory")
    run_parser.add_argument(
        "--mode", choices=["deterministic", "generative"], default="deterministic",
        help="Use 'deterministic' (recommended building-block library flow) or 'generative' (raw code)"
    )

    # Command: catalog
    subparsers.add_parser("catalog", help="List verified geometric building blocks and parameter bounds")

    # Command: status
    status_parser = subparsers.add_parser("status", help="Get Bambu P1S status over local LAN")

    # Command: view
    view_parser = subparsers.add_parser("view", help="Launch interactive 3D inspection studio in browser")
    view_parser.add_argument("path", type=str, help="Path to output directory or STL file")
    view_parser.add_argument("--port", type=int, default=8765, help="Local HTTP port")

    # Command: audit
    audit_parser = subparsers.add_parser("audit", help="Audit an existing STL mesh for 3D printability")
    audit_parser.add_argument("stl", type=str, help="Path to STL file")

    # Command: serve (MCP)
    serve_parser = subparsers.add_parser("serve", help="Run as an MCP (Model Context Protocol) server")

    args = parser.parse_args()

    if args.command == "run":
        img_path = Path(args.image).resolve()
        if not img_path.exists():
            print(f"Error: Image not found at {img_path}")
            sys.exit(1)

        out_dir = Path(args.outdir).resolve() if args.outdir else None

        if args.mode == "deterministic":
            from vlm_pipeline.workflow.task_flow import DeterministicTaskFlow
            flow = DeterministicTaskFlow()
            flow.run_flow(
                image_path=img_path,
                user_guidance=args.guidance,
                auto_print=args.auto_print,
                work_dir=out_dir
            )
        else:
            pipeline = VLM3DPrintPipeline()
            pipeline.run(
                image_path=img_path,
                user_guidance=args.guidance,
                auto_print=args.auto_print,
                work_dir=out_dir
            )

    elif args.command == "catalog":
        from vlm_pipeline.library.catalog import COMPONENT_CATALOG
        print("\n" + "=" * 65)
        print("  VERIFIED 3D PRINTING BUILDING BLOCK CATALOG")
        print("=" * 65)
        for name, comp in COMPONENT_CATALOG.items():
            print(f"\n📦 [{comp.category.upper()}] {name}")
            print(f"   Description: {comp.description}")
            print("   Parameters:")
            for p in comp.parameters:
                bounds = f"[{p.min_val} to {p.max_val} {p.unit}]" if p.min_val is not None else ""
                print(f"     - {p.name} ({p.type}): default={p.default} {bounds} -- {p.description}")
        print("\n" + "=" * 65 + "\n")

    elif args.command == "status":
        controller = BambuPrinterController()
        status = controller.get_status()
        print("\n[Bambu P1S Status]:")
        for k, v in status.items():
            print(f"  {k}: {v}")

    elif args.command == "view":
        from vlm_pipeline.visualizer.web_viewer import InspectionVisualizer
        target_path = Path(args.path).resolve()
        if target_path.is_file():
            target_dir = target_path.parent
        else:
            target_dir = target_path
        InspectionVisualizer.launch_local_viewer(target_dir, port=args.port)

    elif args.command == "audit":
        stl_path = Path(args.stl).resolve()
        if not stl_path.exists():
            print(f"Error: STL not found at {stl_path}")
            sys.exit(1)
        audit = FallbackMeshEngine.audit_stl(stl_path)
        print(audit.model_dump_json(indent=2))

    elif args.command == "serve":
        from vlm_pipeline.mcp_server import start_mcp_server
        start_mcp_server()


if __name__ == "__main__":
    main()
