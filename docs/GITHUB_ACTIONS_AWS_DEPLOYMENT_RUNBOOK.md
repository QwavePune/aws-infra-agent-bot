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
- ECS cluster/service already created.

Main workflow file:
- `.github/workflows/ci-cd.yml`

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
- `ecs:RegisterTaskDefinition`
- `ecs:DescribeTaskDefinition`
- `ecs:DescribeServices`
- `ecs:UpdateService`
- `logs:CreateLogGroup` / `logs:DescribeLogGroups`
- `iam:PassRole` for task execution role and task role
- `secretsmanager:GetSecretValue` for secret ARN

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

## 7. Dockerfile Build Fix Applied

Build failed previously on Terraform install (`exit code: 100`) because of deprecated apt setup.

Fixes applied in `Dockerfile`:
- `FROM ... AS builder` casing normalized.
- Replaced `apt-key` + `apt-add-repository` with keyring-based repo config.

Key block now uses:
- `/etc/apt/keyrings/hashicorp-archive-keyring.gpg`
- `${VERSION_CODENAME}` from `/etc/os-release`

---

## 8. ECS Existence Checks

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

---

## 9. CloudTrail Debug Commands (OIDC Failures)

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

