import re
from typing import Protocol
from urllib.parse import urljoin, urlsplit

from playwright.async_api import Locator, Page, Route, TimeoutError as PlaywrightTimeoutError
from playwright.async_api import Error as PlaywrightError

from app.browser.page_reader import read_page
from app.browser.screenshot_manager import ScreenshotManager
from app.core.config import Settings
from app.schemas.browser_action import BrowserAction, BrowserToolName
from app.services.browser_test_service import UrlValidationError, validate_url


class BrowserToolError(RuntimeError):
    pass


class CredentialProvider(Protocol):
    def get_username(self) -> str: ...

    def get_password(self) -> str: ...


class MockCredentialProvider:
    """Test-only credentials read from backend configuration and never sent to the AI."""

    def __init__(self, settings: Settings) -> None:
        self._username = settings.test_credential_username
        self._password = settings.test_credential_password

    def get_username(self) -> str:
        if not self._username:
            raise BrowserToolError("Mock test username is not configured.")
        return self._username

    def get_password(self) -> str:
        if self._password is None or not self._password.get_secret_value():
            raise BrowserToolError("Mock test password is not configured.")
        return self._password.get_secret_value()


def _target_candidates(target: str) -> list[str]:
    values = [target.strip()]
    for suffix in (" field", " input", " button", " link", " checkbox", " radio button", " select"):
        if target.casefold().endswith(suffix):
            values.append(target[: -len(suffix)].strip())
    return list(dict.fromkeys(value for value in values if value))


async def _one_visible(locator: Locator, target: str, strategy: str) -> Locator | None:
    count = await locator.count()
    if count > 100:
        raise BrowserToolError(f"Multiple elements matched target '{target}'.")
    visible: list[Locator] = []
    for index in range(count):
        candidate = locator.nth(index)
        if await candidate.is_visible():
            visible.append(candidate)
    if len(visible) > 1:
        raise BrowserToolError(f"Multiple elements matched target '{target}'.")
    if visible:
        return visible[0]
    return None


async def resolve_element(
    page: Page,
    target: str,
    action: BrowserToolName | None = None,
) -> Locator:
    candidates = _target_candidates(target)
    role_names = {
        BrowserToolName.CLICK: ("button", "link", "menuitem", "tab"),
        BrowserToolName.FILL: ("textbox",),
        BrowserToolName.SELECT: ("combobox",),
        BrowserToolName.CHECK: ("checkbox", "radio", "switch"),
        BrowserToolName.UNCHECK: ("checkbox", "radio", "switch"),
        BrowserToolName.PRESS: ("button", "link", "textbox", "checkbox", "radio", "combobox", "tab", "menuitem"),
    }.get(action, ("button", "link", "textbox", "checkbox", "radio", "combobox", "option", "tab", "heading", "menuitem", "switch"))

    for candidate in candidates:
        role_matches: list[Locator] = []
        for role in role_names:
            match = await _one_visible(page.get_by_role(role, name=candidate, exact=True), target, "role")
            if match is not None:
                role_matches.append(match)
        if len(role_matches) > 1:
            raise BrowserToolError(f"Multiple elements matched target '{target}'.")
        if role_matches:
            return role_matches[0]

    strategies = (
        lambda candidate: page.get_by_label(candidate, exact=True),
        lambda candidate: page.get_by_placeholder(candidate, exact=True),
        lambda candidate: page.get_by_text(candidate, exact=True),
    )
    for locator_factory in strategies:
        for candidate in candidates:
            match = await _one_visible(locator_factory(candidate), target, "accessible name")
            if match is not None:
                return match

    fixed_elements = page.locator("input, textarea, select, button, a, [role]")
    count = min(await fixed_elements.count(), 500)
    for attribute in ("name", "id"):
        for candidate in candidates:
            matches: list[Locator] = []
            for index in range(count):
                locator = fixed_elements.nth(index)
                if await locator.get_attribute(attribute) == candidate and await locator.is_visible():
                    matches.append(locator)
            if len(matches) > 1:
                raise BrowserToolError(f"Multiple elements matched target '{target}'.")
            if matches:
                return matches[0]

    raise BrowserToolError(f"Element not found for target '{target}'.")


_DESTRUCTIVE_TARGET = re.compile(r"\b(delete|remove|purchase|buy|pay|payment|send|cancel|place order|submit|irreversible)\b", re.IGNORECASE)
_ALLOWED_KEYS = {"Enter", "Tab", "Escape", "Space", "ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight", "Home", "End", "Backspace", "Delete"}
MOCK_PASSWORD_TOKEN = "[MOCK_PASSWORD]"
MOCK_INVALID_PASSWORD_TOKEN = "[MOCK_INVALID_PASSWORD]"


