import asyncio
from types import SimpleNamespace

from bifang import cli
from bifang.config import Config


def test_model_listing_preserves_catalog_without_brand_name_filters(monkeypatch, capsys):
    class Provider:
        async def list_models(self, provider):
            assert provider == "nebius"
            return ["Qwen/fixture", "MiniMax/fixture", "nvidia/fixture"]

        async def close(self):
            pass

    monkeypatch.setattr(cli.Config, "load", lambda: Config())
    monkeypatch.setattr(cli, "ProviderManager", lambda config: Provider())
    asyncio.run(cli.amain(SimpleNamespace(cmd="models", provider="nebius")))
    assert capsys.readouterr().out.splitlines() == ["Qwen/fixture", "MiniMax/fixture", "nvidia/fixture"]
