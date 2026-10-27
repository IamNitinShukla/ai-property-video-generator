"""
captions.py
-----------
Caption generation logic.

Phase 1  – Factually grounded template captions derived only from user-
            supplied property details.  No invented amenities or generic
            marketing claims.

Phase 2  – Calls the Gemini API (google-genai SDK) when GEMINI_API_KEY is set.

            Image-aware mode (default when images are supplied):
              Passes every uploaded photo to Gemini as a multimodal message,
              in upload order, each labelled "Image <n>".  Gemini sees the
              actual pixels and writes one caption per image based on what it
              observes, grounded by the user-supplied property details.

            Text-only mode (fallback when images cannot be read):
              Sends only property details and photo count.  Gemini assigns
              captions from the feature list sequentially, which can
              mis-align captions with photos.  This mode is explicitly
              labelled "gemini-text" so callers can distinguish it.

            Falls back to template captions if:
              • GEMINI_API_KEY is absent or empty
              • The HTTP request fails for any reason
              • The returned JSON is missing required fields or has wrong types
              • Any other unexpected exception

Public API
----------
generate_scene_data(property_details, num_photo_slides)  -> SceneData
    Returns structured scene info from templates (no API call).

generate_captions(property_details, num_slides, uploaded_files=None)
    -> (list[str], str)
    Tries Gemini first (image-aware when files are supplied); falls back to
    templates.  Returns (photo_caption_list, method_label).
    method_label: "gemini-images" | "gemini-text" | "template"
"""

from __future__ import annotations

import io
import json
import logging
import time
from dataclasses import dataclass
from typing import Any

