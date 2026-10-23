from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

BLOCKED=[
 (r"(^|\s)sudo(\s|$)","privilege escalation"),
 (r"(^|\s)(su|shutdown|reboot|mkfs|fdisk)(\s|$)","host administration"),
 (r"(^|\s)rm\s+[^\n]*(?:-r|-f|--recursive|--force)","destructive removal"),
 (r"\$\(|`","command substitution"),
 (r"(^|\s)(ssh|scp|rsync)(\s|$)","remote access"),
 (r"(/|~)\.ssh|\.aws/credentials|\.config/gcloud","credential access"),
]
@dataclass(frozen=True)
class Decision:
 allowed:bool; approval:bool; reason:str
class Policy:
 def __init__(self,root:Path,mode="assist"): self.root=root.resolve(); self.mode=mode
 def path(self,value:str|Path)->Path:
  p=Path(value); p=(self.root/p).resolve() if not p.is_absolute() else p.resolve()
  if p!=self.root and self.root not in p.parents: raise PermissionError(f"Path escapes Arca: {value}")
  return p
 def command(self,cmd:str,mutating=True)->Decision:
  if self.mode=="observe": return Decision(False,False,"observe mode")
  for pattern,reason in BLOCKED:
   if re.search(pattern,cmd,re.IGNORECASE): return Decision(False,False,f"blocked: {reason}")
  return Decision(True,self.mode=="assist" and mutating,"allowed")
