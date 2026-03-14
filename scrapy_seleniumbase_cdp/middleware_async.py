import asyncio
from base64 import b64decode
from functools import wraps

import mycdp
from scrapy import Request, signals
from scrapy.crawler import Crawler
from scrapy.exceptions import IgnoreRequest
from scrapy.http import HtmlResponse
from seleniumbase.undetected import cdp_driver
from seleniumbase.undetected.cdp_driver.browser import Browser
from seleniumbase.undetected.cdp_driver.tab import Tab

from .request import SeleniumBaseRequest


class SeleniumBaseAsyncCDPMiddleware:
    """
    Scrapy downloader middleware handling the requests using SeleniumBase pure CDP mode instead of the UC mode.
    Uses SeleniumBase's async/await API because the event loop of the pure CDP mode conflicts with Scrapy's own event loop.
    """

    def __init__(self, crawler: Crawler):
        """Initialize the middleware.

        Args:
            crawler (Crawler): The Scrapy crawler instance.
        """
        self.crawler = crawler
        self.browser: Browser | None = None
        self.browser_options = crawler.settings.get('SELENIUMBASE_BROWSER_OPTIONS', {})
        self.backoff_on_429 = crawler.settings.getint('SELENIUMBASE_BACKOFF_ON_429', 60)

    @classmethod
    def from_crawler(cls, crawler: Crawler):
        """Initialize the middleware with the crawler settings."""
        middleware = cls(crawler)
        crawler.signals.connect(middleware.spider_opened, signals.spider_opened)
        crawler.signals.connect(middleware.spider_closed, signals.spider_closed)
        return middleware

    @staticmethod
    def _handle_errors(error_msg: str):
        """Decorator that catches and logs exceptions from async middleware methods."""

        def decorator(func):
            @wraps(func)
            async def wrapper(self, *args, **kwargs):
                try:
                    return await func(self, *args, **kwargs)
                except Exception as e:
                    self.crawler.spider.logger.exception(f'{error_msg}: {e}')

            return wrapper

        return decorator

    async def process_request(self, request: Request):
        """Process request using SeleniumBase."""
        if not isinstance(request, SeleniumBaseRequest):
            return None

        tab: Tab = await self.browser.get(request.url)
        await tab.solve_captcha()
        status_code = await tab.evaluate('performance.getEntriesByType("navigation")[0]?.responseStatus ?? 200')

        if 200 <= status_code < 300:
            await self._wait_for_element(tab, request)
            await self._execute_callback(request)
            await self._execute_script(tab, request)
        else:
            self.crawler.spider.logger.warning(f'Received {status_code} for {request.url}')
            if status_code == 429:
                self.crawler.spider.logger.warning(f'Backing off for {self.backoff_on_429} seconds')
                await asyncio.sleep(self.backoff_on_429)

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

    async def _wait_for_element(self, tab: Tab, request: SeleniumBaseRequest):
        """Wait for the specified element if requested.

        Raises:
            IgnoreRequest: If the element is not found within the timeout.
        """
        if not request.wait_for:
            return

        try:
            await tab.wait_for(selector=request.wait_for, timeout=request.wait_timeout)
        except asyncio.TimeoutError:
            self.crawler.spider.logger.error(f'Timed out waiting for element "{request.wait_for}" on {request.url}')
            await self._take_debug_screenshot(tab)
            raise IgnoreRequest(f'Element "{request.wait_for}" not found within {request.wait_timeout} seconds')

    @_handle_errors("Error executing browser callback")
    async def _execute_callback(self, request: SeleniumBaseRequest):
        """Execute the browser callback method if requested."""
        if not request.browser_callback:
            return

        request.meta['callback'] = await request.browser_callback(self.browser)

    @_handle_errors("Error executing script")
    async def _execute_script(self, tab: Tab, request: SeleniumBaseRequest):
        """Execute the JavaScript code if requested."""
        if not request.script or not request.script.get('script'):
            return

        request.meta['script'] = await tab.evaluate(request.script['script'],
                                                    await_promise=request.script.get('await_promise', False))

    @_handle_errors("Error taking screenshot")
    async def _take_screenshot(self, tab: Tab, request: SeleniumBaseRequest):
        """Take a screenshot if requested."""
        if not request.screenshot:
            return

        image_format = request.screenshot.get('format', 'png')
        full_page = request.screenshot.get('full_page', True)

        if request.screenshot.get('path'):
            path = await tab.save_screenshot(request.screenshot.get('path'), image_format, full_page)
            self.crawler.spider.logger.debug(f'Screenshot saved in {path}')
        else:
            command = mycdp.page.capture_screenshot(format_=image_format, capture_beyond_viewport=full_page)
            request.meta['screenshot'] = b64decode(await tab.send(command))
            self.crawler.spider.logger.debug('Screenshot saved in response.meta["screenshot"]')

    @_handle_errors("Error taking debug screenshot")
    async def _take_debug_screenshot(self, tab: Tab):
        """Take a full-page debug screenshot using SeleniumBase's default path."""
        path = await tab.save_screenshot('auto', 'png', True)
        self.crawler.spider.logger.info(f'Debug screenshot saved in {path}')

    async def spider_opened(self, spider):
        """Start the CDP browser when the spider opens."""
        self.browser = await cdp_driver.start_async(**self.browser_options)

    def spider_closed(self):
        """Stop the browser when the spider closes."""
        self.browser.stop()
