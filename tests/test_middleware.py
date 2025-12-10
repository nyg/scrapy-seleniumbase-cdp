"""Tests for SeleniumBaseAsyncCDPMiddleware"""

import pytest
from unittest.mock import Mock, AsyncMock, MagicMock
from scrapy import Request
from scrapy.http import HtmlResponse

from scrapy_seleniumbase_cdp import SeleniumBaseAsyncCDPMiddleware, SeleniumBaseRequest


class TestSeleniumBaseAsyncCDPMiddleware:
    """Test cases for SeleniumBaseAsyncCDPMiddleware class"""

    def test_init(self):
        """Test middleware initialization"""
        driver_kwargs = {"headless": True}
        middleware = SeleniumBaseAsyncCDPMiddleware(driver_kwargs)
        assert middleware.driver_kwargs == driver_kwargs
        assert middleware.driver is None

    def test_from_crawler(self):
        """Test middleware creation from crawler"""
        crawler = Mock()
        crawler.settings.get.return_value = {"headless": True}
        crawler.signals.connect = Mock()

        middleware = SeleniumBaseAsyncCDPMiddleware.from_crawler(crawler)

        assert middleware.driver_kwargs == {"headless": True}
        assert crawler.signals.connect.call_count == 2

    @pytest.mark.asyncio
    async def test_process_request_non_selenium_request(self):
        """Test that non-SeleniumBaseRequest is ignored"""
        middleware = SeleniumBaseAsyncCDPMiddleware({})
        spider = Mock()
        request = Request(url="https://example.com")

        result = await middleware.process_request(request, spider)

        assert result is None

    @pytest.mark.asyncio
    async def test_process_request_basic(self):
        """Test basic request processing"""
        middleware = SeleniumBaseAsyncCDPMiddleware({})
        spider = Mock()
        spider.logger = Mock()

        # Mock driver and page
        page = AsyncMock()
        page.get = AsyncMock(return_value=page)
        page.evaluate = AsyncMock()
        page.evaluate.side_effect = [
            '<html><body>Test</body></html>',  # First call for outerHTML
            'https://example.com'  # Second call for location.href
        ]

        middleware.driver = Mock()
        middleware.driver.get = AsyncMock(return_value=page)

        request = SeleniumBaseRequest(url="https://example.com")

        response = await middleware.process_request(request, spider)

        assert isinstance(response, HtmlResponse)
        assert response.url == 'https://example.com'
        assert 'driver' in request.meta
