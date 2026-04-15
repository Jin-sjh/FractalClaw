---
name: web_search
description: "Web search capabilities for finding information online"
metadata:
  emoji: "🔍"
  requires:
    bins: []
  install: []
---

# Web Search Skill

Search the web for information using various search engines and APIs.

## When to Use

✅ USE this skill when:
- Looking up documentation or tutorials
- Finding solutions to technical problems
- Researching best practices
- Discovering libraries or tools

❌ DON'T use this skill when:
- The information is already in the codebase
- You need to fetch specific URLs (use fetch tool instead)

## Available Methods

### Web Search Tool
```
search(query: str, num_results: int = 5)
```

### Web Fetch Tool
```
fetch(url: str)
```

## Common Patterns

### Search for documentation
```
search(query="Python asyncio tutorial", num_results=5)
```

### Search for error solutions
```
search(query="TypeError 'NoneType' object is not iterable solution")
```

### Fetch a specific page
```
fetch(url="https://docs.python.org/3/library/asyncio.html")
```

## Best Practices

1. Use specific, targeted queries for better results
2. Limit `num_results` to avoid information overload
3. Verify information from multiple sources
4. Check the date of search results for relevance
5. Use `fetch` to get full content from promising search results
