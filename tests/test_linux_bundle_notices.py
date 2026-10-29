import importlib.util
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location("linux_bundle_notices", Path(__file__).resolve().parents[1] / "scripts/collect-linux-bundle-notices.py")
COLLECTOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(COLLECTOR)


def test_payload_path_rejects_parent_traversal_and_external_symlinks(tmp_path):
    root = tmp_path / "payload"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.write_bytes(b"fixture")
    (root / "link").symlink_to(outside)
    for relative in ("../outside", str(outside), "link"):
        with pytest.raises(ValueError):
            COLLECTOR.payload_file(root, relative)


def test_payload_path_accepts_regular_contained_file(tmp_path):
    source = tmp_path / "library.so"
    source.write_bytes(b"fixture")
    assert COLLECTOR.payload_file(tmp_path, "library.so") == source


def test_package_ownership_parser_preserves_architecture_and_rejects_ambiguous_rows(tmp_path):
    library = tmp_path / "libfixture.so"
    library.write_bytes(b"fixture")
    lines = f"libfixture:amd64: {library}\nlibfirst, libsecond: {library}\ninvalid: missing\n"
    assert COLLECTOR.owners(lines) == [("libfixture:amd64", library)]


def test_correspondence_requires_code_data_and_nonempty_build_identity():
    identity = {"build_ids": ["abcd"], "text_rodata_sha256": "fixture", "text_rodata_bytes": 12}
    assert COLLECTOR.correspondence(identity, dict(identity))
    assert not COLLECTOR.correspondence(identity, {**identity, "text_rodata_sha256": "different"})
    assert not COLLECTOR.correspondence(identity, {**identity, "build_ids": []})
    assert not COLLECTOR.correspondence({**identity, "build_ids": []}, {**identity, "build_ids": []})


def test_distribution_notice_capture_is_content_bound_and_rejects_external_link(tmp_path):
    docs = tmp_path / "docs"
    output = tmp_path / "output"
    (docs / "libfixture").mkdir(parents=True)
    output.mkdir()
    notice = docs / "libfixture/copyright"
    notice.write_text("Synthetic public notice")
    result = COLLECTOR.retain_notice(docs, "libfixture:amd64", output)
    assert result["retained"] and result["sha256"] == COLLECTOR.digest(notice)
    assert (output / result["file"]).read_bytes() == notice.read_bytes()
    notice.unlink()
    outside = tmp_path / "unrelated"
    outside.write_text("Not a distribution notice")
    notice.symlink_to(outside)
    assert COLLECTOR.retain_notice(docs, "libfixture:amd64", output) == {"retained": False}


def test_payload_hash_mismatch_stops_before_provider_queries(tmp_path):
    payload = tmp_path / "payload"
    payload.mkdir()
    (payload / "libfixture.so").write_bytes(b"different")
    with pytest.raises(ValueError, match="does not match"):
        COLLECTOR.audit(payload, {"binaries": [{"path": "libfixture.so", "sha256": "wrong"}]}, tmp_path / "report")
