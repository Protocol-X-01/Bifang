import json
import os
import re
import subprocess
import tempfile
from pathlib import Path


def fetch_environment(destination, runner=subprocess.run):
    directory = destination.parent
    if directory.is_symlink() or not directory.is_dir() or directory.stat().st_mode & 0o077:
        raise ValueError("Use a private runtime directory")
    if destination.is_symlink():
        raise ValueError("Runtime environment path must not be a symlink")
    values = {}
    for parameter, variable, required in (
        ("nebius_api_key", "NEBIUS_API_KEY", True),
        ("client_registry", "BIFANG_REMOTE_CLIENTS", True),
        ("nvidia_api_key", "NVIDIA_API_KEY", False),
    ):
        result = runner(["aws", "ssm", "get-parameter", "--region", "us-east-1", "--with-decryption",
                         "--name", "/bifang/remote/" + parameter, "--output", "json", "--no-cli-pager"],
                        capture_output=True, text=True, timeout=30)
        if result.returncode:
            if not required and re.search(r"\(ParameterNotFound\)", result.stderr):
                continue
            raise RuntimeError("Runtime parameter unavailable: " + parameter)
        value = json.loads(result.stdout)["Parameter"]["Value"]
        if not isinstance(value, str) or not value or any(character in value for character in "\r\n\x00"):
            raise ValueError("Invalid runtime parameter: " + parameter)
        values[variable] = value
    if not isinstance(json.loads(values["BIFANG_REMOTE_CLIENTS"]), list):
        raise TypeError("Invalid client registry")
    descriptor, name = tempfile.mkstemp(prefix=".environment-", dir=directory)
    staging = Path(name)
    try:
        with os.fdopen(descriptor, "w") as stream:
            for variable, value in values.items():
                stream.write(variable + "=" + value + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(staging, destination)
    finally:
        staging.unlink(missing_ok=True)
    return len(values) - 1


if __name__ == "__main__":
    count = fetch_environment(Path("/run/bifang/service.env"))
    print(json.dumps({"runtime_environment_prepared": True, "provider_count": count}))
