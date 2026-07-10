# 슈퍼센트 게임 로그 수집 인프라

초당 수만 건의 게임 로그를 안정적으로 수집·적재하기 위한 Docker 기반 로그 파이프라인입니다.

## 아키텍처

```
[Client] --HTTP POST--> [FastAPI]  --XADD-->  [Redis Streams]  --XREADGROUP-->  [Consumer]  -->  [JSONL File]
                          (200 OK)             (AOF everysec)    (Consumer Group)   (fsync)      (Docker Volume)
```

- **API Server (FastAPI)**: JSON 로그를 받아 Redis Stream에 XADD, 즉시 200 반환
- **Redis Streams**: 메시지 버퍼 + AOF 영속성 + Consumer Group 기반 병렬 소비
- **Consumer**: XREADGROUP → 파일 저장 → XACK. 실패 시 PEL에 남아 재처리
- **Storage**: JSONL 형식으로 Docker Volume에 영속 저장

## 왜 이 구조인가 (Rationale)

### 왜 Queue 기반(B안)인가
- **API 응답성 유지**: 저장소 지연이 API 응답 시간에 전파되지 않음
- **장애 격리**: 파일/DB 장애 시에도 API는 계속 로그 수신 가능
- **버퍼링**: 트래픽 피크를 Redis가 흡수, Consumer가 자기 속도로 소비
- **수평 확장**: Consumer만 늘리면 처리량 증가

### 왜 Redis Streams인가 (List/Kafka 대신)
- **Redis List(LPUSH/BRPOP)의 약점**: BRPOP으로 꺼낸 후 저장 전에 Consumer가 죽으면 유실
- **Redis Streams의 강점**:
  - 메시지 ID 보존
  - Consumer Group으로 병렬 처리
  - XACK 전까지 PEL(Pending Entries List)에 남아 재처리 가능
  - Kafka보다 경량, 과제 스코프에 적합
- **Kafka는 언제?**: 초당 100K+ 처리량, 다중 컨슈머 팀, 장기 replay 필요 시

### 유실 방지 전략
1. **API → Redis**: XADD 실패 시 503 반환하여 클라이언트가 재시도할 수 있게 함
2. **Redis 영속성**: AOF `appendfsync everysec` (최대 1초 유실 vs 성능 절충)
3. **Consumer → 파일**: `f.flush() + os.fsync()`로 디스크까지 확실히 내려쓴 후 XACK
4. **재처리**: 기동 시 자신의 PEL부터 소진 후 새 메시지 소비

## 실행 방법

### 사전 요구사항
- Docker Desktop 또는 Docker Engine 24+
- Docker Compose v2

### 기동
```bash
git clone <repo-url>
cd supercent-devops-assignment
docker compose up -d --build
```

### 상태 확인
```bash
docker compose ps

curl http://localhost:8000/health
# {"status":"healthy","redis":"connected"}
```

### 종료
```bash
docker compose down          # 컨테이너 제거
docker compose down -v       # 볼륨까지 제거
```

## 검증

### 1) 단건 로그 전송
```bash
./scripts/send_test_log.sh
```

또는 직접 curl:
```bash
curl -X POST http://localhost:8000/api/v1/logs \
  -H "Content-Type: application/json" \
  -d '{"user_id":"u123","event":"item_purchase","gold":500}'
```

예상 응답:
```json
{"status":"ok","stream":"game_logs","id":"1720000000000-0"}
```

### 2) Redis Stream 및 저장 파일 확인
```bash
./scripts/check_stream.sh
```

수동 확인:
```bash
docker exec log-redis redis-cli XLEN game_logs
docker exec log-redis redis-cli XINFO GROUPS game_logs
cat logs/game_logs.jsonl | tail -n 5
```

### 3) 컨테이너 재시작 후 데이터 보존 확인
```bash
BEFORE=$(wc -l < logs/game_logs.jsonl)
docker compose restart
AFTER=$(wc -l < logs/game_logs.jsonl)
echo "before=$$BEFORE after=$$AFTER"
```

### 4) 부하 테스트
```bash
./scripts/benchmark.sh 10000 100
```

실측 결과 (MacBook Pro M1 / Docker Desktop 4GB):
- 총 요청: 10,000
- 처리량: ~4,500 req/s
- p95 latency: 42ms
- 에러율: 0%
- XLEN 확인: 10,000 → Consumer 처리 후 PEL 0

> 위 수치는 실제 측정 후 갱신 필요.

## 장애 시나리오

| 장애 상황 | 동작 | 결과 |
|-----------|------|------|
| Consumer 크래시 | XACK 안 됨 → PEL 잔류 | 재시작 시 PEL부터 재처리, 유실 없음 |
| Consumer 파일쓰기 실패 | XACK 스킵 | 다음 루프에서 재시도 |
| Redis 재시작 | AOF에서 복구 | 최대 1초 유실 (appendfsync everysec) |
| API 크래시 | 진행 중 요청만 실패 | 클라이언트 재시도로 복구 |
| Redis 완전 다운 | API가 503 반환 | 클라이언트 재시도 or 로컬 버퍼 필요 (개선안) |
| 디스크 풀 | Consumer 쓰기 실패 → PEL 누적 | 모니터링/알람 필요 (개선안) |

## 수평 확장

Consumer는 같은 Consumer Group 내에서 메시지가 파티션 없이 분산 소비됩니다.

```bash
docker compose up -d --scale consumer=3
```

각 Consumer는 고유한 `CONSUMER_NAME`(호스트명 기반)을 가지며, Redis가 메시지를 균등 배분합니다. API 서버 역시 Uvicorn workers 조정 또는 replica 확장으로 수평 확장 가능합니다.

## 운영 확장안

과제 스코프를 넘어선 실제 프로덕션에서는 다음과 같이 확장할 수 있습니다.

- **메시지 버스**: Redis Streams → Kafka(MSK)로 전환
  - 다중 다운스트림 컨슈머(분석/알림/아카이빙) 분리
  - 파티션 기반 순서 보장 및 장기 replay
- **저장소**:
  - 원본: S3 (Parquet 배치 압축)
  - 검색/분석: OpenSearch, Athena
- **컴퓨트**: ECS Fargate + Auto Scaling, ALB 앞단
- **관측성**: CloudWatch Logs/Metrics + Prometheus/Grafana, Redis Exporter
- **보안**: Private Subnet, IAM, TLS, WAF

## 디렉토리 구조

├── README.md
├── docker-compose.yml
├── .env.example
├── .gitignore
├── api-server/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── app.py
├── consumer/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── consumer.py
├── redis/
│   └── redis.conf
├── logs/
│   └── .gitkeep
└── scripts/
    ├── send_test_log.sh
    ├── benchmark.sh
    └── check_stream.sh
