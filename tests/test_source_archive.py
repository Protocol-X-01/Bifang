import hashlib
import json
import os
import runpy
import tarfile
from pathlib import Path

import pytest

EXPORTER = runpy.run_path(str(Path(__file__).resolve().parents[1] / "scripts/build-source-archive.py"))


@pytest.fixture
def project(tmp_path):
    root = tmp_path / "project"
    for name in EXPORTER["REQUIRED"]:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"fixture source for {name}\n")
    return root


def test_archive_preserves_worktree_build_support_and_omits_private_state(project, tmp_path):
    for name in [".env", ".env.local", "desktop/.env", "src/credentials.json", "desktop/node_modules/private.ts",
                 "desktop/src-tauri/target/private.rs", "src/.bifang/audit.json", "src/private.key", "docs/private.log"]:
        path = project / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("synthetic-private-value")
    selected = project / "desktop/dev/localWorkspaces.ts"
    selected.write_text("export const actualWorkingTree = true;\n")
    report = EXPORTER["build_archive"](project, tmp_path / "source.tar.gz")
    with tarfile.open(tmp_path / "source.tar.gz") as archive:
        names = set(archive.getnames())
        assert names == EXPORTER["REQUIRED"] | {"SOURCE_MANIFEST.json"}
        assert archive.extractfile(selected.relative_to(project).as_posix()).read() == selected.read_bytes()
        manifest = json.load(archive.extractfile("SOURCE_MANIFEST.json"))
        for item in manifest["files"]:
            assert hashlib.sha256(archive.extractfile(item["path"]).read()).hexdigest() == item["sha256"]
    assert not report["publication_approved"]
    assert (tmp_path / "source.tar.gz").stat().st_mode & 0o777 == 0o600


def test_archive_preserves_android_sources_and_wrapper_without_local_sdk_or_signing_state(project, tmp_path):
    android = project / "companion/src-tauri/gen/android"
    prefix = "companion/src-tauri/gen/android/"
    included = sorted(name.removeprefix(prefix) for name in EXPORTER["ANDROID_REQUIRED"])
    excluded = ["local.properties", "key.properties", "keystore.properties", "release.jks",
                "build/generated.json", "app/build/generated.json", ".gradle/state.json", "unreviewed.jar",
                "tauri.properties", "tauri.settings.gradle", "app/tauri.build.gradle.kts"]
    for name in included + excluded:
        path = android / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("Synthetic Android build input")
    EXPORTER["build_archive"](project, tmp_path / "android.tar.gz")
    with tarfile.open(tmp_path / "android.tar.gz") as archive:
        names = set(archive.getnames())
        assert all(prefix + name in names for name in included)
        assert all(prefix + name not in names for name in excluded)


def test_archive_refuses_incomplete_initialized_android_project(project, tmp_path):
    android = project / "companion/src-tauri/gen/android"
    android.mkdir(parents=True)
    with pytest.raises(ValueError, match="gradle-wrapper.jar"):
        EXPORTER["build_archive"](project, tmp_path / "incomplete-android.tar.gz")


def test_archive_requires_the_packaged_distribution_runtime_asset(project, tmp_path):
    for name in EXPORTER["ANDROID_REQUIRED"]:
        path = project / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("Synthetic Android source")
    (project / "companion/src-tauri/gen/android/app/src/main/assets/bifang_runtime.py").unlink()
    with pytest.raises(ValueError, match="bifang_runtime.py"):
        EXPORTER["build_archive"](project, tmp_path / "missing-runtime.tar.gz")
    assert not (tmp_path / "missing-runtime.tar.gz").exists()


def test_archive_is_reproducible_across_mtimes_and_output_names(project, tmp_path):
    first = EXPORTER["build_archive"](project, tmp_path / "first.tar.gz")
    for name in EXPORTER["REQUIRED"]:
        os.utime(project / name, (1_700_000_000, 1_700_000_000))
    second = EXPORTER["build_archive"](project, tmp_path / "second.tar.gz")
    assert first["archive_sha256"] == second["archive_sha256"]
    assert (tmp_path / "first.tar.gz").read_bytes() == (tmp_path / "second.tar.gz").read_bytes()


