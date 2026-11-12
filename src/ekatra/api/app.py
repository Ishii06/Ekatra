from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ekatra.api.builds import load_builds_from_disk, router as builds_router
from ekatra.api.routes import router


@asynccontextmanager
async def lifespan(_app: FastAPI):
    load_builds_from_disk()  # projects built before this start stay available (and can be changed)
    yield


app = FastAPI(
    title="Ekatra API",
    description="Minimal REST API adapter for the Ekatra multi-agent orchestration engine.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")
app.include_router(builds_router, prefix="/api")


@app.get("/")
def root() -> dict[str, str]:
    return {"message": "Ekatra API root", "docs": "/docs"}
