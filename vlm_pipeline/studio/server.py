"""Interactive Fast-API Studio Server with Chat, Image Input, and Real-Time 3D Viewport."""

import base64
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import List, Dict, Any, Optional

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from pydantic import BaseModel

from vlm_pipeline.config import config
from vlm_pipeline.workflow.schema import AssemblyPlan
from vlm_pipeline.workflow.compiler import AssemblyCompiler
from vlm_pipeline.workflow.task_flow import DeterministicTaskFlow
from vlm_pipeline.engine.fallback_mesh_engine import FallbackMeshEngine
from vlm_pipeline.slicer.orca_slicer import HeadlessSlicer
from vlm_pipeline.bambu.controller import BambuPrinterController
from vlm_pipeline.vision.vlm_client import VLMClient


app = FastAPI(title="Bambu VLM 3D Studio")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SESSION_DIR = Path(tempfile.mkdtemp(prefix="vlm_studio_"))

class SessionState:
    image_path: Optional[Path] = None
    assembly_plan: Optional[AssemblyPlan] = None
    stl_path: Optional[Path] = None
    step_path: Optional[Path] = None
    sliced_3mf_path: Optional[Path] = None
    chat_history: List[Dict[str, Any]] = []
    telemetry: Dict[str, Any] = {}

state = SessionState()
vlm_client = VLMClient()
slicer = HeadlessSlicer()
bambu = BambuPrinterController()


class SettingsUpdate(BaseModel):
    provider: str  # "offline", "gemini", "anthropic", "openai"
    model: Optional[str] = None
    api_key: Optional[str] = None


@app.get("/api/settings")
async def get_settings():
    """Returns current active VLM / CAD engine status."""
    has_key = bool(
        vlm_client.api_key
        or os.getenv("GEMINI_API_KEY")
        or os.getenv("ANTHROPIC_API_KEY")
        or os.getenv("OPENAI_API_KEY")
    )
    return {
        "provider": vlm_client.provider or "offline",
        "model": vlm_client.model,
        "has_api_key": has_key,
        "available_providers": [
            {"id": "offline", "name": "Offline Deterministic CAD Engine (No API Key)", "models": ["parametric-rules-v1"]},
            {"id": "gemini", "name": "Google Gemini (Fast Multimodal)", "models": ["gemini-2.0-flash", "gemini-1.5-pro"]},
            {"id": "anthropic", "name": "Anthropic Claude (High Fidelity)", "models": ["claude-3-5-sonnet-20241022"]},
            {"id": "openai", "name": "OpenAI GPT-4o (Vision)", "models": ["gpt-4o", "gpt-4o-mini"]}
        ]
    }


@app.post("/api/settings")
async def update_settings(req: SettingsUpdate):
    """Updates active VLM provider, model, and API key at runtime."""
    vlm_client.provider = req.provider
    if req.model:
        vlm_client.model = req.model
    if req.api_key:
        vlm_client.api_key = req.api_key
        if req.provider == "gemini":
            os.environ["GEMINI_API_KEY"] = req.api_key
        elif req.provider == "anthropic":
            os.environ["ANTHROPIC_API_KEY"] = req.api_key
        elif req.provider == "openai":
            os.environ["OPENAI_API_KEY"] = req.api_key

    return {
        "status": "success",
        "provider": vlm_client.provider,
        "model": vlm_client.model,
        "configured": bool(vlm_client.api_key or req.provider == "offline")
    }


@app.post("/api/reset")
async def reset_session():
    """Resets session state so the user can generate a brand new CAD model."""
    state.assembly_plan = None
    state.image_path = None
    state.chat_history = []
    return {"status": "success", "message": "Session reset. Ready for new component design."}


ITERATION_SYSTEM_PROMPT = """You are a senior CAD systems engineer modifying an existing mechanical AssemblyPlan.
You receive the user's natural language request (and optional visual input) and the current AssemblyPlan JSON.

RULES:
1. Make surgical modifications to the component parameters or add/remove building blocks as requested.
2. Maintain all physical invariants: minimum wall thickness >= 1.2mm, ISO clearances, Bambu P1S envelope.
3. Return ONLY the complete updated AssemblyPlan JSON. No conversational text outside the JSON.
"""


@app.get("/", response_class=HTMLResponse)
async def get_studio_ui():
    """Serves the interactive 3D Web Studio HTML."""
    html_path = Path(__file__).parent / "studio.html"
    if html_path.exists():
        with open(html_path, "r") as f:
            return f.read()
    return "<h1>Studio UI template missing</h1>"


