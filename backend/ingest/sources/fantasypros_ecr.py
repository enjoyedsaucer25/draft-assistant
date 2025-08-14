import pandas as pd, re, httpx
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session
from ... import models

def _ensure_consensus_row(db: Session, season: int, player_id: str, ecr_rank, ecr_pos_rank, tier, source="fantasypros"):
    cr = db.query(models.ConsensusRank).filter_by(season=season, player_id=player_id).first()
    if not cr:
        cr = models.ConsensusRank(season=season, player_id=player_id)
        db.add(cr)
    cr.ecr_rank = float(ecr_rank) if ecr_rank is not None else cr.ecr_rank
    cr.ecr_pos_rank = float(ecr_pos_rank) if ecr_pos_rank is not None else cr.ecr_pos_rank
    cr.tier = int(tier) if pd.notna(tier) and tier != "" else cr.tier
    cr.source = source

def import_fp_csv(db: Session, season: int, csv_path: str) -> dict:
    df = pd.read_csv(csv_path)
    # Expected columns like: Player, Team, Pos, ECR, Pos Rank, Tier
    name_col = next((c for c in df.columns if c.lower() in ("player","name")), None)
    if not name_col:
        return {"imported": 0, "errors": ["CSV missing 'Player' column"]}
    count = 0
    for _, r in df.iterrows():
        name = str(r[name_col]).strip()
        team = str(r.get("Team") or r.get("team") or "").strip() or None
        pos = str(r.get("Pos") or r.get("Position") or "").strip() or None
        ecr = r.get("ECR") or r.get("Rank")
        pos_rank = r.get("Pos Rank") or r.get("PosRank")
        tier = r.get("Tier")
        # match player by name + position (and team if present)
        q = db.query(models.Player).filter(models.Player.clean_name==name)
        if pos: q = q.filter(models.Player.position==pos)
        if team: q = q.filter(models.Player.team==team)
        p = q.first()
        if not p: 
            continue
        _ensure_consensus_row(db, season, p.player_id, ecr, pos_rank, tier)
        count += 1
    db.commit()
    return {"imported": count, "errors": []}

def import_fp_overall_html(db: Session, season: int, url: str) -> dict:
    # fallback scraper for the overall ECR page
    with httpx.Client(timeout=60) as client:
        html = client.get(url).text
    soup = BeautifulSoup(html, "lxml")
    table = soup.find("table")
    if not table:
        return {"imported": 0, "errors": ["No table found"]}
    rows = table.find_all("tr")
    count = 0
    for tr in rows:
        cols = [c.get_text(strip=True) for c in tr.find_all(["td","th"])]
        if len(cols) < 4: 
            continue
        # Heuristic: [Rank, Player, Team, Pos, Tier ...]
        try:
            rank = float(cols[0])
        except:
            continue
        name = cols[1]
        team = cols[2] if len(cols) > 2 else None
        pos = cols[3] if len(cols) > 3 else None
        tier = None
        for c in cols:
            if c.lower().startswith("tier"):
                m = re.search(r"(\d+)", c)
                if m: tier = int(m.group(1))
        q = db.query(models.Player).filter(models.Player.clean_name==name)
        if pos: q = q.filter(models.Player.position==pos)
        if team: q = q.filter(models.Player.team==team)
        p = q.first()
        if not p: 
            continue
        _ensure_consensus_row(db, season, p.player_id, rank, None, tier)
        count += 1
    db.commit()
    return {"imported": count, "errors": []}
