"""
video_generator.py
------------------
Video-rendering pipeline using MoviePy 2.x and Pillow.

Scene order
-----------
1. Opening title card  – property name + subtitle (type · location)
2. Photo slides        – one per uploaded image, with a factual caption bar
3. Closing contact card – price, any remaining feature bullets, contact info

Duration targets
----------------
  4 photos → ~30 s     8 photos → ~40 s
  Formula: TITLE + (N × SLIDE) + CONTACT − (N+1) × TRANSITION

MoviePy ≥ 2.0 note
------------------
  Imports come directly from `moviepy` and `moviepy.vfx`.
  The older `moviepy.editor` namespace was removed in 2.x.
"""

from __future__ import annotations

import io
import os
import textwrap
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw, ImageFont

try:
    from moviepy import ImageClip, concatenate_videoclips
    from moviepy import vfx as mvfx
    MOVIEPY_AVAILABLE = True
except ImportError:
    MOVIEPY_AVAILABLE = False

from captions import SceneData, generate_scene_data
from config import (
    CONTACT_SCENE_DURATION,
    SLIDE_DURATION_SECONDS,
    TITLE_SCENE_DURATION,
    TRANSITION_DURATION,
    VIDEO_FPS,
    VIDEO_OUTPUT_DIR,
    VIDEO_RESOLUTION,
)


# ---------------------------------------------------------------------------
# Font helper
# ---------------------------------------------------------------------------

def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Returns the best available TrueType font at *size*, or the bitmap default."""
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except (IOError, OSError):
            continue
    return ImageFont.load_default()


def _load_font_regular(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Returns a regular-weight font; falls back to the bold helper."""
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except (IOError, OSError):
            continue
    return _load_font(size)


# ---------------------------------------------------------------------------
# Image / frame helpers
# ---------------------------------------------------------------------------

