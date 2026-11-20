from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import HTTPException


ZERO_GPU_QUOTA_URL = "https://huggingface.co/api/spaces/zero-gpu/quota"


async def get_zero_gpu_quota(client: httpx.AsyncClient) -> dict[str, Any]:
    """Return the backend token's ZeroGPU quota without exposing the token."""

    token = os.getenv("GRADIO_HF_TOKEN", "").strip()
    if not token:
        raise HTTPException(status_code=503, detail="Token Hugging Face backend belum dikonfigurasi.")

    try:
        response = await client.get(
            ZERO_GPU_QUOTA_URL,
            headers={"Authorization": f"Bearer {token}"},
            timeout=20,
        )
    except httpx.HTTPError as error:
        raise HTTPException(
            status_code=503,
            detail="Layanan kuota Hugging Face tidak dapat dihubungi.",
        ) from error

    if response.status_code in {401, 403}:
        raise HTTPException(
            status_code=503,
            detail=(
                "Token Hugging Face belum memiliki izin Billing: Read billing usage "
                "and payment method status."
            ),
        )

    try:
        response.raise_for_status()
        payload = response.json()
        total = max(0.0, float(payload["base"]))
        remaining = max(0.0, float(payload["current"]))
        overquota_used = max(0.0, float(payload.get("overquotaUsed") or 0))
    except (httpx.HTTPError, KeyError, TypeError, ValueError) as error:
        raise HTTPException(status_code=503, detail="Respons kuota Hugging Face tidak valid.") from error

    remaining = min(remaining, total) if total else remaining
    used = max(0.0, total - remaining)
    remaining_percent = (remaining / total * 100) if total else 0.0

    return {
        "total_gpu_seconds": round(total, 3),
        "remaining_gpu_seconds": round(remaining, 3),
        "used_gpu_seconds": round(used, 3),
        "remaining_percent": round(remaining_percent, 2),
        "resets_at": payload.get("resetsAt"),
        "overquota_used_gpu_seconds": round(overquota_used, 3),
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }
