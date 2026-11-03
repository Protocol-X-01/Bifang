from io import StringIO

import pytest
from rich.console import Console

from bifang import cli
from bifang.config import Config
from bifang.providers.types import ProviderConfig


@pytest.mark.parametrize(
    ("providers", "expected_status", "expected_exit"),
    [
        ({}, "missing", 1),
        (
            {"nvidia": ProviderConfig(name="nvidia", base_url="http://127.0.0.1:8000/v1")},
            "endpoint configured",
            0,
        ),
        (
            {"nvidia": ProviderConfig(name="nvidia", api_key="test-key")},
            "credential set",
            0,
        ),
    ],
)
def test_doctor_reports_model_access_status(monkeypatch, providers, expected_status, expected_exit):
    output = StringIO()
    monkeypatch.setattr(cli, "C", Console(file=output, force_terminal=False))
    monkeypatch.setattr(cli.shutil, "which", lambda name: "/usr/bin/git" if name == "git" else None)

    result = cli.doctor(Config(default_provider="nvidia", providers=providers))

    assert result == expected_exit
    assert f"api_access {expected_status}" in output.getvalue()
