# LangChain Agent CLI & Configuration Guide 🛠️

This guide documents the core CLI components and configuration logic of the AWS Infrastructure Agent project. These tools provide a way to interact with the LLMs directly from your terminal and manage your API credentials securely.

---

## 🗝️ `setup_keychain.py`
The **Credential Setup Utility**. This script allows you to securely store your LLM API keys (Perplexity, Anthropic, OpenAI, etc.) in various encrypted storage backends instead of hardcoding them or leaving them in plain text.

### Usage
Run the script and follow the interactive prompts:
```bash
python3 setup_keychain.py
```

### Storage Options:
1.  **Local Keyring (Recommended for Local Dev)**: Uses your OS-native encrypted store (macOS Keychain, Windows Credential Manager, or Linux Secret Service).
2.  **Azure KeyVault**: Stores keys in a cloud-based Azure KeyVault. requires `AZURE_KEYVAULT_URL` in `.env`.
3.  **AWS Secrets Manager**: Stores keys in AWS Secrets Manager. Requires `AWS_REGION` in `.env`.

### Commands:
- `python3 setup_keychain.py local` - Setup local keyring only.
- `python3 setup_keychain.py verify` - Check if keys are correctly stored and accessible.

---

## ⚙️ `llm_config.py`
The **Configuration Engine**. This module is the "brain" for LLM management. It handles:
- **Provider Mapping**: Supports OpenAI, Anthropic, Google Gemini, Perplexity, and Ollama.
- **Credential Priority**: Automatically looks for API keys in the following order:
    1. Local Keyring
    2. Azure KeyVault
    3. AWS Secrets Manager
    4. `.env` file
    5. Environment Variables
- **LLM Initialization**: Provides the `initialize_llm()` function used by both the CLI and Web Server to create standardized LangChain ChatModel instances.

---

## 🤖 `langchain-agent.py`
The **AWS Infrastructure CLI Agent**. A robust terminal-based counterpart to the AG-UI, capable of full infrastructure management.

### Features:
- **Full Tool Support**: Can generate, plan, and apply Terraform configurations directly from the terminal.
- **Tool-Calling Loop**: Handles iterative reasoning (up to 5 turns) to resolve complex infrastructure requests.
- **Identity Awareness**: Verifies AWS Account ID and ARN at startup to ensure your session is active.
- **Environment Aware**: Option to select/change your `AWS_PROFILE` at startup.

### Usage:
1. **Start the agent**:
   ```bash
   python3 langchain-agent.py
   ```
2. **Setup**: Follow the interactive prompts to confirm your AWS profile and LLM provider.
3. **Infrastructure Management**:
   - Talk to it like a DevOps engineer: *"Deploy an RDS database for my app."*
   - Monitor the `🛠️` and `✅` status icons as it executes MCP tools.
   - Use `terraform_apply` through the agent to ship your changes.

### Environment Shortcuts:
You can skip the interactive selection by setting an environment variable:
```bash
export LLM_PROVIDER=openai
python3 langchain-agent.py
```

---

## 🛠️ Developer Setup
To use these CLI tools, ensure you have the core dependencies installed:
```bash
pip install langchain-core python-dotenv keyring boto3
```
*(Optional: `pip install azure-identity azure-keyvault-secrets` for Azure support)*
