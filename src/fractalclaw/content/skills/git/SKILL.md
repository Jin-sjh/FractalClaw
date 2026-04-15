---
name: git
description: "Git version control operations for repository management"
metadata:
  emoji: "🔀"
  requires:
    bins: ["git"]
  install:
    - kind: brew
      formula: git
    - kind: download
      url: "https://git-scm.com/downloads"
---

# Git Skill

Git version control operations for managing code repositories.

## When to Use

✅ USE this skill when:
- Committing changes to a repository
- Creating, switching, or merging branches
- Viewing commit history and diffs
- Managing remotes and pushing/pulling
- Resolving merge conflicts

❌ DON'T use this skill when:
- GitHub-specific operations (use github skill instead)
- Working with other version control systems

## Common Commands

### Basic Operations

```bash
# Check status
git status

# Stage changes
git add .
git add path/to/file

# Commit changes
git commit -m "feat: add new feature"

# View history
git log --oneline -10
```

### Branches

```bash
# List branches
git branch -a

# Create branch
git branch feature-name

# Switch branch
git checkout feature-name
git switch feature-name

# Create and switch
git checkout -b feature-name

# Merge branch
git merge feature-name

# Delete branch
git branch -d feature-name
```

### Remote Operations

```bash
# List remotes
git remote -v

# Add remote
git remote add origin https://github.com/user/repo.git

# Push
git push origin main
git push -u origin main  # set upstream

# Pull
git pull origin main

# Fetch
git fetch --all
```

### Diff and History

```bash
# View diff
git diff
git diff --staged
git diff HEAD~1 HEAD

# View file history
git log --follow -p path/to/file

# Blame
git blame path/to/file
```

## Best Practices

1. Write clear, descriptive commit messages
2. Use branches for features and fixes
3. Pull before pushing to avoid conflicts
4. Review changes with `git diff` before committing
5. Use `.gitignore` to exclude unnecessary files
