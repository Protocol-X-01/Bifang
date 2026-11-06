import shutil

import pytest

from bifang.tools import files

# Deliberately synthetic text, not a usable private key.
BODY_LINES = (
    "U1lOVEhFVElDX0JPRFlfTElORV9PTkVfTk9UX0FfUkVBTF9QUklWQVRFX0tFWQ==",
    "U1lOVEhFVElDX0JPRFlfTElORV9UV09fTk9UX0FfUkVBTF9QUklWQVRFX0tFWQ==",
    "U1lOVEhFVElDX1RBSUw=",
)
PUBLIC_PREFIX = "U1lOVEhFVElDX"


@pytest.fixture(params=["rg", "fallback"])
def search_backend(request, monkeypatch):
    rg_binary = shutil.which("rg")
    if request.param == "rg" and rg_binary is None:
        pytest.skip("ripgrep is not installed")
    monkeypatch.setattr(files.shutil, "which", lambda _: rg_binary if request.param == "rg" else None)
    return request.param


@pytest.fixture(params=["", "    ", "\t"])
def key_document(request, tmp_path):
    indentation = request.param
    lines = [
        f"public before {PUBLIC_PREFIX}",
        indentation + "-----BEGIN RSA PRIVATE KEY-----",
        *(indentation + line for line in BODY_LINES),
        indentation + "-----END RSA PRIVATE KEY-----",
        f"public after {PUBLIC_PREFIX}",
    ]
    (tmp_path / "settings.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return lines


def match_rows(result):
    assert result != "No matches"
    return [(path, int(number), content) for path, number, content in
            (line.split(":", 2) for line in result.splitlines())]


@pytest.mark.parametrize(("query", "line_number"), [
    ("TElORV9PTkV", 3),
    (BODY_LINES[-1], 5),
])
def test_search_body_fragment_keeps_match_without_key_material(
    tmp_path, search_backend, key_document, query, line_number
):
    result = files.search(tmp_path, query)

    rows = match_rows(result)
    assert [(path, number) for path, number, _ in rows] == [("settings.txt", line_number)]
    assert "[REDACTED]" in rows[0][2]
    assert not any(body in result for body in BODY_LINES)
    assert query not in result


def test_search_multiple_matches_preserves_public_lines_and_numbers(
    tmp_path, search_backend, key_document
):
    result = files.search(tmp_path, PUBLIC_PREFIX)

    rows = match_rows(result)
    assert [(path, number) for path, number, _ in rows] == [
        ("settings.txt", number) for number in (1, 3, 4, 5, 7)
    ]
    assert rows[0][2] == key_document[0]
    assert rows[-1][2] == key_document[-1]
    assert all("[REDACTED]" in content for _, _, content in rows[1:-1])
    assert not any(body in result for body in BODY_LINES)


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_search_private_key_footer_without_final_newline(tmp_path, search_backend, newline):
    lines = ["public", "-----BEGIN PRIVATE KEY-----", BODY_LINES[-1], "-----END PRIVATE KEY-----"]
    (tmp_path / "fixture.txt").write_bytes(newline.join(lines).encode())

    rows = match_rows(files.search(tmp_path, "PRIVATE KEY"))

    assert [(path, number) for path, number, _ in rows] == [("fixture.txt", 2), ("fixture.txt", 4)]
    assert all("REDACTED" in content for _, _, content in rows)


def test_search_raw_inline_secret_still_returns_public_matching_line(tmp_path, search_backend):
    synthetic_value = "synthetic-fixture-token-246801"
    (tmp_path / "settings.txt").write_text(f'API_KEY="{synthetic_value}"\n', encoding="utf-8")

    assert files.search(tmp_path, synthetic_value) == "settings.txt:1:API_KEY=[REDACTED]"


def test_search_does_not_return_oversized_file_context(tmp_path, search_backend, monkeypatch):
    monkeypatch.setattr(files, "MAX_READ_FILE_BYTES", 128)
    (tmp_path / "large.txt").write_text("public-match " + "x" * 128, encoding="utf-8")

    assert files.search(tmp_path, "public-match") == "No matches"


def test_search_keeps_private_path_and_symlink_protections(tmp_path, search_backend):
    root = tmp_path / "workspace"
    root.mkdir()
    (root / "public.txt").write_text("public-match", encoding="utf-8")
    (root / "secrets.json").write_text("public-match private-fixture", encoding="utf-8")
    outside = tmp_path / "outside.txt"
    outside.write_text("public-match outside-fixture", encoding="utf-8")
    (root / "external.txt").symlink_to(outside)

    assert files.search(root, "public-match") == "public.txt:1:public-match"


def test_search_keeps_output_bounded(tmp_path, search_backend):
    (tmp_path / "public.txt").write_text(("public-match " + "x" * 200 + "\n") * 1100, encoding="utf-8")

    result = files.search(tmp_path, "public-match")

    assert len(result) <= 100000
    assert len(result.splitlines()) <= 1000
    assert result.startswith("public.txt:1:public-match ")
