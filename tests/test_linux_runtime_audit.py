import json
import os
import runpy
import shutil
import subprocess
from pathlib import Path

import pytest

AUDITOR = runpy.run_path(str(Path(__file__).resolve().parents[1] / "scripts/check-linux-runtime.py"))
RPM = runpy.run_path(str(Path(__file__).resolve().parents[1] / "scripts/bundle-linux.py"))


@pytest.mark.parametrize("fail", [False, True])
def test_bundles_restore_pristine_binary_for_each_format_and_after_failure(tmp_path, monkeypatch, fail):
    directory = tmp_path / "desktop/src-tauri/target/debug"
    directory.mkdir(parents=True)
    binary = directory / "bifang-desktop"
    pristine = b"fixture __TAURI_BUNDLE_TYPE_VAR_UNK executable"
    binary.write_bytes(pristine)
    binary.chmod(0o755)
    (directory.parent.parent / "tauri.conf.json").write_text(json.dumps({"version": "0.2.1-dev.9"}))
    seen = []
    monkeypatch.setattr(os, "confstr", lambda name: "glibc 2.35")

    def invoke(command, **kwargs):
        assert binary.read_bytes() == pristine
        selected = command[command.index("--bundles") + 1]
        seen.append(selected)
        binary.write_bytes(b"patched " + selected.encode())
        if selected == "rpm":
            assert json.loads(command[-1])["bundle"]["linux"]["rpm"]["release"] == "0.dev.9"
            assert json.loads(command[-1])["bundle"]["linux"]["rpm"]["depends"] == ["libc.so.6(GLIBC_2.35)(64bit)"]
        if fail:
            raise subprocess.CalledProcessError(1, command)

    monkeypatch.setattr(subprocess, "run", invoke)
    if fail:
        with pytest.raises(subprocess.CalledProcessError):
            RPM["bundle"](tmp_path, ["deb", "rpm"], True)
    else:
        RPM["bundle"](tmp_path, ["deb", "rpm"], True)
    assert seen == (["deb"] if fail else ["deb", "rpm"])
    assert binary.read_bytes() == pristine and binary.stat().st_mode & 0o777 == 0o755
    assert not list(directory.glob(".bifang-unbundled-*"))


def test_rpm_prerelease_mapping_preserves_configured_release_version():
    assert RPM["rpm_override"]("0.2.1-dev.9") == {
        "version": "0.2.1", "bundle": {"linux": {"rpm": {"release": "0.dev.9"}}}}
    assert RPM["rpm_override"]("1.2.3") == {}


def test_bundles_refuse_to_reuse_an_already_patched_desktop(tmp_path):
    directory = tmp_path / "desktop/src-tauri/target/debug"
    directory.mkdir(parents=True)
    (directory / "bifang-desktop").write_bytes(b"fixture __TAURI_BUNDLE_TYPE_VAR_RPM executable")
    with pytest.raises(ValueError, match="already patched"):
        RPM["bundle"](tmp_path, ["rpm"], True)


@pytest.mark.parametrize("version", ["0.2.1-dev-x", "0.2.1+metadata", "0.2", "0.2.1;false"])
def test_rpm_mapping_refuses_unsupported_version_shapes(version):
    with pytest.raises(ValueError):
        RPM["rpm_override"](version)


def test_runtime_requirements_ignore_definitions_and_compare_versions_numerically():
    output = """Version definition section
Name: GLIBC_99.0
Version needs section '.gnu.version_r' contains 3 entries:
Name: GLIBC_2.9
Name: GLIBC_2.39
Name: GLIBCXX_3.4.9
Name: GLIBCXX_3.4.32
Name: CXXABI_1.3
"""
    assert AUDITOR["requirements"](output) == {"GLIBC": "2.39", "GLIBCXX": "3.4.32", "CXXABI": "1.3"}
    assert AUDITOR["requirements"]("No version information found") == {}


@pytest.mark.parametrize("value", ["latest", "2.39;false", "2", "2.-1", ""])
def test_runtime_ceiling_rejects_non_numeric_values(value):
    with pytest.raises(ValueError):
        AUDITOR["version_tuple"](value)


def test_actual_elf_audit_does_not_execute_payload_and_rejects_external_links(tmp_path):
    if not shutil.which("readelf"):
        pytest.skip("Linux readelf required")
    shutil.copyfile("/usr/bin/true", tmp_path / "fixture")
    (tmp_path / "not-elf").write_text("must not execute")
    (tmp_path / "internal").symlink_to("fixture")
    report = AUDITOR["audit"](tmp_path, "99.0")
    assert report["passed"] and report["elf_count"] == 1
    assert report["binaries"][0]["path"] == "fixture"
    assert not AUDITOR["audit"](tmp_path, "0.0")["passed"]
    (tmp_path / "external").symlink_to("/usr/bin/true")
    assert "External symlink: external" in AUDITOR["audit"](tmp_path)["violations"]


def test_empty_payload_is_not_success(tmp_path):
    assert not AUDITOR["audit"](tmp_path)["passed"]
