#!/bin/bash
# Fix git push by removing terraform_workspace from tracking

cd /Users/parag.kulkarni/ai-workspace/aws-infra-agent-bot

echo "Step 1: Removing terraform_workspace from git cache..."
git rm -r --cached terraform_workspace/ 2>&1 | head -5

echo ""
echo "Step 2: Checking git status..."
git status --short | head -20

echo ""
echo "Step 3: Staging .gitignore change..."
git add .gitignore

echo ""
echo "Step 4: Committing changes..."
git commit -m "chore: ignore terraform_workspace and build artifacts

- Added terraform_workspace/ to .gitignore
- Ignore *.tfstate and .terraform directories
- Removed large terraform provider binaries from tracking"

echo ""
echo "✅ Ready to push. Run: git push"
