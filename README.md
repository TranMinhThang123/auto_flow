# Auto Flow AI

Automate image upload and AI video generation on [Google Labs Flow](https://labs.google/flow/about) using Playwright browser automation.

## What it does

Given two images (a start frame and an end frame) and a text prompt, the script will:

1. Open a persistent browser session (login saved — no re-login needed after first run)
2. Navigate to your Flow project
3. Upload both images to the project media library
4. Open the generation settings panel and configure: **Video** → **Ingredients** → **9:16** → **x1**
5. Add both uploaded images as model ingredients
6. Enter the text prompt
7. Click **Generate** and wait for the video to complete

---

## Requirements

- Python 3.9+
- A Google account with access to [Google Labs Flow](https://labs.google/flow/about)

---

## Installation

### 1. Create and activate a virtual environment (recommended)

```bash
python -m venv venv
source venv/bin/activate        # Linux / macOS
venv\Scripts\activate           # Windows
```

### 2. Install dependencies

```bash
pip install playwright
playwright install chromium
```

---

## First-time setup — Google login

The script stores your browser session in a local `.browser_profile/` folder so you only need to sign in **once**.

```bash
python auto_flow.py --login
```

A browser window will open. Complete these steps manually:

1. Click **"Create with Flow"** on the landing page (or it clicks automatically)
2. Accept the Terms of Service popup if it appears
3. Sign in to your Google account
4. Wait for the Flow editor to load

Once the editor loads, close or let the script close the browser — your session is saved. All future runs will be fully automated without any login prompt.

---

## Usage

### Basic

```bash
python auto_flow.py --begin start.jpg --end end.jpg --prompt "smooth camera zoom in"
```

### With all options

```bash
python auto_flow.py \
  --begin  path/to/start_frame.jpg \
  --end    path/to/end_frame.jpg \
  --prompt "slow dolly zoom, cinematic lighting" \
  --headless \
  --debug
```

### Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `--begin` | Yes | Path to the **start** frame image |
| `--end` | Yes | Path to the **end** frame image |
| `--prompt` | Yes | Text prompt describing the video to generate |
| `--headless` | No | Run without opening a visible browser window |
| `--debug` | No | Save screenshots and print page elements at key steps |
| `--login` | No | First-time setup: open browser for Google sign-in |

---

## Automation flow (step by step)

| Step | Action |
|------|--------|
| 1 | Launch Chromium with persistent profile (`.browser_profile/`) |
| 2 | Navigate to the Flow project URL |
| 3 | Upload **begin** image via the Add Media button |
| 4 | Upload **end** image via the Add Media button |
| 5 | Click the generation settings button (`crop_9_16` icon) |
| 6 | Select **Video** tab → **Ingredients** tab → **9:16** tab → **x1** tab |
| 7 | Click `+` twice to add both uploaded images as model ingredients |
| 8 | Fill in the text prompt |
| 9 | Click the **Generate** (arrow forward) button |
| 10 | Wait up to 5 minutes for the video to be ready |

---

## Project structure

```
auto_flow_ai/
├── auto_flow.py          # Main automation script
├── requirements.txt      # Python dependencies
├── .browser_profile/     # Saved browser session (auto-created, do not delete)
└── README.md
```

---

## Troubleshooting

### Login required on every run
The `.browser_profile/` folder stores your session. Make sure it is not deleted between runs. If your session expires, run `--login` again.

### Upload shows "Failed"
- Check that the image file exists and is a supported format (JPEG, PNG, WEBP)
- Try running without `--headless` to watch what happens in the browser

### Tab or button not found
Run with `--debug` to save screenshots at each step:
```bash
python auto_flow.py --begin img1.jpg --end img2.jpg --prompt "test" --debug
```
Screenshots are saved as `debug_after_open.png`, `debug_after_upload.png`, `debug_after_settings.png`, and `debug_tab_fail.png`.

### Google sign-in page appears mid-run
Your session expired. Run `python auto_flow.py --login` to refresh it.

### Video generation times out
Flow can take several minutes depending on server load. The default timeout is **5 minutes**. If it consistently times out, check the Flow website manually.

---

## Notes

- The script targets a specific project URL defined in `FLOW_PROJECT_URL` inside `auto_flow.py`. Update this constant if you want to use a different project.
- Generation settings are fixed to: **Video mode**, **Ingredients reference**, **9:16 aspect ratio**, **x1 scale**. Modify the `select_*` functions in the script to change these defaults.
- The browser stays open for **60 seconds** after generation (in headed mode) so you can review or download the video manually.
