from types import SimpleNamespace
from PIL import Image

import httpx

from app.core.config.settings import settings
from app.services.huggingface_dataset_service import HuggingFaceDatasetService
from app.services.image_generation import HuggingFaceImageGenerationProvider, ImageGenerationRequest


class FakeHttpClient:
    responses = []

    def __init__(self, *args, **kwargs):
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def post(self, url, **kwargs):
        self.calls.append(url)
        return self.responses.pop(0)

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs.get("params")))
        return self.responses.pop(0)


def response(status: int, *, content: bytes = b"", json_data=None, content_type="application/json"):
    request = httpx.Request("GET", "https://example.test")
    if json_data is not None:
        return httpx.Response(status, request=request, json=json_data, headers={"content-type": content_type})
    return httpx.Response(status, request=request, content=content, headers={"content-type": content_type})


def test_image_generation_falls_back_to_second_model(monkeypatch):
    monkeypatch.setattr(settings, "huggingface_api_key", "safe-test-key")
    monkeypatch.setattr(settings, "huggingface_image_model", "primary/model")
    monkeypatch.setattr(settings, "huggingface_image_models_raw", "primary/model,fallback/model")
    class FakeInferenceClient:
        calls = []

        def __init__(self, **_kwargs):
            pass

        def text_to_image(self, _prompt, *, model, **_kwargs):
            self.calls.append(model)
            if model == "primary/model":
                error = RuntimeError("unavailable")
                error.response = SimpleNamespace(status_code=503)
                raise error
            return Image.new("RGB", (8, 8))

    monkeypatch.setattr("app.services.image_generation.InferenceClient", FakeInferenceClient)
    monkeypatch.setattr("app.services.image_generation.StorageService.store", lambda *_args, **_kwargs: "users/u/image.png")
    monkeypatch.setattr("app.services.image_generation.FileService.create", lambda *_args, **_kwargs: SimpleNamespace(id="file-1"))

    result = HuggingFaceImageGenerationProvider(object()).generate("user-1", ImageGenerationRequest(prompt="A launch poster"))[0]

    assert result.status == "completed"
    assert result.model_id == "fallback/model"


def test_dataset_search_is_bounded_and_nonfatal(monkeypatch):
    monkeypatch.setattr(settings, "huggingface_datasets_enabled", True)
    monkeypatch.setattr(settings, "huggingface_datasets_json", '[{"dataset":"example/data","config":"default","split":"train"}]')
    monkeypatch.setattr(settings, "huggingface_dataset_max_rows", 2)
    FakeHttpClient.responses = [response(200, json_data={"rows": [{"row": {"text": "Useful evidence"}}]})]
    monkeypatch.setattr("app.services.huggingface_dataset_service.httpx.Client", FakeHttpClient)
    result = HuggingFaceDatasetService().search("useful")
    assert len(result["rows"]) == 1
    assert "Useful evidence" in result["evidence"]

    FakeHttpClient.responses = [response(429)]
    result = HuggingFaceDatasetService().search("useful")
    assert result["evidence"] == ""
    assert result["errors"] == [{"dataset": "example/data", "category": "http_429"}]
