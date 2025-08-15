# backend/run_debug.py
import os
import sys
from pathlib import Path
import uvicorn

# Ensure the project root is on sys.path so "import backend.*" works
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

def in_reload_worker() -> bool:
    """
    Only start debugpy in the *worker* process (not the reloader parent).
    Uvicorn with --reload sets WATCHFILES_RESTARTED in the worker.
    Also check common fallbacks used by other reloaders.
    """
    if os.environ.get("WATCHFILES_RESTARTED") is not None:
        return True
    if os.environ.get("RUN_MAIN") == "true":
        return True
    if os.environ.get("UVICORN_RELOAD_PROCESS") == "true":
        return True
    return False

def main():
    # Start debugpy only in the worker process
    if in_reload_worker():
        try:
            import debugpy  # installed in your venv
            port = int(os.environ.get("DEBUGPY_PORT", "5678"))
            debugpy.listen(("127.0.0.1", port))
            print(f">> debugpy listening on {port} (attach from VS Code)")
        except Exception as e:
            print(f">> debugpy disabled: {e}")
    else:
        print(">> reloader parent process (no debugpy listener)")

    # Use package path; this now works regardless of current directory
    uvicorn.run(
        "backend.app:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        reload_dirs=["backend"],
    )

if __name__ == "__main__":
    main()
