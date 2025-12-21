# scrapy-seleniumbase-cdp

[![PyPI](https://img.shields.io/pypi/v/scrapy-seleniumbase-cdp)](https://pypi.org/project/scrapy-seleniumbase-cdp/)
[![Python Versions](https://img.shields.io/pypi/pyversions/scrapy-seleniumbase-cdp)](https://pypi.org/project/scrapy-seleniumbase-cdp/)
[![License](https://img.shields.io/pypi/l/scrapy-seleniumbase-cdp)](https://github.com/nyg/scrapy-seleniumbase-cdp/blob/master/LICENSE)
[![Downloads](https://img.shields.io/pypi/dm/scrapy-seleniumbase-cdp)](https://pypi.org/project/scrapy-seleniumbase-cdp/)

Scrapy downloader middleware that uses [SeleniumBase][4]'s pure CDP mode to make
requests, allowing to bypass most anti-bot protections (e.g. CloudFlare).

Using Selenium's pure CDP mode also makes the middleware more platform
independent as no WebDriver is required.

🚧 Work in progress, see working example [here][5]. 🚧

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

2. If needed, Driver configuration can be provided:

   ```python
   SELENIUMBASE_DRIVER_KWARGS = {
       # …
   }
   ```

## Usage

Use the `scrapy_seleniumbase_cdp.SeleniumBaseRequest` instead of the scrapy
built-in `Request` like below:

```python
from scrapy_seleniumbase_cdp import SeleniumBaseRequest

async def start(self):
    yield SeleniumBaseRequest(url=url, callback=self.parse_result)
```

The request will be handled by SeleniumBase, and the request will have an
additional `meta` key, named `driver` containing the SeleniumBase driver with
the request processed.

```python
def parse_result(self, response):
    print(response.request.meta['driver'].title)
```

For more information about the available driver methods and attributes, refer to
the [selenium python documentation][1] (all vanilla selenium driver methods are
available) and [seleniumbase documentation][2] (look for "driver" specific
methods, located at the end of the page).

The `selector` response attribute work as usual (but contains the HTML processed
by the selenium driver).

```python
def parse_result(self, response):
    print(response.selector.xpath('//title/@text'))
```

### Additional arguments

The `scrapy_selenium.SeleniumBaseRequest` accept 5 additional arguments:

#### `wait_time` / `wait_until`

When used, SeleniumBase will wait for the element to be selectable before
returning the response to the spider.

```python
yield SeleniumBaseRequest(
    url=url,
    callback=self.parse_result,
    wait_time=10,
    wait_until='h1.some-class'))
```

#### `screenshot`

When used, SeleniumBase will take a screenshot of the page and the binary data
will be added to the response `meta`:

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
data is **not** added to the response `meta`):

```python
yield SeleniumBaseRequest(…, screenshot={'path': 'output/image.png'})
```

Available configuration keys:

- `path`: File path where screenshot will be saved. Use `auto` for
  SeleniumBase default path. Leave empty to return data in response `meta`.
- `format`: Image format, defaults to `png`, `jpg` also available. 
- `full_page`: Capture full page or just viewport, defaults to `True`.

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

#### `driver_methods`

**Not implemented**

When used, seleniumbase webdriver will execute methods, provided as strings in a
list, before returning page's HTML.

```python
def start_requests(self):
    for url in self.start_urls:
        yield SeleniumRequest(
            url=url,
            driver_methods=['''.find_element("xpath","some_xpath").click()''']))
```

## License

This project is licensed under the MIT License. It is a fork
of [Quartz-Core/scrapy-seleniumbase](https://github.com/Quartz-Core/scrapy-seleniumbase)
which was originally released under the WTFPL.

[1]: http://selenium-python.readthedocs.io/api.html#module-selenium.webdriver.remote.webdriver
[2]: https://seleniumbase.io/help_docs/method_summary/#seleniumbase-methods-api-reference
[4]: https://seleniumbase.io/examples/cdp_mode/ReadMe/
[5]: https://github.com/nyg/autoscout24-trends
