"""
PyVault Wi-Fi Sync Server
Lightweight local network server to transfer vault.enc directly to Android.
"""

import os
import sys
import socket
import secrets
import shutil
import urllib.parse
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from typing import Optional

def get_vault_path() -> str:
    if os.environ.get("PYVAULT_PATH"):
        return os.environ["PYVAULT_PATH"]
    home_vault = os.path.expanduser("~/.pyvault/vault.enc")
    if os.path.exists(home_vault):
        return home_vault
    if os.path.exists("vault.enc"):
        return os.path.abspath("vault.enc")
    return home_vault

VAULT_FILE = get_vault_path()
PORT = 8765


def get_local_ip() -> str:
    """Finds the local network IP of this machine."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip


class SyncHandler(BaseHTTPRequestHandler):
    pairing_pin: str = ""
    vault_path: str = VAULT_FILE
    on_vault_uploaded = None
    timeout = 15  # Prevent hanging keep-alive sockets

    def log_message(self, format, *args):
        # Clean terminal logging
        pass

    @classmethod
    def find_apk(cls) -> Optional[str]:
        search_dirs = [
            os.path.expanduser("~/.pyvault/downloads"),
            os.path.expanduser("~/Desktop/Projects/pyvault/downloads"),
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "downloads"),
            os.path.dirname(os.path.abspath(__file__)),
            os.path.expanduser("~/Downloads"),
        ]
        latest_apk = None
        latest_mtime = 0
        for d in search_dirs:
            if not os.path.exists(d):
                continue
            try:
                for root, _, files in os.walk(d):
                    # Skip hidden / venv directories
                    if "/." in root or "/venv" in root or "/build" in root:
                        continue
                    for f in files:
                        if f.lower().endswith(".apk"):
                            full_path = os.path.join(root, f)
                            try:
                                mtime = os.path.getmtime(full_path)
                                if mtime > latest_mtime:
                                    latest_mtime = mtime
                                    latest_apk = full_path
                            except Exception:
                                pass
            except Exception:
                continue
        return latest_apk

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        clean_path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        # 1. Web Installer landing page
        if clean_path in ("/", "/index.html"):
            apk_path = self.find_apk()
            apk_size_mb = ""
            if apk_path and os.path.exists(apk_path):
                size_mb = os.path.getsize(apk_path) / (1024 * 1024)
                apk_size_mb = f"({size_mb:.1f} MB)"

            html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>PyVault Android Installer</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: #0F172A;
      color: #F8FAFC;
      display: flex;
      align-items: center;
      justify-content: center;
      min-height: 100vh;
      padding: 24px;
      text-align: center;
    }}
    .card {{
      background: #1E293B;
      border: 1px solid #334155;
      border-radius: 20px;
      padding: 36px 24px;
      max-width: 420px;
      width: 100%;
      box-shadow: 0 10px 25px rgba(0,0,0,0.5);
    }}
    .badge {{
      display: inline-block;
      background: rgba(37,99,235,0.15);
      color: #38BDF8;
      padding: 6px 14px;
      border-radius: 20px;
      font-size: 13px;
      font-weight: 600;
      margin-bottom: 16px;
    }}
    h1 {{ font-size: 26px; font-weight: 700; margin-bottom: 8px; }}
    p {{ color: #94A3B8; font-size: 14px; line-height: 1.5; margin-bottom: 28px; }}
    .btn {{
      display: block;
      background: #2563EB;
      color: #FFFFFF;
      padding: 16px 24px;
      border-radius: 12px;
      font-size: 16px;
      font-weight: 600;
      text-decoration: none;
      box-shadow: 0 4px 14px rgba(37,99,235,0.4);
    }}
    .btn:active {{ background: #1D4ED8; }}
    .hint {{ color: #64748B; font-size: 12px; margin-top: 20px; }}
  </style>
</head>
<body>
  <div class="card">
    <div class="badge">PyVault Zero-Knowledge</div>
    <h1>Install PyVault</h1>
    <p>Download and install the native Android password manager directly from your laptop over local Wi-Fi.</p>
    <a class="btn" href="/apk">⬇️ Download Android APK {apk_size_mb}</a>
    <div class="hint">Tap "Download anyway" and "Allow install from unknown apps" if prompted by Android.</div>
  </div>
</body>
</html>"""
            data = html.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            try:
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError):
                pass
            return

        # 2. Direct APK download
        if clean_path in ("/apk", "/download-apk") or clean_path.endswith(".apk"):
            apk_path = self.find_apk()
            if not apk_path or not os.path.exists(apk_path):
                self.send_response(404)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.end_headers()
                self.wfile.write(b"APK file not found on laptop. Please place it in downloads/ or ~/Downloads.")
                return

            try:
                file_size = os.path.getsize(apk_path)
                self.send_response(200)
                self.send_header("Content-Type", "application/vnd.android.package-archive")
                self.send_header("Content-Disposition", 'attachment; filename="PyVault.apk"')
                self.send_header("Content-Length", str(file_size))
                self.end_headers()

                with open(apk_path, "rb") as f:
                    shutil.copyfileobj(f, self.wfile, length=64 * 1024)
                print(f"[+] Successfully served PyVault APK ({file_size / 1024 / 1024:.1f} MB) to phone!")
            except (BrokenPipeError, ConnectionResetError):
                pass
            return

        # 3. Endpoint: /vault?pin=123456
        if clean_path.startswith("/vault"):
            query_pin = query.get("pin", [""])[0]

            if query_pin != self.pairing_pin:
                self.send_response(401)
                self.send_header("Content-Type", "text/plain")
                self.end_headers()
                self.wfile.write(b"Unauthorized: Invalid Sync PIN.")
                print("[!] Rejected sync attempt: Invalid PIN.")
                return

            if not os.path.exists(self.vault_path):
                self.send_response(404)
                self.end_headers()
                self.wfile.write(b"Vault file not found.")
                return

            with open(self.vault_path, "rb") as f:
                data = f.read()

            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Disposition", 'attachment; filename="vault.enc"')
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            try:
                self.wfile.write(data)
                print("[+] Successfully synced vault to phone!")
            except (BrokenPipeError, ConnectionResetError):
                pass
            return

        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        clean_path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        # Endpoint: /upload?pin=123456
        if clean_path.startswith("/upload"):
            query_pin = query.get("pin", [""])[0]

            if query_pin != self.pairing_pin:
                self.send_response(401)
                self.end_headers()
                return

            content_len = int(self.headers.get("Content-Length", 0))
            if content_len == 0 or content_len > 50 * 1024 * 1024:  # 50MB max limit
                self.send_response(400)
                self.end_headers()
                return

            uploaded_data = self.rfile.read(content_len)
            is_valid = False
            try:
                import json
                env_obj = json.loads(uploaded_data.decode("utf-8"))
                if env_obj.get("format") == "PV02" or "slot_pw" in env_obj:
                    is_valid = True
            except Exception:
                if uploaded_data.startswith(b"PV01"):
                    is_valid = True

            if not is_valid:
                self.send_response(400)
                self.send_header("Content-Type", "text/plain")
                self.end_headers()
                self.wfile.write(b"Invalid vault file: expected PV02 envelope.")
                return

            # Atomic save
            tmp_path = self.vault_path + ".incoming"
            with open(tmp_path, "wb") as f:
                f.write(uploaded_data)
            os.replace(tmp_path, self.vault_path)

            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"Vault updated successfully.")
            print("[+] Successfully received updated vault from phone!")
            if SyncHandler.on_vault_uploaded:
                try:
                    SyncHandler.on_vault_uploaded()
                except Exception as e:
                    print(f"[!] Error in on_vault_uploaded: {e}")
            return

        self.send_response(404)
        self.end_headers()


class ReusableThreadingServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True


def run_sync_server(vault_path: str = VAULT_FILE, pin: Optional[str] = None, server_holder: Optional[list] = None):
    local_ip = get_local_ip()
    sync_pin = pin or f"{secrets.randbelow(900000) + 100000}"

    SyncHandler.pairing_pin = sync_pin
    SyncHandler.vault_path = vault_path

    server = ReusableThreadingServer(("0.0.0.0", PORT), SyncHandler)
    if server_holder is not None:
        server_holder.append(server)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        try:
            server.server_close()
        except Exception:
            pass


if __name__ == "__main__":
    run_sync_server()
