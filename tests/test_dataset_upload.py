import hashlib

import httpx
import pytest

from bifang.dataset_export import export_dataset
from bifang.dataset_upload import inspect_dataset, upload_file, verify_remote


def fixture(tmp_path, answer="return 1"):
    export_dataset([{"input": "Implement a function", "output": answer, "license": "cc-by-4.0"}],
                   tmp_path / "train", source="synthetic", revision="test", allowed_licenses={"cc-by-4.0"})
    return tmp_path / "train"


def test_upload_is_one_post_then_remote_content_verified(tmp_path):
    directory = fixture(tmp_path)
    expected = inspect_dataset(directory)
    content = (directory / "coding.jsonl").read_bytes()
    filename = f"bifang-ocr-train-{expected['sha256'][:16]}.jsonl"
    paths = []

    def handler(request):
        paths.append((request.method, request.url.path))
        if request.method == "POST":
            assert b'name="purpose"' in request.content and b"fine-tune" in request.content
            assert content in request.content
            return httpx.Response(200, json={"id": "file-fixture", "filename": filename,
                "bytes": len(content), "purpose": "fine-tune"})
        if request.url.path.endswith("/content"):
            return httpx.Response(200, content=content)
        return httpx.Response(200, json={"data": []})

    checkpoints = []
    with httpx.Client(base_url="https://fixture.invalid", transport=httpx.MockTransport(handler)) as client:
        report = upload_file(client, directory, "train", expected, checkpoints.append)
    assert report["remote_content_verified"] and not report["reused"]
    assert paths == [("GET", "/v1/files"), ("POST", "/v1/files"), ("GET", "/v1/files/file-fixture/content")]
    assert len(checkpoints) == 2


def test_existing_matching_file_is_verified_without_post(tmp_path):
    directory = fixture(tmp_path)
    expected = inspect_dataset(directory)
    content = (directory / "coding.jsonl").read_bytes()

    def handler(request):
        assert request.method == "GET"
        if request.url.path.endswith("/content"):
            return httpx.Response(200, content=content)
        return httpx.Response(200, json={"data": [{"id": "file-fixture", "bytes": len(content),
            "filename": f"bifang-ocr-train-{expected['sha256'][:16]}.jsonl", "purpose": "fine-tune"}]})

    with httpx.Client(base_url="https://fixture.invalid", transport=httpx.MockTransport(handler)) as client:
        assert upload_file(client, directory, "train", expected, lambda row: None)["reused"]


def test_changed_content_and_private_values_stop_preflight(tmp_path):
    directory = fixture(tmp_path, "synthetic-private-value")
    with pytest.raises(ValueError, match="Credential screen"):
        inspect_dataset(directory, ("synthetic-private-value",))
    (directory / "coding.jsonl").write_text('{"messages": []}\n')
    with pytest.raises(ValueError):
        inspect_dataset(directory)


def test_remote_content_mismatch_is_not_success(tmp_path):
    directory = fixture(tmp_path)
    expected = inspect_dataset(directory)

    def handler(request):
        if request.url.path.endswith("/content"):
            return httpx.Response(200, content=b"wrong")
        return httpx.Response(200, json={"data": [{"id": "file-fixture", "bytes": expected["bytes"],
            "filename": f"bifang-ocr-train-{expected['sha256'][:16]}.jsonl", "purpose": "fine-tune"}]})

    with httpx.Client(base_url="https://fixture.invalid", transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ValueError, match="digest mismatch"):
            upload_file(client, directory, "train", expected, lambda row: None)


def test_upload_timeout_is_not_retried(tmp_path):
    directory = fixture(tmp_path)
    expected = inspect_dataset(directory)
    posts = []

    def handler(request):
        if request.method == "POST":
            posts.append(request)
            raise httpx.ReadTimeout("synthetic timeout")
        return httpx.Response(200, json={"data": []})

    with httpx.Client(base_url="https://fixture.invalid", transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(httpx.ReadTimeout):
            upload_file(client, directory, "train", expected, lambda row: None)
    assert len(posts) == 1
    assert expected["sha256"] == hashlib.sha256((directory / "coding.jsonl").read_bytes()).hexdigest()


def test_presigned_storage_download_never_receives_api_authorization(tmp_path):
    directory = fixture(tmp_path)
    expected = inspect_dataset(directory)
    content = (directory / "coding.jsonl").read_bytes()
    filename = "fixture.jsonl"

    def handler(request):
        if request.url.host == "fixture.invalid":
            assert request.headers["authorization"] == "Bearer synthetic-private-key"
            return httpx.Response(307, headers={
                "Location": "https://storage.eu-west2.nebius.cloud/synthetic?signature=synthetic"})
        assert request.url.host == "storage.eu-west2.nebius.cloud"
        assert "authorization" not in request.headers
        return httpx.Response(200, content=content)

    with httpx.Client(base_url="https://fixture.invalid", headers={"Authorization": "Bearer synthetic-private-key"},
                      transport=httpx.MockTransport(handler)) as client:
        assert verify_remote(client, {"id": "file-test", "filename": filename,
            "purpose": "fine-tune", "bytes": len(content)}, expected, filename)["remote_content_verified"]


def test_unexpected_redirect_host_is_rejected_before_request(tmp_path):
    directory = fixture(tmp_path)
    expected = inspect_dataset(directory)
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(307, headers={"Location": "https://unexpected.invalid/private"})

    with httpx.Client(base_url="https://fixture.invalid", transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ValueError, match="Unsupported storage redirect"):
            verify_remote(client, {"id": "file-test", "filename": "fixture", "purpose": "fine-tune",
                "bytes": expected["bytes"]}, expected, "fixture")
    assert len(calls) == 1
