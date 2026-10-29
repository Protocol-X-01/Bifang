"""LangChain Guardrails integration for Bifang.

Provides safety validation for AI-generated commands and outputs.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any


def validate_command_safety(command: list[str]) -> tuple[bool, str]:
    """Validate shell command safety before execution.

    Checks against dangerous patterns that could compromise system security.

    Args:
        command: List of command parts (e.g., ["ls", "-la"])

    Returns:
        Tuple of (safe: bool, message: str)
    """
    if not isinstance(command, list) or not command:
        return False, "Command must be a non-empty list"

    if not all(isinstance(part, str) for part in command):
        return False, "All command parts must be strings"

    dangerous_patterns = [
        (r"sudo\s", "sudo requires explicit approval"),
        (r"chmod\s+[0-7]{3,4}", "chmod with broad permissions"),
        (r">\s*/etc/", "writing to system configuration"),
        (r"curl.*\|\s*(bash|sh)", "remote code execution via curl"),
        (r"wget.*\|\s*(bash|sh)", "remote code execution via wget"),
        (r"rm\s+-rf\s+/", "recursive root deletion"),
        (r">\s*/dev/sd", "direct disk write"),
        (r"mkfs\.", "filesystem formatting"),
        (r"dd\s+if=", "disk duplication"),
        (r":()\s*{\s*:\s*|\s*:\s*}", "fork bomb pattern"),
        (r"eval\s+", "eval is dangerous"),
        (r"exec\s+", "exec replaces process"),
    ]

    command_str = " ".join(command)

    for pattern, reason in dangerous_patterns:
        if re.search(pattern, command_str):
            return False, f"Blocked: {reason}"

    return True, "OK"


def filter_pii(text: str) -> tuple[str, list[str]]:
    """Filter personally identifiable information from text.

    Detects and masks common PII patterns like emails, phone numbers,
    and API keys.

    Args:
        text: Input text to filter

    Returns:
        Tuple of (filtered_text: str, warnings: list[str])
    """
    warnings = []
    filtered = text

    email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
    if re.search(email_pattern, filtered):
        filtered = re.sub(email_pattern, '[EMAIL]', filtered)
        warnings.append("Email address filtered")

    phone_pattern = r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b'
    if re.search(phone_pattern, filtered):
        filtered = re.sub(phone_pattern, '[PHONE]', filtered)
        warnings.append("Phone number filtered")

    ssn_pattern = r'\b\d{3}-\d{2}-\d{4}\b'
    if re.search(ssn_pattern, filtered):
        filtered = re.sub(ssn_pattern, '[SSN]', filtered)
        warnings.append("SSN filtered")

    api_key_patterns = [
        (r'sk-[A-Za-z0-9]{20,}', "OpenAI-style API key"),
        (r'NEBIUS_API_KEY\s*=\s*[A-Za-z0-9_-]+', "NEBIUS API key"),
        (r'TAVILY_API_KEY\s*=\s*[A-Za-z0-9_-]+', "TAVILY API key"),
        (r'LANGSMITH_API_KEY\s*=\s*[A-Za-z0-9_-]+', "LANGSMITH API key"),
        (r'x-api-key:\s*[A-Za-z0-9_-]+', "API key header"),
    ]

    for pattern, key_type in api_key_patterns:
        if re.search(pattern, text):
            warnings.append(f"Potential {key_type} detected")

    return filtered, warnings


def validate_file_path(
    path: str, allowed_roots: list[str]
) -> tuple[bool, str]:
    """Validate file path stays within allowed directories.

    Prevents directory traversal attacks and ensures operations
    only occur within designated workspace areas.

    Args:
        path: File path to validate
        allowed_roots: List of allowed root directories

    Returns:
        Tuple of (valid: bool, message: str)
    """
    if not path or not isinstance(path, str):
        return False, "Path must be a non-empty string"

    if not allowed_roots:
        return False, "Must specify at least one allowed root"

    try:
        resolved = Path(path).resolve()
    except (OSError, ValueError) as e:
        return False, f"Invalid path: {e}"

    for root in allowed_roots:
        try:
            root_path = Path(root).resolve()
            if str(resolved).startswith(str(root_path)):
                return True, "OK"
        except (OSError, ValueError):
            continue

    return False, "Path outside allowed workspace roots"


def validate_edit_safety(
    file_path: str, content: str, allowed_roots: list[str]
) -> tuple[bool, str]:
    """Validate a file edit operation for safety.

    Combines path validation with content checks.

    Args:
        file_path: Target file path
        content: Content to write
        allowed_roots: Allowed directory roots

    Returns:
        Tuple of (safe: bool, message: str)
    """
    valid, msg = validate_file_path(file_path, allowed_roots)
    if not valid:
        return False, msg

    dangerous_imports = [
        r"import\s+os\s*;\s*os\.system",
        r"subprocess\.call\s*\(\s*['\"]",
        r"eval\s*\(",
        r"exec\s*\(",
    ]

    for pattern in dangerous_imports:
        if re.search(pattern, content):
            return False, f"Blocked dangerous pattern in content: {pattern}"

    return True, "OK"


def create_safety_report(
    command: list[str] | None = None,
    text: str | None = None,
    path: str | None = None,
    allowed_roots: list[str] | None = None,
) -> dict[str, Any]:
    """Generate comprehensive safety report.

    Args:
        command: Optional command to validate
        text: Optional text to filter
        path: Optional path to validate
        allowed_roots: Optional allowed roots for path validation

    Returns:
        Dictionary with safety report details
    """
    report = {
        "timestamp": None,
        "checks": [],
        "warnings": [],
        "passed": True,
    }

    if command is not None:
        safe, msg = validate_command_safety(command)
        report["checks"].append({
            "type": "command",
            "passed": safe,
            "message": msg
        })
        if not safe:
            report["passed"] = False
            report["warnings"].append(f"Command unsafe: {msg}")

    if text is not None:
        filtered, warnings = filter_pii(text)
        report["checks"].append({
            "type": "pii_filter",
            "passed": True,
            "warnings": warnings,
            "modified": filtered != text
        })
        report["warnings"].extend(warnings)

    if path is not None and allowed_roots is not None:
        valid, msg = validate_file_path(path, allowed_roots)
        report["checks"].append({
            "type": "path",
            "passed": valid,
            "message": msg
        })
        if not valid:
            report["passed"] = False
            report["warnings"].append(f"Path invalid: {msg}")

    from datetime import datetime, timezone
    report["timestamp"] = datetime.now(timezone.utc).isoformat()

    return report
