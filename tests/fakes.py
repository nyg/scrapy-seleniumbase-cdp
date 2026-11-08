import asyncio
from base64 import b64encode
from collections import defaultdict
from types import SimpleNamespace

from mycdp import network, page
from mycdp.network import Headers, LoaderId, MonotonicTime, RequestId, ResourceType, Response, ResponseReceived
from mycdp.page import FrameId, LoadEventFired
from mycdp.security import SecurityState
from mycdp.target import TargetID

MAIN_FRAME_ID = 'main-frame'
IFRAME_ID = 'iframe'
SCREENSHOT_FORMATS = ('jpeg', 'png', 'webp')


def response_received(url: str,
                      status: int,
                      frame_id: str = MAIN_FRAME_ID,
                      resource_type: ResourceType = ResourceType.DOCUMENT) -> ResponseReceived:
    return ResponseReceived(
        request_id=RequestId('1'),
        loader_id=LoaderId('1'),
        timestamp=MonotonicTime(0),
        type_=resource_type,
        response=Response(
            url=url,
            status=status,
            status_text='',
            headers=Headers({}),
            mime_type='text/html',
            charset='utf-8',
            connection_reused=False,
            connection_id=0,
            encoded_data_length=0,
            security_state=SecurityState.SECURE,
        ),
        has_extra_info=False,
        frame_id=FrameId(frame_id),
    )


def load_event_fired() -> LoadEventFired:
    return LoadEventFired(timestamp=MonotonicTime(0))


def cookie(name: str, value: str, domain: str) -> dict:
    return {'name': name, 'value': value, 'domain': domain, 'path': '/', 'size': len(name + value), 'httpOnly': False, 'secure': True,
            'session': True, 'priority': 'Medium', 'sourceScheme': 'Secure', 'sourcePort': 443}


def _respond(command, result: dict):
    try:
        command.send(result)
    except StopIteration as stop:
        return stop.value


class FakeTab:

    def __init__(self,
                 navigation_events=(),
                 redirect_to: str | None = None,
                 captcha_results=(),
                 events_after_captcha=(),
                 reload_delay: float = 0,
                 element_found: bool = True,
                 script_result=None,
                 script_error: Exception | None = None,
                 screenshot_error: Exception | None = None,
                 failing_methods=(),
                 html: str = '<html><head></head><body>page</body></html>',
                 screenshot: bytes = b'screenshot',
                 cookies_by_url: dict[str, list[dict]] | None = None):
        self.target_id = TargetID(MAIN_FRAME_ID)
        self.handlers = defaultdict(list)
        self.navigation_events = list(navigation_events)
        self.redirect_to = redirect_to
        self.captcha_results = iter(captcha_results)
        self.events_after_captcha = list(events_after_captcha)
        self.reload_delay = reload_delay
        self.element_found = element_found
        self.script_result = script_result
        self.script_error = script_error
        self.screenshot_error = screenshot_error
        self.failing_methods = set(failing_methods)
        self.html = html
        self.screenshot = screenshot
        self.cookies_by_url = cookies_by_url or {}
        self.browser: FakeBrowser | None = None
        self.websocket = object()
        self.websocket_open = True
        self.enabled_domains = set()
        self.user_agent = None
        self.location = 'about:blank'
        self.target = SimpleNamespace(url=self.location)
        self.navigations = []
        self.solve_captcha_calls = 0
        self.solve_captcha_times = []

    def add_handler(self, event_type, handler):
        self.handlers[event_type].append(handler)

    async def aopen(self):
        # Like seleniumbase's Connection.aopen, which opens a new websocket once the previous one closed: a new DevTools session.
        if not self.websocket_open:
            self.websocket = object()
            self.websocket_open = True
            self.enabled_domains = set()
            self.user_agent = None

    async def send(self, command):
        await self.aopen()
        request = next(command)
        method, params = request['method'], request['params']
        if method in self.failing_methods or method == 'Page.captureScreenshot' and params['format'] not in SCREENSHOT_FORMATS:
            # Like seleniumbase's Connection.send, which closes the websocket on a CDP error and returns None.
            self.websocket_open = False
            return None
        if method.endswith('.enable'):
            self.enabled_domains.add(method.removesuffix('.enable').lower())
            return _respond(command, {})
        if method == 'Network.setUserAgentOverride':
            self.user_agent = params['userAgent']
            return _respond(command, {})
        if method == 'Page.navigate':
            self.location = self.redirect_to or params['url']
            self.navigations.append(SimpleNamespace(url=params['url'], referrer=params.get('referrer'), user_agent=self.user_agent))
            self._emit(self.navigation_events)
            return _respond(command, {'frameId': str(self.target_id)})
        if method == 'Page.captureScreenshot':
            if self.screenshot_error:
                raise self.screenshot_error
            return _respond(command, {'data': b64encode(self.screenshot).decode()})
        if method == 'Network.getCookies':
            # Without urls, Chrome returns the cookies of the page and all its subframes.
            urls = params.get('urls', list(self.cookies_by_url))
            return _respond(command, {'cookies': [c for url in urls for c in self.cookies_by_url.get(url, [])]})
        return _respond(command, {})

    async def close(self):
        self.browser.targets.remove(self)

    async def update_target(self):
        self.target = SimpleNamespace(url=self.location)

    async def solve_captcha(self) -> bool:
        self.solve_captcha_calls += 1
        self.solve_captcha_times.append(asyncio.get_running_loop().time())
        solved = next(self.captcha_results, False)
        if solved:
            asyncio.get_running_loop().call_later(self.reload_delay, self._emit, self.events_after_captcha)
        return solved

    async def wait_for(self, selector: str | None = '', text: str | None = '', timeout: float | None = 10):
        if not self.element_found:
            raise TimeoutError(f'Time ran out while waiting for: {{{selector}}}')

    async def evaluate(self, expression: str, await_promise: bool = False, return_by_value: bool = True):
        if expression == 'window.location.href':
            return self.location
        if expression == 'document.documentElement.outerHTML':
            return self.html
        if self.script_error:
            raise self.script_error
        return self.script_result

    async def save_screenshot(self, filename='auto', format='png', full_page=False) -> str:
        return str(filename)

    def _emit(self, events):
        for event in events:
            # Chrome sends a domain's events only to the sessions that enabled it.
            if type(event).__module__.removeprefix('mycdp.') not in self.enabled_domains:
                continue
            for handler in list(self.handlers[type(event)]):
                # Same dispatch as seleniumbase's Connection: a handler may or may not take the connection.
                try:
                    handler(event, self)
                except TypeError:
                    handler(event)


class FakeBrowser:

    def __init__(self, *targets: FakeTab, new_tabs=(), user_agent: str = 'Mozilla/5.0 (fake)'):
        self.targets = list(targets)
        self.new_tabs = list(new_tabs)
        self.user_agent = user_agent
        for tab in self.targets + self.new_tabs:
            tab.browser = self

    async def get(self, url: str, new_tab: bool = False) -> FakeTab:
        # Like seleniumbase's Browser.get, which sets up and navigates a new tab or, without new_tab, the most recent target.
        if new_tab:
            self.targets.append(self.new_tabs.pop(0))
        tab = self.targets[-1]
        await tab.send(network.set_user_agent_override(user_agent=self.user_agent))
        await tab.send(page.navigate(url))
        return tab
