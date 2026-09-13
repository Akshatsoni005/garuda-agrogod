"""
Garuda AgroGod - Unified Production Deployment Runner
Starts both FastAPI backend server and Cloudflare Public Tunnel,
keeping both processes supervised and persistent.
"""

import subprocess
import time
import os
import sys
import re
import signal

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PYTHON_BIN = os.path.join(BASE_DIR, ".venv", "bin", "python")
BIN_CLOUDFLARED = os.path.join(BASE_DIR, "bin", "cloudflared")
URL_FILE = os.path.join(BASE_DIR, "PUBLIC_URL.txt")

def main():
    print("=======================================================")
    print("  GARUDA AGROGOD - PRODUCTION DEPLOYMENT SUPERVISOR    ")
    print("=======================================================")

    # 1. Start FastAPI server
    server_cmd = [PYTHON_BIN, os.path.join(BASE_DIR, "server", "main.py")]
    server_proc = subprocess.Popen(server_cmd, cwd=BASE_DIR)
    print(f"[Supervisor] FastAPI server launched (PID: {server_proc.pid})")
    time.sleep(2)

    # 2. Start Cloudflare Tunnel
    tunnel_cmd = [BIN_CLOUDFLARED, "tunnel", "--url", "http://localhost:8000"]
    tunnel_proc = subprocess.Popen(tunnel_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    print(f"[Supervisor] Cloudflare Tunnel launched (PID: {tunnel_proc.pid})")

    regex = re.compile(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com")
    public_url = None

    def cleanup(signum, frame):
        print("\n[Supervisor] Shutting down deployment...")
        server_proc.terminate()
        tunnel_proc.terminate()
        sys.exit(0)

    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)

    for line in tunnel_proc.stdout:
        match = regex.search(line)
        if match:
            public_url = match.group(0)
            with open(URL_FILE, "w") as f:
                f.write(public_url.strip() + "\n")
            print(f"\n=======================================================")
            print(f"  🚀 [DEPLOYED LIVE TO THE WORLD]                     ")
            print(f"  Public Tactical Deck: {public_url}                  ")
            print(f"  Public 3D God's Eye:  {public_url}/gods_eye.html    ")
            print(f"=======================================================\n")
            break

    # Keep supervising both processes
    while True:
        if server_proc.poll() is not None:
            print("[Supervisor] Server exited, restarting...")
            server_proc = subprocess.Popen(server_cmd, cwd=BASE_DIR)
        if tunnel_proc.poll() is not None:
            print("[Supervisor] Tunnel exited, restarting...")
            tunnel_proc = subprocess.Popen(tunnel_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        time.sleep(2)

if __name__ == "__main__":
    main()
