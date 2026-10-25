import socket
import struct
import time
from pathlib import Path

path = Path("/run/bifang-executor/check.sock")
for attempt in range(100):
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(1)
            connection.connect(str(path))
            peer = connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i"))
            if struct.unpack("3i", peer)[1] != 0:
                raise RuntimeError("Unexpected executor peer")
        assert path.stat().st_uid == 10001 and path.stat().st_mode & 0o077 == 0
        break
    except OSError:
        time.sleep(0.1)
else:
    raise SystemExit("Executor socket did not become ready")
