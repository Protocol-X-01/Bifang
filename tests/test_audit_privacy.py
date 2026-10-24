import json
import os

import pytest

from bifang.audit import Audit


def test_audit_records_are_private_and_do_not_collide_between_sessions(tmp_path):
    first = Audit(tmp_path)
    second = Audit(tmp_path)
    assert first.path != second.path
    first.add("user", content="synthetic quotation café")
    second.add("user", content="different conversation")
    assert json.loads(first.path.read_text())["content"] == "synthetic quotation café"
    assert json.loads(second.path.read_text())["content"] == "different conversation"
    if os.name == "posix":
        assert first.path.stat().st_mode & 0o777 == 0o600
        assert first.path.parent.stat().st_mode & 0o777 == 0o700


def test_audit_rejects_directory_symlink_escaping_the_workspace(tmp_path):
    workspace = tmp_path / "workspace"
    outside = tmp_path / "outside"
    workspace.mkdir()
    outside.mkdir()
    (workspace / ".bifang").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="escapes"):
        Audit(workspace)
    assert list(outside.iterdir()) == []
