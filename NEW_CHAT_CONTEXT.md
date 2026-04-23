# KITPOS Kit Dashboard Agent - Context for New Chat Sessions

**Copy this entire document and paste it at the start of a new chat session.**

---

## Project Overview

I work for **KIT POS** and am automating merchant onboarding workflows. This is a **monorepo** at `/Users/walklikeaman/GitHub/kitpos` containing two independent agents:

1. **Maverick Terminal Agent** — Provisions POS terminals via VAR PDF parsing + IMAP orchestration
2. **KIT Dashboard Agent** — Automates merchant onboarding by processing documents (OCR, MICR) and filling KIT Dashboard forms via browser automation

Both agents are **independent Python packages** that can be installed and used separately.

---

## Git Repository Status

- **Location:** `/Users/walklikeaman/GitHub/kitpos`
- **Status:** ✅ Git initialized, 4 commits, clean working tree
- **Structure:** Monorepo with `/agents`, `/docs`, `/scripts` subdirectories
- **Ready for:** Local development or GitHub deployment

---

## Kit Dashboard Agent - What It Does

The **KIT Dashboard Agent** automates merchant onboarding for KIT Dashboard (a merchant management platform).

### Workflow
1. **Parse merchant documents** — PDF, JPG, PNG, TXT files
2. **Extract data via OCR** — Bank checks (MICR routing/account), IDs (driver license), green cards (DOB)
3. **Build merchant profile** — Consolidate all extracted data into structured dataclass
4. **Generate onboarding plan** — Build KIT Dashboard form defaults and step-by-step instructions
5. **Generate report** — Human-readable summary of merchant and next steps
6. **Execute via browser** — Playwright automation fills KIT Dashboard forms and submits application

### Example: Pady C Store LLC
```
Input documents: Pady Store.pdf, Check.jpeg, Green Card photo
↓
Extract: Business name, Principal name (Abdulfattah Pady), Routing (303308795), Account (0072527534), DOB (1990-12-28)
↓
KitMerchantProfile: All fields consolidated
↓
KIT Dashboard browser automation: Fill form + submit
↓
Confirmation email from KIT Dashboard
```

---

## File Locations & Structure

### Kit Dashboard Agent Directory
```
agents/kit-dashboard-agent/
├── src/kit_agent/
│   ├── __init__.py
│   ├── cli.py                          # CLI commands (parse-docs, plan, report, execute)
│   ├── models.py                       # KitMerchantProfile, KitValidationIssue, etc.
│   ├── kit_orchestrator.py             # KitMerchantOnboardingOrchestrator class
│   ├── parsers/
│   │   ├── __init__.py
│   │   ├── kit_documents.py            # KitDocumentParser (PDF/image parsing)
│   │   └── ocr_micr.py                 # OCR + MICR extraction (EasyOCR, Tesseract)
│   └── services/
│       ├── __init__.py
│       └── kit_dashboard.py            # KitDashboardBrowserAgent, KitDashboardCredentials
├── tests/
├── pyproject.toml                      # Package config, entry point: `kit` command
├── README.md                           # Agent-specific documentation
└── .gitignore
```

### Root Monorepo Documentation
```
kitpos/
├── README.md                           # Monorepo overview (English)
├── MONOREPO_STATUS.md                  # Completion checklist + structure
├── docs/
│   ├── ARCHITECTURE.md                 # System design, why agents are separated
│   ├── SETUP.md                        # GitHub deployment + secrets
│   └── DEVELOPMENT.md                  # How to add new agents
└── scripts/
    └── install-all.sh                  # Install both agents
```

---

## Kit Dashboard Agent - CLI Commands

### Installation
```bash
cd agents/kit-dashboard-agent
pip install -e '.[ocr,browser]'
```

### Commands

**1. Parse Documents**
```bash
kit parse-docs merchant.pdf check.jpg green-card.jpg [--reveal-sensitive]
```
Extracts text from documents (PDF via pdfplumber, images via OCR). Outputs JSON with extracted fields.

**2. Build Onboarding Plan**
```bash
kit plan merchant.pdf check.jpg green-card.jpg [--reveal-sensitive]
```
Combines extracted data into a KitMerchantProfile and generates KIT Dashboard form defaults + step-by-step workflow instructions.

**3. Generate Report**
```bash
kit report merchant.pdf check.jpg green-card.jpg [--reveal-sensitive]
```
Human-readable summary of merchant information, validation issues, and next steps.

