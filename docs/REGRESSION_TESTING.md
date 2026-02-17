# Regression Testing Guide

Use this guide to run a consistent validation pass after each batch of fixes.

## Prerequisites

Install test dependencies:

```bash
python3 -m pip install -r requirements.txt
python3 -m pip install pytest
```

## Test Tiers

### 1) Fast (local dev loop)

Validates guardrails and MCP read-only behavior.

```bash
make test-fast
```

### 2) Regression (default for every fix batch)

Runs all non-integration/non-AWS tests.

```bash
make test-regression
```

### 3) Integration (credentialed environment only)

Runs integration/aws-marked tests.

```bash
make test-integration
```

## What is covered

- Intent classification guardrails (`core/intent_policy.py`)
- Mutating tool classification for safe blocking
- MCP read-only tool availability:
  - `list_account_inventory`
  - `list_aws_resources`
  - `describe_resource`
- MCP tool routing behavior
- Inventory summarization logic

## Recommended workflow after code fixes

1. Run `make test-fast`
2. If green, run `make test-regression`
3. If deployment-related changes were made, run `make test-integration` in a configured environment
4. Merge only after all applicable tiers pass

