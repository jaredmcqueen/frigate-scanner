"""Tests for frigate_scanner.report — render_html, write_jsonl, write_html."""

from pathlib import Path

import pytest

from frigate_scanner.report import (
    render_cards_fragment,
    render_detail_fragment,
    render_html,
    render_shell,
    write_html,
    write_jsonl,
)


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


def make_card(
    url: str = "http://10.0.0.1:8971",
    country_code: str | None = "US",
    org: str | None = "Acme Corp",
    cameras: list[str] | None = None,
    is_new: bool = False,
) -> dict:
    cam_names = cameras if cameras is not None else ["front", "back"]
    return {
        "url": url,
        "port": 8971,
        "country": "United States",
        "country_code": country_code,
        "org": org,
        "frigate_version": "0.14.0",
        "camera_count": len(cam_names),
        "cameras": [
            {"name": n, "first_seen": "2024-01-01T00:00:00", "last_seen": "2024-01-02T00:00:00"}
            for n in cam_names
        ],
        "first_seen": "2024-01-01T00:00:00",
        "last_seen": "2024-01-02T00:00:00",
        "is_new": is_new,
    }


class TestRenderShell:
    def test_htmx_script_present(self):
        html = render_shell()
        assert "htmx.org" in html

    def test_card_grid_load_trigger_present(self):
        html = render_shell()
        assert 'hx-get="/fragments/cards"' in html
        assert 'hx-trigger="load, filter-changed"' in html

    def test_search_input_present(self):
        html = render_shell()
        assert 'id="search-input"' in html

    def test_detail_panel_present(self):
        html = render_shell()
        assert 'id="detail-panel"' in html

    def test_nav_links_present(self):
        html = render_shell()
        assert 'href="/"' in html
        assert 'href="/trends"' in html


class TestRenderCardsFragment:
    def test_instance_url_appears_in_output(self):
        card = make_card(url="http://10.0.0.1:5000")
        html = render_cards_fragment([card], ["US"], 1, 2, 1, 20, "", "")
        assert "10.0.0.1:5000" in html

    def test_camera_names_rendered(self):
        card = make_card(cameras=["garage", "driveway"])
        html = render_cards_fragment([card], ["US"], 1, 2, 1, 20, "", "")
        assert "garage" in html
        assert "driveway" in html

    def test_new_badge_when_is_new(self):
        card = make_card(is_new=True)
        html = render_cards_fragment([card], ["US"], 1, 2, 1, 20, "", "")
        assert 'class="badge badge-new"' in html

    def test_no_new_badge_when_not_new(self):
        card = make_card(is_new=False)
        html = render_cards_fragment([card], ["US"], 1, 2, 1, 20, "", "")
        assert 'class="badge badge-new"' not in html

    def test_active_country_button_marked(self):
        html = render_cards_fragment([], ["US", "DE"], 0, 0, 1, 20, "US", "")
        assert "filter-btn active" in html

    def test_card_detail_link_includes_url(self):
        card = make_card(url="http://10.0.0.1:8971")
        html = render_cards_fragment([card], ["US"], 1, 2, 1, 20, "", "")
        assert "hx-get=\"/instance?url=" in html

    def test_pagination_shown_when_total_exceeds_page_size(self):
        cards = [make_card(url=f"http://10.0.0.{i}:8971") for i in range(20)]
        html = render_cards_fragment(cards, ["US"], 25, 20, 1, 20, "", "")
        assert "pagination" in html
        assert "Next" in html

    def test_pagination_hidden_when_total_fits_page(self):
        cards = [make_card()]
        html = render_cards_fragment(cards, ["US"], 1, 1, 1, 20, "", "")
        assert "pagination" not in html

    def test_no_results_message_when_empty(self):
        html = render_cards_fragment([], [], 0, 0, 1, 20, "", "")
        assert "No instances match your filter" in html

    def test_xss_url_escaped(self):
        card = make_card(url='http://evil.com/<script>alert(1)</script>')
        html = render_cards_fragment([card], ["US"], 1, 2, 1, 20, "", "")
        assert "<script>alert(1)</script>" not in html


class TestRenderDetailFragment:
    def test_instance_url_in_output(self):
        instance = make_card(url="http://10.0.0.1:5000")
        html = render_detail_fragment(instance, [])
        assert "10.0.0.1:5000" in html

    def test_camera_names_rendered(self):
        instance = make_card()
        cameras = [
            {"name": "front", "first_seen": "2024-01-01T00:00:00", "last_seen": "2024-01-02T00:00:00"},
            {"name": "back", "first_seen": "2024-01-01T00:00:00", "last_seen": "2024-01-02T00:00:00"},
        ]
        html = render_detail_fragment(instance, cameras)
        assert "front" in html
        assert "back" in html

    def test_first_and_last_seen_dates_rendered(self):
        instance = make_card()
        html = render_detail_fragment(instance, [])
        assert "2024-01-01" in html
        assert "2024-01-02" in html

    def test_no_cameras_message(self):
        instance = make_card()
        html = render_detail_fragment(instance, [])
        assert "No cameras recorded" in html

    def test_close_button_present(self):
        instance = make_card()
        html = render_detail_fragment(instance, [])
        assert "detail-close" in html

    def test_org_and_version_rendered(self):
        instance = make_card(org="Acme Corp")
        html = render_detail_fragment(instance, [])
        assert "Acme Corp" in html
        assert "0.14.0" in html
