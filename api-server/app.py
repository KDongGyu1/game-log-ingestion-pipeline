import json
import logging
import os

import redis
from fastapi import FastAPI, HTTPException, Request

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("api")

REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
STREAM_KEY = os.getenv("STREAM_KEY", "game_logs")

app = FastAPI(title="Game Log Ingestion API")
r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)


@app.get("/health")
def health():
    try:
        r.ping()
        return {"status": "healthy"}
    except redis.RedisError:
        raise HTTPException(status_code=503, detail="redis unavailable")


@app.post("/api/v1/logs")
async def ingest_log(request: Request):
    try:
        payload = await request.json()
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="invalid JSON")

    try:
        entry_id = r.xadd(STREAM_KEY, {"data": json.dumps(payload, ensure_ascii=False)})
        return {"status": "ok", "id": entry_id}
    except redis.RedisError as e:
        logger.exception("XADD failed")
        raise HTTPException(status_code=503, detail=f"queue unavailable: {e}")