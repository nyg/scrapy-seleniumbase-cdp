from pathlib import Path
from typing import Any, Awaitable, Callable, NotRequired, TypedDict

from scrapy import Request
from seleniumbase.undetected.cdp_driver.browser import Browser


class ScreenshotConfig(TypedDict):
    """Configuration for taking screenshots.

    Attributes:
        path (str | Path): The file path where the screenshot will be saved. Use 'auto' to rely on
            SeleniumBase default path. If omitted, the screenshot will not be saved to disk but the
            bytes will be accessible in the response, i.e. ``response.meta['screenshot']``.
        format (str): File format of the screenshot, png by default.
        full_page (bool): Whether to capture the full page or just the visible viewport. True by default.
    """
    path: NotRequired[str | Path]
    format: NotRequired[str]
    full_page: NotRequired[bool]


class ScriptConfig(TypedDict):
    """Configuration for executing JavaScript.

    Attributes:
        script (str): The JavaScript code to execute.
        await_promise (bool): Whether to await the result if the script returns a Promise.
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

        Args:
            wait_for (str | None): The CSS selector of an element to wait for before returning
                the response to the spider.
            wait_timeout (int): The number of seconds to wait for the specified element. Defaults to 10.
            browser_callback (Callable[[Browser], Awaitable[Any]] | None): An async callback that allows
                interaction with the browser and/or its tabs. The callback result is stored in
                ``response.meta['callback']``.
            script (str | dict | ScriptConfig | None): JavaScript code to execute. If str, executes
                the code directly. If dict, see ScriptConfig for available options. The script result
                is stored in ``response.meta['script']``.
            screenshot (bool | dict | ScreenshotConfig | None): Screenshot configuration. If True, uses
                defaults and stores data in ``response.meta['screenshot']``. If dict, see ScreenshotConfig
                for available options.
            args: Additional positional arguments for the Scrapy ``Request``.
            kwargs: Additional keyword arguments for the Scrapy ``Request``.
        """
        self.wait_for = wait_for
        self.wait_timeout = wait_timeout
        self.browser_callback = browser_callback

        match script:
            case str():
                self.script = {'script': script, 'await_promise': False}
            case {"script": str()}:
                self.script = script
            case None:
                self.script = None
            case _:
                raise TypeError(f"Invalid script type: {type(script)}")

        match screenshot:
            case True | {}:
                self.screenshot = {'format': 'png', 'full_page': True}
            case dict():
                self.screenshot = screenshot
            case False | None:
                self.screenshot = None
            case _:
                raise TypeError(f"Invalid screenshot type: {type(screenshot)}")

        super().__init__(*args, **kwargs)
