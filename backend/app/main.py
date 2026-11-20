"""FastAPI application factory."""
from __future__ import annotations

import time
import uuid

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import auth, documents, insights, invoices, knowledge, masterdata, queue, review, system
from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.services.documents.validation import UploadRejected

log = get_logger("api")


def create_app() -> FastAPI:
    s = get_settings()
    configure_logging(json_logs=s.environment != "development")
    app = FastAPI(title="InvoiceFlow API", version="1.0.0",
                  description="AI-assisted supplier-invoice processing with deterministic reconciliation.",
                  docs_url="/api/docs", openapi_url="/api/openapi.json")
    app.add_middleware(CORSMiddleware, allow_origins=s.cors_origins, allow_credentials=True,
                       allow_methods=["GET", "POST", "PATCH", "DELETE"],
                       allow_headers=["Authorization", "Content-Type", "X-Requested-With"])

    @app.middleware("http")
    async def request_context(request: Request, call_next):  # noqa: ANN001, ANN202
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
        structlog.contextvars.bind_contextvars(request_id=rid)
        t0 = time.perf_counter()
        response = await call_next(request)
        response.headers["X-Request-ID"] = rid
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        if not request.url.path.startswith(("/health", "/api/events")):
            log.info("request", method=request.method, path=request.url.path, status=response.status_code,
                     duration_ms=int((time.perf_counter() - t0) * 1000))
        structlog.contextvars.clear_contextvars()
        return response

    @app.exception_handler(UploadRejected)
    async def _upload_rejected(_: Request, exc: UploadRejected) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=422)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse({"detail": "Validation error",
                             "errors": [{"loc": e["loc"], "msg": e["msg"]} for e in exc.errors()]}, status_code=422)

    for r in (auth, masterdata, invoices, documents, review, queue, knowledge, insights, system):
        app.include_router(r.router)
    return app


app = create_app()
