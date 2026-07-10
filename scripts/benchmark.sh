#!/usr/bin/env bash
# 로그 API 부하 테스트 스크립트
# 사용법: ./scripts/benchmark.sh [requests] [concurrency]
# 예:    ./scripts/benchmark.sh 100000 200
set -euo pipefail

REQUESTS="${1:-10000}"
CONCURRENCY="${2:-100}"
URL="${URL:-http://localhost:8000/api/v1/logs}"

if ! command -v hey >/dev/null 2>&1; then
  echo "❌ 'hey'가 설치되어 있지 않습니다."
  echo "   macOS: brew install hey"
  echo "   Go:    go install github.com/rakyll/hey@latest"
  exit 1
fi

PAYLOAD_FILE="$(mktemp)"
cat > "$PAYLOAD_FILE" <<EOF
{"user_id":"u_bench","event":"item_purchase","item_id":"sword_01","gold":500,"level":42,"region":"ap-northeast-2"}
EOF

echo "▶ Target      : $URL"
echo "▶ Requests    : $REQUESTS"
echo "▶ Concurrency : $CONCURRENCY"
echo ""

hey -n "$REQUESTS" -c "$CONCURRENCY" -m POST \
    -H "Content-Type: application/json" \
    -D "$PAYLOAD_FILE" \
    "$URL"

rm -f "$PAYLOAD_FILE"

echo ""
echo "▶ 검증: docker exec log-redis redis-cli XLEN game_logs"