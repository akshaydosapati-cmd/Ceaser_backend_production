from __future__ import annotations

from pathlib import Path

from app.services.documents.docx_reader import DOCXReader
from app.services.documents.ocr_service import OCRService
from app.services.documents.pdf_reader import PDFReader
from app.services.documents.pptx_reader import PPTXReader
from app.services.documents.schemas import ExtractedDocument
from app.services.documents.xlsx_reader import XLSXReader


class TextExtractor:
    def extract(self, path: Path, file_type: str) -> ExtractedDocument:
        suffix = path.suffix.lower().lstrip(".")
        kind = file_type.lower() or suffix
        if kind == "pdf" or suffix == "pdf":
            extracted = PDFReader().read(path)
            if not extracted.content.strip():
                extracted.content = OCRService().extract_pdf_text(path)
                extracted.metadata["ocr_required"] = True
                extracted.metadata["ocr"] = True
            return extracted
        if kind in {"docx", "document"} or suffix == "docx":
            return DOCXReader().read(path)
        if kind in {"pptx", "presentation"} or suffix == "pptx":
            return PPTXReader().read(path)
        if kind in {"xlsx", "spreadsheet"} or suffix == "xlsx":
            return XLSXReader().read(path)
        if kind in {"png", "jpg", "jpeg", "image"} or suffix in {"png", "jpg", "jpeg"}:
            content = OCRService().extract_image_text(path)
            if not content.strip():
                content = (
                    f"Image attachment: {path.name}.\n"
                    "No readable text was detected through OCR. Treat this as a visual image attachment. "
                    "If the user asks for captions, Instagram copy, social media ideas, descriptions, or creative text, "
                    "generate polished options using the user's request, file name, and available conversation context. "
                    "Do not respond as if OCR is the final task."
                )
            return ExtractedDocument(title=path.stem, pages=1, content=content, metadata={"reader": "tesseract", "ocr": True, "image": True})
        content = path.read_text(encoding="utf-8", errors="ignore")
        return ExtractedDocument(title=path.stem, pages=1, content=content, metadata={"reader": "text"})
