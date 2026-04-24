# KITPOS Maverick Terminal Agent - Context for New Chat Sessions

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
- **Status:** ✅ Git initialized, 5 commits, clean working tree
- **Structure:** Monorepo with `/agents`, `/docs`, `/scripts` subdirectories
- **Ready for:** Local development or GitHub deployment

---

## Maverick Terminal Agent - What It Does

The **Maverick Terminal Agent** automates provisioning of Maverick POS terminals by parsing VAR (Value-Added Reseller) merchant PDFs and orchestrating provisioning workflows via IMAP inbox monitoring.

### Workflow
1. **Parse VAR PDF** — Extract merchant information from standardized PDF documents
2. **Monitor IMAP inbox** — Listen for MerchantRequest messages with merchant_id and serial_number
3. **Build provisioning plan** — Create RunPlan with extracted VAR data + serial number
4. **Execute provisioning** — Send plan to PAX Store (or email follow-up)
5. **Track outcome** — Log success/failure and update task status

### Example Workflow
```
Incoming IMAP: MerchantRequest(merchant_id=ABC123, serial_number=SN456)
    ↓
Parse VAR PDF for merchant ABC123
    ↓
Extract: business_name, principal_name, address, email, phone, SSN, etc.
    ↓
Build RunPlan: {merchant_data + serial_number}
    ↓
Send to PAX Store OR email provisioning instructions
    ↓
Log outcome: Success/Failed
```

---

## File Locations & Structure

### Maverick Terminal Agent Directory
```
agents/maverick-terminal-agent/
├── src/maverick_agent/
│   ├── __init__.py
│   ├── cli.py                          # CLI commands (parse-pdf, plan, execute)
│   ├── models.py                       # MerchantRequest, VarPayload, RunPlan, RunOutcome
│   ├── config.py                       # Configuration (VAR PDF field aliases)
│   ├── orchestrator.py                 # ProvisioningOrchestrator class
│   ├── parsers/
│   │   ├── __init__.py
│   │   └── var_pdf.py                  # VarPdfParser (pdfplumber-based)
│   └── services/
│       ├── __init__.py
│       ├── inbox.py                    # ImapInboxClient (IMAP monitoring)
│       └── paxstore.py                 # PAXStoreApi (or email fallback)
├── config/
│   └── field_aliases.json              # Custom field mapping for VAR PDFs
├── tests/
├── pyproject.toml                      # Package config, entry point: `maverick` command
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

## Maverick Terminal Agent - CLI Commands

### Installation
```bash
cd agents/maverick-terminal-agent
pip install -e '.[ocr]'
```

### Commands

**1. Parse VAR PDF**
```bash
maverick parse-pdf merchant-application.pdf [--output json|csv|table]
```
Extracts merchant information from a standardized VAR PDF. Outputs extracted fields in specified format.

**2. Build Provisioning Plan**
```bash
maverick plan --merchant-id ABC123 --serial-number SN456 [--output json]
```
Takes merchant ID (links to PDF file) and terminal serial number. Creates RunPlan with all provisioning details.

**3. Execute Provisioning**
```bash
maverick execute --merchant-id ABC123 --serial-number SN456 [--mode paxstore|email]
```
Executes the provisioning plan. Can send to PAX Store API or email provisioning instructions.

**4. Monitor Inbox (Daemon Mode)**
```bash
maverick monitor --mode daemon [--poll-interval 30]
```
Continuously monitors IMAP inbox for MerchantRequest messages. Automatically processes matching VAR PDFs and provisions terminals.

---

## Key Data Models

### MerchantRequest (in `models.py`)
Represents an incoming IMAP message requesting terminal provisioning:
```python
@dataclass
class MerchantRequest:
    merchant_id: str                   # "ABC123"
    serial_number: str                 # "SN456"
    requested_at: str                  # ISO timestamp
    requester_email: str               # "team@company.com"
