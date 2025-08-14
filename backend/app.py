from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .db import Base, engine
from .config.settings import settings
from .routes import players, teams, picks, suggestions, admin
from .routes import meta
from .routes import edits


app = FastAPI(title="Draft Assistant API")

app.include_router(meta.router)
app.include_router(edits.router)

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

app.include_router(players.router)
app.include_router(teams.router)
app.include_router(picks.router)
app.include_router(suggestions.router)
app.include_router(admin.router)
