variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "ap-northeast-2"
}

variable "project_name" {
  description = "Project name used as a resource name prefix"
  type        = string
  default     = "game-log-pipeline"
}

variable "environment" {
  description = "Environment name"
  type        = string
  default     = "dev"
}

# ---- VPC ----
variable "vpc_cidr" {
  description = "VPC CIDR block"
  type        = string
  default     = "10.0.0.0/16"
}

variable "availability_zones" {
  description = "Availability zones for Multi-AZ placement"
  type        = list(string)
  default     = ["ap-northeast-2a", "ap-northeast-2c"]
}

variable "public_subnet_cidrs" {
  description = "Public subnet CIDR blocks for ALB and NAT Gateway"
  type        = list(string)
  default     = ["10.0.1.0/24", "10.0.2.0/24"]
}

variable "private_subnet_cidrs" {
  description = "Private subnet CIDR blocks for ECS tasks and Redis"
  type        = list(string)
  default     = ["10.0.11.0/24", "10.0.12.0/24"]
}

# ---- ECS ----
variable "api_image" {
  description = "API container image URI"
  type        = string
}

variable "api_container_port" {
  description = "API container port"
  type        = number
  default     = 8000
}

variable "api_desired_count" {
  description = "Initial number of API tasks"
  type        = number
  default     = 2
}

variable "api_cpu" {
  description = "API task CPU units"
  type        = number
  default     = 512
}

variable "api_memory" {
  description = "API task memory in MiB"
  type        = number
  default     = 1024
}

# ---- Redis ----
variable "redis_node_type" {
  description = "ElastiCache Redis node type"
  type        = string
  default     = "cache.t4g.micro"
}
