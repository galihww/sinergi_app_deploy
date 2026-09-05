from __future__ import annotations

import logging
import re
import uuid

from fastapi import HTTPException, Request
from firebase_admin import storage
from google.cloud.firestore_v1.base_vector_query import DistanceMeasure

from app.core.firebase import db
from app.embeddings import EMBEDDING_MODEL_ID
from app.rag import SECTION_LABELS, retrieve, sectionize
from app.rag.vector_store import cosine_score, query_vector
from app.schemas import RagIngestRequest, RagIngestResponse, RagQueryRequest, RagQueryResponse, RagHit, RagSection, PdfExtractResponse
from app.services.content_service import estimate_tokens, extract_pdf_document, extract_pdf_text

logger = logging.getLogger(__name__)


def _lexical_score(question: str, text: str) -> float:
    query_terms = {term for term in re.findall(r"[a-z0-9]+", question.lower()) if len(term) > 2}
    if not query_terms:
        return 0.0
    text_terms = set(re.findall(r"[a-z0-9]+", text.lower()))
    return len(query_terms & text_terms) / len(query_terms)


def _global_index(snapshot_id: str, document_id: str, data: dict) -> int | None:
    value = data.get("global_index")
    if isinstance(value, int):
        return value
    suffix = snapshot_id.removeprefix(f"{document_id}-").split("-", 1)[0]
    return int(suffix) if suffix.isdigit() else None


def pdf_extract(body: RagIngestRequest) -> PdfExtractResponse:
    extracted = extract_pdf_document(body.data)
    if not extracted.text:
        logger.warning("PDF extraction returned no text for %s", body.name)
        raise HTTPException(status_code=422, detail=f"PDF '{body.name}' tidak dapat dibaca (tidak ada teks ter-extract).")
    return PdfExtractResponse(
        name=body.name,
        text=extracted.text,
        char_count=len(extracted.text),
        token_count=estimate_tokens(extracted.text),
        page_count=extracted.page_count,
        ocr_used=extracted.ocr_used,
        warnings=extracted.warnings,
    )


def rag_ingest(body: RagIngestRequest, request: Request) -> RagIngestResponse:
    text = extract_pdf_text(body.data, max_chars=None, collapse=False)
    if not text:
        logger.warning("RAG PDF extraction returned no text for %s", body.name)
        raise HTTPException(status_code=422, detail=f"PDF '{body.name}' tidak dapat dibaca (tidak ada teks ter-extract).")
    doc_id = str(uuid.uuid4())
    request.app.state.rag_docs[doc_id] = {"name": body.name, "text": text}
    return RagIngestResponse(id=doc_id, name=body.name, char_count=len(text), sections=[RagSection(key=key, label=SECTION_LABELS.get(key, key), text=span) for key, span in sectionize(text).items() if span and span.strip()])


def _vector_hits(question: str, document_ids: list[str], user_id: str, top_k: int) -> list[RagHit]:
    vector = query_vector(question)
    candidates: list[dict] = []
    for document_id in document_ids:
        query = (
            db.collection("document_chunks")
            .where("user_id", "==", user_id)
            .where("file_id", "==", document_id)
            .find_nearest(
                vector_field="embedding",
                query_vector=vector,
                distance_measure=DistanceMeasure.COSINE,
                limit=min(30, max(top_k * 3, top_k)),
                distance_result_field="vector_distance",
            )
        )
        for snapshot in query.stream():
            data = snapshot.to_dict()
            vector_score = cosine_score(data.get("vector_distance"))
            lexical_score = _lexical_score(question, data.get("text", ""))
            score = 0.8 * vector_score + 0.2 * lexical_score
            candidates.append(
                {
                    "document_id": document_id,
                    "global_index": _global_index(snapshot.id, document_id, data),
                    "data": data,
                    "hit": RagHit(
                        key=data.get("section_key", "document"),
                        label=data.get("section_label", "Dokumen"),
                        text=data.get("text", ""),
                        score=score,
                        reason=f"hybrid:{EMBEDDING_MODEL_ID}:vector={vector_score:.2f}:lexical={lexical_score:.2f}",
                    ),
                }
            )
    candidates.sort(key=lambda candidate: candidate["hit"].score, reverse=True)

    results: list[RagHit] = []
    seen: set[tuple[str, int | None]] = set()
    for candidate in candidates:
        identity = (candidate["document_id"], candidate["global_index"])
        if identity not in seen:
            results.append(candidate["hit"])
            seen.add(identity)
        if len(results) >= top_k:
            break

        global_index = candidate["global_index"]
        if global_index is None:
            continue
        for neighbor_index in (global_index - 1, global_index + 1):
            if neighbor_index < 0 or len(results) >= top_k:
                continue
            neighbor_identity = (candidate["document_id"], neighbor_index)
            if neighbor_identity in seen:
                continue
            snapshot = db.collection("document_chunks").document(
                f"{candidate['document_id']}-{neighbor_index}"
            ).get()
            if not snapshot.exists:
                continue
            data = snapshot.to_dict()
            if data.get("user_id") != user_id or data.get("file_id") != candidate["document_id"]:
                continue
            results.append(
                RagHit(
                    key=data.get("section_key", "document"),
                    label=data.get("section_label", "Dokumen"),
                    text=data.get("text", ""),
                    score=max(0.0, candidate["hit"].score - 0.05),
                    reason=f"neighbor-of:{candidate['global_index']}",
                )
            )
            seen.add(neighbor_identity)
    return results[:top_k]


def _stored_texts(document_ids: list[str], user_id: str) -> list[str]:
    texts: list[str] = []
    for document_id in document_ids:
        snapshot = db.collection("files").document(document_id).get()
        if snapshot.exists:
            data = snapshot.to_dict()
            if data.get("user_id") == user_id and data.get("text"):
                texts.append(data["text"])
            elif data.get("user_id") == user_id and data.get("text_storage_path"):
                try:
                    text = storage.bucket().blob(data["text_storage_path"]).download_as_text()
                except Exception:
                    text = ""
                if text:
                    texts.append(text)
    return texts


def rag_query(body: RagQueryRequest, request: Request, user: dict | None = None) -> RagQueryResponse:
    if user and body.document_ids:
        try:
            vector_hits = _vector_hits(body.question, body.document_ids, user["uid"], body.top_k)
            if vector_hits:
                return RagQueryResponse(question=body.question, hits=vector_hits)
        except Exception as exc:
            # Missing vector indexes, model downloads, or old documents should
            # not make retrieval unusable; section-aware lexical retrieval is
            # deterministic and remains the fallback.
            logger.warning("Vector retrieval failed; using lexical fallback: %s", exc)

    sources = [body.text] if body.text else []
    for doc_id in body.document_ids:
        doc = request.app.state.rag_docs.get(doc_id)
        if doc is not None:
            sources.append(doc.get("text", ""))
        elif not user:
            raise HTTPException(status_code=404, detail=f"Unknown RAG document id '{doc_id}'.")
    if user and body.document_ids:
        sources.extend(_stored_texts(body.document_ids, user["uid"]))
    if body.document_ids and not sources:
        raise HTTPException(status_code=404, detail="No accessible document was found for the supplied ids.")
    if not sources:
        raise HTTPException(status_code=422, detail="Provide at least one document (text or document_ids).")
    hits = retrieve("\n\n".join(sources), body.question, top_k=body.top_k)
    return RagQueryResponse(question=body.question, hits=[RagHit(key=h.key, label=h.label, text=h.text, score=h.score, reason=h.reason) for h in hits])
