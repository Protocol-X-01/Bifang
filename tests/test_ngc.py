import asyncio

from bifang.ngc import NGCClient


def test_list_models_maps_ngc_records_without_network():
    async def run_test():
        client = NGCClient("test-key")

        async def fake_request(method, endpoint, **kwargs):
            assert method == "GET"
            assert endpoint == "/models"
            return {
                "models": [
                    {
                        "name": "nemotron",
                        "orgName": "nvidia",
                        "teamName": "nim",
                        "latestVersionIdStr": "1.0",
                    }
                ]
            }

        client._request = fake_request
        try:
            models = await client.list_models()
        finally:
            await client.close()

        assert len(models) == 1
        assert (models[0].org_name, models[0].team_name, models[0].name) == (
            "nvidia",
            "nim",
            "nemotron",
        )

    asyncio.run(run_test())
