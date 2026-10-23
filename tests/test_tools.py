import asyncio
from pathlib import Path

from bifang.tools import list_files
from bifang.tools.builtin import code_execute


def test_list_skips_state(tmp_path:Path):
  (tmp_path/"a.py").write_text("x=1"); (tmp_path/".bifang").mkdir(); (tmp_path/".bifang/x").write_text("x")
  assert list_files(tmp_path)=="a.py"


def test_code_execute_does_not_inherit_secrets(monkeypatch):
    monkeypatch.setenv("BIFANG_TEST_SECRET", "marker-secret")
    output = asyncio.run(code_execute("import os; print(os.getenv('BIFANG_TEST_SECRET', 'missing'))"))

    assert "missing" in output
    assert "marker-secret" not in output
