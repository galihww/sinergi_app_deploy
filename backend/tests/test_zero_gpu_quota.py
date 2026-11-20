from __future__ import annotations

import httpx
import pytest
from fastapi import HTTPException

from app.services.zero_gpu_quota_service import ZERO_GPU_QUOTA_URL, get_zero_gpu_quota


@pytest.mark.asyncio
async def test_get_zero_gpu_quota_normalizes_hugging_face_response(monkeypatch) -> None:
    monkeypatch.setenv("GRADIO_HF_TOKEN", "hf_test_token")

    async def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == ZERO_GPU_QUOTA_URL
        assert request.headers["Authorization"] == "Bearer hf_test_token"
        return httpx.Response(
            200,
            json={
                "base": 2400,
                "current": 1200.5,
                "resetsAt": "2026-11-21T10:27:35.925Z",
                "overquotaUsed": 0,
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        quota = await get_zero_gpu_quota(client)

    assert quota["total_gpu_seconds"] == 2400
    assert quota["remaining_gpu_seconds"] == 1200.5
    assert quota["used_gpu_seconds"] == 1199.5
    assert quota["remaining_percent"] == 50.02
    assert quota["resets_at"] == "2026-11-21T10:27:35.925Z"
    assert quota["overquota_used_gpu_seconds"] == 0
    assert quota["checked_at"]


@pytest.mark.asyncio
async def test_get_zero_gpu_quota_requires_backend_token(monkeypatch) -> None:
    monkeypatch.delenv("GRADIO_HF_TOKEN", raising=False)

    async with httpx.AsyncClient() as client:
        with pytest.raises(HTTPException) as exc:
            await get_zero_gpu_quota(client)

    assert exc.value.status_code == 503
    assert "belum dikonfigurasi" in exc.value.detail


@pytest.mark.asyncio
async def test_get_zero_gpu_quota_explains_missing_billing_permission(monkeypatch) -> None:
    monkeypatch.setenv("GRADIO_HF_TOKEN", "hf_test_token")

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(HTTPException) as exc:
            await get_zero_gpu_quota(client)

    assert exc.value.status_code == 503
    assert "Billing" in exc.value.detail