@app.post("/api/upload-image")
async def upload_image(file: UploadFile = File(...)):
    """Uploads and registers an image/sketch for multimodal reasoning."""
    ext = Path(file.filename).suffix or ".png"
    target = SESSION_DIR / f"input_image{ext}"
    with open(target, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    state.image_path = target
    return {
        "status": "success",
        "filename": file.filename,
        "path": str(target)
    }


class ChatRequest(BaseModel):
    message: str
    mode: str = "deterministic"  # "deterministic" or "generative"


@app.post("/api/chat")
async def chat_iterate(req: ChatRequest):
    """Processes multimodal chat prompt, updates CAD plan, compiles 3D geometry, and slices."""
    user_msg = req.message.strip()
    if not user_msg and not state.image_path:
        raise HTTPException(status_code=400, detail="Please provide a message or upload an image.")

    state.chat_history.append({"role": "user", "content": user_msg})

    # Check if using offline parametric engine or cloud VLM
    has_cloud_key = bool(
        vlm_client.api_key
        or os.getenv("GEMINI_API_KEY")
        or os.getenv("ANTHROPIC_API_KEY")
        or os.getenv("OPENAI_API_KEY")
    )
    is_offline = (vlm_client.provider == "offline") or not has_cloud_key

    from vlm_pipeline.workflow.parametric_interpreter import DeterministicParametricInterpreter

    if is_offline:
        # High-performance local deterministic parametric interpreter
        plan, assistant_reply = DeterministicParametricInterpreter.process_prompt(
            prompt=user_msg,
            current_plan=state.assembly_plan
        )
        state.assembly_plan = plan
    else:
        # Cloud Multimodal VLM (Gemini, Claude, GPT-4o)
        if state.assembly_plan is None:
            if not state.image_path:
                sample_img = SESSION_DIR / "sample.png"
                from PIL import Image
                Image.new("RGB", (400, 400), (240, 240, 240)).save(sample_img)
                state.image_path = sample_img

            flow = DeterministicTaskFlow(vlm_client=vlm_client)
            plan = flow.step1_extract_assembly_plan(state.image_path, user_guidance=user_msg)
            state.assembly_plan = plan
            assistant_reply = f"Generated mechanical assembly: **{plan.part_name}** ({len(plan.components)} components)."
        else:
            iteration_prompt = f"""Update the existing AssemblyPlan based on user request:
User Feedback: "{user_msg}"

Current AssemblyPlan:
{state.assembly_plan.model_dump_json(indent=2)}
"""
            img_paths = [state.image_path] if state.image_path and state.image_path.exists() else []
            raw_output = vlm_client.complete_multimodal(
                prompt=iteration_prompt,
                image_paths=img_paths,
                system_prompt=ITERATION_SYSTEM_PROMPT,
                temperature=0.0
            )

            import re
            cleaned = raw_output.strip()
            if "```json" in cleaned:
                cleaned = cleaned.split("```json")[1].split("```")[0].strip()
            elif "```" in cleaned:
                cleaned = cleaned.split("```")[1].split("```")[0].strip()
            match = re.search(r"\{[\s\S]*\}", cleaned)
            if match:
                plan_dict = json.loads(match.group(0))
                state.assembly_plan = AssemblyPlan(**plan_dict)
                assistant_reply = f"Applied iterative revisions to **{state.assembly_plan.part_name}**."
            else:
                assistant_reply = "Updated assembly parameters."

    # 2. Compile Updated Geometry via OpenCASCADE
    cad_outputs = AssemblyCompiler.compile_to_cad(state.assembly_plan, SESSION_DIR / "cad")
    state.stl_path = cad_outputs["stl"]
    state.step_path = cad_outputs["step"]

    # 3. Printability Audit
    audit = FallbackMeshEngine.audit_stl(state.stl_path)

    # 4. Slicing
    slice_res = slicer.slice_to_3mf(
        input_model_path=state.stl_path,
        output_dir=SESSION_DIR / "sliced",
        layer_height=config.print_quality.layer_height_mm,
        enable_tree_supports=config.print_quality.enable_tree_supports
    )
    state.sliced_3mf_path = Path(slice_res.output_3mf_path) if slice_res.output_3mf_path else None

    # Telemetry
    state.telemetry = {
        "part_name": state.assembly_plan.part_name,
        "is_watertight": audit.is_watertight,
        "non_manifold_edges": audit.non_manifold_edges,
        "overhang_faces": audit.overhang_faces_exceeding_threshold,
        "estimated_time_minutes": slice_res.estimated_time_minutes,
        "filament_used_grams": slice_res.filament_used_grams,
        "step_size_bytes": state.step_path.stat().st_size if state.step_path else 0,
        "stl_size_bytes": state.stl_path.stat().st_size if state.stl_path else 0,
    }

    state.chat_history.append({"role": "assistant", "content": assistant_reply})

    return {
        "status": "success",
        "reply": assistant_reply,
        "plan": state.assembly_plan.model_dump(),
        "telemetry": state.telemetry,
        "stl_url": "/api/model.stl"
    }


@app.get("/api/model.stl")
async def get_current_stl():
    """Serves the latest compiled STL binary to Three.js."""
    if not state.stl_path or not state.stl_path.exists():
        raise HTTPException(status_code=404, detail="No 3D model compiled yet.")
    return FileResponse(state.stl_path, media_type="application/sla", filename="model.stl")


@app.get("/api/model.step")
async def download_step():
    """Serves the true mathematical STEP B-Rep solid."""
    if not state.step_path or not state.step_path.exists():
        raise HTTPException(status_code=404, detail="No STEP file available.")
    return FileResponse(state.step_path, media_type="application/step", filename=f"{state.assembly_plan.part_name}.step")


@app.post("/api/print")
async def trigger_print():
    """Dispatches the sliced 3MF project over local LAN to the Bambu Lab P1S."""
    if not state.sliced_3mf_path or not state.sliced_3mf_path.exists():
        # Fallback to STL if 3MF not generated
        target = state.stl_path
    else:
        target = state.sliced_3mf_path

    if not target or not target.exists():
        raise HTTPException(status_code=400, detail="No model available to print.")

    res = bambu.print_model(target, auto_start=True)
    return res


@app.get("/api/printer-status")
async def get_printer_status():
    """Queries live telemetry from Bambu P1S."""
    return bambu.get_status()


def start_studio_server(port: int = 8000):
    """Launches the Uvicorn server and opens browser."""
    import uvicorn
    import webbrowser

    url = f"http://127.0.0.1:{port}"
    print(f"\n[Studio] Launching Interactive VLM 3D Studio at: {url}")
    threading_timer = threading = None
    import threading
    t = threading.Timer(1.5, lambda: webbrowser.open(url))
    t.daemon = True
    t.start()

    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
