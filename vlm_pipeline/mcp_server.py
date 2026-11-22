"""Model Context Protocol (MCP) Server for the VLM 3D Printing Pipeline."""

import json
from pathlib import Path
from typing import Dict, Any

from vlm_pipeline.pipeline import VLM3DPrintPipeline
from vlm_pipeline.vision.analyzer import VisualAnalyzer
from vlm_pipeline.engine.blender_headless import HeadlessBlenderRunner
from vlm_pipeline.engine.fallback_mesh_engine import FallbackMeshEngine
from vlm_pipeline.slicer.orca_slicer import HeadlessSlicer
from vlm_pipeline.bambu.controller import BambuPrinterController
from vlm_pipeline.config import config


def start_mcp_server():
    """Starts the FastMCP server over standard I/O."""
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError:
        print("Error: `mcp` library not installed. Install via `pip install mcp`.")
        return

    mcp = FastMCP("Bambu-VLM-Print-Pipeline")

    @mcp.tool()
    def run_image_to_print_pipeline(image_path: str, guidance: str = "", auto_print: bool = False) -> str:
        """Run the autonomous visual-to-print pipeline from an image to the Bambu P1S."""
        pipeline = VLM3DPrintPipeline()
        summary = pipeline.run(
            image_path=Path(image_path),
            user_guidance=guidance,
            auto_print=auto_print
        )
        return json.dumps(summary, indent=2)

    @mcp.tool()
    def audit_mesh_printability(stl_path: str) -> str:
        """Run DFM printability checks on an STL file (manifoldness, overhangs, volume)."""
        blender = HeadlessBlenderRunner()
        if blender.is_available():
            p = Path(stl_path)
            res = FallbackMeshEngine.audit_stl(p)
            return res.model_dump_json(indent=2)
        else:
            res = FallbackMeshEngine.audit_stl(Path(stl_path))
            return res.model_dump_json(indent=2)

    @mcp.tool()
    def slice_stl_for_bambu(stl_path: str, layer_height_mm: float = 0.20, tree_supports: bool = True) -> str:
        """Headlessly slice an STL file using OrcaSlicer/BambuStudio CLI."""
        slicer = HeadlessSlicer()
        res = slicer.slice_to_3mf(
            input_model_path=Path(stl_path),
            output_dir=Path("./output/sliced"),
            layer_height=layer_height_mm,
            enable_tree_supports=tree_supports
        )
        return res.model_dump_json(indent=2)

    @mcp.tool()
    def get_bambu_p1s_status() -> str:
        """Query live temperatures and print progress from the Bambu Lab P1S via LAN MQTT."""
        controller = BambuPrinterController()
        status = controller.get_status()
        return json.dumps(status, indent=2)

    @mcp.tool()
    def dispatch_print_to_bambu(file_3mf_path: str) -> str:
        """Upload and start printing a sliced 3MF file on the Bambu P1S."""
        controller = BambuPrinterController()
        result = controller.print_model(Path(file_3mf_path), auto_start=True)
        return json.dumps(result, indent=2)

    print("Starting Bambu-VLM-Print-Pipeline MCP Server on stdio...")
    mcp.run(transport="stdio")


if __name__ == "__main__":
    start_mcp_server()
