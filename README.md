# KITPOS Agents

A monorepo for KIT POS automation agents. Each agent handles specific workflows within the KIT POS ecosystem as they mature from proof-of-concept to production automation.

## Agents

### [Maverick Terminal Agent](./agents/maverick-terminal-agent)
Provisioning agent for Maverick POS terminals. Parses VAR merchant PDFs and orchestrates terminal setup workflows via IMAP-triggered provisioning plans.

**Key features:**
- VAR PDF parsing with configurable fields
- IMAP inbox monitoring for MerchantRequest messages
- Provisioning plan orchestration with email follow-up
- CLI: `maverick parse-pdf` | `maverick plan` | `maverick execute`

### [KIT Dashboard Agent](./agents/kit-dashboard-agent)
Merchant onboarding automation for KIT Dashboard. Processes merchant documents (checks, IDs, green cards), extracts data via OCR/MICR, and automates KIT Dashboard form submission.

**Key features:**
- Multi-format document parsing (PDF, JPG, PNG, TXT)
- MICR routing number extraction from bank checks
- OCR with EasyOCR → Tesseract fallback
- KIT Dashboard browser automation with Playwright
- CLI: `kit parse-docs` | `kit plan` | `kit report` | `kit execute`

## Directory Structure

```
kitpos/
├── agents/
│   ├── maverick-terminal-agent/    # Terminal provisioning
│   └── kit-dashboard-agent/         # Merchant onboarding
├── docs/
│   ├── ARCHITECTURE.md              # System design & separation
│   ├── SETUP.md                     # GitHub & deployment setup
│   └── DEVELOPMENT.md               # Adding new agents
├── README.md                        # This file
└── .gitignore                       # Monorepo-level ignore rules
```

## Quick Start

### Install Both Agents

```bash
# Clone the repository
git clone https://github.com/yourusername/kitpos.git
cd kitpos

# Install Maverick Terminal Agent
cd agents/maverick-terminal-agent
pip install -e '.[ocr]'

# Install KIT Dashboard Agent (in a fresh terminal)
cd ../kit-dashboard-agent
pip install -e '.[ocr,browser]'
```

### Use Individual Agents

**Maverick Terminal:**
```bash
maverick parse-pdf merchant-app.pdf
maverick plan --merchant-id ABC123 --serial-number SN456
```

**KIT Dashboard:**
```bash
kit parse-docs merchant-*.pdf check.jpg green-card.jpg
kit plan merchant-*.pdf check.jpg green-card.jpg
kit report merchant-*.pdf check.jpg green-card.jpg
```

## Architecture

- **Independent agents** — Each agent has its own `pyproject.toml`, dependencies, models, and CLI namespace
- **Shared utilities** — Common types (`Address`, `ContactPerson`, utility functions) duplicated in each agent to maintain independence
- **No inter-agent imports** — Agents are designed to work standalone or be orchestrated externally
- **Modular design** — New agents can be added without modifying existing ones

See [ARCHITECTURE.md](./docs/ARCHITECTURE.md) for detailed separation rationale.

## Adding a New Agent

1. Create `agents/new-agent/` with `src/new_agent/` package
2. Copy `pyproject.toml` structure from an existing agent, update package name and CLI entry point
3. Implement core modules: `models.py`, `cli.py`, specialized parsers/services
4. Add `README.md` and `tests/` to the agent directory
5. Document the agent in this root README and in [DEVELOPMENT.md](./docs/DEVELOPMENT.md)

See [DEVELOPMENT.md](./docs/DEVELOPMENT.md) for detailed guidelines.

## Documentation

- **[ARCHITECTURE.md](./docs/ARCHITECTURE.md)** — Technical design, separation rationale, and comparison with monolithic approach
- **[SETUP.md](./docs/SETUP.md)** — GitHub setup, secrets management, and deployment
- **[DEVELOPMENT.md](./docs/DEVELOPMENT.md)** — Guidelines for adding new agents and extending the monorepo

Each agent also has its own `README.md` with usage, testing, and troubleshooting information.

## Development

### Environment Setup

```bash
# Install Python 3.9+
python3 --version

# Optional: Create a virtual environment for each agent
cd agents/maverick-terminal-agent
python3 -m venv venv
source venv/bin/activate
pip install -e '.[ocr]'
```

### Running Tests

```bash
# Maverick tests
cd agents/maverick-terminal-agent
python3 -m pytest tests/

# KIT Dashboard tests
cd ../kit-dashboard-agent
python3 -m pytest tests/
```

### Code Style

- Python 3.9+ with type hints
- PEP 8 style guide
- Dataclasses for data models (pydantic for validation if needed)
- Minimal dependencies per agent

## Status

| Agent | Status | Tests | Docs |
|-------|--------|-------|------|
| Maverick Terminal | ✅ Functional | ✅ | ✅ |
| KIT Dashboard | ✅ Functional | ✅ | ✅ |

## License

Proprietary - Internal KIT POS automation

---

**Created:** 2026-04-24  
**Last Updated:** 2026-04-24  
**Monorepo Structure:** v1.0.0
