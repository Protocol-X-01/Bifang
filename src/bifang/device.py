from __future__ import annotations

import asyncio
import json
import os
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional

import httpx


class DevicePlatform(Enum):
    IOS = "ios"
    ANDROID = "android"
    LINUX = "linux"
    MACOS = "macos"
    WINDOWS = "windows"


class DeviceStatus(Enum):
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    UNAUTHORIZED = "unauthorized"
    BOOTING = "booting"
    RECOVERY = "recovery"


@dataclass
class DeviceInfo:
    """Information about a connected device."""
    id: str
    name: str
    platform: DevicePlatform
    status: DeviceStatus
    model: str = ""
    os_version: str = ""
    serial: str = ""
    ip_address: str = ""
    port: int = 0
    is_emulator: bool = False
    capabilities: list[str] = field(default_factory=list)
    last_seen: datetime = field(default_factory=datetime.now)


@dataclass
class AppInfo:
    """Information about an installed app."""
    package_name: str
    name: str
    version: str
    version_code: int
    platform: DevicePlatform
    install_path: str = ""
    data_path: str = ""
    permissions: list[str] = field(default_factory=list)


@dataclass
class TestResult:
    """Result of a device test run."""
    test_id: str
    device_id: str
    app_package: str
    test_type: str  # unit, ui, integration, performance
    status: str  # passed, failed, error, skipped
    duration: float
    output: str = ""
    screenshots: list[str] = field(default_factory=list)
    logs: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)


