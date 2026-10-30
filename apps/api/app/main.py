import asyncio
import json
import logging
import uuid
from contextlib import asynccontextmanager

from arq import create_pool
from arq.connections import RedisSettings
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import router
from app.core.config import production_problems, settings
from app.security.auth import hasher

logger = logging.getLogger("researchos")
logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app):
    if problems := production_problems(settings()):
        raise RuntimeError("Unsafe production configuration: " + "; ".join(problems))
    app.state.dummy_hash = await asyncio.to_thread(hasher.hash, uuid.uuid4().hex)
    app.state.redis = await create_pool(RedisSettings.from_dsn(settings().redis_url))
    yield
    await app.state.redis.aclose()


app = FastAPI(title="ResearchOS", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings().public_origin],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Content-Type", "X-CSRF-Token", "Last-Event-ID"],
)
app.include_router(router)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    request_id = str(uuid.uuid4())
    try:
        if request.url.path.startswith("/api/"):
            # Apply admission control before authentication. Client-controlled cookies
            # must never create fresh buckets (nor trust unconfigured proxy headers).
            key = request.client.host if request.client else "unknown"
            from app.security.guards import digest

            limit_key = f"rate:client:{digest(key)}"
            count = await request.app.state.redis.incr(limit_key)
            if count == 1:
                await request.app.state.redis.expire(limit_key, 60)
            if count > settings().max_requests_per_minute:
                return JSONResponse({"detail": "Rate limit exceeded"}, 429, headers={"Retry-After": "60"})
        response = await call_next(request)
    except Exception:
        logger.exception(json.dumps({"request_id": request_id, "path": request.url.path, "status": "failed"}))
        return JSONResponse({"detail": "Service unavailable", "request_id": request_id}, 503)
    response.headers.update(
        {
            "X-Request-ID": request_id,
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "Referrer-Policy": "strict-origin-when-cross-origin",
            "Cache-Control": "no-store",
        }
    )
    logger.info(json.dumps({"request_id": request_id, "path": request.url.path, "status": response.status_code}))
    return response


@app.get("/health")
async def health():
    return {"status": "ok"}