class BrowserTools:
    def __init__(
        self,
        page: Page,
        settings: Settings,
        execution_id: str,
        session_url: str,
        credential_provider: CredentialProvider,
        confirm_destructive: bool = False,
        requires_credentials: bool = False,
    ) -> None:
        self.page = page
        self._settings = settings
        self._execution_id = execution_id
        self._session_url = session_url
        self._credential_provider = credential_provider
        self._confirm_destructive = confirm_destructive
        self._requires_credentials = requires_credentials
        self._screenshot_manager = ScreenshotManager()
        self.restricted_request = False

    async def guard_request(self, route: Route) -> None:
        request = route.request
        try:
            await validate_url(request.url, self._settings.allow_local_urls)
            if request.is_navigation_request() and not self._same_origin(request.url):
                raise BrowserToolError("Navigation outside the testing website is blocked.")
            await route.continue_()
        except (UrlValidationError, BrowserToolError):
            self.restricted_request = True
            await route.abort()

    def _same_origin(self, url: str) -> bool:
        base = urlsplit(self._session_url)
        target = urlsplit(urljoin(self.page.url or self._session_url, url))
        base_port = base.port or (443 if base.scheme == "https" else 80)
        target_port = target.port or (443 if target.scheme == "https" else 80)
        return (
            target.scheme in {"http", "https"}
            and target.scheme == base.scheme
            and target.hostname == base.hostname
            and target_port == base_port
        )

    async def execute_browser_action(self, action: BrowserAction) -> dict[str, object]:
        try:
            return await self._execute(action)
        except BrowserToolError:
            raise
        except PlaywrightTimeoutError as error:
            raise BrowserToolError("Browser action timed out.") from error
        except PlaywrightError as error:
            raise BrowserToolError("Browser action failed. Check the target and current page state.") from error

    async def _execute(self, action: BrowserAction) -> dict[str, object]:
        timeout = self._settings.action_timeout
        target = action.target or ""
        if action.action == BrowserToolName.NAVIGATE:
            if _DESTRUCTIVE_TARGET.search(target) and not self._confirm_destructive:
                raise BrowserToolError("Destructive action requires explicit user confirmation.")
            destination = urljoin(self.page.url or self._session_url, target)
            if not self._same_origin(destination):
                raise BrowserToolError("Navigation outside the testing website is blocked.")
            try:
                await validate_url(destination, self._settings.allow_local_urls)
            except UrlValidationError as error:
                raise BrowserToolError(str(error)) from error
            await self.page.goto(destination, wait_until="domcontentloaded", timeout=self._settings.navigation_timeout)
            return {"url": self.page.url}

        if action.action == BrowserToolName.READ_PAGE:
            return await read_page(self.page, self._settings.max_page_text_length)
        if action.action == BrowserToolName.TAKE_SCREENSHOT:
            screenshot_id = await self.capture_screenshot()
            return {"screenshot_id": screenshot_id}
        if action.action == BrowserToolName.SCROLL:
            delta = -600 if action.value == "up" else 600
            await self.page.mouse.wheel(0, delta)
            return {"scrolled": action.value}
        if action.action == BrowserToolName.WAIT:
            wait_ms = min(int(action.value or "0"), timeout)
            await self.page.wait_for_timeout(wait_ms)
            return {"waited_ms": wait_ms}

        if action.action in {BrowserToolName.CLICK, BrowserToolName.PRESS} and _DESTRUCTIVE_TARGET.search(target) and not self._confirm_destructive:
            raise BrowserToolError("Destructive action requires explicit user confirmation.")

        locator = await resolve_element(self.page, target, action.action)
        if action.action == BrowserToolName.PRESS and action.value == "Enter" and not self._confirm_destructive:
            controls = self.page.locator("button, input[type='submit']")
            for index in range(min(await controls.count(), 100)):
                control = controls.nth(index)
                if not await control.is_visible():
                    continue
                label = " ".join(filter(None, [
                    await control.inner_text(),
                    await control.get_attribute("aria-label"),
                    await control.get_attribute("value"),
                ]))
                if _DESTRUCTIVE_TARGET.search(label):
                    raise BrowserToolError("Enter could submit a destructive action; explicit user confirmation is required.")
        if action.action == BrowserToolName.CLICK:
            await locator.click(timeout=timeout)
        elif action.action == BrowserToolName.FILL:
            value = action.value or ""
            input_type = (await locator.get_attribute("type") or "").casefold()
            if input_type == "password":
                if self._requires_credentials and value == MOCK_PASSWORD_TOKEN:
                    value = self._credential_provider.get_password()
                elif not self._requires_credentials and value == MOCK_INVALID_PASSWORD_TOKEN:
                    value = "not-a-valid-mock-password"
                else:
                    raise BrowserToolError("Password values must use the approved mock credential placeholder.")
            elif self._requires_credentials and any(word in target.casefold() for word in ("username", "user name", "email")):
                value = self._credential_provider.get_username()
            await locator.fill(value, timeout=timeout)
        elif action.action == BrowserToolName.SELECT:
            value = action.value or ""
            try:
                await locator.select_option(label=value, timeout=timeout)
            except PlaywrightError:
                await locator.select_option(value=value, timeout=timeout)
        elif action.action == BrowserToolName.CHECK:
            await locator.check(timeout=timeout)
        elif action.action == BrowserToolName.UNCHECK:
            await locator.uncheck(timeout=timeout)
        elif action.action == BrowserToolName.PRESS:
            key = action.value or ""
            if key not in _ALLOWED_KEYS and not (len(key) == 1 and key.isalnum()):
                raise BrowserToolError("Keyboard key is not in the approved key list.")
            await locator.press(key, timeout=timeout)
        else:
            raise BrowserToolError("Browser tool is not available.")
        return {"completed": True}

    async def capture_screenshot(self) -> str:
        password_inputs = self.page.locator("input[type='password']")
        values: list[tuple[Locator, str]] = []
        for index in range(min(await password_inputs.count(), 50)):
            locator = password_inputs.nth(index)
            if not await locator.is_visible():
                continue
            value = await locator.input_value()
            values.append((locator, value))
            if value:
                await locator.fill("", timeout=self._settings.action_timeout)
        try:
            return await self._screenshot_manager.capture(self.page, self._execution_id)
        finally:
            for locator, value in values:
                if value:
                    await locator.fill(value, timeout=self._settings.action_timeout)
