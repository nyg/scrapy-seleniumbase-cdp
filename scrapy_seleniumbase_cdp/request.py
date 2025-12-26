from pathlib import Path
from typing import TypedDict, NotRequired, Callable, Awaitable, Any

from scrapy import Request
from seleniumbase.undetected.cdp_driver.browser import Browser


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


class ScriptConfig(TypedDict):
    """Configuration for executing JavaScript.

    Attributes
    ----------
    script : str, required
        The JavaScript code to execute.
    await_promise : bool, optional
        Whether to await the result if the script returns a Promise.
        Defaults to False.
    """
    script: str
    await_promise: NotRequired[bool]


class SeleniumBaseRequest(Request):
    """Subclass of Scrapy ``Request`` providing additional arguments"""

    def __init__(self,
                 wait_for: str | None = None,
                 wait_timeout: int = 10,
                 browser_callback: Callable[[Browser], Awaitable[Any]] | None = None,
                 script: str | dict | ScriptConfig | None = None,
                 screenshot: bool | dict | ScreenshotConfig | None = None,
                 *args,
                 **kwargs):
        """Initialize a new SeleniumBase request.

        Parameters
        ----------
        wait_for: str, optional
            The CSS selector of an element to wait for before returning the response to the spider.
        wait_timeout: int, optional
            The number of seconds to wait for the specified element, defaults to 10.
        browser_callback: callable, optional
            An async callback that allows interaction with the browser and/or its tabs.
            The callback result is stored in ``response.meta['callback']``.
        script : str or dict, optional
            JavaScript code to execute. If str, executes the code directly.
            If dict, see ScriptConfig for available options.
            The script result is stored in ``response.meta['script']``.
        screenshot : bool or dict, optional
            Screenshot configuration. If True, uses defaults and stores data in ``response.meta['screenshot']``.
            If dict, see ScreenshotConfig for available options.
        """
        self.wait_for = wait_for
        self.wait_timeout = wait_timeout
        self.screenshot = {} if screenshot is True else screenshot
        self.script = {'script': script, 'await_promise': False} if isinstance(script, str) else script
        self.browser_callback = browser_callback
        super().__init__(*args, **kwargs)
