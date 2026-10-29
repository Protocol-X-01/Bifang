import importlib.util
import shutil
import subprocess
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location("debian_preview", Path(__file__).resolve().parents[1] / "scripts/normalize-debian-preview.py")
NORMALIZER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(NORMALIZER)
pytestmark = pytest.mark.skipif(not shutil.which("dpkg-deb"), reason="Debian package tools required")


@pytest.fixture
def package(tmp_path):
    root = tmp_path / "payload"
    (root / "DEBIAN").mkdir(parents=True)
    (root / "DEBIAN/control").write_text("Package: fixture\nVersion: 0.2.1-dev.10\nArchitecture: amd64\nMaintainer: Fixture <fixture@example.invalid>\nDescription: Version normalization fixture\n")
    (root / "DEBIAN/postinst").write_text("#!/bin/sh\nexit 0\n")
    (root / "DEBIAN/postinst").chmod(0o755)
    (root / "usr/bin").mkdir(parents=True)
    (root / "usr/bin/fixture").write_bytes(b"fixture\x00payload")
    (root / "usr/bin/fixture").chmod(0o755)
    (root / "usr/bin/alias").symlink_to("fixture")
    candidate = tmp_path / "original.deb"
    subprocess.run(["dpkg-deb", "--build", "--root-owner-group", str(root), str(candidate)], check=True, capture_output=True)
    return candidate


def test_version_rewrite_preserves_payload_and_orders_upgrades(package, tmp_path):
    output = tmp_path / "normalized.deb"
    report = NORMALIZER.normalize(package, output, "0.2.1~preview.7", "0.2.1~preview.6", "0.2.1", NORMALIZER.digest(package))
    assert report["payload_manifest_unchanged"] and report["other_control_files_unchanged"]
    assert NORMALIZER.payload_manifest(package) == NORMALIZER.payload_manifest(output)
    assert "usr/bin/fixture" in NORMALIZER.payload_manifest(output)
    assert "." not in NORMALIZER.payload_manifest(output)
    version = subprocess.run(["dpkg-deb", "-f", str(output), "Version"], check=True, capture_output=True, text=True)
    assert version.stdout.strip() == "0.2.1~preview.7"
    with pytest.raises(ValueError, match="overwrite"):
        NORMALIZER.normalize(package, output, "0.2.1~preview.7", "0.2.1~preview.6", "0.2.1", NORMALIZER.digest(package))


def test_invalid_identity_or_order_never_creates_output(package, tmp_path):
    output = tmp_path / "refused.deb"
    with pytest.raises(ValueError, match="checksum"):
        NORMALIZER.normalize(package, output, "0.2.1~preview.7", "0.2.1~preview.6", "0.2.1", "0" * 64)
    with pytest.raises(ValueError, match="sort"):
        NORMALIZER.normalize(package, output, "0.2.1~dev.10", "0.2.1~preview.6", "0.2.1", NORMALIZER.digest(package))
    assert not output.exists()
