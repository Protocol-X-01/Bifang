import re
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
    r"[\"']?[^\S\r\n]*[:=][^\S\r\n]*)(\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*'|"
    # Bare values include punctuation and escaped spaces, ending at unescaped whitespace.
    r"(?:\\[^\r\n]|[^\s])+)"
)
_BASE64_ONLY_LINE = re.compile(r"(?m)^[A-Za-z0-9+/]{40,}={0,2}$")
_GIT_QUOTED_PATH = re.compile(r'"(?:[^"\\]|\\.)*"')

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


def _decode_git_path(value: str) -> str | None:
    """Decode Git's C-style pathname quoting, including octal-escaped bytes."""
    if not value.startswith('"'):
        if not value or any(character in '\\"' or ord(character) < 32 or ord(character) == 127
                            for character in value):
            return None
        return value
    if _GIT_QUOTED_PATH.fullmatch(value) is None:
        return None

    escapes = {'a': 7, 'b': 8, 't': 9, 'n': 10, 'v': 11, 'f': 12, 'r': 13,
               '\\': 92, '"': 34}
    encoded = bytearray()
    index = 1
    while index < len(value) - 1:
        character = value[index]
        if character == '\\':
            index += 1
            character = value[index]
            if character in escapes:
                encoded.append(escapes[character])
            else:
                digits = value[index:index + 3]
                if len(digits) != 3 or any(digit not in '01234567' for digit in digits):
                    return None
                number = int(digits, 8)
                if number > 255:
                    return None
                encoded.append(number)
                index += 2
        else:
            if ord(character) < 32 or ord(character) == 127:
                return None
            try:
                encoded.extend(character.encode('utf-8', errors='surrogateescape'))
            except UnicodeError:
                return None
        index += 1
    decoded = encoded.decode('utf-8', errors='surrogateescape')
    return decoded if decoded and '\0' not in decoded else None


def _git_diff_path(value: str, prefix: str | None) -> str | None:
    decoded = _decode_git_path(value)
    if decoded is None:
        return None
    if prefix is None:
        if not decoded.startswith(('a/', 'b/')):
            return None
        prefix = decoded[:2]
    if not decoded.startswith(prefix):
        return None
    relative = decoded[len(prefix):]
    if any(part in {'', '.', '..'} for part in relative.split('/')):
        return None
    return relative


def _git_diff_paths(section: str) -> tuple[str, ...] | None:
    """Verify affected paths without treating unquoted spaces as shell separators."""
    header, _, remainder = section.partition('\n')
    header = header.removeprefix('diff --git ')
    if header.startswith('"'):
        quoted = _GIT_QUOTED_PATH.match(header)
        if quoted is None or header[quoted.end():quoted.end() + 1] != ' ':
            return None
        pairs = [(header[:quoted.end()], header[quoted.end() + 1:])]
    else:
        # A filename can itself contain " b/". Keep every possible split until
        # file/rename metadata can establish which two complete paths Git emitted.
        pairs = [(header[:match.start()], header[match.end():])
                 for match in re.finditer(r' (?=[ab]/|"[ab]/)', header)]
    candidates = set()
    for old, new in pairs:
        # --no-index directory additions/deletions can use b/ or a/ on both sides.
        old_path, new_path = _git_diff_path(old, None), _git_diff_path(new, None)
        if old_path is not None and new_path is not None:
            candidates.add((old_path, new_path))

    hints = (('--- ', 0, True), ('+++ ', 1, True),
             ('rename from ', 0, False), ('rename to ', 1, False),
             ('copy from ', 0, False), ('copy to ', 1, False))
    binary = False
    modes = set()
    renamed_or_copied = False
    for line in remainder.split('\n'):
        if line.startswith('@@'):
            break
        if line.startswith(('GIT binary patch', 'Binary files ')):
            binary = True
            break
        mode = re.fullmatch(r'(old|new) mode [0-7]{6}', line)
        if mode:
            modes.add(mode.group(1))
        for label, side, prefixed in hints:
            if not line.startswith(label):
                continue
            value = line[len(label):]
            if prefixed:
                # Git appends a tab to unquoted ---/+++ paths containing spaces.
                value = value.removesuffix('\t')
                if value == '/dev/null':
                    break
            else:
                renamed_or_copied = True
            path = _git_diff_path(value, None if prefixed else '')
            if path is None:
                return None
            candidates = {pair for pair in candidates if pair[side] == path}
            break
    if len(candidates) > 1 and not renamed_or_copied and (binary or modes == {'old', 'new'}):
        same_path = {pair for pair in candidates if pair[0] == pair[1]}
        if len(same_path) == 1:
            # Binary/mode-only sections may lack path markers. A same-path split
            # identifies that shape, but --no-index can mean a different pair:
            # retain ALL alternatives for the sensitive-path decision.
            return tuple(path for pair in candidates for path in pair)
    return next(iter(candidates)) if len(candidates) == 1 else None


def redact_model_diff(diff: str) -> str:
    """Omit credential-file patches and redact recognized values in other hunks."""
    sections = re.split(r"(?m)(?=^diff --git )", diff)
    output = []
    for section in sections:
        if section.startswith("diff --git "):
            paths = _git_diff_paths(section)
            if paths is None or any(is_sensitive_workspace_path(path) for path in paths):
                output.append("[Sensitive file diff omitted]\n")
                continue
        output.append(redact_secrets(section))
    return "".join(output)
