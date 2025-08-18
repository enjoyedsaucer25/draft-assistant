# backend/ingest/sources/sleeper_players.py
from __future__ import annotations

from datetime import datetime

import httpx
from sqlalchemy.orm import Session

from ... import models

URL = "https://api.sleeper.app/v1/players/nfl"


def get_or_create_source(db: Session, name: str, kind: str) -> models.Source:
    src = db.query(models.Source).filter_by(name=name).first()
    if not src:
        src = models.Source(name=name, kind=kind)
        db.add(src)
        db.commit()
        db.refresh(src)
    return src


def import_sleeper_players(db: Session, season: int) -> dict:
    """
    Fetch the Sleeper master player file and upsert `players` table.
    - Only record players that have `position` and `full_name`.
    - Set external IDs when available.
    """
    src = get_or_create_source(db, "sleeper", "players")
    run = models.ImportRun(source_id=src.source_id)
    db.add(run)
    db.commit()
    db.refresh(run)

    try:
        with httpx.Client(timeout=60) as client:
            resp = client.get(URL)
            resp.raise_for_status()
            data = resp.json()

        count = 0
        for sid, pl in data.items():
            full_name = pl.get("full_name") or ""
            pos = pl.get("position") or ""
            if not full_name or not pos:
                continue

            team = pl.get("team")
            clean_name = full_name.strip()
            player_id = pl.get("player_id") or f"{pos.lower()}.{clean_name.lower().replace(' ', '')}"

            p = db.query(models.Player).filter_by(player_id=player_id).first()
            if not p:
                p = models.Player(
                    player_id=player_id,
                    season=season,
                    clean_name=clean_name,
                    position=pos,
                    team=team,
                    bye_week=None,
                    sleeper_id=pl.get("player_id"),
                    espn_id=str(pl.get("espn_id")) if pl.get("espn_id") else None,
                    nfl_id=str(pl.get("nfl_id")) if pl.get("nfl_id") else None,
                )
                db.add(p)
            else:
                p.season = season
                p.clean_name = clean_name
                p.position = pos
                p.team = team
                p.sleeper_id = pl.get("player_id")
                if pl.get("espn_id"):
                    p.espn_id = str(pl["espn_id"])
                if pl.get("nfl_id"):
                    p.nfl_id = str(pl["nfl_id"])

            count += 1

        db.commit()
        run.success = True
        run.row_count = count
        run.finished_at = datetime.utcnow()
        db.commit()
        return {"imported": count, "errors": []}
    except Exception as e:
        run.success = False
        run.error_text = str(e)
        run.finished_at = datetime.utcnow()
        db.commit()
        return {"imported": 0, "errors": [str(e)]}
