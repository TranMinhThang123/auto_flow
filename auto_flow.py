"""
Auto Flow AI - Automate image upload and video generation on Google Labs Flow

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
FLOW_PROJECT_URL = "https://labs.google/fx/tools/flow/project/e7507ce7-6140-4e99-925f-d1a7c1baea0f"
DEFAULT_TIMEOUT  = 60_000
SIGN_IN_TIMEOUT  = 300_000
GEN_TIMEOUT      = 300_000

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
                page.wait_for_timeout(800)
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


# ─── step 1 & 2: upload images ─────────────────────────────────────────────────

def upload_media(page: Page, image_path: str, label: str):
    """Upload one image via the Add Media button → hidden file input."""
    abs_path = str(Path(image_path).resolve())

    add_btn = page.wait_for_selector(
        "button[aria-label='Add Media'], button[aria-label='Thêm nội dung nghe nhìn'], "
        "button:has-text('Add Media'), button:has-text('Thêm nội dung nghe nhìn')",
        state="visible", timeout=DEFAULT_TIMEOUT,
    )
    add_btn.click()
    page.wait_for_timeout(400)

    page.wait_for_selector("input[type='file']", state="attached", timeout=10_000)
    inputs = page.query_selector_all("input[type='file']")
    if not inputs:
        raise RuntimeError(f"No file input found for {label}.")
    inputs[0].set_input_files(abs_path)
    print(f"  Uploaded {label}: {abs_path}")
    page.wait_for_timeout(2500)


# ─── step 3: open settings panel ──────────────────────────────────────────────

def open_settings_panel(page: Page):
    """Click the Video/crop_9_16/x1 settings button.

    The button text varies ('Video', '🍌 Nano Banana 2', etc.) but it always
    contains an <i>crop_9_16</i> icon — that's the stable unique marker.
    Press Escape first to close any open menu.
    """
    page.keyboard.press("Escape")
    page.wait_for_timeout(400)

    btn = page.wait_for_selector(
        "button:has(i:has-text('crop_9_16'))",
        state="visible", timeout=DEFAULT_TIMEOUT,
    )
    btn.click()
    print("  Opened settings panel")
    page.wait_for_timeout(1000)


# ─── step 4: configure tabs ────────────────────────────────────────────────────

def _click_tab(page: Page, label: str, *selectors: str):
    """Try each selector; save a screenshot and raise if all fail."""
    for sel in selectors:
        try:
            el = page.wait_for_selector(sel, state="visible", timeout=8_000)
            el.click()
            print(f"  Selected tab: {label}")
            page.wait_for_timeout(600)
            return
        except Exception:
            continue
    shot = Path("debug_tab_fail.png")
    page.screenshot(path=str(shot), full_page=True)
    raise RuntimeError(
        f"Tab '{label}' not found. Screenshot: {shot.resolve()}\nTried: {selectors}"
    )


def select_video_tab(page: Page):
    _click_tab(
        page, "Video",
        # Stable: class flow_tab_slider_trigger + text Video (not Ingredients)
        ".flow_tab_slider_trigger:has-text('Video'):not(:has-text('Ingredients')):not(:has-text('Image'))",
        "[role='tab'].flow_tab_slider_trigger:has-text('Video')",
        "[role='tab'][aria-controls*='-VIDEO']:not([aria-controls*='REFERENCES'])",
        "[role='tab']:has(i:has-text('videocam'))",
    )


def select_ingredients_tab(page: Page):
    _click_tab(
        page, "Ingredients",
        ".flow_tab_slider_trigger:has-text('Ingredients')",
        "[role='tab'].flow_tab_slider_trigger:has-text('Ingredients')",
        "[role='tab'][aria-controls*='VIDEO_REFERENCES']",
        "[role='tab']:has(i:has-text('chrome_extension'))",
    )


def select_9_16_tab(page: Page):
    _click_tab(
        page, "9:16",
        ".flow_tab_slider_trigger:has-text('9:16')",
        "[role='tab'].flow_tab_slider_trigger:has-text('9:16')",
        "[role='tab'][aria-controls*='PORTRAIT']",
        "[role='tab']:has(i:has-text('crop_9_16'))",
    )


def select_x1_tab(page: Page):
    _click_tab(
        page, "x1",
        ".flow_tab_slider_trigger:has-text('x1')",
        "[role='tab'].flow_tab_slider_trigger:has-text('x1')",
        "[role='tab'][aria-controls*='-1']",
    )


# ─── step 5: add images as ingredients ────────────────────────────────────────

def _pick_ingredient(page: Page, n: int):
    """Open the '+' picker and select the first available thumbnail."""
    plus_btn = page.wait_for_selector(
        "button[aria-haspopup='dialog']:has(i:has-text('add_2'))",
        state="visible", timeout=10_000,
    )
    plus_btn.click()
    print(f"  Clicked + button (ingredient {n})")

    page.wait_for_selector(
        "[role='dialog'], [data-state='open']",
        state="visible", timeout=10_000,
    )
    page.wait_for_timeout(800)

    thumb_sel = (
        "[role='dialog'] img, [data-state='open'] img, "
        "[role='dialog'] [role='option'], [role='dialog'] [role='checkbox']"
    )
    thumbs = [t for t in page.query_selector_all(thumb_sel) if t.is_visible()]
    if not thumbs:
        raise RuntimeError(f"No thumbnails in picker for ingredient {n}.")

    thumbs[0].scroll_into_view_if_needed()
    thumbs[0].click()
    print(f"  Selected ingredient {n}")
    page.wait_for_timeout(600)

    # Close dialog if still open
    for confirm_sel in [
        "button:has-text('Done')", "button:has-text('Xong')",
        "button:has-text('Confirm')", "button:has-text('Thêm')",
        "[role='dialog'] button[type='submit']",
    ]:
        el = page.query_selector(confirm_sel)
        if el and el.is_visible():
            el.click()
            page.wait_for_timeout(400)
            return


def add_ingredients(page: Page, count: int = 2):
    """Click '+' once per ingredient — the dialog closes after each selection."""
    for i in range(1, count + 1):
        _pick_ingredient(page, i)
        page.wait_for_timeout(500)


# ─── step 6: prompt ────────────────────────────────────────────────────────────

def enter_prompt(page: Page, prompt: str):
    for sel in ["textarea", "[contenteditable='true']",
                "[placeholder*='prompt' i]", "[placeholder*='mô tả' i]",
                "[aria-label*='prompt' i]"]:
        el = page.query_selector(sel)
        if not el:
            continue
        try:
            el.scroll_into_view_if_needed()
            el.fill(prompt)
            print("  Prompt entered")
            return
        except Exception:
            try:
                el.evaluate(
                    f"e => {{ e.value = {repr(prompt)}; "
                    "e.dispatchEvent(new Event('input', {bubbles:true})); }}"
                )
                print("  Prompt entered (via JS)")
                return
            except Exception:
                continue
    print("  Warning: prompt field not found.")


# ─── step 7: generate ──────────────────────────────────────────────────────────

def click_generate(page: Page):
    el = page.wait_for_selector(
        "button:has(i:has-text('arrow_forward'))",
        state="visible", timeout=DEFAULT_TIMEOUT,
    )
    el.click()
    print("  Generate clicked")


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
    page.screenshot(path=str(shot), full_page=True)
    print(f"\n[DEBUG] Screenshot: {shot.resolve()}")
    els = page.query_selector_all(
        "button, [role='button'], [role='tab'], [role='menuitem']"
    )
    visible = [e for e in els if e.is_visible()]
    print(f"  Visible interactive elements: {len(visible)}")
    for i, e in enumerate(visible):
        try:
            txt = e.evaluate(
                "e => [e.tagName, e.getAttribute('role'), e.getAttribute('aria-controls'),"
                " (e.innerText||'').slice(0,60)].filter(Boolean).join(' | ')"
            )
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
        page.goto(FLOW_ABOUT_URL, wait_until="domcontentloaded", timeout=DEFAULT_TIMEOUT)
        page.wait_for_timeout(2000)
        try:
            el = page.wait_for_selector(
                "a:has-text('Create with Flow'), button:has-text('Create with Flow')",
                timeout=DEFAULT_TIMEOUT, state="visible",
            )
            el.click()
        except Exception:
            print("  'Create with Flow' not found — click it manually.")
        page.wait_for_timeout(1500)
        _accept_tos(page)
        print("Please sign in to Google in the browser window...")
        try:
            page.wait_for_url("**/tools/flow**", timeout=SIGN_IN_TIMEOUT)
            print("\nLogin complete! Session saved.")
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
        open_settings_panel(page)

        if debug:
            debug_page(page, "after_settings")

        print("[6] Configuring: Video → Ingredients → 9:16 → x1...")
        select_video_tab(page)
        select_ingredients_tab(page)
        select_9_16_tab(page)
        select_x1_tab(page)

        print("[7] Adding images as ingredients...")
        add_ingredients(page, count=2)

        print("[8] Entering prompt...")
        enter_prompt(page, prompt)
        page.wait_for_timeout(500)

        print("[9] Generating video...")
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
        description="Upload images to Google Labs Flow and generate a video"
    )
    parser.add_argument("--login",    action="store_true",
                        help="One-time Google sign-in (saves session)")
    parser.add_argument("--begin",   help="Path to the BEGIN (start) frame image")
    parser.add_argument("--end",     help="Path to the END (finish) frame image")
    parser.add_argument("--prompt",  default="",
                        help="Text prompt for video generation")
    parser.add_argument("--headless", action="store_true",
                        help="Run without a visible browser window")
    parser.add_argument("--debug",   action="store_true",
                        help="Save screenshots and dump elements for debugging")
    args = parser.parse_args()

    if args.login:
        login()
    else:
        if not args.begin or not args.end:
            parser.error("--begin and --end are required (or use --login for first-time setup)")
        if not args.prompt:
            parser.error("--prompt is required")
        run(args.begin, args.end, args.prompt, args.headless, args.debug)


if __name__ == "__main__":
    main()
