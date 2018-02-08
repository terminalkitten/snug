import asyncio
import json
from unittest import mock

import pytest

import snug


LIVE = pytest.config.getoption('--live')


@pytest.fixture
def loop(scope='module'):
    return asyncio.get_event_loop()


class MockAsyncClient:
    def __init__(self, response):
        self.response = response

    @asyncio.coroutine
    def send(self, req):
        yield from asyncio.sleep(0)
        self.request = req
        return self.response


class MockClient:
    def __init__(self, response):
        self.response = response

    def send(self, req):
        self.request = req
        return self.response


snug.send.register(MockClient, MockClient.send)
snug.send_async.register(MockAsyncClient, MockAsyncClient.send)


def test_exec():
    sender = {
        '/posts/latest': 'redirect:/posts/latest/',
        '/posts/latest/': 'redirect:/posts/december/',
        '/posts/december/': b'hello world'
    }.__getitem__

    class MyQuery:
        def __iter__(self):
            redirect = yield '/posts/latest'
            redirect = yield redirect.split(':')[1]
            response = yield redirect.split(':')[1]
            return response.decode('ascii')

    assert snug.core._exec(MyQuery(), sender=sender) == 'hello world'


def test_exec_async(loop):

    @asyncio.coroutine
    def sender(req):
        yield from asyncio.sleep(0)
        if not req.endswith('/'):
            return 'redirect:' + req + '/'
        elif req == '/posts/latest/':
            return 'hello world'

    def myquery():
        response = yield '/posts/latest'
        while response.startswith('redirect:'):
            response = yield response[9:]
        return response.upper()

    result_future = snug.core._exec_async(myquery(), sender=sender)
    result = loop.run_until_complete(result_future)
    assert result == 'HELLO WORLD'


class TestExecute:

    @mock.patch('urllib.request.Request', autospec=True)
    @mock.patch('urllib.request.urlopen', autospec=True)
    def test_defaults(self, urlopen, _):

        def myquery():
            return (yield snug.GET('my/url'))

        assert snug.execute(myquery()) == snug.Response(
            status_code=urlopen.return_value.getcode.return_value,
            content=urlopen.return_value.read.return_value,
            headers=urlopen.return_value.headers,
        )

    def test_custom_client(self):
        client = MockClient(snug.Response(204))

        def myquery():
            return (yield snug.GET('my/url'))

        result = snug.execute(myquery(), client=client)
        assert result == snug.Response(204)
        assert client.request == snug.GET('my/url')

    def test_auth(self):
        client = MockClient(snug.Response(204))

        def myquery():
            return (yield snug.GET('my/url'))

        result = snug.execute(myquery(),
                              auth=('user', 'pw'),
                              client=client)
        assert result == snug.Response(204)
        assert client.request == snug.GET(
            'my/url', headers={'Authorization': 'Basic dXNlcjpwdw=='})

    def test_auth_method(self):

        def token_auth(token, request):
            return request.with_headers({
                'Authorization': 'Bearer {}'.format(token)
            })

        def myquery():
            return (yield snug.GET('my/url'))

        client = MockClient(snug.Response(204))
        result = snug.execute(myquery(), auth='foo', client=client,
                              auth_method=token_auth)

        assert result == snug.Response(204)
        assert client.request == snug.GET(
            'my/url', headers={'Authorization': 'Bearer foo'})


