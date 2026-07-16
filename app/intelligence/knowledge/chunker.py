from __future__ import annotations


class TextChunker:
    def __init__(self, *, max_chars: int = 1400, overlap: int = 180) -> None:
        self.max_chars = max_chars
        self.overlap = overlap

    def chunk(self, text: str) -> list[str]:
        clean = "\n".join(line.strip() for line in text.splitlines() if line.strip())
        if not clean:
            return []
        chunks: list[str] = []
        start = 0
        while start < len(clean):
            end = min(start + self.max_chars, len(clean))
            window = clean[start:end]
            split_at = max(window.rfind("\n"), window.rfind(". "), window.rfind(" "))
            if end < len(clean) and split_at > self.max_chars // 2:
                end = start + split_at + 1
                window = clean[start:end]
            chunks.append(window.strip())
            if end >= len(clean):
                break
            start = max(end - self.overlap, start + 1)
        return chunks


text_chunker = TextChunker()

