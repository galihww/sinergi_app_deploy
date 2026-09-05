from __future__ import annotations

import os
from typing import Any, Iterator

from gradio_client import Client

GRADIO_API_NAME = "/respond"
GRADIO_EMPTY_RETRIES = 1

_INTEGER_FIELDS = ("max_new_tokens", "top_k")
_FLOAT_FIELDS = ("temperature", "top_p")
_RETRYABLE_ERROR_MARKERS = (
    "temporarily unavailable",
    "timeout",
    "timed out",
    "connection reset",
    "scheduling",
    "capacity",
)


def _client(space: str) -> Client:
    token = os.getenv("GRADIO_HF_TOKEN", "").strip() or None
    return Client(space, token=token)


def _normalize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Return a defensive copy with Gradio slider inputs as real numbers."""
    normalized = dict(payload)
    for field in _INTEGER_FIELDS:
        if field in normalized:
            normalized[field] = int(normalized[field])
    for field in _FLOAT_FIELDS:
        if field in normalized:
            normalized[field] = float(normalized[field])
    return normalized


def _result_text(value: Any) -> str:
    return "" if value is None else str(value)


def _is_retryable(error: BaseException) -> bool:
    message = str(error).lower()
    return any(marker in message for marker in _RETRYABLE_ERROR_MARKERS)


def _describe_error(error: BaseException) -> str:
    message = str(error).strip() or type(error).__name__
    lowered = message.lower()
    if "quota" in lowered or ("gpu task" in lowered and "left" in lowered):
        return (
            "Hugging Face ZeroGPU quota is insufficient for this request. "
            "Reduce Output to 1K or 4K, or try again after the quota resets."
        )
    if "expected a `float`" in lowered or "not supported between instances" in lowered:
        return (
            "Hugging Face Space rejected a generation setting because it was not numeric. "
            "Reload the page and try again."
        )
    if "timeout" in lowered or "timed out" in lowered:
        return "Hugging Face Space timed out. Try again with Output set to 1K or 4K."
    return f"Hugging Face Space request failed: {message}"


def gradio_respond(space: str, payload: dict[str, Any]) -> str:
    normalized = _normalize_payload(payload)
    for attempt in range(GRADIO_EMPTY_RETRIES + 1):
        try:
            result = _client(space).predict(
                **{**normalized, "api_name": GRADIO_API_NAME}
            )
        except Exception as error:
            if attempt < GRADIO_EMPTY_RETRIES and _is_retryable(error):
                continue
            raise RuntimeError(_describe_error(error)) from error
        text = _result_text(result)
        if text.strip():
            return text
    raise RuntimeError(
        "Hugging Face Space completed without generating text after one retry."
    )


def gradio_stream(space: str, payload: dict[str, Any]) -> Iterator[str]:
    normalized = _normalize_payload(payload)
    for attempt in range(GRADIO_EMPTY_RETRIES + 1):
        job = _client(space).submit(
            **{**normalized, "api_name": GRADIO_API_NAME}
        )
        emitted = False
        for value in job:
            text = _result_text(value)
            if text.strip():
                emitted = True
                yield text

        error = job.exception()
        if error is not None:
            if (
                not emitted
                and attempt < GRADIO_EMPTY_RETRIES
                and _is_retryable(error)
            ):
                continue
            raise RuntimeError(_describe_error(error)) from error

        if emitted:
            return

        # Some Gradio versions retain only the final value instead of exposing
        # generator updates through iteration. Recover it before calling the
        # response genuinely empty.
        text = _result_text(job.result())
        if text.strip():
            yield text
            return

    raise RuntimeError(
        "Hugging Face Space completed without generating text after one retry."
    )
