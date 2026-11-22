"""High-level Bambu Lab printer controller orchestrating upload, print, and monitoring."""

from pathlib import Path
from typing import Dict, Any, Optional

from vlm_pipeline.bambu.ftps_uploader import BambuFTPSClient
from vlm_pipeline.bambu.mqtt_client import BambuMQTTClient
from vlm_pipeline.config import config


class BambuPrinterController:
    """End-to-end controller for Bambu Lab P1S/X1/A1 printers."""

    def __init__(
        self,
        ip: Optional[str] = None,
        serial: Optional[str] = None,
        access_code: Optional[str] = None
    ):
        self.ip = ip or config.bambu.ip
        self.serial = serial or config.bambu.serial
        self.access_code = access_code or config.bambu.access_code

        self.ftps = BambuFTPSClient(ip=self.ip, access_code=self.access_code)
        self.mqtt = BambuMQTTClient(ip=self.ip, serial=self.serial, access_code=self.access_code)

    def print_model(self, file_path: Path, auto_start: bool = True) -> Dict[str, Any]:
        """
        Uploads a sliced .gcode.3mf file over local FTPS and triggers
        the automated print job via local MQTT.
        """
        filename = file_path.name
        print(f"[Controller] Uploading {filename} to Bambu P1S at {self.ip}...")

        upload_ok = self.ftps.upload_file(file_path, remote_filename=filename)
        if not upload_ok:
            return {
                "success": False,
                "error": "Failed to upload file to printer via FTPS."
            }

        if auto_start:
            print(f"[Controller] Triggering print job for {filename}...")
            start_ok = self.mqtt.send_print_job(filename=filename)
            return {
                "success": start_ok,
                "filename": filename,
                "status": "PRINT_INITIATED" if start_ok else "DISPATCH_FAILED"
            }

        return {
            "success": True,
            "filename": filename,
            "status": "UPLOADED_READY_ON_SD"
        }

    def get_status(self) -> Dict[str, Any]:
        """Fetches live printer telemetry."""
        return self.mqtt.get_status()
