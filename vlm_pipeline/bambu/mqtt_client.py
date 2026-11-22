"""MQTT Client for Bambu Lab telemetry and print dispatch."""

import json
import ssl
import time
from typing import Dict, Any, Optional, Callable
from vlm_pipeline.config import config


class BambuMQTTClient:
    """Communicates with Bambu Lab printer local MQTT broker (Port 8883, TLS)."""

    def __init__(
        self,
        ip: Optional[str] = None,
        serial: Optional[str] = None,
        access_code: Optional[str] = None
    ):
        self.ip = ip or config.bambu.ip
        self.serial = serial or config.bambu.serial
        self.access_code = access_code or config.bambu.access_code
        self.user = config.bambu.mqtt_user
        self.report_topic = f"device/{self.serial}/report"
        self.request_topic = f"device/{self.serial}/request"
        self.latest_status: Dict[str, Any] = {}

    def get_status(self, timeout_sec: int = 5) -> Dict[str, Any]:
        """Polls current printer status (temperatures, state, progress)."""
        try:
            import paho.mqtt.client as mqtt
        except ImportError:
            # Fallback simulated telemetry if paho-mqtt is not installed
            return {
                "gcode_state": "IDLE",
                "mc_percent": 0,
                "nozzle_temper": 25.0,
                "bed_temper": 24.0,
                "chamber_temper": 23.0,
                "online": False,
                "note": "paho-mqtt not installed; simulated telemetry"
            }

        status_received = False

        def on_connect(client, userdata, flags, rc):
            client.subscribe(self.report_topic)
            # Request push status update
            payload = {"pushing": {"command": "pushall", "version": 1, "sequence_id": "1"}}
            client.publish(self.request_topic, json.dumps(payload))

        def on_message(client, userdata, msg):
            nonlocal status_received
            try:
                data = json.loads(msg.payload.decode())
                if "print" in data:
                    self.latest_status = data["print"]
                    status_received = True
            except Exception:
                pass

        client = mqtt.Client(client_id=f"vlm_agent_{int(time.time())}")
        client.username_pw_set(self.user, self.access_code)

        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        client.tls_set_context(context)

        client.on_connect = on_connect
        client.on_message = on_message

        try:
            client.connect(self.ip, config.bambu.port_mqtt, keepalive=10)
            client.loop_start()

            start_t = time.time()
            while time.time() - start_t < timeout_sec and not status_received:
                time.sleep(0.1)

            client.loop_stop()
            client.disconnect()
            return self.latest_status
        except Exception as e:
            return {"error": str(e), "gcode_state": "OFFLINE"}

    def send_print_job(self, filename: str, plate_id: int = 1) -> bool:
        """Dispatches an already-uploaded 3MF project to print on the P1S."""
        try:
            import paho.mqtt.client as mqtt
        except ImportError:
            print("[BambuMQTT] paho-mqtt not installed. Print command simulated.")
            return True

        client = mqtt.Client(client_id=f"vlm_print_{int(time.time())}")
        client.username_pw_set(self.user, self.access_code)

        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        client.tls_set_context(context)

        payload = {
            "print": {
                "command": "project_file",
                "param": f"Metadata/plate_{plate_id}.gcode",
                "subtask_name": filename,
                "url": f"ftp://{filename}",
                "bed_type": "textured_plate",
                "timelapse": False,
                "bed_levelling": True,
                "flow_cali": True,
                "vibration_cali": True,
                "sequence_id": "2"
            }
        }

        try:
            client.connect(self.ip, config.bambu.port_mqtt, keepalive=10)
            client.loop_start()
            client.publish(self.request_topic, json.dumps(payload), qos=1)
            time.sleep(1)
            client.loop_stop()
            client.disconnect()
            return True
        except Exception as e:
            print(f"[BambuMQTT] Print dispatch failed: {e}")
            return False
