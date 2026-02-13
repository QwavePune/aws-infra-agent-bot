# DevOps Pipeline Setup Guide

## Overview

This guide walks you through setting up the complete CI/CD pipeline for the LangChain Agent on AWS.

The pipeline includes:
- ✅ **Build & Lint** - Code quality checks
- ✅ **Unit Tests** - Test coverage reporting
- ✅ **Security Scans** - Dependency and code security analysis
- ✅ **Docker Build** - Container image creation and push to ECR
- ✅ **Deploy to AWS** - Lambda or containerized deployment
- ✅ **Integration Tests** - End-to-end testing on AWS

## Prerequisites

1. **GitHub Repository** - Push code to GitHub (already set up)
2. **AWS Account** - With permissions for:
   - Lambda (if using Lambda deployment)
   - ECS/Fargate (if using containerized deployment)
   - ECR (Elastic Container Registry)
   - CloudWatch (for logs)
   - Secrets Manager (for API keys)
3. **AWS IAM Role for OIDC** - For secure GitHub Actions authentication

## Step 1: Set Up AWS IAM Role for GitHub Actions (OIDC)

This is the **most secure** way to authenticate from GitHub to AWS (no long-lived credentials).

### Create OIDC Provider in AWS

```bash
aws iam create-open-id-connect-provider \
  --url https://token.actions.githubusercontent.com \
  --client-id-list sts.amazonaws.com \
  --thumbprint-list 6938fd4d98bab03faadb97b34396831e3780aea1
```

### Create IAM Role for GitHub Actions

```bash
# Create trust relationship JSON
cat > trust-policy.json <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::724255305552:oidc-provider/token.actions.githubusercontent.com"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
        },
        "StringLike": {
          "token.actions.githubusercontent.com:sub": "repo:YOUR_GITHUB_USERNAME/aws-infra-agent-bot:ref:refs/heads/main"
        }
      }
    }
  ]
}
EOF

# Create the role
aws iam create-role \
  --role-name github-actions-langchain-agent \
  --assume-role-policy-document file://trust-policy.json
```

### Attach Permissions to the Role

```bash
# Create inline policy for deployment permissions
cat > deployment-policy.json <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "ecr:GetAuthorizationToken",
        "ecr:BatchCheckLayerAvailability",
        "ecr:GetDownloadUrlForLayer",
        "ecr:PutImage",
        "ecr:InitiateLayerUpload",
        "ecr:UploadLayerPart",
        "ecr:CompleteLayerUpload",
        "ecr:CreateRepository"
      ],
      "Resource": "arn:aws:ecr:us-east-1:724255305552:repository/langchain-agent"
    },
    {
      "Effect": "Allow",
      "Action": [
        "lambda:UpdateFunctionCode",
        "lambda:InvokeFunction",
        "lambda:GetFunction"
      ],
      "Resource": "arn:aws:lambda:us-east-1:724255305552:function:langchain-agent-function"
    },
    {
      "Effect": "Allow",
      "Action": [
        "ecs:UpdateService",
        "ecs:DescribeServices",
        "ecs:DescribeTaskDefinition",
        "ecs:DescribeClusters",
        "ecs:RegisterTaskDefinition"
      ],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ],
      "Resource": "arn:aws:logs:us-east-1:724255305552:log-group:/aws/lambda/langchain-agent*"
    },
    {
      "Effect": "Allow",
      "Action": "iam:PassRole",
      "Resource": "arn:aws:iam::724255305552:role/lambda-execution-role"
    }
  ]
}
EOF

aws iam put-role-policy \
  --role-name github-actions-langchain-agent \
  --policy-name github-actions-deployment \
  --policy-document file://deployment-policy.json
```

## Step 2: Set GitHub Secrets

1. Go to your GitHub repo → **Settings** → **Secrets and variables** → **Actions**
2. Add these secrets:

```
AWS_ROLE_ARN = arn:aws:iam::YOUR_AWS_ACCOUNT_ID:role/github-actions-langchain-agent
AWS_REGION = us-east-1
```

## Step 3: Run the Pipeline

### Trigger on Push to Main

The pipeline automatically runs when you:
- Push to `main` branch
- Create a pull request

### Manual Trigger (Optional)

Go to **Actions** tab in GitHub → Select workflow → **Run workflow**

## Step 4: Monitor Pipeline Execution

1. Go to **Actions** tab in your GitHub repo
2. Click on the workflow run
3. Check individual job logs:
   - **Build & Lint** - Code quality
   - **Unit Tests** - Test results and coverage
   - **Security** - Vulnerability scans
   - **Build Docker** - Container creation (main branch only)
   - **Deploy** - Deployment status
   - **Integration Tests** - AWS integration testing

## Step 5: Deployment Options

### Option A: Deploy to AWS Lambda

