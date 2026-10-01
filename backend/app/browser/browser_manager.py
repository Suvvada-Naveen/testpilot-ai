from playwright.async_api import Browser, BrowserContext, Page, Playwright, async_playwright


class BrowserManager:
    def __init__(self, headless: bool = True) -> None:
        self._headless = headless
        self._playwright: Playwright | None = None
        self.browser: Browser | None = None
        self.context: BrowserContext | None = None

    async def start(self) -> None:
        self._playwright = await async_playwright().start()
        try:
            self.browser = await self._playwright.chromium.launch(headless=self._headless)
        except Exception:
            await self.close()
            raise

    async def create_context(self) -> BrowserContext:
        if self.browser is None:
            raise RuntimeError("Browser has not been started")
        self.context = await self.browser.new_context(accept_downloads=False)
        return self.context

    async def create_page(self) -> Page:
        if self.context is None:
            raise RuntimeError("Browser context has not been created")
        return await self.context.new_page()

    async def close_page(self, page: Page | None) -> None:
        if page is not None and not page.is_closed():
            await page.close()

    async def close_context(self) -> None:
        if self.context is not None:
            context, self.context = self.context, None
            await context.close()

    async def close_browser(self) -> None:
        if self.browser is not None:
            browser, self.browser = self.browser, None
            await browser.close()

    async def close(self) -> None:
        try:
            await self.close_context()
        finally:
            try:
                await self.close_browser()
            finally:
                if self._playwright is not None:
                    playwright, self._playwright = self._playwright, None
                    await playwright.stop()