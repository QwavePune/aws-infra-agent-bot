# LangChain Perplexity Agent

An interactive LangChain agent that uses the Perplexity API with:
- **Multi-turn conversation support** - Maintains context across queries
- **Multiple credential storage options** - Choose what works best for you
  - Local keyring (macOS Keychain, Windows Credential Manager, Linux Secret Service)
  - Azure KeyVault (cloud-based, cross-platform)
  - AWS Secrets Manager (cloud-based)
- **Interactive CLI** - Ask questions and maintain conversation history

## Features

### 🤖 Interactive Conversation
- Ask multiple questions in a single session
- Maintains conversation history and context
- Each query is aware of previous interactions
- Exit with `Ctrl+C` or by typing `quit`/`exit`

### 🔐 Multiple Credential Storage Options
1. **Local System Keyring** (Recommended for local development)
   - macOS Keychain, Windows Credential Manager, Linux Secret Service
   - Encrypted by your OS
   - No cloud dependency

2. **Azure KeyVault** (Recommended for teams/cloud)
   - Cloud-based secret management
   - Audit logs and access control
   - Works across all platforms

3. **AWS Secrets Manager** (Recommended for AWS users)
   - AWS-native secret management
   - Integration with AWS services
   - Audit trails and rotation policies

4. **Environment Variables** (.env fallback)
   - For testing and local development
   - Never committed to version control

### 🛡️ Security Features
- No hardcoded secrets in code
- API keys excluded from version control
- Flexible credential priority chain
- Support for CI/CD pipelines

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

### Option 3: AWS Secrets Manager (Recommended for AWS users)

#### Prerequisites:
- AWS account with access to Secrets Manager
- AWS CLI installed and configured: `aws configure`
- IAM permissions to manage secrets

#### Setup:

1. **Install AWS dependencies:**
   ```bash
   pip install boto3
   ```

2. **Store API key in AWS Secrets Manager:**
   ```bash
   python3 setup_keychain.py
   ```
   Choose option 3 when prompted, then:
   - Enter your AWS region (e.g., `us-east-1`)
   - Enter your Perplexity API key (or press Enter for default secret name)
   
   The script will:
   - Authenticate using AWS credentials from `aws configure`
   - Create or update the secret in Secrets Manager
   - Save the AWS config to `.env`

3. **Run the agent:**
   ```bash
   python3 langchain-agent.py
   ```

#### AWS Authentication Methods:
1. **AWS CLI**: `aws configure` (simplest)
2. **Environment Variables**:
   ```bash
   export AWS_ACCESS_KEY_ID=<your-key-id>
   export AWS_SECRET_ACCESS_KEY=<your-secret-key>
   export AWS_DEFAULT_REGION=<region>
   ```
3. **IAM Role** (when running in AWS services)

### Option 4: Environment File (.env)

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

## Running the Agent

### Interactive Mode (Recommended)

```bash
python3 langchain-agent.py
```

This will start an interactive session where you can:
1. Ask your first question
2. Receive an answer with full context retention
3. Ask follow-up questions that build on previous answers
4. Continue the conversation indefinitely
5. Exit with `Ctrl+C` or by typing `quit`/`exit`

#### Example Session:
```
==================================================
Running agent with Perplexity API
==================================================

Enter your query (or 'quit' to exit): What is 87 * 45?

[INFO] Using API key from local keyring
FINAL RESULT:
87 × 45 = 3915.

Enter your query (or 'quit' to exit): Write a poem about that number

FINAL RESULT:
Thirty-nine fifteen sings, a mathematical delight...
(The agent remembers the previous answer!)

Enter your query (or 'quit' to exit): quit
Goodbye!
```

## Managing Credentials

### Credential Retrieval Priority

The agent retrieves credentials in this order:

1. **Local Keyring** (if available)
2. **Azure KeyVault** (if `AZURE_KEYVAULT_URL` is set)
3. **AWS Secrets Manager** (if `AWS_REGION` is set)
4. **.env file** (if `PERPLEXITY_API_KEY` is set)
5. **Environment variable** (if `PERPLEXITY_API_KEY` is set in shell)

This allows flexible deployment across different environments.

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

### AWS Secrets Manager

#### View stored secrets:
```bash
aws secretsmanager list-secrets --region <region>
aws secretsmanager get-secret-value --secret-id perplexity-api-key --region <region>
```

#### Update credentials:
```bash
python3 setup_keychain.py
# Choose option 3
```

#### Delete a secret:
```bash
aws secretsmanager delete-secret --secret-id perplexity-api-key --region <region>
```

## Files

- `langchain-agent.py` - Main interactive agent script with conversation history
- `setup_keychain.py` - Interactive credential setup tool (Local Keyring, Azure KeyVault, AWS Secrets Manager)
- `.env.example` - Template for environment variables
- `.env` - Environment file (git-ignored, created by user)
- `.gitignore` - Excludes sensitive files from version control
- `README.md` - This file
- `CREDENTIAL_STORAGE.md` - Detailed credential storage reference guide

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
- Run `python3 setup_keychain.py` to store key in local keyring, Azure KeyVault, or AWS Secrets Manager
- Or create `.env` file with your API key

### Conversation not maintaining context
- The agent automatically maintains conversation history in memory
- Context is lost when you exit the program (this is expected)
- Each new session starts fresh
- To maintain conversations across sessions, consider logging or persistence features

### Local keyring not working
- **macOS**: Ensure Keychain is accessible
- **Windows**: Ensure Windows Credential Manager is working
- **Linux**: Install Secret Service: `sudo apt-get install libsecret-1-dev`
- Try the `.env` file fallback method
- Check that `keyring` is installed: `pip list | grep keyring`

### Azure KeyVault not working
- Ensure you're authenticated: `az login`
- Check KeyVault URL is correct in `.env` or `AZURE_KEYVAULT_URL` environment variable
- Verify you have permissions to manage secrets
- Check that Azure packages are installed: `pip list | grep azure`

### AWS Secrets Manager not working
- Ensure you're authenticated: `aws configure`
- Check region is correct in `.env` or `AWS_REGION` environment variable
- Check secret name is correct: `aws secretsmanager list-secrets --region <region>`
- Verify IAM permissions to access Secrets Manager
- Check that boto3 is installed: `pip list | grep boto3`

### Exit Program Issues
- Use `Ctrl+C` to gracefully exit
- Or type `quit` or `exit` when prompted for a query
- If stuck, use `Ctrl+D` (on Unix/Linux) or `Ctrl+Z` then `Enter` (on Windows)

### Cross-platform Recommendations

#### For Local Development (single machine):
- **Use Local Keyring** 🔐
- Simple setup with `python3 setup_keychain.py`
- No additional cloud infrastructure needed
- Works offline

#### For Teams / Production:
- **Use Azure KeyVault** or **AWS Secrets Manager** ☁️
- Shared, auditable, cloud-managed
- Supports multiple authentication methods
- Access control and rotation policies
- Choose based on your cloud provider

#### For CI/CD Pipelines:
- **Use AWS Secrets Manager** (if on AWS) or **Azure KeyVault** (if on Azure)
- With service principal/role authentication
- Or use environment variables (set securely in CI/CD system)

## Dependencies

- `python-dotenv` - Load environment variables
- `keyring` - System keyring support
- `langchain-perplexity` - Perplexity API integration
- `azure-identity` (optional) - Azure authentication
- `azure-keyvault-secrets` (optional) - Azure KeyVault support
- `boto3` (optional) - AWS SDK for Secrets Manager

Install all with:
```bash
pip install -r requirements.txt
```

## License

MIT