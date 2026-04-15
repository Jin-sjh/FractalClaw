---
name: python
description: "Python development tools for package management, testing, and code quality"
metadata:
  emoji: "🐍"
  requires:
    bins: ["python", "pip"]
  install: []
---

# Python Skill

Python development tools for package management, testing, and code quality.

## When to Use

✅ USE this skill when:
- Managing Python packages and dependencies
- Running Python tests
- Formatting and linting Python code
- Creating virtual environments
- Building Python packages

❌ DON'T use this skill when:
- Running arbitrary Python scripts (use bash)
- Working with other languages

## Common Commands

### Package Management

```bash
# Install packages
pip install package_name

# Install from requirements
pip install -r requirements.txt

# Create virtual environment
python -m venv .venv

# Activate virtual environment
# Windows
.venv\Scripts\activate
# Unix
source .venv/bin/activate
```

### Testing

```bash
# Run pytest
pytest tests/

# Run with coverage
pytest --cov=src tests/

# Run specific test
pytest tests/test_file.py::test_function
```

### Code Quality

```bash
# Format with ruff
ruff format .

# Lint with ruff
ruff check .

# Type check with mypy
mypy src/
```

### Build

```bash
# Build package
python -m build

# Install in development mode
pip install -e .
```

## Best Practices

1. Always use virtual environments for project isolation
2. Pin dependency versions in requirements.txt
3. Run tests before committing changes
4. Use ruff for both formatting and linting
5. Enable type checking with mypy for better code quality
