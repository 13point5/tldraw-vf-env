import asyncio
from concurrent.futures import ThreadPoolExecutor

from playwright.sync_api import sync_playwright

SYSTEM_PROMPT_FETCH_ERROR = "Failed to fetch system prompt."


def fetch_system_prompt_via_bridge(url: str, timeout_ms: int, headless: bool) -> str:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=headless)
        try:
            page = browser.new_page()
            page.set_default_timeout(timeout_ms)
            page.goto(url, wait_until="domcontentloaded")
            page.wait_for_function(
                "() => window.__tldrawValidator && window.__tldrawValidator.getSystemPrompt"
            )
            return page.evaluate("() => window.__tldrawValidator.getSystemPrompt()")
        finally:
            browser.close()


def safe_fetch_system_prompt(url: str, timeout_ms: int, headless: bool) -> str:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        try:
            return fetch_system_prompt_via_bridge(url, timeout_ms, headless)
        except Exception as exc:
            raise RuntimeError(f"{SYSTEM_PROMPT_FETCH_ERROR} {exc}") from exc
    else:
        try:
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(fetch_system_prompt_via_bridge, url, timeout_ms, headless)
                return future.result()
        except Exception as exc:
            raise RuntimeError(f"{SYSTEM_PROMPT_FETCH_ERROR} {exc}") from exc