class TestExecuteAsync:

    @mock.patch('snug.core.asyncio_sender',
                MockAsyncClient(snug.Response(204)).send)
    def test_defaults(self, loop):

        def myquery():
            return (yield snug.GET('my/url'))

        future = snug.execute_async(myquery())
        result = loop.run_until_complete(future)
        assert result == snug.Response(204)

    def test_custom_client(self, loop):
        client = MockAsyncClient(snug.Response(204))

        def myquery():
            return (yield snug.GET('my/url'))

        future = snug.execute_async(myquery(), client=client)
        result = loop.run_until_complete(future)
        assert result == snug.Response(204)
        assert client.request == snug.GET('my/url')

    def test_auth(self, loop):
        client = MockAsyncClient(snug.Response(204))

        def myquery():
            return (yield snug.GET('my/url'))

        future = snug.execute_async(myquery(),
                                    auth=('user', 'pw'),
                                    client=client)
        result = loop.run_until_complete(future)
        assert result == snug.Response(204)
        assert client.request == snug.GET(
            'my/url', headers={'Authorization': 'Basic dXNlcjpwdw=='})

    def test_auth_method(self, loop):

        def token_auth(token, request):
            return request.with_headers({
                'Authorization': 'Bearer {}'.format(token)
            })

        def myquery():
            return (yield snug.GET('my/url'))

        client = MockAsyncClient(snug.Response(204))
        future = snug.execute_async(myquery(), auth='foo', client=client,
                                    auth_method=token_auth)
        result = loop.run_until_complete(future)

        assert result == snug.Response(204)
        assert client.request == snug.GET(
            'my/url', headers={'Authorization': 'Bearer foo'})


class TestRequest:

    def test_defaults(self):
        req = snug.Request('GET', 'my/url/')
        assert req == snug.Request('GET', 'my/url/', params={}, headers={})

    def test_with_headers(self):
        req = snug.GET('my/url', headers={'foo': 'bla'})
        assert req.with_headers({'other-header': 3}) == snug.GET(
            'my/url', headers={'foo': 'bla', 'other-header': 3})

    def test_with_prefix(self):
        req = snug.GET('my/url/')
        assert req.with_prefix('mysite.com/') == snug.GET(
            'mysite.com/my/url/')

    def test_with_params(self):
        req = snug.GET('my/url/', params={'foo': 'bar'})
        assert req.with_params({'other': 3}) == snug.GET(
            'my/url/', params={'foo': 'bar', 'other': 3})

    def test_equality(self):
        req = snug.Request('GET', 'my/url')
        other = req.replace()
        assert req == other
        assert not req != other

        assert not req == req.replace(headers={'foo': 'bar'})
        assert req != req.replace(headers={'foo': 'bar'})

        assert not req == object()
        assert req != object()

    def test_repr(self):
        req = snug.GET('my/url')
        assert 'GET my/url' in repr(req)


class TestResponse:

    def test_equality(self):
        rsp = snug.Response(204)
        other = rsp.replace()
        assert rsp == other
        assert not rsp != other

        assert not rsp == rsp.replace(headers={'foo': 'bar'})
        assert rsp != rsp.replace(headers={'foo': 'bar'})

        assert not rsp == object()
        assert rsp != object()

    def test_repr(self):
        assert '404' in repr(snug.Response(404))


def test_prefix_adder():
    req = snug.GET('my/url')
    adder = snug.prefix_adder('mysite.com/')
    assert adder(req) == snug.GET('mysite.com/my/url')


def test_header_adder():
    req = snug.GET('my/url', headers={'Accept': 'application/json'})
    adder = snug.header_adder({
        'Authorization': 'my-auth'
    })
    assert adder(req) == snug.GET('my/url', headers={
        'Accept': 'application/json',
        'Authorization': 'my-auth'
    })


def test_executor():
    exec = snug.executor(client='foo')
    assert exec.keywords == {'client': 'foo'}


def test_async_executor():
    exec = snug.async_executor(client='foo')
    assert exec.keywords == {'client': 'foo'}


def test_sender_factory_unknown_client():
    class MyClass:
        pass
    with pytest.raises(TypeError, match='MyClass'):
        snug.send(MyClass(), snug.GET('foo'))


@mock.patch('urllib.request.Request', autospec=True)
@mock.patch('urllib.request.urlopen', autospec=True)
def test_urllib_sender(urlopen, urllib_request):
    req = snug.Request('HEAD', 'https://www.api.github.com/organizations',
                       params={'since': 3043},
                       headers={'Accept': 'application/vnd.github.v3+json'})
    response = snug.core.urllib_sender(req, timeout=10)
    assert response == snug.Response(
        status_code=urlopen.return_value.getcode.return_value,
        content=urlopen.return_value.read.return_value,
        headers=urlopen.return_value.headers,
    )
    urlopen.assert_called_once_with(urllib_request.return_value, timeout=10)
    urllib_request.assert_called_once_with(
        'https://www.api.github.com/organizations?since=3043',
        headers={'Accept': 'application/vnd.github.v3+json'},
        method='HEAD',
    )


