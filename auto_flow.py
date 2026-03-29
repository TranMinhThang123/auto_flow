"""
Auto Flow AI - Automate begin/end image upload and video generation on Google Labs Flow

First-time setup (login once, session saved forever):
    python auto_flow.py --login

Normal usage:
    python auto_flow.py --begin start.jpg --end end.jpg --prompt "smooth pan"
    python auto_flow.py --begin start.jpg --end end.jpg --prompt "zoom in" --headless
"""

import argparse
import sys
import time
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright, Page
except ImportError:
    print("Playwright not installed. Run: pip install playwright && playwright install chromium")
    sys.exit(1)


FLOW_ABOUT_URL   = "https://labs.google/flow/about"
FLOW_PROJECT_URL = "https://labs.google/fx/tools/flow/project/87eb7f9c-c354-4d1a-8f40-7708de1466a6"
DEFAULT_TIMEOUT  = 60_000   # 60 s
SIGN_IN_TIMEOUT  = 300_000  # 5 min for manual sign-in
GEN_TIMEOUT      = 300_000  # 5 min for video generation

PROFILE_DIR = Path(__file__).parent / ".browser_profile"


# ─── browser helpers ───────────────────────────────────────────────────────────

def _launch_context(p, headless: bool):
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    return p.chromium.launch_persistent_context(
        user_data_dir=str(PROFILE_DIR),
        headless=headless,
        viewport={"width": 1280, "height": 900},
        user_agent=(
            "Mozilla/5.0 (X11; Linux x86_64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
    )


def _click(page: Page, selector: str, label: str, timeout: int = DEFAULT_TIMEOUT):
    """Wait for a visible element then click it."""
    el = page.wait_for_selector(selector, state="visible", timeout=timeout)
    el.click()
    print(f"  Clicked: {label}")
    page.wait_for_timeout(800)


def _accept_tos(page: Page):
    for sel in [
        "button:has-text('I agree')", "button:has-text('Đồng ý')",
        "button:has-text('Accept')",  "button:has-text('Chấp nhận')",
        "button:has-text('Continue')", "button:has-text('Agree')",
    ]:
        try:
            el = page.wait_for_selector(sel, timeout=3000, state="visible")
            if el:
                el.click()
                print(f"  Accepted ToS ({sel})")
                page.wait_for_timeout(1000)
                return
        except Exception:
            pass


def _ensure_signed_in(page: Page):
    if "accounts.google.com" in page.url or page.query_selector("text=Sign in"):
        print("\n  *** Google sign-in required — please sign in in the browser ***")
        print("  Tip: run  python auto_flow.py --login  once to save your session.")
        page.wait_for_url("**/tools/flow**", timeout=SIGN_IN_TIMEOUT)
        page.wait_for_timeout(2000)
        print("  Signed in.\n")


def _open_editor(page: Page):
    print(f"  Navigating to: {FLOW_PROJECT_URL}")
    page.goto(FLOW_PROJECT_URL, wait_until="domcontentloaded", timeout=DEFAULT_TIMEOUT)
    page.wait_for_timeout(2000)
    _ensure_signed_in(page)
    _accept_tos(page)
    page.wait_for_timeout(1500)
    print("  Editor loaded.")


# ─── step functions ────────────────────────────────────────────────────────────

def upload_media(page: Page, image_path: str, label: str):
    """
    Upload a single image to the project media library via the
    'Thêm nội dung nghe nhìn' (Add media) button.
    Does NOT interact with Start/End frame slots.
    """
    abs_path = str(Path(image_path).resolve())

    # The button's inner text is "add\nThêm nội dung nghe nhìn" (icon + hidden span)
    # Use :has-text() which matches against innerText content
    add_sel = (
        "button:has-text('Thêm nội dung nghe nhìn'), "
        "button:has-text('Add media')"
    )
    _click(page, add_sel, f"Add media ({label})")
    page.wait_for_timeout(400)

    # Inject the file into the hidden input
    page.wait_for_selector("input[type='file']", state="attached", timeout=10_000)
    inputs = page.query_selector_all("input[type='file']")
    if not inputs:
        raise RuntimeError(f"No file input found for {label}.")
    inputs[0].set_input_files(abs_path)
    print(f"  Uploaded {label}: {abs_path}")
    # Wait for the thumbnail to appear before moving to next upload
    page.wait_for_timeout(2500)


def click_settings_button(page: Page):
    """
    Click the 'Video / crop_9_16 / x1' button that opens the generation settings panel.
    Identified by: button[aria-haspopup='menu'] containing 'Video' text.
    """
    _click(
        page,
        "button[aria-haspopup='menu']:has-text('Video')",
        "settings button (Video / crop_9_16 / x1)",
    )


def select_video_tab(page: Page):
    """Click the 'Video' generation-type tab (role=tab, controls *-VIDEO)."""
    # aria-controls ends with '-VIDEO' (not '-VIDEO_REFERENCES')
    _click(
        page,
        "[role='tab'][aria-controls$='-VIDEO']",
        "Video tab",
    )


def select_ingredients_tab(page: Page):
    """Click the 'Ingredients' reference tab (controls *-VIDEO_REFERENCES)."""
    _click(
        page,
        "[role='tab'][aria-controls$='-VIDEO_REFERENCES']",
        "Ingredients tab",
    )


def select_ratio_9_16(page: Page):
    """Click the 9:16 aspect-ratio tab (controls *-PORTRAIT)."""
    _click(
        page,
        "[role='tab'][aria-controls$='-PORTRAIT']",
        "9:16 ratio tab",
    )


def select_x1_scale(page: Page):
    """Click the x1 scale tab."""
    _click(
        page,
        "[role='tab']:has-text('x1')",
        "x1 scale tab",
    )


def enter_prompt(page: Page, prompt: str):
    """Fill the prompt textarea."""
    for sel in [
        "textarea",
        "[contenteditable='true']",
        "[placeholder*='prompt' i]",
        "[placeholder*='mô tả' i]",
        "[aria-label*='prompt' i]",
    ]:
        el = page.query_selector(sel)
        if el and el.is_visible():
            el.click()
            el.fill(prompt)
            print(f"  Prompt entered")
            return
    print("  Warning: prompt field not found.")


def click_generate(page: Page):
    """Click the arrow_forward generate button."""
    _click(
        page,
        "button:has(i:has-text('arrow_forward'))",
        "Generate (arrow_forward)",
    )


def wait_for_video(page: Page) -> str:
    print("  Waiting for video (up to 5 min)...")
    deadline = time.time() + GEN_TIMEOUT / 1000
    while time.time() < deadline:
        for sel in ["video", "a[href*='.mp4']", "a[download]",
                    "button:has-text('Download')", "button:has-text('Tải xuống')"]:
            el = page.query_selector(sel)
            if el and el.is_visible():
                print("  Video ready!")
                tag = el.evaluate("e => e.tagName.toLowerCase()")
                if tag == "video":
                    return el.get_attribute("src") or "VIDEO_ELEMENT_VISIBLE"
                if tag == "a":
                    return el.get_attribute("href") or "DOWNLOAD_LINK_VISIBLE"
                return "VIDEO_READY"
        time.sleep(3)
    raise RuntimeError("Video generation timed out after 5 minutes.")


# ─── debug helper ──────────────────────────────────────────────────────────────

def debug_page(page: Page, label: str = "screenshot"):
    shot = Path(f"debug_{label}.png")
    page.screenshot(path=str(shot))
    print(f"\n[DEBUG] Screenshot: {shot.resolve()}")
    buttons = [b for b in page.query_selector_all("button, [role='button'], [role='tab']") if b.is_visible()]
    print(f"  Visible buttons/tabs: {len(buttons)}")
    for i, b in enumerate(buttons):
        try:
            txt = b.evaluate("e => (e.innerText||e.getAttribute('aria-label')||'').slice(0,80).trim()")
            print(f"    [{i}] {txt}")
        except Exception:
            pass


# ─── login helper ──────────────────────────────────────────────────────────────

def login():
    print("\n=== First-time Login Setup ===")
    print(f"Profile: {PROFILE_DIR}\n")
    with sync_playwright() as p:
        context = _launch_context(p, headless=False)
        page = context.new_page()
        print("[1] Opening labs.google/flow/about ...")
        page.goto(FLOW_ABOUT_URL, wait_until="domcontentloaded", timeout=DEFAULT_TIMEOUT)
        page.wait_for_timeout(2000)
        print("[2] Click 'Create with Flow' in the browser (or it may click automatically)...")
        try:
            el = page.wait_for_selector(
                "a:has-text('Create with Flow'), button:has-text('Create with Flow')",
                timeout=DEFAULT_TIMEOUT, state="visible",
            )
            el.click()
        except Exception:
            print("  Button not found — please click it manually.")
        page.wait_for_timeout(1500)
        _accept_tos(page)
        print("[3] Please sign in to Google in the browser window...")
        try:
            page.wait_for_url("**/tools/flow**", timeout=SIGN_IN_TIMEOUT)
            print("\nLogin complete! Session saved.")
            print("Run: python auto_flow.py --begin img1.jpg --end img2.jpg --prompt 'your prompt'")
        except Exception:
            print("\nTimed out. Session saved as-is.")
        finally:
            context.close()


# ─── main run ──────────────────────────────────────────────────────────────────

def run(begin_image: str, end_image: str, prompt: str,
        headless: bool = False, debug: bool = False):

    for path, lbl in [(begin_image, "begin"), (end_image, "end")]:
        if not Path(path).exists():
            print(f"Error: {lbl} image not found: {path}")
            sys.exit(1)

    print("\n=== Auto Flow AI ===")
    print(f"Begin  : {begin_image}")
    print(f"End    : {end_image}")
    print(f"Prompt : {prompt}")
    print(f"Profile: {PROFILE_DIR}")
    print(f"Mode   : {'headless' if headless else 'headed'}")
    print("=" * 40)

    with sync_playwright() as p:
        print("\n[1] Launching browser...")
        context = _launch_context(p, headless=headless)
        page = context.new_page()

        print("[2] Opening Flow editor...")
        _open_editor(page)

        if debug:
            debug_page(page, "after_open")

        print("[3] Uploading BEGIN image...")
        upload_media(page, begin_image, "begin")

        print("[4] Uploading END image...")
        upload_media(page, end_image, "end")

        if debug:
            debug_page(page, "after_upload")

        print("[5] Opening settings panel...")
        click_settings_button(page)

        print("[6] Configuring generation settings...")
        select_video_tab(page)
        select_ingredients_tab(page)
        select_ratio_9_16(page)
        select_x1_scale(page)

        print("[7] Entering prompt...")
        enter_prompt(page, prompt)
        page.wait_for_timeout(500)

        print("[8] Generating video...")
        click_generate(page)
        page.wait_for_timeout(2000)

        video_url = wait_for_video(page)
        print(f"\n Result: {video_url}")

        if not headless:
            print("Browser stays open for 60 s — download the video if needed.")
            page.wait_for_timeout(60_000)

        context.close()
        print("Done!")
        return video_url


def main():
    parser = argparse.ArgumentParser(
        description="Upload begin/end images to Google Labs Flow and generate a video"
    )
    parser.add_argument("--login",    action="store_true",
                        help="One-time Google sign-in (saves session)")
    parser.add_argument("--begin",   help="Path to the BEGIN (start) frame image")
    parser.add_argument("--end",     help="Path to the END (finish) frame image")
    parser.add_argument("--prompt",  required=False, default="",
                        help="Text prompt for video generation (required by Flow)")
    parser.add_argument("--headless", action="store_true",
                        help="Run without a visible browser window")
    parser.add_argument("--debug",   action="store_true",
                        help="Save screenshots and dump page elements for debugging")
    args = parser.parse_args()

    if args.login:
        login()
    else:
        if not args.begin or not args.end:
            parser.error("--begin and --end are required (or use --login for first-time setup)")
        if not args.prompt:
            parser.error("--prompt is required (Google Flow needs a text prompt to generate video)")
        run(args.begin, args.end, args.prompt, args.headless, args.debug)


if __name__ == "__main__":
    main()
