#!/usr/bin/env bash
# Tear down Argus AWS resources to stop all costs.
# Keeps: SSM parameters (free), IAM roles (free), security group (free) — so redeploy is fast.
# Deletes: ECS service + cluster (the actual cost), ECR images, CloudWatch logs.
set -euo pipefail
REGION=${AWS_REGION:-us-east-2}

echo "--- Scaling service to 0 and deleting it..."
aws ecs update-service --cluster argus-cluster --service argus-service \
  --desired-count 0 --region "$REGION" >/dev/null 2>&1 || true
aws ecs delete-service --cluster argus-cluster --service argus-service \
  --force --region "$REGION" >/dev/null 2>&1 || true

echo "--- Deleting cluster..."
aws ecs delete-cluster --cluster argus-cluster --region "$REGION" >/dev/null 2>&1 || true

echo "--- Deregistering task definitions..."
for td in $(aws ecs list-task-definitions --family-prefix argus-agent --region "$REGION" \
             --query 'taskDefinitionArns[]' --output text); do
  aws ecs deregister-task-definition --task-definition "$td" --region "$REGION" >/dev/null
done

echo "--- Deleting ECR repository (and all images)..."
aws ecr delete-repository --repository-name argus-agent --force --region "$REGION" >/dev/null 2>&1 || true

echo "--- Deleting CloudWatch log group..."
aws logs delete-log-group --log-group-name /ecs/argus-agent --region "$REGION" 2>/dev/null || true

echo ""
echo "Done. Remaining (all free-tier / no-cost): SSM parameters under /argus/*, IAM roles, security group."
echo "To also remove secrets:  for p in OPENAI_API_KEY LANGSMITH_API_KEY SLACK_BOT_TOKEN SLACK_APP_TOKEN GOOGLE_SA_JSON; do aws ssm delete-parameter --name /argus/\$p --region $REGION; done"
echo "To redeploy later: bash ecr_push.sh && bash deploy_ecs.sh"