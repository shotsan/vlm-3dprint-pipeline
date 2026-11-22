"""FTPS uploader for Bambu Lab P1S/X1/A1 printers in local LAN mode."""

import ftplib
import ssl
from pathlib import Path
from vlm_pipeline.config import config


class ImplicitFTP_TLS(ftplib.FTP_TLS):
    """Subclass of FTP_TLS to enforce implicit SSL on port 990 for Bambu printers."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._sock = None

    def connect(self, host="", port=990, timeout=30):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.sock = socket = self.context.wrap_socket(
            self.create_connection((self.host, self.port), timeout=self.timeout),
            server_hostname=self.host
        )
        self.af = socket.family
        self.file = socket.makefile('r', encoding=self.encoding)
        self.welcome = self.getresp()
        return self.welcome


class BambuFTPSClient:
    """Uploads print files directly to Bambu Lab MicroSD card storage."""

    def __init__(self, ip: str = None, access_code: str = None, port: int = 990):
        self.ip = ip or config.bambu.ip
        self.access_code = access_code or config.bambu.access_code
        self.port = port
        self.user = config.bambu.mqtt_user

    def upload_file(self, local_path: Path, remote_filename: str = None) -> bool:
        """Uploads a .gcode.3mf file to the printer's SD card root."""
        if not remote_filename:
            remote_filename = local_path.name

        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE

        try:
            ftps = ImplicitFTP_TLS(context=context)
            ftps.connect(host=self.ip, port=self.port, timeout=15)
            ftps.login(user=self.user, passwd=self.access_code)
            ftps.prot_p()  # Enforce data protection (PBSZ 0, PROT P)

            with open(local_path, "rb") as f:
                ftps.storbinary(f"STOR {remote_filename}", f)

            ftps.quit()
            return True
        except Exception as e:
            print(f"[BambuFTPS] Upload failed: {e}")
            return False
