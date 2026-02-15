#!/bin/bash
# Deep clean git history to remove large terraform provider binaries

set -e

cd /Users/parag.kulkarni/ai-workspace/aws-infra-agent-bot

echo "🔧 Fixing git repository (removing large files from history)..."
echo ""

# Step 1: Show what we're dealing with
echo "Step 1: Checking for large files..."
git rev-list --all --objects | sed -n $(git rev-list --objects --all | cut -f1 -d' ' | git cat-file --batch-check | grep blob | sort -k3 -n | tail -10 | while read hash type size; do echo -n "-e 's/^\(.\{0,40\}\).*'"$size"'$/\1/p;'; done) | sort -u | while read hash; do
  git ls-tree -r --long $(git rev-list --all) | grep -E "$hash" | awk '{ if ($4 > 104857600) print $3, $4}' | sort -k2 -n -r | head -5
done 2>/dev/null || echo "Note: Could not enumerate large files (git history very large)"

echo ""
echo "Step 2: Removing terraform_workspace from all git branches..."
# Use BFG if available, otherwise use filter-branch
if command -v bfg &> /dev/null; then
  echo "Using BFG Repo-Cleaner..."
  bfg --delete-folders terraform_workspace --no-blob-protection
else
  echo "Using git filter-branch (slower but built-in)..."
  git filter-branch --tree-filter 'rm -rf terraform_workspace' --force HEAD
fi

echo ""
echo "Step 3: Garbage collection to reclaim space..."
git reflog expire --expire=now --all
git gc --prune=now --aggressive

echo ""
echo "Step 4: Verifying terraform_workspace is removed..."
git ls-files | grep terraform_workspace && echo "❌ ERROR: Files still present!" || echo "✅ terraform_workspace removed from git"

echo ""
echo "✅ Done! Now push with force:"
echo "   git push --force-with-lease origin feature/SCRUM3-ag-ui-integration"
