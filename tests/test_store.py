"""Unit tests for frigate_scanner.store — Diff and record_scan transitions."""

import pytest

from frigate_scanner.store import Diff, record_scan

URL_A = "http://192.168.1.1:8971"
URL_B = "http://192.168.1.2:8971"


def make_instance(url: str, cameras: list[str]) -> dict:
    return {
        "url": url,
        "ip": "1.2.3.4",
        "port": 8971,
        "country": None,
        "country_code": None,
        "org": None,
        "frigate_version": "0.14.0",
        "probe_camera_count": len(cameras),
        "probe_cameras": cameras,
    }


def do_scan(db_path, instances: list[dict], now: str = "2024-01-01T00:00:00") -> Diff:
    return record_scan(db_path, instances, hosts_scanned=100, now=now)


class TestDiff:
    def test_empty_diff_no_changes(self):
        assert not Diff().has_changes

    def test_new_instances_has_changes(self):
        assert Diff(new_instances=[URL_A]).has_changes

    def test_returned_instances_has_changes(self):
        assert Diff(returned_instances=[URL_A]).has_changes

    def test_dropped_instances_has_changes(self):
        assert Diff(dropped_instances=[{"url": URL_A}]).has_changes

    def test_new_cameras_has_changes(self):
        assert Diff(new_cameras=[(URL_A, "cam1")]).has_changes

    def test_dropped_cameras_has_changes(self):
        assert Diff(dropped_cameras=[(URL_A, "cam1")]).has_changes


class TestRecordScan:
    def test_first_scan_all_instances_new(self, tmp_path):
        db = tmp_path / "test.db"
        diff = do_scan(db, [make_instance(URL_A, ["cam1"]), make_instance(URL_B, ["cam2"])])
        assert sorted(diff.new_instances) == sorted([URL_A, URL_B])
        assert diff.returned_instances == []
        assert diff.dropped_instances == []
        assert sorted(diff.new_cameras) == sorted([(URL_A, "cam1"), (URL_B, "cam2")])
        assert diff.dropped_cameras == []

    def test_second_scan_same_hosts_no_diff(self, tmp_path):
        db = tmp_path / "test.db"
        instances = [make_instance(URL_A, ["cam1"]), make_instance(URL_B, ["cam2"])]
        do_scan(db, instances, now="2024-01-01T00:00:00")
        diff = do_scan(db, instances, now="2024-01-02T00:00:00")
        assert not diff.has_changes

    def test_host_dropped(self, tmp_path):
        db = tmp_path / "test.db"
        do_scan(db, [make_instance(URL_A, ["cam1"]), make_instance(URL_B, ["cam2"])], now="2024-01-01T00:00:00")
        diff = do_scan(db, [make_instance(URL_A, ["cam1"])], now="2024-01-02T00:00:00")
        assert diff.new_instances == []
        assert diff.returned_instances == []
        assert len(diff.dropped_instances) == 1
        assert diff.dropped_instances[0]["url"] == URL_B
        assert diff.new_cameras == []

    def test_dropped_host_returns(self, tmp_path):
        db = tmp_path / "test.db"
        # scan 1: A + B present
        do_scan(db, [make_instance(URL_A, ["cam1"]), make_instance(URL_B, ["cam2"])], now="2024-01-01T00:00:00")
        # scan 2: B disappears
        do_scan(db, [make_instance(URL_A, ["cam1"])], now="2024-01-02T00:00:00")
        # scan 3: B returns
        diff = do_scan(db, [make_instance(URL_A, ["cam1"]), make_instance(URL_B, ["cam2"])], now="2024-01-03T00:00:00")
        assert diff.new_instances == []
        assert diff.returned_instances == [URL_B]
        assert diff.dropped_instances == []

    def test_new_camera_detected(self, tmp_path):
        db = tmp_path / "test.db"
        do_scan(db, [make_instance(URL_A, ["cam1"])], now="2024-01-01T00:00:00")
        diff = do_scan(db, [make_instance(URL_A, ["cam1", "cam2"])], now="2024-01-02T00:00:00")
        assert diff.new_cameras == [(URL_A, "cam2")]
        assert diff.dropped_cameras == []

    def test_camera_dropped(self, tmp_path):
        db = tmp_path / "test.db"
        do_scan(db, [make_instance(URL_A, ["cam1", "cam2"])], now="2024-01-01T00:00:00")
        diff = do_scan(db, [make_instance(URL_A, ["cam1"])], now="2024-01-02T00:00:00")
        assert diff.new_cameras == []
        assert diff.dropped_cameras == [(URL_A, "cam2")]

    def test_new_host_alongside_existing(self, tmp_path):
        db = tmp_path / "test.db"
        do_scan(db, [make_instance(URL_A, ["cam1"])], now="2024-01-01T00:00:00")
        diff = do_scan(db, [make_instance(URL_A, ["cam1"]), make_instance(URL_B, ["cam2"])], now="2024-01-02T00:00:00")
        assert diff.new_instances == [URL_B]
        assert diff.returned_instances == []
        assert diff.dropped_instances == []
        assert diff.new_cameras == [(URL_B, "cam2")]

    def test_empty_scan_after_populated(self, tmp_path):
        db = tmp_path / "test.db"
        do_scan(db, [make_instance(URL_A, ["cam1"]), make_instance(URL_B, ["cam2"])], now="2024-01-01T00:00:00")
        diff = do_scan(db, [], now="2024-01-02T00:00:00")
        assert diff.new_instances == []
        assert diff.returned_instances == []
        assert len(diff.dropped_instances) == 2
        dropped_urls = {d["url"] for d in diff.dropped_instances}
        assert dropped_urls == {URL_A, URL_B}
