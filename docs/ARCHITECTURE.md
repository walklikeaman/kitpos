# KIT POS Agents - Repository Structure

Two independent agents separated and ready for GitHub deployment.

## Directory Structure

```
/Users/walklikeaman/GitHub/
├── maverick-terminal-agent/          # Agent 1: Terminal provisioning
│   ├── src/maverick_agent/
│   │   ├── cli.py                   # Maverick CLI commands
│   │   ├── config.py                # Configuration & settings
│   │   ├── models.py                # Data models (Maverick-specific)
│   │   ├── orchestrator.py          # ProvisioningOrchestrator
│   │   ├── services/
│   │   │   ├── paxstore.py         # PAX Store integration
│   │   │   └── inbox.py            # Email inbox client
│   │   └── parsers/
│   │       └── var_pdf.py          # VAR PDF parser
│   ├── tests/                       # Unit tests
│   ├── config/
│   │   └── field_aliases.json      # Field mapping config
│   ├── pyproject.toml              # Maverick dependencies
│   ├── .gitignore
│   └── README.md
│
├── kit-dashboard-agent/             # Agent 2: Merchant onboarding
│   ├── src/kit_agent/
│   │   ├── cli.py                  # Kit CLI commands
│   │   ├── models.py               # Data models (Kit-specific)
│   │   ├── kit_orchestrator.py     # KitMerchantOnboardingOrchestrator
│   │   ├── services/
│   │   │   └── kit_dashboard.py   # Dashboard form automation
│   │   └── parsers/
│   │       ├── kit_documents.py   # Document parser
│   │       └── ocr_micr.py        # OCR + MICR recognition
│   ├── tests/                      # Unit tests
│   ├── merchants/                  # Merchant profiles (git-ignored)
│   ├── pyproject.toml             # Kit dependencies
│   ├── .gitignore
│   └── README.md
│
└── AGENTS_STRUCTURE.md             # This file
```

## Agents

### 1. Maverick Terminal Agent
**Purpose:** Terminal provisioning automation

**Key Components:**
- Parse merchant VAR (Variable Rate) PDFs
- Extract terminal and merchant information
- Auto-detect merchant data from email (IMAP)
- Build provisioning plans for PAX terminals

**Entry Point:** `maverick_agent/cli.py`

**Commands:**
```bash
maverick parse-pdf <pdf>
maverick plan --merchant-id <id> --serial-number <sn> [--pdf <path>]
```

**Dependencies:**
- python-dotenv, typer, pydantic
- Optional OCR: easyocr, pytesseract, pillow

---

### 2. KIT Dashboard Agent
**Purpose:** Merchant onboarding automation

**Key Components:**
- Parse merchant applications, driver licenses, green cards
- Recognize MICR (magnetic ink character recognition) on checks
- Extract routing numbers and account numbers
- Validate merchant profiles
- Automate KIT Dashboard form filling
- Upload documents and submit applications

**Entry Point:** `kit_agent/cli.py`

**Commands:**
```bash
kit parse-docs <files...>
kit plan <files...> [--reveal-sensitive]
kit report <files...>
```

**Dependencies:**
- python-dotenv, typer, pydantic, pdfplumber
- Optional OCR: easyocr, pytesseract, pillow
- Optional Browser: playwright, playwright-stealth

---

## Key Separation

| Aspect | Maverick | Kit Dashboard |
|--------|----------|---------------|
| **Package Name** | `maverick_agent` | `kit_agent` |
| **CLI Command** | `maverick` | `kit` |
| **Models** | MerchantRequest, RunPlan, RunOutcome | KitMerchantProfile, KitOnboardingPlan |
| **Parsers** | VarPdfParser | KitDocumentParser, MICR |
| **Services** | PAXStore, ImapInbox | KitDashboard |
| **Core Logic** | ProvisioningOrchestrator | KitMerchantOnboardingOrchestrator |
| **Config** | field_aliases.json | (none - defaults in code) |

---

## Shared Utilities

**Models** (duplicated in each agent):
- `Address` - Street, city, state, zip
- `ContactPerson` - First and last name
- `mask_digits()` - Mask sensitive data for CLI output

---

## Setup Instructions

### 1. Initialize Git Repositories

```bash
cd /Users/walklikeaman/GitHub/maverick-terminal-agent
git init
git add .
git commit -m "Initial commit: Maverick Terminal Agent"
git remote add origin https://github.com/YOUR_ORG/maverick-terminal-agent.git
git branch -M main
git push -u origin main

# Do the same for kit-dashboard-agent
cd /Users/walklikeaman/GitHub/kit-dashboard-agent
git init
git add .
git commit -m "Initial commit: KIT Dashboard Agent"
git remote add origin https://github.com/YOUR_ORG/kit-dashboard-agent.git
git branch -M main
git push -u origin main
```

### 2. Make Repositories Private

On GitHub:
1. Go to each repository's Settings
2. Scroll to "Danger Zone"
3. Click "Change repository visibility"
4. Select "Private"

### 3. Install Locally for Development

```bash
# Maverick
cd /Users/walklikeaman/GitHub/maverick-terminal-agent
pip install -e '.[ocr]'

# Kit Dashboard
cd /Users/walklikeaman/GitHub/kit-dashboard-agent
pip install -e '.[ocr,browser]'
```

---

## Integration

Both agents can be run independently:

```bash
# Terminal provisioning
maverick plan --merchant-id MERCHANT123 --serial-number ABC123

# Merchant onboarding
kit plan /path/to/documents/*.pdf
```

Future: Orchestrate both in a master workflow if needed.

---

## Next Steps

1. ✅ Separate agents into independent repositories
2. ⏳ Initialize Git repositories on GitHub
3. ⏳ Make repositories private
4. ⏳ Set up GitHub Actions CI/CD (optional)
5. ⏳ Configure branch protection rules
6. ⏳ Document credentials setup in team wiki

---

**Status:** Ready for GitHub deployment  
**Last Updated:** 2026-04-24
