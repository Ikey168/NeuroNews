# Neptune Configuration for NeuroNews

# Create a Neptune subnet group
#resource "aws_neptune_subnet_group" "neptune" {
#  name        = "${var.bucket_name_prefix}-neptune-${var.environment}-subnet-group"
#  description = "Subnet group for Neptune cluster"
#  subnet_ids  = data.aws_subnets.default.ids
#
#  tags = merge(
#    var.tags,
#    {
#      Name        = "Neptune Subnet Group"
#      Environment = var.environment
#    }
#  )
#}
#
## Create a Neptune parameter group
#resource "aws_neptune_parameter_group" "neptune" {
#  name   = "${var.bucket_name_prefix}-neptune-${var.environment}-params"
#  family = "neptune1.2"
#
#  tags = merge(
#    var.tags,
#    {
#      Name        = "Neptune Parameter Group"
#      Environment = var.environment
#    }
#  )
#}
#
## Create a Neptune cluster
#resource "aws_neptune_cluster" "knowledge_graphs" {
#  cluster_identifier      = "${var.bucket_name_prefix}-neptune-${var.environment}"
#  engine                  = "neptune"
#  engine_version          = "1.2.1.0"
#  backup_retention_period = 5
#  preferred_backup_window = "07:00-09:00"
#  skip_final_snapshot     = true
#  neptune_subnet_group_name = aws_neptune_subnet_group.neptune.name
#  vpc_security_group_ids = [aws_security_group.neptune.id]
#
#  tags = merge(
#    var.tags,
#    {
#      Name        = "Neptune Cluster"
#      Environment = var.environment
#    }
#  )
#}
#
#resource "aws_neptune_cluster_instance" "knowledge_graphs" {
#  cluster_identifier = aws_neptune_cluster.knowledge_graphs.cluster_identifier
#  instance_class     = "db.t3.medium"
#  engine             = "neptune"
#  identifier         = "${var.bucket_name_prefix}-neptune-${var.environment}-0"
#  neptune_parameter_group_name = aws_neptune_parameter_group.neptune.name
#}