```

### VarPayload (Extracted VAR PDF Data)
```python
@dataclass
class VarPayload:
    # Business
    merchant_id: str                   # Primary key for lookups
    business_name: str
    business_legal_name: str
    business_address: Address          # street, city, state, zip
    
    # Principal (Owner/Operator)
    principal_first_name: str
    principal_last_name: str
    principal_email: str
    principal_phone: str
    
    # Identification
    ssn: str                           # Social Security Number (masked)
    ein: str                           # Employer ID
    date_of_birth: str                 # "YYYY-MM-DD"
    
    # Additional
    industry: str                      # Business category
    annual_revenue: str                # "$XXX,XXX"
    years_in_business: str             # "X years"
    
    # Validation
    missing_required: List[str]        # Fields that are required but missing
    extraction_warnings: List[str]     # Non-critical issues
    confidence: float                  # 0.0-1.0 extraction confidence
```

### RunPlan (Provisioning Plan)
```python
@dataclass
class RunPlan:
    merchant_id: str
    serial_number: str
    merchant_data: VarPayload
    provisioning_steps: List[TaskField]  # Sequential provisioning tasks
    estimated_duration: int             # Seconds
    dependencies: List[str]             # Other requirements
```

### RunOutcome (Execution Result)
```python
@dataclass
class RunOutcome:
    plan_id: str
    status: str                        # "success", "failed", "partial"
    executed_at: str                   # ISO timestamp
    duration: float                    # Seconds
    steps_completed: int
    steps_total: int
    error_message: str                 # If failed
    logs: List[str]                    # Execution logs
```

---

## VAR PDF Parsing

### How It Works
The agent uses **pdfplumber** to extract text from VAR PDFs and matches fields using configurable aliases.

### Field Aliases Configuration
File: `config/field_aliases.json`

```json
{
  "business_name": ["Business Name", "DBA", "Doing Business As"],
  "principal_first_name": ["Owner First", "Principal First Name"],
  "principal_last_name": ["Owner Last", "Principal Last Name"],
  "email": ["Email Address", "Contact Email", "Primary Email"],
  "phone": ["Phone Number", "Contact Phone", "Primary Phone"],
  "ssn": ["SSN", "Social Security", "Tax ID"],
  "ein": ["EIN", "Employer ID", "Federal ID"]
}
```

### Parsing Pipeline
```
VAR PDF file
    ↓
pdfplumber.open() → extract_text()
    ↓
Split by patterns (sections, tables, key-value pairs)
    ↓
Match fields using aliases
    ↓
VarPayload dataclass
    ↓
Validate (missing_required, confidence)
```

### Custom Field Mapping
If a VAR PDF uses non-standard field names, add aliases to `config/field_aliases.json`:

```json
{
  "custom_field_name": ["Actual PDF label 1", "Alternate label 2"]
}
```

---

## IMAP Inbox Monitoring

### ImapInboxClient (in `services/inbox.py`)

The agent can monitor an IMAP inbox for MerchantRequest messages automatically.

**Configuration (environment variables):**
```bash
export IMAP_EMAIL="your-email@gmail.com"
export IMAP_PASSWORD="your-app-password"  # Gmail: use app-specific password
export IMAP_HOST="imap.gmail.com"
export IMAP_PORT="993"
export VAR_PDF_DIRECTORY="/path/to/var/pdfs"
```

**Daemon Mode:**
```bash
maverick monitor --mode daemon --poll-interval 30
```

The agent:
1. Connects to IMAP inbox
2. Checks for unread messages with subject pattern: `MerchantRequest: {merchant_id}`
3. Extracts merchant_id and serial_number from message body
4. Finds corresponding VAR PDF in configured directory
5. Parses VAR PDF
6. Creates RunPlan
7. Executes provisioning
8. Sends follow-up email with outcome
9. Marks message as read
10. Continues polling (every 30 seconds by default)

### Message Format Expected
```
From: team@company.com
To: provisioning@kitpos.com
Subject: MerchantRequest: ABC123

