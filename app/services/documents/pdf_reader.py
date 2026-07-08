from __future__ import annotations

from pathlib import Path

from pypdf import PdfReader

from app.services.documents.schemas import ExtractedDocument


class PDFReader:
    def read(self, path: Path) -> ExtractedDocument:
        reader = PdfReader(str(path))
        chunks = []
        for page in reader.pages:
            chunks.append(page.extract_text() or "")
        content = "\n\n".join(chunk.strip() for chunk in chunks if chunk.strip())
        title = reader.metadata.title if reader.metadata and reader.metadata.title else path.stem
        return ExtractedDocument(title=title, pages=len(reader.pages), content=content, metadata={"reader": "pypdf"})
