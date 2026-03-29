"""
Auto Flow AI - Automate begin/end image upload and video generation on Google Labs Flow

First-time setup (login once, session saved forever):
    python auto_flow.py --login

Normal usage:
    python auto_flow.py --begin start.jpg --end end.jpg
    python auto_flow.py --begin start.jpg --end end.jpg --prompt "smooth pan"
    python auto_flow.py --begin start.jpg --end end.jpg --headless
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
FLOW_PROJECT_URL = "https://labs.google/fx/vi/tools/flow/project/f0c44c0c-8cde-4d6a-bcb0-7099821065ab"
DEFAULT_TIMEOUT = 60_000   # 60 s
SIGN_IN_TIMEOUT = 300_000  # 5 min for manual sign-in
GEN_TIMEOUT     = 300_000  # 5 min for video generation

# Persistent profile dir — login cookies are saved here so you only sign in once
PROFILE_DIR = Path(__file__).parent / ".browser_profile"

# ─── helpers ──────────────────────────────────────────────────────────────────

def dismiss_dialogs(page: Page):
    """Dismiss cookie consent or any blocking overlay."""
    for sel in [
        "button:has-text('Accept all')",
        "button:has-text('Chấp nhận tất cả')",
        "button:has-text('I agree')",
        "button:has-text('Đồng ý')",
        "button:has-text('Got it')",
    ]:
        try:
            el = page.query_selector(sel)
            if el and el.is_visible():
                el.click()
                print(f"  Dismissed dialog: {sel}")
                page.wait_for_timeout(800)
        except Exception:
            pass


def ensure_signed_in(page: Page):
    """Pause and wait for the user to sign in if redirected to Google login."""
    if "accounts.google.com" in page.url or page.query_selector("text=Sign in"):
        print("\n  *** Google sign-in required ***")
        print("  Please sign in manually in the browser window.")
        print("  Tip: run  python auto_flow.py --login  once to save your session.")
        print("  Waiting up to 5 minutes for you to complete sign-in...")
        page.wait_for_url("**/tools/flow**", timeout=SIGN_IN_TIMEOUT)
        page.wait_for_timeout(2000)
        print("  Signed in — continuing.\n")


def _get_file_inputs(page: Page):
    """Return all file inputs on the page, including hidden ones."""
    return page.query_selector_all("input[type='file']")


def upload_begin_image(page: Page, image_path: str):
    """Upload the BEGIN (start) frame.

    The file input is always hidden — use state='attached', not 'visible'.
    Click 'Thêm nội dung nghe nhìn' (Add media) to activate the slot first,
    then set files directly on the hidden input.
    """
    abs_path = str(Path(image_path).resolve())

    # Click the "Add media" button to activate the begin upload slot
    for sel in [
        "button[aria-label='Thêm nội dung nghe nhìn']",
        "button[aria-label*='media' i]",
        "button[aria-label*='Add' i]",
    ]:
        el = page.query_selector(sel)
        if el and el.is_visible():
            el.click()
            print(f"  Clicked add-media button ({sel})")
            page.wait_for_timeout(500)
            break

    # Wait for the hidden input to exist in the DOM (not visible — always hidden)
    page.wait_for_selector("input[type='file']", state="attached", timeout=DEFAULT_TIMEOUT)

    inputs = _get_file_inputs(page)
    if not inputs:
        raise RuntimeError("No file inputs found on the page.")

    inputs[0].set_input_files(abs_path)
    print(f"  Uploaded begin image: {abs_path}")
    page.wait_for_timeout(2000)



def upload_end_image(page: Page, image_path: str):
    """Upload the END (finish) frame.

    Button [9] 'add_2 / Tạo' activates the end frame slot.
    Then set_input_files injects the file into the shared hidden input.
    """
    abs_path = str(Path(image_path).resolve())

    # Click the "add_2 / Tạo" button — this is the end-frame add button
    clicked = False
    for sel in [
        "button[aria-label='Tạo']",
        "button[aria-label*='Tạo' i]",
        "button[aria-label*='create' i]",
        "button[aria-label*='add' i]",
    ]:
        els = page.query_selector_all(sel)
        # Pick the one that is NOT the generate (arrow_forward) button
        for el in els:
            if el.is_visible():
                label = el.get_attribute("aria-label") or ""
                icon  = el.inner_text() or ""
                # Skip the generate/forward button
                if "arrow_forward" in icon or "arrow_forward" in label:
                    continue
                el.click()
                print(f"  Clicked end-frame button ({sel}: '{label}')")
                page.wait_for_timeout(500)
                clicked = True
                break
        if clicked:
            break

    if not clicked:
        print("  Warning: end-frame button not found, trying direct input set...")

    inputs = _get_file_inputs(page)
    if not inputs:
        raise RuntimeError("No file inputs found after clicking end-frame button.")

    inputs[-1].set_input_files(abs_path)
    print(f"  Uploaded end image: {abs_path}")
    page.wait_for_timeout(2000)


def enter_prompt(page: Page, prompt: str):
    """Type the optional text prompt into the prompt field."""
    for sel in [
        "textarea",
        "[contenteditable='true']",
        "input[type='text'][placeholder*='prompt' i]",
        "input[type='text'][placeholder*='describe' i]",
        "[aria-label*='prompt' i]",
        "[placeholder*='mô tả' i]",
    ]:
        try:
            el = page.query_selector(sel)
            if el and el.is_visible():
                el.click()
                el.fill(prompt)
                print(f"  Prompt entered ({sel})")
                return
        except Exception:
            pass
    print("  Warning: prompt field not found — skipping.")


def click_generate(page: Page):
    """Click the generate button — button[11] 'arrow_forward - Tạo'."""
    # Find all visible buttons, pick the one with arrow_forward icon
    buttons = page.query_selector_all("button, [role='button']")
    for el in buttons:
        if not el.is_visible():
            continue
        try:
            text = el.inner_text()
            label = el.get_attribute("aria-label") or ""
            if "arrow_forward" in text or "arrow_forward" in label:
                el.click()
                print(f"  Generate clicked (arrow_forward button)")
                return
        except Exception:
            pass

    # Fallback to text-based selectors
    for sel in [
        "button[aria-label='Tạo']:has-text('arrow_forward')",
        "button:has-text('Generate')",
        "button:has-text('Tạo video')",
        "[data-testid*='generate']",
        "button[type='submit']",
    ]:
        el = page.query_selector(sel)
        if el and el.is_visible() and el.is_enabled():
            el.click()
            print(f"  Generate clicked ({sel})")
            return

    raise RuntimeError("Could not find the Generate button.")


def wait_for_video(page: Page) -> str:
    """Poll until a video element or download link appears, then return its URL."""
    print("  Waiting for video (up to 5 min)...")
    deadline = time.time() + GEN_TIMEOUT / 1000
    while time.time() < deadline:
        for sel in ["video", "a[href*='.mp4']", "a[download]",
                    "button:has-text('Download')", "button:has-text('Tải xuống')",
                    "[data-testid*='video']", "[class*='video-result']"]:
            el = page.query_selector(sel)
            if el and el.is_visible():
                print("  Video ready!")
                tag = el.evaluate("e => e.tagName.toLowerCase()")
                if tag == "video":
                    src = el.get_attribute("src") or el.get_attribute("data-src")
                    return src or "VIDEO_ELEMENT_VISIBLE"
                if tag == "a":
                    return el.get_attribute("href") or "DOWNLOAD_LINK_VISIBLE"
                return "VIDEO_READY"
        time.sleep(3)
    raise RuntimeError("Video generation timed out after 5 minutes.")


# ─── browser context (persistent profile) ────────────────────────────────────

def _launch_context(p, headless: bool):
    """
    Launch a persistent browser context that saves cookies/session to PROFILE_DIR.
    This means you only need to sign in once — subsequent runs reuse the session.
    """
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    context = p.chromium.launch_persistent_context(
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
    return context


# ─── login helper ─────────────────────────────────────────────────────────────

def login():
    """
    Walk through the full first-time flow:
      1. Open labs.google/flow/about
      2. Click "Create with Flow"
      3. Accept ToS popup
      4. Sign in to Google account
    Session is saved in PROFILE_DIR — no login needed on future runs.
    """
    print("\n=== First-time Login Setup ===")
    print(f"Profile will be saved to: {PROFILE_DIR}")
    print("Follow the steps in the browser window that opens.\n")

    with sync_playwright() as p:
        context = _launch_context(p, headless=False)
        page = context.new_page()

        # Step 1: go to the about/landing page
        print("[1] Opening labs.google/flow/about ...")
        page.goto(FLOW_ABOUT_URL, wait_until="domcontentloaded", timeout=DEFAULT_TIMEOUT)
        page.wait_for_timeout(2000)

        # Step 2: wait for and click "Create with Flow" button
        print("[2] Waiting for 'Create with Flow' button...")
        try:
            el = page.wait_for_selector(
                "a:has-text('Create with Flow'), button:has-text('Create with Flow')",
                timeout=DEFAULT_TIMEOUT,
                state="visible",
            )
            el.click()
            print("  Clicked 'Create with Flow'")
        except Exception:
            print("  Button not found — please click 'Create with Flow' manually.")

        page.wait_for_timeout(1500)

        # Step 3: accept ToS popup if it appears
        print("[3] Looking for Terms of Service popup...")
        _accept_tos(page)

        # Step 4: handle Google sign-in
        print("[4] Waiting for Google sign-in...")
        print("    Please sign in to your Google account in the browser.")
        print("    The script will finish automatically once you reach the Flow editor.\n")
        try:
            page.wait_for_url("**/tools/flow**", timeout=SIGN_IN_TIMEOUT)
            page.wait_for_timeout(1500)
            print("\nLogin complete! Session saved.")
            print("From now on, run:  python auto_flow.py --begin img1.jpg --end img2.jpg")
        except Exception:
            print("\nTimed out or browser closed. Session saved as-is.")
        finally:
            context.close()


def _accept_tos(page: Page):
    """Accept ToS popup if present (tries each selector, skips if not found)."""
    for sel in [
        "button:has-text('I agree')",
        "button:has-text('Đồng ý')",
        "button:has-text('Accept')",
        "button:has-text('Chấp nhận')",
        "button:has-text('Continue')",
        "button:has-text('Tiếp tục')",
        "button:has-text('Agree')",
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


def _open_flow_editor(page: Page):
    """Go directly to the project URL, accept ToS if shown, handle expired session."""
    print(f"  Navigating to project: {FLOW_PROJECT_URL}")
    page.goto(FLOW_PROJECT_URL, wait_until="domcontentloaded", timeout=DEFAULT_TIMEOUT)
    page.wait_for_timeout(2000)

    # Session expired → sign in again
    ensure_signed_in(page)

    # Accept ToS if it pops up after navigation
    _accept_tos(page)

    page.wait_for_timeout(1500)
    print("  Flow editor loaded.")


# ─── main flow ────────────────────────────────────────────────────────────────

def debug_page(page: Page, label: str = ""):
    """Print all file inputs and visible buttons, and save a screenshot."""
    shot = Path(f"debug_{label or 'screenshot'}.png")
    page.screenshot(path=str(shot))
    print(f"\n  Screenshot: {shot.resolve()}")

    inputs = _get_file_inputs(page)
    print(f"  File inputs: {len(inputs)}")
    for i, el in enumerate(inputs):
        html = el.evaluate("e => e.outerHTML.slice(0, 120)")
        print(f"    [{i}] visible={el.is_visible()} {html}")

    buttons = page.query_selector_all("button, [role='button']")
    visible = [b for b in buttons if b.is_visible()]
    print(f"  Visible buttons: {len(visible)}")
    for i, b in enumerate(visible):
        try:
            txt = b.evaluate("e => (e.innerText || e.getAttribute('aria-label') || e.outerHTML).slice(0,80).trim()")
            print(f"    [{i}] {txt}")
        except Exception:
            pass


def run(begin_image: str, end_image: str, prompt: str = "",
        headless: bool = False, debug: bool = False):

    for path, label in [(begin_image, "begin"), (end_image, "end")]:
        if not Path(path).exists():
            print(f"Error: {label} image not found: {path}")
            sys.exit(1)

    print("\n=== Auto Flow AI ===")
    print(f"Begin  : {begin_image}")
    print(f"End    : {end_image}")
    print(f"Prompt : {prompt or '(none)'}")
    print(f"Profile: {PROFILE_DIR}")
    print(f"Mode   : {'headless' if headless else 'headed'}")
    print("=" * 40)

    with sync_playwright() as p:
        print("\n[1/6] Launching browser (persistent profile)...")
        context = _launch_context(p, headless=headless)
        page = context.new_page()

        print("[2/6] Opening Flow editor...")
        _open_flow_editor(page)
        dismiss_dialogs(page)

        if debug:
            print("\n[DEBUG] Page state after loading editor:")
            debug_page(page)

        print("[3/6] Uploading BEGIN image...")
        upload_begin_image(page, begin_image)

        if debug:
            print("\n[DEBUG] Page state after begin upload:")
            debug_page(page)

        print("[4/6] Uploading END image...")
        upload_end_image(page, end_image)

        if prompt:
            print("[5/6] Entering prompt...")
            enter_prompt(page, prompt)
        else:
            print("[5/6] No prompt — skipping.")

        print("[6/6] Generating video...")
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
    parser.add_argument(
        "--login", action="store_true",
        help="Open browser for one-time Google sign-in (saves session for future runs)"
    )
    parser.add_argument("--begin",  help="Path to the BEGIN (start) frame image")
    parser.add_argument("--end",    help="Path to the END (finish) frame image")
    parser.add_argument("--prompt",   default="", help="Optional text prompt")
    parser.add_argument("--headless", action="store_true", help="Run without a visible browser window")
    parser.add_argument("--debug",    action="store_true", help="Save screenshots and dump page elements")
    args = parser.parse_args()

    if args.login:
        login()
    else:
        if not args.begin or not args.end:
            parser.error("--begin and --end are required (or use --login to set up sign-in)")
        run(args.begin, args.end, args.prompt, args.headless, args.debug)


if __name__ == "__main__":
    main()
