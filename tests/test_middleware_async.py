import asyncio

import pytest
from mycdp.network import ResourceType
from scrapy.utils.test import get_crawler

from fakes import IFRAME_ID, FakeBrowser, FakeTab, cookie, load_event_fired, response_received
from scrapy_seleniumbase_cdp import SeleniumBaseAsyncCDPMiddleware, SeleniumBaseRequest


async def test_should_return_page_url_body_and_status_when_page_loads():
    # Given
    url = 'https://example.com/page'
    tab = FakeTab(navigation_events=[response_received(url, 200), load_event_fired()],
                  html='<html><head></head><body>hello</body></html>')
    unit = SeleniumBaseAsyncCDPMiddleware(get_crawler())
    unit.tab = tab

    # When
    response = await unit.process_request(SeleniumBaseRequest(url=url))

    # Then
    assert response.url == url
    assert response.text == '<html><head></head><body>hello</body></html>'
    assert response.status == 200


async def test_should_store_only_page_url_cookies_in_meta_when_browser_holds_other_domains_cookies():
    # Given
    url = 'https://example.com/page'
    page_cookies = [cookie('session', 'abc', 'example.com'), cookie('theme', 'dark', '.example.com')]
    tab = FakeTab(navigation_events=[response_received(url, 200), load_event_fired()],
                  cookies_by_url={url: page_cookies, 'https://ads.example.net/frame': [cookie('tracker', 'xyz', 'ads.example.net')]})
    unit = SeleniumBaseAsyncCDPMiddleware(get_crawler())
    unit.tab = tab

    # When
    response = await unit.process_request(SeleniumBaseRequest(url=url))

    # Then
    assert response.meta['cookies'] == page_cookies
    assert 'Cookie' not in response.headers


async def test_should_load_page_in_request_tab_when_browser_has_newer_tab():
    # Given
    url = 'https://example.com/page'
    tab = FakeTab(navigation_events=[response_received(url, 200), load_event_fired()])
    newer_tab = FakeTab()
    unit = SeleniumBaseAsyncCDPMiddleware(get_crawler())
    unit.browser = FakeBrowser(tab, newer_tab)
    unit.tab = tab

    # When
    response = await unit.process_request(SeleniumBaseRequest(url=url, page_load_timeout=0.05))

    # Then
    assert response.status == 200
    assert newer_tab.location == 'about:blank'


async def test_should_return_each_request_its_own_page_when_requests_are_processed_concurrently():
    # Given
    url = 'https://example.com/page'
    other_url = 'https://example.com/other'
    tab = FakeTab(navigation_events=[response_received(url, 200), load_event_fired()])
    unit = SeleniumBaseAsyncCDPMiddleware(get_crawler())
    unit.tab = tab

    # When
    response, other_response = await asyncio.gather(unit.process_request(SeleniumBaseRequest(url=url)),
                                                    unit.process_request(SeleniumBaseRequest(url=other_url)))

    # Then
    assert response.url == url
    assert other_response.url == other_url


async def test_should_load_next_page_in_same_tab_when_no_cdp_error_occurred():
    # Given
    url = 'https://example.com/page'
    next_url = 'https://example.com/next'
    tab = FakeTab(navigation_events=[response_received(url, 200), load_event_fired()])
    browser = FakeBrowser(tab)
    unit = SeleniumBaseAsyncCDPMiddleware(get_crawler())
    unit.browser = browser
    unit.tab = await browser.get('about:blank')
    await unit.process_request(SeleniumBaseRequest(url=url))

    # When
    await unit.process_request(SeleniumBaseRequest(url=next_url))

    # Then
    assert tab.location == next_url
    assert browser.targets == [tab]


