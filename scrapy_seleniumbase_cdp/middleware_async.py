from base64 import b64decode

import mycdp
from scrapy import Request
from scrapy import signals, Spider
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

    def __init__(self, browser_options: dict[str, str]):
        """Initialize the middleware.

        Args:
            browser_options (dict[str, str]): A dictionary of keyword arguments to initialize the
                SeleniumBrowser with.
        """
        self.browser: Browser | None = None
        self.browser_options = browser_options

    @classmethod
    def from_crawler(cls, crawler):
        """Initialize the middleware with the crawler settings."""
        browser_options = crawler.settings.get('SELENIUMBASE_BROWSER_OPTIONS', {})
        middleware = cls(browser_options)
        crawler.signals.connect(middleware.spider_opened, signals.spider_opened)
        crawler.signals.connect(middleware.spider_closed, signals.spider_closed)
        return middleware

    async def process_request(self, request: Request, spider: Spider):
        """Process request using SeleniumBase."""
        if not isinstance(request, SeleniumBaseRequest):
            return None

        tab: Tab = await self.browser.get(request.url)
        await tab.solve_captcha()

        await self._wait_for_element(tab, request, spider)
        await self._execute_callback(request, spider)
        await self._execute_script(tab, request, spider)
        await self._take_screenshot(tab, request, spider)

        tab_url = await tab.evaluate('window.location.href')
        page_source = await tab.evaluate('document.documentElement.outerHTML')
        status_code = await tab.evaluate('performance.getEntriesByType("navigation")[0]?.responseStatus || 200')
        cookies = [f'{c.name}={c.value}' for c in await self.browser.cookies.get_all()]

        return HtmlResponse(url=tab_url,
                            body=page_source.encode('utf-8'),
                            encoding='utf-8',
                            request=request,
                            status=status_code,
                            headers={'Cookie': '; '.join(cookies)})

    @staticmethod
    async def _wait_for_element(tab: Tab, request: SeleniumBaseRequest, spider: Spider):
        """Wait for the specified element if requested."""
        if not request.wait_for:
            return

        try:
            await tab.wait_for(selector=request.wait_for, timeout=getattr(request, 'wait_timeout', 10))
        except Exception as e:
            spider.logger.warning(f'Element not found: {request.wait_for}, {e}')

    async def _execute_callback(self, request: SeleniumBaseRequest, spider: Spider):
        """Execute the browser callback method if requested."""
        if not request.browser_callback:
            return

        try:
            request.meta['callback'] = await request.browser_callback(self.browser)
        except Exception as e:
            spider.logger.warning(f'Error executing browser callback: {e}')

    @staticmethod
    async def _execute_script(tab: Tab, request: SeleniumBaseRequest, spider: Spider):
        """Execute the JavaScript code if requested."""
        if not request.script:
            return

        try:
            request.meta['script'] = await tab.evaluate(request.script.get('script', ''),
                                                        await_promise=request.script.get('await_promise', False))
        except Exception as e:
            spider.logger.warning(f'Error executing script: {e}')

    @staticmethod
    async def _take_screenshot(tab: Tab, request: SeleniumBaseRequest, spider: Spider):
        """Take a screenshot if requested."""
        if request.screenshot in (None, False):
            return

        try:
            image_format = request.screenshot.get('format', 'png')
            full_page = request.screenshot.get('full_page', True)

            if request.screenshot.get('path'):
                path = await tab.save_screenshot(request.screenshot.get('path'), image_format, full_page)
                spider.logger.info(f'Screenshot saved in {path}')
            else:
                command = mycdp.page.capture_screenshot(format_=image_format, capture_beyond_viewport=full_page)
                request.meta['screenshot'] = b64decode(await tab.send(command))
                spider.logger.info('Screenshot saved in response.meta["screenshot"]')
        except Exception as e:
            spider.logger.warning(f'Screenshot could not be saved: {e}')

    async def spider_opened(self, spider):
        """Start the CDP browser when the spider opens."""
        self.browser = await cdp_driver.start_async(**self.browser_options)

    def spider_closed(self):
        """Stop the browser when the spider closes."""
        self.browser.stop()
