"""FastAPI application entry point."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from stepdiff import __version__
from stepdiff.api.routes import router

app = FastAPI(
    title="StepDiff",
    description="Capture, compact, and evaluate browser interaction runs",
    version=__version__,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/")
def health() -> dict[str, str]:
    return {"status": "ok", "version": __version__}
