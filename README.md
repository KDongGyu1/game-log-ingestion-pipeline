# 게임 로그 수집 파이프라인

슈퍼센트 DevOps 엔지니어(전환형 인턴) 과제 제출본.

초당 수만 건의 인게임 로그(유저 행동, 재화 소비, 시스템 에러 등)를 안정적으로 수집·적재하기 위한 Docker 기반 파이프라인입니다.

## 아키텍처

```
[Client] --HTTP POST--> [FastAPI]  --XADD-->  [Redis Streams (AOF)]  --XREADGROUP-->  [Consumer]
  (외부)     :8000       (200 OK)              (버퍼 + 영속화)          (Consumer Group, XACK)
```

- **API Server (FastAPI)**: `/api/v1/logs` POST 수신 → Redis Stream에 XADD → 즉시 200 반환
- **Redis Streams**: 메시지 큐 + AOF 영속화. 컨테이너 재시작 시에도 데이터 유지
- **Consumer**: XREADGROUP으로 읽고 XACK 처리. 오래 pending 된 메시지는 XAUTOCLAIM으로 회수해 재처리

## 선택 이유 (Rationale) — B안 (Queue 기반)

### 시나리오 분석

과제 시나리오는 다음을 요구합니다.

- **초당 수만 건의 인게임 로그**
- **안정적, 유실 없는 적재**
- **대량의 글로벌 트래픽 대응**

이 조건에서 핵심은 **API 응답성과 저장소 처리의 분리(decoupling)**입니다. 저장소 지연이 API 응답에 그대로 전파되면 트래픽 피크에서 API가 붕괴합니다.

### 대안 비교 (인프라 엔지니어 관점)

| 항목 | A안 (File 직접) | **B안 (Queue)** | C안 (DB 직접) |
|---|---|---|---|
| API 응답성 | 디스크 I/O에 묶임 | **큐잉 후 즉시 응답** | DB 쓰기에 묶임 |
| 트래픽 피크 흡수 | ❌ | **✅ Queue 버퍼링** | ❌ DB 부하 직결 |
| 장애 격리 | ❌ | **✅ 저장소 장애와 격리** | ❌ DB 장애 = API 장애 |
| 수평 확장 | 파일락 이슈 | **✅ Consumer 확장** | DB 부하 병목 |
| 유실 방지 | flush 정책 의존 | **✅ ACK 기반 재처리** | 트랜잭션 실패 시 유실 |

### 왜 Redis Streams인가 (List / Kafka 대신)

- **Redis List (LPUSH/BRPOP)의 약점**: BRPOP으로 꺼낸 후 처리 전 Consumer 크래시 시 **유실**
- **Redis Streams의 강점**:
  - Consumer Group 기반 병렬 처리
  - **XACK 전까지 PEL(Pending Entries List)에 남고, XAUTOCLAIM으로 회수 가능 → 유실 방지**
  - AOF 활성화로 재시작 후 데이터 복구
  - Kafka보다 경량, 과제 스코프에 적합
- **Kafka는 언제?**: 초당 100K+, 다중 다운스트림 컨슈머, 장기 replay 필요 시. 과제 스코프 초과.

### 유실 방지 3중 방어

1. **API → Redis**: XADD 실패 시 503 반환 → 클라이언트 재시도 유도
2. **Redis 영속성**: AOF 활성화 (`--appendonly yes`)로 재시작 시 복구
3. **Consumer**: XACK 기반 소비. 처리 실패 시 PEL에 남고, 60초 이상 pending 상태인 메시지는 다른 Consumer가 XAUTOCLAIM으로 회수

## 실행 방법

### 사전 요구사항

- Docker Desktop 또는 Docker Engine 24+
- Docker Compose v2

### 기동

동료 엔지니어가 처음부터 동일한 테스트 환경을 복제하는 한 줄 명령:

```bash
git clone https://github.com/KDongGyu1/game-log-ingestion-pipeline.git && cd game-log-ingestion-pipeline && docker compose up -d --build
```

이미 저장소를 받은 상태라면 아래 한 줄로 전체 환경을 기동합니다.

```bash
docker compose up -d --build
```

### 상태 확인

```bash
docker compose ps
curl http://localhost:8000/health
# {"status":"healthy"}
```

### 로그 전송

```bash
curl -X POST http://localhost:8000/api/v1/logs \
  -H "Content-Type: application/json" \
  -d '{"user_id":"u123","event":"item_purchase","gold":500}'
```

### 종료

```bash
docker compose down       # 컨테이너만 제거
docker compose down -v    # 볼륨까지 제거 (데이터 초기화)
```

## 검증 결과

### 1) 헬스체크

```
$ curl http://localhost:8000/health
{"status":"healthy"}
```

### 2) 단건 로그 전송

```
$ curl -X POST http://localhost:8000/api/v1/logs \
    -H "Content-Type: application/json" \
    -d '{"user_id":"u123","event":"item_purchase","gold":500}'
{"status":"ok","id":"1783653733510-0"}
```

