from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
import toml
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional

import httpx


class PackageManagerType(Enum):
    PIP = "pip"
    NPM = "npm"
    CARGO = "cargo"
    UV = "uv"
    PNPM = "pnpm"
    YARN = "yarn"
    POETRY = "poetry"
    PIPENV = "pipenv"


@dataclass
class Package:
    """A package dependency."""
    name: str
    version: str
    latest_version: str = ""
    manager: PackageManagerType = PackageManagerType.PIP
    description: str = ""
    license: str = ""
    homepage: str = ""
    repository: str = ""
    dependencies: list[str] = field(default_factory=list)
    dev_dependency: bool = False
    outdated: bool = False
    update_type: str = ""  # major, minor, patch


@dataclass
class LockfileDiff:
    """Diff between lockfiles."""
    added: list[Package] = field(default_factory=list)
    removed: list[Package] = field(default_factory=list)
    updated: list[tuple[Package, Package]] = field(default_factory=list)  # (old, new)
    unchanged: list[Package] = field(default_factory=list)


@dataclass
class Vulnerability:
    """Security vulnerability in a package."""
    id: str
    package: str
    version: str
    severity: str  # critical, high, medium, low
    title: str
    description: str
    cve: str = ""
    cwe: str = ""
    fixed_versions: list[str] = field(default_factory=list)
    references: list[str] = field(default_factory=list)


class PackageManager:
    """Base class for package managers."""
    
    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root
    
    async def list_packages(self, dev: bool = False) -> list[Package]:
        raise NotImplementedError
    
    async def get_outdated(self) -> list[Package]:
        raise NotImplementedError
    
    async def update_package(self, name: str, version: str | None = None) -> bool:
        raise NotImplementedError
    
    async def add_package(self, name: str, version: str | None = None, dev: bool = False) -> bool:
        raise NotImplementedError
    
    async def remove_package(self, name: str) -> bool:
        raise NotImplementedError
    
    async def audit(self) -> list[Vulnerability]:
        raise NotImplementedError
    
    async def get_lockfile_diff(self, other_lockfile: Path) -> LockfileDiff:
        raise NotImplementedError


