from pathlib import Path
from typing import Literal

ApprovalMode = Literal["manual", "auto", "full"]
APPROVAL_MODES = {"manual", "auto", "full"}
INSPECTION_TOOLS = {"list_files", "read_file", "search", "git_diff", "memory_recall",
                    "memory_context", "todo_read", "todo_write"}
SOURCE_SUFFIXES = {".py", ".js", ".jsx", ".ts", ".tsx", ".rs", ".go", ".java", ".c",
                   ".cpp", ".h", ".css", ".html", ".md", ".txt", ".json", ".yaml", ".yml"}
REVIEW_FILES = {"package.json", "package-lock.json", "pyproject.toml", "uv.lock", "cargo.toml",
                "cargo.lock", "dockerfile", "makefile", "requirements.txt", "setup.py", "setup.cfg"}


def auto_approves_edit(root: Path, source: Path, isolated: bool, arguments: dict) -> bool:
    if not isolated or root.resolve() == source.resolve():
        return False
    value, content = arguments.get("path"), arguments.get("content")
    if not isinstance(value, str) or not isinstance(content, str) or len(content.encode()) > 200_000:
        return False
    target = (root / value).resolve()
    if not target.is_relative_to(root.resolve()):
        return False
    relative = target.relative_to(root.resolve())
    if any(part.startswith(".") or any(word in part.lower() for word in
           ("secret", "credential", "token", "password", "private", "requirements")) for part in relative.parts):
        return False
    return target.suffix.lower() in SOURCE_SUFFIXES and target.name.lower() not in REVIEW_FILES
