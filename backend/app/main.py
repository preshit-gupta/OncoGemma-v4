from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.gcs import ensure_buckets_exist
from app.core.db import Base, engine
from app.routers import cases_router, tiles_router, audit_router, triage_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure database tables exist for dev
    Base.metadata.create_all(bind=engine)
    # Ensure GCS buckets exist for local dev
    ensure_buckets_exist()
    yield

app = FastAPI(
    title="OncoGemma v4 API",
    description="Breast Cancer Diagnostic Copilot API — Nottingham Grading & CAP Dossier Workflow",
    version="4.2.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(cases_router)
app.include_router(tiles_router)
app.include_router(audit_router)
app.include_router(triage_router)

@app.get("/healthz")
def health_check():
    return {
        "status": "healthy",
        "version": app.version,
        "env": settings.ENV
    }
