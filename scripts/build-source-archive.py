from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import os
import tarfile
from pathlib import Path

TREES = ("src", "tests", "scripts", "docs", "desktop", "companion", "tui", "deploy", "examples", "evaluations", ".github", "bifang-brand-kit", "demo-output")
ROOT_FILES = ("LICENSE", "README.md", "pyproject.toml", "uv.lock", "Dockerfile", ".dockerignore", ".gitignore", ".env.example")
OPTIONAL_ROOT_FILES = ("CONTRIBUTING.md", "SECURITY.md", "CODEOWNERS", "bifang-design-tokens.json")
EXCLUDED_DIRS = {"node_modules", "target", "dist", "build", "__pycache__", ".git", ".venv", ".bifang", ".arca"}
EXTENSIONS = {".py", ".ts", ".tsx", ".js", ".mjs", ".cjs", ".rs", ".toml", ".json", ".jsonl", ".yml", ".yaml",
              ".md", ".txt", ".sh", ".html", ".css", ".sql", ".svg", ".png", ".jpg", ".jpeg", ".webp", ".ico",
              ".icns", ".woff", ".woff2", ".ttf", ".h", ".c", ".cpp", ".proto", ".xml", ".kt", ".kts",
              ".java", ".gradle", ".properties", ".pro", ".bat", ".patch"}
SPECIAL_FILES = {"Cargo.lock", "uv.lock", "Dockerfile", "LICENSE", "NOTICE", "gradlew"}
EXACT_BINARY_INPUTS = {"companion/src-tauri/gen/android/gradle/wrapper/gradle-wrapper.jar"}
EXACT_TEXT_INPUTS = {"deploy/vercel-judge-relay/" + name for name in (
    ".python-version", ".vercelignore", "Dockerfile.vercel")} | {"deploy/Dockerfile.remote"}
RELAY_REQUIRED = {"deploy/vercel-judge-relay/" + name for name in (
    "pyproject.toml", "uv.lock", ".python-version", "app.py", "Dockerfile.vercel", ".vercelignore", "README.md", "verify.py", "vercel.json")}
PRIVATE_NAMES = {"credentials", "credentials.json", "token.json", "tokens.json", "service-account.json", "id_rsa", "id_ed25519",
                 "local.properties", "key.properties", "keystore.properties", "tauri.properties",
                 "tauri.settings.gradle", "tauri.build.gradle.kts"}
ANDROID_ROOT = "companion/src-tauri/gen/android"
ANDROID_REQUIRED = {f"{ANDROID_ROOT}/{name}" for name in (
    "build.gradle.kts", "settings.gradle", "gradle.properties", "gradlew", "gradlew.bat",
    "gradle/wrapper/gradle-wrapper.jar", "gradle/wrapper/gradle-wrapper.properties",
    "buildSrc/build.gradle.kts", "buildSrc/src/main/java/com/bifang/companion/kotlin/BuildTask.kt",
    "buildSrc/src/main/java/com/bifang/companion/kotlin/RustPlugin.kt", "app/build.gradle.kts",
    "app/proguard-rules.pro", "app/src/main/AndroidManifest.xml",
    "app/src/main/java/com/bifang/companion/MainActivity.kt",
    "app/src/main/java/com/bifang/companion/DeviceRuntimePlugin.kt",
    "app/src/main/java/com/bifang/companion/DeviceHardware.kt",
    "app/src/main/java/com/bifang/companion/TermuxRuntime.kt",
    "app/src/main/assets/bifang_runtime.py",
)}
REQUIRED = set(ROOT_FILES) | RELAY_REQUIRED | {
    "deploy/Dockerfile.remote",
    "src/bifang/__init__.py", "scripts/build-server-sidecar.sh", "scripts/build-server-sidecar.py", "scripts/bifang-server-entry.py",
    "scripts/build-source-archive.py", "scripts/bundle-linux.py", "scripts/check-linux-runtime.py", "scripts/check-sidecar-runtime.py",
    "scripts/collect-platform-packages.py", ".github/workflows/desktop-platforms.yml",
    "scripts/check-workbench-helper.py", "scripts/check-sidecar-health.py",
    "desktop/package.json", "desktop/package-lock.json", "desktop/index.html", "desktop/vite.config.ts",
    "desktop/dev/localWorkspaces.ts", "desktop/tsconfig.json", "desktop/tsconfig.node.json",
    "desktop/postcss.config.js", "desktop/tailwind.config.js",
    "desktop/src-tauri/Cargo.toml", "desktop/src-tauri/Cargo.lock", "desktop/src-tauri/build.rs",
    "desktop/src-tauri/tauri.conf.json", "desktop/src-tauri/capabilities/default.json",
    "desktop/src-tauri/icons/android/mipmap-anydpi-v26/ic_launcher.xml",
    "desktop/src-tauri/icons/android/values/ic_launcher_background.xml",
    "companion/package.json", "companion/package-lock.json", "companion/vite.config.ts",
    "companion/index.html", "companion/tsconfig.json", "companion/postcss.config.js",
    "companion/src-tauri/Cargo.toml", "companion/src-tauri/Cargo.lock", "companion/src-tauri/build.rs",
    "companion/src-tauri/tauri.conf.json", ".github/workflows/ci.yml",
    "companion/src/DeviceTerminal.tsx", "companion/src/main.tsx", "companion/src/style.css",
    "companion/src-tauri/src/lib.rs", "companion/src-tauri/src/device_terminal.rs",
    "companion/src-tauri/src/device_runtime.rs", "desktop/src-tauri/src/terminal_engine.rs",
}


