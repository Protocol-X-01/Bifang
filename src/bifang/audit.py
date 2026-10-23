import json
from datetime import UTC, datetime
from pathlib import Path


class Audit:
 def __init__(self,root:Path):
   d=root/".bifang/sessions"; d.mkdir(parents=True,exist_ok=True)
   self.path=d/(datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")+".jsonl")
 def add(self,event,**data):
  row={"time":datetime.now(UTC).isoformat(),"event":event,**data}
  with self.path.open("a",encoding="utf-8") as f: f.write(json.dumps(row,ensure_ascii=False)+"\n")