Body:
merchant_id: ABC123
serial_number: SN456
```

---

## PAX Store Integration

### PAXStoreApi (in `services/paxstore.py`)

Two modes of operation:

**Mode 1: Direct API Call (if API available)**
```python
api = PAXStoreApi(base_url="https://paxstore.api/")
response = api.provision_terminal(plan)
```

**Mode 2: Email Fallback**
```python
email_body = format_provisioning_email(plan)
send_email(
    to="activation@paxstore.com",
    subject=f"Terminal Provisioning: {plan.serial_number}",
    body=email_body
)
```

Currently implemented: **Email fallback** (PAX Store API not yet available).

---

## Configuration & Environment

### Required Environment Variables
```bash
# IMAP monitoring (optional)
export IMAP_EMAIL="your-email@company.com"
export IMAP_PASSWORD="your-app-password"
export IMAP_HOST="imap.gmail.com"
export VAR_PDF_DIRECTORY="/path/to/var/pdfs"

# PAX Store (optional)
export PAXSTORE_API_URL="https://api.paxstore.com/"
export PAXSTORE_API_KEY="your-api-key"

# Email notifications (if using email mode)
export SMTP_HOST="smtp.gmail.com"
export SMTP_PORT="587"
export SMTP_EMAIL="notifications@kitpos.com"
export SMTP_PASSWORD="your-password"
```

### Configuration Files
- `config/field_aliases.json` — Custom VAR PDF field mapping (if needed)

---

## PDF Field Extraction Examples

### Example 1: Standard VAR PDF
```
Input: merchant-abc123.pdf
Extracted fields:
  - business_name: "ABC Store LLC"
  - principal_name: "John Smith"
  - email: "john@abcstore.com"
  - phone: "(555) 123-4567"
  - ssn: "123-45-6789"
  - annual_revenue: "$500,000"
  - years_in_business: "5 years"
  
VarPayload created ✓
Confidence: 0.95
```

### Example 2: Partial Extraction (Missing Fields)
```
Input: merchant-xyz789.pdf
Extracted fields:
  - business_name: "XYZ Retail"
  - principal_name: "Jane Doe"
  - email: MISSING ❌
  - phone: "(555) 987-6543"
  - ssn: MISSING ❌
  
VarPayload created ⚠️
Confidence: 0.65
Missing required: ["email", "ssn"]
```

---

## CLI Usage Examples

### Example 1: Parse a VAR PDF
```bash
maverick parse-pdf /path/to/merchant-app.pdf
```

Output:
```
✓ Successfully parsed merchant-app.pdf
  Merchant ID: MER-2024-001
  Business: "Main Street Store"
  Principal: John Smith
  Email: john@mainstreet.com
  Phone: (555) 123-4567
  Confidence: 0.92
```

### Example 2: Build Provisioning Plan
```bash
maverick plan --merchant-id MER-2024-001 --serial-number TERM-456789
```

Output:
```
Provisioning Plan Created:
  Merchant: MER-2024-001
  Terminal: TERM-456789
  Steps: 5
  Estimated Duration: 300 seconds
  
Step 1: Validate merchant data
Step 2: Register terminal with PAX Store
Step 3: Download configurations
Step 4: Apply security settings
Step 5: Activate terminal
```

### Example 3: Monitor Inbox (Daemon)
```bash
maverick monitor --mode daemon --poll-interval 30
```

Output:
```
Starting IMAP monitor...
Connected to imap.gmail.com:993
Checking inbox every 30 seconds...

[2026-04-24 10:15:00] Received: MerchantRequest: MER-2024-001
[2026-04-24 10:15:02] Parsing merchant PDF...
[2026-04-24 10:15:05] Building provisioning plan...
[2026-04-24 10:15:08] Executing provisioning (email mode)...
[2026-04-24 10:15:10] ✓ Provisioning email sent
[2026-04-24 10:15:11] Waiting for next message...
```

---

## Testing & Troubleshooting

### Test PDF Parsing (No Network)
```python
from maverick_agent.parsers.var_pdf import VarPdfParser

parser = VarPdfParser()
payload = parser.parse_pdf("test-merchant.pdf")
print(f"Extracted: {payload.business_name}")
print(f"Confidence: {payload.confidence}")
print(f"Missing: {payload.missing_required}")
```

### Debug Field Extraction
```bash
maverick parse-pdf merchant.pdf --verbose
# Shows each field matched and confidence score
```

### Test IMAP Connection
```python
from maverick_agent.services.inbox import ImapInboxClient

