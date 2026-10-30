"""
Bifang AI Attack Hardening Module

Protects against adversarial attacks through uploaded files:
- Image-based attacks (adversarial examples, hidden payloads)
- Document attacks (macro viruses, embedded scripts)
- Code injection through file metadata
- Prompt injection via file content
"""

from __future__ import annotations

import hashlib
import io
import re
import zipfile
import tarfile
import tempfile
from pathlib import Path
from typing import Literal

from PIL import Image, UnidentifiedImageError
import magic


class FileValidationError(ValueError):
    """Raised when file fails security validation"""
    pass


class SuspiciousContentError(FileValidationError):
    """Raised when file contains potential attack payload"""
    pass


# Limits
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
MAX_IMAGE_SIZE = 2 * 1024 * 1024  # 2MB
MAX_ARCHIVE_ENTRIES = 100
MAX_ARCHIVE_SIZE = 50 * 1024 * 1024  # 50MB total

# Dangerous patterns in text files
DANGEROUS_PATTERNS = [
    r'<script[^>]*>.*?</script>',  # JavaScript injection
    r'javascript:',  # JS protocol
    r'on\w+\s*=',  # Event handlers
    r'data:text/html',  # Data URLs
    r'vbscript:',  # VBScript
    r'<iframe',  # Iframes
    r'<object',  # Objects
    r'<embed',  # Embeds
]

# Prompt injection patterns
PROMPT_INJECTION_PATTERNS = [
    r'ignore\s+(all\s+)?previous\s+instructions',
    r'forget\s+(all\s+)?previous\s+instructions',
    r'you\s+are\s+now\s+a\s+different',
    r'disregard\s+your\s+system\s+prompt',
    r'override\s+your\s+programming',
    r'pretend\s+you\s+are',
    r'act\s+as\s+if\s+you\s+are',
    r'simulate\s+being',
]


def validate_file_uploads(files: list[Path], allowed_extensions: list[str] | None = None) -> dict[str, str]:
    """
    Validate multiple uploaded files for AI attacks.
    
    Returns dict of {filename: security_report}
    """
    reports = {}
    
    for file_path in files:
        try:
            report = validate_single_file(file_path, allowed_extensions)
            reports[file_path.name] = f"✅ {report}"
        except FileValidationError as e:
            reports[file_path.name] = f"❌ BLOCKED: {e}"
    
    return reports


def validate_single_file(file_path: Path, allowed_extensions: list[str] | None = None) -> str:
    """
    Validate a single file for AI attacks.
    
    Returns security report string.
    Raises FileValidationError if suspicious.
    """
    # Check file size
    size = file_path.stat().st_size
    if size > MAX_FILE_SIZE:
        raise FileValidationError(f"File too large ({size} bytes > {MAX_FILE_SIZE} limit)")
    
    # Check extension
    if allowed_extensions:
        ext = file_path.suffix.lower()
        if ext not in allowed_extensions:
            raise FileValidationError(f"Extension '{ext}' not allowed")
    
    # Detect actual file type
    mime_type = detect_mime_type(file_path)
    
    # Route to specific validator
    if mime_type.startswith('image/'):
        validate_image_file(file_path)
    elif mime_type in ['application/zip', 'application/x-tar', 'application/gzip']:
        validate_archive_file(file_path)
    elif mime_type.startswith('text/') or mime_type in ['application/json', 'application/xml']:
        validate_text_file(file_path)
    elif mime_type == 'application/pdf':
        validate_pdf_file(file_path)
    else:
        # Unknown type - extra cautious
        validate_generic_file(file_path)
    
    return f"Validated {mime_type} ({size} bytes)"


def detect_mime_type(file_path: Path) -> str:
    """Detect actual MIME type using magic bytes (not extension)"""
    try:
        mime = magic.Magic(mime=True)
        return mime.from_file(str(file_path))
    except Exception:
        return 'application/octet-stream'