async def test_should_return_next_page_when_cdp_error_closed_tab_session():
    # Given
    url = 'https://example.com/page'
    next_url = 'https://example.com/next'
    tab = FakeTab(navigation_events=[response_received(url, 200), load_event_fired()],
                  failing_methods={'Page.captureScreenshot'})
    new_tab = FakeTab(navigation_events=[response_received(next_url, 200), load_event_fired()])
    browser = FakeBrowser(tab, new_tabs=[new_tab])
    unit = SeleniumBaseAsyncCDPMiddleware(get_crawler())
    unit.browser = browser
    unit.tab = await browser.get('about:blank')
    await unit.process_request(SeleniumBaseRequest(url=url, screenshot=True))

    # When
    response = await unit.process_request(SeleniumBaseRequest(url=next_url, page_load_timeout=0.05))

    # Then
    assert response.url == next_url
    assert response.status == 200


async def test_should_load_next_page_in_new_tab_with_browser_user_agent_when_cdp_error_closed_tab_session():
    # Given
    url = 'https://example.com/page'
    next_url = 'https://example.com/next'
    tab = FakeTab(navigation_events=[response_received(url, 200), load_event_fired()],
                  failing_methods={'Page.captureScreenshot'})
    new_tab = FakeTab(navigation_events=[response_received(next_url, 200), load_event_fired()])
    browser = FakeBrowser(tab, new_tabs=[new_tab], user_agent='Mozilla/5.0 (crawler)')
    unit = SeleniumBaseAsyncCDPMiddleware(get_crawler())
    unit.browser = browser
    unit.tab = await browser.get('about:blank')
    await unit.process_request(SeleniumBaseRequest(url=url, screenshot=True))

    # When
    await unit.process_request(SeleniumBaseRequest(url=next_url))

    # Then
    assert new_tab.location == next_url
    assert new_tab.navigations[-1].user_agent == 'Mozilla/5.0 (crawler)'


async def test_should_close_tab_when_cdp_error_closed_its_session():
    # Given
    url = 'https://example.com/page'
    next_url = 'https://example.com/next'
    tab = FakeTab(navigation_events=[response_received(url, 200), load_event_fired()],
                  failing_methods={'Page.captureScreenshot'})
    new_tab = FakeTab(navigation_events=[response_received(next_url, 200), load_event_fired()])
    browser = FakeBrowser(tab, new_tabs=[new_tab])
    unit = SeleniumBaseAsyncCDPMiddleware(get_crawler())
    unit.browser = browser
    unit.tab = await browser.get('about:blank')
    await unit.process_request(SeleniumBaseRequest(url=url, screenshot=True))

    # When
    await unit.process_request(SeleniumBaseRequest(url=next_url))

    # Then
    assert browser.targets == [new_tab]


async def test_should_send_referer_header_as_navigation_referrer_when_request_has_referer():
    # Given
    url = 'https://example.com/page'
    tab = FakeTab(navigation_events=[response_received(url, 200), load_event_fired()])
    unit = SeleniumBaseAsyncCDPMiddleware(get_crawler())
    unit.tab = tab

    # When
    await unit.process_request(SeleniumBaseRequest(url=url, headers={'Referer': 'https://example.com/list'}))

    # Then
    assert tab.navigations[-1].referrer == 'https://example.com/list'


async def test_should_log_warning_and_return_page_when_request_method_is_post(caplog):
    # Given
    url = 'https://example.com/search'
    tab = FakeTab(navigation_events=[response_received(url, 200), load_event_fired()])
    unit = SeleniumBaseAsyncCDPMiddleware(get_crawler())
    unit.tab = tab

    # When
    response = await unit.process_request(SeleniumBaseRequest(url=url, method='POST', body='q=cars'))

    # Then
    assert response.status == 200
    assert f'POST request loaded as GET, without its body: {url}' in caplog.text


async def test_should_return_reloaded_page_status_when_captcha_is_solved():
    # Given
    url = 'https://example.com/page'
    tab = FakeTab(navigation_events=[response_received(url, 403), load_event_fired()],
                  captcha_results=[True, False],
                  events_after_captcha=[response_received(url, 200), load_event_fired()])
    unit = SeleniumBaseAsyncCDPMiddleware(get_crawler())
    unit.tab = tab

    # When
    response = await unit.process_request(SeleniumBaseRequest(url=url, captcha_blocked_delay=0))

    # Then
    assert response.status == 200


