#!/usr/bin/env bash
# One-time-ish ECS Fargate deployment. Prereqs: ecr_push.sh and put_secrets.sh already run.
set -euo pipefail
REGION=${AWS_REGION:-us-east-1}
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
IMAGE_URI="$ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/argus-agent:latest"
CLUSTER=argus-cluster

# 1) IAM roles ---------------------------------------------------------------
TRUST='{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"ecs-tasks.amazonaws.com"},"Action":"sts:AssumeRole"}]}'

aws iam get-role --role-name argusEcsExecutionRole >/dev/null 2>&1 || {
  aws iam create-role --role-name argusEcsExecutionRole --assume-role-policy-document "$TRUST"
  aws iam attach-role-policy --role-name argusEcsExecutionRole \
    --policy-arn arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy
  # allow the execution role to read SSM SecureString params
  aws iam put-role-policy --role-name argusEcsExecutionRole --policy-name argusSsmRead \
    --policy-document "{\"Version\":\"2012-10-17\",\"Statement\":[{\"Effect\":\"Allow\",\"Action\":[\"ssm:GetParameters\",\"kms:Decrypt\"],\"Resource\":\"*\"}]}"
}

aws iam get-role --role-name argusEcsTaskRole >/dev/null 2>&1 || {
  aws iam create-role --role-name argusEcsTaskRole --assume-role-policy-document "$TRUST"
  # Bedrock access for the LLM_PROVIDER=bedrock path
  aws iam put-role-policy --role-name argusEcsTaskRole --policy-name argusBedrockInvoke \
    --policy-document "{\"Version\":\"2012-10-17\",\"Statement\":[{\"Effect\":\"Allow\",\"Action\":[\"bedrock:InvokeModel\",\"bedrock:InvokeModelWithResponseStream\"],\"Resource\":\"*\"}]}"
}

EXEC_ROLE_ARN=$(aws iam get-role --role-name argusEcsExecutionRole --query Role.Arn --output text)
TASK_ROLE_ARN=$(aws iam get-role --role-name argusEcsTaskRole --query Role.Arn --output text)

# 2) Cluster + logs ----------------------------------------------------------
aws ecs describe-clusters --clusters "$CLUSTER" --region "$REGION" --query 'clusters[0].status' --output text 2>/dev/null | grep -q ACTIVE \
  || aws ecs create-cluster --cluster-name "$CLUSTER" --region "$REGION"
aws logs create-log-group --log-group-name /ecs/argus-agent --region "$REGION" 2>/dev/null || true

# 3) Register task definition ------------------------------------------------
sed -e "s|REPLACE_WITH_EXECUTION_ROLE_ARN|$EXEC_ROLE_ARN|" \
    -e "s|REPLACE_WITH_TASK_ROLE_ARN|$TASK_ROLE_ARN|" \
    -e "s|REPLACE_WITH_IMAGE_URI|$IMAGE_URI|" \
    ecs_task_def.json > /tmp/argus_task_def.json
aws ecs register-task-definition --cli-input-json file:///tmp/argus_task_def.json --region "$REGION" >/dev/null

# 4) Networking (default VPC, public subnet, egress-only) --------------------
VPC_ID=$(aws ec2 describe-vpcs --filters Name=is-default,Values=true --query 'Vpcs[0].VpcId' --output text --region "$REGION")
SUBNET_ID=$(aws ec2 describe-subnets --filters Name=vpc-id,Values=$VPC_ID --query 'Subnets[0].SubnetId' --output text --region "$REGION")
SG_ID=$(aws ec2 describe-security-groups --filters Name=group-name,Values=argus-sg Name=vpc-id,Values=$VPC_ID \
  --query 'SecurityGroups[0].GroupId' --output text --region "$REGION" 2>/dev/null)
if [ "$SG_ID" = "None" ] || [ -z "$SG_ID" ]; then
  SG_ID=$(aws ec2 create-security-group --group-name argus-sg --description "Argus agent (egress only)" \
    --vpc-id "$VPC_ID" --region "$REGION" --query GroupId --output text)
fi

# 5) Create or update the service -------------------------------------------
if aws ecs describe-services --cluster "$CLUSTER" --services argus-service --region "$REGION" \
     --query 'services[0].status' --output text 2>/dev/null | grep -q ACTIVE; then
  aws ecs update-service --cluster "$CLUSTER" --service argus-service \
    --task-definition argus-agent --force-new-deployment --region "$REGION" >/dev/null
  echo "Service updated — new deployment rolling out."
else
  aws ecs create-service --cluster "$CLUSTER" --service-name argus-service \
    --task-definition argus-agent --desired-count 1 --launch-type FARGATE \
    --network-configuration "awsvpcConfiguration={subnets=[$SUBNET_ID],securityGroups=[$SG_ID],assignPublicIp=ENABLED}" \
    --region "$REGION" >/dev/null
  echo "Service created — Argus is starting."
fi

echo "Tail logs with: aws logs tail /ecs/argus-agent --follow --region $REGION"
