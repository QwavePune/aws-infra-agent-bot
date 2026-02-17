# Architecture-Driven Deployment System - Architecture Overview

## System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                         User Interfaces                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────────┐         ┌──────────────────┐              │
│  │  Web UI (HTML)   │         │  CLI/Python      │              │
│  │  - Upload Image  │         │  - API Client    │              │
│  │  - Enter Mermaid │         │  - Scripts       │              │
│  │  - View Results  │         │  - Automation    │              │
│  └────────┬─────────┘         └────────┬─────────┘              │
│           │                           │                          │
└───────────┼───────────────────────────┼──────────────────────────┘
            │                           │
            └───────────────┬───────────┘
                            │
                    ┌───────▼────────┐
                    │  AGUI Server   │ (Port 9595)
                    │  (FastAPI)     │
                    └───────┬────────┘
                            │
        ┌───────────────────┼───────────────────┐
        │                   │                   │
        │                   │                   │
    ┌───▼────┐         ┌────▼────┐        ┌────▼────┐
    │ Parse  │         │Generate │        │ Deploy  │
    │Mermaid │         │Terraform│        │Infra    │
    └───┬────┘         └────┬────┘        └────┬────┘
        │                   │                   │
        │                   │                   │
    ┌───▼──────────────────────────────────────▼────┐
    │                                                │
    │  ArchitectureParser (core module)             │
    │  ┌────────────────────────────────────────┐   │
    │  │ • Mermaid Parsing                      │   │
    │  │ • Image Analysis (Claude Vision)       │   │
    │  │ • Terraform Code Generation            │   │
    │  │ • Service Recognition                  │   │
    │  └────────────────────────────────────────┘   │
    └───┬──────────────────────────────────────┬────┘
        │                                      │
    ┌───▼────────────────┐            ┌───────▼──────────┐
    │ LLM Provider        │            │ MCP Server       │
    │ • Claude           │            │ • terraform_plan │
    │ • OpenAI           │            │ • terraform_apply│
    │ • Gemini           │            │ • terraform_init │
    │ (Vision API)       │            │ • terraform tools│
    └────────────────────┘            └───────┬──────────┘
                                               │
                                    ┌──────────▼─────────┐
                                    │ Terraform Executor │
                                    │ (subprocess)       │
                                    └──────────┬─────────┘
                                               │
                                   ┌───────────▼──────────┐
                                   │ AWS Infrastructure   │
                                   │ • EC2 Instances     │
                                   │ • RDS Databases     │
                                   │ • S3 Buckets        │
                                   │ • VPCs & Subnets    │
                                   │ • Load Balancers    │
                                   │ • ... (30+ services)│
                                   └─────────────────────┘
```

## Data Flow Diagram

```
User provides architecture
        │
        ├─────────────────────────────────┬─────────────────────────────────┐
        │                                 │                                 │
        ▼                                 ▼                                 ▼
    ┌─────────────┐              ┌──────────────┐              ┌──────────────┐
    │ Mermaid     │              │ Image File   │              │ JSON Arch.   │
    │ Text        │              │ (PNG/JPG)    │              │ Dict         │
    └──────┬──────┘              └───────┬──────┘              └──────┬───────┘
           │                             │                            │
           │ Parse                       │ Analyze                    │ Convert
           │ (Regex extraction)          │ (Claude Vision API)        │ (Direct)
           │                             │                            │
           └─────────────┬───────────────┴────────────────────────────┘
                         │
                         ▼
              ┌────────────────────────┐
              │ Architecture JSON      │
              │ {                      │
              │   resources: [...],    │
              │   relationships: [...],│
              │   network: {...}       │
              │ }                      │
              └────────────┬───────────┘
                           │
                    Generate (LLM)
                           │
                           ▼
              ┌────────────────────────┐
              │ Terraform Code         │
              │ (HCL format)           │
              │ main.tf                │
              └────────────┬───────────┘
                           │
                   Save to Project Dir
                           │
                           ▼
              ┌────────────────────────┐
              │ terraform_workspace/   │
              │ ├── ec2_arch/          │
              │ │   ├── main.tf        │
              │ │   └── .terraform/    │
              │ └── ...                │
              └────────────┬───────────┘
                           │
              ┌────────────┴────────────┐
              │                         │
              ▼                         ▼
        ┌─────────────┐          ┌──────────────┐
        │ terraform   │          │ terraform    │
        │ init        │          │ plan         │
        └────────────┬┘          └──────┬───────┘
                     │                  │
                     └──────────┬───────┘
                                │
                                ▼
                    ┌──────────────────────────┐
                    │ Terraform Plan           │
                    │ (Ready for apply)        │
                    │ tfplan file              │
                    └──────────┬───────────────┘
                               │
                       terraform apply
                               │
                               ▼
                    ┌──────────────────────────┐
                    │ AWS Infrastructure       │
                    │ Resources Created        │
                    └──────────────────────────┘
