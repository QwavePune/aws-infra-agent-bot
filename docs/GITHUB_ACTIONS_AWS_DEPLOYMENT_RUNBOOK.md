# GitHub Actions -> AWS ECS Deployment Runbook

This runbook documents the exact setup and troubleshooting steps used to get the CI/CD pipeline working for this repo.

Repository:
- `QwavePune/aws-infra-agent-bot`

AWS Account:
- `724255305552`

Region:
- `ap-south-1`

---

## 1. Pipeline Preconditions

The workflow expects:
- OIDC trust between GitHub and IAM role.
- IAM role permissions for ECR/ECS/Logs/Secrets.
- Required GitHub Actions secrets.
- ECS cluster/service already created, or bootstrapped through the manual workflow added for this repo.

Main workflow file:
- `.github/workflows/ci-cd.yml`

Manual environment workflows:
- `.github/workflows/bootstrap-ecs.yml`
- `.github/workflows/destroy-ecs.yml`

---

## 2. Fix Deprecated GitHub Actions Versions

If pipeline fails with deprecated actions (`upload-artifact@v3`), update to v4.

Verify in workflow:
- `actions/upload-artifact@v4`
- `codecov/codecov-action@v4`

---

## 3. Create/Repair GitHub OIDC Provider in IAM

Check provider audience:

```bash
AWS_PROFILE=default aws iam get-open-id-connect-provider \
  --open-id-connect-provider-arn arn:aws:iam::724255305552:oidc-provider/token.actions.githubusercontent.com \
  --query 'ClientIDList' --output json
```

Expected output contains:
- `sts.amazonaws.com`

If provider is broken/misconfigured, recreate:

```bash
AWS_PROFILE=default aws iam delete-open-id-connect-provider \
  --open-id-connect-provider-arn arn:aws:iam::724255305552:oidc-provider/token.actions.githubusercontent.com

AWS_PROFILE=default aws iam create-open-id-connect-provider \
  --url https://token.actions.githubusercontent.com \
  --client-id-list sts.amazonaws.com \
  --thumbprint-list 6938fd4d98bab03faadb97b34396831e3780aea1
```

---

## 4. Update IAM Role Trust Policy for GitHub OIDC

Role used by GitHub Actions:
- `github-actions-langchain-agent`
- ARN: `arn:aws:iam::724255305552:role/github-actions-langchain-agent`

Apply trust policy:

```bash
AWS_PROFILE=default aws iam update-assume-role-policy \
  --role-name github-actions-langchain-agent \
  --policy-document '{
    "Version":"2012-10-17",
    "Statement":[
      {
        "Effect":"Allow",
        "Principal":{
          "Federated":"arn:aws:iam::724255305552:oidc-provider/token.actions.githubusercontent.com"
        },
        "Action":"sts:AssumeRoleWithWebIdentity",
        "Condition":{
          "StringEquals":{
            "token.actions.githubusercontent.com:aud":"sts.amazonaws.com"
          },
          "StringLike":{
            "token.actions.githubusercontent.com:sub":"repo:QwavePune/aws-infra-agent-bot:*"
          }
        }
      }
    ]
  }'
```

Notes:
- AWS requires a `sub` condition for GitHub OIDC. Removing it causes `MalformedPolicyDocument`.
- Start broad (`repo:...:*`) to unblock. Tighten later to specific branches.

Verify:

```bash
AWS_PROFILE=default aws iam get-role \
  --role-name github-actions-langchain-agent \
  --query 'Role.AssumeRolePolicyDocument' \
  --output json
```

---

## 5. IAM Permissions Required on the Role

### 5.1 ECR permissions (required for build/push)

If error says `not authorized for ecr:GetAuthorizationToken` or `ecr:CreateRepository`, attach policy:

```bash
AWS_PROFILE=default aws iam put-role-policy \
  --role-name github-actions-langchain-agent \
  --policy-name github-actions-ecr \
  --policy-document '{
    "Version":"2012-10-17",
    "Statement":[
      {
        "Effect":"Allow",
        "Action":[
          "ecr:GetAuthorizationToken",
          "ecr:DescribeRepositories",
          "ecr:CreateRepository",
          "ecr:BatchCheckLayerAvailability",
          "ecr:InitiateLayerUpload",
          "ecr:UploadLayerPart",
          "ecr:CompleteLayerUpload",
          "ecr:PutImage",
          "ecr:BatchGetImage"
        ],
        "Resource":"*"
      }
    ]
  }'
```

### 5.2 ECS deployment permissions

Role also needs:
- `ecs:CreateCluster`
- `ecs:DeleteCluster`
- `ecs:CreateService`
- `ecs:DeleteService`
- `ecs:RegisterTaskDefinition`
- `ecs:DeregisterTaskDefinition`
- `ecs:DescribeTaskDefinition`
- `ecs:DescribeServices`
- `ecs:UpdateService`
- `ecs:ListTaskDefinitions`
- `logs:CreateLogGroup` / `logs:DescribeLogGroups`
- `logs:DeleteLogGroup` if you use the destroy workflow cleanup option
- `ec2:DescribeSubnets` / `ec2:DescribeSecurityGroups` for validation and environment checks
- `iam:PassRole` for task execution role and task role
- `secretsmanager:GetSecretValue` for secret ARN