1. **Create Lambda function:**
```bash
aws lambda create-function \
  --function-name langchain-agent-function \
  --runtime python3.11 \
  --role arn:aws:iam::YOUR_AWS_ACCOUNT_ID:role/lambda-execution-role \
  --handler lambda_handler.lambda_handler \
  --timeout 60 \
  --memory-size 512 \
  --environment Variables='{\
    LLM_PROVIDER=perplexity,\
    PERPLEXITY_API_KEY=your-key-from-secrets-manager\
  }'
```

2. **Create Lambda execution role:**
```bash
aws iam create-role \
  --role-name lambda-execution-role \
  --assume-role-policy-document '{
    "Version": "2012-10-17",
    "Statement": [{
      "Effect": "Allow",
      "Principal": {"Service": "lambda.amazonaws.com"},
      "Action": "sts:AssumeRole"
    }]
  }'

aws iam attach-role-policy \
  --role-name lambda-execution-role \
  --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole

# Add Secrets Manager access
aws iam put-role-policy \
  --role-name lambda-execution-role \
  --policy-name SecretsManagerAccess \
  --policy-document '{
    "Version": "2012-10-17",
    "Statement": [{
      "Effect": "Allow",
      "Action": "secretsmanager:GetSecretValue",
      "Resource": "arn:aws:secretsmanager:us-east-1:YOUR_AWS_ACCOUNT_ID:secret:*"
    }]
  }'
```

### Option B: Deploy to ECS Fargate

1. **Create ECS cluster:**
```bash
aws ecs create-cluster --cluster-name langchain-agent-cluster
```

2. **Register task definition** (use provided `ecs-task-definition.json`)

3. **Create service:**
```bash
aws ecs create-service \
  --cluster langchain-agent-cluster \
  --service-name langchain-agent-service \
  --task-definition langchain-agent:1 \
  --desired-count 1
```

## Step 6: Configure Secrets Manager

Store API keys securely in AWS Secrets Manager:

```bash
# Store Perplexity API key
aws secretsmanager create-secret \
  --name perplexity-api-key \
  --secret-string "your-api-key-here"

# Store as JSON (recommended)
aws secretsmanager create-secret \
  --name langchain-agent/credentials \
  --secret-string '{
    "perplexity_api_key": "your-perplexity-key",
    "openai_api_key": "your-openai-key"
  }'
```

Update `llm_config.py` to retrieve from Secrets Manager:

```python
import json
import boto3

def get_secret(secret_name: str) -> str:
    client = boto3.client('secretsmanager', region_name='us-east-1')
    response = client.get_secret_value(SecretId=secret_name)
    
    if 'SecretString' in response:
        return json.loads(response['SecretString'])
    return None
```

## Step 7: Running Tests Locally

Before pushing, test locally:

```bash
# Install test dependencies
pip install pytest pytest-cov flake8 black isort bandit safety

# Run linting
flake8 .
black --check .
isort --check-only .

# Run unit tests with coverage
pytest tests/ -v --cov=. --cov-report=html

# Run security checks
bandit -r .
safety check

# Build Docker image locally
docker build -t langchain-agent:latest .
docker run -it --env-file .env langchain-agent:latest
```

## Troubleshooting

### Pipeline Failures

1. **Build fails:** Check Python syntax with `python -m py_compile langchain-agent.py`
2. **Tests fail:** Run locally with `pytest tests/ -v`
3. **Deploy fails:** Check Lambda permissions and CloudWatch logs
4. **Docker build fails:** Verify `requirements.txt` is correct

### Credential Issues

1. **API key not found:** Check Secrets Manager or `.env` file
2. **AWS authentication fails:** Verify IAM role and OIDC configuration
3. **Lambda timeout:** Increase timeout in Lambda configuration

### Monitor Deployments

```bash
# View Lambda function logs
aws logs tail /aws/lambda/langchain-agent-function --follow

# Check Lambda function status
aws lambda get-function --function-name langchain-agent-function

# View recent invocations
aws lambda list-functions
```

## Next Steps

1. **Add more comprehensive tests** - Create tests specific to your AWS infrastructure queries
2. **Set up monitoring** - CloudWatch dashboards for Lambda invocations and errors
3. **Add canary deployments** - Gradual rollout of new versions
4. **Configure auto-scaling** - For ECS deployments with high traffic
5. **Add approval gates** - Require manual approval before production deployment

## References

- [GitHub Actions OIDC AWS Documentation](https://docs.github.amazon.com/en/actions/deployment/security-hardening-your-deployments/about-security-hardening-with-openid-connect)
- [AWS Lambda Deployment Package](https://docs.aws.amazon.com/lambda/latest/dg/python-package.html)
- [ECS Task Definition Reference](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task_definition_parameters.html)
- [AWS Secrets Manager Best Practices](https://docs.aws.amazon.com/secretsmanager/latest/userguide/best-practices.html)
