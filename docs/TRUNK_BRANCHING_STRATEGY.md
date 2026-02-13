# Trunk-Based Development Branching Strategy

## Overview

The CI/CD pipeline has been configured to support **trunk-based development**, where a main trunk branch (`main` or `master`) serves as the source of truth for deployments, and feature branches are used for development work.

## Branch Naming Convention

### Trunk Branches
- `main` - Primary trunk branch (default)
- `master` - Alternative trunk branch (supported for backward compatibility)

### Feature/Development Branches
All development happens in short-lived branches following these naming patterns:

| Pattern | Purpose | Example |
|---------|---------|---------|
| `feature/**` | New features | `feature/auth-improvements`, `feature/api-v2` |
| `fix/**` | Bug fixes | `fix/memory-leak`, `fix/null-pointer-error` |
| `bugfix/**` | Bug fixes (alternate) | `bugfix/login-issue` |
| `release/**` | Release preparation | `release/v1.0.0`, `release/2.1.0` |
| `hotfix/**` | Production hotfixes | `hotfix/critical-security-patch` |

## Pipeline Execution Rules

### All Branch Types
✅ **Trigger on push to any branch**
- Build & Lint
- Unit Tests
- Security Scans (Bandit, Safety)

✅ **Trigger on PR to main/master**
- Build & Lint
- Unit Tests
- Security Scans
- Code review feedback

### Trunk Branches Only (main/master)
🚀 **Deploy only after merge to trunk**
- Docker Image Build → ECR
- AWS Deployment (Lambda/ECS)
- Integration Tests

## Workflow Examples

### Feature Branch Development
```bash
# Create feature branch
git checkout -b feature/new-llm-provider

# Make changes, commit
git add .
git commit -m "Add Groq LLM provider"

# Push branch
git push origin feature/new-llm-provider

# CI/CD automatically:
# ✓ Runs linting & tests
# ✓ Reports results on PR
# ✗ Skips Docker build & deployment
```

### Merging to Trunk
```bash
# Create PR: feature/new-llm-provider → main
# Reviewers approve after verifying CI passes

# Merge PR (creates commit on main)
git merge feature/new-llm-provider
git push origin main

# CI/CD automatically:
# ✓ Runs all checks again
# ✓ Builds Docker image
# ✓ Deploys to AWS
# ✓ Runs integration tests
```

### Hotfix Workflow
```bash
# Branch from master (if using separate hotfix)
git checkout -b hotfix/security-patch master

# Apply fix, commit
git commit -m "Patch: XSS vulnerability"

# Merge back to master
git checkout master
git merge hotfix/security-patch
git push origin master

# CI/CD:
# ✓ Full pipeline: test → build → deploy → verify
```

## Configuration Details

### Trigger Configuration (`.github/workflows/ci-cd.yml`)

```yaml
on:
  push:
    branches:
      - main
      - master
      - 'feature/**'
      - 'fix/**'
      - 'bugfix/**'
      - 'release/**'
      - 'hotfix/**'
  pull_request:
    branches:
      - main
      - master
      - 'feature/**'
      - 'fix/**'
      - 'bugfix/**'
      - 'release/**'
      - 'hotfix/**'
```

### Deployment Gate Condition

```yaml
if: github.event_name == 'push' && 
    (github.ref == 'refs/heads/main' || 
     github.ref == 'refs/heads/master')
```

This ensures:
- ✓ Deployments only happen on direct pushes to trunk
- ✓ Feature branches run full CI but skip deployment
- ✓ PRs trigger all checks without deployment

## Best Practices

### 1. Keep Branches Short-Lived
- Merge within 1-2 days ideally
- Reduces merge conflicts
- Faster feedback loops

### 2. Frequent Integration
- Commit regularly
- Push to feature branch often
- Merge to trunk at least daily

### 3. Gated Commits to Trunk
- All PRs require CI to pass
- Code review before merge
- Automated checks catch issues early

### 4. Trunk is Always Deployable
- Only merged, tested code goes to trunk
- Trunk commits trigger automatic deployment
- Any failures are immediately visible

## Handling Deployment Failures

If a deployment fails after merging to trunk:

1. **Identify the issue** (check CloudWatch logs)
2. **Create a hotfix** from the working version
3. **Merge hotfix quickly** using `hotfix/*` pattern
4. **Verify in integration tests** before closing PR

## Adding New Branch Patterns

To support additional branch patterns (e.g., `docs/**`, `chore/**`):

1. Edit `.github/workflows/ci-cd.yml`
2. Add pattern to `on.push.branches` and `on.pull_request.branches`
3. Example:
```yaml
on:
  push:
    branches:
      - main
      - master
      - 'docs/**'  # Add new pattern
      - 'feature/**'
```

## Migration from Old Strategy

If migrating from multi-branch strategy (main + develop):

1. **Backup current state**
   ```bash
   git branch -m develop develop-archived
   ```

2. **Update CI/CD config** ✓ Already done

3. **Notify team** of new branching model

4. **Delete old branches** when team is ready
   ```bash
   git push origin --delete develop develop-archived
   ```

## References

- [GitHub Actions Branch Patterns](https://docs.github.com/en/actions/using-workflows/workflow-syntax-for-github-actions#onpushbranchesincludebranches)
- [Trunk-Based Development](https://trunkbaseddevelopment.com/)
- [GitHub Flow Variant](https://guides.github.com/introduction/flow/)