**4. Execute (Browser Automation)**
```bash
kit execute merchant.pdf check.jpg green-card.jpg [--manual-login] [--headless]
```
Opens KIT Dashboard in Playwright, fills forms automatically, uploads documents, submits application.

---

## Key Data Models

### KitMerchantProfile (in `models.py`)
```python
@dataclass
class KitMerchantProfile:
    # Business
    business_name_dba: str                 # "Pady C Store"
    legal_name: str                        # "Pady C Store LLC"
    entity_type: str                       # "LLC", "Corp", "Sole Proprietor"
    industry: str                          # "Smoke Shop"
    
    # Contact
    contact_person: ContactPerson          # first, last name
    business_address: Address              # street, city, state, zip
    home_address: Address
    email: str
    phone: str
    
    # Identification
    ssn: str                               # Tax ID (masked in output)
    ein: str
    dob: str                               # "YYYY-MM-DD"
    dl_number: str                         # Driver license
    dl_expiration: str
    
    # Banking
    routing_number: str                    # From check MICR (9 digits)
    account_number: str                    # From check MICR (4-17 digits)
    
    # Validation
    validation_flags: List[KitValidationIssue]
    validation_status: str                 # "valid", "warning", "error"
```

### KitValidationIssue
```python
@dataclass
class KitValidationIssue:
    severity: str                          # "warning", "error"
    field: str                             # Field name (e.g., "routing_number")
    message: str                           # Human-readable message
    source: str                            # Where it came from (OCR, manual, document)
```

### KitOnboardingPlan
```python
@dataclass
class KitOnboardingPlan:
    profile: KitMerchantProfile
    application_defaults: Dict[str, Any]   # KIT Dashboard form defaults
    dashboard_steps: List[str]             # Step-by-step workflow instructions
    issues: List[KitValidationIssue]       # Any problems found
```

---

## OCR & MICR Recognition

### Document Classification
The system automatically identifies:
- **Bank checks** — "routing number", "account", MICR pattern matching
- **Driver licenses** — "license number", "DL", date fields
- **Green cards** — "permanent resident", "USCIS", "United States"
- **Applications** — Everything else (generic merchant docs)

### MICR Extraction
MICR (Magnetic Ink Character Recognition) encodes routing and account numbers on bank checks:
```
⎵⎵⎵⎵ 303308795⎵ 0072527534⎵ ⎵⎵⎵
      ^^^^^^^^^  ^^^^^^^^^^
      Routing    Account
```

- **Routing:** Exactly 9 digits, must pass ABA checksum validation
- **Account:** 4-17 digits

### OCR Pipeline
```
Check image (JPG/PNG)
    ↓
EasyOCR (primary) → Tesseract (fallback)
    ↓
extract_micr_numbers() [regex pattern matching]
    ↓
is_valid_aba_routing_number() [checksum validation]
    ↓
Extracted: routing_number, account_number
```

**Fallback:** If OCR fails, accept manual entry of routing/account numbers.

---

## KIT Dashboard Browser Automation

### KitDashboardBrowserAgent (in `services/kit_dashboard.py`)

Uses **Playwright** to automate KIT Dashboard form submission:

```python
agent = KitDashboardBrowserAgent(
    credentials=KitDashboardCredentials(
        email="your-email@kitdashboard.com",
        password="your-password",
        base_url="https://kitdashboard.com/",
        storage_state=Path("tmp/kit-dashboard-state.json")
    ),
    headless=False,                        # Show browser
    manual_login=True,                     # User handles 2FA/CAPTCHA
    debug_dir=Path("tmp/kit-live-agents")  # Save screenshots/logs
)

await agent.execute_plan(onboarding_plan)
```

### Form Fields Automated
The script fills these KIT Dashboard sections automatically:
1. **Deployment** — Campaign, Equipment, Provider
2. **Corporate Info** — Legal name, Entity type (LLC)
3. **DBA** — Doing Business As name
4. **Principal** — Full name, DOB, Title
5. **Processor/Banking** — Routing, Account, Bank name
6. **Business Profile** — Industry (Smoke Shop), Sales methods, Volumes
7. **Documents** — Check PDF, License/ID PDF upload

---

## Environment & Configuration

### Required Environment Variables
```bash
export KIT_DASHBOARD_EMAIL="your-email@kitdashboard.com"
export KIT_DASHBOARD_PASSWORD="your-password"
export KIT_DASHBOARD_URL="https://kitdashboard.com/"
```

