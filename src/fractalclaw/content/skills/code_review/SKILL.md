---
name: code_review
description: "Code review and quality analysis tools"
metadata:
  emoji: "👀"
  requires:
    bins: []
  install: []
---

# Code Review Skill

Tools and patterns for reviewing code quality, identifying issues, and suggesting improvements.

## When to Use

✅ USE this skill when:
- Reviewing pull requests
- Analyzing code for potential bugs
- Checking code style and conventions
- Identifying performance issues
- Looking for security vulnerabilities

❌ DON'T use this skill when:
- Running tests (use testing skill instead)
- Formatting code (use format skill instead)

## Review Checklist

### Code Quality
- [ ] Code is readable and well-organized
- [ ] Functions are focused and single-purpose
- [ ] Variable names are descriptive
- [ ] Comments explain "why", not "what"
- [ ] No dead code or commented-out code

### Error Handling
- [ ] Edge cases are handled
- [ ] Errors are properly caught and logged
- [ ] User-facing errors are helpful
- [ ] Resources are properly cleaned up

### Security
- [ ] No hardcoded credentials
- [ ] Input is validated and sanitized
- [ ] SQL queries use parameterized statements
- [ ] Sensitive data is encrypted

### Performance
- [ ] No obvious N+1 queries
- [ ] Large data is paginated
- [ ] Caching is used appropriately
- [ ] No blocking operations in async code

### Testing
- [ ] New code has tests
- [ ] Edge cases are tested
- [ ] Tests are meaningful (not just coverage)

## Common Patterns

### Review a file
```
read(file_path="path/to/file.py")
# Analyze for issues
```

### Check for patterns
```
search(pattern="TODO|FIXME|XXX", path="./src")
search(pattern="password|secret|api_key", path="./src", case_sensitive=false)
```

## Best Practices

1. Be constructive and specific in feedback
2. Focus on the code, not the author
3. Explain the "why" behind suggestions
4. Prioritize issues by severity
5. Acknowledge good code, not just problems
