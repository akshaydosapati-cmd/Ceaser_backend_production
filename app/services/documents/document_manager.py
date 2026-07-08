from __future__ import annotations

from pathlib import Path

from app.services.documents.schemas import ExtractedDocument
from app.services.documents.text_extractor import TextExtractor


class DocumentManager:
    def extract(self, path: Path, file_type: str) -> ExtractedDocument:
        return TextExtractor().extract(path, file_type)

    def build_prompt(self, *, action: str, file_name: str, content: str, language: str | None = None, question: str | None = None) -> str:
        action_labels = {
            "summarize": "Summarize this document.",
            "explain": "Explain this document clearly.",
            "simple": "Explain this document in simple beginner-friendly language.",
            "notes": "Create structured study notes from this document.",
            "mcqs": "Create multiple-choice questions with answers from this document.",
            "flashcards": "Create flashcards with questions and answers from this document.",
            "actions": "Extract action items, decisions, risks, and next steps from this document.",
        }
        target_language = f" Respond in {language}." if language else ""
        instruction = question or action_labels.get(action, "Analyze this document")
        is_image_context = "Image attachment:" in content or file_name.lower().endswith((".png", ".jpg", ".jpeg"))
        image_instruction = ""
        if is_image_context:
            image_instruction = (
                "\n\nThis file is an image attachment. If the user asks for captions, Instagram captions, social posts, "
                "creative copy, descriptions, or ideas, provide direct polished options. Do not answer with OCR status. "
                "If no visual details are available, be honest and create flexible caption options based on the user's prompt and filename."
            )
        return (
            f"{instruction}{target_language}{image_instruction}\n\n"
            f"Document: {file_name}\n\n"
            "Use only the document content below unless you clearly label an inference.\n\n"
            f"{content[:24000]}"
        )
