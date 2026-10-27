# 🏡 AI Property Video Generator

> **Realty Assistant – Recruitment Assignment**  
> A Python + Streamlit web application that accepts property details and 4–8 photographs, generates promotional captions, and exports a short MP4 video.

---

## Table of Contents

1. [Project Structure](#project-structure)  
2. [Prerequisites](#prerequisites)  
3. [Quick Setup – Linux / macOS](#quick-setup--linux--macos)  
4. [Quick Setup – Windows PowerShell](#quick-setup--windows-powershell)  
5. [Running the App](#running-the-app)  
6. [Environment Variables](#environment-variables)  
7. [Development Phases](#development-phases)  
8. [Testing Checklist](#testing-checklist)  
9. [Troubleshooting](#troubleshooting)

---

## Project Structure

```
ai-property-video-generator/
│
├── app.py               # Streamlit entry-point – UI layout, routing, orchestration
├── config.py            # All constants & env-var loading (single source of truth)
├── validators.py        # Pure validation helpers (image count, file type, form fields)
├── captions.py          # Caption generation – template fallback + Phase 2 Gemini hook
├── video_generator.py   # MoviePy / Pillow video-rendering pipeline
├── sample_data.py       # Synthetic demo property data
│
├── requirements.txt     # Python dependencies
├── .env.example         # Template for environment variables (copy → .env)
├── .gitignore           # Excludes .env, output/, venv/, etc.
└── README.md            # This file
```

---

## Prerequisites

| Tool | Minimum version | Install guide |
|------|----------------|---------------|
| Python | 3.11 | [python.org](https://www.python.org/downloads/) |
| FFmpeg | 6.x | See below |
| Git | any | [git-scm.com](https://git-scm.com/) |

### Installing FFmpeg

**Ubuntu / Debian**
```bash
sudo apt update && sudo apt install -y ffmpeg
ffmpeg -version
```

**macOS (Homebrew)**
```bash
brew install ffmpeg
```

**Windows (winget)**
```powershell
winget install -e --id Gyan.FFmpeg
# Restart your terminal after installation
ffmpeg -version
```

---

## Quick Setup – Linux / macOS

```bash
# 1. Clone the repository
git clone <repo-url> ai-property-video-generator
cd ai-property-video-generator

# 2. Create and activate a virtual environment
python3.11 -m venv .venv
source .venv/bin/activate

# 3. Install dependencies
pip install --upgrade pip
pip install -r requirements.txt

# 4. Copy the environment template (no key needed for Phase 1)
cp .env.example .env

# 5. Launch the app
streamlit run app.py
```

---

## Quick Setup – Windows PowerShell

```powershell
# 1. Clone the repository
git clone <repo-url> ai-property-video-generator
Set-Location ai-property-video-generator

# 2. Create a virtual environment
py -3.11 -m venv .venv

# 3. Activate it (run once per terminal session)
.venv\Scripts\Activate.ps1

# If you see an "execution policy" error, run first:
# Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser

# 4. Install dependencies
python -m pip install --upgrade pip
pip install -r requirements.txt

# 5. Copy the environment template
Copy-Item .env.example .env

# 6. Launch the app
streamlit run app.py
```

> **Tip:** Streamlit opens automatically at `http://localhost:8501`.  
> Stop it with `Ctrl + C`.

---

## Running the App

```bash
streamlit run app.py
```

Use the **"Load Sample Data"** button in the sidebar to pre-fill the form, then upload 4–8 photographs and click **Generate Video**.

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `GEMINI_API_KEY` | Phase 2 only | Gemini API key for AI-generated captions |

Copy `.env.example` → `.env` and fill in values.  
**Never commit `.env` to version control.**

---

## Development Phases

| Phase | Status | Description |
|-------|--------|-------------|
| **1** | ✅ Complete | Project setup, Streamlit UI, form validation, template captions, video rendering |
| **2** | 🔜 Planned | Gemini API integration for AI-generated captions |
| **3** | 🔜 Planned | Advanced video effects, music, branding overlays |

---

## Testing Checklist (Phase 1)

- [ ] App loads at `http://localhost:8501` without errors
- [ ] **Load Sample Data** pre-fills all fields
- [ ] Submitting with fewer than 4 images shows a validation error
- [ ] Submitting with more than 8 images shows a validation error
- [ ] Uploading a non-image file (e.g. `.txt`) shows a validation error
- [ ] Empty required fields show per-field validation errors
- [ ] Valid submission (4–8 images + all fields) triggers caption + video generation
- [ ] Generated MP4 is saved in `output/` and offered for download
- [ ] No API key is required in Phase 1

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| `ModuleNotFoundError: moviepy` | Dependencies not installed | Run `pip install -r requirements.txt` |
| `FileNotFoundError: ffmpeg` | FFmpeg not on PATH | Install FFmpeg (see Prerequisites) |
| `OSError: cannot open resource` for font | DejaVu font missing | Install `fonts-dejavu` or system will use default |
| Execution policy error (Windows) | PowerShell restriction | `Set-ExecutionPolicy RemoteSigned -Scope CurrentUser` |
| Video renders but is blank | Corrupt image file | Try replacing the problematic image |