async def test_should_return_challenge_status_when_no_captcha_is_solved():
    # Given
    url = 'https://example.com/page'
    tab = FakeTab(navigation_events=[response_received(url, 403), load_event_fired()],
                  captcha_results=[False])
    unit = SeleniumBaseAsyncCDPMiddleware(get_crawler())
    unit.tab = tab

    # When
    response = await unit.process_request(SeleniumBaseRequest(url=url, captcha_blocked_delay=0))

    # Then
    assert response.status == 403


async def test_should_return_redirect_target_url_and_status_when_page_redirects():
    # Given
    url = 'https://example.com/old'
    target_url = 'https://example.com/new'
    tab = FakeTab(navigation_events=[response_received(target_url, 404), load_event_fired()],
                  redirect_to=target_url)
    unit = SeleniumBaseAsyncCDPMiddleware(get_crawler())
    unit.tab = tab

    # When
    response = await unit.process_request(SeleniumBaseRequest(url=url))

    # Then
    assert response.url == target_url
    assert response.status == 404


async def test_should_refresh_tab_cached_url_when_page_redirects():
    # Given
    url = 'https://example.com/old'
    target_url = 'https://example.com/new'
    tab = FakeTab(navigation_events=[response_received(target_url, 200), load_event_fired()],
                  redirect_to=target_url)
    unit = SeleniumBaseAsyncCDPMiddleware(get_crawler())
    unit.tab = tab

    # When
    await unit.process_request(SeleniumBaseRequest(url=url))

    # Then
    assert tab.target.url == target_url


async def test_should_return_main_frame_status_when_iframe_document_url_is_part_of_request_url():
    # Given
    url = 'https://example.com/page'
    tab = FakeTab(navigation_events=[response_received(url, 200),
                                     response_received('https://example.com/', 403, frame_id=IFRAME_ID),
                                     load_event_fired()])
    unit = SeleniumBaseAsyncCDPMiddleware(get_crawler())
    unit.tab = tab

    # When
    response = await unit.process_request(SeleniumBaseRequest(url=url, captcha_blocked_delay=0))

    # Then
    assert response.status == 200


async def test_should_return_document_status_when_main_frame_subresource_follows_document():
    # Given
    url = 'https://example.com/page'
    tab = FakeTab(navigation_events=[response_received(url, 404),
                                     response_received('https://example.com/favicon.ico', 200, resource_type=ResourceType.OTHER),
                                     load_event_fired()])
    unit = SeleniumBaseAsyncCDPMiddleware(get_crawler())
    unit.tab = tab

    # When
    response = await unit.process_request(SeleniumBaseRequest(url=url))

    # Then
    assert response.status == 404


async def test_should_log_warning_and_return_response_when_load_event_does_not_fire(caplog):
    # Given
    url = 'https://example.com/page'
    tab = FakeTab(navigation_events=[response_received(url, 200)])
    unit = SeleniumBaseAsyncCDPMiddleware(get_crawler())
    unit.tab = tab

    # When
    response = await unit.process_request(SeleniumBaseRequest(url=url, page_load_timeout=0.05))

    # Then
    assert response.status == 200
    assert f'timed out waiting for page to load: {url}' in caplog.text


async def test_should_log_error_and_raise_timeout_error_when_no_document_response_arrives(caplog):
    # Given
    url = 'https://example.com/page'
    tab = FakeTab(navigation_events=[load_event_fired()])
    unit = SeleniumBaseAsyncCDPMiddleware(get_crawler())
    unit.tab = tab

    # When
    with pytest.raises(TimeoutError) as error:
        await unit.process_request(SeleniumBaseRequest(url=url, page_load_timeout=0))

    # Then
    assert str(error.value) == f'no document response within 0s: {url}'
    assert f'no document response within 0s: {url}' in caplog.text