class PipManager(PackageManager):
    """Python pip/uv/poetry/pipenv package manager."""
    
    def __init__(self, workspace_root: Path):
        super().__init__(workspace_root)
        self.uv_path = self._find_uv()
        self.poetry_path = self._find_poetry()
        self.pipenv_path = self._find_pipenv()
    
    def _find_uv(self) -> str | None:
        for path in ["/usr/bin/uv", "/usr/local/bin/uv", os.path.expanduser("~/.cargo/bin/uv")]:
            if os.path.exists(path):
                return path
        return None
    
    def _find_poetry(self) -> str | None:
        for path in ["/usr/bin/poetry", "/usr/local/bin/poetry", os.path.expanduser("~/.local/bin/poetry")]:
            if os.path.exists(path):
                return path
        return None
    
    def _find_pipenv(self) -> str | None:
        for path in ["/usr/bin/pipenv", "/usr/local/bin/pipenv", os.path.expanduser("~/.local/bin/pipenv")]:
            if os.path.exists(path):
                return path
        return None
    
    def _get_lockfile(self) -> Path | None:
        """Find the lockfile."""
        for name in ["uv.lock", "poetry.lock", "Pipfile.lock", "requirements.txt"]:
            path = self.workspace_root / name
            if path.exists():
                return path
        return None
    
    async def list_packages(self, dev: bool = False) -> list[Package]:
        packages = []
        
        # Try uv first
        if self.uv_path:
            try:
                result = await asyncio.to_thread(
                    subprocess.run,
                    [self.uv_path, "pip", "list", "--format=json"],
                    cwd=self.workspace_root,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                if result.returncode == 0:
                    data = json.loads(result.stdout)
                    for item in data:
                        packages.append(Package(
                            name=item["name"],
                            version=item["version"],
                            manager=PackageManagerType.UV,
                        ))
                    return packages
            except:
                pass
        
        # Try poetry
        if self.poetry_path:
            try:
                result = await asyncio.to_thread(
                    subprocess.run,
                    [self.poetry_path, "show", "--no-dev" if not dev else "", "--format=json"],
                    cwd=self.workspace_root,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                if result.returncode == 0:
                    data = json.loads(result.stdout)
                    for item in data:
                        packages.append(Package(
                            name=item["name"],
                            version=item["version"],
                            manager=PackageManagerType.POETRY,
                            description=item.get("description", ""),
                        ))
                    return packages
            except:
                pass
        
        # Fallback to pip
        try:
            result = await asyncio.to_thread(
                subprocess.run,
                ["pip", "list", "--format=json"],
                cwd=self.workspace_root,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                data = json.loads(result.stdout)
                for item in data:
                    packages.append(Package(
                        name=item["name"],
                        version=item["version"],
                        manager=PackageManagerType.PIP,
                    ))
        except:
            pass
        
        return packages
    
    async def get_outdated(self) -> list[Package]:
        outdated = []
        
        if self.uv_path:
            try:
                result = await asyncio.to_thread(
                    subprocess.run,
                    [self.uv_path, "pip", "list", "--outdated", "--format=json"],
                    cwd=self.workspace_root,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                if result.returncode == 0:
                    data = json.loads(result.stdout)
                    for item in data:
                        outdated.append(Package(
                            name=item["name"],
                            version=item["version"],
                            latest_version=item.get("latest_version", ""),
                            manager=PackageManagerType.UV,
                            outdated=True,
                            update_type=self._classify_update(item["version"], item.get("latest_version", "")),
                        ))
                    return outdated
            except:
                pass
        
        try:
            result = await asyncio.to_thread(
                subprocess.run,
                ["pip", "list", "--outdated", "--format=json"],
                cwd=self.workspace_root,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                data = json.loads(result.stdout)
                for item in data:
                    outdated.append(Package(
                        name=item["name"],
                        version=item["version"],
                        latest_version=item.get("latest_version", ""),
                        manager=PackageManagerType.PIP,
                        outdated=True,
                        update_type=self._classify_update(item["version"], item.get("latest_version", "")),
                    ))
        except:
            pass
        
        return outdated
    
    def _classify_update(self, current: str, latest: str) -> str:
        """Classify update as major, minor, or patch."""
        try:
            cur = [int(x) for x in current.split(".")]
            lat = [int(x) for x in latest.split(".")]
            
            # Pad to same length
            while len(cur) < 3:
                cur.append(0)
            while len(lat) < 3:
                lat.append(0)
            
            if lat[0] > cur[0]:
                return "major"
            elif lat[1] > cur[1]:
                return "minor"
            else:
                return "patch"
        except:
            return "unknown"
    
    async def update_package(self, name: str, version: str | None = None) -> bool:
        if self.uv_path:
            cmd = [self.uv_path, "pip", "install", "--upgrade"]
            if version:
                cmd.append(f"{name}=={version}")
            else:
                cmd.append(name)
        else:
            cmd = ["pip", "install", "--upgrade"]
            if version:
                cmd.append(f"{name}=={version}")
            else:
                cmd.append(name)
        
        try:
            result = await asyncio.to_thread(
                subprocess.run,
                cmd,
                cwd=self.workspace_root,
                capture_output=True,
                text=True,
                timeout=120,
            )
            return result.returncode == 0
        except:
            return False
    
    async def add_package(self, name: str, version: str | None = None, dev: bool = False) -> bool:
        if self.uv_path:
            cmd = [self.uv_path, "add"]
            if dev:
                cmd.append("--dev")
            if version:
                cmd.append(f"{name}=={version}")
            else:
                cmd.append(name)
        elif self.poetry_path:
            cmd = [self.poetry_path, "add"]
            if dev:
                cmd.append("--group=dev")
            if version:
                cmd.append(f"{name}=={version}")
            else:
                cmd.append(name)
        else:
            cmd = ["pip", "install"]
            if version:
                cmd.append(f"{name}=={version}")
            else:
                cmd.append(name)
        
        try:
            result = await asyncio.to_thread(
                subprocess.run,
                cmd,
                cwd=self.workspace_root,
                capture_output=True,
                text=True,
                timeout=120,
            )
            return result.returncode == 0
        except:
            return False
    
    async def remove_package(self, name: str) -> bool:
        if self.uv_path:
            cmd = [self.uv_path, "remove", name]
        elif self.poetry_path:
            cmd = [self.poetry_path, "remove", name]
        else:
            cmd = ["pip", "uninstall", "-y", name]
        
        try:
            result = await asyncio.to_thread(
                subprocess.run,
                cmd,
                cwd=self.workspace_root,
                capture_output=True,
                text=True,
                timeout=60,
            )
            return result.returncode == 0
        except:
            return False
    
    async def audit(self) -> list[Vulnerability]:
        vulnerabilities = []
        
        # Try pip-audit
        try:
            result = await asyncio.to_thread(
                subprocess.run,
                ["pip-audit", "--format=json"],
                cwd=self.workspace_root,
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode in (0, 1):  # 1 means vulnerabilities found
                data = json.loads(result.stdout)
                for item in data.get("vulnerabilities", []):
                    vulnerabilities.append(Vulnerability(
                        id=item.get("id", ""),
                        package=item.get("package", ""),
                        version=item.get("installed_version", ""),
                        severity=item.get("severity", "medium").lower(),
                        title=item.get("title", ""),
                        description=item.get("description", ""),
                        cve=item.get("id", "") if item.get("id", "").startswith("CVE-") else "",
                        fixed_versions=item.get("fixed_versions", []),
                    ))
        except:
            pass
        
        return vulnerabilities
    
    async def get_lockfile_diff(self, other_lockfile: Path) -> LockfileDiff:
        # Parse both lockfiles and compare
        current = self._parse_lockfile(self._get_lockfile())
        other = self._parse_lockfile(other_lockfile)
        
        # Simple comparison
        current_names = {p.name: p for p in current}
        other_names = {p.name: p for p in other}
        
        added = [p for n, p in other_names.items() if n not in current_names]
        removed = [p for n, p in current_names.items() if n not in other_names]
        
        updated = []
        unchanged = []
        for name, curr_pkg in current_names.items():
            if name in other_names:
                other_pkg = other_names[name]
                if curr_pkg.version != other_pkg.version:
                    updated.append((curr_pkg, other_pkg))
                else:
                    unchanged.append(curr_pkg)
        
        return LockfileDiff(
            added=added,
            removed=removed,
            updated=updated,
            unchanged=unchanged,
        )
    
    def _parse_lockfile(self, path: Path | None) -> list[Package]:
        if not path or not path.exists():
            return []
        
        packages = []
        
        if path.name == "uv.lock":
            with open(path) as f:
                data = toml.load(f)
            for pkg in data.get("package", []):
                packages.append(Package(
                    name=pkg["name"],
                    version=pkg["version"],
                    manager=PackageManagerType.UV,
                ))
        
        elif path.name == "poetry.lock":
            with open(path) as f:
                data = toml.load(f)
            for pkg in data.get("package", []):
                packages.append(Package(
                    name=pkg["name"],
                    version=pkg["version"],
                    manager=PackageManagerType.POETRY,
                    description=pkg.get("description", ""),
                ))
        
        elif path.name == "Pipfile.lock":
            with open(path) as f:
                data = json.load(f)
            for name, info in data.get("default", {}).items():
                packages.append(Package(
                    name=name,
                    version=info.get("version", "").lstrip("=="),
                    manager=PackageManagerType.PIPENV,
                ))
        
        elif path.name == "requirements.txt":
            with open(path) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        match = re.match(r"^([^=<>!]+)(?:[=<>!]=?)(.+)?", line)
                        if match:
                            packages.append(Package(
                                name=match.group(1).strip(),
                                version=match.group(2).strip() if match.group(2) else "",
                                manager=PackageManagerType.PIP,
                            ))
        
        return packages


class NpmManager(PackageManager):
    """Node.js npm/pnpm/yarn package manager."""
    
    def __init__(self, workspace_root: Path):
        super().__init__(workspace_root)
        self.npm_path = self._find_npm()
        self.pnpm_path = self._find_pnpm()
        self.yarn_path = self._find_yarn()
    
    def _find_npm(self) -> str | None:
        for path in ["/usr/bin/npm", "/usr/local/bin/npm"]:
            if os.path.exists(path):
                return path
        return None
    
    def _find_pnpm(self) -> str | None:
        for path in ["/usr/bin/pnpm", "/usr/local/bin/pnpm", os.path.expanduser("~/.local/bin/pnpm")]:
            if os.path.exists(path):
                return path
        return None
    
    def _find_yarn(self) -> str | None:
        for path in ["/usr/bin/yarn", "/usr/local/bin/yarn", os.path.expanduser("~/.local/bin/yarn")]:
            if os.path.exists(path):
                return path
        return None
    
    def _get_package_json(self) -> Path | None:
        path = self.workspace_root / "package.json"
        return path if path.exists() else None
    
    def _get_lockfile(self) -> Path | None:
        for name in ["pnpm-lock.yaml", "yarn.lock", "package-lock.json"]:
            path = self.workspace_root / name
            if path.exists():
                return path
        return None
    
    async def list_packages(self, dev: bool = False) -> list[Package]:
        packages = []
        
        pkg_json = self._get_package_json()
        if not pkg_json:
            return packages
        
        with open(pkg_json) as f:
            data = json.load(f)
        
        deps = data.get("dependencies", {})
        if dev:
            deps.update(data.get("devDependencies", {}))
        
        # Get installed versions from node_modules
        installed = await self._get_installed_versions()
        
        for name, version in deps.items():
            packages.append(Package(
                name=name,
                version=installed.get(name, version),
                manager=PackageManagerType.NPM,
            ))
        
        return packages
    
    async def _get_installed_versions(self) -> dict[str, str]:
        versions = {}
        node_modules = self.workspace_root / "node_modules"
        if node_modules.exists():
            for pkg_dir in node_modules.iterdir():
                if pkg_dir.is_dir() and not pkg_dir.name.startswith("."):
                    pkg_json = pkg_dir / "package.json"
                    if pkg_json.exists():
                        try:
                            with open(pkg_json) as f:
                                data = json.load(f)
                            versions[data.get("name", pkg_dir.name)] = data.get("version", "")
                        except:
                            pass
        return versions
    
    async def get_outdated(self) -> list[Package]:
        outdated = []
        
        if self.npm_path:
            try:
                result = await asyncio.to_thread(
                    subprocess.run,
                    [self.npm_path, "outdated", "--json", "--long"],
                    cwd=self.workspace_root,
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                if result.returncode in (0, 1):
                    data = json.loads(result.stdout)
                    for item in data:
                        outdated.append(Package(
                            name=item["name"],
                            version=item["current"],
                            latest_version=item["latest"],
                            manager=PackageManagerType.NPM,
                            outdated=True,
                            update_type=self._classify_update(item["current"], item["latest"]),
                        ))
            except:
                pass
        
        return outdated
    
    def _classify_update(self, current: str, latest: str) -> str:
        try:
            cur = [int(x) for x in current.split(".")]
            lat = [int(x) for x in latest.split(".")]
            while len(cur) < 3:
                cur.append(0)
            while len(lat) < 3:
                lat.append(0)
            
            if lat[0] > cur[0]:
                return "major"
            elif lat[1] > cur[1]:
                return "minor"
            else:
                return "patch"
        except:
            return "unknown"
    
    async def update_package(self, name: str, version: str | None = None) -> bool:
        cmd = [self.npm_path or "npm", "update"]
        if version:
            cmd.append(f"{name}@{version}")
        else:
            cmd.append(name)
        
        try:
            result = await asyncio.to_thread(
                subprocess.run,
                cmd,
                cwd=self.workspace_root,
                capture_output=True,
                text=True,
                timeout=120,
            )
            return result.returncode == 0
        except:
            return False
    
    async def add_package(self, name: str, version: str | None = None, dev: bool = False) -> bool:
        if self.pnpm_path:
            cmd = [self.pnpm_path, "add"]
            if dev:
                cmd.append("-D")
            if version:
                cmd.append(f"{name}@{version}")
            else:
                cmd.append(name)
        elif self.yarn_path:
            cmd = [self.yarn_path, "add"]
            if dev:
                cmd.append("-D")
            if version:
                cmd.append(f"{name}@{version}")
            else:
                cmd.append(name)
        else:
            cmd = [self.npm_path or "npm", "install"]
            if dev:
                cmd.append("--save-dev")
            if version:
                cmd.append(f"{name}@{version}")
            else:
                cmd.append(name)
        
        try:
            result = await asyncio.to_thread(
                subprocess.run,
                cmd,
                cwd=self.workspace_root,
                capture_output=True,
                text=True,
                timeout=120,
            )
            return result.returncode == 0
        except:
            return False
    
    async def remove_package(self, name: str) -> bool:
        if self.pnpm_path:
            cmd = [self.pnpm_path, "remove", name]
        elif self.yarn_path:
            cmd = [self.yarn_path, "remove", name]
        else:
            cmd = [self.npm_path or "npm", "uninstall", name]
        
        try:
            result = await asyncio.to_thread(
                subprocess.run,
                cmd,
                cwd=self.workspace_root,
                capture_output=True,
                text=True,
                timeout=60,
            )
            return result.returncode == 0
        except:
            return False
    
    async def audit(self) -> list[Vulnerability]:
        vulnerabilities = []
        
        try:
            result = await asyncio.to_thread(
                subprocess.run,
                ["npm", "audit", "--json"],
                cwd=self.workspace_root,
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode in (0, 1):
                data = json.loads(result.stdout)
                for vuln in data.get("vulnerabilities", {}).values():
                    vulnerabilities.append(Vulnerability(
                        id=vuln.get("id", ""),
                        package=vuln.get("name", ""),
                        version=vuln.get("version", ""),
                        severity=vuln.get("severity", "medium").lower(),
                        title=vuln.get("title", ""),
                        description=vuln.get("description", ""),
                        cve=vuln.get("cve", ""),
                        fixed_versions=vuln.get("fixed_versions", []),
                    ))
        except:
            pass
        
        return vulnerabilities
    
    async def get_lockfile_diff(self, other_lockfile: Path) -> LockfileDiff:
        # Parse both lockfiles
        current = self._parse_lockfile(self._get_lockfile())
        other = self._parse_lockfile(other_lockfile)
        
        current_names = {p.name: p for p in current}
        other_names = {p.name: p for p in other}
        
        added = [p for n, p in other_names.items() if n not in current_names]
        removed = [p for n, p in current_names.items() if n not in other_names]
        
        updated = []
        unchanged = []
        for name, curr_pkg in current_names.items():
            if name in other_names:
                other_pkg = other_names[name]
                if curr_pkg.version != other_pkg.version:
                    updated.append((curr_pkg, other_pkg))
                else:
                    unchanged.append(curr_pkg)
        
        return LockfileDiff(added=added, removed=removed, updated=updated, unchanged=unchanged)
    
    def _parse_lockfile(self, path: Path | None) -> list[Package]:
        if not path or not path.exists():
            return []
        
        packages = []
        
        if path.name == "pnpm-lock.yaml":
            with open(path) as f:
                data = yaml.safe_load(f)
            for pkg in data.get("packages", {}).values():
                packages.append(Package(
                    name=pkg.get("name", ""),
                    version=pkg.get("version", ""),
                    manager=PackageManagerType.PNPM,
                ))
        
        elif path.name == "package-lock.json":
            with open(path) as f:
                data = json.load(f)
            for name, info in data.get("dependencies", {}).items():
                packages.append(Package(
                    name=name,
                    version=info.get("version", ""),
                    manager=PackageManagerType.NPM,
                ))
        
        return packages


class CargoManager(PackageManager):
    """Rust Cargo package manager."""
    
    def __init__(self, workspace_root: Path):
        super().__init__(workspace_root)
        self.cargo_path = self._find_cargo()
    
    def _find_cargo(self) -> str | None:
        for path in ["/usr/bin/cargo", "/usr/local/bin/cargo", os.path.expanduser("~/.cargo/bin/cargo")]:
            if os.path.exists(path):
                return path
        return None
    
    def _get_cargo_toml(self) -> Path | None:
        path = self.workspace_root / "Cargo.toml"
        return path if path.exists() else None
    
    def _get_lockfile(self) -> Path | None:
        path = self.workspace_root / "Cargo.lock"
        return path if path.exists() else None
    
    async def list_packages(self, dev: bool = False) -> list[Package]:
        packages = []
        
        if self.cargo_path:
            try:
                result = await asyncio.to_thread(
                    subprocess.run,
                    [self.cargo_path, "metadata", "--format-version=1", "--no-deps"],
                    cwd=self.workspace_root,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                if result.returncode == 0:
                    data = json.loads(result.stdout)
                    for pkg in data.get("packages", []):
                        packages.append(Package(
                            name=pkg["name"],
                            version=pkg["version"],
                            manager=PackageManagerType.CARGO,
                            description=pkg.get("description", ""),
                            license=pkg.get("license", ""),
                            repository=pkg.get("repository", ""),
                        ))
            except:
                pass
        
        return packages
    
    async def get_outdated(self) -> list[Package]:
        outdated = []
        
        try:
            result = await asyncio.to_thread(
                subprocess.run,
                [self.cargo_path, "outdated", "--format", "json"],
                cwd=self.workspace_root,
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode in (0, 1):
                data = json.loads(result.stdout)
                for item in data:
                    outdated.append(Package(
                        name=item["name"],
                        version=item["version"],
                        latest_version=item.get("latest_version", ""),
                        manager=PackageManagerType.CARGO,
                        outdated=True,
                    ))
        except:
            pass
        
        return outdated
    
    async def update_package(self, name: str, version: str | None = None) -> bool:
        cmd = [self.cargo_path, "update"]
        if version:
            cmd.extend(["-p", name, "--precise", version])
        else:
            cmd.extend(["-p", name])
        
        try:
            result = await asyncio.to_thread(
                subprocess.run,
                cmd,
                cwd=self.workspace_root,
                capture_output=True,
                text=True,
                timeout=120,
            )
            return result.returncode == 0
        except:
            return False
    
    async def add_package(self, name: str, version: str | None = None, dev: bool = False) -> bool:
        cmd = [self.cargo_path, "add"]
        if dev:
            cmd.append("--dev")
        if version:
            cmd.append(f"{name}@{version}")
        else:
            cmd.append(name)
        
        try:
            result = await asyncio.to_thread(
                subprocess.run,
                cmd,
                cwd=self.workspace_root,
                capture_output=True,
                text=True,
                timeout=120,
            )
            return result.returncode == 0
        except:
            return False
    
    async def remove_package(self, name: str) -> bool:
        cmd = [self.cargo_path, "remove", name]
        
        try:
            result = await asyncio.to_thread(
                subprocess.run,
                cmd,
                cwd=self.workspace_root,
                capture_output=True,
                text=True,
                timeout=60,
            )
            return result.returncode == 0
        except:
            return False
    
    async def audit(self) -> list[Vulnerability]:
        vulnerabilities = []
        
        try:
            result = await asyncio.to_thread(
                subprocess.run,
                [self.cargo_path, "audit", "--json"],
                cwd=self.workspace_root,
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode in (0, 1):
                data = json.loads(result.stdout)
                for vuln in data.get("vulnerabilities", {}).get("list", []):
                    vulnerabilities.append(Vulnerability(
                        id=vuln.get("id", ""),
                        package=vuln.get("package", {}).get("name", ""),
                        version=vuln.get("package", {}).get("version", ""),
                        severity=vuln.get("advisory", {}).get("severity", "medium").lower(),
                        title=vuln.get("advisory", {}).get("title", ""),
                        description=vuln.get("advisory", {}).get("description", ""),
                        cve=vuln.get("advisory", {}).get("id", ""),
                    ))
        except:
            pass
        
        return vulnerabilities
    
    async def get_lockfile_diff(self, other_lockfile: Path) -> LockfileDiff:
        current = self._parse_lockfile(self._get_lockfile())
        other = self._parse_lockfile(other_lockfile)
        
        current_names = {p.name: p for p in current}
        other_names = {p.name: p for p in other}
        
        added = [p for n, p in other_names.items() if n not in current_names]
        removed = [p for n, p in current_names.items() if n not in other_names]
        
        updated = []
        unchanged = []
        for name, curr_pkg in current_names.items():
            if name in other_names:
                other_pkg = other_names[name]
                if curr_pkg.version != other_pkg.version:
                    updated.append((curr_pkg, other_pkg))
                else:
                    unchanged.append(curr_pkg)
        
        return LockfileDiff(added=added, removed=removed, updated=updated, unchanged=unchanged)
    
    def _parse_lockfile(self, path: Path | None) -> list[Package]:
        if not path or not path.exists():
            return []
        
        packages = []
        
        if path.name == "Cargo.lock":
            with open(path) as f:
                data = toml.load(f)
            for pkg in data.get("package", []):
                packages.append(Package(
                    name=pkg["name"],
                    version=pkg["version"],
                    manager=PackageManagerType.CARGO,
                ))
        
        return packages


class UnifiedPackageManager:
    """Unified interface for all package managers."""
    
    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root
        self.managers: dict[PackageManagerType, PackageManager] = {
            PackageManagerType.PIP: PipManager(workspace_root),
            PackageManagerType.UV: PipManager(workspace_root),
            PackageManagerType.POETRY: PipManager(workspace_root),
            PackageManagerType.PIPENV: PipManager(workspace_root),
            PackageManagerType.NPM: NpmManager(workspace_root),
            PackageManagerType.PNPM: NpmManager(workspace_root),
            PackageManagerType.YARN: NpmManager(workspace_root),
            PackageManagerType.CARGO: CargoManager(workspace_root),
        }
    
    def detect_managers(self) -> list[PackageManagerType]:
        """Detect which package managers are present in the workspace."""
        detected = []
        
        if (self.workspace_root / "pyproject.toml").exists() or (self.workspace_root / "requirements.txt").exists():
            detected.extend([PackageManagerType.PIP, PackageManagerType.UV, PackageManagerType.POETRY])
        
        if (self.workspace_root / "package.json").exists():
            detected.extend([PackageManagerType.NPM, PackageManagerType.PNPM, PackageManagerType.YARN])
        
        if (self.workspace_root / "Cargo.toml").exists():
            detected.append(PackageManagerType.CARGO)
        
        return detected
    
    def get_manager(self, manager_type: PackageManagerType) -> PackageManager | None:
        return self.managers.get(manager_type)
    
    async def list_all_packages(self, dev: bool = False) -> dict[PackageManagerType, list[Package]]:
        """List packages from all detected managers."""
        detected = self.detect_managers()
        results = {}
        
        for mgr_type in detected:
            mgr = self.get_manager(mgr_type)
            if mgr:
                try:
                    packages = await mgr.list_packages(dev)
                    if packages:
                        results[mgr_type] = packages
                except:
                    pass
        
        return results
    
    async def get_all_outdated(self) -> dict[PackageManagerType, list[Package]]:
        detected = self.detect_managers()
        results = {}
        
        for mgr_type in detected:
            mgr = self.get_manager(mgr_type)
            if mgr:
                try:
                    outdated = await mgr.get_outdated()
                    if outdated:
                        results[mgr_type] = outdated
                except:
                    pass
        
        return results
    
    async def audit_all(self) -> dict[PackageManagerType, list[Vulnerability]]:
        detected = self.detect_managers()
        results = {}
        
        for mgr_type in detected:
            mgr = self.get_manager(mgr_type)
            if mgr:
                try:
                    vulns = await mgr.audit()
                    if vulns:
                        results[mgr_type] = vulns
                except:
                    pass
        
        return results
    
    async def get_all_lockfile_diffs(self, other_workspace: Path) -> dict[PackageManagerType, LockfileDiff]:
        detected = self.detect_managers()
        results = {}
        
        for mgr_type in detected:
            mgr = self.get_manager(mgr_type)
            if mgr:
                try:
                    diff = await mgr.get_lockfile_diff(other_workspace)
                    if diff.added or diff.removed or diff.updated:
                        results[mgr_type] = diff
                except:
                    pass
        
        return results