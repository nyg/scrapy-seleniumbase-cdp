# SeleniumBase middleware using the pure CDP mode instead of the UC mode.
#
# Uses the async/await API of SeleniumBase because the event loop of the pure
# CDP mode conflicts with Scrapy's own event loop. For the moment this means
# less features.
#
# The pure CDP mode does not require any WebDriver and can therefore run on
# platforms where no such drivers are available (e.g., Raspberry Pi)
#
# Based on https://github.com/Quartz-Core/scrapy-seleniumbase.
#
# Doc: https://github.com/seleniumbase/SeleniumBase/blob/master/help_docs/syntax_formats.md#sb_sf_24
#      https://github.com/seleniumbase/SeleniumBase/discussions/3955

from importlib import import_module

from scrapy import signals
from scrapy.http import HtmlResponse

from .request import SeleniumBaseRequest


class SeleniumBaseAsyncCDPMiddleware:
    """Scrapy middleware handling the requests using seleniumbase"""

    def __init__(self, driver_kwargs):
        """Initialize the selenium webdriver

        Parameters
        ----------
        driver_kwargs: dict
            A dictionary of keyword arguments to initialize the driver with.
        """
        seleniumbase_cdp = import_module("seleniumbase")
        cdp_module = getattr(seleniumbase_cdp, 'cdp_driver')
        self.start_async_driver = getattr(cdp_module, "start_async")
        self.driver = None
        self.driver_kwargs = driver_kwargs

    @classmethod
    def from_crawler(cls, crawler):
        """Initialize the middleware with the crawler settings"""
        driver_kwargs = crawler.settings.get('SELENIUMBASE_DRIVER_KWARGS', {})
        middleware = cls(driver_kwargs)
        crawler.signals.connect(middleware.spider_opened, signals.spider_opened)
        crawler.signals.connect(middleware.spider_closed, signals.spider_closed)
        return middleware

    async def process_request(self, request, spider):
        """Process a request using the selenium driver if applicable"""

        if not isinstance(request, SeleniumBaseRequest):
            return None

        page = await self.driver.get(request.url)

        if request.wait_until:
            try:
                await page.select(request.wait_until, timeout=request.wait_time if hasattr(request, 'wait_time') else 10)
            except Exception as e:
                spider.logger.warning(f'Element not found: {request.wait_until}, {e}')

        request.meta.update({'driver': self.driver})

        page_source = await page.evaluate('document.documentElement.outerHTML')
        body = str.encode(page_source)

        return HtmlResponse(await page.evaluate('window.location.href'), body=body, encoding='utf-8', request=request)

    async def spider_opened(self, spider):
        """Start the CDP driver when spider opens"""
        self.driver = await self.start_async_driver(**self.driver_kwargs)

    def spider_closed(self):
        """Shutdown the driver when spider is closed"""
        self.driver.stop()
