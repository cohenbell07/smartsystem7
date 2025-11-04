"""
Browser automation tool using Playwright.
"""

import logging
from typing import Dict, Any, Optional
from playwright.async_api import async_playwright, Browser, Page

logger = logging.getLogger(__name__)


class BrowserTool:
    """Tool for web browsing and automation."""

    def __init__(self, headless: bool = True):
        self.headless = headless
        self.browser: Optional[Browser] = None
        self.page: Optional[Page] = None

    async def _ensure_browser(self):
        """Ensure browser is launched."""
        if not self.browser:
            p = await async_playwright().start()
            self.browser = await p.chromium.launch(headless=self.headless)
            self.page = await self.browser.new_page()

    async def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute browser action.

        Supported actions:
        - goto: Navigate to URL
        - screenshot: Take screenshot
        - extract_text: Extract all text from page
        - fill_form: Fill and submit form
        - click: Click element

        Args:
            inputs: Dict with 'action' and action-specific params

        Returns:
            Dict with action result
        """
        action = inputs.get("action")

        if action == "goto":
            return await self._goto(inputs.get("url"))
        elif action == "screenshot":
            return await self._screenshot(inputs.get("path", "screenshot.png"))
        elif action == "extract_text":
            return await self._extract_text()
        elif action == "fill_form":
            return await self._fill_form(inputs.get("selector"), inputs.get("value"))
        elif action == "click":
            return await self._click(inputs.get("selector"))
        else:
            logger.error(f"Unknown browser action: {action}")
            return {"error": f"Unknown action: {action}"}

    async def _goto(self, url: str) -> Dict[str, Any]:
        """Navigate to URL."""
        await self._ensure_browser()

        try:
            await self.page.goto(url, timeout=30000, wait_until="networkidle")
            title = await self.page.title()
            logger.info(f"Navigated to {url} (title: {title})")
            return {"success": True, "url": url, "title": title}
        except Exception as e:
            logger.error(f"Failed to navigate to {url}: {e}")
            return {"error": str(e)}

    async def _screenshot(self, path: str) -> Dict[str, Any]:
        """Take screenshot."""
        await self._ensure_browser()

        try:
            await self.page.screenshot(path=path)
            logger.info(f"Screenshot saved to {path}")
            return {"success": True, "path": path}
        except Exception as e:
            logger.error(f"Failed to take screenshot: {e}")
            return {"error": str(e)}

    async def _extract_text(self) -> Dict[str, Any]:
        """Extract all text from page."""
        await self._ensure_browser()

        try:
            text = await self.page.inner_text("body")
            logger.info(f"Extracted {len(text)} characters")
            return {"success": True, "text": text}
        except Exception as e:
            logger.error(f"Failed to extract text: {e}")
            return {"error": str(e)}

    async def _fill_form(self, selector: str, value: str) -> Dict[str, Any]:
        """Fill form field."""
        await self._ensure_browser()

        try:
            await self.page.fill(selector, value)
            logger.info(f"Filled form field {selector}")
            return {"success": True}
        except Exception as e:
            logger.error(f"Failed to fill form: {e}")
            return {"error": str(e)}

    async def _click(self, selector: str) -> Dict[str, Any]:
        """Click element."""
        await self._ensure_browser()

        try:
            await self.page.click(selector)
            logger.info(f"Clicked element {selector}")
            return {"success": True}
        except Exception as e:
            logger.error(f"Failed to click: {e}")
            return {"error": str(e)}

    async def close(self):
        """Close browser."""
        if self.browser:
            await self.browser.close()
            self.browser = None
            self.page = None
