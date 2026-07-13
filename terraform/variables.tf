variable "aws_region" {
  description = "AWS 배포 리전"
  type        = string
  default     = "ap-northeast-2"
}

variable "project_name" {
  description = "프로젝트 이름 (리소스 네이밍 prefix)"
  type        = string
  default     = "game-log-pipeline"
}

variable "environment" {
  description = "환경 구분 (dev, staging, prod)"
  type        = string
  default     = "dev"
}

# ---- VPC ----
variable "vpc_cidr" {
  description = "VPC CIDR 블록"
  type        = string
  default     = "10.0.0.0/16"
}

variable "availability_zones" {
  description = "사용할 가용 영역 (Multi-AZ 부하 분산)"
  type        = list(string)
  default     = ["ap-northeast-2a", "ap-northeast-2c"]
}

variable "public_subnet_cidrs" {
  description = "Public Subnet CIDR 블록 (ALB, NAT Gateway 배치)"
  type        = list(string)
  default     = ["10.0.1.0/24", "10.0.2.0/24"]
}

variable "private_subnet_cidrs" {
  description = "Private Subnet CIDR 블록 (ECS Task, Redis 배치)"
  type        = list(string)
  default     = ["10.0.11.0/24", "10.0.12.0/24"]
}

# ---- ECS ----
variable "api_image" {
  description = "API 서버 컨테이너 이미지 (ECR URI)"
  type        = string
}

variable "api_container_port" {
  description = "API 컨테이너 포트"
  type        = number
  default     = 8000
}

variable "api_desired_count" {
  description = "API Task 초기 개수"
  type        = number
  default     = 2
}

variable "api_cpu" {
  description = "API Task CPU (Fargate 단위)"
  type        = number
  default     = 512
}

variable "api_memory" {
  description = "API Task 메모리 (MiB)"
  type        = number
  default     = 1024
}

# ---- Redis ----
variable "redis_node_type" {
  description = "ElastiCache Redis node type"
  type        = string
  default     = "cache.t4g.micro"
}
