# LangChain Perplexity Agent

A secure LangChain agent configured to use the Perplexity API with multiple credential storage options:
- Local keyring (macOS Keychain, Windows Credential Manager, Linux Secret Service)
- Azure KeyVault (cloud-based, cross-platform)

## Security Features

This project implements multiple layers of secure credential management:

### 1. **Local System Keyring** 🔐 (Recommended for local development)
- **macOS**: Keychain (encrypted by OS)
- **Windows**: Credential Manager (encrypted by Windows)
- **Linux**: Secret Service / pass (OS-managed encryption)

### 2. **Azure KeyVault** ☁️ (Recommended for cloud/teams)
- Cloud-based secret management
- Works across all platforms
- Audit logs and access control
- Managed by Azure

### 3. **Environment Variables (.env fallback)**
If neither keyring nor KeyVault is available, credentials can be loaded from a `.env` file (excluded from git).

### 4. **No hardcoded secrets**
API keys are never stored in code or committed to version control.

## Setup Instructions

### Option 1: Local Keyring (Recommended for local development)

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Store API key in local keyring:**
   ```bash
   python3 setup_keychain.py
   ```
   Choose option 1 when prompted, then enter your Perplexity API key.

3. **Run the agent:**
   ```bash
   python3 langchain-agent.py
   ```

### Option 2: Azure KeyVault (Recommended for teams/cloud)

#### Prerequisites:
- Azure subscription and KeyVault created
- Azure CLI installed and authenticated: `az login`
- Permissions to manage secrets in the KeyVault

#### Setup:

1. **Install Azure dependencies:**
   ```bash
   pip install azure-identity azure-keyvault-secrets
   ```

2. **Store API key in Azure KeyVault:**
   ```bash
   python3 setup_keychain.py
   ```
   Choose option 2 when prompted, then:
   - Enter your KeyVault URL (e.g., `https://mykeyvault.vault.azure.net/`)
   - Enter your Perplexity API key
   
   The script will:
   - Authenticate to Azure using `DefaultAzureCredential`
   - Store your API key securely in KeyVault
   - Save the KeyVault URL to `.env`

3. **Run the agent:**
   ```bash
   python3 langchain-agent.py
   ```

#### Azure Authentication Methods (in order of priority):
1. **Service Principal** (environment variables):
   ```bash
   export AZURE_CLIENT_ID=<client-id>
   export AZURE_CLIENT_SECRET=<client-secret>
   export AZURE_TENANT_ID=<tenant-id>
   ```

2. **Azure CLI**: `az login`

3. **Managed Identity** (when running in Azure services)

4. **Visual Studio Code** (if authenticated)

### Option 3: Environment File (.env)

If you prefer not to use system keyring or Azure KeyVault:

1. Copy the template:
   ```bash
   cp .env.example .env
   ```

2. Edit `.env` and add your API key:
   ```
   PERPLEXITY_API_KEY=your_api_key_here
   ```

3. Run the agent:
   ```bash
   python3 langchain-agent.py
   ```

**Important:** Never commit `.env` to version control. It's already in `.gitignore`.

## Credential Retrieval Priority

The agent retrieves credentials in this order:

1. **Local Keyring** (if available)
2. **Azure KeyVault** (if configured)
3. **.env file** (if `PERPLEXITY_API_KEY` is set)
4. **Environment variable** (if `PERPLEXITY_API_KEY` is set in shell)

## Managing Credentials

### Local Keyring

#### View stored keyring credentials:
```bash
# macOS
security dump-keychain | grep langchain-agent

# Linux
secret-tool search service langchain-agent
```

#### Update keyring credentials:
```bash
python3 setup_keychain.py
# Choose option 1
```

#### Delete keyring credentials:
```bash
# macOS
security delete-generic-password -s "langchain-agent" -a "perplexity"

# Linux
secret-tool clear service langchain-agent username perplexity
```

### Azure KeyVault

#### View stored KeyVault secrets:
```bash
az keyvault secret list --vault-name <vault-name>
az keyvault secret show --vault-name <vault-name> --name perplexity-api-key
```

#### Update KeyVault credentials:
```bash
python3 setup_keychain.py
# Choose option 2
```

#### Delete KeyVault credentials:
```bash
az keyvault secret delete --vault-name <vault-name> --name perplexity-api-key
```

## Files

- `langchain-agent.py` - Main agent script
- `setup_keychain.py` - Interactive script to store API key in Keychain
- `.env.example` - Template for environment variables
- `.env` - Environment file (git-ignored, created by user)
- `.gitignore` - Excludes sensitive files from version control

## Getting API Keys

- **Perplexity API**: https://www.perplexity.ai/

## Security Best Practices

✅ **Do:**
- Use macOS Keychain for production/personal machines
- Use environment variables for CI/CD pipelines
- Keep `.env` out of version control
- Rotate API keys regularly

❌ **Don't:**
- Commit `.env` files to git
- Hardcode secrets in code
- Share API keys via email or chat
- Use the same key across multiple projects

## Troubleshooting

### "PERPLEXITY_API_KEY not found"
- Run `python3 setup_keychain.py` to store key in local keyring or Azure KeyVault, OR
- Create `.env` file with your API key

### Local keyring not working
- **macOS**: Ensure Keychain is accessible
- **Windows**: Ensure Windows Credential Manager is working
- **Linux**: Install Secret Service: `sudo apt-get install libsecret-1-dev`
- Try the `.env` file fallback method
- Check that `keyring` is installed: `pip list | grep keyring`

### Azure KeyVault not working
- Ensure you're authenticated: `az login`
- Check KeyVault URL is correct
- Verify you have permissions to manage secrets
- Check that Azure packages are installed: `pip list | grep azure`

### Cross-platform Recommendations

#### For Local Development (single machine):
- **Use Local Keyring**
- Simple setup with `python3 setup_keychain.py`
- No additional cloud infrastructure needed

#### For Teams / Production:
- **Use Azure KeyVault**
- Shared, auditable, cloud-managed
- Supports multiple authentication methods
- Works across all platforms

#### For CI/CD Pipelines:
- Use Azure KeyVault with service principal authentication
- Or use environment variables (set securely in CI/CD system)

## License

MIT