"""Unit tests for frigate_scanner.search."""

from unittest.mock import MagicMock

import shodan

from frigate_scanner.search import build_url, plan_queries, shape


class TestBuildUrl:
    def test_ipv4_http_port_80(self):
        assert build_url("1.2.3.4", 80, False) == "http://1.2.3.4"

    def test_ipv4_https_port_443(self):
        assert build_url("1.2.3.4", 443, False) == "https://1.2.3.4"

    def test_ipv4_non_standard_port_no_ssl(self):
        assert build_url("1.2.3.4", 8080, False) == "http://1.2.3.4:8080"

    def test_ipv4_non_standard_port_with_ssl(self):
        assert build_url("1.2.3.4", 8080, True) == "https://1.2.3.4:8080"

    def test_port_8443_no_ssl_flag(self):
        assert build_url("1.2.3.4", 8443, False) == "https://1.2.3.4:8443"

    def test_port_4443_no_ssl_flag(self):
        assert build_url("1.2.3.4", 4443, False) == "https://1.2.3.4:4443"

    def test_ipv6_non_standard_port(self):
        assert build_url("::1", 8080, False) == "http://[::1]:8080"

    def test_ipv6_port_80(self):
        assert build_url("::1", 80, False) == "http://[::1]"

    def test_ipv6_port_443(self):
        assert build_url("::1", 443, False) == "https://[::1]"


class TestShape:
    def _full_host(self) -> dict:
        return {
            "ip_str": "1.2.3.4",
            "port": 8971,
            "ssl": {},
            "location": {
                "country_name": "United States",
                "country_code": "US",
                "city": "New York",
            },
            "org": "Comcast",
            "hostnames": ["example.com"],
            "domains": ["example.com"],
            "http": {"title": "Live - Frigate"},
            "timestamp": "2024-01-01T00:00:00",
        }

    def test_full_host_all_fields(self):
        result = shape(self._full_host())
        assert result["url"] == "https://1.2.3.4:8971"
        assert result["ip"] == "1.2.3.4"
        assert result["port"] == 8971
        assert result["ssl"] is True
        assert result["country"] == "United States"
        assert result["country_code"] == "US"
        assert result["city"] == "New York"
        assert result["org"] == "Comcast"
        assert result["hostnames"] == ["example.com"]
        assert result["domains"] == ["example.com"]
        assert result["http_title"] == "Live - Frigate"
        assert result["last_update"] == "2024-01-01T00:00:00"
        assert result["shodan_url"] == "https://www.shodan.io/host/1.2.3.4"

    def test_missing_optional_fields_are_none(self):
        result = shape({"ip_str": "5.6.7.8", "port": 80})
        assert result["ssl"] is False
        assert result["country"] is None
        assert result["country_code"] is None
        assert result["city"] is None
        assert result["org"] is None
        assert result["http_title"] is None
        assert result["last_update"] is None
        assert result["hostnames"] == []
        assert result["domains"] == []

    def test_org_falls_back_to_isp(self):
        result = shape({"ip_str": "5.6.7.8", "port": 80, "isp": "ISP Corp"})
        assert result["org"] == "ISP Corp"

    def test_empty_string_fields_become_none(self):
        result = shape({
            "ip_str": "5.6.7.8",
            "port": 80,
            "org": "",
            "location": {"country_name": "", "country_code": "", "city": ""},
        })
        assert result["org"] is None
        assert result["country"] is None
        assert result["city"] is None

    def test_ipv6_url_has_brackets(self):
        result = shape({"ip_str": "::1", "port": 8080})
        assert result["url"] == "http://[::1]:8080"


class TestPlanQueries:
    def test_includes_every_query_with_results(self):
        api = MagicMock()
        api.count.return_value = {"total": 5}
        plans = plan_queries(api)
        assert len(plans) == 2
        assert all(total == 5 for _, total in plans)

    def test_skips_errored_query_keeps_others(self):
        api = MagicMock()
        api.count.side_effect = [
            shodan.APIError("quota exceeded"),
            {"total": 3},
        ]
        plans = plan_queries(api)
        assert len(plans) == 1
        assert plans[0][1] == 3

    def test_all_queries_fail_returns_empty(self):
        api = MagicMock()
        api.count.side_effect = shodan.APIError("fail")
        plans = plan_queries(api)
        assert plans == []

    def test_zero_total_query_excluded(self):
        api = MagicMock()
        api.count.side_effect = [
            {"total": 0},
            {"total": 2},
        ]
        plans = plan_queries(api)
        assert len(plans) == 1
        assert plans[0][1] == 2