def selected_files(root: Path) -> list[Path]:
    selected = [root / name for name in ROOT_FILES + OPTIONAL_ROOT_FILES if (root / name).exists()]
    for tree in TREES:
        directory = root / tree
        if directory.is_symlink():
            raise ValueError(f"Source tree is a symlink: {tree}")
        if not directory.exists():
            continue
        for current, directories, files in os.walk(directory, followlinks=False):
            directories[:] = sorted(name for name in directories if name not in EXCLUDED_DIRS and not name.startswith("."))
            for name in directories:
                if (Path(current) / name).is_symlink():
                    raise ValueError("Review source directory symlinks before exporting")
            for name in sorted(files):
                path = Path(current) / name
                relative = path.relative_to(root).as_posix()
                if ((name.startswith(".") and relative not in EXACT_TEXT_INPUTS) or name.lower() in PRIVATE_NAMES
                        or (path.suffix not in EXTENSIONS and name not in SPECIAL_FILES
                            and relative not in EXACT_BINARY_INPUTS | EXACT_TEXT_INPUTS)):
                    continue
                selected.append(path)
    return sorted(set(selected), key=lambda path: path.relative_to(root).as_posix())


def build_archive(root: Path, output: Path, max_file_bytes: int = 16_777_216, max_total_bytes: int = 134_217_728) -> dict:
    root = root.resolve(strict=True)
    if output.exists() or output.is_symlink():
        raise ValueError("Refusing to overwrite an existing archive")
    payload = []
    total = 0
    for source in selected_files(root):
        relative = source.relative_to(root).as_posix()
        if source.is_symlink() or not source.resolve().is_relative_to(root) or not source.is_file():
            raise ValueError(f"Source must be a regular contained file: {relative}")
        size = source.stat().st_size
        if size > max_file_bytes or total + size > max_total_bytes:
            raise ValueError("Source size limit exceeded; review large inputs separately")
        with source.open("rb") as stream:
            content = stream.read(max_file_bytes + 1)
        total += len(content)
        if len(content) > max_file_bytes or total > max_total_bytes:
            raise ValueError("Source size limit exceeded during read")
        payload.append((relative, content, 0o755 if source.stat().st_mode & 0o111 else 0o644))
    names = {name for name, _, _ in payload}
    required = REQUIRED | ANDROID_REQUIRED if (root / ANDROID_ROOT).is_dir() else REQUIRED
    if (root / "tui").is_dir():
        required = required | {"tui/Cargo.toml", "tui/Cargo.lock", "tui/src/main.rs", "tui/src/lib.rs"}
    missing = sorted(required - names)
    if missing:
        raise ValueError("Missing required build inputs: " + ", ".join(missing))
    manifest = {"version": "bifang-source-v1", "scope": "Selected working-tree source, not Git index or native build provenance",
                "files": [{"path": name, "size": len(content), "sha256": hashlib.sha256(content).hexdigest()}
                          for name, content, _ in payload]}
    payload.append(("SOURCE_MANIFEST.json", (json.dumps(manifest, sort_keys=True, indent=2) + "\n").encode(), 0o644))
    descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with (
        os.fdopen(descriptor, "wb") as destination,
        gzip.GzipFile(filename="", mode="wb", fileobj=destination, mtime=0) as compressed,
        tarfile.open(fileobj=compressed, mode="w", format=tarfile.PAX_FORMAT) as archive,
    ):
        for name, content, mode in sorted(payload):
            information = tarfile.TarInfo(name)
            information.size = len(content)
            information.mode = mode
            information.mtime = 0
            archive.addfile(information, io.BytesIO(content))
    with output.open("rb") as source:
        digest = hashlib.file_digest(source, "sha256").hexdigest()
    return {"archive_sha256": digest, "file_count": len(manifest["files"]), "source_bytes": total,
            "scope": manifest["scope"], "publication_approved": False,
            "secret_scan": "Not performed by exporter; review source and run bounded secret/media scans before publication"}


def main() -> None:
    parser = argparse.ArgumentParser(description="Export deterministic selected source without caches, private state or dependency installs")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    print(json.dumps(build_archive(arguments.root, arguments.output), indent=2))


if __name__ == "__main__":
    main()
