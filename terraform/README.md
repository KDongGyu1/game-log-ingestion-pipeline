# AWS 인프라 설계 및 Terraform (선택 과제)

필수 과제에서 구축한 로그 수집 파이프라인을 **AWS 프로덕션 환경**으로 확장하기 위한 인프라 설계안 및 Terraform 코드입니다.

> **참고**: 과제 요구사항에 따라 **실제 리소스는 프로비저닝하지 않으며**, 설계안과 IaC 코드만 제출합니다.

## 아키텍처 다이어그램

```
                              [ Internet ]
                                    │
                                    ▼
                            ┌──────────────┐
                            │  Route 53    │  (선택)
                            └──────┬───────┘
                                   │
                    ┌──────────────▼──────────────┐
                    │            ALB              │  ← Public Subnet (AZ-a, AZ-c)
                    │      (HTTP → :80)           │     외부 트래픽 진입점
                    └──────────────┬──────────────┘
                                   │
              ┌────────────────────┼────────────────────┐
              │                                         │
     ┌────────▼────────┐                       ┌────────▼────────┐
     │   ECS Fargate   │                       │   ECS Fargate   │
     │   API Task      │                       │   API Task      │  ← Private Subnet
     │   (AZ-a)        │                       │   (AZ-c)        │     Auto Scaling
     └────────┬────────┘                       └────────┬────────┘
              │                                         │
              └────────────────────┬────────────────────┘
                                   │  (XADD)
                                   ▼
                       ┌───────────────────────┐
                       │  ElastiCache Redis    │  ← Private Subnet (Multi-AZ)
                       │  (Streams + Backup)   │     Primary + Replica
                       │  Multi-AZ Failover    │
                       └───────────┬───────────┘
                                   │  (XREADGROUP)
                                   ▼
                       ┌───────────────────────┐
                       │   ECS Fargate         │  ← Private Subnet
                       │   Consumer Task       │     Auto Scaling
                       └───────────┬───────────┘
                                   │
                       ┌───────────▼───────────┐
                       │        S3             │  ← 원본 로그 아카이빙
                       │  (Parquet, Lifecycle) │     장기 보관
                       └───────────────────────┘

  ┌──────────────────────────────────────────────────────────────┐
  │  Observability: CloudWatch Logs / Metrics / Alarms           │
  │  Networking:    NAT Gateway (Private → Internet)             │
  │  Security:      IAM Roles, Security Groups (계층적 접근 제어)│
  └──────────────────────────────────────────────────────────────┘
```

## 설계 원칙

### 1. Multi-AZ 부하 분산
- 2개 가용 영역(`ap-northeast-2a`, `ap-northeast-2c`)에 리소스 분산
- 단일 AZ 장애 시에도 서비스 지속

### 2. Public / Private Subnet 분리
| Subnet | 리소스 | 목적 |
|---|---|---|
| Public | ALB, NAT Gateway | 외부 트래픽 진입점 |
| Private | ECS Task, ElastiCache | 인터넷 직접 노출 금지, 보안 강화 |

### 3. 관리형 서비스 우선
- **ECS Fargate**: EC2 관리 부담 제거, 컨테이너 오케스트레이션 완전 관리형
- **ElastiCache Redis**: Redis 운영 부담 제거, Multi-AZ 자동 페일오버
- **ALB**: L7 로드밸런서, 헬스체크 및 SSL 종단 처리

### 4. Auto Scaling
- ECS Service Auto Scaling으로 CPU 70% 임계치 기반 확장
- min 2 → max 10 태스크로 트래픽 피크 흡수

### 5. 보안 계층화
- Security Group으로 최소 권한 원칙 적용
  - ALB: 외부 → 80 허용
  - ECS: ALB에서만 8000 허용
  - Redis: ECS에서만 6379 허용
- Private Subnet의 아웃바운드는 NAT Gateway 경유

## 필수 과제와의 매핑

| 필수 과제 (로컬) | AWS 프로덕션 매핑 |
|---|---|
| FastAPI 컨테이너 | ECS Fargate Task (API) |
| Redis Streams (Docker) | ElastiCache for Redis (Multi-AZ) |
| Consumer 컨테이너 | ECS Fargate Task (Consumer) |
| Docker Volume (AOF) | ElastiCache 자동 백업 + S3 아카이빙 |
| Docker Network | VPC + Security Group |
| localhost:8000 | ALB DNS (Route53 도메인) |

