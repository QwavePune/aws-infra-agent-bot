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
The **Interactive CLI Agent**. A robust terminal-based interface for chatting with your configured LLMs.

### Features:
- **Multi-turn Conversation**: Remembers previous messages in the session.
- **Provider Switching**: Choose which AI model to talk to at startup.
- **Session Logging**: Automatically saves a transcript of your session to `.agent-session.log`.

### Usage:
1. **Start the agent**:
   ```bash
   python3 langchain-agent.py
   ```
2. **Commands within the chat**:
   - `help`: Show available commands.
   - `clear`: Reset the current conversation history.
   - `quit` or `exit`: Safely end the session.

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
