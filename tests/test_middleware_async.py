import pytest
from scrapy.utils.test import get_crawler

from fakes import FakeBrowser, FakeTab, load_complete, response_received
from scrapy_seleniumbase_cdp import SeleniumBaseAsyncCDPMiddleware, SeleniumBaseRequest


async def test_should_return_page_url_body_status_and_cookies_when_page_loads():
    # Given
    url = 'https://example.com/page'
    tab = FakeTab(navigation_events=[response_received(url, 200), load_complete(url)],
                  html='<html><head></head><body>hello</body></html>')
    unit = SeleniumBaseAsyncCDPMiddleware(get_crawler())
    unit.browser = FakeBrowser(tab, cookies={'session': 'abc', 'theme': 'dark'})

    # When
    response = await unit.process_request(SeleniumBaseRequest(url=url))

    # Then
    assert response.url == url
    assert response.text == '<html><head></head><body>hello</body></html>'
    assert response.status == 200
    assert response.headers['Cookie'] == b'session=abc; theme=dark'


async def test_should_return_reloaded_page_status_when_captcha_is_solved():
    # Given
    url = 'https://example.com/page'
    tab = FakeTab(navigation_events=[response_received(url, 403), load_complete(url)],
                  captcha_results=[True, False],
                  events_after_captcha=[response_received(url, 200), load_complete(url)])
    unit = SeleniumBaseAsyncCDPMiddleware(get_crawler())
    unit.browser = FakeBrowser(tab)

    # When
    response = await unit.process_request(SeleniumBaseRequest(url=url, captcha_blocked_delay=0))

    # Then
    assert response.status == 200


async def test_should_return_challenge_status_when_no_captcha_is_solved():
    # Given
    url = 'https://example.com/page'
    tab = FakeTab(navigation_events=[response_received(url, 403), load_complete(url)],
                  captcha_results=[False])
    unit = SeleniumBaseAsyncCDPMiddleware(get_crawler())
    unit.browser = FakeBrowser(tab)

    # When
    response = await unit.process_request(SeleniumBaseRequest(url=url, captcha_blocked_delay=0))

    # Then
    assert response.status == 403


async def test_should_return_redirect_target_url_when_page_redirects():
    # Given
    url = 'https://example.com/old'
    target_url = 'https://example.com/new'
    tab = FakeTab(navigation_events=[response_received(target_url, 200), load_complete(target_url)],
                  redirect_to=target_url)
    unit = SeleniumBaseAsyncCDPMiddleware(get_crawler())
    unit.browser = FakeBrowser(tab)
    # The target's events don't match the request URL, so the page-load wait runs until its timeout (#81).
    request = SeleniumBaseRequest(url=url, page_load_timeout=0)

    # When
    response = await unit.process_request(request)

    # Then
    assert response.url == target_url
    assert response.status == 200


async def test_should_log_warning_and_return_status_200_when_page_load_times_out_without_response(caplog):
    # Given
    url = 'https://example.com/page'
    tab = FakeTab(navigation_events=[load_complete(url)])
    unit = SeleniumBaseAsyncCDPMiddleware(get_crawler())
    unit.browser = FakeBrowser(tab)

    # When
    response = await unit.process_request(SeleniumBaseRequest(url=url, page_load_timeout=0))

    # Then
    assert response.url == url
    assert response.status == 200
    assert f'timed out waiting for page to load: {url}' in caplog.text


async def test_should_try_captcha_once_when_no_captcha_is_detected():
    # Given
    url = 'https://example.com/page'
    tab = FakeTab(navigation_events=[response_received(url, 200), load_complete(url)],
                  captcha_results=[False])
    unit = SeleniumBaseAsyncCDPMiddleware(get_crawler())
    unit.browser = FakeBrowser(tab)

    # When
    await unit.process_request(SeleniumBaseRequest(url=url))

    # Then
    assert tab.solve_captcha_calls == 1


async def test_should_stop_captcha_loop_when_captcha_is_no_longer_detected(caplog):
    # Given
    url = 'https://example.com/page'
    tab = FakeTab(navigation_events=[response_received(url, 200), load_complete(url)],
                  captcha_results=[True, True, False])
    unit = SeleniumBaseAsyncCDPMiddleware(get_crawler())
    unit.browser = FakeBrowser(tab)

    # When
    await unit.process_request(SeleniumBaseRequest(url=url, captcha_max_attempts=5))

    # Then
    assert tab.solve_captcha_calls == 3
    assert 'max captcha solve attempts' not in caplog.text


async def test_should_stop_captcha_loop_and_log_warning_when_max_attempts_are_reached(caplog):
    # Given
    url = 'https://example.com/page'
    tab = FakeTab(navigation_events=[response_received(url, 200), load_complete(url)],
                  captcha_results=[True, True, True, True])
    unit = SeleniumBaseAsyncCDPMiddleware(get_crawler())
    unit.browser = FakeBrowser(tab)

    # When
    await unit.process_request(SeleniumBaseRequest(url=url, captcha_max_attempts=3))

    # Then
    assert tab.solve_captcha_calls == 3
    assert f'max captcha solve attempts (3) reached for {url}' in caplog.text


async def test_should_store_error_screenshot_and_raise_when_element_is_not_found():
    # Given
    url = 'https://example.com/page'
    tab = FakeTab(navigation_events=[response_received(url, 200), load_complete(url)],
                  element_found=False,
                  screenshot=b'error page')
    unit = SeleniumBaseAsyncCDPMiddleware(get_crawler())
    unit.browser = FakeBrowser(tab)
    request = SeleniumBaseRequest(url=url, wait_for_element='#content', element_timeout=1)

    # When
    with pytest.raises(TimeoutError):
        await unit.process_request(request)

    # Then
    assert request.meta['error_screenshot'] == b'error page'


async def test_should_log_error_and_return_response_when_browser_callback_fails(caplog):
    # Given
    url = 'https://example.com/page'
    tab = FakeTab(navigation_events=[response_received(url, 200), load_complete(url)])
    unit = SeleniumBaseAsyncCDPMiddleware(get_crawler())
    unit.browser = FakeBrowser(tab)

    async def failing_callback(browser):
        raise RuntimeError('callback failed')

    # When
    response = await unit.process_request(SeleniumBaseRequest(url=url, browser_callback=failing_callback))

    # Then
    assert response.status == 200
    assert 'Error executing browser callback: callback failed' in caplog.text


async def test_should_log_error_and_return_response_when_script_fails(caplog):
    # Given
    url = 'https://example.com/page'
    tab = FakeTab(navigation_events=[response_received(url, 200), load_complete(url)],
                  script_error=RuntimeError('script failed'))
    unit = SeleniumBaseAsyncCDPMiddleware(get_crawler())
    unit.browser = FakeBrowser(tab)

    # When
    response = await unit.process_request(SeleniumBaseRequest(url=url, script='document.title'))

    # Then
    assert response.status == 200
    assert 'Error executing script: script failed' in caplog.text


async def test_should_log_error_and_return_response_when_screenshot_fails(caplog):
    # Given
    url = 'https://example.com/page'
    tab = FakeTab(navigation_events=[response_received(url, 200), load_complete(url)],
                  screenshot_error=RuntimeError('screenshot failed'))
    unit = SeleniumBaseAsyncCDPMiddleware(get_crawler())
    unit.browser = FakeBrowser(tab)

    # When
    response = await unit.process_request(SeleniumBaseRequest(url=url, screenshot=True))

    # Then
    assert response.status == 200
    assert 'Error taking screenshot: screenshot failed' in caplog.text
