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
from typing import Optional, Dict, Any

from scrapy import signals
from scrapy.http import HtmlResponse, Request

from .request import SeleniumBaseRequest


class SeleniumBaseAsyncCDPMiddleware:
    """Scrapy middleware handling the requests using seleniumbase"""

    def __init__(self, driver_kwargs: Dict[str, Any]):
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

    async def process_request(self, request: Request, spider) -> Optional[HtmlResponse]:
        """Process a request using the selenium driver if applicable"""

        if not isinstance(request, SeleniumBaseRequest):
            return None

        try:
            page = await self.driver.get(request.url)

            # Handle wait_until condition
            if request.wait_until:
                try:
                    timeout = request.wait_time if request.wait_time else 10
                    await page.select(request.wait_until, timeout=timeout)
                except Exception as e:
                    spider.logger.warning(f'Element not found: {request.wait_until}, {e}')

            # Execute custom JavaScript if provided
            if request.script:
                try:
                    await page.evaluate(request.script)
                except Exception as e:
                    spider.logger.warning(f'Script execution failed: {e}')

            # Execute driver methods if provided
            if request.driver_methods:
                for method in request.driver_methods:
                    try:
                        # Execute the method string on the driver
                        await page.evaluate(f'() => {{ {method} }}')
                    except Exception as e:
                        spider.logger.warning(f'Driver method execution failed: {method}, {e}')

            # Take screenshot if requested
            if request.screenshot:
                try:
                    screenshot_data = await page.screenshot()
                    request.meta.update({'screenshot': screenshot_data})
                except Exception as e:
                    spider.logger.warning(f'Screenshot failed: {e}')

            request.meta.update({'driver': self.driver})

            page_source = await page.evaluate('document.documentElement.outerHTML')
            body = str.encode(page_source)

            return HtmlResponse(
                await page.evaluate('window.location.href'),
                body=body,
                encoding='utf-8',
                request=request
            )
        except Exception as e:
            spider.logger.error(f'Error processing request {request.url}: {e}')
            raise

    async def spider_opened(self, spider):
        """Start the CDP driver when spider opens"""
        try:
            self.driver = await self.start_async_driver(**self.driver_kwargs)
            spider.logger.info('SeleniumBase CDP driver started successfully')
        except Exception as e:
            spider.logger.error(f'Failed to start CDP driver: {e}')
            raise

    def spider_closed(self, spider):
        """Shutdown the driver when spider is closed"""
        if self.driver:
            try:
                self.driver.stop()
                spider.logger.info('SeleniumBase CDP driver stopped')
            except Exception as e:
                spider.logger.error(f'Error stopping CDP driver: {e}')