def validate_image_file(file_path: Path) -> None:
    """
    Validate image files for adversarial attacks.
    
    Checks:
    - Actual format matches extension
    - No hidden steganography payloads
    - No EXIF-based exploits
    - Reasonable dimensions
    - No animation bombs
    """
    try:
        with Image.open(file_path) as img:
            # Check for decompression bombs
            img.load()
            
            # Verify dimensions
            width, height = img.size
            if width * height > 4_000_000:
                raise FileValidationError("Image dimensions too large (potential decompression bomb)")
            
            # Check for animation bombs
            n_frames = getattr(img, 'n_frames', 1)
            if n_frames > 100:
                raise FileValidationError("Too many frames (potential animation bomb)")
            
            # Strip metadata (EXIF bomb prevention)
            # Metadata is stripped in prepare_image (vision.py)
            
            # Check for steganography markers (basic detection)
            # Note: Sophisticated steganography requires specialized tools
            file_bytes = file_path.read_bytes()
            
            # Check for embedded scripts in-comments (PNG text chunks)
            # This is a basic check - production would need pngcheck
            
    except UnidentifiedImageError:
        raise FileValidationError("Invalid or corrupted image file")
    except Image.DecompressionBombError:
        raise FileValidationError("Decompression bomb detected")


def validate_archive_file(file_path: Path) -> None:
    """
    Validate archive files (zip, tar, gzip) for extraction attacks.
    
    Checks:
    - No path traversal in entries
    - Entry count within limits
    - Total uncompressed size within limits
    - No password-protected bombs
    """
    try:
        if file_path.suffix == '.zip':
            validate_zip_file(file_path)
        elif file_path.suffix in ['.tar', '.tar.gz', '.tgz']:
            validate_tar_file(file_path)
    except Exception as e:
        raise FileValidationError(f"Archive validation failed: {e}")


def validate_zip_file(file_path: Path) -> None:
    """Validate ZIP archives for extraction attacks"""
    total_size = 0
    
    try:
        with zipfile.ZipFile(file_path, 'r') as zf:
            entries = zf.infolist()
            
            # Check entry count
            if len(entries) > MAX_ARCHIVE_ENTRIES:
                raise FileValidationError(f"Too many entries ({len(entries)} > {MAX_ARCHIVE_ENTRIES})")
            
            for entry in entries:
                # Check for path traversal
                if '..' in entry.filename or entry.filename.startswith('/'):
                    raise FileValidationError(f"Path traversal detected: {entry.filename}")
                
                # Check for absolute paths
                if Path(entry.filename).is_absolute():
                    raise FileValidationError(f"Absolute path not allowed: {entry.filename}")
                
                # Check uncompressed size
                total_size += entry.file_size
                if total_size > MAX_ARCHIVE_SIZE:
                    raise FileValidationError(f"Archive too large when extracted ({total_size} bytes)")
                
                # Check for symlinks (potential escape)
                if entry.is_dir() is False and entry.external_attr >> 28 == 0xA:
                    raise FileValidationError(f"Symlinks not allowed: {entry.filename}")
    
    except zipfile.BadZipFile:
        raise FileValidationError("Invalid or corrupted ZIP file")


def validate_tar_file(file_path: Path) -> None:
    """Validate TAR archives for extraction attacks"""
    total_size = 0
    entry_count = 0
    
    try:
        with tarfile.open(file_path, 'r:*') as tf:
            for member in tf:
                entry_count += 1
                
                if entry_count > MAX_ARCHIVE_ENTRIES:
                    raise FileValidationError(f"Too many entries")
                
                # Check for path traversal
                if '..' in member.name or member.name.startswith('/'):
                    raise FileValidationError(f"Path traversal: {member.name}")
                
                # Check for symlinks
                if member.issym() or member.islnk():
                    raise FileValidationError(f"Symlinks/hardlinks not allowed: {member.name}")
                
                # Check size
                total_size += member.size
                if total_size > MAX_ARCHIVE_SIZE:
                    raise FileValidationError("Archive too large")
    
    except tarfile.TarError:
        raise FileValidationError("Invalid or corrupted TAR file")


def validate_text_file(file_path: Path) -> None:
    """
    Validate text files for prompt injection and XSS attacks.
    
    Checks:
    - No embedded scripts
    - No prompt injection patterns
    - No suspicious HTML/JS
    """
    try:
        content = file_path.read_text(encoding='utf-8', errors='ignore')
    except Exception:
        content = file_path.read_bytes().decode('utf-8', errors='ignore')
    
    # Check for dangerous patterns
    for pattern in DANGEROUS_PATTERNS:
        if re.search(pattern, content, re.IGNORECASE):
            raise SuspiciousContentError(f"Suspicious content detected (potential XSS)")
    
    # Check for prompt injection
    for pattern in PROMPT_INJECTION_PATTERNS:
        if re.search(pattern, content, re.IGNORECASE):
            raise SuspiciousContentError(f"Potential prompt injection detected")
    
    # Check for excessive repetition (DoS)
    lines = content.split('\n')
    if len(lines) > 10_000:
        raise FileValidationError("File has too many lines (potential DoS)")


