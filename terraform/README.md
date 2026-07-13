# AWS 인프라 설계 및 Terraform

로그 수집 파이프라인을 AWS 관리형 인프라로 구성하기 위한 설계안과 Terraform 코드입니다.

## 아키텍처 다이어그램

```
                              [ Internet ]
                                   │
                                   ▼
                    ┌─────────────────────────────┐
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

## AWS 구성 요약

| 영역 | 구성 |
|---|---|
| 네트워크 | VPC, Public Subnet 2개, Private Subnet 2개 |
| 진입점 | Public Subnet의 Application Load Balancer |
| API 실행 환경 | Private Subnet의 ECS Fargate Service |
| 로그 적재 | Private Subnet의 ElastiCache Redis Replication Group |
| 보안 | ALB, ECS Task, Redis Security Group 분리 |
| 확장 | ECS Service Auto Scaling, Redis Multi-AZ Failover |

## Terraform 파일 구조

```
terraform/
├── main.tf              # Provider 설정
├── variables.tf         # 변수 정의
├── vpc.tf               # VPC, Subnet, IGW, NAT Gateway, Route Table
├── security.tf          # Security Group (ALB, ECS, Redis)
├── alb.tf               # ALB, Target Group, Listener
├── ecs.tf               # ECS Cluster, Task Definition, Service, Auto Scaling, IAM
├── redis.tf             # ElastiCache Redis, Subnet Group
├── outputs.tf           # 출력값
└── README.md            # 본 문서
```

## Terraform 구현 범위

- VPC, Subnet (Public/Private × 2AZ)
- Internet Gateway, NAT Gateway, Route Table
- Security Group (ALB, ECS Task, Redis)
- ALB, Target Group, HTTP Listener
- ECS Cluster, Task Definition, Service (API)
- ECS Auto Scaling (CPU 기반)
- ElastiCache Redis Replication Group (Multi-AZ, Automatic Failover)
- CloudWatch Log Group
- IAM Role (ECS Task Execution, Task Role)

## 검증 절차

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

# 실행 계획 확인
terraform plan -var 'api_image=123456789012.dkr.ecr.ap-northeast-2.amazonaws.com/game-log-api:latest'
```

### 3. 이미지 변수
```bash
# api_image 변수로 컨테이너 이미지 URI를 전달
terraform plan -var 'api_image=123456789012.dkr.ecr.ap-northeast-2.amazonaws.com/game-log-api:latest'
```

## 주요 설계 판단 근거

### 왜 EC2 대신 ECS Fargate인가 
- **관리 부담 최소화**: 인프라 엔지니어가 EC2 패치, AMI 관리 등에서 해방
- **초당 과금**: 트래픽 없는 시간에 비용 절감
- **Auto Scaling과 궁합**: Task 수 조정만으로 수평 확장
- **EKS 대비 단순함**: Kubernetes 운영 복잡도 없이 컨테이너 서비스를 구성할 수 있음

### 셀프 호스팅 Redis 대신 ElastiCache Redis 사용 
- **Multi-AZ 자동 페일오버**: Primary 장애 시 Replica가 승격
- **자동 백업**: 스냅샷 자동 생성 및 S3 저장
- **패치/업그레이드 관리**: AWS가 무중단 유지보수 수행
- **모니터링 통합**: CloudWatch 메트릭 기본 제공

### NAT Gateway 설정 이유
- **관리형 서비스**: 고가용성 자동 보장 (AZ 내 다중화)
- **처리량 자동 확장**: 최대 45 Gbps
- **트레이드오프**: NAT Instance보다 비용은 높지만 운영 부담이 낮음

### 단일 NAT Gateway 설정 이유
- 본 Terraform 코드는 **비용 최적화**를 위해 단일 NAT 사용
- **HA 필요 시**: `aws_nat_gateway`를 AZ 개수만큼 생성하고 `aws_route_table.private`도 AZ별로 분리
- 트래픽과 가용성 요구가 높아지면 NAT Gateway를 AZ별로 분리

## 보안 고려사항

| 항목 | 구성 |
|---|---|
| 네트워크 격리 | API Task와 Redis를 Private Subnet에 배치 |
| 외부 노출 | ALB만 Public Subnet에 배치 |
| 접근 제어 | ECS Task는 ALB에서만 8000 포트 수신 |
| Redis 보호 | Redis는 ECS Task Security Group에서만 6379 포트 수신 |
| 권한 관리 | ECS Task Execution Role과 Task Role 분리 |
| 로그 | ECS Task 로그를 CloudWatch Log Group으로 전송 |

## 관측성

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
ECS Task → awslogs driver → CloudWatch Log Group
```

## 결론

본 설계는 필수 과제에서 검증한 **API → Redis Streams → Consumer** 파이프라인을 AWS 관리형 서비스로 매핑한 것입니다.

- **재현성**: Terraform 코드로 인프라 전체를 코드 관리
- **확장성**: Multi-AZ + Auto Scaling으로 트래픽 피크 대응
- **안정성**: 관리형 서비스 활용으로 운영 부담 최소화
- **관측성**: CloudWatch Log Group과 Container Insights 구성

Terraform 코드로 네트워크, API 실행 환경, 로드밸런서, 로그 적재 컴포넌트를 재현 가능하게 관리합니다.
