import asyncio
import logging
from asyncio import Event
from base64 import b64decode
from functools import wraps

import mycdp
from mycdp.network import ResponseReceived
from mycdp.page import LoadEventFired
from scrapy import Request, signals
from scrapy.crawler import Crawler
from scrapy.http import HtmlResponse
from seleniumbase.undetected import cdp_driver
from seleniumbase.undetected.cdp_driver.browser import Browser
from seleniumbase.undetected.cdp_driver.tab import Tab

from .request import SeleniumBaseRequest

logger = logging.getLogger(__name__)


def _handle_errors(error_msg: str, stat: str):
    """Decorator that catches and logs exceptions from async middleware methods, and counts them in the ``stat`` stat.

    Wrapped methods log the error but do **not** abort the request — processing
    continues so that partial results (e.g. page source without a screenshot) are
    still returned to the spider.
    """

    def decorator(func):
        @wraps(func)
        async def wrapper(self, *args, **kwargs):
            try:
                return await func(self, *args, **kwargs)
            except Exception as e:
                logger.exception(f'{error_msg}: {e}')
                self.stats.inc_value(stat)

        return wrapper

    return decorator


class SeleniumBaseAsyncCDPMiddleware:
    """Scrapy downloader middleware that handles requests using SeleniumBase's pure CDP mode.

    This middleware intercepts ``SeleniumBaseRequest`` instances and processes them through a
    shared CDP browser, while letting regular Scrapy ``Request`` objects pass through unchanged.

    Lifecycle:
        1. ``spider_opened``: starts a shared ``Browser`` instance via ``cdp_driver.start_async`` and
           picks the tab every request loads in.
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
        self.stats = crawler.stats
        self.browser: Browser | None = None
        self.tab: Tab | None = None
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
        ``ResponseReceived`` and ``LoadEventFired``, delegates to ``_process_request`` for
        the actual page load and post-processing, then cleans up the handlers.

        Raises:
            TimeoutError: If the main frame gets no document response within ``page_load_timeout``,
                or the ``wait_for_element`` element is not found within ``element_timeout``.
            Exception: Any other processing error, logged and re-raised.
        """
        if not isinstance(request, SeleniumBaseRequest):
            return None

        logger.debug(f'processing request: {request.url}')

        tab = self.tab
        # Chrome gives a page target's main frame the target's id.
        main_frame_id = tab.target_id

        status = {'code': None}
        status_event = Event()
        page_loaded_event = Event()

        def on_response_received(e: ResponseReceived):
            if e.frame_id != main_frame_id or mycdp.network.ResourceType.DOCUMENT != e.type_:
                return
            status['code'] = e.response.status
            status_event.set()
            logger.debug(f'response received: [{e.response.status}] {e.response.url}')

        # Chrome fires Page.loadEventFired for the main frame only.
        def on_load_event_fired(e: LoadEventFired):
            logger.debug(f'load event fired: {request.url}')
            page_loaded_event.set()

        tab.add_handler(ResponseReceived, on_response_received)
        tab.add_handler(LoadEventFired, on_load_event_fired)

        try:
            return await self._process_request(request, status_event, page_loaded_event, status)
        except TimeoutError:
            raise
        except Exception as e:
            logger.exception(f'Error processing request: {e}')
            raise
        finally:
            tab.handlers.get(ResponseReceived, []).remove(on_response_received)
            tab.handlers.get(LoadEventFired, []).remove(on_load_event_fired)

    async def _process_request(self, request: SeleniumBaseRequest, status_event: Event, page_loaded_event: Event, status: dict):
        """Execute the full request processing pipeline.

        Steps (in order):
            1. Navigate the tab to the request URL.
            2. Wait for both the main frame's document response and the page load event (with timeout,
               raises ``TimeoutError`` if the document response never arrives).
            3. Attempt to solve any captcha present on the page.
            4. Wait for a specific DOM element (optional, raises ``TimeoutError`` on timeout).
            5. Execute the user-provided browser callback (optional).
            6. Execute a JavaScript snippet (optional).
            7. Take a screenshot (optional).
            8. Build and return an ``HtmlResponse``.
        """
        tab = self.tab
        logger.debug(f'navigating to: {request.url}')
        await tab.send(mycdp.page.navigate(request.url))

        await self._wait_for_page_load(request, status_event, page_loaded_event)
        self.stats.inc_value(f'seleniumbase/response_status_count/{status["code"]}')

        await self._solve_captcha(tab, request, status['code'], status_event, page_loaded_event)
        # SeleniumBase caches the tab's url, which save_screenshot('auto') names files after, and only Browser.get refreshed it.
        await tab.update_target()
        await self._wait_for_element(tab, request)
        await self._execute_callback(request)
        await self._execute_script(tab, request)
        await self._take_screenshot(tab, request)

        # Read again: a solved challenge reloads the page and on_response_received records the new status.
        return await self._build_response(tab, request, status['code'])

    @staticmethod
    async def _wait_for_page_load(request: SeleniumBaseRequest, status_event: Event, page_loaded_event: Event):
        try:
            await asyncio.wait_for(asyncio.gather(status_event.wait(), page_loaded_event.wait()), timeout=request.page_load_timeout)
        except TimeoutError:
            if status_event.is_set():
                logger.warning(f'timed out waiting for page to load: {request.url}')
                return
            error = TimeoutError(f'no document response within {request.page_load_timeout}s: {request.url}')
            logger.error(error)
            raise error from None

    async def _solve_captcha(self, tab: Tab, request: SeleniumBaseRequest, status_code: int, status_event: Event, page_loaded_event: Event):
        # Set on every pass so a retried request does not keep the previous attempt's outcome.
        request.meta['captcha_unsolved'] = False
        if not request.captcha_max_attempts:
            return

        if status_code in request.captcha_blocked_codes:
            delay = request.captcha_blocked_delay
        elif request.captcha_only_when_blocked:
            logger.debug(f'no captcha check for unblocked status {status_code}: {request.url}')
            return
        else:
            delay = request.captcha_delay

        for attempt in range(1, request.captcha_max_attempts + 1):
            await asyncio.sleep(delay)
            status_event.clear()
            page_loaded_event.clear()
            if not await tab.solve_captcha():
                logger.debug(f'no captcha detected: {request.url}')
                if attempt > 1:
                    self.stats.inc_value('captcha/solved')
                return
            if attempt == 1:
                self.stats.inc_value('captcha/detected')
            logger.debug(f'captcha clicked on attempt {attempt}/{request.captcha_max_attempts}: {request.url}')
            # solve_captcha() returns once it has clicked, while the challenge may still be verifying.
            try:
                await asyncio.wait_for(asyncio.gather(status_event.wait(), page_loaded_event.wait()), timeout=request.page_load_timeout)
            except TimeoutError:
                logger.debug(f'no reload within {request.page_load_timeout}s of the captcha click: {request.url}')

        logger.warning(f'max captcha solve attempts ({request.captcha_max_attempts}) reached for {request.url}')
        self.stats.inc_value('captcha/unsolved')
        request.meta['captcha_unsolved'] = True

    async def _build_response(self, tab: Tab, request: Request, status_code: int) -> HtmlResponse:
        """Build an HtmlResponse from the current tab state."""
        tab_url = await tab.evaluate('window.location.href')
        page_source = await tab.evaluate('document.documentElement.outerHTML')
        request.meta['cookies'] = [c.to_json() for c in await tab.send(mycdp.network.get_cookies(urls=[tab_url]))]
        return HtmlResponse(url=tab_url,
                            body=page_source.encode('utf-8'),
                            encoding='utf-8',
                            request=request,
                            status=status_code)

    async def _wait_for_element(self, tab: Tab, request: SeleniumBaseRequest):
        """Wait for the specified element if requested.

        Raises:
            TimeoutError: If the element is not found within the timeout.
        """
        if not request.wait_for_element:
            return

        try:
            logger.debug(f'waiting for element "{request.wait_for_element}" (timeout: {request.element_timeout}s): {request.url}')
            await tab.wait_for(selector=request.wait_for_element, timeout=request.element_timeout)
        except TimeoutError:
            logger.error(f'timed out waiting for element "{request.wait_for_element}" on {request.url}')
            await self._take_error_screenshot(tab, request)
            raise

    @_handle_errors("Error executing browser callback", 'seleniumbase/browser_callback_failed')
    async def _execute_callback(self, request: SeleniumBaseRequest):
        """Execute the browser callback method if requested."""
        if not request.browser_callback:
            return

        logger.debug(f'executing browser callback: {request.url}')
        request.meta['callback'] = await request.browser_callback(self.browser)

    @_handle_errors("Error executing script", 'seleniumbase/script_failed')
    async def _execute_script(self, tab: Tab, request: SeleniumBaseRequest):
        """Execute the JavaScript code if requested."""
        if not request.script or not request.script.get('script'):
            return

        logger.debug(f'executing script: {request.url}')
        request.meta['script'] = await tab.evaluate(request.script['script'],
                                                    await_promise=request.script.get('await_promise', False))

    @_handle_errors("Error taking screenshot", 'seleniumbase/screenshot_failed')
    async def _take_screenshot(self, tab: Tab, request: SeleniumBaseRequest):
        """Take a screenshot if requested."""
        if not request.screenshot:
            return

        logger.debug(f'taking screenshot: {request.url}')

        image_format = request.screenshot.get('format', 'png')
        full_page = request.screenshot.get('full_page', True)

        if request.screenshot.get('path'):
            path = await tab.save_screenshot(request.screenshot.get('path'), image_format, full_page)
            logger.debug(f'screenshot saved in {path}')
        else:
            command = mycdp.page.capture_screenshot(format_=image_format, capture_beyond_viewport=full_page)
            request.meta['screenshot'] = b64decode(await tab.send(command))
            logger.debug('screenshot saved in response.meta["screenshot"]')

    @_handle_errors("Error taking error screenshot", 'seleniumbase/error_screenshot_failed')
    async def _take_error_screenshot(self, tab: Tab, request: SeleniumBaseRequest):
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
        # Browser.get applies the sb_config settings (user agent, locale, ad block...) to the tab it navigates, but that tab is
        # browser.targets[-1], which any tab opened later becomes. So it runs once, and every request reuses this tab.
        self.tab = await self.browser.get('about:blank')
        logger.debug('browser started')

    def spider_closed(self, spider):
        """Stop the browser when the spider closes."""
        self.browser.stop()
        logger.debug('browser stopped')