from config import (
    GEMINI_API_KEY,
    GEMINI_MAX_RETRIES,
    GEMINI_MODEL,
    GEMINI_REQUEST_TIMEOUT_MS,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data structure
# ---------------------------------------------------------------------------

@dataclass
class SceneData:
    """Structured scene information for the video renderer."""
    title_line1: str           # large text on opening title card
    title_line2: str           # smaller subtitle on opening title card
    photo_captions: list[str]  # one caption per photo slide
    contact_lines: list[str]   # lines rendered on the closing contact card


# ---------------------------------------------------------------------------
# Helpers shared by both generators
# ---------------------------------------------------------------------------

def _feature_bullets(features_text: str) -> list[str]:
    """Splits the free-text features field into a list of non-empty lines."""
    return [line.strip() for line in features_text.splitlines() if line.strip()]


def _build_contact_lines(
    price: str,
    bullets: list[str],
    shown_bullets: int,
    contact: str,
) -> list[str]:
    """
    Builds the list of lines for the closing contact card.

    Parameters
    ----------
    price          : asking price string (may be empty)
    bullets        : all feature bullets
    shown_bullets  : how many bullets were already used on photo slides
    contact        : contact string (may be empty)
    """
    lines: list[str] = []
    if price:
        lines.append(f"Asking Price: {price}")
    lines.extend(bullets[shown_bullets:])
    if contact:
        lines.append("")           # blank separator line
        lines.append("Enquire Now")
        lines.append(contact)
    return lines


def _safe_fallback_captions(
    property_details: dict,
    num_photos: int,
) -> list[str]:
    """
    Returns generic, non-feature-specific captions safe to use when image
    alignment cannot be guaranteed.  No feature bullet is assigned to any
    specific photo.
    """
    name     = property_details.get("name", "").strip() or "Property"
    location = property_details.get("location", "").strip() or ""
    price    = property_details.get("price", "").strip()

    captions: list[str] = []
    for i in range(num_photos):
        if i == 0:
            cap = f"{name}  ·  {location}" if location else name
        elif price and i == num_photos - 1:
            cap = f"Asking Price: {price}"
        else:
            cap = name
        captions.append(cap)
    return captions


# ---------------------------------------------------------------------------
# Template generator (Phase 1 / fallback)
# ---------------------------------------------------------------------------

def generate_scene_data(
    property_details: dict,
    num_photo_slides: int,
) -> SceneData:
    """
    Builds all scene captions from user-supplied property details only.

    Rules
    -----
    - Only information present in *property_details* is used.
    - No invented amenities, finishes, or lifestyle claims.
    - Slide 1 anchors with property name + location.
    - Slides 2..N each show one feature bullet.
    - Once bullets are exhausted, remaining slides show the price or location.
    - Remaining bullets and contact info appear on the closing card.
    """
    name      = property_details.get("name", "").strip()      or "Property"
    location  = property_details.get("location", "").strip()  or "Location not specified"
    price     = property_details.get("price", "").strip()
    prop_type = property_details.get("property_type", "").strip() or "Property"
    features  = property_details.get("features", "").strip()
    contact   = property_details.get("contact", "").strip()

    bullets = _feature_bullets(features)

    # ── Title card ───────────────────────────────────────────────────────────
    title_line1 = name
    title_line2 = f"{prop_type}  ·  {location}"

    # ── Photo slide captions ─────────────────────────────────────────────────
    photo_captions: list[str] = []
    for i in range(num_photo_slides):
        if i == 0:
            caption = f"{name}  ·  {location}"
        elif (i - 1) < len(bullets):
            caption = bullets[i - 1]
        elif price:
            caption = f"Asking Price: {price}"
        else:
            caption = location
        photo_captions.append(caption)

    # ── Contact card ─────────────────────────────────────────────────────────
    shown_bullets = num_photo_slides - 1   # slide 0 used for identity anchor
    contact_lines = _build_contact_lines(price, bullets, shown_bullets, contact)

    return SceneData(
        title_line1=title_line1,
        title_line2=title_line2,
        photo_captions=photo_captions,
        contact_lines=contact_lines,
    )


# ---------------------------------------------------------------------------
# Gemini generator (Phase 2) – image-aware
# ---------------------------------------------------------------------------

_IMAGE_AWARE_SCHEMA = """\
Return ONLY a valid JSON object — no markdown fences, no extra keys:
{{
  "title_line1": "<property name, max 60 chars>",
  "title_line2": "<property type and location, max 80 chars>",
  "photo_captions": [
    {{"index": 0, "caption": "<caption for Image 0>"}},
    ...
    {{"index": {last_idx}, "caption": "<caption for Image {last_idx}>"}}
  ],
  "contact_lines": ["<line 1>", ...]
}}

Rules for photo_captions:
- Array must contain exactly {num_photos} objects, one per image, in index order 0..{last_idx}.
- Each object has "index" (integer, 0-based) and "caption" (string).
- Write the caption based on what you actually see in the corresponding image.
- Use ONLY the property details below to supply factual claims (name, location,
  type, price, features). Do NOT invent amenities or attributes not listed.
- If you cannot determine what a room is, write a neutral description
  (e.g. "Interior view – {{name}}") rather than inventing a room type.
- Caption 0 must state the property name and location.
- Captions 1..N describe what is visible in each image, grounded by the
  listed features where applicable.
- Each caption: 10–120 characters.

Rules for contact_lines:
- Include the asking price (if provided) as the first non-blank line.
- Include "Enquire Now" followed by the contact string.
- Max 6 lines (blank separators count).
"""

_TEXT_ONLY_SCHEMA = """\
Return ONLY a valid JSON object — no markdown fences, no extra keys:
{{
  "title_line1": "<property name, max 60 chars>",
  "title_line2": "<property type and location, max 80 chars>",
  "photo_captions": ["<caption for photo 0>", ..., "<caption for photo {last_idx}>"],
  "contact_lines": ["<line 1>", ...]
}}

Rules for photo_captions:
- Array must contain exactly {num_photos} strings.
- Caption 0: state the property name and location only.
- Captions 1..N: each states one factual detail from the features list.
  If features run out, use location, property type, or price (once each).
  Do NOT repeat the same phrase on consecutive slides.
- Do NOT invent amenities or attributes not listed in the details.
- Each caption: 10–120 characters.

Rules for contact_lines:
- Include the asking price (if provided) as the first non-blank line.
- Include "Enquire Now" followed by the contact string.
- Max 6 lines.
"""


def _build_property_block(property_details: dict, num_photos: int) -> str:
    """Returns the property-details section of the prompt (text only)."""
    name      = property_details.get("name", "").strip()
    location  = property_details.get("location", "").strip()
    price     = property_details.get("price", "").strip()
    prop_type = property_details.get("property_type", "").strip()
    features  = property_details.get("features", "").strip()
    contact   = property_details.get("contact", "").strip()
    return (
        "PROPERTY DETAILS\n"
        "----------------\n"
        f"Name          : {name}\n"
        f"Location      : {location}\n"
        f"Type          : {prop_type}\n"
        f"Asking Price  : {price if price else 'Not specified'}\n"
        f"Features      : {features if features else 'None provided'}\n"
        f"Contact       : {contact if contact else 'Not specified'}\n"
        f"Photo count   : {num_photos}\n"
    )


def _validate_image_aware_json(data: object, num_photos: int) -> list[str]:
    """
    Validates the image-aware JSON response (photo_captions is a list of
    {index, caption} objects) and returns a plain list[str] of captions
    ordered by index.

    Raises ValueError on any schema or ordering violation.
    """
    if not isinstance(data, dict):
        raise ValueError(f"Expected dict, got {type(data).__name__}")

    if "photo_captions" not in data:
        raise ValueError("Missing 'photo_captions'")
    raw = data["photo_captions"]
    if not isinstance(raw, list):
        raise ValueError("'photo_captions' must be a list")
    if len(raw) != num_photos:
        raise ValueError(
            f"'photo_captions' has {len(raw)} items; expected {num_photos}"
        )

    # Accept either [{index, caption}] objects OR plain strings (text-only
    # fallback if model ignores the schema format).
    if raw and isinstance(raw[0], str):
        # Model returned plain strings – validate and return directly.
        captions: list[str | None] = list(raw)
    else:
        # Expect [{index, caption}] objects.
        captions = [None] * num_photos
        seen: set[int] = set()
        for item in raw:
            if not isinstance(item, dict):
                raise ValueError(f"photo_captions item is not a dict: {item!r}")
            if "index" not in item or "caption" not in item:
                raise ValueError(
                    f"photo_captions item missing 'index' or 'caption': {item!r}"
                )
            idx = item["index"]
            cap = item["caption"]
            if not isinstance(idx, int):
                raise ValueError(f"'index' must be int, got {type(idx).__name__}")
            if idx in seen:
                raise ValueError(f"Duplicate index {idx} in photo_captions")
            if idx < 0 or idx >= num_photos:
                raise ValueError(
                    f"Index {idx} out of range [0, {num_photos - 1}]"
                )
            if not isinstance(cap, str) or not cap.strip():
                raise ValueError(f"caption for index {idx} is not a non-empty string")
            if len(cap) > 200:
                raise ValueError(f"caption for index {idx} exceeds 200 chars")
            seen.add(idx)
            captions[idx] = cap

        missing = [i for i, c in enumerate(captions) if c is None]
        if missing:
            raise ValueError(f"No caption for image index(es): {missing}")

    # Final per-caption checks (applies to both formats)
    result: list[str] = []
    for i, cap in enumerate(captions):
        if not isinstance(cap, str) or not cap.strip():
            raise ValueError(f"caption[{i}] is empty or not a string")
        if len(cap) > 200:
            raise ValueError(f"caption[{i}] exceeds 200 chars")
        result.append(cap.strip())
    return result


def _validate_gemini_json(data: object, num_photos: int) -> SceneData:
    """
    Validates the text-only JSON response and returns a SceneData.
    Raises ValueError on any schema violation.
    """
    if not isinstance(data, dict):
        raise ValueError(f"Expected dict, got {type(data).__name__}")

    for field in ("title_line1", "title_line2"):
        if field not in data:
            raise ValueError(f"Missing field: '{field}'")
        if not isinstance(data[field], str) or not data[field].strip():
            raise ValueError(f"Field '{field}' must be a non-empty string")

    if "photo_captions" not in data:
        raise ValueError("Missing field: 'photo_captions'")
    captions = data["photo_captions"]
    if not isinstance(captions, list):
        raise ValueError("'photo_captions' must be a list")
    if len(captions) != num_photos:
        raise ValueError(
            f"'photo_captions' has {len(captions)} items; expected {num_photos}"
        )
    for i, cap in enumerate(captions):
        if not isinstance(cap, str) or not cap.strip():
            raise ValueError(f"photo_captions[{i}] is not a non-empty string")
        if len(cap) > 200:
            raise ValueError(f"photo_captions[{i}] exceeds 200 chars")

    if "contact_lines" not in data:
        raise ValueError("Missing field: 'contact_lines'")
    contact_lines = data["contact_lines"]
    if not isinstance(contact_lines, list):
        raise ValueError("'contact_lines' must be a list")
    for i, ln in enumerate(contact_lines):
        if not isinstance(ln, str):
            raise ValueError(f"contact_lines[{i}] is not a string")

    return SceneData(
        title_line1=data["title_line1"].strip(),
        title_line2=data["title_line2"].strip(),
        photo_captions=[c.strip() for c in captions],
        contact_lines=[str(ln) for ln in contact_lines],
    )


def _strip_fences(raw: str) -> str:
    """Strips accidental ```json ... ``` markdown fences from a response."""
    raw = raw.strip()
    if raw.startswith("```"):
        lines = raw.splitlines()
        raw = "\n".join(
            ln for ln in lines if not ln.strip().startswith("```")
        ).strip()
    return raw


def _read_image_bytes(uploaded_file: Any) -> bytes:
    """
    Reads bytes from a Streamlit UploadedFile (or any file-like with
    .read()/.seek()).  Always rewinds to position 0 after reading.
    """
    data = uploaded_file.read()
    uploaded_file.seek(0)
    return data


def _infer_mime(filename: str) -> str:
    """Returns the MIME type for common image extensions."""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return {
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "png": "image/png",
        "webp": "image/webp",
        "gif": "image/gif",
    }.get(ext, "image/jpeg")


def _call_gemini_with_images(
    property_details: dict,
    uploaded_files: list[Any],
) -> tuple[list[str], str]:
    """
    Calls Gemini with the actual image bytes so it can caption each photo
    based on what it sees.  Returns (photo_captions, "gemini-images").

    The prompt instructs Gemini to return one {index, caption} object per
    image, keyed by the 0-based upload order so we can verify alignment.

    A hard timeout (GEMINI_REQUEST_TIMEOUT_MS) is set on the HTTP client so
    the call never blocks the Streamlit main thread indefinitely.  Transient
    503/429 errors are retried up to GEMINI_MAX_RETRIES times with
    exponential back-off before the exception is re-raised to the caller.

    Security
    --------
    The API key is passed only to the SDK constructor; it never appears in
    prompts, logs, or error messages.
    """
    # pyrefly: ignore[missing-import]
    import google.genai as genai
    # pyrefly: ignore[missing-import]
    from google.genai import types

    num_photos = len(uploaded_files)
    last_idx   = num_photos - 1
    prop_block = _build_property_block(property_details, num_photos)
    schema     = _IMAGE_AWARE_SCHEMA.format(
        num_photos=num_photos,
        last_idx=last_idx,
    )

    intro = (
        "You are generating image-specific captions for a real-estate "
        "promotional video.\n"
        "Each image is labelled with its index number (0-based) so you can "
        "match captions to photos exactly.\n"
        "Describe what you actually see in each image. Use the property "
        "details only for factual claims — do not invent anything.\n\n"
        f"{prop_block}\n{schema}"
    )

    # Build a multimodal content list:
    # [text intro, Image 0 bytes, label, Image 1 bytes, label, …]
    contents: list[Any] = [intro]
    for i, uf in enumerate(uploaded_files):
        img_bytes = _read_image_bytes(uf)
        mime      = _infer_mime(getattr(uf, "name", "image.jpg"))
        contents.append(
            types.Part.from_bytes(data=img_bytes, mime_type=mime)
        )
        contents.append(f"(Above image is Image {i})")

    # Apply a hard wall-clock timeout so the spinner can't block forever.
    client = genai.Client(
        api_key=GEMINI_API_KEY,
        http_options=types.HttpOptions(timeout=GEMINI_REQUEST_TIMEOUT_MS),
    )
    gen_cfg = types.GenerateContentConfig(
        response_mime_type="application/json",
        temperature=0.15,        # low → consistent visual descriptions
        max_output_tokens=2048,  # larger budget for multi-image responses
    )

    # Bounded retry loop for transient 503 / 429 errors.
    last_exc: Exception | None = None
    for attempt in range(1, GEMINI_MAX_RETRIES + 2):   # +2 → initial + N retries
        try:
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=contents,
                config=gen_cfg,
            )
            break   # success
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            err_str  = str(exc)
            is_retryable = "503" in err_str or "429" in err_str or "UNAVAILABLE" in err_str
            if is_retryable and attempt <= GEMINI_MAX_RETRIES:
                wait = 2 ** attempt          # 2s, 4s …
                logger.warning(
                    "Gemini image-aware: attempt %d/%d failed (%s). Retrying in %ds.",
                    attempt, GEMINI_MAX_RETRIES + 1, type(exc).__name__, wait,
                )
                time.sleep(wait)
            else:
                raise   # non-retryable or retries exhausted
    else:
        # All retries exhausted (loop exited without break)
        raise last_exc  # type: ignore[misc]

    raw = _strip_fences(response.text)
    parsed = json.loads(raw)
    photo_captions = _validate_image_aware_json(parsed, num_photos)
    return photo_captions, "gemini-images"


