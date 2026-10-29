from pathlib import Path

import pytest

from bifang.policy import Policy


def test_path_boundary(tmp_path:Path):
 p=Policy(tmp_path); assert p.path("src")==tmp_path/"src"
 with pytest.raises(PermissionError): p.path("../secret")
def test_assist_approval(tmp_path): assert Policy(tmp_path,"assist").command("pytest -q").approval
def test_observe_denies(tmp_path): assert not Policy(tmp_path,"observe").command("pytest").allowed
def test_sudo_denied(tmp_path): assert not Policy(tmp_path,"trusted").command("sudo id").allowed
