import json
import time
from pathlib import Path
from urllib.request import urlopen

try:
    for attempt in range(90):
        try:
            with urlopen('http://127.0.0.1:8125/health',timeout=2) as response:
                value=json.load(response)
            if value.get('status')=='ok' and value.get('worker_enabled') is True and value.get('coding_enabled') is True:
                print(json.dumps({'production_coding_ready':True}))
                break
        except (OSError,ValueError):
            pass
        time.sleep(1)
    else:
        raise SystemExit('Coding service did not become ready')
finally:
    Path('/run/bifang/service.env').unlink(missing_ok=True)
