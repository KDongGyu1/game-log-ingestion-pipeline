import json
import logging
import os
import signal
import socket
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import redis

# ---------- Logging ----------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
logger = logging.getLogger("log-consumer")

# ---------- Config ----------
REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
STREAM_KEY = os.getenv("STREAM_KEY", "game_logs")
GROUP_NAME = os.getenv("GROUP_NAME", "log_consumers")
CONSUMER_NAME = os.getenv("CONSUMER_NAME", f"consumer-{socket.gethostname()}")
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "100"))
BLOCK_MS = int(os.getenv("BLOCK_MS", "5000"))
OUTPUT_PATH = Path(os.getenv("OUTPUT_PATH", "/logs/game_logs.jsonl"))

# ---------- Graceful Shutdown ----------
_shutdown = False


def _handle_signal(signum, frame):
    global _shutdown
    logger.info(f"Signal {signum} received, shutting down gracefully...")
    _shutdown = True


signal.signal(signal.SIGTERM, _handle_signal)
signal.signal(signal.SIGINT, _handle_signal)


# ---------- Helpers ----------
def connect_redis() -> redis.Redis:
    for i in range(30):
        try:
            client = redis.Redis(
                host=REDIS_HOST,
                port=REDIS_PORT,
                decode_responses=True,
                socket_connect_timeout=3,
            )
            client.ping()
            logger.info(f"Connected to Redis at {REDIS_HOST}:{REDIS_PORT}")
            return client
        except redis.ConnectionError:
            logger.warning(f"Waiting for Redis... ({i+1}/30)")
            time.sleep(2)
    logger.error("Cannot connect to Redis")
    sys.exit(1)


def ensure_group(client: redis.Redis) -> None:
    """Consumer Group을 idempotent하게 생성."""
    try:
        client.xgroup_create(STREAM_KEY, GROUP_NAME, id="0", mkstream=True)
        logger.info(f"Created consumer group '{GROUP_NAME}' on '{STREAM_KEY}'")
    except redis.ResponseError as e:
        if "BUSYGROUP" in str(e):
            logger.info(f"Consumer group '{GROUP_NAME}' already exists")
        else:
            raise


def ensure_output_dir():
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)


def persist(entries) -> list[str]:
    """
    entries: [(id, {"data": "<json>"}), ...]
    파일에 성공적으로 쓴 id 리스트를 반환 (XACK 대상).
    실패 시 ack하지 않아 PEL에 남아 다음 루프에서 재처리됨.
    """
    if not entries:
        return []

    acked_ids: list[str] = []
    try:
        with OUTPUT_PATH.open("a", encoding="utf-8") as f:
            for entry_id, fields in entries:
                raw = fields.get("data", "{}")
                try:
                    original = json.loads(raw)
                except json.JSONDecodeError:
                    original = {"_raw": raw}

                record = {
                    "stream_id": entry_id,
                    "received_at": datetime.now(timezone.utc).isoformat(),
                    "consumer": CONSUMER_NAME,
                    "data": original,
                }
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
                acked_ids.append(entry_id)
            f.flush()
            os.fsync(f.fileno())  # 디스크 flush로 유실 최소화
        return acked_ids
    except OSError as e:
        logger.exception(f"Failed to write logs: {e}")
        # 이미 write까지 성공한 부분만 반환 (부분 성공 허용)
        return acked_ids


def consume_pending(client: redis.Redis) -> int:
    """
    기동 시 자기 이름으로 남아있던 PEL(Pending Entries List)부터 처리.
    이전에 크래시로 XACK하지 못한 메시지를 우선 재처리하여 유실 방지.
    """
    processed = 0
    last_id = "0"
    while not _shutdown:
        resp = client.xreadgroup(
            groupname=GROUP_NAME,
            consumername=CONSUMER_NAME,
            streams={STREAM_KEY: last_id},
            count=BATCH_SIZE,
            block=None,  # non-blocking: PEL이 비면 즉시 종료
        )
        if not resp:
            break

        empty_all = True
        for _stream, entries in resp:
            if not entries:
                continue
            empty_all = False
            acked = persist(entries)
            if acked:
                client.xack(STREAM_KEY, GROUP_NAME, *acked)
                processed += len(acked)
                last_id = acked[-1]

        if empty_all:
            break

    if processed:
        logger.info(f"Recovered {processed} pending messages from PEL")
    return processed


def consume_new(client: redis.Redis):
    """새 메시지를 blocking으로 소비."""
    while not _shutdown:
        try:
            resp = client.xreadgroup(
                groupname=GROUP_NAME,
                consumername=CONSUMER_NAME,
                streams={STREAM_KEY: ">"},  # 새 메시지만
                count=BATCH_SIZE,
                block=BLOCK_MS,
            )
        except redis.ConnectionError as e:
            logger.warning(f"Redis connection error: {e}, retrying in 2s")
            time.sleep(2)
            continue

        if not resp:
            continue  # timeout: shutdown 플래그 재확인 후 다시 대기

        for _stream, entries in resp:
            if not entries:
                continue
            acked = persist(entries)
            if acked:
                try:
                    client.xack(STREAM_KEY, GROUP_NAME, *acked)
                    logger.info(f"Processed & acked {len(acked)} messages")
                except redis.RedisError as e:
                    logger.error(f"XACK failed: {e}")


def main():
    logger.info(
        f"Starting consumer '{CONSUMER_NAME}' "
        f"stream='{STREAM_KEY}' group='{GROUP_NAME}' "
        f"output='{OUTPUT_PATH}'"
    )
    ensure_output_dir()
    client = connect_redis()
    ensure_group(client)

    # 1) PEL 재처리 먼저
    consume_pending(client)

    # 2) 새 메시지 blocking 소비
    consume_new(client)

    logger.info("Consumer stopped cleanly")


if __name__ == "__main__":
    main()