"""
Check image cropper — extracts MICR line and highlights routing/account regions.

Produces two cropped PNG images per check:
  - check_routing.png  — bottom strip, routing number region highlighted
  - check_account.png  — bottom strip, account number region highlighted

Uses PyMuPDF (fitz) + Pillow for reliable crop/annotate.
"""
from __future__ import annotations
import io
from pathlib import Path

import fitz  # PyMuPDF
from PIL import Image, ImageDraw, ImageFont


def crop_check_images(check_pdf: Path, output_dir: Path, routing: str, account: str) -> dict[str, Path]:
    """
    Crop the MICR line from the check PDF and save annotated images.
    Returns {"routing": Path, "account": Path, "full_micr": Path}
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    # Render full page to PIL Image via PyMuPDF
    doc = fitz.open(str(check_pdf))
    page = doc[0]
    mat = fitz.Matrix(2.0, 2.0)
    pix = page.get_pixmap(matrix=mat)
    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

    # Checks are often scanned sideways — detect and correct orientation.
    # If width < height the scan is portrait; checks are landscape, so rotate CCW.
    if img.width < img.height:
        img = img.rotate(90, expand=True)

    w, h = img.size  # now landscape: wide × tall

    # MICR line sits at ~68-73% of the check height (above the bottom blank margin).
    # We crop 64%-76% to include the line with a little breathing room.
    micr_top = int(h * 0.64)
    micr_bottom = int(h * 0.76)

    # Full MICR strip with context
    micr = img.crop((0, micr_top, w, micr_bottom))
    paths = {}
    micr_path = output_dir / "check_micr.png"
    micr.save(str(micr_path))
    paths["full_micr"] = micr_path

    # Routing: left ~40% of MICR line
    r_right = int(w * 0.40)
    routing_crop = img.crop((0, micr_top, r_right, micr_bottom))
    routing_annotated = _annotate(routing_crop, f"Routing: {routing}", color=(255, 200, 0))
    routing_path = output_dir / "check_routing.png"
    routing_annotated.save(str(routing_path))
    paths["routing"] = routing_path

    # Account: middle 38%-78%
    a_left = int(w * 0.38)
    a_right = int(w * 0.78)
    account_crop = img.crop((a_left, micr_top, a_right, micr_bottom))
    account_annotated = _annotate(account_crop, f"Account: {account}", color=(50, 150, 255))
    account_path = output_dir / "check_account.png"
    account_annotated.save(str(account_path))
    paths["account"] = account_path

    return paths


def _annotate(img: Image.Image, label: str, color: tuple) -> Image.Image:
    """Add a colored border and label text to an image."""
    result = img.copy()
    draw = ImageDraw.Draw(result)
    bw, bh = result.size

    # Border
    border = 4
    draw.rectangle([border, border, bw - border, bh - border], outline=color, width=border)

    # Label background
    font_size = max(18, bh // 5)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", font_size)
    except Exception:
        font = ImageFont.load_default()

    text_bbox = draw.textbbox((0, 0), label, font=font)
    text_w = text_bbox[2] - text_bbox[0]
    text_h = text_bbox[3] - text_bbox[1]
    pad = 6
    draw.rectangle([border, border, text_w + pad * 2, text_h + pad * 2], fill=color)
    draw.text((border + pad, border + pad), label, fill=(0, 0, 0), font=font)

    return result
