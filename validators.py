"""
validators.py
-------------
Pure-Python validation helpers.  No Streamlit or IO side-effects so they are
easy to unit-test in isolation.
"""

from __future__ import annotations

import io
import os
from pathlib import Path
from typing import Any

from PIL import Image, UnidentifiedImageError

from config import ALLOWED_EXTENSIONS, MAX_IMAGES, MIN_IMAGES


# ---------------------------------------------------------------------------
# Image validation
# ---------------------------------------------------------------------------

def validate_image_file(uploaded_file: Any) -> tuple[bool, str]:
    """
    Validates a single Streamlit UploadedFile object.

    Returns
    -------
    (is_valid, error_message)  –  error_message is empty when valid.
    """
    name: str = getattr(uploaded_file, "name", "")
    ext = Path(name).suffix.lower()

    if ext not in ALLOWED_EXTENSIONS:
        return False, (
            f"'{name}' has an unsupported extension '{ext}'. "
            f"Allowed: {', '.join(ALLOWED_EXTENSIONS)}"
        )

    try:
        raw_bytes: bytes = uploaded_file.read()
        uploaded_file.seek(0)          # reset so the caller can read again
        img = Image.open(io.BytesIO(raw_bytes))
        img.verify()                   # checks file integrity without decoding
    except UnidentifiedImageError:
        return False, f"'{name}' could not be identified as a valid image."
    except Exception as exc:           # noqa: BLE001
        return False, f"'{name}' failed validation: {exc}"

    return True, ""


def validate_image_count(files: list[Any]) -> tuple[bool, str]:
    """
    Checks that the upload count is within [MIN_IMAGES, MAX_IMAGES].

    Returns
    -------
    (is_valid, error_message)
    """
    count = len(files)
    if count < MIN_IMAGES:
        return False, (
            f"Please upload at least {MIN_IMAGES} images "
            f"(you uploaded {count})."
        )
    if count > MAX_IMAGES:
        return False, (
            f"Please upload no more than {MAX_IMAGES} images "
            f"(you uploaded {count})."
        )
    return True, ""


def validate_all_images(files: list[Any]) -> list[str]:
    """
    Validates count and each individual file.

    Returns
    -------
    A list of error strings; empty list means everything is valid.
    """
    errors: list[str] = []

    count_ok, count_err = validate_image_count(files)
    if not count_ok:
        errors.append(count_err)
        return errors  # no point checking individual files if count is wrong

    for f in files:
        ok, msg = validate_image_file(f)
        if not ok:
            errors.append(msg)

    return errors


# ---------------------------------------------------------------------------
# Property form validation
# ---------------------------------------------------------------------------

def validate_property_details(details: dict) -> list[str]:
    """
    Validates the property form fields submitted via the Streamlit UI.

    Parameters
    ----------
    details : dict
        Keys: name, location, price, property_type, features, contact

    Returns
    -------
    A list of error strings; empty means the form is valid.
    """
    errors: list[str] = []
    required = {
        "name": "Property Name",
        "location": "Location",
        "price": "Price",
        "property_type": "Property Type",
        "contact": "Contact Information",
    }

    for field, label in required.items():
        value = details.get(field, "")
        if not str(value).strip():
            errors.append(f"'{label}' is required.")

    # Price should be a positive number if provided
    price_raw = str(details.get("price", "")).strip()
    if price_raw:
        cleaned = price_raw.replace(",", "").replace("₹", "").replace("$", "").strip()
        try:
            if float(cleaned) <= 0:
                errors.append("'Price' must be a positive number.")
        except ValueError:
            errors.append(
                "'Price' must be a numeric value (e.g. 8500000 or 85,00,000)."
            )

    return errors