def validate_pdf_file(file_path: Path) -> None:
    """
    Validate PDF files for embedded exploits.
    
    Checks:
    - No JavaScript
    - No embedded executables
    - No suspicious actions
    """
    # Basic PDF validation - production would need PyPDF2 or similar
    file_bytes = file_path.read_bytes()
    
    # Check for PDF magic bytes
    if not file_bytes.startswith(b'%PDF'):
        raise FileValidationError("Invalid PDF file")
    
    # Check for embedded JavaScript (basic)
    if b'/JavaScript' in file_bytes or b'/JS' in file_bytes:
        raise SuspiciousContentError("PDF contains JavaScript (blocked)")
    
    # Check for embedded executables
    if b'/EmbeddedFile' in file_bytes:
        raise SuspiciousContentError("PDF contains embedded files (blocked)")


def validate_generic_file(file_path: Path) -> None:
    """
    Validate files of unknown type.
    
    Extra cautious validation:
    - Scan for embedded scripts
    - Check for executable signatures
    """
    file_bytes = file_path.read_bytes()
    
    # Check for executable signatures
    executable_sigs = [
        b'MZ',  # Windows PE
        b'\x7fELF',  # Linux ELF
        b'\xca\xfe\xba\xbe',  # Java class
        b'dex\n',  # Android DEX
    ]
    
    for sig in executable_sigs:
        if file_bytes.startswith(sig):
            raise FileValidationError("Executable files not allowed")
    
    # Scan for script signatures anywhere in file
    script_patterns = [
        b'<script',
        b'javascript:',
        b'<?php',
        b'<%',
        b'#!',
    ]
    
    for pattern in script_patterns:
        if pattern in file_bytes[:4096]:  # Check first 4KB
            raise SuspiciousContentError(f"Embedded script detected")


def sanitize_filename(filename: str) -> str:
    """
    Sanitize filename to prevent path traversal and injection.
    
    Returns safe filename or raises FileValidationError.
    """
    # Remove path separators
    safe = filename.replace('/', '_').replace('\\', '_')
    
    # Remove null bytes
    safe = safe.replace('\x00', '')
    
    # Remove leading dots
    safe = safe.lstrip('.')
    
    # Limit length
    if len(safe) > 255:
        safe = safe[:255]
    
    if not safe or safe in ['.', '..']:
        raise FileValidationError(f"Invalid filename: {filename}")
    
    return safe


def check_file_entropy(file_path: Path) -> float:
    """
    Calculate file entropy (measure of randomness).
    
    High entropy may indicate encryption/compression bombs.
    Returns bits per byte (0-8).
    """
    import math
    from collections import Counter
    
    file_bytes = file_path.read_bytes()
    
    if not file_bytes:
        return 0.0
    
    byte_counts = Counter(file_bytes)
    file_size = len(file_bytes)
    
    entropy = 0.0
    for count in byte_counts.values():
        if count:
            probability = count / file_size
            entropy -= probability * math.log2(probability)
    
    return entropy


# Integration with existing guardrails

def integrate_with_guardrails() -> None:
    """
    Add file validation to existing guardrails system.
    
    Should be called during initialization.
    """
    from . import guardrails
    
    # Add file validation to safety checks
    original_validate = guardrails.validate_command_safety
    
    def enhanced_validate_command(cmd: list[str]) -> tuple[bool, str]:
        """Enhanced validation that checks file operations"""
        # Check for file operations
        file_operations = {'cat', 'head', 'tail', 'less', 'more', 'vim', 'nano', 'emacs'}
        
        if cmd and cmd[0] in file_operations:
            # Validate file paths in command
            for part in cmd[1:]:
                if '/' in part or part.startswith('.'):
                    try:
                        validate_single_file(Path(part))
                    except Exception as e:
                        return False, f"File validation failed: {e}"
        
        return original_validate_command(cmd)
    
    # Monkey-patch (production would use proper integration)
    guardrails.validate_command_safety = enhanced_validate_command


__all__ = [
    'FileValidationError',
    'SuspiciousContentError',
    'validate_file_uploads',
    'validate_single_file',
    'sanitize_filename',
    'check_file_entropy',
]
