from types import SimpleNamespace

import pytest

from bifang import system_metrics
from bifang.workbench import dispatch


def test_metrics_use_a_measured_cpu_interval_and_available_memory(tmp_path, monkeypatch):
    intervals = []
    monkeypatch.setattr(system_metrics.psutil, "cpu_percent", lambda interval: intervals.append(interval) or 25.5)
    monkeypatch.setattr(system_metrics.psutil, "virtual_memory", lambda: SimpleNamespace(total=1000, available=400, used=999))
    monkeypatch.setattr(system_metrics.psutil, "disk_usage", lambda path: SimpleNamespace(total=1000, used=500, free=400, percent=55.5))
    result = system_metrics.sample_system_metrics(tmp_path)
    assert intervals == [0.1]
    assert result["cpu"] == {"available": True, "percent": 25.5, "sample_ms": 100}
    assert result["memory"]["used_bytes"] == 600
    assert result["memory"]["percent"] == 60
    assert result["disk"]["percent"] == 55.5
    assert not result["gpu"]["available"]
    assert result["sampled_at"].endswith("+00:00")
    assert result["collection_ms"] >= 0
    assert not {"hostname", "processes", "environment", "network"}.intersection(result)


@pytest.mark.parametrize("failed", ["cpu_percent", "virtual_memory", "disk_usage"])
def test_os_failure_is_explicit_partial_unavailability_without_diagnostic_leaks(tmp_path, monkeypatch, failed):
    monkeypatch.setattr(system_metrics.psutil, "cpu_percent", lambda interval: 0)
    monkeypatch.setattr(system_metrics.psutil, "virtual_memory", lambda: SimpleNamespace(total=1000, available=1000))
    monkeypatch.setattr(system_metrics.psutil, "disk_usage", lambda path: SimpleNamespace(total=1000, used=0, free=1000, percent=0))
    def unavailable(*args, **kwargs):
        raise PermissionError("private-fixture-error")
    monkeypatch.setattr(system_metrics.psutil, failed, unavailable)
    result = system_metrics.sample_system_metrics(tmp_path)
    field = {"cpu_percent": "cpu", "virtual_memory": "memory", "disk_usage": "disk"}[failed]
    assert result[field]["available"] is False
    assert "percent" not in result[field]
    assert "private-fixture-error" not in str(result)
    assert sum(result[name]["available"] for name in ("cpu", "memory", "disk")) == 2


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -1, 101])
def test_invalid_cpu_measurements_are_not_presented_as_real_data(tmp_path, monkeypatch, value):
    monkeypatch.setattr(system_metrics.psutil, "cpu_percent", lambda interval: value)
    assert system_metrics.sample_system_metrics(tmp_path)["cpu"]["available"] is False


def test_metrics_protocol_collects_real_host_readings_without_plugin_discovery(tmp_path, monkeypatch):
    from bifang.plugins.catalog import PluginCatalog
    def forbidden(*args):
        raise AssertionError("Metrics must not inspect or load plugins")
    monkeypatch.setattr(PluginCatalog, "discover", forbidden)
    result = dispatch({"version": 1, "action": "metrics.sample", "workspace": str(tmp_path)})
    assert result["schema"] == 1
    assert result["cpu"]["available"]
    assert result["memory"]["available"]
    assert result["disk"]["available"]
    assert 0 <= result["cpu"]["percent"] <= 100
    assert result["memory"]["total_bytes"] > 0
    assert result["disk"]["total_bytes"] > 0
