# KITPOS Development Guide

This guide explains how to add new agents to the KITPOS monorepo and maintain the existing codebase.

## Adding a New Agent

### 1. Create Directory Structure

```bash
cd agents/
mkdir your-agent-name
cd your-agent-name

# Create Python package structure
mkdir -p src/your_agent tests docs
touch src/your_agent/__init__.py
touch tests/__init__.py
```

### 2. Create pyproject.toml

Copy and adapt from an existing agent. Key sections:

```toml
[build-system]
requires = ["setuptools>=45", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "your-agent"
version = "0.1.0"
description = "Brief agent description"
dependencies = [
    "pydantic>=1.9",
    "typer>=0.4",
    # Add specific dependencies for your agent
]

[project.optional-dependencies]
# Optional feature groups (ocr, browser, etc.)

[project.scripts]
your-agent = "your_agent.cli:app"  # CLI entry point

[tool.setuptools.packages]
find = {where = ["src"]}
```

### 3. Create Core Modules

**`src/your_agent/models.py`** — Data models using dataclasses or Pydantic:

```python
from dataclasses import dataclass
from typing import Optional

@dataclass
class YourAgentInput:
    """Input data for the agent."""
    field1: str
    field2: Optional[str] = None

@dataclass
class YourAgentOutput:
    """Output data from the agent."""
    result: str
    status: str
```

**`src/your_agent/cli.py`** — CLI commands using Typer:

```python
import typer
from pathlib import Path

app = typer.Typer(help="Your agent description")

@app.command()
def process(
    input_file: Path = typer.Argument(..., help="Input file"),
    verbose: bool = typer.Option(False, help="Verbose output"),
):
    """Process input and produce output."""
    # Implementation
    typer.echo("Done!")

if __name__ == "__main__":
    app()
```

**`src/your_agent/orchestrator.py`** — Main orchestration logic:

```python
from .models import YourAgentInput, YourAgentOutput

class YourAgentOrchestrator:
    """Main orchestrator for your agent."""
    
    def execute(self, input_data: YourAgentInput) -> YourAgentOutput:
        """Execute the agent workflow."""
        # Implementation
        return YourAgentOutput(result="...", status="success")
```

### 4. Create README.md

Include:
- Quick start with `pip install -e '.[extras]'`
- CLI command examples
- Configuration (environment variables, secrets)
- Troubleshooting section
- Architecture overview

### 5. Add Tests

```python
# tests/test_agent.py
import pytest
from your_agent.models import YourAgentInput, YourAgentOutput
from your_agent.orchestrator import YourAgentOrchestrator

def test_basic_flow():
    input_data = YourAgentInput(field1="test")
    orchestrator = YourAgentOrchestrator()
    output = orchestrator.execute(input_data)
    assert output.status == "success"
```

Run tests:
```bash
pip install -e '.[test]'
pytest tests/
```

### 6. Document the Agent

1. **README.md** — Usage and quick start (required)
2. **docs/ARCHITECTURE.md** — Internal design (if complex)
3. **docs/EXAMPLES.md** — Detailed usage examples (optional)

## Agent Guidelines

### Independence

- Each agent is a standalone Python package
- Can be installed and used separately
- No imports from other agents
- No shared code repository (duplicate utilities if needed)

### Naming Conventions

- Directory: `kebab-case` (e.g., `your-agent-name`)
- Package: `snake_case` (e.g., `your_agent_name`)
- CLI command: `kebab-case` (e.g., `your-agent`)
- Classes/functions: `PascalCase` / `snake_case`

### Dependencies

- Minimal and specific to the agent's function
- Pin versions in `pyproject.toml` where stability matters
- Group optional features (ocr, browser, test) in `[project.optional-dependencies]`
- Avoid version conflicts with other agents

### Configuration

- Use environment variables for credentials
- Support `.env` files via `python-dotenv`
- Mask sensitive data in CLI output
- Validate configuration on startup

