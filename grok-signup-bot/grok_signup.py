"""Playwright automation for xAI signup via OAuth Device Login flow.

Uses DrissionPage (Chromium) + turnstilePatch extension for antiblock.

Usage:
    python3 grok_signup.py \\
        --verification-url https://auth.x.ai/activate?user_code=XXXXXX \\
        [--headless]

Stdout protocol (parsed by Go bridge):
    __STEP__ <step>
    __CREDS__ {"email":"...","name":"...","password":"...","provider":"..."}
    __RESULT__ {"status":"success|error","reason":"...","step":"..."}
"""

from __future__ import annotations

import argparse
import json
import os
import random
import string
import sys
import time

from DrissionPage import Chromium, ChromiumOptions
from DrissionPage.errors import PageDisconnectedError, ElementLostError

from creds import CredsStore, random_name, random_password


def log(msg: str) -> None:
    print(msg, flush=True)


def fail(step: str, reason: str) -> None:
    log(f"__RESULT__ {json.dumps({'status': 'error', 'step': step, 'reason': reason})}")
    sys.exit(1)


def ensure_element(page, selectors_text: list[str], step: str, timeout: float = 10) -> object:
    """Wait for any of the given text selectors and return the element."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        for text in selectors_text:
            try:
                el = page.ele(f"tag:button@@text()={text}", timeout=3)
                if el and el.states.is_displayed:
                    return el
            except Exception:
                pass
            try:
                el = page.ele(f"tag:a@@text()={text}", timeout=3)
                if el and el.states.is_displayed:
                    return el
            except Exception:
                pass
        time.sleep(0.5)
    fail(step, f"no visible element matched: {selectors_text}")


def wait_and_click(page, selectors_text: list[str], step: str, timeout: float = 15) -> None:
    el = resolve_element(page, selectors_text, step, timeout)
    try:
        el.click()
    except Exception as e:
        fail(step, f"click failed: {e}")


def run_signup(
    verification_url: str,
    headless: bool = True,
    creds_dir: str | None = None,
) -> None:
    creds_store = CredsStore(creds_dir or os.environ.get("CREDS_DIR", ""))

    ext_path = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "turnstilePatch")
    )

    co = ChromiumOptions()
    co.auto_port()
    co.set_argument("--no-sandbox")
    co.set_argument("--disable-gpu")
    co.set_argument("--disable-dev-shm-usage")
    co.set_argument("--disable-software-rasterizer")
    co.add_extension(ext_path)
    co.set_timeouts(base=10)

    if headless:
        co.set_argument("--headless=new")

    if not headless and not os.environ.get("DISPLAY"):
        log("__STEP__ xvfb")
        try:
            from pyvirtualdisplay import Display
            _vd = Display(visible=0, size=(1920, 1080))
            _vd.start()
            log("xvfb started")
        except ImportError:
            log("xvfb not available, trying headless anyway")

    log("__STEP__ launching")

    browser = Chromium(co)
    tab = browser.new_tab()

    try:
        log("__STEP__ device")
        tab.get(verification_url)
        tab.wait.load_complete()
        time.sleep(2)

        # 1. Click "Continuar" / "Continue"
        log("__STEP__ continue")
        wait_and_click(tab, ["Continuar", "Continue"], "continue")
        time.sleep(2)

        # 2. Click "Sign up" / "Criar conta"
        log("__STEP__ signup")
        wait_and_click(tab, ["Criar conta", "Sign up", "Registrar"], "signup")
        time.sleep(1.5)

        # 3. Email
        from email_provider import build_providers, create_inbox_with_fallback

        providers = build_providers(
            names=["duckmail", "mailtm"],
            duckmail_url=os.environ.get("DUCKMAIL_URL", ""),
            duckmail_key=os.environ.get("DUCKMAIL_KEY", ""),
        )
        inbox = create_inbox_with_fallback(providers)
        email_addr = inbox["address"]
        log(f"__STEP__ email {inbox.get('provider', '?')} {email_addr}")

        fill_input(tab, email_addr, "email")
        time.sleep(1)
        # Press Enter / click submit
        submit_via_js(tab)
        time.sleep(2)

        # 4. OTP
        log("__STEP__ otp")
        from email_provider import provider_for_inbox as pfi
        provider = pfi(providers, inbox)
        since_ms = int(time.time() * 1000)
        code = provider.fetch_code(inbox, since_ms=since_ms, timeout=120)
        if not code:
            fail("otp", "timeout waiting for OTP")

        fill_input(tab, code, "otp")
        time.sleep(0.5)
        submit_via_js(tab)
        time.sleep(2)

        # 5. Name + password
        log("__STEP__ profile")
        name = random_name()
        password = random_password()

        fill_input(tab, name, "name")
        time.sleep(0.3)
        fill_input(tab, password, "password")
        time.sleep(0.5)

        # Try clicking submit
        submit_btn = None
        for sel in ["完成注册", "Create Account", "Sign up", "Criar conta", "Continuar"]:
            try:
                submit_btn = tab.ele(f"tag:button@@text()={sel}", timeout=3)
                if submit_btn and submit_btn.states.is_displayed:
                    submit_btn.click()
                    break
            except Exception:
                continue
        if not submit_btn:
            submit_via_js(tab)
        time.sleep(2)

        # 6. Turnstile — extension handles this; wait for it
        log("__STEP__ turnstile")
        time.sleep(5)

        # 7. Allow
        log("__STEP__ allow")
        wait_and_click(tab, ["Allow", "Permitir", "Autorizar"], "allow")
        time.sleep(2)

        # 8. Sign out
        log("__STEP__ signout")
        try:
            signout_btn = (
                tab.ele("tag:button@@text()=Sair", timeout=3)
                or tab.ele("tag:a@@text()=Sair", timeout=3)
                or tab.ele("tag:a@@text()=Sign out", timeout=3)
                or tab.ele("tag:button@@text()=Logout", timeout=3)
            )
            if signout_btn:
                signout_btn.click()
                time.sleep(1.5)
        except Exception:
            pass

        log("__STEP__ done")
        entry = creds_store.save(email_addr, name, password, inbox.get("provider", ""))
        log(f"__CREDS__ {json.dumps(entry)}")
        log('{"status":"success"}')

    except Exception as e:
        fail("runtime", str(e))
    finally:
        browser.quit()


def fill_input(tab, value: str, field_type: str) -> None:
    """Fill an input field by type (email, otp, name, password)."""
    selectors = {
        "email": [
            'input[data-testid="email"]',
            'input[name="email"]',
            'input[type="email"]',
        ],
        "otp": [
            'input[data-testid="code"]',
            'input[name="code"]',
            'input[autocomplete="one-time-code"]',
            'input[data-input-otp="true"]',
            'input[inputmode="numeric"]',
        ],
        "name": [
            'input[data-testid="givenName"]',
            'input[name="givenName"]',
            'input[autocomplete="given-name"]',
        ],
        "password": [
            'input[data-testid="password"]',
            'input[name="password"]',
            'input[type="password"]',
        ],
    }
    deadline = time.time() + 15
    while time.time() < deadline:
        for sel in selectors.get(field_type, []):
            try:
                el = page.ele(sel, timeout=2)
                if el and el.states.is_displayed and not el.states.is_disabled:
                    el.input(value)
                    return
            except Exception:
                continue
        time.sleep(0.5)
    fail(f"fill_{field_type}", f"no visible input for {field_type}")


def submit_via_js(page) -> None:
    """Click the first visible submit button via JS."""
    try:
        page.run_js("""
const btn = document.querySelector('button[type="submit"]');
if (btn && !btn.disabled) btn.click();
""")
    except Exception:
        pass


def main() -> None:
    parser = argparse.ArgumentParser(description="xAI signup via device login")
    parser.add_argument("--verification-url", required=True)
    parser.add_argument("--user-code")
    parser.add_argument("--headless", default="true")
    parser.add_argument("--creds-dir", default="", help="directory to save auto_creds.json")
    args = parser.parse_args()

    headless = args.headless.lower() not in ("false", "0", "no")

    run_signup(
        verification_url=args.verification_url,
        headless=headless,
        creds_dir=args.creds_dir,
    )


if __name__ == "__main__":
    main()