## Terraform 파일 구조

```
terraform/
├── main.tf              # Provider 설정, 백엔드
├── variables.tf         # 변수 정의
├── vpc.tf               # VPC, Subnet, IGW, NAT Gateway, Route Table
├── security.tf          # Security Group (ALB, ECS, Redis)
├── alb.tf               # ALB, Target Group, Listener
├── ecs.tf               # ECS Cluster, Task Definition, Service, Auto Scaling, IAM
├── redis.tf             # ElastiCache Redis, Subnet Group
├── outputs.tf           # 출력값
└── README.md            # 본 문서
```

## 코드화 범위

### ✅ Terraform 코드로 구현
- VPC, Subnet (Public/Private × 2AZ)
- Internet Gateway, NAT Gateway, Route Table
- Security Group (ALB, ECS Task, Redis)
- ALB, Target Group, HTTP Listener
- ECS Cluster, Task Definition, Service (API)
- ECS Auto Scaling (CPU 기반)
- ElastiCache Redis Replication Group (Multi-AZ, Automatic Failover)
- CloudWatch Log Group
- IAM Role (ECS Task Execution, Task Role)

### 📋 설계만 서술 (코드 생략)
과제 요구인 "일부 핵심 인프라"에 집중하기 위해 아래 항목은 설계만 문서화합니다.

- **Consumer ECS Service**: API Service와 동일한 패턴으로 확장 가능 (Task Definition의 이미지와 command만 다름).
- **S3 아카이빙**: `aws_s3_bucket` + Lifecycle Policy로 90일 후 Glacier 전환.
- **Route53**: `aws_route53_record`로 ALB Alias 레코드 생성.
- **ACM**: HTTPS를 위한 인증서 발급 및 ALB Listener 연동.
- **ECR**: API/Consumer 이미지 저장소.

## 실행 절차 (참고용)

> 실제 apply는 하지 않지만, 재현성을 위한 절차입니다.

### 1. 사전 요구사항
```bash
# Terraform 설치
terraform --version   # >= 1.5.0

# AWS CLI 자격 증명 설정
aws configure
```

### 2. 초기화 및 검증
```bash
cd terraform

# 프로바이더 다운로드
terraform init

# 문법 검증
terraform validate

# 포맷 정리
terraform fmt

# 실행 계획 확인 (실제 생성 없음)
terraform plan -var 'api_image=123456789012.dkr.ecr.ap-northeast-2.amazonaws.com/game-log-api:latest'
```

### 3. 실제 배포 (본 과제에서는 실행하지 않음)
```bash
# 리소스 생성
terraform apply

# 리소스 삭제
terraform destroy
```

### 4. 이미지 준비 (실제 배포 시)
```bash
# ECR 리포지토리에 이미지 푸시 후 api_image 변수로 이미지 URI를 전달
terraform plan -var 'api_image=123456789012.dkr.ecr.ap-northeast-2.amazonaws.com/game-log-api:latest'
```

## 주요 설계 판단 근거

### 왜 ECS Fargate인가 (EC2 대신)
- **관리 부담 최소화**: 인프라 엔지니어가 EC2 패치, AMI 관리 등에서 해방
- **초당 과금**: 트래픽 없는 시간에 비용 절감
- **Auto Scaling과 궁합**: Task 수 조정만으로 수평 확장
- **EKS는 오버킬**: 과제 스코프에서 K8s 학습 비용 대비 이점 낮음

### 왜 ElastiCache Redis인가 (셀프 호스팅 Redis 대신)
- **Multi-AZ 자동 페일오버**: Primary 장애 시 Replica가 승격
- **자동 백업**: 스냅샷 자동 생성 및 S3 저장
- **패치/업그레이드 관리**: AWS가 무중단 유지보수 수행
- **모니터링 통합**: CloudWatch 메트릭 기본 제공