If bootstrap fails with `AccessDeniedException` for `ecs:CreateCluster`, your GitHub Actions role policy is still deploy-only and has not been expanded for bootstrap/teardown.

---

## 6. GitHub Repository Secrets Required

Set under:
- GitHub repo -> `Settings` -> `Secrets and variables` -> `Actions` -> `Repository secrets`

Required secrets:
- `AWS_ROLE_ARN` = `arn:aws:iam::724255305552:role/github-actions-langchain-agent`
- `ECS_CLUSTER` = ECS cluster name
- `ECS_SERVICE` = ECS service name
- `ECS_TASK_EXECUTION_ROLE_ARN` = execution role ARN
- `ECS_TASK_ROLE_ARN` = task role ARN
- `PERPLEXITY_SECRET_ARN` = Secrets Manager ARN containing key

Optional:
- `AWS_REGION` (repo variable or secret); workflow defaults to `ap-south-1`.

Note:
- `role-to-assume: ***` in logs is expected because GitHub masks secrets.

---

## 7. One-Time ECS Bootstrap Prerequisites

Before the ECS bootstrap workflow can succeed, you still need:
- an ECS task execution role
- an ECS task role
- at least one subnet, usually two, for Fargate networking
- a security group that allows outbound HTTPS
- Secrets Manager secrets for OpenAI and/or Perplexity

### 7.1 Create ECS task execution role

This role is assumed by the ECS agent to pull images from ECR, write logs, and read Secrets Manager values referenced by the task definition.

```bash
AWS_PROFILE=default aws iam create-role \
  --role-name ecsTaskExecutionRole \
  --assume-role-policy-document '{
    "Version":"2012-10-17",
    "Statement":[
      {
        "Effect":"Allow",
        "Principal":{"Service":"ecs-tasks.amazonaws.com"},
        "Action":"sts:AssumeRole"
      }
    ]
  }'

AWS_PROFILE=default aws iam attach-role-policy \
  --role-name ecsTaskExecutionRole \
  --policy-arn arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy

AWS_PROFILE=default aws iam put-role-policy \
  --role-name ecsTaskExecutionRole \
  --policy-name ecs-task-secrets-access \
  --policy-document '{
    "Version":"2012-10-17",
    "Statement":[
      {
        "Effect":"Allow",
        "Action":["secretsmanager:GetSecretValue"],
        "Resource":"*"
      }
    ]
  }'
```

### 7.2 Create ECS task role

This is the role available to your application container at runtime. Start simple for testing, then tighten later.

```bash
AWS_PROFILE=default aws iam create-role \
  --role-name ecsTaskRole \
  --assume-role-policy-document '{
    "Version":"2012-10-17",
    "Statement":[
      {
        "Effect":"Allow",
        "Principal":{"Service":"ecs-tasks.amazonaws.com"},
        "Action":"sts:AssumeRole"
      }
    ]
  }'
```

If the app needs to read Secrets Manager directly at runtime, add:

```bash
AWS_PROFILE=default aws iam put-role-policy \
  --role-name ecsTaskRole \
  --policy-name app-secrets-access \
  --policy-document '{
    "Version":"2012-10-17",
    "Statement":[
      {
        "Effect":"Allow",
        "Action":["secretsmanager:GetSecretValue"],
        "Resource":"*"
      }
    ]
  }'
```

### 7.3 Create or locate subnets

For a temporary environment, the easiest path is to reuse default-VPC subnets if your account has them:

```bash
AWS_PROFILE=default aws ec2 describe-subnets \
  --region ap-south-1 \
  --query 'Subnets[].{SubnetId:SubnetId,VpcId:VpcId,Az:AvailabilityZone,MapPublicIp:MapPublicIpOnLaunch}' \
  --output table
```

Choose one or two subnets in the same VPC. For Fargate, two subnets across AZs is preferred.

If you specifically want default-VPC subnets:

```bash
AWS_PROFILE=default aws ec2 describe-route-tables \
  --region ap-south-1 \
  --query 'RouteTables[].{RouteTableId:RouteTableId,VpcId:VpcId}'
```

### 7.4 Create or locate a security group

For a simple temporary environment, a security group with outbound internet access is enough if the container does not expose inbound traffic.

List existing groups:

```bash
AWS_PROFILE=default aws ec2 describe-security-groups \
  --region ap-south-1 \
  --query 'SecurityGroups[].{GroupId:GroupId,VpcId:VpcId,Name:GroupName}' \
  --output table
```

Create a new one if needed:

```bash
AWS_PROFILE=default aws ec2 create-security-group \
  --group-name langchain-agent-ecs-sg \
  --description "Temporary ECS security group for langchain-agent" \
  --vpc-id <your-vpc-id> \
  --region ap-south-1
```

