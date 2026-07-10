import json
import logging
import os
import time
from contextlib import asynccontextmanager
from typing import Any, Dict

import redis
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

# ---------- Logging ----------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
logger = logging.getLogger("log-api")

# ---------- Config ----------
REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
STREAM_KEY = os.getenv("STREAM_KEY", "game_logs")
STREAM_MAXLEN = int(os.getenv("STREAM_MAXLEN", "1000000"))  # approximate cap

# ---------- Redis Client ----------
redis_client: redis.Redis | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global redis_client
    redis_client = redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        decode_responses=True,
        socket_connect_timeout=3,
        socket_timeout=3,
        health_check_interval=30,
    )
    # 시작 시 연결 확인
    for i in range(10):
        try:
            redis_client.ping()
            logger.info(f"Connected to Redis at {REDIS_HOST}:{REDIS_PORT}")
            break
        except redis.ConnectionError:
            logger.warning(f"Redis not ready, retry {i+1}/10")
            time.sleep(1)
    else:
        logger.error("Failed to connect to Redis after 10 retries")

    yield

    if redis_client:
        redis_client.close()
        logger.info("Redis connection closed")


app = FastAPI(title="Supercent Log Ingestion API", version="1.0.0", lifespan=lifespan)


# ---------- Routes ----------
@app.get("/health")
def health() -> Dict[str, Any]:
    """Liveness + Readiness. Redis 연결까지 확인."""
    try:
        redis_client.ping()
        return {"status": "healthy", "redis": "connected"}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"redis unavailable: {e}")


@app.post("/api/v1/logs")
async def ingest_log(request: Request):
    """
    JSON 로그를 받아 Redis Stream에 XADD.
    - 최소한의 검증만 수행 (스코프상 스키마는 유연하게 유지)
    - MAXLEN으로 스트림 크기 제한 (approximate)
    """
    try:
        payload = await request.json()
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="invalid JSON")

    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="payload must be a JSON object")

    try:
        # Stream 필드는 flat string-string이 관례. 원본 JSON은 data 필드에 통째로 저장.
        entry_id = redis_client.xadd(
            STREAM_KEY,
            {"data": json.dumps(payload, ensure_ascii=False)},
            maxlen=STREAM_MAXLEN,
            approximate=True,
        )
        return JSONResponse(
            status_code=200,
            content={"status": "ok", "stream": STREAM_KEY, "id": entry_id},
        )
    except redis.RedisError as e:
        logger.exception("Redis XADD failed")
        raise HTTPException(status_code=503, detail=f"queue unavailable: {e}")


@app.get("/api/v1/stats")
def stats():
    """운영 편의를 위한 간단한 스트림 현황 조회."""
    try:
        info = redis_client.xinfo_stream(STREAM_KEY)
        return {
            "length": info.get("length"),
            "first_entry": info.get("first-entry"),
            "last_entry": info.get("last-entry"),
            "groups": info.get("groups"),
        }
    except redis.ResponseError:
        return {"length": 0, "note": "stream not created yet"}