def test_requests_send():
    requests = pytest.importorskip("requests")
    session = mock.Mock(spec=requests.Session)
    req = snug.GET('https://www.api.github.com/organizations',
                   params={'since': 3043},
                   headers={'Accept': 'application/vnd.github.v3+json'})
    response = snug.send(session, req)
    assert response == snug.Response(
        status_code=session.request.return_value.status_code,
        content=session.request.return_value.content,
        headers=session.request.return_value.headers,
    )
    session.request.assert_called_once_with(
        'GET',
        'https://www.api.github.com/organizations',
        params={'since': 3043},
        headers={'Accept': 'application/vnd.github.v3+json'})


def test_async_sender_factory_unknown_client():
    class MyClass:
        pass
    with pytest.raises(TypeError, match='MyClass'):
        snug.send_async(MyClass(), snug.GET('foo'))


@pytest.mark.skipif(not LIVE, reason='skip live data test')
class TestAsyncioSender:

    def test_https(self, loop):
        req = snug.Request('GET', 'https://httpbin.org/get',
                           params={'param1': 'foo'},
                           headers={'Accept': 'application/json'})
        response = loop.run_until_complete(snug.core.asyncio_sender(req))
        assert response == snug.Response(200, mock.ANY, headers=mock.ANY)
        data = json.loads(response.content.decode())
        assert data['args'] == {'param1': 'foo'}
        assert data['headers']['Accept'] == 'application/json'
        assert data['headers']['User-Agent'].startswith('Python-asyncio/')

    def test_http(self, loop):
        req = snug.Request('POST', 'http://httpbin.org/post',
                           content=json.dumps({"foo": 4}).encode(),
                           headers={'User-Agent': 'snug/dev'})
        response = loop.run_until_complete(snug.core.asyncio_sender(req))
        assert response == snug.Response(200, mock.ANY, headers=mock.ANY)
        data = json.loads(response.content.decode())
        assert data['args'] == {}
        assert json.loads(data['data']) == {'foo': 4}
        assert data['headers']['User-Agent'] == 'snug/dev'


def test_aiohttp_send(loop):
    req = snug.GET('https://test.com',
                   content=b'{"foo": 4}',
                   params={'bla': 99},
                   headers={'Authorization': 'Basic ABC'})
    aiohttp = pytest.importorskip('aiohttp')
    from aioresponses import aioresponses

    @asyncio.coroutine
    def do_test():
        session = aiohttp.ClientSession()
        try:
            return (yield from snug.send_async(session, req))
        finally:
            session.close()

    with aioresponses() as m:
        m.get('https://test.com/?bla=99', body=b'{"my": "content"}',
              status=201,
              headers={'Content-Type': 'application/json'})
        response = loop.run_until_complete(do_test())

        assert response == snug.Response(
            201,
            content=b'{"my": "content"}',
            headers={'Content-Type': 'application/json'})

        call, = m.requests[('GET', 'https://test.com/?bla=99')]
        assert call.kwargs['headers'] == {'Authorization': 'Basic ABC'}
        assert call.kwargs['params'] == {'bla': 99}
        assert call.kwargs['data'] == b'{"foo": 4}'


def test_relation():

    class Foo:

        @snug.related
        class Bar(snug.Query):
            def __iter__(self): pass

            def __init__(self, a, b):
                self.a, self.b = a, b

        class Qux(snug.Query):
            def __iter__(self): pass

            def __init__(self, a, b):
                self.a, self.b = a, b

    f = Foo()
    bar = f.Bar(b=4)
    assert isinstance(bar, Foo.Bar)
    assert bar.a is f
    bar2 = Foo.Bar(f, 4)
    assert isinstance(bar2, Foo.Bar)
    assert bar.a is f

    # staticmethod opts out
    qux = f.Qux(1, 2)
    assert isinstance(qux, f.Qux)
    qux2 = Foo.Qux(1, 2)
    assert isinstance(qux2, Foo.Qux)
