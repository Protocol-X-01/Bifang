import os

from bifang.judge_quota import public_quota_from_env
from bifang.judge_relay import (
    JUDGE_TOKEN_EXPIRES_ENV,
    PUBLIC_ACCESS_ENV,
    create_app,
    public_access_enabled,
)

public = public_access_enabled(os.environ.get(PUBLIC_ACCESS_ENV))
app = create_app(
    os.environ.get("NEBIUS_API_KEY", ""),
    os.environ.get("BIFANG_JUDGE_TOKEN", ""),
    token_expires_at=os.environ.get(JUDGE_TOKEN_EXPIRES_ENV),
    public_access=public,
    public_quota=public_quota_from_env() if public else None,
    trust_vercel_headers=os.environ.get("VERCEL") == "1",
)
