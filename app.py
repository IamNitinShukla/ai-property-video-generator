"""
app.py
------
Entry point for the AI Property Video Generator Streamlit application.

Run with:
    streamlit run app.py
"""

from __future__ import annotations

# pyrefly: ignore[missing-import]
import streamlit as st

from captions import generate_captions, generate_scene_data
from config import GEMINI_API_KEY, GEMINI_MODEL, MAX_IMAGES, MIN_IMAGES, PROPERTY_TYPES
from sample_data import SAMPLE_PROPERTY
from validators import validate_all_images, validate_property_details
from video_generator import expected_duration, render_video

# ---------------------------------------------------------------------------
# Page configuration
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="AI Property Video Generator | Realty Assistant",
    page_icon="🏡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Custom CSS
# ---------------------------------------------------------------------------
st.markdown(
    """
    <style>
        /* ---- global palette ---- */
        :root {
            --accent: #E8622A;
            --accent-light: #FF8C5A;
            --bg-card: #1E1E2E;
            --text-muted: #A0A0B0;
        }

        /* ---- hero banner ---- */
        .hero {
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
            border-radius: 16px;
            padding: 2.5rem 2rem;
            margin-bottom: 1.5rem;
            border: 1px solid rgba(232,98,42,0.3);
            box-shadow: 0 8px 32px rgba(0,0,0,0.4);
        }
        .hero h1 {
            font-size: 2.4rem;
            font-weight: 800;
            color: #fff;
            margin: 0 0 0.4rem 0;
        }
        .hero h1 span { color: var(--accent-light); }
        .hero p  { color: #ccc; font-size: 1.05rem; margin: 0; }

        /* ---- section headers ---- */
        .section-title {
            font-size: 1.2rem;
            font-weight: 700;
            color: var(--accent-light);
            border-left: 4px solid var(--accent);
            padding-left: 0.6rem;
            margin: 1.4rem 0 0.8rem 0;
        }

        /* ---- validation error box ---- */
        .err-box {
            background: rgba(220, 50, 50, 0.15);
            border: 1px solid rgba(220, 50, 50, 0.5);
            border-radius: 8px;
            padding: 0.8rem 1rem;
            margin-top: 0.5rem;
        }
        .err-box ul { margin: 0.3rem 0 0 1.2rem; padding: 0; }

        /* ---- info badge ---- */
        .badge {
            display: inline-block;
            background: rgba(232,98,42,0.2);
            color: var(--accent-light);
            border: 1px solid rgba(232,98,42,0.4);
            border-radius: 20px;
            padding: 2px 12px;
            font-size: 0.82rem;
            font-weight: 600;
        }

        /* ---- generate button override ---- */
        div[data-testid="stButton"] button {
            background: linear-gradient(90deg, #E8622A, #FF8C5A);
            color: white;
            border: none;
            font-weight: 700;
            font-size: 1rem;
            padding: 0.6rem 2rem;
            border-radius: 8px;
            transition: opacity 0.2s;
        }
        div[data-testid="stButton"] button:hover { opacity: 0.88; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Hero banner
# ---------------------------------------------------------------------------
st.markdown(
    """
    <div class="hero">
        <h1>🏡 AI Property <span>Video Generator</span></h1>
        <p>
            Fill in your property details, upload 4–8 high-quality photographs,
            and click <strong>Generate Video</strong> to export a polished MP4
            promotional reel – powered by <em>Realty Assistant</em>.
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Session-state initialisation
# ---------------------------------------------------------------------------
# Set default (empty) values for all field keys on the very first run only.
# After that, session_state owns the values – we never overwrite them unless
# the user explicitly clicks "Load Sample Data".
_FIELD_DEFAULTS: dict = {
    "ss_name":     "",
    "ss_location":  "",
    "ss_price":    "",
    "ss_type_idx": 0,
    "ss_features": "",
    "ss_contact":  "",
}
for _k, _v in _FIELD_DEFAULTS.items():
    if _k not in st.session_state:
        st.session_state[_k] = _v

# ---------------------------------------------------------------------------
# Sidebar – demo data loader
# ---------------------------------------------------------------------------
with st.sidebar:
    st.image(
        "https://img.icons8.com/fluency/96/real-estate.png",
        width=72,
    )
    st.markdown("### Quick Actions")
    if st.button("📋 Load Sample Data", width="stretch"):
        # Write sample values directly into session_state so every widget
        # picks them up on this same rerun (value= is ignored for already-
        # initialised widgets, so we must set session_state keys instead).
        st.session_state["ss_name"]     = SAMPLE_PROPERTY["name"]
        st.session_state["ss_location"]  = SAMPLE_PROPERTY["location"]
        st.session_state["ss_price"]    = SAMPLE_PROPERTY["price"]
        st.session_state["ss_features"] = SAMPLE_PROPERTY["features"]
        st.session_state["ss_contact"]  = SAMPLE_PROPERTY["contact"]
        _pt = SAMPLE_PROPERTY["property_type"]
        st.session_state["ss_type_idx"] = (
            PROPERTY_TYPES.index(_pt) if _pt in PROPERTY_TYPES else 0
        )
        st.toast("✅ Sample data loaded!", icon="📋")
    st.markdown("---")

    # Gemini status badge
    if GEMINI_API_KEY:
        st.markdown(
            f"🤖 **Gemini AI** enabled  "
            f"<br><small style='color:#aaa'>Model: `{GEMINI_MODEL}`</small>",
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            "📄 **Template captions** active  "
            "<br><small style='color:#aaa'>Set `GEMINI_API_KEY` in `.env` "
            "to enable AI captions</small>",
            unsafe_allow_html=True,
        )
    st.markdown("---")
    st.markdown(
        """
        **Phase 1** – Template captions ✅  
        **Phase 2** – AI captions (Gemini) ✅  
        **Phase 3** – Advanced effects  
        """
    )
    st.markdown("---")
    st.markdown(
        "<small style='color:#888'>Realty Assistant · Assignment Demo</small>",
        unsafe_allow_html=True,
    )

# ---------------------------------------------------------------------------
# Main layout – two columns
# ---------------------------------------------------------------------------
col_form, col_preview = st.columns([3, 2], gap="large")

with col_form:
    # ── Section 1: Property Details ──────────────────────────────────────
    st.markdown('<p class="section-title">🏢 Property Details</p>', unsafe_allow_html=True)

    # Each widget is bound to a session_state key ("ss_*").  We do NOT pass
    # value= here because Streamlit ignores it when the key is already in
    # session_state.  Instead, the Load Sample Data handler writes into
    # session_state directly, so values appear immediately on the next render.
    prop_name = st.text_input(
        "Property Name *",
        placeholder="e.g. Skyline Residency – Tower B",
        key="ss_name",
    )
    prop_location = st.text_input(
        "Location *",
        placeholder="e.g. Bandra West, Mumbai",
        key="ss_location",
    )

    col_price, col_type = st.columns(2)
    with col_price:
        prop_price = st.text_input(
            "Price *",
            placeholder="e.g. ₹2,85,00,000",
            key="ss_price",
        )
    with col_type:
        # Derive the current index from the stored value when available
        # (ss_type holds the selected string after first render; ss_type_idx
        # is only written by the Load Sample Data handler to set the initial
        # position on that specific rerun).
        _stored_type = st.session_state.get("ss_type", "")
        _type_idx = (
            PROPERTY_TYPES.index(_stored_type)
            if _stored_type in PROPERTY_TYPES
            else st.session_state["ss_type_idx"]
        )
        prop_type = st.selectbox(
            "Property Type *",
            options=PROPERTY_TYPES,
            index=_type_idx,
            key="ss_type",
        )

    prop_features = st.text_area(
        "Key Features",
        placeholder="Enter one feature per line…",
        height=130,
        key="ss_features",
        help="Optional but recommended. One feature per line.",
    )

    prop_contact = st.text_input(
        "Contact Information *",
        placeholder="e.g. agent@example.com | +91 98000 00000",
        key="ss_contact",
    )

    # ── Section 2: Image Upload ───────────────────────────────────────────
    st.markdown(
        f'<p class="section-title">📸 Property Photographs '
        f'<span class="badge">{MIN_IMAGES}–{MAX_IMAGES} images</span></p>',
        unsafe_allow_html=True,
    )

    uploaded_files = st.file_uploader(
        f"Upload {MIN_IMAGES}–{MAX_IMAGES} property photographs",
        type=["jpg", "jpeg", "png", "webp"],
        accept_multiple_files=True,
        key="img_upload",
        label_visibility="collapsed",
    )

    # Sample images note
    if not uploaded_files:
        st.caption(
            "💡 **Sample images** are not bundled with this project. "
            "Please upload 4–8 of your own JPEG/PNG property photos to test video generation."
        )

    if uploaded_files:
        count = len(uploaded_files)
        colour = "green" if MIN_IMAGES <= count <= MAX_IMAGES else "red"
        st.markdown(
            f"<small style='color:{colour}'>"
            f"<strong>{count}</strong> image(s) selected "
            f"(need {MIN_IMAGES}–{MAX_IMAGES})</small>",
            unsafe_allow_html=True,
        )

    # ── Generate button ───────────────────────────────────────────────────
    st.markdown("<br>", unsafe_allow_html=True)
    generate_clicked = st.button("🎬 Generate Video", width="stretch")

# ---------------------------------------------------------------------------
# Preview column – thumbnails
# ---------------------------------------------------------------------------
with col_preview:
    st.markdown('<p class="section-title">🖼️ Image Preview</p>', unsafe_allow_html=True)

    if uploaded_files:
        thumb_cols = st.columns(2)
        for i, f in enumerate(uploaded_files[:MAX_IMAGES]):
            with thumb_cols[i % 2]:
                st.image(f, caption=f"Slide {i + 1}", width="stretch")
    else:
        st.info("Uploaded images will appear here as thumbnails.", icon="🖼️")

# ---------------------------------------------------------------------------
# Validation & video generation
# ---------------------------------------------------------------------------
if generate_clicked:
    st.markdown("---")

    # Collect form data – read from session_state to guarantee we have the
    # latest values (widgets bound to ss_* keys update session_state in-place).
    property_details = {
        "name":          st.session_state.get("ss_name", "").strip(),
        "location":      st.session_state.get("ss_location", "").strip(),
        "price":         st.session_state.get("ss_price", "").strip(),
        "property_type": st.session_state.get("ss_type", PROPERTY_TYPES[0]),
        "features":      st.session_state.get("ss_features", "").strip(),
        "contact":       st.session_state.get("ss_contact", "").strip(),
    }

    form_errors = validate_property_details(property_details)
    image_errors = validate_all_images(uploaded_files or [])
    all_errors = form_errors + image_errors

    if all_errors:
        err_items = "".join(f"<li>{e}</li>" for e in all_errors)
        st.markdown(
            f'<div class="err-box">❌ <strong>Please fix the following:</strong>'
            f"<ul>{err_items}</ul></div>",
            unsafe_allow_html=True,
        )
    else:
        num_photos = len(uploaded_files)

        # ── Step 1: Generate captions ────────────────────────────────────
        with st.spinner("✍️ Generating captions…"):
            # Pass the uploaded files so Gemini can see the actual images
            # and assign each caption to the correct photo by index.
            captions, method = generate_captions(
                property_details, num_photos, uploaded_files=uploaded_files
            )
            # Rebuild SceneData for title/contact cards (always from templates)
            scene = generate_scene_data(property_details, num_photos)

        _METHOD_LABELS = {
            "gemini-images": ("🤖 Gemini AI (image-aware)",  "success"),
            "gemini-text":   ("🤖 Gemini AI (text-only)",    "warning"),
            "template":      ("📄 Template (factual)",        "success"),
        }
        method_label, msg_type = _METHOD_LABELS.get(
            method, (f"📄 {method}", "success")
        )
        if msg_type == "success":
            st.success(f"Captions generated using {method_label}.")
        else:
            note = (
                " Caption-to-photo alignment is not guaranteed in this mode."
                if method == "gemini-text"
                else ""
            )
            st.warning(f"Captions generated using {method_label}.{note}")

        # ── Step 2: Scene breakdown preview ─────────────────────────────
        est_secs = expected_duration(num_photos)
        est_min  = int(est_secs) // 60
        est_sec  = int(est_secs) % 60
        duration_str = (
            f"{est_min}m {est_sec:02d}s" if est_min else f"{est_secs:.0f}s"
        )

        with st.expander(
            f"🎬 Scene Breakdown  ·  {num_photos + 2} scenes  ·  ~{duration_str}",
            expanded=True,
        ):
            # Opening title row
            st.markdown(
                f"""
                | # | Scene | Text |
                |---|-------|------|
                | **0** | 🏠 **Opening Title** | {scene.title_line1} · *{scene.title_line2}* |
                """
            )
            # Photo rows
            rows = []
            for idx, cap in enumerate(captions, start=1):
                rows.append(f"| **{idx}** | 📷 Photo {idx} | {cap} |")
            # Contact row
            contact_preview = " · ".join(
                ln for ln in scene.contact_lines if ln.strip()
            )
            rows.append(
                f"| **{num_photos + 1}** | 📞 **Contact Card** | {contact_preview} |"
            )
            st.markdown("\n".join(rows))

        # ── Step 3: Render video ───────────────────────────────────
        with st.spinner(
            f"🎬 Rendering {num_photos + 2} scenes (~{duration_str}) – "
            "this may take 30–60 seconds…"
        ):
            ok, result = render_video(
                uploaded_files,
                captions,
                property_details=property_details,
            )

        if ok:
            st.success(
                f"✅ Video saved to `{result}`  ·  "
                f"Expected duration ~{duration_str}"
            )
            with open(result, "rb") as f:
                st.download_button(
                    "⬇️ Download MP4",
                    data=f,
                    file_name="property_video.mp4",
                    mime="video/mp4",
                    width="stretch",
                )
            st.video(result)
        else:
            st.error(f"❌ Video rendering failed: {result}")
            st.info(
                "Ensure **FFmpeg** is installed and available on your PATH.\n\n"
                "Ubuntu/Debian: `sudo apt install ffmpeg`\n\n"
                "Windows (winget): `winget install ffmpeg`"
            )
