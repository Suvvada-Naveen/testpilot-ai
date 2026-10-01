import asyncio
import ipaddress
import socket
from urllib.parse import urlsplit, urlunsplit

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Page, Request, Route, TimeoutError as PlaywrightTimeoutError

from app.browser.browser_manager import BrowserManager
from app.browser.page_reader import read_page
from app.browser.screenshot_manager import ScreenshotManager
from app.core.config import Settings


class UrlValidationError(ValueError):
    pass


class BrowserInspectionError(RuntimeError):
    pass


def _parse_http_url(url: str, allow_local_urls: bool) -> tuple[str, int]:
    try:
        parsed = urlsplit(url.strip())
        hostname = parsed.hostname
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
    except ValueError as error:
        raise UrlValidationError("Enter a valid website URL using HTTP or HTTPS.") from error

    if parsed.scheme not in {"http", "https"} or not hostname or parsed.username or parsed.password:
        raise UrlValidationError("Enter a valid website URL using HTTP or HTTPS, without embedded credentials.")
    if not parsed.netloc:
        raise UrlValidationError("Enter a valid website URL using HTTP or HTTPS.")

    normalized_host = hostname.rstrip(".").lower()
    is_local_name = normalized_host == "localhost" or normalized_host.endswith((".localhost", ".local", ".internal"))
    try:
        address = ipaddress.ip_address(normalized_host)
    except ValueError:
        address = None
    if not allow_local_urls and (is_local_name or (address is not None and not address.is_global)):
        raise UrlValidationError("Local and private network addresses are not allowed.")
    return normalized_host, port


async def validate_url(url: str, allow_local_urls: bool = False) -> None:
    hostname, port = _parse_http_url(url, allow_local_urls)
    if allow_local_urls:
        return
    try:
        resolved = await asyncio.to_thread(
            socket.getaddrinfo,
            hostname,
            port,
            0,
            socket.SOCK_STREAM,
        )
    except socket.gaierror as error:
        raise UrlValidationError("The website domain could not be resolved.") from error
    if not resolved:
        raise UrlValidationError("The website domain could not be resolved.")
    for result in resolved:
        address_text = result[4][0].split("%", maxsplit=1)[0]
        try:
            address = ipaddress.ip_address(address_text)
        except ValueError as error:
            raise UrlValidationError("The website resolved to an invalid network address.") from error
        if not address.is_global:
            raise UrlValidationError("Local and private network addresses are not allowed.")


def _safe_url(url: str) -> str:
    try:
        parsed = urlsplit(url)
        host = parsed.hostname or ""
        netloc = host
        if parsed.port:
            netloc = f"{host}:{parsed.port}"
        return urlunsplit((parsed.scheme, netloc, parsed.path, "", ""))
    except ValueError:
        return "[invalid URL]"


def _on_page_console(console_messages: list[dict[str, str]], max_count: int, message: object) -> None:
    message_type = getattr(message, "type", "log")
    if message_type not in {"log", "info", "warning", "error"} or len(console_messages) >= max_count:
        return
    console_messages.append({"type": message_type, "text": str(getattr(message, "text", "")).strip()[:2000]})


def _on_request_failed(network_errors: list[dict[str, str]], max_count: int, request: Request) -> None:
    if len(network_errors) >= max_count:
        return
    network_errors.append({
        "url": _safe_url(request.url),
        "method": request.method,
        "failure": str(request.failure or "Request failed")[:500],
    })


async def inspect_website(url: str, session_id: str, settings: Settings) -> dict[str, object]:
    await validate_url(url, settings.allow_local_urls)
    manager = BrowserManager(headless=settings.browser_headless)
    page: Page | None = None
    console_messages: list[dict[str, str]] = []
    network_errors: list[dict[str, str]] = []
    blocked_network = False
    response_status: int | None = None
    try:
        await manager.start()
        context = await manager.create_context()
        page = await manager.create_page()
        page.set_default_timeout(settings.browser_timeout)

        def capture_console(message: object) -> None:
            _on_page_console(console_messages, settings.max_console_messages, message)

        def capture_failure(request: Request) -> None:
            _on_request_failed(network_errors, settings.max_console_messages, request)

        # DNS checks and request interception are defense-in-depth; production needs OS/container egress isolation.
        async def guard_request(route: Route) -> None:
            nonlocal blocked_network
            request = route.request
            try:
                await validate_url(request.url, settings.allow_local_urls)
                await route.continue_()
            except UrlValidationError as error:
                blocked_network = True
                if len(network_errors) < settings.max_console_messages:
                    network_errors.append({
                        "url": _safe_url(request.url),
                        "method": request.method,
                        "failure": str(error),
                    })
                await route.abort()

        page.on("console", capture_console)
        page.on("requestfailed", capture_failure)
        await page.route("**/*", guard_request)
        try:
            response = await page.goto(url, wait_until="load", timeout=settings.browser_timeout)
        except PlaywrightTimeoutError as error:
            if blocked_network:
                raise BrowserInspectionError("The website attempted to access a restricted network address.") from error
            raise BrowserInspectionError("The website did not finish loading before the 30-second timeout.") from error
        except PlaywrightError as error:
            if blocked_network:
                raise BrowserInspectionError("The website attempted to access a restricted network address.") from error
            raise BrowserInspectionError("Unable to connect to or load this website.") from error

        response_status = response.status if response is not None else None
        page_data = await read_page(page, settings.max_page_text_length)
        screenshot_id = await ScreenshotManager().capture(page, session_id)
        elements = {key: value for key, value in page_data.items() if key not in {"title", "url", "visible_text"}}
        return {
            "session_id": session_id,
            "status": "COMPLETED",
            "page": {
                "requested_url": url,
                "final_url": page.url,
                "status_code": response_status,
                "title": page_data["title"],
            },
            "elements": elements,
            "visible_text": page_data["visible_text"],
            "screenshot_id": screenshot_id,
            "console_errors": [message for message in console_messages if message["type"] == "error"],
            "console_messages": console_messages,
            "network_errors": network_errors,
        }
    except (UrlValidationError, BrowserInspectionError):
        raise
    except Exception as error:
        if blocked_network:
            raise BrowserInspectionError("The website attempted to access a restricted network address.") from error
        raise BrowserInspectionError("Unable to inspect this website due to a browser error.") from error
    finally:
        try:
            await manager.close_page(page)
        finally:
            await manager.close()