import os
import subprocess
import sys


def test_config_loads_explicit_env_file(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("NEBIUS_API_KEY=test-key\n", encoding="utf-8")
    environment = os.environ.copy()
    environment["BIFANG_ENV_FILE"] = str(env_file)
    environment.pop("BIFANG_NO_DOTENV", None)
    environment.pop("NEBIUS_API_KEY", None)

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from bifang.config import Config; assert Config.load().providers['nebius'].api_key == 'test-key'",
        ],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
