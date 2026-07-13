import json
import logging
import os

import redis

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("consumer")

REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
STREAM_KEY = os.getenv("STREAM_KEY", "game_logs")
GROUP_NAME = os.getenv("GROUP_NAME", "log_consumers")
CONSUMER_NAME = os.getenv("CONSUMER_NAME", "consumer-1")


def ensure_group(client: redis.Redis) -> None:
    try:
        client.xgroup_create(STREAM_KEY, GROUP_NAME, id="0", mkstream=True)
        logger.info(f"created group '{GROUP_NAME}'")
    except redis.ResponseError as e:
        if "BUSYGROUP" in str(e):
            logger.info(f"group '{GROUP_NAME}' already exists")
        else:
            raise


def main():
    client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
    ensure_group(client)
    logger.info(f"consumer started: stream={STREAM_KEY} group={GROUP_NAME}")

    processed = 0
    while True:
        resp = client.xreadgroup(
            groupname=GROUP_NAME,
            consumername=CONSUMER_NAME,
            streams={STREAM_KEY: ">"},
            count=1000,
            block=5000,
        )
        if not resp:
            continue

        for _stream, entries in resp:
            ack_ids = [entry_id for entry_id, _ in entries]
            client.xack(STREAM_KEY, GROUP_NAME, *ack_ids)
            processed += len(ack_ids)
            if processed % 1000 == 0 or len(ack_ids) < 1000:
                logger.info(f"consumed total={processed} (batch={len(ack_ids)})")


if __name__ == "__main__":
    main()