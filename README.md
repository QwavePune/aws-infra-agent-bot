# AWS Infrastructure Agent Bot 🤖🚀

An advanced AI-powered agent designed to provision and manage AWS infrastructure based on natural language requirements. Built using **LangChain**, **Model Context Protocol (MCP)**, and **Terraform**, this agent provides a seamless bridge between human intent and production-ready cloud resources.

## 🌟 True Purpose
The primary goal of this project is to empower users to build and manage complex AWS infrastructure by simply describing their requirements in plain English. The agent handles the heavy lifting of generating Terraform configurations, planning changes, and safely executing deployments.

---

## ✨ Key Features

### 🏗️ AWS Infrastructure as Code (IaC)
- **Terraform Integration:** Automatically generates, plans, and applies Terraform configurations with environment-aware execution.
- **Production Templates:** Sophisticated patterns for **Multi-AZ VPCs**, **RDS PostgreSQL**, **AWS Lambda**, and EC2 with automatic Security Group provisioning.
- **Safe Execution:** Implements a "Plan-First" workflow with raw tool output visibility and `-input=false` protection for stable deployments.

### 🖥️ AG-UI Console (Web Interface)
- **Real-time Streaming:** Uses Server-Sent Events (SSE) for a fast, token-by-token interactive chat experience.
- **AWS Profile Selector:** Dynamically switch between AWS CLI profiles (SSO support included) directly from the UI.
- **Identity Awareness:** Real-time verification of the active AWS Account ID and IAM User/Role in the header.

### 🤖 Advanced CLI Agent
- **Infrastructure Ready:** The `langchain-agent.py` CLI is a full-featured infrastructure engine, supporting the same tool-calling loops as the Web UI.
- **Identity Check:** Automatically verifies AWS session health and profile context on startup.
- **Multi-LLM Setup:** centralized `setup_keychain.py` for configuring OpenAI, Gemini, Perplexity, and more.

---

## 🚀 Getting Started

### 📦 Prerequisites
- **Python 3.9+**
- **Terraform** installed on your system.
- **AWS CLI** configured (`aws configure` or SSO).

### 🛠️ Installation
1. **Clone the repository:**
   ```bash
   git clone <repo-url>
   cd aws-infra-agent-bot
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Setup API Keys:**
   ```bash
   python3 setup_keychain.py
   ```
   Choose your preferred storage (Local Keyring, AWS, or Azure) and enter your LLM API keys (e.g., Anthropic, OpenAI).

### 🏃 Running the Agent
1. **Start the Backend Server:**
   ```bash
   python3 agui_server.py
   ```
2. **Open the UI:**
   Navigate to `http://localhost:8000` in your browser.

---

## 📖 How to Use

1. **Authenticate:** Click **"CLI Login"** in the top bar to ensure the agent has access to your AWS session.
2. **Select MCP:** Ensure **"AWS Infrastructure (Terraform)"** is selected in the MCP Server dropdown.
3. **Describe Infrastructure:**
   - *"Build a VPC in us-east-1 with a public and private subnet."*
   - *"Create a t3.micro EC2 instance with port 80 open."*
4. **Review & Apply:**
   - The agent will generate the config and show you a **Terraform Plan**.
   - Type *"Apply it"* or *"Go ahead"* to execute the deployment.
   - Monitor the **Dark Tool Box** for real-time success/error logs from Terraform.

---

## 🏗️ Project Structure
- `agui_server.py`: FastAPI backend handling model routing and tool execution.
- `mcp_servers/`: Contains the AWS/Terraform MCP server implementation.
- `ui/`: Modern web frontend (HTML/JS/CSS).
- `llm_config.py`: Centralized LLM and credential management.
- `terraform_workspace/`: Local directory where the agent generates and manages IaC code.

---

## 🛡️ Best Practices
- **Plan Review:** Always review the Terraform Plan output before giving the final "apply" command.
- **Least Privilege:** Ensure your AWS CLI user has only the necessary permissions for the resources you intend to build.
- **Cleanup:** Use the agent to *"destroy the infrastructure"* when you are finished testing to avoid unnecessary AWS costs.

---

## 📜 License
MIT
