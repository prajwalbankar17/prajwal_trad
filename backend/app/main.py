"""FastAPI application entry point."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.router import api_router
from app.core import safety
from app.core.config import settings
from app.core.exceptions import AppError
from app.core.logging import configure_logging, get_logger

configure_logging()
log = get_logger("app")


@asynccontextmanager
async def lifespan(_: FastAPI):
    log.info(
        "startup",
        app=settings.APP_NAME,
        environment=settings.ENVIRONMENT,
        execution_mode=safety.execution_mode(),
        live_order_placement_possible=False,
    )
    yield
    log.info("shutdown")


app = FastAPI(
    title=settings.APP_NAME,
    version="0.1.0",
    description=(
        "AI-powered equity research and **paper trading** platform.\n\n"
        "**Live order execution is disabled in this build.** See `/api/v1/safety`."
    ),
    openapi_url=f"{settings.API_V1_PREFIX}/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(AppError)
async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
    if exc.status_code >= 500:
        log.error("app_error", code=exc.code, message=exc.message, details=exc.details)
    else:
        log.info("app_error", code=exc.code, message=exc.message)
    return JSONResponse(status_code=exc.status_code, content=exc.to_dict())


@app.exception_handler(Exception)
async def unhandled_handler(_: Request, exc: Exception) -> JSONResponse:
    log.exception("unhandled_error", error=str(exc))
    return JSONResponse(
        status_code=500,
        content={
            "code": "internal_error",
            "message": "An unexpected error occurred.",
            "details": {},
        },
    )


app.include_router(api_router, prefix=settings.API_V1_PREFIX)


@app.get("/", tags=["System"])
def root() -> dict:
    return {
        "app": settings.APP_NAME,
        "version": "0.1.0",
        "docs": "/docs",
        "api": settings.API_V1_PREFIX,
        "execution_mode": safety.execution_mode(),
        "live_order_placement_possible": False,
    }
