# Copilot Instructions

## Project Overview

This is a Scrapy downloader middleware that uses SeleniumBase's **pure CDP mode** (Chrome DevTools Protocol, no WebDriver) to bypass anti-bot protections. It consists of exactly three source files in `scrapy_seleniumbase_cdp/`.

## Build & Install

```bash
pip install build
python -m build        # produces dist/ artifacts
pip install -e .       # editable install for development
```

There are no tests or linter configs in this project.

## Release Workflow

Releases are fully automated via GitHub Actions (three chained workflows):

1. **`tag.yml`** — triggered manually via `workflow_dispatch`; uses `commitizen` (`cz bump`) to bump `version` in `pyproject.toml` and push a `vX.Y.Z` tag.
2. **`release.yml`** — triggered on tag push; builds the package and generates a changelog with `git-cliff`, then creates a GitHub Release with the dist assets.
3. **`publish.yml`** — triggered on GitHub Release published; uploads dist assets to PyPI using trusted publishing (no token needed).

Changelog entries are driven by **Conventional Commits** (feat, fix, refactor, etc.) — follow this format for all commit messages.

## Architecture

The package exposes two public symbols (re-exported from `__init__.py`):

- **`SeleniumBaseRequest`** (`request.py`) — subclass of Scrapy's `Request`. Accepts extra kwargs: `wait_for_element`, `element_timeout`, `browser_callback`, `script`, `screenshot`, `page_load_timeout`, `captcha_delay`, `captcha_blocked_delay`, `captcha_blocked_codes`, `captcha_max_attempts`. The `script` arg is normalised to a `ScriptConfig` dict in `__init__` via a `match` statement. `screenshot=True` is coerced to `{'format': 'png', 'full_page': True}`.

- **`SeleniumBaseAsyncCDPMiddleware`** (`middleware_async.py`) — async Scrapy downloader middleware. Key behaviours:
  - Returns `None` immediately for any request that is **not** a `SeleniumBaseRequest` (lets Scrapy handle it normally).
  - Holds a single `Browser` instance (from `seleniumbase.undetected.cdp_driver`) shared across all requests; started in `spider_opened`, stopped in `spider_closed`.
  - `__init__` takes only a `Crawler` and reads the `SELENIUMBASE_BROWSER_OPTIONS` setting from it (dict of kwargs forwarded to `cdp_driver.start_async`).
  - **Event-driven page load**: after `browser.get()`, two `asyncio.Event`s are awaited — one for the HTTP response status (`ResponseReceived`) and one for page load (`LoadComplete`). Both are gathered with `asyncio.wait_for(timeout=request.page_load_timeout)`. On timeout, processing continues with a warning.
  - **Captcha solving loop**: after page load, a delay is applied based on the HTTP status code (`captcha_delay` for 2xx, `captcha_blocked_delay` for codes in `captcha_blocked_codes`). Then `tab.solve_captcha()` is called in a loop up to `captcha_max_attempts` times, sleeping `delay` seconds between each attempt. If max attempts are exhausted, a warning is logged and processing continues.
  - **`_wait_for_element` timeout**: raises `IgnoreRequest` (after taking a debug screenshot), which causes Scrapy to skip the request.
  - Per-request results are stored in `response.meta`: `'callback'`, `'script'`, `'screenshot'`.
  - Errors in `_execute_callback`, `_execute_script`, and `_take_screenshot` are caught by the `@_handle_errors` decorator (a `@staticmethod` on the class that accesses the spider via `self.crawler.spider`) and logged — they do **not** abort the request.

## Key Conventions

- **Python 3.10+** is required; the codebase uses `match`/`case` and `TypedDict` with `NotRequired`.
- The middleware must use async/await (`cdp_driver`'s async API) because pure CDP mode has its own event loop that conflicts with Scrapy's Twisted loop.
- `SeleniumBaseRequest` kwargs mirror the README documentation exactly — keep them in sync when adding new features.
- Version is maintained solely in `pyproject.toml` under `[project] version`; `commitizen` updates it automatically — do not edit it manually.
