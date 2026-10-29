import hashlib
import json
import shutil
from pathlib import Path

import pytest

from bifang.model_ids import TOKEN_FACTORY_ROLES
from bifang.routing import TOKEN_FACTORY_ROLES as ROUTING_ROLES
from bifang.vercel_bundle import MODULES, TEMPLATES, build_bundle


@pytest.fixture
def repository(tmp_path):
    source = Path(__file__).resolve().parents[1]
    root = tmp_path / "repository"
    for relative in (["deploy/vercel-judge-relay/" + name for name in TEMPLATES] +
                     ["src/bifang/" + name for name in MODULES] + ["LICENSE"]):
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / relative, destination)
    (root / ".env").write_text("SYNTHETIC_PRIVATE=must-not-export\n")
    (root / "src/bifang/agent.py").write_text("Synthetic unlisted agent module")
    return root


def test_bundle_copies_only_reviewed_relay_files_and_verifies_hashes(repository, tmp_path):
    output = tmp_path / "bundle"
    manifest = build_bundle(repository, output)
    expected = set(TEMPLATES) | {"bifang/" + name for name in MODULES} | {"LICENSE"}
    assert {row["path"] for row in manifest["files"]} == expected
    assert not (output / ".env").exists()
    assert not (output / "bifang/agent.py").exists()
    for row in manifest["files"]:
        assert hashlib.sha256((output / row["path"]).read_bytes()).hexdigest() == row["sha256"]


def test_bundle_never_overwrites_existing_output(repository, tmp_path):
    output = tmp_path / "existing"
    output.mkdir()
    (output / "keep").write_text("unchanged")
    with pytest.raises(FileExistsError):
        build_bundle(repository, output)
    assert (output / "keep").read_text() == "unchanged"


def test_bundle_rejects_in_repository_destination(repository):
    with pytest.raises(ValueError, match="outside the repository"):
        build_bundle(repository, repository / "bundle")
    assert not (repository / "bundle").exists()


def test_bundle_rejects_symlinked_sources_before_writing(repository, tmp_path):
    source = repository / "src/bifang/model_ids.py"
    source.unlink()
    outside = tmp_path / "outside"
    outside.write_text("Synthetic out-of-repository data")
    source.symlink_to(outside)
    with pytest.raises(ValueError, match="symlinked"):
        build_bundle(repository, tmp_path / "rejected")
    assert not (tmp_path / "rejected").exists()


def test_routing_and_relay_share_one_authoritative_model_catalog():
    assert TOKEN_FACTORY_ROLES is ROUTING_ROLES


def test_managed_runtime_is_explicit_and_container_is_not_uploaded(repository, tmp_path):
    output = tmp_path / "bundle"
    build_bundle(repository, output)
    configuration = json.loads((output / "vercel.json").read_text())
    assert configuration["framework"] == "fastapi"
    assert configuration["functions"]["app.py"]["maxDuration"] == 120
    assert "Dockerfile.vercel" in (output / ".vercelignore").read_text().splitlines()