def test_archive_refuses_missing_vite_support_module(project, tmp_path):
    (project / "desktop/dev/localWorkspaces.ts").unlink()
    with pytest.raises(ValueError, match="desktop/dev/localWorkspaces.ts"):
        EXPORTER["build_archive"](project, tmp_path / "missing.tar.gz")
    assert not (tmp_path / "missing.tar.gz").exists()


def test_archive_preserves_exact_relay_runtime_metadata_without_other_dotfiles(project, tmp_path):
    relay = project / "deploy/vercel-judge-relay"
    (relay / ".python-version").write_text("3.11\n")
    (relay / ".vercelignore").write_text(".env\n")
    (relay / ".env").write_text("SYNTHETIC_PRIVATE=not-for-export\n")
    (relay / ".other-config").write_text("unreviewed")
    output = tmp_path / "relay-source.tar.gz"
    EXPORTER["build_archive"](project, output)
    with tarfile.open(output) as archive:
        assert archive.extractfile("deploy/vercel-judge-relay/.python-version").read() == b"3.11\n"
        assert archive.extractfile("deploy/vercel-judge-relay/.vercelignore").read() == b".env\n"
        assert "deploy/vercel-judge-relay/.env" not in archive.getnames()
        assert "deploy/vercel-judge-relay/.other-config" not in archive.getnames()


def test_archive_refuses_missing_relay_runtime_pin(project, tmp_path):
    (project / "deploy/vercel-judge-relay/.python-version").unlink()
    with pytest.raises(ValueError, match="python-version"):
        EXPORTER["build_archive"](project, tmp_path / "missing-relay.tar.gz")


def test_archive_preserves_remote_service_build_recipe_and_requires_it(project, tmp_path):
    recipe = project / "deploy/Dockerfile.remote"
    recipe.write_text("FROM python:3.11-slim\nCOPY src/ ./src/\n")
    output = tmp_path / "remote-service.tar.gz"
    EXPORTER["build_archive"](project, output)
    with tarfile.open(output) as archive:
        assert archive.extractfile("deploy/Dockerfile.remote").read() == recipe.read_bytes()
    recipe.unlink()
    with pytest.raises(ValueError, match="Dockerfile.remote"):
        EXPORTER["build_archive"](project, tmp_path / "missing-remote-service.tar.gz")
    assert not (tmp_path / "missing-remote-service.tar.gz").exists()


def test_exported_source_can_build_the_complete_relay_bundle(project, tmp_path):
    from bifang.vercel_bundle import MODULES, TEMPLATES, build_bundle

    assert {"deploy/vercel-judge-relay/" + name for name in TEMPLATES} <= EXPORTER["REQUIRED"]
    for name in MODULES:
        path = project / "src/bifang" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("Synthetic relay module")
    output = tmp_path / "relay-roundtrip.tar.gz"
    EXPORTER["build_archive"](project, output)
    extracted = tmp_path / "extracted"
    with tarfile.open(output) as archive:
        archive.extractall(extracted, filter="data")
    report = build_bundle(extracted, tmp_path / "deploy-bundle")
    assert {item["path"] for item in report["files"]} == set(TEMPLATES) | {"bifang/" + name for name in MODULES} | {"LICENSE"}


def test_archive_refuses_source_symlinks_and_never_overwrites(project, tmp_path):
    (project / "src/leak.py").symlink_to(project / ".env.example")
    with pytest.raises(ValueError, match="regular contained file"):
        EXPORTER["build_archive"](project, tmp_path / "symlink.tar.gz")
    (tmp_path / "existing.tar.gz").write_bytes(b"preserve")
    with pytest.raises(ValueError, match="overwrite"):
        EXPORTER["build_archive"](project, tmp_path / "existing.tar.gz")
    assert (tmp_path / "existing.tar.gz").read_bytes() == b"preserve"


def test_archive_refuses_oversized_inputs_before_writing(project, tmp_path):
    with pytest.raises(ValueError, match="size limit"):
        EXPORTER["build_archive"](project, tmp_path / "large.tar.gz", max_file_bytes=4)
    assert not (tmp_path / "large.tar.gz").exists()
