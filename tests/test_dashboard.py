"""Tests for frigate_scanner.dashboard — FastAPI app routes."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from frigate_scanner.dashboard import create_app
from frigate_scanner.store import SCHEMA, record_scan


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
        # DB file does not exist — app should return 200 with a placeholder page
        client = TestClient(create_app(db))
        resp = client.get("/")
        assert resp.status_code == 200

    def test_missing_db_shows_no_data_message(self, db: Path):
        client = TestClient(create_app(db))
        resp = client.get("/")
        assert "No scan data" in resp.text

    def test_seeded_db_returns_html(self, seeded_client: TestClient):
        resp = seeded_client.get("/")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]

    def test_instance_urls_in_response(self, seeded_client: TestClient):
        resp = seeded_client.get("/")
        assert "10.0.0.1:8971" in resp.text
        assert "10.0.0.2:8971" in resp.text

    def test_camera_names_in_response(self, seeded_client: TestClient):
        resp = seeded_client.get("/")
        assert "front" in resp.text
        assert "garage" in resp.text

    def test_country_filter_button_rendered(self, seeded_client: TestClient):
        resp = seeded_client.get("/")
        assert 'data-country="US"' in resp.text

    def test_new_badge_on_first_scan(self, seeded_client: TestClient):
        # All instances in the first scan are "new" (no previous scan)
        resp = seeded_client.get("/")
        assert 'class="badge badge-new"' in resp.text

    def test_second_scan_known_instances_not_new(self, db: Path):
        inst = make_instance("http://10.0.0.1:8971", ["front"])
        _seed_db(db, [inst], now="2024-01-01T00:00:00")
        _seed_db(db, [inst], now="2024-01-02T00:00:00")
        client = TestClient(create_app(db))
        resp = client.get("/")
        assert resp.status_code == 200
        # Known instance should not show NEW badge
        assert 'class="badge badge-new"' not in resp.text

    def test_stats_bar_shows_instance_count(self, seeded_client: TestClient):
        resp = seeded_client.get("/")
        assert "stat-value" in resp.text
