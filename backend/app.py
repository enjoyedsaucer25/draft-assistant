from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from .db import Base, engine, get_db
from . import models, schemas

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
def list_players(db: Session = Depends(get_db)):
    return db.query(models.Player).limit(2000).all()

@app.get("/")
def home():
    return {"service": "Draft Assistant API", "status": "ok", "hint": "see /health and /docs"}

