from fastapi import APIRouter, Depends, HTTPException, Header, Query
from sqlalchemy.orm import Session
import os
import sys
import subprocess
import tempfile

from ..db import get_db
from ..config.settings import settings
from ..ingest.csv_importer import import_from_csv
from .. import models
from ..ingest.sources.sleeper_players import import_sleeper_players
from ..ingest.sources.fantasypros_ecr import (
    import_fp_csv,
    import_fp_overall_html,
    import_fp_csv_from_url,
    import_fp_ecr_auto,
)
from ..ingest.sources.fantasypros_adp import import_fp_adp_csv
from ..ingest.sources.injuries_cbs import import_cbs_injuries

router = APIRouter(prefix="/admin", tags=["admin"])

def require_admin(x_token: str | None = Header(None, description="admin token for /admin/* (header name: x-token)")):
    if settings.admin_token and x_token != settings.admin_token:
        raise HTTPException(status_code=401, detail="unauthorized")


@router.post("/import/csv", dependencies=[Depends(require_admin)])
def admin_import_csv(path: str, db: Session = Depends(get_db)):
    if not os.path.exists(path):
        raise HTTPException(status_code=400, detail=f"File not found: {path}")
    result = import_from_csv(path, db)
    if result["errors"]:
        raise HTTPException(status_code=400, detail=result)
    return {"ok": True, "result": result}

@router.post("/import/demo", dependencies=[Depends(require_admin)])
def admin_import_demo(db: Session = Depends(get_db)):
    demo = [
        {"player_id":"rb.cmcc","season":2025,"clean_name":"Christian McCaffrey","position":"RB","team":"SF","bye_week":9,"ecr_rank":1,"ecr_pos_rank":1,"tier":1},
        {"player_id":"wr.jchase","season":2025,"clean_name":"Ja'Marr Chase","position":"WR","team":"CIN","bye_week":12,"ecr_rank":2,"ecr_pos_rank":1,"tier":1},
        {"player_id":"wr.cupl","season":2025,"clean_name":"CeeDee Lamb","position":"WR","team":"DAL","bye_week":7,"ecr_rank":3,"ecr_pos_rank":2,"tier":1},
        {"player_id":"rb.brobinson","season":2025,"clean_name":"Bijan Robinson","position":"RB","team":"ATL","bye_week":12,"ecr_rank":4,"ecr_pos_rank":2,"tier":1},
        {"player_id":"wr.asb","season":2025,"clean_name":"Amon-Ra St. Brown","position":"WR","team":"DET","bye_week":9,"ecr_rank":5,"ecr_pos_rank":3,"tier":1},
        {"player_id":"qb.jallen","season":2025,"clean_name":"Josh Allen","position":"QB","team":"BUF","bye_week":12,"ecr_rank":20,"ecr_pos_rank":1,"tier":2},
    ]
    for r in demo:
        p = db.query(models.Player).filter_by(player_id=r["player_id"]).first()
        if not p:
            db.add(models.Player(**{k:r[k] for k in ["player_id","season","clean_name","position","team","bye_week"]}))
        else:
            p.season=r["season"]; p.clean_name=r["clean_name"]; p.position=r["position"]; p.team=r["team"]; p.bye_week=r["bye_week"]
        cr = db.query(models.ConsensusRank).filter_by(season=r["season"], player_id=r["player_id"]).first()
        if not cr:
            db.add(models.ConsensusRank(season=r["season"], player_id=r["player_id"], ecr_rank=r["ecr_rank"], ecr_pos_rank=r["ecr_pos_rank"], tier=r["tier"], source="demo"))
        else:
            cr.ecr_rank=r["ecr_rank"]; cr.ecr_pos_rank=r["ecr_pos_rank"]; cr.tier=r["tier"]; cr.source="demo"
    db.commit()
    return {"ok": True, "imported": len(demo)}