async def test_should_try_captcha_once_when_no_captcha_is_detected():
    # Given
    url = 'https://example.com/page'
    tab = FakeTab(navigation_events=[response_received(url, 200), load_event_fired()],
                  captcha_results=[False])
    unit = SeleniumBaseAsyncCDPMiddleware(get_crawler())
    unit.tab = tab

    # When
    await unit.process_request(SeleniumBaseRequest(url=url))

    # Then
    assert tab.solve_captcha_calls == 1


async def test_should_stop_captcha_loop_when_captcha_is_no_longer_detected(caplog):
    # Given
    url = 'https://example.com/page'
    tab = FakeTab(navigation_events=[response_received(url, 200), load_event_fired()],
                  captcha_results=[True, True, False],
                  events_after_captcha=[response_received(url, 200), load_event_fired()])
    unit = SeleniumBaseAsyncCDPMiddleware(get_crawler())
    unit.tab = tab

    # When
    await unit.process_request(SeleniumBaseRequest(url=url, captcha_max_attempts=5))

    # Then
    assert tab.solve_captcha_calls == 3
    assert 'max captcha solve attempts' not in caplog.text


async def test_should_stop_captcha_loop_and_log_warning_when_max_attempts_are_reached(caplog):
    # Given
    url = 'https://example.com/page'
    tab = FakeTab(navigation_events=[response_received(url, 200), load_event_fired()],
                  captcha_results=[True, True, True, True],
                  events_after_captcha=[response_received(url, 429), load_event_fired()])
    unit = SeleniumBaseAsyncCDPMiddleware(get_crawler())
    unit.tab = tab

    # When
    await unit.process_request(SeleniumBaseRequest(url=url, captcha_blocked_delay=0, captcha_max_attempts=3))

    # Then
    assert tab.solve_captcha_calls == 3
    assert f'max captcha solve attempts (3) reached for {url}' in caplog.text


async def test_should_log_error_and_raise_connection_error_when_tab_loses_session_while_solving_captcha(caplog):
    # Given
    url = 'https://example.com/page'
    tab = FakeTab(navigation_events=[response_received(url, 403), load_event_fired()],
                  captcha_results=[True, False],
                  cdp_error_in_captcha=True,
                  events_after_captcha=[response_received(url, 200), load_event_fired()])
    unit = SeleniumBaseAsyncCDPMiddleware(get_crawler())
    unit.tab = tab

    # When
    with pytest.raises(ConnectionError):
        await unit.process_request(SeleniumBaseRequest(url=url, captcha_blocked_delay=0, page_load_timeout=0.05))

    # Then
    assert f'request tab lost its devtools session while solving the captcha: {url}' in caplog.text


async def test_should_return_page_when_tab_loses_session_while_finding_no_captcha():
    # Given
    url = 'https://example.com/page'
    tab = FakeTab(navigation_events=[response_received(url, 200), load_event_fired()],
                  captcha_results=[False],
                  cdp_error_in_captcha=True)
    unit = SeleniumBaseAsyncCDPMiddleware(get_crawler())
    unit.tab = tab

    # When
    response = await unit.process_request(SeleniumBaseRequest(url=url))

    # Then
    assert response.status == 200


async def test_should_return_reloaded_page_status_when_reload_arrives_after_captcha_click():
    # Given
    url = 'https://example.com/page'
    tab = FakeTab(navigation_events=[response_received(url, 429), load_event_fired()],
                  captcha_results=[True, False],
                  events_after_captcha=[response_received(url, 200), load_event_fired()],
                  reload_delay=0.05)
    unit = SeleniumBaseAsyncCDPMiddleware(get_crawler())
    unit.tab = tab

    # When
    response = await unit.process_request(SeleniumBaseRequest(url=url, captcha_blocked_delay=0))

    # Then
    assert response.status == 200
    assert tab.solve_captcha_calls == 2


async def test_should_check_captcha_again_after_captcha_delay_when_click_reloads_page_with_unblocked_status():
    # Given
    url = 'https://example.com/page'
    tab = FakeTab(navigation_events=[response_received(url, 429), load_event_fired()],
                  captcha_results=[True, False],
                  events_after_captcha=[response_received(url, 200), load_event_fired()])
    unit = SeleniumBaseAsyncCDPMiddleware(get_crawler())
    unit.tab = tab

    # When
    await unit.process_request(SeleniumBaseRequest(url=url, captcha_delay=0, captcha_blocked_delay=0.2))

    # Then
    first_check, second_check = tab.solve_captcha_times
    assert second_check - first_check < 0.1


