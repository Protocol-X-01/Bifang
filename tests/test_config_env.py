import os
import subprocess
import sys
from pathlib import Path


def test_config_loads_explicit_env_file(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("NEBIUS_API_KEY=test-key\n", encoding="utf-8")
    environment = os.environ.copy()
    environment["BIFANG_ENV_FILE"] = str(env_file)
    environment.pop("BIFANG_NO_DOTENV", None)
    environment.pop("NEBIUS_API_KEY", None)
    source = Path(__file__).resolve().parents[1] / "src"
    environment["PYTHONPATH"] = os.pathsep.join(filter(None, [str(source), environment.get("PYTHONPATH", "")]))

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


def test_config_wires_zai_and_huggingface_providers():
    environment = os.environ.copy()
    for key in list(environment):
        if key in {"ZAI_API_KEY", "ZHIPU_API_KEY", "GLM_API_KEY", "HF_TOKEN", "HUGGINGFACE_API_KEY",
                   "BIFANG_ZAI_BASE_URL", "BIFANG_ZAI_MODEL", "BIFANG_HUGGINGFACE_BASE_URL",
                   "BIFANG_HUGGINGFACE_MODEL", "BIFANG_DEFAULT_PROVIDER"}:
            environment.pop(key)
    environment["BIFANG_NO_DOTENV"] = "1"
    environment["ZAI_API_KEY"] = "zai-test"
    environment["HF_TOKEN"] = "hf-test"
    source = Path(__file__).resolve().parents[1] / "src"
    environment["PYTHONPATH"] = os.pathsep.join(filter(None, [str(source), environment.get("PYTHONPATH", "")]))

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from bifang.config import Config;\ncfg = Config.load()\n"
            "assert cfg.providers['zai'].api_key == 'zai-test'\n"
            "assert cfg.providers['zai'].base_url.endswith('/api/paas/v4')\n"
            "assert cfg.providers['zai'].default_model == 'glm-5.3'\n"
            "assert cfg.providers['huggingface'].base_url.endswith('router.huggingface.co/v1')\n"
            "assert cfg.providers['huggingface'].default_model == 'meta-llama/Llama-3.3-70B-Instruct'\n"
            "from bifang.provider import ProviderManager\n"
            "manager = ProviderManager(cfg)\n"
            "assert manager.registry.get('zai') is not None\n"
            "assert manager.registry.get('huggingface') is not None\n"
            "split = manager._split_model_spec(None, 'zai::glm-5.3', cfg.default_provider)\n"
            "assert split == ('zai', 'glm-5.3'), split",
        ],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
