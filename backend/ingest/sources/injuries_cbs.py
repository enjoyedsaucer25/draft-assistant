import httpx
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session
from ... import models
from datetime import datetime

CBS_URL = "https://www.cbssports.com/nfl/injuries/"

def import_cbs_injuries(db: Session, season: int) -> dict:
    with httpx.Client(timeout=60) as client:
        html = client.get(CBS_URL).text
    soup = BeautifulSoup(html, "lxml")
    sections = soup.select("div.Page-colMain div.TeamInjuries")  # team blocks
    count = 0
    for sec in sections:
        rows = sec.select("table tr")[1:]  # skip header
        for tr in rows:
            tds = [td.get_text(strip=True) for td in tr.find_all("td")]
            if len(tds) < 5: 
                continue
            name = tds[0]
            pos = tds[1]
            updated = tds[2]       # not used but available
            body = tds[3]          # "Hamstring", "Knee", etc.
            status = tds[4]        # "Questionable for Week 1", "IR"...
            # Match to player (name + position is most reliable here)
            q = db.query(models.Player).filter(models.Player.clean_name==name)
            if pos: q = q.filter(models.Player.position==pos)
            p = q.first()
            if not p:
                continue
            inj = db.query(models.Injury).filter_by(season=season, player_id=p.player_id, source="cbs").first()
            if not inj:
                inj = models.Injury(season=season, player_id=p.player_id, source="cbs")
                db.add(inj)
            inj.status = status
            inj.body_part = body
            inj.practice_status = None
            inj.return_timeline = None
            inj.asof_ts = datetime.utcnow()
            count += 1
    db.commit()
    return {"imported": count, "errors": []}