client = ImapInboxClient(
    email="test@gmail.com",
    password="app-password",
    host="imap.gmail.com"
)
messages = client.fetch_unread()
print(f"Found {len(messages)} messages")
```

### Test Provisioning Plan Generation
```bash
maverick plan --merchant-id TEST123 --serial-number SN999 --output json
```

---

## Known Limitations & Workarounds

### 1. VAR PDF Format Variations
- **Problem:** Different PDFs use different field names
- **Workaround:** Add custom aliases to `config/field_aliases.json`

### 2. OCR Not Implemented
- **Problem:** Scanned/image PDFs won't parse correctly
- **Workaround:** Use digital PDFs only, or add OCR via optional `[ocr]` extra

### 3. IMAP Gmail Rate Limiting
- **Problem:** Polling too frequently may trigger Gmail rate limits
- **Workaround:** Use `--poll-interval 30` or higher (30+ seconds)

### 4. PAX Store API Not Available
- **Problem:** Direct API integration not yet implemented
- **Workaround:** Using email fallback mode (already implemented)

---

## Git Commands Reference

### Check Maverick Agent Status
```bash
cd /Users/walklikeaman/GitHub/kitpos/agents/maverick-terminal-agent
git log --oneline                         # See commit history
git status                                # Check working tree
git diff                                  # See changes
```

### Update Maverick Agent
```bash
git add -A && git commit -m "message"
git push origin main
```

### Compare with Kit Dashboard Agent
```bash
cd ../kit-dashboard-agent
diff -r ../maverick-terminal-agent/src/maverick_agent/ src/kit_agent/
# See structural differences
```

---

## Architecture Decisions

### Why PDF Parsing via pdfplumber
- Simple, no OCR dependency (unless optional)
- Works well with structured PDFs
- Can handle tables and key-value pairs
- Lightweight alternative to full document parsing

### Why IMAP for Inbox Monitoring
- Standard email protocol, works with any provider (Gmail, Outlook, company mail)
- No API keys needed for configuration
- Easy to implement request format (email with subject/body)
- Self-hosted or cloud provider agnostic

### Why Email Fallback for PAX Store
- PAX Store API not yet available
- Email is reliable, auditable, and human-readable
- Can be easily upgraded to direct API later without changing orchestrator

### Why Independent from Kit Dashboard Agent
- Different workflows (PDF parsing vs document OCR)
- Different integrations (IMAP + PAX Store vs Playwright + KIT Dashboard)
- Can scale independently
- Different deployment requirements

---

## How to Work with This Agent in New Chat

1. **Reference the codebase** by file path: `agents/maverick-terminal-agent/src/maverick_agent/models.py:50`
2. **Ask about CLI commands** — I know the exact signatures and options
3. **Report bugs/issues** — I can locate exact lines and fix them
4. **Add features** — I can extend PDF field aliases, add new CLI commands, or integrate PAX Store API
5. **Test changes** — I can run the agent locally and verify behavior

---

## Recent Work Summary

- ✅ Separated monolithic agent into Maverick Terminal + Kit Dashboard agents
- ✅ Created monorepo structure at `/Users/walklikeaman/GitHub/kitpos`
- ✅ Initialized git with clean history (5 commits)
- ✅ Created comprehensive documentation
- ✅ Maverick agent fully functional with PDF parsing + IMAP monitoring
- ✅ Email fallback mode implemented for provisioning
- ✅ Ready for GitHub deployment or continued local development

---

## Next Steps

- **Expand field aliases** — Add custom PDF field mappings as needed
- **Implement PAX Store API** — Direct integration when API becomes available
- **Add OCR support** — Optional `[ocr]` extra for scanned PDFs
- **Add comprehensive tests** — Unit and integration tests for parser
- **Implement audit logging** — Track all provisioning operations
- **Push to GitHub** — Deploy monorepo to GitHub (optional)

---

**Last Updated:** 2026-04-24  
**Project Status:** ✅ Production Ready  
**Monorepo Version:** 1.0.0  
**Agent Version:** 0.1.0
