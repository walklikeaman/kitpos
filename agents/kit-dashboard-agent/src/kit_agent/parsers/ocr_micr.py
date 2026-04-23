"""
OCR and MICR (Magnetic Ink Character Recognition) for document images.

Handles bank checks, green cards, and other document photos with specialized
recognition for MICR magnetic ink numbers on checks (routing + account).
"""

from __future__ import annotations

from pathlib import Path
import re
import subprocess
import sys
from typing import Optional


def extract_text_from_image(image_path: Path | str) -> str:
    """
    Extract text from image files (.jpg, .png, .jpeg).
    Uses EasyOCR for general text and MICR detection for bank checks.
    Falls back to Tesseract if EasyOCR is not available.
    """
    path = Path(image_path)

    # Try EasyOCR first (better for modern document formats and MICR)
    try:
        import easyocr
        reader = easyocr.Reader(['en'], gpu=False)
        result = reader.readtext(str(path), detail=0)
        text = '\n'.join(result)
        return text
    except ImportError:
        pass
    except Exception:
        # EasyOCR may fail at runtime when its model download hits local SSL /
        # trust-store issues. Fall through to Tesseract instead of aborting OCR.
        pass

    # Fallback to Tesseract
    try:
        import pytesseract
        from PIL import Image

        img = Image.open(path)
        # Use Tesseract config optimized for check recognition
        custom_config = r'--oem 3 --psm 6'
        text = pytesseract.image_to_string(img, config=custom_config)
        return text
    except ImportError:
        pass

    # Last resort: use tesseract via subprocess
    try:
        result = subprocess.run(
            ['tesseract', str(path), 'stdout'],
            capture_output=True,
            text=True,
            check=False
        )
        if result.returncode == 0:
            return result.stdout
    except FileNotFoundError:
        pass

    raise RuntimeError(
        f"Cannot extract text from {path}. "
        "Install easyocr (pip install easyocr) or pytesseract + tesseract-ocr"
    )


def extract_micr_numbers(text: str) -> tuple[str, str]:
    """
    Extract routing number and account number from MICR encoded text.

    MICR format on checks:
    - Special magnetic ink character set
    - Pattern: ⎵⎵⎵RRRRRRRRR⎵AAAAAA...⎵⎵⎵
    - Routing: 9 digits
    - Account: 4-17 digits

    Returns: (routing_number, account_number)
    """

    # Pattern 1: Standard MICR format "1: 123456789 1234567890"
    match = re.search(r'1[:;]\s*(?P<routing>\d{9})\s+(?P<account>\d{4,17})', text)
    if match:
        return match.group('routing'), match.group('account')

    # Pattern 2: Tesseract misread MICR - common patterns
    # Sometimes 0 -> O, 1 -> I, etc. Try fuzzy matching
    matches = re.findall(r'\b(?:1|[|oO]:)\s*([0-9oOlI|]{9})\s+([0-9]{4,17})', text)
    for m in matches:
        routing = m[0].replace('o', '0').replace('O', '0').replace('l', '1').replace('I', '1').replace('|', '1')
        account = m[1]
        if len(routing) == 9 and routing.isdigit():
            return routing, account

    # Pattern 3: Line with 9 digits followed by account
    # Looking for patterns like "123456789 12345678"
    lines = text.split('\n')
    for line in lines:
        # Extract sequences of digits
        digit_sequences = re.findall(r'\d{4,20}', line)
        if len(digit_sequences) >= 2:
            potential_routing = digit_sequences[0]
            potential_account = digit_sequences[1]

            # Routing must be 9 digits
            if len(potential_routing) == 9:
                if 4 <= len(potential_account) <= 17:
                    return potential_routing, potential_account

    return "", ""


def save_check_snippets(image_path: Path | str, output_dir: Path | str) -> dict[str, Path]:
    """
    Save heuristic crops for the MICR line, routing area, and account area.

    These snippets are meant for operator review and report attachments, not as
    a sole source of truth. The crop ratios are based on typical US check
    layouts and should be treated as adjustable heuristics.
    """
    from PIL import Image

    path = Path(image_path)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    image = Image.open(path)
    width, height = image.size
    crops = {
        "full_micr": (int(width * 0.12), int(height * 0.74), int(width * 0.88), int(height * 0.96)),
        "routing": (int(width * 0.55), int(height * 0.74), int(width * 0.88), int(height * 0.96)),
        "account": (int(width * 0.23), int(height * 0.74), int(width * 0.58), int(height * 0.96)),
    }
    outputs: dict[str, Path] = {}
    for name, box in crops.items():
        target = out / f"{name}.png"
        image.crop(box).save(target)
        outputs[name] = target
    return outputs


def is_valid_aba_routing_number(routing: str) -> bool:
    """
    Validate ABA routing number using checksum algorithm.
    Routing numbers are 9 digits with a specific checksum.
    """
    if not routing or len(routing) != 9 or not routing.isdigit():
        return False

    # Checksum: sum((d[0] + d[3] + d[6]) * 3 + (d[1] + d[4] + d[7]) * 7 + (d[2] + d[5] + d[8]) * 1) % 10 == 0
    digits = [int(d) for d in routing]
    checksum = (
        (digits[0] + digits[3] + digits[6]) * 3 +
        (digits[1] + digits[4] + digits[7]) * 7 +
        (digits[2] + digits[5] + digits[8]) * 1
    ) % 10

    return checksum == 0


def classify_image_document(text: str, filename: str) -> str:
    """
    Classify what type of document an image is based on OCR text.
    Returns: 'bank_document', 'driver_license', 'green_card', 'application', or 'unknown'
    """
    text_lower = text.lower()
    filename_lower = filename.lower()

    # Bank check indicators
    if any(word in text_lower for word in ['routing number', 'account number', 'check number', 'pay to']):
        return 'bank_document'
    if 'check' in filename_lower:
        return 'bank_document'

    # Driver license indicators
    if any(word in text_lower for word in ['driver license', 'license number', 'expires', 'dob', 'date of birth']):
        return 'driver_license'
    if 'dl' in filename_lower or 'license' in filename_lower:
        return 'driver_license'

    # Green card / Permanent Resident
    if any(word in text_lower for word in ['permanent resident', 'united states', 'uscis', 'category', 'card expires']):
        return 'green_card'
    if 'green' in filename_lower or 'resident' in filename_lower:
        return 'green_card'

    return 'unknown'


def ensure_ocr_dependencies():
    """
    Check if OCR dependencies are available.
    Suggests installation if missing.
    """
    has_easyocr = False
    has_tesseract = False

    try:
        import easyocr  # noqa
        has_easyocr = True
    except ImportError:
        pass

    try:
        subprocess.run(['tesseract', '--version'], capture_output=True, check=True)
        has_tesseract = True
    except (FileNotFoundError, subprocess.CalledProcessError):
        pass

    if not (has_easyocr or has_tesseract):
        print(
            "WARNING: No OCR engine available.\n"
            "Install one of:\n"
            "  pip install easyocr\n"
            "  brew install tesseract && pip install pytesseract\n"
        )
        return False

    return True
