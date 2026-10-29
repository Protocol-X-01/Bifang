import hashlib
import runpy
from pathlib import Path

import pytest

COLLECT = runpy.run_path(str(Path(__file__).resolve().parents[1] / "scripts/collect-platform-packages.py"))["collect"]


@pytest.mark.parametrize("target,formats", [
    ("x86_64-pc-windows-msvc", {"nsis": "setup.exe", "msi": "setup.msi"}),
    ("x86_64-apple-darwin", {"dmg": "Bifang Intel.dmg"}),
    ("aarch64-apple-darwin", {"dmg": "Bifang ARM.dmg"}),
])
def test_both_applications_and_each_format_are_required(tmp_path, target, formats):
    for application in ("desktop", "companion"):
        for kind, name in formats.items():
            folder = tmp_path / application / "src-tauri/target/release/bundle" / kind
            folder.mkdir(parents=True)
            (folder / name).write_bytes(b"synthetic package")
    report = COLLECT(tmp_path, target)
    assert len(report["packages"]) == 2 * len(formats)
    assert all(item["sha256"] == hashlib.sha256(b"synthetic package").hexdigest() for item in report["packages"])
    selected = tmp_path / report["packages"][-1]["path"]
    selected.unlink()
    with pytest.raises(ValueError, match="exactly one"):
        COLLECT(tmp_path, target)


def test_ambiguous_or_empty_artifacts_cannot_pass(tmp_path):
    for application in ("desktop", "companion"):
        folder = tmp_path / application / "src-tauri/target/release/bundle/dmg"
        folder.mkdir(parents=True)
        (folder / "one.dmg").write_bytes(b"synthetic")
    extra = tmp_path / "desktop/src-tauri/target/release/bundle/dmg/two.dmg"
    extra.write_bytes(b"other")
    with pytest.raises(ValueError, match="exactly one"):
        COLLECT(tmp_path, "aarch64-apple-darwin")
    extra.unlink()
    (extra.parent / "one.dmg").write_bytes(b"")
    with pytest.raises(ValueError, match="nonempty"):
        COLLECT(tmp_path, "aarch64-apple-darwin")


def test_unknown_platform_cannot_report_success(tmp_path):
    with pytest.raises(ValueError, match="Unsupported"):
        COLLECT(tmp_path, "unknown")
