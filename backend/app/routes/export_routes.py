from fastapi import APIRouter, Depends

from app.controllers.export_controller import export_document
from app.core.auth import require_verified_user
from app.schemas import ExportRequest

router = APIRouter()


@router.post("/api/exports")
async def export_document_route(body: ExportRequest, user: dict = Depends(require_verified_user)):
    return export_document(body, user)
