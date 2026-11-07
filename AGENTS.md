# AGENTS.md

Scrapy downloader middleware that loads each `SeleniumBaseRequest` in one shared Chrome driven by SeleniumBase's pure CDP mode (no WebDriver); other requests go through Scrapy's own downloader. Read `docs/ARCHITECTURE.md` before changing the request pipeline in `scrapy_seleniumbase_cdp/middleware_async.py`. `README.md` is the user documentation.

## Tests

```bash
pip install -e . --group test   # --group needs pip 25.1+
pytest
```

- The tests drive `SeleniumBaseAsyncCDPMiddleware.process_request` through the fake `Tab` and `Browser` in `tests/fakes.py`, which hand real `mycdp` `ResponseReceived` and `LoadComplete` events to the middleware's handlers, so no Chrome is needed. When a test needs new browser behaviour, add it to the fakes.
- Each test is self-contained: it builds its own `FakeTab` and middleware (named `unit`), is named `test_should_<expectation>_when_<condition>`, and is split by bare `# Given`, `# When`, `# Then` comments.
- `.github/workflows/run-tests.yml` runs the suite on Python 3.11 and the latest 3.x for every pull request and push to `master`.

## Code conventions

- Python 3.11 is the minimum: `request.py` imports `typing.NotRequired`.
- SeleniumBase's sync CDP API runs its own event loop, which cannot run inside Scrapy's, so the middleware awaits the async `cdp_driver` API.
- A new `SeleniumBaseRequest` argument goes in three places: `__init__`, `SeleniumBaseRequest.attributes` (Scrapy's `Request.replace()` and `to_dict()` copy only the names listed there), and `README.md`.
- The optional post-load steps (browser callback, script, screenshot, error screenshot) are wrapped in `_handle_errors`, which logs the exception and lets the response through. A `wait_for_element` timeout is the one step that fails the request: it stores `request.meta['error_screenshot']` and re-raises `TimeoutError`.
- Log through the module logger, `scrapy_seleniumbase_cdp.middleware_async`: `debug` for routine steps, `warning` when processing carries on past a problem (page-load timeout, exhausted captcha attempts), `error` when a step fails. Write new messages in lowercase and include the request URL.

## Commits, pull requests and releases

- Commit subjects follow Conventional Commits; `git-cliff` (`cliff.toml`) groups the changelog by type. Pull requests are squash-merged, so the PR title becomes the changelog line.
- Work on a branch and open the pull request against `master`.
- Pin GitHub Actions to a commit digest followed by a version comment; Renovate keeps them current.
- The two `version` fields in `pyproject.toml` (`[project]` and `[tool.commitizen]`) belong to the release workflows: `bump-version-create-tag.yml` (run by hand) runs `cz bump` and pushes a `vX.Y.Z` tag, `create-gh-release.yml` builds the package and creates the GitHub release, and `publish-to-pypi.yml` uploads it to PyPI with trusted publishing.
