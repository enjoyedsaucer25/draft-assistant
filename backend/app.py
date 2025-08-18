# backend/app.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse

from .db import Base, engine
from .config.settings import settings
from .routes import players, teams, picks, suggestions, admin, meta, edits


app = FastAPI(
    title="Draft Assistant API",
    default_response_class=ORJSONResponse,
)

# Routers
app.include_router(meta.router)
app.include_router(edits.router)
app.include_router(players.router)
app.include_router(teams.router)
app.include_router(picks.router)
app.include_router(suggestions.router)
app.include_router(admin.router)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def startup():
    Base.metadata.create_all(bind=engine)

@app.get("/")
def home():
    return {"service": "Draft Assistant API", "ok": True, "hint": "see /health and /docs"}

@app.get("/health")
def health():
    return {"ok": True}
