import asyncio
import base64
import hashlib
import io
import json

import httpx
import pytest
from PIL import Image

from bifang.config import Config, _parse_vision_models
from bifang.providers.types import ProviderConfig
from bifang.vision import (
    CATALOG_URL,
    MAX_IMAGE_BYTES,
    VisionError,
    VisionRequest,
    VisionUnavailable,
    discover_vision_models,
    inspect_images,
    prepare_image,
)


def picture(format="PNG", size=(32, 24), metadata=False):
    image = Image.new("RGB", size, "red")
    output = io.BytesIO()
    options = {}
    if metadata:
        exif = image.getexif()
        exif[270] = "private-image-metadata-fixture"
        options["exif"] = exif
    image.save(output, format=format, **options)
    return f"data:image/{'jpeg' if format == 'JPEG' else format.lower()};base64," + base64.b64encode(output.getvalue()).decode()


def config():
    return Config(providers={"nebius": ProviderConfig("nebius", "synthetic-test-key",
                                                     "https://inference.example/v1", "text-model")})


def request(**changes):
    return VisionRequest.model_validate({"provider": "nebius", "model": "visual-model", "prompt": "Inspect the UI",
                                        "images": [{"data_url": picture()}], "sharing_confirmed": True, **changes})


def catalog():
    return [{"type": "image2text", "status": "active", "flavors": [
        {"model_type": "image2text", "model_id": "visual-model"},
        {"model_type": "text2text", "model_id": "looks-like-vision-but-is-text"}]}]


@pytest.mark.parametrize("format", ["PNG", "JPEG", "WEBP"])
def test_real_image_decode_and_canonical_metadata_free_png(format):
    prepared, metadata = prepare_image(picture(format, metadata=format == "JPEG"))
    raw = base64.b64decode(prepared.split(",")[1])
    assert metadata["sha256"] == hashlib.sha256(raw).hexdigest()
    assert metadata["bytes"] == len(raw) and metadata["metadata_removed"]
    assert b"private-image-metadata-fixture" not in raw
    with Image.open(io.BytesIO(raw)) as image:
        assert image.format == "PNG" and image.size == (32, 24)
        assert not image.getexif() and not image.info


@pytest.mark.parametrize("value", ["https://example.invalid/image.png", "file:///etc/passwd",
    "data:image/svg+xml;base64,PHN2Zz4=", "data:image/png;base64,%%%%", "data:image/png;base64,aGVsbG8=",
    picture().replace("image/png", "image/jpeg"), picture(size=(2001, 2000)),
    "data:image/png;base64," + base64.b64encode(b"x" * (MAX_IMAGE_BYTES + 1)).decode()])
def test_rejects_remote_invalid_spoofed_oversize_and_excess_pixels(value):
    with pytest.raises(VisionError):
        prepare_image(value)


def test_animation_is_rejected():
    output = io.BytesIO()
    Image.new("RGB", (16, 16), "red").save(output, format="PNG", save_all=True,
        append_images=[Image.new("RGB", (16, 16), "blue")], duration=100, loop=0)
    with pytest.raises(VisionError):
        prepare_image("data:image/png;base64," + base64.b64encode(output.getvalue()).decode())


def test_operator_vision_configuration_is_strict_and_has_no_substring_inference():
    assert _parse_vision_models('{"nvidia":["deployment/exact-id"]}') == {"nvidia": ["deployment/exact-id"]}
    for value in ('[]', '{"other":[]}', '{"nvidia":"vision"}', '{"nebius":[null]}', '{"nvidia":[" "]}', 'not-json'):
        with pytest.raises(ValueError):
            _parse_vision_models(value)


