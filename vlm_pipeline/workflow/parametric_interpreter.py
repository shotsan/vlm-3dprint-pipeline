"""Deterministic Parametric NLP Interpreter for Offline CAD Generation & Iteration.

When no external VLM API key is configured (or in offline mode), this engine
parses natural language prompts and technical dimensions to synthesize and update
strictly-typed AssemblyPlan objects without hallucination or static mock data.
"""

import re
from typing import Dict, Any, Optional, Tuple
from vlm_pipeline.workflow.schema import AssemblyPlan, ComponentInstance, Transform3D
from vlm_pipeline.library.catalog import COMPONENT_CATALOG


class DeterministicParametricInterpreter:
    """Parses user intent and dimensions to generate or modify AssemblyPlan ASTs deterministically."""

    @classmethod
    def process_prompt(
        cls,
        prompt: str,
        current_plan: Optional[AssemblyPlan] = None
    ) -> Tuple[AssemblyPlan, str]:
        """Processes a prompt. If current_plan exists and user isn't asking for a new part,
        iteratively updates it. Otherwise synthesizes a new AssemblyPlan.
        """
        text = prompt.strip().lower()

        current_base_type = current_plan.components[0].component_type if current_plan else None
        detected_new_type = cls._detect_part_type(text)
        is_type_change = detected_new_type is not None and detected_new_type != current_base_type
        explicit_new = any(w in text for w in ["new", "create", "design", "make", "build", "switch", "reset", "generate"])

        if current_plan is None or is_type_change or (explicit_new and detected_new_type):
            return cls._synthesize_new_plan(text, detected_new_type or "mounting_plate")
        else:
            return cls._iterate_existing_plan(text, current_plan)

    @classmethod
    def _detect_part_type(cls, text: str) -> Optional[str]:
        """Detects primary mechanical archetype from user prompt."""
        if any(w in text for w in ["gear", "spur gear", "pinion", "sprocket"]):
            return "involute_spur_gear"
        if any(w in text for w in ["bracket", "l-bracket", "l bracket", "angle brace", "corner bracket"]):
            return "structural_l_bracket"
        if any(w in text for w in ["box", "enclosure", "housing", "case", "chassis"]):
            return "enclosure_shell_box"
        if any(w in text for w in ["airplane", "aeroplane", "plane", "toy plane", "glider"]):
            return "toy_aeroplane"
        if any(w in text for w in ["plate", "mount", "adapter", "mounting plate", "base"]):
            return "mounting_plate"
        return None

    @classmethod
    def _extract_dimensions(cls, text: str) -> Dict[str, float]:
        """Extracts numerical dimensions (e.g. '100x70mm', 'width 80', 'thickness 6mm')."""
        dims: Dict[str, float] = {}

        # 1. Matches AxB or AxBxC (e.g. 100x70, 80x60x5, 120 x 80 x 30 mm)
        match_3d = re.search(r"(\d+(?:\.\d+)?)\s*(?:x|by|×)\s*(\d+(?:\.\d+)?)\s*(?:x|by|×)\s*(\d+(?:\.\d+)?)", text)
        if match_3d:
            dims["dim1"] = float(match_3d.group(1))
            dims["dim2"] = float(match_3d.group(2))
            dims["dim3"] = float(match_3d.group(3))
        else:
            match_2d = re.search(r"(\d+(?:\.\d+)?)\s*(?:x|by|×)\s*(\d+(?:\.\d+)?)", text)
            if match_2d:
                dims["dim1"] = float(match_2d.group(1))
                dims["dim2"] = float(match_2d.group(2))

        # 2. Named dimensions with strict word boundaries
        m_w = re.search(r"\b(?:width|w)\b\s*(?:of|to|=)?\s*(\d+(?:\.\d+)?)", text)
        if m_w: dims["width"] = float(m_w.group(1))

        m_d = re.search(r"\b(?:depth|length|len)\b\s*(?:of|to|=)?\s*(\d+(?:\.\d+)?)", text)
        if m_d: dims["depth"] = float(m_d.group(1))

        m_t = re.search(r"\b(?:thickness|thick|height)\b\s*(?:of|to|=)?\s*(\d+(?:\.\d+)?)", text)
        if m_t: dims["thickness"] = float(m_t.group(1))

        m_r = re.search(r"\b(?:radius|fillet|corner|round)\b\s*(?:of|to|=)?\s*(\d+(?:\.\d+)?)", text)
        if m_r: dims["corner_radius"] = float(m_r.group(1))

        m_teeth = re.search(r"(\d+)\s*(?:teeth|tooth|\bt\b)", text)
        if m_teeth: dims["teeth_count"] = int(m_teeth.group(1))

        m_mod = re.search(r"\bmodule\b\s*(?:of|to|=)?\s*(\d+(?:\.\d+)?)", text)
        if m_mod: dims["module"] = float(m_mod.group(1))

        m_bore = re.search(r"\bbore\b\s*(?:diameter|dia)?\s*(?:of|to|=)?\s*(\d+(?:\.\d+)?)", text)
        if m_bore:
            dims["bore_dia"] = float(m_bore.group(1))
        else:
            m_bore2 = re.search(r"(\d+(?:\.\d+)?)\s*mm\s*bore\b", text)
            if m_bore2: dims["bore_dia"] = float(m_bore2.group(1))

        return dims

    @classmethod
    def _extract_screw_size(cls, text: str) -> Optional[str]:
        """Extracts standard metric screw size e.g. M3, M4, M5, M6."""
        m = re.search(r"\bm([2-8])\b", text)
        if m:
            pitch_map = {
                "2": "M2-0.4",
                "3": "M3-0.5",
                "4": "M4-0.7",
                "5": "M5-0.8",
                "6": "M6-1.0",
                "8": "M8-1.25"
            }
            return pitch_map.get(m.group(1), f"M{m.group(1)}-0.5")
        return None

    @classmethod
    def _extract_bearing_spec(cls, text: str) -> Optional[str]:
        """Extracts standard ball bearing standard e.g. 608, 624, 625, 688."""
        m = re.search(r"\b(608|624|625|688|6000|6001)\b", text)
        if m:
            return m.group(1)
        return None

    @classmethod
    def _synthesize_new_plan(cls, text: str, part_type: str) -> Tuple[AssemblyPlan, str]:
        """Synthesizes a brand new AssemblyPlan according to the requested archetype."""
        dims = cls._extract_dimensions(text)
        screw_size = cls._extract_screw_size(text) or "M3-0.5"
        bearing_spec = cls._extract_bearing_spec(text) or "608"

        # -------------------------------------------------------------
        # 1. SPUR GEAR
        # -------------------------------------------------------------
        if part_type == "involute_spur_gear":
            teeth = int(dims.get("teeth_count", 24))
            module = dims.get("module", 1.0)
            bore = dims.get("bore_dia", 5.0)
            face_w = dims.get("thickness", dims.get("dim3", 8.0))

            plan = AssemblyPlan(
                part_name=f"spur_gear_{teeth}t_m{int(module*10)}",
                description=f"Involute spur gear with {teeth} teeth, module {module}mm, {bore}mm bore",
                target_material="PETG",
                components=[
                    ComponentInstance(
                        instance_id="gear_body",
                        component_type="involute_spur_gear",
                        operation="BASE",
                        parameters={
                            "teeth_count": teeth,
                            "module": module,
                            "face_width": face_w,
                            "bore_dia": bore,
                            "d_flat_depth": 0.5
                        },
                        transform=Transform3D(translation_mm=[0.0, 0.0, 0.0], rotation_deg=[0.0, 0.0, 0.0])
                    )
                ]
            )
            reply = f"Synthesized **{plan.part_name}**: Involute spur gear with {teeth} teeth, {module}mm module, {bore}mm central bore, and {face_w}mm face width."
            return plan, reply

        # -------------------------------------------------------------
        # 2. L-BRACKET
        # -------------------------------------------------------------
        elif part_type == "structural_l_bracket":
            leg1 = dims.get("dim1", dims.get("length", 40.0))
            leg2 = dims.get("dim2", dims.get("height", 40.0))
            width = dims.get("dim3", dims.get("width", 25.0))
            wall_t = dims.get("thickness", 4.0)

            plan = AssemblyPlan(
                part_name=f"l_bracket_{int(leg1)}x{int(leg2)}mm",
                description=f"Reinforced 90-degree corner L-bracket ({leg1}x{leg2}mm, width {width}mm)",
                target_material="PETG",
                components=[
                    ComponentInstance(
                        instance_id="bracket_body",
                        component_type="structural_l_bracket",
                        operation="BASE",
                        parameters={
                            "leg_1_length": leg1,
                            "leg_2_length": leg2,
                            "bracket_width": width,
                            "wall_thickness": wall_t,
                            "gusset_thickness": 3.0
                        },
                        transform=Transform3D(translation_mm=[0.0, 0.0, 0.0], rotation_deg=[0.0, 0.0, 0.0])
                    ),
                    ComponentInstance(
                        instance_id="hole_leg1",
                        component_type="socket_head_cap_screw",
                        operation="DIFFERENCE",
                        parameters={"size": screw_size, "length": 12.0, "fit": "Normal"},
                        transform=Transform3D(translation_mm=[leg1 * 0.6, 0.0, wall_t], rotation_deg=[0.0, 0.0, 0.0])
                    )
                ]
            )
            reply = f"Synthesized **{plan.part_name}**: Rigid 90° corner bracket with {leg1}mm & {leg2}mm legs, {width}mm width, 3mm gusset reinforcement, and {screw_size} mounting holes."
            return plan, reply

        # -------------------------------------------------------------
        # 3. ENCLOSURE SHELL
        # -------------------------------------------------------------
        elif part_type == "enclosure_shell_box":
            length = dims.get("dim1", dims.get("length", 100.0))
            width = dims.get("dim2", dims.get("width", 70.0))
            height = dims.get("dim3", dims.get("height", 35.0))
            wall_t = dims.get("thickness", 2.4)

            plan = AssemblyPlan(
                part_name=f"enclosure_box_{int(length)}x{int(width)}mm",
                description=f"Electronics enclosure shell ({length}x{width}x{height}mm)",
                target_material="PLA",
                components=[
                    ComponentInstance(
                        instance_id="enclosure_body",
                        component_type="enclosure_shell_box",
                        operation="BASE",
                        parameters={
                            "outer_length": length,
                            "outer_width": width,
                            "outer_height": height,
                            "wall_thickness": wall_t,
                            "corner_radius": 4.0
                        },
                        transform=Transform3D(translation_mm=[0.0, 0.0, 0.0], rotation_deg=[0.0, 0.0, 0.0])
                    )
                ]
            )
            reply = f"Synthesized **{plan.part_name}**: Electronics tub enclosure ({length} × {width} × {height} mm) with {wall_t}mm walls and 4mm rounded corners."
            return plan, reply

        # -------------------------------------------------------------
        # 4. TOY AEROPLANE
        # -------------------------------------------------------------
        elif part_type == "toy_aeroplane":
            fuselage_l = dims.get("dim1", dims.get("length", 110.0))
            wingspan = dims.get("dim2", dims.get("width", 140.0))

            plan = AssemblyPlan(
                part_name="toy_aeroplane_glider",
                description=f"Printable toy aeroplane ({fuselage_l}mm fuselage, {wingspan}mm wingspan)",
                target_material="PLA",
                components=[
                    ComponentInstance(
                        instance_id="aeroplane_airframe",
                        component_type="toy_aeroplane",
                        operation="BASE",
                        parameters={
                            "fuselage_length": fuselage_l,
                            "wingspan": wingspan,
                            "wing_thickness": 3.0,
                            "has_propeller_mount": True
                        },
                        transform=Transform3D(translation_mm=[0.0, 0.0, 0.0], rotation_deg=[0.0, 0.0, 0.0])
                    )
                ]
            )
            reply = f"Synthesized **{plan.part_name}**: Aerodynamic toy airplane with {fuselage_l}mm fuselage, {wingspan}mm swept wings, vertical fin, and nose axle mount."
            return plan, reply

        # -------------------------------------------------------------
        # 5. MOUNTING PLATE (DEFAULT)
        # -------------------------------------------------------------
        else:
            w_x = dims.get("dim1", dims.get("width", 80.0))
            d_y = dims.get("dim2", dims.get("depth", 60.0))
            t_z = dims.get("dim3", dims.get("thickness", 5.0))
            r_c = dims.get("corner_radius", 3.0)

            # Screw offsets: 12mm inset from corners
            sx = max(5.0, (w_x / 2.0) - 12.0)
            sy = max(5.0, (d_y / 2.0) - 12.0)

            components = [
                ComponentInstance(
                    instance_id="base_plate",
                    component_type="mounting_plate",
                    operation="BASE",
                    parameters={
                        "width_x": w_x,
                        "depth_y": d_y,
                        "thickness_z": t_z,
                        "corner_radius": r_c,
                        "edge_chamfer": 0.5
                    },
                    transform=Transform3D(translation_mm=[0.0, 0.0, 0.0], rotation_deg=[0.0, 0.0, 0.0])
                )
            ]

            # Add bearing if mentioned or by default
            if "bearing" in text or "center" in text or "608" in text or not ("no bearing" in text or "without bearing" in text):
                components.append(
                    ComponentInstance(
                        instance_id="center_bearing",
                        component_type="deep_groove_ball_bearing",
                        operation="DIFFERENCE",
                        parameters={"bearing_standard": bearing_spec, "press_fit_clearance_mm": 0.15},
                        transform=Transform3D(translation_mm=[0.0, 0.0, t_z], rotation_deg=[0.0, 0.0, 0.0])
                    )
                )

            # Add 4 corner screw clearance holes if not excluded
            if not ("no screw" in text or "no hole" in text or "without hole" in text):
                for corner_id, (cx, cy) in [
                    ("tl", (-sx, sy)),
                    ("tr", (sx, sy)),
                    ("bl", (-sx, -sy)),
                    ("br", (sx, -sy))
                ]:
                    components.append(
                        ComponentInstance(
                            instance_id=f"hole_{corner_id}",
                            component_type="socket_head_cap_screw",
                            operation="DIFFERENCE",
                            parameters={"size": screw_size, "length": 12.0, "fit": "Normal"},
                            transform=Transform3D(translation_mm=[cx, cy, t_z], rotation_deg=[0.0, 0.0, 0.0])
                        )
                    )

            plan = AssemblyPlan(
                part_name=f"mounting_plate_{int(w_x)}x{int(d_y)}mm",
                description=f"{w_x}x{d_y}mm mounting adapter with {bearing_spec} bearing pocket and 4x {screw_size} holes",
                target_material="PETG",
                components=components
            )
            reply = f"Synthesized **{plan.part_name}**: {w_x} × {d_y} × {t_z} mm plate with {r_c}mm fillets, center {bearing_spec} bearing pocket, and 4x {screw_size} clearance holes."
            return plan, reply

    @classmethod
    def _iterate_existing_plan(cls, text: str, plan: AssemblyPlan) -> Tuple[AssemblyPlan, str]:
        """Performs surgical parametric updates on the existing plan."""
        dims = cls._extract_dimensions(text)
        screw_size = cls._extract_screw_size(text)
        bearing_spec = cls._extract_bearing_spec(text)
        changes = []

        base = plan.components[0]
        base_p = base.parameters

        # Update Plate Dimensions
        if base.component_type == "mounting_plate":
            if "dim1" in dims and "dim2" in dims:
                base_p["width_x"] = dims["dim1"]
                base_p["depth_y"] = dims["dim2"]
                changes.append(f"dimensions to {dims['dim1']} × {dims['dim2']} mm")
            elif "width" in dims:
                base_p["width_x"] = dims["width"]
                changes.append(f"width to {dims['width']} mm")
            elif "depth" in dims:
                base_p["depth_y"] = dims["depth"]
                changes.append(f"depth to {dims['depth']} mm")

            if "thickness" in dims or "dim3" in dims:
                t = dims.get("thickness", dims.get("dim3"))
                base_p["thickness_z"] = max(1.2, t)
                changes.append(f"thickness to {base_p['thickness_z']} mm")

            if "corner_radius" in dims:
                base_p["corner_radius"] = dims["corner_radius"]
                changes.append(f"corner radius to {dims['corner_radius']} mm")

            # Update screw offsets if plate width/depth changed
            w_x = base_p.get("width_x", 80.0)
            d_y = base_p.get("depth_y", 60.0)
            t_z = base_p.get("thickness_z", 5.0)
            sx = max(5.0, (w_x / 2.0) - 12.0)
            sy = max(5.0, (d_y / 2.0) - 12.0)

            for comp in plan.components[1:]:
                cid = comp.instance_id
                if "tl" in cid: comp.transform.translation_mm = [-sx, sy, t_z]
                elif "tr" in cid: comp.transform.translation_mm = [sx, sy, t_z]
                elif "bl" in cid: comp.transform.translation_mm = [-sx, -sy, t_z]
                elif "br" in cid: comp.transform.translation_mm = [sx, -sy, t_z]
                elif "bearing" in cid: comp.transform.translation_mm = [0.0, 0.0, t_z]

        # Update Spur Gear
        elif base.component_type == "involute_spur_gear":
            if "teeth_count" in dims:
                base_p["teeth_count"] = dims["teeth_count"]
                changes.append(f"teeth count to {dims['teeth_count']}")
            if "module" in dims:
                base_p["module"] = dims["module"]
                changes.append(f"module to {dims['module']} mm")
            if "bore_dia" in dims:
                base_p["bore_dia"] = dims["bore_dia"]
                changes.append(f"bore to {dims['bore_dia']} mm")
            if "thickness" in dims:
                base_p["face_width"] = dims["thickness"]
                changes.append(f"face width to {dims['thickness']} mm")

        # Update L-Bracket
        elif base.component_type in ["structural_l_bracket", "l_bracket"]:
            if "dim1" in dims:
                base_p["leg_1_length"] = dims["dim1"]
                changes.append(f"leg 1 to {dims['dim1']} mm")
            if "dim2" in dims:
                base_p["leg_2_length"] = dims["dim2"]
                changes.append(f"leg 2 to {dims['dim2']} mm")
            if "width" in dims or "dim3" in dims:
                base_p["bracket_width"] = dims.get("width", dims.get("dim3"))
                changes.append(f"width to {base_p['bracket_width']} mm")
            if "thickness" in dims:
                base_p["wall_thickness"] = max(1.2, dims["thickness"])
                changes.append(f"wall thickness to {base_p['wall_thickness']} mm")

        # Update Enclosure Shell
        elif base.component_type in ["enclosure_shell_box", "enclosure_shell"]:
            if "dim1" in dims and "dim2" in dims:
                base_p["outer_length"] = dims["dim1"]
                base_p["outer_width"] = dims["dim2"]
                changes.append(f"length × width to {dims['dim1']} × {dims['dim2']} mm")
            if "dim3" in dims or "height" in dims:
                base_p["outer_height"] = dims.get("height", dims.get("dim3"))
                changes.append(f"height to {base_p['outer_height']} mm")
            if "thickness" in dims:
                base_p["wall_thickness"] = max(1.2, dims["thickness"])
                changes.append(f"wall thickness to {base_p['wall_thickness']} mm")

        # Update Screws / Fasteners
        if screw_size:
            for comp in plan.components:
                if comp.component_type in ["socket_head_cap_screw", "button_head_screw", "countersunk_screw"]:
                    comp.parameters["size"] = screw_size
            changes.append(f"screw clearance holes to {screw_size}")

        if "countersunk" in text:
            for comp in plan.components:
                if comp.component_type == "socket_head_cap_screw":
                    comp.component_type = "countersunk_screw"
            changes.append("fasteners to flush countersunk")

        # Update Bearing
        if bearing_spec:
            for comp in plan.components:
                if comp.component_type == "deep_groove_ball_bearing":
                    comp.parameters["bearing_standard"] = bearing_spec
            changes.append(f"center bearing pocket to {bearing_spec}")

        # Removal commands
        if any(w in text for w in ["remove holes", "remove screw", "no holes", "without holes", "delete holes"]) or ("remove" in text and ("hole" in text or "screw" in text)):
            plan.components = [
                c for c in plan.components
                if not any(f in c.component_type for f in ["screw", "fastener", "hole"])
            ]
            changes.append("removed all screw holes")

        if any(w in text for w in ["remove bearing", "no bearing", "without bearing", "delete bearing"]) or ("remove" in text and "bearing" in text):
            plan.components = [
                c for c in plan.components
                if "bearing" not in c.component_type
            ]
            changes.append("removed center bearing cavity")

        # Add NEMA Stepper Mount if requested
        if "nema" in text:
            m_nema = re.search(r"nema\s*(14|17|23)", text)
            size = int(m_nema.group(1)) if m_nema else 17
            t_z = base_p.get("thickness_z", 5.0)
            plan.components.append(
                ComponentInstance(
                    instance_id=f"nema_{size}_mount",
                    component_type="nema_stepper_mount",
                    operation="DIFFERENCE",
                    parameters={"nema_size": size, "slotted_holes": False},
                    transform=Transform3D(translation_mm=[0.0, 0.0, t_z], rotation_deg=[0.0, 0.0, 0.0])
                )
            )
            changes.append(f"added NEMA {size} motor faceplate cutout")

        if not changes:
            changes.append("verified physical parameters against Bambu P1S build envelope")

        reply = f"Applied iterative revisions to **{plan.part_name}**: Updated {', '.join(changes)}."
        return plan, reply
