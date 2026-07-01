"""Tests for frigate_scanner.dashboard — FastAPI app routes."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from frigate_scanner.dashboard import create_app
from frigate_scanner.store import record_scan


def _seed_db(db_path: Path, instances: list[dict], now: str = "2024-01-01T00:00:00") -> None:
    record_scan(db_path, instances, hosts_scanned=100, now=now)


def make_instance(url: str, cameras: list[str]) -> dict:
    return {
        "url": url,
        "ip": "1.2.3.4",
        "port": 8971,
        "country": "United States",
        "country_code": "US",
        "org": "Acme Corp",
        "frigate_version": "0.14.0",
        "probe_camera_count": len(cameras),
        "probe_cameras": cameras,
    }


@pytest.fixture()
def db(tmp_path: Path) -> Path:
    return tmp_path / "frigate.db"


@pytest.fixture()
def client(db: Path) -> TestClient:
    app = create_app(db)
    return TestClient(app)


@pytest.fixture()
def seeded_client(db: Path) -> TestClient:
    _seed_db(db, [
        make_instance("http://10.0.0.1:8971", ["front", "back"]),
        make_instance("http://10.0.0.2:8971", ["garage"]),
    ])
    app = create_app(db)
    return TestClient(app)


class TestHealth:
    def test_returns_200(self, client: TestClient):
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_returns_ok_status(self, client: TestClient):
        resp = client.get("/health")
        assert resp.json() == {"status": "ok"}


class TestIndex:
    def test_missing_db_returns_200(self, db: Path):
        # The shell page does not touch the DB directly — always 200
        client = TestClient(create_app(db))
        resp = client.get("/")
        assert resp.status_code == 200

    def test_htmx_script_present(self, client: TestClient):
        resp = client.get("/")
        assert "htmx.org" in resp.text

    def test_cards_fragment_load_trigger_present(self, client: TestClient):
        resp = client.get("/")
        assert 'hx-get="/fragments/cards"' in resp.text

    def test_search_input_present(self, client: TestClient):
        resp = client.get("/")
        assert 'id="search-input"' in resp.text

    def test_detail_panel_present(self, client: TestClient):
        resp = client.get("/")
        assert 'id="detail-panel"' in resp.text

    def test_nav_link_to_trends_present(self, client: TestClient):
        resp = client.get("/")
        assert 'href="/trends"' in resp.text


class TestCardsFragment:
    def test_missing_db_returns_200(self, db: Path):
        client = TestClient(create_app(db))
        resp = client.get("/fragments/cards")
        assert resp.status_code == 200

    def test_missing_db_shows_no_data_message(self, db: Path):
        client = TestClient(create_app(db))
        resp = client.get("/fragments/cards")
        assert "No scan data" in resp.text

    def test_seeded_db_returns_html(self, seeded_client: TestClient):
        resp = seeded_client.get("/fragments/cards")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]

    def test_instance_urls_in_response(self, seeded_client: TestClient):
        resp = seeded_client.get("/fragments/cards")
        assert "10.0.0.1:8971" in resp.text
        assert "10.0.0.2:8971" in resp.text

    def test_camera_names_in_response(self, seeded_client: TestClient):
        resp = seeded_client.get("/fragments/cards")
        assert "front" in resp.text
        assert "garage" in resp.text

    def test_country_filter_button_rendered(self, seeded_client: TestClient):
        resp = seeded_client.get("/fragments/cards")
        assert ">US<" in resp.text

    def test_country_filter_excludes_other_countries(self, db: Path):
        us = make_instance("http://10.0.0.1:8971", ["front"])
        de = {**make_instance("http://10.0.0.2:8971", ["garage"]), "country_code": "DE", "country": "Germany"}
        _seed_db(db, [us, de])
        client = TestClient(create_app(db))
        resp = client.get("/fragments/cards?country=US")
        assert "10.0.0.1:8971" in resp.text
        assert "10.0.0.2:8971" not in resp.text

    def test_search_filter_matches_url(self, seeded_client: TestClient):
        resp = seeded_client.get("/fragments/cards?q=10.0.0.1")
        assert "10.0.0.1:8971" in resp.text
        assert "10.0.0.2:8971" not in resp.text

    def test_search_filter_matches_org(self, db: Path):
        inst = {**make_instance("http://10.0.0.1:8971", ["front"]), "org": "UniqueOrgName"}
        _seed_db(db, [inst])
        client = TestClient(create_app(db))
        resp = client.get("/fragments/cards?q=UniqueOrgName")
        assert "10.0.0.1:8971" in resp.text

    def test_pagination_second_page(self, db: Path):
        # URLs sort lexicographically; with 25 instances "10.0.0.5" lands on page 2
        instances = [
            make_instance(f"http://10.0.0.{i}:8971", [f"cam{i}"]) for i in range(1, 26)
        ]
        _seed_db(db, instances)
        client = TestClient(create_app(db))
        resp = client.get("/fragments/cards?page=2")
        assert resp.status_code == 200
        assert "10.0.0.5:8971" in resp.text
        assert "10.0.0.1:8971" not in resp.text

    def test_active_country_button_marked(self, seeded_client: TestClient):
        resp = seeded_client.get("/fragments/cards?country=US")
        assert "filter-btn active" in resp.text

    def test_count_display_shows_total(self, seeded_client: TestClient):
        resp = seeded_client.get("/fragments/cards")
        assert "2 shown" in resp.text

    def test_new_badge_on_first_scan(self, seeded_client: TestClient):
        resp = seeded_client.get("/fragments/cards")
        assert 'class="badge badge-new"' in resp.text

    def test_second_scan_known_instances_not_new(self, db: Path):
        inst = make_instance("http://10.0.0.1:8971", ["front"])
        _seed_db(db, [inst], now="2024-01-01T00:00:00")
        _seed_db(db, [inst], now="2024-01-02T00:00:00")
        client = TestClient(create_app(db))
        resp = client.get("/fragments/cards")
        assert resp.status_code == 200
        assert 'class="badge badge-new"' not in resp.text

    def test_stats_bar_shows_instance_count(self, seeded_client: TestClient):
        resp = seeded_client.get("/fragments/cards")
        assert "stat-value" in resp.text


class TestStarInstance:
    def test_star_returns_200(self, seeded_client: TestClient):
        resp = seeded_client.post("/instance/star", params={"url": "http://10.0.0.1:8971"})
        assert resp.status_code == 200

    def test_star_marks_button_as_starred(self, seeded_client: TestClient):
        resp = seeded_client.post("/instance/star", params={"url": "http://10.0.0.1:8971"})
        assert "star-btn is-starred" in resp.text

    def test_toggle_twice_unstars(self, seeded_client: TestClient):
        seeded_client.post("/instance/star", params={"url": "http://10.0.0.1:8971"})
        resp = seeded_client.post("/instance/star", params={"url": "http://10.0.0.1:8971"})
        assert "star-btn is-starred" not in resp.text

    def test_starred_instance_sorts_first(self, db: Path):
        _seed_db(db, [
            make_instance("http://a.example:8971", ["cam1"]),
            make_instance("http://z.example:8971", ["cam2"]),
        ])
        client = TestClient(create_app(db))
        client.post("/instance/star", params={"url": "http://z.example:8971"})
        resp = client.get("/fragments/cards")
        assert resp.text.index("z.example") < resp.text.index("a.example")

    def test_unknown_url_returns_404(self, seeded_client: TestClient):
        resp = seeded_client.post("/instance/star", params={"url": "http://unknown:9999"})
        assert resp.status_code == 404

    def test_missing_db_returns_404(self, db: Path):
        client = TestClient(create_app(db))
        resp = client.post("/instance/star", params={"url": "http://10.0.0.1:8971"})
        assert resp.status_code == 404


class TestInstanceDetail:
    def test_returns_200_for_known_url(self, seeded_client: TestClient):
        resp = seeded_client.get("/instance", params={"url": "http://10.0.0.1:8971"})
        assert resp.status_code == 200

    def test_shows_camera_names(self, seeded_client: TestClient):
        resp = seeded_client.get("/instance", params={"url": "http://10.0.0.1:8971"})
        assert "front" in resp.text
        assert "back" in resp.text

    def test_shows_first_and_last_seen(self, seeded_client: TestClient):
        resp = seeded_client.get("/instance", params={"url": "http://10.0.0.1:8971"})
        assert "2024-01-01" in resp.text

    def test_shows_org_and_version(self, seeded_client: TestClient):
        resp = seeded_client.get("/instance", params={"url": "http://10.0.0.1:8971"})
        assert "Acme Corp" in resp.text
        assert "0.14.0" in resp.text

    def test_unknown_url_returns_404(self, seeded_client: TestClient):
        resp = seeded_client.get("/instance", params={"url": "http://unknown:9999"})
        assert resp.status_code == 404

    def test_missing_db_returns_404(self, db: Path):
        client = TestClient(create_app(db))
        resp = client.get("/instance", params={"url": "http://10.0.0.1:8971"})
        assert resp.status_code == 404


class TestTrends:
    def test_missing_db_returns_200(self, db: Path):
        client = TestClient(create_app(db))
        resp = client.get("/trends")
        assert resp.status_code == 200

    def test_missing_db_shows_no_data_message(self, db: Path):
        client = TestClient(create_app(db))
        resp = client.get("/trends")
        assert "No scan data" in resp.text

    def test_single_scan_returns_html(self, seeded_client: TestClient):
        resp = seeded_client.get("/trends")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]

    def test_single_scan_shows_no_chart(self, seeded_client: TestClient):
        resp = seeded_client.get("/trends")
        assert "Need at least 2 scans" in resp.text

    def test_two_scans_renders_svg_chart(self, db: Path):
        inst = make_instance("http://10.0.0.1:8971", ["front"])
        _seed_db(db, [inst], now="2024-01-01T00:00:00")
        _seed_db(db, [inst], now="2024-01-02T00:00:00")
        client = TestClient(create_app(db))
        resp = client.get("/trends")
        assert resp.status_code == 200
        assert "<svg" in resp.text
        assert "<polyline" in resp.text

    def test_trends_shows_scan_count_in_stats_bar(self, db: Path):
        inst = make_instance("http://10.0.0.1:8971", ["front"])
        _seed_db(db, [inst], now="2024-01-01T00:00:00")
        _seed_db(db, [inst], now="2024-01-02T00:00:00")
        client = TestClient(create_app(db))
        resp = client.get("/trends")
        assert "2" in resp.text  # 2 scans in stat bar

    def test_dropped_instance_appears_in_trends(self, db: Path):
        inst1 = make_instance("http://10.0.0.1:8971", ["front"])
        inst2 = make_instance("http://10.0.0.2:8971", ["back"])
        _seed_db(db, [inst1, inst2], now="2024-01-01T00:00:00")
        _seed_db(db, [inst1], now="2024-01-02T00:00:00")  # inst2 drops off
        client = TestClient(create_app(db))
        resp = client.get("/trends")
        assert "10.0.0.2" in resp.text

    def test_longevity_table_shows_active_instances(self, db: Path):
        inst = make_instance("http://10.0.0.1:8971", ["front"])
        _seed_db(db, [inst], now="2024-01-01T00:00:00")
        _seed_db(db, [inst], now="2024-01-02T00:00:00")
        client = TestClient(create_app(db))
        resp = client.get("/trends")
        assert "10.0.0.1" in resp.text
        assert "2024-01-01" in resp.text  # first_seen date

    def test_nav_link_to_live_view_present(self, seeded_client: TestClient):
        resp = seeded_client.get("/trends")
        assert 'href="/"' in resp.text
