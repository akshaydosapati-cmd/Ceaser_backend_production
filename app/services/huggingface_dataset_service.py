from __future__ import annotations

from typing import Any

import httpx

from app.core.config.settings import settings


class HuggingFaceDatasetService:
    """Read bounded evidence from explicitly configured Hugging Face datasets."""

    endpoint = "https://datasets-server.huggingface.co/search"

    def search(self, query: str) -> dict[str, Any]:
        if not settings.huggingface_datasets_enabled or not settings.huggingface_datasets:
            return {"evidence": "", "rows": [], "errors": []}
        headers = {"Authorization": f"Bearer {settings.huggingface_api_key}"} if settings.huggingface_api_key else {}
        rows: list[dict[str, Any]] = []
        errors: list[dict[str, str]] = []
        timeout = httpx.Timeout(settings.huggingface_dataset_timeout_seconds)
        with httpx.Client(timeout=timeout) as client:
            for source in settings.huggingface_datasets:
                try:
                    response = client.get(
                        self.endpoint,
                        headers=headers,
                        params={**source, "query": query[:300], "length": max(1, min(settings.huggingface_dataset_max_rows, 10))},
                    )
                    if response.status_code >= 400:
                        errors.append({"dataset": source["dataset"], "category": f"http_{response.status_code}"})
                        continue
                    for item in response.json().get("rows", []):
                        row = item.get("row") if isinstance(item, dict) else None
                        if isinstance(row, dict):
                            rows.append({"dataset": source["dataset"], "row": row})
                except (httpx.HTTPError, ValueError, TypeError):
                    errors.append({"dataset": source["dataset"], "category": "unavailable"})
        evidence = "\n\n".join(
            f"Hugging Face dataset {item['dataset']}: {self._flatten(item['row'])}" for item in rows
        )[:6000]
        return {"evidence": evidence, "rows": rows, "errors": errors}

    @classmethod
    def _flatten(cls, value: Any) -> str:
        if isinstance(value, dict):
            return "; ".join(f"{key}: {cls._flatten(item)}" for key, item in value.items())[:1500]
        if isinstance(value, list):
            return ", ".join(cls._flatten(item) for item in value[:10])[:1500]
        return str(value)[:1000]
