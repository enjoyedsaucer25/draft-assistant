# draft-assistant

Local fantasy draft assistant: FastAPI (backend) + React/Vite (frontend) with SQLite storage.

## Quick Start

### Backend
```bash
# from repo root, create/activate venv (optional)
python -m venv .venv
source .venv/bin/activate  # Windows: .\.venv\Scripts\Activate.ps1

pip install -r requirements.txt

# run the API
uvicorn backend.app:app --host 0.0.0.0 --port 8000 --reload
