import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

import redis

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("consumer")

REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
STREAM_KEY = os.getenv("STREAM_KEY", "game_logs")
GROUP_NAME = os.getenv("GROUP_NAME", "log_consumers")
CONSUMER_NAME = os.getenv("CONSUMER_NAME", "consumer-1")
OUTPUT_PATH = Path(os.getenv("OUTPUT_PATH", "/logs/game_logs.jsonl"))


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
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
    ensure_group(client)
    logger.info(f"consumer started: stream={STREAM_KEY} group={GROUP_NAME}")

    while True:
        resp = client.xreadgroup(
            groupname=GROUP_NAME,
            consumername=CONSUMER_NAME,
            streams={STREAM_KEY: ">"},
            count=100,
            block=5000,
        )
        if not resp:
            continue

        for _stream, entries in resp:
            ack_ids = []
            with OUTPUT_PATH.open("a", encoding="utf-8") as f:
                for entry_id, fields in entries:
                    record = {
                        "stream_id": entry_id,
                        "received_at": datetime.now(timezone.utc).isoformat(),
                        "data": json.loads(fields.get("data", "{}")),
                    }
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")
                    ack_ids.append(entry_id)

            if ack_ids:
                client.xack(STREAM_KEY, GROUP_NAME, *ack_ids)
                logger.info(f"acked {len(ack_ids)} messages")


if __name__ == "__main__":
    main()