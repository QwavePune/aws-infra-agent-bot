set -euo pipefail

export AWS_PROFILE=default
export AWS_REGION=ap-south-1
export AWS_PAGER=""

export CLUSTER_NAME=aws-infra-agent-cluster
export SERVICE_NAME=langchain-agent-service
export TASK_FAMILY=langchain-agent
export ECR_REPO=langchain-agent

# 1) Ensure cluster exists
aws ecs describe-clusters --clusters "$CLUSTER_NAME" --region "$AWS_REGION" \
  --query 'clusters[0].clusterName' --output text 2>/dev/null | grep -qx "$CLUSTER_NAME" || \
aws ecs create-cluster --cluster-name "$CLUSTER_NAME" --region "$AWS_REGION" >/dev/null

# 2) Ensure ECR repo exists
aws ecr describe-repositories --repository-names "$ECR_REPO" --region "$AWS_REGION" >/dev/null 2>&1 || \
aws ecr create-repository --repository-name "$ECR_REPO" --region "$AWS_REGION" >/dev/null

# 3) Get default VPC and two subnets
VPC_ID=$(aws ec2 describe-vpcs --region "$AWS_REGION" \
  --filters Name=isDefault,Values=true --query 'Vpcs[0].VpcId' --output text)
SUBNET1=$(aws ec2 describe-subnets --region "$AWS_REGION" \
  --filters Name=vpc-id,Values="$VPC_ID" \
  --query 'Subnets[0].SubnetId' --output text)
SUBNET2=$(aws ec2 describe-subnets --region "$AWS_REGION" \
  --filters Name=vpc-id,Values="$VPC_ID" \
  --query 'Subnets[1].SubnetId' --output text)

# 4) Ensure service SG exists
SG_ID=$(aws ec2 describe-security-groups --region "$AWS_REGION" \
  --filters Name=group-name,Values=langchain-agent-sg Name=vpc-id,Values="$VPC_ID" \
  --query 'SecurityGroups[0].GroupId' --output text)

if [ "$SG_ID" = "None" ]; then
  SG_ID=$(aws ec2 create-security-group \
    --group-name langchain-agent-sg \
    --description "SG for langchain-agent ECS service" \
    --vpc-id "$VPC_ID" --region "$AWS_REGION" \
    --query 'GroupId' --output text)
fi

aws ec2 authorize-security-group-ingress \
  --group-id "$SG_ID" --protocol tcp --port 80 --cidr 0.0.0.0/0 \
  --region "$AWS_REGION" >/dev/null 2>&1 || true

# 5) Ensure CloudWatch log group exists
aws logs create-log-group --log-group-name "/ecs/langchain-agent" --region "$AWS_REGION" >/dev/null 2>&1 || true

# 6) Register a minimal task definition (bootstrap only)
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
EXEC_ROLE_ARN="arn:aws:iam::${ACCOUNT_ID}:role/ecsTaskExecutionRole"
TASK_ROLE_ARN="arn:aws:iam::${ACCOUNT_ID}:role/ecsTaskRole"

cat > /tmp/bootstrap-taskdef.json <<EOF
{
  "family": "${TASK_FAMILY}",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "256",
  "memory": "512",
  "executionRoleArn": "${EXEC_ROLE_ARN}",
  "taskRoleArn": "${TASK_ROLE_ARN}",
  "containerDefinitions": [
    {
      "name": "langchain-agent",
      "image": "${ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPO}:latest",
      "essential": true,
      "portMappings": [{"containerPort": 80, "protocol": "tcp"}],
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "/ecs/langchain-agent",
          "awslogs-region": "${AWS_REGION}",
          "awslogs-stream-prefix": "ecs"
        }
      }
    }
  ]
}
EOF

aws ecs register-task-definition --cli-input-json file:///tmp/bootstrap-taskdef.json --region "$AWS_REGION" >/dev/null

# 7) Ensure service exists
SERVICE_STATUS=$(aws ecs describe-services \
  --cluster "$CLUSTER_NAME" --services "$SERVICE_NAME" --region "$AWS_REGION" \
  --query 'services[0].status' --output text 2>/dev/null || true)

if [ "$SERVICE_STATUS" = "ACTIVE" ]; then
  echo "Service already exists."
else
  aws ecs create-service \
    --cluster "$CLUSTER_NAME" \
    --service-name "$SERVICE_NAME" \
    --task-definition "$TASK_FAMILY" \
    --desired-count 1 \
    --launch-type FARGATE \
    --network-configuration "awsvpcConfiguration={subnets=[$SUBNET1,$SUBNET2],securityGroups=[$SG_ID],assignPublicIp=ENABLED}" \
    --region "$AWS_REGION" >/dev/null
fi

echo "Bootstrap complete."
echo "ECS_CLUSTER=$CLUSTER_NAME"
echo "ECS_SERVICE=$SERVICE_NAME"
echo "ECS_TASK_EXECUTION_ROLE_ARN=$EXEC_ROLE_ARN"
echo "ECS_TASK_ROLE_ARN=$TASK_ROLE_ARN"
