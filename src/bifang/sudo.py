from __future__ import annotations

import asyncio
import os
import shlex
import subprocess
import time
from dataclasses import dataclass, field
from typing import Dict, Optional, Set
from pathlib import Path


@dataclass
class SudoRule:
    """A rule allowing a specific command to run with sudo."""
    command_pattern: str  # Exact command or pattern with wildcards
    description: str
    granted_at: float
    expires_at: float | None = None
    max_uses: int | None = None
    uses: int = 0
    require_confirmation: bool = True


class SudoManager:
    """Manages sudo privilege gifting for the agent."""
    
    def __init__(self):
        self.rules: Dict[str, SudoRule] = {}
        self.session_grants: Set[str] = set()  # Rules granted in current session
    
    def add_rule(self, rule: SudoRule) -> None:
        """Add a sudo rule."""
        self.rules[rule.command_pattern] = rule
    
    def remove_rule(self, pattern: str) -> bool:
        """Remove a sudo rule."""
        if pattern in self.rules:
            del self.rules[pattern]
            return True
        return False
    
    def check_sudo_allowed(self, command: str) -> tuple[bool, str | None, SudoRule | None]:
        """
        Check if a command is allowed to run with sudo.
        Returns (allowed, reason, matching_rule).
        """
        for pattern, rule in self.rules.items():
            if self._match_command(command, pattern):
                # Check expiration
                if rule.expires_at and time.time() > rule.expires_at:
                    return False, f"Sudo rule expired: {rule.description}", rule
                
                # Check max uses
                if rule.max_uses and rule.uses >= rule.max_uses:
                    return False, f"Sudo rule max uses exceeded: {rule.description}", rule
                
                return True, None, rule
        
        return False, "No matching sudo rule", None
    
    def _match_command(self, command: str, pattern: str) -> bool:
        """Match command against pattern (supports wildcards)."""
        import fnmatch
        return fnmatch.fnmatch(command, pattern)
    
    def grant_for_session(self, pattern: str) -> bool:
        """Grant sudo for a command pattern for the current session only."""
        if pattern in self.rules:
            self.session_grants.add(pattern)
            return True
        return False
    
    def revoke_session_grant(self, pattern: str) -> bool:
        """Revoke a session-only grant."""
        self.session_grants.discard(pattern)
        return True
    
    def use_rule(self, pattern: str) -> bool:
        """Increment usage count for a rule."""
        if pattern in self.rules:
            self.rules[pattern].uses += 1
            return True
        return False
    
    async def run_with_sudo(self, command: str, timeout: int = 180) -> dict:
        """Run a command with sudo if allowed."""
        allowed, reason, rule = self.check_sudo_allowed(command)
        
        if not allowed:
            return {
                "returncode": -1,
                "stdout": "",
                "stderr": f"Sudo not allowed: {reason}",
            }
        
        # Increment usage
        if rule:
            self.use_rule(rule.command_pattern)
        
        # Run with sudo
        sudo_cmd = f"sudo {command}"
        env = {k: v for k, v in os.environ.items() if k in {"PATH", "LANG", "LC_ALL", "TERM", "USER"}}
        
        try:
            proc = await asyncio.create_subprocess_exec(
                "sudo", "-n", *shlex.split(command),
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout)
                return {
                    "returncode": proc.returncode,
                    "stdout": stdout.decode(errors="replace")[-100000:],
                    "stderr": stderr.decode(errors="replace")[-100000:],
                }
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                return {
                    "returncode": -1,
                    "stdout": "",
                    "stderr": f"Timed out after {timeout}s",
                }
        except Exception as e:
            return {
                "returncode": -1,
                "stdout": "",
                "stderr": f"Failed to execute: {e}",
            }
    
    def list_rules(self) -> list[SudoRule]:
        """List all sudo rules."""
        return list(self.rules.values())
    
    def get_rule(self, pattern: str) -> SudoRule | None:
        """Get a specific rule."""
        return self.rules.get(pattern)


# Default rules for common development tasks
DEFAULT_SUDO_RULES = [
    SudoRule(
        command_pattern="apt install *",
        description="Install packages via apt",
        granted_at=time.time(),
        max_uses=10,
    ),
    SudoRule(
        command_pattern="apt update",
        description="Update package lists",
        granted_at=time.time(),
    ),
    SudoRule(
        command_pattern="apt upgrade *",
        description="Upgrade packages",
        granted_at=time.time(),
        max_uses=5,
    ),
    SudoRule(
        command_pattern="systemctl restart *",
        description="Restart systemd services",
        granted_at=time.time(),
        max_uses=5,
    ),
    SudoRule(
        command_pattern="systemctl start *",
        description="Start systemd services",
        granted_at=time.time(),
        max_uses=5,
    ),
    SudoRule(
        command_pattern="systemctl stop *",
        description="Stop systemd services",
        granted_at=time.time(),
        max_uses=5,
    ),
    SudoRule(
        command_pattern="docker *",
        description="Docker commands",
        granted_at=time.time(),
    ),
    SudoRule(
        command_pattern="npm install -g *",
        description="Global npm packages",
        granted_at=time.time(),
        max_uses=10,
    ),
    SudoRule(
        command_pattern="pip install *",
        description="Pip packages (system-wide)",
        granted_at=time.time(),
        max_uses=10,
    ),
    SudoRule(
        command_pattern="cargo install *",
        description="Cargo packages (system-wide)",
        granted_at=time.time(),
        max_uses=10,
    ),
]


def create_sudo_manager(with_defaults: bool = True) -> SudoManager:
    """Create a sudo manager with optional default rules."""
    manager = SudoManager()
    if with_defaults:
        for rule in DEFAULT_SUDO_RULES:
            manager.add_rule(rule)
    return manager