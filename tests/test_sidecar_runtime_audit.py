import runpy
from pathlib import Path
from types import SimpleNamespace

import pytest

AUDIT = runpy.run_path(str(Path(__file__).resolve().parents[1] / "scripts/check-sidecar-runtime.py"))


@pytest.mark.parametrize("name", ["../escape.so", "/tmp/escape.so", "folder\\escape.so"])
def test_archive_paths_cannot_escape_extraction(tmp_path, name):
    reader = SimpleNamespace(toc={name: (0, 4, 4, 0, "b")}, extract=lambda _: b"\x7fELF")
    with pytest.raises(ValueError, match="Unsafe"):
        AUDIT["extract_native"](reader, tmp_path)
    assert not list(tmp_path.iterdir())


def test_archive_rejects_large_members_before_decompression(tmp_path):
    def extract(name):
        pytest.fail("Oversized member must not be extracted")

    reader = SimpleNamespace(toc={"huge.so": (0, 1, 268435457, 1, "b")}, extract=extract)
    with pytest.raises(ValueError, match="size exceeds"):
        AUDIT["extract_native"](reader, tmp_path)


def test_archive_includes_elf_data_members_but_does_not_materialize_links(tmp_path):
    payloads = {"lib/native.so": b"\x7fELFfixture", "NOTICE": b"fixture text"}
    reader = SimpleNamespace(toc={name: (0, len(data), len(data), 0, "x") for name, data in payloads.items()}, extract=payloads.__getitem__)
    reader.toc["link"] = (0, 9, 9, 0, "n")
    assert AUDIT["extract_native"](reader, tmp_path) == 1
    assert (tmp_path / "lib/native.so").read_bytes() == payloads["lib/native.so"]
    assert not (tmp_path / "link").exists()
    assert not (tmp_path / "NOTICE").exists()
