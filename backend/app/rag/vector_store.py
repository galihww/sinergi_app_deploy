from __future__ import annotations

import re
from dataclasses import dataclass

from google.cloud.firestore_v1.base_vector_query import DistanceMeasure
from google.cloud.firestore_v1.vector import Vector
from app.embeddings import EMBEDDING_DIMENSION, EMBEDDING_MODEL_ID, embed_documents, embed_query
from app.rag.sections import SECTION_LABELS
from app.rag.sectionizer import sectionize


@dataclass
class DocumentChunk:
    section_key: str
    section_label: str
    text: str
    chunk_index: int


_PAGE_MARKER_RE = re.compile(r"(?m)^\[HALAMAN\s+(\d+)\]\s*$")


def _split_text(text: str, max_chars: int = 1800, overlap: int = 240) -> list[str]:
    paragraphs = [part.strip() for part in text.split("\n\n") if part.strip()]
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs or [text.strip()]:
        if not paragraph:
            continue
        if len(paragraph) <= max_chars and len(current) + len(paragraph) + 2 <= max_chars:
            current = f"{current}\n\n{paragraph}".strip()
            continue
        if current:
            chunks.append(current)
        if len(paragraph) <= max_chars:
            current = paragraph
            continue
        start = 0
        while start < len(paragraph):
            end = min(len(paragraph), start + max_chars)
            if end < len(paragraph):
                boundary = max(paragraph.rfind(". ", start, end), paragraph.rfind("; ", start, end))
                if boundary > start + max_chars // 2:
                    end = boundary + 1
            chunks.append(paragraph[start:end].strip())
            if end >= len(paragraph):
                break
            start = max(0, end - overlap)
        current = ""
    if current:
        chunks.append(current)
    return [chunk for chunk in chunks if chunk]


def make_chunks(text: str) -> list[DocumentChunk]:
    page_markers = list(_PAGE_MARKER_RE.finditer(text))
    if page_markers:
        page_chunks: list[DocumentChunk] = []
        for marker_index, marker in enumerate(page_markers):
            page_number = int(marker.group(1))
            body_start = marker.end()
            body_end = page_markers[marker_index + 1].start() if marker_index + 1 < len(page_markers) else len(text)
            page_text = text[body_start:body_end].strip()
            for chunk_index, chunk in enumerate(_split_text(page_text)):
                page_chunks.append(
                    DocumentChunk(
                        section_key=f"page_{page_number}",
                        section_label=f"Halaman {page_number}",
                        text=f"[HALAMAN {page_number}]\n{chunk}",
                        chunk_index=chunk_index,
                    )
                )
        if page_chunks:
            return page_chunks

    chunks: list[DocumentChunk] = []
    for key, section_text in sectionize(text).items():
        for index, chunk in enumerate(_split_text(section_text)):
            chunks.append(DocumentChunk(key, SECTION_LABELS.get(key, key), chunk, index))
    if not chunks and text.strip():
        chunks = [
            DocumentChunk("document", "Dokumen", chunk, index)
            for index, chunk in enumerate(_split_text(text))
        ]
    return chunks


def chunk_payloads(text: str) -> list[tuple[DocumentChunk, list[float]]]:
    chunks = make_chunks(text)
    vectors: list[list[float]] = []
    for start in range(0, len(chunks), 64):
        vectors.extend(embed_documents([chunk.text for chunk in chunks[start:start + 64]]))
    return list(zip(chunks, vectors))


def query_vector(text: str) -> Vector:
    vector = embed_query(text)
    return Vector(vector)


def cosine_score(distance: float | int | None) -> float:
    if distance is None:
        return 0.0
    return max(0.0, min(1.0, 1.0 - float(distance) / 2.0))


__all__ = [
    "EMBEDDING_DIMENSION",
    "EMBEDDING_MODEL_ID",
    "chunk_payloads",
    "cosine_score",
    "make_chunks",
    "query_vector",
]