Allow all outbound traffic:

```bash
AWS_PROFILE=default aws ec2 authorize-security-group-egress \
  --group-id <your-security-group-id> \
  --ip-permissions '[
    {
      "IpProtocol":"-1",
      "IpRanges":[{"CidrIp":"0.0.0.0/0"}],
      "Ipv6Ranges":[{"CidrIpv6":"::/0"}]
    }
  ]' \
  --region ap-south-1
```

### 7.5 Create Secrets Manager secrets

```bash
AWS_PROFILE=default aws secretsmanager create-secret \
  --name openai-api-key \
  --secret-string '<your-openai-api-key>' \
  --region ap-south-1

AWS_PROFILE=default aws secretsmanager create-secret \
  --name perplexity-api-key \
  --secret-string '<your-perplexity-api-key>' \
  --region ap-south-1
```

Capture the returned ARNs and store them in GitHub secrets:
- `OPENAI_SECRET_ARN`
- `PERPLEXITY_SECRET_ARN`
- `ECS_TASK_EXECUTION_ROLE_ARN`
- `ECS_TASK_ROLE_ARN`

---

## 8. Dockerfile Build Fix Applied

Build failed previously on Terraform install (`exit code: 100`) because of deprecated apt setup.

Fixes applied in `Dockerfile`:
- `FROM ... AS builder` casing normalized.
- Replaced `apt-key` + `apt-add-repository` with keyring-based repo config.

Key block now uses:
- `/etc/apt/keyrings/hashicorp-archive-keyring.gpg`
- `${VERSION_CODENAME}` from `/etc/os-release`

---

## 9. ECS Existence Checks

Before deploy, verify ECS resources exist:

```bash
AWS_PROFILE=default aws ecs describe-clusters \
  --clusters langchain-agent-cluster \
  --region ap-south-1

AWS_PROFILE=default aws ecs describe-services \
  --cluster langchain-agent-cluster \
  --services langchain-agent-service \
  --region ap-south-1
```

If not found, create cluster/service first (one-time infra bootstrap).

### 8.1 Manual Bootstrap Through GitHub Actions

Use the `Bootstrap ECS Environment` workflow when you want GitHub Actions to create a temporary ECS environment before the normal CI/CD deploy job updates it.

Required workflow inputs:
- `aws_region`
- `cluster_name`
- `service_name`
- `subnet_ids` as comma-separated subnet IDs
- `security_group_ids` as comma-separated security group IDs
- `desired_count`
- `assign_public_ip`
- `llm_provider`

What it does:
- ensures the ECR repository exists
- ensures the CloudWatch log group exists
- creates the ECS cluster if missing
- renders and registers the ECS task definition
- creates or updates the ECS Fargate service
- waits for service stability

### 8.2 Tear Down Temporary Environment

Use the `Destroy ECS Environment` workflow when testing is complete.

It can:
- delete the ECS service
- delete the ECS cluster
- deregister active task definition revisions for the family
- optionally delete the CloudWatch log group
- optionally delete the ECR repository

---

## 10. Example Temporary Environment Flow

1. Create `ecsTaskExecutionRole` and `ecsTaskRole`.
2. Create or choose subnets in one VPC.
3. Create or choose a security group in the same VPC.
4. Create Secrets Manager secrets for OpenAI/Perplexity.
5. Add the resulting ARNs to GitHub repository secrets.
6. Run `Bootstrap ECS Environment`.
7. Push to `main` to let `ci-cd.yml` update the service.
8. Run `Destroy ECS Environment` after testing.

---

## 11. CloudTrail Debug Commands (OIDC Failures)

Get recent `AssumeRoleWithWebIdentity` events:

```bash
AWS_PROFILE=default aws cloudtrail lookup-events \
  --lookup-attributes AttributeKey=EventName,AttributeValue=AssumeRoleWithWebIdentity \
  --max-results 20 \
  --query 'Events[].CloudTrailEvent' \
  --output text
```

Parse useful fields:

```bash
AWS_PROFILE=default aws cloudtrail lookup-events \
  --lookup-attributes AttributeKey=EventName,AttributeValue=AssumeRoleWithWebIdentity \
  --max-results 20 \
  --query 'Events[].CloudTrailEvent' \
  --output text | jq -r '
  . as $e | {
    eventTime,
    errorCode,
    errorMessage,
    roleArn: .requestParameters.roleArn,
    provider: .requestParameters.providerId,
    subjectFromWebIdentityToken,
    audience: .requestParameters.audience
  }'
```

---

## 10. Recommended Hardening After Successful Runs

After pipeline is stable, tighten trust policy `sub`:

```json
"StringLike": {
  "token.actions.githubusercontent.com:sub": [
    "repo:QwavePune/aws-infra-agent-bot:ref:refs/heads/main",
    "repo:QwavePune/aws-infra-agent-bot:ref:refs/heads/master"
  ]
}
```

Keep wildcard only if you intentionally allow all refs/workflows.
