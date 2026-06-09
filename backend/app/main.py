from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .api import router
from .db import init_db

app = FastAPI(title="LocalAds Manager")
app.include_router(router)

try:
    from .agent import router as agent_router
    app.include_router(agent_router)
except ImportError:
    pass  # anthropic not installed; dashboard works without the agent

FRONTEND = Path(__file__).resolve().parents[2] / "frontend"
if FRONTEND.exists():
    app.mount("/", StaticFiles(directory=FRONTEND, html=True), name="frontend")


@app.on_event("startup")
def _startup():
    init_db()
