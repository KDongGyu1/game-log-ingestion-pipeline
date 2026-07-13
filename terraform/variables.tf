variable "aws_region" {
  description = "AWS 리전"
  type        = string
  default     = "ap-northeast-2"
}

variable "project_name" {
  description = "리소스명 앞에 붙는 프로젝트명"
  type        = string
  default     = "game-log-pipeline"
}

variable "environment" {
  description = "환경 이름"
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
  description = "Multi-AZ 배치에 사용할 가용 영역"
  type        = list(string)
  default     = ["ap-northeast-2a", "ap-northeast-2c"]
}

variable "public_subnet_cidrs" {
  description = "ALB와 NAT Gateway를 배치할 Public Subnet CIDR"
  type        = list(string)
  default     = ["10.0.1.0/24", "10.0.2.0/24"]
}

variable "private_subnet_cidrs" {
  description = "ECS Task와 Redis를 배치할 Private Subnet CIDR"
  type        = list(string)
  default     = ["10.0.11.0/24", "10.0.12.0/24"]
}

# ---- ECS ----
variable "api_image" {
  description = "API 컨테이너 이미지 URI"
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
  description = "API Task CPU 단위"
  type        = number
  default     = 512
}

variable "api_memory" {
  description = "API Task 메모리 MiB"
  type        = number
  default     = 1024
}

# ---- Redis ----
variable "redis_node_type" {
  description = "ElastiCache Redis 노드 타입"
  type        = string
  default     = "cache.t4g.micro"
}
