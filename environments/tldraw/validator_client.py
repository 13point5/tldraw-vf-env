import asyncio
import base64
import json
import logging
import re
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import unquote

from playwright.async_api import async_playwright


class ValidatorClient:
    def __init__(
        self,
        url: str,
        pool_size: int = 2,
        headless: bool = True,
        timeout_ms: int = 15000,
        save_screenshots: bool = True,
        screenshot_dir: str = "outputs/screenshots",
        log_errors: bool = True,
        error_log_dir: str = "outputs/errors",
    ) -> None:
        self.url = url
        self.pool_size = pool_size
        self.headless = headless
        self.timeout_ms = timeout_ms
        self.save_screenshots = save_screenshots
        self.screenshot_dir = screenshot_dir
        self.log_errors = log_errors
        self.error_log_dir = error_log_dir
        self._playwright = None
        self._browser = None
        self._queue: asyncio.Queue = asyncio.Queue()
        self._lock = asyncio.Lock()
        self._started = False
        self._run_tag: str | None = None
        self._run_dir: Path | None = None
        self._error_log_path: Path | None = None

    def _ensure_run_tag(self) -> str:
        if self._run_tag is None:
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            run_id = uuid.uuid4().hex[:8]
            self._run_tag = f"run_{timestamp}_{run_id}"
        return self._run_tag

    def _ensure_error_log_path(self) -> Path | None:
        if not self.log_errors:
            return None
        if self._error_log_path is not None:
            return self._error_log_path
        run_tag = self._ensure_run_tag()
        error_dir = Path(self.error_log_dir) / run_tag
        error_dir.mkdir(parents=True, exist_ok=True)
        self._error_log_path = error_dir / "errors.jsonl"
        logging.getLogger(__name__).info("Logging validator errors to %s", self._error_log_path)
        return self._error_log_path

    async def start(self) -> None:
        if self._started:
            return
        async with self._lock:
            if self._started:
                return
            if self.save_screenshots or self.log_errors:
                run_tag = self._ensure_run_tag()
                if self.save_screenshots and self._run_dir is None:
                    self._run_dir = Path(self.screenshot_dir) / run_tag
                    self._run_dir.mkdir(parents=True, exist_ok=True)
                    logging.getLogger(__name__).info("Saving rendered images to %s", self._run_dir)
                if self.log_errors and self._error_log_path is None:
                    error_dir = Path(self.error_log_dir) / run_tag
                    error_dir.mkdir(parents=True, exist_ok=True)
                    self._error_log_path = error_dir / "errors.jsonl"
                    logging.getLogger(__name__).info(
                        "Logging validator errors to %s", self._error_log_path
                    )
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(headless=self.headless)
            for _ in range(self.pool_size):
                page = await self._browser.new_page()
                page.set_default_timeout(self.timeout_ms)
                await page.goto(self.url, wait_until="domcontentloaded")
                await page.wait_for_function(
                    "() => window.__tldrawValidator && window.__tldrawValidator.validate"
                )
                await self._queue.put(page)
            self._started = True

    async def close(self) -> None:
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        self._started = False

    @asynccontextmanager
    async def _with_page(self):
        await self.start()
        page = await self._queue.get()
        try:
            yield page
        finally:
            await self._queue.put(page)

    def _build_screenshot_path(self, ext: str) -> Path:
        if self._run_dir is None:
            directory = Path(self.screenshot_dir)
            directory.mkdir(parents=True, exist_ok=True)
            return directory / f"render_{uuid.uuid4().hex}.{ext}"
        return self._run_dir / f"render_{uuid.uuid4().hex}.{ext}"

    def log_error_payload(self, payload: dict[str, Any]) -> str | None:
        if not self.log_errors:
            return None
        if self._error_log_path is None:
            self._ensure_error_log_path()
        if self._error_log_path is None:
            return None
        try:
            with self._error_log_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(payload) + "\n")
            return str(self._error_log_path)
        except Exception:
            logging.getLogger(__name__).exception("Failed to write error log")
            return None

    def _decode_data_url(self, data_url: str) -> tuple[str, bytes] | None:
        base64_match = re.match(r"^data:image/([^;]+);base64,(.+)$", data_url, re.DOTALL)
        if base64_match:
            ext = base64_match.group(1)
            payload = base64_match.group(2)
            return ext, base64.b64decode(payload)

        utf8_match = re.match(r"^data:image/([^;]+);utf8,(.+)$", data_url, re.DOTALL)
        if utf8_match:
            ext = utf8_match.group(1)
            payload = unquote(utf8_match.group(2))
            return ext, payload.encode("utf-8")

        return None

    def _save_data_url(self, data_url: str) -> str | None:
        decoded = self._decode_data_url(data_url)
        if not decoded:
            return None
        ext, payload = decoded
        target = self._build_screenshot_path(ext)
        with target.open("wb") as handle:
            handle.write(payload)
        return str(target)

    def _write_data_url(self, data_url: str, target: Path) -> bool:
        decoded = self._decode_data_url(data_url)
        if not decoded:
            return False
        _, payload = decoded
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("wb") as handle:
            handle.write(payload)
        return True

    async def validate(
        self, actions: list[dict[str, Any]], screenshot_path: str | None = None
    ) -> dict[str, Any]:
        async with self._with_page() as page:
            await page.evaluate("() => window.__tldrawValidator.reset()")
            result = await page.evaluate(
                "(payload) => window.__tldrawValidator.validate(payload.actions, payload.options)",
                {"actions": actions, "options": None},
            )
            image_payload = result.get("image")
            if image_payload and isinstance(image_payload, dict):
                data_url = image_payload.get("url")
                if screenshot_path:
                    if data_url and self._write_data_url(data_url, Path(screenshot_path)):
                        image_payload.pop("url", None)
                        image_payload["path"] = screenshot_path
                        result["image_source"] = "tldraw_export"
                    else:
                        result.setdefault("errors", []).append(
                            {
                                "stage": "export",
                                "message": "Image export failed: unable to save data URL",
                            }
                        )
                elif self.save_screenshots:
                    if data_url:
                        saved = self._save_data_url(data_url)
                        if saved:
                            image_payload.pop("url", None)
                            image_payload["path"] = saved
                            result["image_source"] = "tldraw_export"
                        else:
                            result.setdefault("errors", []).append(
                                {
                                    "stage": "export",
                                    "message": "Image export failed: unsupported data URL",
                                }
                            )
                    else:
                        result.setdefault("errors", []).append(
                            {
                                "stage": "export",
                                "message": "Image export failed: missing data URL",
                            }
                        )
            if self.save_screenshots and not result.get("image_source"):
                target = (
                    Path(screenshot_path) if screenshot_path else self._build_screenshot_path("png")
                )
                try:
                    await page.screenshot(path=str(target), full_page=True)
                    if not isinstance(result.get("image"), dict):
                        result["image"] = {}
                    result["image"]["path"] = str(target)
                    result["image_source"] = "page_screenshot"
                except Exception as exc:
                    result.setdefault("errors", []).append(
                        {"stage": "fallback", "message": f"Fallback screenshot failed: {exc}"}
                    )
            if self._run_dir is not None:
                result["image_dir"] = str(self._run_dir)
            if self._error_log_path is not None:
                result["error_log_path"] = str(self._error_log_path)
            return result
        return {"errors": [{"message": "No validator page available"}]}
