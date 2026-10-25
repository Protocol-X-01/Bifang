import json
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

try:
    for attempt in range(90):
        try:
            with urlopen("http://127.0.0.1:8125/health", timeout=2) as response:
                value = json.load(response)
            if value.get("status") == "ok" and value.get("worker_enabled") is True:
                print(json.dumps({"loopback_service_ready": True}))
                break
        except (OSError, URLError, ValueError):
            pass
        time.sleep(1)
    else:
        raise SystemExit("Remote worker did not become ready")
finally:
    Path("/run/bifang/service.env").unlink(missing_ok=True)
