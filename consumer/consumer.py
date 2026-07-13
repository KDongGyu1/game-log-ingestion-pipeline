import json
import logging
import os
import socket
import time

import redis

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("consumer")

REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
STREAM_KEY = os.getenv("STREAM_KEY", "game_logs")
GROUP_NAME = os.getenv("GROUP_NAME", "log_consumers")
CONSUMER_NAME = os.getenv("CONSUMER_NAME", socket.gethostname())
PENDING_IDLE_MS = int(os.getenv("PENDING_IDLE_MS", "60000"))


def ensure_group(client: redis.Redis) -> None:
    try:
        client.xgroup_create(STREAM_KEY, GROUP_NAME, id="0", mkstream=True)
        logger.info(f"created group '{GROUP_NAME}'")
    except redis.ResponseError as e:
        if "BUSYGROUP" in str(e):
            logger.info(f"group '{GROUP_NAME}' already exists")
        else:
            raise


def ack_entries(client: redis.Redis, entries: list[tuple[str, dict]]) -> int:
    if not entries:
        return 0

    ack_ids = [entry_id for entry_id, _ in entries]
    client.xack(STREAM_KEY, GROUP_NAME, *ack_ids)
    return len(ack_ids)


def reclaim_stale_pending(client: redis.Redis) -> int:
    try:
        _next_id, entries, *_ = client.xautoclaim(
            name=STREAM_KEY,
            groupname=GROUP_NAME,
            consumername=CONSUMER_NAME,
            min_idle_time=PENDING_IDLE_MS,
            start_id="0-0",
            count=1000,
        )
    except redis.ResponseError as e:
        logger.warning(f"pending reclaim skipped: {e}")
        return 0

    claimed = ack_entries(client, entries)
    if claimed:
        logger.info(f"reclaimed and acked stale pending entries: {claimed}")
    return claimed


def main():
    client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
    ensure_group(client)
    logger.info(
        f"consumer started: stream={STREAM_KEY} group={GROUP_NAME} "
        f"consumer={CONSUMER_NAME} pending_idle_ms={PENDING_IDLE_MS}"
    )

    processed = 0
    while True:
        try:
            processed += reclaim_stale_pending(client)

            resp = client.xreadgroup(
                groupname=GROUP_NAME,
                consumername=CONSUMER_NAME,
                streams={STREAM_KEY: ">"},
                count=1000,
                block=5000,
            )
        except redis.RedisError as e:
            logger.warning(f"redis unavailable, retrying in 2s: {e}")
            time.sleep(2)
            continue

        for _stream, entries in resp:
            acked = ack_entries(client, entries)
            processed += acked
            if processed % 1000 == 0 or acked < 1000:
                logger.info(f"consumed total={processed} (batch={acked})")


if __name__ == "__main__":
    main()