Example:
```python
import os
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv("API_KEY")
if not api_key:
    raise ValueError("API_KEY environment variable not set")
```

### CLI Design

- Use Typer for command structure
- Provide meaningful help text (`help=` parameter)
- Support JSON output for piping (`--json` flag)
- Show progress for long operations
- Return appropriate exit codes

### Error Handling

- Raise specific exceptions with context
- Provide actionable error messages
- Log to files in `tmp/<agent-name>/` directory
- Don't mask internal errors without context

## Testing New Agents

### Local Installation

```bash
cd agents/your-agent-name
pip install -e '.[ocr,browser]'  # Include optional dependencies

# Test CLI
your-agent --help
your-agent command --option value
```

### Integration Testing

For agents that interact with external services:

```python
# tests/test_integration.py
@pytest.mark.integration
def test_external_api():
    # Test with real API (requires credentials)
    pass

# Run: pytest -m integration
```

## Updating the Monorepo Root

When adding a new agent:

1. Update `/README.md` with agent description and CLI examples
2. Update `docs/ARCHITECTURE.md` if the design is unique
3. Create a brief entry in `docs/DEVELOPMENT.md` for quick reference
4. Consider documenting in `docs/SETUP.md` if it has special deployment needs

## Version Management

Each agent maintains its own version in `pyproject.toml`:

```toml
[project]
version = "0.1.0"  # Follows semantic versioning
```

The monorepo as a whole uses the latest major versions:
- Monorepo structure version: 1.0.0+ (see root README)
- Individual agents: Follow their own semver

## Deployment

### Local Testing

```bash
# Install all agents in development mode
cd kitpos
./scripts/install-all.sh  # If you create a helper script
```

### GitHub Deployment

1. Push to repository
2. Tag releases: `git tag v1.0.0-maverick`
3. GitHub Actions can build/test on push
4. Users install specific agents: `pip install git+https://github.com/user/kitpos.git@v1.0.0-maverick#egg=maverick-agent&subdirectory=agents/maverick-terminal-agent`

## Common Patterns

### Pattern 1: Document Parser

```python
class DocumentParser:
    def parse(self, file_path: Path) -> ParsedDocument:
        # Detect file type
        # Extract content (text, OCR, etc.)
        # Validate and normalize
        # Return structured data
```

### Pattern 2: Browser Automation

```python
class DashboardAgent:
    async def execute_workflow(self, credentials: Credentials) -> Outcome:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=False)
            page = await browser.new_page()
            # Automate workflow
            await browser.close()
```

### Pattern 3: Message Queue Processing

```python
class ImapOrchestrator:
    def monitor_inbox(self) -> None:
        while True:
            messages = self.fetch_new_messages()
            for msg in messages:
                request = self.parse_message(msg)
                self.execute_workflow(request)
            time.sleep(30)  # Poll interval
```

## Troubleshooting

### Import Errors When Installing

If `pip install -e .` fails:
```bash
# Verify you're in the agent directory
pwd  # Should end with agents/your-agent-name

# Check pyproject.toml format
cat pyproject.toml | head -20

# Try verbose installation
pip install -e . -v
```

### CLI Command Not Found

```bash
# Reinstall entry points
pip install -e .

# Verify it's registered
which your-agent
your-agent --help
```

### Version Conflicts Between Agents

If agents require different versions of the same package:
1. Use virtual environments per agent
2. Or install one at a time to avoid global conflicts
3. Consider using conda for isolation

## Future Agents (Ideas)

Potential agents to add to KITPOS:

- **PAX Settings Agent** — Configure PAX terminal settings
- **Reconciliation Agent** — Match transactions with bank statements
- **Customer Sync Agent** — Sync customer data to third-party systems
- **Compliance Agent** — Monitor and report compliance issues
- **Analytics Agent** — Extract and analyze transaction patterns

Each would follow the same structure and guidelines as the existing agents.

---

**Last Updated:** 2026-04-24  
**Version:** 1.0.0
