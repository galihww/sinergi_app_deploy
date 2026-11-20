from typing import Literal

from fastapi import APIRouter, Depends, Query, Request

from app.core.auth import require_admin
from app.controllers.admin_controller import admin_list_users, admin_set_verified
from app.services.zero_gpu_quota_service import get_zero_gpu_quota

router = APIRouter(prefix="/api/admin", dependencies=[Depends(require_admin)])


@router.get("/zero-gpu/quota")
async def admin_zero_gpu_quota_route(request: Request) -> dict:
    return await get_zero_gpu_quota(request.app.state.http)


@router.get("/users")
def admin_list_users_route(
    status: Literal["pending", "approved", "all"] = Query("pending"),
) -> list[dict]:
    return admin_list_users(status)


@router.post("/users/{uid}/approve")
def admin_approve_route(uid: str) -> dict:
    return admin_set_verified(uid, True)


@router.post("/users/{uid}/revoke")
def admin_revoke_route(uid: str) -> dict:
    return admin_set_verified(uid, False)
