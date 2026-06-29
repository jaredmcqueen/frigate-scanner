"""Tests for frigate_scanner.report — render_html, write_jsonl, write_html."""

from pathlib import Path

import pytest

from frigate_scanner.report import render_html, write_html, write_jsonl


def make_instance(
    url: str = "http://1.2.3.4:8971",
    country_code: str | None = "US",
    org: str | None = "Acme Corp",
    cameras: list[str] | None = None,
    is_new: bool = False,
) -> dict:
    cameras = cameras or ["front", "back"]
    return {
        "url": url,
        "port": 8971,
        "country_code": country_code,
        "org": org,
        "frigate_version": "0.14.0",
        "probe_camera_count": len(cameras),
        "probe_cameras": cameras,
        "frigate_uptime_days": None,
        "is_new": is_new,
        "new_cameras": set(),
    }


class TestRenderHtml:
    def test_returns_html_string(self):
        html = render_html([], "2024-01-01 00:00 UTC")
        assert html.startswith("<!DOCTYPE html>")

    def test_instance_url_appears_in_output(self):
        inst = make_instance(url="http://10.0.0.1:5000")
        html = render_html([inst], "2024-01-01 00:00 UTC")
        assert "10.0.0.1:5000" in html

    def test_country_filter_button_rendered(self):
        inst = make_instance(country_code="DE")
        html = render_html([inst], "2024-01-01 00:00 UTC")
        assert 'data-country="DE"' in html

    def test_no_country_code_uses_xx(self):
        inst = make_instance(country_code=None)
        html = render_html([inst], "2024-01-01 00:00 UTC")
        assert 'data-country="XX"' in html

    def test_new_badge_when_is_new(self):
        inst = make_instance(is_new=True)
        html = render_html([inst], "2024-01-01 00:00 UTC")
        assert 'class="badge badge-new"' in html

    def test_no_new_badge_when_not_new(self):
        inst = make_instance(is_new=False)
        html = render_html([inst], "2024-01-01 00:00 UTC")
        assert 'class="badge badge-new"' not in html

    def test_camera_names_rendered(self):
        inst = make_instance(cameras=["garage", "driveway"])
        html = render_html([inst], "2024-01-01 00:00 UTC")
        assert "garage" in html
        assert "driveway" in html

    def test_total_count_in_output(self):
        instances = [make_instance(f"http://10.0.0.{i}:8971") for i in range(3)]
        html = render_html(instances, "2024-01-01 00:00 UTC")
        assert "3" in html

    def test_diff_section_hidden_when_no_diff(self):
        html = render_html([], "2024-01-01 00:00 UTC", diff=None)
        assert "Changes since last scan" not in html

    def test_xss_url_escaped(self):
        inst = make_instance(url='http://evil.com/<script>alert(1)</script>')
        html = render_html([inst], "2024-01-01 00:00 UTC")
        assert "<script>alert(1)</script>" not in html


class TestWriteJsonl:
    def test_writes_one_line_per_instance(self, tmp_path: Path):
        path = tmp_path / "out.jsonl"
        instances = [make_instance("http://a.com"), make_instance("http://b.com")]
        write_jsonl(instances, path)
        lines = path.read_text().strip().splitlines()
        assert len(lines) == 2

    def test_each_line_is_valid_json(self, tmp_path: Path):
        import json

        path = tmp_path / "out.jsonl"
        write_jsonl([make_instance()], path)
        for line in path.read_text().strip().splitlines():
            data = json.loads(line)
            assert "url" in data

    def test_empty_list_writes_empty_file(self, tmp_path: Path):
        path = tmp_path / "out.jsonl"
        write_jsonl([], path)
        assert path.read_text() == ""


class TestWriteHtml:
    def test_writes_html_file(self, tmp_path: Path):
        path = tmp_path / "report.html"
        write_html([make_instance()], "2024-01-01 00:00 UTC", None, path)
        assert path.exists()
        assert path.read_text().startswith("<!DOCTYPE html>")