@router.post("/import/sleeper_players", dependencies=[Depends(require_admin)])
def admin_import_sleeper_players(season: int, db: Session = Depends(get_db)):
    return import_sleeper_players(db, season)

@router.post("/import/fp_ecr_csv", dependencies=[Depends(require_admin)])
def admin_import_fp_ecr_csv(season: int, path: str, db: Session = Depends(get_db)):
    return import_fp_csv(db, season, path)

@router.post("/import/fp_ecr_html", dependencies=[Depends(require_admin)])
def admin_import_fp_ecr_html(season: int, url: str, db: Session = Depends(get_db)):
    return import_fp_overall_html(db, season, url)

@router.post("/import/fp_ecr_url", dependencies=[Depends(require_admin)])
def admin_import_fp_ecr_url(season: int, url: str, db: Session = Depends(get_db)):
    """Directly fetch CSV from a FantasyPros URL (best-effort)."""
    return import_fp_csv_from_url(db, season, url)

@router.post("/import/fp_ecr_auto", dependencies=[Depends(require_admin)])
def admin_import_fp_ecr_auto_route(season: int, path_or_url: str, db: Session = Depends(get_db)):
    """
    Smart import: 
      - if path_or_url is a URL, try CSV, fallback to HTML
      - else treat as local CSV path
    """
    return import_fp_ecr_auto(db, season, path_or_url)

@router.post("/import/fp_adp_csv", dependencies=[Depends(require_admin)])
def admin_import_fp_adp_csv(season: int, path: str, source: str = "fp_composite", db: Session = Depends(get_db)):
    return import_fp_adp_csv(db, season, path, source_name=source)

@router.post("/import/injuries_cbs", dependencies=[Depends(require_admin)])
def admin_import_injuries_cbs(season: int, db: Session = Depends(get_db)):
    return import_cbs_injuries(db, season)

# NEW: run your Playwright scraper then ingest its normalized CSV
@router.post("/import/fp_ecr_via_script", dependencies=[Depends(require_admin)])
def admin_import_fp_ecr_via_script(
    season: int,
    script_path: str = Query("fp_pull_half_ppr.py", description="Path to your scraper script"),
    url: str = Query("https://www.fantasypros.com/nfl/rankings/half-point-ppr-cheatsheets.php"),
    headful: bool = Query(False, description="Open browser window (debug)"),
    db: Session = Depends(get_db),
):
    """
    Runs your FP scraper to produce a normalized CSV, then ingests it into consensus_ranks.
    Requires Playwright + Chromium installed in the same venv used to run the API.
    """
    tmpdir = tempfile.mkdtemp(prefix="fp_norm_")
    out_csv = os.path.join(tmpdir, "fp_half_ppr_overall_normalized.csv")

    py = sys.executable or "python"
    args = [py, script_path, "--url", url, "--out-csv", out_csv, "--no-sqlite"]
    if headful:
        args.append("--headful")

    try:
        proc = subprocess.run(args, capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError as e:
        tail_out = (e.stdout or "")[-2000:]
        tail_err = (e.stderr or "")[-2000:]
        raise HTTPException(
            status_code=500,
            detail=f"Scraper failed.\ncmd: {' '.join(args)}\nstdout:\n{tail_out}\nstderr:\n{tail_err}"
        )

    result = import_fp_csv(db, season, out_csv)

    # Surface issues loudly if nothing matched
    if result.get("imported", 0) == 0:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "FP ECR import matched 0 players. Check that Sleeper players are loaded for this season and CSV headers include 'player_name'/'rank'.",
                "result": result,
                "stdout_tail": (proc.stdout or "")[-1000:],
                "stderr_tail": (proc.stderr or "")[-1000:],
                "csv_path": out_csv,
            }
        )

    return {
        "ok": True,
        "csv": out_csv,
        "scraper_stdout_tail": (proc.stdout or "")[-2000:],
        "scraper_stderr_tail": (proc.stderr or "")[-2000:],
        "result": result,
    }
