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

2. If needed, configuration can be provided to the SeleniumBase browser instance:

   ```python
   SELENIUMBASE_BROWSER_OPTIONS = {
       # …
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

The `scrapy_seleniumbase_cdp.SeleniumBaseRequest` accepts five additional
arguments. They are executed in the order presented below:

#### `wait_for` / `wait_timeout`

When used, SeleniumBase will wait for the element with the given CSS selector
to appear. The default timeout value is of 10 seconds but can be changed if
needed.

```python
yield SeleniumBaseRequest(
    url=url,
    callback=self.parse_result,
    wait_for='h1.some-class',
    wait_timeout=5))
```

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

## License

This project is licensed under the MIT License. It is a fork
of [Quartz-Core/scrapy-seleniumbase][1]
which was originally released under the WTFPL.

[1]: https://github.com/Quartz-Core/scrapy-seleniumbase
[4]: https://seleniumbase.io/examples/cdp_mode/ReadMe/
[5]: https://github.com/nyg/autoscout24-trends
