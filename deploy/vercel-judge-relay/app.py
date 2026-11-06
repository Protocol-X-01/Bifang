import os

from bifang.judge_relay import JUDGE_TOKEN_EXPIRES_ENV, create_app

app = create_app(
    os.environ.get("NEBIUS_API_KEY", ""),
    os.environ.get("BIFANG_JUDGE_TOKEN", ""),
    token_expires_at=os.environ.get(JUDGE_TOKEN_EXPIRES_ENV),
)
