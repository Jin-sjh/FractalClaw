---
name: github
description: "GitHub operations via gh CLI for repository management, issues, and pull requests"
metadata:
  emoji: "🐙"
  requires:
    bins: ["gh"]
  install:
    - kind: brew
      formula: gh
    - kind: download
      url: "https://cli.github.com/"
---

# GitHub Skill

Use the `gh` CLI to interact with GitHub for repository operations, issue management, and pull requests.

## When to Use

✅ USE this skill when:
- Creating or managing GitHub issues
- Working with pull requests
- Managing repository settings
- Viewing GitHub Actions workflows
- Interacting with GitHub releases

❌ DON'T use this skill when:
- Cloning repositories (use git directly)
- Local git operations (use git skill)

## Prerequisites

Install the GitHub CLI:

```bash
# macOS
brew install gh

# Windows
winget install GitHub.cli

# Linux
sudo apt install gh
```

Authenticate with GitHub:
```bash
gh auth login
```

## Common Commands

### Issues

```bash
# List issues
gh issue list --repo owner/repo --state open

# Create an issue
gh issue create --repo owner/repo --title "Bug report" --body "Description"

# View issue details
gh issue view 123 --repo owner/repo
```

### Pull Requests

```bash
# List PRs
gh pr list --repo owner/repo --state open

# Create a PR
gh pr create --repo owner/repo --title "Feature" --body "Description"

# View PR details
gh pr view 456 --repo owner/repo

# Check out a PR locally
gh pr checkout 456
```

### Repositories

```bash
# Create a new repository
gh repo create my-repo --public

# View repository info
gh repo view owner/repo

# Clone a repository
gh repo clone owner/repo
```

## Best Practices

1. Always specify `--repo` when working with non-default repositories
2. Use `--json` flag for machine-readable output
3. Check authentication status with `gh auth status` before operations
4. Use `--web` flag to open results in browser when needed