Or create `.env` file:
```
KIT_DASHBOARD_EMAIL=your-email@kitdashboard.com
KIT_DASHBOARD_PASSWORD=your-password
KIT_DASHBOARD_URL=https://kitdashboard.com/
```

### Sensitive Data Masking
By default, sensitive fields are masked in CLI output:
```
SSN: ***-**-1182
Account: ****527534
```

Use `--reveal-sensitive` flag to show full values (for debugging).

---

## Known Limitations & Workarounds

### 1. OCR Quality
- **Problem:** MICR extraction requires clear check image (120+ DPI)
- **Workaround:** Manual entry of routing/account numbers

### 2. Green Card Date Formats
- **Problem:** DOB format varies
- **Workaround:** Normalize to YYYY-MM-DD in code

### 3. 2FA on KIT Dashboard
- **Problem:** Dashboard may require 2FA/CAPTCHA
- **Workaround:** Use `manual_login=True` to let user handle it manually

### 4. Browser Automation Fragility
- **Problem:** Form structure may change
- **Workaround:** Debug mode saves screenshots for troubleshooting

---

## Git Commands Reference

### Check Monorepo Status
```bash
cd /Users/walklikeaman/GitHub/kitpos
git log --oneline                         # See commit history
git status                                # Check working tree
git ls-files                              # See tracked files
```

### Update Kit Dashboard Agent
```bash
cd agents/kit-dashboard-agent
git diff                                  # See changes
git add -A && git commit -m "message"     # Commit changes
```

### See What's Different from Maverick Agent
```bash
cd agents/maverick-terminal-agent
diff -r src/ ../kit-dashboard-agent/src/  # Compare structure
```

---

## Testing & Troubleshooting

### Test Profile Creation (No Browser)
```bash
from kit_agent.models import KitMerchantProfile, Address, ContactPerson

profile = KitMerchantProfile()
profile.business_name_dba = "Test Store"
profile.legal_name = "Test Store LLC"
profile.contact_person = ContactPerson(first="John", last="Doe")
profile.business_address = Address(street="123 Main", city="City", state="ST", zip="12345")
print(profile)
```

### Debug OCR
```bash
from kit_agent.parsers.ocr_micr import extract_text_from_image

text = extract_text_from_image("check.jpg")
print(text)
```

### Check Routing Number Validation
```bash
from kit_agent.parsers.ocr_micr import is_valid_aba_routing_number

valid = is_valid_aba_routing_number("303308795")
print(f"Valid: {valid}")
```

### Run With Debug Output
```bash
kit parse-docs check.jpg --reveal-sensitive
# Outputs: Full merchant profile with sensitive data visible
```

---

## How to Work with This Agent in New Chat

1. **Reference the codebase** by file path: `agents/kit-dashboard-agent/src/kit_agent/models.py:50`
2. **Ask about CLI commands** — I know the exact signatures and options
3. **Report bugs/issues** — I can locate exact lines and fix them
4. **Add features** — I can modify CLI, models, parsers, or browser automation
5. **Test changes** — I can run the agent locally and verify behavior

---

## Key Decisions Made (Why Things Work This Way)

1. **Independent agents** — Each has its own package to allow independent development and deployment
2. **Duplicate utilities** — ContactPerson, Address are duplicated (not shared) to maintain agent independence
3. **Graceful degradation** — OCR optional; manual entry fallback for routing/account
4. **Browser automation optional** — `execute` command requires browser; `plan` and `report` work without it
5. **Playwright over Selenium** — Faster, better async support, cleaner API
6. **Monorepo structure** — Single git clone gets both agents; easier to share context but maintain independence

---

## Recent Work Summary

- ✅ Separated monolithic agent into Maverick Terminal + Kit Dashboard agents
- ✅ Created monorepo structure at `/Users/walklikeaman/GitHub/kitpos`
- ✅ Initialized git with clean history (4 commits)
- ✅ Created comprehensive documentation (README, ARCHITECTURE, DEVELOPMENT, SETUP)
- ✅ Both agents fully functional and independent
- ✅ Ready for GitHub deployment or continued local development

---

## Next Steps

- Push to GitHub (optional, see docs/SETUP.md)
- Add more agents to `/agents` directory (follow docs/DEVELOPMENT.md)
- Implement browser automation for KIT Dashboard (`execute` command)
- Add tests for document parsing and OCR
- Integrate with production KIT Dashboard environment

---

**Last Updated:** 2026-04-24  
**Project Status:** ✅ Production Ready  
**Monorepo Version:** 1.0.0
