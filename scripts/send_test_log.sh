#!/usr/bin/env bash
# 단건 로그 전송 테스트
set -euo pipefail

URL="${URL:-http://localhost:8000/api/v1/logs}"

curl -sS -X POST "$URL" \
  -H "Content-Type: application/json" \
  -d '{"user_id":"u123","event":"item_purchase","gold":500}'
echo ""