### 왜 NAT Gateway (NAT Instance 대신)
- **관리형 서비스**: 고가용성 자동 보장 (AZ 내 다중화)
- **처리량 자동 확장**: 최대 45 Gbps
- **트레이드오프**: 비용이 높음 → 실제 운영에서는 AZ별 1개씩 배치하여 AZ 간 트래픽 비용 최소화

### 왜 단일 NAT Gateway로 시작하는가
- 본 Terraform 코드는 **비용 최적화**를 위해 단일 NAT 사용
- **HA 필요 시**: `aws_nat_gateway`를 AZ 개수만큼 생성하고 `aws_route_table.private`도 AZ별로 분리
- 실제 프로덕션 이전 시 이 부분을 우선 개선 항목으로 문서화

## 확장 로드맵

### Phase 1 (현재 설계)
- Multi-AZ ECS + ElastiCache Redis Streams
- ALB + Auto Scaling
- CloudWatch 기본 관측성

### Phase 2 (트래픽 증가 시)
- **Consumer 세분화**: 분석용/아카이빙용/알림용으로 분리
- **S3 → Athena/Redshift**: 배치 분석 파이프라인
- **OpenSearch**: 실시간 로그 검색

### Phase 3 (초당 100K+ 도달 시)
- **ElastiCache → MSK (Kafka)**: 파티셔닝 기반 처리량 확보
- **Kinesis Data Firehose**: S3 자동 배치 적재
- **Multi-Region**: DR 및 글로벌 유저 대응


## 보안 고려사항

| 항목 | 현재 설계 | 프로덕션 강화 방향 |
|---|---|---|
| 통신 암호화 | HTTP (ALB) | ACM + HTTPS Listener + TLS 1.3 |
| ElastiCache | VPC 격리 | Auth Token + In-transit Encryption |
| IAM | Task Role 기본 | 최소 권한 정책 (S3 특정 prefix만 허용 등) |
| Secrets | 환경변수 | AWS Secrets Manager 연동 |
| WAF | 없음 | ALB 앞단 AWS WAF 배치 (Rate Limiting, IP 차단) |
| VPC Flow Logs | 없음 | 활성화 후 S3/CloudWatch 저장 |
| GuardDuty | 없음 | 계정 수준 활성화 |

## 비용 최적화 관점

| 리소스 | 현재 설계 | 최적화 방안 |
|---|---|---|
| NAT Gateway | 단일 | AZ별 1개 (트래픽 비용 vs 가용성 절충) |
| ECS Fargate | 온디맨드 | Fargate Spot으로 Consumer 등 무상태 워크로드 실행 |
| ElastiCache | On-Demand | Reserved Node로 1년/3년 약정 |
| CloudWatch Logs | 14일 보관 | 장기 보관은 S3 export |
| S3 아카이빙 | Standard | Lifecycle Policy로 90일 후 Glacier, 365일 후 Deep Archive |

## 관측성 (Observability)

### CloudWatch Metrics
- **ALB**: `RequestCount`, `TargetResponseTime`, `HTTPCode_Target_5XX_Count`
- **ECS**: `CPUUtilization`, `MemoryUtilization`
- **ElastiCache**: `CPUUtilization`, `DatabaseMemoryUsagePercentage`, `CurrConnections`

### 권장 알람
- ALB 5xx 비율 > 1% (5분 지속)
- ECS Task CPU > 80% (10분 지속) → Auto Scaling 트리거
- ElastiCache 메모리 > 75% → 스케일 업 검토
- Redis Stream 길이 급증 → Consumer 처리량 부족 신호

### 로그 파이프라인
```
ECS Task → awslogs driver → CloudWatch Log Group → (선택) Kinesis Firehose → S3
```

## 결론

본 설계는 필수 과제에서 검증한 **API → Redis Streams → Consumer** 파이프라인을 AWS 관리형 서비스로 매핑한 것입니다.

- **재현성**: Terraform 코드로 인프라 전체를 코드 관리
- **확장성**: Multi-AZ + Auto Scaling으로 트래픽 피크 대응
- **안정성**: 관리형 서비스 활용으로 운영 부담 최소화
- **점진적 확장**: Phase 1~3 로드맵으로 성장 시나리오 대비

과제 스코프상 실제 프로비저닝은 하지 않았으나, `terraform plan` 수준의 코드 완성도를 목표로 작성했습니다.