async def test_should_try_captcha_again_when_click_does_not_reload_page_within_page_load_timeout():
    # Given
    url = 'https://example.com/page'
    tab = FakeTab(navigation_events=[response_received(url, 200), load_event_fired()],
                  captcha_results=[True, False])
    unit = SeleniumBaseAsyncCDPMiddleware(get_crawler())
    unit.tab = tab

    # When
    await unit.process_request(SeleniumBaseRequest(url=url, page_load_timeout=0.05))

    # Then
    assert tab.solve_captcha_calls == 2


async def test_should_flag_captcha_unsolved_in_meta_when_max_attempts_are_reached():
    # Given
    url = 'https://example.com/page'
    tab = FakeTab(navigation_events=[response_received(url, 429), load_event_fired()],
                  captcha_results=[True, True],
                  events_after_captcha=[response_received(url, 429), load_event_fired()])
    unit = SeleniumBaseAsyncCDPMiddleware(get_crawler())
    unit.tab = tab

    # When
    response = await unit.process_request(SeleniumBaseRequest(url=url, captcha_blocked_delay=0, captcha_max_attempts=2))

    # Then
    assert response.meta['captcha_unsolved'] is True


async def test_should_clear_captcha_unsolved_flag_when_retried_request_solves_captcha():
    # Given
    url = 'https://example.com/page'
    tab = FakeTab(navigation_events=[response_received(url, 429), load_event_fired()],
                  captcha_results=[True, False],
                  events_after_captcha=[response_received(url, 200), load_event_fired()])
    unit = SeleniumBaseAsyncCDPMiddleware(get_crawler())
    unit.tab = tab
    retried_request = SeleniumBaseRequest(url=url, captcha_blocked_delay=0, meta={'captcha_unsolved': True})

    # When
    response = await unit.process_request(retried_request)

    # Then
    assert response.meta['captcha_unsolved'] is False


async def test_should_skip_captcha_without_warning_or_count_when_max_attempts_is_zero(caplog):
    # Given
    url = 'https://example.com/page'
    tab = FakeTab(navigation_events=[response_received(url, 403), load_event_fired()],
                  captcha_results=[True])
    crawler = get_crawler()
    unit = SeleniumBaseAsyncCDPMiddleware(crawler)
    unit.tab = tab

    # When
    await unit.process_request(SeleniumBaseRequest(url=url, captcha_blocked_delay=0, captcha_max_attempts=0))

    # Then
    assert tab.solve_captcha_calls == 0
    assert 'max captcha solve attempts' not in caplog.text
    assert crawler.stats.get_stats() == {'seleniumbase/response_status_count/403': 1}


async def test_should_skip_captcha_check_when_only_when_blocked_and_page_loads_with_unblocked_status():
    # Given
    url = 'https://example.com/page'
    tab = FakeTab(navigation_events=[response_received(url, 200), load_event_fired()],
                  captcha_results=[True])
    crawler = get_crawler()
    unit = SeleniumBaseAsyncCDPMiddleware(crawler)
    unit.tab = tab

    # When
    await unit.process_request(SeleniumBaseRequest(url=url, captcha_only_when_blocked=True))

    # Then
    assert tab.solve_captcha_calls == 0
    assert crawler.stats.get_stats() == {'seleniumbase/response_status_count/200': 1}


async def test_should_clear_captcha_unsolved_flag_when_retried_request_skips_captcha_check():
    # Given
    url = 'https://example.com/page'
    tab = FakeTab(navigation_events=[response_received(url, 200), load_event_fired()])
    unit = SeleniumBaseAsyncCDPMiddleware(get_crawler())
    unit.tab = tab
    retried_request = SeleniumBaseRequest(url=url, captcha_only_when_blocked=True, meta={'captcha_unsolved': True})

    # When
    response = await unit.process_request(retried_request)

    # Then
    assert response.meta['captcha_unsolved'] is False


