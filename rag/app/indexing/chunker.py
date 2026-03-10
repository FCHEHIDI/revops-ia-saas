import re
from dataclasses import dataclass


@dataclass
class Chunk:
    text: str
    chunk_index: int
    start_char: int
    end_char: int
    page_number: int | None = None


class TextChunker:
    """Sliding-window text chunker with character-level overlap.

    Token count is approximated as ``len(text) / 4`` (4 chars ≈ 1 BPE token
    for mixed-language text).  The splitter tries to break at sentence or
    paragraph boundaries before falling back to raw character splits.
    """

    # Roughly 4 chars per token — works well for both English and French
    CHARS_PER_TOKEN: int = 4

    def __init__(self, chunk_size: int = 512, overlap: int = 50) -> None:
        if overlap >= chunk_size:
            raise ValueError("overlap must be less than chunk_size")
        self.chunk_size = chunk_size
        self.overlap = overlap
        self._char_size = chunk_size * self.CHARS_PER_TOKEN
        self._char_overlap = overlap * self.CHARS_PER_TOKEN

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def split(self, text: str, document_type: str = "other") -> list[Chunk]:
        """Split *text* into overlapping chunks.

        The strategy adapts slightly per document type:
        - ``playbook`` / ``report``: paragraph-aware splitting
        - everything else: sentence-aware splitting
        """
        text = self._normalize(text)
        if not text:
            return []

        if len(text) <= self._char_size:
            return [Chunk(text=text, chunk_index=0, start_char=0, end_char=len(text))]

        if document_type in ("playbook", "report"):
            segments = self._split_by_paragraphs(text)
        else:
            segments = self._split_by_sentences(text)

        return self._build_chunks(text, segments)

    # ------------------------------------------------------------------
    # Splitting helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize(text: str) -> str:
        text = re.sub(r"\r\n", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    @staticmethod
    def _split_by_paragraphs(text: str) -> list[tuple[int, int]]:
        """Return (start, end) char positions for each non-empty paragraph."""
        segments: list[tuple[int, int]] = []
        pos = 0
        for para in re.split(r"\n\n+", text):
            start = text.find(para, pos)
            end = start + len(para)
            if para.strip():
                segments.append((start, end))
            pos = end
        return segments

    @staticmethod
    def _split_by_sentences(text: str) -> list[tuple[int, int]]:
        """Return (start, end) char positions for each sentence."""
        segments: list[tuple[int, int]] = []
        # Match sentence-ending punctuation followed by whitespace / EOL
        pattern = re.compile(r"(?<=[.!?…])\s+")
        prev = 0
        for m in pattern.finditer(text):
            end = m.start() + 1
            if text[prev:end].strip():
                segments.append((prev, end))
            prev = m.end()
        if prev < len(text) and text[prev:].strip():
            segments.append((prev, len(text)))
        return segments if segments else [(0, len(text))]

    def _build_chunks(
        self, text: str, segments: list[tuple[int, int]]
    ) -> list[Chunk]:
        chunks: list[Chunk] = []
        current_start: int = segments[0][0]
        current_end: int = segments[0][0]
        idx = 0

        for seg_start, seg_end in segments:
            current_end = seg_end
            window_len = current_end - current_start

            if window_len >= self._char_size:
                chunk_text = text[current_start:current_end].strip()
                if chunk_text:
                    chunks.append(
                        Chunk(
                            text=chunk_text,
                            chunk_index=idx,
                            start_char=current_start,
                            end_char=current_end,
                        )
                    )
                    idx += 1
                # Slide forward with overlap
                overlap_start = max(current_start, current_end - self._char_overlap)
                current_start = overlap_start

        # Flush remainder
        if current_end > current_start:
            tail = text[current_start:current_end].strip()
            if tail:
                chunks.append(
                    Chunk(
                        text=tail,
                        chunk_index=idx,
                        start_char=current_start,
                        end_char=current_end,
                    )
                )

        return chunks or [
            Chunk(text=text, chunk_index=0, start_char=0, end_char=len(text))
        ]