### 3) 대량 트래픽 부하 테스트

동시 연결 100개로 10,000건 요청:

```
$ docker run --rm --network game-log-ingestion-pipeline_log-net alpine/bombardier \
    -c 100 -n 10000 -m POST \
    -H "Content-Type: application/json" \
    -b '{"user_id":"u_bench","event":"purchase","gold":500}' \
    http://api:8000/api/v1/logs

Bombarding http://api:8000/api/v1/logs with 10000 request(s) using 100 connection(s)
 10000 / 10000  100.00% 711/s 14s
Done!
Statistics        Avg      Stdev        Max
  Reqs/sec       712.88     213.53    1064.39
  Latency      139.37ms    18.53ms   223.69ms
  HTTP codes:
    1xx - 0, 2xx - 10000, 3xx - 0, 4xx - 0, 5xx - 0
  Throughput:   232.57KB/s
```

- **성공률 100%** (2xx: 10,000 / 5xx: 0)
- **평균 처리량**: 712 req/s (단일 인스턴스, Docker Desktop 환경)

> **처리량 해석**: 본 벤치마크는 로컬 Docker Desktop 환경에서 단일 Uvicorn 워커, 동기 Redis 클라이언트로 측정한 값입니다. 프로덕션에서 "초당 수만 건" 달성을 위한 확장 경로는 아래 [운영 확장안](#운영-확장안) 참조.

### 4) Redis Stream 적재 확인

```
$ docker exec log-redis redis-cli XLEN game_logs
10000
```

### 5) Consumer 소비 확인

```
$ docker exec log-redis redis-cli XINFO GROUPS game_logs
name              log_consumers
consumers         1
pending           0
last-delivered-id 1783654580725-0
entries-read      10000
lag               0
```

**pending 0, lag 0** → 10,000건 전부 유실 없이 XACK 완료.

### 6) 재시작 후 유실 없음 검증

```
$ docker exec log-redis redis-cli XLEN game_logs
10000

$ docker compose restart

$ docker exec log-redis redis-cli XLEN game_logs
10000
```

**Redis AOF 활성화로 컨테이너 재시작 후에도 10,000건 데이터 그대로 유지.**

## 장애 시나리오

| 장애 상황 | 동작 | 결과 |
|---|---|---|
| Consumer 크래시 | XACK 안 됨 → PEL 잔류 | 재시작 또는 다른 Consumer가 XAUTOCLAIM으로 회수 후 재처리 |
| Redis 재시작 | AOF에서 복구 | 최대 1초 유실 (`appendfsync everysec` 기본값) |
| API 크래시 | 진행 중 요청만 실패 | 클라이언트 재시도로 복구 |
| Redis 완전 다운 | API가 503 반환 | 클라이언트 재시도 필요 |

## 운영 확장안

과제 스코프를 넘어선 실제 프로덕션 환경에서 "초당 수만 건" 달성 경로:

### API 서버 수평 확장
- Uvicorn workers를 vCPU 수만큼 (`--workers N`)
- `redis.asyncio`로 비동기 I/O 전환
- ECS Fargate + ALB로 인스턴스 오토스케일링

### 메시지 브로커 확장
- Redis Streams → Kafka(MSK)로 전환 (초당 100K+, 다중 다운스트림, 장기 replay 필요 시)
- 파티셔닝으로 순서 보장 + 처리량 확보

### 저장소 확장
- Consumer → S3 (Parquet 배치 압축, 원본 아카이빙)
- Consumer → OpenSearch (실시간 검색/분석)
- Consumer → Athena/Redshift (배치 분석)

### 관측성
- CloudWatch Logs/Metrics + Prometheus/Grafana
- Redis Exporter로 큐 길이, PEL 크기 모니터링
- API 서버 p95/p99 레이턴시 알람

### 수평 확장 (현재 스택에서 즉시 가능)
```bash
docker compose up -d --scale consumer=3
```
Consumer Group이 자동으로 메시지를 분산 소비합니다.

## 디렉토리 구조

.
├── README.md
├── docker-compose.yml
├── .gitignore
├── .gitattributes
├── api-server/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── app.py
├── consumer/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── consumer.py
├── scripts/
│   └── send_test_log.sh
└── terraform/              
    ├── README.md
    ├── main.tf
    ├── variables.tf
    ├── vpc.tf
    ├── security.tf
    ├── alb.tf
    ├── ecs.tf
    ├── redis.tf
    └── outputs.tf

## 기술 스택

| 구성 요소 | 기술 | 이유 |
|---|---|---|
| API 서버 | FastAPI + Uvicorn | 비동기 지원, 경량, 개발 속도 |
| 메시지 브로커 | Redis Streams | Consumer Group + AOF, Kafka 대비 경량 |
| Consumer | Python + redis-py | 브로커와 동일 스택 유지 |
| 오케스트레이션 | Docker Compose | 재현성, 단일 명령 기동 |
