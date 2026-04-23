# KIT Dashboard Agent

Automated merchant onboarding agent for KIT Dashboard with document parsing and browser automation.

## Features

- Parse merchant application PDFs
- Extract data from driver licenses and green cards
- Recognize MICR (bank check routing/account numbers)
- Validate merchant profiles with ABA checksum
- Automate KIT Dashboard form filling
- Upload supporting documents
- Submit applications with validation

## Installation

```bash
# Clone the repository
git clone https://github.com/your-org/kit-dashboard-agent.git
cd kit-dashboard-agent

# Install dependencies
pip install -e .

# Optional: Install with OCR support for document text extraction
pip install -e '.[ocr]'

# Optional: Install browser automation for dashboard submission
pip install -e '.[browser]'

# Download browser drivers (Playwright)
playwright install chromium
```

## Configuration

Create a `.env` file with:

```bash
KIT_DASHBOARD_EMAIL=your-email@example.com
KIT_DASHBOARD_PASSWORD=your-password
KIT_DASHBOARD_URL=https://kitdashboard.com/
```

## Usage

### Parse merchant documents

```bash
kit parse-docs "/path/to/application.pdf" "/path/to/check.jpg" "/path/to/license.jpg"
```

### Build an onboarding plan

```bash
kit plan "/path/to/application.pdf" "/path/to/check.jpg" "/path/to/license.jpg"
```

### Generate a formatted report

```bash
kit report "/path/to/application.pdf" "/path/to/check.jpg" "/path/to/license.jpg"
```

### Reveal sensitive data (for testing)

```bash
kit plan --reveal-sensitive "/path/to/application.pdf" "/path/to/check.jpg" "/path/to/license.jpg"
```

## Project Structure

```
kit-dashboard-agent/
├── src/kit_agent/
│   ├── cli.py                      # Command-line interface
│   ├── models.py                   # Data models
│   ├── kit_orchestrator.py        # Onboarding orchestrator
│   ├── services/
│   │   └── kit_dashboard.py       # KIT Dashboard form automation
│   └── parsers/
│       ├── kit_documents.py       # Document parser
│       └── ocr_micr.py            # OCR + MICR recognition
├── tests/                          # Unit tests
├── config/                         # Configuration files
├── merchants/                      # Merchant profiles (git-ignored)
├── pyproject.toml                 # Project configuration
└── README.md
```

## Architecture

1. **CLI** - Command interface for onboarding operators
2. **KitMerchantOnboardingOrchestrator** - Coordinates the onboarding workflow
3. **KitDocumentParser** - Extracts merchant data from mixed documents
4. **OCR Module** - Text extraction with EasyOCR/Tesseract fallback
5. **MICR Recognition** - Bank routing/account number extraction
6. **KitDashboardBrowserAgent** - Playwright automation for form filling

## Supported Documents

- **PDF** - Application forms, voided checks
- **JPEG/PNG** - Driver licenses, green cards, check images
- **Text** - Manual merchant data entry

## Document Types

- **Application** - Merchant business information
- **Driver License** - Principal identification
- **Green Card** - Permanent resident card with DOB
- **Bank Check** - MICR-encoded routing and account numbers

## Security

- ✅ Sensitive data (SSN, account numbers) masked by default
- ✅ Credentials from environment variables only
- ✅ No hardcoded secrets in code
- ✅ ABA routing number validation before submission

## Models

- `KitMerchantProfile` - Extracted merchant data
- `KitDocumentPayload` - Parsed documents and validation results
- `KitOnboardingPlan` - Complete onboarding plan with defaults
- `KitOnboardingOutcome` - Status, validation results, and next actions
