"""Multimodal VLM client supporting Anthropic, OpenAI, and local endpoints."""

import base64
import json
import os
from pathlib import Path
from typing import List, Dict, Any, Optional

from vlm_pipeline.config import config


class VLMClient:
    """Unified client for multimodal vision-language models."""

    def __init__(self, provider: Optional[str] = None, model: Optional[str] = None, api_key: Optional[str] = None):
        self.provider = provider or config.vlm_provider
        self.model = model or config.vlm_model
        self.api_key = api_key or config.vlm_api_key

    def _encode_image(self, image_path: Path) -> str:
        """Read and encode an image to base64."""
        with open(image_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")

    def _get_mime_type(self, image_path: Path) -> str:
        suffix = image_path.suffix.lower()
        if suffix in [".jpg", ".jpeg"]:
            return "image/jpeg"
        elif suffix == ".png":
            return "image/png"
        elif suffix == ".webp":
            return "image/webp"
        return "application/octet-stream"

    def complete_multimodal(
        self,
        prompt: str,
        image_paths: List[Path],
        system_prompt: Optional[str] = None,
        temperature: float = 0.2
    ) -> str:
        """Send a prompt with one or more images to the VLM."""
        api_key = self.api_key or os.getenv("ANTHROPIC_API_KEY") or os.getenv("OPENAI_API_KEY")
        if not api_key:
            # Deterministic offline demonstration fallback
            return self._offline_demo_response(prompt, image_paths)

        if self.provider == "anthropic":
            return self._call_anthropic(prompt, image_paths, system_prompt, temperature)
        elif self.provider == "openai":
            return self._call_openai(prompt, image_paths, system_prompt, temperature)
        else:
            raise ValueError(f"Unsupported VLM provider: {self.provider}")

    def _offline_demo_response(self, prompt: str, image_paths: List[Path]) -> str:
        """Deterministic slot-filler fallback for testing without cloud API keys."""
        print("[VLMClient] Note: No VLM API key configured in environment. Using deterministic offline slot-filler.")
        return json.dumps({
            "part_name": "stepper_adapter_plate",
            "description": "80x60mm mounting plate with center 608 bearing and 4x M3 screw clearance holes",
            "target_material": "PETG",
            "components": [
                {
                    "instance_id": "base_plate",
                    "component_type": "mounting_plate",
                    "operation": "BASE",
                    "parameters": {"width_x": 80.0, "depth_y": 60.0, "thickness_z": 5.0, "corner_radius": 3.0, "edge_chamfer": 0.5},
                    "transform": {"translation_mm": [0, 0, 0], "rotation_deg": [0, 0, 0]}
                },
                {
                    "instance_id": "center_bearing",
                    "component_type": "ball_bearing_pocket",
                    "operation": "DIFFERENCE",
                    "parameters": {"bearing_standard": "608", "press_fit_clearance_mm": 0.15},
                    "transform": {"translation_mm": [0, 0, 5.0], "rotation_deg": [0, 0, 0]}
                },
                {
                    "instance_id": "hole_tl",
                    "component_type": "iso_screw_hole",
                    "operation": "DIFFERENCE",
                    "parameters": {"size": "M3-0.5", "screw_type": "socket_head", "length": 12.0, "fit": "Normal"},
                    "transform": {"translation_mm": [-28.0, 18.0, 5.0], "rotation_deg": [0, 0, 0]}
                },
                {
                    "instance_id": "hole_tr",
                    "component_type": "iso_screw_hole",
                    "operation": "DIFFERENCE",
                    "parameters": {"size": "M3-0.5", "screw_type": "socket_head", "length": 12.0, "fit": "Normal"},
                    "transform": {"translation_mm": [28.0, 18.0, 5.0], "rotation_deg": [0, 0, 0]}
                },
                {
                    "instance_id": "hole_bl",
                    "component_type": "iso_screw_hole",
                    "operation": "DIFFERENCE",
                    "parameters": {"size": "M3-0.5", "screw_type": "socket_head", "length": 12.0, "fit": "Normal"},
                    "transform": {"translation_mm": [-28.0, -18.0, 5.0], "rotation_deg": [0, 0, 0]}
                },
                {
                    "instance_id": "hole_br",
                    "component_type": "iso_screw_hole",
                    "operation": "DIFFERENCE",
                    "parameters": {"size": "M3-0.5", "screw_type": "socket_head", "length": 12.0, "fit": "Normal"},
                    "transform": {"translation_mm": [28.0, -18.0, 5.0], "rotation_deg": [0, 0, 0]}
                }
            ]
        })

    def _call_anthropic(
        self, prompt: str, image_paths: List[Path], system_prompt: Optional[str], temperature: float
    ) -> str:
        import anthropic

        client = anthropic.Anthropic(api_key=self.api_key or os.getenv("ANTHROPIC_API_KEY"))
        content: List[Dict[str, Any]] = []

        for p in image_paths:
            content.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": self._get_mime_type(p),
                    "data": self._encode_image(p)
                }
            })

        content.append({"type": "text", "text": prompt})

        response = client.messages.create(
            model=self.model,
            max_tokens=4096,
            temperature=temperature,
            system=system_prompt or "You are an expert mechanical engineer and CAD specialist.",
            messages=[{"role": "user", "content": content}]
        )
        return response.content[0].text

    def _call_openai(
        self, prompt: str, image_paths: List[Path], system_prompt: Optional[str], temperature: float
    ) -> str:
        import openai

        client = openai.OpenAI(api_key=self.api_key or os.getenv("OPENAI_API_KEY"))
        content: List[Dict[str, Any]] = []

        for p in image_paths:
            b64_data = self._encode_image(p)
            mime = self._get_mime_type(p)
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:{mime};base64,{b64_data}"}
            })

        content.append({"type": "text", "text": prompt})

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": content})

        response = client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=4096
        )
        return response.choices[0].message.content or ""