```

## Component Interaction Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          AGUI Server (FastAPI)                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─ Endpoint ────────────────────────────────────────────────────────────┐  │
│  │ /api/architecture/parse-mermaid                                      │  │
│  │ ├─ Input: Mermaid text                                              │  │
│  │ ├─ Processor: ArchitectureParser.parse_mermaid_diagram()            │  │
│  │ └─ Output: {resources, relationships}                               │  │
│  └────────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
│  ┌─ Endpoint ────────────────────────────────────────────────────────────┐  │
│  │ /api/architecture/parse-image                                       │  │
│  │ ├─ Input: Image file (PNG/JPG/GIF/WebP)                            │  │
│  │ ├─ Processor: ArchitectureParser.parse_architecture_image()        │  │
│  │ │  └─ Uses: Claude Vision API                                     │  │
│  │ └─ Output: {resources, relationships, network}                     │  │
│  └────────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
│  ┌─ Endpoint ────────────────────────────────────────────────────────────┐  │
│  │ /api/architecture/generate-terraform                                │  │
│  │ ├─ Input: Architecture JSON                                         │  │
│  │ ├─ Processor: ArchitectureParser.architecture_to_terraform()       │  │
│  │ │  └─ Uses: Claude LLM                                            │  │
│  │ └─ Output: {terraform_code, project_name}                         │  │
│  └────────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
│  ┌─ Endpoint ────────────────────────────────────────────────────────────┐  │
│  │ /api/architecture/deploy                                           │  │
│  │ ├─ Input: Architecture JSON                                         │  │
│  │ ├─ Step 1: Generate Terraform                                      │  │
│  │ ├─ Step 2: Create project directory                               │  │
│  │ ├─ Step 3: Run terraform init (via MCP)                          │  │
│  │ ├─ Step 4: Run terraform plan (via MCP)                          │  │
│  │ └─ Output: {plan_result, project_name}                            │  │
│  └────────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
└──────────────┬──────────────────────────────────────────────────────┬────────┘
               │                                                      │
               │ Uses                                                 │ Uses
               │                                                      │
   ┌───────────▼──────────────┐                        ┌─────────────▼────┐
   │ ArchitectureParser       │                        │ MCP Server       │
   │ (core/architecture_parser)                        │ (aws_terraform)  │
   │                          │                        │                  │
   │ • parse_mermaid_diagram()│                        │ • terraform_init │
   │ • parse_architecture_img()                        │ • terraform_plan │
   │ • architecture_to_tf()   │                        │ • terraform_apply│
   │ • Service detection      │                        │                  │
   │ • Terraform generation   │                        │ [Uses Terraform] │
   │                          │                        │                  │
   └──────────┬───────────────┘                        └────────┬─────────┘
              │                                                │
              │ Uses Claude Vision & LLM                      │ Executes via subprocess
              │                                                │
              └────┬──────────────────────┬───────────────────┘
                   │                      │
         ┌─────────▼──────┐      ┌────────▼────────┐
         │ Claude API     │      │ Terraform CLI   │
         │ • Vision       │      │ • init          │
         │ • Completions │      │ • plan          │
         │                │      │ • apply         │
         │                │      │ • destroy       │
         └────────────────┘      └────────┬────────┘
                                          │
                                ┌─────────▼──────────┐
                                │ AWS API (boto3)    │
                                │ • EC2              │
                                │ • S3               │
                                │ • RDS              │
                                │ • ... (30+ services)
                                └────────────────────┘
```

## Service Recognition Flow

```
Input Text/Image
        │
        ▼
Service Keyword Detection
        │
        ├─ "ec2" / "instance" ───────────→ EC2
        ├─ "s3" / "bucket" ──────────────→ S3
        ├─ "rds" / "database" ──────────→ RDS
        ├─ "lambda" / "function" ───────→ Lambda
        ├─ "vpc" / "network" ───────────→ VPC
        ├─ "alb" / "load" ──────────────→ Load Balancer
        ├─ "dynamodb" / "table" ────────→ DynamoDB
        ├─ "api" / "gateway" ───────────→ API Gateway
        ├─ "cache" / "redis" ───────────→ ElastiCache
        ├─ "sqs" / "queue" ─────────────→ SQS
        ├─ "sns" / "topic" ─────────────→ SNS
        ├─ "s3" / "storage" ────────────→ S3
        ├─ "cloudfront" / "cdn" ────────→ CloudFront
        ├─ "iam" / "role" ──────────────→ IAM
        └─ ... (30+ patterns)
        │
        ▼
Resource JSON Object
{
  "type": "ec2",
  "name": "web-server",
  "details": {...}
}
```

## Deployment Timeline

```
Time    Action                          Duration    Output
────────────────────────────────────────────────────────────────
T+0s    User uploads architecture       -           File received
        │
T+1s    Parse/Analyze                   1-3s        Architecture JSON
        │
T+4s    Generate Terraform               5-15s       terraform_code
        │
T+19s   Create project directory         1s          Project ready
        │
T+20s   terraform init                   10-30s      .terraform/ created
        │
T+50s   terraform plan                   10-30s      tfplan generated
        │
T+80s   Ready for apply                  -           User can review
        │
        [User reviews plan]
        │
T+??s   terraform apply                  varies      Infrastructure live
        │
T+end   Deployment complete              -           Resources created
```

## Technology Stack

```
Frontend Layer
├── HTML/CSS/JavaScript
├── UI Components (React/Vue compatible)
└── API Client Library

API Layer (AGUI Server)
├── FastAPI (Python)
├── File Upload Handling
├── LLM Integration
└── REST Endpoints

Processing Layer
├── ArchitectureParser
├── Mermaid Parser (Regex)
├── LLM Vision API Integration
└── Terraform Code Generation

Infrastructure Layer
├── MCP Server
├── Terraform CLI
├── AWS SDK (boto3)
└── AWS Services (30+)

Data Flow
├── Diagrams/Images → JSON
├── JSON → Terraform Code
└── Terraform Code → AWS Resources
```

---

This architecture provides a complete, scalable, and maintainable system for architecture-driven infrastructure deployment.
