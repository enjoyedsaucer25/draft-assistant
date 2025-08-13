from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from .db import Base, engine, get_db
from . import models, schemas
from .ingest.csv_importer import import_from_csv
import os

app = FastAPI(title="Draft Assistant API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

@app.on_event("startup")
def startup():
    Base.metadata.create_all(bind=engine)

@app.get("/health")
def health(): return {"ok": True}

@app.get("/players", response_model=list[schemas.PlayerOut])
def list_players(
    q: str | None = Query(None, description="search by name/position/team"),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db)
):
    qry = db.query(models.Player)
    if q:
        like = f"%{q}%"
        qry = qry.filter(
            (models.Player.clean_name.ilike(like)) |
            (models.Player.position.ilike(like)) |
            (models.Player.team.ilike(like))
        )
    return qry.order_by(models.Player.clean_name.asc()).limit(limit).all()

@app.post("/admin/import/csv")
def admin_import_csv(path: str, db: Session = Depends(get_db)):
    if not os.path.exists(path):
        raise HTTPException(status_code=400, detail=f"File not found: {path}")
    result = import_from_csv(path, db)
    if result["errors"]:
        raise HTTPException(status_code=400, detail=result)
    return {"ok": True, "result": result}