def _call_gemini_text_only(
    property_details: dict,
    num_photos: int,
) -> SceneData:
    """
    Text-only Gemini call (no images).  Captions are assigned from the
    feature list in sequential order — alignment with specific photos is
    NOT guaranteed.  Used as an intermediate fallback when images cannot
    be read.

    Same timeout and retry policy as _call_gemini_with_images.

    Security: API key passed only to SDK constructor.
    """
    # pyrefly: ignore[missing-import]
    import google.genai as genai
    # pyrefly: ignore[missing-import]
    from google.genai import types

    last_idx   = num_photos - 1
    prop_block = _build_property_block(property_details, num_photos)
    schema     = _TEXT_ONLY_SCHEMA.format(
        num_photos=num_photos,
        last_idx=last_idx,
    )

    prompt = (
        "You are generating scene captions for a real-estate promotional "
        "video.\nUse ONLY the property details provided. Do not invent "
        f"facts.\n\n{prop_block}\n{schema}"
    )

    # Hard timeout – same policy as the image-aware call.
    client = genai.Client(
        api_key=GEMINI_API_KEY,
        http_options=types.HttpOptions(timeout=GEMINI_REQUEST_TIMEOUT_MS),
    )
    gen_cfg = types.GenerateContentConfig(
        response_mime_type="application/json",
        temperature=0.2,
        max_output_tokens=1024,
    )

    last_exc: Exception | None = None
    for attempt in range(1, GEMINI_MAX_RETRIES + 2):
        try:
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=prompt,
                config=gen_cfg,
            )
            break
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            err_str  = str(exc)
            is_retryable = "503" in err_str or "429" in err_str or "UNAVAILABLE" in err_str
            if is_retryable and attempt <= GEMINI_MAX_RETRIES:
                wait = 2 ** attempt
                logger.warning(
                    "Gemini text-only: attempt %d/%d failed (%s). Retrying in %ds.",
                    attempt, GEMINI_MAX_RETRIES + 1, type(exc).__name__, wait,
                )
                time.sleep(wait)
            else:
                raise
    else:
        raise last_exc  # type: ignore[misc]

    raw = _strip_fences(response.text)
    parsed = json.loads(raw)
    return _validate_gemini_json(parsed, num_photos)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def generate_captions(
    property_details: dict,
    num_slides: int,
    uploaded_files: list[Any] | None = None,
) -> tuple[list[str], str]:
    """
    Returns (photo_caption_list, method_label).

    Priority order:
    1. Gemini with images  ("gemini-images") — requires GEMINI_API_KEY +
                                               uploaded_files readable as bytes
    2. Gemini text-only   ("gemini-text")   — requires GEMINI_API_KEY;
                                               no image alignment guarantee
    3. Template fallback  ("template")      — always safe

    Falls back silently to the next level on any exception.
    The API key never appears in logs or error strings.
    """
    if GEMINI_API_KEY:
        # ── Attempt 1: image-aware Gemini ────────────────────────────────
        if uploaded_files and len(uploaded_files) == num_slides:
            try:
                caps, method = _call_gemini_with_images(
                    property_details, uploaded_files
                )
                logger.info("Image-aware Gemini captions generated successfully.")
                return caps, method
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Image-aware Gemini call failed (%s: %s). "
                    "Falling back to text-only Gemini.",
                    type(exc).__name__,
                    str(exc)[:200],
                )

        # ── Attempt 2: text-only Gemini (no alignment guarantee) ─────────
        try:
            scene = _call_gemini_text_only(property_details, num_slides)
            logger.info("Text-only Gemini captions generated (no image alignment).")
            return scene.photo_captions, "gemini-text"
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Text-only Gemini call also failed (%s: %s). "
                "Falling back to templates.",
                type(exc).__name__,
                str(exc)[:200],
            )

    # ── Attempt 3: template fallback ─────────────────────────────────────
    scene = generate_scene_data(property_details, num_slides)
    return scene.photo_captions, "template"