async def test_should_solve_captcha_when_only_when_blocked_and_page_loads_with_blocked_status():
    # Given
    url = 'https://example.com/page'
    tab = FakeTab(navigation_events=[response_received(url, 429), load_event_fired()],
                  captcha_results=[True, False],
                  events_after_captcha=[response_received(url, 200), load_event_fired()])
    unit = SeleniumBaseAsyncCDPMiddleware(get_crawler())
    unit.tab = tab

    # When
    response = await unit.process_request(SeleniumBaseRequest(url=url, captcha_blocked_delay=0, captcha_only_when_blocked=True))

    # Then
    assert tab.solve_captcha_calls == 2
    assert response.status == 200


async def test_should_count_challenge_status_and_solved_captcha_when_captcha_is_solved():
    # Given
    url = 'https://example.com/page'
    tab = FakeTab(navigation_events=[response_received(url, 403), load_event_fired()],
                  captcha_results=[True, False],
                  events_after_captcha=[response_received(url, 200), load_event_fired()])
    crawler = get_crawler()
    unit = SeleniumBaseAsyncCDPMiddleware(crawler)
    unit.tab = tab

    # When
    await unit.process_request(SeleniumBaseRequest(url=url, captcha_blocked_delay=0))

    # Then
    assert crawler.stats.get_stats() == {
        'seleniumbase/response_status_count/403': 1,
        'captcha/detected': 1,
        'captcha/solved': 1,
    }


async def test_should_count_unsolved_captcha_when_max_attempts_are_reached():
    # Given
    url = 'https://example.com/page'
    tab = FakeTab(navigation_events=[response_received(url, 429), load_event_fired()],
                  captcha_results=[True, True, True],
                  events_after_captcha=[response_received(url, 429), load_event_fired()])
    crawler = get_crawler()
    unit = SeleniumBaseAsyncCDPMiddleware(crawler)
    unit.tab = tab

    # When
    await unit.process_request(SeleniumBaseRequest(url=url, captcha_blocked_delay=0, captcha_max_attempts=3))

    # Then
    assert crawler.stats.get_stats() == {
        'seleniumbase/response_status_count/429': 1,
        'captcha/detected': 1,
        'captcha/unsolved': 1,
    }


async def test_should_count_only_status_when_no_captcha_is_detected():
    # Given
    url = 'https://example.com/page'
    tab = FakeTab(navigation_events=[response_received(url, 200), load_event_fired()],
                  captcha_results=[False])
    crawler = get_crawler()
    unit = SeleniumBaseAsyncCDPMiddleware(crawler)
    unit.tab = tab

    # When
    await unit.process_request(SeleniumBaseRequest(url=url))

    # Then
    assert crawler.stats.get_stats() == {'seleniumbase/response_status_count/200': 1}


async def test_should_not_count_status_when_no_document_response_arrives():
    # Given
    url = 'https://example.com/page'
    tab = FakeTab(navigation_events=[load_event_fired()])
    crawler = get_crawler()
    unit = SeleniumBaseAsyncCDPMiddleware(crawler)
    unit.tab = tab

    # When
    with pytest.raises(TimeoutError):
        await unit.process_request(SeleniumBaseRequest(url=url, page_load_timeout=0))

    # Then
    assert crawler.stats.get_stats() == {}


async def test_should_store_error_screenshot_and_raise_when_element_is_not_found():
    # Given
    url = 'https://example.com/page'
    tab = FakeTab(navigation_events=[response_received(url, 200), load_event_fired()],
                  element_found=False,
                  screenshot=b'error page')
    unit = SeleniumBaseAsyncCDPMiddleware(get_crawler())
    unit.tab = tab
    request = SeleniumBaseRequest(url=url, wait_for_element='#content', element_timeout=1)

    # When
    with pytest.raises(TimeoutError):
        await unit.process_request(request)

    # Then
    assert request.meta['error_screenshot'] == b'error page'


