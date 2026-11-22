"""Interactive 3D Visualizer and Side-by-Side Comparison Dashboard."""

import base64
import http.server
import json
import os
import socketserver
import threading
import webbrowser
from pathlib import Path
from typing import Optional, Dict, Any


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>VLM 3D Print Visualizer & Inspection Studio</title>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/controls/OrbitControls.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/loaders/STLLoader.js"></script>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, monospace; }
        body { background: #0f1117; color: #e1e4ea; height: 100vh; display: flex; flex-direction: column; overflow: hidden; }
        header { background: #161922; padding: 12px 20px; border-bottom: 1px solid #282d3d; display: flex; justify-content: space-between; align-items: center; }
        header h1 { font-size: 16px; font-weight: 600; color: #4ade80; display: flex; align-items: center; gap: 8px; }
        header .badge { background: #1e293b; color: #94a3b8; font-size: 11px; padding: 3px 8px; border-radius: 4px; border: 1px solid #334155; }
        .main-container { display: flex; flex: 1; height: calc(100vh - 50px); }
        .pane-reference { width: 35%; background: #13161f; border-right: 1px solid #282d3d; display: flex; flex-direction: column; overflow: hidden; }
        .pane-header { padding: 10px 16px; font-size: 12px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; color: #94a3b8; background: #181b26; border-bottom: 1px solid #282d3d; display: flex; justify-content: space-between; }
        .reference-img-container { flex: 1; padding: 16px; display: flex; align-items: center; justify-content: center; background: #0b0d13; overflow: hidden; }
        .reference-img-container img { max-width: 100%; max-height: 100%; object-fit: contain; border-radius: 6px; box-shadow: 0 4px 12px rgba(0,0,0,0.5); }
        .spec-sidebar { height: 40%; background: #13161f; border-top: 1px solid #282d3d; overflow-y: auto; padding: 14px; font-size: 12px; }
        .spec-item { margin-bottom: 8px; display: flex; justify-content: space-between; border-bottom: 1px dashed #232736; padding-bottom: 4px; }
        .spec-item .label { color: #64748b; }
        .spec-item .value { color: #f1f5f9; font-weight: 500; }
        .pane-3d { flex: 1; position: relative; background: radial-gradient(circle at center, #1e2433 0%, #0d1017 100%); }
        #canvas3d { width: 100%; height: 100%; display: block; }
        .hud-overlay { position: absolute; top: 16px; left: 16px; background: rgba(22, 25, 34, 0.85); backdrop-filter: blur(8px); border: 1px solid #282d3d; border-radius: 6px; padding: 12px; font-size: 11px; z-index: 10; pointer-events: none; }
        .controls-toolbar { position: absolute; bottom: 20px; left: 50%; transform: translateX(-50%); background: rgba(22, 25, 34, 0.9); backdrop-filter: blur(8px); border: 1px solid #282d3d; border-radius: 30px; padding: 6px 14px; display: flex; gap: 8px; z-index: 10; }
        .btn-tool { background: #232838; border: 1px solid #384158; color: #cbd5e1; padding: 6px 12px; border-radius: 20px; font-size: 12px; cursor: pointer; transition: all 0.15s; }
        .btn-tool:hover { background: #333a4f; color: #fff; }
        .btn-tool.active { background: #22c55e; color: #000; font-weight: 600; border-color: #22c55e; }
        .legend { position: absolute; bottom: 20px; right: 20px; background: rgba(22, 25, 34, 0.85); padding: 10px; border-radius: 6px; border: 1px solid #282d3d; font-size: 11px; display: flex; flex-direction: column; gap: 4px; }
        .legend-row { display: flex; align-items: center; gap: 8px; }
        .legend-color { width: 12px; height: 12px; border-radius: 2px; }
    </style>
</head>
<body>
    <header>
        <h1><span>●</span> Bambu Lab P1S | VLM 3D Inspection Studio</h1>
        <div class="badge">Model: <span id="partNameDisplay">GeneratedPart</span></div>
    </header>

    <div class="main-container">
        <!-- LEFT: Target Reference & Assembly Spec -->
        <div class="pane-reference">
            <div class="pane-header">
                <span>Target Reference Image</span>
                <span id="imgDimensionsTag">2D Vision Input</span>
            </div>
            <div class="reference-img-container">
                <img id="refImage" src="{ref_image_b64}" alt="Reference Image">
            </div>
            <div class="pane-header">Assembly Plan & Physical Invariants</div>
            <div class="spec-sidebar" id="specContainer">
                <!-- Dynamically populated -->
            </div>
        </div>

        <!-- RIGHT: Interactive 3D WebGL Viewer -->
        <div class="pane-3d">
            <div class="hud-overlay" id="hudOverlay">
                <div><strong>Bambu P1S Envelope:</strong> 256 × 256 × 256 mm</div>
                <div style="margin-top: 4px;" id="bboxDims">Bounding Box: Calculating...</div>
                <div id="volumeDisplay">Volume: Calculating...</div>
            </div>

            <canvas id="canvas3d"></canvas>

            <div class="controls-toolbar">
                <button class="btn-tool active" id="btnShaded" onclick="setRenderMode('shaded')">Solid Shaded</button>
                <button class="btn-tool" id="btnWire" onclick="setRenderMode('wireframe')">Wireframe</button>
                <button class="btn-tool" id="btnOverhang" onclick="setRenderMode('overhang')">Overhang Heatmap</button>
                <button class="btn-tool" onclick="resetCamera()">Reset View</button>
            </div>

            <div class="legend" id="overhangLegend" style="display: none;">
                <div style="font-weight: 600; margin-bottom: 2px;">Overhang Risk Angle</div>
                <div class="legend-row"><div class="legend-color" style="background: #22c55e;"></div> &le; 45° (Self-supporting)</div>
                <div class="legend-row"><div class="legend-color" style="background: #eab308;"></div> 45° - 60° (Marginal)</div>
                <div class="legend-row"><div class="legend-color" style="background: #ef4444;"></div> &gt; 60° (Requires Support)</div>
            </div>
        </div>
    </div>

    <script>
        const stlBase64 = "{stl_b64}";
        const planData = {plan_json};

        // Populate spec sidebar
        const specDiv = document.getElementById("specContainer");
        if (planData) {
            document.getElementById("partNameDisplay").innerText = planData.part_name || "GeneratedPart";
            let html = `
                <div class="spec-item"><span class="label">Target Material:</span><span class="value">${planData.target_material || "PLA"}</span></div>
                <div class="spec-item"><span class="label">Components Count:</span><span class="value">${(planData.components || []).length}</span></div>
            `;
            (planData.components || []).forEach(c => {
                html += `
                    <div style="margin-top: 10px; font-weight: 600; color: #38bdf8;">[${c.operation}] ${c.instance_id} (${c.component_type})</div>
                `;
                for (const [k, v] of Object.entries(c.parameters || {})) {
                    html += `<div class="spec-item"><span class="label">&nbsp;&nbsp;${k}</span><span class="value">${v}</span></div>`;
                }
            });
            specDiv.innerHTML = html;
        }

        // --- THREE.JS SCENE SETUP ---
        const container = document.querySelector(".pane-3d");
        const canvas = document.getElementById("canvas3d");
        const scene = new THREE.Scene();

        const camera = new THREE.PerspectiveCamera(45, container.clientWidth / container.clientHeight, 0.1, 2000);
        camera.position.set(150, -180, 160);

        const renderer = new THREE.WebGLRenderer({ canvas: canvas, antialias: true, alpha: true });
        renderer.setSize(container.clientWidth, container.clientHeight);
        renderer.setPixelRatio(window.devicePixelRatio);
        renderer.shadowMap.enabled = true;

        const controls = new THREE.OrbitControls(camera, renderer.domElement);
        controls.enableDamping = true;
        controls.dampingFactor = 0.05;

        // Bambu Lab P1S Bed Grid (256 x 256 mm)
        const bedGrid = new THREE.GridHelper(256, 32, 0x4ade80, 0x334155);
        bedGrid.rotation.x = Math.PI / 2;
        scene.add(bedGrid);

        // Lighting
        const hemiLight = new THREE.HemisphereLight(0xffffff, 0x444455, 0.8);
        scene.add(hemiLight);

        const dirLight1 = new THREE.DirectionalLight(0xffffff, 0.9);
        dirLight1.position.set(150, 150, 250);
        scene.add(dirLight1);

        const dirLight2 = new THREE.DirectionalLight(0x94a3b8, 0.5);
        dirLight2.position.set(-150, -150, 100);
        scene.add(dirLight2);

        // Materials
        const shadedMat = new THREE.MeshStandardMaterial({
            color: 0x38bdf8,
            roughness: 0.35,
            metalness: 0.1,
            side: THREE.DoubleSide
        });

        const wireMat = new THREE.MeshBasicMaterial({
            color: 0x4ade80,
            wireframe: true
        });

        let loadedMesh = null;
        let overhangMesh = null;

        // Custom Overhang Shader Material
        const overhangShaderMat = new THREE.ShaderMaterial({
            vertexShader: `
                varying vec3 vNormal;
                void main() {
                    vNormal = normalize(normalMatrix * normal);
                    gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
                }
            `,
            fragmentShader: `
                varying vec3 vNormal;
                void main() {
                    // Angle with downward direction (0, 0, -1)
                    float dotDown = dot(vNormal, vec3(0.0, 0.0, -1.0));
                    // cos(45 deg) = 0.7071, cos(60 deg) = 0.5
                    if (dotDown > 0.7071) {
                        // Critical overhang > 45 deg
                        gl_FragColor = vec4(0.937, 0.267, 0.267, 1.0); // RED
                    } else if (dotDown > 0.5) {
                        gl_FragColor = vec4(0.917, 0.702, 0.031, 1.0); // YELLOW
                    } else {
                        gl_FragColor = vec4(0.133, 0.773, 0.369, 1.0); // GREEN
                    }
                }
            `,
            side: THREE.DoubleSide
        });

        // Load STL Data
        if (stlBase64) {
            const byteCharacters = atob(stlBase64);
            const byteNumbers = new Array(byteCharacters.length);
            for (let i = 0; i < byteCharacters.length; i++) {
                byteNumbers[i] = byteCharacters.charCodeAt(i);
            }
            const byteArray = new Uint8Array(byteNumbers);
            const loader = new THREE.STLLoader();
            const geometry = loader.parse(byteArray.buffer);

            geometry.computeBoundingBox();
            const bbox = geometry.boundingBox;
            const sizeX = (bbox.max.x - bbox.min.x).toFixed(1);
            const sizeY = (bbox.max.y - bbox.min.y).toFixed(1);
            const sizeZ = (bbox.max.z - bbox.min.z).toFixed(1);
            document.getElementById("bboxDims").innerText = `Bounding Box: ${sizeX} × ${sizeY} × ${sizeZ} mm`;

            loadedMesh = new THREE.Mesh(geometry, shadedMat);
            scene.add(loadedMesh);

            // Center on bed plate Z=0
            const center = new THREE.Vector3();
            bbox.getCenter(center);
            loadedMesh.position.x = -center.x;
            loadedMesh.position.y = -center.y;
            loadedMesh.position.z = -bbox.min.z; // Sit flat on build plate

            controls.target.set(0, 0, (bbox.max.z - bbox.min.z) / 2);
            controls.update();
        }

        // Render Mode Switcher
        function setRenderMode(mode) {
            document.querySelectorAll(".controls-toolbar .btn-tool").forEach(b => b.classList.remove("active"));
            const legend = document.getElementById("overhangLegend");

            if (!loadedMesh) return;

            if (mode === 'shaded') {
                document.getElementById("btnShaded").classList.add("active");
                loadedMesh.material = shadedMat;
                legend.style.display = "none";
            } else if (mode === 'wireframe') {
                document.getElementById("btnWire").classList.add("active");
                loadedMesh.material = wireMat;
                legend.style.display = "none";
            } else if (mode === 'overhang') {
                document.getElementById("btnOverhang").classList.add("active");
                loadedMesh.material = overhangShaderMat;
                legend.style.display = "flex";
            }
        }

        function resetCamera() {
            camera.position.set(150, -180, 160);
            controls.target.set(0, 0, 15);
            controls.update();
        }

        window.addEventListener('resize', () => {
            camera.aspect = container.clientWidth / container.clientHeight;
            camera.updateProjectionMatrix();
            renderer.setSize(container.clientWidth, container.clientHeight);
        });

        function animate() {
            requestAnimationFrame(animate);
            controls.update();
            renderer.render(scene, camera);
        }
        animate();
    </script>
</body>
</html>
"""


class InspectionVisualizer:
    """Generates the interactive inspection HTML and serves it locally."""

    @staticmethod
    def generate_html(
        stl_path: Path,
        ref_image_path: Optional[Path] = None,
        assembly_plan_path: Optional[Path] = None
    ) -> str:
        """Embeds assets into a single zero-dependency HTML studio."""
        # Read STL bytes as base64
        stl_b64 = ""
        if stl_path and stl_path.exists():
            with open(stl_path, "rb") as f:
                stl_b64 = base64.b64encode(f.read()).decode("utf-8")

        # Read Reference Image bytes as base64
        ref_b64 = ""
        if ref_image_path and ref_image_path.exists():
            with open(ref_image_path, "rb") as f:
                suffix = ref_image_path.suffix.lower()
                mime = "image/png" if suffix == ".png" else "image/jpeg"
                ref_b64 = f"data:{mime};base64," + base64.b64encode(f.read()).decode("utf-8")

        # Read Assembly Plan JSON
        plan_json_str = "null"
        if assembly_plan_path and assembly_plan_path.exists():
            with open(assembly_plan_path, "r") as f:
                plan_json_str = f.read()

        html = HTML_TEMPLATE.replace("{stl_b64}", stl_b64)
        html = html.replace("{ref_image_b64}", ref_b64)
        html = html.replace("{plan_json}", plan_json_str)
        return html

    @staticmethod
    def launch_local_viewer(output_dir: Path, port: int = 8765):
        """Builds viewer.html and spins up a local server to view in browser."""
        stl_path = output_dir / "mesh" / "model.stl"
        if not stl_path.exists():
            stl_path = output_dir / "model.stl"

        ref_img = None
        for ext in [".jpg", ".png", ".jpeg", ".webp"]:
            cand = output_dir / f"reference{ext}"
            if cand.exists():
                ref_img = cand
                break
        if not ref_img:
            # check parent directory for input image
            for f in output_dir.parent.glob("*.*"):
                if f.suffix.lower() in [".jpg", ".png", ".jpeg"]:
                    ref_img = f
                    break

        plan_path = output_dir / "assembly_plan.json"

        html_content = InspectionVisualizer.generate_html(
            stl_path=stl_path,
            ref_image_path=ref_img,
            assembly_plan_path=plan_path
        )

        viewer_file = output_dir / "viewer.html"
        with open(viewer_file, "w") as f:
            f.write(html_content)

        print(f"\n[Visualizer] Standalone HTML studio written to: {viewer_file}")

        # Start non-blocking server to view
        class SilentHandler(http.server.SimpleHTTPRequestHandler):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory=str(output_dir), **kwargs)
            def log_message(self, format, *args):
                pass  # suppress request logging

        try:
            server = socketserver.TCPServer(("127.0.0.1", port), SilentHandler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            url = f"http://127.0.0.1:{port}/viewer.html"
            print(f"[Visualizer] Interactive 3D Studio live at: {url}")
            webbrowser.open(url)
        except OSError:
            # Port already in use or headless; file:// works directly in any browser
            print(f"[Visualizer] Open file directly: file://{viewer_file}")
