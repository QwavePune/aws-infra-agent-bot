# Application Architecture 🏗️

This document describes the high-level architecture of the AWS Infrastructure Agent Bot, illustrating the flow from credential setup to multi-interface interaction and automated infrastructure provisioning.

## 🗺️ System Overview

```mermaid
graph TD
    subgraph Setup_Phase [1. Credential Setup]
        U[User] -->|Runs| SK[setup_keychain.py]
        SK -->|Encrypts & Stores Keys| SS{Secret Storage}
        subgraph Secret_Storage [Storage Backends]
            SS --> LK[Local Keyring]
            SS --> AKV[Azure KeyVault]
            SS --> ASM[AWS Secrets Manager]
            SS --> ENV[.env File]
        end
    end

    subgraph Interface_Layers [2. Interaction Interfaces]
        U -->|Browses to localhost:8000| UI[AG-UI Web Console]
        U -->|Runs Terminal Command| CLI[langchain-agent.py]
    end

    subgraph Core_Engine [3. Core Agent Logic]
        UI -->|SSE / REST| AS[agui_server.py - FastAPI]
        CLI -->|Python Library| LC[LangChain Agent Engine]
        AS --> LC

        LC -->|Retrieves Keys| LC_CONF[llm_config.py]
        LC_CONF --> SS
        
        LC -->|Natural Language Query| LLM[LLM Provider: Gemini / OpenAI / Claude]
        LLM -->|Tool Call| LC
    end

    subgraph Execution_Layer [4. Infrastructure Provisioning]
        LC -->|Execute Intent| MCP[AWS Terraform MCP Server]
        MCP -->|Generates HCL| TF[Terraform Binary]
        TF -->|Apply / Plan| AWS((AWS Cloud Infrastructure))
        
        subgraph Workspace [Filesystem]
            TF <---> TWS[./terraform_workspace/]
        end
    end

    subgraph Serverless_Deployment [5. Continuous Operations]
        LH[lambda_handler.py] -->|Shared Logic| LC
        CW[CloudWatch / EventBridge] -->|Trigger| LH
    end

    %% Styling
    style U fill:#f9f,stroke:#333,stroke-width:2px
    style AWS fill:#ff9900,stroke:#333,stroke-width:2px
    style SS fill:#00c,color:#fff
    style LLM fill:#4285F4,color:#fff
    style TF fill:#623ce4,color:#fff
```

## 🔍 Component Descriptions

| Component | Responsibility |
| :--- | :--- |
| **`setup_keychain.py`** | Securely captures LLM API keys and stores them in your preferred vault (Keyring, AWS, Azure). |
| **`llm_config.py`** | Central engine for provider mapping and multi-source credential retrieval. |
| **`agui_server.py`** | FastAPI backend that manages chat sessions and streams responses via Server-Sent Events (SSE). |
| **`langchain-agent.py`** | The CLI interface that provides the exact same infrastructure logic in a terminal environment. |
| **`aws_terraform_server.py`** | The MCP server that translates LLM intents into real Terraform code and manages the deployment lifecycle. |
| **`lambda_handler.py`** | Wraps the agent logic into a serverless function for remote triggers or API integration. |
| **`terraform_workspace/`** | The directory where the agent generates, manages, and tracks the state of your infrastructure. |
