import asyncio
import logging
from asyncio import Event
from base64 import b64decode
from functools import wraps

import mycdp
from mycdp.accessibility import LoadComplete
from mycdp.network import ResponseReceived
from scrapy import Request, signals
from scrapy.crawler import Crawler
from scrapy.exceptions import IgnoreRequest
from scrapy.http import HtmlResponse
from seleniumbase.undetected import cdp_driver
from seleniumbase.undetected.cdp_driver.browser import Browser
from seleniumbase.undetected.cdp_driver.tab import Tab

from .request import SeleniumBaseRequest

logger = logging.getLogger(__name__)


def _handle_errors(error_msg: str):
    """Decorator that catches and logs exceptions from async middleware methods.

    Wrapped methods log the error but do **not** abort the request — processing
    continues so that partial results (e.g. page source without a screenshot) are
    still returned to the spider.
    """

    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                logger.exception(f'{error_msg}: {e}')

        return wrapper

    return decorator


class SeleniumBaseAsyncCDPMiddleware:
    """Scrapy downloader middleware that handles requests using SeleniumBase's pure CDP mode.

    This middleware intercepts ``SeleniumBaseRequest`` instances and processes them through a
    shared CDP browser, while letting regular Scrapy ``Request`` objects pass through unchanged.

    Lifecycle:
        1. ``spider_opened``: starts a shared ``Browser`` instance via ``cdp_driver.start_async``.
        2. ``process_request``: for each ``SeleniumBaseRequest``, navigates the browser, waits for
           page load, solves captchas, and executes optional post-load steps (element wait, callback,
           script, screenshot).
        3. ``spider_closed``: stops the shared browser instance.

    The middleware uses async/await because SeleniumBase's pure CDP mode has its own event loop
    that conflicts with Scrapy's Twisted reactor.
    """

    def __init__(self, crawler: Crawler):
        """Initialize the middleware.

        Args:
            crawler: The Scrapy crawler instance. The ``SELENIUMBASE_BROWSER_OPTIONS`` setting
                is read from it and forwarded as kwargs to ``cdp_driver.start_async``.
        """
        self.crawler = crawler
        self.browser: Browser | None = None
        self.browser_options = crawler.settings.get('SELENIUMBASE_BROWSER_OPTIONS', {})

    @classmethod
    def from_crawler(cls, crawler: Crawler):
        """Create the middleware instance and connect Scrapy signals.

        Connects ``spider_opened`` and ``spider_closed`` signals so the browser
        is started and stopped together with the spider lifecycle.
        """
        middleware = cls(crawler)
        crawler.signals.connect(middleware.spider_opened, signals.spider_opened)
        crawler.signals.connect(middleware.spider_closed, signals.spider_closed)
        return middleware

    async def process_request(self, request: Request):
        """Process a request using the CDP browser if it is a ``SeleniumBaseRequest``.

        For regular Scrapy ``Request`` objects, returns ``None`` so Scrapy handles them normally.

        For ``SeleniumBaseRequest`` instances, registers CDP event handlers for
        ``ResponseReceived`` and ``LoadComplete``, delegates to ``_process_request`` for
        the actual page load and post-processing, then cleans up the handlers.

        Raises:
            IgnoreRequest: If an unrecoverable error occurs during processing.
        """
        if not isinstance(request, SeleniumBaseRequest):
            return None

        logger.debug(f'processing request: {request.url}')

        status = {'code': 200}
        status_event = Event()
        page_loaded_event = Event()

        def on_response_received(e: ResponseReceived):
            if e.response.url not in request.url or mycdp.network.ResourceType.DOCUMENT != e.type_:
                return
            status['code'] = e.response.status
            status_event.set()
            logger.debug(f'response received: [{e.response.status}] {e.response.url}')

        def on_load_complete(e: LoadComplete, connection=None):
            url = next((p.value.value for p in e.root.properties if p.name.value == 'url'), None)
            if url not in request.url:
                return
            logger.debug(f'page loaded: {url}')
            page_loaded_event.set()

        tab = self.browser.main_tab

        await tab.send(mycdp.accessibility.enable())

        tab.add_handler(ResponseReceived, on_response_received)
        tab.add_handler(LoadComplete, on_load_complete)

        try:
            return await self._process_request(request, status_event, page_loaded_event, status)
        except IgnoreRequest:
            raise
        except Exception as e:
            logger.exception(f'Error processing request: {e}')
            raise IgnoreRequest(f'Error processing request: {e}')
        finally:
            tab.handlers.get(ResponseReceived, []).remove(on_response_received)
            tab.handlers.get(LoadComplete, []).remove(on_load_complete)
            await tab.send(mycdp.accessibility.disable())

    async def _process_request(self, request: SeleniumBaseRequest, status_event: Event, page_loaded_event: Event, status: dict):
        """Execute the full request processing pipeline.

        Steps (in order):
            1. Navigate the browser to the request URL.
            2. Wait for both the HTTP response and the page load event (with timeout).
            3. Attempt to solve any captcha present on the page.
            4. Wait for a specific DOM element (optional, raises ``IgnoreRequest`` on timeout).
            5. Execute the user-provided browser callback (optional).
            6. Execute a JavaScript snippet (optional).
            7. Take a screenshot (optional).
            8. Build and return an ``HtmlResponse``.
        """
        tab: Tab = await self.browser.get(request.url)
        logger.debug(f'navigating to: {request.url}')

        try:
            await asyncio.wait_for(asyncio.gather(status_event.wait(), page_loaded_event.wait()), timeout=request.page_load_timeout)
        except TimeoutError:
            logger.warning(f'Timed out waiting for page to load: {request.url}')

        status_code = status['code']
        if status_code in request.captcha_blocked_codes:
            delay = request.captcha_blocked_delay
        else:
            delay = request.captcha_delay

        for attempt in range(request.captcha_max_attempts):
            await asyncio.sleep(delay)
            if not await tab.solve_captcha():
                logger.debug(f'no captcha detected: {request.url}')
                break
            logger.debug(f'captcha solved on attempt {attempt + 1}/{request.captcha_max_attempts}: {request.url}')
        else:
            logger.warning(f'Max captcha solve attempts ({request.captcha_max_attempts}) reached for {request.url}')

        await self._wait_for_element(tab, request)
        await self._execute_callback(request)
        await self._execute_script(tab, request)
        await self._take_screenshot(tab, request)

        return await self._build_response(tab, request, status_code)

    async def _build_response(self, tab: Tab, request: Request, status_code: int) -> HtmlResponse:
        """Build an HtmlResponse from the current tab state."""
        tab_url = await tab.evaluate('window.location.href')
        page_source = await tab.evaluate('document.documentElement.outerHTML')
        cookies = [f'{c.name}={c.value}' for c in await self.browser.cookies.get_all()]
        return HtmlResponse(url=tab_url,
                            body=page_source.encode('utf-8'),
                            encoding='utf-8',
                            request=request,
                            status=status_code,
                            headers={'Cookie': '; '.join(cookies)})

    @staticmethod
    async def _wait_for_element(tab: Tab, request: SeleniumBaseRequest):
        """Wait for the specified element if requested.

        Raises:
            IgnoreRequest: If the element is not found within the timeout.
        """
        if not request.wait_for_element:
            return

        logger.debug(f'waiting for element "{request.wait_for_element}" (timeout: {request.element_timeout}s): {request.url}')

        try:
            await tab.wait_for(selector=request.wait_for_element, timeout=request.element_timeout)
        except TimeoutError:
            logger.error(f'Timed out waiting for element "{request.wait_for_element}" on {request.url}')
            await SeleniumBaseAsyncCDPMiddleware._take_error_screenshot(tab, request)
            raise IgnoreRequest(f'Element "{request.wait_for_element}" not found within {request.element_timeout} seconds')

    @_handle_errors("Error executing browser callback")
    async def _execute_callback(self, request: SeleniumBaseRequest):
        """Execute the browser callback method if requested."""
        if not request.browser_callback:
            return

        logger.debug(f'executing browser callback: {request.url}')
        request.meta['callback'] = await request.browser_callback(self.browser)

    @staticmethod
    @_handle_errors("Error executing script")
    async def _execute_script(tab: Tab, request: SeleniumBaseRequest):
        """Execute the JavaScript code if requested."""
        if not request.script or not request.script.get('script'):
            return

        logger.debug(f'executing script: {request.url}')
        request.meta['script'] = await tab.evaluate(request.script['script'],
                                                     await_promise=request.script.get('await_promise', False))

    @staticmethod
    @_handle_errors("Error taking screenshot")
    async def _take_screenshot(tab: Tab, request: SeleniumBaseRequest):
        """Take a screenshot if requested."""
        if not request.screenshot:
            return

        logger.debug(f'taking screenshot: {request.url}')

        image_format = request.screenshot.get('format', 'png')
        full_page = request.screenshot.get('full_page', True)

        if request.screenshot.get('path'):
            path = await tab.save_screenshot(request.screenshot.get('path'), image_format, full_page)
            logger.debug(f'Screenshot saved in {path}')
        else:
            command = mycdp.page.capture_screenshot(format_=image_format, capture_beyond_viewport=full_page)
            request.meta['screenshot'] = b64decode(await tab.send(command))
            logger.debug('Screenshot saved in response.meta["screenshot"]')

    @staticmethod
    @_handle_errors("Error taking error screenshot")
    async def _take_error_screenshot(tab: Tab, request: SeleniumBaseRequest):
        """Take a screenshot on error and store it in ``request.meta['error_screenshot']``.

        Uses the image format from the request's screenshot configuration if available,
        otherwise defaults to a full-page PNG. Always captures the full page regardless
        of the user's ``full_page`` setting, to maximise diagnostic value.

        The screenshot is accessible in the spider's errback via
        ``failure.request.meta['error_screenshot']``.
        """
        image_format = 'png'
        if request.screenshot and isinstance(request.screenshot, dict):
            image_format = request.screenshot.get('format', 'png')

        command = mycdp.page.capture_screenshot(format_=image_format, capture_beyond_viewport=True)
        request.meta['error_screenshot'] = b64decode(await tab.send(command))
        logger.debug(f'error screenshot saved in request.meta["error_screenshot"]: {request.url}')

    async def spider_opened(self, spider):
        """Start the CDP browser when the spider opens."""
        self.browser = await cdp_driver.start_async(**self.browser_options)
        logger.debug('browser started')

    def spider_closed(self, spider):
        """Stop the browser when the spider closes."""
        self.browser.stop()
        logger.debug('browser stopped')
