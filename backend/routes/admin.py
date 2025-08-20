# backend/routes/admin.py
from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..db import get_db
from ..config.settings import settings
from ..ingest.sources.sleeper_players import import_sleeper_players
from ..ingest.fp_importers import (
    import_fp_ecr_csv_to_orm,
    import_fp_adp_csv_to_orm,
    import_fp_proj_csv_to_orm,
)

router = APIRouter(prefix="/admin", tags=["admin"])

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

def _now_year() -> int:
    return datetime.utcnow().year

def _sqlite_path_from_url(db_url: str) -> str:
    if db_url.startswith("sqlite:///"):
        return db_url.replace("sqlite:///", "", 1)
    if db_url.startswith("sqlite:////"):
        return db_url.replace("sqlite:////", "/", 1)
    return "./draft.db"

SQLITE_PATH = _sqlite_path_from_url(settings.db_url)

def _run_script(pyfile: str, args: list[str]) -> dict:
    """
    Run a Python script in a subprocess, capture stdout/stderr and returncode.
    Force UTF-8 stdio so scripts can print Unicode (fixes Windows cp1252 errors).
    """
    script_path = os.path.join(BASE_DIR, pyfile)
    cmd = [sys.executable, script_path, *args]
    if not os.path.exists(script_path):
        return {"ok": False, "code": 127, "stdout": "", "stderr": f"Script not found: {script_path}", "cmd": cmd}

    env = os.environ.copy()
    # Ensure Unicode-friendly console I/O for subprocess on Windows too
    env.setdefault("PYTHONUTF8", "1")
    env.setdefault("PYTHONIOENCODING", "utf-8")

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, env=env)
        return {
            "ok": proc.returncode == 0,
            "code": proc.returncode,
            "stdout": (proc.stdout or "")[-20000:],
            "stderr": (proc.stderr or "")[-20000:],
            "cmd": cmd,
        }
    except Exception as e:
        return {"ok": False, "code": 1, "stdout": "", "stderr": str(e), "cmd": cmd}


@router.post("/import/fp_ecr_via_script")
def import_fp_ecr_via_script(
    season: Optional[int] = Query(None, description="Season; defaults to current year"),
    db: Session = Depends(get_db),
):
    season = season or _now_year()
    raw_csv = os.path.join(BASE_DIR, "data", "raw", "fp_half_ppr_overall.csv")
    norm_csv = os.path.join(BASE_DIR, "data", "normalized", "fp_half_ppr_overall_normalized.csv")

    res = _run_script("fp_pull_half_ppr.py", [
        "--season", str(season),
        "--sqlite", SQLITE_PATH,
        "--download-to", raw_csv,
        "--out-csv", norm_csv,
    ])

    import_res = import_fp_ecr_csv_to_orm(norm_csv, db, season)
    return {"season": season, "script": res, "import": import_res}


@router.post("/import/fp_adp_via_script")
def import_fp_adp_via_script(
    season: Optional[int] = Query(None, description="Season; defaults to current year"),
    db: Session = Depends(get_db),
):
    season = season or _now_year()
    raw_csv = os.path.join(BASE_DIR, "data", "raw", "fp_half_ppr_adp_overall.csv")
    norm_csv = os.path.join(BASE_DIR, "data", "normalized", "fp_half_ppr_adp_overall_normalized.csv")

    res = _run_script("fp_pull_adp_half_ppr_overall.py", [
        "--season", str(season),
        "--sqlite", SQLITE_PATH,
        "--download-to", raw_csv,
        "--out-csv", norm_csv,
    ])

    import_res = import_fp_adp_csv_to_orm(norm_csv, db, season)
    return {"season": season, "script": res, "import": import_res}


@router.post("/import/fp_projections_via_script")
def import_fp_projections_via_script(
    season: Optional[int] = Query(None, description="Season; defaults to current year"),
    db: Session = Depends(get_db),
):
    season = season or _now_year()
    out_combined = os.path.join(BASE_DIR, "data", "normalized", "fp_projections_combined.csv")

    res = _run_script("fp_pull_projections.py", [
        "--season", str(season),
        "--sqlite", SQLITE_PATH,
        "--out-csv-combined", out_combined,
    ])

    import_res = import_fp_proj_csv_to_orm(out_combined, db, season)
    return {"season": season, "script": res, "import": import_res}


@router.post("/import/sleeper_players")
def import_sleeper_players_admin(
    season: Optional[int] = Query(None, description="Season; defaults to current year"),
    db: Session = Depends(get_db),
):
    season = season or _now_year()
    res = import_sleeper_players(db, season=season)
    return {"season": season, **res}


@router.post("/import/run_all")
def import_run_all(
    season: Optional[int] = Query(None, description="Season; defaults to current year"),
    db: Session = Depends(get_db),
):
    season = season or _now_year()
    logs = []

    # 1) Sleeper players (foundation for crosswalk)
    try:
        sp = import_sleeper_players(db, season=season)
        logs.append({"step": "sleeper_players", "ok": True, "stdout": str(sp), "stderr": ""})
    except Exception as e:
        logs.append({"step": "sleeper_players", "ok": False, "stdout": "", "stderr": str(e)})

    # 2) ECR (tiers/ranks)
    raw_ecr = os.path.join(BASE_DIR, "data", "raw", "fp_half_ppr_overall.csv")
    norm_ecr = os.path.join(BASE_DIR, "data", "normalized", "fp_half_ppr_overall_normalized.csv")
    ecr = _run_script("fp_pull_half_ppr.py", [
        "--season", str(season),
        "--sqlite", SQLITE_PATH,
        "--download-to", raw_ecr,
        "--out-csv", norm_ecr,
    ])
    logs.append({"step": "fp_ecr_script", **ecr})
    ecr_import = import_fp_ecr_csv_to_orm(norm_ecr, db, season)
    logs.append({"step": "fp_ecr_import", "ok": (ecr_import.get("errors") == []), "stdout": str(ecr_import), "stderr": ""})

    # 3) ADP
    raw_adp = os.path.join(BASE_DIR, "data", "raw", "fp_half_ppr_adp_overall.csv")
    norm_adp = os.path.join(BASE_DIR, "data", "normalized", "fp_half_ppr_adp_overall_normalized.csv")
    adp = _run_script("fp_pull_adp_half_ppr_overall.py", [
        "--season", str(season),
        "--sqlite", SQLITE_PATH,
        "--download-to", raw_adp,
        "--out-csv", norm_adp,
    ])
    logs.append({"step": "fp_adp_script", **adp})
    adp_import = import_fp_adp_csv_to_orm(norm_adp, db, season)
    logs.append({"step": "fp_adp_import", "ok": (adp_import.get("errors") == []), "stdout": str(adp_import), "stderr": ""})

    # 4) Projections (with UTF-8 stdout handled)
    out_proj = os.path.join(BASE_DIR, "data", "normalized", "fp_projections_combined.csv")
    proj = _run_script("fp_pull_projections.py", [
        "--season", str(season),
        "--sqlite", SQLITE_PATH,
        "--out-csv-combined", out_proj,
    ])
    logs.append({"step": "fp_projections_script", **proj})
    proj_import = import_fp_proj_csv_to_orm(out_proj, db, season)
    logs.append({"step": "fp_projections_import", "ok": (proj_import.get("errors") == []), "stdout": str(proj_import), "stderr": ""})

    ok = all(x.get("ok", True) for x in logs if "ok" in x)
    return {"ok": ok, "season": season, "logs": logs}
