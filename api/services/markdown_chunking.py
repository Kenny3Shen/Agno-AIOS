from __future__ import annotations

import re

from agno.knowledge.chunking.recursive import RecursiveChunking
from agno.knowledge.chunking.strategy import ChunkingStrategy
from agno.knowledge.document import Document


_ANY_HEADING = re.compile(r"#{1,6}\s+.+")


class MarkdownHeadingChunking(ChunkingStrategy):
    """Heading-aware Markdown chunking without the optional unstructured package."""

    def __init__(
        self,
        *,
        chunk_size: int = 5000,
        overlap: int = 0,
        split_on_headings: bool | int = True,
    ) -> None:
        if chunk_size <= 0:
            raise ValueError("chunk_size must be greater than zero")
        if overlap < 0 or overlap >= chunk_size:
            raise ValueError("overlap must be non-negative and smaller than chunk_size")
        if isinstance(split_on_headings, int) and not isinstance(split_on_headings, bool):
            if not 1 <= split_on_headings <= 6:
                raise ValueError("split_on_headings must be between 1 and 6")
        self.chunk_size = chunk_size
        self.overlap = overlap
        self.split_on_headings = split_on_headings

    def _heading_pattern(self) -> re.Pattern[str]:
        if isinstance(self.split_on_headings, int) and not isinstance(
            self.split_on_headings, bool
        ):
            return re.compile(
                rf"^#{{1,{self.split_on_headings}}}\s+.+$", re.MULTILINE
            )
        return re.compile(r"^#{1,6}\s+.+$", re.MULTILINE)

    def _heading_sections(self, content: str) -> list[str]:
        matches = list(self._heading_pattern().finditer(content))
        if not matches:
            return [content]

        sections: list[str] = []
        leading_content = content[: matches[0].start()].strip()
        if leading_content:
            sections.append(leading_content)
        for index, match in enumerate(matches):
            next_start = matches[index + 1].start() if index + 1 < len(matches) else len(content)
            section = content[match.start() : next_start].strip()
            if section:
                sections.append(section)
        return sections

    def _split_large_section(self, section: str) -> list[str]:
        if len(section) <= self.chunk_size:
            return [section]

        lines = section.splitlines()
        heading = lines[0].strip() if lines and _ANY_HEADING.fullmatch(lines[0].strip()) else ""
        body = "\n".join(lines[1:] if heading else lines).strip()
        if not body:
            return [section]

        heading_size = len(heading) + 2 if heading else 0
        body_chunk_size = max(1, self.chunk_size - heading_size)
        body_overlap = min(self.overlap, max(0, body_chunk_size - 1))
        body_chunks = RecursiveChunking(
            chunk_size=body_chunk_size,
            overlap=body_overlap,
        ).chunk(Document(content=body))
        return [
            f"{heading}\n\n{chunk.content}".strip() if heading else chunk.content
            for chunk in body_chunks
            if chunk.content.strip()
        ]

    def _document_chunk(self, document: Document, number: int, content: str) -> Document:
        meta_data = document.meta_data.copy()
        meta_data["chunk"] = number
        meta_data["chunk_size"] = len(content)
        return Document(
            id=self._generate_chunk_id(document, number, content),
            name=document.name,
            meta_data=meta_data,
            content=content,
        )

    def _overlap_chunks(self, document: Document, chunks: list[Document]) -> list[Document]:
        if self.overlap <= 0:
            return chunks

        overlapped = [chunks[0]]
        for previous, current in zip(chunks, chunks[1:], strict=False):
            content = f"{previous.content[-self.overlap:]}{current.content}"
            chunk_number = int(current.meta_data["chunk"])
            overlapped.append(self._document_chunk(document, chunk_number, content))
        return overlapped

    def chunk(self, document: Document) -> list[Document]:
        if not document.content:
            return [document]
        if not self.split_on_headings:
            return RecursiveChunking(
                chunk_size=self.chunk_size,
                overlap=self.overlap,
            ).chunk(document)

        chunks: list[Document] = []
        chunk_number = 1
        for section in self._heading_sections(document.content):
            for content in self._split_large_section(section):
                chunks.append(self._document_chunk(document, chunk_number, content))
                chunk_number += 1
        return self._overlap_chunks(document, chunks)