def _fit_image(pil_img: Image.Image, target_wh: tuple[int, int]) -> np.ndarray:
    """
    Letterbox-resizes *pil_img* to *target_wh* (width, height) with black
    bars to preserve aspect ratio.  Returns a uint8 NumPy array.
    """
    tw, th = target_wh
    pil_img = pil_img.convert("RGB")
    # Pillow 9.1+ uses Image.Resampling.LANCZOS; older versions expose it
    # directly on the module.  Support both to stay compatible.
    lanczos = (
        Image.Resampling.LANCZOS
        if hasattr(Image, "Resampling")
        else Image.LANCZOS  # type: ignore[attr-defined]
    )
    pil_img.thumbnail((tw, th), lanczos)
    canvas = Image.new("RGB", (tw, th), (0, 0, 0))
    canvas.paste(pil_img, ((tw - pil_img.width) // 2, (th - pil_img.height) // 2))
    return np.array(canvas)


def _draw_centered_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    y_center: int,
    canvas_w: int,
    fill: tuple[int, int, int, int] = (255, 255, 255, 255),
    shadow: bool = True,
    max_chars: int = 60,
) -> int:
    """
    Wraps *text*, draws it horizontally centred at *y_center*, and returns
    the y-coordinate of the line below the last drawn line.
    """
    wrapped = textwrap.fill(text, width=max_chars)
    lines = wrapped.split("\n")
    try:
        bbox = draw.textbbox((0, 0), "Ag", font=font)
        line_h = int(bbox[3] - bbox[1]) + 6
    except Exception:  # noqa: BLE001
        line_h = 30
    total_h = len(lines) * line_h
    y = y_center - total_h // 2
    for line in lines:
        try:
            bbox = draw.textbbox((0, 0), line, font=font)
            text_w = bbox[2] - bbox[0]
        except Exception:  # noqa: BLE001
            text_w = canvas_w // 2
        x = (canvas_w - text_w) // 2
        if shadow:
            draw.text((x + 2, y + 2), line, font=font, fill=(0, 0, 0, 180))
        draw.text((x, y), line, font=font, fill=fill)
        y += line_h
    return y


# ---------------------------------------------------------------------------
# Scene frame builders
# ---------------------------------------------------------------------------

def _make_title_frame(scene: SceneData, target_wh: tuple[int, int]) -> np.ndarray:
    """
    Renders the opening title card: dark gradient background, property name
    (large, white), subtitle line (smaller, amber), and a thin accent bar.
    """
    tw, th = target_wh
    img = Image.new("RGBA", (tw, th), (0, 0, 0, 255))
    draw = ImageDraw.Draw(img)

    # Dark gradient background (top to bottom: deep navy → very dark blue)
    for y in range(th):
        t = y / th
        r = int(10 + 15 * t)
        g = int(10 + 20 * t)
        b = int(35 + 45 * t)
        draw.line([(0, y), (tw, y)], fill=(r, g, b, 255))

    # Accent bar (horizontal rule ~40 % from top)
    bar_y = int(th * 0.40)
    draw.rectangle([(tw // 6, bar_y), (tw * 5 // 6, bar_y + 3)],
                   fill=(232, 98, 42, 255))

    # Property name – large bold
    font_title = _load_font(max(48, tw // 22))
    _draw_centered_text(draw, scene.title_line1, font_title,
                        y_center=int(th * 0.50), canvas_w=tw,
                        fill=(255, 255, 255, 255), max_chars=40)

    # Subtitle – type · location
    font_sub = _load_font_regular(max(28, tw // 38))
    _draw_centered_text(draw, scene.title_line2, font_sub,
                        y_center=int(th * 0.65), canvas_w=tw,
                        fill=(255, 200, 120, 255), max_chars=55)

    return np.array(img.convert("RGB"))


def _make_contact_frame(scene: SceneData, target_wh: tuple[int, int]) -> np.ndarray:
    """
    Renders the closing contact card with all lines from scene.contact_lines.
    Same dark gradient background as the title card for visual bookending.
    """
    tw, th = target_wh
    img = Image.new("RGBA", (tw, th), (0, 0, 0, 255))
    draw = ImageDraw.Draw(img)

    # Same dark gradient as title card
    for y in range(th):
        t = y / th
        r = int(10 + 15 * t)
        g = int(10 + 20 * t)
        b = int(35 + 45 * t)
        draw.line([(0, y), (tw, y)], fill=(r, g, b, 255))

    # Accent bar near top
    bar_y = int(th * 0.15)
    draw.rectangle([(tw // 6, bar_y), (tw * 5 // 6, bar_y + 3)],
                   fill=(232, 98, 42, 255))

    # Filter out the empty separator to determine layout
    visible_lines = [ln for ln in scene.contact_lines if ln.strip()]
    n = len(visible_lines)
    if n == 0:
        visible_lines = ["Contact us for more information"]
        n = 1

    font_large  = _load_font(max(34, tw // 30))
    font_medium = _load_font_regular(max(24, tw // 42))
    font_small  = _load_font_regular(max(20, tw // 52))

    # Lay out lines evenly in the vertical centre region
    start_y = int(th * 0.22)
    end_y   = int(th * 0.90)
    available_h = end_y - start_y
    step = available_h // max(n, 1)

    special_keywords = {"Enquire Now", "Enquiries", "Contact"}

    y = start_y + step // 2
    for ln in visible_lines:
        if ln in special_keywords or ln.startswith("Enquire"):
            font = font_large
            colour: tuple[int, int, int, int] = (255, 200, 80, 255)
        elif ln.startswith("Asking Price") or ln.startswith("₹") or "Price" in ln:
            font = font_medium
            colour = (120, 220, 120, 255)
        else:
            font = font_small
            colour = (220, 220, 220, 255)
        _draw_centered_text(draw, ln, font, y_center=y, canvas_w=tw,
                            fill=colour, max_chars=55)
        y += step

    # Accent bar near bottom
    draw.rectangle([(tw // 6, int(th * 0.88)), (tw * 5 // 6, int(th * 0.88) + 3)],
                   fill=(232, 98, 42, 255))

    return np.array(img.convert("RGB"))


def _add_caption_bar(
    frame_array: np.ndarray,
    caption: str,
    target_wh: tuple[int, int],
) -> np.ndarray:
    """
    Adds a semi-transparent dark gradient bar at the bottom of a photo frame
    and renders *caption* centred on it.
    """
    tw, th = target_wh
    img = Image.fromarray(frame_array).convert("RGBA")

    bar_h = max(80, th // 7)
    overlay = Image.new("RGBA", (tw, bar_h), (0, 0, 0, 0))
    draw_bar = ImageDraw.Draw(overlay)
    for y in range(bar_h):
        alpha = int(185 * (y / bar_h))
        draw_bar.line([(0, y), (tw, y)], fill=(0, 0, 0, alpha))
    img.paste(overlay, (0, th - bar_h), overlay)

    font_size = max(24, tw // 48)
    font = _load_font(font_size)
    draw_main = ImageDraw.Draw(img)
    max_chars = max(45, tw // max(1, font_size // 2))
    wrapped = textwrap.fill(caption, width=max_chars)
    lines = wrapped.split("\n")
    line_spacing = font_size + 6
    text_block_h = len(lines) * line_spacing
    text_y = th - bar_h + (bar_h - text_block_h) // 2

    for i, line in enumerate(lines):
        bbox = draw_main.textbbox((0, 0), line, font=font)
        text_w = bbox[2] - bbox[0]
        x = (tw - text_w) // 2
        y = text_y + i * line_spacing
        draw_main.text((x + 2, y + 2), line, font=font, fill=(0, 0, 0, 200))
        draw_main.text((x, y),         line, font=font, fill=(255, 255, 255, 255))

    return np.array(img.convert("RGB"))


# ---------------------------------------------------------------------------
# Clip builder
# ---------------------------------------------------------------------------

def _make_clip(frame: np.ndarray, duration: float) -> Any:
    """Wraps a frame array in an ImageClip with cross-fade-in applied."""
    clip = ImageClip(frame).with_duration(duration)
    if TRANSITION_DURATION > 0:
        clip = clip.with_effects([mvfx.CrossFadeIn(TRANSITION_DURATION)])
    return clip


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def render_video(
    uploaded_files: list[Any],
    photo_captions: list[str],
    output_filename: str = "property_video.mp4",
    property_details: dict | None = None,
) -> tuple[bool, str]:
    """
    Renders the full-scene MP4:

        [Title card] → [Photo slides × N] → [Contact card]

    Parameters
    ----------
    uploaded_files : list
        Streamlit UploadedFile objects (or any file-like with .read()/.seek()).
    photo_captions : list[str]
        One caption per uploaded file (must match len(uploaded_files)).
    output_filename : str
        Output file name (placed under VIDEO_OUTPUT_DIR).
    property_details : dict | None
        If supplied, used to build the title and contact cards.  If None,
        a minimal two-scene video (photo slides only) is produced.

    Returns
    -------
    (success: bool, path_or_error: str)
    """
    if not MOVIEPY_AVAILABLE:
        return False, "MoviePy is not installed. Run: pip install moviepy"

    if len(uploaded_files) != len(photo_captions):
        return False, (
            f"Mismatch: {len(uploaded_files)} images vs "
            f"{len(photo_captions)} captions."
        )

    os.makedirs(VIDEO_OUTPUT_DIR, exist_ok=True)
    output_path = str(Path(VIDEO_OUTPUT_DIR) / output_filename)
    tw, th = VIDEO_RESOLUTION

    try:
        # Build the scene data (needed for title + contact cards)
        if property_details:
            scene = generate_scene_data(property_details, len(uploaded_files))
        else:
            # Minimal fallback when called without property details
            from captions import SceneData  # local import to avoid circularity
            scene = SceneData(
                title_line1="Property Tour",
                title_line2="",
                photo_captions=photo_captions,
                contact_lines=["Contact us for more information"],
            )

        clips: list[Any] = []

        # ── 1. Opening title card ─────────────────────────────────────────
        title_frame = _make_title_frame(scene, (tw, th))
        clips.append(_make_clip(title_frame, TITLE_SCENE_DURATION))

        # ── 2. Photo slides ───────────────────────────────────────────────
        for uploaded_file, caption in zip(uploaded_files, photo_captions):
            raw = uploaded_file.read()
            uploaded_file.seek(0)
            pil_img = Image.open(io.BytesIO(raw))
            frame = _fit_image(pil_img, (tw, th))
            frame = _add_caption_bar(frame, caption, (tw, th))
            clips.append(_make_clip(frame, SLIDE_DURATION_SECONDS))

        # ── 3. Closing contact card ───────────────────────────────────────
        contact_frame = _make_contact_frame(scene, (tw, th))
        clips.append(_make_clip(contact_frame, CONTACT_SCENE_DURATION))

        # Concatenate with cross-fade overlap
        # padding accepts float in practice; cast to satisfy strict type stubs.
        # Negated so clips overlap by TRANSITION_DURATION seconds (cross-fade).
        final = concatenate_videoclips(
            clips,
            method="compose",
            padding=-TRANSITION_DURATION,  # type: ignore[arg-type]
        )
        final.write_videofile(
            output_path,
            fps=VIDEO_FPS,
            codec="libx264",
            audio=False,
            logger=None,
        )
        return True, output_path

    except Exception as exc:  # noqa: BLE001
        return False, f"Video rendering failed: {exc}"


def expected_duration(num_photos: int) -> float:
    """
    Returns the approximate total video duration in seconds for *num_photos*
    uploaded images, accounting for cross-fade overlap.

    Formula
    -------
    TITLE + (N × SLIDE) + CONTACT − (N + 1) × TRANSITION
    """
    n_transitions = num_photos + 1   # title→slide1, slide1→slide2…, slideN→contact
    raw = TITLE_SCENE_DURATION + num_photos * SLIDE_DURATION_SECONDS + CONTACT_SCENE_DURATION
    return raw - n_transitions * TRANSITION_DURATION
