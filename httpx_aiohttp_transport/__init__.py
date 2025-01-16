import asyncio
import typing
from contextvars import ContextVar
from types import TracebackType

import aiohttp
import httpx
from httpx import AsyncBaseTransport

AIOHTTP_TO_HTTPX_EXCEPTIONS: dict[type[Exception], type[Exception]] = {
    # 基础异常
    aiohttp.ClientError: httpx.RequestError,
    # 网络相关异常
    aiohttp.ClientConnectionError: httpx.NetworkError,
    aiohttp.ClientConnectorError: httpx.ConnectError,
    aiohttp.ClientOSError: httpx.ConnectError,
    aiohttp.ClientConnectionResetError: httpx.ConnectError,
    # DNS相关异常
    aiohttp.ClientConnectorDNSError: httpx.ConnectError,
    # SSL相关异常
    aiohttp.ClientSSLError: httpx.ProtocolError,
    aiohttp.ClientConnectorCertificateError: httpx.ProtocolError,
    aiohttp.ServerFingerprintMismatch: httpx.ProtocolError,
    # 代理相关异常
    aiohttp.ClientProxyConnectionError: httpx.ProxyError,
    # 响应相关异常
    aiohttp.ClientResponseError: httpx.HTTPStatusError,
    aiohttp.ContentTypeError: httpx.DecodingError,
    aiohttp.ClientPayloadError: httpx.ReadError,
    # 连接断开异常
    aiohttp.ServerDisconnectedError: httpx.ReadError,
    # URL相关异常
    aiohttp.InvalidURL: httpx.InvalidURL,
    # 重定向相关异常
    aiohttp.TooManyRedirects: httpx.TooManyRedirects,
}


def map_aiohttp_exception(exc: Exception) -> Exception:
    """
    将 aiohttp 异常映射为对应的 httpx 异常

    Args:
        exc: aiohttp 异常实例

    Returns:
        对应的 httpx 异常实例
    """
    for aiohttp_exc, httpx_exc in AIOHTTP_TO_HTTPX_EXCEPTIONS.items():
        if isinstance(exc, aiohttp_exc):
            return httpx_exc(str(exc))

    # 处理 asyncio 的超时异常
    if isinstance(exc, asyncio.TimeoutError):
        return httpx.TimeoutException(str(exc))

    # 未知异常，包装为通用 HTTPError
    return httpx.HTTPError(f"Unknown error: {str(exc)}")


class AiohttpTransport(AsyncBaseTransport):
    def __init__(self, session: aiohttp.ClientSession | None = None):
        self._session = session or aiohttp.ClientSession()
        self._closed = False

    async def __aenter__(self) -> typing.Self:
        await self._session.__aenter__()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None = None,
        exc_value: BaseException | None = None,
        traceback: TracebackType | None = None,
    ):
        await self._session.__aexit__(exc_type, exc_value, traceback)
        self._closed = True

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        if (
            _rsp := try_to_get_mocked_response(request)
        ) is not None:  # 为了兼容RESPX mock
            return _rsp

        if self._closed:
            raise RuntimeError("Transport is closed")

        try:
            # 应用认证
            headers = dict(request.headers)

            # 准备请求参数
            method = request.method
            url = str(request.url)
            content = request.content

            async with self._session.request(
                method=method,
                url=url,
                headers=headers,
                data=content,
                allow_redirects=True,
            ) as aiohttp_response:
                # 读取响应内容
                content = await aiohttp_response.read()

                # 转换headers
                new_headers = [
                    (k.lower(), v)
                    for k, v in aiohttp_response.headers.items()
                    if k.lower() != "content-encoding"
                ]

                # 构建httpx.Response
                return httpx.Response(
                    status_code=aiohttp_response.status,
                    headers=new_headers,
                    content=content,
                    request=request,
                )
        except Exception as e:
            raise map_aiohttp_exception(e) from e

    async def aclose(self):
        if not self._closed:
            self._closed = True
            await self._session.close()


mock_router: ContextVar[typing.Callable[[httpx.Request], httpx.Response]] = ContextVar(
    "mock_router"
)


def try_to_get_mocked_response(request: httpx.Request) -> httpx.Response | None:
    try:
        _mock_handler = mock_router.get()
    except LookupError:
        return None
    return _mock_handler(request)


def create_aiohttp_backed_httpx_client(
    *,
    headers: dict[str, str] | None = None,
    total_timeout: float | None = None,
    base_url: str = "",
    proxy: str | None = None,
    keepalive_timeout: float = 15,
    max_connections: int = 100,
    max_connections_per_host: int = 0,
    verify_ssl: bool = False,
    login: str | None = None,
    password: str | None = None,
    encoding: str = "latin1",
    force_close: bool = False,
) -> httpx.AsyncClient:
    timeout = aiohttp.ClientTimeout(total=total_timeout)
    connector = aiohttp.TCPConnector(
        keepalive_timeout=keepalive_timeout if not force_close else None,
        limit=max_connections,
        limit_per_host=max_connections_per_host,
        ssl=verify_ssl,
        enable_cleanup_closed=True,
        force_close=force_close,
        ttl_dns_cache=None,
    )
    if login and password:
        auth = aiohttp.BasicAuth(login=login, password=password, encoding=encoding)
    else:
        auth = None
    return httpx.AsyncClient(
        base_url=base_url,
        verify=False,
        transport=AiohttpTransport(
            session=aiohttp.ClientSession(
                proxy=proxy,
                auth=auth,
                timeout=timeout,
                connector=connector,
                headers=headers,
            )
        ),
    )


__all__ = [
    "create_aiohttp_backed_httpx_client",
    "mock_router",
]
