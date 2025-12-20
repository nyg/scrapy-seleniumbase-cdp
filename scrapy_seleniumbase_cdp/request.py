"""This module contains the ``SeleniumBaseRequest`` class"""
from pathlib import Path
from typing import TypedDict

from scrapy import Request


class ScreenshotConfig(TypedDict, total=False):
    """Configuration for taking screenshots.

    Attributes
    ----------
    path : str or Path, optional
        The file path where the screenshot will be saved. Use 'auto' to rely on SeleniumBase default path.
        If omitted, the screenshot will not be saved to disk but the bytes will be accessible in the response, i.e. response.meta['screenshot'].
    format: str, optional
        File format of the screenshot, png by default.
    full_page : bool, optional
        Whether to capture the full page or just the visible viewport. True by default.
    """
    path: str | Path
    format: str
    full_page: bool


class SeleniumBaseRequest(Request):
    """Scrapy ``Request`` subclass providing additional arguments"""

    def __init__(self,
                 wait_time=None,
                 wait_until=None,
                 screenshot: bool | ScreenshotConfig | None = None,
                 script=None,
                 driver_methods=None,
                 *args,
                 **kwargs):
        """Initialize a new selenium request

        Parameters
        ----------
        wait_time: int
            The number of seconds to wait.
        wait_until: method
            One of the "selenium.webdriver.support.expected_conditions". The response
            will be returned until the given condition is fulfilled.
        screenshot : bool or dict, optional
            Configuration for taking screenshots. If True, uses default settings.
            If dict, see ScreenshotConfig for available options.
            Screenshot data will be available in response.meta['screenshot'] or saved to disk.
        script: str
            JavaScript code to execute.
        driver_methods: list
            List of seleniumbase driver methods as strings to execute. (e.g., [".find_element(...).click()", ...])
        """
        self.wait_time = wait_time
        self.wait_until = wait_until
        self.screenshot = {} if screenshot is True else screenshot
        self.script = script
        self.driver_methods = driver_methods
        super().__init__(*args, **kwargs)
