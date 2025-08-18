# backend/run_debug.py
"""
Launch the FastAPI app under a debugpy listener, tolerating port collisions.

Usage (Windows bash or PowerShell):
    python -m backend.run_debug
or:
    python backend/run_debug.py

Then attach VS Code to "Python: Remote Attach" on localhost:DA_DEBUG_PORT (default 5678).
"""
from __future__ import annotations

import os
import socket
import sys

import debugpy
import uvicorn


def find_open_port(start: int = 5678, limit: int = 50) -> int:
    for p in range(start, start + limit):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("0.0.0.0", p))
                return p
        except OSError:
            continue
    return start


def main() -> None:
    port = int(os.getenv("DA_DEBUG_PORT", "5678"))
    port = find_open_port(port, 50)
    print(f"[debug] starting debugpy on 0.0.0.0:{port}")
    debugpy.listen(("0.0.0.0", port))
    if os.getenv("DA_DEBUG_WAIT", "0") == "1":
        print("[debug] waiting for debugger attach...")
        debugpy.wait_for_client()

    # Make backend importable in both direct and module modes
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
    uvicorn.run("backend.app:app", host="0.0.0.0", port=int(os.getenv("PORT", "8000")), reload=True)


if __name__ == "__main__":
    main()
