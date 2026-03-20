"""FastAPI application for VHP."""

from __future__ import annotations

import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

# Configure logging so Ollama / reasoning logs show in the terminal
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(name)-30s  %(levelname)-5s  %(message)s",
    datefmt="%H:%M:%S",
)

# Auto-configure PYTHONPATH so this file can be run directly:
#   python src/api/main.py   (from backend/)
#   python main.py           (from src/api/)
_this_dir = Path(__file__).resolve().parent          # src/api/
_src_dir = _this_dir.parent                          # src/
_backend_dir = _src_dir.parent                       # backend/
_data_dir = _backend_dir / "data"                    # backend/data/

for p in [str(_src_dir), str(_data_dir)]:
    if p not in sys.path:
        sys.path.insert(0, p)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.dependencies import get_state
from api.routers import audit, benchmark, hypergraph, provenance, reasoning, symptom, verkle


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialise VHP state on startup."""
    state = get_state()
    state.initialise()
    yield


app = FastAPI(
    title="VHP API",
    description="Verkle-Verified Hypergraph Provenance for Trustworthy AI Decision Systems",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(hypergraph.router, prefix="/api/hypergraph", tags=["hypergraph"])
app.include_router(verkle.router, prefix="/api/verkle", tags=["verkle"])
app.include_router(provenance.router, prefix="/api/provenance", tags=["provenance"])
app.include_router(reasoning.router, prefix="/api/reasoning", tags=["reasoning"])
app.include_router(audit.router, prefix="/api/audit", tags=["audit"])
app.include_router(benchmark.router, prefix="/api/benchmark", tags=["benchmark"])
app.include_router(symptom.router, prefix="/api/symptom", tags=["symptom"])


@app.get("/api/health")
def health_check():
    state = get_state()
    return {
        "status": "healthy",
        "hypergraph": state.hypergraph.stats,
        "verkle_root": state.verkle.root_hex,
        "root_chain_length": len(state.root_chain),
        "engine_type": state.engine_type,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.main:app", host="0.0.0.0", port=8000, reload=True)
