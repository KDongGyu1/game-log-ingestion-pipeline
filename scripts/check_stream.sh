#!/usr/bin/env bash
# Redis Stream / Consumer Group 상태 점검 스크립트
set -euo pipefail

CONTAINER="${CONTAINER:-log-redis}"
STREAM="${STREAM:-game_logs}"
GROUP="${GROUP:-log_consumers}"

echo "═══ Stream 요약: $STREAM ═══"
docker exec "$CONTAINER" redis-cli XLEN "$STREAM" | \
  xargs -I{} echo "총 메시지 수 (XLEN): {}"

echo ""
echo "═══ Consumer Group: $GROUP ═══"
docker exec "$CONTAINER" redis-cli XINFO GROUPS "$STREAM" || \
  echo "(그룹이 아직 생성되지 않았습니다)"

echo ""
echo "═══ Consumer 목록 ═══"
docker exec "$CONTAINER" redis-cli XINFO CONSUMERS "$STREAM" "$GROUP" || \
  echo "(컨슈머가 아직 등록되지 않았습니다)"

echo ""
echo "═══ 저장된 로그 파일 라인 수 ═══"
if [ -f ./logs/game_logs.jsonl ]; then
  wc -l ./logs/game_logs.jsonl
else
  echo "(logs/game_logs.jsonl 없음)"
fi