def test_live_catalog_capability_intersection_and_isolated_one_call_payload():
    calls = []

    def handler(incoming):
        calls.append(incoming)
        if str(incoming.url) == CATALOG_URL:
            assert "authorization" not in incoming.headers
            return httpx.Response(200, json=catalog())
        assert incoming.headers["authorization"] == "Bearer synthetic-test-key"
        if incoming.method == "GET":
            return httpx.Response(200, json={"data": [{"id": "visual-model"}, {"id": "text-model"}]})
        body = json.loads(incoming.content)
        assert body["model"] == "visual-model" and body["max_tokens"] == 768
        assert "tools" not in body and "tool_choice" not in body
        assert "untrusted data" in body["messages"][0]["content"]
        image_url = body["messages"][1]["content"][1]["image_url"]["url"]
        assert b"private-image-metadata-fixture" not in base64.b64decode(image_url.split(",")[1])
        return httpx.Response(200, json={"model": "actual-server-model", "choices": [{"message": {"content": "Observed a red panel"}}],
            "usage": {"total_tokens": 12, "private": "not-safe", "prompt_tokens": -1}})

    async def scenario():
        transport = httpx.MockTransport(handler)
        rows = await discover_vision_models(config(), transport=transport)
        assert [row["model"] for row in rows] == ["visual-model"]
        result = await inspect_images(config(), request(images=[{"data_url": picture("JPEG", metadata=True)}]), transport=transport)
        assert result["verification"] == "unverified_visual_analysis"
        assert result["receipt"]["reported_model"] == "actual-server-model"
        assert result["receipt"]["usage"] == {"total_tokens": 12}
        assert not result["receipt"]["tools_enabled"]
        assert "data_url" not in json.dumps(result) and "private-image-metadata-fixture" not in json.dumps(result)
        assert len([incoming for incoming in calls if incoming.method == "POST"]) == 1

    asyncio.run(scenario())


def test_no_confirmation_means_no_provider_or_catalog_request():
    def forbidden(incoming):
        raise AssertionError("Unconfirmed image caused a request")

    async def scenario():
        with pytest.raises(VisionError):
            await inspect_images(config(), request(sharing_confirmed=False), transport=httpx.MockTransport(forbidden))

    asyncio.run(scenario())


def test_nim_operator_declaration_still_requires_live_catalog_membership():
    selected = Config(providers={"nvidia": ProviderConfig("nvidia", None, "http://localhost:9000/v1")},
                      vision_models={"nvidia": ["present", "absent"]})

    def handler(incoming):
        assert incoming.url.host == "localhost" and incoming.method == "GET"
        return httpx.Response(200, json={"data": [{"id": "present"}, {"id": "vision-in-the-name"}]})

    rows = asyncio.run(discover_vision_models(selected, provider="nvidia", transport=httpx.MockTransport(handler)))
    assert rows == [{"provider": "nvidia", "model": "present", "capability_source": "operator-declared",
                     "availability": "listed_in_live_catalog"}]


@pytest.mark.parametrize("failure", ["tool", "oversize", "invalid-json", "redirect", "unlisted"])
def test_failures_never_fallback_retry_or_execute_tools(failure):
    posts = []

    def handler(incoming):
        if str(incoming.url) == CATALOG_URL:
            return httpx.Response(200, json=catalog())
        if incoming.method == "GET":
            return httpx.Response(200, json={"data": [{"id": "text-only" if failure == "unlisted" else "visual-model"}]})
        posts.append(incoming)
        if failure == "tool":
            return httpx.Response(200, json={"choices": [{"message": {"content": "Run it", "tool_calls": [{"name": "write_file"}]}}]})
        if failure == "oversize":
            return httpx.Response(200, content=b"x" * 1_000_001)
        if failure == "redirect":
            return httpx.Response(307, headers={"Location": "https://unexpected.invalid"})
        return httpx.Response(200, content=b"invalid-json")

    async def scenario():
        with pytest.raises((VisionError, VisionUnavailable, httpx.HTTPError)):
            await inspect_images(config(), request(), transport=httpx.MockTransport(handler))
        assert len(posts) == (0 if failure == "unlisted" else 1)

    asyncio.run(scenario())