class DeviceManager:
    """Manages connected devices for testing and deployment."""
    
    def __init__(self):
        self.devices: dict[str, DeviceInfo] = {}
        self.apps: dict[str, AppInfo] = {}
        self.test_results: list[TestResult] = []
        self.adb_path = self._find_adb()
        self.xcrun_path = self._find_xcrun()
        self.event_callbacks: list[callable] = []
    
    def _find_adb(self) -> str | None:
        """Find adb executable."""
        for path in ["/usr/bin/adb", "/usr/local/bin/adb", os.path.expanduser("~/Library/Android/sdk/platform-tools/adb")]:
            if os.path.exists(path):
                return path
        return None
    
    def _find_xcrun(self) -> str | None:
        """Find xcrun executable (for iOS)."""
        for path in ["/usr/bin/xcrun", "/Applications/Xcode.app/Contents/Developer/usr/bin/xcrun"]:
            if os.path.exists(path):
                return path
        return None
    
    async def discover_devices(self) -> list[DeviceInfo]:
        """Discover all connected devices."""
        devices = []
        
        # Discover Android devices via ADB
        if self.adb_path:
            android_devices = await self._discover_android()
            devices.extend(android_devices)
        
        # Discover iOS devices via xcrun
        if self.xcrun_path:
            ios_devices = await self._discover_ios()
            devices.extend(ios_devices)
        
        # Update device registry
        for device in devices:
            self.devices[device.id] = device
            self._emit_event("device_connected", {"device": device.__dict__})
        
        return devices
    
    async def _discover_android(self) -> list[DeviceInfo]:
        """Discover Android devices via ADB."""
        devices = []
        try:
            result = await asyncio.to_thread(
                subprocess.run,
                [self.adb_path, "devices", "-l"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            
            for line in result.stdout.strip().split("\n")[1:]:  # Skip header
                if not line.strip():
                    continue
                parts = line.split()
                if len(parts) < 2:
                    continue
                
                device_id = parts[0]
                status_str = parts[1]
                
                # Parse status
                status = DeviceStatus.DISCONNECTED
                if status_str == "device":
                    status = DeviceStatus.CONNECTED
                elif status_str == "unauthorized":
                    status = DeviceStatus.UNAUTHORIZED
                elif status_str == "offline":
                    status = DeviceStatus.DISCONNECTED
                
                # Get detailed info
                model = ""
                os_version = ""
                for part in parts[2:]:
                    if part.startswith("model:"):
                        model = part[6:]
                    elif part.startswith("device:") and not model:
                        model = part[7:]
                
                # Get OS version
                try:
                    os_result = await asyncio.to_thread(
                        subprocess.run,
                        [self.adb_path, "-s", device_id, "shell", "getprop", "ro.build.version.release"],
                        capture_output=True,
                        text=True,
                        timeout=5,
                    )
                    os_version = os_result.stdout.strip()
                except:
                    pass
                
                device = DeviceInfo(
                    id=device_id,
                    name=model or device_id,
                    platform=DevicePlatform.ANDROID,
                    status=status,
                    model=model,
                    os_version=os_version,
                    serial=device_id,
                    is_emulator="emulator" in device_id,
                    capabilities=["adb", "shell", "install", "uninstall", "logcat", "screencap", "screenrecord"],
                )
                devices.append(device)
                
        except Exception as e:
            print(f"Android discovery error: {e}")
        
        return devices
    
    async def _discover_ios(self) -> list[DeviceInfo]:
        """Discover iOS devices via xcrun."""
        devices = []
        try:
            # List devices
            result = await asyncio.to_thread(
                subprocess.run,
                [self.xcrun_path, "devicectl", "list", "devices", "--json"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            
            data = json.loads(result.stdout)
            for device_data in data.get("devices", []):
                device_id = device_data.get("udid", "")
                if not device_id:
                    continue
                
                device = DeviceInfo(
                    id=device_id,
                    name=device_data.get("name", "iOS Device"),
                    platform=DevicePlatform.IOS,
                    status=DeviceStatus.CONNECTED if device_data.get("state") == "Booted" else DeviceStatus.DISCONNECTED,
                    model=device_data.get("model", ""),
                    os_version=device_data.get("os_version", ""),
                    serial=device_id,
                    is_emulator=device_data.get("is_simulator", False),
                    capabilities=["xcrun", "install", "uninstall", "log", "screenshot", "video"],
                )
                devices.append(device)
                
        except Exception as e:
            print(f"iOS discovery error: {e}")
        
        return devices
    
    async def install_app(self, device_id: str, app_path: str) -> bool:
        """Install an app on a device."""
        device = self.devices.get(device_id)
        if not device:
            return False
        
        try:
            if device.platform == DevicePlatform.ANDROID:
                result = await asyncio.to_thread(
                    subprocess.run,
                    [self.adb_path, "-s", device_id, "install", "-r", app_path],
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                return result.returncode == 0
            
            elif device.platform == DevicePlatform.IOS:
                result = await asyncio.to_thread(
                    subprocess.run,
                    [self.xcrun_path, "devicectl", "device", "install", "app", "--device", device_id, app_path],
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                return result.returncode == 0
                
        except Exception as e:
            print(f"Install error: {e}")
        
        return False
    
    async def uninstall_app(self, device_id: str, package_name: str) -> bool:
        """Uninstall an app from a device."""
        device = self.devices.get(device_id)
        if not device:
            return False
        
        try:
            if device.platform == DevicePlatform.ANDROID:
                result = await asyncio.to_thread(
                    subprocess.run,
                    [self.adb_path, "-s", device_id, "uninstall", package_name],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                return result.returncode == 0
            
            elif device.platform == DevicePlatform.IOS:
                result = await asyncio.to_thread(
                    subprocess.run,
                    [self.xcrun_path, "devicectl", "device", "uninstall", "app", "--device", device_id, package_name],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                return result.returncode == 0
                
        except Exception as e:
            print(f"Uninstall error: {e}")
        
        return False
    
    async def run_tests(
        self,
        device_id: str,
        app_package: str,
        test_type: str = "ui",
        test_class: str | None = None,
        test_method: str | None = None,
        extra_args: list[str] | None = None,
    ) -> TestResult:
        """Run tests on a device."""
        device = self.devices.get(device_id)
        if not device:
            raise ValueError(f"Device {device_id} not found")
        
        test_id = f"test-{uuid.uuid4().hex[:8]}"
        start_time = datetime.now()
        
        try:
            if device.platform == DevicePlatform.ANDROID:
                cmd = [self.adb_path, "-s", device_id, "shell", "am", "instrument", "-w"]
                
                if test_type == "ui":
                    cmd.extend(["-r", "-e", "class", test_class or f"{app_package}.test.UiTests"])
                elif test_type == "unit":
                    cmd.extend(["-r", "-e", "class", test_class or f"{app_package}.test.UnitTests"])
                
                if test_method:
                    cmd.extend(["-e", "method", test_method])
                
                cmd.append(f"{app_package}.test/androidx.test.runner.AndroidJUnitRunner")
                
                result = await asyncio.to_thread(
                    subprocess.run,
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=300,
                )
                
                status = "passed" if result.returncode == 0 else "failed"
                output = result.stdout + result.stderr
            
            elif device.platform == DevicePlatform.IOS:
                # Use xcodebuild test
                cmd = [
                    self.xcrun_path, "xcodebuild", "test",
                    "-destination", f"id={device_id}",
                    "-scheme", app_package,
                ]
                
                if test_class:
                    cmd.extend(["-only-testing", test_class])
                if test_method:
                    cmd.extend(["-only-testing", f"{test_class}/{test_method}"])
                
                result = await asyncio.to_thread(
                    subprocess.run,
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=300,
                )
                
                status = "passed" if result.returncode == 0 else "failed"
                output = result.stdout + result.stderr
            
            duration = (datetime.now() - start_time).total_seconds()
            
            test_result = TestResult(
                test_id=test_id,
                device_id=device_id,
                app_package=app_package,
                test_type=test_type,
                status=status,
                duration=duration,
                output=output,
            )
            
            self.test_results.append(test_result)
            self._emit_event("test_completed", {"result": test_result.__dict__})
            
            return test_result
            
        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            test_result = TestResult(
                test_id=test_id,
                device_id=device_id,
                app_package=app_package,
                test_type=test_type,
                status="error",
                duration=duration,
                output=str(e),
            )
            self.test_results.append(test_result)
            return test_result
    
    async def take_screenshot(self, device_id: str, output_path: str) -> bool:
        """Take a screenshot on a device."""
        device = self.devices.get(device_id)
        if not device:
            return False
        
        try:
            if device.platform == DevicePlatform.ANDROID:
                # Take screenshot on device
                result = await asyncio.to_thread(
                    subprocess.run,
                    [self.adb_path, "-s", device_id, "shell", "screencap", "-p", "/sdcard/screenshot.png"],
                    capture_output=True,
                    timeout=10,
                )
                if result.returncode != 0:
                    return False
                
                # Pull screenshot
                result = await asyncio.to_thread(
                    subprocess.run,
                    [self.adb_path, "-s", device_id, "pull", "/sdcard/screenshot.png", output_path],
                    capture_output=True,
                    timeout=10,
                )
                return result.returncode == 0
            
            elif device.platform == DevicePlatform.IOS:
                result = await asyncio.to_thread(
                    subprocess.run,
                    [self.xcrun_path, "devicectl", "device", "screenshot", "--device", device_id, "--output", output_path],
                    capture_output=True,
                    timeout=10,
                )
                return result.returncode == 0
                
        except Exception as e:
            print(f"Screenshot error: {e}")
        
        return False
    
    async def record_screen(self, device_id: str, output_path: str, duration: int = 30) -> bool:
        """Record screen on a device."""
        device = self.devices.get(device_id)
        if not device:
            return False
        
        try:
            if device.platform == DevicePlatform.ANDROID:
                # screenrecord max 3 minutes
                duration = min(duration, 180)
                result = await asyncio.to_thread(
                    subprocess.run,
                    [self.adb_path, "-s", device_id, "shell", "screenrecord", "--time-limit", str(duration), "/sdcard/recording.mp4"],
                    capture_output=True,
                    timeout=duration + 10,
                )
                if result.returncode != 0:
                    return False
                
                result = await asyncio.to_thread(
                    subprocess.run,
                    [self.adb_path, "-s", device_id, "pull", "/sdcard/recording.mp4", output_path],
                    capture_output=True,
                    timeout=10,
                )
                return result.returncode == 0
            
            elif device.platform == DevicePlatform.IOS:
                result = await asyncio.to_thread(
                    subprocess.run,
                    [self.xcrun_path, "devicectl", "device", "record", "video", "--device", device_id, "--duration", str(duration), "--output", output_path],
                    capture_output=True,
                    timeout=duration + 10,
                )
                return result.returncode == 0
                
        except Exception as e:
            print(f"Screen recording error: {e}")
        
        return False
    
    async def get_logs(self, device_id: str, lines: int = 100) -> list[str]:
        """Get device logs."""
        device = self.devices.get(device_id)
        if not device:
            return []
        
        try:
            if device.platform == DevicePlatform.ANDROID:
                result = await asyncio.to_thread(
                    subprocess.run,
                    [self.adb_path, "-s", device_id, "logcat", "-d", "-t", str(lines)],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                return result.stdout.strip().split("\n")
            
            elif device.platform == DevicePlatform.IOS:
                result = await asyncio.to_thread(
                    subprocess.run,
                    [self.xcrun_path, "devicectl", "device", "log", "--device", device_id, "--last", str(lines)],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                return result.stdout.strip().split("\n")
                
        except Exception as e:
            print(f"Log retrieval error: {e}")
        
        return []
    
    async def push_file(self, device_id: str, local_path: str, remote_path: str) -> bool:
        """Push a file to device."""
        device = self.devices.get(device_id)
        if not device:
            return False
        
        try:
            if device.platform == DevicePlatform.ANDROID:
                result = await asyncio.to_thread(
                    subprocess.run,
                    [self.adb_path, "-s", device_id, "push", local_path, remote_path],
                    capture_output=True,
                    timeout=30,
                )
                return result.returncode == 0
            
            elif device.platform == DevicePlatform.IOS:
                # iOS file transfer is more complex, typically via app container
                return False
                
        except Exception as e:
            print(f"Push file error: {e}")
        
        return False
    
    async def pull_file(self, device_id: str, remote_path: str, local_path: str) -> bool:
        """Pull a file from device."""
        device = self.devices.get(device_id)
        if not device:
            return False
        
        try:
            if device.platform == DevicePlatform.ANDROID:
                result = await asyncio.to_thread(
                    subprocess.run,
                    [self.adb_path, "-s", device_id, "pull", remote_path, local_path],
                    capture_output=True,
                    timeout=30,
                )
                return result.returncode == 0
                
        except Exception as e:
            print(f"Pull file error: {e}")
        
        return False
    
    async def execute_shell(self, device_id: str, command: str) -> tuple[int, str, str]:
        """Execute shell command on device."""
        device = self.devices.get(device_id)
        if not device:
            return -1, "", "Device not found"
        
        try:
            if device.platform == DevicePlatform.ANDROID:
                result = await asyncio.to_thread(
                    subprocess.run,
                    [self.adb_path, "-s", device_id, "shell", command],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                return result.returncode, result.stdout, result.stderr
            
            elif device.platform == DevicePlatform.IOS:
                # iOS shell is limited
                return -1, "", "Shell not supported on iOS"
                
        except Exception as e:
            return -1, "", str(e)
        
        return -1, "", "Unknown platform"
    
    def get_device(self, device_id: str) -> Optional[DeviceInfo]:
        return self.devices.get(device_id)
    
    def list_devices(self, platform: DevicePlatform | None = None) -> list[DeviceInfo]:
        devices = list(self.devices.values())
        if platform:
            devices = [d for d in devices if d.platform == platform]
        return devices
    
    def on_event(self, callback: callable):
        self.event_callbacks.append(callback)
    
    def _emit_event(self, event_type: str, data: dict):
        for cb in self.event_callbacks:
            try:
                cb(event_type, data)
            except Exception:
                pass


import uuid


async def create_device_manager() -> DeviceManager:
    """Create and initialize device manager."""
    manager = DeviceManager()
    await manager.discover_devices()
    return manager