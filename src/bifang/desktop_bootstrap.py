import json
import os
import secrets
import socket

import uvicorn


def serve_desktop(app):
    os.environ["BIFANG_SERVER_HOST"] = "127.0.0.1"
    os.environ["BIFANG_SERVER_REQUIRE_AUTH"] = "1"
    os.environ["BIFANG_SERVER_API_KEY"] = secrets.token_hex(32)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]

        class DesktopServer(uvicorn.Server):
            async def startup(self, sockets=None):
                await super().startup(sockets=sockets)
                if self.started:
                    print("BIFANG_DESKTOP_READY " + json.dumps({
                        "version": 1,
                        "origin": f"http://127.0.0.1:{port}",
                        "api_key": os.environ["BIFANG_SERVER_API_KEY"],
                    }), flush=True)

        DesktopServer(uvicorn.Config(app, access_log=False)).run(sockets=[listener])
