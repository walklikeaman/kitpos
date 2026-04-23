# Maverick Terminal Agent

Automated terminal provisioning agent for adding payment terminals to merchants.

## Features

- Parse merchant VAR (Variable Rate) PDFs
- Extract terminal and merchant information
- Auto-detect merchant data from email inbox (IMAP)
- Build provisioning plans for PAX terminals
- Validate merchant references and required fields

## Installation

```bash
# Clone the repository
git clone https://github.com/your-org/maverick-terminal-agent.git
cd maverick-terminal-agent

# Install dependencies
pip install -e .

# Optional: Install with OCR support for serial number recognition
pip install -e '.[ocr]'
```

## Configuration

Create a `.env` file with:

```bash
# Email configuration (optional)
MAIL_PROVIDER=imap
MAIL_IMAP_HOST=mail.example.com
MAIL_IMAP_PORT=993
MAIL_USERNAME=your-email@example.com
MAIL_PASSWORD=your-password
MAIL_IMAP_MAILBOX=INBOX
MAIL_SCAN_LIMIT=50
```

Or set environment variables:

```bash
export MAIL_IMAP_HOST="mail.example.com"
export MAIL_IMAP_PORT="993"
export MAIL_USERNAME="your-email"
export MAIL_PASSWORD="your-password"
```

## Usage

### Parse a VAR PDF

```bash
maverick parse-pdf "/path/to/merchant-vat.pdf"
```

### Build a provisioning plan

```bash
maverick plan \
  --merchant-id MERCHANT123 \
  --serial-number ABC123DEF456 \
  --pdf "/path/to/merchant-vat.pdf"
```

Or auto-detect PDF from email:

```bash
maverick plan \
  --merchant-id MERCHANT123 \
  --serial-number ABC123DEF456
```

## Project Structure

```
maverick-terminal-agent/
├── src/maverick_agent/
│   ├── cli.py                    # Command-line interface
│   ├── config.py                 # Configuration management
│   ├── models.py                 # Data models
│   ├── orchestrator.py           # Provisioning orchestrator
│   ├── services/
│   │   ├── paxstore.py          # PAX Store integration
│   │   └── inbox.py             # Email inbox client
│   └── parsers/
│       └── var_pdf.py           # VAR PDF parser
├── tests/                        # Unit tests
├── pyproject.toml               # Project configuration
└── README.md
```

## Architecture

1. **CLI** - Command interface for operators
2. **ProvisioningOrchestrator** - Coordinates the provisioning workflow
3. **VarPdfParser** - Extracts data from merchant PDFs
4. **ImapInboxClient** - Auto-detects merchant PDFs in email
5. **PAXStore** - Integration with payment processor

## Models

- `MerchantRequest` - Input: merchant ID, serial number, PDF path
- `VarPayload` - Extracted fields from PDF
- `RunPlan` - Provisioning plan with validated fields
- `RunOutcome` - Final status and next actions