async def test_should_store_error_screenshot_when_element_is_not_found_and_screenshot_format_is_jpg():
    # Given
    url = 'https://example.com/page'
    tab = FakeTab(navigation_events=[response_received(url, 200), load_event_fired()],
                  element_found=False,
                  screenshot=b'error page')
    unit = SeleniumBaseAsyncCDPMiddleware(get_crawler())
    unit.tab = tab
    request = SeleniumBaseRequest(url=url, wait_for_element='#content', element_timeout=1, screenshot={'format': 'jpg'})

    # When
    with pytest.raises(TimeoutError):
        await unit.process_request(request)

    # Then
    assert request.meta['error_screenshot'] == b'error page'


async def test_should_log_and_count_error_and_return_response_when_browser_callback_fails(caplog):
    # Given
    url = 'https://example.com/page'
    tab = FakeTab(navigation_events=[response_received(url, 200), load_event_fired()])
    crawler = get_crawler()
    unit = SeleniumBaseAsyncCDPMiddleware(crawler)
    unit.tab = tab

    async def failing_callback(browser):
        raise RuntimeError('callback failed')

    # When
    response = await unit.process_request(SeleniumBaseRequest(url=url, browser_callback=failing_callback))

    # Then
    assert response.status == 200
    assert 'Error executing browser callback: callback failed' in caplog.text
    assert crawler.stats.get_value('seleniumbase/browser_callback_failed') == 1


async def test_should_log_and_count_error_and_return_response_when_script_fails(caplog):
    # Given
    url = 'https://example.com/page'
    tab = FakeTab(navigation_events=[response_received(url, 200), load_event_fired()],
                  script_error=RuntimeError('script failed'))
    crawler = get_crawler()
    unit = SeleniumBaseAsyncCDPMiddleware(crawler)
    unit.tab = tab

    # When
    response = await unit.process_request(SeleniumBaseRequest(url=url, script='document.title'))

    # Then
    assert response.status == 200
    assert 'Error executing script: script failed' in caplog.text
    assert crawler.stats.get_value('seleniumbase/script_failed') == 1


async def test_should_log_and_count_error_and_return_response_when_screenshot_fails(caplog):
    # Given
    url = 'https://example.com/page'
    tab = FakeTab(navigation_events=[response_received(url, 200), load_event_fired()],
                  screenshot_error=RuntimeError('screenshot failed'))
    crawler = get_crawler()
    unit = SeleniumBaseAsyncCDPMiddleware(crawler)
    unit.tab = tab

    # When
    response = await unit.process_request(SeleniumBaseRequest(url=url, screenshot=True))

    # Then
    assert response.status == 200
    assert 'Error taking screenshot: screenshot failed' in caplog.text
    assert crawler.stats.get_value('seleniumbase/screenshot_failed') == 1


async def test_should_store_screenshot_when_format_is_jpg():
    # Given
    url = 'https://example.com/page'
    tab = FakeTab(navigation_events=[response_received(url, 200), load_event_fired()],
                  screenshot=b'jpeg image')
    unit = SeleniumBaseAsyncCDPMiddleware(get_crawler())
    unit.tab = tab

    # When
    response = await unit.process_request(SeleniumBaseRequest(url=url, screenshot={'format': 'jpg'}))

    # Then
    assert response.meta['screenshot'] == b'jpeg image'


async def test_should_count_error_and_raise_timeout_error_when_error_screenshot_fails():
    # Given
    url = 'https://example.com/page'
    tab = FakeTab(navigation_events=[response_received(url, 200), load_event_fired()],
                  element_found=False,
                  screenshot_error=RuntimeError('screenshot failed'))
    crawler = get_crawler()
    unit = SeleniumBaseAsyncCDPMiddleware(crawler)
    unit.tab = tab

    # When
    with pytest.raises(TimeoutError):
        await unit.process_request(SeleniumBaseRequest(url=url, wait_for_element='#content', element_timeout=1))

    # Then
    assert crawler.stats.get_value('seleniumbase/error_screenshot_failed') == 1
