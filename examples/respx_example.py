import respx

from httpx_aiohttp_transport import mock_router


def test_metric_group_scale(respx_mock: respx.Router) -> None:
    respx_mock.route(...).mock(...)
    mock_router.set(respx_mock.handler)
