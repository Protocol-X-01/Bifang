import subprocess
from pathlib import Path

from bifang.workspace import Workspace


def test_non_git_workspace(tmp_path:Path, monkeypatch):
 monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
 source = tmp_path / "source"
 source.mkdir()
 workspace = Workspace.create(source)
 try:
  assert workspace.root != source and workspace.isolated
  assert not (source / ".git").exists()
 finally:
  workspace.discard()


def test_diff_includes_untracked_files(tmp_path:Path):
 subprocess.run(["git","init",str(tmp_path)],check=True,capture_output=True)
 subprocess.run(["git","-C",str(tmp_path),"config","user.email","test@example.com"],check=True)
 subprocess.run(["git","-C",str(tmp_path),"config","user.name","Test"],check=True)
 tracked=tmp_path/"tracked.txt"
 tracked.write_text("before\n")
 subprocess.run(["git","-C",str(tmp_path),"add","tracked.txt"],check=True)
 subprocess.run(["git","-C",str(tmp_path),"commit","-m","initial"],check=True,capture_output=True)
 tracked.write_text("after\n")
 (tmp_path/"new.txt").write_text("new file\n")
 (tmp_path/".bifang").mkdir()
 (tmp_path/".bifang"/"audit.jsonl").write_text("private-transcript-content\n")

 diff=Workspace(tmp_path,tmp_path).diff()

 assert "-before" in diff
 assert "+after" in diff
 assert "diff --git a/new.txt b/new.txt" in diff
 assert "+new file" in diff
 assert ".bifang" not in diff
 assert "private-transcript-content" not in diff


def test_apply_patch_to_clean_source(tmp_path:Path):
 source=tmp_path/"source"
 worktree=tmp_path/"worktree"
 source.mkdir()
 subprocess.run(["git","init",str(source)],check=True,capture_output=True)
 subprocess.run(["git","-C",str(source),"config","user.email","test@example.com"],check=True)
 subprocess.run(["git","-C",str(source),"config","user.name","Test"],check=True)
 (source/"tracked.txt").write_text("before\n")
 subprocess.run(["git","-C",str(source),"add","tracked.txt"],check=True)
 subprocess.run(["git","-C",str(source),"commit","-m","initial"],check=True,capture_output=True)
 subprocess.run(["git","-C",str(source),"worktree","add","-b","bifang/test",str(worktree),"HEAD"],check=True,capture_output=True)
 (worktree/"tracked.txt").write_text("after\n")
 (worktree/"new.txt").write_text("new file\n")

 assert Workspace(source,worktree,isolated=True).apply()
 assert (source/"tracked.txt").read_text()=="after\n"
 assert (source/"new.txt").read_text()=="new file\n"
