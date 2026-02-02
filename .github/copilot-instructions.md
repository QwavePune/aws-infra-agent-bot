# Copilot Instructions for LangChain AWS Infrastructure Agent

## Project Overview
This is a **multi-LLM interactive agent** built with LangChain that supports conversation history and pluggable credential storage. It's designed to help with AWS infrastructure queries while maintaining security through flexible credential management.

**Key characteristics:**
- Multi-provider LLM support (Perplexity, OpenAI, Claude, Gemini, Ollama)
- Stateful conversation tracking via `conversation_history` list
- Pluggable credential sources (local keyring, Azure KeyVault, AWS Secrets Manager)
- Session logging to `.agent-session.log`

## Architecture Patterns

### LLM Provider Registration
Providers are defined in [llm_config.py](llm_config.py) via `SUPPORTED_LLMS` dictionary. When adding new providers:
- Add entry to `SUPPORTED_LLMS` with package, class name, default model
- Implement credential retrieval using `get_api_key()` function which tries sources in order: local keyring → Azure KeyVault → AWS Secrets Manager → .env → environment variable
- Update [setup_keychain.py](setup_keychain.py) to support credential setup for new providers

### Conversation State Management
[langchain-agent.py](langchain-agent.py) maintains conversation context via:
```python
conversation_history = []  # List of HumanMessage/AIMessage objects
response = llm.invoke(conversation_history)  # Pass full history for context
conversation_history.append(AIMessage(content=response.content))  # Append responses
```
Commands like `clear` reset history by reassigning the list. This pattern enables true multi-turn dialogue.

### Credential Abstraction
The `get_api_key()` function in [llm_config.py](llm_config.py) implements a **credential priority chain** (lines 66-160+). Use this pattern when adding new credential sources:
1. Check preferred source first (if specified)
2. Fall back to priority order (local → Azure → AWS → .env → env var)
3. Log source for debugging in `.agent-session.log`

## Critical Developer Workflows

### Setup & Initialization
```bash
# 1. Create virtual environment
scripts/setup_env.sh

# 2. Store credentials (interactive, supports multiple backends)
python3 setup_keychain.py
# Or directly: python3 setup_keychain.py local

# 3. Run agent
scripts/run_agent.sh  # Uses venv's python
# Or: python3 langchain-agent.py
```

### Debugging
- Session logs: `.agent-session.log` (INFO level, includes timestamps and provider info)
- Enable debug logs: Set logging level to `DEBUG` in [langchain-agent.py](langchain-agent.py) line 10
- Check credential source: Script prints `[INFO] API key retrieved from: <source>` on startup
- Verify environment: `python3 check_env.py` shows any API keys in environment

### Adding a New LLM Provider
1. Update `SUPPORTED_LLMS` in [llm_config.py](llm_config.py) with provider config
2. Update `initialize_llm()` function in [llm_config.py](llm_config.py) to handle provider imports
3. Add setup branch to `setup_keychain.py` (e.g., `setup_<provider>_keyring()`)
4. Test via: `LLM_PROVIDER=<provider> python3 langchain-agent.py`

## Project-Specific Conventions

### File Organization
- **Core agents:** `langchain-*.py` files (main agent is `langchain-agent.py`, groq variant in `langchain-groq.py`)
- **Configuration:** `llm_config.py` (all LLM logic), `setup_keychain.py` (credential setup)
- **Scripts:** `scripts/` contains shell automation (always uses venv's python)
- **Documentation:** `README.md` (user guide), `CREDENTIAL_STORAGE.md` (credential deep dive)

### Logging Standards
- Use `logging` module with format: `%(asctime)s - %(name)s - %(levelname)s - %(message)s`
- Always log session start/end and credential source for auditing
- Avoid logging sensitive content (API keys, full queries); log lengths/metadata instead
- Session logs append to `.agent-session.log` (not overwritten each run)

### Credential Handling
- **Never hardcode secrets** - all API keys come from credential functions
- **Priority chain test:** Check credential source via print statement in interactive flow
- **Azure auth:** Uses `DefaultAzureCredential` (supports service principals via `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_CLIENT_SECRET`)
- **AWS auth:** Uses `boto3` with AWS credential chain (SDK auto-detects credentials)
- **.env exclusion:** `.env` is in `.gitignore` - safe for local testing, never committed

### Error Handling Pattern
[langchain-agent.py](langchain-agent.py) demonstrates the expected pattern:
```python
try:
    llm = initialize_llm(llm_provider, temperature=0, preferred_source=credential_source)
except Exception as e:
    logger.error(f"Failed to initialize: {str(e)}", exc_info=True)
    sys.exit(1)
```
- Log full traceback with `exc_info=True` for debugging
- Print user-friendly error messages separately from logs
- Exit cleanly on initialization failure

## External Dependencies
- **LangChain ecosystem:** langchain-core, langchain-{groq,perplexity,openai,anthropic,google_genai,ollama}
- **Cloud SDKs:** azure-identity, azure-keyvault-secrets (Azure), boto3 (AWS)
- **Credential storage:** keyring (local system keychains)
- **Utilities:** python-dotenv (environment loading), invoke/fabric (task automation)

## Testing Notes
- `langchain-groq.py` is a standalone test agent with a calculator tool (not integrated into main agent)
- For credential testing: `python3 setup_keychain.py` then `python3 langchain-agent.py` with interactive LLM selection
- For environment checks: `python3 check_env.py` scans for API key environment variables
