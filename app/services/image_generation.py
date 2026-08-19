from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Literal

import httpx
from pydantic import BaseModel, Field

from app.core.config.settings import settings
from app.services.file_service import FileService
from app.services.storage_service import StorageService


class ImageGenerationRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=4000)
    model_id: str | None = None
    aspect_ratio: str = "1:1"
    size: str = "1024x1024"
    count: int = Field(default=1, ge=1, le=4)
    style_hint: str | None = None
    negative_prompt: str | None = None
    output_format: Literal["png", "jpeg", "webp"] = "png"


class ImageGenerationResult(BaseModel):
    asset_id: str | None = None
    reference: str | None = None
    mime_type: str | None = None
    width: int | None = None
    height: int | None = None
    provider: str | None = None
    status: Literal["completed", "failed", "image_generation_unavailable"]
    error_code: str | None = None


class ImageGenerationProvider(ABC):
    @abstractmethod
    def available(self) -> bool: ...

    @abstractmethod
    def generate(self, user_id: str, request: ImageGenerationRequest) -> list[ImageGenerationResult]: ...


@dataclass(slots=True)
class HuggingFaceImageGenerationProvider(ImageGenerationProvider):
    db: object

    def available(self) -> bool:
        return bool(settings.huggingface_api_key)

    def generate(self, user_id: str, request: ImageGenerationRequest) -> list[ImageGenerationResult]:
        if not self.available():
            return [ImageGenerationResult(status="image_generation_unavailable", error_code="image_generation_unavailable")]

        model_id = request.model_id or settings.huggingface_image_model
        width, height = self._dimensions(request.size, request.aspect_ratio)
        payload = {
            "inputs": self._build_prompt(request),
            "parameters": {
                "width": width,
                "height": height,
                "guidance_scale": 4.5,
                "num_inference_steps": 28,
            },
        }
        if request.negative_prompt:
            payload["parameters"]["negative_prompt"] = request.negative_prompt

        endpoint = f"https://router.huggingface.co/hf-inference/models/{model_id}"
        headers = {
            "Authorization": f"Bearer {settings.huggingface_api_key}",
            "Content-Type": "application/json",
            "Accept": "image/*,application/octet-stream",
        }
        timeout = httpx.Timeout(connect=settings.llm_connect_timeout_seconds, read=settings.llm_total_timeout_seconds, write=settings.llm_total_timeout_seconds, pool=settings.llm_total_timeout_seconds)

        try:
            with httpx.Client(timeout=timeout) as client:
                response = client.post(endpoint, headers=headers, json=payload)
                if response.status_code >= 400:
                    return [ImageGenerationResult(status="failed", error_code=f"http_{response.status_code}", provider="huggingface")]
                content_type = (response.headers.get("content-type") or "image/png").split(";", 1)[0].strip() or "image/png"
                ext = self._extension(content_type, request.output_format)
                filename = f"ceaser-image-{user_id[:8]}-{abs(hash((request.prompt, model_id))) & 0xFFFFFFFF:x}.{ext}"
                storage_path = StorageService().store(user_id=user_id, filename=filename, content=response.content, content_type=content_type)
                file = FileService(self.db).create(user_id=user_id, project_id=None, name=filename, file_type=ext, storage_path=storage_path)
                return [
                    ImageGenerationResult(
                        asset_id=file.id,
                        reference=storage_path,
                        mime_type=content_type,
                        width=width,
                        height=height,
                        provider="huggingface",
                        status="completed",
                    )
                ]
        except httpx.HTTPError:
            return [ImageGenerationResult(status="failed", error_code="provider_error", provider="huggingface")]

    @staticmethod
    def _build_prompt(request: ImageGenerationRequest) -> str:
        parts = [request.prompt.strip()]
        if request.style_hint:
            parts.append(f"Style: {request.style_hint.strip()}")
        return "\n".join(part for part in parts if part)

    @staticmethod
    def _dimensions(size: str, aspect_ratio: str) -> tuple[int, int]:
        parsed_width, parsed_height = 1024, 1024
        if "x" in size:
            try:
                width_str, height_str = size.lower().split("x", 1)
                parsed_width, parsed_height = int(width_str), int(height_str)
            except ValueError:
                pass
        if aspect_ratio == "16:9":
            return parsed_width if parsed_width >= parsed_height else 1344, max(768, int((parsed_width or 1024) * 9 / 16))
        if aspect_ratio == "9:16":
            return max(768, int((parsed_height or 1024) * 9 / 16)), parsed_height if parsed_height >= parsed_width else 1344
        return parsed_width, parsed_height

    @staticmethod
    def _extension(content_type: str, output_format: Literal["png", "jpeg", "webp"]) -> str:
        if "jpeg" in content_type or output_format == "jpeg":
            return "jpg"
        if "webp" in content_type or output_format == "webp":
            return "webp"
        return "png"


class ImageGenerationService:
    def __init__(self, provider: ImageGenerationProvider | None = None):
        self.provider = provider

    def generate(self, user_id: str, request: ImageGenerationRequest):
        if not self.provider or not self.provider.available():
            return [ImageGenerationResult(status="image_generation_unavailable", error_code="image_generation_unavailable")]
        return self.provider.generate(user_id, request)
