import asyncio
from base64 import b64encode
from collections import defaultdict
from types import SimpleNamespace

from mycdp.accessibility import AXNode, AXNodeId, AXProperty, AXPropertyName, AXValue, AXValueType, LoadComplete
from mycdp.network import Headers, LoaderId, MonotonicTime, RequestId, ResourceType, Response, ResponseReceived
from mycdp.page import FrameId
from mycdp.security import SecurityState
from mycdp.target import TargetID

MAIN_FRAME_ID = 'main-frame'
IFRAME_ID = 'iframe'


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


def load_complete(url: str, frame_id: str = MAIN_FRAME_ID) -> LoadComplete:
    url_property = AXProperty(name=AXPropertyName.URL, value=AXValue(type_=AXValueType.STRING, value=url))
    return LoadComplete(root=AXNode(node_id=AXNodeId('1'), ignored=False, properties=[url_property], frame_id=FrameId(frame_id)))


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
                 html: str = '<html><head></head><body>page</body></html>',
                 screenshot: bytes = b'screenshot'):
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
        self.html = html
        self.screenshot = screenshot
        self.location = 'about:blank'
        self.solve_captcha_calls = 0

    def add_handler(self, event_type, handler):
        self.handlers[event_type].append(handler)

    def navigate(self, url: str):
        self.location = self.redirect_to or url
        self._emit(self.navigation_events)

    async def send(self, command):
        request = next(command)
        if request['method'] == 'Page.captureScreenshot':
            if self.screenshot_error:
                raise self.screenshot_error
            return _respond(command, {'data': b64encode(self.screenshot).decode()})
        return _respond(command, {})

    async def solve_captcha(self) -> bool:
        self.solve_captcha_calls += 1
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
            for handler in list(self.handlers[type(event)]):
                # Same dispatch as seleniumbase's Connection: a handler may or may not take the connection.
                try:
                    handler(event, self)
                except TypeError:
                    handler(event)


class FakeCookieJar:

    def __init__(self, cookies: dict[str, str]):
        self._cookies = cookies

    async def get_all(self):
        return [SimpleNamespace(name=name, value=value) for name, value in self._cookies.items()]


class FakeBrowser:

    def __init__(self, tab: FakeTab, cookies: dict[str, str] | None = None):
        self.main_tab = tab
        self.cookies = FakeCookieJar(cookies or {})

    async def get(self, url: str) -> FakeTab:
        self.main_tab.navigate(url)
        return self.main_tab
