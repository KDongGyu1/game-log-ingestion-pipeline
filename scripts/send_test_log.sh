#!/usr/bin/env bash
# 단건 로그 전송 스크립트
# 사용법: ./scripts/send_test_log.sh
set -euo pipefail

URL="${URL:-http://localhost:8000/api/v1/logs}"

PAYLOAD=$(cat <<EOF
{
  "user_id": "u_${RANDOM}",
  "event": "item_purchase",
  "item_id": "sword_legendary_01",
  "gold": 500,
  "level": 42,
  "region": "ap-northeast-2",
  "ts": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
}
EOF
)

echo "▶ POST $URL"
echo "▶ Payload:"
echo "$PAYLOAD" | jq . 2>/dev/null || echo "$PAYLOAD"
echo ""
echo "▶ Response:"

curl -sS -X POST "$URL" \
  -H "Content-Type: application/json" \
  -d "$PAYLOAD" | jq . 2>/dev/null || cat
echo ""