# Credential Storage Quick Reference

## Which storage method should I use?

### Local Keyring 🔐 (Recommended for local development)
- **Platforms**: macOS, Windows, Linux
- **Setup time**: ~1 minute
- **Access**: Automatic (no additional config needed)
- **Use when**: Developing on your personal machine

```bash
python3 setup_keychain.py
# Choose option 1: Local Keyring
```

### Azure KeyVault ☁️ (Recommended for teams/production)
- **Platforms**: All (cloud-based)
- **Setup time**: ~5 minutes (if you have an Azure account)
- **Access**: Requires Azure authentication
- **Use when**: Team collaboration, production, CI/CD pipelines

```bash
python3 setup_keychain.py
# Choose option 2: Azure KeyVault
# Enter your vault URL when prompted
```

### .env File (Quick but less secure)
- **Platforms**: All
- **Setup time**: ~1 minute
- **Security**: File-based, needs to stay out of git
- **Use when**: Testing, or environments without keyring support

```bash
cp .env.example .env
# Edit .env and add your API key
```

---

## Command Reference

### Setup Storage

```bash
# Interactive setup (choose provider, then storage backend)
python3 setup_keychain.py

# Setup local keyring directly (will prompt for provider)
python3 setup_keychain.py local

# Verify which methods are configured for ALL providers
python3 setup_keychain.py verify
```

### Run Agent

```bash
python3 langchain-agent.py
```

### Manage Credentials

#### Local Keyring

```bash
# macOS: View credentials
security dump-keychain | grep langchain-agent

# macOS: Delete credentials
security delete-generic-password -s "langchain-agent" -a "perplexity"

# Linux: View credentials
secret-tool search service langchain-agent

# Linux: Delete credentials
secret-tool clear service langchain-agent username perplexity

# Windows: Use Windows Credential Manager GUI
```

#### Azure KeyVault

```bash
# List all secrets
az keyvault secret list --vault-name <vault-name>

# View a secret
az keyvault secret show --vault-name <vault-name> --name perplexity-api-key

# Delete a secret
az keyvault secret delete --vault-name <vault-name> --name perplexity-api-key

# Update a secret (re-run setup script)
python3 setup_keychain.py azure
```

---

## Comparison Table

| Feature | Local Keyring | Azure KeyVault | .env File |
|---------|---|---|---|
| **Security** | High (OS-managed) | Very High (Cloud-managed) | Medium (file-based) |
| **Ease of Setup** | Very Easy | Moderate | Easy |
| **Cross-platform** | Yes | Yes | Yes |
| **Team Sharing** | No | Yes | No (security issue) |
| **Audit Logging** | Limited | Yes | No |
| **Cost** | Free | Paid (usually <$1/month) | Free |
| **Internet Required** | No | Yes | No |
| **Best For** | Personal Machines | Teams & Production | Quick Testing |

---

## Azure KeyVault Setup Details

### 1. Create a KeyVault (if you don't have one)

```bash
# Set variables
RESOURCE_GROUP="myResourceGroup"
VAULT_NAME="mykeyvault"
LOCATION="eastus"

# Create resource group
az group create --name $RESOURCE_GROUP --location $LOCATION

# Create KeyVault
az keyvault create --name $VAULT_NAME --resource-group $RESOURCE_GROUP --location $LOCATION

# Get vault URL
az keyvault show --name $VAULT_NAME --query properties.vaultUri --output tsv
```

### 2. Authenticate to Azure

```bash
# Option 1: Use Azure CLI (simplest)
az login

# Option 2: Service Principal (for automation)
export AZURE_CLIENT_ID="<your-client-id>"
export AZURE_CLIENT_SECRET="<your-client-secret>"
export AZURE_TENANT_ID="<your-tenant-id>"

# Option 3: Check authentication
az account show
```

### 3. Set up the agent

```bash
python3 setup_keychain.py
# Choose option 2: Azure KeyVault
# Enter your vault URL from step 1
```

---

## Environment Variables for Azure

If you're using service principal authentication, set these:

```bash
# In your shell or .env
export AZURE_CLIENT_ID="00000000-0000-0000-0000-000000000000"
export AZURE_CLIENT_SECRET="your-secret-value"
export AZURE_TENANT_ID="00000000-0000-0000-0000-000000000000"
export AZURE_KEYVAULT_URL="https://mykeyvault.vault.azure.net/"
```

Then run:

```bash
python3 langchain-agent.py
```

---

## Troubleshooting

### KeyError or Authentication Errors with Azure

```bash
# Check if you're authenticated
az account show

# Re-authenticate
az login

# Check if keyring packages are installed
pip list | grep -i azure
pip list | grep -i keyring
```

### Local Keyring Issues

```bash
# Check keyring backend
python3 -c "import keyring; print(keyring.get_keyring())"

# Reinstall keyring (Linux)
sudo apt-get install libsecret-1-dev
pip install --upgrade keyring
```

### Still Having Issues?

Check the main README.md for detailed troubleshooting.
