output "vpc_id" {
  description = "VPC ID"
  value       = aws_vpc.main.id
}

output "public_subnet_ids" {
  description = "Public Subnet IDs (Multi-AZ)"
  value       = aws_subnet.public[*].id
}

output "private_subnet_ids" {
  description = "Private Subnet IDs (Multi-AZ)"
  value       = aws_subnet.private[*].id
}

output "alb_dns_name" {
  description = "ALB DNS 이름 (외부 접근 엔드포인트)"
  value       = aws_lb.api.dns_name
}

output "alb_zone_id" {
  description = "ALB Zone ID (Route53 Alias 레코드용)"
  value       = aws_lb.api.zone_id
}

output "ecs_cluster_name" {
  description = "ECS 클러스터 이름"
  value       = aws_ecs_cluster.main.name
}

output "ecs_service_name" {
  description = "ECS API 서비스 이름"
  value       = aws_ecs_service.api.name
}

output "cloudwatch_log_group" {
  description = "API 로그가 저장되는 CloudWatch Log Group"
  value       = aws_cloudwatch_log_group.api.name
}

output "redis_primary_endpoint" {
  description = "ElastiCache Redis primary endpoint"
  value       = aws_elasticache_replication_group.redis.primary_endpoint_address
}
