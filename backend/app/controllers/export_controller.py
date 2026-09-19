from __future__ import annotations

from pathlib import Path
from urllib.parse import quote

from fastapi import HTTPException
from fastapi.responses import Response
from firebase_admin import storage

from app.core.firebase import db
from app.schemas import ExportRequest
from app.services.export_service import (
    build_chat_message_markdown,
    build_chat_session_markdown,
    build_pdf_markdown,
    build_rag_sources_markdown,
    docx_bytes,
    markdown_bytes,
)


DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
MARKDOWN_MIME = "text/markdown"


def _owned_document(collection: str, document_id: str, uid: str) -> dict:
    snapshot = db.collection(collection).document(document_id).get()
    if not snapshot.exists:
        raise HTTPException(status_code=404, detail="Sumber ekspor tidak ditemukan.")
    data = snapshot.to_dict() or {}
    owner = data.get("user_id") or data.get("created_by")
    if owner != uid:
        raise HTTPException(status_code=403, detail="Akses ditolak.")
    return data


def _library_text(data: dict) -> str:
    text = str(data.get("text") or "").strip()
    if text:
        return text
    text_path = data.get("text_storage_path")
    if not text_path:
        raise HTTPException(status_code=422, detail="Teks hasil ekstraksi PDF tidak tersedia.")
    try:
        return storage.bucket().blob(text_path).download_as_bytes().decode("utf-8").strip()
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Teks PDF tidak dapat dimuat dari penyimpanan.") from exc


def export_document(body: ExportRequest, user: dict) -> Response:
    uid = user["uid"]
    if body.source_type == "library_file":
        data = _owned_document("files", body.source_id, uid)
        extension = str(data.get("extension") or Path(str(data.get("name") or "")).suffix.lstrip(".")).lower()
        if extension != "pdf":
            raise HTTPException(status_code=422, detail="Saat ini hanya dokumen PDF yang dapat dikonversi.")
        markdown, stem = build_pdf_markdown(
            str(data.get("name") or "putusan.pdf"),
            _library_text(data),
            page_count=int(data.get("page_count") or 0),
            ocr_used=bool(data.get("ocr_used")),
            warnings=data.get("extraction_warnings") or [],
        )
        title = Path(str(data.get("name") or "Putusan")).stem
    else:
        data = _owned_document("chats", body.source_id, uid)
        messages = data.get("messages") or []
        title = str(data.get("title") or "Percakapan Legal-Verse")
        try:
            if body.source_type == "chat_message":
                if not body.message_id:
                    raise HTTPException(status_code=422, detail="message_id wajib untuk mengekspor satu jawaban.")
                markdown, stem = build_chat_message_markdown(
                    title,
                    messages,
                    body.message_id,
                )
            elif body.source_type == "rag_sources":
                if not body.message_id:
                    raise HTTPException(status_code=422, detail="message_id wajib untuk mengekspor hasil RAG.")
                markdown, stem = build_rag_sources_markdown(title, messages, body.message_id)
            else:
                markdown, stem = build_chat_session_markdown(title, messages)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    if body.format == "docx":
        content = docx_bytes(title, markdown)
        media_type = DOCX_MIME
        extension = "docx"
    else:
        content = markdown_bytes(markdown)
        media_type = MARKDOWN_MIME
        extension = "md"
    filename = f"{stem}.{extension}"
    ascii_filename = filename.encode("ascii", "ignore").decode() or f"legal-verse-export.{extension}"
    headers = {
        "Content-Disposition": f"attachment; filename=\"{ascii_filename}\"; filename*=UTF-8''{quote(filename)}",
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
    }
    return Response(content=content, media_type=media_type, headers=headers)
