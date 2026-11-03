import re
import shlex
from pathlib import Path

SECRET_PATTERN = re.compile(
    r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|"
    r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b|\bgh[pousr]_[A-Za-z0-9]{30,}\b|"
    r"\bhf_[A-Za-z0-9]{30,}\b|\bsk-(?:proj-)?[A-Za-z0-9_-]{32,}\b|"
    r"\bnvapi-[A-Za-z0-9_-]{24,}\b|\btvly-[A-Za-z0-9_-]{24,}\b|"
    r"\bglpat-[A-Za-z0-9_-]{20,}\b|\bxox[baprs]-[A-Za-z0-9-]{10,}\b|"
    r"\bAIza[0-9A-Za-z_-]{30,}\b|\bnpm_[A-Za-z0-9]{20,}\b"
)

_PRIVATE_KEY_BLOCK = re.compile(
    r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z0-9 ]*PRIVATE KEY-----"
)
_JWT = re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")
_BEARER = re.compile(r"(?i)(\bBearer\s+)[A-Za-z0-9._~+/-]+=*")
_URI_AUTHORITY = re.compile(
    r"(?i)(?:(?P<scheme>\b[A-Z][A-Z0-9+.-]*:(?:\\?/){2})|"
    r"(?P<boundary>^|[\s\"'=(:,\[{])(?:\\?/){2})"
    r"(?P<authority>[^/?#\s]*)"
)
_CREDENTIAL_ASSIGNMENT = re.compile(
    r"(?i)(\b(?:[A-Z0-9]+[_-])*(?:api[_-]?key|access[_-]?(?:key|token)|refresh[_-]?token|"
    r"auth[_-]?token|client[_-]?secret|secret[_-]?(?:access[_-]?)?key|password|passwd|"
    r"private[_-]?key|token)\b"
    r"[\"']?\s*[:=]\s*)(\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*'|[A-Za-z0-9_~+/=-]{8,})"
)
_BASE64_ONLY_LINE = re.compile(r"(?m)^[A-Za-z0-9+/]{40,}={0,2}$")

_SENSITIVE_DIRECTORIES = {
    ".git", ".bifang", ".arca", ".ssh", ".aws", ".azure", ".gcloud", ".kube", ".docker",
}
_SENSITIVE_NAMES = {
    ".envrc", ".netrc", ".npmrc", ".pypirc", ".git-credentials",
    "credentials", "credentials.db", "credentials.json", "token.json", "auth.json", "secrets",
    "secrets.json", "secrets.yaml", "secrets.yml", "secrets.toml",
    "service-account.json", "application_default_credentials.json",
    "id_rsa", "id_ed25519", "id_ecdsa", "id_dsa",
}
_SENSITIVE_SUFFIXES = {".pem", ".key", ".p8", ".der", ".p12", ".pfx", ".jks", ".keystore", ".mobileprovision"}
_SAFE_ENV_EXAMPLES = {".env.example", ".env.sample", ".env.template", ".env.dist"}


def is_sensitive_workspace_path(path: str | Path) -> bool:
    """Identify conventional credential files and private application state."""
    relative = Path(path)
    parts = tuple(part.casefold() for part in relative.parts)
    if _contains_sensitive_directory(parts, include_git=True):
        return True

    for index, name in enumerate(parts):
        # A sensitive file name used as a directory must protect its entire subtree.
        # Safe .env examples are exempt only when they are the requested final path.
        if _is_sensitive_component(name, allow_safe_example=index == len(parts) - 1):
            return True
    return False


def is_sensitive_command_path(path: str | Path) -> bool:
    """Identify private paths hidden from sandboxed workspace commands.

    Git metadata remains visible so repository commands keep working. Explicit
    credential files inside that metadata are still treated as sensitive.
    """
    relative = Path(path)
    parts = tuple(part.casefold() for part in relative.parts)
    if _contains_sensitive_directory(parts, include_git=False):
        return True

    for index, name in enumerate(parts):
        if _is_sensitive_component(name, allow_safe_example=index == len(parts) - 1):
            return True
    return False


def _contains_sensitive_directory(parts: tuple[str, ...], *, include_git: bool) -> bool:
    protected_directories = _SENSITIVE_DIRECTORIES if include_git else _SENSITIVE_DIRECTORIES - {".git"}
    if any(part in protected_directories for part in parts):
        return True
    return any(parts[index:index + 2] == (".config", "gcloud") for index in range(len(parts) - 1))


def _is_sensitive_component(name: str, *, allow_safe_example: bool) -> bool:
    if allow_safe_example and name in _SAFE_ENV_EXAMPLES:
        return False
    if name == ".env" or name.endswith(".env") or name.startswith(".env."):
        return True
    return name in _SENSITIVE_NAMES or Path(name).suffix in _SENSITIVE_SUFFIXES


def redact_secrets(text: str) -> str:
    """Redact common credentials before workspace text reaches a model."""
    def preserve_line_count(match: re.Match[str]) -> str:
        return "[REDACTED PRIVATE KEY]" + "\n" * match.group(0).count("\n")

    def redact_uri_authority(match: re.Match[str]) -> str:
        prefix = match.group("scheme")
        if prefix is None:
            prefix = f"{match.group('boundary')}//"
        authority = match.group("authority")
        literal_at = authority.rfind("@")
        escaped_at = authority.casefold().rfind(r"\u0040")
        if literal_at < 0 and escaped_at < 0:
            return prefix + authority
        if literal_at > escaped_at:
            userinfo, host = authority[:literal_at], authority[literal_at + 1:]
        else:
            delimiter = r"\u0040"
            userinfo = authority[:escaped_at]
            host = authority[escaped_at + len(delimiter):]
        folded_userinfo = userinfo.casefold()
        if (":" not in userinfo and "%3a" not in folded_userinfo
                and r"\u003a" not in folded_userinfo):
            return prefix + authority
        return f"{prefix}[REDACTED]@{host}"

    text = _PRIVATE_KEY_BLOCK.sub(preserve_line_count, text)
    text = _URI_AUTHORITY.sub(redact_uri_authority, text)
    text = SECRET_PATTERN.sub("[REDACTED]", text)
    text = _JWT.sub("[REDACTED]", text)
    text = _BEARER.sub(r"\1[REDACTED]", text)
    text = _CREDENTIAL_ASSIGNMENT.sub(r"\1[REDACTED]", text)
    return _BASE64_ONLY_LINE.sub("[REDACTED]", text)


def redact_model_diff(diff: str) -> str:
    """Omit credential-file patches and redact recognized values in other hunks."""
    sections = re.split(r"(?m)(?=^diff --git )", diff)
    output = []
    for section in sections:
        first_line = section.splitlines()[0] if section else ""
        if first_line.startswith("diff --git "):
            try:
                paths = shlex.split(first_line)[2:]
            except ValueError:
                paths = []
            workspace_paths = [path[2:] for path in paths if path.startswith(("a/", "b/"))]
            if workspace_paths and any(is_sensitive_workspace_path(path) for path in workspace_paths):
                output.append("[Sensitive file diff omitted]\n")
                continue
        output.append(redact_secrets(section))
    return "".join(output)
