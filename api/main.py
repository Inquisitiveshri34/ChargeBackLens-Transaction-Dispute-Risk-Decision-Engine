"""
api/main.py — the FastAPI app.

Run from the repo root:  uvicorn api.main:app --reload --port 8000

The model and CSVs are loaded once, in the lifespan hook, and the artifact
contract is asserted there. If it fails the exception propagates and the server
does not start: a stale artifact is a boot failure, never a wrong score.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import service
from .artifacts import Artifacts, load_artifacts
from .schemas import EconomicsRequest, ScoreRequest

DEFAULT_CORS_ORIGINS = "http://localhost:3000,http://127.0.0.1:3000"

# The front end's host may put a CDN in front of /api/* and cache whatever the
# API allows, so every response says what it allows. Three endpoints are pure
# reads of frozen artifacts and may be held for five minutes (and served stale
# for an hour while a fresh copy is fetched). Everything else is computed per
# request, or may carry a model-written note, and is never stored.
CACHE_FROZEN = "public, max-age=0, s-maxage=300, stale-while-revalidate=3600"
CACHE_NEVER = "no-store"


@asynccontextmanager
async def lifespan(app: FastAPI):
    art = load_artifacts()            # raises scoring.ArtifactError -> no server
    app.state.art = art
    app.state.economics = service.EconomicsEngine(art)
    yield


def get_art(request: Request) -> Artifacts:
    return request.app.state.art


def get_economics(request: Request) -> service.EconomicsEngine:
    return request.app.state.economics


Art = Annotated[Artifacts, Depends(get_art)]
Economics = Annotated[service.EconomicsEngine, Depends(get_economics)]


def _error(status: int, error: str, message: str, fields: list[dict] | None = None) -> JSONResponse:
    return JSONResponse(status_code=status,
                        content={"error": error, "message": message, "fields": fields or []})


def create_app() -> FastAPI:
    app = FastAPI(title="ChargebackLens API", version="1.0.0", lifespan=lifespan)

    origins = [o.strip() for o in
               os.environ.get("CHARGEBACKLENS_CORS_ORIGINS", DEFAULT_CORS_ORIGINS).split(",")
               if o.strip()]
    app.add_middleware(CORSMiddleware, allow_origins=origins,
                       allow_methods=["GET", "POST"], allow_headers=["Content-Type"])
    # A 25% queue slice is about 300 KB of JSON; compressed it is a tenth of that.
    app.add_middleware(GZipMiddleware, minimum_size=1024)

    @app.middleware("http")
    async def default_cache_policy(request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("Cache-Control", CACHE_NEVER)
        return response

    # One error shape for everything, so the front end can show it inline:
    #   {"error": "...", "message": "one readable sentence", "fields": [{field, message}]}

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError):
        fields = []
        for err in exc.errors():
            loc = [str(p) for p in err["loc"] if p not in ("body", "query", "path")]
            message = err["msg"].removeprefix("Value error, ")
            fields.append({"field": ".".join(loc) or "request", "message": message})
        summary = "; ".join(f"{f['field']}: {f['message']}" for f in fields)
        return _error(422, "validation_error", summary, fields)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(_: Request, exc: StarletteHTTPException):
        return _error(exc.status_code, "not_found" if exc.status_code == 404 else "http_error",
                      str(exc.detail))

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    @app.get("/api/meta")
    def meta(art: Art, response: Response):
        response.headers["Cache-Control"] = CACHE_FROZEN
        return service.meta(art)

    @app.post("/api/score")
    def score(body: ScoreRequest, art: Art):
        try:
            return service.score(art, body.to_form())
        except ValueError as err:
            # scoring.build_instant_features rejects inputs notebook 1 would
            # have excluded; that is the caller's input, not a server fault.
            return _error(422, "validation_error", str(err))

    @app.get("/api/queue")
    def queue(art: Art, top_k_pct: Annotated[float, Query(ge=0.5, le=25)] = 5.0):
        return service.queue_slice(art, top_k_pct)

    @app.get("/api/queue/{payment_id}")
    def queue_detail(payment_id: str, art: Art):
        detail = service.queue_detail(art, payment_id)
        if detail is None:
            return _error(404, "not_found", f"No queue row with payment_id {payment_id}.")
        return detail

    @app.post("/api/economics")
    def economics(body: EconomicsRequest, engine: Economics):
        return engine.run(body.dispute_fee, body.ops_review_cost, body.merchant_margin,
                          body.step_up_abandon_rate, body.live_segments)

    @app.get("/api/sensitivity")
    def sensitivity(art: Art, response: Response):
        response.headers["Cache-Control"] = CACHE_FROZEN
        return service.sensitivity(art)

    @app.get("/api/lane-examples")
    def lane_examples(art: Art, response: Response,
                      per_band: Annotated[int, Query(ge=1, le=12)] = 5):
        response.headers["Cache-Control"] = CACHE_FROZEN
        return service.lane_examples(art, per_band)

    return app


app = create_app()
