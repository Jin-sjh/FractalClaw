---
name: file_operations
description: "File system operations for reading, writing, and managing files"
metadata:
  emoji: "📁"
  requires:
    bins: []
  install: []
---

# File Operations Skill

This skill provides comprehensive file system operations capabilities.

## When to Use

✅ USE this skill when:
- Reading file contents for analysis
- Writing or editing source code files
- Searching for files or content within files
- Listing directory contents

❌ DON'T use this skill when:
- Executing shell commands (use bash skill instead)
- Making network requests (use network skill instead)

## Available Tools

| Tool | Description |
|------|-------------|
| `read` | Read file contents with optional line range |
| `write` | Write content to a file (overwrite or append) |
| `edit` | Find and replace content in a file |
| `search` | Search for patterns in files |
| `find_files` | Find files matching a glob pattern |
| `list_directory` | List directory contents |

## Common Patterns

### Reading a file
```
read(file_path="/path/to/file.py", offset=1, limit=100)
```

### Writing a new file
```
write(file_path="/path/to/new.py", content="# New file\n")
```

### Editing a file
```
edit(file_path="/path/to/file.py", old_content="old", new_content="new")
```

### Searching for code
```
search(pattern="def.*function", path="./src", use_regex=true)
```

## Best Practices

1. Always use absolute paths when possible
2. Use `offset` and `limit` for large files to avoid memory issues
3. Verify file existence before writing to avoid accidental overwrites
4. Use `search` before `edit` to verify the content exists
