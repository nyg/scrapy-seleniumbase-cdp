# scrapy-seleniumbase-cdp

[![PyPI](https://img.shields.io/pypi/v/scrapy-seleniumbase-cdp)](https://pypi.org/project/scrapy-seleniumbase-cdp/)
[![Python Versions](https://img.shields.io/pypi/pyversions/scrapy-seleniumbase-cdp)](https://pypi.org/project/scrapy-seleniumbase-cdp/)
[![License](https://img.shields.io/pypi/l/scrapy-seleniumbase-cdp)](https://github.com/nyg/scrapy-seleniumbase-cdp/blob/master/LICENSE)
[![Downloads](https://img.shields.io/pypi/dm/scrapy-seleniumbase-cdp)](https://pypi.org/project/scrapy-seleniumbase-cdp/)

Scrapy downloader middleware that uses [SeleniumBase][4]'s pure CDP mode to make
requests, allowing to bypass most anti-bot protections (e.g. CloudFlare).

Using Selenium's pure CDP mode also makes the middleware more platform
independent as no WebDriver is required.

## Installation

```
pip install scrapy-seleniumbase-cdp
```

## Configuration

1. Add the `SeleniumBaseAsyncCDPMiddleware` to the downloader middlewares:
    ```python
    DOWNLOADER_MIDDLEWARES = {
        'scrapy_seleniumbase_cdp.SeleniumBaseAsyncCDPMiddleware': 800
    }
    ```

2. If needed, configuration can be provided to the SeleniumBase browser instance.
   For example, to enable the built-in ad blocker (blocks 30+ ad and tracking
   domains via CDP):

   ```python
   SELENIUMBASE_BROWSER_OPTIONS = {
       'ad_block': True,
   }
   ```

## Usage

To have SeleniumBase handle requests, use the
`scrapy_seleniumbase_cdp.SeleniumBaseRequest` instead of Scrapy's built-in
`Request`:

```python
from scrapy_seleniumbase_cdp import SeleniumBaseRequest

async def start(self):
    yield SeleniumBaseRequest(url=url, callback=self.parse_result)
```

### Additional arguments

The `scrapy_seleniumbase_cdp.SeleniumBaseRequest` accepts additional
arguments. They are executed in the order presented below:

#### `wait_for_element` / `element_timeout`

When used, SeleniumBase will wait for the element with the given CSS selector
to appear. The default timeout value is of 10 seconds but can be changed if
needed. If the element is not found within the timeout, the request is skipped
(Scrapy's `IgnoreRequest` is raised) and a full-page debug screenshot is saved
using SeleniumBase's default path.

```python
yield SeleniumBaseRequest(
    url=url,
    callback=self.parse_result,
    wait_for_element='h1.some-class',
    element_timeout=5,
    page_load_timeout=20))
```

#### `page_load_timeout`

Maximum number of seconds to wait for both the HTTP response and the page load
event before proceeding. If the timeout is reached, a warning is logged but the
request continues. Defaults to `15`.

#### `browser_callback`

If needed, it is possible to provide a callback to interact with the browser
instance and/or its tabs. The return value of the async callback is stored in
`response.meta['callback']`. 

```python
async def start(self):
    async def maximize_window(browser: Browser):
        await browser.main_tab.maximize()

    yield SeleniumBaseRequest(…, browser_callback=maximize_window)
```

#### `script`

When used, SeleniumBase will execute the provided JavaScript code.

```python
yield SeleniumBaseRequest(
    # …
    script='window.scrollTo(0, document.body.scrollHeight)')
```

If the script returns a Promise, it is possible to await its result:

```python
yield SeleniumBaseRequest(
    # …
    script={
        'await_promise': True,
        'script': '''
            document.getElementById('onetrust-accept-btn-handler').click()
            new Promise(resolve => setTimeout(resolve, 1000))
        '''
    })
```

The result of the JavaScript code is stored in `response.meta['script']`.

#### `screenshot`

When used, SeleniumBase will take a screenshot of the page and the binary data
will be stored in `response.meta['screenshot']`:

```python
yield SeleniumBaseRequest(url=url, callback=self.parse_result, screenshot=True)


def parse_result(self, response):
    # …
    with open('image.png', 'wb') as image_file:
        image_file.write(response.meta['screenshot'])
```

You can also specify additional configuration options:

```python
yield SeleniumBaseRequest(…, screenshot={'format': 'jpg', 'full_page': False})
```

Or provide a path to automatically save the screenshot (in this case, the image
data is **not** stored in the response):

```python
yield SeleniumBaseRequest(…, screenshot={'path': 'output/image.png'})
```

Available configuration keys:

- `path`: File path where screenshot will be saved. Use `auto` for
  SeleniumBase default path. Leave empty to return data in response `meta`.
- `format`: Image format, defaults to `png`, `jpg` also available.
- `full_page`: Capture full page or just viewport, defaults to `True`.

#### Captcha handling

After navigating to a page, the middleware waits for both the HTTP response
status and the page load event. It then attempts to solve any captcha present
on the page using SeleniumBase's built-in solver, retrying up to a configurable
maximum number of attempts.

The delay before the first solve attempt and between retries depends on the
HTTP status code:

- **2xx responses**: wait `captcha_delay` seconds (default `0`)
- **Blocked responses** (status in `captcha_blocked_codes`): wait
  `captcha_blocked_delay` seconds (default `4`)

```python
yield SeleniumBaseRequest(
    url=url,
    callback=self.parse_result,
    captcha_delay=1,
    captcha_blocked_delay=5,
    captcha_blocked_codes=[403, 429, 503],
    captcha_max_attempts=5)
```

Available captcha configuration:

- `captcha_delay`: Seconds to wait before solving on a successful response.
  Defaults to `0`.
- `captcha_blocked_delay`: Seconds to wait before solving on a blocked
  response. Defaults to `4`.
- `captcha_blocked_codes`: List of HTTP status codes treated as blocked.
  Defaults to `[403, 429, 503]`.
- `captcha_max_attempts`: Maximum number of solve attempts. Defaults to `3`.
  After exhausting all attempts the middleware continues normally but logs a
  warning.

## Error handling

The middleware checks the HTTP status code right after loading the page to
determine captcha-solving behaviour (see [Captcha handling](#captcha-handling)
above).

- **`wait_for_element` timeout**: if the expected element is not found within
  `element_timeout` seconds, a full-page debug screenshot is saved using
  SeleniumBase's default path and `IgnoreRequest` is raised, causing Scrapy to
  skip the request.

## License

This project is licensed under the MIT License. It is a fork
of [Quartz-Core/scrapy-seleniumbase][1]
which was originally released under the WTFPL.

[1]: https://github.com/Quartz-Core/scrapy-seleniumbase
[4]: https://seleniumbase.io/examples/cdp_mode/ReadMe/
[5]: https://github.com/nyg/autoscout24-trends
