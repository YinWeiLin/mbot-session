import sys
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from config_agentscope import init_agentscope
from utils.logger import setup_logger
from server.routers import chat
from server.logger import setup_http_logger, get_http_logger
from server.response import fail

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FALLBACK_ERROR_MESSAGE = "本商家暂时不能服务，请谅解"


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_http_logger(PROJECT_ROOT)
    setup_logger(PROJECT_ROOT)
    init_agentscope()
    yield


app = FastAPI(
    title="mbot API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    logger = get_http_logger()
    logger.info(f"→ {request.method} {request.url.path}")
    response = await call_next(request)
    logger.info(f"← {request.method} {request.url.path} {response.status_code}")
    return response


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger = get_http_logger()
    logger.error(f"Unhandled exception on {request.url.path}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=200,
        content=fail(FALLBACK_ERROR_MESSAGE).model_dump(),
    )


app.include_router(chat.router, prefix="/api", tags=["对话"])


@app.get("/health")
async def health():
    return {"status": "ok"}
