"""Unit tests for frigate_scanner.probe."""

from unittest.mock import AsyncMock, MagicMock


from frigate_scanner.probe import _check, _extract_frigate_info

STATS_FULL = {
    "service": {
        "version": "0.14.0",
        "latest_version": "0.14.1",
        "uptime": 86400,
    },
    "cameras": {
        "front_door": {"camera_fps": 5.0, "detection_enabled": True},
        "backyard": {"camera_fps": 10.0, "detection_enabled": False},
    },
}


class TestExtractFrigateInfo:
    def test_full_stats(self):
        result = _extract_frigate_info(STATS_FULL)
        assert result["frigate_version"] == "0.14.0"
        assert result["frigate_latest_version"] == "0.14.1"
        assert result["frigate_uptime_secs"] == 86400
        assert result["frigate_uptime_days"] == 1.0
        names = {c["name"] for c in result["frigate_camera_details"]}
        assert names == {"front_door", "backyard"}

    def test_uptime_none_gives_none_days(self):
        result = _extract_frigate_info({"service": {"uptime": None}, "cameras": {}})
        assert result["frigate_uptime_days"] is None
        assert result["frigate_uptime_secs"] is None

    def test_empty_cameras(self):
        result = _extract_frigate_info({"service": {}, "cameras": {}})
        assert result["frigate_camera_details"] == []

    def test_uptime_rounding(self):
        result = _extract_frigate_info({"service": {"uptime": 90000}, "cameras": {}})
        assert result["frigate_uptime_days"] == 1.0

    def test_camera_details_fields(self):
        result = _extract_frigate_info(STATS_FULL)
        cam = next(c for c in result["frigate_camera_details"] if c["name"] == "front_door")
        assert cam["fps"] == 5.0
        assert cam["detection_enabled"] is True


def _make_client(status_code: int = 200, json_data=None, raise_exc=None) -> AsyncMock:
    client = AsyncMock()
    if raise_exc is not None:
        client.get.side_effect = raise_exc
    else:
        resp = MagicMock()
        resp.status_code = status_code
        if json_data is not None:
            resp.json.return_value = json_data
        else:
            resp.json.side_effect = ValueError("bad json")
        client.get.return_value = resp
    return client


class TestCheck:
    async def test_valid_frigate_response(self):
        client = _make_client(json_data=STATS_FULL)
        result = await _check(client, {"url": "http://1.2.3.4:8971"})
        assert result is not None
        assert result["probe_status"] == 200
        assert result["probe_stats_url"] == "http://1.2.3.4:8971/api/stats"
        assert set(result["probe_cameras"]) == {"front_door", "backyard"}
        assert result["probe_camera_count"] == 2
        assert result["frigate_version"] == "0.14.0"
        assert "probe_at" in result

    async def test_record_fields_passed_through(self):
        client = _make_client(json_data=STATS_FULL)
        record = {"url": "http://1.2.3.4:8971", "ip": "1.2.3.4", "country": "US"}
        result = await _check(client, record)
        assert result["ip"] == "1.2.3.4"
        assert result["country"] == "US"

    async def test_missing_cameras_key_returns_none(self):
        client = _make_client(json_data={"service": {}})
        result = await _check(client, {"url": "http://1.2.3.4"})
        assert result is None

    async def test_non_200_status_returns_none(self):
        client = _make_client(status_code=401)
        result = await _check(client, {"url": "http://1.2.3.4"})
        assert result is None

    async def test_403_returns_none(self):
        client = _make_client(status_code=403)
        result = await _check(client, {"url": "http://1.2.3.4"})
        assert result is None

    async def test_network_exception_returns_none(self):
        client = _make_client(raise_exc=ConnectionError("timeout"))
        result = await _check(client, {"url": "http://1.2.3.4"})
        assert result is None

    async def test_invalid_json_returns_none(self):
        client = _make_client(status_code=200)  # json() raises ValueError
        result = await _check(client, {"url": "http://1.2.3.4"})
        assert result is None

    async def test_url_trailing_slash_stripped(self):
        client = _make_client(json_data=STATS_FULL)
        result = await _check(client, {"url": "http://1.2.3.4:8971/"})
        assert result["probe_stats_url"] == "http://1.2.3.4:8971/api/stats"
