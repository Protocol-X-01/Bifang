import os
import subprocess
import sys

from bifang import __version__


def test_cli_version_does_not_require_or_advertise_optional_gpu_runtime(tmp_path):
    empty_env = tmp_path / "empty.env"
    empty_env.write_text("")
    environment = {**os.environ, "BIFANG_ENV_FILE": str(empty_env)}
    process = subprocess.run([sys.executable, "-c",
        "import sys; from bifang.cli import main; sys.argv=['bifang', '--version']; main()"],
        cwd=tmp_path, env=environment, text=True, capture_output=True, timeout=15, check=False)
    assert process.returncode == 0
    assert process.stdout.strip() == __version__
    assert process.stderr == ""
