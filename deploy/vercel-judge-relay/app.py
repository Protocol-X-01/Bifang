import os

from bifang.judge_relay import create_app

app = create_app(os.environ.get("NEBIUS_API_KEY", ""), os.environ.get("BIFANG_JUDGE_TOKEN", ""))
