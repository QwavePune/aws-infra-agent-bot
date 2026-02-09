# Copilot Instructions for LangChain Multi-LLM Agent

## Project Overview
This is a **multi-LLM interactive CLI agent** built with LangChain that supports multi-turn conversations with flexible credential management. It's NOT AWS-specific—it's a general-purpose agent that supports multiple LLM providers with extensible authentication.

**Core characteristics:**
- Multi-provider LLM support: Perplexity, OpenAI, Claude (Anthropic), Gemini, Groq, Ollama
- Stateful multi-turn conversations via `conversation_history` list (HumanMessage/AIMessage from langchain_core)
- Three credential backends: local keyring (OS-native), Azure KeyVault, AWS Secrets Manager
- Session logging to `.agent-session.log` with provider/source info
- Production-ready: Docker container, CI/CD pipeline, unit tests, security scans

## Architecture Patterns

### LLM Provider Registration & Initialization
Providers are defined in [llm_config.py](llm_config.py#L16-L57) via the `SUPPORTED_LLMS` dict. Key pattern:
```python
SUPPORTED_LLMS = {
    "provider_name": {
        "name": "Display Name",
        "package": "langchain_provider",
        "class": "ChatProvider",
        "default_model": "model-id",
        "requires_api_key": True,
        "env_var": "PROVIDER_API_KEY"
    }
}
```
When adding providers: Update dict → add to `initialize_llm()` with conditional import → update [setup_keychain.py](setup_keychain.py) with credential setup function.

### Conversation State Management
[langchain-agent.py](langchain-agent.py#L94) maintains conversations via:
```python
conversation_history = []  # List of HumanMessage/AIMessage objects
while True:
    user_query = input("You: ")
    conversation_history.append(HumanMessage(content=user_query))
    response = llm.invoke(conversation_history)  # Full history for context
    conversation_history.append(AIMessage(content=response.content))
```
The `clear` command resets history: `conversation_history = []`.

### Credential Abstraction Pattern
`get_api_key()` in [llm_config.py](llm_config.py#L60-L110) implements credential priority chain. When preferred source is None, it tries in order: local keyring → Azure KeyVault → AWS Secrets Manager → .env → environment variable. Logs the source used for auditing.

## Critical Developer Workflows

### Local Development Setup
```bash
# 1. Create virtual environment using provided script
scripts/setup_env.sh  # Creates venv, installs requirements.txt

# 2. Store credentials (choose one backend)
python3 setup_keychain.py
# Option 1: Local keyring (macOS Keychain, Windows Cred Manager, Linux Secret Service)
# Option 2: Azure KeyVault (requires Azure CLI auth: az login)
# Option 3: AWS Secrets Manager (requires AWS CLI auth)

# 3. Run interactive agent
python3 langchain-agent.py
# Or specify provider: LLM_PROVIDER=openai python3 langchain-agent.py
```

### Testing
```bash
# Unit tests with coverage
pytest tests/ -v --cov=. --cov-report=html

# Integration tests (AWS services)
pytest tests/integration/ -v
```

### Environment Debugging
- Check what API keys exist: `python3 check_env.py` (scans environment variables)
- View session logs: `cat .agent-session.log` (includes provider, credential source, timestamps)
- Enable debug logging: Change line 13 in [langchain-agent.py](langchain-agent.py#L13) from `logging.INFO` to `logging.DEBUG`

### Adding a New LLM Provider
1. Add entry to `SUPPORTED_LLMS` dict in [llm_config.py](llm_config.py#L16-L57)
2. Update `initialize_llm()` function to handle conditional imports (line ~200+)
3. Add setup function to [setup_keychain.py](setup_keychain.py) for credential storage
4. Test via: `LLM_PROVIDER=<provider> python3 langchain-agent.py`

### Updating Code Quality & Tests
```bash
# Format code
black . && isort .

# Run linting checks (what CI/CD runs)
flake8 . --max-complexity=10 --max-line-length=127
pytest tests/ -v --cov=.

# Security checks (what CI/CD runs)
bandit -r .  # Code vulnerabilities
safety check  # Dependency vulnerabilities
```

## Project-Specific Conventions

### File Organization
- **Core agents:** `langchain-*.py` files (main agent is `langchain-agent.py`)
- **Configuration:** `llm_config.py` (all LLM logic), `setup_keychain.py` (credential setup)
- **Scripts:** `scripts/` contains shell automation (always uses venv's python)
- **Tests:** `tests/` for unit tests, `tests/integration/` for AWS integration tests
- **Documentation:** `README.md` (user guide), `CREDENTIAL_STORAGE.md` (credential deep dive), `DEVOPS_SETUP.md` (deployment guide)

### Logging Standards
- Use `logging` module with format: `%(asctime)s - %(name)s - %(levelname)s - %(message)s`
- Always log session start/end and credential source for auditing
- Avoid logging sensitive content (API keys, full queries); log lengths/metadata instead
- Session logs append to `.agent-session.log` (not overwritten each run)
- Example from [langchain-agent.py](langchain-agent.py#L26-L30):
  ```python
  logger.info("LangChain Multi-LLM Agent Session Started")
  logger.info(f"LLM Provider: {llm_provider.upper()} (selected interactively)")
  ```

### Credential Handling
- **Never hardcode secrets** - all API keys come from credential functions
- **Priority chain test:** Check credential source via print statement in interactive flow
- **Azure auth:** Uses `DefaultAzureCredential` (supports service principals via `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_CLIENT_SECRET`)
- **AWS auth:** Uses `boto3` with AWS credential chain (SDK auto-detects credentials)
- **.env exclusion:** `.env` is in `.gitignore` - safe for local testing, never committed

### Multi-Turn Conversation Pattern
The agent maintains state via the `conversation_history` list. Key interactions:
1. User input is wrapped in `HumanMessage(content=user_query)`
2. Full history is passed to `llm.invoke(conversation_history)` - includes all prior exchanges
3. Response is wrapped in `AIMessage(content=response.content)` and appended
4. Commands: `quit`/`exit`/`q`/`x` exit; `clear` resets history; `help` shows commands
5. Session logging includes timestamps and provider info for debugging multi-turn flows

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
- For credential testing: `python3 setup_keychain.py` then `python3 langchain-agent.py` with interactive LLM selection
- For environment checks: `python3 check_env.py` scans for API key environment variables
- Unit tests in `tests/test_llm_config.py` validate provider initialization and credential retrieval
- Integration tests in `tests/integration/test_aws_integration.py` test AWS service interactions

## CI/CD Pipeline & Deployment

### Automated Pipeline (`.github/workflows/ci-cd.yml`)
The pipeline runs on every push to `main` and PR creation:
1. **Build & Lint** (Ubuntu) - Flake8, Black, isort checks; Python 3.11
2. **Unit Tests** - pytest with coverage reports (xml + html); failures don't block PR
3. **Security Scans** - Bandit (code vulnerabilities) and Safety (dependency vulnerabilities)
4. **Docker Build** - Multi-stage build (builder + runtime) for Python 3.11; pushed to ECR on main branch only
5. **Deploy to AWS** - Lambda update or ECS service deployment
6. **Integration Tests** - End-to-end tests against deployed service

### Docker Build Pattern
The Dockerfile uses multi-stage builds in [Dockerfile](Dockerfile):
- **Stage 1 (builder):** Python 3.11-slim, installs dependencies with `pip install --user --no-cache-dir`
- **Stage 2 (runtime):** Copies only user packages from builder, includes dbus for keyring support, creates non-root `agent` user
- **Health check:** Simple python -c "import sys; print('healthy')" for orchestration monitoring

### Environment Variables in CI/CD
- `AWS_REGION: ap-south-1` (defined in workflow)
- `PYTHON_VERSION: '3.11'` (defined in workflow)
- GitHub secrets required: `AWS_ROLE_ARN`, `AWS_REGION` (for OIDC authentication)

### Deployment Options
- **AWS Lambda:** Stateless, event-driven via `lambda_handler.py` - good for scheduled queries or API-driven access
- **ECS Fargate:** Containerized, long-running service - good for continuous availability
- **Both:** Use Lambda for API endpoint, ECS for background workers

### Setup Steps
1. Create AWS OIDC provider for GitHub Actions (no long-lived credentials)
2. Create IAM role with permissions for ECR, Lambda, ECS, CloudWatch
3. Add GitHub secrets: `AWS_ROLE_ARN`, `AWS_REGION`
4. Push to main branch to trigger pipeline
5. Monitor via GitHub Actions → CloudWatch Logs

See [DEVOPS_SETUP.md](DEVOPS_SETUP.md) for complete setup guide, IAM policy templates, and troubleshooting.

### Test Locally Before Deploying
```bash
pytest tests/ -v --cov=.
docker build -t langchain-agent:latest .
docker run -it --env-file .env langchain-agent:latest
```
