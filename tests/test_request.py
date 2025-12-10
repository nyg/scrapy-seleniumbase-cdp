"""Tests for SeleniumBaseRequest"""

import pytest
from scrapy_seleniumbase_cdp import SeleniumBaseRequest


class TestSeleniumBaseRequest:
    """Test cases for SeleniumBaseRequest class"""

    def test_basic_request_creation(self):
        """Test creating a basic request"""
        url = "https://example.com"
        request = SeleniumBaseRequest(url=url)
        assert request.url == url
        assert request.wait_time is None
        assert request.wait_until is None
        assert request.screenshot is False
        assert request.script is None
        assert request.driver_methods is None

    def test_request_with_wait_time(self):
        """Test request with wait_time parameter"""
        request = SeleniumBaseRequest(
            url="https://example.com",
            wait_time=5
        )
        assert request.wait_time == 5

    def test_request_with_wait_until(self):
        """Test request with wait_until parameter"""
        selector = "#some-element"
        request = SeleniumBaseRequest(
            url="https://example.com",
            wait_until=selector
        )
        assert request.wait_until == selector

    def test_request_with_screenshot(self):
        """Test request with screenshot enabled"""
        request = SeleniumBaseRequest(
            url="https://example.com",
            screenshot=True
        )
        assert request.screenshot is True

    def test_request_with_script(self):
        """Test request with custom JavaScript"""
        script = "console.log('test');"
        request = SeleniumBaseRequest(
            url="https://example.com",
            script=script
        )
        assert request.script == script

    def test_request_with_driver_methods(self):
        """Test request with driver methods"""
        methods = [".find_element('id', 'test').click()"]
        request = SeleniumBaseRequest(
            url="https://example.com",
            driver_methods=methods
        )
        assert request.driver_methods == methods

    def test_request_with_all_parameters(self):
        """Test request with all parameters"""
        url = "https://example.com"
        wait_time = 10
        wait_until = "#element"
        script = "window.scrollTo(0, 100);"
        methods = [".click()"]

        request = SeleniumBaseRequest(
            url=url,
            wait_time=wait_time,
            wait_until=wait_until,
            screenshot=True,
            script=script,
            driver_methods=methods
        )

        assert request.url == url
        assert request.wait_time == wait_time
        assert request.wait_until == wait_until
        assert request.screenshot is True
        assert request.script == script
        assert request.driver_methods == methods
